"""Section 12 — oracle-timing control.

Two annotators independently mark, per clip, beat positions and per-slot anchor
times by ear in a DAW against the authored slot mask; disagreements > 20 ms are
adjudicated by a third.  The output conforms to the **same ``AcousticEvidence``
contract** as HEAR, including ``anchors[]`` (v1.0 defect 5).

This module only *loads* an annotation file and converts it to that contract.
It deliberately cannot synthesise an annotation: an oracle the pipeline invented
would not be a control.  Where F8 is unpopulated the loader raises rather than
falling back — see ``fixtures/F8_oracle/README.md``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .constants import HOP_SECONDS, METHOD_ONSET_SUPPORTED, PROVENANCE_ORACLE
from .contracts import AcousticEvent, AcousticEvidence, Anchor, EnvelopeSequence
from .errors import ContractError, FixtureUnpopulatedError
from .slots import SlotMask

DEFAULT_ORACLE_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "F8_oracle"

ADJUDICATION_THRESHOLD_S = 0.020  # Section 12: disagreements > 20 ms go to a third annotator


def load_oracle(
    audio_id: str, mask: SlotMask, engine_version: str, oracle_dir: Path | str | None = None
) -> AcousticEvidence:
    """``load_oracle(audio_id, SlotMask) -> AcousticEvidence`` (Section 21)."""
    directory = Path(oracle_dir) if oracle_dir is not None else DEFAULT_ORACLE_DIR
    path = directory / f"{audio_id}.{mask.mask_id}.json"
    if not path.exists():
        raise FixtureUnpopulatedError(
            f"F8 oracle annotation for audio_id={audio_id[:16]}... mask={mask.mask_id}",
            "two independent human annotations of beat positions and per-slot anchor "
            "times, marked by ear in a DAW against the authored slot mask, with "
            "disagreements > 20 ms adjudicated by a third annotator (Section 12)",
        )
    doc = json.loads(path.read_bytes().decode("utf-8"))
    return oracle_evidence_from_doc(doc, audio_id, mask, engine_version)


def oracle_evidence_from_doc(
    doc: dict, audio_id: str, mask: SlotMask, engine_version: str
) -> AcousticEvidence:
    if doc.get("slot_mask_id") != mask.mask_id:
        raise ContractError(
            f"annotation names slot mask {doc.get('slot_mask_id')!r}, expected {mask.mask_id!r}"
        )
    anchor_times = [float(t) for t in doc["anchor_times_s"]]
    if len(anchor_times) != mask.slot_count:
        raise ContractError(
            f"{mask.mask_id}: {mask.slot_count} slots but {len(anchor_times)} annotated anchors"
        )
    sigmas = [float(s) for s in doc["anchor_sigma_s"]]
    beats = tuple(float(t) for t in doc["beat_times_s"])

    events = tuple(
        AcousticEvent(
            id=f"O{i:04d}",
            time_s=float(t),
            salience=1.0,
            rise_time_ms=0.0,
            delta_s=0.0,
            matched_beat_index=i,
        )
        for i, t in enumerate(beats)
    )
    anchors = tuple(
        Anchor(
            slot_index=i,
            time_s=anchor_times[i],
            sigma_s=sigmas[i],
            method=METHOD_ONSET_SUPPORTED,
            supporting_event_ids=(),
            rise_time_ms=0.0,
        )
        for i in range(mask.slot_count)
    )
    return AcousticEvidence(
        audio_id=audio_id,
        engine_version=engine_version,
        provenance=PROVENANCE_ORACLE,
        tempo_bpm=float(doc["tempo_bpm"]),
        beat_times_s=beats,
        slot_mask_id=mask.mask_id,
        anchors=anchors,
        events=events,
    )


# --------------------------------------------------------------------------- #
# Section 12 / Section 16 cross-cut: the HEAR-vs-oracle anchor delta table
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class AnchorDelta:
    audio_id: str
    slot_mask_id: str
    slot_index: int
    hear_time_s: float
    oracle_time_s: float
    delta_s: float
    hear_method: str


@dataclass(frozen=True)
class AnchorDeltaSummary:
    audio_id: str
    slot_mask_id: str
    n_slots: int
    mean_abs_delta_s: float
    max_abs_delta_s: float
    median_abs_delta_s: float
    systematic_offset_s: float          # signed mean; a whole-beat value is risk R1
    beat_period_s: float
    systematic_offset_beats: float
    excluded_for_beat_offset: bool      # Section 25 R1 guard


def anchor_deltas(hear: AcousticEvidence, oracle: AcousticEvidence) -> tuple[AnchorDelta, ...]:
    """Paired HEAR-vs-oracle anchor delta per slot (Section 16 cross-cut).

    "This table is what distinguishes 'our DSP was wrong' from 'the hypothesis is
    wrong.'"  It must exist before any human data collection.
    """
    if hear.audio_id != oracle.audio_id:
        raise ContractError("anchor_deltas: audio_id mismatch")
    if hear.slot_mask_id != oracle.slot_mask_id:
        raise ContractError("anchor_deltas: slot_mask_id mismatch")
    return tuple(
        AnchorDelta(
            audio_id=hear.audio_id,
            slot_mask_id=hear.slot_mask_id,
            slot_index=h.slot_index,
            hear_time_s=h.time_s,
            oracle_time_s=o.time_s,
            delta_s=h.time_s - o.time_s,
            hear_method=h.method,
        )
        for h, o in zip(hear.anchors, oracle.anchors)
    )


def summarize_anchor_deltas(
    deltas: tuple[AnchorDelta, ...], tempo_bpm: float
) -> AnchorDeltaSummary:
    """Per-clip distribution plus the Section 25 R1 whole-beat-offset guard."""
    if not deltas:
        raise ContractError("summarize_anchor_deltas: empty")
    values = [d.delta_s for d in deltas]
    absolute = sorted(abs(v) for v in values)
    mid = len(absolute) // 2
    median = absolute[mid] if len(absolute) % 2 else (absolute[mid - 1] + absolute[mid]) / 2.0
    signed_mean = sum(values) / len(values)
    beat_period = 60.0 / tempo_bpm
    offset_beats = signed_mean / beat_period
    return AnchorDeltaSummary(
        audio_id=deltas[0].audio_id,
        slot_mask_id=deltas[0].slot_mask_id,
        n_slots=len(deltas),
        mean_abs_delta_s=sum(absolute) / len(absolute),
        max_abs_delta_s=absolute[-1],
        median_abs_delta_s=median,
        systematic_offset_s=signed_mean,
        beat_period_s=beat_period,
        systematic_offset_beats=offset_beats,
        # R1: "Any clip showing a systematic offset >= one beat period is
        # excluded before the human phase, not corrected."
        #
        # Compared with one analysis hop of slack.  A real one-beat phase slip
        # lands *near* the beat period, never exactly on it, because the anchors
        # themselves carry measurement error; a bare >= would let the guard miss
        # precisely the failure it exists to catch.  Slack in this direction is
        # the safe one: R1 excludes rather than corrects.
        excluded_for_beat_offset=abs(signed_mean) + HOP_SECONDS >= beat_period,
    )


def envelope_pair_delta(hear_env: EnvelopeSequence, oracle_env: EnvelopeSequence) -> tuple[float, ...]:
    """Per-slot |I_effective| difference between the two provenances, for logging."""
    return tuple(
        abs(h.interval_effective_s - o.interval_effective_s)
        for h, o in zip(hear_env.slots, oracle_env.slots)
    )
