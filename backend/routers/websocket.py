"""
Sherlock Backend — WebSocket Router

Two WebSocket endpoints:
  1. /ws/ingest  — receives events from the Chrome extension
  2. /ws/dashboard/{interview_id} — pushes live updates to the dashboard
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from models import IngestEvent, DashboardUpdate
import json
import logging

logger = logging.getLogger("sherlock.websocket")

router = APIRouter(tags=["websocket"])

# Import will be set by main.py after session_manager is initialized
session_manager = None


def set_session_manager(sm):
    """Called by main.py to inject the session manager dependency."""
    global session_manager
    session_manager = sm


@router.websocket("/ws/ingest")
async def websocket_ingest(ws: WebSocket):
    """
    Receive events from the Chrome extension.
    Query params: interview_id, expected_candidate_name (optional)
    """
    await ws.accept()
    interview_id = ws.query_params.get("interview_id")
    expected_name = ws.query_params.get("expected_candidate_name")

    if not interview_id:
        await ws.send_json({"error": "interview_id query param required"})
        await ws.close(code=1008)
        return

    logger.info(f"Extension connected for interview {interview_id}")

    # Ensure session exists
    await session_manager.get_or_create_session(
        interview_id, expected_candidate_name=expected_name
    )

    try:
        while True:
            data = await ws.receive_text()

            # Handle heartbeat
            if data == "ping":
                await ws.send_text("pong")
                continue

            try:
                event_data = json.loads(data)
                event = IngestEvent(**event_data)
                await session_manager.process_event(event)
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(f"Invalid event: {e}")
                await ws.send_json({"error": str(e)})

    except WebSocketDisconnect:
        logger.info(f"Extension disconnected for interview {interview_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        pass


@router.websocket("/ws/dashboard/{interview_id}")
async def websocket_dashboard(ws: WebSocket, interview_id: str):
    """
    Push live updates to the dashboard.
    On connect, sends the full current state snapshot.
    Subsequently sends incremental updates.
    """
    await ws.accept()
    logger.info(f"Dashboard connected for interview {interview_id}")

    session = await session_manager.get_or_create_session(interview_id)
    session.add_dashboard_connection(ws)

    try:
        # Send initial full state
        snapshot = session.get_full_state_snapshot()
        await ws.send_json({
            "type": "full_state",
            "interview_id": interview_id,
            "data": snapshot,
        })

        # Keep connection alive, handle any dashboard → backend messages
        while True:
            data = await ws.receive_text()
            if data == "ping":
                await ws.send_text("pong")

    except WebSocketDisconnect:
        logger.info(f"Dashboard disconnected for interview {interview_id}")
    except Exception as e:
        logger.error(f"Dashboard WebSocket error: {e}")
    finally:
        session.remove_dashboard_connection(ws)
