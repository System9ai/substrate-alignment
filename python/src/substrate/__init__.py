"""Substrate-alignment — reference Python implementation.

substrate-alignment is an open standard, reference implementation, and
machine-checkable conformance suite for primitives used in multi-entity
agent systems. This package is one conforming implementation; the
language-neutral specifications live alongside it in the ``spec/``
directory of the source repository.

The top-level surface re-exports the vocabulary types and the most
commonly used primitives. Sub-packages (``substrate.cadence``,
``substrate.audit``, ``substrate.governor`` …) carry the rest of the
primitive surface.

Project home: https://github.com/System9ai/substrate-alignment
"""
from __future__ import annotations

from substrate.alignment_computer import (
    DEFAULT_ALIGNMENT_WEIGHTS,
    DEFAULT_LONG_CYCLE_THRESHOLD,
    DEFAULT_MIXED_THRESHOLD,
    AlignmentWeights,
    auto_classify_mode,
    compute_alignment_vector,
    compute_net_potential,
)
from substrate.alignment_refresher import (
    ALIGNMENT_COMPONENTS,
    AlignmentRefresher,
)
from substrate.evidence_grade.composer import (
    EVIDENCE_GRADES,
    EvidenceAttestation,
    EvidenceComposition,
    EvidenceGrade,
    EvidenceGradeConfig,
    SubstrateStateClaim,
    compose_evidence_grade,
)
from substrate.multi_scale.scope_registry import (
    CELL_SCOPE,
    DEFAULT_SCOPES,
    NODE_SCOPE,
    ORG_SCOPE,
    ConcreteScope,
    ScopeRegistry,
    SubstrateScope,
    default_registry,
)
from substrate.net_potential_gain_gate import (
    ACTION_KIND_HEURISTICS,
    DEFAULT_POSITIVE_THRESHOLD,
    NPG_VERDICTS,
    DefaultNetPotentialGainGate,
    NetPotentialGainEvaluation,
    NetPotentialGainGate,
    NetPotentialGainNegative,
    NetPotentialGainVerdict,
    RaiseOnNegativeGate,
)
from substrate.executive import (
    BandProfile,
    CyclePhase,
    LoadZone,
    Quantity,
    classify_cycle_phase,
    classify_load_zone,
    negentropy,
    order_index,
    setpoint_for,
)
from substrate.resistance_band import (
    DEFAULT_CONFIG,
    LOWER_BOUND,
    PHI,
    PHI_SQUARED,
    RESISTANCE_BAND_CLASSIFICATIONS,
    TARGET,
    UPPER_BOUND,
    ResistanceBandAssessment,
    ResistanceBandClassification,
    ResistanceBandConfig,
    assess,
    classify,
    recommend_scaling_factor,
)
from substrate.types import (
    SUBSTRATE_MODES,
    AlignmentVector,
    EntityRef,
    InMemorySubstrateMetadataStore,
    SubstrateMetadata,
    SubstrateMetadataStore,
    SubstrateMode,
)

__version__ = "0.1.0.dev0"

__all__ = [
    # Vocabulary types
    "SUBSTRATE_MODES",
    "AlignmentVector",
    "EntityRef",
    "SubstrateMetadata",
    "SubstrateMode",
    # Storage Protocol + default impl
    "InMemorySubstrateMetadataStore",
    "SubstrateMetadataStore",
    # Alignment computer
    "AlignmentWeights",
    "DEFAULT_ALIGNMENT_WEIGHTS",
    "DEFAULT_LONG_CYCLE_THRESHOLD",
    "DEFAULT_MIXED_THRESHOLD",
    "auto_classify_mode",
    "compute_alignment_vector",
    "compute_net_potential",
    # Alignment refresher
    "ALIGNMENT_COMPONENTS",
    "AlignmentRefresher",
    # Evidence-grade ladder (spec v0.2.0)
    "EVIDENCE_GRADES",
    "EvidenceAttestation",
    "EvidenceComposition",
    "EvidenceGrade",
    "EvidenceGradeConfig",
    "SubstrateStateClaim",
    "compose_evidence_grade",
    # Multi-scale scope registry (spec v0.3.0)
    "CELL_SCOPE",
    "ConcreteScope",
    "DEFAULT_SCOPES",
    "NODE_SCOPE",
    "ORG_SCOPE",
    "ScopeRegistry",
    "SubstrateScope",
    "default_registry",
    # NPG gate
    "ACTION_KIND_HEURISTICS",
    "DEFAULT_POSITIVE_THRESHOLD",
    "DefaultNetPotentialGainGate",
    "NPG_VERDICTS",
    "NetPotentialGainEvaluation",
    "NetPotentialGainGate",
    "NetPotentialGainNegative",
    "NetPotentialGainVerdict",
    "RaiseOnNegativeGate",
    # Resistance band
    "DEFAULT_CONFIG",
    "LOWER_BOUND",
    "PHI",
    "PHI_SQUARED",
    "RESISTANCE_BAND_CLASSIFICATIONS",
    "ResistanceBandAssessment",
    "ResistanceBandClassification",
    "ResistanceBandConfig",
    "TARGET",
    "UPPER_BOUND",
    "assess",
    "classify",
    "recommend_scaling_factor",
    # Executive band (the band as a decision engine)
    "BandProfile",
    "CyclePhase",
    "LoadZone",
    "Quantity",
    "classify_cycle_phase",
    "classify_load_zone",
    "negentropy",
    "order_index",
    "setpoint_for",
    # Version
    "__version__",
]
