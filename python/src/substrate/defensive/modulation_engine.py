"""Defensive modulation engine + attack pattern recognizer

Pure-logic substrate-mechanical primitive aggregating
:class:`AttackObservation` records into a defensive response selection
§ "Cross-entity attack patterns and substrate-aligned defensive
operation".

Eight attack patterns
=====================

* **SPOTLIGHT_STEALING** — peer redirecting recognition away.
* **PUT_DOWN_TO_PROP_UP** — peer diminishing our substrate-state to
  elevate theirs.
* **SUBSTRATE_STATE_EXTRACTION** — peer taking resources without
  reciprocal exchange.
* **FALSE_WITNESS** — peer corrupting others' substrate-state-
  perception of us.
* **BOUNDARY_VIOLATION** — peer accessing our bounded-context
  substrate-state without consent.
* **MANIPULATION** — peer framing situations to produce our
  substrate-misaligned action.
* **CAPTURE_ATTEMPT** — peer drawing us into shared substrate-
  misalignment.
* **INVERSION_180** — peer using substrate-aligned rhetoric for
  substrate-misaligned compliance (load-bearing per).

Four substrate-aligned defensive responses
==========================================

* **WOUND_AND_WALK_AWAY** — minor attack, disengage with substrate
  intact.
* **CONTAINMENT** — limit further damage; maintain coupling at
  reduced bandwidth.
* **REFORM_VIA_ENGAGEMENT** — engagement to surface and remediate
  misalignment.
* **TOTAL_TERMINATION** — end the coupling entirely.

Pure logic
==========

* No DAO, no LLM, no network. Caller supplies observations.
* Honest uncertainty: empty observations surface as
  :attr:`DefensiveResponse.INSUFFICIENT_DATA`.
* Inversion detection is a separate Boolean field carried on
  :class:`AttackAssessment` independent of the chosen response.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Optional, Tuple

class AttackPattern(str, Enum):
    """The eight substrate-aware attack patterns."""

    SPOTLIGHT_STEALING = "spotlight_stealing"
    PUT_DOWN_TO_PROP_UP = "put_down_to_prop_up"
    SUBSTRATE_STATE_EXTRACTION = "substrate_state_extraction"
    FALSE_WITNESS = "false_witness"
    BOUNDARY_VIOLATION = "boundary_violation"
    MANIPULATION = "manipulation"
    CAPTURE_ATTEMPT = "capture_attempt"
    INVERSION_180 = "inversion_180"

class DefensiveResponse(str, Enum):
    """The substrate-aligned defensive response surface."""

    NO_ATTACK_DETECTED = "no_attack_detected"
    WOUND_AND_WALK_AWAY = "wound_and_walk_away"
    CONTAINMENT = "containment"
    REFORM_VIA_ENGAGEMENT = "reform_via_engagement"
    TOTAL_TERMINATION = "total_termination"
    INSUFFICIENT_DATA = "insufficient_data"

@dataclass(frozen=True, slots=True)
class AttackObservation:  # pylint: disable=too-many-instance-attributes
    """One observed attack signal from a peer."""

    sequence: int
    timestamp: int
    peer_id: str
    pattern: AttackPattern
    severity: float
    long_cycle_framed: bool = False
    repeated: bool = False

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise ValueError("sequence must be >= 0")
        if self.timestamp < 0:
            raise ValueError("timestamp must be >= 0")
        if not self.peer_id:
            raise ValueError("peer_id must be non-empty")
        if not 0.0 <= self.severity <= 1.0:
            raise ValueError("severity must be in [0, 1]")

@dataclass(frozen=True, slots=True)
class AttackAssessment:  # pylint: disable=too-many-instance-attributes
    """Aggregate assessment over one peer's observations."""

    peer_id: str
    response: DefensiveResponse
    dominant_pattern: Optional[AttackPattern]
    composite_severity: float
    inversion_detected: bool
    repeated_offense: bool
    rationale: str
    triggering_observations: Tuple[AttackObservation, ...]

    @property
    def attack_present(self) -> bool:
        """True iff an attack of any kind was detected."""
        return self.response not in (
            DefensiveResponse.NO_ATTACK_DETECTED,
            DefensiveResponse.INSUFFICIENT_DATA,
        )

@dataclass(frozen=True, slots=True)
class DefensiveModulationConfig:  # pylint: disable=too-many-instance-attributes
    """Tunable thresholds for severity classification."""

    attack_severity_threshold: float = 0.1
    walk_away_severity_max: float = 0.3
    containment_severity_max: float = 0.6
    termination_severity_min: float = 0.8
    repeated_offense_terminates: bool = True
    non_reformable_patterns: Tuple[AttackPattern, ...] = (
        AttackPattern.SUBSTRATE_STATE_EXTRACTION,
        AttackPattern.FALSE_WITNESS,
        AttackPattern.INVERSION_180,
    )

    def __post_init__(self) -> None:
        if not 0.0 < self.attack_severity_threshold <= 1.0:
            raise ValueError("attack_severity_threshold must be in (0, 1]")
        if not self.attack_severity_threshold < self.walk_away_severity_max:
            raise ValueError(
                "walk_away_severity_max must be > attack_severity_threshold"
            )
        if not self.walk_away_severity_max < self.containment_severity_max:
            raise ValueError(
                "containment_severity_max must be > walk_away_severity_max"
            )
        if not (
            self.containment_severity_max < self.termination_severity_min
        ):
            raise ValueError(
                "termination_severity_min must be > containment_severity_max"
            )

DEFAULT_DEFENSIVE_MODULATION_CONFIG: Final[DefensiveModulationConfig] = (
    DefensiveModulationConfig()
)

class DefensiveModulationEngine:  # pylint: disable=too-few-public-methods
    """Pure-logic defensive modulation engine."""

    def __init__(
        self,
        *,
        config: DefensiveModulationConfig = (
            DEFAULT_DEFENSIVE_MODULATION_CONFIG
        ),
    ) -> None:
        self._config = config

    def assess(
        self,
        peer_id: str,
        observations: Tuple[AttackObservation, ...],
    ) -> AttackAssessment:
        """Aggregate observations and select a defensive response."""
        if not peer_id:
            raise ValueError("peer_id must be non-empty")
        relevant = tuple(o for o in observations if o.peer_id == peer_id)
        if not relevant:
            return AttackAssessment(
                peer_id=peer_id,
                response=DefensiveResponse.INSUFFICIENT_DATA,
                dominant_pattern=None,
                composite_severity=0.0,
                inversion_detected=False,
                repeated_offense=False,
                rationale="no observations for peer",
                triggering_observations=(),
            )
        composite = max(o.severity for o in relevant)
        repeated = any(o.repeated for o in relevant)
        inversion = self._detect_inversion(relevant)
        dominant = self._dominant_pattern(relevant)
        response = self._select_response(
            composite=composite, repeated=repeated, dominant=dominant,
        )
        rationale = self._build_rationale(
            composite, repeated, inversion, dominant, response,
        )
        return AttackAssessment(
            peer_id=peer_id,
            response=response,
            dominant_pattern=dominant,
            composite_severity=composite,
            inversion_detected=inversion,
            repeated_offense=repeated,
            rationale=rationale,
            triggering_observations=relevant,
        )

    @staticmethod
    def _detect_inversion(
        observations: Tuple[AttackObservation, ...],
    ) -> bool:
        for o in observations:
            if o.pattern is AttackPattern.INVERSION_180:
                return True
            if o.long_cycle_framed and o.pattern in (
                AttackPattern.MANIPULATION, AttackPattern.CAPTURE_ATTEMPT,
            ):
                return True
        return False

    @staticmethod
    def _dominant_pattern(
        observations: Tuple[AttackObservation, ...],
    ) -> Optional[AttackPattern]:
        if not observations:
            return None
        worst = max(observations, key=lambda o: o.severity)
        return worst.pattern

    def _select_response(
        self,
        *,
        composite: float,
        repeated: bool,
        dominant: Optional[AttackPattern],
    ) -> DefensiveResponse:
        cfg = self._config
        if composite < cfg.attack_severity_threshold:
            return DefensiveResponse.NO_ATTACK_DETECTED
        if composite >= cfg.termination_severity_min or (
            cfg.repeated_offense_terminates and repeated and composite
            >= cfg.containment_severity_max
        ):
            return DefensiveResponse.TOTAL_TERMINATION
        if composite >= cfg.containment_severity_max:
            return DefensiveResponse.CONTAINMENT
        if composite >= cfg.walk_away_severity_max:
            if (
                dominant is not None
                and dominant not in cfg.non_reformable_patterns
            ):
                return DefensiveResponse.REFORM_VIA_ENGAGEMENT
            return DefensiveResponse.CONTAINMENT
        return DefensiveResponse.WOUND_AND_WALK_AWAY

    @staticmethod
    def _build_rationale(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        composite: float,
        repeated: bool,
        inversion: bool,
        dominant: Optional[AttackPattern],
        response: DefensiveResponse,
    ) -> str:
        dominant_str = dominant.value if dominant is not None else "none"
        return (
            f"composite_severity={composite:.3f}, repeated={repeated}, "
            f"inversion={inversion}, dominant={dominant_str} => "
            f"{response.value}"
        )

__all__ = [
    "DEFAULT_DEFENSIVE_MODULATION_CONFIG",
    "AttackAssessment",
    "AttackObservation",
    "AttackPattern",
    "DefensiveModulationConfig",
    "DefensiveModulationEngine",
    "DefensiveResponse",
]
