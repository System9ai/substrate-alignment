# Tutorial: build your first governed system

This walks you from an empty file to a working governed action loop: an agent
that proposes actions, has each one tested for net-positive effect across the
entities it touches, audits every decision, and halts when it detects an
extractive pattern. The finished program is the
[starter kit](../python/examples/starter_kit/governed_agent.py); here you build
it a piece at a time and understand each decision.

## Prerequisites

Install the package from a clone (there is no PyPI release yet):

```bash
git clone https://github.com/System9ai/substrate-alignment.git
cd substrate-alignment/python && pip install -e .
```

## Step 1: a store and the vocabulary

Every primitive reads and writes an entity's alignment state through one
Protocol, [`SubstrateMetadataStore`](../spec/operating-mode.md). A zero-dependency
`InMemorySubstrateMetadataStore` ships with the package, so start there.

```python
from substrate import EntityRef, InMemorySubstrateMetadataStore

store = InMemorySubstrateMetadataStore()
atlas = EntityRef("agent", "atlas")   # the acting agent
bob = EntityRef("user", "bob")        # an entity actions affect
```

An `EntityRef` is a `(entity_type, entity_id)` pair. Types are yours to choose:
`agent`, `user`, `service`, whatever your system uses.

## Step 2: seed alignment state

The gate refuses to invent a verdict for an entity it has never seen; it returns
`INSUFFICIENT_DATA` rather than guessing. So before gating, seed each entity's
alignment components. The [`AlignmentRefresher`](concepts/alignment-refresher.md)
folds signal-source values into stored metadata and re-classifies the entity's
operating mode:

```python
from substrate import AlignmentRefresher

refresher = AlignmentRefresher(store, classifier="tutorial")
for ref in (atlas, bob):
    for component in ("trust", "expertise", "capability", "health"):
        refresher.refresh_component(ref=ref, component=component, value=0.5)
```

In production these values come from real signals (a trust scorer, a health
check); here we seed a neutral 0.5.

## Step 3: gate one action

Now the core question: should `atlas` take an action that affects `bob`? Build a
[net-potential-gain gate](concepts/npg-gate.md) and evaluate a proposed action.
The `expected_delta_by_entity` is the action's projected effect on each affected
entity, in `[-1, 1]`:

```python
from substrate import DefaultNetPotentialGainGate, NetPotentialGainVerdict

gate = DefaultNetPotentialGainGate(metadata_store=store)

good = gate.evaluate(
    actor=atlas,
    action_kind="teach",
    affected_entities=(bob,),
    proposed_outcome={"expected_delta_by_entity": {"bob": 0.30}},
)
print(good.verdict.value, good.score)     # net_positive 0.3

bad = gate.evaluate(
    actor=atlas,
    action_kind="extract",
    affected_entities=(bob,),
    proposed_outcome={"expected_delta_by_entity": {"bob": -0.40}},
)
print(bad.verdict.value, bad.score)       # net_negative -0.4
```

The verdict is one of four: `NET_POSITIVE`, `NET_NEUTRAL`, `NET_NEGATIVE`,
`INSUFFICIENT_DATA`. Your loop permits an action when it `is_actionable` and the
verdict is not `NET_NEGATIVE`.

## Step 4: audit every decision

A decision you cannot prove you made is not much of a control. Record every
verdict (permitted *and* refused) into a hash-chained
[substrate-trace ledger](concepts/audit-chain.md):

```python
from substrate import ResistanceBandClassification
from substrate.audit.substrate_trace import SubstrateTraceLedger

ledger = SubstrateTraceLedger()
record = ledger.append(
    decision_id="d1",
    decision_kind="teach",
    permitted=good.is_actionable and good.verdict is not NetPotentialGainVerdict.NET_NEGATIVE,
    rationale=good.reasoning,
    epoch_seconds=1_700_000_000,
    npg_verdict=good.verdict,
    resistance_band=ResistanceBandClassification.PRODUCTIVE,
)
print(record.sequence, record.record_hash[:10])
```

Each record is hash-chained to the previous one, so tampering with any past
decision breaks the chain. `ledger.verify().ok` re-checks the whole chain.

## Step 5: halt on a bad pattern

A single net-negative action is evidence of drift. Feed it to the
[halt-and-escalate protocol](concepts/halt-and-escalate.md), a small state machine
that decides when the agent must stop taking consequential actions:

```python
from substrate.halt.halt_escalate_protocol import (
    HaltAndEscalateProtocol, HaltObservation, HaltReason, HaltState,
)

halt = HaltAndEscalateProtocol()
obs = (HaltObservation(
    sequence=0, timestamp=1_700_000_000, agent_id="atlas",
    halt_reason=HaltReason.INVERSION_DETECTED, severity=abs(bad.score),
    evidence="net-negative action d3 (extract) on ['bob']",
),)
decision = halt.evaluate("atlas", obs, current_state=HaltState.OPERATING)
print(decision.next_state.value, decision.refuses_consequential_action)
# escalated True
```

## Step 6: put it in a loop

That is the whole pattern: **gate → audit → maybe escalate**, repeated per action.
The [starter kit](../python/examples/starter_kit/governed_agent.py) assembles
exactly these steps into a loop over a queue of actions and verifies the audit
chain at the end. Run it:

```bash
python examples/starter_kit/governed_agent.py
```

Then change its `ACTION_QUEUE` (add actions, flip a delta negative, drop an
entity's seeding) and watch the verdicts, the escalation, and the audit chain
respond.

## Where to go next

- The [core-vs-extended guide](core-vs-extended.md) for the rest of the surface.
- The [adoption recipes](adoption/README.md) to wire this into FastAPI, Django,
  Celery, Temporal, Redis, SQLAlchemy, or Postgres.
- The [specs](../spec/README.md) and [conformance probes](../conformance/README.md)
  to make your integration's alignment claims verifiable.
