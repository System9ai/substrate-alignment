"""Tests for Cause inference + hallmarks."""
from __future__ import annotations

from substrate.executive.cause import (
    Cause,
    HallmarkReport,
    HallmarkSource,
    infer_cause,
    max_cause,
)
from substrate.executive.scale import ExecutiveScale
from substrate.sustained_load import LoadTrend


def _ok_args(**over: object):
    args = {
        "hallmarks": HallmarkReport(),
        "profile_valid": True,
        "npg_insufficient": False,
        "trend": LoadTrend.NOMINAL,
    }
    args.update(over)
    return args


class TestHallmarkReport:
    def test_clean_report_not_malicious(self) -> None:
        assert HallmarkReport().any_malicious is False

    def test_any_hallmark_is_malicious(self) -> None:
        assert HallmarkReport(evading_limits=True).any_malicious is True
        assert HallmarkReport(resource_hoarding=True).any_malicious is True


class TestInferCause:
    def test_none_when_clean(self) -> None:
        assert infer_cause(**_ok_args()) is Cause.NONE

    def test_stress_on_strain(self) -> None:
        assert infer_cause(**_ok_args(trend=LoadTrend.SUSTAINED_STRAIN)) is Cause.STRESS

    def test_stress_on_spike(self) -> None:
        assert infer_cause(**_ok_args(trend=LoadTrend.SPIKE)) is Cause.STRESS

    def test_accident_on_invalid_profile(self) -> None:
        assert infer_cause(**_ok_args(profile_valid=False)) is Cause.ACCIDENT

    def test_accident_on_insufficient_npg(self) -> None:
        assert infer_cause(**_ok_args(npg_insufficient=True)) is Cause.ACCIDENT

    def test_malice_preempts_everything(self) -> None:
        # A malicious hallmark wins even with strain + invalid profile.
        cause = infer_cause(**_ok_args(
            hallmarks=HallmarkReport(peer_displacement=True),
            profile_valid=False,
            trend=LoadTrend.DEBT_ACCRUING,
        ))
        assert cause is Cause.MALICE

    def test_accident_outranks_stress(self) -> None:
        cause = infer_cause(**_ok_args(
            profile_valid=False, trend=LoadTrend.SUSTAINED_STRAIN,
        ))
        assert cause is Cause.ACCIDENT


class TestIntentEscalatesOnly:
    def test_intent_escalates(self) -> None:
        # A clean inference + a MALICE intent → MALICE.
        assert infer_cause(**_ok_args(), intent=Cause.MALICE) is Cause.MALICE

    def test_intent_cannot_lower(self) -> None:
        # Inferred MALICE + a benign NONE intent stays MALICE.
        cause = infer_cause(
            **_ok_args(hallmarks=HallmarkReport(unbounded_growth=True)),
            intent=Cause.NONE,
        )
        assert cause is Cause.MALICE


class TestMaxCause:
    def test_ordering(self) -> None:
        assert max_cause(Cause.NONE, Cause.STRESS) is Cause.STRESS
        assert max_cause(Cause.ACCIDENT, Cause.STRESS) is Cause.ACCIDENT
        assert max_cause(Cause.MALICE, Cause.ACCIDENT) is Cause.MALICE


def test_hallmark_source_protocol() -> None:
    class _Src:
        def hallmarks(self, *, actor_entity_id: str, scale: ExecutiveScale) -> HallmarkReport:
            assert actor_entity_id and scale
            return HallmarkReport(evading_limits=True)

    src = _Src()
    assert isinstance(src, HallmarkSource)
    assert src.hallmarks(actor_entity_id="a", scale=ExecutiveScale.AGENT).any_malicious
