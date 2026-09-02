"""Generate the F2 pipeline-exercise stand-in.

**These clips are NOT F2.**  F2 is real recorded accompaniment (see
fixtures/F2_clips/README.md).  These synthesised clips exist so that SHAPE, the
six conditions, RANK and the determinism harness can be exercised end-to-end on
something Section 2 admits.  No result computed from them is a result about the
hypothesis, and every runner that reads them stamps ``uses_synthetic_fixtures``.
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

OUT = ROOT / "fixtures" / "F2_SYNTH_pipeline_exercise"

# Chord roots (Hz) for the pad, one per clip, and the drum pattern to use.
# (clip_id, bpm, duration_s, phase_s, pattern, root_hz, slot_mask_id)
SPECS = [
    ("S01",  76.0, 10.5, 0.040, "backbeat",  110.00, "M5_short_first_4"),
    ("S02",  82.0,  9.8, 0.110, "backbeat",  123.47, "M6_long_first_4"),
    ("S03",  88.0, 11.2, 0.075, "eighths",   130.81, "M5_short_first_4"),
    ("S04",  94.0, 10.0, 0.020, "eighths",   146.83, "M6_long_first_4"),
    ("S05",  98.0,  9.2, 0.150, "backbeat",  164.81, "M7_short_first_6"),
    ("S06", 102.0, 10.8, 0.090, "backbeat",  174.61, "M8_long_first_6"),
    ("S07", 106.0,  8.6, 0.030, "eighths",   196.00, "M7_short_first_6"),
    ("S08", 110.0, 11.5, 0.125, "eighths",   103.83, "M8_long_first_6"),
    ("S09", 114.0,  9.4, 0.060, "backbeat",  116.54, "M5_short_first_4"),
    ("S10", 118.0, 10.2, 0.100, "backbeat",  138.59, "M6_long_first_4"),
    ("S11", 122.0,  8.8, 0.045, "eighths",   155.56, "M7_short_first_6"),
    ("S12", 126.0, 11.0, 0.135, "eighths",   185.00, "M8_long_first_6"),
    ("S13",  74.0,  9.6, 0.085, "backbeat",  207.65, "M1_quarters_4"),
    ("S14",  86.0, 10.4, 0.055, "eighths",   233.08, "M2_quarters_8"),
    ("S15",  96.0,  8.4, 0.115, "backbeat",  110.00, "M3_eighths_4"),
    ("S16", 108.0, 11.8, 0.070, "eighths",   123.47, "M4_dotted_4"),
    ("S17", 120.0,  9.0, 0.035, "backbeat",  130.81, "M1_quarters_4"),
    ("S18", 130.0, 10.6, 0.145, "eighths",   146.83, "M2_quarters_8"),
    ("S19", 134.0,  8.2, 0.095, "backbeat",  164.81, "M3_eighths_4"),
    ("S20", 138.0, 11.4, 0.065, "eighths",   174.61, "M4_dotted_4"),
]


def build(bpm: float, duration_s: float, phase_s: float, pattern: str, root: float):
    period = 60.0 / bpm
    n = int(round(duration_s * SR))
    buf = np.zeros(n, dtype=np.float64)

    kick = click(duration_s=0.055, f_lo=140.0, f_hi=48.0, body_hz=52.0, decay=42.0)
    snare = click(duration_s=0.045, f_lo=900.0, f_hi=4200.0, body_hz=185.0, decay=150.0)
    hat = click(duration_s=0.018, f_lo=5200.0, f_hi=11000.0, body_hz=0.0, decay=520.0)

    beats = []
    b = 0
    while phase_s + b * period < duration_s - 0.08:
        t = phase_s + b * period
        beats.append(t)
        in_bar = b % 4
        place(buf, kick, t, 1.0 if in_bar in (0, 2) else 0.35)
        if in_bar in (1, 3):
            place(buf, snare, t, 0.85)
        if pattern == "eighths":
            place(buf, hat, t, 0.30)
            t_off = t + period / 2.0
            if t_off < duration_s - 0.08:
                place(buf, hat, t_off, 0.22)
        b += 1

    # Sustained triad pad: harmonic content with no transients of its own, so it
    # colours the spectrum without adding onsets.
    pad = pad_tone(duration_s, (root, root * 1.25, root * 1.5, root * 2.0))
    buf += 0.16 * pad / max(1e-12, float(np.max(np.abs(pad))))
    return normalize_peak_dbfs(buf, -3.0), beats


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = {
        "fixture_id": "F2_SYNTH_pipeline_exercise",
        "title": "Synthetic accompaniment stand-in — NOT F2",
        "not_f2": (
            "These clips are synthesised. F2 requires real recorded accompaniment "
            "(fixtures/F2_clips/README.md). Nothing computed from these files is a "
            "result about the hypothesis; they exist to exercise SHAPE, the six "
            "conditions, RANK and the determinism harness."
        ),
        "provenance": "SYNTHETIC_BY_CONSTRUCTION",
        "clips": [],
    }
    for clip_id, bpm, duration, phase, pattern, root, mask_id in SPECS:
        pcm, beats = build(bpm, duration, phase, pattern, root)
        path = OUT / f"{clip_id}.wav"
        write_wav_pcm24(path, pcm, SR)
        manifest["clips"].append({
            "clip_id": clip_id, "file": path.name, "tempo_bpm": bpm,
            "duration_s": duration, "phase_s": phase, "pattern": pattern,
            "pad_root_hz": root, "slot_mask_id": mask_id,
            "true_beat_times_s": [round(t, 12) for t in beats],
            "authored_meter": "4/4", "authored_content": "accompaniment only, no vocal",
            "authored_language": "n/a (synthetic)",
        })
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {len(SPECS)} synthetic clips to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
