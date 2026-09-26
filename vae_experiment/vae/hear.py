"""HEAR — Section 4 deterministic feature set, Section 6 anchors.

Classical DSP only, no learned parameters: that is what makes the determinism
contract cheap (Section 4).  Downbeat / bar-phase identification is REMOVED
(Section 4, Section 19); metrical strength comes from the authored slot mask.

Implementation decisions taken where Section 4 is terse.  Each is deterministic,
carries no learned parameter, and is logged:

*   **Onset time refinement.**  A spectral-flux peak localises a transient only
    to its 2048-sample analysis window.  The onset time is therefore refined to
    the 10 % point of the short-time energy rise inside that window — the same
    10 % point the Section 4 attack-sharpness definition already uses.  Without
    this the reported onset carries up to 23 ms of window bias, which the
    5.8 ms F1 gate would not survive.
*   **Tempo.**  ODF autocorrelation read as a harmonic comb over a fine period
    grid inside 70-140 BPM.  Still a single global estimate from the ODF
    autocorrelation; the comb simply reads the same ACF at h*T for h = 1..H so
    that period resolution is not capped by the 5.805 ms frame lag.
*   **Beat phase.**  The objective is exactly Section 4's "maximises summed
    onset salience within +/-W_match".  That objective is piecewise-constant in
    phase, so ties (within epsilon_num) are broken by minimising the
    salience-weighted squared residual, then by the smaller phase.  Documented
    tie-break, not a different objective.
"""

from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from .config import Config
from .constants import (
    ATTACK_ENERGY_FRAME,
    ATTACK_ENERGY_HOP,
    ATTACK_HIGH_FRAC,
    ATTACK_LOW_FRAC,
    ATTACK_WINDOW_S,
    BEAT_PHASE_SEARCH_STEPS,
    METHOD_GRID_ONLY,
    METHOD_ONSET_SUPPORTED,
    MAX_ONSETS_PER_EIGHTH,
    MIN_GRID_MATCH_RATE,
    MIN_INTER_ONSET_S,
    ODF_MEDIAN_FRAMES,
    ONSET_REFINE_LAG_FRAMES,
    ONSET_THRESHOLD_DELTA,
    ONSET_THRESHOLD_LAMBDA,
    ONSET_THRESHOLD_MEDIAN_FRAMES,
    PROVENANCE_HEAR,
    SAMPLE_RATE_HZ,
    STFT_HOP,
    STFT_N,
    SUBDIVISIONS_PER_BEAT,
    TEMPO_DRIFT_MAX_FRAC,
    TEMPO_MAX_BPM,
    TEMPO_MIN_BPM,
)
from .contracts import AcousticEvent, AcousticEvidence, Anchor, CanonicalAudio
from .errors import ClipRejected
from .slots import SlotMask

# Tempo comb-search resolution.  Structural, not swept.
TEMPO_GRID_BPM_STEP = 0.01
TEMPO_COMB_HARMONICS = 8


# --------------------------------------------------------------------------- #
# STFT and onset detection function
# --------------------------------------------------------------------------- #

def hann_periodic(n: int) -> np.ndarray:
    """Periodic Hann, the STFT convention (constants.WINDOW)."""
    return 0.5 - 0.5 * np.cos(2.0 * np.pi * np.arange(n, dtype=np.float64) / n)


def stft_magnitude(pcm: np.ndarray) -> np.ndarray:
    """Hann, N=2048, hop=256 (Section 4).  Returns (n_frames, N/2 + 1) float64."""
    x = np.asarray(pcm, dtype=np.float64)
    if x.size < STFT_N:
        x = np.concatenate((x, np.zeros(STFT_N - x.size, dtype=np.float64)))
    n_frames = 1 + (x.size - STFT_N) // STFT_HOP
    window = hann_periodic(STFT_N)
    frames = np.lib.stride_tricks.sliding_window_view(x, STFT_N)[:: STFT_HOP][:n_frames]
    return np.abs(np.fft.rfft(frames * window, axis=1)).astype(np.float64)


def median_filter_1d(x: np.ndarray, width: int) -> np.ndarray:
    """Centred median with edge replication.  Deterministic, no SciPy."""
    half = width // 2
    padded = np.pad(np.asarray(x, dtype=np.float64), (half, half), mode="edge")
    windows = np.lib.stride_tricks.sliding_window_view(padded, width)
    return np.median(windows, axis=1)


def onset_detection_function(mag: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Half-wave-rectified spectral flux, L1 over bins 1..N/2, median-normalised.

    Returns ``(odf_normalised, raw_flux)``; the normalised curve is in [0, 1] and
    is what the salience field reports (Section 4: "Normalized flux at peak").
    """
    diff = np.diff(mag[:, 1:], axis=0)                  # bins 1..N/2, skip DC
    flux = np.sum(np.maximum(diff, 0.0), axis=1, dtype=np.float64)
    flux = np.concatenate(([0.0], flux))                # align to frame index
    detrended = np.maximum(flux - median_filter_1d(flux, ODF_MEDIAN_FRAMES), 0.0)
    peak = float(np.max(detrended)) if detrended.size else 0.0
    odf = detrended / peak if peak > 0.0 else detrended
    return odf, flux


# --------------------------------------------------------------------------- #
# Onset peaks (with rejection log) and attack sharpness
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class RejectedPeak:
    frame: int
    time_s: float
    salience: float
    reason: str


def _short_time_energy(pcm: np.ndarray) -> np.ndarray:
    """Short-time energy at a fine hop, used for onset refinement and rise time."""
    x = np.asarray(pcm, dtype=np.float64)
    if x.size < ATTACK_ENERGY_FRAME:
        x = np.concatenate((x, np.zeros(ATTACK_ENERGY_FRAME - x.size, dtype=np.float64)))
    frames = np.lib.stride_tricks.sliding_window_view(x, ATTACK_ENERGY_FRAME)[
        ::ATTACK_ENERGY_HOP
    ]
    return np.sum(frames * frames, axis=1, dtype=np.float64)


def _search_span(energy: np.ndarray, frame: int) -> tuple[int, int]:
    """The interval that must contain the transient behind the flux peak.

    Half-wave-rectified spectral flux at frame m compares frame m's magnitude
    spectrum with frame m-1's.  A transient can only raise it by being inside
    frame m's window and outside frame m-1's, which pins it to
    ``[(m-1)*hop + N, m*hop + N)`` — one hop wide.  The flux peak can trail first
    entry by a frame or two, so the lower bound is relaxed by
    ``ONSET_REFINE_LAG_FRAMES``.  This is far tighter than searching the whole
    2048-sample window and is what keeps anchor error inside the Section 23
    step-2 gate.
    """
    lo_sample = max(0, (frame - 1 - ONSET_REFINE_LAG_FRAMES) * STFT_HOP + STFT_N)
    hi_sample = frame * STFT_HOP + STFT_N
    lo = min(lo_sample // ATTACK_ENERGY_HOP, max(0, energy.size - 2))
    hi = min(energy.size, max(lo + 2, hi_sample // ATTACK_ENERGY_HOP))
    return lo, hi


def _attack_start_index(span: np.ndarray) -> int:
    """Index of the attack that produced ``span``'s peak, by backtracking from it.

    Scanning *forward* for a 10 %-of-peak crossing does not work on real
    accompaniment.  Two things defeat it: the baseline is modulated rather than
    flat (a sustained pad's instantaneous energy beats as its partials
    interfere), and the transient may be quiet relative to that baseline.  Either
    can put the span's first sample above the threshold, which pins the onset to
    the window start — tens of milliseconds early.

    Backtracking is immune to both: find the peak, then walk back to the last
    sample at or below the 10 % point of the rise *leading to that peak*.  The
    reference floor is the minimum on the rising side only, so energy after the
    peak cannot move it.
    """
    peak_index = int(np.argmax(span))
    rising = span[: peak_index + 1]
    if rising.size < 2:
        return peak_index
    floor = float(np.min(rising))
    threshold = floor + ATTACK_LOW_FRAC * (float(span[peak_index]) - floor)
    below = np.flatnonzero(rising <= threshold)
    return int(below[-1]) if below.size else 0


def _refine_onset_sample(energy: np.ndarray, frame: int) -> int:
    """Locate the transient inside the flux peak's analysis window.

    A spectral-flux peak localises a transient only to its 2048-sample analysis
    window: the ODF rises as soon as the transient enters the *end* of that
    window, which is up to 46 ms before the event.  The onset is therefore
    refined to the 10 % point of the energy rise — the same 10 % point the
    Section 4 attack-sharpness definition uses.
    """
    lo, hi = _search_span(energy, frame)
    span = energy[lo:hi]
    if span.size == 0 or float(np.max(span)) <= 0.0:
        return frame * STFT_HOP
    idx = lo + _attack_start_index(span)
    return idx * ATTACK_ENERGY_HOP + ATTACK_ENERGY_FRAME // 2


def _rise_time_ms(energy: np.ndarray, onset_sample: int) -> float:
    """10-90 % rise time of short-time energy in a 50 ms post-onset window.

    Measured from the local floor, for the same reason as ``_rise_thresholds``.
    """
    lo = onset_sample // ATTACK_ENERGY_HOP
    hi = min(energy.size, lo + int(round(ATTACK_WINDOW_S * SAMPLE_RATE_HZ / ATTACK_ENERGY_HOP)))
    span = energy[lo:hi]
    if span.size < 2 or float(np.max(span)) <= 0.0:
        return 0.0
    peak_index = int(np.argmax(span))
    floor = float(np.min(span[: peak_index + 1])) if peak_index else float(span[0])
    rise = float(span[peak_index]) - floor
    if rise <= 0.0:
        return 0.0
    low_hits = np.flatnonzero(span >= floor + ATTACK_LOW_FRAC * rise)
    high_hits = np.flatnonzero(span >= floor + ATTACK_HIGH_FRAC * rise)
    if low_hits.size == 0 or high_hits.size == 0:
        return 0.0
    n_hops = max(0, int(high_hits[0]) - int(low_hits[0]))
    return 1000.0 * n_hops * ATTACK_ENERGY_HOP / SAMPLE_RATE_HZ


def pick_onsets(
    odf: np.ndarray, pcm: np.ndarray
) -> tuple[list[AcousticEvent], list[RejectedPeak]]:
    """Fixed adaptive threshold, min inter-onset 30 ms (Section 4).

    Every ODF peak is reported, accepted or rejected, with a rejection reason
    (Section 16: "every ODF peak including rejected ones").
    """
    energy = _short_time_energy(pcm)
    threshold = ONSET_THRESHOLD_DELTA + ONSET_THRESHOLD_LAMBDA * median_filter_1d(
        odf, ONSET_THRESHOLD_MEDIAN_FRAMES
    )

    candidates: list[tuple[int, float, str]] = []
    for m in range(1, odf.size - 1):
        if not (odf[m] >= odf[m - 1] and odf[m] > odf[m + 1]):
            continue
        if odf[m] < threshold[m]:
            candidates.append((m, float(odf[m]), "BELOW_ADAPTIVE_THRESHOLD"))
        else:
            candidates.append((m, float(odf[m]), ""))

    # Greedy min-IOI enforcement in descending salience, frame index as the
    # lexicographic tie-break.  No dict/set iteration order anywhere.
    order = sorted(
        (c for c in candidates if not c[2]), key=lambda c: (-c[1], c[0])
    )
    accepted_frames: list[int] = []
    rejected: list[RejectedPeak] = [
        RejectedPeak(m, _frame_time(m), s, r) for m, s, r in candidates if r
    ]
    min_ioi_frames = MIN_INTER_ONSET_S * SAMPLE_RATE_HZ / STFT_HOP
    for frame, salience, _ in order:
        if any(abs(frame - a) < min_ioi_frames for a in accepted_frames):
            rejected.append(RejectedPeak(frame, _frame_time(frame), salience, "MIN_INTER_ONSET"))
            continue
        accepted_frames.append(frame)

    events: list[AcousticEvent] = []
    for i, frame in enumerate(sorted(accepted_frames)):
        onset_sample = _refine_onset_sample(energy, frame)
        events.append(
            AcousticEvent(
                id=f"E{i:04d}",
                time_s=onset_sample / SAMPLE_RATE_HZ,
                salience=float(odf[frame]),
                rise_time_ms=_rise_time_ms(energy, onset_sample),
                delta_s=None,
                matched_beat_index=None,
            )
        )
    rejected.sort(key=lambda r: (r.frame, r.reason))
    return events, rejected


def _frame_time(frame: int) -> float:
    """Frame reference time = window start.  Onsets are refined off this."""
    return frame * STFT_HOP / SAMPLE_RATE_HZ


# --------------------------------------------------------------------------- #
# Tempo and beat grid
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class TempoCandidate:
    bpm: float
    score: float


def _autocorrelation(odf: np.ndarray) -> np.ndarray:
    """Unbiased ODF autocorrelation, zero-mean, normalised to r[0] = 1."""
    x = np.asarray(odf, dtype=np.float64)
    x = x - np.mean(x, dtype=np.float64)
    n = x.size
    full = np.correlate(x, x, mode="full")[n - 1 :]
    counts = np.arange(n, 0, -1, dtype=np.float64)
    r = full / counts
    return r / r[0] if r[0] > 0.0 else r


def estimate_tempo(odf: np.ndarray) -> tuple[float, list[TempoCandidate]]:
    """Single global tempo from the ODF autocorrelation, restricted to 70-140 BPM.

    The ACF is read as a harmonic comb so that period resolution is not capped by
    the frame lag; candidates and their scores are returned for Section 16.
    """
    acf = _autocorrelation(odf)
    frame_rate = SAMPLE_RATE_HZ / STFT_HOP
    bpms = np.arange(
        TEMPO_MIN_BPM, TEMPO_MAX_BPM + TEMPO_GRID_BPM_STEP / 2.0, TEMPO_GRID_BPM_STEP,
        dtype=np.float64,
    )
    periods = 60.0 / bpms
    scores = np.zeros(bpms.size, dtype=np.float64)
    used = np.zeros(bpms.size, dtype=np.float64)
    for h in range(1, TEMPO_COMB_HARMONICS + 1):
        lags = periods * h * frame_rate
        valid = lags < acf.size - 1
        idx = np.floor(lags).astype(np.int64)
        frac = lags - idx
        lo = np.clip(idx, 0, acf.size - 1)
        hi = np.clip(idx + 1, 0, acf.size - 1)
        interp = acf[lo] * (1.0 - frac) + acf[hi] * frac
        scores += np.where(valid, interp, 0.0)
        used += valid.astype(np.float64)
    scores = np.divide(scores, np.maximum(used, 1.0))

    best = int(np.argmax(scores))
    bpm = float(bpms[best])

    candidates: list[TempoCandidate] = []
    for i in range(1, scores.size - 1):
        if scores[i] >= scores[i - 1] and scores[i] > scores[i + 1]:
            candidates.append(TempoCandidate(float(bpms[i]), float(scores[i])))
    candidates.sort(key=lambda c: (-c.score, c.bpm))
    return bpm, candidates[:10]


def build_beat_grid(
    events: list[AcousticEvent], bpm: float, duration_s: float, config: Config
) -> tuple[np.ndarray, float]:
    """Constant-tempo grid whose phase maximises summed onset salience.

    Returns ``(beat_times_s, phase_s)``.
    """
    period = 60.0 / bpm
    times = np.array([e.time_s for e in events], dtype=np.float64)
    saliences = np.array([e.salience for e in events], dtype=np.float64)
    n_beats = max(1, int(np.floor(duration_s / period)) + 1)

    best_phase = 0.0
    best_score = -1.0
    best_residual = float("inf")
    for step in range(BEAT_PHASE_SEARCH_STEPS):
        phase = step * period / BEAT_PHASE_SEARCH_STEPS
        grid = phase + period * np.arange(n_beats, dtype=np.float64)
        score, residual = _grid_score(grid, times, saliences, config.W_match)
        better = score > best_score + config.epsilon_num
        tied = abs(score - best_score) <= config.epsilon_num
        if better or (tied and residual < best_residual - config.epsilon_num):
            best_phase, best_score, best_residual = phase, score, residual
    return best_phase + period * np.arange(n_beats, dtype=np.float64), best_phase


def _grid_score(
    grid: np.ndarray, times: np.ndarray, saliences: np.ndarray, w_match: float
) -> tuple[float, float]:
    """Summed salience of the best-matching onset per beat, plus its residual."""
    if times.size == 0:
        return 0.0, float("inf")
    delta = np.abs(times[None, :] - grid[:, None])
    within = delta <= w_match
    masked = np.where(within, saliences[None, :], -1.0)
    best = np.argmax(masked, axis=1)
    rows = np.arange(grid.size)
    hit = masked[rows, best] >= 0.0
    score = float(np.sum(np.where(hit, saliences[best], 0.0), dtype=np.float64))
    residual = float(
        np.sum(np.where(hit, saliences[best] * delta[rows, best] ** 2, 0.0), dtype=np.float64)
    )
    return score, residual


def match_onsets_to_grid(
    events: list[AcousticEvent], grid: np.ndarray, w_match: float
) -> list[AcousticEvent]:
    """Attach the microtiming residual delta = t_onset - t_grid (Section 4)."""
    matched: list[AcousticEvent] = []
    for event in events:
        if grid.size:
            distances = np.abs(grid - event.time_s)
            nearest = int(np.argmin(distances))
            if distances[nearest] <= w_match:
                matched.append(
                    AcousticEvent(
                        id=event.id,
                        time_s=event.time_s,
                        salience=event.salience,
                        rise_time_ms=event.rise_time_ms,
                        delta_s=float(event.time_s - grid[nearest]),
                        matched_beat_index=nearest,
                    )
                )
                continue
        matched.append(event)
    return matched


# --------------------------------------------------------------------------- #
# Anchors (Section 6)
# --------------------------------------------------------------------------- #

def derive_anchors(
    events: list[AcousticEvent],
    grid: np.ndarray,
    bpm: float,
    mask: SlotMask,
    config: Config,
) -> tuple[Anchor, ...]:
    """Section 6 verbatim.

        supporting = { onsets o : |t_o - g_k| <= W_match }
        empty  -> anchor = g_k, GRID_ONLY,       sigma = SIGMA_GRID_ONLY
        else   -> salience-weighted mean of t_o, ONSET_SUPPORTED,
                  sigma = sqrt(spread^2 + floor^2)
    """
    anchors: list[Anchor] = []
    for slot_index, g_k in enumerate(mask.slot_times(grid[0] if grid.size else 0.0, bpm)):
        supporting = [e for e in events if abs(e.time_s - g_k) <= config.W_match]
        if not supporting:
            anchors.append(
                Anchor(
                    slot_index=slot_index,
                    time_s=float(g_k),
                    sigma_s=float(config.SIGMA_GRID_ONLY),
                    method=METHOD_GRID_ONLY,
                    supporting_event_ids=(),
                    rise_time_ms=0.0,
                )
            )
            continue

        times = np.array([e.time_s for e in supporting], dtype=np.float64)
        weights = np.array([e.salience for e in supporting], dtype=np.float64)
        total = float(np.sum(weights, dtype=np.float64))
        if total <= 0.0:                       # degenerate: fall back to unweighted
            weights = np.ones_like(weights)
            total = float(weights.size)
        anchor_time = float(np.sum(weights * times, dtype=np.float64) / total)
        variance = float(
            np.sum(weights * (times - anchor_time) ** 2, dtype=np.float64) / total
        )
        spread = float(np.sqrt(max(variance, 0.0)))
        rises = np.array([e.rise_time_ms for e in supporting], dtype=np.float64)
        mean_rise_ms = float(np.sum(weights * rises, dtype=np.float64) / total)
        floor = config.SIGMA_FLOOR_BASE + config.SIGMA_ATTACK_COEF * (mean_rise_ms / 1000.0)
        anchors.append(
            Anchor(
                slot_index=slot_index,
                time_s=anchor_time,
                sigma_s=float(np.sqrt(spread * spread + floor * floor)),
                method=METHOD_ONSET_SUPPORTED,
                supporting_event_ids=tuple(sorted(e.id for e in supporting)),
                rise_time_ms=mean_rise_ms,
            )
        )
    return tuple(anchors)


# --------------------------------------------------------------------------- #
# Section 2 admission checks that need the ODF, and the stage entry point
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class HearLog:
    """Section 16 HEAR logging.  Derived deterministically; not part of Section 20."""

    audio_id: str
    tempo_bpm: float
    tempo_candidates: tuple[TempoCandidate, ...]
    tempo_first_half_bpm: float
    tempo_second_half_bpm: float
    tempo_drift_frac: float
    beat_phase_s: float
    n_beats: int
    grid_match_rate: float
    onset_density_per_eighth: float
    n_onsets: int
    rejected_peaks: tuple[RejectedPeak, ...]
    onset_deltas_s: tuple[float, ...]
    grid_only_slot_count: int


def analyse(pcm: np.ndarray) -> tuple[np.ndarray, np.ndarray, list[AcousticEvent], list[RejectedPeak]]:
    mag = stft_magnitude(pcm)
    odf, flux = onset_detection_function(mag)
    events, rejected = pick_onsets(odf, pcm)
    return odf, flux, events, rejected


def admit_clip(pcm: np.ndarray, source_path: str) -> tuple[float, float]:
    """Section 2 checks requiring analysis: tempo range, +/-2 % drift, audible pulse.

    Raises ``ClipRejected``.  There is no graceful degradation.
    """
    odf, _flux, events, _rejected = analyse(pcm)
    bpm, _candidates = estimate_tempo(odf)
    if not TEMPO_MIN_BPM <= bpm <= TEMPO_MAX_BPM:
        raise ClipRejected("TEMPO_OUT_OF_RANGE", f"{source_path}: {bpm:.2f} BPM")

    half = odf.size // 2
    bpm_a, _ = estimate_tempo(odf[:half])
    bpm_b, _ = estimate_tempo(odf[half:])
    drift = abs(bpm_a - bpm_b) / ((bpm_a + bpm_b) / 2.0)
    if drift > TEMPO_DRIFT_MAX_FRAC:
        raise ClipRejected(
            "TEMPO_DRIFT", f"{source_path}: {100.0 * drift:.2f}% > {100.0 * TEMPO_DRIFT_MAX_FRAC}%"
        )
    return bpm, drift


def onset_density_per_eighth(n_onsets: int, bpm: float, duration_s: float) -> float:
    """Onsets per eighth-note lattice position (Section 2 "clearly articulated")."""
    eighth = (60.0 / bpm) / SUBDIVISIONS_PER_BEAT
    positions = duration_s / eighth
    return n_onsets / positions if positions > 0.0 else float("inf")


def grid_match_rate(events: list[AcousticEvent], grid: np.ndarray, w_match: float) -> float:
    if grid.size == 0:
        return 0.0
    times = np.array([e.time_s for e in events], dtype=np.float64)
    if times.size == 0:
        return 0.0
    hits = np.sum(np.min(np.abs(times[None, :] - grid[:, None]), axis=1) <= w_match)
    return float(hits) / float(grid.size)


def hear(audio: CanonicalAudio, mask: SlotMask, config: Config) -> AcousticEvidence:
    """``hear(CanonicalAudio, SlotMask) -> AcousticEvidence`` (Section 21).

    Pure: no I/O, no globals, no history, no RNG, no wall-clock.
    """
    evidence, _log = hear_with_log(audio, mask, config)
    return evidence


def hear_with_log(
    audio: CanonicalAudio, mask: SlotMask, config: Config
) -> tuple[AcousticEvidence, HearLog]:
    pcm = np.asarray(audio.pcm, dtype=np.float64)
    duration_s = pcm.size / SAMPLE_RATE_HZ

    odf, _flux, events, rejected = analyse(pcm)
    bpm, candidates = estimate_tempo(odf)
    if not TEMPO_MIN_BPM <= bpm <= TEMPO_MAX_BPM:
        raise ClipRejected("TEMPO_OUT_OF_RANGE", f"{audio.source_path}: {bpm:.2f} BPM")

    half = odf.size // 2
    bpm_a, _ = estimate_tempo(odf[:half])
    bpm_b, _ = estimate_tempo(odf[half:])
    drift = abs(bpm_a - bpm_b) / ((bpm_a + bpm_b) / 2.0)
    if drift > TEMPO_DRIFT_MAX_FRAC:
        raise ClipRejected(
            "TEMPO_DRIFT",
            f"{audio.source_path}: {100.0 * drift:.2f}% > {100.0 * TEMPO_DRIFT_MAX_FRAC}%",
        )

    grid, phase = build_beat_grid(events, bpm, duration_s, config)
    matched = match_onsets_to_grid(events, grid, config.W_match)
    rate = grid_match_rate(matched, grid, config.W_match)
    if rate < MIN_GRID_MATCH_RATE:
        raise ClipRejected(
            "NO_AUDIBLE_PULSE",
            f"{audio.source_path}: grid-match rate {rate:.2f} < {MIN_GRID_MATCH_RATE}",
        )
    density = onset_density_per_eighth(len(matched), bpm, duration_s)
    if density > MAX_ONSETS_PER_EIGHTH:
        raise ClipRejected(
            "NO_AUDIBLE_PULSE",
            f"{audio.source_path}: {density:.2f} onsets per eighth-note position exceeds "
            f"{MAX_ONSETS_PER_EIGHTH}; the detector is firing on texture, not articulation",
        )

    anchors = derive_anchors(matched, grid, bpm, mask, config)
    evidence = AcousticEvidence(
        audio_id=audio.audio_id,
        engine_version=audio.engine_version,
        provenance=PROVENANCE_HEAR,
        tempo_bpm=bpm,
        beat_times_s=tuple(float(t) for t in grid),
        slot_mask_id=mask.mask_id,
        anchors=anchors,
        events=tuple(matched),
    )
    log = HearLog(
        audio_id=audio.audio_id,
        tempo_bpm=bpm,
        tempo_candidates=tuple(candidates),
        tempo_first_half_bpm=bpm_a,
        tempo_second_half_bpm=bpm_b,
        tempo_drift_frac=drift,
        beat_phase_s=phase,
        n_beats=int(grid.size),
        grid_match_rate=rate,
        onset_density_per_eighth=density,
        n_onsets=len(matched),
        rejected_peaks=tuple(rejected),
        onset_deltas_s=tuple(e.delta_s for e in matched if e.delta_s is not None),
        grid_only_slot_count=sum(1 for a in anchors if a.method == METHOD_GRID_ONLY),
    )
    return evidence, log
