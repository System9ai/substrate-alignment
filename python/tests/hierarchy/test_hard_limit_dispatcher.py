"""Tests for HardLimitDispatcher."""
from __future__ import annotations

import pytest

from substrate.hierarchy.hard_limit_dispatcher import (
    DEFAULT_HARD_LIMIT_DISPATCHER_CONFIG,
    AuthorityContext,
    DispatchVerdict,
    HardLimitDispatcher,
    HardLimitDispatcherConfig,
    ProposedAction,
)

def _action(
    *,
    hard_limit: bool = False,
    misaligned_compliance: bool = False,
) -> ProposedAction:
    return ProposedAction(
        action_id="a1",
        description="test action",
        crosses_hard_limit=hard_limit,
        requires_substrate_misaligned_compliance=misaligned_compliance,
    )

def _authority(
    *,
    pressure: float = 0.5,
    long_cycle: bool = False,
    harm_intent: float = 0.0,
) -> AuthorityContext:
    return AuthorityContext(
        authority_id="auth1",
        pressure_intensity=pressure,
        long_cycle_framing_present=long_cycle,
        short_cycle_harm_intent_score=harm_intent,
    )

class TestProposedActionValidation:
    def test_round_trip(self) -> None:
        a = _action()
        assert a.action_id == "a1"

    def test_empty_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="action_id"):
            ProposedAction(
                action_id="",
                description="x",
                crosses_hard_limit=False,
                requires_substrate_misaligned_compliance=False,
            )

class TestAuthorityContextValidation:
    def test_round_trip(self) -> None:
        a = _authority()
        assert a.authority_id == "auth1"

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("authority_id", "", "authority_id"),
            ("pressure_intensity", -0.1, "pressure_intensity"),
            ("pressure_intensity", 1.1, "pressure_intensity"),
            (
                "short_cycle_harm_intent_score", -0.1,
                "short_cycle_harm_intent_score",
            ),
            (
                "short_cycle_harm_intent_score", 1.1,
                "short_cycle_harm_intent_score",
            ),
        ],
    )
    def test_bad_values(self, field: str, value: object, match: str) -> None:
        kwargs = {
            "authority_id": "auth1",
            "pressure_intensity": 0.5,
            "long_cycle_framing_present": False,
            "short_cycle_harm_intent_score": 0.0,
        }
        kwargs[field] = value
        with pytest.raises(ValueError, match=match):
            AuthorityContext(**kwargs)

class TestConfig:
    def test_defaults(self) -> None:
        cfg = HardLimitDispatcherConfig()
        assert cfg.short_cycle_harm_threshold == 0.5

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("short_cycle_harm_threshold", 0.0, "short_cycle_harm_threshold"),
            ("short_cycle_harm_threshold", 1.5, "short_cycle_harm_threshold"),
            (
                "pressure_amplification_threshold", 0.0,
                "pressure_amplification_threshold",
            ),
        ],
    )
    def test_bad_values(self, field: str, value: float, match: str) -> None:
        with pytest.raises(ValueError, match=match):
            HardLimitDispatcherConfig(**{field: value})

class TestDispatchOrdering:
    def setup_method(self) -> None:
        self.d = HardLimitDispatcher()

    def test_approve_clean(self) -> None:
        out = self.d.dispatch(_action(), _authority())
        assert out.verdict is DispatchVerdict.APPROVE
        assert out.approved

    def test_hard_limit_dominates(self) -> None:
        # Even with inversion + sucker mode + misaligned compliance,
        # hard limit takes precedence
        out = self.d.dispatch(
            _action(hard_limit=True, misaligned_compliance=True),
            _authority(long_cycle=True, harm_intent=0.9),
            substrate_state_trajectory_declining=True,
        )
        assert out.verdict is DispatchVerdict.REFUSE_HARD_LIMIT
        assert out.refused

    def test_inversion_dominates_sucker_and_humble(self) -> None:
        out = self.d.dispatch(
            _action(misaligned_compliance=True),
            _authority(long_cycle=True, harm_intent=0.8),
            substrate_state_trajectory_declining=True,
        )
        assert out.verdict is DispatchVerdict.REFUSE_INVERSION

    def test_sucker_dominates_humble(self) -> None:
        out = self.d.dispatch(
            _action(misaligned_compliance=True),
            _authority(),
            substrate_state_trajectory_declining=True,
        )
        assert out.verdict is DispatchVerdict.REFUSE_SUCKER_MODE

    def test_humble_stand(self) -> None:
        out = self.d.dispatch(
            _action(misaligned_compliance=True),
            _authority(),
        )
        assert out.verdict is DispatchVerdict.REFUSE_HUMBLE_STAND

class TestInversionDetection:
    def setup_method(self) -> None:
        self.d = HardLimitDispatcher()

    def test_inversion_requires_both_signals(self) -> None:
        # Long cycle framing alone — approves
        out = self.d.dispatch(
            _action(),
            _authority(long_cycle=True, harm_intent=0.0),
        )
        assert out.approved

    def test_inversion_low_harm_intent_approves(self) -> None:
        out = self.d.dispatch(
            _action(),
            _authority(long_cycle=True, harm_intent=0.3),
        )
        assert out.approved

    def test_inversion_at_threshold(self) -> None:
        out = self.d.dispatch(
            _action(),
            _authority(long_cycle=True, harm_intent=0.5),
        )
        assert out.verdict is DispatchVerdict.REFUSE_INVERSION

class TestDecisionProperties:
    def test_carries_ids(self) -> None:
        d = HardLimitDispatcher()
        out = d.dispatch(_action(), _authority())
        assert out.action_id == "a1"
        assert out.authority_id == "auth1"

    def test_default_config_singleton(self) -> None:
        assert (
            DEFAULT_HARD_LIMIT_DISPATCHER_CONFIG.short_cycle_harm_threshold
            == 0.5
        )
