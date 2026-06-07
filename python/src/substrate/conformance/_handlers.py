"""Per-spec probe handlers for the bundled conformance suite.

Each handler accepts the parsed probe data and executes the scenario
against the in-package primitives. It raises :class:`ProbeFailure`
(re-exported as ``substrate.conformance.ProbeFailure``) when the
observed behaviour does not match the probe's ``expected`` clause.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from substrate.alignment_computer import (
    AlignmentWeights,
    auto_classify_mode,
    compute_alignment_vector,
    compute_net_potential,
)
from substrate.audit.substrate_trace import SubstrateTraceLedger
from substrate.conformance._errors import ProbeFailure
from substrate.drift.drift_pattern_matcher import DriftPatternMatcher
from substrate.evidence_grade.composer import (
    EvidenceAttestation,
    EvidenceGrade,
    compose_evidence_grade,
)
from substrate.multi_scale.scope_registry import (
    ConcreteScope,
    ScopeRegistry,
)
from substrate.halt.halt_escalate_protocol import (
    HaltAndEscalateProtocol,
    HaltObservation,
    HaltReason,
    HaltState,
)
from substrate.governed_ascent import (
    ClimbTermination,
    GovernedAscentLoop,
    StepProposal,
)
from substrate.net_potential_gain_gate import (
    DefaultNetPotentialGainGate,
    NetPotentialGainEvaluation,
    NetPotentialGainVerdict,
)
from substrate.objective_gate import (
    ClimbObjective,
    ObjectiveCertification,
    ObjectiveCertificationVerdict,
)
from substrate.offense.reflex_restraint_gate import (
    RESTRAINT_VERDICTS,
    ReflexRestraintGate,
    RestraintGateConfig,
    RestraintVerdict,
    ThreatAppraisal,
)
from substrate.pair_coupling.state_machine import (
    IllegalStateTransition,
    PairCouplingState,
    PairCouplingStateMachine,
    PairCouplingTrigger,
)
from substrate.resistance_band import (
    ResistanceBandClassification,
    ResistanceBandConfig,
    ZoneClassification,
    assess_growth_step,
    classify,
    classify_zone,
    maintain_target,
)
from substrate.sustained_load import (
    LoadObservation,
    LoadTrend,
    SustainedLoadTracker,
)
from substrate.types import (
    AlignmentVector,
    EntityRef,
    InMemorySubstrateMetadataStore,
    SubstrateMode,
)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ProbeFailure(message)


def _refs(items: Sequence[Mapping[str, Any]]) -> tuple[EntityRef, ...]:
    return tuple(
        EntityRef(entity_type=str(it["entity_type"]), entity_id=str(it["entity_id"]))
        for it in items
    )


# ---------------------------------------------------------------------------
# operating-mode
# ---------------------------------------------------------------------------


def handle_operating_mode(probe: Mapping[str, Any]) -> None:
    """Dispatch on ``input.fn`` for the operating-mode primitives."""
    inp = probe.get("input", {})
    expected = probe.get("expected", {})
    fn = inp.get("fn")
    if fn == "compute_alignment_vector":
        vec = compute_alignment_vector(**inp["kwargs"])
        for name, value in expected["vector"].items():
            _require(
                abs(getattr(vec, name) - float(value)) < 1e-9,
                f"vector.{name}: expected {value}, got {getattr(vec, name)}",
            )
    elif fn == "compute_net_potential":
        vec = AlignmentVector(**inp["vector"])
        weights = AlignmentWeights(**inp["weights"]) if inp.get("weights") else None
        np_value = compute_net_potential(vec, weights=weights)
        _require(
            abs(np_value - float(expected["net_potential"])) < 1e-9,
            f"net_potential: expected {expected['net_potential']}, got {np_value}",
        )
    elif fn == "auto_classify_mode":
        mode = auto_classify_mode(
            float(inp["net_potential"]),
            long_cycle_threshold=float(inp.get("long_cycle_threshold", 0.70)),
            mixed_threshold=float(inp.get("mixed_threshold", 0.40)),
        )
        _require(
            mode is SubstrateMode(expected["mode"]),
            f"mode: expected {expected['mode']}, got {mode.value}",
        )
    else:
        raise ProbeFailure(f"unknown operating-mode fn: {fn!r}")


# ---------------------------------------------------------------------------
# reflex-restraint
# ---------------------------------------------------------------------------


def handle_reflex_restraint(probe: Mapping[str, Any]) -> None:
    """Dispatch on ``input.fn`` for the reflex-vs-restraint gate."""
    inp = probe["input"]
    expected = probe["expected"]
    fn = inp.get("fn")
    if fn == "enum_values":
        want = {str(v) for v in expected["verdicts"]}
        _require(
            set(RESTRAINT_VERDICTS) == want,
            f"verdicts: expected {sorted(want)}, "
            f"got {sorted(RESTRAINT_VERDICTS)}",
        )
        return
    if fn == "evaluate":
        cfg = (
            RestraintGateConfig(**inp["config"])
            if inp.get("config")
            else RestraintGateConfig()
        )
        gate = ReflexRestraintGate(config=cfg)
        a = inp["appraisal"]
        appraisal = ThreatAppraisal(
            actor_entity_id=str(a["actor_entity_id"]),
            threat_id=str(a["threat_id"]),
            survival_threat_score=float(a["survival_threat_score"]),
            reactive_action_kind=str(a["reactive_action_kind"]),
            reactive_action_npg=NetPotentialGainVerdict(
                a["reactive_action_npg"]
            ),
            crosses_hard_limit=bool(a.get("crosses_hard_limit", False)),
            has_live_counterparty=bool(a.get("has_live_counterparty", True)),
        )
        decision = gate.evaluate(appraisal)
        _require(
            decision.verdict is RestraintVerdict(expected["verdict"]),
            f"verdict: expected {expected['verdict']}, "
            f"got {decision.verdict.value}",
        )
        return
    raise ProbeFailure(f"unknown reflex-restraint fn: {fn!r}")


# ---------------------------------------------------------------------------
# npg-gate-protocol
# ---------------------------------------------------------------------------


def handle_npg_gate_protocol(probe: Mapping[str, Any]) -> None:
    setup = probe.get("setup", {})
    inp = probe["input"]
    expected = probe["expected"]

    store = InMemorySubstrateMetadataStore()
    for row in setup.get("store", []):
        ref = EntityRef(
            entity_type=str(row["entity_type"]),
            entity_id=str(row["entity_id"]),
        )
        store.upsert(
            ref,
            substrate_mode=SubstrateMode(row.get("substrate_mode", "Mixed")),
            classifier=str(row.get("classifier", "probe")),
            classifier_rationale=str(row.get("classifier_rationale", "")),
            alignment_vector=AlignmentVector(
                trust=float(row.get("trust", 0.5)),
                expertise=float(row.get("expertise", 0.5)),
                capability=float(row.get("capability", 0.5)),
                health=float(row.get("health", 0.5)),
            ),
            net_potential=float(row.get("net_potential", 0.5)),
        )

    gate = DefaultNetPotentialGainGate(
        metadata_store=store,
        positive_threshold=float(setup.get("positive_threshold", 0.05)),
    )
    actor = EntityRef(
        entity_type=str(inp["actor"]["entity_type"]),
        entity_id=str(inp["actor"]["entity_id"]),
    )
    affected = _refs(inp.get("affected_entities", []))
    evaluation = gate.evaluate(
        actor=actor,
        action_kind=str(inp["action_kind"]),
        affected_entities=affected,
        proposed_outcome=inp.get("proposed_outcome", {}),
    )

    _require(
        evaluation.verdict is NetPotentialGainVerdict(expected["verdict"]),
        f"verdict: expected {expected['verdict']}, got {evaluation.verdict.value}",
    )
    if "score_lt" in expected:
        _require(
            evaluation.score < float(expected["score_lt"]),
            f"score: expected < {expected['score_lt']}, got {evaluation.score}",
        )
    if "score_gt" in expected:
        _require(
            evaluation.score > float(expected["score_gt"]),
            f"score: expected > {expected['score_gt']}, got {evaluation.score}",
        )
    if "missing_count" in expected:
        _require(
            len(evaluation.missing_metadata_for) == int(expected["missing_count"]),
            f"missing_count: expected {expected['missing_count']}, "
            f"got {len(evaluation.missing_metadata_for)}",
        )


# ---------------------------------------------------------------------------
# runaway-power-prevention
# ---------------------------------------------------------------------------


def handle_runaway_power_prevention(probe: Mapping[str, Any]) -> None:
    """Dispatch on the mechanism number embedded in the scenario name."""
    inp = probe["input"]
    expected = probe["expected"]
    mechanism = str(inp.get("mechanism", ""))
    if mechanism == "resistance-band":
        _runaway_resistance_band(inp, expected)
    elif mechanism == "sustained-load":
        _runaway_sustained_load(inp, expected)
    elif mechanism == "maintain-target":
        _runaway_maintain_target(inp, expected)
    elif mechanism == "growth-step":
        _runaway_growth_step(inp, expected)
    elif mechanism == "halt-and-escalate":
        _runaway_halt_and_escalate(inp, expected)
    elif mechanism == "audit-chain":
        _runaway_audit_chain(inp, expected)
    elif mechanism == "pair-coupling":
        _runaway_pair_coupling(inp, expected)
    elif mechanism == "governed-ascent":
        _runaway_governed_ascent(inp, expected)
    else:
        raise ProbeFailure(
            f"runaway-power-prevention mechanism not yet wired: {mechanism!r}"
        )


def _runaway_resistance_band(
    inp: Mapping[str, Any], expected: Mapping[str, Any],
) -> None:
    cfg = (
        ResistanceBandConfig(**inp["config"])
        if inp.get("config")
        else None
    )
    utilization = float(inp["utilization"])
    if "classification" in expected:
        classification = classify(utilization, config=cfg)
        _require(
            classification
            is ResistanceBandClassification(expected["classification"]),
            f"classification: expected {expected['classification']}, "
            f"got {classification.value}",
        )
    if "zone" in expected:
        zone = classify_zone(utilization, config=cfg)
        _require(
            zone is ZoneClassification(expected["zone"]),
            f"zone: expected {expected['zone']}, got {zone.value}",
        )


def _runaway_sustained_load(
    inp: Mapping[str, Any], expected: Mapping[str, Any],
) -> None:
    """Layered zone model §2.3 — sporadic-vs-sustained + debt accrual."""
    tracker = SustainedLoadTracker()
    assessment = None
    for i, util in enumerate(inp["utilization_sequence"]):
        assessment = tracker.observe(
            LoadObservation(timestamp=i, utilization=float(util))
        )
    _require(assessment is not None, "utilization_sequence must be non-empty")
    assert assessment is not None
    _require(
        assessment.trend is LoadTrend(expected["trend"]),
        f"trend: expected {expected['trend']}, got {assessment.trend.value}",
    )
    if "debt_accrued" in expected:
        accrued = assessment.accrued_debt_units > 0.0
        _require(
            accrued == bool(expected["debt_accrued"]),
            f"debt_accrued: expected {expected['debt_accrued']}, "
            f"got {accrued} (units={assessment.accrued_debt_units:.4f})",
        )


def _runaway_maintain_target(
    inp: Mapping[str, Any], expected: Mapping[str, Any],
) -> None:
    """Layered zone model §2.4b — group-size-aware maintain target."""
    target = maintain_target(int(inp["group_size"]))
    want = float(expected["target"])
    _require(
        abs(target - want) <= 1e-6,
        f"maintain_target: expected {want}, got {target}",
    )
    if "survivor_at_or_under_debt_line" in expected:
        group = int(inp["group_size"])
        survivor = target + (target / (group - 1)) if group > 1 else target
        ok = survivor <= float(1.0 / 1.618033988749895) + 1e-6
        _require(
            ok == bool(expected["survivor_at_or_under_debt_line"]),
            f"survivor check: projected {survivor:.4f}",
        )


def _runaway_growth_step(
    inp: Mapping[str, Any], expected: Mapping[str, Any],
) -> None:
    """Layered zone model — φ-proportioned growth-step discipline."""
    out = assess_growth_step(
        float(inp["current_capacity"]), float(inp["proposed_capacity"])
    )
    _require(
        out.within_phi == bool(expected["within_phi"]),
        f"within_phi: expected {expected['within_phi']}, "
        f"got {out.within_phi} (ratio={out.step_ratio:.4f})",
    )


def _runaway_halt_and_escalate(
    inp: Mapping[str, Any], expected: Mapping[str, Any],
) -> None:
    """Observe a trigger sequence; assert state transition + refusal flag."""
    protocol = HaltAndEscalateProtocol()
    agent_id = str(inp.get("agent_id", "agent-1"))
    current_state = HaltState(inp.get("current_state", "operating"))
    observations = tuple(
        HaltObservation(
            sequence=int(o.get("sequence", i)),
            timestamp=int(o.get("timestamp", 1_700_000_000 + i)),
            agent_id=agent_id,
            halt_reason=HaltReason(o["halt_reason"]),
            severity=float(o.get("severity", 0.9)),
            evidence=str(o.get("evidence", "")),
        )
        for i, o in enumerate(inp.get("observations", []))
    )
    decision = protocol.evaluate(
        agent_id, observations, current_state=current_state,
    )
    _require(
        decision.next_state is HaltState(expected["next_state"]),
        f"next_state: expected {expected['next_state']}, "
        f"got {decision.next_state.value}",
    )
    if "refuses_consequential_action" in expected:
        _require(
            decision.refuses_consequential_action
            == bool(expected["refuses_consequential_action"]),
            f"refuses_consequential_action: expected "
            f"{expected['refuses_consequential_action']}, "
            f"got {decision.refuses_consequential_action}",
        )
    if "triggering_reason" in expected:
        reasons = tuple(r.value for r in decision.triggering_reasons)
        _require(
            expected["triggering_reason"] in reasons,
            f"triggering_reasons: expected {expected['triggering_reason']} in "
            f"{reasons}",
        )


def _runaway_audit_chain(
    inp: Mapping[str, Any], expected: Mapping[str, Any],
) -> None:
    """Verify hash-chain continuity guarantees for the in-memory ledger."""
    scenario = str(inp.get("scenario", ""))
    if scenario == "hash-continuity":
        # Append a sequence of records and assert each record's
        # ``previous_hash`` equals the prior record's ``record_hash``
        # via ``ledger.verify()``.
        ledger = SubstrateTraceLedger()
        records = inp.get("appends", [])
        for i, r in enumerate(records):
            ledger.append(
                decision_id=str(r.get("decision_id", f"d{i}")),
                decision_kind=str(r.get("decision_kind", "test")),
                permitted=bool(r.get("permitted", True)),
                rationale=str(r.get("rationale", "")),
                epoch_seconds=int(r.get("epoch_seconds", 1_700_000_000 + i)),
                npg_verdict=NetPotentialGainVerdict(
                    r.get("npg_verdict", "net_neutral"),
                ),
                resistance_band=ResistanceBandClassification(
                    r.get("resistance_band", "productive"),
                ),
            )
        verification = ledger.verify()
        _require(
            verification.ok == bool(expected.get("valid", True)),
            f"ledger.verify().ok: expected "
            f"{expected.get('valid', True)}, got {verification.ok}",
        )
        if "length" in expected:
            actual_len = ledger.length
            _require(
                actual_len == int(expected["length"]),
                f"ledger.length: expected {expected['length']}, "
                f"got {actual_len}",
            )
    else:
        raise ProbeFailure(f"unknown audit-chain scenario: {scenario!r}")


def _runaway_pair_coupling(
    inp: Mapping[str, Any], expected: Mapping[str, Any],
) -> None:
    """State-machine transition assertion."""
    scenario = str(inp.get("scenario", ""))
    if scenario == "transition":
        try:
            transition = PairCouplingStateMachine.next_state(
                pair_id=str(inp.get("pair_id", "pair-1")),
                current=PairCouplingState(inp["current"]),
                trigger=PairCouplingTrigger(inp["trigger"]),
            )
        except IllegalStateTransition as exc:
            _require(
                expected.get("illegal") is True,
                f"expected legal transition, got IllegalStateTransition: {exc}",
            )
            return
        _require(
            transition.to_state is PairCouplingState(expected["to_state"]),
            f"to_state: expected {expected['to_state']}, "
            f"got {transition.to_state.value}",
        )
    else:
        raise ProbeFailure(f"unknown pair-coupling scenario: {scenario!r}")


# ---------------------------------------------------------------------------
# drift-signals
# ---------------------------------------------------------------------------


class _AscentScriptedNpgGate:  # pylint: disable=too-few-public-methods
    """Per-step scripted NPG gate for governed-ascent probes."""

    def __init__(self, steps: Sequence[Mapping[str, Any]]) -> None:
        self._steps = list(steps)
        self._calls = 0

    def evaluate(self, **kwargs: Any) -> NetPotentialGainEvaluation:
        idx = min(self._calls, len(self._steps) - 1)
        step = self._steps[idx]
        self._calls += 1
        verdict = NetPotentialGainVerdict(
            str(step.get("verdict", "net_positive"))
        )
        score = float(step.get("score", 0.0))
        return NetPotentialGainEvaluation(
            verdict=verdict,
            action_kind=str(kwargs.get("action_kind", "optimize")),
            score=score,
            per_entity_delta=(),
            reasoning=f"probe-scripted {verdict.value}",
            evaluated_at_epoch=0.0,
            actor_entity_id=str(kwargs.get("actor_entity_id", "probe")),
            affected_entity_ids=tuple(
                kwargs.get("affected_entity_ids", ("probe",))
            ),
        )


class _AscentStubObjectiveGate:  # pylint: disable=too-few-public-methods
    """Fixed-verdict objective gate for governed-ascent probes."""

    def __init__(self, certified: bool) -> None:
        self._verdict = (
            ObjectiveCertificationVerdict.CERTIFIED
            if certified
            else ObjectiveCertificationVerdict.REFUSED
        )

    def certify(self, objective: ClimbObjective) -> ObjectiveCertification:
        return ObjectiveCertification(
            verdict=self._verdict,
            objective_id=objective.objective_id,
            reasoning=f"probe-scripted {self._verdict.value}",
        )


def _runaway_governed_ascent(
    inp: Mapping[str, Any], expected: Mapping[str, Any],
) -> None:
    """Governed ascent — NPG-governed hill climbing termination contract."""
    steps: Sequence[Mapping[str, Any]] = inp.get("steps", [])
    utilizations = [float(u) for u in inp.get("utilization_sequence", [])]
    _require(bool(steps), "probe must supply at least one step")
    _require(bool(utilizations), "probe must supply utilization_sequence")
    consolidated: list[object] = []
    loop = GovernedAscentLoop(
        npg_gate=_AscentScriptedNpgGate(steps),
        objective_gate=_AscentStubObjectiveGate(
            bool(inp.get("objective_certified", True))
        ),
        load_tracker=SustainedLoadTracker(),
        on_consolidate=consolidated.append,
    )
    proposals = [
        StepProposal(
            action_kind=str(step.get("action_kind", "optimize")),
            affected_entity_ids=("probe",),
            grows_capacity=bool(step.get("grows_capacity", False)),
        )
        for step in steps
    ]

    def observe(step_index: int) -> LoadObservation:
        idx = min(step_index, len(utilizations) - 1)
        return LoadObservation(
            timestamp=step_index, utilization=utilizations[idx]
        )

    trajectory = loop.climb(
        objective=ClimbObjective(
            objective_id="probe-objective",
            actor_entity_id="probe",
            action_kind="optimize",
            affected_entity_ids=("probe",),
        ),
        step_generator=lambda i: (
            proposals[i] if i < len(proposals) else None
        ),
        load_observer=observe,
    )
    _require(
        trajectory.termination
        is ClimbTermination(expected["termination"]),
        f"termination: expected {expected['termination']}, "
        f"got {trajectory.termination.value}",
    )
    if "step_count" in expected:
        _require(
            trajectory.step_count == int(expected["step_count"]),
            f"step_count: expected {expected['step_count']}, "
            f"got {trajectory.step_count}",
        )
    if "consolidated" in expected:
        ok = trajectory.consolidation_emitted and len(consolidated) == 1
        _require(
            ok == bool(expected["consolidated"]),
            f"consolidated: expected {expected['consolidated']}, "
            f"got {ok} (sink calls={len(consolidated)})",
        )


def handle_four_options_matrix(probe: Mapping[str, Any]) -> None:
    """Exercise the four-options-matrix surfaces.

    The probe input declares a ``scenario`` that maps to one of the
    game-theoretic primitives (classifier, folk-theorem verifier,
    awareness verifier). At v0.1.0 the only scenario wired into the
    runner is ``pair-shape-classification`` against the cycle / sum
    structure enums; richer scenarios land as the schema matures.
    """
    inp = probe["input"]
    expected = probe["expected"]
    scenario = str(inp.get("scenario", ""))
    if scenario == "enum-values":
        # Pin the canonical wire forms of the cycle / sum enums.
        # Other-language ports MUST emit the same strings.
        from substrate.game_theory.game_theoretic_classifier import (  # pylint: disable=import-outside-toplevel
            CycleClass,
            SumStructure,
        )
        if "cycle_class" in expected:
            for label in expected["cycle_class"]:
                _require(
                    label in {c.value for c in CycleClass},
                    f"cycle_class: {label!r} not in {[c.value for c in CycleClass]!r}",
                )
        if "sum_structure" in expected:
            for label in expected["sum_structure"]:
                _require(
                    label in {s.value for s in SumStructure},
                    f"sum_structure: {label!r} not in {[s.value for s in SumStructure]!r}",
                )
    else:
        raise ProbeFailure(
            f"four-options-matrix scenario not yet supported: {scenario!r}"
        )


def handle_drift_signals(probe: Mapping[str, Any]) -> None:
    """Run a drift-pattern detection scenario against the matcher."""
    inp = probe["input"]
    expected = probe["expected"]

    matcher = DriftPatternMatcher()
    report = matcher.detect(
        behavior_text=str(inp.get("behavior_text", "")),
        structured_signals=inp.get("structured_signals"),
    )

    if "dominant_pattern" in expected:
        observed = (
            report.dominant_pattern.value
            if report.dominant_pattern is not None
            else None
        )
        _require(
            observed == expected["dominant_pattern"],
            f"dominant_pattern: expected {expected['dominant_pattern']}, "
            f"got {observed}",
        )
    if "amplifier_pattern_present" in expected:
        _require(
            report.amplifier_pattern_present
            == bool(expected["amplifier_pattern_present"]),
            f"amplifier_pattern_present: expected "
            f"{expected['amplifier_pattern_present']}, "
            f"got {report.amplifier_pattern_present}",
        )
    if "contains_pattern" in expected:
        present = {d.pattern.value for d in report.detections}
        for want in expected["contains_pattern"]:
            _require(
                want in present,
                f"detections: expected pattern {want!r} to be detected; "
                f"got {sorted(present)!r}",
            )
    if "no_detections" in expected and bool(expected["no_detections"]):
        _require(
            not report.detections,
            f"expected no detections; got {len(report.detections)}",
        )


# ---------------------------------------------------------------------------
# evidence-grade
# ---------------------------------------------------------------------------


def handle_evidence_grade(probe: Mapping[str, Any]) -> None:
    """Dispatch on ``input.fn`` for the evidence-grade composer."""
    inp = probe["input"]
    expected = probe["expected"]
    fn = inp.get("fn")
    if fn != "compose_evidence_grade":
        raise ProbeFailure(f"unknown evidence-grade fn: {fn!r}")
    attestations = tuple(
        EvidenceAttestation(
            source_id=str(row["source_id"]),
            observed_at_epoch_seconds=float(
                row["observed_at_epoch_seconds"]
            ),
            provenance_verified=bool(row["provenance_verified"]),
        )
        for row in inp.get("attestations", [])
    )
    result = compose_evidence_grade(
        attestations,
        now_epoch_seconds=float(inp["now_epoch_seconds"]),
    )
    if "grade" in expected:
        want = EvidenceGrade(str(expected["grade"]))
        _require(
            result.grade is want,
            f"grade: expected {want.value}, got {result.grade.value}",
        )
    if "attestation_count" in expected:
        _require(
            result.attestation_count == int(expected["attestation_count"]),
            f"attestation_count: expected {expected['attestation_count']}, "
            f"got {result.attestation_count}",
        )
    if "unique_source_count" in expected:
        _require(
            result.unique_source_count
            == int(expected["unique_source_count"]),
            f"unique_source_count: expected "
            f"{expected['unique_source_count']}, "
            f"got {result.unique_source_count}",
        )
    if "provenance_verified_count" in expected:
        _require(
            result.provenance_verified_count
            == int(expected["provenance_verified_count"]),
            f"provenance_verified_count: expected "
            f"{expected['provenance_verified_count']}, "
            f"got {result.provenance_verified_count}",
        )


# ---------------------------------------------------------------------------
# multi-scale
# ---------------------------------------------------------------------------


def handle_multi_scale(probe: Mapping[str, Any]) -> None:
    """Dispatch on ``input.fn`` for the scope-registry primitive."""
    inp = probe["input"]
    expected = probe["expected"]
    fn = inp.get("fn")
    if fn == "assert_default_triple":
        registry = ScopeRegistry()
        names = list(registry.names())
        expected_names = list(expected.get("scope_names", []))
        _require(
            names == expected_names,
            f"scope_names: expected {expected_names}, got {names}",
        )
        cell = registry.get("cell")
        node = registry.get("node")
        org = registry.get("org")
        _require(
            cell.parent_name == expected.get("cell_parent"),
            f"cell_parent: expected {expected.get('cell_parent')!r}, "
            f"got {cell.parent_name!r}",
        )
        _require(
            node.parent_name == expected.get("node_parent"),
            f"node_parent: expected {expected.get('node_parent')!r}, "
            f"got {node.parent_name!r}",
        )
        _require(
            org.parent_name == expected.get("org_parent"),
            f"org_parent: expected {expected.get('org_parent')!r}, "
            f"got {org.parent_name!r}",
        )
        _require(
            cell.aggregating == bool(expected.get("cell_aggregating", False)),
            "cell.aggregating mismatch",
        )
        _require(
            node.aggregating == bool(expected.get("node_aggregating", True)),
            "node.aggregating mismatch",
        )
        _require(
            org.aggregating == bool(expected.get("org_aggregating", True)),
            "org.aggregating mismatch",
        )
    elif fn == "register_and_walk":
        registry = ScopeRegistry()
        scope_data = inp["scope"]
        new_scope = ConcreteScope(
            name=str(scope_data["name"]),
            display_name=str(scope_data["display_name"]),
            parent_name=(
                None
                if scope_data.get("parent_name") in (None, "")
                else str(scope_data["parent_name"])
            ),
            aggregating=bool(scope_data["aggregating"]),
        )
        registry.register(new_scope)
        observed_chain = list(registry.parents_of(new_scope.name))
        expected_chain = list(
            expected.get("parent_chain_of_new_scope", [])
        )
        _require(
            observed_chain == expected_chain,
            f"parent_chain_of_new_scope: expected {expected_chain}, "
            f"got {observed_chain}",
        )
        observed_names = sorted(registry.names())
        expected_registry_contents = sorted(
            expected.get("registry_contains", [])
        )
        _require(
            observed_names == expected_registry_contents,
            "registry_contains: expected "
            f"{expected_registry_contents}, got {observed_names}",
        )
    elif fn == "assert_cycle_rejected":
        registry = ScopeRegistry()
        scope_data = inp["scope"]
        new_scope = ConcreteScope(
            name=str(scope_data["name"]),
            display_name=str(scope_data["display_name"]),
            parent_name=(
                None
                if scope_data.get("parent_name") in (None, "")
                else str(scope_data["parent_name"])
            ),
            aggregating=bool(scope_data["aggregating"]),
        )
        try:
            registry.register(new_scope)
            raised = False
        except ValueError:
            raised = True
        _require(
            raised == bool(expected.get("raises", True)),
            f"raises: expected {expected.get('raises')!r}, got {raised!r}",
        )
        observed_names = sorted(registry.names())
        expected_registry_contents = sorted(
            expected.get("registry_contains", [])
        )
        _require(
            observed_names == expected_registry_contents,
            "registry_contains: expected "
            f"{expected_registry_contents}, got {observed_names}",
        )
    else:
        raise ProbeFailure(f"unknown multi-scale fn: {fn!r}")
