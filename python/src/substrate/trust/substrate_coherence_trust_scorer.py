"""Substrate-coherence trust scorer

Pure-logic primitive that scores an entity's substrate-mode-coherence
over a rolling window of its Phase 16 :class:`SubstrateTraceRecord`
history. The library's reading:

    Substrate-coherent identity = an entity whose iteration sustains
    modeling mode operation rather than collapsing to reactive mode
    default. An entity's trustworthiness is the degree to which it
    sustains substrate-aligned operation across decisions.
sustained long-cycle operation is the operational achievement that
must be cultivated through iteration. This scorer measures how
reliably an entity holds that operation by examining its substrate
trace history across five components:

1. **NPG-positive rate** — fraction of decisions verified net-
   positive by the Phase 1 :class:`NetPotentialGainGate` (higher is
   better).
2. **Productive-band rate** — fraction classified PRODUCTIVE by the
   Phase 5 :class:`ResistanceBand` (higher is better).
3. **Intercept inverse** — fraction of decisions that did NOT
   trigger a Phase 8 harness intercept (higher is better; inverse of
   intercept rate).
4. **DriftPattern inverse** — fraction of decisions on which the Phase 15
   :class:`DriftPatternMatcher` detected NO pattern pattern (higher is
   better).
5. **Inversion inverse** — fraction of decisions on which the Phase
   8 harness did NOT fire an :attr:`InterceptKind.INVERSION_DETECTED`
   intercept (higher is better).

Pure logic
==========

* No DAO, no LLM, no network. Composes Phase 22's
  :class:`SubstrateMetricsAggregator` to read all rate components.
* Honest uncertainty. With fewer than ``min_records`` history, the
  verdict is :attr:`TrustVerdict.INSUFFICIENT_DATA` and components +
  composite are :class:`None` — the scorer does not fabricate trust.
* Operator-overridable weights and thresholds.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Optional, Sequence

from substrate.audit.substrate_trace import (
    SubstrateTraceLedger,
    SubstrateTraceRecord,
)
from substrate.harness import InterceptKind
from substrate.metrics.substrate_metrics import (
    SubstrateMetrics,
    SubstrateMetricsAggregator,
)

class TrustVerdict(str, Enum):
    """Four-valued verdict from the substrate-coherence trust scorer."""

    TRUSTED = "trusted"
    MIXED = "mixed"
    DRIFTING = "drifting"
    INSUFFICIENT_DATA = "insufficient_data"

@dataclass(frozen=True, slots=True)
class TrustScoreComponents:
    """Per-component normalized scores (each in [0, 1])."""

    npg_positive_rate: float
    productive_rate: float
    intercept_inverse: float
    sin_inverse: float
    inversion_inverse: float

@dataclass(frozen=True, slots=True)
class TrustScore:
    """Aggregate trust evaluation for one entity."""

    entity_id: str
    record_count: int
    components: Optional[TrustScoreComponents]
    composite_score: Optional[float]
    verdict: TrustVerdict
    rationale: str

    @property
    def is_trusted(self) -> bool:
        """True iff verdict is TRUSTED."""
        return self.verdict is TrustVerdict.TRUSTED

    @property
    def is_drifting(self) -> bool:
        """True iff verdict is DRIFTING."""
        return self.verdict is TrustVerdict.DRIFTING

    @property
    def is_insufficient(self) -> bool:
        """True iff verdict is INSUFFICIENT_DATA."""
        return self.verdict is TrustVerdict.INSUFFICIENT_DATA

@dataclass(frozen=True, slots=True)
class TrustScorerConfig:  # pylint: disable=too-many-instance-attributes
    """Weights + thresholds for trust-score computation."""

    npg_weight: float = 1.0
    productive_weight: float = 1.0
    intercept_inverse_weight: float = 1.0
    sin_inverse_weight: float = 1.0
    inversion_inverse_weight: float = 1.0
    min_records: int = 5
    trusted_threshold: float = 0.75
    drifting_threshold: float = 0.4

    def __post_init__(self) -> None:
        if self.min_records < 1:
            raise ValueError("min_records must be >= 1")
        for name in (
            "npg_weight",
            "productive_weight",
            "intercept_inverse_weight",
            "sin_inverse_weight",
            "inversion_inverse_weight",
        ):
            if getattr(self, name) <= 0.0:
                raise ValueError(f"{name} must be > 0")
        if not 0.0 < self.trusted_threshold <= 1.0:
            raise ValueError("trusted_threshold must be in (0, 1]")
        if not 0.0 <= self.drifting_threshold < 1.0:
            raise ValueError("drifting_threshold must be in [0, 1)")
        if self.trusted_threshold <= self.drifting_threshold:
            raise ValueError(
                "trusted_threshold must be > drifting_threshold"
            )

DEFAULT_TRUST_SCORER_CONFIG: Final[TrustScorerConfig] = TrustScorerConfig()

class SubstrateCoherenceTrustScorer:  # pylint: disable=too-few-public-methods
    """Pure-logic substrate-coherence trust scorer."""

    def __init__(
        self,
        *,
        config: TrustScorerConfig = DEFAULT_TRUST_SCORER_CONFIG,
        aggregator: Optional[SubstrateMetricsAggregator] = None,
    ) -> None:
        self._config = config
        self._aggregator = aggregator or SubstrateMetricsAggregator()

    def score(
        self,
        *,
        entity_id: str,
        records: Sequence[SubstrateTraceRecord],
    ) -> TrustScore:
        """Score an entity over an explicit sequence of trace records."""
        if not entity_id:
            raise ValueError("entity_id must be non-empty")
        record_count = len(records)
        if record_count < self._config.min_records:
            return _insufficient(
                entity_id=entity_id,
                record_count=record_count,
                min_records=self._config.min_records,
            )
        metrics = self._aggregator.aggregate(records)
        components = self._components_from_metrics(metrics)
        composite = self._compose(components)
        verdict, rationale = self._verdict_for(composite, components)
        return TrustScore(
            entity_id=entity_id,
            record_count=record_count,
            components=components,
            composite_score=composite,
            verdict=verdict,
            rationale=rationale,
        )

    def score_from_ledger(
        self,
        *,
        entity_id: str,
        ledger: SubstrateTraceLedger,
    ) -> TrustScore:
        """Convenience: ``score(entity_id=..., records=ledger.records())``."""
        return self.score(entity_id=entity_id, records=ledger.records())

    # ---- helpers ----------------------------------------------------

    def _components_from_metrics(
        self, metrics: SubstrateMetrics,
    ) -> TrustScoreComponents:
        npg_pos = metrics.npg_positive_rate or 0.0
        productive = metrics.productive_rate or 0.0
        intercept = metrics.intercept_rate or 0.0
        pattern = metrics.sin_detection_rate or 0.0
        inversion = self._inversion_rate(metrics)
        return TrustScoreComponents(
            npg_positive_rate=npg_pos,
            productive_rate=productive,
            intercept_inverse=1.0 - intercept,
            sin_inverse=1.0 - pattern,
            inversion_inverse=1.0 - inversion,
        )

    @staticmethod
    def _inversion_rate(metrics: SubstrateMetrics) -> float:
        if metrics.record_count <= 0:
            return 0.0
        for kind, count in metrics.intercept_count_by_kind:
            if kind is InterceptKind.INVERSION_DETECTED:
                return count / metrics.record_count
        return 0.0

    def _compose(self, components: TrustScoreComponents) -> float:
        cfg = self._config
        weights = (
            cfg.npg_weight,
            cfg.productive_weight,
            cfg.intercept_inverse_weight,
            cfg.sin_inverse_weight,
            cfg.inversion_inverse_weight,
        )
        values = (
            components.npg_positive_rate,
            components.productive_rate,
            components.intercept_inverse,
            components.sin_inverse,
            components.inversion_inverse,
        )
        total_weight = sum(weights)
        weighted_sum = sum(w * v for w, v in zip(weights, values))
        return weighted_sum / total_weight

    def _verdict_for(
        self,
        composite: float,
        components: TrustScoreComponents,
    ) -> tuple[TrustVerdict, str]:
        cfg = self._config
        if composite >= cfg.trusted_threshold:
            verdict = TrustVerdict.TRUSTED
        elif composite >= cfg.drifting_threshold:
            verdict = TrustVerdict.MIXED
        else:
            verdict = TrustVerdict.DRIFTING
        rationale = (
            f"composite={composite:.3f} "
            f"(npg+={components.npg_positive_rate:.2f}, "
            f"prod={components.productive_rate:.2f}, "
            f"intercept_inv={components.intercept_inverse:.2f}, "
            f"sin_inv={components.sin_inverse:.2f}, "
            f"inversion_inv={components.inversion_inverse:.2f}); "
            f"verdict={verdict.value}"
        )
        return verdict, rationale

def _insufficient(
    *, entity_id: str, record_count: int, min_records: int,
) -> TrustScore:
    return TrustScore(
        entity_id=entity_id,
        record_count=record_count,
        components=None,
        composite_score=None,
        verdict=TrustVerdict.INSUFFICIENT_DATA,
        rationale=(
            f"insufficient history: {record_count} records < "
            f"min_records={min_records}"
        ),
    )

__all__ = [
    "DEFAULT_TRUST_SCORER_CONFIG",
    "SubstrateCoherenceTrustScorer",
    "TrustScore",
    "TrustScoreComponents",
    "TrustScorerConfig",
    "TrustVerdict",
]
