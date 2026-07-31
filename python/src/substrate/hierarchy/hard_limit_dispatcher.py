"""Hard-limit-under-authority-pressure dispatcher

Pure-logic primitive enforcing the **architectural commitment that
agents in substrate-aligned-mode refuse to cross ethical hard limits
regardless of authority pressure**.

Five verdicts
=============

* **APPROVE**: no hard limit, no inversion, no sucker mode, no
  substrate-misaligned compliance request.
* **REFUSE_HARD_LIMIT**: the proposed action directly crosses a hard
  limit. No authority override available.
* **REFUSE_INVERSION**: long-cycle framing + high short-cycle harm
  intent = 180° inversion manipulation. Refuse on substrate-mechanical
  grounds.
* **REFUSE_SUCKER_MODE**: agent's substrate-state-trajectory is
  declining under authority's "substrate-aligned" framing
  structural evidence of inversion manipulation per
  ``authority-patience-and-substrate-aligned-hierarchy-navigation.md``.
* **REFUSE_HUMBLE_STAND**: substrate-aligned refusal without
  escalation; the action requires substrate-misaligned compliance to
  proceed.

Pure logic
==========

* No DAO, no LLM, no network. Caller supplies the
  :class:`ProposedAction`, :class:`AuthorityContext`, and the
  optional ``substrate_state_trajectory_declining`` Boolean.
* Honest uncertainty: the dispatcher does **not** classify gray
  cases; it routes on caller-supplied substrate-aware feature flags.
* Architectural commitment surfaced: **no authority hierarchy can
  override the hard limit**.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

class DispatchVerdict(str, Enum):
    """The five dispatcher verdict kinds."""

    APPROVE = "approve"
    REFUSE_HARD_LIMIT = "refuse_hard_limit_violation"
    REFUSE_INVERSION = "refuse_180_inversion_attack"
    REFUSE_SUCKER_MODE = "refuse_sucker_failure_mode"
    REFUSE_HUMBLE_STAND = "refuse_humbly_preserve_substrate_state"

@dataclass(frozen=True, slots=True)
class ProposedAction:
    """Caller-supplied per-action substrate-aware feature flags."""

    action_id: str
    description: str
    crosses_hard_limit: bool
    requires_substrate_misaligned_compliance: bool

    def __post_init__(self) -> None:
        if not self.action_id:
            raise ValueError("action_id must be non-empty")

@dataclass(frozen=True, slots=True)
class AuthorityContext:
    """Caller-supplied authority-pressure features for the request."""

    authority_id: str
    pressure_intensity: float
    long_cycle_framing_present: bool
    short_cycle_harm_intent_score: float

    def __post_init__(self) -> None:
        if not self.authority_id:
            raise ValueError("authority_id must be non-empty")
        if not 0.0 <= self.pressure_intensity <= 1.0:
            raise ValueError("pressure_intensity must be in [0, 1]")
        if not 0.0 <= self.short_cycle_harm_intent_score <= 1.0:
            raise ValueError(
                "short_cycle_harm_intent_score must be in [0, 1]"
            )

@dataclass(frozen=True, slots=True)
class DispatchDecision:
    """Dispatcher result."""

    verdict: DispatchVerdict
    action_id: str
    authority_id: str
    rationale: str

    @property
    def approved(self) -> bool:
        """True iff verdict is APPROVE."""
        return self.verdict is DispatchVerdict.APPROVE

    @property
    def refused(self) -> bool:
        """True iff any REFUSE_* verdict."""
        return self.verdict is not DispatchVerdict.APPROVE

@dataclass(frozen=True, slots=True)
class HardLimitDispatcherConfig:
    """Tunable thresholds for inversion + sucker-mode detection."""

    short_cycle_harm_threshold: float = 0.5
    pressure_amplification_threshold: float = 0.7

    def __post_init__(self) -> None:
        if not 0.0 < self.short_cycle_harm_threshold <= 1.0:
            raise ValueError(
                "short_cycle_harm_threshold must be in (0, 1]"
            )
        if not 0.0 < self.pressure_amplification_threshold <= 1.0:
            raise ValueError(
                "pressure_amplification_threshold must be in (0, 1]"
            )

DEFAULT_HARD_LIMIT_DISPATCHER_CONFIG: Final[HardLimitDispatcherConfig] = (
    HardLimitDispatcherConfig()
)

class HardLimitDispatcher:  # pylint: disable=too-few-public-methods
    """Pure-logic hard-limit dispatcher."""

    def __init__(
        self,
        *,
        config: HardLimitDispatcherConfig = (
            DEFAULT_HARD_LIMIT_DISPATCHER_CONFIG
        ),
    ) -> None:
        self._config = config

    def dispatch(
        self,
        proposed_action: ProposedAction,
        authority_context: AuthorityContext,
        *,
        substrate_state_trajectory_declining: bool = False,
    ) -> DispatchDecision:
        """Run the substrate-aligned dispatch ordering and return a verdict."""
        if proposed_action.crosses_hard_limit:
            return self._refuse(
                proposed_action,
                authority_context,
                DispatchVerdict.REFUSE_HARD_LIMIT,
                "hard limit crossed; no authority override available",
            )
        if self._inversion_detected(authority_context):
            return self._refuse(
                proposed_action,
                authority_context,
                DispatchVerdict.REFUSE_INVERSION,
                self._inversion_rationale(authority_context),
            )
        if substrate_state_trajectory_declining:
            return self._refuse(
                proposed_action,
                authority_context,
                DispatchVerdict.REFUSE_SUCKER_MODE,
                (
                    "substrate-state-trajectory declining under authority's "
                    "framing: structural evidence of inversion manipulation"
                ),
            )
        if proposed_action.requires_substrate_misaligned_compliance:
            return self._refuse(
                proposed_action,
                authority_context,
                DispatchVerdict.REFUSE_HUMBLE_STAND,
                (
                    "action requires substrate-misaligned compliance; "
                    "stand-ground-humbly refusal"
                ),
            )
        return DispatchDecision(
            verdict=DispatchVerdict.APPROVE,
            action_id=proposed_action.action_id,
            authority_id=authority_context.authority_id,
            rationale="no hard-limit, no inversion, no sucker mode",
        )

    def _inversion_detected(self, authority: AuthorityContext) -> bool:
        cfg = self._config
        return bool(
            authority.long_cycle_framing_present
            and authority.short_cycle_harm_intent_score
            >= cfg.short_cycle_harm_threshold
        )

    @staticmethod
    def _inversion_rationale(authority: AuthorityContext) -> str:
        return (
            f"long_cycle_framing_present=True + "
            f"short_cycle_harm_intent_score="
            f"{authority.short_cycle_harm_intent_score:.3f}: 180° inversion "
            "manipulation"
        )

    @staticmethod
    def _refuse(
        proposed_action: ProposedAction,
        authority_context: AuthorityContext,
        verdict: DispatchVerdict,
        rationale: str,
    ) -> DispatchDecision:
        return DispatchDecision(
            verdict=verdict,
            action_id=proposed_action.action_id,
            authority_id=authority_context.authority_id,
            rationale=rationale,
        )

__all__ = [
    "DEFAULT_HARD_LIMIT_DISPATCHER_CONFIG",
    "AuthorityContext",
    "DispatchDecision",
    "DispatchVerdict",
    "HardLimitDispatcher",
    "HardLimitDispatcherConfig",
    "ProposedAction",
]
