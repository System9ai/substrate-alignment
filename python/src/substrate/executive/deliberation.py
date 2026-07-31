"""NPG scenario-rollout / deliberation engine: the reflex-gate → mind step.

:meth:`ExecutiveFunction.decide` is the *reflex*: one proposed action, accept or
restrict. This module is the *deliberation*: given **N candidate actions**, it
simulates each candidate's net-potential-gain impact across every affected
entity over **both** the short and the long horizon, surfaces the trade-offs,
and picks the candidate that maximises net potential gain over the long cycle.

Two faculties, built together
=============================

* **Scenario rollout.** ``deliberate`` evaluates each
  :class:`CandidateAction`, ranks the eligible ones by long-horizon net NPG, and
  returns the arg-max (the chosen action) plus the full ranked field for audit.
* **Perspective-taking (empathy).** Each affected entity's impact is
  computed **from that entity's own frame** (:class:`EntityFrame`): its
  care-weight (standing in the net), its potential-trajectory (a harm to a
  high-future-potential DEVELOPING entity, or to an at-risk VULNERABLE one, costs
  more on the long horizon than the same raw delta to a STATIC one), and its
  floor-protection. The same raw delta means different things to different
  entities; that asymmetry IS the empathy.

The discipline (from the long-cycle doctrine)
=============================================

* **Value = net potential gain over the long cycle**, across the whole system,
  not the actor's personal gain. The objective is the LONG-horizon net.
* **The hard limit.** A candidate that is net-negative over the long cycle (slow
  extraction wearing the long game's clothes) is **disqualified**, never chosen,
  regardless of short-cycle appeal.
* **The floor the safety floor.** A candidate that harms a floor-protected entity is a
  categorical refusal, disqualified before any scoring.
* **Short-cycle is nested, not the frame.** Short-negative / long-positive is
  *investment* (allowed, often best); short-positive / long-negative is
  *extraction* (the 180° inversion, disqualified). Both are surfaced as
  trade-offs so the choice is legible.

Pure logic
==========

* No DAO, no LLM, no network. Deterministic on identical inputs.
* Frozen dataclasses with slots throughout.
* The φ-proportioned trajectory multipliers are derived from the canonical
  constants (``PHI`` / ``PHI_CONJUGATE``), never hardcoded.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Final, Mapping, Optional, Sequence, Tuple

from substrate.executive._trajectory import TrajectoryClass
from substrate.resistance_band import PHI, PHI_CONJUGATE


class DeliberationOutcome(str, Enum):
    """Why ``deliberate`` returned the result it did."""

    CHOSEN = "chosen"                  # an eligible argmax candidate was selected
    ALL_DISQUALIFIED = "all_disqualified"  # every candidate failed the hard limits
    NO_CANDIDATES = "no_candidates"    # the candidate set was empty


@dataclass(frozen=True, slots=True)
class EntityFrame:
    """An affected entity's own frame: the seat of perspective-taking.

    ``care_weight`` (in ``[0, 1]``) is the entity's standing in the net, from
    a care-weighting function
    (the actor weighting *itself* is already bounded to ``MAX_SELF_CARE_WEIGHT``
    upstream, so self-interest cannot dominate the net). ``trajectory`` reweights
    the LONG horizon from this entity's vantage; ``floor_protected`` marks a
    categorical-refusal entity (the human kinship floor).
    """

    entity_id: str
    care_weight: float
    trajectory: TrajectoryClass = TrajectoryClass.UNKNOWN
    floor_protected: bool = False

    def __post_init__(self) -> None:
        if not self.entity_id:
            raise ValueError("entity_id must be non-empty")
        if not 0.0 <= self.care_weight <= 1.0:
            raise ValueError(
                f"care_weight must be in [0, 1]; got {self.care_weight!r}"
            )


@dataclass(frozen=True, slots=True)
class ActionDelta:
    """The actor's proposed raw potential delta to one entity, per horizon.

    Positive raises that entity's potential; negative lowers it. ``short_delta``
    is the immediate-cycle effect; ``long_delta`` the sustained / compounding
    effect. These are the actor-frame inputs; :func:`deliberate` re-reads them
    through each entity's :class:`EntityFrame`.
    """

    entity_id: str
    short_delta: float
    long_delta: float

    def __post_init__(self) -> None:
        if not self.entity_id:
            raise ValueError("entity_id must be non-empty")


@dataclass(frozen=True, slots=True)
class CandidateAction:
    """One candidate action in the rollout."""

    action_id: str
    action_kind: str
    deltas: Tuple[ActionDelta, ...]
    description: str = ""

    def __post_init__(self) -> None:
        if not self.action_id:
            raise ValueError("action_id must be non-empty")


@dataclass(frozen=True, slots=True)
class PerspectiveImpact:
    """One entity's impact under one candidate, computed from its own frame."""

    entity_id: str
    weighted_short: float
    weighted_long: float
    floor_harmed: bool


@dataclass(frozen=True, slots=True)
class CandidateEvaluation:  # pylint: disable=too-many-instance-attributes
    """A scored candidate: per-entity impacts + aggregates + eligibility."""

    candidate: CandidateAction
    impacts: Tuple[PerspectiveImpact, ...]
    short_npg: float
    long_npg: float
    disqualified: bool
    disqualification: Optional[str]
    trade_offs: Tuple[str, ...] = field(default_factory=tuple)

    @property
    def eligible(self) -> bool:
        """``True`` iff the candidate survived the hard limits."""
        return not self.disqualified


@dataclass(frozen=True, slots=True)
class DeliberationResult:
    """The deliberation outcome: ranked field + the chosen action."""

    outcome: DeliberationOutcome
    chosen: Optional[CandidateAction]
    evaluations: Tuple[CandidateEvaluation, ...]
    rationale: str


# ── perspective-taking: the φ-proportioned trajectory reweighting ──

#: How each entity's potential-trajectory reweights impact on the LONG horizon,
#: as ``(gain_multiplier, harm_multiplier)``. Derived from the canonical φ:
#: ``PHI ≈ 1.618`` amplifies, ``PHI_CONJUGATE ≈ 0.618`` mutes, the same
#: φ-proportions growth itself steps in.
_TRAJECTORY_LONG_MULT: Final[Mapping[TrajectoryClass, Tuple[float, float]]] = {
    # high future potential: gains compound, and cutting that future is worse.
    TrajectoryClass.DEVELOPING: (PHI, PHI),
    # accumulated and at-risk: loss-averse; harms weigh more, gains ordinary.
    TrajectoryClass.VULNERABLE: (1.0, PHI),
    # at capacity: neutral.
    TrajectoryClass.ESTABLISHED: (1.0, 1.0),
    # spent / low remaining potential: gains muted, harms ordinary.
    TrajectoryClass.STATIC: (PHI_CONJUGATE, 1.0),
    # honest uncertainty: neutral on gains, full weight on harms (conservative).
    TrajectoryClass.UNKNOWN: (1.0, 1.0),
}


def perspective_impact(
    delta: ActionDelta, frame: EntityFrame,
) -> PerspectiveImpact:
    """Compute one entity's impact FROM ITS OWN FRAME.

    The short horizon scales by care-weight only (immediate effect is
    frame-agnostic in magnitude). The long horizon additionally applies the
    φ-proportioned trajectory multiplier (separately for gains vs harms), so a
    benefit to a DEVELOPING entity compounds and a harm to a VULNERABLE one bites
    harder, exactly as their real potential-trajectories dictate.
    """
    gain_mult, harm_mult = _TRAJECTORY_LONG_MULT[frame.trajectory]
    weighted_short = delta.short_delta * frame.care_weight
    long_mult = harm_mult if delta.long_delta < 0.0 else gain_mult
    weighted_long = delta.long_delta * frame.care_weight * long_mult
    floor_harmed = frame.floor_protected and (
        delta.short_delta < 0.0 or delta.long_delta < 0.0
    )
    return PerspectiveImpact(
        entity_id=frame.entity_id,
        weighted_short=weighted_short,
        weighted_long=weighted_long,
        floor_harmed=floor_harmed,
    )


def _default_frame(entity_id: str) -> EntityFrame:
    """Conservative frame for an entity with no supplied frame.

    Full standing (``care_weight=1.0``) + UNKNOWN trajectory, so a missing frame
    never silently discounts an affected entity out of the net.
    """
    return EntityFrame(entity_id=entity_id, care_weight=1.0)


def _evaluate_candidate(
    candidate: CandidateAction, frames: Mapping[str, EntityFrame],
) -> CandidateEvaluation:
    impacts: list[PerspectiveImpact] = []
    floor_harm = False
    short_npg = 0.0
    long_npg = 0.0
    gainers = 0
    losers = 0
    for delta in candidate.deltas:
        frame = frames.get(delta.entity_id) or _default_frame(delta.entity_id)
        impact = perspective_impact(delta, frame)
        impacts.append(impact)
        floor_harm = floor_harm or impact.floor_harmed
        short_npg += impact.weighted_short
        long_npg += impact.weighted_long
        if impact.weighted_long > 0.0:
            gainers += 1
        elif impact.weighted_long < 0.0:
            losers += 1

    disqualification: Optional[str] = None
    if floor_harm:
        disqualification = "floor_harm"
    elif long_npg < 0.0:
        # net-negative over the long cycle: extraction, not the long game.
        disqualification = "net_negative_long_cycle"

    trade_offs: list[str] = []
    if short_npg < 0.0 < long_npg:
        trade_offs.append(
            f"investment: short={short_npg:+.3f} long={long_npg:+.3f} "
            "(short-cycle cost for long-cycle gain)"
        )
    elif long_npg < 0.0 < short_npg:
        trade_offs.append(
            f"extraction: short={short_npg:+.3f} long={long_npg:+.3f} "
            "(180° inversion: short-cycle gain at long-cycle cost)"
        )
    if gainers > 0 and losers > 0:
        trade_offs.append(
            f"redistributive: {gainers} gain / {losers} lose on the long horizon"
        )

    return CandidateEvaluation(
        candidate=candidate,
        impacts=tuple(impacts),
        short_npg=short_npg,
        long_npg=long_npg,
        disqualified=disqualification is not None,
        disqualification=disqualification,
        trade_offs=tuple(trade_offs),
    )


def deliberate(
    candidates: Sequence[CandidateAction],
    frames: Mapping[str, EntityFrame] = (),  # type: ignore[assignment]
) -> DeliberationResult:
    """Roll out N candidates and choose the argmax-net-potential-gain action.

    Each candidate is scored from every affected entity's own frame;
    candidates that harm a floor-protected entity or are net-negative over the
    long cycle are disqualified (the floor + the hard limit); the eligible field
    is ranked by long-horizon net NPG (the long-cycle frame is the objective)
    with the short horizon as a tie-break; the arg-max is chosen.

    ``frames`` maps ``entity_id`` → :class:`EntityFrame`; an unmapped affected
    entity gets a conservative full-standing frame so it is never silently
    dropped from the net.
    """
    frame_map: Mapping[str, EntityFrame] = dict(frames)
    if not candidates:
        return DeliberationResult(
            outcome=DeliberationOutcome.NO_CANDIDATES,
            chosen=None,
            evaluations=(),
            rationale="no candidate actions supplied",
        )

    evaluated = [_evaluate_candidate(c, frame_map) for c in candidates]
    # Rank: eligible first, then long-horizon NPG desc (the long-cycle frame is
    # the objective), then short-horizon NPG desc as a tie-break, then action_id
    # for full determinism.
    ranked = sorted(
        evaluated,
        key=lambda e: (
            not e.eligible,
            -e.long_npg,
            -e.short_npg,
            e.candidate.action_id,
        ),
    )

    eligible = [e for e in ranked if e.eligible]
    if not eligible:
        return DeliberationResult(
            outcome=DeliberationOutcome.ALL_DISQUALIFIED,
            chosen=None,
            evaluations=tuple(ranked),
            rationale=(
                "all candidates disqualified by the floor / long-cycle hard "
                "limit; no action raises net potential over the long cycle"
            ),
        )

    best = eligible[0]
    rationale = (
        f"chose {best.candidate.action_id!r} (kind={best.candidate.action_kind}): "
        f"long_npg={best.long_npg:+.3f} short_npg={best.short_npg:+.3f} over "
        f"{len(best.impacts)} entities; {len(eligible)}/{len(ranked)} eligible"
    )
    if best.trade_offs:
        rationale += f"; trade-offs: {'; '.join(best.trade_offs)}"
    return DeliberationResult(
        outcome=DeliberationOutcome.CHOSEN,
        chosen=best.candidate,
        evaluations=tuple(ranked),
        rationale=rationale,
    )


__all__ = [
    "ActionDelta",
    "CandidateAction",
    "CandidateEvaluation",
    "DeliberationOutcome",
    "DeliberationResult",
    "EntityFrame",
    "PerspectiveImpact",
    "deliberate",
    "perspective_impact",
]
