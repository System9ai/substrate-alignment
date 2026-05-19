"""Cross-entity response-cadence tracker.

A pure-logic primitive that scores the coupling between a pair of
entities (agents, services, users) over time.

Behavioural model
=================

- Coupling field strength between an entity pair at time ``t`` is
  ``1.0`` while the most-recent interaction is younger than the pair's
  expected cadence (the mean of their historical inter-event intervals).
- Beyond expected cadence, field strength decays as
  ``(expected / actual)²`` — the inverse-square form chosen so that
  doubling the wait halves field strength by a factor of four.
- Sustained skip past
  :attr:`CadenceConfig.ghosting_skip_multiples` cadence-intervals
  without an explicit-close event is classified as **ghosting**.

Host applications choose what to do with the classifications. The
tracker is purely observational: it computes states, it does not act.

Pure logic
==========

- No DAO, no LLM, no network. The caller supplies ``current_time``;
  the tracker has no internal clock.
- Honest about uncertainty: a pair with fewer than
  :attr:`CadenceConfig.min_history_for_pattern` interactions returns
  no :class:`CadencePattern`; downstream queries surface this as
  :attr:`CouplingStatus.INSUFFICIENT_DATA`.
- Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from statistics import mean, pstdev
from typing import Final, Optional, Tuple


class CadenceEventKind(str, Enum):
    """Event kinds that shape cadence history."""

    INTERACTION = "interaction"
    EXPLICIT_CLOSE = "explicit_close"


class CouplingStatus(str, Enum):
    """Coupling state classification at one query time."""

    ACTIVE = "active"
    WEAKENING = "weakening"
    DECOUPLED = "decoupled"
    GHOSTED = "ghosted"
    EXPLICITLY_CLOSED = "explicitly_closed"
    INSUFFICIENT_DATA = "insufficient_data"


@dataclass(frozen=True, slots=True)
class CadenceEvent:
    """One observed coupling event between an entity pair."""

    timestamp: float
    pair_id_a: str
    pair_id_b: str
    kind: CadenceEventKind = CadenceEventKind.INTERACTION

    def __post_init__(self) -> None:
        if self.timestamp < 0:
            raise ValueError("timestamp must be >= 0")
        if not self.pair_id_a:
            raise ValueError("pair_id_a must be non-empty")
        if not self.pair_id_b:
            raise ValueError("pair_id_b must be non-empty")
        if self.pair_id_a == self.pair_id_b:
            raise ValueError("pair_id_a and pair_id_b must differ")

    @property
    def canonical_pair(self) -> Tuple[str, str]:
        """Sorted-pair canonical key for the event."""
        return _canonical_pair(self.pair_id_a, self.pair_id_b)


@dataclass(frozen=True, slots=True)
class CadencePattern:
    """Historical mean + sample-stdev of inter-interaction intervals."""

    mean_interval: float
    stdev_interval: float
    sample_size: int


@dataclass(frozen=True, slots=True)
class FieldStrengthReport:
    """Field-strength + status at one ``(pair, current_time)`` query."""

    pair_id_a: str
    pair_id_b: str
    field_strength: float
    coupling_status: CouplingStatus
    time_since_last_coupling: float
    expected_cadence: Optional[float]
    rationale: str


@dataclass(frozen=True, slots=True)
class GhostingEvent:
    """Detected ghosting between a pair."""

    pair_id_a: str
    pair_id_b: str
    last_event_timestamp: float
    skipped_cadence_multiples: float
    rationale: str


@dataclass(frozen=True, slots=True)
class CouplingAtRisk:
    """One pair an agent participates in that is at decoupling risk."""

    pair_id_a: str
    pair_id_b: str
    field_strength: float
    coupling_status: CouplingStatus
    rationale: str


@dataclass(frozen=True, slots=True)
class CadenceConfig:
    """Tunable thresholds for cadence interpretation."""

    weakening_threshold: float = 0.5
    decoupling_threshold: float = 0.1
    ghosting_skip_multiples: float = 3.0
    min_history_for_pattern: int = 3
    field_strength_clamp: float = 1.0

    def __post_init__(self) -> None:
        if not 0.0 < self.weakening_threshold < 1.0:
            raise ValueError("weakening_threshold must be in (0, 1)")
        if not 0.0 < self.decoupling_threshold < self.weakening_threshold:
            raise ValueError(
                "decoupling_threshold must be in (0, weakening_threshold)"
            )
        if self.ghosting_skip_multiples <= 1.0:
            raise ValueError("ghosting_skip_multiples must be > 1.0")
        if self.min_history_for_pattern < 2:
            raise ValueError("min_history_for_pattern must be >= 2")
        if self.field_strength_clamp <= 0:
            raise ValueError("field_strength_clamp must be > 0")


DEFAULT_CADENCE_CONFIG: Final[CadenceConfig] = CadenceConfig()


def _canonical_pair(a: str, b: str) -> Tuple[str, str]:
    return (a, b) if a <= b else (b, a)


class CadenceTracker:
    """Pure-logic cross-entity cadence tracker."""

    def __init__(
        self, *, config: CadenceConfig = DEFAULT_CADENCE_CONFIG,
    ) -> None:
        self._config = config

    def compute_pattern(
        self, events: Tuple[CadenceEvent, ...],
    ) -> Optional[CadencePattern]:
        """Compute mean + stdev of intervals between INTERACTION events."""
        interactions = sorted(
            (
                e
                for e in events
                if e.kind is CadenceEventKind.INTERACTION
            ),
            key=lambda e: e.timestamp,
        )
        if len(interactions) < self._config.min_history_for_pattern:
            return None
        intervals = [
            interactions[i].timestamp - interactions[i - 1].timestamp
            for i in range(1, len(interactions))
        ]
        if not intervals:
            return None
        return CadencePattern(
            mean_interval=mean(intervals),
            stdev_interval=pstdev(intervals),
            sample_size=len(intervals),
        )

    def compute_field_strength(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        *,
        pair_id_a: str,
        pair_id_b: str,
        current_time: float,
        events: Tuple[CadenceEvent, ...],
    ) -> FieldStrengthReport:
        """Score the current coupling strength between the pair."""
        self._validate_pair(pair_id_a, pair_id_b, current_time)
        pair_events = self._pair_events(pair_id_a, pair_id_b, events)
        if not pair_events:
            return FieldStrengthReport(
                pair_id_a=pair_id_a,
                pair_id_b=pair_id_b,
                field_strength=0.0,
                coupling_status=CouplingStatus.INSUFFICIENT_DATA,
                time_since_last_coupling=math.inf,
                expected_cadence=None,
                rationale="no events for pair",
            )
        last = pair_events[-1]
        time_since_last = current_time - last.timestamp
        if last.kind is CadenceEventKind.EXPLICIT_CLOSE:
            return FieldStrengthReport(
                pair_id_a=pair_id_a,
                pair_id_b=pair_id_b,
                field_strength=0.0,
                coupling_status=CouplingStatus.EXPLICITLY_CLOSED,
                time_since_last_coupling=time_since_last,
                expected_cadence=None,
                rationale="explicit close event observed",
            )
        pattern = self.compute_pattern(pair_events)
        if pattern is None:
            return FieldStrengthReport(
                pair_id_a=pair_id_a,
                pair_id_b=pair_id_b,
                field_strength=0.0,
                coupling_status=CouplingStatus.INSUFFICIENT_DATA,
                time_since_last_coupling=time_since_last,
                expected_cadence=None,
                rationale=(
                    f"history len={len(pair_events)} < "
                    f"{self._config.min_history_for_pattern}"
                ),
            )
        expected = pattern.mean_interval
        if expected <= 0:
            return FieldStrengthReport(
                pair_id_a=pair_id_a,
                pair_id_b=pair_id_b,
                field_strength=0.0,
                coupling_status=CouplingStatus.INSUFFICIENT_DATA,
                time_since_last_coupling=time_since_last,
                expected_cadence=expected,
                rationale="degenerate expected cadence (=0)",
            )
        if time_since_last <= expected:
            field_strength = self._config.field_strength_clamp
        else:
            field_strength = min(
                self._config.field_strength_clamp,
                (expected / time_since_last) ** 2,
            )
        status = self._classify_status(
            field_strength=field_strength,
            time_since_last=time_since_last,
            expected_cadence=expected,
        )
        return FieldStrengthReport(
            pair_id_a=pair_id_a,
            pair_id_b=pair_id_b,
            field_strength=field_strength,
            coupling_status=status,
            time_since_last_coupling=time_since_last,
            expected_cadence=expected,
            rationale=(
                f"field={field_strength:.3f}, expected={expected:.3f}, "
                f"elapsed={time_since_last:.3f}, status={status.value}"
            ),
        )

    def detect_ghosting(
        self,
        *,
        pair_id_a: str,
        pair_id_b: str,
        current_time: float,
        events: Tuple[CadenceEvent, ...],
    ) -> Optional[GhostingEvent]:
        """Return a ghosting event if the pair has skipped past threshold."""
        report = self.compute_field_strength(
            pair_id_a=pair_id_a,
            pair_id_b=pair_id_b,
            current_time=current_time,
            events=events,
        )
        if report.coupling_status is not CouplingStatus.GHOSTED:
            return None
        assert report.expected_cadence is not None
        pair_events = self._pair_events(pair_id_a, pair_id_b, events)
        last = pair_events[-1]
        skipped = report.time_since_last_coupling / report.expected_cadence
        return GhostingEvent(
            pair_id_a=pair_id_a,
            pair_id_b=pair_id_b,
            last_event_timestamp=last.timestamp,
            skipped_cadence_multiples=skipped,
            rationale=(
                f"skipped {skipped:.2f} cadence multiples without "
                "explicit close"
            ),
        )

    def alert_decoupling_risk(
        self,
        *,
        agent_id: str,
        current_time: float,
        events: Tuple[CadenceEvent, ...],
    ) -> Tuple[CouplingAtRisk, ...]:
        """Return all pairs the agent participates in that risk decoupling."""
        if not agent_id:
            raise ValueError("agent_id must be non-empty")
        if current_time < 0:
            raise ValueError("current_time must be >= 0")
        pairs: set[Tuple[str, str]] = set()
        for e in events:
            if agent_id in (e.pair_id_a, e.pair_id_b):
                pairs.add(e.canonical_pair)
        risks: list[CouplingAtRisk] = []
        for pair_a, pair_b in sorted(pairs):
            report = self.compute_field_strength(
                pair_id_a=pair_a,
                pair_id_b=pair_b,
                current_time=current_time,
                events=events,
            )
            if report.coupling_status in (
                CouplingStatus.WEAKENING,
                CouplingStatus.DECOUPLED,
                CouplingStatus.GHOSTED,
            ):
                risks.append(
                    CouplingAtRisk(
                        pair_id_a=pair_a,
                        pair_id_b=pair_b,
                        field_strength=report.field_strength,
                        coupling_status=report.coupling_status,
                        rationale=report.rationale,
                    )
                )
        return tuple(risks)

    def _classify_status(
        self,
        *,
        field_strength: float,
        time_since_last: float,
        expected_cadence: float,
    ) -> CouplingStatus:
        if (
            expected_cadence > 0
            and (time_since_last / expected_cadence)
            >= self._config.ghosting_skip_multiples
        ):
            return CouplingStatus.GHOSTED
        if field_strength >= self._config.weakening_threshold:
            return CouplingStatus.ACTIVE
        if field_strength >= self._config.decoupling_threshold:
            return CouplingStatus.WEAKENING
        return CouplingStatus.DECOUPLED

    @staticmethod
    def _validate_pair(a: str, b: str, current_time: float) -> None:
        if not a or not b:
            raise ValueError("pair ids must be non-empty")
        if a == b:
            raise ValueError("pair_id_a and pair_id_b must differ")
        if current_time < 0:
            raise ValueError("current_time must be >= 0")

    @staticmethod
    def _pair_events(
        a: str, b: str, events: Tuple[CadenceEvent, ...],
    ) -> Tuple[CadenceEvent, ...]:
        target = _canonical_pair(a, b)
        filtered = [e for e in events if e.canonical_pair == target]
        filtered.sort(key=lambda e: e.timestamp)
        return tuple(filtered)


__all__ = [
    "DEFAULT_CADENCE_CONFIG",
    "CadenceConfig",
    "CadenceEvent",
    "CadenceEventKind",
    "CadencePattern",
    "CadenceTracker",
    "CouplingAtRisk",
    "CouplingStatus",
    "FieldStrengthReport",
    "GhostingEvent",
]
