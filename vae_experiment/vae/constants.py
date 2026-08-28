"""Hard-coded structural constants (Section 18, "Hard-coded" column).

Changing anything in this file is a *new experiment*, not a configuration
change.  These are deliberately not in the versioned config file so that they
cannot be swept; they are covered by ``code_version`` inside ``EngineVersion``.

The Section 18 hard-coded list is: 44.1 kHz; mono; 4/4; constant tempo;
English/CMUdict; STFT N=2048 hop=256; spectral-flux ODF; eighth-note
subdivision lattice; one pocket per clip; arithmetic-mean aggregation;
syllabic alignment only.  Everything below either *is* one of those or is a
structural detail of one of them (e.g. the ODF median-filter length is part of
"spectral-flux ODF").
"""

from types import MappingProxyType

# --- Canonical audio (Section 3) ---------------------------------------------
SAMPLE_RATE_HZ = 44100
CHANNELS = 1
NORMALIZE_PEAK_DBFS = -3.0

# --- STFT / ODF (Section 4) ---------------------------------------------------
STFT_N = 2048
STFT_HOP = 256
HOP_SECONDS = STFT_HOP / SAMPLE_RATE_HZ  # 5.8050 ms
WINDOW = "hann_periodic"

# Median-filter normalisation of the spectral flux, and the fixed adaptive
# onset threshold.  Structural parts of "spectral-flux ODF" / "fixed adaptive
# threshold" in the Section 4 table, hence hard-coded rather than swept.
ODF_MEDIAN_FRAMES = 17           # ~98.7 ms, odd so the window is symmetric
ONSET_THRESHOLD_MEDIAN_FRAMES = 17
ONSET_THRESHOLD_DELTA = 0.06     # absolute floor on the normalised ODF
ONSET_THRESHOLD_LAMBDA = 1.30    # multiplier on the local median
MIN_INTER_ONSET_S = 0.030        # Section 4: min inter-onset 30 ms
# A transient that makes flux rise at frame m entered frame m's analysis window
# but not frame m-1's, so it lies in [(m-1)*hop + N, m*hop + N) — one hop wide.
# The flux PEAK can trail first entry by a frame or two as more of the transient
# enters the window, so the refinement search span is widened by this many frames.
ONSET_REFINE_LAG_FRAMES = 4

# --- Attack sharpness (Section 4) --------------------------------------------
ATTACK_WINDOW_S = 0.050          # 50 ms post-onset window
ATTACK_LOW_FRAC = 0.10           # 10-90% rise time
ATTACK_HIGH_FRAC = 0.90
ATTACK_ENERGY_FRAME = 64         # short-time energy frame, samples
ATTACK_ENERGY_HOP = 16

# --- Tempo / beat grid (Section 4) -------------------------------------------
TEMPO_MIN_BPM = 70.0
TEMPO_MAX_BPM = 140.0
TEMPO_DRIFT_MAX_FRAC = 0.02      # Section 2: constant within +/-2%
BEAT_PHASE_SEARCH_STEPS = 512    # deterministic phase sweep resolution

# --- Metre / lattice (Section 5, Section 18) ---------------------------------
BEATS_PER_BAR = 4                # 4/4 only
SUBDIVISIONS_PER_BEAT = 2        # eighth-note subdivision lattice
BARS_PER_MASK = 2
MASK_POSITION_COUNT = BEATS_PER_BAR * SUBDIVISIONS_PER_BEAT * BARS_PER_MASK  # 16

# --- Section 2 admission ------------------------------------------------------
DURATION_MIN_S = 8.0
DURATION_MAX_S = 12.0
SOURCE_PEAK_MAX_DBFS = -1.0
MIN_SOURCE_SAMPLE_RATE_HZ = 44100
MIN_SOURCE_BIT_DEPTH = 16
# "Audible percussive or clearly articulated harmonic pulse" is operationalised
# as two conditions, because either alone is trivially satisfiable:
#   * a pulse must be PRESENT  -> a minimum fraction of grid beats carry an onset;
#   * a pulse must be ARTICULATED -> the onset rate must be one an articulation
#     lattice can actually hold.  An ambient wash yields threshold crossings at
#     ~20/s, which no 4/4 eighth lattice at <=140 BPM can express (max 4.67/s), so
#     density above the lattice is texture being detected, not articulation.
MIN_GRID_MATCH_RATE = 0.60
MAX_ONSETS_PER_EIGHTH = 1.5

# --- Phonology (Section 9) ----------------------------------------------------
# ARPAbet diphthongs, used only to select F_min via DIPHTHONG_FACTOR (Section 8).
# This is a phone-inventory fact about the CMUdict symbol set, not measured data.
ARPABET_DIPHTHONGS = ("AW", "AY", "EY", "OW", "OY")

STRESS_PRIMARY = "PRIMARY"
STRESS_SECONDARY = "SECONDARY"
STRESS_UNSTRESSED = "UNSTRESSED"
STRESS_DIGIT_MAP = MappingProxyType(
    {"1": STRESS_PRIMARY, "2": STRESS_SECONDARY, "0": STRESS_UNSTRESSED}
)

METRICAL_STRONG = "STRONG"
METRICAL_MEDIUM = "MEDIUM"
METRICAL_WEAK = "WEAK"
METRICAL_STRENGTHS = (METRICAL_STRONG, METRICAL_MEDIUM, METRICAL_WEAK)

# Fixed 3x3 stress-vs-metrical-strength lookup (Section 10, s_stress).
# Rows: syllable stress.  Columns: slot metrical strength.  Hard-coded, not tuned.
STRESS_STRENGTH_TABLE = MappingProxyType({
    (STRESS_PRIMARY, METRICAL_STRONG): 1.00,
    (STRESS_PRIMARY, METRICAL_MEDIUM): 0.60,
    (STRESS_PRIMARY, METRICAL_WEAK): 0.00,
    (STRESS_SECONDARY, METRICAL_STRONG): 0.60,
    (STRESS_SECONDARY, METRICAL_MEDIUM): 1.00,
    (STRESS_SECONDARY, METRICAL_WEAK): 0.60,
    (STRESS_UNSTRESSED, METRICAL_STRONG): 0.00,
    (STRESS_UNSTRESSED, METRICAL_MEDIUM): 0.60,
    (STRESS_UNSTRESSED, METRICAL_WEAK): 1.00,
})

# --- Anchor methods (Section 6) ----------------------------------------------
METHOD_GRID_ONLY = "GRID_ONLY"
METHOD_ONSET_SUPPORTED = "ONSET_SUPPORTED"

# --- Feasibility tiers (Section 8) -------------------------------------------
TIER_HARD_INFEASIBLE = "HARD_INFEASIBLE"
TIER_BELOW_FLOOR = "BELOW_FLOOR"
TIER_BORDERLINE = "BORDERLINE"
TIER_OK = "OK"

# --- Verdicts (Section 10) ----------------------------------------------------
VERDICT_ACCEPT = "ACCEPT"
VERDICT_REJECT_HARD = "REJECT_HARD"
VERDICT_ABSTAIN_OOV = "ABSTAIN_OOV"

# --- Provenance / conditions (Section 20) ------------------------------------
PROVENANCE_HEAR = "HEAR"
PROVENANCE_ORACLE = "ORACLE"
CONDITIONS = ("A", "B", "C", "C_FLAT", "C_SHUFFLED", "C_ORACLE")

# --- Resampler ----------------------------------------------------------------
RESAMPLER_VERSION = "polyphase-windowed-sinc-v1"
