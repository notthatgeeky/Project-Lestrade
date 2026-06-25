"""
Sherlock Backend — Pydantic Models

Request/response models for the REST API and WebSocket messages.
"""
from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid


def generate_id() -> str:
    return str(uuid.uuid4())


# ─── Interview Models ───────────────────────────────────────────────

class InterviewCreate(BaseModel):
    title: str = ""
    platform: str = "GOOGLE_MEET"
    expected_candidate_name: Optional[str] = None
    expected_candidate_email: Optional[str] = None
    meeting_url: Optional[str] = None


class InterviewResponse(BaseModel):
    id: str
    title: str
    platform: str
    expected_candidate_name: Optional[str]
    expected_candidate_email: Optional[str]
    status: str
    meeting_url: Optional[str]
    started_at: Optional[str]
    ended_at: Optional[str]
    identified_participant_id: Optional[str]
    overall_fraud_score: Optional[float]
    overall_fraud_tier: Optional[str]
    created_at: str


class InterviewUpdate(BaseModel):
    title: Optional[str] = None
    expected_candidate_name: Optional[str] = None
    status: Optional[str] = None


# ─── Participant Models ─────────────────────────────────────────────

class ParticipantResponse(BaseModel):
    id: str
    interview_id: str
    platform_id: Optional[str]
    current_display_name: Optional[str]
    display_name_history: List[Dict[str, Any]] = []
    first_join_at: Optional[str]
    rejoin_count: int = 0
    speaking_duration_ms: int = 0
    speaking_ratio: float = 0.0
    speaking_turn_count: int = 0
    avg_utterance_length_ms: float = 0.0
    camera_on: bool = False
    camera_on_ratio: float = 0.0
    candidate_probability: float = 0.0
    confidence_band: str = "UNCERTAIN"
    is_identified_candidate: bool = False


# ─── WebSocket Event Models ─────────────────────────────────────────

class IngestEvent(BaseModel):
    """Event received from the Chrome extension via WebSocket."""
    interview_id: str
    type: str
    participant_id: Optional[str] = None
    timestamp_ms: int
    payload: Dict[str, Any] = Field(default_factory=dict)


class DashboardUpdate(BaseModel):
    """Update pushed to the dashboard via WebSocket."""
    type: str  # 'participant_update', 'score_update', 'explanation', 'full_state'
    interview_id: str
    data: Dict[str, Any] = Field(default_factory=dict)


# ─── Confidence Snapshot ────────────────────────────────────────────

class ConfidenceSnapshotResponse(BaseModel):
    participant_id: str
    timestamp_ms: int
    candidate_score: float
    confidence_band: str
    signal_scores: Dict[str, float] = {}
    delta_score: float = 0.0
    trigger_signal: Optional[str] = None
    explanation: Optional[str] = None
