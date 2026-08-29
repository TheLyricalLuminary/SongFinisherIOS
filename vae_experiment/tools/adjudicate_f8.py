"""Combine two independent annotations into the final F8 oracle files.

Section 12: disagreements greater than 20 ms are adjudicated by a third
annotator.  This tool does not invent a resolution -- it reports every slot that
needs adjudication and refuses to write that clip's oracle file until a third
annotation supplies the value.

Slots that agree within 20 ms are averaged, and the A/B spread is carried through
as ``anchor_sigma_s`` so real annotator uncertainty reaches ``I_effective``
(Section 6) instead of being thrown away.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from vae.oracle import ADJUDICATION_THRESHOLD_S  # noqa: E402

ANNOTATIONS = ROOT / "fixtures" / "F8_oracle" / "annotations"
OUT_DIR = ROOT / "fixtures" / "F8_oracle"


def _load(path: Path) -> dict:
    doc = json.loads(path.read_text())
    missing = [s["slot_index"] for s in doc["slots"] if s.get("anchor_time_s") is None]
    if missing:
        raise ValueError(f"{path.name}: slots {missing} have no anchor_time_s")
    if not doc.get("beat_times_s"):
        raise ValueError(f"{path.name}: beat_times_s is empty")
    return doc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a", default="A", help="first annotator id")
    parser.add_argument("--b", default="B", help="second annotator id")
    parser.add_argument("--adjudicator", default="C", help="third annotator id")
    args = parser.parse_args()

    if not ANNOTATIONS.exists() or not any(ANNOTATIONS.glob("*.json")):
        print("No annotations found. Generate worksheets first:")
        print(f"  python3 tools/make_f8_worksheets.py --annotator {args.a}")
        print(f"  python3 tools/make_f8_worksheets.py --annotator {args.b}")
        print("then have two people fill them in independently, by ear, in a DAW.")
        return 2

    suffix_a = f".{args.a}.json"
    pairs = sorted(ANNOTATIONS.glob(f"*{suffix_a}"))
    if not pairs:
        print(f"No annotator-{args.a} files in {ANNOTATIONS.relative_to(ROOT)}.")
        return 2

    written, blocked = 0, []
    for path_a in pairs:
        stem = path_a.name[: -len(suffix_a)]
        path_b = ANNOTATIONS / f"{stem}.{args.b}.json"
        if not path_b.exists():
            blocked.append((stem, f"missing annotator-{args.b} file"))
            continue
        try:
            doc_a, doc_b = _load(path_a), _load(path_b)
        except ValueError as exc:
            blocked.append((stem, str(exc)))
            continue

        path_c = ANNOTATIONS / f"{stem}.{args.adjudicator}.json"
        doc_c = None
        if path_c.exists():
            try:
                doc_c = _load(path_c)
            except ValueError as exc:
                blocked.append((stem, str(exc)))
                continue

        anchors, sigmas, adjudicated, needs = [], [], [], []
        for slot_a, slot_b in zip(doc_a["slots"], doc_b["slots"]):
            index = slot_a["slot_index"]
            a, b = float(slot_a["anchor_time_s"]), float(slot_b["anchor_time_s"])
            if abs(a - b) > ADJUDICATION_THRESHOLD_S:
                if doc_c is None:
                    needs.append((index, abs(a - b)))
                    continue
                anchors.append(float(doc_c["slots"][index]["anchor_time_s"]))
                sigmas.append(abs(a - b) / 2.0)   # residual disagreement, not discarded
                adjudicated.append(index)
            else:
                anchors.append((a + b) / 2.0)
                sigmas.append(abs(a - b) / 2.0)

        if needs:
            detail = ", ".join(f"slot {i} differs by {1000 * d:.1f} ms" for i, d in needs)
            blocked.append((stem, f"needs adjudication ({detail})"))
            continue

        beats = sorted(set(doc_a["beat_times_s"]) | set(doc_b["beat_times_s"]))
        (OUT_DIR / f"{stem}.json").write_text(json.dumps({
            "audio_id": doc_a["audio_id"],
            "clip_id": doc_a.get("clip_id", ""),
            "slot_mask_id": doc_a["slot_mask_id"],
            "tempo_bpm": 60.0 / statistics.mean(
                [b - a for a, b in zip(beats, beats[1:])]
            ) if len(beats) > 1 else 0.0,
            "beat_times_s": beats,
            "anchor_times_s": anchors,
            "anchor_sigma_s": sigmas,
            "annotation_source": "HUMAN_BY_EAR",
            "annotator_ids": [args.a, args.b] + ([args.adjudicator] if adjudicated else []),
            "adjudicated_slots": adjudicated,
        }, indent=2, sort_keys=True) + "\n")
        written += 1

    print(f"F8: wrote {written} oracle file(s); {len(blocked)} blocked")
    for stem, reason in blocked:
        print(f"  BLOCKED {stem[:24]}...: {reason}")
    if blocked:
        print(f"\nA slot differing by more than {1000 * ADJUDICATION_THRESHOLD_S:.0f} ms needs a "
              f"third annotator (Section 12). Generate their worksheet with:")
        print(f"  python3 tools/make_f8_worksheets.py --annotator {args.adjudicator}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
