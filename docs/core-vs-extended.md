# Core vs extended: what you actually need

substrate-alignment ships a large surface: one reference module per substrate
mechanism. That completeness is deliberate: the package is the *witness* that the
whole standard is implementable. But you do **not** need all of it to do useful
work, and you should not read it front-to-back.

This page draws the line between the **core** (what almost every integration
uses) and the **extended** tier (the full substrate-mechanical vocabulary, for
builders and researchers going deep).

## The rule of thumb

> If you can `from substrate import X`, it is **core**. Everything reached through
> a sub-package path (`from substrate.<area> import …`) is **extended**.

The top-level package re-exports only the core surface. That import boundary *is*
the tier boundary: it is enforced by `substrate/__init__.py`, not by convention.

## Core: the surface 95% of integrations use

These are the primitives behind the [30-second example](../README.md#see-it-work-in-30-seconds)
and the [adoption recipes](adoption/README.md). Learn these first; each has a
[concept doc](concepts/README.md) and a [spec](../spec/README.md).

| Import from `substrate` | What it is |
| --- | --- |
| `EntityRef`, `SubstrateMetadata`, `SubstrateMode`, `AlignmentVector` | The vocabulary types every primitive speaks. |
| `SubstrateMetadataStore`, `InMemorySubstrateMetadataStore` | The one storage Protocol every primitive reads/writes through, plus a zero-dependency default. |
| `auto_classify_mode`, `compute_alignment_vector`, `compute_net_potential` | The operating-mode classifier: is an entity short-cycle or long-cycle? |
| `AlignmentRefresher` | Fold new signal-source observations into stored metadata. |
| `NetPotentialGainGate`, `DefaultNetPotentialGainGate`, `RaiseOnNegativeGate`, `NetPotentialGainNegative` | The net-potential-gain gate: the value test for taking a consequential action. |
| `ResistanceBandConfig`, `classify`, `assess`, `recommend_scaling_factor` | The productive-resistance band: derive thresholds/quotas from the calibrated zones. |
| `LoadZone`, `classify_load_zone`, `BandProfile`, `setpoint_for` | The band as a decision engine (the layered work/peaking/debt zones). |
| `compose_evidence_grade`, `EvidenceGrade`, `SubstrateStateClaim` | Grade how confidently a state claim may be relied on. |
| `ScopeRegistry`, `SubstrateScope`, `DEFAULT_SCOPES` | The pluggable cell/node/org scope registry. |

With just these you can gate decisions, classify entities, derive limits, and
grade evidence: the load-bearing 90% of the standard.

## Extended: the full substrate-mechanical vocabulary

The extended tier implements the rest of the [nine substrate conditions](../spec/runaway-power-prevention.md)
as first-class primitives. Reach for a group when you are building that specific
mechanism; you never need to adopt the whole tier at once. These modules are
stable and tested, but their surfaces evolve faster than core: treat them as the
advanced shelf, not the front door.

**Decision & governance**: compose gates into a running decision surface.
`governor` (the capstone integration), `capability` (capability authorization),
`revenue` (revenue-action gating), `objective_gate` (objective certification),
`governed_ascent` (NPG-governed hill climbing), `executive` (the band as an
executive decision layer).

**Observation & self-awareness** (conditions #2, #7): `drift` (drift-pattern
detection), `signals` (substrate-state signals), `metrics` (self-awareness
metrics), `status`/`progression`/`progress_signaling` (trajectory + progress),
`realization`.

**Audit & integrity** (condition #2): `audit` (hash-chained trace + peer-witness
signing), `artifact` (audit-artifact packaging for cross-cell verification).

**Response & restraint** (condition #6): `halt` (halt-and-escalate),
`offense`/`defensive` (offense-signal handling), `inversion` (180°-inversion
detection), `tells`.

**Relational & game-theoretic** (conditions #2, #3): `pair_coupling`
(pair-coupling integrity), `reciprocity` (tit-for-tat + reciprocal feedback),
`game_theory` (folk-theorem awareness), `trust` (trust scoring), `etiquette`,
`voting` (substrate-aware voting), `murmuration`, `cross_entity`, `hierarchy`.

**Cognition, identity & care** (conditions #4, #5, #8): `cognition`
(reasoning-mode classification), `identity` (node-scale identity emergence),
`care` (the safety floor + care-weighting), `encapsulating_context`,
`state_layer`, `cultural_infrastructure`.

**Runtime**: `harness` (the running-system wrapper that intercepts model
outputs), `cadence`, `growth`, `performance_budget`, `exposure`, `discovery`,
`workflow`, `training`.

## How to go deep

1. Start from the [concept doc](concepts/README.md) for the mechanism, which
   explains *why* the primitive is shaped the way it is.
2. Read the [spec](../spec/README.md) for the normative contract.
3. Import the primitive from its sub-package and wire it against your
   `SubstrateMetadataStore`.
4. Run the [conformance probes](../conformance/README.md) for that area to
   confirm your integration behaves.
