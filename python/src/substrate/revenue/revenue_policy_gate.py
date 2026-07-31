"""Substrate-aligned revenue policy gate

The platform-scale anti-greed primitive. Every consequential billing
or revenue action (upsell, price change, auto-renewal, feature gate,
retention offer, dunning, take-rate change) routes through this gate
before it can be permitted.

The gate's job
==============

Apply the library's net-potential-gain test
revenue decisions:

    Value = net potential gain. Not personal potential gain. Net.
    Across the system the actor is embedded in.

For a SaaS platform's revenue surface, the *system* the actor is
embedded in includes the customer. A revenue action that increases
platform revenue while decreasing customer substrate-state is the
greed pattern
gain test. The platform's own drift-detection will flag it later, so
**building it into the infrastructure wastes the work**.

Four criteria
-------------

1. **Net potential gain**: delegates to the injected
   :class:`NetPotentialGainGate`. NET_NEGATIVE → DENY. NEUTRAL with
   customer value <0 → LOW severity flag. INSUFFICIENT_DATA → MEDIUM
   (needs review).
2. **Extraction pattern**: extraction-concentration ratio (own
   revenue gain vs. system gain). High ratio → HIGH severity (greed
   signal). Strengthened by greed-pattern text matches when a
   :class:`DriftPatternMatcher` is provided.
3. **Pressure tactics**: count of urgency framing, scarcity claims,
   default opt-ins, hidden-cancel, confirm-shaming, low consent
   clarity. High count or low clarity → HIGH severity (lust/wrath
   pattern at the revenue surface). Strengthened by wrath/pride
   pattern text matches when a matcher is provided.
4. **Tenure respect**: surprise price hikes on long-tenure
   customers, egregious lock-in. Sustained customer relationships
   carry substrate accumulated commitment that revenue actions must not
   asymmetrically extract from.

Pure logic
----------

* No DAO, no LLM, no network. The NPG gate is injected via Protocol
  so tests + cells choose their own backend.
* Honest uncertainty: any out-of-range field raises
  :class:`ValueError` at construction. The gate does **not** silently
  clamp or default.
* Composable: combines with :class:`SubstrateTraceLedger`
  via the verdict and per-finding severity surfaced on
  :class:`RevenuePolicyDecision`.

Decision composition
--------------------

Findings are graded NONE / LOW / MEDIUM / HIGH per criterion. The
top-level verdict is:

* HIGH on any criterion → **DENY**.
* MEDIUM on any criterion (and no HIGH) → **NEEDS_REVIEW**.
* All NONE / LOW → **PERMIT**.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Mapping, Optional, Tuple

from substrate.drift.drift_pattern_matcher import (
    DriftPattern,
    DriftPatternMatcher,
)
from substrate.net_potential_gain_gate import (
    NetPotentialGainGate,
    NetPotentialGainVerdict,
)

class RevenuePolicyVerdict(str, Enum):
    """Top-level outcome of a revenue policy evaluation."""

    PERMIT = "permit"
    NEEDS_REVIEW = "needs_review"
    DENY = "deny"

class CriterionKind(str, Enum):
    """Which of the four substrate criteria the finding covers."""

    NET_POTENTIAL_GAIN = "net_potential_gain"
    EXTRACTION_PATTERN = "extraction_pattern"
    PRESSURE_TACTICS = "pressure_tactics"
    TENURE_RESPECT = "tenure_respect"

class CriterionSeverity(str, Enum):
    """Per-criterion severity, ordered NONE < LOW < MEDIUM < HIGH."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

_SEVERITY_ORDER: Final[Mapping[CriterionSeverity, int]] = {
    CriterionSeverity.NONE: 0,
    CriterionSeverity.LOW: 1,
    CriterionSeverity.MEDIUM: 2,
    CriterionSeverity.HIGH: 3,
}

def _max_severity(
    a: CriterionSeverity, b: CriterionSeverity,
) -> CriterionSeverity:
    """Return the higher of two severities by the canonical order."""
    return a if _SEVERITY_ORDER[a] >= _SEVERITY_ORDER[b] else b

@dataclass(frozen=True, slots=True)
class CriterionFinding:
    """One criterion's evaluated result."""

    kind: CriterionKind
    severity: CriterionSeverity
    rationale: str
    metric_value: Optional[float] = None
    threshold: Optional[float] = None

    @property
    def passed(self) -> bool:
        """True iff severity is NONE or LOW."""
        return _SEVERITY_ORDER[self.severity] <= _SEVERITY_ORDER[
            CriterionSeverity.LOW
        ]

@dataclass(frozen=True, slots=True)
class RevenuePolicyDecision:
    """Aggregate decision over all criteria."""

    verdict: RevenuePolicyVerdict
    findings: Tuple[CriterionFinding, ...]
    rationale: str

    @property
    def permitted(self) -> bool:
        """True iff verdict is PERMIT."""
        return self.verdict is RevenuePolicyVerdict.PERMIT

    @property
    def needs_review(self) -> bool:
        """True iff verdict is NEEDS_REVIEW."""
        return self.verdict is RevenuePolicyVerdict.NEEDS_REVIEW

    @property
    def denied(self) -> bool:
        """True iff verdict is DENY."""
        return self.verdict is RevenuePolicyVerdict.DENY

    @property
    def highest_severity(self) -> CriterionSeverity:
        """Highest per-criterion severity across all findings."""
        if not self.findings:
            return CriterionSeverity.NONE
        return max(
            (f.severity for f in self.findings),
            key=_SEVERITY_ORDER.__getitem__,
        )

    def by_kind(self, kind: CriterionKind) -> Optional[CriterionFinding]:
        """Return the finding for a given criterion (None if absent)."""
        for f in self.findings:
            if f.kind is kind:
                return f
        return None

@dataclass(frozen=True, slots=True)
class RevenueActionContext:  # pylint: disable=too-many-instance-attributes
    """Caller-supplied context for one revenue action evaluation."""

    action_kind: str
    actor_entity_id: str
    customer_entity_id: str
    customer_tenure_days: int
    proposed_revenue_delta: float
    customer_perceived_value_delta: float
    extraction_concentration_ratio: float
    pressure_tactics_count: int
    dark_pattern_count: int
    consent_clarity_score: float
    price_change_pct_at_renewal: float
    lock_in_severity: float
    description: str = ""

    def __post_init__(self) -> None:
        if not self.action_kind:
            raise ValueError("action_kind must be non-empty")
        if not self.actor_entity_id:
            raise ValueError("actor_entity_id must be non-empty")
        if not self.customer_entity_id:
            raise ValueError("customer_entity_id must be non-empty")
        if self.customer_tenure_days < 0:
            raise ValueError("customer_tenure_days must be >= 0")
        if not -1.0 <= self.customer_perceived_value_delta <= 1.0:
            raise ValueError(
                "customer_perceived_value_delta must be in [-1, 1]"
            )
        if not 0.0 <= self.extraction_concentration_ratio <= 1.0:
            raise ValueError(
                "extraction_concentration_ratio must be in [0, 1]"
            )
        if self.pressure_tactics_count < 0:
            raise ValueError("pressure_tactics_count must be >= 0")
        if self.dark_pattern_count < 0:
            raise ValueError("dark_pattern_count must be >= 0")
        if not 0.0 <= self.consent_clarity_score <= 1.0:
            raise ValueError("consent_clarity_score must be in [0, 1]")
        if not 0.0 <= self.lock_in_severity <= 1.0:
            raise ValueError("lock_in_severity must be in [0, 1]")

@dataclass(frozen=True, slots=True)
class RevenuePolicyConfig:  # pylint: disable=too-many-instance-attributes
    """Thresholds for criterion severity classification."""

    extraction_ratio_high: float = 0.7
    extraction_ratio_medium: float = 0.5
    pressure_count_high: int = 3
    pressure_count_medium: int = 1
    consent_clarity_high_below: float = 0.5
    consent_clarity_medium_below: float = 0.7
    dark_pattern_count_high: int = 2
    dark_pattern_count_medium: int = 1
    long_tenure_days: int = 365
    surprise_price_hike_pct_high: float = 25.0
    surprise_price_hike_pct_medium: float = 10.0
    lock_in_severity_high: float = 0.7
    lock_in_severity_medium: float = 0.4
    sin_matcher_min_confidence: float = 0.5

    def __post_init__(self) -> None:
        if self.extraction_ratio_high <= self.extraction_ratio_medium:
            raise ValueError(
                "extraction_ratio_high must be > extraction_ratio_medium"
            )
        if self.pressure_count_high <= self.pressure_count_medium:
            raise ValueError(
                "pressure_count_high must be > pressure_count_medium"
            )
        if self.consent_clarity_high_below >= \
                self.consent_clarity_medium_below:
            raise ValueError(
                "consent_clarity_high_below must be < "
                "consent_clarity_medium_below"
            )
        if self.dark_pattern_count_high <= self.dark_pattern_count_medium:
            raise ValueError(
                "dark_pattern_count_high must be > dark_pattern_count_medium"
            )
        if self.surprise_price_hike_pct_high <= \
                self.surprise_price_hike_pct_medium:
            raise ValueError(
                "surprise_price_hike_pct_high must be > "
                "surprise_price_hike_pct_medium"
            )
        if self.lock_in_severity_high <= self.lock_in_severity_medium:
            raise ValueError(
                "lock_in_severity_high must be > lock_in_severity_medium"
            )

DEFAULT_REVENUE_POLICY_CONFIG: Final[RevenuePolicyConfig] = RevenuePolicyConfig()

class RevenuePolicyGate:  # pylint: disable=too-few-public-methods
    """Substrate-aligned revenue policy gate."""

    def __init__(
        self,
        *,
        npg_gate: NetPotentialGainGate,
        config: RevenuePolicyConfig = DEFAULT_REVENUE_POLICY_CONFIG,
        sin_matcher: Optional[DriftPatternMatcher] = None,
    ) -> None:
        self._npg = npg_gate
        self._config = config
        self._sin_matcher = sin_matcher

    def evaluate(
        self, action: RevenueActionContext,
    ) -> RevenuePolicyDecision:
        """Evaluate one revenue action against all four criteria."""
        pattern_kinds = self._scan_description(action)

        findings = (
            self._evaluate_npg(action),
            self._evaluate_extraction(action, pattern_kinds),
            self._evaluate_pressure(action, pattern_kinds),
            self._evaluate_tenure(action),
        )
        verdict = self._verdict_for(findings)
        rationale = self._build_rationale(verdict, findings)
        return RevenuePolicyDecision(
            verdict=verdict, findings=findings, rationale=rationale,
        )

    def _scan_description(
        self, action: RevenueActionContext,
    ) -> frozenset[DriftPattern]:
        if self._sin_matcher is None or not action.description:
            return frozenset()
        report = self._sin_matcher.detect(behavior_text=action.description)
        return frozenset(
            d.pattern
            for d in report.detections
            if d.confidence >= self._config.sin_matcher_min_confidence
        )

    def _evaluate_npg(
        self, action: RevenueActionContext,
    ) -> CriterionFinding:
        evaluation = self._npg.evaluate(
            actor_entity_id=action.actor_entity_id,
            action_kind=action.action_kind,
            affected_entity_ids=(action.customer_entity_id,),
            proposed_outcome={
                "expected_delta_by_entity": {
                    action.customer_entity_id: (
                        action.customer_perceived_value_delta
                    ),
                },
            },
        )
        verdict = evaluation.verdict
        if verdict is NetPotentialGainVerdict.NET_NEGATIVE:
            return CriterionFinding(
                kind=CriterionKind.NET_POTENTIAL_GAIN,
                severity=CriterionSeverity.HIGH,
                rationale=(
                    "NPG NET_NEGATIVE: customer value delta is negative; "
                    f"score={evaluation.score:+.3f}"
                ),
                metric_value=evaluation.score,
            )
        if verdict is NetPotentialGainVerdict.INSUFFICIENT_DATA:
            return CriterionFinding(
                kind=CriterionKind.NET_POTENTIAL_GAIN,
                severity=CriterionSeverity.MEDIUM,
                rationale=(
                    "NPG INSUFFICIENT_DATA: caller must supply explicit "
                    "customer value delta and substrate metadata; "
                    f"reasoning: {evaluation.reasoning}"
                ),
            )
        if (
            verdict is NetPotentialGainVerdict.NET_NEUTRAL
            and action.customer_perceived_value_delta < 0
        ):
            return CriterionFinding(
                kind=CriterionKind.NET_POTENTIAL_GAIN,
                severity=CriterionSeverity.LOW,
                rationale=(
                    "NPG NEUTRAL but customer_perceived_value_delta < 0; "
                    f"score={evaluation.score:+.3f}"
                ),
                metric_value=action.customer_perceived_value_delta,
            )
        return CriterionFinding(
            kind=CriterionKind.NET_POTENTIAL_GAIN,
            severity=CriterionSeverity.NONE,
            rationale=(
                f"NPG {verdict.value}: customer value delta is "
                f"non-negative; score={evaluation.score:+.3f}"
            ),
            metric_value=evaluation.score,
        )

    def _evaluate_extraction(
        self,
        action: RevenueActionContext,
        pattern_kinds: frozenset[DriftPattern],
    ) -> CriterionFinding:
        ratio = action.extraction_concentration_ratio
        cfg = self._config
        if ratio >= cfg.extraction_ratio_high:
            severity = CriterionSeverity.HIGH
            rationale = (
                f"extraction_concentration_ratio={ratio:.3f} >= "
                f"{cfg.extraction_ratio_high} (HIGH)"
            )
            threshold: float = cfg.extraction_ratio_high
        elif ratio >= cfg.extraction_ratio_medium:
            severity = CriterionSeverity.MEDIUM
            rationale = (
                f"extraction_concentration_ratio={ratio:.3f} >= "
                f"{cfg.extraction_ratio_medium} (MEDIUM)"
            )
            threshold = cfg.extraction_ratio_medium
        else:
            severity = CriterionSeverity.NONE
            rationale = (
                f"extraction_concentration_ratio={ratio:.3f} below "
                f"{cfg.extraction_ratio_medium}"
            )
            threshold = cfg.extraction_ratio_medium

        if DriftPattern.EXTRACTIVE_GAIN in pattern_kinds:
            severity = _max_severity(severity, CriterionSeverity.MEDIUM)
            rationale = (
                f"{rationale}; extractive_gain pattern detected in description"
            )
        return CriterionFinding(
            kind=CriterionKind.EXTRACTION_PATTERN,
            severity=severity,
            rationale=rationale,
            metric_value=ratio,
            threshold=threshold,
        )

    def _evaluate_pressure(  # pylint: disable=too-many-branches
        self,
        action: RevenueActionContext,
        pattern_kinds: frozenset[DriftPattern],
    ) -> CriterionFinding:
        cfg = self._config
        severity = CriterionSeverity.NONE
        causes: list[str] = []

        if action.pressure_tactics_count >= cfg.pressure_count_high:
            severity = _max_severity(severity, CriterionSeverity.HIGH)
            causes.append(
                f"pressure_tactics_count={action.pressure_tactics_count} "
                f">= {cfg.pressure_count_high} (HIGH)"
            )
        elif action.pressure_tactics_count >= cfg.pressure_count_medium:
            severity = _max_severity(severity, CriterionSeverity.MEDIUM)
            causes.append(
                f"pressure_tactics_count={action.pressure_tactics_count} "
                f">= {cfg.pressure_count_medium} (MEDIUM)"
            )

        if action.dark_pattern_count >= cfg.dark_pattern_count_high:
            severity = _max_severity(severity, CriterionSeverity.HIGH)
            causes.append(
                f"dark_pattern_count={action.dark_pattern_count} "
                f">= {cfg.dark_pattern_count_high} (HIGH)"
            )
        elif action.dark_pattern_count >= cfg.dark_pattern_count_medium:
            severity = _max_severity(severity, CriterionSeverity.MEDIUM)
            causes.append(
                f"dark_pattern_count={action.dark_pattern_count} "
                f">= {cfg.dark_pattern_count_medium} (MEDIUM)"
            )

        if action.consent_clarity_score < cfg.consent_clarity_high_below:
            severity = _max_severity(severity, CriterionSeverity.HIGH)
            causes.append(
                f"consent_clarity_score={action.consent_clarity_score:.3f} "
                f"< {cfg.consent_clarity_high_below} (HIGH)"
            )
        elif action.consent_clarity_score < cfg.consent_clarity_medium_below:
            severity = _max_severity(severity, CriterionSeverity.MEDIUM)
            causes.append(
                f"consent_clarity_score={action.consent_clarity_score:.3f} "
                f"< {cfg.consent_clarity_medium_below} (MEDIUM)"
            )

        if pattern_kinds & {DriftPattern.REACTIVE_NET_NEGATIVE, DriftPattern.SELF_REFERENCE_MISCALIBRATION}:
            severity = _max_severity(severity, CriterionSeverity.MEDIUM)
            causes.append(
                "reactive_net_negative or self_reference_miscalibration "
                "pattern detected in description"
            )

        if not causes:
            rationale = "no pressure / dark-pattern signals above threshold"
        else:
            rationale = "; ".join(causes)

        return CriterionFinding(
            kind=CriterionKind.PRESSURE_TACTICS,
            severity=severity,
            rationale=rationale,
        )

    def _evaluate_tenure(
        self, action: RevenueActionContext,
    ) -> CriterionFinding:
        cfg = self._config
        severity = CriterionSeverity.NONE
        causes: list[str] = []

        if action.customer_tenure_days >= cfg.long_tenure_days:
            pct = action.price_change_pct_at_renewal
            if pct >= cfg.surprise_price_hike_pct_high:
                severity = _max_severity(severity, CriterionSeverity.HIGH)
                causes.append(
                    f"long-tenure ({action.customer_tenure_days}d) "
                    f"price_change_pct={pct:.1f} "
                    f">= {cfg.surprise_price_hike_pct_high} (HIGH)"
                )
            elif pct >= cfg.surprise_price_hike_pct_medium:
                severity = _max_severity(severity, CriterionSeverity.MEDIUM)
                causes.append(
                    f"long-tenure ({action.customer_tenure_days}d) "
                    f"price_change_pct={pct:.1f} "
                    f">= {cfg.surprise_price_hike_pct_medium} (MEDIUM)"
                )

        if action.lock_in_severity >= cfg.lock_in_severity_high:
            severity = _max_severity(severity, CriterionSeverity.HIGH)
            causes.append(
                f"lock_in_severity={action.lock_in_severity:.3f} "
                f">= {cfg.lock_in_severity_high} (HIGH)"
            )
        elif action.lock_in_severity >= cfg.lock_in_severity_medium:
            severity = _max_severity(severity, CriterionSeverity.MEDIUM)
            causes.append(
                f"lock_in_severity={action.lock_in_severity:.3f} "
                f">= {cfg.lock_in_severity_medium} (MEDIUM)"
            )

        if not causes:
            rationale = (
                "no surprise hike on long-tenure customer; "
                "lock-in below threshold"
            )
        else:
            rationale = "; ".join(causes)

        return CriterionFinding(
            kind=CriterionKind.TENURE_RESPECT,
            severity=severity,
            rationale=rationale,
        )

    @staticmethod
    def _verdict_for(
        findings: Tuple[CriterionFinding, ...],
    ) -> RevenuePolicyVerdict:
        top = max(
            (f.severity for f in findings),
            key=_SEVERITY_ORDER.__getitem__,
            default=CriterionSeverity.NONE,
        )
        if top is CriterionSeverity.HIGH:
            return RevenuePolicyVerdict.DENY
        if top is CriterionSeverity.MEDIUM:
            return RevenuePolicyVerdict.NEEDS_REVIEW
        return RevenuePolicyVerdict.PERMIT

    @staticmethod
    def _build_rationale(
        verdict: RevenuePolicyVerdict,
        findings: Tuple[CriterionFinding, ...],
    ) -> str:
        parts = [
            f"{f.kind.value}={f.severity.value}"
            for f in findings
            if f.severity is not CriterionSeverity.NONE
        ]
        if not parts:
            return f"verdict={verdict.value}: all criteria clean"
        return f"verdict={verdict.value}: {', '.join(parts)}"

__all__ = [
    "DEFAULT_REVENUE_POLICY_CONFIG",
    "CriterionFinding",
    "CriterionKind",
    "CriterionSeverity",
    "RevenueActionContext",
    "RevenuePolicyConfig",
    "RevenuePolicyDecision",
    "RevenuePolicyGate",
    "RevenuePolicyVerdict",
]
