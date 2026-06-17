"""
Tests for individual signal processors.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import pytest
from engine.participant_state import ParticipantState
from engine.signal_processors import (
    metadata_processor,
    speaking_processor,
    semantic_processor,
    visual_processor,
)

def test_metadata_signal_processor():
    # Exact match
    p = ParticipantState(id="1", interview_id="i1", current_display_name="Aarav Sharma")
    score = metadata_processor.compute(p, "Aarav Sharma")
    assert score == 1.0

    # Fuzzy match
    score = metadata_processor.compute(p, "aarav sharma")
    assert score == 1.0
    
    score = metadata_processor.compute(p, "Aarav S.")
    assert score >= 0.7

    # Generic name penalty
    p_generic = ParticipantState(id="2", interview_id="i1", current_display_name="MacBook Pro")
    score_generic = metadata_processor.compute(p_generic, "Aarav Sharma")
    assert score_generic < 0.1

    # No expected name
    assert metadata_processor.compute(p, None) == 0.0


def test_speaking_signal_processor():
    p = ParticipantState(id="1", interview_id="i1")
    
    # Too little presence time (<30 seconds)
    p.total_presence_ms = 10_000
    p.speaking_duration_ms = 6000
    assert speaking_processor.compute(p) == 0.5

    # 5 minutes presence, 60% speaking (peaks candidate distribution Beta(6,4))
    p.total_presence_ms = 300_000
    p.speaking_duration_ms = 180_000
    p.speaking_turn_count = 10
    p.utterance_lengths_ms = [18000] * 10
    score = speaking_processor.compute(p)
    # With scipy: candidate Beta(6,4) pdf(0.6) = 2.0736, noncand Beta(3,7) pdf(0.6) = 0.5038.
    # normalized = 2.0736 / (2.0736 + 0.5038) = ~0.804
    assert score > 0.7

    # 5 minutes presence, 15% speaking (peaks interviewer distribution Beta(3,7))
    p.speaking_duration_ms = 45_000
    p.utterance_lengths_ms = [4500] * 10
    score_low = speaking_processor.compute(p)
    assert score_low < 0.4

    # Utterance length signal
    assert speaking_processor.compute_utterance_length_signal(p) < 0.5  # average length is 4.5s
    p.utterance_lengths_ms = [25000, 30000]
    assert speaking_processor.compute_utterance_length_signal(p) > 0.6  # average length 27.5s


def test_semantic_signal_processor():
    p = ParticipantState(id="1", interview_id="i1")
    
    # No transcript
    assert semantic_processor.compute(p) == 0.5

    # Answering utterances
    p.recent_utterances = [
        "Yes, in my previous role I built a real-time tracking system.",
        "I would approach this database design by normalization.",
    ]
    score = semantic_processor.compute(p)
    assert score > 0.7

    # Asking utterances
    p.recent_utterances = [
        "Can you explain your database schema?",
        "What are the latency targets for this system?",
    ]
    score_asking = semantic_processor.compute(p)
    assert score_asking < 0.4


def test_visual_signal_processor():
    p = ParticipantState(id="1", interview_id="i1")
    
    p.camera_on = True
    assert visual_processor.compute(p) == 0.85

    p.camera_on = False
    assert visual_processor.compute(p) == 0.25
