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
          "authored_language,source_attribution\n")
GOOD = "4/4,accompaniment only no vocal,English (US),own recording"


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
      "clips": [{"audio_id": "same", "meets_asymmetry_min": True}] * 20,
      "rejected": []}, "INCOMPLETE"),
    ("twenty distinct, too few asymmetric",
     {"status": "POPULATED", "provenance": "REAL_RECORDED_ACCOMPANIMENT",
      "clips": [{"audio_id": f"a{i}", "meets_asymmetry_min": i < 11} for i in range(20)],
      "rejected": []}, "INCOMPLETE"),
    ("qualifies, but the importer did not say POPULATED",
     {"status": "INCOMPLETE", "provenance": "REAL_RECORDED_ACCOMPANIMENT",
      "clips": [{"audio_id": f"a{i}", "meets_asymmetry_min": i < 12} for i in range(20)],
      "rejected": []}, "INCOMPLETE"),
    ("twenty distinct, twelve asymmetric, importer agrees",
     {"status": "POPULATED", "provenance": "REAL_RECORDED_ACCOMPANIMENT",
      "clips": [{"audio_id": f"a{i}", "meets_asymmetry_min": i < 12} for i in range(20)],
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
