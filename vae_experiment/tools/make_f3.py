"""Generate F3: 5 out-of-spec clips for the Section 2 rejection test.

F3 exists to prove clips are *excluded*, not degraded.  Each clip targets one
distinct rejection code so the test cannot pass by accident on a single path.
Synthetic: a clip that is out of spec by construction is out of spec, and no
scientific claim rests on these files.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.synth import SR, click, normalize_peak_dbfs, pad_tone, place  # noqa: E402
from vae.wavio import write_wav_pcm24  # noqa: E402

OUT = ROOT / "fixtures" / "F3_out_of_spec"


def ramped_clicks(bpm_start: float, bpm_end: float, duration_s: float) -> np.ndarray:
    """Accelerando / drift: the beat period sweeps linearly across the clip."""
    buf = np.zeros(int(round(duration_s * SR)), dtype=np.float64)
    accent = click()
    t, b = 0.0, 0
    while t < duration_s - 0.05:
        place(buf, accent, t, 1.0)
        frac = t / duration_s
        bpm = bpm_start + (bpm_end - bpm_start) * frac
        t += 60.0 / bpm
        b += 1
    return buf


def steady_clicks(bpm: float, duration_s: float) -> np.ndarray:
    buf = np.zeros(int(round(duration_s * SR)), dtype=np.float64)
    accent = click()
    t = 0.02
    while t < duration_s - 0.05:
        place(buf, accent, t, 1.0)
        t += 60.0 / bpm
    return buf


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    clips = []

    # 1. Rubato — large, continuous tempo change.
    pcm = normalize_peak_dbfs(ramped_clicks(88.0, 126.0, 10.0), -3.0)
    write_wav_pcm24(OUT / "F3_01_rubato.wav", pcm, SR)
    clips.append(("F3_01_rubato", "rubato: 88 -> 126 BPM accelerando", "TEMPO_DRIFT"))

    # 2. Ambient — sustained pad, no percussive or clearly articulated pulse.
    pad = pad_tone(10.0, (110.0, 165.0, 220.0, 277.2, 330.0))
    envelope = 0.5 - 0.5 * np.cos(
        2.0 * np.pi * np.arange(pad.size, dtype=np.float64) / pad.size
    )
    write_wav_pcm24(OUT / "F3_02_ambient.wav", normalize_peak_dbfs(pad * envelope, -3.0), SR)
    clips.append(("F3_02_ambient", "ambient pad, no pulse", "NO_AUDIBLE_PULSE"))

    # 3. Drift — slow tempo drift just over the +/-2 % limit.
    pcm = normalize_peak_dbfs(ramped_clicks(100.0, 106.0, 11.0), -3.0)
    write_wav_pcm24(OUT / "F3_03_drift.wav", pcm, SR)
    clips.append(("F3_03_drift", "drift: 100 -> 106 BPM (~6 %)", "TEMPO_DRIFT"))

    # 4. Duration out of range — steady and in tempo, but too short for Section 2.
    #    NOTE: an out-of-range *tempo* clip is deliberately not in F3.  The 70-140
    #    BPM restriction is itself the Section 22 failure #2 guard, so a 168 BPM
    #    clip is read at its in-range 84 BPM half-time and is not a rejection case.
    pcm = normalize_peak_dbfs(steady_clicks(110.0, 6.0), -3.0)
    write_wav_pcm24(OUT / "F3_04_short.wav", pcm, SR)
    clips.append(("F3_04_short", "6.0 s, outside the 8-12 s window", "DURATION_OUT_OF_RANGE"))

    # 5. Clipped — samples driven to digital full scale.
    pcm = np.clip(steady_clicks(110.0, 9.5) * 3.0, -1.0, 1.0)
    write_wav_pcm24(OUT / "F3_05_clipped.wav", pcm, SR)
    clips.append(("F3_05_clipped", "hard-clipped, samples at full scale", "CLIPPED_SAMPLES"))

    manifest = {
        "fixture_id": "F3",
        "title": "5 out-of-spec clips — rejection test",
        "spec_reference": "Section 2 (rejection is mandatory, no graceful degradation); Section 17 F3",
        "provenance": "SYNTHETIC_BY_CONSTRUCTION",
        "clips": [
            {"clip_id": cid, "file": f"{cid}.wav", "defect": defect,
             "expected_rejection_code": code}
            for cid, defect, code in clips
        ],
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    for cid, defect, code in clips:
        print(f"{cid}: {defect}  -> expect {code}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
