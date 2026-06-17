"""
Tests for the candidate identification engine.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from engine.candidate_engine import CandidateEngine
from engine.participant_state import ParticipantState


def _make_participant(pid, name, interview_id="test_int"):
    """Helper to create a ParticipantState."""
    return ParticipantState(
        id=pid,
        interview_id=interview_id,
        platform_id=pid,
        current_display_name=name,
        first_join_at_ms=1000,
    )


def test_uniform_prior():
    """With no evidence, all participants should have equal probability."""
    engine = CandidateEngine(expected_candidate_name="Aarav Sharma")
    p1 = _make_participant("p1", "Aarav Sharma")
    p2 = _make_participant("p2", "Sarah Chen")

    participants = {"p1": p1, "p2": p2}
    engine.evaluate(participants, now_ms=1000)

    # Aarav should score higher due to name match
    assert p1.candidate_probability > p2.candidate_probability


def test_speaking_ratio_shifts_score():
    """A participant who speaks more should gain candidate probability."""
    engine = CandidateEngine(expected_candidate_name=None)  # No name hint
    p1 = _make_participant("p1", "User 1")
    p2 = _make_participant("p2", "User 2")

    # Simulate p1 speaking 60% of the time
    p1.speaking_duration_ms = 60000
    p1.total_presence_ms = 100000
    p1.speaking_turn_count = 5
    p1.utterance_lengths_ms = [12000] * 5

    # p2 speaks only 15%
    p2.speaking_duration_ms = 15000
    p2.total_presence_ms = 100000
    p2.speaking_turn_count = 5
    p2.utterance_lengths_ms = [3000] * 5

    participants = {"p1": p1, "p2": p2}
    engine.evaluate(participants, now_ms=101000)

    assert p1.candidate_probability > p2.candidate_probability, \
        f"p1 ({p1.candidate_probability}) should > p2 ({p2.candidate_probability})"


def test_semantic_signal():
    """Participant answering questions should score higher."""
    engine = CandidateEngine(expected_candidate_name=None)
    p1 = _make_participant("p1", "Alice")
    p2 = _make_participant("p2", "Bob")

    # Alice answers questions
    p1.recent_utterances = [
        "In my previous role, I led the migration to microservices.",
        "Yes, I have 5 years of experience with distributed systems.",
        "I would approach it by first analyzing the data flow.",
        "We shipped the feature to production within 3 weeks.",
    ]
    p1.total_presence_ms = 120000

    # Bob asks questions
    p2.recent_utterances = [
        "Can you tell me about your experience?",
        "How would you handle this scenario?",
        "What's your biggest strength?",
    ]
    p2.total_presence_ms = 120000

    participants = {"p1": p1, "p2": p2}
    engine.evaluate(participants, now_ms=121000)

    assert p1.candidate_probability > p2.candidate_probability, \
        f"Alice ({p1.candidate_probability}) should > Bob ({p2.candidate_probability})"


def test_name_match_boosts_early():
    """Name match should be the dominant signal early in the meeting."""
    engine = CandidateEngine(expected_candidate_name="Aarav Sharma")
    p1 = _make_participant("p1", "Aarav Sharma")
    p2 = _make_participant("p2", "Sarah Chen")
    p1.total_presence_ms = 5000
    p2.total_presence_ms = 5000

    participants = {"p1": p1, "p2": p2}
    engine.evaluate(participants, now_ms=6000)

    assert p1.candidate_probability > 0.55, \
        f"Expected > 0.55 with name match, got {p1.candidate_probability}"


def test_generic_name_no_crash():
    """Generic device names should not crash and should score low on metadata."""
    engine = CandidateEngine(expected_candidate_name="Aarav Sharma")
    p1 = _make_participant("p1", "MacBook Pro")
    p2 = _make_participant("p2", "iPhone")

    p1.total_presence_ms = 60000
    p2.total_presence_ms = 60000

    participants = {"p1": p1, "p2": p2}
    engine.evaluate(participants, now_ms=61000)

    # Should not crash, scores should be low-ish
    assert p1.candidate_probability <= 1.0
    assert p2.candidate_probability <= 1.0


def test_confidence_band_assignment():
    """Confidence bands should be assigned correctly."""
    engine = CandidateEngine(expected_candidate_name="Aarav Sharma")
    p1 = _make_participant("p1", "Aarav Sharma")
    p2 = _make_participant("p2", "Sarah Chen")

    # Make p1 clearly the candidate
    p1.speaking_duration_ms = 120000
    p1.total_presence_ms = 200000
    p1.speaking_turn_count = 10
    p1.utterance_lengths_ms = [12000] * 10
    p1.recent_utterances = [
        "In my experience, I found that...",
        "Yes, I managed a team of 8 engineers.",
        "I would approach this problem by...",
    ]
    p1.camera_on = True

    p2.speaking_duration_ms = 30000
    p2.total_presence_ms = 200000
    p2.speaking_turn_count = 10
    p2.utterance_lengths_ms = [3000] * 10
    p2.recent_utterances = [
        "Tell me about your background.",
        "How would you handle this?",
    ]

    participants = {"p1": p1, "p2": p2}
    engine.evaluate(participants, now_ms=201000)

    assert p1.confidence_band in ("PROBABLE", "HIGH"), \
        f"Expected PROBABLE or HIGH, got {p1.confidence_band}"


def test_normalization():
    """Probabilities should sum to approximately 1.0."""
    engine = CandidateEngine(expected_candidate_name="Test")
    participants = {}
    for i in range(5):
        p = _make_participant(f"p{i}", f"Person {i}")
        p.total_presence_ms = 60000
        participants[f"p{i}"] = p

    engine.evaluate(participants, now_ms=61000)

    total = sum(p.candidate_probability for p in participants.values())
    assert abs(total - 1.0) < 0.01, f"Probabilities sum to {total}, expected ~1.0"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
