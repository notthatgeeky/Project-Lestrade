"""
Sherlock Backend — Session Manager

Manages in-memory state for active interview sessions.
Routes events from the extension to participant states and the candidate engine.
Broadcasts updates to connected dashboard WebSocket clients.
"""
from __future__ import annotations
from typing import Dict, Optional, List, Any
from engine.participant_state import ParticipantState
from engine.candidate_engine import CandidateEngine
from models import IngestEvent, generate_id
from database import get_db
from schemas import serialize_json_field
import asyncio
import json
import logging
import time

logger = logging.getLogger("sherlock.session")


class InterviewSession:
    """In-memory state for one active interview."""

    def __init__(self, interview_id: str, expected_candidate_name: Optional[str] = None):
        self.interview_id = interview_id
        self.expected_candidate_name = expected_candidate_name
        self.participants: Dict[str, ParticipantState] = {}
        self.engine = CandidateEngine(expected_candidate_name=expected_candidate_name)
        self.dashboard_connections: List[Any] = []  # WebSocket connections
        self.start_time_ms: Optional[int] = None
        self._tick_task: Optional[asyncio.Task] = None
        self._running = False

    def add_dashboard_connection(self, ws):
        """Register a dashboard WebSocket for live updates."""
        if ws not in self.dashboard_connections:
            self.dashboard_connections.append(ws)

    def remove_dashboard_connection(self, ws):
        """Unregister a dashboard WebSocket."""
        if ws in self.dashboard_connections:
            self.dashboard_connections.remove(ws)

    def get_full_state_snapshot(self) -> Dict[str, Any]:
        """Get the full current state for initial dashboard load."""
        return {
            "interview_id": self.interview_id,
            "expected_candidate_name": self.expected_candidate_name,
            "start_time_ms": self.start_time_ms,
            "participants": {
                pid: p.to_dict() for pid, p in self.participants.items()
            },
        }

    async def broadcast_to_dashboard(self, message: Dict[str, Any]):
        """Send a JSON message to all connected dashboard clients."""
        dead = []
        for ws in self.dashboard_connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.dashboard_connections.remove(ws)

    def _get_or_create_participant(
        self, platform_id: str, display_name: str, timestamp_ms: int
    ) -> ParticipantState:
        """Find existing participant by platform_id or create a new one."""
        if platform_id in self.participants:
            return self.participants[platform_id]

        # Create new participant
        participant = ParticipantState(
            id=generate_id(),
            interview_id=self.interview_id,
            platform_id=platform_id,
            current_display_name=display_name,
            first_join_at_ms=timestamp_ms,
        )
        self.participants[platform_id] = participant
        logger.info(
            f"New participant: {display_name} ({platform_id}) "
            f"in interview {self.interview_id}"
        )
        return participant

    async def process_event(self, event: IngestEvent):
        """Route an incoming event to the appropriate handler."""
        if self.start_time_ms is None:
            self.start_time_ms = event.timestamp_ms

        handler = self._event_handlers.get(event.type)
        if handler:
            await handler(self, event)
        else:
            logger.debug(f"Unhandled event type: {event.type}")

        # Persist event to database (fire-and-forget)
        asyncio.create_task(self._persist_event(event))

        # Run engine evaluation
        await self._run_engine_tick(event.timestamp_ms)

    async def _handle_participant_join(self, event: IngestEvent):
        """Handle PARTICIPANT_JOIN event."""
        pid = event.participant_id or event.payload.get("platform_id", generate_id())
        name = event.payload.get("display_name", "Unknown")
        camera = event.payload.get("camera_on", False)

        p = self._get_or_create_participant(pid, name, event.timestamp_ms)
        p.is_present = True
        p.camera_on = camera
        if camera:
            p.camera_on_last_change_ms = event.timestamp_ms

        await self.broadcast_to_dashboard({
            "type": "participant_join",
            "interview_id": self.interview_id,
            "data": p.to_dict(),
        })

    async def _handle_participant_leave(self, event: IngestEvent):
        """Handle PARTICIPANT_LEAVE event."""
        pid = event.participant_id
        if pid and pid in self.participants:
            p = self.participants[pid]
            p.is_present = False
            p.last_leave_at_ms = event.timestamp_ms
            p.stop_speaking(event.timestamp_ms)  # End any active utterance

            await self.broadcast_to_dashboard({
                "type": "participant_leave",
                "interview_id": self.interview_id,
                "data": {"participant_id": pid},
            })

    async def _handle_participant_rename(self, event: IngestEvent):
        """Handle PARTICIPANT_RENAME event."""
        pid = event.participant_id
        if pid and pid in self.participants:
            new_name = event.payload.get("new_name", "")
            self.participants[pid].rename(new_name, event.timestamp_ms)
            logger.info(f"Participant {pid} renamed to '{new_name}'")

            await self.broadcast_to_dashboard({
                "type": "participant_update",
                "interview_id": self.interview_id,
                "data": self.participants[pid].to_dict(),
            })

    async def _handle_participant_state_change(self, event: IngestEvent):
        """Handle PARTICIPANT_STATE_CHANGE (camera, mute, etc.)."""
        pid = event.participant_id
        if pid and pid in self.participants:
            p = self.participants[pid]
            if "camera_on" in event.payload:
                p.set_camera(event.payload["camera_on"], event.timestamp_ms)

    async def _handle_speaking_start(self, event: IngestEvent):
        """Handle SPEAKING_START event."""
        pid = event.participant_id
        if pid and pid in self.participants:
            self.participants[pid].start_speaking(event.timestamp_ms)

    async def _handle_speaking_stop(self, event: IngestEvent):
        """Handle SPEAKING_STOP event."""
        pid = event.participant_id
        if pid and pid in self.participants:
            self.participants[pid].stop_speaking(event.timestamp_ms)

    async def _handle_transcript_chunk(self, event: IngestEvent):
        """Handle TRANSCRIPT_CHUNK event — caption text from DOM."""
        # Try to attribute by participant_id first, then by speaker_name
        pid = event.participant_id
        text = event.payload.get("text", "")
        speaker_name = event.payload.get("speaker_name", "")

        if not text.strip():
            return

        # If no direct participant_id, try to match by speaker name
        if not pid and speaker_name:
            for candidate_pid, p in self.participants.items():
                if p.current_display_name and (
                    speaker_name.lower() in p.current_display_name.lower()
                    or p.current_display_name.lower() in speaker_name.lower()
                ):
                    pid = candidate_pid
                    break

        if pid and pid in self.participants:
            self.participants[pid].add_transcript(text)

    async def _run_engine_tick(self, now_ms: int):
        """Run the candidate identification engine and broadcast changes."""
        changes = self.engine.evaluate(self.participants, now_ms)

        for change in changes:
            # Broadcast score update to dashboard
            pid = change["participant_id"]
            p = self.participants.get(pid)
            if p:
                await self.broadcast_to_dashboard({
                    "type": "score_update",
                    "interview_id": self.interview_id,
                    "data": {
                        "participant": p.to_dict(),
                        "old_score": change["old_score"],
                        "delta": change["delta"],
                        "explanation": change.get("explanation"),
                    },
                })

            # Persist confidence snapshot
            if change.get("explanation"):
                asyncio.create_task(
                    self._persist_snapshot(change, now_ms)
                )

    async def _persist_event(self, event: IngestEvent):
        """Persist a raw event to the database."""
        try:
            db = await get_db()
            try:
                await db.execute(
                    """INSERT INTO realtime_events
                       (interview_id, participant_id, event_type, timestamp_ms, payload)
                       VALUES (?, ?, ?, ?, ?)""",
                    (event.interview_id, event.participant_id, event.type,
                     event.timestamp_ms, json.dumps(event.payload)),
                )
                await db.commit()
            finally:
                await db.close()
        except Exception as e:
            logger.error(f"Failed to persist event: {e}")

    async def _persist_snapshot(self, change: Dict, now_ms: int):
        """Persist a confidence snapshot to the database."""
        try:
            db = await get_db()
            try:
                await db.execute(
                    """INSERT INTO confidence_snapshots
                       (interview_id, participant_id, timestamp_ms, candidate_score,
                        confidence_band, signal_scores, delta_score, trigger_signal,
                        explanation)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        self.interview_id,
                        change["participant_id"],
                        now_ms,
                        change["new_score"],
                        change["confidence_band"],
                        json.dumps(change["signal_scores"]),
                        change["delta"],
                        change.get("trigger_signal"),
                        change.get("explanation"),
                    ),
                )
                await db.commit()
            finally:
                await db.close()
        except Exception as e:
            logger.error(f"Failed to persist snapshot: {e}")

    # Event handler dispatch table
    _event_handlers = {
        "PARTICIPANT_JOIN": _handle_participant_join,
        "PARTICIPANT_LEAVE": _handle_participant_leave,
        "PARTICIPANT_RENAME": _handle_participant_rename,
        "PARTICIPANT_STATE_CHANGE": _handle_participant_state_change,
        "SPEAKING_START": _handle_speaking_start,
        "SPEAKING_STOP": _handle_speaking_stop,
        "TRANSCRIPT_CHUNK": _handle_transcript_chunk,
    }


class SessionManager:
    """Manages all active interview sessions."""

    def __init__(self):
        self.sessions: Dict[str, InterviewSession] = {}

    async def get_or_create_session(
        self,
        interview_id: str,
        expected_candidate_name: Optional[str] = None,
    ) -> InterviewSession:
        """Get an existing session or create a new one."""
        if interview_id not in self.sessions:
            self.sessions[interview_id] = InterviewSession(
                interview_id=interview_id,
                expected_candidate_name=expected_candidate_name,
            )

            # Ensure interview exists in DB
            db = await get_db()
            try:
                rows = await db.execute_fetchall(
                    "SELECT id FROM interviews WHERE id = ?", (interview_id,)
                )
                if not rows:
                    await db.execute(
                        """INSERT INTO interviews (id, title, expected_candidate_name, status)
                           VALUES (?, ?, ?, 'LIVE')""",
                        (interview_id, f"Interview {interview_id[:8]}",
                         expected_candidate_name),
                    )
                    await db.commit()
                else:
                    await db.execute(
                        "UPDATE interviews SET status = 'LIVE' WHERE id = ?",
                        (interview_id,),
                    )
                    await db.commit()
            finally:
                await db.close()

            logger.info(f"Created session for interview {interview_id}")
        else:
            # Update expected name if provided
            session = self.sessions[interview_id]
            if expected_candidate_name and not session.expected_candidate_name:
                session.expected_candidate_name = expected_candidate_name
                session.engine.expected_candidate_name = expected_candidate_name

        return self.sessions[interview_id]

    async def process_event(self, event: IngestEvent):
        """Route an event to the correct session."""
        session = await self.get_or_create_session(event.interview_id)
        await session.process_event(event)

    def get_session(self, interview_id: str) -> Optional[InterviewSession]:
        """Get a session if it exists."""
        return self.sessions.get(interview_id)
