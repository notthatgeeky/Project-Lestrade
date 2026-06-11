"""
Sherlock Backend — Fuzzy String Matching

Provides Levenshtein similarity, Jaro-Winkler, and token-set ratio
for matching participant display names against expected candidate names.

Uses rapidfuzz if available, falls back to pure Python.
"""
from __future__ import annotations
from typing import Optional

try:
    from rapidfuzz import fuzz as rf_fuzz
    from rapidfuzz.distance import Levenshtein as rf_levenshtein
    from rapidfuzz.distance import JaroWinkler as rf_jaro
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False


def _normalize(s: Optional[str]) -> str:
    """Lowercase, strip, collapse whitespace."""
    if not s:
        return ""
    return " ".join(s.lower().strip().split())


def levenshtein_similarity(a: str, b: str) -> float:
    """
    Normalized Levenshtein similarity in [0, 1].
    1.0 = identical, 0.0 = completely different.
    """
    a, b = _normalize(a), _normalize(b)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0

    if HAS_RAPIDFUZZ:
        dist = rf_levenshtein.distance(a, b)
        max_len = max(len(a), len(b))
        return 1.0 - (dist / max_len) if max_len > 0 else 1.0

    # Pure Python Levenshtein
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, n + 1):
            temp = dp[j]
            if a[i - 1] == b[j - 1]:
                dp[j] = prev
            else:
                dp[j] = 1 + min(prev, dp[j], dp[j - 1])
            prev = temp
    max_len = max(m, n)
    return 1.0 - (dp[n] / max_len) if max_len > 0 else 1.0


def jaro_winkler_similarity(a: str, b: str) -> float:
    """
    Jaro-Winkler similarity in [0, 1].
    Gives extra weight to common prefixes (handles "Chitransh S." vs "Chitransh Srivastava").
    """
    a, b = _normalize(a), _normalize(b)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0

    if HAS_RAPIDFUZZ:
        return rf_jaro.normalized_similarity(a, b)

    # Pure Python Jaro-Winkler
    s1_len, s2_len = len(a), len(b)
    match_distance = max(s1_len, s2_len) // 2 - 1
    if match_distance < 0:
        match_distance = 0

    s1_matches = [False] * s1_len
    s2_matches = [False] * s2_len
    matches = 0
    transpositions = 0

    for i in range(s1_len):
        start = max(0, i - match_distance)
        end = min(i + match_distance + 1, s2_len)
        for j in range(start, end):
            if s2_matches[j] or a[i] != b[j]:
                continue
            s1_matches[i] = True
            s2_matches[j] = True
            matches += 1
            break

    if matches == 0:
        return 0.0

    k = 0
    for i in range(s1_len):
        if not s1_matches[i]:
            continue
        while not s2_matches[k]:
            k += 1
        if a[i] != b[k]:
            transpositions += 1
        k += 1

    jaro = (matches / s1_len + matches / s2_len +
            (matches - transpositions / 2) / matches) / 3

    # Winkler boost for common prefix (up to 4 chars)
    prefix_len = 0
    for i in range(min(4, s1_len, s2_len)):
        if a[i] == b[i]:
            prefix_len += 1
        else:
            break

    return jaro + prefix_len * 0.1 * (1 - jaro)


def token_set_ratio(a: str, b: str) -> float:
    """
    Token-set similarity: handles word reordering.
    "Srivastava, Chitransh" vs "Chitransh Srivastava" → high score.
    """
    a, b = _normalize(a), _normalize(b)
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0

    if HAS_RAPIDFUZZ:
        return rf_fuzz.token_set_ratio(a, b) / 100.0

    # Pure Python: Jaccard-like on token sets
    tokens_a = set(a.split())
    tokens_b = set(b.split())
    if not tokens_a and not tokens_b:
        return 1.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union) if union else 0.0


def best_match_score(a: str, b: str) -> float:
    """
    Return the best (maximum) similarity score across all three methods.
    This is the primary function used by the candidate identification engine.
    """
    if not a or not b:
        return 0.0
    return max(
        levenshtein_similarity(a, b),
        jaro_winkler_similarity(a, b),
        token_set_ratio(a, b),
    )
