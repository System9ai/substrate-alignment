"""Tests for PairCoupledExtractionMonitor (Companion #2)."""
from __future__ import annotations

import pytest

from substrate.pair_coupling.alignment_audit import (
    AuditVerdict,
)
from substrate.pair_coupling.extraction_monitor import (
    DEFAULT_EXTRACTION_MONITOR_CONFIG,
    ExtractionMonitorConfig,
    ExtractionVerdict,
    PairCoupledExtractionMonitor,
    VerdictObservation,
)

def _obs(
    *,
    coupling: str = "pair-1",
    cycle: int,
    verdict: AuditVerdict,
) -> VerdictObservation:
    return VerdictObservation(
        coupling_id=coupling, cycle_index=cycle,
        audit_verdict=verdict,
    )

class TestObservationValidation:
    def test_round_trip(self) -> None:
        o = _obs(cycle=0, verdict=AuditVerdict.SUBSTRATE_ALIGNED)
        assert o.cycle_index == 0

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("coupling", "", "coupling_id"),
            ("cycle", -1, "cycle_index"),
        ],
    )
    def test_bad_values(
        self, field: str, value: object, match: str,
    ) -> None:
        kwargs: dict[str, object] = {
            "cycle": 0,
            "verdict": AuditVerdict.SUBSTRATE_ALIGNED,
            field: value,
        }
        with pytest.raises(ValueError, match=match):
            _obs(**kwargs)  # type: ignore[arg-type]

class TestConfig:
    def test_defaults(self) -> None:
        c = ExtractionMonitorConfig()
        assert c.sustained_extraction_rate == 0.3

    def test_min_obs_cannot_exceed_window(self) -> None:
        with pytest.raises(ValueError, match="cannot exceed"):
            ExtractionMonitorConfig(
                window_size=5, min_observations=10,
            )

    def test_threshold_ordering(self) -> None:
        with pytest.raises(ValueError, match="episodic"):
            ExtractionMonitorConfig(
                episodic_extraction_rate=0.5,
                sustained_extraction_rate=0.3,
            )

class TestMonitor:
    def setup_method(self) -> None:
        self.m = PairCoupledExtractionMonitor(coupling_id="pair-1")

    def test_insufficient_data(self) -> None:
        for i in range(5):
            self.m.observe(_obs(
                cycle=i, verdict=AuditVerdict.SUBSTRATE_ALIGNED,
            ))
        out = self.m.verdict()
        assert out.verdict is ExtractionVerdict.INSUFFICIENT_DATA

    def test_no_extraction(self) -> None:
        for i in range(15):
            self.m.observe(_obs(
                cycle=i, verdict=AuditVerdict.SUBSTRATE_ALIGNED,
            ))
        out = self.m.verdict()
        assert out.verdict is ExtractionVerdict.NO_EXTRACTION
        assert out.aligned_rate == 1.0

    def test_episodic(self) -> None:
        # 2/15 extractive = ~13% > 10% < 30%
        for i in range(13):
            self.m.observe(_obs(
                cycle=i, verdict=AuditVerdict.SUBSTRATE_ALIGNED,
            ))
        for i in range(13, 15):
            self.m.observe(_obs(
                cycle=i, verdict=AuditVerdict.EXTRACTIVE_TOWARD_A,
            ))
        out = self.m.verdict()
        assert out.verdict is ExtractionVerdict.EPISODIC

    def test_sustained(self) -> None:
        for i in range(15):
            self.m.observe(_obs(
                cycle=i, verdict=AuditVerdict.EXTRACTIVE_TOWARD_A,
            ))
        out = self.m.verdict()
        assert out.verdict is ExtractionVerdict.SUSTAINED
        assert out.sustained

    def test_coupling_mismatch_rejected(self) -> None:
        with pytest.raises(ValueError, match="does not match"):
            self.m.observe(_obs(
                coupling="other", cycle=0,
                verdict=AuditVerdict.SUBSTRATE_ALIGNED,
            ))

class TestModuleSurface:
    def test_default_singleton(self) -> None:
        assert (
            DEFAULT_EXTRACTION_MONITOR_CONFIG.window_size == 50
        )

    def test_monitor_requires_coupling_id(self) -> None:
        with pytest.raises(ValueError, match="coupling_id"):
            PairCoupledExtractionMonitor(coupling_id="")
