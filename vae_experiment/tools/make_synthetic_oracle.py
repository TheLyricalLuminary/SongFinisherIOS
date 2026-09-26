"""Emit oracle annotations for the synthetic clips from their known construction.

Covers F1 (click tracks) and the F2 pipeline-exercise stand-in.  Both are
synthesised, so their true beat phase and tempo are known exactly and the anchor
times follow from the mask by the same Section 5 formula the pipeline uses.

These are ground truth by construction, not annotation by ear.  They exist so
that the Section 12 / Section 16 HEAR-vs-oracle machinery is exercised and
measured against something genuinely independent of HEAR — nothing here reads
any HEAR output.  They are NOT a substitute for the F2 oracle, which requires two
human annotators and a third adjudicator.  See fixtures/F8_oracle/README.md.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from vae.canonical import ingest  # noqa: E402
from vae.slots import load_slot_masks  # noqa: E402

SOURCES = (
    ROOT / "fixtures" / "F1_click_tracks",
    ROOT / "fixtures" / "F2_SYNTH_pipeline_exercise",
)
OUT = ROOT / "fixtures" / "F8_oracle"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    masks = load_slot_masks()
    written = 0
    clips = [
        (source, clip)
        for source in SOURCES
        for clip in json.loads((source / "manifest.json").read_text())["clips"]
    ]
    for source, clip in clips:
        audio = ingest(source / clip["file"], "ORACLE_EMIT")
        bpm, phase, duration = clip["tempo_bpm"], clip["phase_s"], clip["duration_s"]
        eighth = (60.0 / bpm) / 2.0
        for mask in masks.masks:
            if phase + mask.positions[-1] * eighth > duration - 0.05:
                continue
            doc = {
                "audio_id": audio.audio_id,
                "clip_id": clip["clip_id"],
                "slot_mask_id": mask.mask_id,
                "tempo_bpm": bpm,
                "beat_times_s": clip["true_beat_times_s"],
                "anchor_times_s": [phase + p * eighth for p in mask.positions],
                # Ground truth by construction carries no annotator disagreement.
                "anchor_sigma_s": [0.0] * mask.slot_count,
                "annotation_source": "GROUND_TRUTH_BY_CONSTRUCTION",
                "annotator_ids": [],
                "adjudicated_slots": [],
                "not_a_substitute_for_f2_oracle": True,
                "source_fixture": source.name,
            }
            path = OUT / f"{audio.audio_id}.{mask.mask_id}.json"
            path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")
            written += 1
    print(f"wrote {written} ground-truth oracle annotation files to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
