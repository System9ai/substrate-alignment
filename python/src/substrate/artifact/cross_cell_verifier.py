"""Cross-cell substrate audit verifier

Pure-logic primitive that ingests :class:`SubstrateAuditArtifact`
bundles from multiple cells (each produced via the
:class:`SubstrateAuditArtifact` primitive) and
produces a unified :class:`CrossCellVerificationReport` describing:

1. **Per-cell artifact verification**: runs
   :meth:`SubstrateAuditArtifact.verify` for each artifact with the
   optional HMAC secret looked up by ``cell_id``.
2. **Cross-cell observation overlap**: when the same
   ``decision_id`` appears in multiple cells' artifacts, both cells
   observed the same decision; this is substrate condition #2's
   symmetric-audit property operating across cells.
3. **Cross-cell inconsistency**: overlapping observations whose
   substrate context fields disagree are surfaced as findings
   graded LOW / MEDIUM / HIGH by which fields differ.

The primitive **observes**; it does not gate. Operators consume the
report to decide remediation (re-attestation, peer-audit escalation,
ledger reconciliation).

Substrate-alignment
===================

Per substrate condition #2: ``tamper-evident audit at every scale
must be **symmetric** (every agent observes and is observed)``. A
cell that produces a ledger but cannot have its observations cross-
checked by peer cells is operating asymmetrically: the audit chain
is write-only from that cell. This verifier is the **operational
form** of cross-cell symmetry: peers verify each other.

When two cells agree on a decision's substrate context, condition #2
is satisfied for that decision. When they disagree, the
inconsistency is surfaced as a finding so operators can investigate
(tampering, observation divergence, clock drift).

Pure logic
----------

* No DAO, no LLM, no network.
* Honest uncertainty: empty artifacts list returns an empty report
  with ``ok=True``; failures are surfaced rather than swallowed.
* Composition only: delegates artifact verification to the
  :class:`SubstrateAuditArtifact`. No re-implementation of the
  manifest / chain / HMAC checks.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from enum import Enum
from typing import (
    Final,
    Mapping,
    Optional,
    Sequence,
    Tuple,
)

from substrate.artifact.substrate_audit_artifact import (
    ArtifactVerification,
    SubstrateAuditArtifact,
)
from substrate.audit.substrate_trace import (
    SubstrateTraceRecord,
)

class CrossCellFindingSeverity(str, Enum):
    """Severity of a cross-cell inconsistency finding."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

_SEVERITY_ORDER: Final[Mapping[CrossCellFindingSeverity, int]] = {
    CrossCellFindingSeverity.NONE: 0,
    CrossCellFindingSeverity.LOW: 1,
    CrossCellFindingSeverity.MEDIUM: 2,
    CrossCellFindingSeverity.HIGH: 3,
}

def _max_severity(
    a: CrossCellFindingSeverity, b: CrossCellFindingSeverity,
) -> CrossCellFindingSeverity:
    """Return the higher of two severities."""
    return a if _SEVERITY_ORDER[a] >= _SEVERITY_ORDER[b] else b

# Fields whose mismatch across cells is high-severity (verdict-bearing).
DEFAULT_HIGH_SEVERITY_FIELDS: Final[frozenset[str]] = frozenset({
    "decision_kind",
    "permitted",
    "npg_verdict",
    "resistance_band",
    "sin_dominant",
    "sin_kinds_detected",
    "harness_intercept_kinds",
})

# Fields whose mismatch is medium-severity (context-bearing).
DEFAULT_MEDIUM_SEVERITY_FIELDS: Final[frozenset[str]] = frozenset({
    "sin_composite_confidence",
    "sin_pride_present",
    "epoch_seconds",
})

# Fields whose mismatch is low-severity (descriptive-only).
DEFAULT_LOW_SEVERITY_FIELDS: Final[frozenset[str]] = frozenset({
    "rationale",
})

@dataclass(frozen=True, slots=True)
class CellArtifactFinding:
    """Per-cell artifact verification result."""

    cell_id: str
    artifact_index: int
    verification: ArtifactVerification
    record_count: int

@dataclass(frozen=True, slots=True)
class CrossCellOverlap:
    """A decision_id observed by more than one cell."""

    decision_id: str
    cells: Tuple[str, ...]
    consistent: bool

@dataclass(frozen=True, slots=True)
class CrossCellInconsistency:
    """A decision_id with differing substrate context across cells."""

    decision_id: str
    cells: Tuple[str, ...]
    differing_fields: Tuple[str, ...]
    severity: CrossCellFindingSeverity
    detail: str

@dataclass(frozen=True, slots=True)
class CrossCellVerificationReport:  # pylint: disable=too-many-instance-attributes
    """Aggregate report over a batch of cell artifacts."""

    per_cell: Tuple[CellArtifactFinding, ...]
    overlaps: Tuple[CrossCellOverlap, ...]
    inconsistencies: Tuple[CrossCellInconsistency, ...]
    total_artifacts: int
    total_unique_decisions: int
    all_artifacts_valid: bool
    cross_cell_consistent: bool

    @property
    def ok(self) -> bool:
        """Top-level pass/fail: both artifacts valid AND no inconsistency."""
        return self.all_artifacts_valid and self.cross_cell_consistent

    @property
    def highest_severity(self) -> CrossCellFindingSeverity:
        """Highest severity across all inconsistencies (NONE if none)."""
        if not self.inconsistencies:
            return CrossCellFindingSeverity.NONE
        return max(
            (i.severity for i in self.inconsistencies),
            key=_SEVERITY_ORDER.__getitem__,
        )

class CrossCellAuditVerifier:  # pylint: disable=too-few-public-methods
    """Cross-cell substrate audit verifier."""

    def __init__(
        self,
        *,
        high_severity_fields: frozenset[str] = DEFAULT_HIGH_SEVERITY_FIELDS,
        medium_severity_fields: frozenset[str] = DEFAULT_MEDIUM_SEVERITY_FIELDS,
        low_severity_fields: frozenset[str] = DEFAULT_LOW_SEVERITY_FIELDS,
    ) -> None:
        overlap_h_m = high_severity_fields & medium_severity_fields
        overlap_h_l = high_severity_fields & low_severity_fields
        overlap_m_l = medium_severity_fields & low_severity_fields
        if overlap_h_m or overlap_h_l or overlap_m_l:
            raise ValueError(
                "severity field sets must be disjoint"
            )
        self._high = high_severity_fields
        self._medium = medium_severity_fields
        self._low = low_severity_fields

    def verify(
        self,
        *,
        artifacts: Sequence[SubstrateAuditArtifact],
        hmac_secrets: Optional[Mapping[str, bytes]] = None,
    ) -> CrossCellVerificationReport:
        """Run cross-cell verification over a batch of artifacts."""
        secrets: Mapping[str, bytes] = hmac_secrets or {}

        per_cell = self._verify_each(artifacts, secrets)
        all_valid = all(c.verification.ok for c in per_cell)

        decision_index = self._build_decision_index(artifacts)
        overlaps, inconsistencies = self._classify_overlaps(decision_index)

        return CrossCellVerificationReport(
            per_cell=per_cell,
            overlaps=overlaps,
            inconsistencies=inconsistencies,
            total_artifacts=len(artifacts),
            total_unique_decisions=len(decision_index),
            all_artifacts_valid=all_valid,
            cross_cell_consistent=not inconsistencies,
        )

    @staticmethod
    def _verify_each(
        artifacts: Sequence[SubstrateAuditArtifact],
        secrets: Mapping[str, bytes],
    ) -> Tuple[CellArtifactFinding, ...]:
        results: list[CellArtifactFinding] = []
        for index, artifact in enumerate(artifacts):
            secret = secrets.get(artifact.manifest.cell_id)
            verification = artifact.verify(hmac_secret=secret)
            results.append(
                CellArtifactFinding(
                    cell_id=artifact.manifest.cell_id,
                    artifact_index=index,
                    verification=verification,
                    record_count=artifact.manifest.record_count,
                )
            )
        return tuple(results)

    @staticmethod
    def _build_decision_index(
        artifacts: Sequence[SubstrateAuditArtifact],
    ) -> dict[str, list[tuple[str, SubstrateTraceRecord]]]:
        index: dict[str, list[tuple[str, SubstrateTraceRecord]]] = (
            defaultdict(list)
        )
        for artifact in artifacts:
            for record in artifact.records:
                index[record.decision_id].append(
                    (artifact.manifest.cell_id, record)
                )
        return index

    def _classify_overlaps(
        self,
        index: Mapping[str, list[tuple[str, SubstrateTraceRecord]]],
    ) -> Tuple[
        Tuple[CrossCellOverlap, ...],
        Tuple[CrossCellInconsistency, ...],
    ]:
        overlaps: list[CrossCellOverlap] = []
        inconsistencies: list[CrossCellInconsistency] = []
        for decision_id, entries in index.items():
            cells_in_overlap = self._unique_cells(entries)
            if len(cells_in_overlap) < 2:
                continue
            differing = self._differing_fields(entries)
            consistent = not differing
            overlaps.append(
                CrossCellOverlap(
                    decision_id=decision_id,
                    cells=cells_in_overlap,
                    consistent=consistent,
                )
            )
            if not consistent:
                severity = self._severity_for(differing)
                inconsistencies.append(
                    CrossCellInconsistency(
                        decision_id=decision_id,
                        cells=cells_in_overlap,
                        differing_fields=tuple(sorted(differing)),
                        severity=severity,
                        detail=(
                            f"cells {cells_in_overlap} disagree on "
                            f"{tuple(sorted(differing))} for decision_id="
                            f"{decision_id!r}"
                        ),
                    )
                )
        return tuple(overlaps), tuple(inconsistencies)

    @staticmethod
    def _unique_cells(
        entries: Sequence[tuple[str, SubstrateTraceRecord]],
    ) -> Tuple[str, ...]:
        seen: set[str] = set()
        ordered: list[str] = []
        for cell_id, _ in entries:
            if cell_id not in seen:
                seen.add(cell_id)
                ordered.append(cell_id)
        return tuple(ordered)

    @staticmethod
    def _differing_fields(
        entries: Sequence[tuple[str, SubstrateTraceRecord]],
    ) -> set[str]:
        differing: set[str] = set()
        first_record = entries[0][1]
        for _, record in entries[1:]:
            for field_name in _COMPARED_FIELDS:
                if getattr(record, field_name) != getattr(
                    first_record, field_name,
                ):
                    differing.add(field_name)
        return differing

    def _severity_for(self, fields: set[str]) -> CrossCellFindingSeverity:
        severity = CrossCellFindingSeverity.NONE
        for name in fields:
            if name in self._high:
                severity = _max_severity(
                    severity, CrossCellFindingSeverity.HIGH,
                )
            elif name in self._medium:
                severity = _max_severity(
                    severity, CrossCellFindingSeverity.MEDIUM,
                )
            elif name in self._low:
                severity = _max_severity(
                    severity, CrossCellFindingSeverity.LOW,
                )
            else:
                # Unclassified field: treat as MEDIUM by default.
                severity = _max_severity(
                    severity, CrossCellFindingSeverity.MEDIUM,
                )
        return severity

# The record fields the verifier compares for cross-cell consistency.
# Excludes chain-position fields (sequence, prev_hash, record_hash)
# because those are expected to differ across cells with independent
# chains.
_COMPARED_FIELDS: Final[Tuple[str, ...]] = (
    "decision_kind",
    "permitted",
    "rationale",
    "npg_verdict",
    "resistance_band",
    "sin_dominant",
    "sin_composite_confidence",
    "sin_pride_present",
    "sin_kinds_detected",
    "harness_intercept_kinds",
    "epoch_seconds",
)

__all__ = [
    "CellArtifactFinding",
    "CrossCellAuditVerifier",
    "CrossCellFindingSeverity",
    "CrossCellInconsistency",
    "CrossCellOverlap",
    "CrossCellVerificationReport",
    "DEFAULT_HIGH_SEVERITY_FIELDS",
    "DEFAULT_LOW_SEVERITY_FIELDS",
    "DEFAULT_MEDIUM_SEVERITY_FIELDS",
]
