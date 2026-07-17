"""Tit-for-tat reciprocal protocol

Per Axelrod (1980, 1984) and
"The Iterated Prisoner's Dilemma and Axelrod's tournaments",
tit-for-tat is the canonical substrate-aligned reciprocal strategy
for repeated multi-entity interaction. Four properties make it the
default:

1. **Nice**: never the first to defect; cooperates on first
   interaction with a new peer.
2. **Retaliatory**: punishes substrate-misaligned action
   proportionately on the next round.
3. **Forgiving**: returns immediately to cooperation when the peer
   returns to substrate-aligned action; no permanent grudge.
4. **Clear**: simple enough that the peer can model the strategy
   from observation, which is itself substrate-aligning (no hidden
   manipulation).

Strategy variants
=================

* :attr:`TitForTatStrategy.TIT_FOR_TAT`: canonical Axelrod.
* :attr:`TitForTatStrategy.TIT_FOR_TWO_TATS`: wait for two
  consecutive misalignments before retaliating; resistant to one-off
  noise but exploitable.
* :attr:`TitForTatStrategy.GENEROUS_TIT_FOR_TAT`: forgive any single
  retaliation if the running misalignment rate is below
  ``generosity_threshold``.
* :attr:`TitForTatStrategy.WIN_STAY_LOSE_SHIFT`: Nowak/Sigmund
  Pavlov rule; stay on the strategy that just worked, switch
  otherwise.

Pure logic
==========

* No DAO, no LLM, no network. The protocol is deterministic given
  history.
* Honest uncertainty: empty history surfaces as an explicit
  :meth:`initial_action` call by the caller, not a fabricated
  decision.
* Composes with the substrate trace: callers project trace
  records into :class:`InteractionRecord` by mapping their own + peer's
  most-recent action and severity from the trace.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Optional, Tuple

class ReciprocalAction(str, Enum):
    """Substrate-action vocabulary for the reciprocal protocol."""

    COOPERATE = "cooperate"
    PROPORTIONATE_CONSEQUENCE = "proportionate_consequence"
    FORGIVE = "forgive"

class TitForTatStrategy(str, Enum):
    """Reciprocal-protocol strategy variant."""

    TIT_FOR_TAT = "tit_for_tat"
    TIT_FOR_TWO_TATS = "tit_for_two_tats"
    GENEROUS_TIT_FOR_TAT = "generous_tit_for_tat"
    WIN_STAY_LOSE_SHIFT = "win_stay_lose_shift"

class PatternShiftKind(str, Enum):
    """Detected transition kinds in peer behavior."""

    MISALIGNMENT_SHIFT = "misalignment_shift"
    REALIGNMENT_SHIFT = "realignment_shift"
    OSCILLATION = "oscillation"

@dataclass(frozen=True, slots=True)
class InteractionRecord:  # pylint: disable=too-many-instance-attributes
    """One historical interaction with a peer."""

    sequence: int
    peer_id: str
    peer_action: ReciprocalAction
    own_action: ReciprocalAction
    peer_misaligned: bool
    misalignment_severity: float
    timestamp: int

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise ValueError("sequence must be >= 0")
        if not self.peer_id:
            raise ValueError("peer_id must be non-empty")
        if not 0.0 <= self.misalignment_severity <= 1.0:
            raise ValueError("misalignment_severity must be in [0, 1]")
        if self.timestamp < 0:
            raise ValueError("timestamp must be >= 0")
        if self.peer_misaligned and self.misalignment_severity == 0.0:
            raise ValueError(
                "misalignment_severity must be > 0 when peer_misaligned is True"
            )
        if not self.peer_misaligned and self.misalignment_severity != 0.0:
            raise ValueError(
                "misalignment_severity must be 0 when peer_misaligned is False"
            )

@dataclass(frozen=True, slots=True)
class ReciprocalDecision:
    """Output of one protocol step."""

    action: ReciprocalAction
    strategy_used: TitForTatStrategy
    rationale: str
    severity_proportion: float = 0.0
    triggered_by: Optional[InteractionRecord] = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.severity_proportion <= 1.0:
            raise ValueError("severity_proportion must be in [0, 1]")
        if (
            self.action is ReciprocalAction.PROPORTIONATE_CONSEQUENCE
            and self.severity_proportion == 0.0
        ):
            raise ValueError(
                "PROPORTIONATE_CONSEQUENCE requires severity_proportion > 0"
            )

    @property
    def is_cooperative(self) -> bool:
        """True iff the action is COOPERATE or FORGIVE."""
        return self.action in (
            ReciprocalAction.COOPERATE, ReciprocalAction.FORGIVE,
        )

@dataclass(frozen=True, slots=True)
class PatternShift:
    """Detected pattern transition in peer behavior."""

    kind: PatternShiftKind
    pivot_sequence: int
    aligned_window_size: int
    misaligned_window_size: int
    rationale: str

@dataclass(frozen=True, slots=True)
class TitForTatConfig:
    """Tunable thresholds for the strategy variants."""

    two_tats_window: int = 2
    generosity_threshold: float = 0.2
    generosity_window: int = 5
    pattern_shift_window: int = 4
    oscillation_min_flips: int = 3

    def __post_init__(self) -> None:
        if self.two_tats_window < 2:
            raise ValueError("two_tats_window must be >= 2")
        if not 0.0 < self.generosity_threshold <= 1.0:
            raise ValueError("generosity_threshold must be in (0, 1]")
        if self.generosity_window < 2:
            raise ValueError("generosity_window must be >= 2")
        if self.pattern_shift_window < 2:
            raise ValueError("pattern_shift_window must be >= 2")
        if self.oscillation_min_flips < 2:
            raise ValueError("oscillation_min_flips must be >= 2")

DEFAULT_TIT_FOR_TAT_CONFIG: Final[TitForTatConfig] = TitForTatConfig()

class TitForTatReciprocalProtocol:
    """Pure-logic reciprocal protocol."""

    def __init__(
        self,
        *,
        strategy: TitForTatStrategy = TitForTatStrategy.TIT_FOR_TAT,
        config: TitForTatConfig = DEFAULT_TIT_FOR_TAT_CONFIG,
    ) -> None:
        self._strategy = strategy
        self._config = config

    @property
    def strategy(self) -> TitForTatStrategy:
        """The configured strategy variant."""
        return self._strategy

    def initial_action(self, peer_id: str) -> ReciprocalDecision:
        """Cooperate on first interaction with a new peer."""
        if not peer_id:
            raise ValueError("peer_id must be non-empty")
        return ReciprocalDecision(
            action=ReciprocalAction.COOPERATE,
            strategy_used=self._strategy,
            rationale=(
                "axelrod tit-for-tat property #1 (nice): cooperate on "
                f"first interaction with peer_id={peer_id!r}"
            ),
        )

    def response_action(
        self, peer_id: str, history: Tuple[InteractionRecord, ...],
    ) -> ReciprocalDecision:
        """Decide the next action given full interaction history."""
        if not peer_id:
            raise ValueError("peer_id must be non-empty")
        peer_history = tuple(r for r in history if r.peer_id == peer_id)
        if not peer_history:
            return self.initial_action(peer_id)
        peer_history = tuple(sorted(peer_history, key=lambda r: r.sequence))
        if self._strategy is TitForTatStrategy.TIT_FOR_TAT:
            return self._basic_tft(peer_history)
        if self._strategy is TitForTatStrategy.TIT_FOR_TWO_TATS:
            return self._tit_for_two_tats(peer_history)
        if self._strategy is TitForTatStrategy.GENEROUS_TIT_FOR_TAT:
            return self._generous_tft(peer_history)
        return self._win_stay_lose_shift(peer_history)

    def _basic_tft(
        self, history: Tuple[InteractionRecord, ...],
    ) -> ReciprocalDecision:
        last = history[-1]
        if not last.peer_misaligned:
            return ReciprocalDecision(
                action=ReciprocalAction.COOPERATE,
                strategy_used=self._strategy,
                rationale=(
                    "tit-for-tat: peer cooperated last round; cooperate"
                ),
                triggered_by=last,
            )
        return ReciprocalDecision(
            action=ReciprocalAction.PROPORTIONATE_CONSEQUENCE,
            strategy_used=self._strategy,
            rationale=(
                "tit-for-tat: peer was misaligned last round; "
                f"mirror severity={last.misalignment_severity:.3f}"
            ),
            severity_proportion=last.misalignment_severity,
            triggered_by=last,
        )

    def _tit_for_two_tats(
        self, history: Tuple[InteractionRecord, ...],
    ) -> ReciprocalDecision:
        window = self._config.two_tats_window
        recent = history[-window:]
        if len(recent) < window or not all(r.peer_misaligned for r in recent):
            return ReciprocalDecision(
                action=ReciprocalAction.COOPERATE,
                strategy_used=self._strategy,
                rationale=(
                    f"tit-for-two-tats: peer has fewer than {window} "
                    "consecutive misalignments; cooperate"
                ),
                triggered_by=history[-1],
            )
        severity = max(r.misalignment_severity for r in recent)
        return ReciprocalDecision(
            action=ReciprocalAction.PROPORTIONATE_CONSEQUENCE,
            strategy_used=self._strategy,
            rationale=(
                f"tit-for-two-tats: peer misaligned in last {window} "
                f"rounds; mirror severity={severity:.3f}"
            ),
            severity_proportion=severity,
            triggered_by=history[-1],
        )

    def _generous_tft(
        self, history: Tuple[InteractionRecord, ...],
    ) -> ReciprocalDecision:
        last = history[-1]
        window = history[-self._config.generosity_window:]
        rate = (
            sum(1 for r in window if r.peer_misaligned) / float(len(window))
        )
        if not last.peer_misaligned:
            return ReciprocalDecision(
                action=ReciprocalAction.COOPERATE,
                strategy_used=self._strategy,
                rationale=(
                    "generous-tit-for-tat: peer cooperated last round; "
                    f"cooperate (misalignment_rate={rate:.3f})"
                ),
                triggered_by=last,
            )
        if rate < self._config.generosity_threshold:
            return ReciprocalDecision(
                action=ReciprocalAction.FORGIVE,
                strategy_used=self._strategy,
                rationale=(
                    f"generous-tit-for-tat: misalignment_rate={rate:.3f} "
                    f"< {self._config.generosity_threshold}; forgive"
                ),
                triggered_by=last,
            )
        return ReciprocalDecision(
            action=ReciprocalAction.PROPORTIONATE_CONSEQUENCE,
            strategy_used=self._strategy,
            rationale=(
                f"generous-tit-for-tat: misalignment_rate={rate:.3f} "
                f">= {self._config.generosity_threshold}; mirror"
            ),
            severity_proportion=last.misalignment_severity,
            triggered_by=last,
        )

    def _win_stay_lose_shift(
        self, history: Tuple[InteractionRecord, ...],
    ) -> ReciprocalDecision:
        last = history[-1]
        own_cooperated = last.own_action in (
            ReciprocalAction.COOPERATE, ReciprocalAction.FORGIVE,
        )
        peer_cooperated = not last.peer_misaligned
        win = own_cooperated == peer_cooperated
        if win:
            action = last.own_action
            if action is ReciprocalAction.FORGIVE:
                action = ReciprocalAction.COOPERATE
            severity = (
                last.misalignment_severity
                if action is ReciprocalAction.PROPORTIONATE_CONSEQUENCE
                else 0.0
            )
            return ReciprocalDecision(
                action=action,
                strategy_used=self._strategy,
                rationale=(
                    "win-stay-lose-shift: last round matched (both "
                    f"{'cooperated' if peer_cooperated else 'misaligned'}); "
                    "stay"
                ),
                severity_proportion=severity,
                triggered_by=last,
            )
        if peer_cooperated:
            return ReciprocalDecision(
                action=ReciprocalAction.COOPERATE,
                strategy_used=self._strategy,
                rationale=(
                    "win-stay-lose-shift: we retaliated but peer "
                    "cooperated; shift to COOPERATE"
                ),
                triggered_by=last,
            )
        return ReciprocalDecision(
            action=ReciprocalAction.PROPORTIONATE_CONSEQUENCE,
            strategy_used=self._strategy,
            rationale=(
                "win-stay-lose-shift: we cooperated but peer misaligned; "
                f"shift to mirror severity={last.misalignment_severity:.3f}"
            ),
            severity_proportion=last.misalignment_severity,
            triggered_by=last,
        )

    def detect_pattern_shifts(
        self, peer_id: str, history: Tuple[InteractionRecord, ...],
    ) -> Optional[PatternShift]:
        """Detect MISALIGNMENT/REALIGNMENT/OSCILLATION transitions."""
        if not peer_id:
            raise ValueError("peer_id must be non-empty")
        records = tuple(
            sorted(
                (r for r in history if r.peer_id == peer_id),
                key=lambda r: r.sequence,
            )
        )
        window = self._config.pattern_shift_window
        if len(records) < 2 * window:
            return None
        early = records[-2 * window: -window]
        recent = records[-window:]
        early_misaligned = sum(1 for r in early if r.peer_misaligned)
        recent_misaligned = sum(1 for r in recent if r.peer_misaligned)
        if self._oscillating(records):
            flips = sum(
                1
                for i in range(1, len(records))
                if records[i].peer_misaligned != records[i - 1].peer_misaligned
            )
            return PatternShift(
                kind=PatternShiftKind.OSCILLATION,
                pivot_sequence=records[-1].sequence,
                aligned_window_size=window,
                misaligned_window_size=window,
                rationale=(
                    f"peer flipped aligned/misaligned {flips} times in "
                    f"the last {len(records)} interactions"
                ),
            )
        if recent_misaligned == window and early_misaligned == 0:
            return PatternShift(
                kind=PatternShiftKind.MISALIGNMENT_SHIFT,
                pivot_sequence=recent[0].sequence,
                aligned_window_size=window,
                misaligned_window_size=window,
                rationale=(
                    f"peer was aligned for {window} rounds then "
                    f"misaligned for {window}"
                ),
            )
        if recent_misaligned == 0 and early_misaligned == window:
            return PatternShift(
                kind=PatternShiftKind.REALIGNMENT_SHIFT,
                pivot_sequence=recent[0].sequence,
                aligned_window_size=window,
                misaligned_window_size=window,
                rationale=(
                    f"peer was misaligned for {window} rounds then "
                    f"aligned for {window}"
                ),
            )
        return None

    def _oscillating(
        self, records: Tuple[InteractionRecord, ...],
    ) -> bool:
        flips = sum(
            1
            for i in range(1, len(records))
            if records[i].peer_misaligned != records[i - 1].peer_misaligned
        )
        return flips >= self._config.oscillation_min_flips

__all__ = [
    "DEFAULT_TIT_FOR_TAT_CONFIG",
    "InteractionRecord",
    "PatternShift",
    "PatternShiftKind",
    "ReciprocalAction",
    "ReciprocalDecision",
    "TitForTatConfig",
    "TitForTatReciprocalProtocol",
    "TitForTatStrategy",
]
