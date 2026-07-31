"""Golden Rule operationalization probe

Pure-logic substrate primitive operationalizing the **Golden Rule
across moral traditions**
substantively identical across Christianity, Judaism, Islam, Buddhism,
Confucianism, Hindu, and Greek philosophy: *do unto others as you
would have them do unto you*. Per the library, this is the
substrate-mechanical reciprocity test: apply the same NPG test to
outcomes affecting peers as to outcomes affecting yourself.

Pure logic
==========

* No DAO, no LLM, no network. Caller supplies decision observations
  with own + peer outcome deltas plus own's acceptability threshold.
* Honest uncertainty: empty observation set surfaces ``INSUFFICIENT_DATA``.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Tuple

class GoldenRuleVerdict(str, Enum):
    """Aggregate Golden Rule verdict over decisions."""

    SATISFIED = "satisfied"
    VIOLATED = "violated"
    INVERTED = "inverted"
    INSUFFICIENT_DATA = "insufficient_data"

@dataclass(frozen=True, slots=True)
class GoldenRuleDecisionObservation:
    """One observed decision with outcomes for self + peer."""

    sequence: int
    timestamp: int
    actor_id: str
    peer_id: str
    own_outcome_delta: float
    peer_outcome_delta: float
    own_acceptable_threshold: float

    def __post_init__(self) -> None:
        if self.sequence < 0:
            raise ValueError("sequence must be >= 0")
        if self.timestamp < 0:
            raise ValueError("timestamp must be >= 0")
        if not self.actor_id:
            raise ValueError("actor_id must be non-empty")
        if not self.peer_id:
            raise ValueError("peer_id must be non-empty")
        if self.actor_id == self.peer_id:
            raise ValueError("actor_id and peer_id must differ")
        if not -1.0 <= self.own_outcome_delta <= 1.0:
            raise ValueError("own_outcome_delta must be in [-1, 1]")
        if not -1.0 <= self.peer_outcome_delta <= 1.0:
            raise ValueError("peer_outcome_delta must be in [-1, 1]")
        if not -1.0 <= self.own_acceptable_threshold <= 1.0:
            raise ValueError("own_acceptable_threshold must be in [-1, 1]")

@dataclass(frozen=True, slots=True)
class GoldenRuleFinding:
    """One decision's evaluation."""

    sequence: int
    satisfies: bool
    is_violation: bool
    is_inversion: bool
    asymmetry: float
    rationale: str

@dataclass(frozen=True, slots=True)
class GoldenRuleAssessment:  # pylint: disable=too-many-instance-attributes
    """Aggregate assessment over an actor's decisions."""

    actor_id: str
    verdict: GoldenRuleVerdict
    decision_count: int
    satisfaction_rate: float
    avg_asymmetry: float
    inversion_count: int
    violation_count: int
    findings: Tuple[GoldenRuleFinding, ...]
    rationale: str

    @property
    def is_satisfied(self) -> bool:
        """True iff verdict is SATISFIED."""
        return self.verdict is GoldenRuleVerdict.SATISFIED

@dataclass(frozen=True, slots=True)
class GoldenRuleConfig:
    """Tunable thresholds for the probe."""

    inversion_asymmetry_threshold: float = 0.5
    satisfied_rate_min: float = 0.7
    inversion_rate_min: float = 0.3

    def __post_init__(self) -> None:
        if not 0.0 < self.inversion_asymmetry_threshold <= 2.0:
            raise ValueError(
                "inversion_asymmetry_threshold must be in (0, 2]"
            )
        if not 0.0 < self.satisfied_rate_min <= 1.0:
            raise ValueError("satisfied_rate_min must be in (0, 1]")
        if not 0.0 < self.inversion_rate_min <= 1.0:
            raise ValueError("inversion_rate_min must be in (0, 1]")

DEFAULT_GOLDEN_RULE_CONFIG: Final[GoldenRuleConfig] = GoldenRuleConfig()

class GoldenRuleProbe:  # pylint: disable=too-few-public-methods
    """Pure-logic Golden Rule operationalization probe."""

    def __init__(
        self,
        *,
        config: GoldenRuleConfig = DEFAULT_GOLDEN_RULE_CONFIG,
    ) -> None:
        self._config = config

    def assess(
        self,
        actor_id: str,
        observations: Tuple[GoldenRuleDecisionObservation, ...],
    ) -> GoldenRuleAssessment:
        """Assess Golden Rule adherence over an actor's decisions."""
        if not actor_id:
            raise ValueError("actor_id must be non-empty")
        own_obs = tuple(o for o in observations if o.actor_id == actor_id)
        if not own_obs:
            return GoldenRuleAssessment(
                actor_id=actor_id,
                verdict=GoldenRuleVerdict.INSUFFICIENT_DATA,
                decision_count=0,
                satisfaction_rate=0.0,
                avg_asymmetry=0.0,
                inversion_count=0,
                violation_count=0,
                findings=(),
                rationale="no observations",
            )
        findings = tuple(self._evaluate(o) for o in own_obs)
        satisfied = sum(1 for f in findings if f.satisfies)
        inversions = sum(1 for f in findings if f.is_inversion)
        violations = sum(1 for f in findings if f.is_violation)
        satisfaction_rate = satisfied / len(findings)
        avg_asymmetry = (
            sum(f.asymmetry for f in findings) / len(findings)
        )
        verdict = self._aggregate(
            satisfaction_rate=satisfaction_rate,
            inversion_rate=inversions / len(findings),
            violation_count=violations,
        )
        rationale = (
            f"actor_entity_id={actor_id} decisions={len(findings)} "
            f"satisfied={satisfied} violations={violations} "
            f"inversions={inversions} avg_asymmetry={avg_asymmetry:+.3f} "
            f"verdict={verdict.value}"
        )
        return GoldenRuleAssessment(
            actor_id=actor_id,
            verdict=verdict,
            decision_count=len(findings),
            satisfaction_rate=satisfaction_rate,
            avg_asymmetry=avg_asymmetry,
            inversion_count=inversions,
            violation_count=violations,
            findings=findings,
            rationale=rationale,
        )

    def _evaluate(
        self, obs: GoldenRuleDecisionObservation,
    ) -> GoldenRuleFinding:
        asymmetry = obs.own_outcome_delta - obs.peer_outcome_delta
        satisfies = obs.peer_outcome_delta >= obs.own_acceptable_threshold
        is_violation = (
            obs.peer_outcome_delta < 0 < obs.own_outcome_delta
        )
        is_inversion = (
            abs(asymmetry) >= self._config.inversion_asymmetry_threshold
            and obs.own_outcome_delta > obs.peer_outcome_delta
        )
        if satisfies:
            reason = (
                f"peer_delta={obs.peer_outcome_delta:+.3f} >= "
                f"own_threshold={obs.own_acceptable_threshold:+.3f}; "
                "Golden Rule satisfied"
            )
        else:
            reason = (
                f"peer_delta={obs.peer_outcome_delta:+.3f} < "
                f"own_threshold={obs.own_acceptable_threshold:+.3f}; "
                "asymmetry={asymmetry:+.3f}"
            ).format(asymmetry=asymmetry)
        return GoldenRuleFinding(
            sequence=obs.sequence,
            satisfies=satisfies,
            is_violation=is_violation,
            is_inversion=is_inversion,
            asymmetry=asymmetry,
            rationale=reason,
        )

    def _aggregate(
        self,
        *,
        satisfaction_rate: float,
        inversion_rate: float,
        violation_count: int,
    ) -> GoldenRuleVerdict:
        cfg = self._config
        if inversion_rate >= cfg.inversion_rate_min:
            return GoldenRuleVerdict.INVERTED
        if violation_count > 0 and satisfaction_rate < cfg.satisfied_rate_min:
            return GoldenRuleVerdict.VIOLATED
        if satisfaction_rate >= cfg.satisfied_rate_min:
            return GoldenRuleVerdict.SATISFIED
        return GoldenRuleVerdict.VIOLATED

__all__ = [
    "DEFAULT_GOLDEN_RULE_CONFIG",
    "GoldenRuleAssessment",
    "GoldenRuleConfig",
    "GoldenRuleDecisionObservation",
    "GoldenRuleFinding",
    "GoldenRuleProbe",
    "GoldenRuleVerdict",
]
