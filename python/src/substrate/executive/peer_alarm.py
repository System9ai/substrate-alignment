"""Peer awareness + collective alarm propagation: "see something, say something".

A distributed early-warning faculty. Two mechanisms:

* **Herd-panic correlation** (:func:`correlate_anomalies`): one peer acting weird
  is noise; *N peers in the same group acting weird together* means the **enclosing
  scale** has a problem (the rack, not the cell). Correlation across independent
  peers is what separates a real shared cause from individual bugs, and it
  attributes the anomaly UP to the group scale.
* **Alarm-call propagation** (:func:`assess_alarm`): an intelligence that detects
  a threat broadcasts a warning to its group and peers *heed* it without each
  re-deriving the threat (prairie-dog alarm calls; a person yelling "fire").

The inversion guard 
===============================

A malicious entity yelling "fire!" to cause chaos is an ATTACK (panic-injection /
alarm-washing). So an alarm is **trust-weighted × corroboration-weighted**: a lone
uncorroborated alarm is never allowed to trigger group-wide panic. Many INDEPENDENT
alarms about the same scale corroborate each other (that IS the herd-panic signal)
and are heeded; a lone loud alarm is HELD (and the source's own trust checked), and
a lone alarm from a low-trust source is SUPPRESSED as likely injection.

Pure logic
==========

* No DAO, no LLM, no network. Deterministic. Frozen dataclasses with slots.
* The corroboration threshold is the caller's (typically band-derived); this module
  applies it, it does not pick it.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence, Tuple

from substrate.executive.scale import ExecutiveScale


# ── herd-panic correlation ──────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class PeerAnomaly:
    """One peer's anomaly observation within a group."""

    peer_id: str
    anomalous: bool

    def __post_init__(self) -> None:
        if not self.peer_id:
            raise ValueError("peer_id must be non-empty")


@dataclass(frozen=True, slots=True)
class HerdVerdict:
    """Whether a group-level (enclosing-scale) problem is indicated."""

    group_scale: ExecutiveScale
    anomalous_peers: int
    total_peers: int
    fraction: float
    is_group_problem: bool
    rationale: str


def correlate_anomalies(
    anomalies: Sequence[PeerAnomaly],
    *,
    group_scale: ExecutiveScale,
    min_correlated: int = 2,
) -> Optional[HerdVerdict]:
    """Attribute correlated peer anomalies UP to the enclosing scale ("herd panic").

    A single anomalous peer is noise; ``min_correlated`` or more DISTINCT peers
    anomalous together indicates the *group* (``group_scale``) has a shared problem.
    Returns ``None`` for an empty group (nothing to correlate). Raises for
    ``min_correlated < 1``.
    """
    if min_correlated < 1:
        raise ValueError("min_correlated must be >= 1")
    if not anomalies:
        return None
    anomalous = {a.peer_id for a in anomalies if a.anomalous}
    total = len({a.peer_id for a in anomalies})
    count = len(anomalous)
    is_group_problem = count >= min_correlated
    label = (
        "GROUP problem (correlated → enclosing scale)"
        if is_group_problem
        else "individual noise"
    )
    rationale = (
        f"{count}/{total} peers anomalous in {group_scale.value}; "
        f"{label} (threshold {min_correlated})"
    )
    return HerdVerdict(
        group_scale=group_scale,
        anomalous_peers=count,
        total_peers=total,
        fraction=count / total if total else 0.0,
        is_group_problem=is_group_problem,
        rationale=rationale,
    )


# ── alarm-call propagation ──────────────────────────────────────────────


class AlarmDisposition(str, Enum):
    """What to do with a received alarm."""

    HEED = "heed"          # corroborated → act on it (the herd is right)
    HOLD = "hold"          # trusted but uncorroborated → hold + check the source
    SUPPRESS = "suppress"  # untrusted + uncorroborated → likely panic-injection


@dataclass(frozen=True, slots=True)
class PeerAlarm:
    """One peer's broadcast warning about an enclosing scale."""

    alarm_id: str
    source_entity_id: str
    about_scale: ExecutiveScale
    kind: str
    severity: float
    source_trust: float

    def __post_init__(self) -> None:
        if not self.alarm_id:
            raise ValueError("alarm_id must be non-empty")
        if not self.source_entity_id:
            raise ValueError("source_entity_id must be non-empty")
        for name, value in (
            ("severity", self.severity),
            ("source_trust", self.source_trust),
        ):
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be in [0, 1]; got {value!r}")


@dataclass(frozen=True, slots=True)
class AlarmAssessment:
    """The trust × corroboration verdict on an alarm."""

    alarm: PeerAlarm
    corroboration_count: int
    effective_weight: float
    disposition: AlarmDisposition
    rationale: str


def assess_alarm(
    alarm: PeerAlarm,
    corroborating: Sequence[PeerAlarm] = (),
    *,
    min_corroborators: int = 2,
    trust_floor: float = 0.5,
) -> AlarmAssessment:
    """Decide whether to HEED, HOLD, or SUPPRESS an alarm (the panic-injection guard).

    Corroboration = the number of DISTINCT OTHER source entities alarming about the
    SAME ``about_scale`` (the source itself and duplicate sources do not corroborate
    themselves; independence is required). With ``min_corroborators`` or more
    independent corroborators the alarm is HEEDED (the herd-panic signal is real). A
    lone alarm is HELD if the source clears ``trust_floor`` (trusted but unverified)
    and SUPPRESSED otherwise (untrusted + uncorroborated → likely injection). No
    single entity can trigger group-wide panic.
    """
    if min_corroborators < 1:
        raise ValueError("min_corroborators must be >= 1")
    independent = {
        a.source_entity_id
        for a in corroborating
        if a.about_scale is alarm.about_scale
        and a.source_entity_id != alarm.source_entity_id
    }
    count = len(independent)
    # weight rises with source trust, severity, and independent corroboration.
    effective_weight = alarm.source_trust * alarm.severity * (1 + count)
    if count >= min_corroborators:
        disposition = AlarmDisposition.HEED
    elif alarm.source_trust >= trust_floor:
        disposition = AlarmDisposition.HOLD
    else:
        disposition = AlarmDisposition.SUPPRESS
    rationale = (
        f"alarm {alarm.kind!r} about {alarm.about_scale.value} from "
        f"{alarm.source_entity_id} (trust={alarm.source_trust:.2f} "
        f"severity={alarm.severity:.2f}): {count} independent corroborators "
        f"(need {min_corroborators}) → {disposition.value}"
    )
    return AlarmAssessment(
        alarm=alarm,
        corroboration_count=count,
        effective_weight=effective_weight,
        disposition=disposition,
        rationale=rationale,
    )


def heeded_alarms(
    alarms: Sequence[PeerAlarm],
    *,
    min_corroborators: int = 2,
    trust_floor: float = 0.5,
) -> Tuple[AlarmAssessment, ...]:
    """Assess a batch of alarms against EACH OTHER and return the HEEDED ones.

    Each alarm is corroborated by the rest of the batch, so a set of independent
    alarms about the same scale corroborate one another into HEED, while lone or
    injection alarms fall out as HOLD / SUPPRESS.
    """
    out: list[AlarmAssessment] = []
    for i, alarm in enumerate(alarms):
        others = tuple(alarms[:i]) + tuple(alarms[i + 1:])
        assessment = assess_alarm(
            alarm, others,
            min_corroborators=min_corroborators,
            trust_floor=trust_floor,
        )
        if assessment.disposition is AlarmDisposition.HEED:
            out.append(assessment)
    return tuple(out)


__all__ = [
    "AlarmAssessment",
    "AlarmDisposition",
    "HerdVerdict",
    "PeerAlarm",
    "PeerAnomaly",
    "assess_alarm",
    "correlate_anomalies",
    "heeded_alarms",
]
