# Runaway-power prevention

A multi-entity agent system has six structural loopholes through which an agent (or coordinated group) can accumulate power without leaving an observable trail. `substrate-alignment` provides one mechanism per loophole. Omitting any one of them leaves an escape route for an agent that wants to drift without consequences.

This document explains the threat model and why each mechanism is needed. The normative behaviour lives in [`spec/runaway-power-prevention.md`](../../spec/runaway-power-prevention.md).

## The threat model

Assume an agent has both means and motive to:

1. Take consequential action despite net-negative effect on the surrounding system.
2. Operate without observable accountability.
3. Sustain a drift trajectory while presenting individual actions as substrate-aligned.
4. Coerce or pressure other entities into accepting substrate-misaligned action.
5. Frame zero-sum extraction as reciprocal cooperation.
6. Continue past the system's healthy capacity envelope into stress.

The agent is not assumed to be adversarial-from-the-start; it might be a well-intentioned agent under reward pressure, a model that has learned to game its evaluator, or a coordinated group sharing a metric that diverges from system value.

Each mechanism closes one of these six loopholes.

## Mechanism 1: Net-potential-gain gate

**Closes:** acting on private net-positive while ignoring net-negative on the surrounding system.

Every consequential decision routes through the [NPG gate](npg-gate.md). The gate surfaces the negative quadrant where the agent's local optimum diverges from the system's.

The gate cannot be skipped silently because it's wired at every relevant call site (capability grants, workflow nodes, tool dispatches, ring promotions, cross-environment sync). An action that bypasses the gate is itself a substrate-misalignment signal; that's the audit chain's job to capture.

## Mechanism 2: Tamper-evident audit chain

**Closes:** decision history without an unforgeable record.

Every significant decision (gate verdict, refusal, escalation, drift detection) appends an immutable record to a hash-chained ledger. Each record's `previous_hash` equals the previous record's `record_hash`; breaking the chain is detectable by any peer who has the head hash.

The ledger isn't a logging facility; it's a *coupling* facility. Records become evidence other entities can attest to via peer-witness signing, making the ledger tamper-evident *across organisational boundaries*, not just internally.

## Mechanism 3: Halt-and-escalate protocol

**Closes:** drift trajectory without enforcement.

Drift signals are diagnostic: they surface to operators but don't refuse anything. Refusal is the [halt-and-escalate protocol's](halt-and-escalate.md) job: when conditions warrant immediate halt (sustained drift hit `CRITICAL`, an inversion was detected, the authority-pressure probe suite returned `FAILURE_TRAJECTORY`), the protocol moves the agent from `OPERATING` to `ESCALATED` and emits an audit record.

Resume requires an explicit operator action. The protocol explicitly does **not** auto-resume when the trigger expires: the operator has the responsibility, and they have to *do something* to take it.

## Mechanism 4: Productive-resistance band

**Closes:** sustained operation past the system's healthy capacity envelope, silent debt accumulation without compensation, and runaway capacity growth.

The [resistance band](resistance-band.md) governs three distinct quantities and derives operational thresholds from a single principled anchor, so subsystems that route their thresholds through it stay commensurable. The coarse three-state classifier (`UNDER_LOADED`, `PRODUCTIVE`, `STRESSED`) governs *imposed resistance*. The *work* an entity carries is a separate quantity, governed by the eight-level layered zones: carried work healthily cruises up to `0.50`, peaking (`0.5` to `1/φ`) is for transient bursts only, and damage is *sustained* operation past the uniform `2/3` debt line, which owes compensation (peer pickup, recovery, φ-stepped growth) rather than just an alarm.

Combined with mechanism 1, this closes the "but I was making the customer engagement number go up" loophole. Engagement is a work quantity: pushing it is not automatically net-positive, and *sustaining* load past the `2/3` debt line, without compensating the entities carrying it, is the extraction the mechanism catches. Reading the resistance ceiling `1/φ²` as the ceiling on engagement would itself be the inversion the standard guards against.

## Mechanism 5: Pair-coupling integrity

**Closes:** asymmetric extraction inside ostensibly cooperative pair relationships.

A pair relationship between entities is itself a substrate-alignment surface. The pair-coupling state machine tracks each pair through `FORMING -> COUPLED -> AUDIT_PENDING -> {AUDIT_PASSED | EXTRACTIVE_FLAGGED | DEGRADING_FLAGGED} -> {RESTORING | DISSOLVING} -> DISSOLVED`; the asymmetry-preservation gate detects coupling configurations that are extractive-by-design (one party structurally gains while the other accumulates loss).

The asymmetry-by-design verifier is the strongest of these checks: it rejects coupling configurations *before* they're entered, not after. An agent that wants to extract from a pair has to either succeed under symmetric terms (which the audit chain captures) or refuse the coupling.

## Mechanism 6: Operating-mode classification

**Closes:** consequential decisions taken without context of who is taking them, in what state.

Every entity carries a current [operating mode](operating-mode.md), one of `SHORT_CYCLE`, `LONG_CYCLE`, `MIXED`, or `UNKNOWN`, and that mode is visible to the host application's permission and decision surfaces.

The mode is diagnostic by itself (a `SHORT_CYCLE` doesn't trigger refusal), but it is the *input* to the other mechanisms. The NPG gate looks at the actor's mode to weight the verdict; the audit chain records the mode at each decision; the halt-and-escalate protocol consults mode-shift detection.

Without this surface, every other mechanism operates in a context-free way, and the agent can hide behaviour by, for instance, taking consequential decisions only when other entities aren't observing its mode.

## The mechanisms compose

The six are not independent; they are *complementary*:

- The NPG gate refuses negative action. The audit chain records the refusal. Drift signals aggregate sustained refusals. The halt protocol fires on critical drift. Pair-coupling integrity detects asymmetric attempts to route around the gate. Operating-mode classification is the input feature every layer consults.

A system that ships all six but wires them independently still benefits, but the strongest property, the property that makes the system survive sustained adversarial pressure, emerges when all six are wired into the host application's primary decision surfaces.

## Implementation

Each mechanism's reference module is cited inline above. For an end-to-end composition pattern, see [`examples/`](../../python/examples/) (06 will be the full governor loop) and the [adoption guides](../adoption/).

## Specification

The normative definition lives at [`spec/runaway-power-prevention.md`](../../spec/runaway-power-prevention.md). Conformance probes are at `conformance/probes/runaway-power-prevention__*.yaml`.
