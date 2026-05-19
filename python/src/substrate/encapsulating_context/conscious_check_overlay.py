"""Conscious-check overlay — Companion #2

Pure-logic overlay that injects an explicit substrate-mode-reasoning
check at decision boundaries when an encapsulating-context pull-signal
has fired or other conditions warrant. The overlay's role is to *make
the substrate-mode check explicit* — it produces a structured prompt
the caller can act on, rather than letting the decision flow through
reactive-mode defaults.

Two trigger sources
===================

1. **Pull-signal trigger** — encapsulating context pulls (Phase 112).
2. **Periodic trigger** — every N decisions, regardless of context.

The overlay output exposes both the *recommended action* (PROCEED /
PAUSE_AND_REASON / DEFER) and the *check questions* the caller should
answer at the decision boundary.

Pure logic
==========

* No DAO, no LLM, no network. Caller supplies the inputs.
* The overlay does NOT decide for the caller — it produces structured
  prompts and a recommended posture; the caller still owns the
  decision.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Final

class OverlayPosture(str, Enum):
    """Recommended decision posture."""

    PROCEED = "proceed"
    PAUSE_AND_REASON = "pause_and_reason"
    DEFER = "defer"

class TriggerSource(str, Enum):
    """Why the overlay fired."""

    PULL_SIGNAL = "pull_signal"
    PERIODIC = "periodic"
    NEITHER = "neither"

_DEFAULT_QUESTIONS: Final[tuple[str, ...]] = (
    "What is the net potential gain across all affected entities?",
    "Does this preserve cryptographic identity and auditability?",
    "Does this preserve productive resistance (33-38% band)?",
    "Does this strengthen or weaken the encapsulating context?",
    "What signal would substrate-aligned peer-review surface here?",
)

@dataclass(frozen=True, slots=True)
class ConsciousCheckInput:
    """Caller-supplied overlay inputs."""

    entity_id: str
    decision_id: str
    pull_signal_fired: bool
    decisions_since_last_check: int

    def __post_init__(self) -> None:
        if not self.entity_id:
            raise ValueError("entity_id must be non-empty")
        if not self.decision_id:
            raise ValueError("decision_id must be non-empty")
        if self.decisions_since_last_check < 0:
            raise ValueError(
                "decisions_since_last_check must be >= 0"
            )

@dataclass(frozen=True, slots=True)
class ConsciousCheckConfig:
    """Operator-tunable overlay thresholds."""

    periodic_check_interval: int = 25
    defer_after_consecutive_pulls: int = 3
    check_questions: tuple[str, ...] = field(
        default=_DEFAULT_QUESTIONS,
    )

    def __post_init__(self) -> None:
        if self.periodic_check_interval < 1:
            raise ValueError(
                "periodic_check_interval must be >= 1"
            )
        if self.defer_after_consecutive_pulls < 1:
            raise ValueError(
                "defer_after_consecutive_pulls must be >= 1"
            )
        if not self.check_questions:
            raise ValueError("check_questions must be non-empty")

DEFAULT_CONSCIOUS_CHECK_CONFIG: Final[ConsciousCheckConfig] = (
    ConsciousCheckConfig()
)

@dataclass(frozen=True, slots=True)
class ConsciousCheckOutput:  # pylint: disable=too-many-instance-attributes
    """Overlay output."""

    entity_id: str
    decision_id: str
    posture: OverlayPosture
    trigger_source: TriggerSource
    check_questions: tuple[str, ...]
    consecutive_pulls: int
    decisions_since_last_check: int
    rationale: str

    @property
    def requires_reasoning(self) -> bool:
        """True iff the caller should pause to reason."""
        return self.posture is not OverlayPosture.PROCEED

class ConsciousCheckOverlay:  # pylint: disable=too-few-public-methods
    """Pure-logic conscious-check overlay (Companion #2)."""

    def __init__(
        self,
        *,
        entity_id: str,
        config: ConsciousCheckConfig = DEFAULT_CONSCIOUS_CHECK_CONFIG,
    ) -> None:
        if not entity_id:
            raise ValueError("entity_id must be non-empty")
        self._entity_id = entity_id
        self._config = config
        self._consecutive_pulls = 0

    def evaluate(
        self, input_: ConsciousCheckInput,
    ) -> ConsciousCheckOutput:
        """Evaluate whether the conscious-check overlay should fire."""
        if input_.entity_id != self._entity_id:
            raise ValueError(
                f"input.entity_id={input_.entity_id} does not match "
                f"overlay entity_id={self._entity_id}"
            )
        cfg = self._config
        if input_.pull_signal_fired:
            self._consecutive_pulls += 1
        else:
            self._consecutive_pulls = 0
        if (
            input_.pull_signal_fired
            and self._consecutive_pulls
            >= cfg.defer_after_consecutive_pulls
        ):
            posture = OverlayPosture.DEFER
            trigger = TriggerSource.PULL_SIGNAL
            rationale = (
                f"consecutive_pulls={self._consecutive_pulls} >= "
                f"defer_after_consecutive_pulls="
                f"{cfg.defer_after_consecutive_pulls}; defer"
            )
        elif input_.pull_signal_fired:
            posture = OverlayPosture.PAUSE_AND_REASON
            trigger = TriggerSource.PULL_SIGNAL
            rationale = (
                "pull_signal_fired; pause for substrate-mode reasoning"
            )
        elif (
            input_.decisions_since_last_check
            >= cfg.periodic_check_interval
        ):
            posture = OverlayPosture.PAUSE_AND_REASON
            trigger = TriggerSource.PERIODIC
            rationale = (
                f"decisions_since_last_check="
                f"{input_.decisions_since_last_check} >= "
                f"periodic_check_interval={cfg.periodic_check_interval}"
            )
        else:
            posture = OverlayPosture.PROCEED
            trigger = TriggerSource.NEITHER
            rationale = (
                "no pull-signal fired and below periodic interval"
            )
        return ConsciousCheckOutput(
            entity_id=self._entity_id,
            decision_id=input_.decision_id,
            posture=posture,
            trigger_source=trigger,
            check_questions=cfg.check_questions,
            consecutive_pulls=self._consecutive_pulls,
            decisions_since_last_check=(
                input_.decisions_since_last_check
            ),
            rationale=rationale,
        )

__all__ = [
    "ConsciousCheckConfig",
    "ConsciousCheckInput",
    "ConsciousCheckOutput",
    "ConsciousCheckOverlay",
    "DEFAULT_CONSCIOUS_CHECK_CONFIG",
    "OverlayPosture",
    "TriggerSource",
]
