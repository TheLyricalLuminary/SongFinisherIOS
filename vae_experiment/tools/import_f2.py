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

import argparse
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

DEFAULT_F2_DIR = ROOT / "fixtures" / "F2_clips"

REQUIRED_CLIPS = 20
REQUIRED_ASYMMETRIC = 12

# Section 2 fixes these two rows exactly.  They stay human DECLARATIONS -- the
# pipeline cannot hear whether a clip is accompaniment-only or in 4/4 -- but a
# blank or wrong declaration must not let a clip count toward F2, or the frozen
# admission criteria would be recorded rather than enforced.
REQUIRED_METER = "4/4"
REQUIRED_LANGUAGE = "English (US)"


def _rows(intake_csv: Path) -> list[dict]:
    if not intake_csv.exists():
        return []
    lines = [
        line for line in intake_csv.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    return list(csv.DictReader(lines))


def run(f2_dir: Path) -> int:
    engine = build_engine()
    intake_dir, intake_csv = f2_dir / "intake", f2_dir / "intake_f2.csv"
    rows = _rows(intake_csv)
    present = sorted(p.name for p in intake_dir.glob("*.wav")) if intake_dir.exists() else []

    if not rows and not present:
        print("F2 remains UNPOPULATED: no clips supplied.")
        print(f"  Put WAV files in {intake_dir}/ and list them in {intake_csv.name}.")
        print(f"  See {f2_dir / 'ACCEPTANCE.md'} for the exact requirements.")
        print("  Nothing synthetic will be substituted.")
        return 2

    unlisted = sorted(set(present) - {(r.get('file') or '').strip() for r in rows})
    if unlisted:
        print(f"WARNING: {len(unlisted)} file(s) in intake/ are not listed in the CSV "
              f"and will be ignored: {unlisted}")

    # F2 is 20 DISTINCT recordings.  Without these three, one real clip listed
    # twenty times under twenty clip_ids drives the gate to POPULATED with 20
    # accepted and 20 asymmetric -- verified, not hypothetical.  First occurrence
    # in CSV order wins so the outcome does not depend on iteration order.
    seen_clip_ids: dict[str, str] = {}
    seen_files: dict[str, str] = {}
    seen_audio_ids: dict[str, str] = {}

    accepted, rejected = [], []
    for row in rows:
        filename = (row.get("file") or "").strip()
        clip_id = (row.get("clip_id") or "").strip() or Path(filename).stem
        mask_id = (row.get("slot_mask_id") or "").strip()
        path = intake_dir / filename

        if clip_id in seen_clip_ids:
            rejected.append((clip_id, "DUPLICATE_CLIP_ID",
                             f"clip_id {clip_id!r} already used by file "
                             f"{seen_clip_ids[clip_id]!r}"))
            continue
        if filename and filename in seen_files:
            rejected.append((clip_id, "DUPLICATE_FILE",
                             f"{filename!r} is already listed as {seen_files[filename]!r}; "
                             f"F2 requires {REQUIRED_CLIPS} distinct recordings"))
            continue
        if not filename or not path.exists():
            rejected.append((clip_id, "FILE_MISSING", f"{path} not found"))
            continue
        try:
            mask = engine.masks.by_id(mask_id)
        except KeyError:
            rejected.append((clip_id, "UNKNOWN_SLOT_MASK",
                             f"{mask_id!r} is not in the F6 inventory"))
            continue

        meter = (row.get("authored_meter") or "").strip()
        content = (row.get("authored_content") or "").strip()
        language = (row.get("authored_language") or "").strip()
        attribution = (row.get("source_attribution") or "").strip()
        permission = (row.get("permission_note") or "").strip()

        missing = [name for name, value in
                   (("authored_content", content), ("source_attribution", attribution))
                   if not value]
        if missing:
            rejected.append((clip_id, "DECLARATION_MISSING",
                             f"empty {', '.join(missing)}; Section 2 requires these to be declared"))
            continue
        if meter != REQUIRED_METER:
            rejected.append((clip_id, "DECLARATION_INVALID",
                             f"authored_meter is {meter!r}; Section 2 admits {REQUIRED_METER!r} only"))
            continue
        if language != REQUIRED_LANGUAGE:
            rejected.append((clip_id, "DECLARATION_INVALID",
                             f"authored_language is {language!r}; Section 2 admits "
                             f"{REQUIRED_LANGUAGE!r} only"))
            continue
        # Provenance/compliance gate, NOT an acoustic or scientific criterion, so it
        # carries its own reason code rather than joining DECLARATION_MISSING: a clip
        # excluded for missing paperwork failed nothing about the recording.
        # Deliberately independent of source_attribution -- knowing WHERE a recording
        # came from is not a statement that it may be used and retained, and inferring
        # one from the other is exactly the inference this gate exists to prevent.
        if not permission:
            rejected.append((clip_id, "PERMISSION_NOTE_MISSING",
                             "permission_note is blank; record the basis on which this "
                             "recording may be used and retained (see INTAKE_CHECKLIST.md)"))
            continue

        try:
            check_source_format(wavio.read_wav(path), str(path))
            audio = engine.ingest(path)
            evidence, log = engine.hear_with_log(audio, mask)
        except ClipRejected as exc:
            rejected.append((clip_id, exc.reason_code, exc.detail))
            continue

        # AudioID, not the file sha256: canonicalisation peak-normalises, so two
        # copies of one recording at different levels are byte-different files
        # with identical canonical PCM.  The file hash would miss that; this does
        # not.
        if audio.audio_id in seen_audio_ids:
            rejected.append((clip_id, "DUPLICATE_AUDIO",
                             f"canonical audio is identical to {seen_audio_ids[audio.audio_id]!r} "
                             f"(AudioID {audio.audio_id[:12]}...); F2 requires distinct recordings"))
            continue

        seen_clip_ids[clip_id] = filename
        seen_files[filename] = clip_id
        seen_audio_ids[audio.audio_id] = clip_id

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
            "authored_meter": meter,
            "authored_content": content,
            "authored_language": language,
            "source_attribution": attribution,
            "permission_note": permission,
        })

    n_asym = sum(1 for c in accepted if c["meets_asymmetry_min"])
    n_distinct = len({c["audio_id"] for c in accepted})
    complete = (
        len(accepted) >= REQUIRED_CLIPS
        and n_distinct == len(accepted)          # belt and braces: no duplicate slipped through
        and n_asym >= REQUIRED_ASYMMETRIC
    )

    manifest = {
        "fixture_id": "F2",
        "title": "Accompaniment clips meeting Section 2",
        "status": "POPULATED" if complete else "INCOMPLETE",
        "provenance": "REAL_RECORDED_ACCOMPANIMENT",
        "requirements": {
            "clips_required": REQUIRED_CLIPS,
            "asymmetric_required": REQUIRED_ASYMMETRIC,
            "clips_accepted": len(accepted),
            "distinct_audio_ids": n_distinct,
            "asymmetric_accepted": n_asym,
        },
        "authored_fields_are_declarations": (
            "authored_meter, authored_content and authored_language cannot be verified by the "
            "pipeline and are recorded as declared. They are nonetheless REQUIRED and are "
            "checked for presence and exact value: a clip with a missing or wrong declaration "
            "is rejected and does not count toward F2 completeness."
        ),
        "permission_note_is_provenance_not_verification": (
            "permission_note is REQUIRED: a blank or whitespace-only value rejects the clip "
            "as PERMISSION_NOTE_MISSING. It records the experiment owner's STATED basis for "
            "using and retaining the recording. It is not a licence check and makes no legal "
            "determination that a source actually is licensed; nothing here verifies the "
            "claim, and it is never inferred from source_attribution."
        ),
        "clips": accepted,
        "rejected": [
            {"clip_id": c, "reason_code": r, "detail": d} for c, r, d in rejected
        ],
    }
    (f2_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--f2-dir", default=str(DEFAULT_F2_DIR),
                        help="directory holding intake/, intake_f2.csv and manifest.json")
    return run(Path(parser.parse_args().f2_dir))


if __name__ == "__main__":
    raise SystemExit(main())
