"""
Candidate Identification Engine

Bayesian multi-signal fusion engine that calculates a shifting probability
P(Candidate | Evidence) for each participant in real-time.

Architecture reference: Blueprint §2.3
"""
from __future__ import annotations
from typing import Dict, Optional, List, Tuple
from engine.participant_state import ParticipantState
from engine.signal_processors import (
    metadata_processor,
    speaking_processor,
    semantic_processor,
    visual_processor,
)
from engine.explainability import generate_explanation, get_dominant_signal
from config import CONFIDENCE_BANDS, SCORE_CHANGE_THRESHOLD, EXPLANATION_THRESHOLD
import logging
import time

logger = logging.getLogger("sherlock.engine")


def _lerp(a: float, b: float, t: float) -> float:
    """Linear interpolation from a to b by factor t in [0, 1]."""
    return a + (b - a) * min(max(t, 0.0), 1.0)


def _get_confidence_band(score: float) -> str:
    """Map a score to its confidence band."""
    for band, (lo, hi) in CONFIDENCE_BANDS.items():
        if lo <= score < hi:
            return band
    return "HIGH" if score >= 0.85 else "UNCERTAIN"


class CandidateEngine:
    """
    Bayesian candidate identification engine.

    Maintains posterior probabilities for each participant being the candidate.
    Updates on a 1-second tick, recomputing signal scores and applying
    Bayesian updates with time-dependent weights.
    """

    def __init__(self, expected_candidate_name: Optional[str] = None):
        self.expected_candidate_name = expected_candidate_name
        self.start_time_ms: Optional[int] = None

    def get_weights(self, elapsed_seconds: float) -> Dict[str, float]:
        """
        Time-dependent signal weights.
        Early: metadata dominates. Later: behavioral/semantic take over.
        """
        t = min(elapsed_seconds / 300.0, 1.0)  # normalize over 5 minutes
        return {
            "metadata_match": _lerp(0.35, 0.10, t),
            "speaking_ratio": _lerp(0.25, 0.35, t),
            "semantic_role":  _lerp(0.25, 0.35, t),
            "visual_presence": _lerp(0.15, 0.20, t),
        }

    def evaluate(
        self, participants: Dict[str, ParticipantState], now_ms: int
    ) -> List[Dict]:
        """
        Run one evaluation tick across all participants.

        Args:
            participants: Map of participant_id → ParticipantState
            now_ms: Current timestamp in milliseconds

        Returns:
            List of score change records (for snapshots/explanations)
        """
        if not participants:
            return []

        if self.start_time_ms is None:
            self.start_time_ms = now_ms

        elapsed_s = (now_ms - self.start_time_ms) / 1000.0
        weights = self.get_weights(elapsed_s)

        # Update presence durations
        for p in participants.values():
            p.update_presence(now_ms)

        # Step 1: Compute raw signal scores for each participant
        raw_scores = {}
        for pid, p in participants.items():
            raw_scores[pid] = {
                "metadata_match": metadata_processor.compute(
                    p, self.expected_candidate_name
                ),
                "speaking_ratio": speaking_processor.compute(p),
                "semantic_role": semantic_processor.compute(p),
                "visual_presence": visual_processor.compute(p),
            }

        # Step 2: Compute weighted composite score per participant
        composite = {}
        for pid, scores in raw_scores.items():
            composite[pid] = sum(
                scores[signal] * weights[signal] for signal in weights
            )

        # Step 3: Normalize to probabilities (softmax-like)
        total = sum(composite.values())
        if total <= 0:
            # All zeros — distribute uniformly
            n = len(composite)
            for pid in composite:
                composite[pid] = 1.0 / n if n > 0 else 0.0
        else:
            for pid in composite:
                composite[pid] = composite[pid] / total

        # Step 4: Update participant states and detect changes
        changes = []
        for pid, p in participants.items():
            old_score = p.candidate_probability
            old_signals = dict(p.signal_scores)
            new_score = composite[pid]
            new_signals = raw_scores[pid]

            p.candidate_probability = new_score
            p.signal_scores = new_signals
            p.confidence_band = _get_confidence_band(new_score)

            delta = abs(new_score - old_score)

            if delta >= SCORE_CHANGE_THRESHOLD:
                change_record = {
                    "participant_id": pid,
                    "old_score": old_score,
                    "new_score": new_score,
                    "delta": delta,
                    "confidence_band": p.confidence_band,
                    "signal_scores": new_signals,
                    "timestamp_ms": now_ms,
                    "explanation": None,
                }

                # Generate explanation for significant changes
                if delta >= EXPLANATION_THRESHOLD:
                    dominant = get_dominant_signal(old_signals, new_signals)
                    change_record["trigger_signal"] = dominant
                    change_record["explanation"] = generate_explanation(
                        display_name=p.current_display_name,
                        old_score=old_score,
                        new_score=new_score,
                        dominant_signal=dominant,
                        signal_scores=new_signals,
                        expected_name=self.expected_candidate_name,
                        participant_state=p,
                    )

                changes.append(change_record)

        return changes
