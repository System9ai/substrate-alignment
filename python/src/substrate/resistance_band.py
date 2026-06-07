"""ResistanceBand — the productive-resistance band primitive.

A three-valued classifier for *utilisation* — the fraction of capacity a
subsystem is consuming, in ``[0.0, 1.0]``. The band has a lower and an
upper edge; the package's defaults are ``1/3`` and ``1/φ²``, which place
the productive band between approximately ``0.333`` and ``0.382``.

- Below the lower edge: the subsystem is **under-loaded**. Useful work
  could be added.
- Above the upper edge: the subsystem is **stressed**. Drift risk grows;
  load should be shed.
- Between the edges: **productive**. Hold or fine-tune.

See ``docs/concepts/resistance-band.md`` for the derivation of the
default bounds and the rationale for clamping tighter, not looser,
override bands.

Module API
==========

- :data:`LOWER_BOUND`, :data:`UPPER_BOUND`, :data:`TARGET` — the default
  band edges and midpoint, exposed as constants when callers want the
  raw values.
- :class:`ResistanceBandConfig` — frozen dataclass for caller-supplied
  overrides (tighter than the defaults is permitted; looser is not).
- :class:`ResistanceBandClassification` — three-valued enum
  (``UNDER_LOADED`` / ``PRODUCTIVE`` / ``STRESSED``).
- :class:`ResistanceBandAssessment` — frozen assessment result carrying
  the classification, the signed distance to the band, the band's
  target, and the recommended scaling factor.
- :func:`classify` — one-shot classifier.
- :func:`assess` — full assessment.
- :func:`recommend_scaling_factor` — scalar control helper:
  ``> 1.0`` scale up, ``< 1.0`` scale down, ``1.0`` hold.

Every entry point rejects an out-of-range utilisation (``< 0``, ``> 1``,
or non-finite) with ``ValueError`` rather than silently clamping
silent clamping hides caller bugs.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Final, Optional

#: The golden ratio. ``(1 + sqrt(5)) / 2 ≈ 1.6180339887498949``.
PHI: Final[float] = (1.0 + math.sqrt(5.0)) / 2.0

#: ``φ²``. Equivalently ``φ + 1`` because of the golden-ratio identity.
PHI_SQUARED: Final[float] = PHI * PHI

#: Lower edge of the default productive band — ``1/3 ≈ 0.3333``. Below
#: this, the subsystem is under-loaded.
LOWER_BOUND: Final[float] = 1.0 / 3.0

#: Upper edge of the default productive band — ``1/φ² ≈ 0.3820``.
#: Equivalently ``2 - φ``. Above this, the subsystem is stressed.
UPPER_BOUND: Final[float] = 1.0 / PHI_SQUARED

#: Midpoint of the default productive band — the target utilisation for
#: closed-loop control of RESISTANCE-type quantities. Approximately
#: ``0.357566``. For WORK-type quantities with peer pickup, prefer
#: :func:`maintain_target`.
TARGET: Final[float] = (LOWER_BOUND + UPPER_BOUND) / 2.0

#: The φ-conjugate — ``1/φ = φ - 1 ≈ 0.6180``: the fraction of capacity
#: an entity maintains for itself, and equivalently the **debt line**.
#: Sustained operation above it accrues compensation debt that peers
#: must pick up (see ``substrate/debt_pickup.py`` and
#: ``docs/concepts/resistance-band.md`` § "The layered zone model").
PHI_CONJUGATE: Final[float] = 1.0 / PHI

#: Vocabulary alias for :data:`PHI_CONJUGATE` — "the ~62% an entity is
#: trying to maintain".
MAINTAINED_CAPACITY: Final[float] = PHI_CONJUGATE

#: The work-zone ceiling — the 0.5 line. Work in ``(1/φ², 0.5]`` is
#: genuinely productive sustained effort ("in the zone but not rising
#: too fast"); past the line a turnaround is expected (PEAKING) and the
#: excursion is tolerable only sporadically.
WORK_ZONE_UPPER: Final[float] = 0.5

#: φ-proportioned growth-step ratio ("domino chain"): capacity raises
#: by at most ~1.618x per step with consolidation between steps.
#: Faster sustained growth builds no foundation and topples.
GROWTH_STEP_RATIO: Final[float] = PHI

class ResistanceBandClassification(str, Enum):
    """Three-valued band classification.

    str-Enum so the value serialises stably across SQL, JSON, and the
    canonical-bytes form used by the audit chain.
    """

    UNDER_LOADED = "under_loaded"
    PRODUCTIVE = "productive"
    STRESSED = "stressed"

#: All classifications. Stays in lockstep with the enum so any downstream
#: discriminator or persisted CHECK constraint imports a single source.
RESISTANCE_BAND_CLASSIFICATIONS: Final[frozenset[str]] = frozenset(
    c.value for c in ResistanceBandClassification
)


class ZoneClassification(str, Enum):
    """Five-valued layered-zone classification.

    The legacy three-state model mislabels the work zone as STRESSED
    for WORK-type quantities; this enum carries the layered capacity
    model (spec ``runaway-power-prevention.md`` §4):

    - UNDER_LOADED ``< 1/3`` — the rest zone; legitimate for recovery.
    - CALIBRATION ``[1/3, 1/φ²]`` — work-entry threshold and the
      imposed-resistance setpoint (the legacy PRODUCTIVE band).
    - WORKING ``(1/φ², 0.5]`` — genuinely productive sustained work.
    - PEAKING ``(0.5, 1/φ]`` — sporadic-tolerable; turnaround expected.
    - DEBT ``> 1/φ`` — sustained operation accrues compensation debt;
      others pick up.
    """

    UNDER_LOADED = "under_loaded"
    CALIBRATION = "calibration"
    WORKING = "working"
    PEAKING = "peaking"
    DEBT = "debt"


#: All zone classifications, lockstep with the enum.
ZONE_CLASSIFICATIONS: Final[frozenset[str]] = frozenset(
    z.value for z in ZoneClassification
)


_ZONE_TO_LEGACY: Final[dict["ZoneClassification", ResistanceBandClassification]] = {
    ZoneClassification.UNDER_LOADED: ResistanceBandClassification.UNDER_LOADED,
    ZoneClassification.CALIBRATION: ResistanceBandClassification.PRODUCTIVE,
    ZoneClassification.WORKING: ResistanceBandClassification.STRESSED,
    ZoneClassification.PEAKING: ResistanceBandClassification.STRESSED,
    ZoneClassification.DEBT: ResistanceBandClassification.STRESSED,
}


class OperatingMode(str, Enum):
    """Grow vs maintain — the mode dimension of the capacity contract.

    MAINTAIN is the legitimate default steady state (no growth
    pressure; cruise per :func:`maintain_target`). GROW is a
    deliberate, gated transition — never a default: an entity that
    always chooses grow without consolidation exhibits the
    unbounded-growth pattern (runaway-power-prevention mechanism 6);
    the streak detector lives in ``substrate/sustained_load.py``.
    """

    MAINTAIN = "maintain"
    GROW = "grow"

@dataclass(frozen=True, slots=True)
class ResistanceBandConfig:
    """Caller-supplied band override.

    Defaults match :data:`LOWER_BOUND` and :data:`UPPER_BOUND`. Callers
    may tighten the band when a subsystem has independent evidence that
    its safe operating envelope is narrower; widening beyond the package
    defaults is rejected.
    """

    lower_bound: float = LOWER_BOUND
    upper_bound: float = UPPER_BOUND

    def __post_init__(self) -> None:
        if self.lower_bound < 0.0:
            raise ValueError(
                f"lower_bound must be >= 0.0; got {self.lower_bound!r}"
            )
        if self.upper_bound > 1.0:
            raise ValueError(
                f"upper_bound must be <= 1.0; got {self.upper_bound!r}"
            )
        if self.lower_bound >= self.upper_bound:
            raise ValueError(
                "lower_bound must be strictly less than upper_bound; "
                f"got [{self.lower_bound!r}, {self.upper_bound!r}]"
            )
        if self.lower_bound < LOWER_BOUND - 1e-9:
            raise ValueError(
                f"lower_bound must not be looser than the default "
                f"{LOWER_BOUND:.4f}; got {self.lower_bound!r}"
            )
        if self.upper_bound > UPPER_BOUND + 1e-9:
            raise ValueError(
                f"upper_bound must not be looser than the default "
                f"{UPPER_BOUND:.4f}; got {self.upper_bound!r}"
            )

    @property
    def target(self) -> float:
        """Midpoint of the band — the closed-loop target utilisation."""
        return (self.lower_bound + self.upper_bound) / 2.0

#: The package-default :class:`ResistanceBandConfig`. Importable as a
#: singleton when callers don't need to override the bounds.
DEFAULT_CONFIG: Final[ResistanceBandConfig] = ResistanceBandConfig()

@dataclass(frozen=True, slots=True)
class ResistanceBandAssessment:
    """Frozen result of one band assessment.

    ``distance_to_band`` is the signed distance from the utilisation to
    the nearest band edge: negative when below the lower bound, positive
    when above the upper bound, zero when inside. Callers use this for
    proportional control (e.g. "we are ``0.10`` above the band, so cut
    load by an additional ratio").

    ``recommended_scaling_factor`` is the multiplier that aims the
    utilisation at the band's :attr:`target` midpoint when applied to
    the current load. ``> 1.0`` means scale up; ``< 1.0`` means scale
    down; ``1.0`` means hold.
    """

    utilization: float
    classification: ResistanceBandClassification
    distance_to_band: float
    target: float
    recommended_scaling_factor: float
    reasoning: str
    config: ResistanceBandConfig

    @property
    def is_productive(self) -> bool:
        """``True`` iff the classification is PRODUCTIVE."""
        return self.classification is ResistanceBandClassification.PRODUCTIVE

    @property
    def is_under_loaded(self) -> bool:
        """``True`` iff the classification is UNDER_LOADED."""
        return self.classification is ResistanceBandClassification.UNDER_LOADED

    @property
    def is_stressed(self) -> bool:
        """``True`` iff the classification is STRESSED."""
        return self.classification is ResistanceBandClassification.STRESSED

def validate_utilization(utilization: float) -> None:
    """Reject a non-finite or out-of-range utilisation with ``ValueError``.

    Public so sibling layered-model modules (``sustained_load``,
    ``debt_pickup``) share one validation contract.
    """
    if not math.isfinite(utilization):
        raise ValueError(
            f"utilization must be a finite float in [0.0, 1.0]; "
            f"got {utilization!r}"
        )
    if not 0.0 <= utilization <= 1.0:
        raise ValueError(
            f"utilization must be in [0.0, 1.0]; got {utilization!r}"
        )


#: Backwards-compatible private alias (pre-v2 internal call sites).
_validate_utilization = validate_utilization


def classify_zone(
    utilization: float,
    *,
    config: Optional[ResistanceBandConfig] = None,
) -> ZoneClassification:
    """Return the five-valued layered-zone classification.

    The calibration edges come from ``config`` (tighter-only, as with
    :func:`classify`); the work-zone ceiling (0.5) and the φ-conjugate
    debt line are substrate anchors and are not tunable. Boundaries:
    calibration edges inclusive (matching :func:`classify`); the work
    zone includes 0.5; DEBT is strictly above ``1/φ``.
    """
    validate_utilization(utilization)
    cfg = config or DEFAULT_CONFIG
    if utilization < cfg.lower_bound:
        return ZoneClassification.UNDER_LOADED
    if utilization <= cfg.upper_bound:
        return ZoneClassification.CALIBRATION
    if utilization <= WORK_ZONE_UPPER:
        return ZoneClassification.WORKING
    if utilization <= PHI_CONJUGATE:
        return ZoneClassification.PEAKING
    return ZoneClassification.DEBT


def zone_to_legacy(zone: ZoneClassification) -> ResistanceBandClassification:
    """Project a layered zone onto the legacy three-state enum.

    WORKING/PEAKING/DEBT all project to STRESSED — intentionally lossy;
    persisted three-state consumers keep working unchanged while
    five-state consumers opt in via :func:`classify_zone`.
    """
    return _ZONE_TO_LEGACY[zone]


def maintain_target(
    group_size: int,
    *,
    debt_line: float = PHI_CONJUGATE,
    ceiling: float = WORK_ZONE_UPPER,
) -> float:
    """Group-size-aware maintain-mode utilisation target for WORK quantities.

    Derived from the debt line + peer-pickup math: after one peer of
    ``group_size`` fails, each survivor takes ``u + u/(N-1)`` and must
    stay at or under the debt line, so
    ``u* = min(ceiling, debt_line * (N-1)/N)``. Small groups cruise
    lighter (N=2 → ≈0.309); larger groups earn the work zone (N≥6 →
    the 0.5 ceiling). ``group_size == 1`` has no pickup peer — the
    failover constraint is vacuous, so the conservative
    calibration-band :data:`TARGET` is returned. Applies to fungible,
    transferable resources; hard-fail resources (memory) carry their
    own band instance and semantics.
    """
    if group_size < 1:
        raise ValueError(f"group_size must be >= 1; got {group_size!r}")
    if not 0.0 < debt_line <= 1.0:
        raise ValueError(f"debt_line must be in (0, 1]; got {debt_line!r}")
    if not 0.0 < ceiling <= debt_line:
        raise ValueError(
            f"ceiling must be in (0, debt_line]; got {ceiling!r}"
        )
    if group_size == 1:
        return TARGET
    return min(ceiling, debt_line * (group_size - 1) / group_size)


@dataclass(frozen=True, slots=True)
class GrowthStepAssessment:
    """Frozen verdict on a proposed capacity-growth step.

    Signals feed interpretation: the assessment never blocks — the
    caller's gate decides. ``within_phi`` is ``False`` when the
    proposed step exceeds the φ ratio ("rise too fast and you topple").
    """

    current_capacity: float
    proposed_capacity: float
    step_ratio: float
    within_phi: bool
    reasoning: str


def assess_growth_step(
    current_capacity: float,
    proposed_capacity: float,
    *,
    max_ratio: float = GROWTH_STEP_RATIO,
) -> GrowthStepAssessment:
    """Assess a proposed capacity raise against the φ-step discipline.

    Shrinking or holding capacity is always ``within_phi`` (it is not
    growth). Raises ``ValueError`` for non-positive capacities or a
    ``max_ratio <= 1.0``.
    """
    if current_capacity <= 0.0 or not math.isfinite(current_capacity):
        raise ValueError(
            f"current_capacity must be a positive finite float; "
            f"got {current_capacity!r}"
        )
    if proposed_capacity <= 0.0 or not math.isfinite(proposed_capacity):
        raise ValueError(
            f"proposed_capacity must be a positive finite float; "
            f"got {proposed_capacity!r}"
        )
    if max_ratio <= 1.0:
        raise ValueError(f"max_ratio must be > 1.0; got {max_ratio!r}")
    ratio = proposed_capacity / current_capacity
    within = ratio <= max_ratio + 1e-9
    reasoning = (
        f"step_ratio={ratio:.4f} max_ratio={max_ratio:.4f} "
        f"within_phi={within} — "
        + (
            "phi-proportioned (foundation preserved)"
            if within
            else "exceeds the phi step; rise-too-fast topple risk"
        )
    )
    return GrowthStepAssessment(
        current_capacity=current_capacity,
        proposed_capacity=proposed_capacity,
        step_ratio=ratio,
        within_phi=within,
        reasoning=reasoning,
    )

def classify(
    utilization: float,
    *,
    config: Optional[ResistanceBandConfig] = None,
) -> ResistanceBandClassification:
    """Return the three-valued band classification for ``utilization``.

    Boundaries are inclusive: a utilisation exactly at ``lower_bound``
    or ``upper_bound`` resolves to PRODUCTIVE. Raises ``ValueError`` when
    ``utilization`` is outside ``[0.0, 1.0]`` or not finite.
    """
    _validate_utilization(utilization)
    cfg = config or DEFAULT_CONFIG
    if utilization < cfg.lower_bound:
        return ResistanceBandClassification.UNDER_LOADED
    if utilization > cfg.upper_bound:
        return ResistanceBandClassification.STRESSED
    return ResistanceBandClassification.PRODUCTIVE

def assess(
    utilization: float,
    *,
    config: Optional[ResistanceBandConfig] = None,
) -> ResistanceBandAssessment:
    """Compute the full band assessment for ``utilization``.

    Always returns a :class:`ResistanceBandAssessment`. The only failure
    mode is ``ValueError`` for an out-of-range or non-finite utilisation.
    """
    _validate_utilization(utilization)
    cfg = config or DEFAULT_CONFIG
    classification = classify(utilization, config=cfg)
    if classification is ResistanceBandClassification.UNDER_LOADED:
        distance = utilization - cfg.lower_bound  # negative
    elif classification is ResistanceBandClassification.STRESSED:
        distance = utilization - cfg.upper_bound  # positive
    else:
        distance = 0.0
    scaling = _scaling_factor(utilization=utilization, target=cfg.target)
    reasoning = _render_reasoning(
        utilization=utilization,
        classification=classification,
        distance=distance,
        target=cfg.target,
    )
    return ResistanceBandAssessment(
        utilization=utilization,
        classification=classification,
        distance_to_band=distance,
        target=cfg.target,
        recommended_scaling_factor=scaling,
        reasoning=reasoning,
        config=cfg,
    )

def recommend_scaling_factor(
    utilization: float,
    *,
    config: Optional[ResistanceBandConfig] = None,
) -> float:
    """Pure scalar helper: the multiplier that aims ``utilization`` at ``target``.

    Equivalent to ``target / utilization`` with safe handling for
    ``utilization == 0`` (returns a large but finite scale-up factor).
    Useful for control loops that don't need a full
    :class:`ResistanceBandAssessment`.
    """
    _validate_utilization(utilization)
    cfg = config or DEFAULT_CONFIG
    return _scaling_factor(utilization=utilization, target=cfg.target)

def _scaling_factor(*, utilization: float, target: float) -> float:
    """Return ``target / utilization`` with a finite cap at ``utilization=0``.

    A perfectly-idle subsystem (``utilization == 0``) would otherwise
    divide by zero; capping at ``target * 1e6`` produces a large but
    finite "scale up aggressively" signal that downstream controllers
    can still saturate against their own headroom limits.
    """
    if utilization <= 0.0:
        return target * 1e6
    return target / utilization

def _render_reasoning(
    *,
    utilization: float,
    classification: ResistanceBandClassification,
    distance: float,
    target: float,
) -> str:
    """Single-line human-readable explanation rendered into assessments."""
    return (
        f"utilization={utilization:.4f} classification={classification.value} "
        f"distance_to_band={distance:+.4f} target={target:.4f}"
    )

__all__ = [
    "DEFAULT_CONFIG",
    "GROWTH_STEP_RATIO",
    "GrowthStepAssessment",
    "LOWER_BOUND",
    "MAINTAINED_CAPACITY",
    "OperatingMode",
    "PHI",
    "PHI_CONJUGATE",
    "PHI_SQUARED",
    "RESISTANCE_BAND_CLASSIFICATIONS",
    "ResistanceBandAssessment",
    "ResistanceBandClassification",
    "ResistanceBandConfig",
    "TARGET",
    "UPPER_BOUND",
    "WORK_ZONE_UPPER",
    "ZONE_CLASSIFICATIONS",
    "ZoneClassification",
    "assess",
    "assess_growth_step",
    "classify",
    "classify_zone",
    "maintain_target",
    "recommend_scaling_factor",
    "validate_utilization",
    "zone_to_legacy",
]
