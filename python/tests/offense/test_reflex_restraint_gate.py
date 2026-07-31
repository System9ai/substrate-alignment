# pylint: disable=missing-class-docstring,missing-function-docstring
# pylint: disable=too-many-public-methods
# pylint: disable=too-few-public-methods
"""Tests for ReflexRestraintGate (fight-or-flight vs deliberate restraint)."""
from __future__ import annotations

import pytest

from substrate.net_potential_gain_gate import NetPotentialGainVerdict
from substrate.offense.reflex_restraint_gate import (
    DEFAULT_RESTRAINT_GATE_CONFIG,
    RESTRAINT_VERDICTS,
    ReflexRestraintGate,
    RestraintGateConfig,
    RestraintVerdict,
    ThreatAppraisal,
)


def _appraisal(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    *,
    actor: str = "alice",
    threat: str = "threat-1",
    survival: float = 0.0,
    action_kind: str = "retaliate",
    npg: NetPotentialGainVerdict = NetPotentialGainVerdict.NET_NEGATIVE,
    crosses_hard_limit: bool = False,
    has_live_counterparty: bool = True,
) -> ThreatAppraisal:
    return ThreatAppraisal(
        actor_entity_id=actor,
        threat_id=threat,
        survival_threat_score=survival,
        reactive_action_kind=action_kind,
        reactive_action_npg=npg,
        crosses_hard_limit=crosses_hard_limit,
        has_live_counterparty=has_live_counterparty,
    )


class TestAppraisalValidation:
    def test_round_trip(self) -> None:
        a = _appraisal(survival=0.5)
        assert a.survival_threat_score == 0.5
        assert a.has_live_counterparty is True

    def test_empty_actor_rejected(self) -> None:
        with pytest.raises(ValueError, match="actor_entity_id"):
            _appraisal(actor="")

    def test_empty_threat_rejected(self) -> None:
        with pytest.raises(ValueError, match="threat_id"):
            _appraisal(threat="")

    def test_empty_action_kind_rejected(self) -> None:
        with pytest.raises(ValueError, match="reactive_action_kind"):
            _appraisal(action_kind="")

    def test_survival_score_out_of_range_rejected(self) -> None:
        with pytest.raises(ValueError, match="survival_threat_score"):
            _appraisal(survival=1.5)
        with pytest.raises(ValueError, match="survival_threat_score"):
            _appraisal(survival=-0.1)


class TestVerdictsetLockstep:
    def test_verdicts_match_enum(self) -> None:
        assert RESTRAINT_VERDICTS == {v.value for v in RestraintVerdict}


class TestConfigValidation:
    def test_default_threshold(self) -> None:
        assert DEFAULT_RESTRAINT_GATE_CONFIG.survival_threshold == 0.70

    def test_threshold_out_of_range_rejected(self) -> None:
        with pytest.raises(ValueError, match="survival_threshold"):
            RestraintGateConfig(survival_threshold=0.0)
        with pytest.raises(ValueError, match="survival_threshold"):
            RestraintGateConfig(survival_threshold=1.5)


class TestHardLimit:
    def test_hard_limit_refused_even_at_survival(self) -> None:
        gate = ReflexRestraintGate()
        d = gate.evaluate(_appraisal(survival=1.0, crosses_hard_limit=True))
        assert d.verdict is RestraintVerdict.REFUSE_HARD_LIMIT
        assert d.reactive_permitted is False

    def test_hard_limit_refused_at_provocation(self) -> None:
        gate = ReflexRestraintGate()
        d = gate.evaluate(_appraisal(survival=0.1, crosses_hard_limit=True))
        assert d.verdict is RestraintVerdict.REFUSE_HARD_LIMIT


class TestSurvivalReflex:
    def test_genuine_survival_threat_acts_reactive(self) -> None:
        gate = ReflexRestraintGate()
        d = gate.evaluate(_appraisal(survival=0.9))
        assert d.verdict is RestraintVerdict.ACT_REACTIVE
        assert d.reflex_justified is True
        assert d.reactive_permitted is True
        assert d.requires_deliberation is False

    def test_threshold_boundary_inclusive(self) -> None:
        gate = ReflexRestraintGate()
        d = gate.evaluate(_appraisal(survival=0.70))
        assert d.verdict is RestraintVerdict.ACT_REACTIVE

    def test_survival_acts_even_with_negative_npg(self) -> None:
        gate = ReflexRestraintGate()
        d = gate.evaluate(
            _appraisal(survival=0.95, npg=NetPotentialGainVerdict.NET_NEGATIVE)
        )
        assert d.verdict is RestraintVerdict.ACT_REACTIVE


class TestRestraintOverride:
    def test_provocation_net_negative_with_counterparty_de_escalates(
        self,
    ) -> None:
        gate = ReflexRestraintGate()
        d = gate.evaluate(
            _appraisal(
                survival=0.2,
                npg=NetPotentialGainVerdict.NET_NEGATIVE,
                has_live_counterparty=True,
            )
        )
        assert d.verdict is RestraintVerdict.DE_ESCALATE
        assert d.reflex_justified is False
        assert d.requires_deliberation is True

    def test_provocation_net_negative_no_counterparty_restrains(self) -> None:
        gate = ReflexRestraintGate()
        d = gate.evaluate(
            _appraisal(
                survival=0.2,
                npg=NetPotentialGainVerdict.NET_NEGATIVE,
                has_live_counterparty=False,
            )
        )
        assert d.verdict is RestraintVerdict.RESTRAIN

    def test_provocation_net_positive_still_restrains(self) -> None:
        gate = ReflexRestraintGate()
        d = gate.evaluate(
            _appraisal(survival=0.3, npg=NetPotentialGainVerdict.NET_POSITIVE)
        )
        assert d.verdict is RestraintVerdict.RESTRAIN

    def test_provocation_net_neutral_restrains(self) -> None:
        gate = ReflexRestraintGate()
        d = gate.evaluate(
            _appraisal(survival=0.3, npg=NetPotentialGainVerdict.NET_NEUTRAL)
        )
        assert d.verdict is RestraintVerdict.RESTRAIN

    def test_provocation_insufficient_npg_data(self) -> None:
        gate = ReflexRestraintGate()
        d = gate.evaluate(
            _appraisal(
                survival=0.3,
                npg=NetPotentialGainVerdict.INSUFFICIENT_DATA,
            )
        )
        assert d.verdict is RestraintVerdict.INSUFFICIENT_DATA


class TestConfigTuning:
    def test_lower_survival_threshold_permits_more_reflex(self) -> None:
        gate = ReflexRestraintGate(
            config=RestraintGateConfig(survival_threshold=0.30)
        )
        d = gate.evaluate(_appraisal(survival=0.35))
        assert d.verdict is RestraintVerdict.ACT_REACTIVE

    def test_decision_carries_inputs_through(self) -> None:
        gate = ReflexRestraintGate()
        d = gate.evaluate(_appraisal(actor="agent-7", threat="t-9"))
        assert d.actor_entity_id == "agent-7"
        assert d.threat_id == "t-9"
        assert d.reactive_action_kind == "retaliate"
