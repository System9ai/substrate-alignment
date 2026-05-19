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

### Verified
- 2315 unit tests passing across the Python package.
- Pyright strict: 0 errors, 0 warnings, 0 informations on the production surface.
- Pylint: 10.00/10 across the production surface and the test suite.
- CI matrix passing on Python 3.11, 3.12, 3.13, 3.14.

[Unreleased]: https://github.com/System9ai/substrate-alignment/commits/main
