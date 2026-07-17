# Pair-coupling integrity

A pair relationship between two entities is itself a substrate-alignment surface. The pair-coupling primitives in this package track each pair's lifecycle, detect asymmetric extraction, and refuse coupling configurations that are extractive-by-design.

This document explains the state machine and the three integrity gates layered on top of it. The normative behaviour lives in [`spec/runaway-power-prevention.md`](../../spec/runaway-power-prevention.md) as mechanism 5.

## The state machine

A pair moves through nine observable states (the canonical flow is `FORMING -> COUPLED -> AUDIT_PENDING -> {AUDIT_PASSED | EXTRACTIVE_FLAGGED | DEGRADING_FLAGGED} -> {RESTORING | DISSOLVING} -> DISSOLVED`):

| State | Meaning |
| --- | --- |
| `FORMING` | The pair is being bound; preconditions are being checked. |
| `COUPLED` | Active mutual coupling. |
| `AUDIT_PENDING` | An integrity audit has been requested and is awaiting its verdict. |
| `AUDIT_PASSED` | The most recent audit returned substrate-aligned; the pair operates with confidence. |
| `EXTRACTIVE_FLAGGED` | An audit detected asymmetric extraction (one pole rising at the other's expense). |
| `DEGRADING_FLAGGED` | An audit found both trajectories attenuating; cadence is declining, with ghosting risk if not repaired. |
| `RESTORING` | Repair in progress after an extractive or degrading flag. |
| `DISSOLVING` | Explicit-close in progress. |
| `DISSOLVED` | Terminal; the coupling is closed. |

Each transition is **typed** by a trigger:

| Trigger | Source |
| --- | --- |
| `BIND` | Both parties consent to coupling. |
| `AUDIT_REQUESTED` | Either party (or an operator) requests an integrity audit. |
| `AUDIT_VERDICT_ALIGNED` | The audit returned no extraction signal. |
| `AUDIT_VERDICT_EXTRACTIVE` | The audit detected asymmetric extraction. |
| `AUDIT_VERDICT_DEGRADING` | The audit detected attenuation. |
| `AUDIT_VERDICT_INSUFFICIENT_DATA` | The audit could not decide. |
| `REPAIR_INITIATED` | A party started repairing the relationship. |
| `REPAIR_SUCCEEDED` / `REPAIR_FAILED` | Repair outcome. |
| `DISSOLUTION_INITIATED` / `DISSOLUTION_COMPLETED` | Explicit close. |

Illegal transitions raise `IllegalStateTransition` at the state-machine layer. There is no "soft" or "implicit" transition: every state change is named, audited, and reproducible. An entity that tries to skip from `FORMING` straight to `AUDIT_PASSED` without passing through `COUPLED` cannot do so; the state machine refuses.

## Three integrity gates

The state machine pins down the *shape* of the pair's lifecycle. Three integrity gates layered on top of it pin down the *content*.

### Alignment audit

`substrate.pair_coupling.alignment_audit` evaluates a coupling's audit verdict from observed signals: are the parties' alignment vectors moving together (`ALIGNED`), apart (`DEGRADING`), or asymmetrically (`EXTRACTIVE`)? The audit returns one of the four `AUDIT_VERDICT_*` values that drive state transitions.

### Asymmetry preservation

`substrate.pair_coupling.asymmetry_preservation` and `substrate.pair_coupling.asymmetry_by_design_verifier` enforce a deeper property: **the package refuses coupling configurations that bake extraction into the design.**

A coupling configuration is "extractive by design" when one party structurally (under the coupling's stated rules, before either party does anything) has a path to gain that costs the other party. The asymmetry-by-design verifier rejects these configurations at bind time, not after the fact. An entity that wants to extract has to either succeed under symmetric terms (the audit chain captures the attempt) or refuse the coupling.

This is the strongest of the three gates: it stops extraction before it starts.

### Extraction monitor

`substrate.pair_coupling.extraction_monitor` watches active couplings for the *behavioural* asymmetry: even when the configuration was symmetric at bind time, can the running behaviour drift into extraction? The monitor surfaces the drift as a feed into the [drift-signal aggregator](drift-signals.md), where sustained extraction promotes to a critical drift severity and routes through the [halt-and-escalate protocol](halt-and-escalate.md).

## Trajectory-capacity tracker

A pair has a *trajectory-generation capacity*: how much future the coupling has, measured in committed-but-unrealised joint outcomes. The package's tracker (`substrate.pair_coupling.trajectory_capacity_tracker`) computes this from observed history: pairs with high trajectory capacity are worth investing in; pairs with low capacity are signalling that dissolution is appropriate.

The tracker is **diagnostic, not prescriptive**: it does not refuse anything, it just surfaces whether the coupling has trajectory remaining. Operators (and the entities themselves) use the signal to decide whether to invest in repair, accept the attenuation, or initiate dissolution.

## Why the explicit-close discipline matters

The most consequential property of the pair-coupling subsystem is what it does about *ghosting*: the failure mode where one party silently stops engaging. The state machine's `DISSOLVING` and `DISSOLVED` states require an explicit-close trigger (`DISSOLUTION_INITIATED` followed by `DISSOLUTION_COMPLETED`). A pair that just stops interacting *does not transition to DISSOLVED*; it remains `COUPLED` and attenuates, which the extraction monitor flags as substrate-misalignment.

The discipline is: **substrate-aligned coupling can end, but it cannot ghost.** Either maintain cadence, or close explicitly. The package's primitives are designed to make the explicit close the path of least resistance: silent attenuation creates more downstream friction than an honest close.

## Implementation

```python
from substrate.pair_coupling.state_machine import (
    PairCouplingState, PairCouplingStateMachine, PairCouplingTrigger,
)

transition = PairCouplingStateMachine.next_state(
    pair_id="alice-bob",
    current=PairCouplingState.FORMING,
    trigger=PairCouplingTrigger.BIND,
)
transition.to_state    # PairCouplingState.COUPLED
```

For end-to-end usage including the audit + asymmetry + extraction surfaces, see [`substrate.pair_coupling`](../../python/src/substrate/pair_coupling/).

## Specification

The normative definition lives at [`spec/runaway-power-prevention.md`](../../spec/runaway-power-prevention.md) as mechanism 5. Conformance probes are at `conformance/probes/runaway-power-prevention__mech-5__*.yaml`.
