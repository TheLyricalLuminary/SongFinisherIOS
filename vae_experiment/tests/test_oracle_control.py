"""Section 12 oracle control and the Section 16 cross-cut anchor-delta table."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vae.constants import PROVENANCE_HEAR, PROVENANCE_ORACLE
from vae.errors import ContractError, FixtureUnpopulatedError
from vae.oracle import (
    anchor_deltas, load_oracle, oracle_evidence_from_doc, summarize_anchor_deltas,
)
from vae.pipeline import build_engine

ROOT = Path(__file__).resolve().parent.parent
F1_DIR = ROOT / "fixtures" / "F1_click_tracks"
CLIPS = json.loads((F1_DIR / "manifest.json").read_text())["clips"]


@pytest.fixture(scope="module")
def engine():
    return build_engine()


def test_oracle_produces_the_same_contract_as_hear(engine):
    clip = CLIPS[0]
    mask = engine.masks.by_id("M5_short_first_4")
    audio = engine.ingest(F1_DIR / clip["file"])
    hear_ev, _ = engine.hear_with_log(audio, mask)
    oracle_ev = load_oracle(audio.audio_id, mask, engine.version)
    assert type(oracle_ev) is type(hear_ev)
    assert oracle_ev.provenance == PROVENANCE_ORACLE
    assert hear_ev.provenance == PROVENANCE_HEAR
    assert len(oracle_ev.anchors) == len(hear_ev.anchors) == mask.slot_count
    assert oracle_ev.slot_mask_id == hear_ev.slot_mask_id


def test_missing_oracle_annotation_raises_and_names_what_is_required(engine):
    mask = engine.masks.by_id("M5_short_first_4")
    with pytest.raises(FixtureUnpopulatedError) as excinfo:
        load_oracle("no-such-audio-id", mask, engine.version)
    message = str(excinfo.value)
    assert "two independent human annotations" in message
    assert "adjudicated by a third" in message


def test_oracle_is_never_synthesised_from_hear(engine):
    """There is no code path that manufactures an oracle from HEAR output."""
    import inspect
    from vae import oracle as oracle_module
    source = inspect.getsource(oracle_module)
    assert "def hear" not in source
    assert "estimate_tempo" not in source


@pytest.mark.parametrize("clip", CLIPS, ids=lambda c: c["clip_id"])
def test_hear_vs_oracle_anchor_delta_is_computed_for_every_f1_clip(clip, engine):
    audio = engine.ingest(F1_DIR / clip["file"])
    eighth = (60.0 / clip["tempo_bpm"]) / 2.0
    for mask in engine.masks.masks:
        if clip["phase_s"] + mask.positions[-1] * eighth > clip["duration_s"] - 0.05:
            continue
        hear_ev, log = engine.hear_with_log(audio, mask)
        oracle_ev = load_oracle(audio.audio_id, mask, engine.version)
        deltas = anchor_deltas(hear_ev, oracle_ev)
        assert len(deltas) == mask.slot_count
        summary = summarize_anchor_deltas(deltas, log.tempo_bpm)
        assert summary.max_abs_delta_s < 0.0058
        assert not summary.excluded_for_beat_offset


def test_r1_whole_beat_offset_is_detected_and_excluded(engine):
    """Section 25 R1: a systematic offset >= one beat period excludes the clip."""
    import dataclasses
    clip = CLIPS[0]
    mask = engine.masks.by_id("M5_short_first_4")
    audio = engine.ingest(F1_DIR / clip["file"])
    hear_ev, log = engine.hear_with_log(audio, mask)
    oracle_ev = load_oracle(audio.audio_id, mask, engine.version)
    period = 60.0 / log.tempo_bpm
    shifted = dataclasses.replace(
        hear_ev,
        anchors=tuple(
            dataclasses.replace(a, time_s=a.time_s + period) for a in hear_ev.anchors
        ),
    )
    summary = summarize_anchor_deltas(anchor_deltas(shifted, oracle_ev), log.tempo_bpm)
    assert summary.excluded_for_beat_offset
    # Not exactly 1.0: the anchors carry their own error, which is the reason the
    # guard compares with one hop of slack rather than against the bare period.
    assert abs(summary.systematic_offset_beats - 1.0) < 0.01


def test_mismatched_audio_id_is_a_contract_error(engine):
    import dataclasses
    clip = CLIPS[0]
    mask = engine.masks.by_id("M5_short_first_4")
    audio = engine.ingest(F1_DIR / clip["file"])
    hear_ev, _ = engine.hear_with_log(audio, mask)
    oracle_ev = load_oracle(audio.audio_id, mask, engine.version)
    with pytest.raises(ContractError):
        anchor_deltas(hear_ev, dataclasses.replace(oracle_ev, audio_id="OTHER"))


def test_annotation_naming_a_different_mask_is_rejected(engine):
    mask = engine.masks.by_id("M5_short_first_4")
    doc = {"slot_mask_id": "M6_long_first_4", "tempo_bpm": 100.0,
           "beat_times_s": [0.0], "anchor_times_s": [0.0] * 4, "anchor_sigma_s": [0.0] * 4}
    with pytest.raises(ContractError):
        oracle_evidence_from_doc(doc, "AID", mask, "EV")
