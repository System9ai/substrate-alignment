# Changelog

All notable changes to substrate-alignment will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Repository skeleton: top-level project metadata, Python package scaffold,
  CI and PyPI publish workflows, stub specification and conformance directories.
- Vocabulary types: `SubstrateMode`, `AlignmentVector`, `SubstrateMetadata`,
  `EntityRef`, plus the `SUBSTRATE_MODES` constant.
- Host-integration surface: `SubstrateMetadataStore` Protocol plus the
  zero-dependency `InMemorySubstrateMetadataStore` default implementation.
- Alignment-vector primitives: `AlignmentWeights`, `compute_alignment_vector`,
  `compute_net_potential`, `auto_classify_mode`.
- `AlignmentRefresher` — coordinator that folds a single signal-source
  component into the merged vector under the storage Protocol.
- `ResistanceBand` primitive — the productive-resistance band classifier
  (lower bound `1/3`, upper bound `1/φ²`), with `classify`, `assess`,
  `recommend_scaling_factor`, and `ResistanceBandAssessment`.
- Band-derived threshold helpers (`derive_threshold`, `derive_soft_limit`,
  `derive_hard_limit`, `derive_target`, `derive_batch_size`, `derive_retry_cap`,
  `assess_utilization`, `BandPosition`).
- `NetPotentialGainGate` Protocol plus `DefaultNetPotentialGainGate` reference
  implementation, `RaiseOnNegativeGate` adapter, and
  `NetPotentialGainEvaluation` frozen result type. Gate composes the
  `SubstrateMetadataStore` Protocol and accepts both typed (`EntityRef`) and
  legacy (entity-id string) caller forms.
- Sub-packages: `cadence`, `audit`, `artifact`, `capability`, `cognition`,
  `conformance`, `cross_entity`, `cultural_infrastructure`, `defensive`,
  `discovery`, `drift`, `encapsulating_context`, `etiquette`, `exposure`,
  `game_theory`, `governor`, `growth`, `halt`, `harness`, `hierarchy`,
  `identity`, `inversion`, `metrics`, `multiscale`, `murmuration`, `offense`,
  `pair_coupling`, `performance_budget`, `progress_signaling`, `progression`,
  `realization`, `reciprocity`, `revenue`, `signals`, `state_layer`, `status`,
  `tells`, `training`, `trust`, `voting`, `workflow`.

- Six normative specifications under `spec/`: `operating-mode.md`,
  `npg-gate-protocol.md`, `drift-signals.md`, `runaway-power-prevention.md`,
  `four-options-matrix.md`, and the updated `conformance-criteria.md`.
- Conformance probe runner under `python/src/substrate/conformance/` —
  consumes YAML probes, dispatches per-spec handlers, ships a CLI
  entry point at `python -m substrate.conformance`.
- 12 bundled conformance probes covering `operating-mode`,
  `npg-gate-protocol`, and `runaway-power-prevention` (mechanism 4).
  All pass against the Python reference implementation.
- Four runnable examples under `python/examples/`: NPG gate (positive /
  negative / insufficient verdicts), resistance band (classification +
  derived thresholds), alignment refresher (component-merge flow),
  metadata-store Protocol (in-memory default + user-supplied
  implementation).
- Engineering concept docs under `docs/concepts/`: operating-mode, NPG
  gate, resistance band, runaway-power prevention.
- Adoption recipes under `docs/adoption/`: FastAPI permission gate,
  Redis-backed rate limiter from `ResistanceBand`, Celery task gate
  decorator, and a SQLAlchemy implementation of the
  `SubstrateMetadataStore` Protocol.
- Engineering concept docs covering every primitive category named in
  `spec/`: operating-mode, alignment-refresher, NPG gate, resistance
  band, drift-signals, audit-chain, halt-and-escalate, pair-coupling,
  runaway-power prevention, four-options-matrix.
- Anonymised production-deployment narrative at
  `docs/case-studies/system9.md` — operating-mode distribution, gate
  verdict mix, drift-signal cadence, halt-and-escalate frequency,
  resistance-band coverage, audit-chain operation at scale, and the
  three load-bearing properties worth surfacing for any team replicating
  the pattern.
- `pyyaml` added as an optional dependency under the `yaml` extra (used
  by the conformance runner).
- Probe-runner handlers for every runaway-power-prevention mechanism
  (audit-chain hash continuity, halt-and-escalate state transitions,
  pair-coupling state machine, plus the existing resistance-band
  handler), the drift-signals primitive (feeding the
  `DriftPatternMatcher`), and the four-options-matrix enum-pinning
  scenario. The runner now dispatches five spec slugs.
- 10 additional conformance probes (total now 22): three for
  halt-and-escalate state transitions, one for audit-chain hash
  continuity, two for pair-coupling state-machine transitions (legal
  + illegal), three for drift-pattern detection (extractive-gain,
  self-reference amplifier, false-positive-free clean signals), one
  for four-options-matrix canonical enum values.
- Examples 05 (full halt-and-escalate flow with audit chain) and 06
  (full governor loop: refresh → gate → classify → ledger) under
  `python/examples/`. Bundled examples now total six.

### Verified
- 2315 unit tests passing across the Python package.
- 22 / 22 conformance probes passing against the reference implementation.
- Pyright strict: 0 errors, 0 warnings, 0 informations on the production surface.
- Pylint: 10.00/10 across the production surface and the test suite.
- All six bundled examples run to completion with exit 0.
- CI matrix passing on Python 3.11, 3.12, 3.13, 3.14.
- Federal-procurement test: zero references to internal System9 documents,
  internal subsystem names, or `infinity-code`/`.claude/` paths anywhere in
  source or test files.

[Unreleased]: https://github.com/System9ai/substrate-alignment/commits/main
