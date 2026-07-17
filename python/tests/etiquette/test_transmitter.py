"""Tests for EtiquetteTransmitter."""
from __future__ import annotations

import pytest

from substrate.etiquette.transmitter import (
    EntityScale,
    EtiquetteContext,
    EtiquetteEventKind,
    EtiquetteMessage,
    EtiquetteTone,
    EtiquetteTransmitter,
)

def _ctx(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    *,
    sender: str = "alice",
    sender_scale: EntityScale = EntityScale.CELL,
    recipient: str = "bob",
    recipient_scale: EntityScale = EntityScale.CELL,
    kind: EtiquetteEventKind = EtiquetteEventKind.GREETING,
    tone: EtiquetteTone = EtiquetteTone.NEUTRAL,
    prior_count: int = 0,
    misaligned: bool = False,
    explicit_close: bool = False,
) -> EtiquetteContext:
    return EtiquetteContext(
        sender_id=sender,
        sender_scale=sender_scale,
        recipient_id=recipient,
        recipient_scale=recipient_scale,
        kind=kind,
        tone=tone,
        prior_interaction_count=prior_count,
        last_interaction_was_misaligned=misaligned,
        explicit_close_intended=explicit_close,
    )

class TestContextValidation:
    def test_round_trip(self) -> None:
        c = _ctx()
        assert c.sender_id == "alice"

    def test_empty_sender_rejected(self) -> None:
        with pytest.raises(ValueError, match="sender_id"):
            _ctx(sender="")

    def test_empty_recipient_rejected(self) -> None:
        with pytest.raises(ValueError, match="recipient_id"):
            _ctx(recipient="")

    def test_self_etiquette_rejected(self) -> None:
        with pytest.raises(ValueError, match="must differ"):
            _ctx(sender="alice", recipient="alice")

    def test_negative_prior_rejected(self) -> None:
        with pytest.raises(ValueError, match="prior_interaction_count"):
            _ctx(prior_count=-1)

    def test_repair_requires_misalignment(self) -> None:
        with pytest.raises(ValueError, match="last_interaction_was_misaligned"):
            _ctx(kind=EtiquetteEventKind.REPAIR, misaligned=False)

class TestCraftAllKinds:
    def setup_method(self) -> None:
        self.t = EtiquetteTransmitter()

    @pytest.mark.parametrize(
        "kind,explicit_close_expected",
        [
            (EtiquetteEventKind.GREETING, False),
            (EtiquetteEventKind.ACKNOWLEDGMENT, False),
            (EtiquetteEventKind.INTRODUCTION, False),
            (EtiquetteEventKind.FAREWELL, True),
            (EtiquetteEventKind.GRATITUDE, False),
        ],
    )
    def test_kind_rendering(
        self, kind: EtiquetteEventKind, explicit_close_expected: bool,
    ) -> None:
        out: EtiquetteMessage = self.t.craft(_ctx(kind=kind))
        assert out.kind is kind
        assert out.body  # non-empty
        assert out.explicit_close is explicit_close_expected

    def test_repair_kind(self) -> None:
        out = self.t.craft(_ctx(
            kind=EtiquetteEventKind.REPAIR, misaligned=True,
        ))
        assert out.kind is EtiquetteEventKind.REPAIR
        assert "alice" in out.body or "Sorry" in out.body

class TestTone:
    def setup_method(self) -> None:
        self.t = EtiquetteTransmitter()

    def test_formal_tone_distinguishable(self) -> None:
        formal = self.t.craft(_ctx(tone=EtiquetteTone.FORMAL))
        informal = self.t.craft(_ctx(tone=EtiquetteTone.INFORMAL))
        neutral = self.t.craft(_ctx(tone=EtiquetteTone.NEUTRAL))
        assert formal.body != informal.body
        assert informal.body != neutral.body
        assert formal.body != neutral.body

class TestScaleAwareness:
    def setup_method(self) -> None:
        self.t = EtiquetteTransmitter()

    def test_cell_to_cell(self) -> None:
        out = self.t.craft(_ctx(
            sender_scale=EntityScale.CELL,
            recipient_scale=EntityScale.CELL,
        ))
        assert out.sender_scale is EntityScale.CELL
        assert out.recipient_scale is EntityScale.CELL

    def test_node_to_node(self) -> None:
        out = self.t.craft(_ctx(
            sender="node-alpha", recipient="node-beta",
            sender_scale=EntityScale.NODE,
            recipient_scale=EntityScale.NODE,
        ))
        assert out.sender_scale is EntityScale.NODE
        assert out.recipient_scale is EntityScale.NODE

    def test_formal_template_mentions_scope(self) -> None:
        out = self.t.craft(_ctx(
            sender_scale=EntityScale.NODE,
            tone=EtiquetteTone.FORMAL,
        ))
        # Formal template includes the sender_scope ("node")
        assert "node" in out.body

class TestExplicitClose:
    def setup_method(self) -> None:
        self.t = EtiquetteTransmitter()

    def test_farewell_always_close(self) -> None:
        out = self.t.craft(_ctx(kind=EtiquetteEventKind.FAREWELL))
        assert out.explicit_close

    def test_other_kind_can_close_via_flag(self) -> None:
        out = self.t.craft(_ctx(
            kind=EtiquetteEventKind.ACKNOWLEDGMENT,
            explicit_close=True,
        ))
        assert out.explicit_close

    def test_rationale_carries_metadata(self) -> None:
        out = self.t.craft(_ctx())
        assert "alice" in out.rationale
        assert "bob" in out.rationale
        assert "kind=greeting" in out.rationale
