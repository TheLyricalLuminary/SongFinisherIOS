"""F2 declarations are required and exact, though still human declarations."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

sys.path.insert(0, str(ROOT / "tools"))
from tools.synth import SR, click, normalize_peak_dbfs, place  # noqa: E402
from vae.wavio import write_wav_pcm24  # noqa: E402

HEADER = ("file,clip_id,slot_mask_id,authored_meter,authored_content,"
          "authored_language,source_attribution,permission_note\n")
GOOD = "4/4,accompaniment only no vocal,English (US),own recording,self-authored"


def _clip(path):
    """A clip that passes every machine-checkable Section 2 requirement."""
    duration, bpm = 10.0, 100.0
    buf = np.zeros(int(duration * SR), dtype=np.float64)
    accent = click()
    t = 0.05
    while t < duration - 0.08:
        place(buf, accent, t, 1.0)
        t += 60.0 / bpm
    write_wav_pcm24(path, normalize_peak_dbfs(buf, -3.0), SR)


@pytest.fixture(scope="module")
def workspace(tmp_path_factory):
    root = tmp_path_factory.mktemp("f2")
    (root / "intake").mkdir()
    _clip(root / "intake" / "c.wav")
    return root


def _run(workspace, tmp_path, declarations):
    """Run the real importer against a temporary F2 directory."""
    f2_dir = tmp_path / "F2_clips"
    (f2_dir / "intake").mkdir(parents=True)
    (f2_dir / "intake" / "c.wav").write_bytes((workspace / "intake" / "c.wav").read_bytes())
    (f2_dir / "intake_f2.csv").write_text(
        HEADER + f"c.wav,F2_01,M1_quarters_4,{declarations}\n"
    )
    proc = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "import_f2.py"), "--f2-dir", str(f2_dir)],
        capture_output=True, text=True,
    )
    manifest = f2_dir / "manifest.json"
    doc = json.loads(manifest.read_text()) if manifest.exists() else {}
    return proc, doc


def test_a_fully_declared_clip_is_accepted(workspace, tmp_path):
    proc, doc = _run(workspace, tmp_path, GOOD)
    assert len(doc.get("clips", [])) == 1, proc.stdout + proc.stderr
    assert doc["clips"][0]["authored_meter"] == "4/4"


@pytest.mark.parametrize("declarations,code,needle", [
    ("4/4,,English (US),own recording", "DECLARATION_MISSING", "authored_content"),
    ("4/4,accompaniment only,English (US),", "DECLARATION_MISSING", "source_attribution"),
    ("3/4,accompaniment only,English (US),own", "DECLARATION_INVALID", "authored_meter"),
    (",accompaniment only,English (US),own", "DECLARATION_INVALID", "authored_meter"),
    ("4/4,accompaniment only,French,own", "DECLARATION_INVALID", "authored_language"),
    ("4/4,accompaniment only,,own", "DECLARATION_INVALID", "authored_language"),
    ("4/4,accompaniment only,english (us),own", "DECLARATION_INVALID", "authored_language"),
])
def test_bad_declarations_are_rejected_and_do_not_count(
    workspace, tmp_path, declarations, code, needle
):
    proc, doc = _run(workspace, tmp_path, declarations)
    assert doc.get("clips") == [], "a badly declared clip must not count toward F2"
    assert doc["rejected"][0]["reason_code"] == code
    assert needle in doc["rejected"][0]["detail"]
    assert doc["requirements"]["clips_accepted"] == 0


def test_manifest_still_marks_the_fields_as_unverifiable(workspace, tmp_path):
    _, doc = _run(workspace, tmp_path, GOOD)
    note = doc["authored_fields_are_declarations"]
    assert "cannot be verified" in note and "REQUIRED" in note
