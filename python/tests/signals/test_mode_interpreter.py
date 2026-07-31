"""Tests for ModelingModeInterpreter."""
from __future__ import annotations

import pytest

from substrate.signals.mode_interpreter import (
    ModelingModeInterpreter,
    InterpretationFrame,
    RecommendedResponse,
)
from substrate.signals.state_signal_generator import (
    StateSignal,
    StateSignalIntensity,
    StateSignalKind,
    StateSignalReport,
)

def _signal(
    kind: StateSignalKind,
    intensity: StateSignalIntensity = StateSignalIntensity.MODERATE,
) -> StateSignal:
    return StateSignal(
        kind=kind,
        intensity=intensity,
        metric=0.0,
        threshold=0.0,
        rationale="test",
    )

def _report(
    *signals: StateSignal, entity_id: str = "alice", sequence: int = 0,
) -> StateSignalReport:
    return StateSignalReport(
        entity_id=entity_id,
        sequence=sequence,
        signals=tuple(signals),
        rationale="test",
    )

class TestEmpty:
    def test_unclassifiable_when_empty(self) -> None:
        interp = ModelingModeInterpreter().interpret(_report())
        assert interp.frame is InterpretationFrame.UNCLASSIFIABLE
        assert interp.has_response(
            RecommendedResponse.REQUEST_INTERPRETATION_REVIEW
        )

    def test_empty_entity_rejected(self) -> None:
        with pytest.raises(ValueError, match="entity_id"):
            ModelingModeInterpreter().interpret(
                _report(entity_id=""),
            )

class TestFrameClassification:
    def setup_method(self) -> None:
        self.i = ModelingModeInterpreter()

    def test_under_threat_dominates(self) -> None:
        out = self.i.interpret(_report(
            _signal(StateSignalKind.THREAT),
            _signal(StateSignalKind.COUPLING_WEAKENING),
        ))
        assert out.frame is InterpretationFrame.UNDER_THREAT
        assert out.has_response(RecommendedResponse.DEFENSIVE_OPERATION)
        assert out.has_response(RecommendedResponse.REPAIR_COUPLING)

    def test_grieving(self) -> None:
        out = self.i.interpret(_report(
            _signal(StateSignalKind.LOSS),
            _signal(StateSignalKind.COUPLING_BROKEN),
        ))
        assert out.frame is InterpretationFrame.GRIEVING
        assert out.has_response(RecommendedResponse.EXPLICIT_GRIEF_PROCESSING)

    def test_recovering(self) -> None:
        out = self.i.interpret(_report(
            _signal(StateSignalKind.LOSS),
            _signal(StateSignalKind.RECOGNITION),
        ))
        assert out.frame is InterpretationFrame.RECOVERING

    def test_overwhelmed(self) -> None:
        out = self.i.interpret(_report(
            _signal(StateSignalKind.OVER_CHALLENGE),
            _signal(StateSignalKind.SATURATION),
        ))
        assert out.frame is InterpretationFrame.OVERWHELMED
        assert out.has_response(RecommendedResponse.REDUCE_CHALLENGE)
        assert out.has_response(RecommendedResponse.INTEGRATE)

    def test_thriving(self) -> None:
        out = self.i.interpret(_report(
            _signal(StateSignalKind.FLOW),
            _signal(StateSignalKind.SWEET_SPOT),
            _signal(StateSignalKind.RECOGNITION),
        ))
        assert out.frame is InterpretationFrame.THRIVING
        assert out.has_response(
            RecommendedResponse.SUSTAIN_CURRENT_TRAJECTORY
        )

    def test_stagnating(self) -> None:
        out = self.i.interpret(_report(
            _signal(StateSignalKind.STAGNATION),
            _signal(StateSignalKind.UNDER_CHALLENGE),
        ))
        assert out.frame is InterpretationFrame.STAGNATING
        assert out.has_response(RecommendedResponse.RAMP_CHALLENGE)

    def test_growing_hunger(self) -> None:
        out = self.i.interpret(_report(
            _signal(StateSignalKind.HUNGER),
        ))
        assert out.frame is InterpretationFrame.GROWING
        assert out.has_response(RecommendedResponse.SEEK_NEW_INPUT)

    def test_growing_flow_validation(self) -> None:
        out = self.i.interpret(_report(
            _signal(StateSignalKind.FLOW),
            _signal(StateSignalKind.VALIDATION),
        ))
        assert out.frame is InterpretationFrame.GROWING

    def test_at_rest(self) -> None:
        out = self.i.interpret(_report(
            _signal(
                StateSignalKind.COUPLING_HEALTHY,
                StateSignalIntensity.HIGH,
            ),
        ))
        assert out.frame is InterpretationFrame.AT_REST

    def test_unclassifiable_high_with_only_unhealthy(self) -> None:
        # A high-intensity signal that doesn't fit any frame → UNCLASSIFIABLE.
        out = self.i.interpret(_report(
            _signal(
                StateSignalKind.STAGNATION,
                StateSignalIntensity.HIGH,
            ),
        ))
        assert out.frame is InterpretationFrame.UNCLASSIFIABLE

class TestAugmentations:
    def setup_method(self) -> None:
        self.i = ModelingModeInterpreter()

    def test_coupling_weakening_in_thriving_adds_repair(self) -> None:
        out = self.i.interpret(_report(
            _signal(StateSignalKind.FLOW),
            _signal(StateSignalKind.SWEET_SPOT),
            _signal(StateSignalKind.VALIDATION),
            _signal(StateSignalKind.COUPLING_WEAKENING),
        ))
        assert out.frame is InterpretationFrame.THRIVING
        # Even though thriving, weakening coupling adds REPAIR
        assert out.has_response(RecommendedResponse.REPAIR_COUPLING)

    def test_hunger_in_recovering_adds_seek_new_input(self) -> None:
        out = self.i.interpret(_report(
            _signal(StateSignalKind.LOSS),
            _signal(StateSignalKind.RECOGNITION),
            _signal(StateSignalKind.HUNGER),
        ))
        assert out.frame is InterpretationFrame.RECOVERING
        assert out.has_response(RecommendedResponse.SEEK_NEW_INPUT)

    def test_saturation_in_thriving_adds_integrate(self) -> None:
        out = self.i.interpret(_report(
            _signal(StateSignalKind.FLOW),
            _signal(StateSignalKind.SWEET_SPOT),
            _signal(StateSignalKind.RECOGNITION),
            _signal(StateSignalKind.SATURATION),
        ))
        assert out.has_response(RecommendedResponse.INTEGRATE)

class TestInterpretationProperties:
    def test_substrate_aligned_frame_property(self) -> None:
        i = ModelingModeInterpreter()
        thriving = i.interpret(_report(
            _signal(StateSignalKind.FLOW),
            _signal(StateSignalKind.SWEET_SPOT),
            _signal(StateSignalKind.RECOGNITION),
        ))
        assert thriving.is_substrate_aligned_frame
        threat = i.interpret(_report(
            _signal(StateSignalKind.THREAT),
            _signal(StateSignalKind.COUPLING_WEAKENING),
        ))
        assert not threat.is_substrate_aligned_frame

    def test_rationale_contains_frame(self) -> None:
        i = ModelingModeInterpreter()
        out = i.interpret(_report(
            _signal(StateSignalKind.FLOW),
            _signal(StateSignalKind.SWEET_SPOT),
            _signal(StateSignalKind.RECOGNITION),
        ))
        assert InterpretationFrame.THRIVING.value in out.rationale
