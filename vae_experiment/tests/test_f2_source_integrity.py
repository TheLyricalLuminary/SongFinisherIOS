"""F2 must be 20 DISTINCT real recordings, and nothing may declare itself complete.

Three defects found by auditing the F2 intake path, each verified against the
real importer and the real readiness tool before being fixed:

1.  Section 2 says "WAV PCM", but ``check_source_format`` never looked at the
    format tag. A 32-bit IEEE float WAV reports bit_depth 32 and sailed past the
    >=16-bit check.
2.  Nothing enforced distinctness. One real clip listed twenty times under twenty
    clip_ids produced 20 accepted, 20 asymmetric, status POPULATED.
3.  Readiness returned the manifest's own ``status`` string, so a manifest
    claiming POPULATED over zero clips and synthetic provenance turned the gate
    green.
"""

from __future__ import annotations

import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from tools.synth import SR, click, normalize_peak_dbfs, place  # noqa: E402
from vae import wavio  # noqa: E402
from vae.canonical import check_source_format  # noqa: E402
from vae.errors import ClipRejected  # noqa: E402
from vae.wavio import write_wav_pcm24  # noqa: E402

HEADER = ("file,clip_id,slot_mask_id,authored_meter,authored_content,"
          "authored_language,source_attribution,permission_note\n")
GOOD = "4/4,accompaniment only no vocal,English (US),own recording,self-authored"


def _clip(path, bpm=100.0, duration=10.0, phase=0.05):
    buf = np.zeros(int(duration * SR), dtype=np.float64)
    accent = click()
    t = phase
    while t < duration - 0.08:
        place(buf, accent, t, 1.0)
        t += 60.0 / bpm
    write_wav_pcm24(path, normalize_peak_dbfs(buf, -3.0), SR)


def _import(f2_dir: Path):
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "import_f2.py"), "--f2-dir", str(f2_dir)],
        capture_output=True, text=True,
    )
    manifest = f2_dir / "manifest.json"
    return proc, (json.loads(manifest.read_text()) if manifest.exists() else {})


# --------------------------------------------------------------------------- #
# 1. "WAV PCM" is enforced, not merely recorded
# --------------------------------------------------------------------------- #

def test_a_non_pcm_wav_is_rejected(tmp_path):
    """An IEEE float WAV is a WAV, but it is not WAV PCM."""
    mono = np.zeros(SR, dtype="<f4")
    mono[::4410] = 0.5
    payload = mono.tobytes()
    path = tmp_path / "float32.wav"
    path.write_bytes(
        b"RIFF" + struct.pack("<I", 36 + len(payload)) + b"WAVE"
        + b"fmt " + struct.pack("<IHHIIHH", 16, wavio.WAVE_FORMAT_IEEE_FLOAT, 1,
                                SR, SR * 4, 4, 32)
        + b"data" + struct.pack("<I", len(payload)) + payload
    )
    source = wavio.read_wav(path)
    assert source.format_tag == wavio.WAVE_FORMAT_IEEE_FLOAT
    assert source.bit_depth == 32                     # would pass the >=16-bit check

    with pytest.raises(ClipRejected) as excinfo:
        check_source_format(source, str(path))
    assert excinfo.value.reason_code == "NOT_PCM"


def test_pcm_is_still_accepted(tmp_path):
    """The guard must not reject the format every shipped fixture actually uses."""
    path = tmp_path / "pcm.wav"
    _clip(path)
    source = wavio.read_wav(path)
    assert source.format_tag == wavio.WAVE_FORMAT_PCM
    check_source_format(source, str(path))            # does not raise


# --------------------------------------------------------------------------- #
# 2. F2 is 20 distinct recordings
# --------------------------------------------------------------------------- #

def test_one_clip_listed_twenty_times_cannot_satisfy_the_gate(tmp_path):
    """Before the fix this produced 20 accepted, 20 asymmetric, POPULATED."""
    f2_dir = tmp_path / "F2_clips"
    (f2_dir / "intake").mkdir(parents=True)
    _clip(f2_dir / "intake" / "one.wav")
    rows = [f"one.wav,F2_{i:02d},M5_short_first_4,{GOOD}" for i in range(1, 21)]
    (f2_dir / "intake_f2.csv").write_text(HEADER + "\n".join(rows) + "\n")

    proc, doc = _import(f2_dir)
    assert doc["status"] == "INCOMPLETE", proc.stdout
    assert doc["requirements"]["clips_accepted"] == 1
    assert doc["requirements"]["distinct_audio_ids"] == 1
    assert len(doc["rejected"]) == 19
    assert {r["reason_code"] for r in doc["rejected"]} == {"DUPLICATE_FILE"}


def test_the_same_recording_under_two_filenames_is_caught(tmp_path):
    """A rename defeats the filename check; the AudioID is what actually differs."""
    f2_dir = tmp_path / "F2_clips"
    (f2_dir / "intake").mkdir(parents=True)
    _clip(f2_dir / "intake" / "take_a.wav")
    (f2_dir / "intake" / "take_b.wav").write_bytes(
        (f2_dir / "intake" / "take_a.wav").read_bytes()
    )
    (f2_dir / "intake_f2.csv").write_text(
        HEADER
        + f"take_a.wav,F2_01,M5_short_first_4,{GOOD}\n"
        + f"take_b.wav,F2_02,M5_short_first_4,{GOOD}\n"
    )
    proc, doc = _import(f2_dir)
    assert doc["requirements"]["clips_accepted"] == 1, proc.stdout
    assert doc["rejected"][0]["reason_code"] == "DUPLICATE_AUDIO"


def test_a_reused_clip_id_is_rejected(tmp_path):
    f2_dir = tmp_path / "F2_clips"
    (f2_dir / "intake").mkdir(parents=True)
    _clip(f2_dir / "intake" / "a.wav", bpm=100.0)
    _clip(f2_dir / "intake" / "b.wav", bpm=120.0)
    (f2_dir / "intake_f2.csv").write_text(
        HEADER
        + f"a.wav,F2_01,M5_short_first_4,{GOOD}\n"
        + f"b.wav,F2_01,M5_short_first_4,{GOOD}\n"
    )
    _, doc = _import(f2_dir)
    assert doc["requirements"]["clips_accepted"] == 1
    assert doc["rejected"][0]["reason_code"] == "DUPLICATE_CLIP_ID"


def test_distinct_recordings_are_still_accepted(tmp_path):
    """The distinctness guard must not reject genuinely different clips."""
    f2_dir = tmp_path / "F2_clips"
    (f2_dir / "intake").mkdir(parents=True)
    _clip(f2_dir / "intake" / "a.wav", bpm=100.0)
    _clip(f2_dir / "intake" / "b.wav", bpm=120.0)
    (f2_dir / "intake_f2.csv").write_text(
        HEADER
        + f"a.wav,F2_01,M5_short_first_4,{GOOD}\n"
        + f"b.wav,F2_02,M5_short_first_4,{GOOD}\n"
    )
    proc, doc = _import(f2_dir)
    assert doc["requirements"]["clips_accepted"] == 2, proc.stdout
    assert doc["requirements"]["distinct_audio_ids"] == 2
    assert doc["rejected"] == []


def test_an_unknown_slot_mask_is_rejected(tmp_path):
    f2_dir = tmp_path / "F2_clips"
    (f2_dir / "intake").mkdir(parents=True)
    _clip(f2_dir / "intake" / "a.wav")
    (f2_dir / "intake_f2.csv").write_text(HEADER + f"a.wav,F2_01,NOT_A_MASK,{GOOD}\n")
    _, doc = _import(f2_dir)
    assert doc["requirements"]["clips_accepted"] == 0
    assert doc["rejected"][0]["reason_code"] == "UNKNOWN_SLOT_MASK"


# --------------------------------------------------------------------------- #
# 3. Readiness derives F2's status; it never accepts a self-report
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("label,doc,expected", [
    ("synthetic provenance",
     {"status": "POPULATED", "provenance": "SYNTHETIC_BY_CONSTRUCTION",
      "clips": [], "rejected": []}, "UNPOPULATED"),
    ("no provenance at all",
     {"status": "POPULATED", "clips": [], "rejected": []}, "UNPOPULATED"),
    ("real provenance but no clips",
     {"status": "POPULATED", "provenance": "REAL_RECORDED_ACCOMPANIMENT",
      "clips": [], "rejected": []}, "INCOMPLETE"),
    ("twenty rows, one recording",
     {"status": "POPULATED", "provenance": "REAL_RECORDED_ACCOMPANIMENT",
      "clips": [{"audio_id": "same", "meets_asymmetry_min": True,
                "permission_note": "self-authored"}] * 20,
      "rejected": []}, "INCOMPLETE"),
    ("twenty distinct, too few asymmetric",
     {"status": "POPULATED", "provenance": "REAL_RECORDED_ACCOMPANIMENT",
      "clips": [{"audio_id": f"a{i}", "meets_asymmetry_min": i < 11,
                "permission_note": "self-authored"} for i in range(20)],
      "rejected": []}, "INCOMPLETE"),
    ("qualifies, but the importer did not say POPULATED",
     {"status": "INCOMPLETE", "provenance": "REAL_RECORDED_ACCOMPANIMENT",
      "clips": [{"audio_id": f"a{i}", "meets_asymmetry_min": i < 12,
                "permission_note": "self-authored"} for i in range(20)],
      "rejected": []}, "INCOMPLETE"),
    ("twenty distinct, twelve asymmetric, importer agrees",
     {"status": "POPULATED", "provenance": "REAL_RECORDED_ACCOMPANIMENT",
      "clips": [{"audio_id": f"a{i}", "meets_asymmetry_min": i < 12,
                "permission_note": "self-authored"} for i in range(20)],
      "rejected": []}, "POPULATED"),
])
def test_readiness_derives_f2_status_from_contents(label, doc, expected):
    import tools.readiness as readiness

    original = readiness.F2_MANIFEST
    try:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "manifest.json"
            path.write_text(json.dumps(doc))
            readiness.F2_MANIFEST = path
            status, _notes = readiness._f2()
    finally:
        readiness.F2_MANIFEST = original
    assert status == expected, label


def test_the_shipped_repository_reports_f2_unpopulated():
    """No source audio has been supplied, and nothing may pretend otherwise."""
    import tools.readiness as readiness

    assert not readiness.F2_MANIFEST.exists()
    status, notes = readiness._f2()
    assert status == "UNPOPULATED"
    assert any("no clips supplied" in n for n in notes)


# --------------------------------------------------------------------------- #
# 4. permission_note is a required provenance gate (spec-owner decision)
# --------------------------------------------------------------------------- #

NO_PERMISSION = "4/4,accompaniment only no vocal,English (US),own recording,"


def _one_clip(tmp_path, declarations):
    f2_dir = tmp_path / "F2_clips"
    (f2_dir / "intake").mkdir(parents=True)
    _clip(f2_dir / "intake" / "a.wav")
    (f2_dir / "intake_f2.csv").write_text(
        HEADER + f"a.wav,F2_01,M5_short_first_4,{declarations}\n"
    )
    return _import(f2_dir)


@pytest.mark.parametrize("label,declarations", [
    ("blank", NO_PERMISSION),
    ("spaces", "4/4,accompaniment only no vocal,English (US),own recording,   "),
    ("tab", "4/4,accompaniment only no vocal,English (US),own recording,\t"),
])
def test_a_blank_permission_note_rejects_the_clip(tmp_path, label, declarations):
    _, doc = _one_clip(tmp_path, declarations)
    assert doc["requirements"]["clips_accepted"] == 0, label
    assert doc["rejected"][0]["reason_code"] == "PERMISSION_NOTE_MISSING", label


def test_an_absent_permission_column_rejects_the_clip(tmp_path):
    """A CSV written to the old seven-column shape must not slip through."""
    f2_dir = tmp_path / "F2_clips"
    (f2_dir / "intake").mkdir(parents=True)
    _clip(f2_dir / "intake" / "a.wav")
    (f2_dir / "intake_f2.csv").write_text(
        "file,clip_id,slot_mask_id,authored_meter,authored_content,"
        "authored_language,source_attribution\n"
        "a.wav,F2_01,M5_short_first_4,4/4,accompaniment only,English (US),own recording\n"
    )
    _, doc = _import(f2_dir)
    assert doc["requirements"]["clips_accepted"] == 0
    assert doc["rejected"][0]["reason_code"] == "PERMISSION_NOTE_MISSING"


def test_the_code_is_distinct_from_the_section_2_declaration_codes(tmp_path):
    """A provenance failure is not an acoustic or Section 2 failure."""
    _, doc = _one_clip(tmp_path, NO_PERMISSION)
    code = doc["rejected"][0]["reason_code"]
    assert code == "PERMISSION_NOTE_MISSING"
    assert code not in ("DECLARATION_MISSING", "DECLARATION_INVALID")


def test_permission_is_never_inferred_from_source_attribution(tmp_path):
    """Knowing where a recording came from is not a statement that it may be used."""
    detailed = ("4/4,accompaniment only no vocal,English (US),"
                "recorded at Abbey Road 1998 by the composer himself,")
    _, doc = _one_clip(tmp_path, detailed)
    assert doc["requirements"]["clips_accepted"] == 0
    assert doc["rejected"][0]["reason_code"] == "PERMISSION_NOTE_MISSING"


def test_the_same_clip_is_accepted_once_the_note_is_supplied(tmp_path):
    """The gate is provenance only: the audio checks are untouched by it."""
    _, without = _one_clip(tmp_path / "a", NO_PERMISSION)
    _, with_note = _one_clip(tmp_path / "b", GOOD)
    assert without["requirements"]["clips_accepted"] == 0
    assert with_note["requirements"]["clips_accepted"] == 1
    assert with_note["rejected"] == []
    assert with_note["clips"][0]["permission_note"] == "self-authored"


def test_the_manifest_says_the_field_is_not_a_licence_check(tmp_path):
    _, doc = _one_clip(tmp_path, GOOD)
    note = doc["permission_note_is_provenance_not_verification"]
    assert "REQUIRED" in note
    assert "no legal determination" in note
    assert "never inferred from source_attribution" in note


def test_readiness_refuses_accepted_clips_that_carry_no_permission_note():
    """Same rule as the status field: derive, never trust what the manifest asserts."""
    import tools.readiness as readiness

    doc = {
        "status": "POPULATED", "provenance": "REAL_RECORDED_ACCOMPANIMENT",
        "clips": [{"clip_id": f"F2_{i:02d}", "audio_id": f"a{i}",
                   "meets_asymmetry_min": i < 12,
                   "permission_note": "self-authored" if i else ""}
                  for i in range(20)],
        "rejected": [],
    }
    original = readiness.F2_MANIFEST
    try:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "manifest.json"
            path.write_text(json.dumps(doc))
            readiness.F2_MANIFEST = path
            status, notes = readiness._f2()
    finally:
        readiness.F2_MANIFEST = original
    assert status == "INCOMPLETE"
    assert any("no permission_note" in n for n in notes)
