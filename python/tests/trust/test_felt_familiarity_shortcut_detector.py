"""Tests for FeltFamiliarityShortcutDetector (Companion #2)."""
from __future__ import annotations

import pytest

from substrate.trust.felt_familiarity_shortcut_detector import (
    DEFAULT_FAMILIARITY_SHORTCUT_CONFIG,
    FamiliarityShortcutConfig,
    FamiliarityShortcutInput,
    FeltFamiliarityShortcutDetector,
    ShortcutVerdict,
)

def _input(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    *,
    entity: str = "agent-1",
    interactions: int = 60,
    recent: float = 0.8,
    substantive: float = 0.3,
    audit_rate: float = 0.5,
    audit_count: int = 10,
) -> FamiliarityShortcutInput:
    return FamiliarityShortcutInput(
        entity_id=entity,
        interaction_count=interactions,
        recent_interaction_fraction=recent,
        substantive_evidence_trust_score=substantive,
        audit_pass_rate=audit_rate,
        audit_count=audit_count,
    )

class TestInputValidation:
    def test_round_trip(self) -> None:
        i = _input()
        assert i.interaction_count == 60

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("entity", "", "entity_id"),
            ("interactions", -1, "interaction_count"),
            ("recent", 1.5, "recent_interaction_fraction"),
            ("substantive", -0.1, "substantive_evidence_trust_score"),
            ("audit_rate", 1.5, "audit_pass_rate"),
            ("audit_count", -1, "audit_count"),
        ],
    )
    def test_bad_values(
        self, field: str, value: object, match: str,
    ) -> None:
        kwargs: dict[str, object] = {field: value}
        with pytest.raises(ValueError, match=match):
            _input(**kwargs)  # type: ignore[arg-type]

class TestConfig:
    def test_defaults(self) -> None:
        c = FamiliarityShortcutConfig()
        assert c.min_interaction_count == 10

    def test_saturation_exceeds_min(self) -> None:
        with pytest.raises(
            ValueError, match="interaction_saturation",
        ):
            FamiliarityShortcutConfig(
                min_interaction_count=20,
                interaction_saturation=10,
            )

class TestDetection:
    def setup_method(self) -> None:
        self.d = FeltFamiliarityShortcutDetector()

    def test_insufficient_data_interactions(self) -> None:
        out = self.d.detect(_input(interactions=3))
        assert out.verdict is ShortcutVerdict.INSUFFICIENT_DATA

    def test_insufficient_data_audits(self) -> None:
        out = self.d.detect(_input(audit_count=0))
        assert out.verdict is ShortcutVerdict.INSUFFICIENT_DATA

    def test_shortcut_flagged_high_familiarity_low_substantive(
        self,
    ) -> None:
        out = self.d.detect(_input(
            interactions=100, recent=1.0,
            substantive=0.1, audit_rate=0.2, audit_count=10,
        ))
        assert out.verdict is ShortcutVerdict.SHORTCUT_FLAGGED
        assert out.shortcut_flagged
        assert out.shortcut_risk_score > 0.0

    def test_no_shortcut_balanced(self) -> None:
        out = self.d.detect(_input(
            interactions=60, recent=0.5,
            substantive=0.7, audit_rate=0.8, audit_count=10,
        ))
        assert out.verdict is ShortcutVerdict.NO_SHORTCUT
        assert not out.shortcut_flagged

    def test_no_shortcut_low_familiarity(self) -> None:
        out = self.d.detect(_input(
            interactions=15, recent=0.3,
            substantive=0.2, audit_rate=0.3, audit_count=5,
        ))
        # Low interaction count keeps familiarity below threshold
        assert out.verdict is ShortcutVerdict.NO_SHORTCUT

class TestModuleSurface:
    def test_default_singleton(self) -> None:
        assert (
            DEFAULT_FAMILIARITY_SHORTCUT_CONFIG.min_interaction_count == 10
        )
