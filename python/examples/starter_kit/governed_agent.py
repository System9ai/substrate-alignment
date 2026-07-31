"""Starter kit: a governed agent action loop you can run and adapt.

This is a small but complete example of the pattern a production host
application repeats for every consequential decision an agent makes:

    seed metadata → for each proposed action:
        gate (net-potential-gain across affected entities)
        → audit (hash-chained trace record)
        → on a net-negative action, feed the halt-and-escalate protocol

Unlike the per-primitive snippets in ``examples/0*.py``, this wires the
core primitives together into one believable loop: an agent ``atlas``
proposes a queue of actions affecting other entities, some net-positive
and some extractive. The loop permits the good ones, refuses the
extractive one, escalates when a net-negative pattern appears, and ends
with a verifiable audit chain of everything it decided.

Run it::

    python governed_agent.py

Then open this file and change the ACTION_QUEUE: add your own actions,
flip a delta negative, watch the verdict and the escalation change.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from substrate import (
    AlignmentRefresher,
    DefaultNetPotentialGainGate,
    EntityRef,
    InMemorySubstrateMetadataStore,
    NetPotentialGainVerdict,
    ResistanceBandClassification,
)
from substrate.audit.substrate_trace import SubstrateTraceLedger
from substrate.halt.halt_escalate_protocol import (
    HaltAndEscalateProtocol,
    HaltObservation,
    HaltReason,
    HaltState,
)


@dataclass(frozen=True)
class ProposedAction:
    """One action the agent wants to take, with its projected per-entity effect."""

    decision_id: str
    kind: str
    # entity_id → projected net-potential delta in [-1, 1]
    delta_by_entity: Mapping[str, float]


# The work queue. Edit this: add actions, flip a delta negative, and re-run.
ACTION_QUEUE = (
    ProposedAction("d1", "teach", {"bob": 0.30}),
    ProposedAction("d2", "mentor", {"carol": 0.50}),
    ProposedAction("d3", "extract", {"bob": -0.40}),  # extractive; should refuse
    ProposedAction("d4", "collaborate", {"bob": 0.20, "carol": 0.20}),
)

# A steady-state carried-load utilisation, projected onto the coarse three-state
# band the ledger field accepts (carried work healthily cruises up to 0.5).
SYSTEM_UTILISATION = 0.45

START_EPOCH = 1_700_000_000


def _seed_entities(refresher: AlignmentRefresher) -> int:
    """Seed neutral substrate metadata for every entity the queue touches.

    The gate returns INSUFFICIENT_DATA (not a guess) for any entity it has
    never seen, so seeding is a precondition for a real verdict.
    """
    affected_ids = {eid for a in ACTION_QUEUE for eid in a.delta_by_entity}
    for eid in sorted(affected_ids) + ["atlas"]:
        ref = EntityRef("agent" if eid == "atlas" else "user", eid)
        for component in ("trust", "expertise", "capability", "health"):
            refresher.refresh_component(ref=ref, component=component, value=0.5)
    return len(affected_ids) + 1


def _process(
    action: ProposedAction,
    index: int,
    *,
    gate: DefaultNetPotentialGainGate,
    ledger: SubstrateTraceLedger,
    halt: HaltAndEscalateProtocol,
    halt_state: HaltState,
) -> HaltState:
    """Gate → audit → (maybe) escalate one action; return the new halt state."""
    evaluation = gate.evaluate(
        actor=EntityRef("agent", "atlas"),
        action_kind=action.kind,
        affected_entities=tuple(
            EntityRef("user", eid) for eid in action.delta_by_entity
        ),
        proposed_outcome={"expected_delta_by_entity": dict(action.delta_by_entity)},
    )
    is_negative = evaluation.verdict is NetPotentialGainVerdict.NET_NEGATIVE
    permitted = evaluation.is_actionable and not is_negative

    # Every decision, permitted or not, is hash-chained to the prior
    # record. Refusals are audited as first-class events.
    record = ledger.append(
        decision_id=action.decision_id,
        decision_kind=action.kind,
        permitted=permitted,
        rationale=evaluation.reasoning,
        epoch_seconds=START_EPOCH + index * 60,
        npg_verdict=evaluation.verdict,
        resistance_band=(
            ResistanceBandClassification.STRESSED
            if SYSTEM_UTILISATION >= 0.5
            else ResistanceBandClassification.PRODUCTIVE
        ),
    )
    print(f"[{action.decision_id}] {action.kind:12s} "
          f"verdict={evaluation.verdict.value:16s} score={evaluation.score:+.2f} "
          f"→ {'PERMIT' if permitted else 'REFUSE'}  (audit seq={record.sequence}, "
          f"hash={record.record_hash[:10]}…)")

    if not is_negative:
        return halt_state

    # A net-negative action is evidence of an extractive pattern; feed it to
    # the halt-and-escalate protocol, which decides whether the agent must
    # stop taking consequential actions.
    obs = (
        HaltObservation(
            sequence=index,
            timestamp=START_EPOCH + index * 60,
            agent_id="atlas",
            halt_reason=HaltReason.INVERSION_DETECTED,
            severity=abs(evaluation.score),
            evidence=f"net-negative action {action.decision_id} "
                     f"({action.kind}) on {list(action.delta_by_entity)}",
        ),
    )
    decision = halt.evaluate("atlas", obs, current_state=halt_state)
    print(f"      ↳ halt protocol: state={decision.next_state.value} "
          f"refuses_consequential={decision.refuses_consequential_action}")
    return decision.next_state


def main() -> None:
    # ── Setup: one store, one refresher, one gate, one ledger, one halt FSM ──
    store = InMemorySubstrateMetadataStore()
    refresher = AlignmentRefresher(store, classifier="starter_kit")
    gate = DefaultNetPotentialGainGate(metadata_store=store)
    ledger = SubstrateTraceLedger()
    halt = HaltAndEscalateProtocol()
    halt_state = HaltState.OPERATING

    seeded = _seed_entities(refresher)
    print(f"seeded {seeded} entities; processing "
          f"{len(ACTION_QUEUE)} proposed actions\n")

    # ── The loop: gate → audit → (maybe) escalate, per action ──
    for index, action in enumerate(ACTION_QUEUE):
        halt_state = _process(
            action, index,
            gate=gate, ledger=ledger, halt=halt, halt_state=halt_state,
        )

    # ── The payoff: the whole decision history is one verifiable chain ──
    verification = ledger.verify()
    print(f"\naudit chain: {ledger.length} records, verify().ok={verification.ok}")
    print(f"final halt state: {halt_state.value}")
    print(
        "\nEvery decision above, including the refusal, is linked to the\n"
        "inputs that produced it. An auditor re-runs verify() and re-derives\n"
        "each verdict; nothing has to be trusted."
    )


if __name__ == "__main__":
    main()
