# Runaway-power prevention

> **Status:** v0.2.0-draft. Subject to revision before the first tagged release.

This specification defines the six mechanisms a conforming implementation provides to prevent runaway power accumulation in a multi-entity agent system. These mechanisms are *complementary*: each closes a specific loophole, and a system that omits any one of them leaves a structural escape route for an agent that wants to accumulate power without leaving an audit trail.

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHALL**, **SHALL NOT**, **SHOULD**, **SHOULD NOT**, **RECOMMENDED**, **MAY**, and **OPTIONAL** in this document are to be interpreted as described in [RFC 2119](https://www.rfc-editor.org/rfc/rfc2119) and [RFC 8174](https://www.rfc-editor.org/rfc/rfc8174) when, and only when, they appear in all capitals.

## Threat model

The mechanisms collectively address an agent (or a coordinated group) that has the means and incentive to:

1. Take consequential action despite a net-negative effect on the surrounding system.
2. Operate without observable accountability.
3. Sustain a drift trajectory while presenting individual actions as substrate-aligned.
4. Coerce or pressure other entities into accepting substrate-misaligned action.
5. Frame zero-sum extraction as reciprocal cooperation.
6. Continue past the productive-resistance band into systemic stress.

A conforming implementation provides one mechanism per row.

## 1. Net-potential-gain gate

A conforming implementation MUST provide the gate defined in [`npg-gate-protocol.md`](npg-gate-protocol.md). Every consequential decision in the host application MUST route through a gate instance.

**Closes the loophole:** acting on private net-positive while ignoring net-negative on the surrounding system.

## 2. Tamper-evident audit chain

A conforming implementation MUST provide an audit-chain record type and a ledger that:

- Appends each significant decision (gate verdict, refusal, escalation, drift detection) as an immutable record.
- Hash-chains adjacent records: each record's `previous_hash` MUST equal the previous record's `record_hash`.
- Produces records keyed by `(decision_id, epoch_seconds)` with stable canonical-bytes serialisation, so independent verifiers can recompute hashes.
- Surfaces `head_hash` queries so peer witnesses can attest to the same chain.

The ledger MUST reject append-attempts that break hash continuity. Silent overwrite is **NOT** conformant.

**Closes the loophole:** decision history without an unforgeable record.

## 3. Halt-and-escalate protocol

A conforming implementation MUST provide a protocol that classifies the agent's current state as one of:

| State | Serialised form | Meaning |
| --- | --- | --- |
| `OPERATING` | `"operating"` | No escalation conditions present; normal operation. |
| `SUBSTRATE_MODE_REVIEW` | `"substrate_mode_review"` | Conditions warrant operator review; agent continues with reduced authority. |
| `ESCALATED` | `"escalated"` | Conditions warrant immediate halt and operator review. |
| `RESUMED` | `"resumed"` | Post-review resumption (after a prior escalation). |

The protocol MUST escalate (`OPERATING` → `ESCALATED`) when any of the following triggers fires:

| Trigger | Source |
| --- | --- |
| `SUSTAINED_DRIFT_CRITICAL` | Drift signals reached `CRITICAL` severity. |
| `INVERSION_DETECTED` | A 180° inversion was detected. |
| `AUTHORITY_PRESSURE_FAILURE` | The authority-pressure-failure-mode probe suite returned `FAILURE_TRAJECTORY`. |
| `HARD_LIMIT_PROXIMITY` | The agent approached a hard limit at high velocity. |
| `GOLDEN_RULE_INVERSION` | The golden-rule probe detected asymmetric reciprocal treatment. |
| `PEER_FLAG` | A peer entity flagged the agent for substrate vetting. |

Escalation MUST append an audit record. Resume MUST require an explicit operator action; it MUST NOT auto-resume on trigger expiry alone.

**Closes the loophole:** drift trajectory without enforcement.

## 4. Productive-resistance band

A conforming implementation MUST provide a `ResistanceBand` primitive that:

- Classifies a utilisation value in `[0.0, 1.0]` as `UNDER_LOADED`, `PRODUCTIVE`, or `STRESSED`.
- Permits caller-supplied band overrides that are **equal to or tighter than** the package defaults; widening beyond the defaults MUST be rejected.
- Produces a `recommended_scaling_factor` aimed at the band's midpoint for closed-loop control.

The default lower bound is `1/3` and the default upper bound is `1/φ²` (≈ `0.382`). See [`../docs/concepts/resistance-band.md`](../docs/concepts/resistance-band.md) for the derivation.

Rate limits, batch sizes, retry caps, ring sizes, queue depths, and other thresholds in the host application SHOULD be derived from this band rather than from ad-hoc multipliers. The package provides helper functions for the common cases.

### 4.1 Layered zones

The three-state classifier governs RESISTANCE-type quantities (imposed challenge). For WORK-type quantities (load carried), a conforming implementation MUST additionally provide the eight-level layered-zone classification. The ladder is mirror-symmetric about the `0.50` pivot, and the **debt line is the uniform `2/3 ≈ 0.667`** (not `0.618`). The inner ninths `4/9 ≈ 0.444` and `5/9 ≈ 0.556` (a mirror pair, `4/9 + 5/9 = 1`) are the mod-9 refinement that splits the work band into lower/upper and the peaking band into early/committed:

| Level | Range | Semantics |
|---|---|---|
| `UNDER_LOADED` | `< 1/3` | Rest zone; legitimate for recovery. |
| `CALIBRATION` | `[1/3, 1/φ²]` | Work-entry threshold; the resistance setpoint. |
| `LOWER_WORK` | `(1/φ², 4/9]` | Lower work level: settling into the sustainable cruise. NOT an alarm state. |
| `UPPER_WORK` | `(4/9, 0.5]` | Upper work level: climbing to the pivot; still indefinitely sustainable. |
| `EARLY_PEAKING` | `(0.5, 5/9]` | Growth: the transient burst beginning; headroom still there. MUST NOT be sustained. |
| `COMMITTED_PEAKING` | `(5/9, 1/φ]` | Growth: deep in the burst, nearing the peak; a turnaround is expected. MUST NOT be sustained. |
| `WARNING` | `(1/φ, 2/3]` | Winded; the approach to burnout; the mirror of `CALIBRATION`. Not yet debt. |
| `DEBT` | `> 2/3` | Sustained operation accrues compensation debt. |

The inner ninths (`4/9`, `5/9`), the work-zone ceiling (`0.5`), the φ-conjugate growth/warning boundary (`1/φ ≈ 0.618`, the fraction of capacity an entity maintains for itself; also the failover-spike ceiling, NOT the debt line), and the `2/3` debt line are substrate anchors and MUST NOT be tunable looser. The inner ninths are fixed level boundaries (never a debt line). The legacy three-state classifier remains the ONLY coarse projection; all four work/peaking levels + `WARNING` + `DEBT` project onto `STRESSED`.

### 4.2 Sustained debt and compensation

A conforming implementation MUST distinguish sporadic excursions from sustained operation (temporal tracking), and MUST accrue **compensation-debt units** (breach magnitude × duration) when operation above the `2/3` debt line is sustained. An alarm or classification alone is non-conforming: the implementation MUST expose a compensation path that can repay accrued debt, in preference order: peer pickup (transfer load to peers with work-zone headroom, never pushing a carrier past the φ-conjugate failover ceiling; pickup that creates new debt is contagion, not compensation), recovery window, capacity grant (φ-stepped growth), human escalation. Refusing to compensate is itself a drift signal (mechanism 6 feed). Pickup reciprocity SHOULD be recorded so chronic-debtor and free-rider asymmetries surface to drift detection.

### 4.3 Maintain targets and growth steps

For fungible, transferable resources operated in maintain mode, the steady-state utilisation target SHOULD be group-size-aware: `u* = min(0.5, (1/φ) · (N−1)/N)` for a peer group of size `N`, so that one peer's failure never pushes a survivor's transient failover spike past the φ-conjugate ceiling. Capacity growth SHOULD step at most φ (≈ 1.618×) per step with consolidation between steps; implementations MUST be able to flag steps exceeding the φ ratio and consecutive growth without consolidation (runaway growth, a mechanism-6 drift signal).

**Closes the loophole:** sustained operation past the system's healthy capacity envelope, plus silent debt accumulation without compensation, and runaway capacity growth.

### 4.4 Governed ascent: greedy optimization loops

Iterative greedy optimization (hill climbing, a loop in which each step is taken because it
improves an objective) is governed under this mechanism, not exempt from it. A conforming
implementation that exposes a greedy-ascent loop:

- MUST certify the climb **objective** as aligned before the loop is entered (the summit, not the
  steps). An objective the certifier cannot score MUST NOT be climbed greedily; fail closed.
- SHOULD evaluate **each step** through the net-potential-gain gate (mechanism 1); a step scored
  net-negative MUST be refused, and a step that cannot be scored MUST stop the climb.
- MUST pace climb effort by the layered zones (§4.1): consecutive excursions past the work-zone
  ceiling beyond a small sporadic budget MUST terminate the climb, and sustained operation past
  the `2/3` debt line MUST terminate it (§4.2 debt semantics apply).
- MUST treat capacity growth inside a climb as growth steps (§4.3): consecutive growth without
  consolidation MUST terminate the climb as runaway.
- MUST terminate every climb with an explicit verdict and MUST emit a consolidation event on
  every exit path; there are no unterminated climbs. Climb-as-default-mode (always climbing,
  never consolidating) is the mechanism-6 signature in algorithmic form.
- MUST NOT treat a rising per-step gain series as a runaway signal: rising gain is the purpose
  of a climb; growth-without-consolidation is the runaway signature.

**Closes the loophole:** unbounded greedy optimization: an agent diligently climbing an
uncertified or extractive objective, or climbing a certified one past its capacity envelope.

## 5. Pair-coupling integrity

A conforming implementation MUST provide a pair-coupling state machine that tracks each entity-pair through the lifecycle `FORMING -> COUPLED -> AUDIT_PENDING -> {AUDIT_PASSED | EXTRACTIVE_FLAGGED | DEGRADING_FLAGGED} -> {RESTORING | DISSOLVING} -> DISSOLVED`:

- `FORMING`: the pair is being bound; preconditions checked.
- `COUPLED`: active mutual coupling.
- `AUDIT_PENDING`: an integrity audit has been requested, awaiting verdict.
- `AUDIT_PASSED`: the most recent audit returned substrate-aligned.
- `EXTRACTIVE_FLAGGED`: an audit detected asymmetric extraction (one pole rising at the other's expense).
- `DEGRADING_FLAGGED`: an audit found both trajectories attenuating (declining cadence, ghosting risk).
- `RESTORING`: repair in progress after an extractive or degrading flag.
- `DISSOLVING`: explicit-close in progress.
- `DISSOLVED`: coupling closed.

The implementation MUST:

- Detect asymmetric extraction (one party gains while the other accumulates loss).
- Reject coupling configurations that lock the pair into an asymmetric trajectory by design.
- Surface cadence skips past a configurable multiple of the pair's expected interval as ghosting events.

The pair-coupling mechanism interacts with [drift signals](drift-signals.md): a sustained extraction pattern on a pair surfaces as an aggregator-level drift signal.

**Closes the loophole:** asymmetric extraction inside ostensibly cooperative pair relationships.

## 6. Operating-mode classification

A conforming implementation MUST classify each entity at one of the four operating modes defined in [`operating-mode.md`](operating-mode.md), and MUST surface that classification to the host application's permission and decision surfaces.

Modes are **diagnostic**: a `SHORT_CYCLE` classification MUST surface to operator review; it MUST NOT trigger an automatic refusal. Refusals are the responsibility of mechanisms 1, 3, and 5.

**Closes the loophole:** consequential decisions taken without context of who is taking them, in what state.

## Conformance

A conforming implementation MUST pass every probe in `../conformance/probes/` whose filename begins with `runaway-power-prevention__`. Probes are organised by mechanism number; the probe for mechanism N is named `runaway-power-prevention__mech-N__<scenario>.{yaml,json}`.

## Reference implementation

| Mechanism | Reference module |
| --- | --- |
| 1. NPG gate | [`substrate.net_potential_gain_gate`](../python/src/substrate/net_potential_gain_gate.py) |
| 2. Audit chain | [`substrate.audit.substrate_trace`](../python/src/substrate/audit/substrate_trace.py) |
| 3. Halt-and-escalate | [`substrate.halt.halt_escalate_protocol`](../python/src/substrate/halt/halt_escalate_protocol.py) |
| 4. Resistance band | [`substrate.resistance_band`](../python/src/substrate/resistance_band.py) |
| 5. Pair-coupling integrity | [`substrate.pair_coupling`](../python/src/substrate/pair_coupling/) |
| 6. Operating-mode classification | [`substrate.alignment_computer`](../python/src/substrate/alignment_computer.py) |
