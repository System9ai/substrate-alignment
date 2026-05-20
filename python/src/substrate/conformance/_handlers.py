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
from substrate.halt.halt_escalate_protocol import (
    HaltAndEscalateProtocol,
    HaltObservation,
    HaltReason,
    HaltState,
)
from substrate.net_potential_gain_gate import (
    DefaultNetPotentialGainGate,
    NetPotentialGainVerdict,
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
    classify,
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
    elif mechanism == "halt-and-escalate":
        _runaway_halt_and_escalate(inp, expected)
    elif mechanism == "audit-chain":
        _runaway_audit_chain(inp, expected)
    elif mechanism == "pair-coupling":
        _runaway_pair_coupling(inp, expected)
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
    classification = classify(float(inp["utilization"]), config=cfg)
    _require(
        classification is ResistanceBandClassification(expected["classification"]),
        f"classification: expected {expected['classification']}, "
        f"got {classification.value}",
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
