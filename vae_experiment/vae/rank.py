"""RANK — Section 10 verdicts into a ranked list, Section 15 tie discipline.

    rank(CompatibilityReport[], mode) -> RankedCandidateList

``mode`` is the condition (Section 1).  It selects **which score column is
read**, not which scorer ran: B reads ``score_b``, every C variant reads
``score_c``.  The envelope that produced the report is what makes C_FLAT,
C_SHUFFLED and C_ORACLE different from C — no condition flag reaches the scorer.

Ties break lexicographically on ``candidate_id`` — never on iteration or
hash-map order (Section 15).  ``REJECT_HARD`` candidates are excluded from
ranking (Section 8); ``ABSTAIN_OOV`` candidates are excluded and logged
(Section 9).
"""

from __future__ import annotations

from .config import Config
from .constants import (
    CONDITIONS,
    VERDICT_ABSTAIN_OOV,
    VERDICT_ACCEPT,
    VERDICT_REJECT_HARD,
)
from .contracts import CompatibilityReport, RankedCandidateList, RankedEntry
from .errors import ContractError

B_CONDITIONS = ("B",)
C_CONDITIONS = ("A", "C", "C_FLAT", "C_SHUFFLED", "C_ORACLE")


def score_for(report: CompatibilityReport, condition: str) -> float:
    """B is count + timing + stress only.  Everything else reads Score_C.

    Condition A is a manipulation check on *candidates* (deliberately mismatched
    syllable count and stress), not on the envelope, so it is scored like C.
    """
    if condition not in CONDITIONS:
        raise ContractError(f"unknown condition {condition!r}")
    return report.score_b if condition in B_CONDITIONS else report.score_c


def rank(
    reports: tuple[CompatibilityReport, ...] | list[CompatibilityReport],
    condition: str,
    config: Config,
) -> RankedCandidateList:
    if not reports:
        raise ContractError("rank: no reports")
    audio_ids = {r.audio_id for r in reports}
    if len(audio_ids) != 1:
        raise ContractError(f"rank: reports span {len(audio_ids)} audio_ids")
    provenances = {r.provenance for r in reports}
    if len(provenances) != 1:
        raise ContractError(f"rank: reports span {len(provenances)} provenances")

    rankable = [r for r in reports if r.verdict == VERDICT_ACCEPT]

    # Sort by descending score, then ascending candidate_id.  A tiebreak is
    # "applied" when a neighbour shares the score within epsilon_num.
    ordered = sorted(rankable, key=lambda r: (-score_for(r, condition), r.candidate_id))
    entries: list[RankedEntry] = []
    for i, report in enumerate(ordered):
        score = score_for(report, condition)
        tied = any(
            abs(score - score_for(other, condition)) <= config.epsilon_num
            for j, other in enumerate(ordered)
            if j != i
        )
        entries.append(
            RankedEntry(candidate_id=report.candidate_id, score=float(score), tiebreak_applied=tied)
        )

    return RankedCandidateList(
        audio_id=reports[0].audio_id,
        engine_version=reports[0].engine_version,
        provenance=reports[0].provenance,
        condition=condition,
        ranked=tuple(entries),
    )


def excluded(reports) -> tuple[tuple[str, str], ...]:
    """(candidate_id, verdict) for everything rank() dropped.  Logged, not hidden."""
    return tuple(
        sorted(
            (r.candidate_id, r.verdict)
            for r in reports
            if r.verdict in (VERDICT_REJECT_HARD, VERDICT_ABSTAIN_OOV)
        )
    )
