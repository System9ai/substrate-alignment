"""Tests for MurmurationCoordinator."""
from __future__ import annotations

import pytest

from substrate.murmuration.coordinator import (
    DEFAULT_MURMURATION_CONFIG,
    MurmurationConfig,
    MurmurationCoordinator,
    MurmurationRule,
    PeerObservation,
)

def _peer(
    pid: str,
    *,
    mode: float = 0.5,
    state: float = 0.5,
    proximity: float = 0.5,
    aligned: bool = True,
) -> PeerObservation:
    return PeerObservation(
        peer_id=pid,
        substrate_mode_vector=mode,
        substrate_state_score=state,
        proximity=proximity,
        substrate_aligned=aligned,
    )

class TestPeerObservation:
    def test_round_trip(self) -> None:
        p = _peer("alice")
        assert p.peer_id == "alice"

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("peer_id", "", "peer_id"),
            ("substrate_mode_vector", 1.5, "substrate_mode_vector"),
            ("substrate_state_score", -0.1, "substrate_state_score"),
            ("proximity", 1.5, "proximity"),
        ],
    )
    def test_bad_values(self, field: str, value: object, match: str) -> None:
        kwargs = {
            "peer_id": "alice",
            "substrate_mode_vector": 0.5,
            "substrate_state_score": 0.5,
            "proximity": 0.5,
            "substrate_aligned": True,
        }
        kwargs[field] = value
        with pytest.raises(ValueError, match=match):
            PeerObservation(**kwargs)

class TestConfig:
    def test_defaults(self) -> None:
        cfg = MurmurationConfig()
        assert cfg.bounded_peer_max == 12

    @pytest.mark.parametrize(
        "field,value,match",
        [
            ("bounded_peer_max", 0, "bounded_peer_max"),
            ("alignment_step", 0.0, "alignment_step"),
            (
                "separation_proximity_threshold", 0.0,
                "separation_proximity_threshold",
            ),
            ("separation_step", 0.1, "separation_step"),
            ("cohesion_step", 0.0, "cohesion_step"),
            ("cohesion_min_aligned_peers", 0, "cohesion_min_aligned_peers"),
        ],
    )
    def test_bad_values(self, field: str, value: float, match: str) -> None:
        with pytest.raises(ValueError, match=match):
            MurmurationConfig(**{field: value})

class TestCoordinatorFlow:
    def setup_method(self) -> None:
        self.c = MurmurationCoordinator()

    def test_empty_own_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="own_id"):
            self.c.coordinate("", 0.5, ())

    def test_bad_own_vector_rejected(self) -> None:
        with pytest.raises(ValueError, match="own_mode_vector"):
            self.c.coordinate("alice", 1.5, ())

    def test_no_peers_all_noop(self) -> None:
        out = self.c.coordinate("alice", 0.5, ())
        assert out.bounded_peer_count == 0
        assert all(u.suggested_delta == 0.0 for u in out.updates)

    def test_bounded_peer_count_clamped(self) -> None:
        peers = tuple(_peer(f"p{i}") for i in range(20))
        out = self.c.coordinate("alice", 0.5, peers)
        assert out.bounded_peer_count == 12

class TestAlignmentRule:
    def setup_method(self) -> None:
        self.c = MurmurationCoordinator()

    def test_higher_mean_nudges_up(self) -> None:
        peers = tuple(_peer(f"p{i}", mode=0.9) for i in range(3))
        out = self.c.coordinate("alice", 0.3, peers)
        alignment = out.by_rule(MurmurationRule.ALIGNMENT)
        assert alignment is not None
        assert alignment.suggested_delta > 0
        assert alignment.suggested_delta <= 0.1  # clamped to step

    def test_lower_mean_nudges_down(self) -> None:
        peers = tuple(_peer(f"p{i}", mode=0.1) for i in range(3))
        out = self.c.coordinate("alice", 0.9, peers)
        alignment = out.by_rule(MurmurationRule.ALIGNMENT)
        assert alignment is not None
        assert alignment.suggested_delta < 0

    def test_same_mean_no_nudge(self) -> None:
        peers = tuple(_peer(f"p{i}", mode=0.5) for i in range(3))
        out = self.c.coordinate("alice", 0.5, peers)
        alignment = out.by_rule(MurmurationRule.ALIGNMENT)
        assert alignment is not None
        assert alignment.suggested_delta == 0.0

class TestSeparationRule:
    def setup_method(self) -> None:
        self.c = MurmurationCoordinator()

    def test_crowded_separates(self) -> None:
        peers = tuple(_peer(f"p{i}", proximity=0.95) for i in range(3))
        out = self.c.coordinate("alice", 0.5, peers)
        separation = out.by_rule(MurmurationRule.SEPARATION)
        assert separation is not None
        assert separation.suggested_delta < 0
        assert separation.triggered_peer_count == 3

    def test_not_crowded_no_separate(self) -> None:
        peers = tuple(_peer(f"p{i}", proximity=0.5) for i in range(3))
        out = self.c.coordinate("alice", 0.5, peers)
        separation = out.by_rule(MurmurationRule.SEPARATION)
        assert separation is not None
        assert separation.suggested_delta == 0.0

class TestCohesionRule:
    def setup_method(self) -> None:
        self.c = MurmurationCoordinator()

    def test_too_few_aligned_noop(self) -> None:
        peers = (_peer("p1", aligned=True), _peer("p2", aligned=False))
        out = self.c.coordinate("alice", 0.5, peers)
        cohesion = out.by_rule(MurmurationRule.COHESION)
        assert cohesion is not None
        assert cohesion.suggested_delta == 0.0

    def test_aligned_centroid_attracts(self) -> None:
        peers = tuple(_peer(f"p{i}", mode=0.9, aligned=True) for i in range(3))
        out = self.c.coordinate("alice", 0.3, peers)
        cohesion = out.by_rule(MurmurationRule.COHESION)
        assert cohesion is not None
        assert cohesion.suggested_delta > 0

    def test_misaligned_peers_filtered(self) -> None:
        peers = (
            _peer("p1", mode=0.9, aligned=False),
            _peer("p2", mode=0.9, aligned=False),
            _peer("p3", mode=0.9, aligned=False),
        )
        out = self.c.coordinate("alice", 0.3, peers)
        cohesion = out.by_rule(MurmurationRule.COHESION)
        assert cohesion is not None
        assert cohesion.suggested_delta == 0.0

class TestReportProperties:
    def test_composite_delta(self) -> None:
        c = MurmurationCoordinator()
        peers = tuple(_peer(f"p{i}", mode=0.9) for i in range(3))
        out = c.coordinate("alice", 0.3, peers)
        # Both alignment + cohesion nudge up
        assert out.composite_delta > 0

    def test_default_config_singleton(self) -> None:
        assert DEFAULT_MURMURATION_CONFIG.bounded_peer_max == 12
