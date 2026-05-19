"""Encapsulating-context pull-signal detector — Companion #2

Pure-logic detector that produces a *pull signal* drawing an entity to
shift from reactive-mode reasoning to substrate-mode reasoning when
the encapsulating context (parent node, org, cluster) shows
sufficient state-pressure. The substrate-aligned reading: an entity
inside a stressed encapsulating context must reason at substrate-mode
level even on routine decisions, because the encapsulating context's
stress shifts the cost-benefit of cheap reactive heuristics.

The detector returns:

* ``PULL_FIRED`` — pull signal warrants substrate-mode reasoning.
* ``NO_PULL`` — encapsulating context is stable.
* ``INSUFFICIENT_DATA`` — too few signals to reach a verdict.

Pure logic
==========

* No DAO, no LLM, no network. Caller supplies the input vector.
* Honest uncertainty: insufficient signal_count returns
  ``INSUFFICIENT_DATA``.
* Scale-aware via :class:`ContextScale` so call sites can disambiguate
  node-level vs. org-level pulls.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final

class ContextScale(str, Enum):
    """Encapsulating-context scale."""

    NODE = "node"
    ORG = "org"
    CLUSTER = "cluster"

class PullVerdict(str, Enum):
    """Pull-signal verdict."""

    PULL_FIRED = "pull_fired"
    NO_PULL = "no_pull"
    INSUFFICIENT_DATA = "insufficient_data"

@dataclass(frozen=True, slots=True)
class PullSignalInput:  # pylint: disable=too-many-instance-attributes
    """Caller-supplied pull-signal inputs."""

    entity_id: str
    context_id: str
    context_scale: ContextScale
    context_substrate_state: float
    """Encapsulating context's substrate-state estimate in [0, 1]."""

    context_drift_rate: float
    """Encapsulating context's per-cycle drift rate in [-1, 1]."""

    recent_audit_failure_rate: float
    """Encapsulating context's recent substrate-coherence audit failure
    rate in [0, 1]."""

    signal_count: int
    """Number of distinct encapsulating-context observations contributing
    to this input."""

    def __post_init__(self) -> None:
        if not self.entity_id:
            raise ValueError("entity_id must be non-empty")
        if not self.context_id:
            raise ValueError("context_id must be non-empty")
        if not 0.0 <= self.context_substrate_state <= 1.0:
            raise ValueError(
                "context_substrate_state must be in [0, 1]"
            )
        if not -1.0 <= self.context_drift_rate <= 1.0:
            raise ValueError(
                "context_drift_rate must be in [-1, 1]"
            )
        if not 0.0 <= self.recent_audit_failure_rate <= 1.0:
            raise ValueError(
                "recent_audit_failure_rate must be in [0, 1]"
            )
        if self.signal_count < 0:
            raise ValueError("signal_count must be >= 0")

@dataclass(frozen=True, slots=True)
class PullSignalConfig:
    """Operator-tunable detector thresholds."""

    min_signal_count: int = 3
    state_pressure_threshold: float = 0.5
    """Context substrate-state below this contributes pull pressure."""

    drift_pressure_threshold: float = 0.05
    """Per-cycle drift above this contributes pull pressure."""

    audit_failure_pressure_threshold: float = 0.2
    """Audit failure rate above this contributes pull pressure."""

    fire_threshold: float = 0.4
    """Composite pressure above this fires PULL_FIRED."""

    def __post_init__(self) -> None:
        if self.min_signal_count < 1:
            raise ValueError("min_signal_count must be >= 1")
        if not 0.0 < self.state_pressure_threshold <= 1.0:
            raise ValueError(
                "state_pressure_threshold must be in (0, 1]"
            )
        if not 0.0 < self.drift_pressure_threshold <= 1.0:
            raise ValueError(
                "drift_pressure_threshold must be in (0, 1]"
            )
        if not 0.0 < self.audit_failure_pressure_threshold <= 1.0:
            raise ValueError(
                "audit_failure_pressure_threshold must be in (0, 1]"
            )
        if not 0.0 < self.fire_threshold <= 1.0:
            raise ValueError(
                "fire_threshold must be in (0, 1]"
            )

DEFAULT_PULL_SIGNAL_CONFIG: Final[PullSignalConfig] = PullSignalConfig()

@dataclass(frozen=True, slots=True)
class PullSignalOutput:  # pylint: disable=too-many-instance-attributes
    """Pull-signal detector output."""

    entity_id: str
    context_id: str
    context_scale: ContextScale
    verdict: PullVerdict
    composite_pressure: float
    state_component: float
    drift_component: float
    audit_component: float
    rationale: str

    @property
    def pull_fired(self) -> bool:
        """True iff pull signal fired."""
        return self.verdict is PullVerdict.PULL_FIRED

class EncapsulatingContextPullSignal:  # pylint: disable=too-few-public-methods
    """Pure-logic encapsulating-context pull-signal detector (Companion #2)."""

    def __init__(
        self,
        *,
        config: PullSignalConfig = DEFAULT_PULL_SIGNAL_CONFIG,
    ) -> None:
        self._config = config

    def evaluate(
        self, input_: PullSignalInput,
    ) -> PullSignalOutput:
        """Evaluate whether the encapsulating context is pulling."""
        cfg = self._config
        if input_.signal_count < cfg.min_signal_count:
            return PullSignalOutput(
                entity_id=input_.entity_id,
                context_id=input_.context_id,
                context_scale=input_.context_scale,
                verdict=PullVerdict.INSUFFICIENT_DATA,
                composite_pressure=0.0,
                state_component=0.0,
                drift_component=0.0,
                audit_component=0.0,
                rationale=(
                    f"signal_count={input_.signal_count} below "
                    f"min {cfg.min_signal_count}"
                ),
            )
        state_component = max(
            0.0,
            (cfg.state_pressure_threshold - input_.context_substrate_state)
            / cfg.state_pressure_threshold,
        )
        drift_component = max(
            0.0,
            (input_.context_drift_rate - cfg.drift_pressure_threshold)
            / max(1.0 - cfg.drift_pressure_threshold, 1e-9),
        )
        audit_component = max(
            0.0,
            (
                input_.recent_audit_failure_rate
                - cfg.audit_failure_pressure_threshold
            )
            / max(
                1.0 - cfg.audit_failure_pressure_threshold, 1e-9,
            ),
        )
        composite = (
            state_component + drift_component + audit_component
        ) / 3.0
        if composite >= cfg.fire_threshold:
            verdict = PullVerdict.PULL_FIRED
            rationale = (
                f"composite={composite:.3f} >= "
                f"fire_threshold={cfg.fire_threshold:.3f}"
            )
        else:
            verdict = PullVerdict.NO_PULL
            rationale = (
                f"composite={composite:.3f} < "
                f"fire_threshold={cfg.fire_threshold:.3f}"
            )
        return PullSignalOutput(
            entity_id=input_.entity_id,
            context_id=input_.context_id,
            context_scale=input_.context_scale,
            verdict=verdict,
            composite_pressure=composite,
            state_component=state_component,
            drift_component=drift_component,
            audit_component=audit_component,
            rationale=rationale,
        )

__all__ = [
    "ContextScale",
    "DEFAULT_PULL_SIGNAL_CONFIG",
    "EncapsulatingContextPullSignal",
    "PullSignalConfig",
    "PullSignalInput",
    "PullSignalOutput",
    "PullVerdict",
]
