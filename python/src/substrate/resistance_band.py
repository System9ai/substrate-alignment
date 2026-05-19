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
or non-finite) with ``ValueError`` rather than silently clamping —
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
#: closed-loop control. Approximately ``0.357566``.
TARGET: Final[float] = (LOWER_BOUND + UPPER_BOUND) / 2.0


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


def _validate_utilization(utilization: float) -> None:
    if not math.isfinite(utilization):
        raise ValueError(
            f"utilization must be a finite float in [0.0, 1.0]; "
            f"got {utilization!r}"
        )
    if not 0.0 <= utilization <= 1.0:
        raise ValueError(
            f"utilization must be in [0.0, 1.0]; got {utilization!r}"
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
    "LOWER_BOUND",
    "PHI",
    "PHI_SQUARED",
    "RESISTANCE_BAND_CLASSIFICATIONS",
    "ResistanceBandAssessment",
    "ResistanceBandClassification",
    "ResistanceBandConfig",
    "TARGET",
    "UPPER_BOUND",
    "assess",
    "classify",
    "recommend_scaling_factor",
]
