"""
Sherlock Backend — Interviews REST Router
"""
from fastapi import APIRouter, HTTPException
from models import InterviewCreate, InterviewResponse, InterviewUpdate, generate_id
from database import get_db
from schemas import row_to_dict
import json

router = APIRouter(prefix="/api/interviews", tags=["interviews"])


@router.post("", response_model=InterviewResponse, status_code=201)
async def create_interview(body: InterviewCreate):
    """Create a new interview session."""
    interview_id = generate_id()
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO interviews (id, title, platform, expected_candidate_name,
               expected_candidate_email, meeting_url)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (interview_id, body.title, body.platform,
             body.expected_candidate_name, body.expected_candidate_email,
             body.meeting_url),
        )
        await db.commit()
        row = await db.execute_fetchall(
            "SELECT * FROM interviews WHERE id = ?", (interview_id,)
        )
        return row_to_dict(row[0])
    finally:
        await db.close()


@router.get("", response_model=list[InterviewResponse])
async def list_interviews():
    """List all interviews, most recent first."""
    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            "SELECT * FROM interviews ORDER BY created_at DESC LIMIT 50"
        )
        return [row_to_dict(r) for r in rows]
    finally:
        await db.close()


@router.get("/{interview_id}", response_model=InterviewResponse)
async def get_interview(interview_id: str):
    """Get a single interview by ID."""
    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            "SELECT * FROM interviews WHERE id = ?", (interview_id,)
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Interview not found")
        return row_to_dict(rows[0])
    finally:
        await db.close()


@router.patch("/{interview_id}", response_model=InterviewResponse)
async def update_interview(interview_id: str, body: InterviewUpdate):
    """Update interview fields."""
    db = await get_db()
    try:
        # Build dynamic SET clause
        updates = {}
        if body.title is not None:
            updates["title"] = body.title
        if body.expected_candidate_name is not None:
            updates["expected_candidate_name"] = body.expected_candidate_name
        if body.status is not None:
            updates["status"] = body.status

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        set_clause = ", ".join(f"{k} = ?" for k in updates.keys())
        values = list(updates.values()) + [interview_id]

        await db.execute(
            f"UPDATE interviews SET {set_clause}, updated_at = datetime('now') WHERE id = ?",
            values,
        )
        await db.commit()

        rows = await db.execute_fetchall(
            "SELECT * FROM interviews WHERE id = ?", (interview_id,)
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Interview not found")
        return row_to_dict(rows[0])
    finally:
        await db.close()


@router.get("/{interview_id}/participants")
async def get_participants(interview_id: str):
    """Get all participants for an interview."""
    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            """SELECT * FROM participants
               WHERE interview_id = ?
               ORDER BY candidate_probability DESC""",
            (interview_id,),
        )
        from schemas import participant_row_to_response
        return [participant_row_to_response(row_to_dict(r)) for r in rows]
    finally:
        await db.close()


@router.get("/{interview_id}/snapshots")
async def get_confidence_snapshots(interview_id: str, limit: int = 500):
    """Get confidence snapshot history for an interview."""
    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            """SELECT * FROM confidence_snapshots
               WHERE interview_id = ?
               ORDER BY timestamp_ms ASC
               LIMIT ?""",
            (interview_id, limit),
        )
        results = []
        for r in rows:
            d = row_to_dict(r)
            d["signal_scores"] = json.loads(d.get("signal_scores", "{}"))
            results.append(d)
        return results
    finally:
        await db.close()
