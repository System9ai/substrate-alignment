"""Tests for OutgrowingPatternDetector."""
from __future__ import annotations

import pytest

from substrate.hierarchy.outgrowing_detector import (
    DEFAULT_OUTGROWING_CONFIG,
    CycleObservation,
    OutgrowingConfig,
    OutgrowingPatternDetector,
    OutgrowingSignal,
    OutgrowingVerdict,
)

def _cycle(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    seq: int,
    *,
    capacity_exceeded: bool = True,
    failures: int = 0,
    work: float = 0.9,
    trust_size: int = 5,
    authority: int = 3,
    grandiose: int = 0,
    timestamp: int = 0,
) -> CycleObservation:
    return CycleObservation(
        sequence=seq,
        timestamp=timestamp or seq,
        capacity_exceeded_role=capacity_exceeded,
        role_failures_count=failures,
        accumulated_work_product_score=work,
        trust_cluster_size=trust_size,
        authority_corroborations=authority,
        grandiose_claim_count=grandiose,
    )

class TestCycleObservation:
    def test_round_trip(self) -> None:
        c = _cycle(0)
        assert c.sequence == 0

    @pytest.mark.parametrize(
        "kwargs,match",
        [
            ({"seq": -1}, "sequence"),
            ({"failures": -1}, "role_failures_count"),
            ({"work": 1.5}, "accumulated_work_product_score"),
            ({"trust_size": -1}, "trust_cluster_size"),
            ({"authority": -1}, "authority_corroborations"),
            ({"grandiose": -1}, "grandiose_claim_count"),
        ],
    )
    def test_invalid_fields(self, kwargs: dict, match: str) -> None:
        defaults: dict[str, object] = {"seq": 0}
        defaults.update(kwargs)
        with pytest.raises(ValueError, match=match):
            _cycle(**defaults)

    def test_bad_timestamp(self) -> None:
        with pytest.raises(ValueError, match="timestamp"):
            CycleObservation(
                sequence=0,
                timestamp=-1,
                capacity_exceeded_role=True,
                role_failures_count=0,
                accumulated_work_product_score=0.0,
                trust_cluster_size=0,
                authority_corroborations=0,
                grandiose_claim_count=0,
            )

class TestConfig:
    def test_defaults(self) -> None:
        cfg = OutgrowingConfig()
        assert cfg.sustained_cycles_window >= 1

    @pytest.mark.parametrize(
        "field,value,match",
        [
            (
                "capacity_exceed_rate_threshold", 0.0,
                "capacity_exceed_rate_threshold",
            ),
            (
                "role_failure_rate_threshold", 0.0,
                "role_failure_rate_threshold",
            ),
            ("work_product_threshold", 0.0, "work_product_threshold"),
            ("trust_cluster_min_size", 0, "trust_cluster_min_size"),
            (
                "authority_corroborations_min", 0,
                "authority_corroborations_min",
            ),
            (
                "grandiose_claims_max_allowed", -1,
                "grandiose_claims_max_allowed",
            ),
            ("sustained_cycles_window", 0, "sustained_cycles_window"),
            (
                "min_history_for_assessment", 0,
                "min_history_for_assessment",
            ),
        ],
    )
    def test_bad_values(self, field: str, value: float, match: str) -> None:
        with pytest.raises(ValueError, match=match):
            OutgrowingConfig(**{field: value})

class TestAssessmentFlow:
    def setup_method(self) -> None:
        self.d = OutgrowingPatternDetector()

    def test_empty_agent_rejected(self) -> None:
        with pytest.raises(ValueError, match="agent_id"):
            self.d.assess("", ())

    def test_empty_cycles_insufficient(self) -> None:
        out = self.d.assess("alice", ())
        assert out.verdict is OutgrowingVerdict.INSUFFICIENT_DATA
        assert out.findings == ()

    def test_short_history_insufficient(self) -> None:
        out = self.d.assess("alice", (_cycle(0), _cycle(1)))
        assert out.verdict is OutgrowingVerdict.INSUFFICIENT_DATA

class TestGenuineOutgrowing:
    def setup_method(self) -> None:
        self.d = OutgrowingPatternDetector()

    def test_full_signals_yield_genuine(self) -> None:
        cycles = tuple(_cycle(i) for i in range(5))
        out = self.d.assess("alice", cycles)
        assert out.verdict is OutgrowingVerdict.GENUINE_OUTGROWING
        assert out.is_genuine_outgrowing

    def test_unsorted_input_handled(self) -> None:
        cycles = tuple(_cycle(i) for i in [3, 1, 4, 0, 2])
        out = self.d.assess("alice", cycles)
        assert out.is_genuine_outgrowing

class TestMisalignedFrustration:
    def setup_method(self) -> None:
        self.d = OutgrowingPatternDetector()

    def test_high_capacity_high_failures_misaligned(self) -> None:
        cycles = tuple(_cycle(i, failures=5) for i in range(5))
        out = self.d.assess("alice", cycles)
        assert out.is_misaligned_frustration

    def test_high_capacity_grandiose_misaligned(self) -> None:
        cycles = tuple(_cycle(i, grandiose=5) for i in range(5))
        out = self.d.assess("alice", cycles)
        assert out.is_misaligned_frustration

    def test_high_capacity_low_trust_misaligned(self) -> None:
        # capacity exceeds, role intact, no grandiose — but no trust cluster
        cycles = tuple(_cycle(i, trust_size=0) for i in range(5))
        out = self.d.assess("alice", cycles)
        assert out.verdict is (
            OutgrowingVerdict.SUBSTRATE_MISALIGNED_FRUSTRATION
        )

class TestNotOutgrowing:
    def setup_method(self) -> None:
        self.d = OutgrowingPatternDetector()

    def test_low_capacity_not_outgrowing(self) -> None:
        cycles = tuple(_cycle(i, capacity_exceeded=False) for i in range(5))
        out = self.d.assess("alice", cycles)
        assert out.verdict is OutgrowingVerdict.NOT_OUTGROWING

class TestSignalFindings:
    def test_missing_signals_reported(self) -> None:
        d = OutgrowingPatternDetector()
        cycles = tuple(_cycle(i, failures=3, grandiose=5) for i in range(5))
        out = d.assess("alice", cycles)
        missing = out.missing_signals()
        assert OutgrowingSignal.ROLE_INTEGRITY_INTACT in missing
        assert OutgrowingSignal.NO_GRANDIOSE_CLAIMS in missing
        assert OutgrowingSignal.CAPACITY_EXCEEDING_ROLE not in missing

    def test_rationale_includes_verdict(self) -> None:
        d = OutgrowingPatternDetector()
        cycles = tuple(_cycle(i) for i in range(5))
        out = d.assess("alice", cycles)
        assert OutgrowingVerdict.GENUINE_OUTGROWING.value in out.rationale

    def test_default_config_singleton(self) -> None:
        cfg = DEFAULT_OUTGROWING_CONFIG
        assert cfg.capacity_exceed_rate_threshold == 0.6

class TestWindowEnforcement:
    def test_only_last_window_counts(self) -> None:
        # First 5 cycles bad, last 5 good — window size 5 → genuine outgrowing
        d = OutgrowingPatternDetector(
            config=OutgrowingConfig(
                sustained_cycles_window=5,
                min_history_for_assessment=3,
            ),
        )
        cycles = tuple(
            _cycle(
                i,
                capacity_exceeded=(i >= 5),
                failures=(5 if i < 5 else 0),
            )
            for i in range(10)
        )
        out = d.assess("alice", cycles)
        assert out.is_genuine_outgrowing
