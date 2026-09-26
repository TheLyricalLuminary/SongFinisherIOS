"""Section 23 step 2 gate: anchor error < 5.8 ms on all F1.

Nothing proceeds past step 2 unless this holds, so it is a test rather than a
report line.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vae.constants import HOP_SECONDS
from vae.pipeline import build_engine

ROOT = Path(__file__).resolve().parent.parent
F1_DIR = ROOT / "fixtures" / "F1_click_tracks"
GATE_S = 0.0058

CLIPS = json.loads((F1_DIR / "manifest.json").read_text())["clips"]


@pytest.fixture(scope="module")
def engine():
    return build_engine()


@pytest.mark.parametrize("clip", CLIPS, ids=lambda c: c["clip_id"])
def test_anchor_error_is_under_the_gate_for_every_mask(clip, engine):
    audio = engine.ingest(F1_DIR / clip["file"])
    eighth = (60.0 / clip["tempo_bpm"]) / 2.0
    evaluated = 0
    for mask in engine.masks.masks:
        if clip["phase_s"] + mask.positions[-1] * eighth > clip["duration_s"] - 0.05:
            continue
        evidence, _ = engine.hear_with_log(audio, mask)
        for anchor, position in zip(evidence.anchors, mask.positions):
            truth = clip["phase_s"] + position * eighth
            error = abs(anchor.time_s - truth)
            assert error < GATE_S, (
                f"{clip['clip_id']}/{mask.mask_id} slot {anchor.slot_index}: "
                f"{1000 * error:.3f} ms >= {1000 * GATE_S} ms"
            )
            assert error < HOP_SECONDS      # Section 22 failure #1: within one hop
        evaluated += 1
    assert evaluated > 0


@pytest.mark.parametrize("clip", CLIPS, ids=lambda c: c["clip_id"])
def test_tempo_is_recovered_within_a_tenth_of_a_percent(clip, engine):
    audio = engine.ingest(F1_DIR / clip["file"])
    _, log = engine.hear_with_log(audio, engine.masks.by_id("M1_quarters_4"))
    assert abs(log.tempo_bpm - clip["tempo_bpm"]) / clip["tempo_bpm"] < 1e-3
