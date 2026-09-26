"""Section 3 — canonical audio representation, and Section 2 admission.

    1. Decode to float64 -> mono (L + R) / 2
    2. Resample to exactly 44100 Hz, fixed versioned polyphase resampler
    3. DC-remove
    4. Peak-normalize to -3.0 dBFS.  No compression, EQ, or dither.
    5. Zero-pad to integer multiple of hop
    6. CanonicalAudio { pcm, sample_rate: 44100, n_samples, sha256 }

``sha256`` over float32 LE serialisation is the AudioID.  It is carried on every
downstream record; a differing AudioID across runs on the same input means the
pipeline is broken.

Section 2 rejection is *mandatory* and happens before analysis.  The checks that
need only the file (format, duration, level, clipping) run here; the ones that
need the ODF (tempo range, drift, audible pulse) run in ``hear.admit_clip``.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from . import wavio
from .constants import (
    DURATION_MAX_S,
    DURATION_MIN_S,
    MIN_SOURCE_BIT_DEPTH,
    MIN_SOURCE_SAMPLE_RATE_HZ,
    NORMALIZE_PEAK_DBFS,
    SAMPLE_RATE_HZ,
    SOURCE_PEAK_MAX_DBFS,
    STFT_HOP,
)
from .contracts import CanonicalAudio
from .errors import ClipRejected
from .resampler import resample


def audio_id_of(pcm: np.ndarray) -> str:
    """sha256 over the float32 little-endian serialisation of the canonical PCM."""
    payload = np.asarray(pcm, dtype="<f4").tobytes()
    return hashlib.sha256(payload).hexdigest()


def check_source_format(source: wavio.SourceAudio, path: str) -> None:
    """Section 2 checks that need only the decoded source file."""
    if source.format_tag != wavio.WAVE_FORMAT_PCM:
        # Section 2 says "WAV PCM".  ``wavio`` can also decode IEEE float WAVs, so
        # without this the format row would be recorded rather than enforced: a
        # float32 file reports bit_depth 32 and sails past the >=16-bit check.
        raise ClipRejected(
            "NOT_PCM",
            f"{path}: WAV format tag {source.format_tag} is not PCM "
            f"({wavio.WAVE_FORMAT_PCM}); Section 2 admits WAV PCM only",
        )
    if source.sample_rate < MIN_SOURCE_SAMPLE_RATE_HZ:
        raise ClipRejected("SAMPLE_RATE_TOO_LOW", f"{path}: {source.sample_rate} Hz < 44100 Hz")
    if source.bit_depth < MIN_SOURCE_BIT_DEPTH:
        raise ClipRejected("BIT_DEPTH_TOO_LOW", f"{path}: {source.bit_depth}-bit < 16-bit")
    if source.n_clipped_samples > 0:
        raise ClipRejected(
            "CLIPPED_SAMPLES", f"{path}: {source.n_clipped_samples} sample(s) at full scale"
        )

    duration_s = source.samples.shape[0] / source.sample_rate
    if not DURATION_MIN_S <= duration_s <= DURATION_MAX_S:
        raise ClipRejected(
            "DURATION_OUT_OF_RANGE",
            f"{path}: {duration_s:.3f} s outside [{DURATION_MIN_S}, {DURATION_MAX_S}] s",
        )

    peak = float(np.max(np.abs(source.samples))) if source.samples.size else 0.0
    if peak <= 0.0:
        raise ClipRejected("SILENT", f"{path}: all-zero source")
    peak_dbfs = 20.0 * np.log10(peak)
    if peak_dbfs > SOURCE_PEAK_MAX_DBFS:
        raise ClipRejected(
            "LEVEL_TOO_HOT", f"{path}: peak {peak_dbfs:.2f} dBFS > {SOURCE_PEAK_MAX_DBFS} dBFS"
        )


def canonicalize(samples: np.ndarray, sample_rate: int) -> np.ndarray:
    """Steps 1-5 of Section 3 on already-decoded audio."""
    x = np.asarray(samples, dtype=np.float64)
    if x.ndim == 2:                                    # 1. mono (L + R) / 2
        x = np.sum(x, axis=1, dtype=np.float64) / x.shape[1]
    x = resample(x, sample_rate, SAMPLE_RATE_HZ)       # 2. exact 44100 Hz
    x = x - np.mean(x, dtype=np.float64)               # 3. DC-remove
    peak = float(np.max(np.abs(x))) if x.size else 0.0 # 4. peak-normalize to -3 dBFS
    if peak > 0.0:
        x = x * (10.0 ** (NORMALIZE_PEAK_DBFS / 20.0) / peak)
    remainder = x.size % STFT_HOP                      # 5. zero-pad to a hop multiple
    if remainder:
        x = np.concatenate((x, np.zeros(STFT_HOP - remainder, dtype=np.float64)))
    return np.ascontiguousarray(x)


def ingest(path: Path | str, engine_version: str) -> CanonicalAudio:
    """``ingest(path) -> CanonicalAudio`` (Section 21).  Pure: reads, never writes."""
    path = str(path)
    source = wavio.read_wav(path)
    check_source_format(source, path)
    pcm = canonicalize(source.samples, source.sample_rate)
    return CanonicalAudio(
        audio_id=audio_id_of(pcm),
        sample_rate=SAMPLE_RATE_HZ,
        n_samples=int(pcm.size),
        source_path=path,
        engine_version=engine_version,
        pcm=pcm,
    )
