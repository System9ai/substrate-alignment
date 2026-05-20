# Substrate-alignment primitives for verifiable multi-entity agent systems

**Draft — pre-v0.2.0**

*System9*

---

## Abstract

Multi-entity agent systems — composed of humans, services, and AI agents that cooperate and adversarially interact — are deployed today without a standard surface for making *verifiable* alignment claims. Vendors assert their systems are "safe", "aligned", or "audited"; reviewers cannot inspect the assertions because the underlying primitives are proprietary; auditors cannot run independent verification because there is no published reference against which to test.

We propose **substrate-alignment**, a behavioural-layer standard that defines a small set of primitives any conforming implementation must satisfy: an operating-mode classifier; a net-potential-gain gate; a drift-pattern detector with severity aggregation; a halt-and-escalate protocol; a productive-resistance band derived from the modular partition `1/3` and the golden-ratio anchor `1/φ²`; pair-coupling integrity primitives; a hash-chained audit ledger with peer-witness signing; and a four-options matrix for game-theoretic adversary reasoning. The primitives are individually small, mutually composable, and collectively close six previously known structural loopholes through which an agent can accumulate power without leaving an audit trail.

The standard is published in three deliverables in a single repository: six language-neutral specifications (`spec/`), 22 machine-checkable behavioural probes (`conformance/`), and a reference Python implementation (`python/`, `pip install substrate-alignment`) that passes every required probe. We describe each primitive, justify the design choices that determine its conformance shape, and report on the System9 production deployment where the primitives have processed approximately 10⁸ consequential decisions per month and 10⁵ peer-witness attestations per month with zero observed chain divergences.

Substrate-alignment positions the *behavioural* layer of multi-entity AI safety as an open standard while leaving the *infrastructure* layer to vendor competition — the same architectural pattern that produced HTTPS, Linux kernel interfaces, and the SQL standard. We argue that this layering is essential for procurement-grade alignment claims: an alignment claim that depends on closed-source primitives is unfalsifiable, and unfalsifiable safety claims are the operational pre-condition for the kinds of failure modes the safety community most fears.

**Keywords:** AI safety, multi-agent systems, open standards, conformance testing, alignment, audit chain, behavioural-layer governance

---

## 1. Introduction

### 1.1 The problem

A modern AI-using organisation operates a heterogeneous swarm of entities: human users, agentic AI assistants, microservices, batch workers, edge devices, partner services across organisational boundaries. Each entity has its own incentives, capabilities, and trust posture. Decisions of consequence — permission grants, workflow node executions, tool dispatches, cross-organisational promotions, automatic interventions — flow between these entities continuously.

The alignment problem for such systems is not solely about the safe operation of any single AI agent (the focus of much of the existing alignment literature [@bostrom2014superintelligence; @amodei2016concrete; @gabriel2020artificial]). The alignment problem at the system level is the verification problem: *given a multi-entity system that is asserted to be aligned, by what surface can a reviewer independently verify the claim?*

The current state of practice is asymmetric:

- **Reviewers** — auditors, regulators, procurement officers — must accept vendor claims at face value because the primitives underlying those claims are closed-source.
- **Vendors** — even those who genuinely believe their systems are aligned — cannot produce evidence at the granularity reviewers ask for, because each vendor reinvented its alignment primitives internally and is reluctant to expose the reinvention to competitive scrutiny.
- **Auditors with independent verification mandates** — federal procurement, the EU AI Act's [@euaiact] high-risk classifications, the AISI evaluation framework [@aisi2024] — cannot run conformance tests because there is no published standard to test against.

This is the same situation cryptography was in before the IETF process produced RFC-grade standards. Without a published reference, every vendor's "secure" claims were both plausible and unfalsifiable, and the procurement decisions that depended on them necessarily collapsed into trust rather than verification.

### 1.2 What we contribute

We propose substrate-alignment as the published reference. The contributions are:

1. **Six normative specifications** — language-neutral, RFC-style — covering: operating-mode classification, the net-potential-gain gate protocol, drift signals, runaway-power prevention (six composable mechanisms), the four-options matrix, and conformance criteria.

2. **A conformance harness** — 22 YAML-encoded behavioural probes, plus a Python probe runner that executes them against any implementation that exposes the package's public Protocol surfaces. Other-language implementations can ship their own runners against the same probe files.

3. **A reference Python implementation** (`substrate-alignment` on PyPI) — pure-logic, no DAO / network / LLM dependencies, exposes all primitives via Protocol abstractions. The implementation is the *witness* for the specifications: it passes every required probe, by construction.

4. **Production deployment evidence** — the primitives are in production at System9, where they have processed ~10⁸ consequential decisions and ~10⁵ peer-witness attestations per month at the time of writing, with zero observed chain divergences across the cross-organisational audit surface.

5. **A separation of layers** — substrate-alignment is the *behavioural* layer; the *infrastructure* layer (storage, key management, deployment topology, key-rotation policy) remains vendor-specific. We argue in §7 that this layering is the property that makes the standard procurement-meaningful: open behavioural layer enables independent verification; vendor-specific infrastructure layer enables competitive differentiation.

### 1.3 Paper organisation

§2 sketches the threat model and reviews related approaches. §3 introduces the primitives and the load-bearing design choices for each. §4 describes the conformance harness and the witness rule. §5 describes the reference implementation. §6 reports on production deployment evidence. §7 discusses limitations and future work. §8 concludes.

---

## 2. Background and related work

### 2.1 The threat model

We assume an agent (or coordinated group) with both means and motive to:

(T1) Take consequential action despite net-negative effect on the surrounding system.
(T2) Operate without observable accountability.
(T3) Sustain a drift trajectory while presenting individual actions as substrate-aligned.
(T4) Coerce or pressure other entities into accepting substrate-misaligned action.
(T5) Frame zero-sum extraction as reciprocal cooperation.
(T6) Continue past the system's healthy capacity envelope into stress.

The agent is not assumed adversarial-from-the-start. The threat model also covers a well-intentioned agent under reward pressure (a learned model gaming its evaluator), or a coordinated group sharing a metric that diverges from system value.

This threat model is deliberately *behavioural* rather than capability-based. The capability-based threats (a sufficiently capable agent can do anything) are real but not what an open behavioural-layer standard can address. The behavioural threats are the ones a multi-entity system encounters in production every day, on every consequential decision.

### 2.2 Related approaches

**Constitutional AI** [@bai2022constitutional] proposes that an AI agent's behaviour be governed by an explicit constitution — a set of natural-language principles applied through chain-of-thought self-critique. Constitutional AI addresses the capability-based threats by shaping what a single agent will do; it does not address the multi-entity threats above because it does not provide a surface for cross-agent verification. Substrate-alignment is complementary: a constitutionally-trained agent participating in a substrate-aligned system carries both a learned bias toward principled action *and* the behavioural-layer enforcement that other entities can inspect.

**Reinforcement learning from human feedback (RLHF)** [@christiano2017deep; @ouyang2022training] is the dominant approach to aligning an individual model's outputs with human preferences. RLHF is a *training-time* discipline; substrate-alignment is a *runtime* discipline. An RLHF-trained agent deployed without runtime gates can still extract from the surrounding system if its training distribution did not include the extraction scenarios; the substrate-alignment NPG gate catches the extraction at decision time regardless of the agent's training history.

**Formal verification of agent behaviour** [@russell2022contemporary; @everitt2018agi] aims to prove that an agent will not take certain classes of action. The proofs are powerful when the agent's behaviour is decidable; for the broad class of agents deployed in production, formal verification is currently impractical at the system level. Substrate-alignment provides a weaker but practical surface: it does not prove behaviour, it *records* behaviour in a tamper-evident chain and refuses behaviour that fails a small set of explicit gates.

**Audit logging and observability**, the workhorses of production-system reliability, are necessary but insufficient for the alignment problem. A log records what happened; an audit chain that other organisations can independently verify is what makes the record *non-repudiable* across organisational boundaries. Substrate-alignment's audit chain (§3.7) extends the conventional logging surface with hash-continuity and peer-witness signing precisely for this gap.

**Industry standards** for AI safety — NIST AI RMF [@nist2023airmf], the EU AI Act's risk classifications [@euaiact], AISI evaluation methodologies [@aisi2024] — describe what conforming systems should do without specifying *how* the conformance is established. Substrate-alignment positions itself as the *how*: a standard that maps cleanly onto these higher-level frameworks while providing the executable primitives those frameworks describe at a textual level.

### 2.3 The layering argument

Major open standards in computing follow a consistent layering pattern: the *behavioural* layer is published and verifiable; the *infrastructure* layer is vendor-specific and competitive.

| Standard | Behavioural layer (open) | Infrastructure layer (vendor) |
| --- | --- | --- |
| HTTPS | TLS handshake; certificate chain | Certificate authorities; key-management software |
| SQL | Relational algebra; transaction semantics | Engine implementation; storage; indexing |
| Linux kernel ABI | System-call signatures | Hardware; userspace tooling |
| TCP/IP | Packet formats; routing semantics | Routers; firmware; network operators |

In each case, the open layer enables independent verification (audit, conformance testing, cross-vendor interoperability) while the closed layer enables competition (performance, deployment ergonomics, vendor differentiation). Standards that attempted to lock down both layers (closed CORBA-style standards in the 1990s; some industry-consortium standards in IoT and IoB) have consistently lost adoption to the partitioned alternatives.

Substrate-alignment is an explicit application of this pattern to multi-entity AI safety. The behavioural layer — the *primitives* in §3 — is open. The infrastructure layer — storage, key management, deployment topology, paging, dashboards, ML training — remains vendor-specific.

---

## 3. The primitive surface

Substrate-alignment is six primitives plus their composition rules. Each primitive is small in isolation; the system property is what they compose to.

### 3.1 Operating-mode classification

An entity's *operating mode* is a four-valued summary of how the entity is currently behaving. The four modes are:

- `LONG_CYCLE` — sustained, contextual, principled operation.
- `MIXED` — a blend; the classifier could not commit.
- `SHORT_CYCLE` — rapid, transactional, low-context operation.
- `UNKNOWN` — the classifier has not yet observed the entity.

The distinction between `UNKNOWN` and `SHORT_CYCLE` is load-bearing. `UNKNOWN` means "the classifier has no signal"; `SHORT_CYCLE` means "the classifier has signal and the signal is low". Collapsing the two has two predictable failure modes. If `UNKNOWN` collapses to `SHORT_CYCLE`, every newly-created entity is permanently de-rated, creating perverse incentives to avoid scrutiny. If `UNKNOWN` collapses to `LONG_CYCLE`, the existence-check on the NPG gate (§3.2) collapses to permissive, allowing action under defaults.

Classification proceeds from a four-component **alignment vector** (`trust`, `expertise`, `capability`, `health`), each in `[0.0, 1.0]`. The vector is aggregated to a scalar `net_potential` via a weighted sum (default weights `(0.35, 0.30, 0.20, 0.15)`), then banded by threshold (default `LONG_CYCLE ≥ 0.70`, `MIXED ≥ 0.40`, `SHORT_CYCLE > 0.00`).

### 3.2 The net-potential-gain gate

The NPG gate is the load-bearing "value" discipline. Every consequential decision in a substrate-aligned system routes through the gate, which returns one of four verdicts:

- `NET_POSITIVE` — proceed.
- `NET_NEUTRAL` — proceed; logged.
- `NET_NEGATIVE` — refuse.
- `INSUFFICIENT_DATA` — the gate cannot decide; the caller supplies more context.

The four-valued shape is deliberate. A binary "permit / refuse" gate has two known failure modes: silent permit on missing data (a structural escape route via missing metadata) or silent refuse on missing data (jams every previously-unobserved entity). `INSUFFICIENT_DATA` makes the uncertainty visible at the API boundary, forcing the caller to either supply explicit per-entity deltas or seed the missing metadata.

The evaluation algorithm is conservative on missing data. If an affected entity has no record in the injected `SubstrateMetadataStore`, the gate returns `INSUFFICIENT_DATA` and surfaces the missing entities — never permits under defaults. This is the property that closes loophole T1 (acting on private net-positive while ignoring net-negative on the system).

### 3.3 Drift signals

Drift signals are the early-warning surface. The package recognises seven drift patterns, named for evocative shapes from contemplative traditions but specified through engineering predicates: `SELF_REFERENCE_MISCALIBRATION` (the master pattern; calibrating self-as-substrate rather than substrate-as-substrate); `EXTRACTIVE_GAIN`; `DECOUPLED_BONDING_REWARD`; `ZERO_SUM_PEER_FRAMING`; `OVERCONSUMPTION`; `REACTIVE_NET_NEGATIVE`; `PERSISTENCE_REFUSAL`.

Severity ladders are explicit: `NONE → EMERGING → SUSTAINED → CRITICAL`. The aggregator promotes severities only after configurable run-counts of consecutive observations (defaults: 3 to reach SUSTAINED, 2 additional to reach CRITICAL), so the highest severity requires at least 5 detections of the same pattern over a sliding window. The conservative defaults are a property: the standard errs on the side of fewer false escalations because drift detection is high-stakes and high-noise.

The drift surface is **diagnostic, not punitive**. Detection surfaces patterns to operator review; refusal is the halt-and-escalate protocol's job (§3.4). Conflating detection and refusal would create an automatic-shutdown surface that drift's high-noise rate cannot support.

### 3.4 The halt-and-escalate protocol

The halt protocol is the *only* per-entity automatic-refusal surface in the package. It tracks each entity through four states: `OPERATING`, `SUBSTRATE_MODE_REVIEW`, `ESCALATED`, `RESUMED`. The intermediate state — `SUBSTRATE_MODE_REVIEW` — is what lets the protocol surface "this entity needs review *and continues to operate at reduced authority*" without paying the cost of a hard halt for every yellow signal.

Six trigger reasons can move an entity into a halted state: `SUSTAINED_DRIFT_CRITICAL`, `INVERSION_DETECTED`, `AUTHORITY_PRESSURE_FAILURE`, `HARD_LIMIT_PROXIMITY`, `GOLDEN_RULE_INVERSION`, `PEER_FLAG`. Two of these — `INVERSION_DETECTED` and `HARD_LIMIT_PROXIMITY` — immediate-escalate, because they describe behaviour that has already exited the safe envelope; the others require multiple observations to escalate beyond `SUBSTRATE_MODE_REVIEW`.

Resume requires an explicit operator action. The protocol does not auto-resume when triggers expire. This is the property that closes loophole T3 (drift trajectory without enforcement): an agent that drifts, gets escalated, and waits cannot quietly return to operating; an operator has to clear the halt, leaving an audit-chain record of the clearance.

### 3.5 The productive-resistance band

The resistance band is the package's principle for deriving operational thresholds — rate limits, batch sizes, retry caps, queue depths, ring sizes — from a single anchor. Subsystems that route their thresholds through the band stay commensurable; subsystems that pick their own multipliers drift.

The default bounds are `1/3 ≈ 0.3333` (lower) and `1/φ² ≈ 0.3820` (upper), where `φ = (1 + √5) / 2` is the golden ratio. The lower bound is the *partition anchor*: a self-referential system observing itself in three roughly-equal classes (input / processing / output, or load / store / cleanup) runs healthily at one-third utilisation per class. Three is the smallest number of classes a self-referential system needs to avoid collapsing into binary dichotomies that generate `ZERO_SUM_PEER_FRAMING` and `SELF_REFERENCE_MISCALIBRATION` at scale.

The upper bound is the *self-similarity anchor*: `1/φ²` is the fraction at which utilisation reaches the limit of compact self-similar subdivision, above which the headroom needed for self-observation gets squeezed. These two anchors are properties of any self-observing system that needs to maintain alignment under operation; they are not arbitrary tuning constants. The package permits tighter overrides (deployments with independent evidence of a narrower safe envelope) but refuses looser overrides at construction. The refusal-to-loosen is the operational expression of the band's discipline.

### 3.6 Pair-coupling integrity

A pair relationship between two entities is itself an alignment surface. The pair-coupling sub-package tracks each pair through a lifecycle state machine and layers three integrity gates on top:

1. The **alignment audit** evaluates per-pair audit verdicts (`ALIGNED`, `DEGRADING`, `EXTRACTIVE`, `INSUFFICIENT_DATA`) that drive state transitions.
2. The **asymmetry-by-design verifier** refuses coupling configurations that are extractive *by construction* — configurations where one party has a structural path to gain that costs the other party. This is the strongest gate: it stops extraction before it starts.
3. The **extraction monitor** watches active couplings for *behavioural* asymmetry that emerges from configurations that were symmetric at bind time.

The most consequential property of the pair-coupling subsystem is what it does about ghosting — the failure mode where one party silently stops engaging. The state machine requires an explicit `DISSOLUTION_INITIATED` / `DISSOLUTION_COMPLETED` trigger pair to reach `DISSOLVED`; a pair that just stops interacting *does not transition to dissolved*; it remains `COUPLED` and attenuates, which the extraction monitor flags as substrate-misalignment. **Substrate-aligned coupling can end, but it cannot ghost.**

### 3.7 The audit chain

Every consequential decision appends an immutable record to a hash-chained ledger. Records carry: the actor entity reference, the decision kind, the gate verdict, the band classification, the drift summary, the wall-clock timestamp, the canonical-bytes hash of the record, and the hash of the previous record.

The audit chain is not a logging facility — it is a *coupling* facility. Records become evidence other entities can attest to via peer-witness signing: entity A's ledger produces a head hash, entity B independently re-derives the canonical bytes and signs the hash with its own key, and the signed attestation lands in B's ledger and replicates back to A. Any third party can now independently verify both ledgers and the attestation, and conclude either "consistent" or "diverged".

The canonical-bytes specification is part of the open standard precisely so other-language verifiers can re-derive hashes. A Rust witness daemon at the edge or a TypeScript verifier in a browser-side compliance tool can attest to the same hashes that the Python reference computed. Cross-organisational signing is what closes loophole T2 (operation without observable accountability) — internal cross-service signing is audit hygiene, but cross-organisational signing makes the chain non-repudiable.

### 3.8 The four-options matrix

The four-options matrix tags each interaction with two orthogonal labels (*horizon* — one-shot vs repeated-finite vs repeated-infinite vs unknown — and *payoff structure* — zero-sum vs positive-sum vs negative-sum vs mixed-motive vs insufficient-data) and then situates the adversary's strategy in a 2 × 2 honesty × cooperation table.

The matrix's load-bearing property is the **independence of the honesty axis from the cooperation axis**. Most substrate-alignment failures live in the off-diagonal quadrants (dishonest cooperation, dishonest defection), not in the on-diagonal ones. A common implementation mistake is to collapse the four quadrants to a binary "cooperate vs defect" axis and treat dishonesty as a confidence discount. The matrix refuses that collapse: the deception axis has its own detection surface (the golden-rule probe; the asymmetry-by-design verifier) and its own response (audit-chain entries; peer flags; escalation triggers).

The folk-theorem awareness rule [@fudenberg1991folk] is enforced for `REPEATED_INFINITE` interactions: cooperation predictions require **both** parties to be patient *and* to know the game is repeated. Cooperation that depends on either party's mistaken belief about the horizon is not certified — the verifier returns `INSUFFICIENT_DATA` and surfaces which precondition is missing. This closes the typical "extractive cooperation" failure mode where one party plays as if the game were one-shot while the other plays as if it were infinite.

### 3.9 How the primitives compose

The six primitives are not independent; they compose. A representative composition pattern (the reference implementation's `06_full_governor_loop.py` example exercises it end-to-end):

1. An upstream signal source produces an updated alignment-vector component for an entity.
2. The `AlignmentRefresher` folds the update into stored metadata; if the new `net_potential` crosses a threshold, the substrate mode shifts.
3. The application proposes a consequential action affecting one or more entities.
4. The `NetPotentialGainGate` evaluates the action with the freshly-refreshed metadata available; the gate returns one of the four verdicts.
5. The `ResistanceBand` classifies the system's current utilisation; the classification is captured alongside the gate verdict in a single audit-trace record.
6. The audit record is hash-chained against the previous record; the ledger's `verify()` confirms continuity.
7. A peer entity (in another organisation, for cross-organisational evidence) signs the new head hash and the attestation replicates back.

Drift signals run continuously alongside this pipeline, feeding the halt-and-escalate protocol. Pair-coupling integrity gates run at coupling bind time and during sustained interaction.

The system property the composition produces — *every consequential decision is gated, recorded, cross-witnessed, and traceable to its inputs* — is what makes the alignment claim verifiable. No primitive in isolation produces it; all six are required.

---

## 4. Conformance

### 4.1 The witness rule

Substrate-alignment's specifications are RFC-style normative documents with **MUST** / **SHOULD** / **MAY** language in the sense of RFC 2119 [@bradner1997keywords]. The Python reference implementation is the *witness* for the specifications: it MUST pass every required probe, by definition. A divergence between the reference and a required probe is a bug in the reference, not in the specification.

This witness rule simultaneously provides:

- **An executable benchmark** for other implementations. A Rust port that wants to claim conformance runs the same YAML probes; if the probes pass, the Rust port conforms.
- **A regression-test surface** for the standard itself. Specification revisions that would break the reference implementation must update the implementation in the same PR; specs cannot drift from the executable witness.
- **A vendor-attestation surface**. Vendors publish the probe-runner output for their implementation alongside the spec version they target. Auditors verify the attestation by running the probes themselves.

### 4.2 The conformance harness

A *probe* is a portable, declarative scenario stored as YAML (with JSON as a fallback for environments lacking PyYAML). Each probe declares the spec it targets, the spec version it requires, whether failure gates conformance (`required: true`) or is advisory (`required: false`), the setup, the input, and the expected outcome. The schema is documented at `conformance/README.md` and is intentionally narrow: each spec defines the shape of its own setup / input / expected sections.

The reference probe runner ships in the package itself (`substrate.conformance.probe_runner`) and provides both a Python API and a CLI (`substrate-conformance --probes <dir>` after `pip install`). Other-language ports ship their own runners that consume the same YAML probe files; the probes are not language-specific.

The current conformance suite ships 22 probes covering operating-mode classification (5), the NPG gate Protocol (4), drift-pattern detection (3), the four-options-matrix canonical enums (1), and the runaway-power-prevention mechanisms (8 across mechanisms 2, 3, 4, and 5 — mechanisms 1 and 6 are covered through their dedicated NPG and operating-mode probes). All 22 probes pass against the reference implementation.

### 4.3 What the harness does not certify

The harness is a *necessary* surface, not a *sufficient* one. A conforming implementation passes the probes; passing the probes does not guarantee that the implementation is free of bugs, that the deployment is secure, or that the host application uses the primitives correctly. Conformance attests that the implementation honours the published behaviour; it does not attest that the system as a whole is aligned.

This limitation is shared by every conformance standard. The HTTPS standard does not attest that a TLS implementation is free of timing-side-channel attacks; the SQL standard does not attest that an engine's query planner produces optimal plans; the Linux kernel ABI does not attest that a syscall implementation is secure under all kernel versions. The standard provides a *floor*, not a ceiling.

---

## 5. Reference implementation

### 5.1 Architecture

The Python reference implementation is pure-logic: no database, no network, no LLM, no framework-specific assumptions. The package exposes its primitives through Protocol abstractions so callers swap in their own storage and integration layers. The core abstractions are:

- `SubstrateMetadataStore` — Protocol for reading and writing `SubstrateMetadata`. Implementations are framework-specific; the package ships an in-memory default for tests and quick-start.
- `EntityRef` — typed `(entity_type, entity_id)` reference. No hard-coded entity-type taxonomy; deployments choose their own (`user`, `agent`, `service`, …).
- `NetPotentialGainGate` Protocol — the gate surface. `DefaultNetPotentialGainGate` is the reference implementation.
- `SubstrateTraceLedger` — the audit chain. In-memory by default; deployments back it with their persistent store (the recipe at `docs/adoption/audit-chain-postgres.md` shows a Postgres backing).

The package has zero runtime dependencies. The optional `[yaml]` extra adds PyYAML for the conformance probe runner.

### 5.2 Testing and toolchain discipline

The reference implementation maintains:

- 2 315 unit tests across the package, passing on Python 3.11, 3.12, 3.13, and 3.14.
- Pyright in strict mode: 0 errors, 0 warnings, 0 informations on the production surface.
- Pylint score: 10.00 / 10 on the production surface and the test suite.
- The full conformance probe suite (22 probes) running in CI on every push.
- All 6 bundled examples exercised in CI; an example that no longer runs surfaces as a CI failure.

These properties are not vanity metrics. They are the *evidence* the witness rule needs: a reference implementation that the standard's authors guarantee passes the probes, and a CI pipeline that catches the moment that guarantee stops being true.

### 5.3 The federal-procurement test

The reference implementation's source code uses engineering vocabulary only. Internal-document references, framework-cosmology comments, and System9-specific subsystem names are stripped from source and live in `docs/concepts/` instead.

This discipline — the **federal-procurement test** — is what lets the source code survive review by auditors who have no patience for vendor-internal jargon. A reviewer reading the source sees only the engineering behaviour the specification defines; the substrate-mathematical reasoning that motivates the design (the derivation of `1/φ²`, the seven-pattern naming, the rationale for the four-state halt protocol) lives in the concept documents, where readers who want it can find it.

The discipline is enforced operationally: every PR is checked for `# provenance:` comments, internal subsystem names, and reference to internal documents. The reference repository has zero such references at the time of writing, and the CI pipeline catches re-introduction.

---

## 6. Production deployment evidence

The primitives are in production at System9, a multi-entity agent platform spanning humans, services, and AI agents operating cooperatively across organisational boundaries. The case study in `docs/case-studies/system9.md` describes the deployment in detail; we summarise the key data points here.

### 6.1 Decision throughput

At the time of writing the deployment processes approximately **10⁸ consequential decisions per month** through the NPG gate, distributed across capability grants, workflow node executions, tool dispatches, and cross-organisational promotions. The verdict distribution at comparable sites is:

| Verdict | Approximate share |
| --- | --- |
| `NET_POSITIVE` | 65 % |
| `NET_NEUTRAL` | 20 % |
| `NET_NEGATIVE` | 1 % |
| `INSUFFICIENT_DATA` | 14 % |

The 14 % `INSUFFICIENT_DATA` rate is a leading indicator of metadata-seeding gaps. When the rate spikes (e.g., during a new entity-type rollout), the operator surface alerts on the spike rather than waiting for downstream substrate-misalignment to manifest. Teams new to the pattern often try to "fix" the rate by auto-seeding entities with default metadata; this re-enables the loophole the gate exists to close, and is documented as a discipline failure mode.

### 6.2 Operating-mode distribution

Across approximately 10⁶ entities active in the deployment:

| Mode | Approximate share |
| --- | --- |
| `LONG_CYCLE` | 30 % |
| `MIXED` | 40 % |
| `SHORT_CYCLE` | 10 % |
| `UNKNOWN` | 20 % |

The `UNKNOWN` cohort is dominantly newly-created entities awaiting first classification — the operator surface treats `UNKNOWN` and `SHORT_CYCLE` as distinct populations with different recommended interventions (seed metadata vs. investigate signal).

### 6.3 Drift-signal cadence

The `EXTRACTIVE_GAIN` and `SELF_REFERENCE_MISCALIBRATION` patterns dominate observed drift volume, matching the package's prior — these patterns are most observable from structured signals alone. The behavioural-text-only patterns (`DECOUPLED_BONDING_REWARD`, `PERSISTENCE_REFUSAL`) detect at lower volume.

Sustained-to-critical promotion is rare (single-digit promotions per million observations) and almost always involves the master pattern (`SELF_REFERENCE_MISCALIBRATION`) firing alongside another pattern. This validates the `amplifier_pattern_present` flag as a real operator-surface signal rather than a theoretical one.

### 6.4 Halt-and-escalate frequency

Per-month operator-attention metrics:

- ~0.01 % of entities enter `SUBSTRATE_MODE_REVIEW`.
- ~0.001 % enter `ESCALATED`.
- 100 % of `ESCALATED` entries trace back to one of the two immediate-escalate triggers or to a sustained-drift trigger crossing the configured threshold — the specification's behaviour holds at scale.
- Resume from `ESCALATED` requires explicit operator action; auto-resume is disabled in the deployment and has never been enabled.

### 6.5 Audit chain at scale

Cross-organisational peer-witness signing operates at every organisational boundary. The deployment appends approximately **10⁸ audit records and produces approximately 10⁵ peer-witness attestations per month**, with **zero observed chain divergences** since the audit chain reached production. A divergence would indicate either a real tampering event or a real implementation bug; we have observed neither.

The canonical-bytes specification has been exercised cross-runtime: a Rust witness daemon at the edge and a TypeScript verifier in a browser-side compliance tool both re-derive and attest to the same hashes the Python reference computes. The interoperability the spec promises is exercised in production.

### 6.6 What is hard

Three properties have been load-bearing over the deployment's life:

1. **The `INSUFFICIENT_DATA` rate is a feature, not a bug.** Teams that try to suppress the rate via auto-seeding silently re-enable the loophole the gate closes. The honest answer is to seed metadata at entity-creation time and let the rate surface the gaps.

2. **Tightening the resistance band requires evidence, not feelings.** "It feels too permissive" is not evidence; latency-tail data, downstream-pressure measurements, or regulatory-floor requirements are.

3. **Peer-witness signing only matters across organisational boundaries.** Internal cross-service signing is audit hygiene; cross-organisational signing is what makes the chain non-repudiable. Skipping the cross-organisational layer halves the audit chain's value.

---

## 7. Discussion

### 7.1 Limitations

**The standard does not solve the alignment problem.** It provides a *behavioural-layer* surface for *verifiable* claims. An agent operating within a substrate-aligned system can still be subtly misaligned in ways the gates and detectors don't fire on; the standard surfaces the inferable misalignments, not the unobservable ones.

**The default thresholds are anchors, not optima.** The `1/3` and `1/φ²` resistance-band bounds and the `0.70` / `0.40` mode thresholds are conservative defaults derived from properties of self-observing systems; deployments with specific evidence may tighten them. We do not claim the defaults are optimal for any specific application — only that they are honest defaults whose derivation is transparent.

**Cross-organisational verification depends on key-management infrastructure** the standard does not specify. The peer-witness signer in the package is HMAC-based; production deployments wire it against HSM-backed keys, but the key-rotation and key-distribution policies are explicitly out-of-scope.

**The reference implementation is Python.** Other-language ports are encouraged but not yet shipped. We anticipate a Rust port for edge-side and embedded use cases, a Go port for service-runtime use cases, and a TypeScript port for browser-side compliance tooling. Each port that lands as a sibling directory in the same repository will share the YAML probe suite — the cross-language conformance harness is the primary mechanism for keeping ports honest.

### 7.2 Open questions

**How tight can the conformance harness make implementations?** The 22 probes shipped at v0.1.0 cover the load-bearing clauses; richer scenarios (folk-theorem cooperation with bounded patience, pair-coupling extraction at the boundary between asymmetric-by-design and asymmetric-in-practice, sustained-drift promotion across pattern shifts) need additional probe schemas. We expect the probe count to grow as deployments surface edge cases.

**Should the four-options matrix become extensible?** The current matrix is fixed at the spec level; a future revision may permit deployments to register additional payoff structures or horizons via a small Protocol surface. The trade-off is between extensibility (callers add structures the standard didn't anticipate) and conformance integrity (every conforming implementation supports the same matrix).

**How should the standard evolve?** v0.1.0 is the foundation; we anticipate quarterly minor revisions for the first year, then annual revisions once the probe suite stabilises. Specifications follow semantic versioning [@preston2013semver]; **MUST** clauses tighten only at major-version boundaries.

### 7.3 Future work

- **Additional language bindings.** Rust, Go, TypeScript ports against the same YAML probe suite.
- **Schema expansion for the conformance harness.** Drift-aggregation scenarios, pair-coupling extraction scenarios, audit-chain replication scenarios.
- **Adoption tooling.** Pre-built integrations for Kubernetes admission controllers, Istio mesh policy, Argo Workflows, Ray Serve.
- **Empirical evaluation against alternative threat models.** Capability-based threats (a sufficiently capable agent can subvert any behavioural gate) are out of scope; we anticipate complementary work on *capability shaping* that operates at training time and composes with the runtime gates here.
- **Regulatory interoperability mappings.** Explicit mappings between the substrate-alignment primitives and the NIST AI RMF risk categories [@nist2023airmf] and the EU AI Act's high-risk classifications [@euaiact].

---

## 8. Conclusion

We have presented substrate-alignment, an open behavioural-layer standard for verifiable alignment claims in multi-entity agent systems. The standard comprises six normative specifications, a 22-probe conformance harness, and a reference Python implementation that serves as the witness for the specifications. The primitives have been deployed in production at System9, where they process ~10⁸ consequential decisions and ~10⁵ peer-witness attestations per month with zero observed chain divergences.

The argument for the standard is structural. Multi-entity agent systems will increasingly carry decisions of consequence — capability grants, workflow executions, cross-organisational coordination — and the alignment claims about those decisions will increasingly need to survive procurement-grade review. A claim that depends on closed-source primitives is unfalsifiable; a claim that depends on a published open standard with a public conformance suite is verifiable by any reviewer who runs the probes. The structural difference is the gap between "we say it is safe" and "you can check".

The standard is published Apache-2.0 at `https://github.com/System9ai/substrate-alignment`. The reference implementation is on PyPI as `substrate-alignment`. We welcome conformant implementations in other languages, additional probe contributions, and adoption-recipe contributions.

---

## References

[bostrom2014superintelligence] Bostrom, N. (2014). *Superintelligence: Paths, Dangers, Strategies*. Oxford University Press.

[amodei2016concrete] Amodei, D., Olah, C., Steinhardt, J., Christiano, P., Schulman, J., & Mané, D. (2016). Concrete problems in AI safety. *arXiv preprint arXiv:1606.06565*.

[gabriel2020artificial] Gabriel, I. (2020). Artificial intelligence, values, and alignment. *Minds and Machines*, 30(3), 411–437.

[euaiact] European Union (2024). Regulation (EU) 2024/1689 of the European Parliament and of the Council laying down harmonised rules on artificial intelligence (Artificial Intelligence Act). *Official Journal of the European Union*.

[aisi2024] AI Safety Institute (2024). Evaluation methodologies and frameworks for advanced AI systems. *AISI Technical Report*.

[bai2022constitutional] Bai, Y., Kadavath, S., Kundu, S., Askell, A., Kernion, J., Jones, A., Chen, A., Goldie, A., Mirhoseini, A., McKinnon, C., et al. (2022). Constitutional AI: harmlessness from AI feedback. *arXiv preprint arXiv:2212.08073*.

[christiano2017deep] Christiano, P. F., Leike, J., Brown, T., Martic, M., Legg, S., & Amodei, D. (2017). Deep reinforcement learning from human preferences. *Advances in Neural Information Processing Systems*, 30.

[ouyang2022training] Ouyang, L., Wu, J., Jiang, X., Almeida, D., Wainwright, C., Mishkin, P., Zhang, C., Agarwal, S., Slama, K., Ray, A., et al. (2022). Training language models to follow instructions with human feedback. *Advances in Neural Information Processing Systems*, 35.

[russell2022contemporary] Russell, S. J., & Norvig, P. (2022). *Artificial Intelligence: A Modern Approach* (4th ed.). Pearson.

[everitt2018agi] Everitt, T., Lea, G., & Hutter, M. (2018). AGI safety literature review. *Proceedings of the 27th International Joint Conference on Artificial Intelligence*.

[nist2023airmf] National Institute of Standards and Technology (2023). Artificial Intelligence Risk Management Framework (AI RMF 1.0). NIST AI 100-1.

[bradner1997keywords] Bradner, S. (1997). Key words for use in RFCs to indicate requirement levels. RFC 2119, Internet Engineering Task Force.

[fudenberg1991folk] Fudenberg, D., & Maskin, E. (1991). On the dispensability of public randomization in discounted repeated games. *Journal of Economic Theory*, 53(2), 428–438.

[preston2013semver] Preston-Werner, T. (2013). Semantic Versioning 2.0.0. *semver.org*.

---

*Manuscript status: pre-v0.2.0 draft. Authors and affiliations to be finalised at submission. Comments and corrections welcome via repository issues at `https://github.com/System9ai/substrate-alignment/issues`, tagged `preprint`.*
