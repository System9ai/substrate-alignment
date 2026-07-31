"""Tests for SubstrateAlignedExitProtocol."""
from __future__ import annotations

import pytest

from substrate.hierarchy.exit_protocol import (
    DEFAULT_EXIT_PROTOCOL_CONFIG,
    ExitChecklist,
    ExitFailureMode,
    ExitProtocolConfig,
    ExitVerdict,
    SubstrateAlignedExitProtocol,
)

def _checklist(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    *,
    notice: bool = True,
    handoff: bool = True,
    trust: bool = True,
    accumulated_commitment: bool = True,
    no_denunciation: bool = True,
    remediation: bool = True,
) -> ExitChecklist:
    return ExitChecklist(
        notice_period_observed=notice,
        handoff_prepared=handoff,
        trust_cluster_preserved=trust,
        accumulated_commitment_documented=accumulated_commitment,
        no_public_denunciation=no_denunciation,
        unresolved_concerns_routed_substrate_alignedly=remediation,
    )

class TestExitChecklist:
    def test_round_trip(self) -> None:
        cl = _checklist()
        assert cl.satisfied_count() == 6

    def test_partial_count(self) -> None:
        cl = _checklist(handoff=False, trust=False)
        assert cl.satisfied_count() == 4

class TestConfig:
    def test_defaults(self) -> None:
        cfg = ExitProtocolConfig()
        assert cfg.aligned_min_satisfied == 6

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("aligned_min_satisfied", 0, "aligned_min_satisfied"),
            ("aligned_min_satisfied", 7, "aligned_min_satisfied"),
            ("partial_min_satisfied", 0, "partial_min_satisfied"),
        ],
    )
    def test_bad_values(self, field: str, value: int, match: str) -> None:
        with pytest.raises(ValueError, match=match):
            ExitProtocolConfig(**{field: value})

    def test_partial_must_be_below_aligned(self) -> None:
        with pytest.raises(ValueError, match="partial_min_satisfied"):
            ExitProtocolConfig(
                aligned_min_satisfied=5,
                partial_min_satisfied=5,
            )

class TestEvaluate:
    def setup_method(self) -> None:
        self.p = SubstrateAlignedExitProtocol()

    def test_empty_agent_rejected(self) -> None:
        with pytest.raises(ValueError, match="agent_id"):
            self.p.evaluate("", _checklist())

    def test_all_six_substrate_aligned(self) -> None:
        out = self.p.evaluate("alice", _checklist())
        assert out.is_substrate_aligned
        assert out.failure_modes == ()

    def test_four_partial(self) -> None:
        out = self.p.evaluate(
            "alice", _checklist(handoff=False, trust=False),
        )
        assert out.verdict is ExitVerdict.PARTIAL
        assert ExitFailureMode.NO_HANDOFF in out.failure_modes
        assert ExitFailureMode.TRUST_BURNED in out.failure_modes

    def test_zero_bridge_burning(self) -> None:
        out = self.p.evaluate(
            "alice",
            _checklist(
                notice=False,
                handoff=False,
                trust=False,
                accumulated_commitment=False,
                no_denunciation=False,
                remediation=False,
            ),
        )
        assert out.is_bridge_burning
        assert len(out.failure_modes) == 6

    def test_denunciation_flagged(self) -> None:
        out = self.p.evaluate("alice", _checklist(no_denunciation=False))
        assert ExitFailureMode.PUBLIC_DENUNCIATION in out.failure_modes

    def test_remediation_routed_flagged(self) -> None:
        out = self.p.evaluate("alice", _checklist(remediation=False))
        assert ExitFailureMode.NO_REMEDIATION_ROUTE in out.failure_modes

    def test_default_config_singleton(self) -> None:
        assert DEFAULT_EXIT_PROTOCOL_CONFIG.aligned_min_satisfied == 6
