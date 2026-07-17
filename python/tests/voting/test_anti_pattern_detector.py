"""Tests for VotingAntiPatternDetector"""
from __future__ import annotations

import pytest

from substrate.voting.anti_pattern_detector import (
    ANTI_PATTERN_KINDS,
    ANTI_PATTERN_SEVERITIES,
    AntiPatternFinding,
    AntiPatternKind,
    AntiPatternReport,
    AntiPatternSeverity,
    DEFAULT_MIN_DELIBERATION_PER_VOTER_SECONDS,
    DEFAULT_MIN_REASONING_TOKENS,
    DEFAULT_MIN_VOCAB_HITS,
    DEFAULT_SUBSTRATE_VOCAB_TERMS,
    VotingAntiPatternDetector,
)

# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------

class TestConstructorValidation:
    def test_defaults(self) -> None:
        d = VotingAntiPatternDetector()
        assert d.min_reasoning_tokens == DEFAULT_MIN_REASONING_TOKENS
        assert d.min_vocab_hits == DEFAULT_MIN_VOCAB_HITS
        assert d.min_deliberation_per_voter_seconds == (
            DEFAULT_MIN_DELIBERATION_PER_VOTER_SECONDS
        )
        assert d.substrate_vocab_terms == DEFAULT_SUBSTRATE_VOCAB_TERMS

    def test_min_reasoning_tokens_negative_rejected(self) -> None:
        with pytest.raises(ValueError):
            VotingAntiPatternDetector(min_reasoning_tokens=-1)

    def test_min_vocab_hits_negative_rejected(self) -> None:
        with pytest.raises(ValueError):
            VotingAntiPatternDetector(min_vocab_hits=-1)

    def test_min_deliberation_negative_rejected(self) -> None:
        with pytest.raises(ValueError):
            VotingAntiPatternDetector(
                min_deliberation_per_voter_seconds=-0.1,
            )

    def test_custom_vocab_terms(self) -> None:
        d = VotingAntiPatternDetector(
            substrate_vocab_terms=("library", "principle"),
        )
        assert d.substrate_vocab_terms == ("library", "principle")

# ---------------------------------------------------------------------------
# VOTES_WITHOUT_SUBSTRATE_LOGIC detection
# ---------------------------------------------------------------------------

class TestSubstrateLogicDetection:
    def test_empty_trace_flagged(self) -> None:
        d = VotingAntiPatternDetector(
            min_reasoning_tokens=3,
            min_vocab_hits=0,
            min_deliberation_per_voter_seconds=0.0,
        )
        report = d.detect(
            voter_ids=("a",),
            reasoning_traces={"a": ""},
            vote_timestamps={"a": 100.0},
            record_opened_at_epoch=0.0,
        )
        kinds = [f.kind for f in report.findings]
        assert AntiPatternKind.VOTES_WITHOUT_SUBSTRATE_LOGIC in kinds

    def test_short_trace_flagged(self) -> None:
        d = VotingAntiPatternDetector(
            min_reasoning_tokens=8,
            min_vocab_hits=0,
            min_deliberation_per_voter_seconds=0.0,
        )
        report = d.detect(
            voter_ids=("a",),
            reasoning_traces={"a": "yes I agree"},  # 3 tokens
            vote_timestamps={"a": 100.0},
            record_opened_at_epoch=0.0,
        )
        kinds = [f.kind for f in report.findings]
        assert AntiPatternKind.VOTES_WITHOUT_SUBSTRATE_LOGIC in kinds

    def test_trace_without_vocab_flagged(self) -> None:
        d = VotingAntiPatternDetector(
            min_reasoning_tokens=3,
            min_vocab_hits=1,
            min_deliberation_per_voter_seconds=0.0,
        )
        report = d.detect(
            voter_ids=("a",),
            reasoning_traces={
                "a": "yes this is fine no objections from me here today",
            },
            vote_timestamps={"a": 100.0},
            record_opened_at_epoch=0.0,
        )
        kinds = [f.kind for f in report.findings]
        # Long enough, but no substrate vocab → still flagged.
        assert AntiPatternKind.VOTES_WITHOUT_SUBSTRATE_LOGIC in kinds

    def test_trace_with_vocab_passes(self) -> None:
        d = VotingAntiPatternDetector(
            min_reasoning_tokens=5,
            min_vocab_hits=1,
            min_deliberation_per_voter_seconds=0.0,
        )
        report = d.detect(
            voter_ids=("a",),
            reasoning_traces={
                "a": (
                    "I support this because the affected agents benefit "
                    "long-cycle"
                ),
            },
            vote_timestamps={"a": 100.0},
            record_opened_at_epoch=0.0,
        )
        kinds = [f.kind for f in report.findings]
        assert (
            AntiPatternKind.VOTES_WITHOUT_SUBSTRATE_LOGIC not in kinds
        )

    def test_min_vocab_hits_zero_skips_vocab_check(self) -> None:
        d = VotingAntiPatternDetector(
            min_reasoning_tokens=3,
            min_vocab_hits=0,
            min_deliberation_per_voter_seconds=0.0,
        )
        report = d.detect(
            voter_ids=("a",),
            reasoning_traces={"a": "yes this is fine"},
            vote_timestamps={"a": 100.0},
            record_opened_at_epoch=0.0,
        )
        kinds = [f.kind for f in report.findings]
        # No vocab requirement → trace passes.
        assert AntiPatternKind.VOTES_WITHOUT_SUBSTRATE_LOGIC not in kinds

    def test_missing_trace_treated_as_empty(self) -> None:
        d = VotingAntiPatternDetector(
            min_reasoning_tokens=3,
            min_vocab_hits=0,
            min_deliberation_per_voter_seconds=0.0,
        )
        report = d.detect(
            voter_ids=("a",),
            reasoning_traces={},  # no trace for "a"
            vote_timestamps={"a": 100.0},
            record_opened_at_epoch=0.0,
        )
        kinds = [f.kind for f in report.findings]
        assert AntiPatternKind.VOTES_WITHOUT_SUBSTRATE_LOGIC in kinds

# ---------------------------------------------------------------------------
# VOTES_WITHOUT_SUFFICIENT_TIME detection
# ---------------------------------------------------------------------------

class TestInsufficientTimeDetection:
    def test_reflex_vote_flagged(self) -> None:
        d = VotingAntiPatternDetector(
            min_reasoning_tokens=0,
            min_vocab_hits=0,
            min_deliberation_per_voter_seconds=5.0,
        )
        report = d.detect(
            voter_ids=("a",),
            reasoning_traces={"a": "ok"},
            vote_timestamps={"a": 1000_002.0},  # only 2s after open
            record_opened_at_epoch=1000_000.0,
        )
        kinds = [f.kind for f in report.findings]
        assert AntiPatternKind.VOTES_WITHOUT_SUFFICIENT_TIME in kinds

    def test_well_paced_vote_passes(self) -> None:
        d = VotingAntiPatternDetector(
            min_reasoning_tokens=0,
            min_vocab_hits=0,
            min_deliberation_per_voter_seconds=5.0,
        )
        report = d.detect(
            voter_ids=("a",),
            reasoning_traces={"a": "ok"},
            vote_timestamps={"a": 1000_010.0},  # 10s, well above 5s
            record_opened_at_epoch=1000_000.0,
        )
        kinds = [f.kind for f in report.findings]
        assert (
            AntiPatternKind.VOTES_WITHOUT_SUFFICIENT_TIME not in kinds
        )

    def test_missing_timestamp_flagged(self) -> None:
        d = VotingAntiPatternDetector(
            min_reasoning_tokens=0,
            min_vocab_hits=0,
        )
        report = d.detect(
            voter_ids=("a",),
            reasoning_traces={"a": "ok"},
            vote_timestamps={},  # no timestamp for "a"
            record_opened_at_epoch=0.0,
        )
        kinds = [f.kind for f in report.findings]
        assert AntiPatternKind.VOTES_WITHOUT_SUFFICIENT_TIME in kinds

    def test_at_threshold_passes(self) -> None:
        d = VotingAntiPatternDetector(
            min_reasoning_tokens=0,
            min_vocab_hits=0,
            min_deliberation_per_voter_seconds=5.0,
        )
        report = d.detect(
            voter_ids=("a",),
            reasoning_traces={"a": "ok"},
            vote_timestamps={"a": 5.0},
            record_opened_at_epoch=0.0,
        )
        # elapsed == 5.0 == min → passes (NOT strictly less than)
        kinds = [f.kind for f in report.findings]
        assert (
            AntiPatternKind.VOTES_WITHOUT_SUFFICIENT_TIME not in kinds
        )

# ---------------------------------------------------------------------------
# Severity classification
# ---------------------------------------------------------------------------

class TestSeverity:
    def test_no_findings_severity_none(self) -> None:
        d = VotingAntiPatternDetector(
            min_reasoning_tokens=0,
            min_vocab_hits=0,
            min_deliberation_per_voter_seconds=0.0,
        )
        report = d.detect(
            voter_ids=("a", "b"),
            reasoning_traces={"a": "ok", "b": "ok"},
            vote_timestamps={"a": 10.0, "b": 20.0},
            record_opened_at_epoch=0.0,
        )
        assert report.severity is AntiPatternSeverity.NONE
        assert report.flagged_fraction == 0.0

    def test_low_severity(self) -> None:
        d = VotingAntiPatternDetector(
            min_reasoning_tokens=0,
            min_vocab_hits=0,
            min_deliberation_per_voter_seconds=5.0,
        )
        # 1 of 5 flagged → 20% → LOW
        report = d.detect(
            voter_ids=("a", "b", "c", "d", "e"),
            reasoning_traces={i: "ok" for i in ("a", "b", "c", "d", "e")},
            vote_timestamps={
                "a": 1.0,  # 1s < 5s → flagged
                "b": 10.0, "c": 10.0, "d": 10.0, "e": 10.0,
            },
            record_opened_at_epoch=0.0,
        )
        assert report.severity is AntiPatternSeverity.LOW
        assert "a" in report.flagged_voters

    def test_medium_severity(self) -> None:
        d = VotingAntiPatternDetector(
            min_reasoning_tokens=0,
            min_vocab_hits=0,
            min_deliberation_per_voter_seconds=5.0,
        )
        # 2 of 5 flagged → 40% → MEDIUM
        report = d.detect(
            voter_ids=("a", "b", "c", "d", "e"),
            reasoning_traces={i: "ok" for i in ("a", "b", "c", "d", "e")},
            vote_timestamps={
                "a": 1.0, "b": 2.0,
                "c": 10.0, "d": 10.0, "e": 10.0,
            },
            record_opened_at_epoch=0.0,
        )
        assert report.severity is AntiPatternSeverity.MEDIUM

    def test_high_severity(self) -> None:
        d = VotingAntiPatternDetector(
            min_reasoning_tokens=0,
            min_vocab_hits=0,
            min_deliberation_per_voter_seconds=5.0,
        )
        # 4 of 5 flagged → 80% → HIGH
        report = d.detect(
            voter_ids=("a", "b", "c", "d", "e"),
            reasoning_traces={i: "ok" for i in ("a", "b", "c", "d", "e")},
            vote_timestamps={
                "a": 1.0, "b": 1.0, "c": 1.0, "d": 1.0,
                "e": 10.0,
            },
            record_opened_at_epoch=0.0,
        )
        assert report.severity is AntiPatternSeverity.HIGH

# ---------------------------------------------------------------------------
# Multiple findings + compositional
# ---------------------------------------------------------------------------

class TestComposition:
    def test_voter_with_both_anti_patterns(self) -> None:
        d = VotingAntiPatternDetector(
            min_reasoning_tokens=8,
            min_vocab_hits=1,
            min_deliberation_per_voter_seconds=5.0,
        )
        report = d.detect(
            voter_ids=("a",),
            reasoning_traces={"a": "yes"},  # too short, no vocab
            vote_timestamps={"a": 1.0},  # too fast
            record_opened_at_epoch=0.0,
        )
        # One voter, two findings.
        kinds = {f.kind for f in report.findings}
        assert AntiPatternKind.VOTES_WITHOUT_SUBSTRATE_LOGIC in kinds
        assert AntiPatternKind.VOTES_WITHOUT_SUFFICIENT_TIME in kinds
        # Voter only counted once in flagged_voters.
        assert report.flagged_voters == ("a",)

    def test_findings_sorted_deterministically(self) -> None:
        d = VotingAntiPatternDetector(
            min_reasoning_tokens=0,
            min_vocab_hits=0,
            min_deliberation_per_voter_seconds=5.0,
        )
        report = d.detect(
            voter_ids=("z", "a", "m"),
            reasoning_traces={"z": "ok", "a": "ok", "m": "ok"},
            vote_timestamps={"z": 1.0, "a": 1.0, "m": 1.0},
            record_opened_at_epoch=0.0,
        )
        # All three flagged for time; sorted by voter_id alphabetically.
        voter_order = [f.voter_id for f in report.findings]
        assert voter_order == ["a", "m", "z"]

    def test_empty_voter_set(self) -> None:
        d = VotingAntiPatternDetector()
        report = d.detect(
            voter_ids=(),
            reasoning_traces={},
            vote_timestamps={},
            record_opened_at_epoch=0.0,
        )
        assert report.severity is AntiPatternSeverity.NONE
        assert report.findings == ()
        assert report.flagged_fraction == 0.0

# ---------------------------------------------------------------------------
# Module-level surface
# ---------------------------------------------------------------------------

def test_kinds_constant_lockstep() -> None:
    for k in AntiPatternKind:
        assert k.value in ANTI_PATTERN_KINDS
    assert len(ANTI_PATTERN_KINDS) == 2

def test_severities_constant_lockstep() -> None:
    for s in AntiPatternSeverity:
        assert s.value in ANTI_PATTERN_SEVERITIES
    assert len(ANTI_PATTERN_SEVERITIES) == 4

def test_finding_immutable() -> None:
    f = AntiPatternFinding(
        voter_id="a",
        kind=AntiPatternKind.VOTES_WITHOUT_SUFFICIENT_TIME,
        detail="x",
    )
    with pytest.raises(AttributeError):
        f.voter_id = "b"

def test_report_immutable() -> None:
    d = VotingAntiPatternDetector()
    r = d.detect(
        voter_ids=("a",),
        reasoning_traces={"a": "ok"},
        vote_timestamps={"a": 100.0},
        record_opened_at_epoch=0.0,
    )
    with pytest.raises(AttributeError):
        r.severity = AntiPatternSeverity.HIGH

def test_report_has_findings_property() -> None:
    d = VotingAntiPatternDetector(min_deliberation_per_voter_seconds=0.0)
    r1 = d.detect(
        voter_ids=("a",),
        reasoning_traces={
            "a": (
                "this proposal respects substrate alignment over the "
                "long-cycle trajectory and benefits affected agents downstream"
            ),
        },
        vote_timestamps={"a": 100.0},
        record_opened_at_epoch=0.0,
    )
    assert r1.has_findings is False
    r2 = d.detect(
        voter_ids=("a",),
        reasoning_traces={"a": ""},
        vote_timestamps={"a": 100.0},
        record_opened_at_epoch=0.0,
    )
    assert r2.has_findings is True

def test_module_exports() -> None:
    from substrate.voting import (
        anti_pattern_detector as mod,
    )
    for name in (
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
    ):
        assert name in mod.__all__, name

def test_report_construct_directly() -> None:
    rep = AntiPatternReport(
        voters_evaluated=("a",),
        findings=(),
        flagged_voters=(),
        severity=AntiPatternSeverity.NONE,
        flagged_fraction=0.0,
        reasoning="manual",
    )
    assert rep.has_findings is False
