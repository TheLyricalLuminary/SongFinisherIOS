"""Generate F1: 10 synthetic click tracks with known BPM and phase (Section 17).

Ground truth is exact by construction, which is what makes the step-2 gate
("anchor error < 5.8 ms on all F1") a real measurement rather than a
self-comparison.  The same ground truth also serves as an F1 oracle for the
Section 12 machinery — see fixtures/F8_oracle/README.md for why that is *not* a
substitute for the F2 oracle, which requires human annotators.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.synth import SR, click, normalize_peak_dbfs, place  # noqa: E402
from vae.wavio import write_wav_pcm24  # noqa: E402

OUT = ROOT / "fixtures" / "F1_click_tracks"

# (id, bpm, phase_s, subdivision, duration_s).  Non-integer BPMs are deliberate:
# they exercise tempo resolution beyond the 5.805 ms frame lag.
SPECS = [
    ("F1_01", 72.0, 0.031, "eighth", 10.0),
    ("F1_02", 84.0, 0.117, "quarter", 9.0),
    ("F1_03", 96.0, 0.203, "eighth", 8.5),
    ("F1_04", 100.0, 0.005, "quarter", 10.0),
    ("F1_05", 104.5, 0.271, "eighth", 11.0),
    ("F1_06", 112.0, 0.089, "quarter", 9.5),
    ("F1_07", 120.0, 0.150, "eighth", 10.5),
    ("F1_08", 128.0, 0.042, "quarter", 8.2),
    ("F1_09", 132.5, 0.213, "eighth", 11.8),
    ("F1_10", 138.0, 0.061, "quarter", 9.2),
]


def build(bpm: float, phase_s: float, subdivision: str, duration_s: float):
    period = 60.0 / bpm
    n = int(round(duration_s * SR))
    buf = np.zeros(n, dtype=np.float64)
    accent = click()
    offbeat = click(duration_s=0.020, f_lo=2600.0, f_hi=9000.0, body_hz=310.0, decay=380.0)

    beats, offbeats = [], []
    b = 0
    while phase_s + b * period < duration_s - 0.05:
        t = phase_s + b * period
        place(buf, accent, t, 1.0)
        beats.append(t)
        if subdivision == "eighth":
            t_off = t + period / 2.0
            if t_off < duration_s - 0.05:
                place(buf, offbeat, t_off, 0.42)   # accented beats keep the ACF on the quarter
                offbeats.append(t_off)
        b += 1
    return normalize_peak_dbfs(buf, -3.0), beats, offbeats


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {
        "fixture_id": "F1",
        "title": "10 synthetic click tracks, known BPM/phase",
        "spec_reference": "Section 17 F1; step 2 gate in Section 23",
        "provenance": "SYNTHETIC_BY_CONSTRUCTION",
        "sample_rate": SR,
        "format": "WAV PCM 24-bit mono",
        "clips": [],
    }
    for clip_id, bpm, phase, subdivision, duration in SPECS:
        pcm, beats, offbeats = build(bpm, phase, subdivision, duration)
        path = OUT / f"{clip_id}.wav"
        write_wav_pcm24(path, pcm, SR)
        manifest["clips"].append({
            "clip_id": clip_id,
            "file": path.name,
            "tempo_bpm": bpm,
            "phase_s": phase,
            "subdivision": subdivision,
            "duration_s": duration,
            "true_beat_times_s": [round(t, 12) for t in beats],
            "true_offbeat_times_s": [round(t, 12) for t in offbeats],
            "authored_meter": "4/4",
            "authored_content": "click track, no vocal",
            "authored_language": "n/a",
        })
        print(f"{clip_id}: {bpm} BPM phase={phase}s {subdivision} "
              f"{duration}s beats={len(beats)} offbeats={len(offbeats)}")
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {len(SPECS)} clips + manifest to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
