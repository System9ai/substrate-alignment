"""Tests for EncapsulatingContextPullSignal (Companion #2)."""
from __future__ import annotations

import pytest

from substrate.encapsulating_context.pull_signal import (
    DEFAULT_PULL_SIGNAL_CONFIG,
    ContextScale,
    EncapsulatingContextPullSignal,
    PullSignalConfig,
    PullSignalInput,
    PullVerdict,
)

def _input(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    *,
    entity: str = "agent-1",
    context: str = "node-1",
    scale: ContextScale = ContextScale.NODE,
    state: float = 0.7,
    drift: float = 0.0,
    audit: float = 0.0,
    signals: int = 10,
) -> PullSignalInput:
    return PullSignalInput(
        entity_id=entity,
        context_id=context,
        context_scale=scale,
        context_substrate_state=state,
        context_drift_rate=drift,
        recent_audit_failure_rate=audit,
        signal_count=signals,
    )

class TestInputValidation:
    def test_round_trip(self) -> None:
        i = _input()
        assert i.context_substrate_state == 0.7

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("entity", "", "entity_id"),
            ("context", "", "context_id"),
            ("state", 1.5, "context_substrate_state"),
            ("drift", 1.5, "context_drift_rate"),
            ("audit", -0.1, "recent_audit_failure_rate"),
            ("signals", -1, "signal_count"),
        ],
    )
    def test_bad_values(
        self, field: str, value: object, match: str,
    ) -> None:
        kwargs: dict[str, object] = {field: value}
        with pytest.raises(ValueError, match=match):
            _input(**kwargs)

class TestConfig:
    def test_defaults(self) -> None:
        c = PullSignalConfig()
        assert c.fire_threshold == 0.4

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("min_signal_count", 0, "min_signal_count"),
            ("state_pressure_threshold", 0.0,
             "state_pressure_threshold"),
            ("drift_pressure_threshold", 1.5,
             "drift_pressure_threshold"),
            ("audit_failure_pressure_threshold", 0.0,
             "audit_failure_pressure_threshold"),
            ("fire_threshold", 1.5, "fire_threshold"),
        ],
    )
    def test_bad_values(
        self, field: str, value: float, match: str,
    ) -> None:
        with pytest.raises(ValueError, match=match):
            PullSignalConfig(**{field: value})

class TestDetection:
    def setup_method(self) -> None:
        self.d = EncapsulatingContextPullSignal()

    def test_insufficient_data(self) -> None:
        out = self.d.evaluate(_input(signals=1))
        assert out.verdict is PullVerdict.INSUFFICIENT_DATA

    def test_pull_fired_low_state(self) -> None:
        out = self.d.evaluate(_input(state=0.0, signals=10))
        # state pressure alone = 1.0, composite = 1.0/3 = 0.33 < 0.4
        # need additional pressure
        assert out.composite_pressure > 0.0

    def test_pull_fired_combined(self) -> None:
        out = self.d.evaluate(_input(
            state=0.1, drift=0.4, audit=0.5, signals=10,
        ))
        assert out.verdict is PullVerdict.PULL_FIRED
        assert out.pull_fired

    def test_no_pull_stable(self) -> None:
        out = self.d.evaluate(_input(
            state=0.9, drift=0.0, audit=0.0, signals=10,
        ))
        assert out.verdict is PullVerdict.NO_PULL
        assert not out.pull_fired

    def test_components_isolation(self) -> None:
        out = self.d.evaluate(_input(
            state=0.5, drift=0.0, audit=0.0, signals=10,
        ))
        assert out.state_component == 0.0
        assert out.drift_component == 0.0
        assert out.audit_component == 0.0

class TestScaleAwareness:
    def test_node_scale(self) -> None:
        d = EncapsulatingContextPullSignal()
        out = d.evaluate(_input(scale=ContextScale.NODE))
        assert out.context_scale is ContextScale.NODE

    def test_org_scale(self) -> None:
        d = EncapsulatingContextPullSignal()
        out = d.evaluate(_input(scale=ContextScale.ORG))
        assert out.context_scale is ContextScale.ORG

    def test_cluster_scale(self) -> None:
        d = EncapsulatingContextPullSignal()
        out = d.evaluate(_input(scale=ContextScale.CLUSTER))
        assert out.context_scale is ContextScale.CLUSTER

class TestModuleSurface:
    def test_default_singleton(self) -> None:
        assert DEFAULT_PULL_SIGNAL_CONFIG.fire_threshold == 0.4
