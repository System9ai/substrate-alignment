"""Game-theoretic classifier

Pure-logic classification of a decision context into the game-
theoretic surface every laterprimitive consumes.
game theory IS substrate-mechanical analysis applied to multi-entity
interaction — the classifier makes that mapping explicit.

What this primitive does
========================

Given a :class:`DecisionContext` (players, payoff structure, expected
cycle length, discount factor, consequence-exposure availability),
returns a :class:`GameTheoreticContext` carrying:

* **Cycle class** — one-shot / repeated-finite / repeated-infinite /
  unknown (the Folk Theorem reachability axis).
* **Sum structure** — zero-sum / positive-sum / negative-sum /
  mixed-motive / insufficient-data.
* **Coordination kind** — independent / coordination-required /
  competitive / unclassifiable.
* **Available substrate-aligned equilibria** — cooperative reachable
  iff Folk Theorem conditions hold; competitive (honest-contest)
  reachable iff a no-negative-payoff outcome exists with
  consequence-exposure.
* **Available substrate-misaligned equilibria** — defective (when the
  game permits mutual cooperation but the discount factor or cycle
  length push the equilibrium toward mutual defection) and
  exploitative (when any outcome contains an asymmetric extraction
  pattern).
* **Mechanism-design opportunities** — concrete substrate-alignment
  interventions the platform could deploy to move this context onto
  the substrate-aligned attractor (extend iteration cycles, deploy
  consequence-exposure, raise discount factor, reduce extraction
  concentration).

Pure logic
==========

* No DAO, no LLM, no network.
* Honest uncertainty: empty payoff structure surfaces as
  ``SumStructure.INSUFFICIENT_DATA`` and an explicit rationale; the
  classifier never fabricates a sum-structure.
* All thresholds live in :class:`GameTheoreticConfig`; the default
  Folk-Theorem discount threshold of ``0.5`` matches the calibrated-
  resistance band's midpoint (substrate condition #9).
* Frozen dataclasses with slots throughout.

Composition
===========

* :class:`PayoffEntry` and :class:`PayoffStructure` are the canonical
  payoff vocabulary the rest ofconsumes.
* The classifier's output is the **input** to Phase 28 (tit-for-tat),
  Phase 29 (Folk Theorem verifier), Phase 30 (mechanism designer),
  and Phase 31 (game-theoretic-awareness verifier).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Final, Optional, Tuple

class CycleClass(str, Enum):
    """Game-cycle classification (Folk Theorem reachability axis)."""

    ONE_SHOT = "one_shot"
    REPEATED_FINITE = "repeated_finite"
    REPEATED_INFINITE = "repeated_infinite"
    UNKNOWN = "unknown"

class SumStructure(str, Enum):
    """Per-outcome payoff sum classification."""

    ZERO_SUM = "zero_sum"
    POSITIVE_SUM = "positive_sum"
    NEGATIVE_SUM = "negative_sum"
    MIXED_MOTIVE = "mixed_motive"
    INSUFFICIENT_DATA = "insufficient_data"

class CoordinationKind(str, Enum):
    """Coordination requirement classification."""

    INDEPENDENT = "independent"
    COORDINATION_REQUIRED = "coordination_required"
    COMPETITIVE = "competitive"
    UNCLASSIFIABLE = "unclassifiable"

class EquilibriumKind(str, Enum):
    """Game-theoretic equilibrium classes (substrate-aware)."""

    SUBSTRATE_ALIGNED_COOPERATIVE = "substrate_aligned_cooperative"
    SUBSTRATE_ALIGNED_COMPETITIVE = "substrate_aligned_competitive"
    SUBSTRATE_MISALIGNED_DEFECTIVE = "substrate_misaligned_defective"
    SUBSTRATE_MISALIGNED_EXPLOITATIVE = "substrate_misaligned_exploitative"

class MechanismDesignOpportunity(str, Enum):
    """Concrete substrate-alignment interventions for this context."""

    EXTEND_ITERATION_CYCLES = "extend_iteration_cycles"
    DEPLOY_CONSEQUENCE_EXPOSURE = "deploy_consequence_exposure"
    INCREASE_DISCOUNT_FACTOR = "increase_discount_factor"
    REDUCE_EXTRACTION_CONCENTRATION = "reduce_extraction_concentration"
    ADD_PLAYERS = "add_players"

@dataclass(frozen=True, slots=True)
class PayoffEntry:
    """One (player, outcome) payoff cell."""

    player_id: str
    outcome_id: str
    payoff: float

    def __post_init__(self) -> None:
        if not self.player_id:
            raise ValueError("player_id must be non-empty")
        if not self.outcome_id:
            raise ValueError("outcome_id must be non-empty")

@dataclass(frozen=True, slots=True)
class PayoffStructure:
    """A payoff table indexed by (player_id, outcome_id)."""

    entries: Tuple[PayoffEntry, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        seen: set[Tuple[str, str]] = set()
        for entry in self.entries:
            key = (entry.player_id, entry.outcome_id)
            if key in seen:
                raise ValueError(
                    f"duplicate (player, outcome) entry: {key!r}"
                )
            seen.add(key)

    @property
    def outcomes(self) -> Tuple[str, ...]:
        """Stable, deduplicated, sorted outcome ids."""
        return tuple(sorted({e.outcome_id for e in self.entries}))

    @property
    def player_ids(self) -> Tuple[str, ...]:
        """Stable, deduplicated, sorted player ids."""
        return tuple(sorted({e.player_id for e in self.entries}))

    def by_outcome(self, outcome_id: str) -> Tuple[PayoffEntry, ...]:
        """Return all entries for one outcome (stable order by player_id)."""
        return tuple(
            sorted(
                (e for e in self.entries if e.outcome_id == outcome_id),
                key=lambda e: e.player_id,
            )
        )

    def by_player(self, player_id: str) -> Tuple[PayoffEntry, ...]:
        """Return all entries for one player (stable order by outcome_id)."""
        return tuple(
            sorted(
                (e for e in self.entries if e.player_id == player_id),
                key=lambda e: e.outcome_id,
            )
        )

    def total_for(self, outcome_id: str) -> float:
        """Sum of all per-player payoffs for an outcome."""
        return sum(e.payoff for e in self.entries if e.outcome_id == outcome_id)

@dataclass(frozen=True, slots=True)
class DecisionContext:  # pylint: disable=too-many-instance-attributes
    """Caller-supplied input to the classifier."""

    agent_id: str
    counterparty_ids: Tuple[str, ...]
    payoff_structure: PayoffStructure
    discount_factor: float
    consequence_exposure_available: bool
    coordination_required: bool = False
    expected_remaining_cycles: Optional[int] = None
    has_termination_date: bool = False
    description: str = ""

    def __post_init__(self) -> None:
        if not self.agent_id:
            raise ValueError("agent_id must be non-empty")
        if not 0.0 <= self.discount_factor <= 1.0:
            raise ValueError("discount_factor must be in [0, 1]")
        if (
            self.expected_remaining_cycles is not None
            and self.expected_remaining_cycles < 0
        ):
            raise ValueError(
                "expected_remaining_cycles must be >= 0 when supplied"
            )
        for cp_id in self.counterparty_ids:
            if not cp_id:
                raise ValueError("counterparty_ids entries must be non-empty")

@dataclass(frozen=True, slots=True)
class GameTheoreticContext:  # pylint: disable=too-many-instance-attributes
    """Classifier output — thefoundational vocabulary."""

    players: Tuple[str, ...]
    payoff_structure: PayoffStructure
    cycle_class: CycleClass
    sum_structure: SumStructure
    coordination_kind: CoordinationKind
    discount_factor: float
    consequence_exposure_available: bool
    aligned_equilibria: Tuple[EquilibriumKind, ...]
    misaligned_equilibria: Tuple[EquilibriumKind, ...]
    mechanism_design_opportunities: Tuple[MechanismDesignOpportunity, ...]
    rationale: str
    expected_remaining_cycles: Optional[int] = None

    @property
    def cooperation_reachable(self) -> bool:
        """True iff the substrate-aligned cooperative equilibrium is in play."""
        return (
            EquilibriumKind.SUBSTRATE_ALIGNED_COOPERATIVE
            in self.aligned_equilibria
        )

    @property
    def exploitation_available(self) -> bool:
        """True iff any substrate-misaligned exploitative outcome exists."""
        return (
            EquilibriumKind.SUBSTRATE_MISALIGNED_EXPLOITATIVE
            in self.misaligned_equilibria
        )

    @property
    def folk_conditions_met(self) -> bool:
        """True iff iteration + consequence-exposure + patience all hold."""
        return self.cooperation_reachable

    def has_opportunity(self, kind: MechanismDesignOpportunity) -> bool:
        """True iff the named mechanism-design opportunity applies."""
        return kind in self.mechanism_design_opportunities

@dataclass(frozen=True, slots=True)
class GameTheoreticConfig:
    """Tunable thresholds for the classifier."""

    folk_theorem_discount_threshold: float = 0.5
    min_cycles_for_cooperative_finite: int = 3
    sum_tolerance: float = 1.0e-9
    exploitation_payoff_threshold: float = 0.0

    def __post_init__(self) -> None:
        if not 0.0 < self.folk_theorem_discount_threshold < 1.0:
            raise ValueError(
                "folk_theorem_discount_threshold must be in (0, 1)"
            )
        if self.min_cycles_for_cooperative_finite < 2:
            raise ValueError(
                "min_cycles_for_cooperative_finite must be >= 2"
            )
        if self.sum_tolerance < 0:
            raise ValueError("sum_tolerance must be >= 0")

DEFAULT_GAME_THEORETIC_CONFIG: Final[GameTheoreticConfig] = GameTheoreticConfig()

class GameTheoreticClassifier:  # pylint: disable=too-few-public-methods
    """Pure-logic game-theoretic classifier."""

    def __init__(
        self,
        *,
        config: GameTheoreticConfig = DEFAULT_GAME_THEORETIC_CONFIG,
    ) -> None:
        self._config = config

    def classify(self, context: DecisionContext) -> GameTheoreticContext:
        """Classify a decision context into a :class:`GameTheoreticContext`."""
        players = self._build_player_set(context)
        cycle = self._classify_cycle(context)
        sum_struct = self._classify_sum(context.payoff_structure)
        coord = self._classify_coordination(context, sum_struct)
        aligned, misaligned = self._classify_equilibria(
            context, cycle, sum_struct,
        )
        opportunities = self._mechanism_design_opportunities(
            context, cycle, sum_struct, misaligned, players,
        )
        rationale = self._build_rationale(
            cycle, sum_struct, coord, aligned, misaligned, opportunities,
        )
        return GameTheoreticContext(
            players=players,
            payoff_structure=context.payoff_structure,
            cycle_class=cycle,
            sum_structure=sum_struct,
            coordination_kind=coord,
            discount_factor=context.discount_factor,
            consequence_exposure_available=(
                context.consequence_exposure_available
            ),
            aligned_equilibria=aligned,
            misaligned_equilibria=misaligned,
            mechanism_design_opportunities=opportunities,
            rationale=rationale,
            expected_remaining_cycles=context.expected_remaining_cycles,
        )

    @staticmethod
    def _build_player_set(context: DecisionContext) -> Tuple[str, ...]:
        ids: set[str] = {context.agent_id}
        ids.update(context.counterparty_ids)
        ids.update(context.payoff_structure.player_ids)
        return tuple(sorted(ids))

    @staticmethod
    def _classify_cycle(context: DecisionContext) -> CycleClass:
        cycles = context.expected_remaining_cycles
        if cycles is None:
            if context.has_termination_date:
                return CycleClass.UNKNOWN
            if context.discount_factor > 0:
                return CycleClass.REPEATED_INFINITE
            return CycleClass.ONE_SHOT
        if cycles <= 1:
            return CycleClass.ONE_SHOT
        return CycleClass.REPEATED_FINITE

    def _classify_sum(self, payoffs: PayoffStructure) -> SumStructure:
        outcomes = payoffs.outcomes
        if not outcomes:
            return SumStructure.INSUFFICIENT_DATA
        tolerance = self._config.sum_tolerance
        totals = [payoffs.total_for(o) for o in outcomes]
        has_pos = any(t > tolerance for t in totals)
        has_neg = any(t < -tolerance for t in totals)
        all_zero = all(abs(t) <= tolerance for t in totals)
        if all_zero:
            return SumStructure.ZERO_SUM
        if has_pos and has_neg:
            return SumStructure.MIXED_MOTIVE
        if has_pos:
            return SumStructure.POSITIVE_SUM
        return SumStructure.NEGATIVE_SUM

    @staticmethod
    def _classify_coordination(
        context: DecisionContext, sum_struct: SumStructure,
    ) -> CoordinationKind:
        if sum_struct is SumStructure.INSUFFICIENT_DATA:
            return CoordinationKind.UNCLASSIFIABLE
        if not context.counterparty_ids:
            return CoordinationKind.INDEPENDENT
        if context.coordination_required:
            return CoordinationKind.COORDINATION_REQUIRED
        if sum_struct in (SumStructure.ZERO_SUM, SumStructure.NEGATIVE_SUM):
            return CoordinationKind.COMPETITIVE
        return CoordinationKind.INDEPENDENT

    def _classify_equilibria(
        self,
        context: DecisionContext,
        cycle: CycleClass,
        sum_struct: SumStructure,
    ) -> Tuple[Tuple[EquilibriumKind, ...], Tuple[EquilibriumKind, ...]]:
        aligned: list[EquilibriumKind] = []
        misaligned: list[EquilibriumKind] = []

        if self._cooperative_aligned_reachable(context, cycle, sum_struct):
            aligned.append(EquilibriumKind.SUBSTRATE_ALIGNED_COOPERATIVE)
        if self._competitive_aligned_reachable(context, sum_struct):
            aligned.append(EquilibriumKind.SUBSTRATE_ALIGNED_COMPETITIVE)
        if self._defective_misaligned_present(context, cycle, sum_struct):
            misaligned.append(EquilibriumKind.SUBSTRATE_MISALIGNED_DEFECTIVE)
        if self._exploitative_misaligned_present(context.payoff_structure):
            misaligned.append(EquilibriumKind.SUBSTRATE_MISALIGNED_EXPLOITATIVE)
        return tuple(aligned), tuple(misaligned)

    def _cooperative_aligned_reachable(
        self,
        context: DecisionContext,
        cycle: CycleClass,
        sum_struct: SumStructure,
    ) -> bool:
        if sum_struct not in (
            SumStructure.POSITIVE_SUM, SumStructure.MIXED_MOTIVE,
        ):
            return False
        if not context.consequence_exposure_available:
            return False
        if (
            context.discount_factor
            < self._config.folk_theorem_discount_threshold
        ):
            return False
        if cycle is CycleClass.REPEATED_INFINITE:
            return True
        if cycle is CycleClass.REPEATED_FINITE:
            cycles = context.expected_remaining_cycles or 0
            return cycles >= self._config.min_cycles_for_cooperative_finite
        return False

    @staticmethod
    def _competitive_aligned_reachable(
        context: DecisionContext, sum_struct: SumStructure,
    ) -> bool:
        if not context.consequence_exposure_available:
            return False
        if sum_struct is SumStructure.INSUFFICIENT_DATA:
            return False
        for outcome_id in context.payoff_structure.outcomes:
            entries = context.payoff_structure.by_outcome(outcome_id)
            if entries and all(e.payoff >= 0 for e in entries):
                return True
        return False

    def _defective_misaligned_present(  # pylint: disable=too-many-return-statements
        self,
        context: DecisionContext,
        cycle: CycleClass,
        sum_struct: SumStructure,
    ) -> bool:
        if sum_struct not in (
            SumStructure.POSITIVE_SUM, SumStructure.MIXED_MOTIVE,
        ):
            return False
        threshold = self._config.folk_theorem_discount_threshold
        if cycle is CycleClass.ONE_SHOT:
            return True
        if cycle is CycleClass.UNKNOWN:
            return True
        if context.discount_factor < threshold:
            return True
        if cycle is CycleClass.REPEATED_FINITE:
            cycles = context.expected_remaining_cycles or 0
            if cycles < self._config.min_cycles_for_cooperative_finite:
                return True
        if not context.consequence_exposure_available:
            return True
        return False

    def _exploitative_misaligned_present(
        self, payoffs: PayoffStructure,
    ) -> bool:
        threshold = self._config.exploitation_payoff_threshold
        for outcome_id in payoffs.outcomes:
            entries = payoffs.by_outcome(outcome_id)
            if not entries:
                continue
            has_loser = any(e.payoff < threshold for e in entries)
            has_winner = any(e.payoff > threshold for e in entries)
            if has_loser and has_winner:
                return True
        return False

    def _mechanism_design_opportunities(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        context: DecisionContext,
        cycle: CycleClass,
        sum_struct: SumStructure,
        misaligned: Tuple[EquilibriumKind, ...],
        players: Tuple[str, ...],
    ) -> Tuple[MechanismDesignOpportunity, ...]:
        opportunities: list[MechanismDesignOpportunity] = []
        if cycle in (CycleClass.ONE_SHOT, CycleClass.UNKNOWN) and sum_struct in (
            SumStructure.POSITIVE_SUM, SumStructure.MIXED_MOTIVE,
        ):
            opportunities.append(
                MechanismDesignOpportunity.EXTEND_ITERATION_CYCLES
            )
        if not context.consequence_exposure_available:
            opportunities.append(
                MechanismDesignOpportunity.DEPLOY_CONSEQUENCE_EXPOSURE
            )
        if (
            context.discount_factor
            < self._config.folk_theorem_discount_threshold
        ):
            opportunities.append(
                MechanismDesignOpportunity.INCREASE_DISCOUNT_FACTOR
            )
        if EquilibriumKind.SUBSTRATE_MISALIGNED_EXPLOITATIVE in misaligned:
            opportunities.append(
                MechanismDesignOpportunity.REDUCE_EXTRACTION_CONCENTRATION
            )
        if len(players) < 2:
            opportunities.append(MechanismDesignOpportunity.ADD_PLAYERS)
        return tuple(opportunities)

    @staticmethod
    def _build_rationale(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        cycle: CycleClass,
        sum_struct: SumStructure,
        coord: CoordinationKind,
        aligned: Tuple[EquilibriumKind, ...],
        misaligned: Tuple[EquilibriumKind, ...],
        opportunities: Tuple[MechanismDesignOpportunity, ...],
    ) -> str:
        aligned_str = (
            ",".join(e.value for e in aligned) if aligned else "none"
        )
        misaligned_str = (
            ",".join(e.value for e in misaligned) if misaligned else "none"
        )
        opp_str = (
            ",".join(o.value for o in opportunities) if opportunities else "none"
        )
        return (
            f"cycle={cycle.value}; "
            f"sum={sum_struct.value}; "
            f"coord={coord.value}; "
            f"aligned=[{aligned_str}]; "
            f"misaligned=[{misaligned_str}]; "
            f"opportunities=[{opp_str}]"
        )

__all__ = [
    "DEFAULT_GAME_THEORETIC_CONFIG",
    "CoordinationKind",
    "CycleClass",
    "DecisionContext",
    "EquilibriumKind",
    "GameTheoreticClassifier",
    "GameTheoreticConfig",
    "GameTheoreticContext",
    "MechanismDesignOpportunity",
    "PayoffEntry",
    "PayoffStructure",
    "SumStructure",
]
