"""Example 01: NetPotentialGainGate.

Demonstrates the load-bearing "value" discipline: every consequential
action routes through the gate, which returns one of four verdicts
based on the action's projected net effect across the affected entities.

Three scenarios are exercised:

1. Caller-supplied positive deltas → NET_POSITIVE.
2. Caller-supplied negative deltas → NET_NEGATIVE; the wrapper escalates
   to an exception.
3. Missing metadata for an affected entity → INSUFFICIENT_DATA.

Run with::

    python 01_npg_gate.py
"""
from __future__ import annotations

from substrate import (
    AlignmentVector,
    DefaultNetPotentialGainGate,
    EntityRef,
    InMemorySubstrateMetadataStore,
    NetPotentialGainNegative,
    RaiseOnNegativeGate,
    SubstrateMode,
)


def seed(store: InMemorySubstrateMetadataStore, *refs: EntityRef) -> None:
    """Seed each ref at a neutral starting alignment."""
    for ref in refs:
        store.upsert(
            ref,
            substrate_mode=SubstrateMode.MIXED,
            classifier="example-seed",
            classifier_rationale="bootstrap",
            alignment_vector=AlignmentVector(
                trust=0.5, expertise=0.5, capability=0.5, health=0.5,
            ),
            net_potential=0.5,
        )


def main() -> None:
    store = InMemorySubstrateMetadataStore()
    gate = DefaultNetPotentialGainGate(metadata_store=store)
    wrapped = RaiseOnNegativeGate(inner=gate)

    actor = EntityRef("agent", "alice")
    bob = EntityRef("user", "bob")
    carol = EntityRef("user", "carol")
    seed(store, actor, bob, carol)

    # 1. Positive net gain: both affected entities benefit.
    result = gate.evaluate(
        actor=actor,
        action_kind="teach",
        affected_entities=(bob, carol),
        proposed_outcome={
            "expected_delta_by_entity": {"bob": 0.3, "carol": 0.3},
        },
    )
    print("[1] verdict =", result.verdict.value, " score =", round(result.score, 3))

    # 2. Negative net gain: wrapped gate refuses with an exception.
    try:
        wrapped.evaluate_or_raise(
            actor=actor,
            action_kind="extract",
            affected_entities=(bob, carol),
            proposed_outcome={
                "expected_delta_by_entity": {"bob": -0.4, "carol": -0.4},
            },
        )
    except NetPotentialGainNegative as exc:
        ev = exc.evaluation
        print("[2] refused: verdict =", ev.verdict.value, " score =", round(ev.score, 3))

    # 3. Missing metadata: gate is honest about uncertainty.
    dave = EntityRef("user", "dave")  # not seeded
    result = gate.evaluate(
        actor=actor,
        action_kind="teach",
        affected_entities=(bob, dave),
        proposed_outcome={},
    )
    print(
        "[3] verdict =", result.verdict.value,
        " missing_for =",
        tuple(ref.entity_id for ref in result.missing_metadata_for),
    )


if __name__ == "__main__":
    main()
