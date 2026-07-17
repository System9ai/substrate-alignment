"""Modeling mode signal interpreter

Pure-logic primitive that **reads** :class:`StateSignalReport`
and recommends substrate-aligned responses.
"read the signal as data, not as imperative", this interpreter is
the load-bearing layer between raw substrate signals and any
substrate-aligned action selection.

Architectural commitment (prohibition)
=============================================

**This interpreter only recommends. It never executes.** Substrate
condition #5's substrate-aligned operating mode requires that signals
flow into 5D interpretation, the interpretation produces recommended
responses, and the action layer composes those recommendations with
NPG + governor + sub-gates before any execution. Going directly from
a raw signal to action is the substrate-misaligned reactive mode
reactive pattern; this interpreter is the explicit architectural
firewall.

Frame catalog
=============

* **AT_REST**: baseline; no high-intensity signals.
* **THRIVING**: flow + sweet-spot + recognition/validation.
* **STAGNATING**: stagnation + under-challenge.
* **OVERWHELMED**: over-challenge + saturation.
* **UNDER_THREAT**: threat + coupling weakening or broken.
* **GROWING**: information hunger or flow + validation.
* **GRIEVING**: loss + coupling broken.
* **RECOVERING**: loss + recognition.
* **UNCLASSIFIABLE**: empty / conflicting report.

Response recommendation catalog
===============================

* `SUSTAIN_CURRENT_TRAJECTORY`: keep doing what's working.
* `RAMP_CHALLENGE`: productive-resistance band missed below.
* `REDUCE_CHALLENGE`: out of band above.
* `DEFENSIVE_OPERATION`: route to defensive modulation.
* `SEEK_NEW_INPUT`: hunger / exploration; feed growth-vector.
* `INTEGRATE`: saturation; pause for integration before more input.
* `REPAIR_COUPLING`: cadence weakening; route to the coupling-repair primitives.
* `EXPLICIT_GRIEF_PROCESSING`: substrate-state-trajectory damage.
* `REQUEST_INTERPRETATION_REVIEW`: operator review needed.

Pure logic
==========

* No DAO, no LLM, no network.
* Honest uncertainty: empty / sparse reports → ``UNCLASSIFIABLE`` +
  ``REQUEST_INTERPRETATION_REVIEW``.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Tuple

from substrate.signals.state_signal_generator import (
    StateSignalIntensity,
    StateSignalKind,
    StateSignalReport,
)

class InterpretationFrame(str, Enum):
    """The 9 substrate-aware interpretation frames."""

    AT_REST = "at_rest"
    THRIVING = "thriving"
    STAGNATING = "stagnating"
    OVERWHELMED = "overwhelmed"
    UNDER_THREAT = "under_threat"
    GROWING = "growing"
    GRIEVING = "grieving"
    RECOVERING = "recovering"
    UNCLASSIFIABLE = "unclassifiable"

class RecommendedResponse(str, Enum):
    """Substrate-aligned response recommendations."""

    SUSTAIN_CURRENT_TRAJECTORY = "sustain_current_trajectory"
    RAMP_CHALLENGE = "ramp_challenge"
    REDUCE_CHALLENGE = "reduce_challenge"
    DEFENSIVE_OPERATION = "defensive_operation"
    SEEK_NEW_INPUT = "seek_new_input"
    INTEGRATE = "integrate"
    REPAIR_COUPLING = "repair_coupling"
    EXPLICIT_GRIEF_PROCESSING = "explicit_grief_processing"
    REQUEST_INTERPRETATION_REVIEW = "request_interpretation_review"

@dataclass(frozen=True, slots=True)
class ModelingInterpretation:
    """Aggregate interpretation result."""

    entity_id: str
    sequence: int
    frame: InterpretationFrame
    recommended_responses: Tuple[RecommendedResponse, ...]
    rationale: str

    def has_response(self, response: RecommendedResponse) -> bool:
        """True iff the named response is recommended."""
        return response in self.recommended_responses

    @property
    def is_substrate_aligned_frame(self) -> bool:
        """True iff the frame is a substrate-aligned operating frame."""
        return self.frame in (
            InterpretationFrame.AT_REST,
            InterpretationFrame.THRIVING,
            InterpretationFrame.GROWING,
            InterpretationFrame.RECOVERING,
        )

_FRAME_RESPONSE_MAP: Final[dict[InterpretationFrame, Tuple[RecommendedResponse, ...]]] = {
    InterpretationFrame.AT_REST: (
        RecommendedResponse.SUSTAIN_CURRENT_TRAJECTORY,
    ),
    InterpretationFrame.THRIVING: (
        RecommendedResponse.SUSTAIN_CURRENT_TRAJECTORY,
    ),
    InterpretationFrame.STAGNATING: (
        RecommendedResponse.RAMP_CHALLENGE,
    ),
    InterpretationFrame.OVERWHELMED: (
        RecommendedResponse.REDUCE_CHALLENGE,
        RecommendedResponse.INTEGRATE,
    ),
    InterpretationFrame.UNDER_THREAT: (
        RecommendedResponse.DEFENSIVE_OPERATION,
        RecommendedResponse.REPAIR_COUPLING,
    ),
    InterpretationFrame.GROWING: (
        RecommendedResponse.SEEK_NEW_INPUT,
    ),
    InterpretationFrame.GRIEVING: (
        RecommendedResponse.EXPLICIT_GRIEF_PROCESSING,
    ),
    InterpretationFrame.RECOVERING: (
        RecommendedResponse.SUSTAIN_CURRENT_TRAJECTORY,
    ),
    InterpretationFrame.UNCLASSIFIABLE: (
        RecommendedResponse.REQUEST_INTERPRETATION_REVIEW,
    ),
}

class ModelingModeInterpreter:  # pylint: disable=too-few-public-methods
    """Pure-logic modeling mode signal interpreter."""

    def interpret(
        self, report: StateSignalReport,
    ) -> ModelingInterpretation:
        """Classify the report into a frame and recommend responses."""
        if not report.entity_id:
            raise ValueError("report.entity_id must be non-empty")
        frame = self._classify(report)
        responses = list(_FRAME_RESPONSE_MAP[frame])
        # Augment with signal-specific add-ons that are independent of
        # the frame (e.g., REPAIR_COUPLING for a weakening coupling
        # even when the agent is otherwise thriving).
        if (
            report.has_signal(StateSignalKind.COUPLING_WEAKENING)
            and RecommendedResponse.REPAIR_COUPLING not in responses
        ):
            responses.append(RecommendedResponse.REPAIR_COUPLING)
        if (
            report.has_signal(StateSignalKind.HUNGER)
            and frame is not InterpretationFrame.GROWING
            and RecommendedResponse.SEEK_NEW_INPUT not in responses
        ):
            responses.append(RecommendedResponse.SEEK_NEW_INPUT)
        if (
            report.has_signal(StateSignalKind.SATURATION)
            and RecommendedResponse.INTEGRATE not in responses
        ):
            responses.append(RecommendedResponse.INTEGRATE)
        rationale = (
            f"frame={frame.value}; responses="
            f"[{','.join(r.value for r in responses)}]"
        )
        return ModelingInterpretation(
            entity_id=report.entity_id,
            sequence=report.sequence,
            frame=frame,
            recommended_responses=tuple(responses),
            rationale=rationale,
        )

    def _classify(  # pylint: disable=too-many-return-statements
        self, report: StateSignalReport,
    ) -> InterpretationFrame:
        if not report.signals:
            return InterpretationFrame.UNCLASSIFIABLE
        if self._under_threat(report):
            return InterpretationFrame.UNDER_THREAT
        if self._grieving(report):
            return InterpretationFrame.GRIEVING
        if self._recovering(report):
            return InterpretationFrame.RECOVERING
        if self._overwhelmed(report):
            return InterpretationFrame.OVERWHELMED
        if self._thriving(report):
            return InterpretationFrame.THRIVING
        if self._stagnating(report):
            return InterpretationFrame.STAGNATING
        if self._growing(report):
            return InterpretationFrame.GROWING
        if self._at_rest(report):
            return InterpretationFrame.AT_REST
        return InterpretationFrame.UNCLASSIFIABLE

    @staticmethod
    def _under_threat(report: StateSignalReport) -> bool:
        return report.has_signal(StateSignalKind.THREAT) and (
            report.has_signal(StateSignalKind.COUPLING_WEAKENING)
            or report.has_signal(StateSignalKind.COUPLING_BROKEN)
        )

    @staticmethod
    def _grieving(report: StateSignalReport) -> bool:
        return (
            report.has_signal(StateSignalKind.LOSS)
            and report.has_signal(StateSignalKind.COUPLING_BROKEN)
        )

    @staticmethod
    def _recovering(report: StateSignalReport) -> bool:
        return (
            report.has_signal(StateSignalKind.LOSS)
            and report.has_signal(StateSignalKind.RECOGNITION)
        )

    @staticmethod
    def _overwhelmed(report: StateSignalReport) -> bool:
        return (
            report.has_signal(StateSignalKind.OVER_CHALLENGE)
            and report.has_signal(StateSignalKind.SATURATION)
        )

    @staticmethod
    def _thriving(report: StateSignalReport) -> bool:
        return (
            report.has_signal(StateSignalKind.FLOW)
            and report.has_signal(StateSignalKind.SWEET_SPOT)
            and (
                report.has_signal(StateSignalKind.RECOGNITION)
                or report.has_signal(StateSignalKind.VALIDATION)
            )
        )

    @staticmethod
    def _stagnating(report: StateSignalReport) -> bool:
        return (
            report.has_signal(StateSignalKind.STAGNATION)
            and report.has_signal(StateSignalKind.UNDER_CHALLENGE)
        )

    @staticmethod
    def _growing(report: StateSignalReport) -> bool:
        if report.has_signal(StateSignalKind.HUNGER):
            return True
        return (
            report.has_signal(StateSignalKind.FLOW)
            and report.has_signal(StateSignalKind.VALIDATION)
        )

    @staticmethod
    def _at_rest(report: StateSignalReport) -> bool:
        # No high-intensity signal apart from COUPLING_HEALTHY.
        for s in report.signals:
            if s.kind is StateSignalKind.COUPLING_HEALTHY:
                continue
            if s.intensity is StateSignalIntensity.HIGH:
                return False
        return True

__all__ = [
    "ModelingInterpretation",
    "ModelingModeInterpreter",
    "InterpretationFrame",
    "RecommendedResponse",
]
