"""
Sherlock Backend — Explainability Generator

Produces human-readable explanations for candidate score changes.
Uses a template system keyed by (signal_type, direction).
"""
from __future__ import annotations
from typing import Optional, Dict


TEMPLATES = {
    ("metadata_match", "UP"): (
        "Display name '{display_name}' matches expected candidate "
        "'{expected_name}' with {match_pct}% similarity."
    ),
    ("metadata_match", "DOWN"): (
        "Display name changed to '{display_name}', reducing match similarity "
        "to {match_pct}% against expected '{expected_name}'."
    ),
    ("speaking_ratio", "UP"): (
        "{display_name} has spoken for {speak_pct}% of the meeting duration, "
        "consistent with a candidate interview pattern."
    ),
    ("speaking_ratio", "DOWN"): (
        "{display_name}'s speaking ratio dropped to {speak_pct}%, "
        "less consistent with candidate behavior."
    ),
    ("semantic_role", "UP"): (
        "{display_name}'s utterances are {answer_pct}% in answer-mode "
        "(responding to questions), characteristic of a candidate."
    ),
    ("semantic_role", "DOWN"): (
        "{display_name}'s utterances shifted toward question-asking mode "
        "({answer_pct}% answer-mode), less characteristic of a candidate."
    ),
    ("visual_presence", "UP"): (
        "{display_name} turned on their camera, which is typical for candidates."
    ),
    ("visual_presence", "DOWN"): (
        "{display_name} turned off their camera, which is atypical for candidates."
    ),
}


def generate_explanation(
    display_name: str,
    old_score: float,
    new_score: float,
    dominant_signal: str,
    signal_scores: Dict[str, float],
    expected_name: Optional[str] = None,
    participant_state: Optional[object] = None,
) -> str:
    """
    Generate a human-readable explanation for a candidate score change.

    Args:
        display_name: Participant's current display name
        old_score: Previous candidate probability
        new_score: New candidate probability
        dominant_signal: The signal that contributed most to the change
        signal_scores: Current per-signal scores
        expected_name: Expected candidate name from interview metadata
        participant_state: ParticipantState object for additional context

    Returns:
        Human-readable explanation string
    """
    direction = "UP" if new_score > old_score else "DOWN"
    template_key = (dominant_signal, direction)
    template = TEMPLATES.get(template_key)

    if not template:
        # Fallback generic template
        verb = "increased" if direction == "UP" else "decreased"
        return (
            f"Candidate score for {display_name} {verb} from "
            f"{old_score:.0%} to {new_score:.0%} based on {dominant_signal} signal."
        )

    # Build template context
    ctx = {
        "display_name": display_name or "Unknown",
        "expected_name": expected_name or "N/A",
        "match_pct": round(signal_scores.get("metadata_match", 0) * 100),
        "speak_pct": round(
            (participant_state.speaking_ratio * 100) if participant_state else 0
        ),
        "answer_pct": round(signal_scores.get("semantic_role", 0) * 100),
    }

    try:
        reason = template.format(**ctx)
    except (KeyError, AttributeError):
        reason = f"Score changed based on {dominant_signal} signal."

    verb = "increased" if direction == "UP" else "decreased"
    return (
        f"Candidate score for {display_name} {verb} from "
        f"{old_score:.0%} to {new_score:.0%}: {reason}"
    )


def get_dominant_signal(
    old_scores: Dict[str, float], new_scores: Dict[str, float]
) -> str:
    """
    Determine which signal contributed most to the score change.
    Returns the signal key with the largest absolute delta.
    """
    max_delta = 0.0
    dominant = "metadata_match"

    for key in new_scores:
        old_val = old_scores.get(key, 0.0)
        new_val = new_scores.get(key, 0.0)
        delta = abs(new_val - old_val)
        if delta > max_delta:
            max_delta = delta
            dominant = key

    return dominant
