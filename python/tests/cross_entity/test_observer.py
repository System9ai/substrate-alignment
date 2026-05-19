"""Tests for CrossEntityStateSignalObserver."""
from __future__ import annotations

import pytest

from substrate.cross_entity.observer import (
    DEFAULT_CROSS_ENTITY_OBSERVER_CONFIG,
    CrossEntityObserverConfig,
    CrossEntityStateSignalObserver,
    ObservationScope,
    PeerStateObservation,
)

def _obs(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    seq: int,
    *,
    observer: str = "alice",
    peer: str = "bob",
    scope: ObservationScope = ObservationScope.CELL,
    alignment: float = 0.8,
    health: float = 0.9,
    coupling: float = 0.7,
    signals: tuple = (),
    quality: float = 0.9,
) -> PeerStateObservation:
    return PeerStateObservation(
        sequence=seq,
        timestamp=seq,
        observer_id=observer,
        peer_id=peer,
        peer_scope=scope,
        alignment_score=alignment,
        health_score=health,
        coupling_field_strength=coupling,
        primary_signal_kinds=signals,
        observation_quality=quality,
    )

class TestObservationValidation:
    def test_round_trip(self) -> None:
        o = _obs(0)
        assert o.observer_id == "alice"

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("observer", "", "observer_id"),
            ("peer", "", "peer_id"),
            ("alignment", 1.5, "alignment_score"),
            ("health", -0.1, "health_score"),
            ("coupling", 1.5, "coupling_field_strength"),
            ("quality", -0.1, "observation_quality"),
        ],
    )
    def test_bad_values(self, field: str, value: object, match: str) -> None:
        kwargs = {"seq": 0}
        kwargs[field] = value
        with pytest.raises(ValueError, match=match):
            _obs(**kwargs)  # type: ignore[arg-type]

    def test_self_observation_rejected(self) -> None:
        with pytest.raises(ValueError, match="must differ"):
            _obs(0, observer="alice", peer="alice")

class TestConfig:
    def test_defaults(self) -> None:
        cfg = CrossEntityObserverConfig()
        assert cfg.quality_threshold == 0.3

    def test_bad_threshold(self) -> None:
        with pytest.raises(ValueError, match="quality_threshold"):
            CrossEntityObserverConfig(quality_threshold=0.0)

class TestObserveFlow:
    def setup_method(self) -> None:
        self.o = CrossEntityStateSignalObserver()

    def test_empty_observer_rejected(self) -> None:
        with pytest.raises(ValueError, match="observer_id"):
            self.o.observe("", ())

    def test_no_observations(self) -> None:
        out = self.o.observe("alice", ())
        assert out.cell_peer_count == 0
        assert out.node_peer_count == 0

    def test_low_quality_filtered(self) -> None:
        out = self.o.observe("alice", (_obs(0, quality=0.1),))
        assert out.total_observation_count == 0

class TestScopeSeparation:
    def setup_method(self) -> None:
        self.o = CrossEntityStateSignalObserver()

    def test_cell_and_node_separated(self) -> None:
        obs = (
            _obs(0, peer="cell-1", scope=ObservationScope.CELL),
            _obs(1, peer="node-1", scope=ObservationScope.NODE),
        )
        out = self.o.observe("alice", obs)
        assert out.cell_peer_count == 1
        assert out.node_peer_count == 1
        assert out.cell_peers[0].is_cell_scope
        assert out.node_peers[0].is_node_scope

    def test_digest_by_peer_id(self) -> None:
        obs = (
            _obs(0, peer="cell-1"),
            _obs(1, peer="cell-1", alignment=0.6),
        )
        out = self.o.observe("alice", obs)
        digest = out.digest_for("cell-1")
        assert digest is not None
        assert digest.observation_count == 2
        assert abs(digest.avg_alignment - 0.7) < 1e-9

class TestSignalFrequencies:
    def test_aggregates_signal_kinds(self) -> None:
        o = CrossEntityStateSignalObserver()
        obs = (
            _obs(0, peer="cell-1", signals=("threat", "loss")),
            _obs(1, peer="cell-1", signals=("threat", "validation")),
        )
        out = o.observe("alice", obs)
        digest = out.digest_for("cell-1")
        assert digest is not None
        assert digest.signal_kind_frequencies["threat"] == 2
        assert digest.signal_kind_frequencies["loss"] == 1
        assert digest.signal_kind_frequencies["validation"] == 1

class TestObserverFiltering:
    def test_only_own_observations(self) -> None:
        o = CrossEntityStateSignalObserver()
        obs = (
            _obs(0, observer="alice", peer="bob"),
            _obs(1, observer="carol", peer="bob"),
        )
        out = o.observe("alice", obs)
        assert out.total_observation_count == 1

    def test_default_config_singleton(self) -> None:
        assert DEFAULT_CROSS_ENTITY_OBSERVER_CONFIG.quality_threshold == 0.3
