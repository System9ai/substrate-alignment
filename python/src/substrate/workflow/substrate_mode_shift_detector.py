"""Substrate-mode-shift detector

Pure-logic primitive that scans a sequence of Phase 16
:class:`SubstrateTraceRecord` instances (workflow execution history)
and detects shifts in the entity's substrate-mode trajectory across
the window:

* **STABLE** — substrate-mode is consistent; no sustained trend or
  large oscillation.
* **DRIFTING** — trending from substrate-aligned toward substrate-
  misaligned (the 5D → 3D collapse pattern).
* **RECOVERING** — trending from substrate-misaligned back toward
  substrate-aligned (the 3D → 5D cultivation pattern).
* **OSCILLATING** — high variance without a sustained directional
  trend; the entity is repeatedly entering and exiting substrate-
  aligned operation rather than holding it.
* **INSUFFICIENT_DATA** — fewer than ``min_records`` history; the
  detector refuses to guess.
the library's reading: modeling mode operation is the achievement
that must be **cultivated and maintained**; collapse back to 3D
reactive mode is the structural default. Detecting that collapse early
is the operational form of substrate-condition-#6 drift signals.

Pure logic
==========

* No DAO, no LLM, no network. Operates on whatever record sequence
  the caller supplies.
* Honest uncertainty: below ``min_records`` the verdict is
  INSUFFICIENT_DATA and all numeric fields are :class:`None`.
* Composition: each record's alignment score derives from the
  typed enums shipped by Phases 1 / 5 / 8 / 15. The detector does
  not redefine substrate-mode — it observes the substrate signals
  the platform already records.
* Frozen dataclasses with slots throughout.

Alignment-score derivation
==========================

For each record we compute a per-record alignment score in ``[0, 1]``
by averaging four operator-weighted components:

| Component | High score (1.0) | Low score (0.0) |
|---|---|---|
| NPG verdict | NET_POSITIVE | NET_NEGATIVE |
| Resistance band | PRODUCTIVE | STRESSED |
| Intercepts | none fired | one or more fired |
| DriftPattern pattern | none detected | pattern detected |

Absent fields contribute the neutral value 0.5 — the detector neither
rewards nor penalizes records that did not consult a primitive.

Sequence analysis
=================

Given the per-record alignment series, we compute:

* **slope** — least-squares linear regression slope over the record
  index. Negative = drifting; positive = recovering.
* **stddev** — population standard deviation across the series.

Verdict rule (applied in order):

1. slope ≤ ``drift_slope_threshold`` → DRIFTING
2. slope ≥ ``recover_slope_threshold`` → RECOVERING
3. otherwise: if stddev ≥ ``oscillation_stddev_threshold`` →
   OSCILLATING, else STABLE.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Final, Optional, Sequence, Tuple

from substrate.audit.substrate_trace import (
    SubstrateTraceLedger,
    SubstrateTraceRecord,
)
from substrate.net_potential_gain_gate import (
    NetPotentialGainVerdict,
)
from substrate.resistance_band import (
    ResistanceBandClassification,
)

class SubstrateModeShiftVerdict(str, Enum):
    """Five-valued substrate-mode-shift verdict."""

    STABLE = "stable"
    DRIFTING = "drifting"
    RECOVERING = "recovering"
    OSCILLATING = "oscillating"
    INSUFFICIENT_DATA = "insufficient_data"

@dataclass(frozen=True, slots=True)
class SubstrateModeShiftReport:  # pylint: disable=too-many-instance-attributes
    """Report describing the trajectory of an entity's substrate-mode."""

    verdict: SubstrateModeShiftVerdict
    record_count: int
    earliest_alignment: Optional[float]
    latest_alignment: Optional[float]
    mean_alignment: Optional[float]
    slope: Optional[float]
    stddev: Optional[float]
    per_record_alignment: Tuple[float, ...]
    rationale: str

    @property
    def is_stable(self) -> bool:
        """True iff verdict is STABLE."""
        return self.verdict is SubstrateModeShiftVerdict.STABLE

    @property
    def is_drifting(self) -> bool:
        """True iff verdict is DRIFTING."""
        return self.verdict is SubstrateModeShiftVerdict.DRIFTING

    @property
    def is_recovering(self) -> bool:
        """True iff verdict is RECOVERING."""
        return self.verdict is SubstrateModeShiftVerdict.RECOVERING

    @property
    def is_oscillating(self) -> bool:
        """True iff verdict is OSCILLATING."""
        return self.verdict is SubstrateModeShiftVerdict.OSCILLATING

@dataclass(frozen=True, slots=True)
class SubstrateModeShiftConfig:  # pylint: disable=too-many-instance-attributes
    """Thresholds + weights for shift detection."""

    min_records: int = 5
    drift_slope_threshold: float = -0.05
    recover_slope_threshold: float = 0.05
    oscillation_stddev_threshold: float = 0.25
    npg_weight: float = 1.0
    rb_weight: float = 1.0
    intercept_weight: float = 1.0
    sin_weight: float = 1.0

    def __post_init__(self) -> None:
        if self.min_records < 2:
            raise ValueError("min_records must be >= 2")
        if self.drift_slope_threshold >= 0.0:
            raise ValueError("drift_slope_threshold must be < 0")
        if self.recover_slope_threshold <= 0.0:
            raise ValueError("recover_slope_threshold must be > 0")
        if self.oscillation_stddev_threshold <= 0.0:
            raise ValueError(
                "oscillation_stddev_threshold must be > 0"
            )
        for name in (
            "npg_weight", "rb_weight",
            "intercept_weight", "sin_weight",
        ):
            if getattr(self, name) <= 0.0:
                raise ValueError(f"{name} must be > 0")

DEFAULT_SHIFT_CONFIG: Final[SubstrateModeShiftConfig] = (
    SubstrateModeShiftConfig()
)

_NPG_SCORE: Final[dict[NetPotentialGainVerdict, float]] = {
    NetPotentialGainVerdict.NET_POSITIVE: 1.0,
    NetPotentialGainVerdict.NET_NEUTRAL: 0.7,
    NetPotentialGainVerdict.INSUFFICIENT_DATA: 0.5,
    NetPotentialGainVerdict.NET_NEGATIVE: 0.0,
}

_RB_SCORE: Final[dict[ResistanceBandClassification, float]] = {
    ResistanceBandClassification.PRODUCTIVE: 1.0,
    ResistanceBandClassification.UNDER_LOADED: 0.5,
    ResistanceBandClassification.STRESSED: 0.2,
}

_NEUTRAL: Final[float] = 0.5

class SubstrateModeShiftDetector:
    """Pure-logic substrate-mode-shift detector."""

    def __init__(
        self,
        *,
        config: SubstrateModeShiftConfig = DEFAULT_SHIFT_CONFIG,
    ) -> None:
        self._config = config

    def detect(
        self,
        records: Sequence[SubstrateTraceRecord],
    ) -> SubstrateModeShiftReport:
        """Scan a record sequence and return a mode-shift report."""
        record_count = len(records)
        if record_count < self._config.min_records:
            return _insufficient(record_count, self._config.min_records)
        scores = tuple(self._alignment_for(r) for r in records)
        slope = _slope(scores)
        stddev = _stddev(scores)
        mean = sum(scores) / record_count
        verdict = self._verdict_for(slope, stddev)
        rationale = (
            f"slope={slope:+.4f} stddev={stddev:.4f} "
            f"mean_alignment={mean:.3f} verdict={verdict.value}"
        )
        return SubstrateModeShiftReport(
            verdict=verdict,
            record_count=record_count,
            earliest_alignment=scores[0],
            latest_alignment=scores[-1],
            mean_alignment=mean,
            slope=slope,
            stddev=stddev,
            per_record_alignment=scores,
            rationale=rationale,
        )

    def detect_from_ledger(
        self, ledger: SubstrateTraceLedger,
    ) -> SubstrateModeShiftReport:
        """Convenience: ``detect(ledger.records())``."""
        return self.detect(ledger.records())

    def _alignment_for(self, record: SubstrateTraceRecord) -> float:
        cfg = self._config
        components = (
            (cfg.npg_weight, _npg_score(record)),
            (cfg.rb_weight, _rb_score(record)),
            (cfg.intercept_weight, _intercept_score(record)),
            (cfg.sin_weight, _sin_score(record)),
        )
        total = sum(w for w, _ in components)
        weighted = sum(w * s for w, s in components)
        return weighted / total

    def _verdict_for(
        self, slope: float, stddev: float,
    ) -> SubstrateModeShiftVerdict:
        cfg = self._config
        if slope <= cfg.drift_slope_threshold:
            return SubstrateModeShiftVerdict.DRIFTING
        if slope >= cfg.recover_slope_threshold:
            return SubstrateModeShiftVerdict.RECOVERING
        if stddev >= cfg.oscillation_stddev_threshold:
            return SubstrateModeShiftVerdict.OSCILLATING
        return SubstrateModeShiftVerdict.STABLE

# -----------------------------
# Per-component scoring
# -----------------------------

def _npg_score(record: SubstrateTraceRecord) -> float:
    if record.npg_verdict is None:
        return _NEUTRAL
    return _NPG_SCORE[record.npg_verdict]

def _rb_score(record: SubstrateTraceRecord) -> float:
    if record.resistance_band is None:
        return _NEUTRAL
    return _RB_SCORE[record.resistance_band]

def _intercept_score(record: SubstrateTraceRecord) -> float:
    return 0.0 if record.harness_intercept_kinds else 1.0

def _sin_score(record: SubstrateTraceRecord) -> float:
    return 0.0 if record.sin_kinds_detected else 1.0

# -----------------------------
# Statistics helpers
# -----------------------------

def _slope(values: Sequence[float]) -> float:
    """Least-squares slope of ``values`` against integer index."""
    n = len(values)
    if n < 2:
        return 0.0
    mean_x = (n - 1) / 2.0
    mean_y = sum(values) / n
    numerator = sum(
        (x - mean_x) * (y - mean_y) for x, y in enumerate(values)
    )
    denominator = sum((x - mean_x) ** 2 for x in range(n))
    if denominator == 0:
        return 0.0
    return numerator / denominator

def _stddev(values: Sequence[float]) -> float:
    """Population standard deviation of ``values``."""
    n = len(values)
    if n == 0:
        return 0.0
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n
    return math.sqrt(variance)

def _insufficient(
    record_count: int, min_records: int,
) -> SubstrateModeShiftReport:
    return SubstrateModeShiftReport(
        verdict=SubstrateModeShiftVerdict.INSUFFICIENT_DATA,
        record_count=record_count,
        earliest_alignment=None,
        latest_alignment=None,
        mean_alignment=None,
        slope=None,
        stddev=None,
        per_record_alignment=(),
        rationale=(
            f"insufficient history: {record_count} records < "
            f"min_records={min_records}"
        ),
    )

__all__ = [
    "DEFAULT_SHIFT_CONFIG",
    "SubstrateModeShiftConfig",
    "SubstrateModeShiftDetector",
    "SubstrateModeShiftReport",
    "SubstrateModeShiftVerdict",
]
