"""F8 adjudication: enforce Section 12 and produce files the oracle branch loads.

The annotation payloads here are TEST INPUTS standing in for what two people
would produce by ear. They live in tmp_path and never reach fixtures/F8_oracle.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ADJUDICATE = ROOT / "tools" / "adjudicate_f8.py"

AUDIO_ID = "a" * 64
MASK_ID = "M5_short_first_4"


def _annotation(annotator, anchors, beats=(0.0, 0.5, 1.0, 1.5, 2.0)):
    return {
        "audio_id": AUDIO_ID, "clip_id": "F2_01", "slot_mask_id": MASK_ID,
        "annotator_id": annotator, "annotation_source": "HUMAN_BY_EAR",
        "beat_times_s": list(beats),
        "slots": [{"slot_index": i, "lattice_position_eighths": p,
                   "metrical_strength": "STRONG", "anchor_time_s": a}
                  for i, (p, a) in enumerate(zip((0, 1, 4, 5), anchors))],
    }


def _run(tmp_path, annotations):
    annotations_dir = tmp_path / "fixtures" / "F8_oracle" / "annotations"
    annotations_dir.mkdir(parents=True)
    for annotator, anchors in annotations.items():
        (annotations_dir / f"{AUDIO_ID}.{MASK_ID}.{annotator}.json").write_text(
            json.dumps(_annotation(annotator, anchors))
        )
    # Run the real tool against a temporary tree so fixtures are untouched.
    script = ADJUDICATE.read_text().replace(
        'ROOT = Path(__file__).resolve().parent.parent',
        f'ROOT = Path({str(ROOT)!r})\nOVERRIDE = Path({str(tmp_path)!r})',
    ).replace(
        'ANNOTATIONS = ROOT / "fixtures" / "F8_oracle" / "annotations"',
        'ANNOTATIONS = OVERRIDE / "fixtures" / "F8_oracle" / "annotations"',
    ).replace(
        'OUT_DIR = ROOT / "fixtures" / "F8_oracle"',
        'OUT_DIR = OVERRIDE / "fixtures" / "F8_oracle"',
    )
    runner = tmp_path / "adjudicate.py"
    runner.write_text(script)
    proc = subprocess.run([sys.executable, str(runner)], capture_output=True, text=True)
    return proc, tmp_path / "fixtures" / "F8_oracle" / f"{AUDIO_ID}.{MASK_ID}.json"


def test_close_annotations_are_averaged_and_spread_becomes_sigma(tmp_path):
    proc, out = _run(tmp_path, {"A": [0.100, 0.300, 1.100, 1.300],
                                "B": [0.110, 0.310, 1.090, 1.290]})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    doc = json.loads(out.read_text())
    assert doc["anchor_times_s"][0] == pytest.approx(0.105)
    assert doc["anchor_sigma_s"][0] == pytest.approx(0.005)   # spread is kept, not discarded
    assert doc["adjudicated_slots"] == []
    assert doc["annotation_source"] == "HUMAN_BY_EAR"


def test_disagreement_over_20ms_blocks_until_a_third_annotator(tmp_path):
    proc, out = _run(tmp_path, {"A": [0.100, 0.300, 1.100, 1.300],
                                "B": [0.100, 0.300, 1.100, 1.400]})   # 100 ms apart
    assert proc.returncode == 2
    assert "needs adjudication" in proc.stdout
    assert "slot 3 differs by 100.0 ms" in proc.stdout
    assert not out.exists(), "must not write an oracle file with an unresolved disagreement"


def test_adjudicator_value_is_taken_as_final(tmp_path):
    proc, out = _run(tmp_path, {"A": [0.100, 0.300, 1.100, 1.300],
                                "B": [0.100, 0.300, 1.100, 1.400],
                                "C": [0.100, 0.300, 1.100, 1.375]})
    assert proc.returncode == 0, proc.stdout + proc.stderr
    doc = json.loads(out.read_text())
    assert doc["anchor_times_s"][3] == pytest.approx(1.375)
    assert doc["adjudicated_slots"] == [3]
    assert "C" in doc["annotator_ids"]


def test_missing_anchor_blocks_rather_than_defaulting(tmp_path):
    proc, out = _run(tmp_path, {"A": [0.100, None, 1.100, 1.300],
                                "B": [0.100, 0.300, 1.100, 1.300]})
    assert proc.returncode == 2
    assert "no anchor_time_s" in proc.stdout
    assert not out.exists()


def test_output_loads_through_the_existing_oracle_contract(tmp_path):
    """The adjudicated file must satisfy the Section 20 AcousticEvidence contract."""
    from vae.oracle import oracle_evidence_from_doc
    from vae.slots import load_slot_masks

    proc, out = _run(tmp_path, {"A": [0.100, 0.300, 1.100, 1.300],
                                "B": [0.110, 0.310, 1.090, 1.290]})
    assert proc.returncode == 0
    mask = load_slot_masks().by_id(MASK_ID)
    evidence = oracle_evidence_from_doc(json.loads(out.read_text()), AUDIO_ID, mask, "EV")
    assert evidence.provenance == "ORACLE"
    assert len(evidence.anchors) == mask.slot_count
    assert evidence.anchors[0].sigma_s == pytest.approx(0.005)
