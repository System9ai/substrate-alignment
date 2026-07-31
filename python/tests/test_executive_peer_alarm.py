"""Tests for peer awareness + collective alarm propagation."""
from __future__ import annotations

import pytest

from substrate.executive.peer_alarm import (
    AlarmDisposition,
    PeerAlarm,
    PeerAnomaly,
    assess_alarm,
    correlate_anomalies,
    heeded_alarms,
)
from substrate.executive.scale import ExecutiveScale


def _anoms(*pairs: tuple[str, bool]) -> list[PeerAnomaly]:
    return [PeerAnomaly(pid, a) for pid, a in pairs]


class TestCorrelateAnomalies:
    def test_empty_returns_none(self) -> None:
        assert correlate_anomalies([], group_scale=ExecutiveScale.RACK) is None

    def test_lone_anomaly_is_noise(self) -> None:
        v = correlate_anomalies(
            _anoms(("c1", True), ("c2", False), ("c3", False)),
            group_scale=ExecutiveScale.RACK,
        )
        assert v is not None
        assert v.is_group_problem is False

    def test_correlated_is_group_problem(self) -> None:
        v = correlate_anomalies(
            _anoms(("c1", True), ("c2", True), ("c3", True), ("c4", False)),
            group_scale=ExecutiveScale.RACK,
        )
        assert v is not None
        assert v.is_group_problem is True
        assert v.anomalous_peers == 3
        assert v.group_scale is ExecutiveScale.RACK

    def test_threshold_respected(self) -> None:
        anoms = _anoms(("c1", True), ("c2", True))
        strict = correlate_anomalies(
            anoms, group_scale=ExecutiveScale.RACK, min_correlated=3
        )
        loose = correlate_anomalies(
            anoms, group_scale=ExecutiveScale.RACK, min_correlated=2
        )
        assert strict is not None and strict.is_group_problem is False
        assert loose is not None and loose.is_group_problem is True

    def test_min_correlated_validated(self) -> None:
        with pytest.raises(ValueError, match="min_correlated"):
            correlate_anomalies(
                _anoms(("c1", True)),
                group_scale=ExecutiveScale.RACK,
                min_correlated=0,
            )


class TestAssessAlarm:
    def _alarm(self, src: str, trust: float, sev: float = 0.8) -> PeerAlarm:
        return PeerAlarm("a", src, ExecutiveScale.RACK, "fire", sev, trust)

    def test_lone_untrusted_suppressed(self) -> None:
        # The panic-injection guard: untrusted + uncorroborated → suppress.
        assert assess_alarm(self._alarm("badguy", 0.2)).disposition is AlarmDisposition.SUPPRESS

    def test_lone_trusted_held(self) -> None:
        assert assess_alarm(self._alarm("goodcell", 0.8)).disposition is AlarmDisposition.HOLD

    def test_corroborated_heeded(self) -> None:
        alarm = self._alarm("c0", 0.4)  # even a low-trust source is heeded if corroborated
        others = [self._alarm("c1", 0.4), self._alarm("c2", 0.4)]
        assert assess_alarm(alarm, others).disposition is AlarmDisposition.HEED

    def test_same_source_does_not_self_corroborate(self) -> None:
        alarm = self._alarm("c0", 0.8)
        # two more alarms but all from c0 → no independent corroboration.
        dupes = [self._alarm("c0", 0.8), self._alarm("c0", 0.8)]
        a = assess_alarm(alarm, dupes)
        assert a.corroboration_count == 0
        assert a.disposition is AlarmDisposition.HOLD

    def test_different_scale_does_not_corroborate(self) -> None:
        alarm = self._alarm("c0", 0.8)
        other_scale = PeerAlarm("a", "c1", ExecutiveScale.ZONE, "fire", 0.8, 0.8)
        a = assess_alarm(alarm, [other_scale])
        assert a.corroboration_count == 0

    def test_severity_validated(self) -> None:
        with pytest.raises(ValueError, match="severity"):
            PeerAlarm("a", "c", ExecutiveScale.RACK, "fire", 1.5, 0.5)


class TestHeededAlarms:
    def test_independent_batch_corroborates_to_heed(self) -> None:
        alarms = [
            PeerAlarm(f"a{i}", f"cell{i}", ExecutiveScale.RACK, "fire", 0.8, 0.7)
            for i in range(3)
        ]
        assert len(heeded_alarms(alarms)) == 3

    def test_lone_alarm_not_heeded(self) -> None:
        alarms = [PeerAlarm("a", "c0", ExecutiveScale.RACK, "fire", 0.9, 0.9)]
        assert not heeded_alarms(alarms)
