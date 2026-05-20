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
from substrate.conformance.probe_runner import ProbeFailure
from substrate.net_potential_gain_gate import (
    DefaultNetPotentialGainGate,
    NetPotentialGainVerdict,
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
    else:
        raise ProbeFailure(
            f"runaway-power-prevention mechanism not yet wired: {mechanism!r}"
        )


# ---------------------------------------------------------------------------
# drift-signals
# ---------------------------------------------------------------------------


def handle_drift_signals(probe: Mapping[str, Any]) -> None:  # pragma: no cover
    """Placeholder until the drift handlers are wired.

    The drift primitives have stable interfaces, but the probe-input
    schema for them is still under design. Probes targeting this spec
    will land alongside the schema.
    """
    del probe  # acknowledged-unused
    raise ProbeFailure("drift-signals probes are not yet supported by the runner")
