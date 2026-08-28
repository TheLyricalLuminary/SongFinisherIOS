"""Section 3 canonical audio and Section 2 mandatory rejection."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from vae.canonical import audio_id_of, canonicalize, ingest
from vae.constants import SAMPLE_RATE_HZ, STFT_HOP
from vae.errors import ClipRejected
from vae.hear import hear_with_log
from vae.resampler import resample
from vae.wavio import read_wav, write_wav_pcm24

ROOT = Path(__file__).resolve().parent.parent
F1_DIR = ROOT / "fixtures" / "F1_click_tracks"
F3_DIR = ROOT / "fixtures" / "F3_out_of_spec"


def test_canonical_audio_meets_every_section_3_postcondition():
    source = read_wav(F1_DIR / "F1_01.wav")
    pcm = canonicalize(source.samples, source.sample_rate)
    assert pcm.dtype == np.float64
    assert pcm.ndim == 1                                   # mono
    assert pcm.size % STFT_HOP == 0                        # zero-padded to a hop multiple
    assert abs(float(np.mean(pcm))) < 1e-9                 # DC removed
    peak_dbfs = 20.0 * np.log10(float(np.max(np.abs(pcm))))
    assert abs(peak_dbfs - (-3.0)) < 1e-9                  # normalised to -3.0 dBFS


def test_audio_id_is_stable_and_input_sensitive():
    source = read_wav(F1_DIR / "F1_01.wav")
    pcm = canonicalize(source.samples, source.sample_rate)
    assert audio_id_of(pcm) == audio_id_of(pcm.copy())
    nudged = pcm.copy()
    nudged[1000] += 1e-3
    assert audio_id_of(nudged) != audio_id_of(pcm)


def test_ingest_is_deterministic_across_repeated_calls():
    a = ingest(F1_DIR / "F1_01.wav", "EV")
    b = ingest(F1_DIR / "F1_01.wav", "EV")
    assert a.audio_id == b.audio_id
    assert a.n_samples == b.n_samples


def test_resampler_is_identity_at_the_canonical_rate():
    x = np.linspace(-0.5, 0.5, 5000, dtype=np.float64)
    assert np.array_equal(resample(x, SAMPLE_RATE_HZ, SAMPLE_RATE_HZ), x)


def test_resampler_preserves_a_tone_from_48k():
    t = np.arange(48000, dtype=np.float64) / 48000.0
    y = resample(0.5 * np.sin(2.0 * np.pi * 1000.0 * t), 48000, SAMPLE_RATE_HZ)
    assert y.size == SAMPLE_RATE_HZ
    interior = y[2000:-2000]
    assert abs(float(np.max(np.abs(interior))) - 0.5) < 1e-3
    spectrum = np.abs(np.fft.rfft(interior * np.hanning(interior.size)))
    peak_hz = np.fft.rfftfreq(interior.size, 1.0 / SAMPLE_RATE_HZ)[int(np.argmax(spectrum))]
    assert abs(peak_hz - 1000.0) < 1.0


@pytest.mark.parametrize(
    "clip", json.loads((F3_DIR / "manifest.json").read_text())["clips"],
    ids=lambda c: c["clip_id"],
)
def test_f3_clips_are_excluded_not_degraded(clip, config, masks):
    """Section 2: rejection is mandatory. No graceful degradation."""
    with pytest.raises(ClipRejected) as excinfo:
        audio = ingest(F3_DIR / clip["file"], "EV")
        hear_with_log(audio, masks.by_id("M1_quarters_4"), config)
    assert excinfo.value.reason_code == clip["expected_rejection_code"]


def test_sample_rate_below_44100_is_rejected(tmp_path):
    path = tmp_path / "low.wav"
    write_wav_pcm24(path, np.zeros(22050 * 9, dtype=np.float64) + 0.1, 22050)
    with pytest.raises(ClipRejected) as excinfo:
        ingest(path, "EV")
    assert excinfo.value.reason_code == "SAMPLE_RATE_TOO_LOW"
