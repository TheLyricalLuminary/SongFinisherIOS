"""Section 20 data contracts.

These dataclasses mirror the spec's JSONC blocks field-for-field.  Two rules
are load-bearing and are enforced here rather than by convention:

*   ``feasibility_floor_s`` lives in ``CompatibilityReport`` and **not** in
    ``EnvelopeSequence`` — it depends on nucleus type, which is candidate
    specific (Section 20 note, Section 7 defect fix).
*   ``d_pre_max_s`` / ``d_post_max_s`` are DIAGNOSTIC ONLY.  They are carried on
    ``EnvelopeSlot`` for logging and are never read by a scoring function
    (Section 7, Section 24 checklist).  ``tests/test_diagnostics_not_scored.py``
    asserts both statically and behaviourally.

Every record carries ``engine_version`` (Section 15) and, where applicable,
``audio_id`` (Section 3): "Differing AudioID across runs on the same input
means the pipeline is broken."
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional, Sequence


@dataclass(frozen=True)
class CanonicalAudio:
    audio_id: str
    sample_rate: int
    n_samples: int
    source_path: str
    engine_version: str
    pcm: Sequence[float] = field(default=(), repr=False, compare=False)

    def to_record(self) -> dict:
        """The Section 20 record, without the PCM payload."""
        return {
            "audio_id": self.audio_id,
            "sample_rate": self.sample_rate,
            "n_samples": self.n_samples,
            "source_path": self.source_path,
            "engine_version": self.engine_version,
        }


@dataclass(frozen=True)
class Anchor:
    slot_index: int
    time_s: float
    sigma_s: float
    method: str
    supporting_event_ids: tuple[str, ...]
    rise_time_ms: float


@dataclass(frozen=True)
class AcousticEvent:
    id: str
    time_s: float
    salience: float
    rise_time_ms: float
    delta_s: Optional[float]
    matched_beat_index: Optional[int]


@dataclass(frozen=True)
class AcousticEvidence:
    """Identical schema for HEAR and ORACLE (Section 12, Section 20).

    ``shape()`` must consume both with zero branching on ``provenance`` — if it
    branches, the oracle is not a control.
    """

    audio_id: str
    engine_version: str
    provenance: str  # "HEAR" | "ORACLE"
    tempo_bpm: float
    beat_times_s: tuple[float, ...]
    slot_mask_id: str
    anchors: tuple[Anchor, ...]
    events: tuple[AcousticEvent, ...]


@dataclass(frozen=True)
class EnvelopeSlot:
    index: int
    interval_s: float                 # I_k, logged, never budgeted against
    interval_effective_s: float       # I_effective_k, the only budgeting quantity
    anchor: Anchor
    d_pre_max_s: float                # DIAGNOSTIC ONLY, not a score input
    d_post_max_s: float               # DIAGNOSTIC ONLY, not a score input
    metrical_strength: str            # from the authored mask, never from a detected downbeat
    uncertainty_anchor_sigma_s: float
    uncertainty_source: str
    derived_from_event_ids: tuple[str, ...]
    derived_from_beat_indices: tuple[int, ...]


@dataclass(frozen=True)
class EnvelopeSequence:
    audio_id: str
    engine_version: str
    provenance: str
    slot_mask_id: str
    slots: tuple[EnvelopeSlot, ...]


@dataclass(frozen=True)
class ReportSlot:
    index: int
    syllable: str
    phones: tuple[str, ...]
    stress: str
    d_pre_s: float
    d_nucleus_s: float
    d_post_s: float
    feasibility_floor_s: float        # candidate-specific: lives here, not in the envelope
    feasibility: str
    s_stress: float
    s_count: float
    s_anchor: float
    s_fit: float


@dataclass(frozen=True)
class CompatibilityReport:
    audio_id: str
    engine_version: str
    provenance: str
    candidate_id: str
    pair_id: Optional[str]
    context_id: Optional[str]
    pair_role: Optional[str]          # "X" | "Y"
    predicted_preferred: Optional[bool]   # pre-registered per trial
    pronunciation_variant_index: Optional[int]
    verdict: str                      # ACCEPT | REJECT_HARD | ABSTAIN_OOV
    score_b: float
    score_c: float
    total_consonant_duration_s: float  # load-match verification (tempo-scaled d(c))
    total_nominal_consonant_duration_s: float  # Section 11 check 4 uses d_nominal
    slots: tuple[ReportSlot, ...]


@dataclass(frozen=True)
class RankedEntry:
    candidate_id: str
    score: float
    tiebreak_applied: bool


@dataclass(frozen=True)
class RankedCandidateList:
    audio_id: str
    engine_version: str
    provenance: str
    condition: str                    # A | B | C | C_FLAT | C_SHUFFLED | C_ORACLE
    ranked: tuple[RankedEntry, ...]


def to_jsonable(obj) -> object:
    """Deterministic, ordering-stable serialisation for goldens and logs."""
    if hasattr(obj, "__dataclass_fields__"):
        if isinstance(obj, CanonicalAudio):
            return obj.to_record()
        return {k: to_jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: to_jsonable(obj[k]) for k in sorted(obj)}
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(v) for v in obj]
    if isinstance(obj, float):
        return obj
    return obj
