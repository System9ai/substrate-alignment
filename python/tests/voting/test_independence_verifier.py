"""Tests for IndependenceVerifier

Covers:
- normalize_tokens: lowercase + punctuation strip + whitespace split
- normalize_tokens with n-gram sizes (1, 2, 3)
- normalize_tokens rejects ngram_size < 1
- jaccard_similarity: identical / disjoint / partial / both-empty edge cases
- IndependenceVerifier constructor validation
- assess on:
  - empty traces dict → score 1.0
  - single voter → score 1.0
  - two identical traces → score 0.0
  - two disjoint traces → score 1.0
  - two partially overlapping → score in (0, 1)
  - three voters: pairwise matrix complete + max_similarity_pair identified
- EmptyTraceStrategy: TREAT_AS_INDEPENDENT / TREAT_AS_IDENTICAL / SKIP_PAIR
- is_mob_detected helper threshold
- assessment.is_mob property
- IndependenceMobProvider adapter
- module __all__ + constant lockstep
"""
from __future__ import annotations

import pytest

from substrate.voting.independence_verifier import (
    DEFAULT_MOB_SIMILARITY_THRESHOLD,
    EMPTY_TRACE_STRATEGIES,
    EmptyTraceStrategy,
    IndependenceAssessment,
    IndependenceMobProvider,
    IndependenceVerifier,
    TraceSimilarity,
    jaccard_similarity,
    normalize_tokens,
)

# ---------------------------------------------------------------------------
# normalize_tokens
# ---------------------------------------------------------------------------

class TestNormalizeTokens:
    def test_lowercase_and_split(self) -> None:
        assert normalize_tokens("Hello World") == frozenset({"hello", "world"})

    def test_punctuation_stripped(self) -> None:
        assert normalize_tokens("Hello, World!") == frozenset({"hello", "world"})

    def test_empty_string_yields_empty(self) -> None:
        assert normalize_tokens("") == frozenset()

    def test_whitespace_only_yields_empty(self) -> None:
        assert normalize_tokens("   \n\t  ") == frozenset()

    def test_alphanumeric_preserved(self) -> None:
        assert "alice42" in normalize_tokens("Alice42 says hi")

    def test_bigrams(self) -> None:
        # "the quick fox" → bigrams: {"the quick", "quick fox"}
        result = normalize_tokens("the quick fox", ngram_size=2)
        assert result == frozenset({"the quick", "quick fox"})

    def test_trigrams(self) -> None:
        result = normalize_tokens("a b c d", ngram_size=3)
        assert result == frozenset({"a b c", "b c d"})

    def test_ngram_size_zero_rejected(self) -> None:
        with pytest.raises(ValueError):
            normalize_tokens("hi", ngram_size=0)

    def test_too_few_tokens_for_ngram(self) -> None:
        # "hi" has 1 token, asking for bigrams → empty set.
        assert normalize_tokens("hi", ngram_size=2) == frozenset()

# ---------------------------------------------------------------------------
# jaccard_similarity
# ---------------------------------------------------------------------------

class TestJaccardSimilarity:
    def test_identical(self) -> None:
        s = frozenset({"a", "b", "c"})
        assert jaccard_similarity(s, s) == 1.0

    def test_disjoint(self) -> None:
        assert jaccard_similarity(
            frozenset({"a", "b"}),
            frozenset({"c", "d"}),
        ) == 0.0

    def test_partial_overlap(self) -> None:
        # |∩| = 2, |∪| = 4 → 0.5
        assert jaccard_similarity(
            frozenset({"a", "b", "c"}),
            frozenset({"b", "c", "d"}),
        ) == pytest.approx(0.5)

    def test_both_empty(self) -> None:
        # Convention: empty ∪ empty → score 0.0 (no signal)
        assert jaccard_similarity(frozenset(), frozenset()) == 0.0

    def test_one_empty(self) -> None:
        # |∩| = 0, |∪| = 2 → 0.0
        assert jaccard_similarity(
            frozenset(), frozenset({"a", "b"}),
        ) == 0.0

# ---------------------------------------------------------------------------
# IndependenceVerifier constructor validation
# ---------------------------------------------------------------------------

class TestConstructorValidation:
    def test_default_constructor(self) -> None:
        v = IndependenceVerifier()
        assert v.ngram_size == 1
        assert v.mob_similarity_threshold == DEFAULT_MOB_SIMILARITY_THRESHOLD
        assert v.empty_trace_strategy is EmptyTraceStrategy.TREAT_AS_INDEPENDENT

    def test_ngram_size_zero_rejected(self) -> None:
        with pytest.raises(ValueError):
            IndependenceVerifier(ngram_size=0)

    def test_ngram_size_negative_rejected(self) -> None:
        with pytest.raises(ValueError):
            IndependenceVerifier(ngram_size=-1)

    def test_threshold_below_zero_rejected(self) -> None:
        with pytest.raises(ValueError):
            IndependenceVerifier(mob_similarity_threshold=-0.1)

    def test_threshold_above_one_rejected(self) -> None:
        with pytest.raises(ValueError):
            IndependenceVerifier(mob_similarity_threshold=1.5)

    def test_threshold_boundary_inclusive(self) -> None:
        IndependenceVerifier(mob_similarity_threshold=0.0)
        IndependenceVerifier(mob_similarity_threshold=1.0)

# ---------------------------------------------------------------------------
# assess(): basic cases
# ---------------------------------------------------------------------------

class TestAssessBasicCases:
    def test_empty_traces_returns_full_independence(self) -> None:
        v = IndependenceVerifier()
        result = v.assess({})
        assert result.independence_score == 1.0
        assert result.voter_ids == ()
        assert result.pairwise_similarities == ()
        assert result.max_similarity_pair is None

    def test_single_voter_returns_full_independence(self) -> None:
        v = IndependenceVerifier()
        result = v.assess({"alice": "I think we should go ahead"})
        assert result.independence_score == 1.0
        assert result.voter_ids == ("alice",)
        assert result.pairwise_similarities == ()

    def test_two_identical_traces_zero_independence(self) -> None:
        v = IndependenceVerifier()
        result = v.assess({
            "alice": "this is a substrate-aligned plan",
            "bob": "this is a substrate-aligned plan",
        })
        assert result.independence_score == pytest.approx(0.0)
        assert len(result.pairwise_similarities) == 1
        assert result.pairwise_similarities[0].similarity == pytest.approx(1.0)

    def test_two_disjoint_traces_full_independence(self) -> None:
        v = IndependenceVerifier()
        result = v.assess({
            "alice": "alpha beta gamma",
            "bob": "delta epsilon zeta",
        })
        assert result.independence_score == pytest.approx(1.0)
        assert result.pairwise_similarities[0].similarity == pytest.approx(0.0)

    def test_two_partial_overlap(self) -> None:
        v = IndependenceVerifier()
        result = v.assess({
            "alice": "the quick brown fox",
            "bob": "the slow brown bear",
        })
        # tokens: {the, quick, brown, fox} & {the, slow, brown, bear}
        # ∩ = {the, brown}, ∪ = 6 → 2/6 ≈ 0.333
        assert result.pairwise_similarities[0].similarity == pytest.approx(2 / 6)
        # Independence = 1 - mean(similarity)
        assert result.independence_score == pytest.approx(1.0 - 2 / 6)

# ---------------------------------------------------------------------------
# assess(): three or more voters
# ---------------------------------------------------------------------------

class TestAssessMultiVoter:
    def test_three_voters_full_pairwise_matrix(self) -> None:
        v = IndependenceVerifier()
        result = v.assess({
            "a": "alpha beta",
            "b": "alpha gamma",
            "c": "delta epsilon",
        })
        # 3 voters → 3 pairs
        assert len(result.pairwise_similarities) == 3
        # Voter IDs deterministic (sorted)
        assert result.voter_ids == ("a", "b", "c")

    def test_max_pair_identified(self) -> None:
        v = IndependenceVerifier()
        result = v.assess({
            "a": "alpha beta gamma",
            "b": "alpha beta gamma",  # identical to a
            "c": "delta epsilon zeta",
        })
        assert result.max_similarity_pair is not None
        assert result.max_similarity_pair.similarity == pytest.approx(1.0)
        # The a/b pair should be the max
        assert {
            result.max_similarity_pair.voter_a,
            result.max_similarity_pair.voter_b,
        } == {"a", "b"}

    def test_ngram_size_2_catches_phrase_copy(self) -> None:
        v = IndependenceVerifier(ngram_size=2)
        result = v.assess({
            "a": "the substrate is aligned",
            "b": "the substrate is misaligned",
        })
        # bigrams a: {"the substrate", "substrate is", "is aligned"}
        # bigrams b: {"the substrate", "substrate is", "is misaligned"}
        # ∩ = {"the substrate", "substrate is"} = 2; ∪ = 4
        # similarity = 0.5
        assert result.pairwise_similarities[0].similarity == pytest.approx(0.5)

# ---------------------------------------------------------------------------
# EmptyTraceStrategy
# ---------------------------------------------------------------------------

class TestEmptyTraceStrategy:
    def test_treat_as_independent_default(self) -> None:
        v = IndependenceVerifier()
        result = v.assess({
            "a": "",
            "b": "hello world",
        })
        # Pair similarity = 0.0 → independence = 1.0
        assert result.pairwise_similarities[0].similarity == 0.0
        assert result.independence_score == 1.0

    def test_treat_as_identical_paranoid(self) -> None:
        v = IndependenceVerifier(
            empty_trace_strategy=EmptyTraceStrategy.TREAT_AS_IDENTICAL,
        )
        result = v.assess({
            "a": "",
            "b": "",
        })
        # Both empty → similarity 1.0 → independence 0.0
        assert result.pairwise_similarities[0].similarity == 1.0
        assert result.independence_score == 0.0

    def test_treat_as_identical_one_empty(self) -> None:
        v = IndependenceVerifier(
            empty_trace_strategy=EmptyTraceStrategy.TREAT_AS_IDENTICAL,
        )
        result = v.assess({"a": "", "b": "hi"})
        # One empty, one not → not identical → 0.0
        assert result.pairwise_similarities[0].similarity == 0.0

    def test_skip_pair(self) -> None:
        v = IndependenceVerifier(
            empty_trace_strategy=EmptyTraceStrategy.SKIP_PAIR,
        )
        result = v.assess({"a": "", "b": "hello"})
        # Pair skipped → no pairs → fallback to full independence
        assert result.pairwise_similarities == ()
        assert result.independence_score == 1.0
        assert result.max_similarity_pair is None

    def test_skip_pair_partial_skip(self) -> None:
        v = IndependenceVerifier(
            empty_trace_strategy=EmptyTraceStrategy.SKIP_PAIR,
        )
        result = v.assess({
            "a": "",       # involves a → skipped
            "b": "alpha",
            "c": "alpha",
        })
        # Only (b, c) pair counted
        assert len(result.pairwise_similarities) == 1
        assert result.pairwise_similarities[0].voter_a == "b"
        assert result.pairwise_similarities[0].voter_b == "c"

# ---------------------------------------------------------------------------
# Mob detection
# ---------------------------------------------------------------------------

class TestMobDetection:
    def test_is_mob_detected_high_similarity(self) -> None:
        v = IndependenceVerifier(mob_similarity_threshold=0.5)
        result = v.assess({
            "a": "alpha beta gamma",
            "b": "alpha beta gamma",
        })
        assert v.is_mob_detected(result) is True

    def test_is_mob_detected_low_similarity(self) -> None:
        v = IndependenceVerifier(mob_similarity_threshold=0.5)
        result = v.assess({
            "a": "alpha beta",
            "b": "gamma delta",
        })
        assert v.is_mob_detected(result) is False

    def test_is_mob_detected_no_pairs(self) -> None:
        v = IndependenceVerifier()
        result = v.assess({"alice": "alone"})
        assert v.is_mob_detected(result) is False

    def test_assessment_is_mob_property_high(self) -> None:
        v = IndependenceVerifier(mob_similarity_threshold=0.5)
        result = v.assess({
            "a": "alpha beta gamma",
            "b": "alpha beta gamma",
        })
        assert result.is_mob is True

    def test_assessment_is_mob_property_low(self) -> None:
        v = IndependenceVerifier(mob_similarity_threshold=0.5)
        result = v.assess({
            "a": "alpha",
            "b": "beta",
        })
        assert result.is_mob is False

# ---------------------------------------------------------------------------
# IndependenceMobProvider adapter
# ---------------------------------------------------------------------------

class TestIndependenceMobProvider:
    def test_provider_wraps_verifier(self) -> None:
        v = IndependenceVerifier(mob_similarity_threshold=0.4)
        p = IndependenceMobProvider(verifier=v)
        assert p.verifier is v

    def test_provider_is_mob_true_on_high_sim(self) -> None:
        v = IndependenceVerifier(mob_similarity_threshold=0.5)
        p = IndependenceMobProvider(verifier=v)
        assert p.is_mob({
            "a": "alpha beta gamma",
            "b": "alpha beta gamma",
        }) is True

    def test_provider_is_mob_false_on_low_sim(self) -> None:
        v = IndependenceVerifier(mob_similarity_threshold=0.5)
        p = IndependenceMobProvider(verifier=v)
        assert p.is_mob({
            "a": "alpha",
            "b": "gamma",
        }) is False

# ---------------------------------------------------------------------------
# Result shape + module exports
# ---------------------------------------------------------------------------

def test_assessment_is_frozen() -> None:
    v = IndependenceVerifier()
    result = v.assess({"a": "x", "b": "y"})
    with pytest.raises(AttributeError):
        result.independence_score = 0.0

def test_trace_similarity_frozen() -> None:
    ts = TraceSimilarity(voter_a="a", voter_b="b", similarity=0.5)
    with pytest.raises(AttributeError):
        ts.similarity = 1.0

def test_empty_trace_strategies_constant_lockstep() -> None:
    for s in EmptyTraceStrategy:
        assert s.value in EMPTY_TRACE_STRATEGIES
    assert len(EMPTY_TRACE_STRATEGIES) == 3

def test_method_label_format() -> None:
    v = IndependenceVerifier(ngram_size=2)
    result = v.assess({"a": "hi there"})
    assert "jaccard.ngram_2" in result.method

def test_reasoning_string_contains_threshold() -> None:
    v = IndependenceVerifier(mob_similarity_threshold=0.42)
    result = v.assess({"a": "x", "b": "x"})
    assert "0.4200" in result.reasoning

def test_module_exports() -> None:
    from substrate.voting import (
        independence_verifier as mod,
    )
    for name in (
        "DEFAULT_MOB_SIMILARITY_THRESHOLD",
        "EMPTY_TRACE_STRATEGIES",
        "EmptyTraceStrategy",
        "IndependenceAssessment",
        "IndependenceMobProvider",
        "IndependenceVerifier",
        "TraceSimilarity",
        "jaccard_similarity",
        "normalize_tokens",
    ):
        assert name in mod.__all__, name

def test_assessment_construct_directly() -> None:
    a = IndependenceAssessment(
        independence_score=0.5,
        voter_ids=("a", "b"),
        pairwise_similarities=(
            TraceSimilarity(voter_a="a", voter_b="b", similarity=0.5),
        ),
        max_similarity_pair=TraceSimilarity(
            voter_a="a", voter_b="b", similarity=0.5,
        ),
        method="jaccard.ngram_1",
        reasoning="manual",
    )
    assert a.independence_score == 0.5
