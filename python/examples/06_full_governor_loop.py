"""Example 06: Full governor loop.

Demonstrates the composition pattern: an agent's decision flows through
every relevant primitive in one pass:

1. AlignmentRefresher folds an updated trust signal into the stored
   metadata; the entity's substrate mode updates.
2. NetPotentialGainGate evaluates a proposed action with the freshly
   refreshed metadata available.
3. The gate's verdict + classification appends to the audit ledger.
4. ResistanceBand classifies the system's current utilisation; the
   classification appends to the same record.
5. The full record is hash-chained against the prior record; ledger
   verify() confirms end-to-end continuity.

This is the wiring pattern a production host application follows to
make every consequential decision substrate-aware.

Run with::

    python 06_full_governor_loop.py
"""
from __future__ import annotations

from substrate import (
    AlignmentRefresher,
    DefaultNetPotentialGainGate,
    EntityRef,
    InMemorySubstrateMetadataStore,
    NetPotentialGainVerdict,
    classify as classify_band,
)
from substrate.audit.substrate_trace import SubstrateTraceLedger


def main() -> None:
    # ──────────────────────────────────────────────────────────────────
    # Setup: shared store, refresher, gate, ledger.
    # ──────────────────────────────────────────────────────────────────
    store = InMemorySubstrateMetadataStore()
    refresher = AlignmentRefresher(store, classifier="trust_scorer_v1")
    gate = DefaultNetPotentialGainGate(metadata_store=store)
    ledger = SubstrateTraceLedger()

    actor = EntityRef("agent", "alice")
    bob = EntityRef("user", "bob")

    # Seed actor and bob at a neutral starting alignment.
    for ref in (actor, bob):
        refresher.refresh_component(ref=ref, component="trust", value=0.5)
        refresher.refresh_component(ref=ref, component="expertise", value=0.5)
        refresher.refresh_component(ref=ref, component="capability", value=0.5)
        refresher.refresh_component(ref=ref, component="health", value=0.5)

    epoch = 1_700_000_000

    # ──────────────────────────────────────────────────────────────────
    # [1] An upstream trust scorer reports that Alice has earned more
    # trust. The refresher folds the update into Alice's stored vector.
    # ──────────────────────────────────────────────────────────────────
    refreshed = refresher.refresh_component(
        ref=actor, component="trust", value=0.85,
    )
    print(
        f"[1] refreshed alice.trust  =  {refreshed.alignment_vector.trust:.2f}  "
        f"net={refreshed.net_potential:.3f}  mode={refreshed.substrate_mode.value}"
    )

    # ──────────────────────────────────────────────────────────────────
    # [2] Alice proposes a "teach" action affecting Bob. The gate runs
    # with Alice's updated trust as one of the inputs.
    # ──────────────────────────────────────────────────────────────────
    evaluation = gate.evaluate(
        actor=actor,
        action_kind="teach",
        affected_entities=(bob,),
        proposed_outcome={},
    )
    print(
        f"[2] gate verdict           =  {evaluation.verdict.value}  "
        f"score={evaluation.score:+.3f}"
    )

    # ──────────────────────────────────────────────────────────────────
    # [3] The entity's imposed-resistance reading is 0.50, which is over the
    # resistance band, so the coarse three-state classifier returns STRESSED.
    # This is the RESISTANCE lens; a carried-work utilisation of 0.50 would be
    # the top of the sustainable work zone instead (classify_zone, layered).
    # ──────────────────────────────────────────────────────────────────
    resistance_reading = 0.50
    band_class = classify_band(resistance_reading)
    print(
        f"[3] resistance band (reading=0.50)=  {band_class.value}  "
        f"(coarse resistance lens; carried work uses the layered zones)"
    )

    # ──────────────────────────────────────────────────────────────────
    # [4] Append a substrate-trace record carrying the verdict and the
    # band classification together. Downstream auditors see both signals
    # in one record.
    # ──────────────────────────────────────────────────────────────────
    record = ledger.append(
        decision_id="teach-1",
        decision_kind="teach",
        permitted=evaluation.is_actionable and evaluation.verdict is not NetPotentialGainVerdict.NET_NEGATIVE,
        rationale=evaluation.reasoning,
        epoch_seconds=epoch,
        npg_verdict=evaluation.verdict,
        resistance_band=band_class,
    )
    print(
        f"[4] audit record           =  seq={record.sequence}  "
        f"permitted={record.permitted}  hash={record.record_hash[:12]}…"
    )

    # ──────────────────────────────────────────────────────────────────
    # [5] Verify the chain. With one record, this is trivial, but the
    # property holds for arbitrary chain lengths.
    # ──────────────────────────────────────────────────────────────────
    verification = ledger.verify()
    print(
        f"[5] ledger.verify()        =  ok={verification.ok}  "
        f"length={ledger.length}"
    )

    print()
    print(
        "This loop is the pattern a production host application repeats\n"
        "per consequential decision: refresh → gate → classify → ledger.\n"
        "The audit chain links every decision back to the inputs that\n"
        "produced it; any downstream auditor can re-derive and verify."
    )


if __name__ == "__main__":
    main()
