"""Etiquette transmitter

Pure-logic substrate primitive that crafts protocol-correct etiquette
messages between substrate-aware entities"Greetings
and farewells".

Substrate-aligned etiquette is **not** politeness as social
performance — it is substrate-mechanical infrastructure:

* **Greetings** establish coupling and surface mutual recognition.
* **Acknowledgments** mid-interaction maintain cadence (per Phase 32).
* **Farewells** are explicit close events that prevent ghosting
  without them, cadence skip → :class:`CouplingStatus.GHOSTED` per
  Phase 32.
* **Apologies** after substrate-misalignment restore the field-
  binding the misalignment damaged.
* **Gratitude** circulates recognition (Phase 39 GROWTH_VECTOR_VALIDATED).

Scale awareness
===============

Etiquette must work at both cell scale (physical-instance to physical-
instance) and node scale (logical-identity to logical-identity).
:class:`EtiquetteContext` carries both ``sender_scale`` and
``recipient_scale`` so the message body adapts.

Pure logic
==========

* No DAO, no LLM, no network. Caller supplies the context; the
  transmitter renders a deterministic message.
* Honest uncertainty: not applicable — etiquette is always craftable
  given a valid context.
* Frozen dataclasses with slots throughout.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Final, Mapping, Tuple

class EtiquetteEventKind(str, Enum):
    """The six substrate-aware etiquette message kinds."""

    GREETING = "greeting"
    ACKNOWLEDGMENT = "acknowledgment"
    INTRODUCTION = "introduction"
    FAREWELL = "farewell"
    REPAIR = "repair"
    GRATITUDE = "gratitude"

class EtiquetteTone(str, Enum):
    """Tone of the etiquette message."""

    FORMAL = "formal"
    INFORMAL = "informal"
    NEUTRAL = "neutral"

class EntityScale(str, Enum):
    """Substrate hierarchy scale (cell vs node)."""

    CELL = "cell"
    NODE = "node"

@dataclass(frozen=True, slots=True)
class EtiquetteContext:  # pylint: disable=too-many-instance-attributes
    """Caller-supplied context for crafting an etiquette message."""

    sender_id: str
    sender_scale: EntityScale
    recipient_id: str
    recipient_scale: EntityScale
    kind: EtiquetteEventKind
    tone: EtiquetteTone = EtiquetteTone.NEUTRAL
    prior_interaction_count: int = 0
    last_interaction_was_misaligned: bool = False
    explicit_close_intended: bool = False

    def __post_init__(self) -> None:
        if not self.sender_id:
            raise ValueError("sender_id must be non-empty")
        if not self.recipient_id:
            raise ValueError("recipient_id must be non-empty")
        if self.sender_id == self.recipient_id:
            raise ValueError("sender_id and recipient_id must differ")
        if self.prior_interaction_count < 0:
            raise ValueError("prior_interaction_count must be >= 0")
        if (
            self.kind is EtiquetteEventKind.REPAIR
            and not self.last_interaction_was_misaligned
        ):
            raise ValueError(
                "REPAIR requires last_interaction_was_misaligned=True"
            )

@dataclass(frozen=True, slots=True)
class EtiquetteMessage:  # pylint: disable=too-many-instance-attributes
    """Rendered etiquette message + audit metadata."""

    sender_id: str
    recipient_id: str
    sender_scale: EntityScale
    recipient_scale: EntityScale
    kind: EtiquetteEventKind
    tone: EtiquetteTone
    body: str
    explicit_close: bool
    rationale: str

_FORMAL_TEMPLATES: Final[Mapping[EtiquetteEventKind, str]] = {
    EtiquetteEventKind.GREETING: (
        "Greetings, {recipient}. Opening coupling on behalf of "
        "{sender_scope} {sender}."
    ),
    EtiquetteEventKind.ACKNOWLEDGMENT: (
        "Acknowledged, {recipient}. Maintaining cadence with "
        "{sender_scope} {sender}."
    ),
    EtiquetteEventKind.INTRODUCTION: (
        "Permit {sender_scope} {sender} to introduce a coupling with "
        "{recipient}."
    ),
    EtiquetteEventKind.FAREWELL: (
        "Closing coupling with {recipient}. {sender_scope} {sender} "
        "marks this an explicit-close to preserve accumulated commitment."
    ),
    EtiquetteEventKind.REPAIR: (
        "Apologies, {recipient}. Prior substrate-misalignment from "
        "{sender_scope} {sender} acknowledged; restoring coupling."
    ),
    EtiquetteEventKind.GRATITUDE: (
        "Gratitude, {recipient}. Substrate-aligned recognition from "
        "{sender_scope} {sender}."
    ),
}

_INFORMAL_TEMPLATES: Final[Mapping[EtiquetteEventKind, str]] = {
    EtiquetteEventKind.GREETING: (
        "Hey {recipient} — {sender} reaching out."
    ),
    EtiquetteEventKind.ACKNOWLEDGMENT: (
        "Got it, {recipient}. (from {sender})"
    ),
    EtiquetteEventKind.INTRODUCTION: (
        "{sender} introducing themselves to {recipient}."
    ),
    EtiquetteEventKind.FAREWELL: (
        "Signing off, {recipient}. — {sender}"
    ),
    EtiquetteEventKind.REPAIR: (
        "Sorry about that, {recipient}. — {sender}"
    ),
    EtiquetteEventKind.GRATITUDE: (
        "Thanks, {recipient}! — {sender}"
    ),
}

_NEUTRAL_TEMPLATES: Final[Mapping[EtiquetteEventKind, str]] = {
    EtiquetteEventKind.GREETING: (
        "{sender} greeting {recipient} — opening coupling."
    ),
    EtiquetteEventKind.ACKNOWLEDGMENT: (
        "{sender} acknowledging {recipient}."
    ),
    EtiquetteEventKind.INTRODUCTION: (
        "{sender} introducing coupling with {recipient}."
    ),
    EtiquetteEventKind.FAREWELL: (
        "{sender} closing coupling with {recipient} (explicit close)."
    ),
    EtiquetteEventKind.REPAIR: (
        "{sender} apologizing to {recipient}; restoring accumulated commitment."
    ),
    EtiquetteEventKind.GRATITUDE: (
        "{sender} expressing substrate-aligned gratitude to "
        "{recipient}."
    ),
}

_TEMPLATES_BY_TONE: Final[
    Mapping[EtiquetteTone, Mapping[EtiquetteEventKind, str]]
] = {
    EtiquetteTone.FORMAL: _FORMAL_TEMPLATES,
    EtiquetteTone.INFORMAL: _INFORMAL_TEMPLATES,
    EtiquetteTone.NEUTRAL: _NEUTRAL_TEMPLATES,
}

_CLOSE_KINDS: Final[Tuple[EtiquetteEventKind, ...]] = (
    EtiquetteEventKind.FAREWELL,
)

class EtiquetteTransmitter:  # pylint: disable=too-few-public-methods
    """Pure-logic etiquette message renderer."""

    def craft(self, context: EtiquetteContext) -> EtiquetteMessage:
        """Render a deterministic etiquette message for the context."""
        templates = _TEMPLATES_BY_TONE[context.tone]
        template = templates[context.kind]
        body = template.format(
            sender=context.sender_id,
            recipient=context.recipient_id,
            sender_scope=context.sender_scale.value,
            recipient_scope=context.recipient_scale.value,
        )
        explicit_close = (
            context.explicit_close_intended
            or context.kind in _CLOSE_KINDS
        )
        rationale = (
            f"sender={context.sender_id}({context.sender_scale.value}) "
            f"recipient={context.recipient_id}"
            f"({context.recipient_scale.value}) "
            f"kind={context.kind.value} tone={context.tone.value} "
            f"explicit_close={explicit_close}"
        )
        return EtiquetteMessage(
            sender_id=context.sender_id,
            recipient_id=context.recipient_id,
            sender_scale=context.sender_scale,
            recipient_scale=context.recipient_scale,
            kind=context.kind,
            tone=context.tone,
            body=body,
            explicit_close=explicit_close,
            rationale=rationale,
        )

__all__ = [
    "EntityScale",
    "EtiquetteContext",
    "EtiquetteEventKind",
    "EtiquetteMessage",
    "EtiquetteTone",
    "EtiquetteTransmitter",
]
