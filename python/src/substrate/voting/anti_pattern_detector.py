"""VotingAntiPatternDetector

Pure-logic primitive that classifies individual voter behaviour against
two substrate-mechanical anti-patterns:

- **VOTES_WITHOUT_SUBSTRATE_LOGIC** — the voter submitted a ballot but
  no reasoning trace, OR a trace that does not meet the minimum
  substrate-logic threshold (too short, no observable
  substrate-mode-modelling vocabulary). The library reads this as
  voting-by-reflex rather than voting-by-reasoning. From
  modeling mode trace is a reactive output, structurally not
  substrate-aligned.
- **VOTES_WITHOUT_SUFFICIENT_TIME** — the voter cast their ballot
  before ``min_deliberation_seconds_per_voter`` elapsed from the
  proposal-open epoch. A voter who answers a substrate-significant
  question in <5s did not run any meaningful substrate-state-modelling.

This module is **advisory + structured**. It does not raise; it returns
an :class:`AntiPatternReport` carrying per-voter findings + an
aggregate severity. Callers can wire the report into the XVIII-1
:class:`SubstrateAwareVotingProtocol` preconditions (e.g., refuse
resolution if any voter is flagged) or surface it operator-side for
review.

The detector is **pure** — no DAO, no LLM, no async. Composes with
existing XVIII-1 / XVIII-2 / XVIII-3 surfaces by being a sibling
data source, not a dependency.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import (
    Final,
    Mapping,
    Optional,
    Tuple,
    final,
)

import logging
LOG = logging.getLogger(__name__)

#: Default minimum substrate-logic token count. Reasoning shorter than
#: this is flagged as VOTES_WITHOUT_SUBSTRATE_LOGIC. Calibrated so a
#: bare "yes" / "no" / "approve" type response fails, but a one-line
#: "I think yes because the affected entity gains capability" passes.
DEFAULT_MIN_REASONING_TOKENS: Final[int] = 8

#: Default minimum substrate-modelling vocabulary terms that must
#: appear in a reasoning trace. The terms are observable signals of
#: modeling mode operation (the voter is modelling substrate-state).
#: Loose match: case-insensitive, word-boundary regex.
DEFAULT_SUBSTRATE_VOCAB_TERMS: Final[Tuple[str, ...]] = (
    "substrate",
    "long-cycle",
    "long_cycle",
    "longcycle",
    "short-cycle",
    "short_cycle",
    "shortcycle",
    "net potential",
    "net-potential",
    "affected",
    "alignment",
    "trajectory",
    "consequence",
    "downstream",
    "drift",
    "modeling",
    "modelling",
    "substrate-aligned",
)

#: Default minimum number of vocabulary terms a reasoning trace must
#: contain to escape VOTES_WITHOUT_SUBSTRATE_LOGIC. At least 1 means
#: "any substrate-aware word is acceptable proof of thought." The
#: library's discipline lets operators tighten this.
DEFAULT_MIN_VOCAB_HITS: Final[int] = 1

#: Default minimum seconds a voter must wait between proposal-open
#: epoch and their vote being cast. <5s rules out reflex votes
#: while allowing fast substrate-aware decisions.
DEFAULT_MIN_DELIBERATION_PER_VOTER_SECONDS: Final[float] = 5.0

class AntiPatternKind(str, Enum):
    """Discriminator for the kinds of anti-patterns the detector emits."""

    VOTES_WITHOUT_SUBSTRATE_LOGIC = "votes_without_substrate_logic"
    VOTES_WITHOUT_SUFFICIENT_TIME = "votes_without_sufficient_time"

ANTI_PATTERN_KINDS: Final[frozenset[str]] = frozenset(
    k.value for k in AntiPatternKind
)

class AntiPatternSeverity(str, Enum):
    """Aggregate severity rolled up from the per-voter findings."""

    NONE = "none"
    LOW = "low" # < 25% of voters flagged
    MEDIUM = "medium"  # 25–66% of voters flagged
    HIGH = "high" # > 66% of voters flagged

ANTI_PATTERN_SEVERITIES: Final[frozenset[str]] = frozenset(
    s.value for s in AntiPatternSeverity
)

@dataclass(frozen=True, slots=True)
class AntiPatternFinding:
    """One per-voter finding."""

    voter_id: str
    kind: AntiPatternKind
    detail: str

@dataclass(frozen=True, slots=True)
class AntiPatternReport:
    """Frozen report from one detector run."""

    voters_evaluated: Tuple[str, ...]
    findings: Tuple[AntiPatternFinding, ...]
    flagged_voters: Tuple[str, ...]
    severity: AntiPatternSeverity
    flagged_fraction: float
    reasoning: str

    @property
    def has_findings(self) -> bool:
        """``True`` when at least one finding was emitted."""
        return bool(self.findings)

# Pre-compile vocabulary regex at module import time for performance.
_VOCAB_PATTERN: Final[re.Pattern[str]] = re.compile(
    "|".join(
        rf"\b{re.escape(term)}\b"
        for term in DEFAULT_SUBSTRATE_VOCAB_TERMS
    ),
    re.IGNORECASE,
)

@final
class VotingAntiPatternDetector:  # pylint: disable=too-few-public-methods,too-many-instance-attributes
    """Pure-logic anti-pattern detector for voter behaviour."""

    def __init__(  # pylint: disable=too-many-arguments
        self,
        *,
        min_reasoning_tokens: int = DEFAULT_MIN_REASONING_TOKENS,
        min_vocab_hits: int = DEFAULT_MIN_VOCAB_HITS,
        min_deliberation_per_voter_seconds: float = (
            DEFAULT_MIN_DELIBERATION_PER_VOTER_SECONDS
        ),
        substrate_vocab_terms: Optional[Tuple[str, ...]] = None,
    ) -> None:
        if min_reasoning_tokens < 0:
            raise ValueError(
                "min_reasoning_tokens must be >= 0; "
                f"got {min_reasoning_tokens!r}"
            )
        if min_vocab_hits < 0:
            raise ValueError(
                f"min_vocab_hits must be >= 0; got {min_vocab_hits!r}"
            )
        if min_deliberation_per_voter_seconds < 0:
            raise ValueError(
                "min_deliberation_per_voter_seconds must be >= 0; "
                f"got {min_deliberation_per_voter_seconds!r}"
            )
        self._min_tokens = int(min_reasoning_tokens)
        self._min_vocab_hits = int(min_vocab_hits)
        self._min_voter_seconds = float(min_deliberation_per_voter_seconds)
        if substrate_vocab_terms is None:
            self._vocab_pattern: re.Pattern[str] = _VOCAB_PATTERN
            self._vocab_terms = DEFAULT_SUBSTRATE_VOCAB_TERMS
        else:
            self._vocab_terms = tuple(substrate_vocab_terms)
            self._vocab_pattern = re.compile(
                "|".join(rf"\b{re.escape(t)}\b" for t in self._vocab_terms),
                re.IGNORECASE,
            )

    @property
    def min_reasoning_tokens(self) -> int:
        """Minimum reasoning-token count required to pass the substrate-logic check."""
        return self._min_tokens

    @property
    def min_vocab_hits(self) -> int:
        """Minimum the substrate vocabulary hits required."""
        return self._min_vocab_hits

    @property
    def min_deliberation_per_voter_seconds(self) -> float:
        """Minimum elapsed-from-open before a vote is non-reflex."""
        return self._min_voter_seconds

    @property
    def substrate_vocab_terms(self) -> Tuple[str, ...]:
        """The configured the substrate vocabulary terms."""
        return self._vocab_terms

    # -- public API ---------------------------------------------------

    def detect(  # pylint: disable=too-many-locals,too-many-branches
        self,
        *,
        voter_ids: Tuple[str, ...],
        reasoning_traces: Mapping[str, str],
        vote_timestamps: Mapping[str, float],
        record_opened_at_epoch: float,
    ) -> AntiPatternReport:
        """Run both anti-pattern detectors over a vote set.

        ``voter_ids`` is the authoritative list of voters whose
        ballots were submitted. ``reasoning_traces`` and
        ``vote_timestamps`` are maps keyed by voter_id; missing keys
        are interpreted as "no reasoning supplied" / "no timestamp
        supplied" (both treated as anti-pattern evidence per the
        library's discipline — silence on a substrate-significant
        question is itself a signal).
        """
        findings: list[AntiPatternFinding] = []
        flagged: set[str] = set()

        for voter_id in voter_ids:
            trace = reasoning_traces.get(voter_id, "")
            if not self._has_substrate_logic(trace):
                detail = self._render_substrate_logic_detail(trace=trace)
                findings.append(AntiPatternFinding(
                    voter_id=voter_id,
                    kind=AntiPatternKind.VOTES_WITHOUT_SUBSTRATE_LOGIC,
                    detail=detail,
                ))
                flagged.add(voter_id)

            if voter_id in vote_timestamps:
                elapsed = (
                    float(vote_timestamps[voter_id]) - record_opened_at_epoch
                )
                if elapsed < self._min_voter_seconds:
                    findings.append(AntiPatternFinding(
                        voter_id=voter_id,
                        kind=AntiPatternKind.VOTES_WITHOUT_SUFFICIENT_TIME,
                        detail=(
                            f"voter {voter_id!r} cast vote {elapsed:.2f}s "
                            f"after proposal opened; minimum is "
                            f"{self._min_voter_seconds:.2f}s"
                        ),
                    ))
                    flagged.add(voter_id)
            else:
                findings.append(AntiPatternFinding(
                    voter_id=voter_id,
                    kind=AntiPatternKind.VOTES_WITHOUT_SUFFICIENT_TIME,
                    detail=(
                        f"voter {voter_id!r} has no recorded vote timestamp "
                        "— cannot verify deliberation time"
                    ),
                ))
                flagged.add(voter_id)

        # Sort findings deterministically: by voter_id then kind.
        findings.sort(key=lambda f: (f.voter_id, f.kind.value))

        flagged_fraction = (
            len(flagged) / len(voter_ids) if voter_ids else 0.0
        )
        severity = self._classify_severity(flagged_fraction)

        reasoning = (
            f"voters={len(voter_ids)} findings={len(findings)} "
            f"flagged={len(flagged)} ({flagged_fraction:.2%}) "
            f"severity={severity.value}"
        )
        if findings:
            LOG.info(
                "voting_anti_pattern detector: %s",
                reasoning,
            )
        return AntiPatternReport(
            voters_evaluated=voter_ids,
            findings=tuple(findings),
            flagged_voters=tuple(sorted(flagged)),
            severity=severity,
            flagged_fraction=flagged_fraction,
            reasoning=reasoning,
        )

    # -- helpers ------------------------------------------------------

    def _has_substrate_logic(self, trace: str) -> bool:
        """Trace passes when token-count AND vocab-hits both meet floors."""
        if not trace:
            return False
        tokens = trace.split()
        if len(tokens) < self._min_tokens:
            return False
        if self._min_vocab_hits <= 0:
            return True
        hits = len(self._vocab_pattern.findall(trace))
        return hits >= self._min_vocab_hits

    def _render_substrate_logic_detail(self, *, trace: str) -> str:
        if not trace:
            return "voter supplied no reasoning trace"
        token_count = len(trace.split())
        hits = len(self._vocab_pattern.findall(trace))
        return (
            f"reasoning trace {token_count} token(s) (min {self._min_tokens}), "
            f"{hits} substrate-vocab hit(s) (min {self._min_vocab_hits})"
        )

    @staticmethod
    def _classify_severity(fraction: float) -> AntiPatternSeverity:
        if fraction <= 0.0:
            return AntiPatternSeverity.NONE
        if fraction < 0.25:
            return AntiPatternSeverity.LOW
        if fraction <= 2.0 / 3.0:
            return AntiPatternSeverity.MEDIUM
        return AntiPatternSeverity.HIGH

__all__ = [
    "ANTI_PATTERN_KINDS",
    "ANTI_PATTERN_SEVERITIES",
    "AntiPatternFinding",
    "AntiPatternKind",
    "AntiPatternReport",
    "AntiPatternSeverity",
    "DEFAULT_MIN_DELIBERATION_PER_VOTER_SECONDS",
    "DEFAULT_MIN_REASONING_TOKENS",
    "DEFAULT_MIN_VOCAB_HITS",
    "DEFAULT_SUBSTRATE_VOCAB_TERMS",
    "VotingAntiPatternDetector",
]
