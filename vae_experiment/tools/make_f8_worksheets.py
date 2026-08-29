"""Emit blank per-clip annotation worksheets for a named annotator.

Worksheets are generated from the F2 manifest, so they exist only for clips that
actually passed Section 2 admission.  They carry no anchor times: the annotator
supplies every one by ear (see fixtures/F8_oracle/ANNOTATOR_INSTRUCTIONS.md).

Deliberately absent: any HEAR-derived hint. The worksheet does not show detected
onsets, the beat grid, or the pipeline's anchors. An annotator shown the answer
is not an independent measurement, and the Section 12 control would be void.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from vae.slots import load_slot_masks  # noqa: E402

F2_MANIFEST = ROOT / "fixtures" / "F2_clips" / "manifest.json"
OUT_DIR = ROOT / "fixtures" / "F8_oracle" / "annotations"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotator", required=True,
                        help="annotator id, e.g. A, B, or the adjudicator's id")
    args = parser.parse_args()

    if not F2_MANIFEST.exists():
        print("No F2 manifest. Import real accompaniment clips first:")
        print("  python3 tools/import_f2.py")
        print("Worksheets are only generated for clips that passed Section 2 admission.")
        return 2

    manifest = json.loads(F2_MANIFEST.read_text())
    clips = manifest.get("clips", [])
    if not clips:
        print("F2 manifest contains no accepted clips; nothing to annotate.")
        return 2

    masks = load_slot_masks()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    written = 0
    for clip in clips:
        mask = masks.by_id(clip["slot_mask_id"])
        path = OUT_DIR / f"{clip['audio_id']}.{mask.mask_id}.{args.annotator}.json"
        if path.exists():
            print(f"  skipping existing {path.name}")
            continue
        path.write_text(json.dumps({
            "audio_id": clip["audio_id"],
            "clip_id": clip["clip_id"],
            "slot_mask_id": mask.mask_id,
            "annotator_id": args.annotator,
            "annotation_source": "HUMAN_BY_EAR",
            "instructions": (
                "anchor_time_s is where a sung VOWEL NUCLEUS would perceptually land -- "
                "not the onset transient and not the grid position. Do not snap to a grid. "
                "Do not consult pipeline output or another annotator."
            ),
            "beat_times_s": [],
            "slots": [
                {"slot_index": i,
                 "lattice_position_eighths": position,
                 "metrical_strength": mask.metrical_strength[i],
                 "anchor_time_s": None}
                for i, position in enumerate(mask.positions)
            ],
        }, indent=2) + "\n")
        written += 1

    print(f"wrote {written} worksheet(s) for annotator {args.annotator!r} to "
          f"{OUT_DIR.relative_to(ROOT)}")
    print("Each needs beat_times_s filled in and every slot's anchor_time_s set.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
