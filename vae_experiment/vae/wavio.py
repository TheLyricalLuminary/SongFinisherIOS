"""Strict WAV reading and writing (Section 2 format requirements).

Standard library only.  Accepts PCM 16/24/32-bit and IEEE float32/64, reports
the source format so Section 2 can reject anything below 44.1 kHz / 16-bit, and
detects full-scale samples so "no clipped samples" is checkable on the source
rather than assumed.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path

import numpy as np

WAVE_FORMAT_PCM = 0x0001
WAVE_FORMAT_IEEE_FLOAT = 0x0003
WAVE_FORMAT_EXTENSIBLE = 0xFFFE


@dataclass(frozen=True)
class SourceAudio:
    samples: np.ndarray      # (n_frames, n_channels) float64 in [-1, 1]
    sample_rate: int
    n_channels: int
    bit_depth: int
    format_tag: int
    n_clipped_samples: int   # samples at digital full scale


def read_wav(path: Path | str) -> SourceAudio:
    data = Path(path).read_bytes()
    if data[0:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError(f"{path}: not a RIFF/WAVE file")

    pos = 12
    fmt = None
    payload = None
    while pos + 8 <= len(data):
        chunk_id = data[pos : pos + 4]
        (chunk_size,) = struct.unpack_from("<I", data, pos + 4)
        body = data[pos + 8 : pos + 8 + chunk_size]
        if chunk_id == b"fmt ":
            fmt = body
        elif chunk_id == b"data":
            payload = body
        pos += 8 + chunk_size + (chunk_size & 1)

    if fmt is None or payload is None:
        raise ValueError(f"{path}: missing fmt or data chunk")

    format_tag, n_channels, sample_rate, _byte_rate, _align, bits = struct.unpack_from(
        "<HHIIHH", fmt, 0
    )
    if format_tag == WAVE_FORMAT_EXTENSIBLE and len(fmt) >= 40:
        (format_tag,) = struct.unpack_from("<H", fmt, 24)

    if format_tag == WAVE_FORMAT_PCM and bits == 16:
        raw = np.frombuffer(payload, dtype="<i2").astype(np.float64)
        full_scale = 32768.0
        clipped = int(np.count_nonzero((raw >= 32767.0) | (raw <= -32768.0)))
        samples = raw / full_scale
    elif format_tag == WAVE_FORMAT_PCM and bits == 24:
        byts = np.frombuffer(payload, dtype=np.uint8).reshape(-1, 3).astype(np.int32)
        raw = (byts[:, 0] | (byts[:, 1] << 8) | (byts[:, 2] << 16)).astype(np.int32)
        raw = np.where(raw & 0x800000, raw - 0x1000000, raw).astype(np.float64)
        clipped = int(np.count_nonzero((raw >= 8388607.0) | (raw <= -8388608.0)))
        samples = raw / 8388608.0
    elif format_tag == WAVE_FORMAT_PCM and bits == 32:
        raw = np.frombuffer(payload, dtype="<i4").astype(np.float64)
        clipped = int(np.count_nonzero((raw >= 2147483647.0) | (raw <= -2147483648.0)))
        samples = raw / 2147483648.0
    elif format_tag == WAVE_FORMAT_IEEE_FLOAT and bits == 32:
        raw = np.frombuffer(payload, dtype="<f4").astype(np.float64)
        clipped = int(np.count_nonzero(np.abs(raw) >= 1.0))
        samples = raw
    elif format_tag == WAVE_FORMAT_IEEE_FLOAT and bits == 64:
        raw = np.frombuffer(payload, dtype="<f8").astype(np.float64)
        clipped = int(np.count_nonzero(np.abs(raw) >= 1.0))
        samples = raw
    else:
        raise ValueError(f"{path}: unsupported format tag {format_tag} / {bits}-bit")

    frames = samples.size // n_channels
    samples = samples[: frames * n_channels].reshape(frames, n_channels)
    return SourceAudio(
        samples=samples,
        sample_rate=int(sample_rate),
        n_channels=int(n_channels),
        bit_depth=int(bits),
        format_tag=int(format_tag),
        n_clipped_samples=clipped,
    )


def write_wav_pcm24(path: Path | str, mono: np.ndarray, sample_rate: int) -> None:
    """Write 24-bit PCM.  Used only by fixture generators, never by the pipeline."""
    x = np.asarray(mono, dtype=np.float64)
    scaled = np.rint(np.clip(x, -1.0, 1.0 - 2.0**-23) * 8388608.0).astype(np.int32)
    raw = np.empty((scaled.size, 3), dtype=np.uint8)
    raw[:, 0] = scaled & 0xFF
    raw[:, 1] = (scaled >> 8) & 0xFF
    raw[:, 2] = (scaled >> 16) & 0xFF
    payload = raw.tobytes()
    block_align = 3
    header = b"RIFF" + struct.pack("<I", 36 + len(payload)) + b"WAVE"
    header += b"fmt " + struct.pack(
        "<IHHIIHH", 16, WAVE_FORMAT_PCM, 1, sample_rate,
        sample_rate * block_align, block_align, 24,
    )
    header += b"data" + struct.pack("<I", len(payload))
    Path(path).write_bytes(header + payload)
