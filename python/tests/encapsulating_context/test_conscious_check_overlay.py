"""Tests for ConsciousCheckOverlay (Companion #2)."""
from __future__ import annotations

import pytest

from substrate.encapsulating_context.conscious_check_overlay import (
    DEFAULT_CONSCIOUS_CHECK_CONFIG,
    ConsciousCheckConfig,
    ConsciousCheckInput,
    ConsciousCheckOverlay,
    OverlayPosture,
    TriggerSource,
)

def _input(
    *,
    entity: str = "agent-1",
    decision: str = "dec-1",
    pull: bool = False,
    since: int = 0,
) -> ConsciousCheckInput:
    return ConsciousCheckInput(
        entity_id=entity,
        decision_id=decision,
        pull_signal_fired=pull,
        decisions_since_last_check=since,
    )

class TestInputValidation:
    def test_round_trip(self) -> None:
        i = _input(since=5)
        assert i.decisions_since_last_check == 5

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("entity", "", "entity_id"),
            ("decision", "", "decision_id"),
            ("since", -1, "decisions_since_last_check"),
        ],
    )
    def test_bad_values(
        self, field: str, value: object, match: str,
    ) -> None:
        kwargs: dict[str, object] = {field: value}
        with pytest.raises(ValueError, match=match):
            _input(**kwargs)

class TestConfig:
    def test_defaults(self) -> None:
        c = ConsciousCheckConfig()
        assert c.periodic_check_interval == 25
        assert len(c.check_questions) >= 1

    def test_empty_questions_rejected(self) -> None:
        with pytest.raises(ValueError, match="check_questions"):
            ConsciousCheckConfig(check_questions=())

    def test_zero_interval_rejected(self) -> None:
        with pytest.raises(
            ValueError, match="periodic_check_interval",
        ):
            ConsciousCheckConfig(periodic_check_interval=0)

    def test_zero_defer_count_rejected(self) -> None:
        with pytest.raises(
            ValueError, match="defer_after_consecutive_pulls",
        ):
            ConsciousCheckConfig(defer_after_consecutive_pulls=0)

class TestOverlay:
    def setup_method(self) -> None:
        self.o = ConsciousCheckOverlay(entity_id="agent-1")

    def test_proceed_when_no_pull(self) -> None:
        out = self.o.evaluate(_input(pull=False, since=5))
        assert out.posture is OverlayPosture.PROCEED
        assert out.trigger_source is TriggerSource.NEITHER

    def test_pull_signal_pauses(self) -> None:
        out = self.o.evaluate(_input(pull=True))
        assert out.posture is OverlayPosture.PAUSE_AND_REASON
        assert out.trigger_source is TriggerSource.PULL_SIGNAL

    def test_periodic_pauses(self) -> None:
        out = self.o.evaluate(_input(since=25))
        assert out.posture is OverlayPosture.PAUSE_AND_REASON
        assert out.trigger_source is TriggerSource.PERIODIC

    def test_defer_after_consecutive_pulls(self) -> None:
        self.o.evaluate(_input(decision="d-0", pull=True))
        self.o.evaluate(_input(decision="d-1", pull=True))
        out = self.o.evaluate(_input(decision="d-2", pull=True))
        assert out.posture is OverlayPosture.DEFER
        assert out.consecutive_pulls == 3

    def test_consecutive_pulls_reset_on_no_pull(self) -> None:
        self.o.evaluate(_input(pull=True))
        self.o.evaluate(_input(pull=True))
        out = self.o.evaluate(_input(pull=False, since=0))
        assert out.consecutive_pulls == 0

    def test_entity_mismatch_rejected(self) -> None:
        with pytest.raises(ValueError, match="does not match"):
            self.o.evaluate(_input(entity="other"))

    def test_check_questions_returned(self) -> None:
        out = self.o.evaluate(_input(pull=True))
        assert out.check_questions == (
            DEFAULT_CONSCIOUS_CHECK_CONFIG.check_questions
        )

class TestModuleSurface:
    def test_default_singleton(self) -> None:
        assert (
            DEFAULT_CONSCIOUS_CHECK_CONFIG.periodic_check_interval == 25
        )

    def test_overlay_requires_entity(self) -> None:
        with pytest.raises(ValueError, match="entity_id"):
            ConsciousCheckOverlay(entity_id="")
