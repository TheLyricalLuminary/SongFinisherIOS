"""Fixed, versioned polyphase resampler (Section 3 step 2).

Rational L/M resampling with a Kaiser-windowed sinc prototype.  Deterministic
by construction: the filter is derived from the ratio alone, all arithmetic is
float64, and the convolution is a fixed-order accumulation with no parallel
reduction.  ``RESAMPLER_VERSION`` is one of the seven EngineVersion inputs, so
changing anything here changes every record's stamp.

No SciPy dependency: the whole point of the determinism contract being cheap
(Section 4) is that the DSP is classical and fully owned.
"""

from __future__ import annotations

from math import gcd

import numpy as np

from .constants import RESAMPLER_VERSION, SAMPLE_RATE_HZ

# Prototype filter design constants.  Structural, not swept.
FILTER_HALF_LENGTH_PER_PHASE = 24   # taps each side, per polyphase branch
KAISER_BETA = 8.6                   # ~ -80 dB stopband
CUTOFF_SAFETY = 0.98                # fraction of Nyquist for the anti-alias cutoff

VERSION = RESAMPLER_VERSION


def design_prototype(up: int, down: int) -> np.ndarray:
    """Windowed-sinc low-pass for an L/M polyphase resampler, float64."""
    max_rate = max(up, down)
    half = FILTER_HALF_LENGTH_PER_PHASE * max_rate
    n = np.arange(-half, half + 1, dtype=np.float64)
    cutoff = CUTOFF_SAFETY / max_rate           # normalised to the up-sampled rate
    # sinc(x) in numpy is sin(pi x)/(pi x); scale to the desired cutoff.
    taps = 2.0 * cutoff * np.sinc(2.0 * cutoff * n)
    taps *= np.kaiser(taps.size, KAISER_BETA)
    taps *= up / np.sum(taps, dtype=np.float64)  # unity passband gain after upsampling
    return taps


def resample(x: np.ndarray, sr_in: int, sr_out: int = SAMPLE_RATE_HZ) -> np.ndarray:
    """Resample float64 mono ``x`` from ``sr_in`` to ``sr_out``.

    Returns ``x`` unchanged when the rates already match, so a 44.1 kHz source
    is bit-preserved rather than round-tripped through a filter.
    """
    x = np.asarray(x, dtype=np.float64)
    if sr_in == sr_out:
        return x
    divisor = gcd(int(sr_in), int(sr_out))
    up = int(sr_out) // divisor
    down = int(sr_in) // divisor

    taps = design_prototype(up, down)
    half = (taps.size - 1) // 2

    upsampled = np.zeros(x.size * up, dtype=np.float64)
    upsampled[::up] = x
    padded = np.concatenate(
        (np.zeros(half, dtype=np.float64), upsampled, np.zeros(half, dtype=np.float64))
    )
    filtered = np.convolve(padded, taps, mode="valid")

    n_out = int(np.floor(x.size * up / down))
    return np.ascontiguousarray(filtered[: n_out * down : down])
