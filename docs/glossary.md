# Glossary

The vocabulary substrate-alignment uses, in one place. Terms are defined as the
[specifications](../spec/README.md) and [concept docs](concepts/README.md) use
them; follow the links for the full treatment.

### Substrate

The running system as a whole: the humans, services, and agents interacting, plus
the mechanisms that govern them. "Substrate-aligned" behaviour is a property of the
*running system*, not of any single model or component in it.

### Entity

Anything that can act or be affected: a user, an agent, a service, a node, an org.
Referenced by an [`EntityRef`](../spec/operating-mode.md), a `(entity_type,
entity_id)` pair. An entity holds cryptographic identity; a workspace or context
does not.

### Substrate metadata

The persisted alignment state for one entity: its operating mode, alignment
vector, net potential, and provenance. Stored behind the
[`SubstrateMetadataStore` Protocol](../spec/operating-mode.md).

### Operating mode (substrate mode)

The four-valued classification of an entity's behaviour:
`LONG_CYCLE` (substrate-aligned, invests across horizons), `SHORT_CYCLE`
(reactive, optimises the immediate), `MIXED`, and `UNKNOWN`. Produced by the
[operating-mode classifier](concepts/operating-mode.md).

### Net potential gain (NPG)

The load-bearing test of value: *value = net potential gain, across the system the
actor is embedded in*, not the actor's private gain. The
[NPG gate](concepts/npg-gate.md) evaluates a proposed action and returns one of
four verdicts: `NET_POSITIVE`, `NET_NEUTRAL`, `NET_NEGATIVE`, `INSUFFICIENT_DATA`.

### 180° inversion

Treating a local proxy for value (a gradient, a metric, revenue) *as* value
itself. A short-cycle optimiser inverts long-cycle intent when it optimises the
proxy while claiming the goal. Detected by the `inversion` primitives.

### Resistance band

The [productive-resistance model](concepts/resistance-band.md). Imposed
*resistance* calibrates at roughly `1/3`–`0.38`; carried *work/utilization*
cruises a higher zone; *growth* steps by φ. Damage comes from **sustained** load
past `2/3`, not transient peaks. Thresholds, quotas, and rate limits are derived
from the band rather than picked ad hoc.

### φ (phi) and φ-conjugate

The golden ratio (`φ ≈ 1.618`) and its conjugate (`1/φ ≈ 0.618`). They anchor the
growth-step discipline (a healthy growth step is ≈ φ) and the peaking/warning boundary (the floor of the warning band; also the failover-spike ceiling).
The derivations live in the [resistance-band concept doc](concepts/resistance-band.md);
they are pinned by tests, not tunable.

### Governed quantities

Three distinct things the model governs, each with its own zone (conflating them
is a bug): imposed **resistance** (calibrates `1/3`–`0.38`), carried
**work/utilization** (cruises `0.38`–`0.5`, with a transient peak band above), and
**growth** (φ-stepped). Applying the resistance ceiling to a work quantity is
itself an inversion.

### Alignment vector / alignment weights

The component measurements (and their weights) that aggregate into an entity's net
potential. Refreshed into stored metadata by the
[`AlignmentRefresher`](concepts/alignment-refresher.md).

### Drift signal

One of the [characteristic patterns](concepts/drift-signals.md) by which
substrate-aligned (long-cycle) operation collapses to a reactive default. The
`drift` primitives match observed behaviour against the pattern set.

### Halt-and-escalate

The [response protocol](concepts/halt-and-escalate.md) a primitive uses when it
must stop rather than proceed: the only automatic per-entity refusal surface, with
explicit states, trigger reasons, and a resume discipline.

### Pair coupling

The [integrity model](concepts/pair-coupling.md) for a relationship between two
entities: a lifecycle state machine plus extraction monitoring, so one party
cannot quietly extract from the other.

### Audit chain / substrate trace

The [hash-chained ledger](concepts/audit-chain.md) of observations, with
peer-witness signing. Tamper-evident and **symmetric**: every entity both
observes and is observed; write-only audit is a weakness, not the goal.

### Evidence grade

An ordinal for *how confidently a state claim may be relied on*: a single
anonymous heuristic and three cryptographically signed peer attestations should not
look alike. Composed by `compose_evidence_grade` over a `SubstrateStateClaim`.

### Scope (cell / node / org)

The [multi-scale](../spec/multi-scale.md) alignment architecture: `cell` (physical,
replicable instance), `node` (logical, persistent, crypto-identified aggregate of
cells), `org` (multi-node aggregate). The `ScopeRegistry` is pluggable; operators
add `household`, `squad`, etc.

### Conformance probe

A machine-checkable behavioural test in YAML that any implementation runs to
[demonstrate conformance](../conformance/README.md) to a spec clause. The probes,
not the code, are the verification surface.

### Federal-procurement test

The discipline that keeps the *source code* in engineering vocabulary only: no
internal-document references, plan numbers, subsystem codenames, or cosmology. The
reasoning lives in `docs/` and `spec/`; a CI guard enforces the boundary. This is
what lets the source survive procurement and audit review.
