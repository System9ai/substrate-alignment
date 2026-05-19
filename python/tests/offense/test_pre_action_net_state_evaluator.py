"""Tests for PreActionNetStateChangeEvaluator (Companion #2b)."""
from __future__ import annotations

import pytest

from substrate.offense.pre_action_net_state_evaluator import (
    DEFAULT_PRE_ACTION_CONFIG,
    EntityDelta,
    PreActionConfig,
    PreActionInput,
    PreActionNetStateChangeEvaluator,
    PreActionVerdict,
)

def _input(
    *,
    action: str = "act-1",
    actor: str = "alice",
    deltas: tuple[tuple[str, float], ...] = (("bob", 0.2), ("carol", 0.3)),
) -> PreActionInput:
    return PreActionInput(
        action_id=action,
        actor_entity_id=actor,
        affected_deltas=tuple(
            EntityDelta(entity_id=e, estimated_delta=d) for e, d in deltas
        ),
    )

class TestEntityDelta:
    def test_round_trip(self) -> None:
        d = EntityDelta(entity_id="e", estimated_delta=0.1)
        assert d.estimated_delta == 0.1

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("entity_id", "", "entity_id"),
            ("estimated_delta", 1.5, "estimated_delta"),
        ],
    )
    def test_bad_values(
        self, field: str, value: object, match: str,
    ) -> None:
        kwargs: dict[str, object] = {
            "entity_id": "e",
            "estimated_delta": 0.0,
            field: value,
        }
        with pytest.raises(ValueError, match=match):
            EntityDelta(**kwargs)  # type: ignore[arg-type]

class TestInputValidation:
    def test_round_trip(self) -> None:
        i = _input()
        assert len(i.affected_deltas) == 2

    def test_duplicate_entity_ids_rejected(self) -> None:
        with pytest.raises(ValueError, match="unique"):
            _input(deltas=(("bob", 0.1), ("bob", 0.2)))

    def test_empty_action_rejected(self) -> None:
        with pytest.raises(ValueError, match="action_id"):
            _input(action="")

    def test_empty_actor_rejected(self) -> None:
        with pytest.raises(ValueError, match="actor_entity_id"):
            _input(actor_entity_id="")

class TestConfig:
    def test_defaults(self) -> None:
        c = PreActionConfig()
        assert c.positive_sum_threshold == 0.1

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("positive_sum_threshold", 0.0, "positive_sum_threshold"),
            ("negative_sum_threshold", 0.0, "negative_sum_threshold"),
            ("min_affected", 0, "min_affected"),
            ("extreme_loss_floor", 0.0, "extreme_loss_floor"),
            ("extreme_loss_floor", -2.0, "extreme_loss_floor"),
        ],
    )
    def test_bad_values(
        self, field: str, value: float, match: str,
    ) -> None:
        with pytest.raises(ValueError, match=match):
            PreActionConfig(**{field: value})

class TestEvaluator:
    def setup_method(self) -> None:
        self.e = PreActionNetStateChangeEvaluator()

    def test_probably_net_positive(self) -> None:
        out = self.e.evaluate(_input(
            deltas=(("a", 0.2), ("b", 0.3), ("c", 0.1)),
        ))
        assert out.verdict is PreActionVerdict.PROBABLY_NET_POSITIVE

    def test_likely_net_negative_sum(self) -> None:
        out = self.e.evaluate(_input(
            deltas=(("a", -0.2), ("b", -0.3)),
        ))
        assert out.verdict is PreActionVerdict.LIKELY_NET_NEGATIVE
        assert out.likely_net_negative

    def test_extreme_loss_triggers_despite_positive_sum(self) -> None:
        # Sum = +0.2, but one entity loses 0.5 → flagged
        out = self.e.evaluate(_input(
            deltas=(("a", -0.5), ("b", 0.4), ("c", 0.3)),
        ))
        assert out.verdict is PreActionVerdict.LIKELY_NET_NEGATIVE

    def test_uncertain_in_dead_zone(self) -> None:
        out = self.e.evaluate(_input(
            deltas=(("a", 0.02), ("b", 0.03)),
        ))
        assert out.verdict is PreActionVerdict.UNCERTAIN

    def test_uncertain_empty(self) -> None:
        i = PreActionInput(
            action_id="x", actor_entity_id="alice",
            affected_deltas=(),
        )
        out = self.e.evaluate(i)
        assert out.verdict is PreActionVerdict.UNCERTAIN

class TestModuleSurface:
    def test_default_singleton(self) -> None:
        assert (
            DEFAULT_PRE_ACTION_CONFIG.positive_sum_threshold == 0.1
        )
