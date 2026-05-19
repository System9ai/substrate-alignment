"""Tests for OffenseHandlingProtocol (Companion #2)."""
from __future__ import annotations

import pytest

from substrate.offense.handling_protocol import (
    DEFAULT_OFFENSE_HANDLING_CONFIG,
    OffenseHandlingConfig,
    OffenseHandlingInput,
    OffenseHandlingProtocol,
    OffenseResponse,
    OffenseSeverity,
)
from substrate.offense.signal_type import (
    OffenseSignalType,
)
from substrate.pair_coupling.state_machine import (
    PairCouplingState,
)

def _input(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    *,
    actor: str = "alice",
    peer: str = "bob",
    signal: OffenseSignalType = OffenseSignalType.SCARCITY_AGGRESSION,
    severity: OffenseSeverity = OffenseSeverity.LOW,
    pair: PairCouplingState = PairCouplingState.COUPLED,
    prior: int = 0,
) -> OffenseHandlingInput:
    return OffenseHandlingInput(
        actor_entity_id=actor,
        peer_entity_id=peer,
        signal_type=signal,
        severity=severity,
        pair_state=pair,
        prior_offense_count=prior,
    )

class TestInputValidation:
    def test_round_trip(self) -> None:
        i = _input()
        assert i.severity is OffenseSeverity.LOW

    def test_same_actor_peer_rejected(self) -> None:
        with pytest.raises(ValueError, match="differ"):
            _input(actor="x", peer="x")

    def test_negative_prior_rejected(self) -> None:
        with pytest.raises(ValueError, match="prior_offense_count"):
            _input(prior=-1)

class TestConfig:
    def test_defaults(self) -> None:
        c = OffenseHandlingConfig()
        assert c.repeat_offense_escalation_count == 3

    def test_repeat_count_must_be_positive(self) -> None:
        with pytest.raises(
            ValueError, match="repeat_offense_escalation_count",
        ):
            OffenseHandlingConfig(repeat_offense_escalation_count=0)

class TestHandling:
    def setup_method(self) -> None:
        self.h = OffenseHandlingProtocol()

    def test_unclassified_acknowledged(self) -> None:
        d = self.h.handle(_input(
            signal=OffenseSignalType.UNCLASSIFIED,
            severity=OffenseSeverity.HIGH,
        ))
        assert d.response is OffenseResponse.ACKNOWLEDGE

    def test_critical_dissolves(self) -> None:
        d = self.h.handle(_input(severity=OffenseSeverity.CRITICAL))
        assert d.response is OffenseResponse.DISSOLVE
        assert d.is_terminal_response

    def test_attribution_concealment_dissolves(self) -> None:
        d = self.h.handle(_input(
            signal=OffenseSignalType.ATTRIBUTION_CONCEALMENT,
            severity=OffenseSeverity.LOW,
        ))
        assert d.response is OffenseResponse.DISSOLVE

    def test_repeat_moderate_escalates(self) -> None:
        d = self.h.handle(_input(
            severity=OffenseSeverity.MODERATE, prior=3,
        ))
        assert d.response is OffenseResponse.ESCALATE
        assert d.halt_reason_hint == "SUSTAINED_DRIFT_CRITICAL"

    def test_high_severity_escalates(self) -> None:
        d = self.h.handle(_input(severity=OffenseSeverity.HIGH))
        assert d.response is OffenseResponse.ESCALATE

    def test_moderate_first_offense_repairs(self) -> None:
        d = self.h.handle(_input(severity=OffenseSeverity.MODERATE))
        assert d.response is OffenseResponse.REPAIR

    def test_low_severity_acknowledged(self) -> None:
        d = self.h.handle(_input(severity=OffenseSeverity.LOW))
        assert d.response is OffenseResponse.ACKNOWLEDGE

    def test_dissolving_pair_acknowledged(self) -> None:
        d = self.h.handle(_input(
            pair=PairCouplingState.DISSOLVING,
            severity=OffenseSeverity.HIGH,
        ))
        assert d.response is OffenseResponse.ACKNOWLEDGE

class TestModuleSurface:
    def test_default_singleton(self) -> None:
        assert (
            DEFAULT_OFFENSE_HANDLING_CONFIG.repeat_offense_escalation_count
            == 3
        )
