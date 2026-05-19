"""IndependenceVerifier

Pure-logic primitive that measures the *independence* of a set of
voter reasoning traces. High pairwise similarity → low independence
→ mob-mentality signal. The library's claim
multiple voters' reasoning converges *before* the deliberation
window closes, the collective is operating in herd-mode rather than
substrate-aware deliberation, and the vote no longer reflects
multi-perspective convergence — it reflects copy-paste.

This module is a **standalone primitive**. It does not call any DAO,
it does not call any LLM. Composes with :class:`SubstrateAwareVotingProtocol`
(``services.compute.intelligence.orchestration.substrate_aware_voting``)
via the :class:`IndependenceMobProvider` adapter exposed in this
module — which translates a low-independence score into the
``MOB_MENTALITY_DETECTED`` precondition violation.

Algorithm choice — token-set Jaccard
====================================

For a set of *N* voters' reasoning traces:

1. Each trace is normalised — lowercased, punctuation-stripped,
   tokenised on whitespace.
2. Optionally rolled into n-grams (``ngram_size > 1`` catches
   phrase-level copying that single-token Jaccard misses).
3. For every pair *(i, j)*, similarity = ``|A ∩ B| / |A ∪ B|``
   (Jaccard). Range ``[0, 1]``. Identical sets → 1; disjoint → 0.
4. ``IndependenceScore = 1 - mean(pairwise similarities)``. Range
   ``[0, 1]``. Identical voters → 0 (no independence). Disjoint
   voters → 1 (full independence).

Token-set Jaccard is intentionally simple — no ML dependency, no
training data, no model bias. The library's anti-fragile
discipline: substrate-mechanical detection should be readable by a
mathematician, not embedded in a black-box classifier.

Edge cases (all honest about uncertainty)
=========================================

- ``traces`` is empty → ``IndependenceScore = 1.0`` (no information
  to undermine independence).
- ``traces`` has one voter → ``IndependenceScore = 1.0`` (no pair
  to measure against).
- All traces are empty strings → ``IndependenceScore = 1.0`` (no
  shared tokens means no shared reasoning).
- A subset of voters have empty traces → those voters' pairs use
  the ``empty_trace_strategy``:
  - ``"treat_as_independent"`` (default) → similarity 0.0 for any
    pair involving an empty trace.
  - ``"treat_as_identical"`` → similarity 1.0 (paranoid mob-detection).
  - ``"skip_pair"`` → that pair is excluded from the mean.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import (
    Final,
    Mapping,
    Optional,
    Tuple,
    final,
)

import logging
LOG = logging.getLogger(__name__)

#: Default similarity threshold above which a pair is considered
#: mob-like. ``0.70`` was chosen so that two voters using mostly the
#: same vocabulary but framing it differently still pass; literal
#: copy-paste between voters does not.
DEFAULT_MOB_SIMILARITY_THRESHOLD: Final[float] = 0.70

class EmptyTraceStrategy(str, Enum):
    """How to score similarity when one or both traces are empty."""

    TREAT_AS_INDEPENDENT = "treat_as_independent"
    TREAT_AS_IDENTICAL = "treat_as_identical"
    SKIP_PAIR = "skip_pair"

EMPTY_TRACE_STRATEGIES: Final[frozenset[str]] = frozenset(
    s.value for s in EmptyTraceStrategy
)

@dataclass(frozen=True, slots=True)
class TraceSimilarity:
    """Frozen pairwise similarity record."""

    voter_a: str
    voter_b: str
    similarity: float

@dataclass(frozen=True, slots=True)
class IndependenceAssessment:
    """Frozen result of one independence assessment."""

    independence_score: float
    voter_ids: Tuple[str, ...]
    pairwise_similarities: Tuple[TraceSimilarity, ...]
    max_similarity_pair: Optional[TraceSimilarity]
    method: str
    reasoning: str

    @property
    def is_mob(self) -> bool:
        """``True`` when ``independence_score`` indicates mob dynamics.

        The threshold is the verifier's ``mob_similarity_threshold``
        translated to its independence complement: a similarity ≥ τ
        means independence ≤ 1 − τ.
        """
        # ``max_similarity_pair`` is the dominant signal — even if the
        # *mean* similarity stays low (lots of independent voters), a
        # single copy-vote pair is still mob-evidence.
        if self.max_similarity_pair is None:
            return False
        # Resolve the implicit threshold from the reasoning string
        # this stays in lockstep with the verifier's
        # ``mob_similarity_threshold`` since the reasoning string
        # records it. Callers wanting a different cutoff should use
        # :func:`IndependenceVerifier.is_mob_detected` directly.
        threshold = _parse_threshold_from_reasoning(self.reasoning)
        if threshold is None:
            return False
        return self.max_similarity_pair.similarity >= threshold

_THRESHOLD_TAG = "mob_similarity_threshold="

def _parse_threshold_from_reasoning(reasoning: str) -> Optional[float]:
    """Recover the threshold the verifier used (encoded in reasoning)."""
    idx = reasoning.find(_THRESHOLD_TAG)
    if idx < 0:
        return None
    tail = reasoning[idx + len(_THRESHOLD_TAG):]
    token = tail.split(maxsplit=1)[0].rstrip(";,")
    try:
        return float(token)
    except ValueError:
        return None

# ---------------------------------------------------------------------------
# Token normalisation + Jaccard primitives (pure functions, exported)
# ---------------------------------------------------------------------------

def normalize_tokens(text: str, *, ngram_size: int = 1) -> frozenset[str]:
    """Tokenise + optionally roll into n-grams.

    - Lowercase
    - Strip ASCII punctuation by replacing with whitespace
    - Split on whitespace (drops empty tokens)
    - For ``ngram_size > 1``, return all consecutive n-grams as
      space-joined strings.

    Returns a ``frozenset`` (deterministic, hashable) for direct use
    with :func:`jaccard_similarity`.
    """
    if ngram_size < 1:
        raise ValueError(
            f"ngram_size must be >= 1; got {ngram_size!r}"
        )
    # Punctuation removal — replace common ASCII punctuation with spaces.
    cleaned_chars: list[str] = []
    for ch in text.lower():
        if ch.isalnum() or ch in (" ", "\t", "\n"):
            cleaned_chars.append(ch)
        else:
            cleaned_chars.append(" ")
    tokens = [tok for tok in "".join(cleaned_chars).split() if tok]
    if ngram_size == 1:
        return frozenset(tokens)
    if len(tokens) < ngram_size:
        return frozenset()
    ngrams = [
        " ".join(tokens[i:i + ngram_size])
        for i in range(len(tokens) - ngram_size + 1)
    ]
    return frozenset(ngrams)

def jaccard_similarity(
    a: frozenset[str],
    b: frozenset[str],
) -> float:
    """Pure Jaccard set similarity: ``|A ∩ B| / |A ∪ B|``.

    Returns ``0.0`` when both sets are empty (which the library
    reads as "no information shared, no mob signal").
    """
    union_size = len(a | b)
    if union_size == 0:
        return 0.0
    return len(a & b) / union_size

# ---------------------------------------------------------------------------
# IndependenceVerifier
# ---------------------------------------------------------------------------

@final
class IndependenceVerifier:  # pylint: disable=too-few-public-methods
    """Pure-logic primitive: assess voter reasoning-trace independence."""

    def __init__(
        self,
        *,
        ngram_size: int = 1,
        mob_similarity_threshold: float = DEFAULT_MOB_SIMILARITY_THRESHOLD,
        empty_trace_strategy: EmptyTraceStrategy = (
            EmptyTraceStrategy.TREAT_AS_INDEPENDENT
        ),
    ) -> None:
        if ngram_size < 1:
            raise ValueError(
                f"ngram_size must be >= 1; got {ngram_size!r}"
            )
        if not 0.0 <= mob_similarity_threshold <= 1.0:
            raise ValueError(
                "mob_similarity_threshold must be in [0.0, 1.0]; "
                f"got {mob_similarity_threshold!r}"
            )
        self._ngram_size = ngram_size
        self._threshold = mob_similarity_threshold
        self._empty_strategy = empty_trace_strategy

    @property
    def ngram_size(self) -> int:
        """The n-gram size used for tokenisation."""
        return self._ngram_size

    @property
    def mob_similarity_threshold(self) -> float:
        """The pairwise-similarity cutoff above which mob dynamics fire."""
        return self._threshold

    @property
    def empty_trace_strategy(self) -> EmptyTraceStrategy:
        """How the verifier scores pairs involving an empty trace."""
        return self._empty_strategy

    def assess(  # pylint: disable=too-many-locals
        self,
        traces: Mapping[str, str],
    ) -> IndependenceAssessment:
        """Compute the typed independence assessment for ``traces``."""
        voter_ids = tuple(sorted(traces.keys()))
        if len(voter_ids) <= 1:
            return IndependenceAssessment(
                independence_score=1.0,
                voter_ids=voter_ids,
                pairwise_similarities=(),
                max_similarity_pair=None,
                method=self._method_label(),
                reasoning=self._render_reasoning(
                    score=1.0,
                    pair_count=0,
                    max_pair=None,
                ),
            )

        # Pre-normalise once per voter.
        normalised: dict[str, frozenset[str]] = {
            v: normalize_tokens(traces[v], ngram_size=self._ngram_size)
            for v in voter_ids
        }

        similarities: list[TraceSimilarity] = []
        included_pair_similarities: list[float] = []
        for i, voter_a in enumerate(voter_ids):
            for voter_b in voter_ids[i + 1:]:
                a_set = normalised[voter_a]
                b_set = normalised[voter_b]
                a_empty = not a_set
                b_empty = not b_set
                if a_empty or b_empty:
                    sim = self._score_empty_pair(
                        a_empty=a_empty, b_empty=b_empty,
                    )
                    if sim is None:
                        # SKIP_PAIR — record nothing.
                        continue
                else:
                    sim = jaccard_similarity(a_set, b_set)
                similarities.append(TraceSimilarity(
                    voter_a=voter_a,
                    voter_b=voter_b,
                    similarity=sim,
                ))
                included_pair_similarities.append(sim)

        if not included_pair_similarities:
            # All pairs skipped — treat as fully independent.
            return IndependenceAssessment(
                independence_score=1.0,
                voter_ids=voter_ids,
                pairwise_similarities=tuple(similarities),
                max_similarity_pair=None,
                method=self._method_label(),
                reasoning=self._render_reasoning(
                    score=1.0, pair_count=0, max_pair=None,
                ),
            )

        mean_similarity = sum(included_pair_similarities) / len(
            included_pair_similarities
        )
        independence = max(0.0, min(1.0, 1.0 - mean_similarity))
        max_pair = max(similarities, key=lambda s: s.similarity)
        return IndependenceAssessment(
            independence_score=independence,
            voter_ids=voter_ids,
            pairwise_similarities=tuple(similarities),
            max_similarity_pair=max_pair,
            method=self._method_label(),
            reasoning=self._render_reasoning(
                score=independence,
                pair_count=len(similarities),
                max_pair=max_pair,
            ),
        )

    def is_mob_detected(
        self,
        assessment: IndependenceAssessment,
    ) -> bool:
        """Pure helper: ``True`` iff any pair's similarity ≥ threshold."""
        if assessment.max_similarity_pair is None:
            return False
        return (
            assessment.max_similarity_pair.similarity >= self._threshold
        )

    # -- helpers ------------------------------------------------------

    def _method_label(self) -> str:
        return f"jaccard.ngram_{self._ngram_size}"

    def _score_empty_pair(
        self,
        *,
        a_empty: bool,
        b_empty: bool,
    ) -> Optional[float]:
        if self._empty_strategy is EmptyTraceStrategy.TREAT_AS_INDEPENDENT:
            return 0.0
        if self._empty_strategy is EmptyTraceStrategy.TREAT_AS_IDENTICAL:
            # Both empty → identical by convention; one empty → not
            # identical to a non-empty trace, but the paranoid
            # operator opted into this; honour the rule.
            return 1.0 if (a_empty and b_empty) else 0.0
        # SKIP_PAIR
        return None

    def _render_reasoning(
        self,
        *,
        score: float,
        pair_count: int,
        max_pair: Optional[TraceSimilarity],
    ) -> str:
        max_part = (
            f" max_pair=({max_pair.voter_a},{max_pair.voter_b})="
            f"{max_pair.similarity:.4f}"
            if max_pair is not None
            else " no pairs"
        )
        return (
            f"independence_score={score:.4f} method={self._method_label()} "
            f"pairs={pair_count}{max_part} "
            f"{_THRESHOLD_TAG}{self._threshold:.4f}"
        )

# ---------------------------------------------------------------------------
# Adapter into XVIII-1 (SubstrateAwareVotingProtocol)
# ---------------------------------------------------------------------------

@final
class IndependenceMobProvider:  # pylint: disable=too-few-public-methods
    """Adapter that surfaces the verifier's mob signal to XVIII-1.

    XVIII-1's :class:`SubstrateAwareVotingProtocol` raises
    ``MOB_MENTALITY_DETECTED`` from timestamp clustering today. This
    adapter exposes a second, independent signal — high
    reasoning-trace similarity — that callers can OR with the
    timestamp check before resolving.

    The adapter is intentionally a thin pass-through. Callers wire
    it where they have access to voter reasoning traces (a future
    :class:`ConsensusRecord` extension carrying ``reasoning`` per
    voter, or a sidecar dict).
    """

    def __init__(
        self,
        *,
        verifier: IndependenceVerifier,
    ) -> None:
        self._verifier = verifier

    @property
    def verifier(self) -> IndependenceVerifier:
        """The wrapped :class:`IndependenceVerifier`."""
        return self._verifier

    def is_mob(self, traces: Mapping[str, str]) -> bool:
        """Compute the assessment and return True iff mob-detected."""
        assessment = self._verifier.assess(traces)
        return self._verifier.is_mob_detected(assessment)

__all__ = [
    "DEFAULT_MOB_SIMILARITY_THRESHOLD",
    "EMPTY_TRACE_STRATEGIES",
    "EmptyTraceStrategy",
    "IndependenceAssessment",
    "IndependenceMobProvider",
    "IndependenceVerifier",
    "TraceSimilarity",
    "jaccard_similarity",
    "normalize_tokens",
]
