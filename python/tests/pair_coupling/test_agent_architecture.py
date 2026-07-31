"""Tests for PairCoupledArchitecture (Companion #2)."""
from __future__ import annotations

import pytest

from substrate.pair_coupling.agent_architecture import (
    ArchitectureStatus,
    IllegalArchitectureTransition,
    PairCoupledArchitecture,
    PairCoupledArchitectureManager,
    PolePrincipal,
)
from substrate.pair_coupling.alignment_audit import (
    PairScale,
)

def _pole(
    *,
    eid: str = "alice",
    role: str = "lead",
    chain: str = "chain-a",
    scope: str = "primary",
) -> PolePrincipal:
    return PolePrincipal(
        entity_id=eid, role_label=role,
        attestation_chain_id=chain, designed_authority_scope=scope,
    )

def _arch(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    *,
    cid: str = "pair-1",
    scale: PairScale = PairScale.NODE_PAIR,
    a: PolePrincipal | None = None,
    b: PolePrincipal | None = None,
    asym: float = 0.4,
    cycle: int = 0,
    status: ArchitectureStatus = ArchitectureStatus.DECLARED,
) -> PairCoupledArchitecture:
    return PairCoupledArchitecture(
        coupling_id=cid,
        scale=scale,
        pole_a=a or _pole(eid="alice", role="lead", chain="chain-a"),
        pole_b=b or _pole(eid="bob", role="support", chain="chain-b"),
        designed_asymmetry=asym,
        declared_cycle_index=cycle,
        status=status,
    )

class TestPolePrincipal:
    def test_round_trip(self) -> None:
        p = _pole()
        assert p.entity_id == "alice"

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("eid", "", "entity_id"),
            ("role", "", "role_label"),
            ("chain", "", "attestation_chain_id"),
            ("scope", "", "designed_authority_scope"),
        ],
    )
    def test_bad_values(
        self, field: str, value: str, match: str,
    ) -> None:
        kwargs: dict[str, str] = {field: value}
        with pytest.raises(ValueError, match=match):
            _pole(**kwargs)

class TestArchitectureConstruction:
    def test_round_trip(self) -> None:
        arch = _arch()
        assert arch.coupling_id == "pair-1"

    def test_same_entity_rejected(self) -> None:
        with pytest.raises(ValueError, match="entity_id"):
            _arch(
                a=_pole(eid="x", chain="chain-a"),
                b=_pole(eid="x", chain="chain-b"),
            )

    def test_same_chain_rejected(self) -> None:
        with pytest.raises(ValueError, match="attestation chain"):
            _arch(
                a=_pole(eid="a", chain="chain-x"),
                b=_pole(eid="b", chain="chain-x", role="support"),
            )

    def test_same_role_rejected(self) -> None:
        with pytest.raises(ValueError, match="role_labels"):
            _arch(
                a=_pole(eid="a", role="lead", chain="chain-a"),
                b=_pole(eid="b", role="lead", chain="chain-b"),
            )

    def test_asymmetry_bounds(self) -> None:
        with pytest.raises(ValueError, match="designed_asymmetry"):
            _arch(asym=1.5)

    def test_empty_coupling_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="coupling_id"):
            _arch(cid="")

    def test_negative_cycle_rejected(self) -> None:
        with pytest.raises(ValueError, match="declared_cycle_index"):
            _arch(cycle=-1)

class TestStatus:
    def test_initial_not_active(self) -> None:
        arch = _arch(status=ArchitectureStatus.DECLARED)
        assert not arch.is_active

    def test_active(self) -> None:
        arch = _arch(status=ArchitectureStatus.ACTIVE)
        assert arch.is_active

class TestTransitions:
    def test_declared_to_active(self) -> None:
        arch = _arch(status=ArchitectureStatus.DECLARED)
        out = PairCoupledArchitectureManager.transition(
            current=arch, to_status=ArchitectureStatus.ACTIVE,
        )
        assert out.status is ArchitectureStatus.ACTIVE

    def test_active_to_quiescent(self) -> None:
        arch = _arch(status=ArchitectureStatus.ACTIVE)
        out = PairCoupledArchitectureManager.transition(
            current=arch, to_status=ArchitectureStatus.QUIESCENT,
        )
        assert out.status is ArchitectureStatus.QUIESCENT

    def test_active_to_retired(self) -> None:
        arch = _arch(status=ArchitectureStatus.ACTIVE)
        out = PairCoupledArchitectureManager.transition(
            current=arch, to_status=ArchitectureStatus.RETIRED,
        )
        assert out.status is ArchitectureStatus.RETIRED

    def test_retired_terminal(self) -> None:
        arch = _arch(status=ArchitectureStatus.RETIRED)
        for status in ArchitectureStatus:
            with pytest.raises(IllegalArchitectureTransition):
                PairCoupledArchitectureManager.transition(
                    current=arch, to_status=status,
                )

    def test_illegal_skip(self) -> None:
        arch = _arch(status=ArchitectureStatus.DECLARED)
        with pytest.raises(IllegalArchitectureTransition):
            PairCoupledArchitectureManager.transition(
                current=arch, to_status=ArchitectureStatus.QUIESCENT,
            )
