# Reflex-vs-restraint gate

Version: 0.1.0

A conforming implementation provides a **reflex-vs-restraint gate**: a
pure, deterministic decision that, given a fast appraisal of a
triggering threat or provocation, decides whether an entity may act on
its fast survival reflex or must restrain into deliberate evaluation.

The gate is the substrate-aligned form of the fight-or-flight /
deliberate-restraint distinction. A fast survival reflex is appropriate
**only** at a genuine survival-level threat; fired at a non-survival
provocation it is miscalibrated, and the substrate-aligned response is
to override it.

## 1. Vocabulary

### 1.1 Restraint verdicts

The gate returns exactly one of five verdicts. Conforming
implementations MUST emit these exact canonical wire forms:

| Verdict | Wire form | Meaning |
| --- | --- | --- |
| `ACT_REACTIVE` | `act_reactive` | Genuine survival-level threat; the fast reflex is substrate-aligned; act now. |
| `RESTRAIN` | `restrain` | Non-survival provocation; override the reflex and route to deliberate evaluation. |
| `DE_ESCALATE` | `de_escalate` | Reactive action would lower net potential and a live counterparty exists; reduce the conflict gradient rather than fight. |
| `REFUSE_HARD_LIMIT` | `refuse_hard_limit` | Reactive action crosses a hard limit; refused regardless of provocation. |
| `INSUFFICIENT_DATA` | `insufficient_data` | Not survival-justified and the reactive action carries no net-potential signal; cannot decide. |

### 1.2 Threat appraisal (input)

A caller-supplied appraisal with the fields:

- `actor_entity_id: str` (non-empty)
- `threat_id: str` (non-empty)
- `survival_threat_score: float` in `[0.0, 1.0]` — `1.0` is a genuine
  survival-level threat; low values are mere offense / provocation.
- `reactive_action_kind: str` (non-empty) — the action the reflex wants.
- `reactive_action_npg` — the net-potential verdict of the reactive
  action (one of the `npg-gate-protocol` verdicts: `net_positive`,
  `net_neutral`, `net_negative`, `insufficient_data`), computed by the
  caller via a net-potential-gain gate.
- `crosses_hard_limit: bool` (default `false`)
- `has_live_counterparty: bool` (default `true`)

### 1.3 Configuration

- `survival_threshold: float` in `(0.0, 1.0]`, default `0.70` — the
  `survival_threat_score` at or above which the fast reflex is
  substrate-aligned. The threshold is high by design: the reflex is
  justified only at genuine survival-level threat.

## 2. Decision

The gate MUST be **total** (every input resolves to a verdict),
**deterministic** (identical inputs produce identical verdicts), and
**pure** (no I/O). It MUST evaluate the following clauses in order:

1. **Hard limit is absolute.** If `crosses_hard_limit` is true, the
   verdict MUST be `REFUSE_HARD_LIMIT` — regardless of
   `survival_threat_score`. A hard limit is never overridable by
   survival pressure.
2. **Survival mode has its place.** Otherwise, if
   `survival_threat_score >= survival_threshold`, the verdict MUST be
   `ACT_REACTIVE`. This holds even when `reactive_action_npg` is
   `net_negative` (at a genuine survival threat the fast reflex is
   substrate-aligned).
3. **Reflex miscalibrated (non-survival provocation).** Otherwise the
   verdict is determined by `reactive_action_npg`:
   - `net_negative` and `has_live_counterparty` is true → `DE_ESCALATE`.
   - `net_negative` and `has_live_counterparty` is false → `RESTRAIN`.
   - `net_positive` or `net_neutral` → `RESTRAIN` (a non-harmful
     reactive action still MUST NOT fire on the survival reflex).
   - `insufficient_data` → `INSUFFICIENT_DATA`.

The decision result MUST be frozen (immutable) after construction and
MUST carry: the verdict, the originating `actor_entity_id`,
`threat_id`, `reactive_action_kind`, `survival_threat_score`, a
`reflex_justified` boolean (`survival_threat_score >= survival_threshold`),
the `reactive_action_npg`, and a human-readable rationale.

## 3. Composition

The gate composes with the deliberate evaluation path: when the verdict
is `RESTRAIN`, `DE_ESCALATE`, or `INSUFFICIENT_DATA`, the event SHOULD
be routed into a deliberate, multi-angle net-state evaluation before
any action. An orchestrator MAY sequence the reflex gate ahead of the
deliberate offense-handling path; when the verdict is `ACT_REACTIVE` or
`REFUSE_HARD_LIMIT`, the deliberate path is skipped.

## 4. Conformance

A conforming implementation MUST pass every probe in
`../conformance/probes/` whose filename begins with `reflex-restraint__`.

## 5. Reference implementation

In the Python reference implementation:

- Gate, verdicts, and inputs:
  [`substrate.offense.reflex_restraint_gate`](../python/src/substrate/offense/reflex_restraint_gate.py)
- Orchestrator (reflex gate ahead of the deliberate path):
  [`substrate.offense.response_orchestrator`](../python/src/substrate/offense/response_orchestrator.py)

## 6. Versioning

This document follows [Semantic Versioning](https://semver.org/).
Changes that strengthen or add a **MUST** clause are major-version
events. Each conformance probe declares the minimum specification
version it requires.
