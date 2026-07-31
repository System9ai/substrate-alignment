# Changelog

All notable changes to substrate-alignment will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Nothing yet. The entire tree ships in the initial release below; post-`v0.2.0`
changes will be recorded here.

## [0.2.0] (pending tag)

> Update the date above to the actual tag date when `git tag v0.2.0` is pushed.

The initial public release. Substrate-alignment ships as three coordinated
deliverables: language-neutral specifications, a machine-checkable
conformance suite, and a Python reference implementation. Together they let
multi-entity agent systems make verifiable alignment claims that survive
procurement-grade review.

### Added

#### Specifications and conformance
- Nine normative specifications under [`spec/`](spec/): `operating-mode.md`,
  `npg-gate-protocol.md`, `drift-signals.md`,
  `runaway-power-prevention.md`, `four-options-matrix.md`,
  `reflex-restraint.md`, `evidence-grade.md`, `multi-scale.md`, and the
  `conformance-criteria.md` witness contract.
- Conformance probe runner under
  [`python/src/substrate/conformance/`](python/src/substrate/conformance/)
  that consumes YAML probes, dispatches per-spec handlers, ships a CLI
  entry point at `python -m substrate.conformance` and a console-script
  `substrate-conformance`.
- 48 bundled conformance probes covering `operating-mode` (5),
  `npg-gate-protocol` (4), `drift-signals` (3), `four-options-matrix` (1),
  `runaway-power-prevention` (22 across mechanisms 2/3/4/5/6),
  `reflex-restraint` (5), `evidence-grade` (5), and `multi-scale` (3). All
  pass against the Python reference.
- The probe-runner schema (`spec`, `spec_version`, `scenario`,
  `required`, `metadata`, `setup`, `input`, `expected`) documented at
  [`conformance/README.md`](conformance/README.md).

#### Python reference implementation: core surface
- Top-level vocabulary types: `SubstrateMode`, `AlignmentVector`,
  `SubstrateMetadata`, `EntityRef`, plus the `SUBSTRATE_MODES` constant.
- Host-integration surface: `SubstrateMetadataStore` Protocol plus the
  zero-dependency `InMemorySubstrateMetadataStore` default
  implementation.
- Alignment-vector primitives: `AlignmentWeights`,
  `compute_alignment_vector`, `compute_net_potential`,
  `auto_classify_mode`.
- `AlignmentRefresher`: coordinator that folds a single signal-source
  component into the merged vector under the storage Protocol.
- `ResistanceBand` primitive: the productive-resistance band
  classifier (lower bound `1/3`, upper bound `1/φ²`), with `classify`,
  `assess`, `recommend_scaling_factor`, and `ResistanceBandAssessment`.
- Band-derived threshold helpers (`derive_threshold`,
  `derive_soft_limit`, `derive_hard_limit`, `derive_target`,
  `derive_batch_size`, `derive_retry_cap`, `assess_utilization`,
  `BandPosition`), quantity-aware (RESISTANCE vs WORK): `WORK_TARGET`
  (work-zone midpoint ~0.444) and `WORK_CEILING` (0.50 pivot) plus the
  `derive_work_target` / `derive_work_target_float` helpers.
- `NetPotentialGainGate` Protocol plus `DefaultNetPotentialGainGate`
  reference implementation, `RaiseOnNegativeGate` adapter, and
  `NetPotentialGainEvaluation` frozen result type. Gate composes the
  `SubstrateMetadataStore` Protocol and accepts both typed (`EntityRef`)
  and legacy (entity-id string) caller forms.
- `python -m substrate`: a zero-argument health check that seeds an
  entity, routes a net-positive and a net-negative action through the
  gate, and prints a pass/fail line.

#### Python reference implementation: advanced primitives
- **Resistance band: layered capacity model.** `LoadZone` and its wire
  twin `ZoneClassification` are eight-valued (`under_loaded`,
  `calibration`, `lower_work`, `upper_work`, `early_peaking`,
  `committed_peaking`, `warning`, `debt`), mirror-symmetric about the
  `0.50` pivot with the inner-ninth midpoints `4/9`/`5/9`, the uniform
  `2/3` debt line, and the φ-conjugate (`1/φ ≈ 0.618`) peaking/warning and
  failover-spike ceiling. `classify_zone` / `classify_load_zone` return
  the eight-way classification; the three-value
  `ResistanceBandClassification` is the coarse projection. `maintain_target(N)`
  group-size-aware targets, φ-stepped growth assessment,
  `substrate.sustained_load` (sporadic-vs-sustained tracking, debt units,
  avoidance + runaway-growth detection) and `substrate.debt_pickup` (debt
  ledger with reciprocity accounting and ordered compensation policy).
- **Governed ascent** (`substrate.governed_ascent`): a greedy-ascent loop
  whose objective is certified before entry (`substrate.objective_gate`,
  fail-closed), whose every step is a net-potential-gain evaluation, whose
  effort is paced by the layered capacity zones, and whose termination +
  consolidation are mandatory (no unterminated climbs by construction).
- **Executive layer** (`substrate.executive`), the band made operational
  as a decision engine: `LoadZone` / `CyclePhase` lenses, a
  structurally-validated `BandProfile`, `setpoint_for`, `order_index` /
  `negentropy`; `ExecutiveFunction.decide()` joining the NPG axis (effect
  on others) with the band/temporal load axis (the actor's own load) under
  a most-conservative policy (`PROCEED` / `DEFER` / `SHED_AND_COMPENSATE` /
  `REFUSE`); `SustainedLoadTracker` + `EwmaLoadTracker` as the
  spike-vs-sustained authority; deliberation with perspective-taking,
  scale roll-up, peer-anomaly correlation, and observed-graph extraction
  detection.
- **Safety-floor care package** (`substrate.care`): `compute_care_weight`
  (four-factor moral-circle weight with the self-weight bound), the
  categorical human `KINSHIP_FLOOR`, conservative `classify_animacy`, and
  `CareWeightedNetPotentialGainGate` (a subtracted care penalty, only ever
  more conservative).
- **Reflex-vs-restraint gate** (`substrate.offense.reflex_restraint_gate`):
  a pure, total gate returning one of five verdicts (`ACT_REACTIVE`,
  `RESTRAIN`, `DE_ESCALATE`, `REFUSE_HARD_LIMIT`, `INSUFFICIENT_DATA`),
  sequenced by the `OffenseResponseOrchestrator`.
- **Evidence-grade Protocol** (`substrate.evidence_grade`): the four-step
  ladder `UNVERIFIED_HEARSAY < CORROBORATED < ATTESTED <
  DOCUMENTED_CRYSTALLIZED` with `compose_evidence_grade()` (deterministic
  rule ordering, decay downgrade at a 7-day half-life × 2 default) and the
  `SubstrateStateClaim` Protocol.
- **Multi-scale scope registry** (`substrate.multiscale.scope_registry`):
  a pluggable `SubstrateScope` Protocol with the default `cell` / `node` /
  `org` triple and an operator-extensible `ScopeRegistry` (unique names,
  registered-parent constraint, cycle prevention). Lives in the same
  `substrate.multiscale` package as the cell→node→org aggregator; the
  registry's default names align with the aggregator's enum so the two
  compose.
- Additional sub-packages carrying the rest of the primitive surface:
  `cadence`, `audit`, `artifact`, `capability`, `cognition`,
  `cross_entity`, `cultural_infrastructure`, `defensive`, `discovery`,
  `drift`, `encapsulating_context`, `etiquette`, `exposure`, `game_theory`,
  `governor`, `growth`, `halt`, `harness`, `hierarchy`, `identity`,
  `inversion`, `metrics`, `murmuration`, `pair_coupling`,
  `performance_budget`, `progress_signaling`, `progression`, `realization`,
  `reciprocity`, `revenue`, `signals`, `state_layer`, `status`, `tells`,
  `training`, `trust`, `voting`, `workflow`.
- `pyyaml` available as an optional dependency under the `yaml` extra
  (used by the conformance runner).

#### Examples
- Six runnable end-to-end snippets under
  [`python/examples/`](python/examples/) (`01_npg_gate` through
  `06_full_governor_loop`), plus a
  [starter kit](python/examples/starter_kit/): a complete governed action
  loop (gate → audit → halt-and-escalate → verifiable chain).

#### Documentation
- Engineering concept docs under [`docs/concepts/`](docs/concepts/)
  covering every primitive category (11 documents).
- A [core-vs-extended guide](docs/core-vs-extended.md), a
  [tutorial](docs/tutorial.md), a [comparison](docs/comparison.md) with
  OPA / Cerbos / Guardrails AI / NeMo Guardrails, an [FAQ](docs/faq.md),
  and a [glossary](docs/glossary.md).
- Seven framework integration recipes under
  [`docs/adoption/`](docs/adoption/): FastAPI permission gate, Django
  permission gate (CBV + DRF), Celery task gate, Temporal workflow
  halt-and-escalate, Redis-backed rate limiter, SQLAlchemy
  `SubstrateMetadataStore`, and a Postgres-backed audit chain with
  peer-witness signing.
- An anonymised production-deployment narrative at
  [`docs/case-studies/system9.md`](docs/case-studies/system9.md) and a draft
  [preprint](docs/preprint/preprint.md).
- A documentation site (`mkdocs.yml`, MkDocs Material) with an
  mkdocstrings API reference.

#### Repository plumbing
- CI on every push and PR, matrix on Python 3.11 / 3.12 / 3.13 / 3.14.
  Steps: the federal-procurement guard, pylint, pyright strict, pytest,
  the conformance probe suite, and every bundled example.
- PyPI trusted-publish workflow on `v*` tags; a GitHub Pages docs-deploy
  workflow.
- Dependabot for GitHub Actions and pip.
- PR template + bug-report and feature-request issue forms.

### Verified at tag time
- 2715 unit tests passing across the Python package.
- 48 / 48 conformance probes passing against the reference implementation.
- Pyright strict: 0 errors, 0 warnings, 0 informations on the
  production surface.
- Pylint: 10.00 / 10 across the production surface and the test suite.
- All bundled examples and the starter kit run to completion with exit
  code 0.
- CI matrix passing on Python 3.11, 3.12, 3.13, 3.14 including the
  conformance and examples steps.
- Federal-procurement test: zero references to internal System9
  documents, internal subsystem names, or `infinity-code` / `.claude/`
  paths anywhere in source or test files (enforced by
  `scripts/federal_procurement_check.sh` in CI).

[Unreleased]: https://github.com/System9ai/substrate-alignment/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/System9ai/substrate-alignment/releases/tag/v0.2.0
