"""
Tests for the fuzzy string matching module.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from utils.fuzzy_match import (
    levenshtein_similarity,
    jaro_winkler_similarity,
    token_set_ratio,
    best_match_score,
)


def test_exact_match():
    """Identical strings should return 1.0."""
    assert levenshtein_similarity("John Doe", "John Doe") == 1.0
    assert jaro_winkler_similarity("John Doe", "John Doe") == 1.0
    assert token_set_ratio("John Doe", "John Doe") == 1.0


def test_empty_strings():
    """Empty strings should be handled gracefully."""
    assert levenshtein_similarity("", "") == 1.0
    assert levenshtein_similarity("abc", "") == 0.0
    assert best_match_score("", "abc") == 0.0
    assert best_match_score(None, "abc") == 0.0


def test_case_insensitive():
    """Matching should be case-insensitive."""
    assert levenshtein_similarity("john doe", "JOHN DOE") == 1.0
    assert jaro_winkler_similarity("Aarav Sharma", "aarav sharma") == 1.0


def test_partial_name():
    """Partial names should get reasonable scores."""
    score = best_match_score("Chitransh S.", "Chitransh Srivastava")
    assert score >= 0.6, f"Expected >= 0.6, got {score}"


def test_reversed_name():
    """Reversed name order should be caught by token-set ratio."""
    score = token_set_ratio("Srivastava, Chitransh", "Chitransh Srivastava")
    assert score >= 0.8, f"Expected >= 0.8, got {score}"


def test_nickname_vs_full():
    """Nicknames should get moderate scores."""
    score = best_match_score("Chris", "Christopher Johnson")
    assert 0.2 <= score <= 0.9, f"Unexpected score: {score}"


def test_completely_different():
    """Unrelated names should score low."""
    score = best_match_score("Alice Smith", "Bob Johnson")
    assert score < 0.5, f"Expected < 0.5, got {score}"


def test_jaro_winkler_prefix_boost():
    """Jaro-Winkler should boost common-prefix names."""
    jw = jaro_winkler_similarity("Chitransh Sriv", "Chitransh Srivastava")
    lev = levenshtein_similarity("Chitransh Sriv", "Chitransh Srivastava")
    assert jw >= lev, "Jaro-Winkler should >= Levenshtein for common prefix"


def test_generic_name_not_matching():
    """Generic device names should score low against real names."""
    score = best_match_score("MacBook Pro", "Aarav Sharma")
    # Raw fuzzy score can be moderate; the signal_processors.MetadataSignalProcessor
    # applies additional penalty for generic device names
    assert score < 0.6, f"Expected < 0.6, got {score}"


def test_unicode_names():
    """Unicode names should work."""
    score = levenshtein_similarity("日本太郎", "日本太郎")
    assert score == 1.0


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
