"""
Sherlock Backend — Signal Processors

Each processor computes one "weak signal" score for candidate identification.
Scores are in [0, 1] where higher = more likely to be the candidate.
"""
from __future__ import annotations
from typing import Optional
from engine.participant_state import ParticipantState
from utils.fuzzy_match import best_match_score
from utils.text_classify import classify_utterance_batch

try:
    from scipy.stats import beta as beta_dist
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False


class MetadataSignalProcessor:
    """
    Compares participant display name against the expected candidate name.
    Uses fuzzy matching (max of Levenshtein, Jaro-Winkler, token-set ratio).
    """

    def compute(
        self, participant: ParticipantState, expected_name: Optional[str]
    ) -> float:
        if not expected_name or not participant.current_display_name:
            return 0.0

        score = best_match_score(
            participant.current_display_name, expected_name
        )

        # Penalize clearly generic/device names
        generic_patterns = [
            "macbook", "iphone", "ipad", "pixel", "galaxy",
            "user 1", "user 2", "user 3", "guest",
            "unknown", "participant",
        ]
        name_lower = participant.current_display_name.lower().strip()
        if any(pattern in name_lower for pattern in generic_patterns):
            score *= 0.1  # Heavily penalize generic names

        return min(score, 1.0)


class SpeakingSignalProcessor:
    """
    Evaluates speaking ratio against the expected candidate distribution.

    Candidates typically speak 50-75% of the time in a 1:1 interview.
    Uses a Beta distribution likelihood ratio if scipy is available,
    otherwise a simpler triangular heuristic.
    """

    def compute(self, participant: ParticipantState) -> float:
        ratio = participant.speaking_ratio

        if participant.total_presence_ms < 30_000:
            # Less than 30 seconds of data — unreliable
            return 0.5  # Neutral

        if HAS_SCIPY:
            # Candidate distribution: Beta(6, 4) — peaks around 0.6
            candidate_likelihood = beta_dist.pdf(ratio, 6, 4)
            # Non-candidate distribution: Beta(3, 7) — peaks around 0.3
            noncand_likelihood = beta_dist.pdf(ratio, 3, 7)

            # Likelihood ratio, normalized to [0, 1]
            total = candidate_likelihood + noncand_likelihood
            if total == 0:
                return 0.5
            return candidate_likelihood / total
        else:
            # Triangular heuristic: peak at 0.6, tails at 0.1 and 0.95
            if ratio < 0.1:
                return 0.1
            elif ratio < 0.35:
                return 0.1 + (ratio - 0.1) * (0.5 / 0.25)
            elif ratio < 0.75:
                return 0.6 + (ratio - 0.35) * (0.4 / 0.4)
            elif ratio < 0.95:
                return 1.0 - (ratio - 0.75) * (0.3 / 0.2)
            else:
                return 0.7  # Very high ratio — possible but suspicious

    def compute_utterance_length_signal(self, participant: ParticipantState) -> float:
        """
        Candidates give longer responses (15-45s avg).
        Interviewers give shorter prompts (5-15s avg).
        """
        avg_ms = participant.avg_utterance_length_ms
        if avg_ms == 0 or len(participant.utterance_lengths_ms) < 2:
            return 0.5  # Neutral

        # Map avg utterance length to a score
        # Peak at 25s (25000ms), low at <5s and >60s
        if avg_ms < 5000:
            return 0.2
        elif avg_ms < 15000:
            return 0.2 + (avg_ms - 5000) / 10000 * 0.5
        elif avg_ms < 45000:
            return 0.7 + (avg_ms - 15000) / 30000 * 0.3
        else:
            return 0.8  # Very long — still likely candidate


class SemanticSignalProcessor:
    """
    Analyzes transcript chunks to determine if participant is answering
    questions (candidate behavior) or asking them (interviewer behavior).
    """

    def compute(self, participant: ParticipantState) -> float:
        if not participant.recent_utterances:
            return 0.5  # Neutral — no transcript data yet

        # Classify recent utterances
        role_dist = classify_utterance_batch(participant.recent_utterances)
        answer_ratio = role_dist.get("answering", 0.25)

        # answering > 0.5 is a strong candidate signal
        return min(answer_ratio * 1.3, 1.0)  # Slight boost, cap at 1.0


class VisualSignalProcessor:
    """
    Camera presence signal — candidates almost always have camera on.
    """

    def compute(self, participant: ParticipantState) -> float:
        if participant.camera_on:
            return 0.85
        else:
            # Camera off — less likely to be candidate, but not impossible
            return 0.25


# ─── Singleton instances ────────────────────────────────────────────

metadata_processor = MetadataSignalProcessor()
speaking_processor = SpeakingSignalProcessor()
semantic_processor = SemanticSignalProcessor()
visual_processor = VisualSignalProcessor()
