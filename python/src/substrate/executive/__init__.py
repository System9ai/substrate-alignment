"""The executive layer: the band as a decision engine.

The resistance band, made operational as the substrate's executive function: the
corrected symmetric ladder (geometric levels, temporal consequences), the
quantity/scale discipline, the temporal sustained-vs-spike authority, and the
faculties built on top: deliberation (scenario rollout + perspective-taking), the
state query, the scale roll-up, peer awareness + alarm propagation, the order
metric, and observed-graph extraction detection.

Curated exports: import the names, not deep module paths.
"""
from __future__ import annotations

from substrate.executive._trajectory import TrajectoryClass
from substrate.executive.band import (
    BAND_TOLERANCE,
    DEFAULT_BAND_PROFILE,
    TWO_THIRDS,
    BandProfile,
    BandProfileInvalid,
    CyclePhase,
    LoadZone,
    classify_cycle_phase,
    classify_load_zone,
    validate_band_profile,
    zone_to_legacy,
)
from substrate.executive.deliberation import (
    ActionDelta,
    CandidateAction,
    CandidateEvaluation,
    DeliberationOutcome,
    DeliberationResult,
    EntityFrame,
    PerspectiveImpact,
    deliberate,
    perspective_impact,
)
from substrate.executive.cause import (
    Cause,
    HallmarkReport,
    HallmarkSource,
    infer_cause,
    max_cause,
)
from substrate.executive.executive_function import (
    Action,
    Disposition,
    ExecutiveFunction,
    ExecutiveVerdict,
    JoinPolicy,
)
from substrate.executive.negentropy import (
    NegentropyDirection,
    NegentropyReport,
    negentropy,
    order_index,
)
from substrate.executive.observed_graph import (
    EntityRollup,
    ExtractionReport,
    NpgEdge,
    detect_extraction,
)
from substrate.executive.peer_alarm import (
    AlarmAssessment,
    AlarmDisposition,
    HerdVerdict,
    PeerAlarm,
    PeerAnomaly,
    assess_alarm,
    correlate_anomalies,
    heeded_alarms,
)
from substrate.executive.quantities import (
    Cycle,
    GrowthNotADecisionBand,
    Quantity,
    ResourceKind,
    setpoint_for,
)
from substrate.executive.roll_up import (
    MemberLoad,
    RollUpError,
    ScaleAggregate,
    roll_up,
)
from substrate.executive.scale import (
    ExecutiveScale,
    ScaleAxis,
    axis_of,
    entity_parent,
    physical_parent,
)
from substrate.executive.state_query import (
    EffortState,
    EnergyState,
    EntityStateReport,
    StateObservation,
    TrajectoryDirection,
    integrate_state,
)
from substrate.executive.utilization_source import (
    CallableUtilizationSource,
    UtilizationFn,
    UtilizationSource,
)
from substrate.executive.temporal import (
    DEFAULT_EWMA_ALPHA,
    DEFAULT_SUSTAIN_COUNT,
    EwmaLoadTracker,
    LoadTrend,
    SustainedLoadTracker,
)

__all__ = [
    "Action",
    "ActionDelta",
    "AlarmAssessment",
    "AlarmDisposition",
    "BAND_TOLERANCE",
    "BandProfile",
    "BandProfileInvalid",
    "CallableUtilizationSource",
    "CandidateAction",
    "CandidateEvaluation",
    "Cause",
    "Cycle",
    "CyclePhase",
    "DEFAULT_BAND_PROFILE",
    "DEFAULT_EWMA_ALPHA",
    "DEFAULT_SUSTAIN_COUNT",
    "DeliberationOutcome",
    "DeliberationResult",
    "Disposition",
    "EffortState",
    "EnergyState",
    "EntityFrame",
    "EntityRollup",
    "EntityStateReport",
    "EwmaLoadTracker",
    "ExecutiveFunction",
    "ExecutiveScale",
    "ExecutiveVerdict",
    "ExtractionReport",
    "GrowthNotADecisionBand",
    "HallmarkReport",
    "HallmarkSource",
    "HerdVerdict",
    "JoinPolicy",
    "LoadTrend",
    "LoadZone",
    "MemberLoad",
    "NegentropyDirection",
    "NegentropyReport",
    "NpgEdge",
    "PeerAlarm",
    "PeerAnomaly",
    "PerspectiveImpact",
    "Quantity",
    "ResourceKind",
    "RollUpError",
    "ScaleAggregate",
    "ScaleAxis",
    "StateObservation",
    "SustainedLoadTracker",
    "TrajectoryClass",
    "TrajectoryDirection",
    "TWO_THIRDS",
    "UtilizationFn",
    "UtilizationSource",
    "assess_alarm",
    "axis_of",
    "classify_cycle_phase",
    "classify_load_zone",
    "correlate_anomalies",
    "deliberate",
    "detect_extraction",
    "entity_parent",
    "heeded_alarms",
    "infer_cause",
    "integrate_state",
    "max_cause",
    "negentropy",
    "order_index",
    "perspective_impact",
    "physical_parent",
    "roll_up",
    "setpoint_for",
    "validate_band_profile",
    "zone_to_legacy",
]
