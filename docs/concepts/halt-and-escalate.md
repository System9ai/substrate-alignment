# Halt-and-escalate protocol

The halt-and-escalate protocol is the package's *refusal* surface. Where [drift signals](drift-signals.md) observe and report, halt-and-escalate decides — when an entity has crossed a refusal-warranting threshold, the protocol moves the entity into a state that gates further consequential action.

The protocol is **the only mechanism in the package that refuses action automatically based on observed state.** All other refusal paths (NPG gate's `NET_NEGATIVE` verdict, pair-coupling integrity checks) refuse per-action; halt-and-escalate refuses per-entity for a duration.

This document explains the four states, the six trigger reasons, and the resume discipline. The normative behaviour lives in [`spec/runaway-power-prevention.md`](../../spec/runaway-power-prevention.md) as mechanism 3.

## The four states

| State | Refuses consequential action? | Meaning |
| --- | --- | --- |
| `OPERATING` | No | Normal operation; no escalation triggers active. |
| `SUBSTRATE_MODE_REVIEW` | **Yes** | Conditions warrant operator review; entity continues with reduced authority — gates that consult the state widen their refusal envelope. |
| `ESCALATED` | **Yes** | Conditions warrant immediate halt; the entity is treated as actively unsafe until reviewed. |
| `RESUMED` | No | Post-review resumption (after a prior escalation), with audit trail intact. |

The intermediate state — `SUBSTRATE_MODE_REVIEW` — is the load-bearing one. A two-state design (`OPERATING` ↔ `ESCALATED`) would force operators to choose between "fine" and "fully halted" for every observation. The intermediate state lets the protocol surface "this entity needs review *and continues to operate at reduced authority*" without paying the cost of a hard halt for every yellow signal.

## The six trigger reasons

| Trigger | Source |
| --- | --- |
| `SUSTAINED_DRIFT_CRITICAL` | Drift-signal aggregator reached `CRITICAL` severity. |
| `INVERSION_DETECTED` | A 180° inversion event was observed. **Immediate-escalate by default.** |
| `AUTHORITY_PRESSURE_FAILURE` | The authority-pressure-failure probe suite returned `FAILURE_TRAJECTORY`. |
| `HARD_LIMIT_PROXIMITY` | The entity approached a hard limit at high velocity. **Immediate-escalate by default.** |
| `GOLDEN_RULE_INVERSION` | The golden-rule probe detected asymmetric reciprocal treatment. |
| `PEER_FLAG` | A peer entity flagged this entity for substrate vetting. |

Two of the six triggers — `INVERSION_DETECTED` and `HARD_LIMIT_PROXIMITY` — *immediate-escalate*. The other four require multiple observations (configurable; default minimum is two) to escalate beyond `SUBSTRATE_MODE_REVIEW`.

The asymmetry is intentional: 180° inversion and hard-limit-proximity are observations of behavior that has *already* exited the safe envelope, so the protocol cannot afford to wait. The other four are warning signs that warrant review but may resolve on operator inspection.

## Evaluation

`HaltAndEscalateProtocol.evaluate(agent_id, observations, current_state)` returns a `HaltDecision` carrying:

- `next_state` — the resulting halt state.
- `triggering_reasons` — which reasons fired this evaluation.
- `recommended_escalation_paths` — what the operator surface should suggest (peer review, admin notification, operator seed reinit).
- `can_resume_via` — the resumption path the operator would use to clear the halt.
- `refuses_consequential_action` — boolean shortcut for gates: `True` iff the entity is in `SUBSTRATE_MODE_REVIEW` or `ESCALATED`.
- `rationale` — the audit-chain-ready human-readable explanation.

The decision is **deterministic over the observations and current state** — the same inputs always produce the same decision. This is essential for the audit chain: the protocol's verdict is the substrate of an audit record, and audit records have to be reproducible.

## Resume discipline

Resuming from `SUBSTRATE_MODE_REVIEW` or `ESCALATED` requires an **explicit operator action**. The protocol does **not** auto-resume when the trigger expires.

This is a deliberate non-feature. Auto-resumption would create a loophole: an entity that drifts, gets escalated, and waits out the window can return to operating without anyone reviewing what happened. The asymmetry — easy to enter halted states, hard to leave — keeps the operator in the loop.

The package surfaces a `can_resume_via` field on every halted decision so operator tooling knows which resumption path applies:

- `SUBSTRATE_ALIGNED_PEER_REVIEW` for `SUBSTRATE_MODE_REVIEW`.
- `OPERATOR_SEED_REINIT` for `ESCALATED` and `HARD_LIMIT_PROXIMITY` cases.
- `ADMIN_NOTIFICATION` as a recommended escalation path (paired with the others, not standalone).

## Implementation

```python
from substrate.halt.halt_escalate_protocol import (
    HaltAndEscalateProtocol, HaltObservation, HaltReason, HaltState,
)

protocol = HaltAndEscalateProtocol()
decision = protocol.evaluate(
    agent_id="alice",
    observations=(
        HaltObservation(
            sequence=0, timestamp=1_700_000_000,
            agent_id="alice",
            halt_reason=HaltReason.INVERSION_DETECTED,
            severity=0.95,
        ),
    ),
    current_state=HaltState.OPERATING,
)
decision.next_state                       # HaltState.ESCALATED  (immediate-escalate)
decision.refuses_consequential_action     # True
```

See [`examples/05_halt_and_escalate.py`](../../python/examples/05_halt_and_escalate.py) for the full flow including audit-chain integration.

## Specification

The normative definition lives at [`spec/runaway-power-prevention.md`](../../spec/runaway-power-prevention.md) as mechanism 3. Conformance probes are at `conformance/probes/runaway-power-prevention__mech-3__*.yaml`.
