"""Encapsulating-context state tracker (Companion #2)

Pure-logic tracker that maintains a rolling window of the
encapsulating context's substrate-state, drift rate, and audit-failure
rate. Child entities consult this tracker to inform their pull-signal
detector and conscious-check overlay.

The tracker is the *source-of-recent-state* for encapsulating-context
substrate-aligned reasoning. Without it, each child entity would have
to maintain its own view; the centralized tracker enforces consistent
observations.

Pure logic
==========

* No DAO, no LLM, no network. Caller pushes
  ``ContextObservation`` entries; the tracker returns aggregated
  state.
* Honest uncertainty: below ``min_observations`` returns
  ``InsufficientContextDataError``.
* Scale-aware via :class:`ContextScale`.
* Stateful only in the bounded-ring sense.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Final

from substrate.encapsulating_context.pull_signal import (
    ContextScale,
)

class InsufficientContextDataError(RuntimeError):
    """Raised when ``aggregate()`` is called with too few observations."""

@dataclass(frozen=True, slots=True)
class ContextObservation:
    """One observation of the encapsulating context."""

    context_id: str
    scale: ContextScale
    substrate_state: float
    drift_rate: float
    audit_failure_rate: float
    cycle_index: int

    def __post_init__(self) -> None:
        if not self.context_id:
            raise ValueError("context_id must be non-empty")
        if not 0.0 <= self.substrate_state <= 1.0:
            raise ValueError("substrate_state must be in [0, 1]")
        if not -1.0 <= self.drift_rate <= 1.0:
            raise ValueError("drift_rate must be in [-1, 1]")
        if not 0.0 <= self.audit_failure_rate <= 1.0:
            raise ValueError("audit_failure_rate must be in [0, 1]")
        if self.cycle_index < 0:
            raise ValueError("cycle_index must be >= 0")

@dataclass(frozen=True, slots=True)
class ContextStateAggregate:
    """Aggregated encapsulating-context state over the window."""

    context_id: str
    scale: ContextScale
    observation_count: int
    mean_substrate_state: float
    mean_drift_rate: float
    mean_audit_failure_rate: float
    latest_substrate_state: float
    latest_drift_rate: float
    latest_audit_failure_rate: float

@dataclass(frozen=True, slots=True)
class ContextStateTrackerConfig:
    """Operator-tunable tracker settings."""

    window_size: int = 50
    min_observations: int = 3

    def __post_init__(self) -> None:
        if self.window_size < 2:
            raise ValueError("window_size must be >= 2")
        if self.min_observations < 1:
            raise ValueError("min_observations must be >= 1")
        if self.min_observations > self.window_size:
            raise ValueError(
                "min_observations cannot exceed window_size"
            )

DEFAULT_CONTEXT_STATE_TRACKER_CONFIG: Final[
    ContextStateTrackerConfig
] = ContextStateTrackerConfig()

class EncapsulatingContextStateTracker:
    """Pure-logic encapsulating-context state tracker (Companion #2)."""

    def __init__(
        self,
        *,
        context_id: str,
        scale: ContextScale,
        config: ContextStateTrackerConfig = (
            DEFAULT_CONTEXT_STATE_TRACKER_CONFIG
        ),
    ) -> None:
        if not context_id:
            raise ValueError("context_id must be non-empty")
        self._context_id = context_id
        self._scale = scale
        self._config = config
        self._window: Deque[ContextObservation] = deque(
            maxlen=config.window_size,
        )

    def observe(self, observation: ContextObservation) -> None:
        """Record an observation."""
        if observation.context_id != self._context_id:
            raise ValueError(
                f"observation.context_id={observation.context_id} "
                f"does not match tracker context_id={self._context_id}"
            )
        if observation.scale is not self._scale:
            raise ValueError(
                f"observation.scale={observation.scale.value} does not "
                f"match tracker scale={self._scale.value}"
            )
        self._window.append(observation)

    def aggregate(self) -> ContextStateAggregate:
        """Return the current aggregate."""
        n = len(self._window)
        if n < self._config.min_observations:
            raise InsufficientContextDataError(
                f"observations={n} below min "
                f"{self._config.min_observations}"
            )
        substrate_states = [o.substrate_state for o in self._window]
        drifts = [o.drift_rate for o in self._window]
        audits = [o.audit_failure_rate for o in self._window]
        latest = self._window[-1]
        return ContextStateAggregate(
            context_id=self._context_id,
            scale=self._scale,
            observation_count=n,
            mean_substrate_state=sum(substrate_states) / n,
            mean_drift_rate=sum(drifts) / n,
            mean_audit_failure_rate=sum(audits) / n,
            latest_substrate_state=latest.substrate_state,
            latest_drift_rate=latest.drift_rate,
            latest_audit_failure_rate=latest.audit_failure_rate,
        )

    @property
    def observation_count(self) -> int:
        """Number of observations currently in the window."""
        return len(self._window)

__all__ = [
    "ContextObservation",
    "ContextScale",
    "ContextStateAggregate",
    "ContextStateTrackerConfig",
    "DEFAULT_CONTEXT_STATE_TRACKER_CONFIG",
    "EncapsulatingContextStateTracker",
    "InsufficientContextDataError",
]
