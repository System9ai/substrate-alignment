# Changelog

All notable changes to substrate-alignment will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added (v0.2.0 candidate)

- **Governed ascent — NPG-governed hill climbing**
  ([`spec/runaway-power-prevention.md`](spec/runaway-power-prevention.md)
  §4.4, [`docs/concepts/governed-ascent.md`](docs/concepts/governed-ascent.md)):
  `substrate.governed_ascent` — a greedy-ascent loop whose objective is
  certified before entry (`substrate.objective_gate`, fail-closed),
  whose every step is a net-potential-gain evaluation, whose effort is
  paced by the layered capacity zones, and whose termination +
  consolidation are mandatory (eight explicit verdicts; no unterminated
  climbs by construction). Six new conformance probes
  (`runaway-power-prevention__mech-6__ascent-*`). MUST-clause
  additions → stays within the v0.2.0 candidate.

- **Resistance band — layered zones, debt, and pickup**
  ([`spec/runaway-power-prevention.md`](spec/runaway-power-prevention.md)
  §4.1–4.3): five-valued `ZoneClassification`
  (under-loaded / calibration / working / peaking / debt) with the
  φ-conjugate (`1/φ ≈ 0.618`) debt line and the 0.5 work-zone ceiling
  as substrate anchors; `maintain_target(N)` group-size-aware
  maintain-mode targets; φ-stepped growth assessment;
  `substrate.sustained_load` (sporadic-vs-sustained tracking, debt
  units, avoidance + runaway-growth detection) and
  `substrate.debt_pickup` (debt ledger with reciprocity accounting,
  peer-pickup planning, ordered compensation policy). PEAKING signal
  added to the state-signal vocabulary; `over_challenge` threshold
  corrected from ad-hoc `0.7` to the φ-conjugate. Six new conformance
  probes (zones, sustained debt, sporadic spike, maintain target,
  growth step). MUST-clause additions → minor version bump.


- **Reflex-vs-restraint gate** ([`spec/reflex-restraint.md`](spec/reflex-restraint.md))
  — the fight-or-flight-vs-deliberate-restraint decision primitive. A
  pure, total, deterministic gate returning one of five verdicts
  (`ACT_REACTIVE`, `RESTRAIN`, `DE_ESCALATE`, `REFUSE_HARD_LIMIT`,
  `INSUFFICIENT_DATA`): the fast survival reflex is substrate-aligned
  only at a genuine survival-level threat; a non-survival provocation
  whose reactive action is net-negative de-escalates or restrains; a
  hard limit refuses regardless. Composes the `npg-gate-protocol`
  verdict as input. Reference impl at
  [`substrate.offense.reflex_restraint_gate`](python/src/substrate/offense/reflex_restraint_gate.py),
  with the [`OffenseResponseOrchestrator`](python/src/substrate/offense/response_orchestrator.py)
  sequencing it ahead of the deliberate offense-handling path. Five
  `reflex-restraint__*` conformance probes.
- **Evidence-grade Protocol** ([`spec/evidence-grade.md`](spec/evidence-grade.md))
  — four-step ladder `UNVERIFIED_HEARSAY < CORROBORATED < ATTESTED <
  DOCUMENTED_CRYSTALLIZED` for grading substrate-state claims by
  evidentiary strength. Includes `EvidenceAttestation`,
  `EvidenceComposition`, `EvidenceGradeConfig`, and the
  `SubstrateStateClaim` runtime-checkable Protocol that host
  applications implement on their canonical-state records (MNEMOSYNE,
  ARGUS, project-specific stores).
- Reference impl at
  [`python/src/substrate/evidence_grade/`](python/src/substrate/evidence_grade/):
  pure-logic `compose_evidence_grade()` with deterministic rule
  ordering and decay downgrade (7-day half-life × 2 default).
- 5 conformance probes covering single-source / corroborated /
  attested / documented-crystallized / decay-downgrade scenarios. All
  pass against the Python reference.
- 28 reference-impl unit tests pin every clause of `spec/evidence-grade.md`
  § 3, lifting the suite from 2315 → 2343 tests.

### Changed (v0.3.0 candidate)

- **`threshold_derivation` is now quantity-aware (RESISTANCE vs WORK).**
  The helper previously offered only the resistance positions
  (`LOWER` / `TARGET` / `UPPER`, `1/3 … 1/φ²`), so deriving a WORK
  quantity (buffer capacity, rate budget, queue depth) from `TARGET`
  under-provisioned it by ~20%. Added `BandPosition.WORK_TARGET`
  (work-zone midpoint ~0.441) + `WORK_CEILING` (0.50 pivot) and the
  `derive_work_target` / `derive_work_target_float` helpers; documented
  that sustained-vs-spike is the caller's `SustainedLoadTracker` call,
  not a static derivation. The `redis-rate-limiter` adoption guide now
  derives its sustained refill rate from the work zone.

### Added (v0.3.0 candidate)

- **Executive band package** (`substrate.executive`) — the resistance band made
  operational as a decision engine. Two named lenses on one utilization value —
  `LoadZone` (the load lens: IDLE/RECREATION/WORK/PEAKING/WARNING/DANGER on the
  symmetric φ-conjugate ladder) and `CyclePhase` (the cycle lens: ASCENDING/PIVOT/
  PAST_PIVOT over the 24-step work span) — with `classify_load_zone` /
  `classify_cycle_phase`. Levels are geometric; consequences are temporal (no
  spike-tolerance field — that belongs to the `SustainedLoadTracker`). A
  structurally-validated `BandProfile` (R1–R5: ordering, φ-anchors, conjugate sum,
  symmetry, RESISTANCE tighten-only), the `Quantity`/`Cycle`/`ResourceKind`
  discriminators + `setpoint_for` (RESISTANCE vs WORK bands; GROWTH rejected), and
  `order_index` / `negentropy` (the order-from-disorder emergence metric, `1 −`
  normalised Shannon entropy + its trend). Lifted into the top-level `substrate`
  namespace. 29 conformance tests; pyright clean; pylint 10.00.

- **Multi-scale observation Protocol** ([`spec/multi-scale.md`](spec/multi-scale.md))
  — pluggable `SubstrateScope` Protocol with default `cell` / `node`
  / `org` triple + operator-extensible registry. Hyphenated package
  `substrate.multi_scale` complements the existing single-word
  `substrate.multiscale.aggregator`; the registry's default names
  align with the aggregator's hard-coded enum so the two compose.
- Reference impl at
  [`python/src/substrate/multi_scale/`](python/src/substrate/multi_scale/):
  `ScopeRegistry` enforces unique names, registered-parent constraint,
  and cycle prevention at registration time. `parents_of()` returns
  the upward chain; `default_registry()` returns a fresh registry
  pre-populated with the canonical triple.
- 3 conformance probes covering default-triple-present, pluggable-
  extension, and cycle-rejected scenarios. All pass against the
  Python reference.
- 23 reference-impl unit tests pin every spec § 2/§ 3 clause,
  lifting the suite (further; see test count in CHANGELOG below).

Other v0.2.0 / v0.3.0 candidate items will be tracked here. See
[`docs/preprint/`](docs/preprint/) for the in-flight preprint that ships
alongside the next tag.

## [0.1.0] — pending tag

> Update the date above to the actual tag date when `git tag v0.1.0` is pushed.

The initial public release. Substrate-alignment ships as three coordinated
deliverables: language-neutral specifications, a machine-checkable
conformance suite, and a Python reference implementation. Together they let
multi-entity agent systems make verifiable alignment claims that survive
procurement-grade review.

### Added

#### Specifications and conformance
- Six normative specifications under [`spec/`](spec/): `operating-mode.md`,
  `npg-gate-protocol.md`, `drift-signals.md`,
  `runaway-power-prevention.md`, `four-options-matrix.md`, and the
  `conformance-criteria.md` witness contract.
- Conformance probe runner under
  [`python/src/substrate/conformance/`](python/src/substrate/conformance/)
  — consumes YAML probes, dispatches per-spec handlers, ships a CLI
  entry point at `python -m substrate.conformance` and a console-script
  `substrate-conformance`.
- 22 bundled conformance probes covering `operating-mode` (5),
  `npg-gate-protocol` (4), `drift-signals` (3),
  `runaway-power-prevention` (8 across mechanisms 2/3/4/5), and
  `four-options-matrix` (1). All pass against the Python reference.
- The probe-runner schema (`spec`, `spec_version`, `scenario`,
  `required`, `metadata`, `setup`, `input`, `expected`) documented at
  [`conformance/README.md`](conformance/README.md).

#### Python reference implementation
- Top-level vocabulary types: `SubstrateMode`, `AlignmentVector`,
  `SubstrateMetadata`, `EntityRef`, plus the `SUBSTRATE_MODES` constant.
- Host-integration surface: `SubstrateMetadataStore` Protocol plus the
  zero-dependency `InMemorySubstrateMetadataStore` default
  implementation.
- Alignment-vector primitives: `AlignmentWeights`,
  `compute_alignment_vector`, `compute_net_potential`,
  `auto_classify_mode`.
- `AlignmentRefresher` — coordinator that folds a single signal-source
  component into the merged vector under the storage Protocol.
- `ResistanceBand` primitive — the productive-resistance band
  classifier (lower bound `1/3`, upper bound `1/φ²`), with `classify`,
  `assess`, `recommend_scaling_factor`, and `ResistanceBandAssessment`.
- Band-derived threshold helpers (`derive_threshold`,
  `derive_soft_limit`, `derive_hard_limit`, `derive_target`,
  `derive_batch_size`, `derive_retry_cap`, `assess_utilization`,
  `BandPosition`).
- `NetPotentialGainGate` Protocol plus `DefaultNetPotentialGainGate`
  reference implementation, `RaiseOnNegativeGate` adapter, and
  `NetPotentialGainEvaluation` frozen result type. Gate composes the
  `SubstrateMetadataStore` Protocol and accepts both typed (`EntityRef`)
  and legacy (entity-id string) caller forms.
- Sub-packages: `cadence`, `audit`, `artifact`, `capability`,
  `cognition`, `conformance`, `cross_entity`,
  `cultural_infrastructure`, `defensive`, `discovery`, `drift`,
  `encapsulating_context`, `etiquette`, `exposure`, `game_theory`,
  `governor`, `growth`, `halt`, `harness`, `hierarchy`, `identity`,
  `inversion`, `metrics`, `multiscale`, `murmuration`, `offense`,
  `pair_coupling`, `performance_budget`, `progress_signaling`,
  `progression`, `realization`, `reciprocity`, `revenue`, `signals`,
  `state_layer`, `status`, `tells`, `training`, `trust`, `voting`,
  `workflow`.
- `pyyaml` available as an optional dependency under the `yaml` extra
  (used by the conformance runner).

#### Examples
- Six runnable end-to-end snippets under
  [`python/examples/`](python/examples/):
  - `01_npg_gate.py` — positive / negative / insufficient verdicts;
    `RaiseOnNegativeGate` adapter.
  - `02_resistance_band.py` — classification + derived thresholds.
  - `03_alignment_refresher.py` — folding signal-source updates.
  - `04_metadata_store.py` — Protocol implementation pattern.
  - `05_halt_and_escalate.py` — full halt protocol with audit chain.
  - `06_full_governor_loop.py` — composition pattern: refresh → gate →
    classify → ledger.

#### Documentation
- Engineering concept docs under [`docs/concepts/`](docs/concepts/)
  covering every primitive category: operating-mode,
  alignment-refresher, NPG gate, resistance band, drift-signals,
  audit-chain, halt-and-escalate, pair-coupling, runaway-power
  prevention, four-options-matrix.
- Framework integration recipes under
  [`docs/adoption/`](docs/adoption/): FastAPI permission gate, Django
  permission gate (CBV + DRF variants), Celery task gate, Temporal
  workflow halt-and-escalate, Redis-backed rate limiter from
  `ResistanceBand`, SQLAlchemy implementation of the
  `SubstrateMetadataStore` Protocol, Postgres-backed audit chain with
  peer-witness signing.
- Anonymised production-deployment narrative at
  [`docs/case-studies/system9.md`](docs/case-studies/system9.md) —
  operating-mode distribution, gate verdict mix, drift-signal cadence,
  halt-and-escalate frequency, resistance-band coverage, audit-chain
  operation at scale, and the three load-bearing properties worth
  surfacing for any team replicating the pattern.

#### Repository plumbing
- CI on every push and PR, matrix on Python 3.11 / 3.12 / 3.13 / 3.14.
  Steps: pylint, pyright strict, pytest, the conformance probe suite,
  and every bundled example.
- PyPI trusted-publish workflow on `v*` tags.
- Dependabot for GitHub Actions and pip.
- PR template + bug-report and feature-request issue forms.

### Verified at tag time
- 2315 unit tests passing across the Python package.
- 22 / 22 conformance probes passing against the reference implementation.
- Pyright strict: 0 errors, 0 warnings, 0 informations on the
  production surface.
- Pylint: 10.00 / 10 across the production surface and the test suite.
- All six bundled examples run to completion with exit code 0.
- CI matrix passing on Python 3.11, 3.12, 3.13, 3.14 including the
  conformance and examples steps.
- Federal-procurement test: zero references to internal System9
  documents, internal subsystem names, or `infinity-code` / `.claude/`
  paths anywhere in source or test files.

[Unreleased]: https://github.com/System9ai/substrate-alignment/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/System9ai/substrate-alignment/releases/tag/v0.1.0
