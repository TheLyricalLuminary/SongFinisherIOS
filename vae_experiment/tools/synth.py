"""Deterministic synthesis primitives for fixture generation.

Fixture generators are tooling, not pipeline stages, but they are still written
without an RNG: every waveform below is a closed-form function of its arguments,
so regenerating a fixture reproduces it byte-for-byte.
"""

from __future__ import annotations

import numpy as np

SR = 44100


def click(duration_s: float = 0.030, f_lo: float = 1800.0, f_hi: float = 7600.0,
          body_hz: float = 190.0, decay: float = 240.0) -> np.ndarray:
    """A broadband percussive click: linear chirp plus a low body, exponential decay."""
    n = int(round(duration_s * SR))
    t = np.arange(n, dtype=np.float64) / SR
    sweep = np.sin(2.0 * np.pi * (f_lo * t + 0.5 * (f_hi - f_lo) / duration_s * t * t))
    body = 0.65 * np.sin(2.0 * np.pi * body_hz * t)
    return (sweep + body) * np.exp(-decay * t)


def pad_tone(duration_s: float, freqs: tuple[float, ...], sr: int = SR) -> np.ndarray:
    """A sustained harmonic pad with fixed phases: deterministic, no RNG."""
    t = np.arange(int(round(duration_s * sr)), dtype=np.float64) / sr
    out = np.zeros(t.size, dtype=np.float64)
    for i, f in enumerate(freqs):
        out += np.sin(2.0 * np.pi * f * t + 0.37 * (i + 1)) / (i + 1)
    return out


def place(buffer: np.ndarray, waveform: np.ndarray, time_s: float, gain: float) -> None:
    """Add ``waveform`` into ``buffer`` at ``time_s``, scaled by ``gain``. In place."""
    start = int(round(time_s * SR))
    if start >= buffer.size:
        return
    end = min(buffer.size, start + waveform.size)
    buffer[start:end] += gain * waveform[: end - start]


def normalize_peak_dbfs(x: np.ndarray, dbfs: float) -> np.ndarray:
    peak = float(np.max(np.abs(x)))
    if peak <= 0.0:
        return x
    return x * (10.0 ** (dbfs / 20.0) / peak)
