"""Tests for CompartmentalizationInvariantVerifier (Companion #2)."""
from __future__ import annotations

import pytest

from substrate.state_layer.compartmentalization_verifier import (
    ALL_INVARIANT_FAILURE_MODES,
    CompartmentalizationInvariantVerifier,
    CompartmentalizationVerdict,
    InvariantFailureMode,
    VerifierContext,
)
from substrate.state_layer.consolidation_event import (
    ConsolidationEvent,
    ConsolidationKind,
)

def _event(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    *,
    eid: str = "e-1",
    compartment: str = "compartment-A",
    rep_hash: str = "hash-abc",
    first: int = 0,
    last: int = 10,
    invariants: tuple[str, ...] = (
        "identity-preserved",
        "cryptographic-chain-intact",
        "compartment-label-preserved",
    ),
) -> ConsolidationEvent:
    return ConsolidationEvent(
        event_id=eid,
        actor_entity_id="alice",
        compartment_label_id=compartment,
        kind=ConsolidationKind.CHECKPOINT,
        source_first_cycle=first,
        source_last_cycle=last,
        compressed_representation_hash=rep_hash,
        declared_invariants=invariants,
    )

def _context(
    *,
    prior_label: str = "compartment-A",
    actor_in: bool = True,
) -> VerifierContext:
    return VerifierContext(
        prior_compartment_label_id=prior_label,
        actor_in_compartment=actor_in,
    )

class TestContextValidation:
    def test_round_trip(self) -> None:
        c = _context()
        assert c.actor_in_compartment

    def test_empty_label_rejected(self) -> None:
        with pytest.raises(
            ValueError, match="prior_compartment_label_id",
        ):
            VerifierContext(
                prior_compartment_label_id="",
                actor_in_compartment=True,
            )

class TestVerifier:
    def test_preserved(self) -> None:
        d = CompartmentalizationInvariantVerifier.verify(
            _event(), _context(),
        )
        assert d.preserved
        assert d.failure_modes == ()

    def test_invariants_missing(self) -> None:
        d = CompartmentalizationInvariantVerifier.verify(
            _event(invariants=("identity-preserved",)), _context(),
        )
        assert d.verdict is CompartmentalizationVerdict.VIOLATED
        assert (
            InvariantFailureMode.REQUIRED_INVARIANTS_NOT_DECLARED
            in d.failure_modes
        )

    def test_label_changed(self) -> None:
        d = CompartmentalizationInvariantVerifier.verify(
            _event(compartment="compartment-B"), _context(),
        )
        assert (
            InvariantFailureMode.COMPARTMENT_LABEL_CHANGED
            in d.failure_modes
        )

    def test_actor_not_in_compartment(self) -> None:
        d = CompartmentalizationInvariantVerifier.verify(
            _event(), _context(actor_in=False),
        )
        assert (
            InvariantFailureMode.ACTOR_NOT_IN_COMPARTMENT
            in d.failure_modes
        )

    def test_hash_malformed(self) -> None:
        d = CompartmentalizationInvariantVerifier.verify(
            _event(rep_hash="bad hash with space"), _context(),
        )
        assert (
            InvariantFailureMode.COMPRESSION_HASH_MALFORMED
            in d.failure_modes
        )

    def test_multiple_failures_surfaced(self) -> None:
        d = CompartmentalizationInvariantVerifier.verify(
            _event(
                compartment="compartment-Z",
                invariants=("identity-preserved",),
            ),
            _context(prior_label="compartment-A", actor_in=False),
        )
        assert len(d.failure_modes) >= 3

class TestModuleSurface:
    def test_all_failure_modes(self) -> None:
        assert len(ALL_INVARIANT_FAILURE_MODES) == 5
