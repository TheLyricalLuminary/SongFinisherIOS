"""Combine two independent annotations into the final F8 oracle files.

Section 12: two annotators independently mark beat positions AND per-slot anchor
times; disagreements greater than 20 ms are adjudicated by a third.  Both are
adjudicated on the same rule here.

This tool does not invent a resolution -- it reports every beat and every slot
that needs adjudication and refuses to write that clip's oracle file until a
third annotation supplies the value.  Marks that agree within 20 ms are averaged,
and the A/B spread is carried through as ``anchor_sigma_s`` so real annotator
uncertainty reaches ``I_effective`` (Section 6) instead of being thrown away.

Beats are paired BY INDEX, never combined as a set: one beat marked at 0.501 s by
one annotator and 0.503 s by the other is a single beat, and unioning the two
lists would fabricate a second one and corrupt the derived tempo.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from vae.intake import merge_annotations  # noqa: E402
from vae.oracle import ADJUDICATION_THRESHOLD_S  # noqa: E402
from vae.slots import load_slot_masks  # noqa: E402

ANNOTATIONS = ROOT / "fixtures" / "F8_oracle" / "annotations"
OUT_DIR = ROOT / "fixtures" / "F8_oracle"


def run(annotations_dir: Path, out_dir: Path, a: str, b: str, adjudicator: str) -> int:
    if not annotations_dir.exists() or not any(annotations_dir.glob("*.json")):
        print("No annotations found. Generate worksheets first:")
        print(f"  python3 tools/make_f8_worksheets.py --annotator {a}")
        print(f"  python3 tools/make_f8_worksheets.py --annotator {b}")
        print("then have two people fill them in independently, by ear, in a DAW.")
        return 2

    masks = load_slot_masks()
    suffix_a = f".{a}.json"
    pairs = sorted(annotations_dir.glob(f"*{suffix_a}"))
    if not pairs:
        print(f"No annotator-{a} files in {annotations_dir}.")
        return 2

    written, blocked = 0, []
    for path_a in pairs:
        stem = path_a.name[: -len(suffix_a)]
        path_b = annotations_dir / f"{stem}.{b}.json"
        if not path_b.exists():
            blocked.append((stem, f"missing annotator-{b} file"))
            continue

        doc_a = json.loads(path_a.read_text())
        doc_b = json.loads(path_b.read_text())
        try:
            mask = masks.by_id(doc_a.get("slot_mask_id", ""))
        except KeyError:
            blocked.append((stem, f"unknown slot mask {doc_a.get('slot_mask_id')!r}"))
            continue

        path_c = annotations_dir / f"{stem}.{adjudicator}.json"
        doc_c = json.loads(path_c.read_text()) if path_c.exists() else None

        merged = merge_annotations(doc_a, doc_b, doc_c, mask.slot_count)
        if merged.errors:
            blocked.append((stem, "; ".join(merged.errors)))
            continue
        if merged.needs_adjudication:
            blocked.append((stem, "needs adjudication (" + ", ".join(merged.needs_adjudication) + ")"))
            continue

        annotators = [a, b]
        if merged.adjudicated_slots or merged.adjudicated_beats:
            annotators.append(adjudicator)
        (out_dir / f"{stem}.json").write_text(json.dumps({
            "audio_id": doc_a["audio_id"],
            "clip_id": doc_a.get("clip_id", ""),
            "slot_mask_id": doc_a["slot_mask_id"],
            "tempo_bpm": merged.tempo_bpm,
            "beat_times_s": merged.beat_times_s,
            "anchor_times_s": merged.anchor_times_s,
            "anchor_sigma_s": merged.anchor_sigma_s,
            "annotation_source": "HUMAN_BY_EAR",
            "annotator_ids": annotators,
            "adjudicated_slots": merged.adjudicated_slots,
            "adjudicated_beats": merged.adjudicated_beats,
        }, indent=2, sort_keys=True) + "\n")
        written += 1

    print(f"F8: wrote {written} oracle file(s); {len(blocked)} blocked")
    for stem, reason in blocked:
        print(f"  BLOCKED {stem[:24]}...: {reason}")
    if blocked:
        print(f"\nA beat or slot differing by more than {1000 * ADJUDICATION_THRESHOLD_S:.0f} ms "
              f"needs a third annotator (Section 12). Generate their worksheet with:")
        print(f"  python3 tools/make_f8_worksheets.py --annotator {adjudicator}")
        return 2
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a", default="A", help="first annotator id")
    parser.add_argument("--b", default="B", help="second annotator id")
    parser.add_argument("--adjudicator", default="C", help="third annotator id")
    parser.add_argument("--annotations-dir", default=str(ANNOTATIONS))
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    args = parser.parse_args()
    return run(Path(args.annotations_dir), Path(args.out_dir),
               args.a, args.b, args.adjudicator)


if __name__ == "__main__":
    raise SystemExit(main())
