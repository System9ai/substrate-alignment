"""ConvergenceTracker

Pure-logic primitive that measures Condorcet-quality emergence across
repeated voting rounds.

Given a chronological sequence of round results (winner + confidence
per round), the tracker computes a :class:`ConvergenceTrajectory`
classifying the deliberation as one of five states:

- **CONVERGED**: same winner has held for ``stable_window_rounds``
  consecutive rounds AND confidence is non-decreasing over that
  window. The substrate-aware committee has resolved.
- **CONVERGING**: winner has been stable in the recent window but
  earlier rounds had different winners; the deliberation is settling.
- **OSCILLATING**: winner changes frequently across rounds; no
  stable substrate-aligned position has emerged. The library reads
  this as either insufficient deliberation time or substrate-mode
  disagreement among voters.
- **DIVERGING**: winner may be stable but confidence is trending
  *downward* across rounds. Voters are losing certainty even as the
  outcome holds: a substrate-mechanical warning that the underlying
  question may be miscast.
- **INSUFFICIENT_ROUNDS**: fewer than ``min_rounds`` rounds recorded;
  honest-uncertainty discipline: cannot pronounce convergence on
  noise.

The tracker is **pure**: no DAO, no LLM. Composes with XVIII-1's
:class:`SubstrateAwareVotingProtocol` for callers running iterative
the host workflow runtime voting workflows.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import (
    Final,
    Optional,
    Sequence,
    Tuple,
    final,
)

import logging
LOG = logging.getLogger(__name__)

#: Default minimum rounds before a non-INSUFFICIENT verdict fires.
DEFAULT_MIN_ROUNDS: Final[int] = 3

#: Default size of the trailing window over which we assess winner
#: stability + confidence trend. Smaller windows respond faster but
#: are noisier.
DEFAULT_STABLE_WINDOW_ROUNDS: Final[int] = 3

#: Default fraction of the stable window the current winner must hold
#: to qualify for CONVERGED or CONVERGING.
DEFAULT_STABILITY_THRESHOLD: Final[float] = 1.0

#: Default oscillation rate above which OSCILLATING fires (fraction
#: of rounds where the winner differed from the prior round).
DEFAULT_OSCILLATION_THRESHOLD: Final[float] = 0.5

#: Default confidence-slope threshold below which DIVERGING fires.
#: A negative slope smaller than this (i.e., dropping faster) flags
#: divergence even when the winner is stable.
DEFAULT_DIVERGENCE_SLOPE_THRESHOLD: Final[float] = -0.02

class ConvergenceVerdict(str, Enum):
    """Five-valued convergence classification."""

    CONVERGED = "converged"
    CONVERGING = "converging"
    OSCILLATING = "oscillating"
    DIVERGING = "diverging"
    INSUFFICIENT_ROUNDS = "insufficient_rounds"

CONVERGENCE_VERDICTS: Final[frozenset[str]] = frozenset(
    v.value for v in ConvergenceVerdict
)

@dataclass(frozen=True, slots=True)
class RoundResult:
    """One round of a repeated vote.

    ``winner`` is the resolution outcome (``str(outcome)``);
    ``confidence`` is the engine's confidence in ``[0, 1]`` from
    :class:`ConsensusRecord.confidence`.
    """

    round_index: int
    winner: str
    confidence: float

@dataclass(frozen=True, slots=True)
class ConvergenceTrajectory:  # pylint: disable=too-many-instance-attributes
    """Frozen result of one convergence assessment."""

    verdict: ConvergenceVerdict
    current_winner: Optional[str]
    convergence_quality: float
    winner_stability: float
    oscillation_count: int
    oscillation_rate: float
    confidence_trend_slope: float
    rounds_assessed: int
    reasoning: str

    @property
    def is_converged(self) -> bool:
        """``True`` iff the verdict is CONVERGED."""
        return self.verdict is ConvergenceVerdict.CONVERGED

@final
class ConvergenceTracker:  # pylint: disable=too-few-public-methods,too-many-instance-attributes
    """Pure tracker over a sequence of :class:`RoundResult`.

    The tracker is constructed with thresholds; ``assess()`` is the
    only public method and is pure (no internal state).
    """

    def __init__(  # pylint: disable=too-many-arguments
        self,
        *,
        min_rounds: int = DEFAULT_MIN_ROUNDS,
        stable_window_rounds: int = DEFAULT_STABLE_WINDOW_ROUNDS,
        stability_threshold: float = DEFAULT_STABILITY_THRESHOLD,
        oscillation_threshold: float = DEFAULT_OSCILLATION_THRESHOLD,
        divergence_slope_threshold: float = DEFAULT_DIVERGENCE_SLOPE_THRESHOLD,
    ) -> None:
        if min_rounds < 2:
            raise ValueError(
                "min_rounds must be >= 2 (need at least two rounds to "
                f"compute oscillation); got {min_rounds!r}"
            )
        if stable_window_rounds < 1:
            raise ValueError(
                "stable_window_rounds must be >= 1; "
                f"got {stable_window_rounds!r}"
            )
        if not 0.0 < stability_threshold <= 1.0:
            raise ValueError(
                "stability_threshold must be in (0.0, 1.0]; "
                f"got {stability_threshold!r}"
            )
        if not 0.0 <= oscillation_threshold <= 1.0:
            raise ValueError(
                "oscillation_threshold must be in [0.0, 1.0]; "
                f"got {oscillation_threshold!r}"
            )
        self._min_rounds = min_rounds
        self._stable_window = stable_window_rounds
        self._stability_threshold = stability_threshold
        self._oscillation_threshold = oscillation_threshold
        self._divergence_slope_threshold = divergence_slope_threshold

    @property
    def min_rounds(self) -> int:
        """Minimum rounds before a non-INSUFFICIENT verdict can fire."""
        return self._min_rounds

    @property
    def stable_window_rounds(self) -> int:
        """Size of the trailing window used for stability + trend."""
        return self._stable_window

    @property
    def stability_threshold(self) -> float:
        """Fraction of the stable window the current winner must hold."""
        return self._stability_threshold

    @property
    def oscillation_threshold(self) -> float:
        """Oscillation rate above which OSCILLATING fires."""
        return self._oscillation_threshold

    @property
    def divergence_slope_threshold(self) -> float:
        """Confidence-slope threshold below which DIVERGING fires."""
        return self._divergence_slope_threshold

    # -- public API ---------------------------------------------------

    def assess(  # pylint: disable=too-many-locals
        self,
        rounds: Sequence[RoundResult],
    ) -> ConvergenceTrajectory:
        """Classify the deliberation trajectory.

        Rounds are assumed chronologically ordered (oldest first).
        The tracker does not sort them; callers must supply ordered
        input. Out-of-order input raises ``ValueError``.
        """
        rounds_assessed = len(rounds)
        if rounds_assessed == 0:
            return self._trajectory_insufficient(
                current_winner=None,
                reason="no rounds supplied",
                rounds_assessed=0,
            )
        # Defensive: ensure chronological order.
        for prev, curr in zip(rounds[:-1], rounds[1:]):
            if curr.round_index <= prev.round_index:
                raise ValueError(
                    "rounds must be strictly chronological; "
                    f"got {prev.round_index} -> {curr.round_index}"
                )
        current_winner = rounds[-1].winner
        if rounds_assessed < self._min_rounds:
            return self._trajectory_insufficient(
                current_winner=current_winner,
                reason=(
                    f"rounds_assessed={rounds_assessed} < min_rounds="
                    f"{self._min_rounds}"
                ),
                rounds_assessed=rounds_assessed,
            )

        oscillation_count = self._oscillation_count(rounds)
        oscillation_rate = oscillation_count / max(1, rounds_assessed - 1)
        winner_stability = self._winner_stability(
            rounds=rounds, target_winner=current_winner,
        )
        slope = self._confidence_slope(rounds[-self._stable_window:])

        verdict = self._classify(
            winner_stability=winner_stability,
            oscillation_rate=oscillation_rate,
            slope=slope,
        )
        quality = self._compose_quality(
            winner_stability=winner_stability,
            oscillation_rate=oscillation_rate,
            slope=slope,
        )
        return ConvergenceTrajectory(
            verdict=verdict,
            current_winner=current_winner,
            convergence_quality=quality,
            winner_stability=winner_stability,
            oscillation_count=oscillation_count,
            oscillation_rate=oscillation_rate,
            confidence_trend_slope=slope,
            rounds_assessed=rounds_assessed,
            reasoning=self._render_reasoning(
                verdict=verdict,
                quality=quality,
                winner_stability=winner_stability,
                oscillation_rate=oscillation_rate,
                slope=slope,
                rounds_assessed=rounds_assessed,
            ),
        )

    # -- helpers ------------------------------------------------------

    @staticmethod
    def _oscillation_count(rounds: Sequence[RoundResult]) -> int:
        """Count winner changes between consecutive rounds."""
        count = 0
        for prev, curr in zip(rounds[:-1], rounds[1:]):
            if curr.winner != prev.winner:
                count += 1
        return count

    def _winner_stability(
        self,
        *,
        rounds: Sequence[RoundResult],
        target_winner: str,
    ) -> float:
        """Fraction of the trailing window where ``target_winner`` won."""
        window = rounds[-self._stable_window:]
        if not window:
            return 0.0
        wins = sum(1 for r in window if r.winner == target_winner)
        return wins / len(window)

    @staticmethod
    def _confidence_slope(window: Sequence[RoundResult]) -> float:
        """Simple linear-regression slope of confidence over the window."""
        n = len(window)
        if n < 2:
            return 0.0
        # x = 0, 1, ..., n-1; y = confidence
        sum_x = (n - 1) * n / 2.0
        sum_y = sum(r.confidence for r in window)
        sum_xx = sum(i * i for i in range(n))
        sum_xy = sum(i * window[i].confidence for i in range(n))
        denom = n * sum_xx - sum_x * sum_x
        if denom == 0:
            return 0.0
        return (n * sum_xy - sum_x * sum_y) / denom

    def _classify(
        self,
        *,
        winner_stability: float,
        oscillation_rate: float,
        slope: float,
    ) -> ConvergenceVerdict:
        """Combine signals into a typed verdict."""
        # Order matters: diverging takes precedence over converged
        # because dropping confidence in a stable winner is a worse
        # signal than the apparent stability suggests.
        if slope <= self._divergence_slope_threshold:
            return ConvergenceVerdict.DIVERGING
        if oscillation_rate >= self._oscillation_threshold:
            return ConvergenceVerdict.OSCILLATING
        if winner_stability >= self._stability_threshold and slope >= 0.0:
            return ConvergenceVerdict.CONVERGED
        if winner_stability >= self._stability_threshold:
            return ConvergenceVerdict.CONVERGING
        # In-between: not stable enough to converge, not oscillating
        # enough to fail outright, call it CONVERGING (still settling).
        return ConvergenceVerdict.CONVERGING

    @staticmethod
    def _compose_quality(
        *,
        winner_stability: float,
        oscillation_rate: float,
        slope: float,
    ) -> float:
        """Composite quality in ``[0, 1]``.

        Composition:
            quality = winner_stability × (1 − oscillation_rate)
                     × confidence_trend_multiplier

        where ``confidence_trend_multiplier`` is clamped in
        ``[0.5, 1.0]``: positive slope leaves quality unchanged;
        negative slope down-weights it but doesn't zero it out
        (the verdict already names DIVERGING when slope is bad).
        """
        stability_term = max(0.0, min(1.0, winner_stability))
        anti_oscillation = max(0.0, min(1.0, 1.0 - oscillation_rate))
        # Map slope ∈ [-0.05, 0.05] linearly to [0.5, 1.0]; clamp.
        scaled = 0.5 + 5.0 * slope
        trend_multiplier = max(0.5, min(1.0, scaled))
        return stability_term * anti_oscillation * trend_multiplier

    @staticmethod
    def _trajectory_insufficient(
        *,
        current_winner: Optional[str],
        reason: str,
        rounds_assessed: int,
    ) -> ConvergenceTrajectory:
        return ConvergenceTrajectory(
            verdict=ConvergenceVerdict.INSUFFICIENT_ROUNDS,
            current_winner=current_winner,
            convergence_quality=0.0,
            winner_stability=0.0,
            oscillation_count=0,
            oscillation_rate=0.0,
            confidence_trend_slope=0.0,
            rounds_assessed=rounds_assessed,
            reasoning=reason,
        )

    @staticmethod
    def _render_reasoning(  # pylint: disable=too-many-arguments
        *,
        verdict: ConvergenceVerdict,
        quality: float,
        winner_stability: float,
        oscillation_rate: float,
        slope: float,
        rounds_assessed: int,
    ) -> str:
        return (
            f"verdict={verdict.value} quality={quality:.4f} "
            f"stability={winner_stability:.4f} "
            f"oscillation_rate={oscillation_rate:.4f} "
            f"slope={slope:+.4f} rounds={rounds_assessed}"
        )

# ---------------------------------------------------------------------------
# Adapter for ConsensusRecord-keyed callers
# ---------------------------------------------------------------------------

def round_results_from_records(
    records: Sequence[object],
    *,
    round_indices: Optional[Sequence[int]] = None,
) -> Tuple[RoundResult, ...]:
    """Project a sequence of :class:`ConsensusRecord`-like objects to RoundResults.

    Accepts any object with ``.outcome: Optional[str]`` and
    ``.confidence: float`` attributes (the duck-type of
    :class:`ConsensusRecord` from
    ``services.compute.intelligence.orchestration.orchestration_types``).
    Records whose ``outcome`` is ``None`` are dropped: INSUFFICIENT
    resolution at one round shouldn't break trajectory math.

    ``round_indices`` overrides the default 0..N-1 numbering when the
    caller wants to preserve sparse round IDs (e.g., real audit
    timestamps).
    """
    out: list[RoundResult] = []
    idx = 0
    for i, rec in enumerate(records):
        outcome = getattr(rec, "outcome", None)
        if outcome is None:
            continue
        confidence = float(getattr(rec, "confidence", 0.0))
        round_idx = (
            int(round_indices[i]) if round_indices is not None else idx
        )
        out.append(RoundResult(
            round_index=round_idx,
            winner=str(outcome),
            confidence=confidence,
        ))
        idx += 1
    return tuple(out)

__all__ = [
    "CONVERGENCE_VERDICTS",
    "ConvergenceTracker",
    "ConvergenceTrajectory",
    "ConvergenceVerdict",
    "DEFAULT_DIVERGENCE_SLOPE_THRESHOLD",
    "DEFAULT_MIN_ROUNDS",
    "DEFAULT_OSCILLATION_THRESHOLD",
    "DEFAULT_STABILITY_THRESHOLD",
    "DEFAULT_STABLE_WINDOW_ROUNDS",
    "RoundResult",
    "round_results_from_records",
]
