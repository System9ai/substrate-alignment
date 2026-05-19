"""Cross-pattern drift signal aggregator

Pure-logic primitive aggregating drift signals across the substrate
spine's drift-detection primitives:

* Phase 15 — :class:`DriftPatternMatcher` (seven pattern categories)
* Phase 19 — :class:`HeuristicInversionDetector` (180° inversion)
* Phase 42 — :class:`DefensiveModulationEngine` (eight attack
  patterns)
* Phase 55 — :class:`GoldenRuleProbe` (cross-tradition reciprocity)
* Phase 1 — :class:`NetPotentialGainGate` (NET_NEGATIVE rate)

The aggregator answers: *across all drift-detection signals, what is
the cumulative drift posture of this entity?* Per the library's
drift-vocabulary discipline, multiple weak signals across different
detector kinds compose into a stronger overall drift verdict than any
one detector alone.

Scale awareness
===============

Drift aggregation operates at both cell scale (per-physical-instance)
and node scale (per-logical-aggregate). Callers supply the
:class:`DriftScale` so the report carries the scope explicitly.

Pure logic
==========

* No DAO, no LLM, no network. Inputs supplied by caller.
* Honest uncertainty: empty input → ``NONE`` severity with explicit
  rationale.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Mapping, Tuple

class DriftScale(str, Enum):
    """the host application entity hierarchy scale for aggregation."""

    CELL = "cell"
    NODE = "node"

class DriftCategory(str, Enum):
    """The five drift-signal categories."""

    PATTERN = "pattern"
    INVERSION = "inversion"
    ATTACK = "attack"
    GOLDEN_RULE_VIOLATION = "golden_rule_violation"
    NPG_NEGATIVE = "npg_negative"

class DriftSeverity(str, Enum):
    """Aggregate severity classification."""

    NONE = "none"
    EMERGING = "emerging"
    SUSTAINED = "sustained"
    CRITICAL = "critical"

@dataclass(frozen=True, slots=True)
class DriftCategoryInput:
    """One category's drift counts + cumulative severity."""

    category: DriftCategory
    event_count: int
    severity_total: float
    description: str = ""

    def __post_init__(self) -> None:
        if self.event_count < 0:
            raise ValueError("event_count must be >= 0")
        if self.severity_total < 0:
            raise ValueError("severity_total must be >= 0")

@dataclass(frozen=True, slots=True)
class DriftAggregateReport:  # pylint: disable=too-many-instance-attributes
    """Aggregate cross-category drift posture."""

    entity_id: str
    scale: DriftScale
    overall_severity: DriftSeverity
    category_counts: Mapping[DriftCategory, int]
    composite_severity_score: float
    total_event_count: int
    high_severity_categories: Tuple[DriftCategory, ...]
    rationale: str

    @property
    def has_critical_drift(self) -> bool:
        """True iff overall_severity is CRITICAL."""
        return self.overall_severity is DriftSeverity.CRITICAL

@dataclass(frozen=True, slots=True)
class DriftAggregatorConfig:
    """Tunable thresholds for severity classification."""

    emerging_score_min: float = 0.2
    sustained_score_min: float = 0.5
    critical_score_min: float = 0.8
    high_category_score_min: float = 0.4

    def __post_init__(self) -> None:
        if not 0.0 < self.emerging_score_min < self.sustained_score_min:
            raise ValueError(
                "emerging_score_min must be in (0, sustained_score_min)"
            )
        if not self.sustained_score_min < self.critical_score_min <= 1.0:
            raise ValueError(
                "sustained_score_min < critical_score_min <= 1.0 required"
            )
        if not 0.0 < self.high_category_score_min <= 1.0:
            raise ValueError(
                "high_category_score_min must be in (0, 1]"
            )

DEFAULT_DRIFT_AGGREGATOR_CONFIG: Final[DriftAggregatorConfig] = (
    DriftAggregatorConfig()
)

# Per-category weights for composite score. Defaults reflect the
# library's weighting: inversions + attacks are higher-impact than
# isolated pattern patterns.
_CATEGORY_WEIGHTS: Final[Mapping[DriftCategory, float]] = {
    DriftCategory.PATTERN: 0.15,
    DriftCategory.INVERSION: 0.30,
    DriftCategory.ATTACK: 0.25,
    DriftCategory.GOLDEN_RULE_VIOLATION: 0.20,
    DriftCategory.NPG_NEGATIVE: 0.10,
}

class DriftSignalAggregator:  # pylint: disable=too-few-public-methods
    """Pure-logic cross-pattern drift aggregator."""

    def __init__(
        self,
        *,
        config: DriftAggregatorConfig = DEFAULT_DRIFT_AGGREGATOR_CONFIG,
    ) -> None:
        self._config = config

    def aggregate(
        self,
        entity_id: str,
        scale: DriftScale,
        inputs: Tuple[DriftCategoryInput, ...],
    ) -> DriftAggregateReport:
        """Aggregate drift inputs into a single posture report."""
        if not entity_id:
            raise ValueError("entity_id must be non-empty")
        if not inputs:
            return DriftAggregateReport(
                entity_id=entity_id,
                scale=scale,
                overall_severity=DriftSeverity.NONE,
                category_counts={c: 0 for c in DriftCategory},
                composite_severity_score=0.0,
                total_event_count=0,
                high_severity_categories=(),
                rationale="no drift inputs supplied",
            )
        self._validate_unique_categories(inputs)
        category_counts = {c: 0 for c in DriftCategory}
        category_severity = {c: 0.0 for c in DriftCategory}
        for inp in inputs:
            category_counts[inp.category] = inp.event_count
            category_severity[inp.category] = inp.severity_total
        total_events = sum(category_counts.values())
        composite = self._composite_score(category_severity)
        high_severity = tuple(
            sorted(
                (
                    c
                    for c, sev in category_severity.items()
                    if sev >= self._config.high_category_score_min
                ),
                key=lambda c: c.value,
            )
        )
        severity = self._severity(composite)
        rationale = (
            f"entity={entity_id} scale={scale.value} events={total_events} "
            f"composite={composite:.3f} severity={severity.value} "
            f"high=[{','.join(c.value for c in high_severity)}]"
        )
        return DriftAggregateReport(
            entity_id=entity_id,
            scale=scale,
            overall_severity=severity,
            category_counts=category_counts,
            composite_severity_score=composite,
            total_event_count=total_events,
            high_severity_categories=high_severity,
            rationale=rationale,
        )

    @staticmethod
    def _validate_unique_categories(
        inputs: Tuple[DriftCategoryInput, ...],
    ) -> None:
        seen: set[DriftCategory] = set()
        for inp in inputs:
            if inp.category in seen:
                raise ValueError(
                    f"duplicate category {inp.category.value!r}"
                )
            seen.add(inp.category)

    @staticmethod
    def _composite_score(
        severities: Mapping[DriftCategory, float],
    ) -> float:
        # Weighted sum, clamped to [0, 1].
        score = sum(
            severities[c] * _CATEGORY_WEIGHTS[c]
            for c in DriftCategory
        )
        return max(0.0, min(1.0, score))

    def _severity(self, composite: float) -> DriftSeverity:
        cfg = self._config
        if composite >= cfg.critical_score_min:
            return DriftSeverity.CRITICAL
        if composite >= cfg.sustained_score_min:
            return DriftSeverity.SUSTAINED
        if composite >= cfg.emerging_score_min:
            return DriftSeverity.EMERGING
        return DriftSeverity.NONE

__all__ = [
    "DEFAULT_DRIFT_AGGREGATOR_CONFIG",
    "DriftAggregateReport",
    "DriftAggregatorConfig",
    "DriftCategory",
    "DriftCategoryInput",
    "DriftScale",
    "DriftSeverity",
    "DriftSignalAggregator",
]
