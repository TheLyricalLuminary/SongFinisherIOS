"""Validate and import real accompaniment clips as F2.

Runs the full Section 2 admission check on every candidate and writes a manifest
containing only the clips that pass.  Failing clips are EXCLUDED and logged --
Section 2 rejection is mandatory and there is no graceful degradation.

Nothing here can be satisfied with synthetic audio: the importer reads whatever
WAV files are in fixtures/F2_clips/intake/ and records their measured properties.
If no files are present it says so and writes nothing.

Measured tempo and beat phase are written into the manifest so downstream mask
fitting has something to work from; they are stamped ``measurement_source:
"HEAR"`` to distinguish them from the ground-truth-by-construction values that
the synthetic fixtures carry.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from vae.canonical import check_source_format  # noqa: E402
from vae.errors import ClipRejected  # noqa: E402
from vae.pipeline import build_engine  # noqa: E402
from vae.shape import realized_asymmetry, realized_asymmetry_direction, shape  # noqa: E402
from vae import wavio  # noqa: E402

F2_DIR = ROOT / "fixtures" / "F2_clips"
INTAKE_DIR = F2_DIR / "intake"
INTAKE_CSV = F2_DIR / "intake_f2.csv"

REQUIRED_CLIPS = 20
REQUIRED_ASYMMETRIC = 12


def _rows() -> list[dict]:
    if not INTAKE_CSV.exists():
        return []
    lines = [
        line for line in INTAKE_CSV.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    return list(csv.DictReader(lines))


def main() -> int:
    engine = build_engine()
    rows = _rows()
    present = sorted(p.name for p in INTAKE_DIR.glob("*.wav")) if INTAKE_DIR.exists() else []

    if not rows and not present:
        print("F2 remains UNPOPULATED: no clips supplied.")
        print(f"  Put WAV files in {INTAKE_DIR.relative_to(ROOT)}/ and list them in "
              f"{INTAKE_CSV.name}.")
        print(f"  See {(F2_DIR / 'ACCEPTANCE.md').relative_to(ROOT)} for the exact requirements.")
        print("  Nothing synthetic will be substituted.")
        return 2

    unlisted = sorted(set(present) - {(r.get('file') or '').strip() for r in rows})
    if unlisted:
        print(f"WARNING: {len(unlisted)} file(s) in intake/ are not listed in the CSV "
              f"and will be ignored: {unlisted}")

    accepted, rejected = [], []
    for row in rows:
        filename = (row.get("file") or "").strip()
        clip_id = (row.get("clip_id") or "").strip() or Path(filename).stem
        mask_id = (row.get("slot_mask_id") or "").strip()
        path = INTAKE_DIR / filename

        if not filename or not path.exists():
            rejected.append((clip_id, "FILE_MISSING", f"{path} not found"))
            continue
        try:
            mask = engine.masks.by_id(mask_id)
        except KeyError:
            rejected.append((clip_id, "UNKNOWN_SLOT_MASK",
                             f"{mask_id!r} is not in the F6 inventory"))
            continue

        try:
            check_source_format(wavio.read_wav(path), str(path))
            audio = engine.ingest(path)
            evidence, log = engine.hear_with_log(audio, mask)
        except ClipRejected as exc:
            rejected.append((clip_id, exc.reason_code, exc.detail))
            continue

        envelope = shape(evidence, engine.config, mask)
        asymmetry = realized_asymmetry(envelope)
        duration_s = audio.n_samples / audio.sample_rate

        accepted.append({
            "clip_id": clip_id,
            "file": filename,
            "audio_id": audio.audio_id,
            "sha256_source_file": hashlib.sha256(path.read_bytes()).hexdigest(),
            "slot_mask_id": mask_id,
            "duration_s": duration_s,
            "tempo_bpm": log.tempo_bpm,
            "phase_s": log.beat_phase_s,
            "measurement_source": "HEAR",
            "tempo_drift_frac": log.tempo_drift_frac,
            "grid_match_rate": log.grid_match_rate,
            "onset_density_per_eighth": log.onset_density_per_eighth,
            "grid_only_slots": log.grid_only_slot_count,
            "realized_asymmetry": asymmetry,
            "realized_asymmetry_direction": realized_asymmetry_direction(envelope, engine.config),
            "meets_asymmetry_min": asymmetry >= engine.config.ASYMMETRY_MIN,
            "authored_meter": (row.get("authored_meter") or "").strip(),
            "authored_content": (row.get("authored_content") or "").strip(),
            "authored_language": (row.get("authored_language") or "").strip(),
            "source_attribution": (row.get("source_attribution") or "").strip(),
        })

    n_asym = sum(1 for c in accepted if c["meets_asymmetry_min"])
    complete = len(accepted) >= REQUIRED_CLIPS and n_asym >= REQUIRED_ASYMMETRIC

    manifest = {
        "fixture_id": "F2",
        "title": "Accompaniment clips meeting Section 2",
        "status": "POPULATED" if complete else "INCOMPLETE",
        "provenance": "REAL_RECORDED_ACCOMPANIMENT",
        "requirements": {
            "clips_required": REQUIRED_CLIPS,
            "asymmetric_required": REQUIRED_ASYMMETRIC,
            "clips_accepted": len(accepted),
            "asymmetric_accepted": n_asym,
        },
        "authored_fields_are_declarations": (
            "authored_meter, authored_content and authored_language cannot be verified by the "
            "pipeline and are recorded as declared."
        ),
        "clips": accepted,
        "rejected": [
            {"clip_id": c, "reason_code": r, "detail": d} for c, r, d in rejected
        ],
    }
    (F2_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    print(f"F2 intake: {len(accepted)} accepted, {len(rejected)} rejected")
    for clip_id, reason, detail in rejected:
        print(f"  REJECTED {clip_id}: {reason} -- {detail}")
    print(f"  asymmetric (>= {engine.config.ASYMMETRY_MIN}): {n_asym}")
    if complete:
        print(f"F2 POPULATED: {len(accepted)} clips, {n_asym} asymmetric.")
        return 0
    print(f"F2 INCOMPLETE: need {REQUIRED_CLIPS} clips ({REQUIRED_ASYMMETRIC} asymmetric); "
          f"have {len(accepted)} ({n_asym} asymmetric).")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
