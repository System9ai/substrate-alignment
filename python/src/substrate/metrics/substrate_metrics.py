"""Substrate self-awareness metrics

Pure-logic aggregator over Phase 16
:class:`SubstrateTraceRecord` sequences. Produces a structured
:class:`SubstrateMetrics` snapshot suitable for the Layer-7 self-
awareness infrastructure required by substrate condition #7

    Self-awareness infrastructure (Layer 7 metrics, query APIs,
    drift-detection)

The aggregator answers the platform's introspection questions over
its own substrate decisions:

* NPG verdict distribution (positive / negative / neutral /
  insufficient / absent).
* Resistance-band distribution (under-loaded / productive /
  stressed / absent).
* DriftPattern-pattern detection rate + per-pattern counts.
* Harness-intercept rate + per-intercept-kind counts.
* Permit/deny rate.
* Optional per-time-window rollups.

Pure logic
==========

* No DAO, no LLM, no network. Aggregates whatever sequence of
  records the caller hands it.
* Honest uncertainty. With zero records all rate properties return
  :class:`None` rather than 0.0 — operators see the absence of data
  rather than a fabricated zero.
* Composition only — consumes the typed record produced by Phase 16
  and the enums from Phases 1 / 5 / 8 / 15.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Final, Optional, Sequence, Tuple

from substrate.audit.substrate_trace import (
    SubstrateTraceLedger,
    SubstrateTraceRecord,
)
from substrate.drift.drift_pattern_matcher import DriftPattern
from substrate.harness import InterceptKind
from substrate.net_potential_gain_gate import (
    NetPotentialGainVerdict,
)
from substrate.resistance_band import (
    ResistanceBandClassification,
)

@dataclass(frozen=True, slots=True)
class SubstrateMetrics:  # pylint: disable=too-many-instance-attributes
    """One snapshot of substrate-aware decision metrics."""

    record_count: int
    earliest_epoch_seconds: Optional[int]
    latest_epoch_seconds: Optional[int]
    # NPG verdict distribution (sums to record_count including absent).
    npg_net_positive: int
    npg_net_negative: int
    npg_net_neutral: int
    npg_insufficient_data: int
    npg_absent: int
    # Resistance-band distribution.
    rb_under_loaded: int
    rb_productive: int
    rb_stressed: int
    rb_absent: int
    # DriftPattern-pattern statistics.
    sin_any_detection_count: int
    sin_pride_present_count: int
    sin_count_by_kind: Tuple[Tuple[DriftPattern, int], ...]
    # Harness intercept statistics.
    intercept_any_count: int
    intercept_count_by_kind: Tuple[Tuple[InterceptKind, int], ...]
    # Permit/deny.
    permitted_count: int
    denied_count: int

    # -- rate properties (None when no records) -----------------------

    @property
    def npg_positive_rate(self) -> Optional[float]:
        """Fraction of records whose NPG verdict is NET_POSITIVE."""
        return _rate(self.npg_net_positive, self.record_count)

    @property
    def npg_negative_rate(self) -> Optional[float]:
        """Fraction of records whose NPG verdict is NET_NEGATIVE."""
        return _rate(self.npg_net_negative, self.record_count)

    @property
    def npg_insufficient_rate(self) -> Optional[float]:
        """Fraction of records whose NPG is INSUFFICIENT_DATA."""
        return _rate(self.npg_insufficient_data, self.record_count)

    @property
    def npg_present_rate(self) -> Optional[float]:
        """Fraction of records that consulted the NPG gate."""
        present = self.record_count - self.npg_absent
        return _rate(present, self.record_count)

    @property
    def productive_rate(self) -> Optional[float]:
        """Fraction of records classified PRODUCTIVE."""
        return _rate(self.rb_productive, self.record_count)

    @property
    def stressed_rate(self) -> Optional[float]:
        """Fraction of records classified STRESSED."""
        return _rate(self.rb_stressed, self.record_count)

    @property
    def under_loaded_rate(self) -> Optional[float]:
        """Fraction of records classified UNDER_LOADED."""
        return _rate(self.rb_under_loaded, self.record_count)

    @property
    def sin_detection_rate(self) -> Optional[float]:
        """Fraction of records with any pattern pattern detected."""
        return _rate(self.sin_any_detection_count, self.record_count)

    @property
    def pride_present_rate(self) -> Optional[float]:
        """Fraction of records with the pride master-pattern flag set."""
        return _rate(self.sin_pride_present_count, self.record_count)

    @property
    def intercept_rate(self) -> Optional[float]:
        """Fraction of records where the harness fired one or more intercepts."""
        return _rate(self.intercept_any_count, self.record_count)

    @property
    def permit_rate(self) -> Optional[float]:
        """Fraction of records whose decision was permitted."""
        return _rate(self.permitted_count, self.record_count)

    @property
    def deny_rate(self) -> Optional[float]:
        """Fraction of records whose decision was denied."""
        return _rate(self.denied_count, self.record_count)

@dataclass(frozen=True, slots=True)
class SubstrateMetricsWindow:
    """One time-window rollup."""

    window_start_epoch_seconds: int
    window_end_epoch_seconds_exclusive: int
    metrics: SubstrateMetrics

def _rate(numerator: int, denominator: int) -> Optional[float]:
    """Return numerator/denominator or None when denominator is 0."""
    if denominator <= 0:
        return None
    return numerator / denominator

# Anchoring sentinel for default window aggregation.
_DEFAULT_ANCHOR: Final[Optional[int]] = None

class SubstrateMetricsAggregator:
    """Pure-logic aggregator producing :class:`SubstrateMetrics` snapshots."""

    def aggregate(
        self,
        records: Sequence[SubstrateTraceRecord],
    ) -> SubstrateMetrics:
        """Aggregate a flat sequence of trace records."""
        return _aggregate(records)

    def aggregate_from_ledger(
        self,
        ledger: SubstrateTraceLedger,
    ) -> SubstrateMetrics:
        """Aggregate all records held by a substrate trace ledger."""
        return self.aggregate(ledger.records())

    def aggregate_windows(
        self,
        records: Sequence[SubstrateTraceRecord],
        *,
        window_size_seconds: int,
        window_anchor_epoch_seconds: Optional[int] = _DEFAULT_ANCHOR,
    ) -> Tuple[SubstrateMetricsWindow, ...]:
        """Bucket records into fixed time windows and aggregate each bucket."""
        if window_size_seconds <= 0:
            raise ValueError("window_size_seconds must be > 0")
        if not records:
            return ()
        anchor = (
            window_anchor_epoch_seconds
            if window_anchor_epoch_seconds is not None
            else min(r.epoch_seconds for r in records)
        )
        buckets: dict[int, list[SubstrateTraceRecord]] = {}
        for rec in records:
            offset = (rec.epoch_seconds - anchor) // window_size_seconds
            window_start = anchor + offset * window_size_seconds
            buckets.setdefault(window_start, []).append(rec)
        windows: list[SubstrateMetricsWindow] = []
        for window_start in sorted(buckets):
            window_records = buckets[window_start]
            windows.append(
                SubstrateMetricsWindow(
                    window_start_epoch_seconds=window_start,
                    window_end_epoch_seconds_exclusive=(
                        window_start + window_size_seconds
                    ),
                    metrics=_aggregate(window_records),
                )
            )
        return tuple(windows)

    def aggregate_windows_from_ledger(
        self,
        ledger: SubstrateTraceLedger,
        *,
        window_size_seconds: int,
        window_anchor_epoch_seconds: Optional[int] = _DEFAULT_ANCHOR,
    ) -> Tuple[SubstrateMetricsWindow, ...]:
        """Convenience: ``aggregate_windows(ledger.records(), ...)``."""
        return self.aggregate_windows(
            ledger.records(),
            window_size_seconds=window_size_seconds,
            window_anchor_epoch_seconds=window_anchor_epoch_seconds,
        )

def _aggregate(  # pylint: disable=too-many-locals,too-many-branches
    records: Sequence[SubstrateTraceRecord],
) -> SubstrateMetrics:
    if not records:
        return _empty_metrics()
    npg_pos = npg_neg = npg_neu = npg_ins = npg_abs = 0
    rb_under = rb_prod = rb_stress = rb_abs = 0
    sin_any = sin_pride = 0
    intercept_any = 0
    permitted = denied = 0
    sin_kind_counts: Counter[DriftPattern] = Counter()
    intercept_kind_counts: Counter[InterceptKind] = Counter()
    earliest = records[0].epoch_seconds
    latest = records[0].epoch_seconds
    for rec in records:
        earliest = min(earliest, rec.epoch_seconds)
        latest = max(latest, rec.epoch_seconds)
        # NPG verdict
        if rec.npg_verdict is None:
            npg_abs += 1
        elif rec.npg_verdict is NetPotentialGainVerdict.NET_POSITIVE:
            npg_pos += 1
        elif rec.npg_verdict is NetPotentialGainVerdict.NET_NEGATIVE:
            npg_neg += 1
        elif rec.npg_verdict is NetPotentialGainVerdict.NET_NEUTRAL:
            npg_neu += 1
        elif rec.npg_verdict is NetPotentialGainVerdict.INSUFFICIENT_DATA:
            npg_ins += 1
        # Resistance band
        if rec.resistance_band is None:
            rb_abs += 1
        elif rec.resistance_band is ResistanceBandClassification.UNDER_LOADED:
            rb_under += 1
        elif rec.resistance_band is ResistanceBandClassification.PRODUCTIVE:
            rb_prod += 1
        elif rec.resistance_band is ResistanceBandClassification.STRESSED:
            rb_stress += 1
        # DriftPattern
        if rec.sin_dominant is not None or rec.sin_kinds_detected:
            sin_any += 1
        if rec.sin_pride_present:
            sin_pride += 1
        for sin_kind in rec.sin_kinds_detected:
            sin_kind_counts[sin_kind] += 1
        # Intercepts
        if rec.harness_intercept_kinds:
            intercept_any += 1
        for ik in rec.harness_intercept_kinds:
            intercept_kind_counts[ik] += 1
        # Permit/deny
        if rec.permitted:
            permitted += 1
        else:
            denied += 1
    return SubstrateMetrics(
        record_count=len(records),
        earliest_epoch_seconds=earliest,
        latest_epoch_seconds=latest,
        npg_net_positive=npg_pos,
        npg_net_negative=npg_neg,
        npg_net_neutral=npg_neu,
        npg_insufficient_data=npg_ins,
        npg_absent=npg_abs,
        rb_under_loaded=rb_under,
        rb_productive=rb_prod,
        rb_stressed=rb_stress,
        rb_absent=rb_abs,
        sin_any_detection_count=sin_any,
        sin_pride_present_count=sin_pride,
        sin_count_by_kind=tuple(
            sorted(sin_kind_counts.items(), key=lambda kv: kv[0].value)
        ),
        intercept_any_count=intercept_any,
        intercept_count_by_kind=tuple(
            sorted(intercept_kind_counts.items(), key=lambda kv: kv[0].value)
        ),
        permitted_count=permitted,
        denied_count=denied,
    )

def _empty_metrics() -> SubstrateMetrics:
    return SubstrateMetrics(
        record_count=0,
        earliest_epoch_seconds=None,
        latest_epoch_seconds=None,
        npg_net_positive=0,
        npg_net_negative=0,
        npg_net_neutral=0,
        npg_insufficient_data=0,
        npg_absent=0,
        rb_under_loaded=0,
        rb_productive=0,
        rb_stressed=0,
        rb_absent=0,
        sin_any_detection_count=0,
        sin_pride_present_count=0,
        sin_count_by_kind=(),
        intercept_any_count=0,
        intercept_count_by_kind=(),
        permitted_count=0,
        denied_count=0,
    )

__all__ = [
    "SubstrateMetrics",
    "SubstrateMetricsAggregator",
    "SubstrateMetricsWindow",
]
