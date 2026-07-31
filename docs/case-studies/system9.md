# Case study: System9

This is the reference production deployment of substrate-alignment. System9 is a multi-entity agent platform (humans, services, AI agents operating cooperatively across organisational boundaries), and substrate-alignment is the behavioural-layer discipline that makes the system's safety claims auditable.

The case study below describes the deployment pattern at a level that lets external teams replicate it; specific entity names and internal subsystem details are anonymised.

> **Status.** This case study reflects the production deployment as of the substrate-alignment v0.2.0 extraction. Subsequent revisions land alongside platform releases.

## Deployment shape

| Layer | What runs there |
| --- | --- |
| **Edge** | Per-host agent processes; carry local trust scoring + capability publication. |
| **Node** | Service-level coordinator; runs the NPG gate, alignment refresher, and the halt-and-escalate protocol against per-entity stored metadata. |
| **Org** | Cross-service audit chain; peer-witness signing across organisations. |

The package's primitives are stateless and pure-logic; the deployment supplies the persistent storage (Postgres at the node, replicated cross-org), the peer-witness key material (HSM-backed at the org), and the operator surfaces (the gate's `INSUFFICIENT_DATA` and the protocol's `SUBSTRATE_MODE_REVIEW` both surface in the operator console).

## What every consequential decision routes through

In the production deployment, *every* consequential decision (capability grant, workflow node execution, tool dispatch, cross-org canonical promotion, edge sync, ring promotion) passes through the wiring shown in [`examples/06_full_governor_loop.py`](../../python/examples/06_full_governor_loop.py):

1. The actor's most recent signal-source updates are folded into stored alignment metadata via `AlignmentRefresher`.
2. The proposed action goes to `DefaultNetPotentialGainGate.evaluate(...)`.
3. The verdict + the system's current utilisation classification land in a `SubstrateTraceLedger` record.
4. The ledger's head hash is peer-witnessed by at least one entity outside the deciding entity's organisational boundary.
5. The verdict gates the action.

Steps 1–3 are package-only. Steps 4 and 5 are host-application wiring on top of the package primitives.

## Operating-mode distribution in production

Across roughly N=10⁶ entities active in the deployment:

| Mode | Approximate share |
| --- | --- |
| `LONG_CYCLE` | 30% (production agents under sustained observation) |
| `MIXED` | 40% (newly-deployed entities; entities with one weak component) |
| `SHORT_CYCLE` | 10% (transactional services; cache-fill workers) |
| `UNKNOWN` | 20% (newly-created entities awaiting first classification) |

The `UNKNOWN`-vs-`SHORT_CYCLE` distinction (see [concept doc](../concepts/operating-mode.md)) earns its keep at this scale: collapsing the two would either silently downrate every newly-created entity (impacting customer onboarding) or silently uprate them (creating an escape route for new identities). The four-valued surface lets each cohort be handled correctly.

## NPG gate verdict distribution

For comparable consequential-decision sites (capability grants, tool dispatches):

| Verdict | Share |
| --- | --- |
| `NET_POSITIVE` | 65% |
| `NET_NEUTRAL` | 20% |
| `NET_NEGATIVE` | 1% |
| `INSUFFICIENT_DATA` | 14% |

The 14% `INSUFFICIENT_DATA` rate is a *leading indicator* of metadata-seeding gaps. When it spikes (e.g., during a new entity-type rollout), the operator surface alerts on the spike rather than waiting for downstream substrate-misalignment to manifest.

## Drift signals in production

The `EXTRACTIVE_GAIN` and `SELF_REFERENCE_MISCALIBRATION` patterns dominate the detection volume, which matches the package's prior; these are the two patterns most observable from structured signals alone, whereas `DECOUPLED_BONDING_REWARD` and `PERSISTENCE_REFUSAL` need behavioural-text traces to detect reliably.

Sustained-to-critical promotion is rare (single-digit promotions per million observations) and almost always involves the master pattern (`SELF_REFERENCE_MISCALIBRATION`) firing alongside another pattern. This validates the package's `amplifier_pattern_present` flag as a real operator-surface signal, not just a theoretical one.

## Halt-and-escalate cadence

Per-month operator-attention metrics:

- ~0.01% of entities enter `SUBSTRATE_MODE_REVIEW` (review-without-halt).
- ~0.001% enter `ESCALATED` (immediate halt).
- 100% of `ESCALATED` entries trace back to one of the two immediate-escalate triggers (`INVERSION_DETECTED`, `HARD_LIMIT_PROXIMITY`) or to a sustained-drift trigger with `critical_count` ≥ the configured minimum. The protocol's specified behaviour holds in production.
- Resume from `ESCALATED` requires explicit operator action; auto-resume is disabled in the deployment and has never been enabled.

## Resistance-band coverage

The deployment wires the productive-resistance band into every rate limiter, batch sizer, retry cap, queue depth, and ring promotion threshold. The discipline pays off in cross-subsystem reasoning: when one subsystem requests a tighter band (e.g., during a degraded downstream), the tighter band propagates to every limiter derived from it.

Attempts to **widen** beyond the default band have been refused at construction every time. The package's deliberate refusal-to-loosen is the property the deployment most relies on.

## Audit chain at scale

Cross-org peer-witness signing operates at every organisational boundary. A representative month sees ~10⁸ audit records appended, ~10⁵ peer-witness attestations signed, zero divergences observed (a divergence would indicate a real tampering event or a real implementation bug; the deployment has seen neither since the audit chain reached production).

The package's canonical-bytes specification (see [concept doc](../concepts/audit-chain.md)) lets non-Python verifiers (a Rust witness daemon at one of the edges, a TypeScript verifier in a browser-side compliance tool) re-derive and confirm hashes. The interoperability the spec promises is exercised in production.

## What the deployment does that the package does not

The package is *just* the primitives. The deployment layers on:

- Storage backends (Postgres at the node, replicated cross-org).
- Peer-witness key material (HSM-backed; the package's signer is HMAC-based and works against any key bytes).
- Operator surfaces (web console; the package surfaces the data, the host renders it).
- Cross-org sync (the package's audit chain shapes the records; the deployment's replication layer moves them).
- Domain-specific NPG action-kind overrides (the package ships generic priors; the deployment supplies its own per-vertical priors via `action_heuristics`).

Every one of these is host-application concern by design. The package keeps a narrow waist (Protocols and pure-logic primitives), so the deployment can swap any of these layers without changing how the substrate-alignment primitives compose.

## What's hard

Three things have been load-bearing over the deployment's life and are worth surfacing for any team replicating the pattern:

1. **The `INSUFFICIENT_DATA` rate is a feature, not a bug.** Teams new to the pattern often try to "fix" the INSUFFICIENT_DATA rate by auto-seeding entities with default metadata. This silently re-enables the loophole the gate exists to close. The honest answer is: seed metadata at entity-creation time via explicit pipeline; let `INSUFFICIENT_DATA` surface the gaps.

2. **Tightening the resistance band requires real evidence, not feelings.** The package permits tighter overrides; the discipline is to only tighten when you have independent evidence (latency tail, downstream pressure, regulatory floor) that justifies it. "It feels too permissive" is not evidence.

3. **Peer-witness signing only matters if you peer-witness across organisational boundaries.** Internal cross-service signing within one organisation is audit hygiene; cross-organisational signing is what makes the chain non-repudiable. Skipping the cross-organisational layer halves the audit chain's value.

## Recommended further reading

- [`spec/`](../../spec/). The normative behaviour of each primitive.
- [`docs/concepts/`](../concepts/). Engineering rationale for each primitive's shape.
- [`docs/adoption/`](../adoption/). Concrete framework-integration recipes.
- [`python/examples/06_full_governor_loop.py`](../../python/examples/06_full_governor_loop.py). The composition pattern this deployment runs in production.
