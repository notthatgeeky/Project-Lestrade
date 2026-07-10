"""
Sherlock Backend — Participant State

Dataclass representing the real-time state of a single participant,
as defined in the architecture blueprint §2.2.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import time


@dataclass
class ParticipantState:
    """Mutable state for one participant in an active interview session."""

    # Identity
    id: str
    interview_id: str
    platform_id: Optional[str] = None
    current_display_name: str = ""
    display_name_history: List[Dict[str, Any]] = field(default_factory=list)

    # Temporal
    first_join_at_ms: int = 0
    last_leave_at_ms: Optional[int] = None
    rejoin_count: int = 0
    total_presence_ms: int = 0
    is_present: bool = True

    # Audio / behavioral
    speaking_duration_ms: int = 0
    speaking_turn_count: int = 0
    current_utterance_start_ms: Optional[int] = None  # None = not speaking
    utterance_lengths_ms: List[int] = field(default_factory=list)

    # Visual
    camera_on: bool = False
    camera_on_duration_ms: int = 0
    camera_on_last_change_ms: int = 0

    # Semantic
    utterances: List[str] = field(default_factory=list)  # all transcript chunks
    recent_utterances: List[str] = field(default_factory=list)  # last 10

    # Candidate identification
    candidate_probability: float = 0.0
    confidence_band: str = "UNCERTAIN"
    signal_scores: Dict[str, float] = field(default_factory=lambda: {
        "metadata_match": 0.0,
        "speaking_ratio": 0.0,
        "semantic_role": 0.0,
        "visual_presence": 0.0,
    })

    @property
    def speaking_ratio(self) -> float:
        """Ratio of this participant's speaking time to their total presence time."""
        if self.total_presence_ms <= 0:
            return 0.0
        return min(self.speaking_duration_ms / self.total_presence_ms, 1.0)

    @property
    def avg_utterance_length_ms(self) -> float:
        """Average length of completed utterances in ms."""
        if not self.utterance_lengths_ms:
            return 0.0
        return sum(self.utterance_lengths_ms) / len(self.utterance_lengths_ms)

    @property
    def camera_on_ratio(self) -> float:
        """Ratio of time camera was on to total presence time."""
        if self.total_presence_ms <= 0:
            return 0.0
        return min(self.camera_on_duration_ms / self.total_presence_ms, 1.0)

    def update_presence(self, now_ms: int):
        """Update cumulative presence duration."""
        if self.is_present and self.first_join_at_ms > 0:
            self.total_presence_ms = now_ms - self.first_join_at_ms

    def start_speaking(self, timestamp_ms: int):
        """Record the start of a speaking turn."""
        if self.current_utterance_start_ms is None:
            # TODO: Add a minimum silence threshold to prevent micro-interruptions from counting as turns
            self.current_utterance_start_ms = timestamp_ms
            self.speaking_turn_count += 1
            # print(f"DEBUG: {self.current_display_name} started speaking at {timestamp_ms}")

    def stop_speaking(self, timestamp_ms: int):
        """Record the end of a speaking turn."""
        if self.current_utterance_start_ms is not None:
            duration = timestamp_ms - self.current_utterance_start_ms
            self.speaking_duration_ms += duration
            self.utterance_lengths_ms.append(duration)
            self.current_utterance_start_ms = None

    def add_transcript(self, text: str):
        """Add a transcript chunk."""
        self.utterances.append(text)
        self.recent_utterances.append(text)
        # Keep only last 10
        if len(self.recent_utterances) > 10:
            self.recent_utterances = self.recent_utterances[-10:]

    def rename(self, new_name: str, timestamp_ms: int):
        """Record a display name change."""
        self.display_name_history.append({
            "name": self.current_display_name,
            "changed_to": new_name,
            "observed_at_ms": timestamp_ms,
        })
        self.current_display_name = new_name

    def set_camera(self, on: bool, timestamp_ms: int):
        """Update camera state and accumulate camera-on duration."""
        if self.camera_on and not on:
            # Camera turning off — accumulate duration
            self.camera_on_duration_ms += (timestamp_ms - self.camera_on_last_change_ms)
        elif not self.camera_on and on:
            # Camera turning on
            self.camera_on_last_change_ms = timestamp_ms
        self.camera_on = on

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a dictionary for API/WebSocket responses."""
        return {
            "id": str(self.id),
            "interview_id": str(self.interview_id),
            "platform_id": str(self.platform_id) if self.platform_id else None,
            "current_display_name": str(self.current_display_name),
            "display_name_history": self.display_name_history,
            "first_join_at_ms": int(self.first_join_at_ms),
            "is_present": bool(self.is_present),
            "rejoin_count": int(self.rejoin_count),
            "total_presence_ms": int(self.total_presence_ms),
            "speaking_duration_ms": int(self.speaking_duration_ms),
            "speaking_ratio": float(round(self.speaking_ratio, 4)),
            "speaking_turn_count": int(self.speaking_turn_count),
            "avg_utterance_length_ms": float(round(self.avg_utterance_length_ms, 1)),
            "camera_on": bool(self.camera_on),
            "camera_on_ratio": float(round(self.camera_on_ratio, 4)),
            "recent_utterances": self.recent_utterances[-5:],
            "candidate_probability": float(round(self.candidate_probability, 4)),
            "confidence_band": str(self.confidence_band),
            "signal_scores": {
                k: float(round(v, 4)) for k, v in self.signal_scores.items()
            },
            "is_identified_candidate": bool(self.candidate_probability >= 0.65),
        }


# docs
