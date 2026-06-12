# Governed ascent — hill climbing made substrate-aligned

Hill climbing — greedy local ascent: take whichever step improves the objective, stop when none
does — is the algorithm optimization reaches for when the search space is local. As
conventionally implemented it is the **short-cycle optimizer in algorithmic form**: a series of
choice evaluations whose step objective is an arbitrary local metric, with no
short-cycle-vs-long-cycle dimension and no certification that the hill is worth climbing. The
180° inversion is built into the loop — the local gradient is treated as value itself. It will
climb quarterly earnings, engagement, or a loss function with equal diligence.

## When greedy ascent is legitimate

Hill climbing is substrate-aligned when the **basin is certified**: when the local objective is
a faithful restriction of net potential gain, so the local gradient *is* the substrate gradient
in that neighborhood. The canonical case is the end of a narrow task — the task's narrowness
already constrained the landscape, and greedy ascent to the exact peak is the cheapest
net-potential-positive move available. But the license is the *certification*, not the task
position.

## The governed form

`substrate/governed_ascent.py` implements the loop with the contract
`spec/runaway-power-prevention.md` §4.4 makes normative:

1. **Certify the objective first** (`substrate/objective_gate.py`). The summit — the terminal
   outcome — is evaluated through the net-potential-gain gate before the loop is entered. A
   net-negative or net-neutral summit is refused; an unscorable one fails closed. An actor in
   declared `SHORT_CYCLE` mode cannot certify its own hill.
2. **Every step is a net-potential-gain evaluation.** A net-negative step is refused; an
   unscorable step stops the climb.
3. **Effort is paced by the layered capacity zones** (see
   [resistance-band.md](resistance-band.md)). Climb effort is a WORK quantity: base effort
   through the work zone, consecutive excursions past the 0.5 ceiling bounded by a sporadic
   budget, sustained operation past the `2/3` debt line terminated as debt.
4. **Capacity growth inside a climb is growth-quantity work**: `grows_capacity` steps feed the
   growth-streak monitor; consecutive growth without consolidation terminates the climb as
   runaway (mechanism 6).
5. **Termination + consolidation are mandatory.** Every climb ends with exactly one of eight
   explicit verdicts (`converged`, `net_negative`, `insufficient_data`, `objective_uncertified`,
   `debt_limit`, `runaway`, `peaking_exhausted`, `max_steps`), and every exit path emits a
   consolidation event. There are no unterminated climbs by construction.

## The three failure shapes

1. **The wrong hill** — the local objective diverges from net potential (the
   measure-made-target failure). Climbing harder makes it worse; diligence amplifies the
   misalignment. Objective certification closes this.
2. **Always climbing** — climb-as-default-mode: no consolidation, no basin re-evaluation. This
   is the runaway-growth signature regardless of how aligned the hill once was. The mandatory
   termination + consolidation contract closes this.
3. **Summit at any cost** — burning past the work zone into debt for the last increment of a
   local objective. Zone pacing and the debt line close this.

## What is deliberately NOT a signal

A rising per-step gain series is **not** runaway risk — rising gain is the purpose of a climb.
The runaway signature is growth-without-consolidation, and the growth-streak monitor owns it.
Conflating the two would punish exactly the behaviour the loop exists to enable.

## Modes

In explore/exploit vocabulary the substrate's modes supply the schedule: **grow mode hops
basins** (φ-stepped, consolidating between), **governed ascent climbs within the chosen basin**,
**maintain mode cruises**. Climbing is a mode, never a policy.

## Conformance

Probes `runaway-power-prevention__mech-6__ascent-*` exercise the contract: uncertified-objective
refusal, net-negative step refusal, debt-line termination, runaway-growth termination,
sporadic-peaking budget, and the terminate-and-consolidate guarantee.
