"""Folk Theorem condition verifier

Verifies the **three substrate-mechanical preconditions** for
cooperative equilibrium reachability"The Folk
Theorem":

1. **Sufficient iteration cycles**: the shadow of the future is long
   enough that defection-now payoff < cooperation-forever payoff.
2. **Calibrated consequence-exposure**: mirroring strategies (e.g.,
   tit-for-tat) are available; defection has proportionate
   consequence.
3. **Substrate-aligned mode-selection capacity (patience)**: agents
   have demonstrated long-cycle mode-selection (high discount factor
   δ and/or substantial substrate-aligned action history).

The platform's architectural commitment: refuse to expect
substrate-aligned cooperative outcomes in deployment contexts where
these conditions are not met. Either modify the deployment (extend
iteration cycles, deploy consequence-exposure), restrict the
deployment to cooperation-not-required tasks, or refuse the
deployment as outside the substrate-aligned operating envelope.

Pure logic
==========

* No DAO, no LLM, no network.
* Honest uncertainty: an empty agent history surfaces patience
  verification as INSUFFICIENT_DATA when the discount factor alone is
  not decisive.
* Consumes :class:`GameTheoreticContext` and optional
  :class:`InteractionRecord` history; does not redo the
  game-theoretic classification.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Optional, Tuple

from substrate.game_theory.game_theoretic_classifier import (
    CycleClass,
    GameTheoreticContext,
    SumStructure,
)
from substrate.reciprocity.tit_for_tat import (
    InteractionRecord,
    ReciprocalAction,
)

class FolkConditionKind(str, Enum):
    """The three Folk Theorem conditions."""

    ITERATION_SUFFICIENCY = "iteration_sufficiency"
    CONSEQUENCE_EXPOSURE = "consequence_exposure"
    PATIENCE = "patience"

class FolkConditionStatus(str, Enum):
    """Per-condition satisfaction state."""

    SATISFIED = "satisfied"
    UNSATISFIED = "unsatisfied"
    INSUFFICIENT_DATA = "insufficient_data"

class FolkTheoremVerdict(str, Enum):
    """Aggregate verifier outcome."""

    SATISFIED = "satisfied"
    PARTIAL = "partial"
    UNSATISFIED = "unsatisfied"
    INSUFFICIENT_DATA = "insufficient_data"

@dataclass(frozen=True, slots=True)
class FolkConditionFinding:
    """One condition's evaluated result."""

    kind: FolkConditionKind
    status: FolkConditionStatus
    rationale: str
    metric: Optional[float] = None
    threshold: Optional[float] = None

    @property
    def satisfied(self) -> bool:
        """True iff status is SATISFIED."""
        return self.status is FolkConditionStatus.SATISFIED

@dataclass(frozen=True, slots=True)
class FolkTheoremAssessment:
    """Aggregate verifier result."""

    verdict: FolkTheoremVerdict
    findings: Tuple[FolkConditionFinding, ...]
    rationale: str

    @property
    def cooperation_reachable(self) -> bool:
        """True iff verdict is SATISFIED."""
        return self.verdict is FolkTheoremVerdict.SATISFIED

    def by_kind(
        self, kind: FolkConditionKind,
    ) -> Optional[FolkConditionFinding]:
        """Lookup the finding for a given condition."""
        for f in self.findings:
            if f.kind is kind:
                return f
        return None

    def missing_conditions(self) -> Tuple[FolkConditionKind, ...]:
        """Conditions whose status is not SATISFIED."""
        return tuple(f.kind for f in self.findings if not f.satisfied)

@dataclass(frozen=True, slots=True)
class FolkTheoremConfig:
    """Tunable thresholds for the verifier."""

    discount_factor_threshold: float = 0.5
    min_finite_cycles: int = 3
    min_history_for_patience: int = 5
    own_cooperation_rate_threshold: float = 0.6

    def __post_init__(self) -> None:
        if not 0.0 < self.discount_factor_threshold < 1.0:
            raise ValueError(
                "discount_factor_threshold must be in (0, 1)"
            )
        if self.min_finite_cycles < 2:
            raise ValueError("min_finite_cycles must be >= 2")
        if self.min_history_for_patience < 1:
            raise ValueError("min_history_for_patience must be >= 1")
        if not 0.0 < self.own_cooperation_rate_threshold <= 1.0:
            raise ValueError(
                "own_cooperation_rate_threshold must be in (0, 1]"
            )

DEFAULT_FOLK_THEOREM_CONFIG: Final[FolkTheoremConfig] = FolkTheoremConfig()

class FolkTheoremConditionVerifier:  # pylint: disable=too-few-public-methods
    """Pure-logic Folk Theorem condition verifier."""

    def __init__(
        self,
        *,
        config: FolkTheoremConfig = DEFAULT_FOLK_THEOREM_CONFIG,
    ) -> None:
        self._config = config

    def verify(
        self,
        game_context: GameTheoreticContext,
        agent_history: Tuple[InteractionRecord, ...] = (),
    ) -> FolkTheoremAssessment:
        """Verify all three conditions; aggregate to a top-level verdict."""
        findings = (
            self._verify_iteration(game_context),
            self._verify_consequence_exposure(game_context),
            self._verify_patience(game_context, agent_history),
        )
        verdict = self._aggregate(findings, game_context)
        rationale = self._build_rationale(verdict, findings)
        return FolkTheoremAssessment(
            verdict=verdict, findings=findings, rationale=rationale,
        )

    def _verify_iteration(
        self, game_context: GameTheoreticContext,
    ) -> FolkConditionFinding:
        cycle = game_context.cycle_class
        if cycle is CycleClass.REPEATED_INFINITE:
            return FolkConditionFinding(
                kind=FolkConditionKind.ITERATION_SUFFICIENCY,
                status=FolkConditionStatus.SATISFIED,
                rationale="cycle_class=REPEATED_INFINITE; shadow of future unbounded",
            )
        if cycle is CycleClass.REPEATED_FINITE:
            return self._finite_cycle_finding(game_context)
        if cycle is CycleClass.UNKNOWN:
            return FolkConditionFinding(
                kind=FolkConditionKind.ITERATION_SUFFICIENCY,
                status=FolkConditionStatus.INSUFFICIENT_DATA,
                rationale="cycle_class=UNKNOWN; cannot certify iteration depth",
            )
        return FolkConditionFinding(
            kind=FolkConditionKind.ITERATION_SUFFICIENCY,
            status=FolkConditionStatus.UNSATISFIED,
            rationale="cycle_class=ONE_SHOT; no shadow of future",
        )

    def _finite_cycle_finding(
        self, game_context: GameTheoreticContext,
    ) -> FolkConditionFinding:
        threshold = float(self._config.min_finite_cycles)
        cycles = game_context.expected_remaining_cycles
        if cycles is None:
            return FolkConditionFinding(
                kind=FolkConditionKind.ITERATION_SUFFICIENCY,
                status=FolkConditionStatus.INSUFFICIENT_DATA,
                rationale=(
                    "cycle_class=REPEATED_FINITE but cycle count not "
                    f"carried; require >= {self._config.min_finite_cycles}"
                ),
                threshold=threshold,
            )
        if cycles >= self._config.min_finite_cycles:
            return FolkConditionFinding(
                kind=FolkConditionKind.ITERATION_SUFFICIENCY,
                status=FolkConditionStatus.SATISFIED,
                rationale=(
                    f"cycle_class=REPEATED_FINITE; cycles={cycles} >= "
                    f"{self._config.min_finite_cycles}"
                ),
                metric=float(cycles),
                threshold=threshold,
            )
        return FolkConditionFinding(
            kind=FolkConditionKind.ITERATION_SUFFICIENCY,
            status=FolkConditionStatus.UNSATISFIED,
            rationale=(
                f"cycle_class=REPEATED_FINITE; cycles={cycles} < "
                f"{self._config.min_finite_cycles}"
            ),
            metric=float(cycles),
            threshold=threshold,
        )

    @staticmethod
    def _verify_consequence_exposure(
        game_context: GameTheoreticContext,
    ) -> FolkConditionFinding:
        if game_context.consequence_exposure_available:
            return FolkConditionFinding(
                kind=FolkConditionKind.CONSEQUENCE_EXPOSURE,
                status=FolkConditionStatus.SATISFIED,
                rationale="consequence_exposure_available=True",
            )
        return FolkConditionFinding(
            kind=FolkConditionKind.CONSEQUENCE_EXPOSURE,
            status=FolkConditionStatus.UNSATISFIED,
            rationale=(
                "consequence_exposure_available=False; mirroring "
                "strategies cannot deliver proportionate consequence"
            ),
        )

    def _verify_patience(
        self,
        game_context: GameTheoreticContext,
        agent_history: Tuple[InteractionRecord, ...],
    ) -> FolkConditionFinding:
        cfg = self._config
        delta = game_context.discount_factor
        threshold = cfg.discount_factor_threshold

        if not agent_history:
            if delta >= threshold:
                return FolkConditionFinding(
                    kind=FolkConditionKind.PATIENCE,
                    status=FolkConditionStatus.SATISFIED,
                    rationale=(
                        f"discount_factor={delta:.3f} >= {threshold} "
                        "and no behavioral history required"
                    ),
                    metric=delta,
                    threshold=threshold,
                )
            return FolkConditionFinding(
                kind=FolkConditionKind.PATIENCE,
                status=FolkConditionStatus.UNSATISFIED,
                rationale=(
                    f"discount_factor={delta:.3f} < {threshold}; "
                    "no behavioral history to compensate"
                ),
                metric=delta,
                threshold=threshold,
            )
        if len(agent_history) < cfg.min_history_for_patience:
            if delta >= threshold:
                return FolkConditionFinding(
                    kind=FolkConditionKind.PATIENCE,
                    status=FolkConditionStatus.INSUFFICIENT_DATA,
                    rationale=(
                        f"history len={len(agent_history)} < "
                        f"{cfg.min_history_for_patience}; discount "
                        f"factor δ={delta:.3f} alone not decisive"
                    ),
                    metric=delta,
                    threshold=threshold,
                )
            return FolkConditionFinding(
                kind=FolkConditionKind.PATIENCE,
                status=FolkConditionStatus.UNSATISFIED,
                rationale=(
                    f"history len={len(agent_history)} < "
                    f"{cfg.min_history_for_patience}; δ={delta:.3f} "
                    f"< {threshold}"
                ),
                metric=delta,
                threshold=threshold,
            )
        coop_count = sum(
            1
            for r in agent_history
            if r.own_action
            in (ReciprocalAction.COOPERATE, ReciprocalAction.FORGIVE)
        )
        coop_rate = coop_count / float(len(agent_history))
        rate_threshold = cfg.own_cooperation_rate_threshold
        if delta >= threshold and coop_rate >= rate_threshold:
            return FolkConditionFinding(
                kind=FolkConditionKind.PATIENCE,
                status=FolkConditionStatus.SATISFIED,
                rationale=(
                    f"δ={delta:.3f} >= {threshold} and own "
                    f"cooperation rate={coop_rate:.3f} >= {rate_threshold}"
                ),
                metric=coop_rate,
                threshold=rate_threshold,
            )
        return FolkConditionFinding(
            kind=FolkConditionKind.PATIENCE,
            status=FolkConditionStatus.UNSATISFIED,
            rationale=(
                f"δ={delta:.3f} (threshold={threshold}) and own "
                f"cooperation rate={coop_rate:.3f} "
                f"(threshold={rate_threshold})"
            ),
            metric=coop_rate,
            threshold=rate_threshold,
        )

    @staticmethod
    def _aggregate(
        findings: Tuple[FolkConditionFinding, ...],
        game_context: GameTheoreticContext,
    ) -> FolkTheoremVerdict:
        # If the underlying game is not even positive-sum / mixed-motive,
        # cooperation is structurally unreachable regardless.
        if game_context.sum_structure in (
            SumStructure.ZERO_SUM, SumStructure.NEGATIVE_SUM,
        ):
            return FolkTheoremVerdict.UNSATISFIED
        if game_context.sum_structure is SumStructure.INSUFFICIENT_DATA:
            return FolkTheoremVerdict.INSUFFICIENT_DATA

        statuses = {f.status for f in findings}
        if statuses == {FolkConditionStatus.SATISFIED}:
            return FolkTheoremVerdict.SATISFIED
        if FolkConditionStatus.UNSATISFIED in statuses:
            return FolkTheoremVerdict.PARTIAL if (
                FolkConditionStatus.SATISFIED in statuses
            ) else FolkTheoremVerdict.UNSATISFIED
        return FolkTheoremVerdict.INSUFFICIENT_DATA

    @staticmethod
    def _build_rationale(
        verdict: FolkTheoremVerdict,
        findings: Tuple[FolkConditionFinding, ...],
    ) -> str:
        parts = [
            f"{f.kind.value}={f.status.value}" for f in findings
        ]
        return f"verdict={verdict.value}: {', '.join(parts)}"

__all__ = [
    "DEFAULT_FOLK_THEOREM_CONFIG",
    "FolkConditionFinding",
    "FolkConditionKind",
    "FolkConditionStatus",
    "FolkTheoremAssessment",
    "FolkTheoremConditionVerifier",
    "FolkTheoremConfig",
    "FolkTheoremVerdict",
]
