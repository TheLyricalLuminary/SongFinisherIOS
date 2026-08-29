"""F8 adjudication: Section 12 on BOTH beats and anchors.

The annotation payloads here are TEST INPUTS standing in for what two people
would produce by ear. They never reach fixtures/F8_oracle.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vae.intake import merge_annotations, validate_annotation  # noqa: E402

AUDIO_ID = "a" * 64
MASK_ID = "M5_short_first_4"
SLOTS = 4

# One steady 120 BPM bar: five beats half a second apart.
BEATS_A = [0.500, 1.000, 1.500, 2.000, 2.500]
ANCHORS_A = [0.500, 0.750, 1.500, 1.750]


def _doc(annotator, beats=None, anchors=None, **overrides):
    doc = {
        "audio_id": AUDIO_ID, "clip_id": "F2_01", "slot_mask_id": MASK_ID,
        "annotator_id": annotator, "annotation_source": "HUMAN_BY_EAR",
        "beat_times_s": list(BEATS_A if beats is None else beats),
        "slots": [
            {"slot_index": i, "lattice_position_eighths": p, "metrical_strength": "STRONG",
             "anchor_time_s": a}
            for i, (p, a) in enumerate(zip((0, 1, 4, 5), ANCHORS_A if anchors is None else anchors))
        ],
    }
    doc.update(overrides)
    return doc


# --- the reported bug ------------------------------------------------------- #

def test_slightly_offset_beat_marks_do_not_double_the_beat_count():
    """The reported defect: a set union turned one beat into two.

    Every beat is marked a few ms apart by the two annotators. That is one beat
    each, not two, and the resolved sequence must have the same length as either
    annotator's.
    """
    offset = [b + 0.003 for b in BEATS_A]           # 3 ms later, well inside 20 ms
    merged = merge_annotations(_doc("A"), _doc("B", beats=offset), None, SLOTS)
    assert merged.ok, merged.errors + merged.needs_adjudication
    assert len(merged.beat_times_s) == len(BEATS_A)
    assert merged.beat_times_s[0] == pytest.approx(0.5015)
    assert len(set(merged.beat_times_s)) == len(BEATS_A)


def test_tempo_is_derived_from_the_resolved_beat_sequence():
    offset = [b + 0.003 for b in BEATS_A]
    merged = merge_annotations(_doc("A"), _doc("B", beats=offset), None, SLOTS)
    assert merged.tempo_bpm == pytest.approx(120.0)


def test_doubled_beats_would_have_halved_the_tempo():
    """Guards the fix by showing what the old union produced."""
    union = sorted(set(BEATS_A) | {b + 0.003 for b in BEATS_A})
    assert len(union) == 2 * len(BEATS_A)           # the old behaviour
    bad_tempo = 60.0 * (len(union) - 1) / (union[-1] - union[0])
    assert bad_tempo > 200.0                        # nowhere near the true 120 BPM


# --- beat adjudication ------------------------------------------------------ #

def test_beat_disagreement_over_20ms_blocks_until_adjudicated():
    beats = list(BEATS_A)
    beats[2] += 0.050
    merged = merge_annotations(_doc("A"), _doc("B", beats=beats), None, SLOTS)
    assert not merged.ok
    assert any("beat 2 differs by 50.0 ms" in n for n in merged.needs_adjudication)


def test_adjudicator_resolves_a_beat_disagreement():
    beats = list(BEATS_A)
    beats[2] += 0.050
    third = list(BEATS_A)
    third[2] = 1.530
    merged = merge_annotations(_doc("A"), _doc("B", beats=beats), _doc("C", beats=third), SLOTS)
    assert merged.ok, merged.errors + merged.needs_adjudication
    assert merged.beat_times_s[2] == pytest.approx(1.530)
    assert merged.adjudicated_beats == [2]


def test_differing_beat_counts_cannot_be_paired():
    merged = merge_annotations(_doc("A"), _doc("B", beats=BEATS_A[:-1]), None, SLOTS)
    assert any("different numbers of beats" in e for e in merged.errors)


def test_non_monotonic_beats_are_rejected():
    merged = merge_annotations(_doc("A", beats=[0.5, 1.5, 1.0]),
                               _doc("B", beats=[0.5, 1.5, 1.0]), None, SLOTS)
    assert any("strictly increasing" in e for e in merged.errors)


# --- anchor adjudication ---------------------------------------------------- #

def test_close_anchors_are_averaged_and_spread_becomes_sigma():
    anchors = [a + 0.010 for a in ANCHORS_A]
    merged = merge_annotations(_doc("A"), _doc("B", anchors=anchors), None, SLOTS)
    assert merged.ok
    assert merged.anchor_times_s[0] == pytest.approx(0.505)
    assert merged.anchor_sigma_s[0] == pytest.approx(0.005)


def test_anchor_disagreement_over_20ms_blocks():
    anchors = list(ANCHORS_A)
    anchors[3] += 0.100
    merged = merge_annotations(_doc("A"), _doc("B", anchors=anchors), None, SLOTS)
    assert not merged.ok
    assert any("slot 3 differs by 100.0 ms" in n for n in merged.needs_adjudication)


def test_adjudicator_value_is_final_for_anchors():
    anchors = list(ANCHORS_A)
    anchors[3] += 0.100
    third = list(ANCHORS_A)
    third[3] = 1.775
    merged = merge_annotations(_doc("A"), _doc("B", anchors=anchors),
                               _doc("C", anchors=third), SLOTS)
    assert merged.ok
    assert merged.anchor_times_s[3] == pytest.approx(1.775)
    assert merged.adjudicated_slots == [3]


# --- metadata and slot-index validation ------------------------------------- #

def test_missing_anchor_blocks_rather_than_defaulting():
    doc = _doc("B")
    doc["slots"][1]["anchor_time_s"] = None
    merged = merge_annotations(_doc("A"), doc, None, SLOTS)
    assert any("no anchor_time_s" in e for e in merged.errors)


def test_out_of_order_slot_indices_are_rejected():
    doc = _doc("B")
    doc["slots"] = list(reversed(doc["slots"]))
    assert any("slot_index must be" in e for e in merge_annotations(_doc("A"), doc, None, SLOTS).errors)


def test_wrong_slot_count_is_rejected():
    doc = _doc("B")
    doc["slots"] = doc["slots"][:3]
    assert any("3 slots annotated" in e for e in merge_annotations(_doc("A"), doc, None, SLOTS).errors)


def test_annotations_of_different_clips_are_never_merged():
    merged = merge_annotations(_doc("A"), _doc("B", audio_id="b" * 64), None, SLOTS)
    assert any("disagree on audio_id" in e for e in merged.errors)


def test_annotations_of_different_masks_are_never_merged():
    merged = merge_annotations(_doc("A"), _doc("B", slot_mask_id="M6_long_first_4"), None, SLOTS)
    assert any("disagree on slot_mask_id" in e for e in merged.errors)


def test_missing_metadata_is_rejected():
    assert any("missing audio_id" in e
               for e in validate_annotation(_doc("A", audio_id=""), SLOTS, "annotator A"))


def test_empty_beat_list_is_rejected():
    assert any("beat_times_s is empty" in e
               for e in validate_annotation(_doc("A", beat_times_s=[]), SLOTS, "annotator A"))


# --- end to end through the CLI --------------------------------------------- #

def _write(dir_path, annotator, doc):
    dir_path.mkdir(parents=True, exist_ok=True)
    (dir_path / f"{AUDIO_ID}.{MASK_ID}.{annotator}.json").write_text(json.dumps(doc))


def _cli(tmp_path, docs):
    annotations, out = tmp_path / "annotations", tmp_path / "out"
    out.mkdir(parents=True, exist_ok=True)
    for annotator, doc in docs.items():
        _write(annotations, annotator, doc)
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "adjudicate_f8.py"),
         "--annotations-dir", str(annotations), "--out-dir", str(out)],
        capture_output=True, text=True,
    )
    return proc, out / f"{AUDIO_ID}.{MASK_ID}.json"


def test_cli_writes_a_file_the_oracle_contract_accepts(tmp_path):
    from vae.oracle import oracle_evidence_from_doc
    from vae.slots import load_slot_masks

    proc, out = _cli(tmp_path, {"A": _doc("A"),
                                "B": _doc("B", beats=[b + 0.003 for b in BEATS_A])})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    doc = json.loads(out.read_text())
    assert len(doc["beat_times_s"]) == len(BEATS_A)
    assert doc["tempo_bpm"] == pytest.approx(120.0)

    mask = load_slot_masks().by_id(MASK_ID)
    evidence = oracle_evidence_from_doc(doc, AUDIO_ID, mask, "EV")
    assert evidence.provenance == "ORACLE"
    assert len(evidence.anchors) == mask.slot_count


def test_cli_blocks_on_an_unresolved_beat_disagreement(tmp_path):
    beats = list(BEATS_A)
    beats[1] += 0.080
    proc, out = _cli(tmp_path, {"A": _doc("A"), "B": _doc("B", beats=beats)})
    assert proc.returncode == 2
    assert "needs adjudication" in proc.stdout
    assert not out.exists()
