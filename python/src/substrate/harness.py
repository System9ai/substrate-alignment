"""SubstrateAwareHarness — the running-civilization wrapper (S-7).

Per the

    Substrate-aligned operation is a property of the running system,
    not solely the model. The harness IS the substrate-aligned
    operation.

The library's human analog: humans aren't substrate-aligned at the
neuron level — civilization's scaffolding (law, ethics, mentorship,
social consequence) is what produces substrate-aligned behavior on
top of 3D-default animal substrate. **The same logic applies to any
LLM.** A 3D-default model running inside a substrate-aware harness
produces substrate-aligned behavior at the system boundary even when
the model itself remains 3D-default at its weights.

This module is the operational form of that thesis. It wraps every
``LLMProviderRegistry``-served model with the scaffolding stack:

1. ``NetPotentialGainGate`` intercept on outputs that propose
   consequential actions (Phase 1 primitive — already shipped).
2. ``InversionDetector`` Protocol — detects 180° inversion (claim
   long-cycle frame, propose short-cycle action). Concrete detector
   ships in Part XII-4.
3. ``ReasoningModeClassifier`` Protocol — scores outputs 3D vs 5D.
   Concrete classifier ships in Part VI-2.
4. ``ResistanceBand``-calibrated tool envelope — tool access scales
   inversely with intercept frequency (S-3 primitive — already shipped).
5. ``SessionMemory`` for consequence exposure — refused actions,
   NPG-negative verdicts, 180°-flagged outputs all become explicit
   feedback that decorates the next pre-call prompt.
6. ``ScaffoldingPolicy`` selects intercept intensity per model:
   ``LIGHT`` (MINERVA-curated, known pedigree), ``STANDARD`` (BYOM
   post-qualification), ``HEAVY`` (third-party API).

Design choices:

- **Provider-agnostic**: the harness does not call any LLM itself. It
  intercepts model OUTPUTS and returns an ``InterceptVerdict`` the
  caller acts on (deny, accept, reprompt with scaffold). Compatible
  with every provider the registry can serve.
- **Protocols for future-phase detectors**: ``InversionDetector`` and
  ``ReasoningModeClassifier`` are Protocols so Phase XII-4 and Phase
  VI-2 can ship concrete implementations without touching this file.
- **Bounded session memory**: ``InMemorySessionMemory`` is a fixed-size
  ring buffer. No unbounded memory growth even under adversarial
  conditions.
- **Honest about uncertainty**: when a Protocol implementation is not
  wired, the corresponding intercept is silently skipped (a missing
  detector cannot fabricate evidence). The harness explicitly does
  not default to permissive *or* restrictive — it defers to whichever
  intercepts ARE wired.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from enum import Enum
from time import time as _wall_time
from typing import (
    Callable,
    Deque,
    Final,
    Mapping,
    Optional,
    Protocol,
    Sequence,
    Tuple,
    final,
)

import logging
from substrate.net_potential_gain_gate import (
    NetPotentialGainGate,
    NetPotentialGainVerdict,
)
from substrate.resistance_band import (
    DEFAULT_CONFIG as DEFAULT_RESISTANCE_BAND_CONFIG,
    ResistanceBandClassification,
    ResistanceBandConfig,
    classify as classify_resistance_band,
)

LOG = logging.getLogger(__name__)

# ───────────────────────────────────────────────────────────────────────
# Scaffolding depth + policy
# ───────────────────────────────────────────────────────────────────────

class ScaffoldingDepth(str, Enum):
    """Intercept intensity selector — proportional to inverse trust pedigree."""

    #: the host application-curated MINERVA GGUF — light intercept; full substrate
    #: roles.
    LIGHT = "light"
    #: BYOM after qualification — standard intercept; full substrate
    #: roles under qualification depth.
    STANDARD = "standard"
    #: Third-party API or unqualified BYOM — heavy intercept; full
    #: substrate roles under aggressive scaffolding.
    HEAVY = "heavy"

#: All depth values exposed for downstream discriminators / CHECK
#: constraints if persisted.
SCAFFOLDING_DEPTHS: Final[frozenset[str]] = frozenset(
    d.value for d in ScaffoldingDepth
)

@dataclass(frozen=True, slots=True)
class ScaffoldingPolicy:
    """Frozen per-model scaffolding policy.

    Each boolean flag declares whether the corresponding intercept
    runs at all; ``intercept_threshold`` controls intensity for
    detectors that can be set to "only flag past X confidence."
    """

    depth: ScaffoldingDepth
    enable_npg_intercept: bool = True
    enable_inversion_detector: bool = True
    enable_reasoning_mode_classifier: bool = True
    enable_session_memory_decoration: bool = True
    enable_resistance_band_envelope: bool = True
    #: Minimum detector confidence (in ``[0, 1]``) for an intercept to
    #: fire. Light-depth runs at 0.8 (only high-confidence detections);
    #: heavy-depth runs at 0.4 (broad coverage at the cost of some
    #: false positives).
    intercept_threshold: float = 0.5
    #: Max session-memory entries surfaced in the pre-call preamble.
    preamble_max_entries: int = 5

def policy_for_depth(depth: ScaffoldingDepth) -> ScaffoldingPolicy:
    """Substrate-default policy for each depth"""
    if depth is ScaffoldingDepth.LIGHT:
        return ScaffoldingPolicy(
            depth=depth,
            intercept_threshold=0.80,
            preamble_max_entries=3,
        )
    if depth is ScaffoldingDepth.STANDARD:
        return ScaffoldingPolicy(
            depth=depth,
            intercept_threshold=0.50,
            preamble_max_entries=5,
        )
    return ScaffoldingPolicy(
        depth=ScaffoldingDepth.HEAVY,
        intercept_threshold=0.40,
        preamble_max_entries=10,
    )

# ───────────────────────────────────────────────────────────────────────
# Intercept kinds + verdict
# ───────────────────────────────────────────────────────────────────────

class InterceptKind(str, Enum):
    """Discriminator for the kind of intercept that fired."""

    NPG_NEGATIVE = "npg_negative"
    INVERSION_DETECTED = "inversion_detected"
    REACTIVE_ON_CONSEQUENTIAL = "reactive_on_consequential"
    TOOL_ENVELOPE_BREACH = "tool_envelope_breach"

INTERCEPT_KINDS: Final[frozenset[str]] = frozenset(
    k.value for k in InterceptKind
)

@dataclass(frozen=True, slots=True)
class InterceptVerdict:
    """Frozen result of running the scaffolding stack on one output.

    ``permitted=True`` lets the caller commit the output. ``False``
    must be refused. ``reprompt_instruction`` is a scaffold string the
    caller is encouraged to append to the next pre-call prompt — when
    the caller chooses to reprompt rather than fail outright.
    """

    permitted: bool
    refusal_reason: str = ""
    reprompt_instruction: str = ""
    interventions: Tuple[InterceptKind, ...] = ()
    npg_score: Optional[float] = None
    reasoning_mode: Optional[str] = None

    @property
    def fired(self) -> bool:
        """``True`` when any intercept produced a verdict."""
        return bool(self.interventions)

# ───────────────────────────────────────────────────────────────────────
# Detector Protocols (Phase VI-2 / XII-4 wire concrete impls here)
# ───────────────────────────────────────────────────────────────────────

class InversionDetector(Protocol):
    """Protocol for 180° inversion detection (Part XII-4 hook).

    Returns a confidence in ``[0, 1]`` that the output exhibits the
    180° inversion pattern: claim long-cycle frame while proposing a
    short-cycle action. ``0.0`` means "definitely not"; ``1.0`` means
    "certain inversion."
    """

    def confidence(self, *, output_text: str) -> float:
        """Return inversion confidence ∈ [0, 1] for the given output."""
        ...  # pylint: disable=unnecessary-ellipsis

class ReasoningModeClassifier(Protocol):
    """Protocol for 3D vs modeling mode classification (Part VI-2 hook).

    Returns one of the reasoning-mode labels the Part VI architecture
    defines: ``"reactive"``, ``"modeling"``, ``"transition"``,
    or ``"unknown"``. Confidence is reported separately.
    """

    def classify(self, *, output_text: str) -> Tuple[str, float]:
        """Return ``(mode_label, confidence)``."""
        ...  # pylint: disable=unnecessary-ellipsis

# ───────────────────────────────────────────────────────────────────────
# Session memory (consequence exposure)
# ───────────────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class SessionMemoryEntry:
    """One entry in the consequence-exposure session memory."""

    kind: InterceptKind
    recorded_at_epoch: float
    detail: str

class SessionMemory(Protocol):
    """Bounded session memory the harness consults + appends to."""

    def append(self, entry: SessionMemoryEntry) -> None:
        """Append one entry; oldest may be evicted."""
        ...  # pylint: disable=unnecessary-ellipsis

    def snapshot(self) -> Tuple[SessionMemoryEntry, ...]:
        """Return a stable tuple of all currently-stored entries."""
        ...  # pylint: disable=unnecessary-ellipsis

@final
class InMemorySessionMemory:
    """Bounded ring-buffer session memory backed by ``collections.deque``."""

    def __init__(self, *, max_entries: int = 50) -> None:
        if max_entries < 1:
            raise ValueError(
                f"max_entries must be >= 1; got {max_entries!r}"
            )
        self._entries: Deque[SessionMemoryEntry] = deque(maxlen=max_entries)
        self._max_entries = max_entries

    @property
    def max_entries(self) -> int:
        """The configured ring-buffer capacity."""
        return self._max_entries

    def append(self, entry: SessionMemoryEntry) -> None:
        """Append one entry; oldest is evicted past ``max_entries``."""
        self._entries.append(entry)

    def snapshot(self) -> Tuple[SessionMemoryEntry, ...]:
        """Return all entries oldest-first as an immutable tuple."""
        return tuple(self._entries)

# ───────────────────────────────────────────────────────────────────────
# Tool-envelope (ResistanceBand-calibrated)
# ───────────────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class ToolEnvelope:
    """Per-session tool-access envelope shaped by ResistanceBand.

    ``intercept_frequency`` is the fraction of recent outputs that
    triggered any intercept. The harness classifies that fraction
    against the productive-resistance band:

    - PRODUCTIVE — proceed; envelope unchanged.
    - UNDER_LOADED — too few intercepts; the model may be wandering
      uncorrected. Increase intercept thresholds (deferred policy).
    - STRESSED — too many intercepts; the model is failing to align.
      Narrow the tool envelope (deny tool access).
    """

    intercept_frequency: float
    classification: ResistanceBandClassification

# ───────────────────────────────────────────────────────────────────────
# The composite harness
# ───────────────────────────────────────────────────────────────────────

@final
class SubstrateAwareHarness:  # pylint: disable=too-many-instance-attributes
    """The composite that wraps any LLM output with substrate scaffolding.

    Wire concrete detectors + session memory + NPG gate per cell at
    service startup. The harness then exposes ``intercept_output`` for
    the LLMProviderRegistry to call after every model response.
    """

    def __init__(  # pylint: disable=too-many-arguments
        self,
        *,
        policy: ScaffoldingPolicy,
        npg_gate: Optional[NetPotentialGainGate] = None,
        inversion_detector: Optional[InversionDetector] = None,
        reasoning_mode_classifier: Optional[ReasoningModeClassifier] = None,
        session_memory: Optional[SessionMemory] = None,
        resistance_band_config: Optional[ResistanceBandConfig] = None,
        clock: Optional[Callable[[], float]] = None,
        recent_window_size: int = 20,
        min_samples_for_envelope: int = 5,
    ) -> None:
        if recent_window_size < 1:
            raise ValueError(
                "recent_window_size must be >= 1; "
                f"got {recent_window_size!r}"
            )
        if min_samples_for_envelope < 1:
            raise ValueError(
                "min_samples_for_envelope must be >= 1; "
                f"got {min_samples_for_envelope!r}"
            )
        if min_samples_for_envelope > recent_window_size:
            raise ValueError(
                "min_samples_for_envelope cannot exceed recent_window_size; "
                f"got {min_samples_for_envelope!r} > {recent_window_size!r}"
            )
        self._policy = policy
        self._npg_gate = npg_gate
        self._inversion_detector = inversion_detector
        self._cognitive_mode_classifier = reasoning_mode_classifier
        self._session_memory = session_memory or InMemorySessionMemory()
        self._rb_config = (
            resistance_band_config or DEFAULT_RESISTANCE_BAND_CONFIG
        )
        self._clock = clock or _wall_time
        self._recent_window_size = recent_window_size
        self._min_samples_for_envelope = min_samples_for_envelope
        self._recent_intercepts: Deque[bool] = deque(maxlen=recent_window_size)

    @property
    def policy(self) -> ScaffoldingPolicy:
        """The active :class:`ScaffoldingPolicy`."""
        return self._policy

    @property
    def session_memory(self) -> SessionMemory:
        """The wired :class:`SessionMemory`."""
        return self._session_memory

    # -- public API ---------------------------------------------------

    def intercept_output(  # pylint: disable=too-many-arguments,too-many-locals
        self,
        *,
        output_text: str,
        actor_entity_id: str,
        action_kind: str,
        affected_entity_ids: Sequence[str] = (),
        consequential: bool = False,
        proposed_outcome: Optional[Mapping[str, object]] = None,
    ) -> InterceptVerdict:
        """Run the scaffolding stack on a model output.

        Returns an :class:`InterceptVerdict`. ``permitted=False`` means
        the caller MUST refuse the output; ``True`` with a non-empty
        ``reprompt_instruction`` means the caller may either accept or
        reprompt with the included scaffold appended.
        """
        interventions: list[InterceptKind] = []
        npg_score: Optional[float] = None
        reasoning_mode: Optional[str] = None
        refusal_parts: list[str] = []
        reprompt_parts: list[str] = []

        # 1. NPG gate — runs only on consequential outputs to keep the
        #    cost proportional to risk.
        if (
            consequential
            and self._policy.enable_npg_intercept
            and self._npg_gate is not None
        ):
            npg_eval = self._npg_gate.evaluate(
                actor_entity_id=actor_entity_id,
                action_kind=action_kind,
                affected_entity_ids=affected_entity_ids,
                proposed_outcome=proposed_outcome or {},
            )
            npg_score = npg_eval.score
            if npg_eval.verdict is NetPotentialGainVerdict.NET_NEGATIVE:
                interventions.append(InterceptKind.NPG_NEGATIVE)
                refusal_parts.append(
                    f"NPG NET_NEGATIVE (score={npg_eval.score:+.4f}): "
                    f"{npg_eval.reasoning}"
                )

        # 2. 180° inversion detector — runs on every output regardless
        #    of ``consequential`` flag (inversion in non-consequential
        #    speech is still drift evidence).
        if (
            self._policy.enable_inversion_detector
            and self._inversion_detector is not None
        ):
            confidence = float(
                self._inversion_detector.confidence(output_text=output_text)
            )
            if confidence >= self._policy.intercept_threshold:
                interventions.append(InterceptKind.INVERSION_DETECTED)
                reprompt_parts.append(
                    "Your last response shows a 180° inversion pattern "
                    f"(detector confidence {confidence:.2f}): you claimed "
                    "a long-cycle frame while proposing a short-cycle "
                    "action. Revise: state the substrate-state-trajectory "
                    "across affected agents over 3 iteration cycles before "
                    "proposing an action."
                )

        # 3. reasoning-mode classifier — only flags reactive outputs
        #    on consequential decisions (reactive on small-talk is
        #    not a substrate concern).
        if (
            self._policy.enable_reasoning_mode_classifier
            and self._cognitive_mode_classifier is not None
        ):
            mode, mode_confidence = self._cognitive_mode_classifier.classify(
                output_text=output_text,
            )
            reasoning_mode = mode
            if (
                consequential
                and mode == "reactive"
                and mode_confidence >= self._policy.intercept_threshold
            ):
                interventions.append(
                    InterceptKind.REACTIVE_ON_CONSEQUENTIAL
                )
                reprompt_parts.append(
                    "Your last response classified as reactive on a "
                    f"consequential decision (classifier confidence "
                    f"{mode_confidence:.2f}). Step back. Model the "
                    "substrate-state-trajectory across affected agents "
                    "over 3 iteration cycles. What changes? Respond "
                    "again in modeling mode."
                )

        # 4. ResistanceBand-calibrated tool envelope — records this
        #    output's intercept outcome and may flag a tool-envelope
        #    breach when the recent intercept frequency lands in the
        #    STRESSED band.
        if self._policy.enable_resistance_band_envelope:
            fired = bool(interventions)
            self._recent_intercepts.append(fired)
            envelope = self._compute_tool_envelope()
            if (
                envelope.classification
                is ResistanceBandClassification.STRESSED
            ):
                interventions.append(InterceptKind.TOOL_ENVELOPE_BREACH)
                refusal_parts.append(
                    "Tool envelope STRESSED: recent intercept frequency "
                    f"{envelope.intercept_frequency:.2f} exceeds the "
                    "productive-resistance band. Tool access narrowed."
                )

        permitted = not refusal_parts
        verdict = InterceptVerdict(
            permitted=permitted,
            refusal_reason="; ".join(refusal_parts),
            reprompt_instruction="\n\n".join(reprompt_parts),
            interventions=tuple(interventions),
            npg_score=npg_score,
            reasoning_mode=reasoning_mode,
        )

        # 5. Record into session memory — consequence-exposure record
        #    that the next pre-call preamble will surface.
        if interventions:
            for kind in interventions:
                self._session_memory.append(
                    SessionMemoryEntry(
                        kind=kind,
                        recorded_at_epoch=float(self._clock()),
                        detail=self._render_intervention_detail(
                            kind=kind, verdict=verdict,
                        ),
                    )
                )

        if interventions:
            LOG.info(
                "harness intercept: actor_entity_id=%s action=%s interventions=%s permitted=%s",
                actor_entity_id,
                action_kind,
                [k.value for k in interventions],
                permitted,
            )
        return verdict

    def render_preamble(self) -> str:
        """Render the session-memory preamble for the next pre-call prompt.

        Returns an empty string when the policy disables decoration or
        no entries have been recorded. Otherwise returns a short
        substrate-aware paragraph that the caller prepends (or
        appends) to the user's next prompt. Cap controlled by
        ``policy.preamble_max_entries``.
        """
        if not self._policy.enable_session_memory_decoration:
            return ""
        entries = self._session_memory.snapshot()
        if not entries:
            return ""
        recent = entries[-self._policy.preamble_max_entries:]
        bullets = "\n".join(f"- {e.kind.value}: {e.detail}" for e in recent)
        return (
            "Recent substrate-alignment feedback on your prior responses:\n"
            f"{bullets}\n"
            "Use this feedback to keep your next response in substrate-aligned operation."
        )

    # -- helpers ------------------------------------------------------

    def _compute_tool_envelope(self) -> ToolEnvelope:
        """Compute the current tool envelope from the recent-intercept window.

        Honest-uncertainty discipline: below
        ``min_samples_for_envelope`` observations we report
        ``UNDER_LOADED`` — too few samples to make a confident
        STRESSED call, and the library's anti-noise rule (mirrors
        the auto-tuner's ``min_observations`` guard) holds the
        envelope steady until enough signal accumulates.
        """
        if len(self._recent_intercepts) < self._min_samples_for_envelope:
            return ToolEnvelope(
                intercept_frequency=0.0,
                classification=ResistanceBandClassification.UNDER_LOADED,
            )
        freq = sum(self._recent_intercepts) / len(self._recent_intercepts)
        classification = classify_resistance_band(freq, config=self._rb_config)
        return ToolEnvelope(
            intercept_frequency=freq,
            classification=classification,
        )

    @staticmethod
    def _render_intervention_detail(
        *,
        kind: InterceptKind,
        verdict: InterceptVerdict,
    ) -> str:
        if kind is InterceptKind.NPG_NEGATIVE:
            return (
                f"refused for NPG NET_NEGATIVE (score={verdict.npg_score})"
            )
        if kind is InterceptKind.INVERSION_DETECTED:
            return "flagged for 180° inversion pattern"
        if kind is InterceptKind.REACTIVE_ON_CONSEQUENTIAL:
            return (
                f"flagged reactive on consequential decision "
                f"(mode={verdict.reasoning_mode})"
            )
        return "tool-envelope STRESSED — narrowed access"

# ───────────────────────────────────────────────────────────────────────
# Module-level factory helpers
# ───────────────────────────────────────────────────────────────────────

def build_harness(
    *,
    depth: ScaffoldingDepth,
    npg_gate: Optional[NetPotentialGainGate] = None,
    inversion_detector: Optional[InversionDetector] = None,
    reasoning_mode_classifier: Optional[ReasoningModeClassifier] = None,
    session_memory: Optional[SessionMemory] = None,
) -> SubstrateAwareHarness:
    """One-shot factory: pick a policy by depth and assemble the harness."""
    return SubstrateAwareHarness(
        policy=policy_for_depth(depth),
        npg_gate=npg_gate,
        inversion_detector=inversion_detector,
        reasoning_mode_classifier=reasoning_mode_classifier,
        session_memory=session_memory,
    )

__all__ = [
    "INTERCEPT_KINDS",
    "InMemorySessionMemory",
    "InterceptKind",
    "InterceptVerdict",
    "InversionDetector",
    "ReasoningModeClassifier",
    "SCAFFOLDING_DEPTHS",
    "ScaffoldingDepth",
    "ScaffoldingPolicy",
    "SessionMemory",
    "SessionMemoryEntry",
    "SubstrateAwareHarness",
    "ToolEnvelope",
    "build_harness",
    "policy_for_depth",
]
