"""Tests for MultiSignalTrustExtension."""
from __future__ import annotations

import pytest

from substrate.trust.multi_signal_trust_extension import (
    DEFAULT_MULTI_SIGNAL_TRUST_CONFIG,
    ExtendedTrustModifier,
    ExtendedTrustVerdict,
    MultiSignalTrustConfig,
    MultiSignalTrustExtension,
    MultiSignalTrustInput,
    TrustScale,
)
from substrate.trust.substrate_coherence_trust_scorer import (
    TrustScore,
    TrustVerdict,
)

def _base_trust(
    entity_id: str = "alice",
    composite: float | None = 0.5,
    verdict: TrustVerdict = TrustVerdict.MIXED,
) -> TrustScore:
    return TrustScore(
        entity_id=entity_id,
        record_count=10,
        components=None,
        composite_score=composite,
        verdict=verdict,
        rationale="base",
    )

def _input(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    *,
    entity_id: str = "alice",
    scale: TrustScale = TrustScale.CELL,
    composite: float | None = 0.5,
    cadence: float | None = None,
    tells: int | None = None,
    folk: bool | None = None,
    peer: str | None = None,
) -> MultiSignalTrustInput:
    return MultiSignalTrustInput(
        entity_id=entity_id,
        scale=scale,
        base_trust=_base_trust(entity_id, composite),
        cadence_field_strength=cadence,
        behavioral_negative_tell_count=tells,
        folk_conditions_satisfied=folk,
        peer_classification=peer,
    )

class TestInputValidation:
    def test_round_trip(self) -> None:
        i = _input()
        assert i.entity_id == "alice"

    def test_empty_entity_rejected(self) -> None:
        with pytest.raises(ValueError, match="entity_id"):
            _input(entity_id="")

    def test_entity_mismatch_rejected(self) -> None:
        with pytest.raises(ValueError, match="base_trust.entity_id"):
            MultiSignalTrustInput(
                entity_id="alice",
                scale=TrustScale.CELL,
                base_trust=_base_trust("bob"),
            )

    def test_bad_cadence_rejected(self) -> None:
        with pytest.raises(ValueError, match="cadence_field_strength"):
            _input(cadence=1.5)

    def test_negative_tells_rejected(self) -> None:
        with pytest.raises(ValueError, match="behavioral_negative_tell_count"):
            _input(tells=-1)

class TestConfig:
    def test_defaults(self) -> None:
        cfg = MultiSignalTrustConfig()
        assert cfg.trusted_min == 0.7

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("cadence_positive_min", 0.0, "cadence_positive_min"),
            ("cadence_negative_max", 0.9, "cadence_negative_max"),
            ("tell_negative_min", 0, "tell_negative_min"),
            ("cadence_delta", 0.0, "cadence_delta"),
            ("tell_delta", 0.1, "tell_delta"),
            ("trusted_min", 0.2, "distrusted_max"),
        ],
    )
    def test_bad_values(self, field: str, value: float, match: str) -> None:
        with pytest.raises(ValueError, match=match):
            MultiSignalTrustConfig(**{field: value})

class TestExtensionFlow:
    def setup_method(self) -> None:
        self.e = MultiSignalTrustExtension()

    def test_insufficient_when_base_is_none(self) -> None:
        out = self.e.score(_input(composite=None))
        assert out.verdict is ExtendedTrustVerdict.INSUFFICIENT_DATA
        assert out.extended_score is None

    def test_no_modifiers_returns_base(self) -> None:
        out = self.e.score(_input(composite=0.5))
        assert out.extended_score == 0.5

    def test_cadence_positive_modifier(self) -> None:
        out = self.e.score(_input(composite=0.6, cadence=0.9))
        # +0.1 from cadence
        assert abs(out.extended_score - 0.7) < 1e-9
        assert out.verdict is ExtendedTrustVerdict.TRUSTED

    def test_cadence_negative_modifier(self) -> None:
        out = self.e.score(_input(composite=0.5, cadence=0.1))
        assert abs(out.extended_score - 0.4) < 1e-9

    def test_tells_negative(self) -> None:
        out = self.e.score(_input(composite=0.5, tells=5))
        assert out.extended_score < 0.5

    def test_folk_positive(self) -> None:
        out = self.e.score(_input(composite=0.6, folk=True))
        assert out.extended_score > 0.6

    def test_peer_aligned_positive(self) -> None:
        out = self.e.score(_input(
            composite=0.6, peer="substrate_aligned",
        ))
        assert out.extended_score > 0.6

    def test_peer_misaligned_negative(self) -> None:
        out = self.e.score(_input(
            composite=0.6, peer="substrate_misaligned",
        ))
        assert out.extended_score < 0.6

class TestScaleAwareness:
    def test_cell_scale(self) -> None:
        out = MultiSignalTrustExtension().score(_input(scale=TrustScale.CELL))
        assert out.scale is TrustScale.CELL

    def test_node_scale(self) -> None:
        out = MultiSignalTrustExtension().score(_input(scale=TrustScale.NODE))
        assert out.scale is TrustScale.NODE

class TestVerdictThresholds:
    def setup_method(self) -> None:
        self.e = MultiSignalTrustExtension()

    def test_trusted_high(self) -> None:
        out = self.e.score(_input(
            composite=0.7, cadence=0.9, folk=True, peer="substrate_aligned",
        ))
        assert out.is_trusted

    def test_distrusted_low(self) -> None:
        out = self.e.score(_input(
            composite=0.3, cadence=0.1, tells=5, peer="substrate_misaligned",
        ))
        assert out.is_distrusted

    def test_mixed_middle(self) -> None:
        out = self.e.score(_input(composite=0.5))
        assert out.verdict is ExtendedTrustVerdict.MIXED

class TestNoDataModifier:
    def test_missing_inputs_no_data(self) -> None:
        out = MultiSignalTrustExtension().score(_input())
        # All modifiers should be NO_DATA when no inputs supplied
        for m in out.modifiers:
            assert m.modifier is ExtendedTrustModifier.NO_DATA

    def test_default_config_singleton(self) -> None:
        assert DEFAULT_MULTI_SIGNAL_TRUST_CONFIG.trusted_min == 0.7
