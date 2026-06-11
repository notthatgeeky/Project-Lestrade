"""
Sherlock Backend — Lightweight Text Classifier

Keyword-based utterance role classification for Phase 1.
Classifies transcript chunks into: answering, asking, small_talk, meta.

No ML models needed — uses pattern matching heuristics tuned for
interview conversations. Will be replaced by a fine-tuned classifier in Phase 3.
"""
from __future__ import annotations
import re
from typing import Dict, List


# ─── Pattern definitions ────────────────────────────────────────────

ANSWER_STARTERS = [
    r"^(so|yes|yeah|sure|absolutely|definitely|right)\b",
    r"^(in my|at my|during my|when i|i have|i was|i am|i did|i would|i think)\b",
    r"^(we (built|designed|implemented|created|managed|developed|shipped))\b",
    r"^(the (approach|way|method|solution) (i|we))\b",
    r"^(that'?s a (great|good|interesting) question)\b",
]

ANSWER_INDICATORS = [
    r"\b(my experience|my role|my team|my background)\b",
    r"\b(i led|i managed|i built|i designed|i architected)\b",
    r"\b(we shipped|we deployed|we launched|we migrated)\b",
    r"\b(years of experience|worked (at|for|with)|previous (role|company|position))\b",
    r"\b(the challenge was|the problem was|the solution was)\b",
    r"\b(i learned|i realized|i discovered)\b",
]

QUESTION_INDICATORS = [
    r"\?\s*$",
    r"^(can you|could you|would you|tell me|describe|explain|walk me|how (would|do|did))\b",
    r"^(what (is|are|was|were|would|do|did))\b",
    r"^(why (did|do|would|is))\b",
    r"^(have you (ever)?)\b",
    r"^(let'?s (talk|discuss|move|dive))\b",
]

SMALL_TALK_INDICATORS = [
    r"\b(how are you|nice to meet|pleasure|thanks for (joining|coming|your time))\b",
    r"\b(can you hear me|is (my|the) (audio|video|screen))\b",
    r"\b(good (morning|afternoon|evening)|hello|hey|hi there)\b",
    r"\b(have a (good|great|nice) (day|rest|one|weekend))\b",
]

META_INDICATORS = [
    r"\b(next (question|topic|section|round))\b",
    r"\b(move on|moving on|let'?s (move|proceed|continue))\b",
    r"\b(any questions|do you have questions|before we (end|wrap))\b",
    r"\b(we'?re (running|almost) out of time)\b",
    r"\b(that'?s (all|it) (from|for) (my|our) (side|end))\b",
]

# Compile patterns
_ANSWER_START_RE = [re.compile(p, re.IGNORECASE) for p in ANSWER_STARTERS]
_ANSWER_IND_RE = [re.compile(p, re.IGNORECASE) for p in ANSWER_INDICATORS]
_QUESTION_RE = [re.compile(p, re.IGNORECASE) for p in QUESTION_INDICATORS]
_SMALL_TALK_RE = [re.compile(p, re.IGNORECASE) for p in SMALL_TALK_INDICATORS]
_META_RE = [re.compile(p, re.IGNORECASE) for p in META_INDICATORS]


def classify_utterance(text: str) -> Dict[str, float]:
    """
    Classify a single utterance into role probabilities.
    Returns dict with keys: answering, asking, small_talk, meta.
    Values sum to ~1.0.
    """
    if not text or not text.strip():
        return {"answering": 0.25, "asking": 0.25, "small_talk": 0.25, "meta": 0.25}

    text = text.strip()
    scores = {"answering": 0.0, "asking": 0.0, "small_talk": 0.0, "meta": 0.0}

    # Count pattern matches
    for p in _ANSWER_START_RE:
        if p.search(text):
            scores["answering"] += 2.0  # Starters are strong signals
    for p in _ANSWER_IND_RE:
        if p.search(text):
            scores["answering"] += 1.0
    for p in _QUESTION_RE:
        if p.search(text):
            scores["asking"] += 1.5
    for p in _SMALL_TALK_RE:
        if p.search(text):
            scores["small_talk"] += 2.0
    for p in _META_RE:
        if p.search(text):
            scores["meta"] += 2.0

    # Self-referential language is a strong answering signal
    first_person_count = len(re.findall(r"\b(i|my|me|we|our)\b", text, re.IGNORECASE))
    if first_person_count >= 3:
        scores["answering"] += 1.5
    elif first_person_count >= 1:
        scores["answering"] += 0.5

    # Long utterances are more likely answers
    word_count = len(text.split())
    if word_count > 30:
        scores["answering"] += 1.0
    elif word_count < 10:
        scores["asking"] += 0.3

    # Normalize to probabilities
    total = sum(scores.values())
    if total == 0:
        return {"answering": 0.25, "asking": 0.25, "small_talk": 0.25, "meta": 0.25}

    return {k: round(v / total, 4) for k, v in scores.items()}


def classify_utterance_batch(utterances: List[str]) -> Dict[str, float]:
    """
    Classify a batch of utterances and return the aggregate role distribution.
    Used by the semantic signal processor on a participant's recent utterances.
    """
    if not utterances:
        return {"answering": 0.25, "asking": 0.25, "small_talk": 0.25, "meta": 0.25}

    totals = {"answering": 0.0, "asking": 0.0, "small_talk": 0.0, "meta": 0.0}
    for utt in utterances:
        scores = classify_utterance(utt)
        for k, v in scores.items():
            totals[k] += v

    n = len(utterances)
    return {k: round(v / n, 4) for k, v in totals.items()}
