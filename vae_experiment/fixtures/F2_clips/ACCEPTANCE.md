# F2 — acceptance requirements for the accompaniment clips

**You supply the recordings.** Nothing synthetic is substituted, and the importer
has no path that accepts generated audio as F2.

## How to submit

1. Put the WAV files in `fixtures/F2_clips/intake/`.
2. List each one in `fixtures/F2_clips/intake_f2.csv`.
3. Run `python3 tools/import_f2.py`.

The importer measures tempo, drift, pulse and asymmetry itself and **rejects**
failing clips with a reason code. Section 2 rejection is mandatory — a clip that
fails is excluded, never repaired.

## How many

**20 clips, of which at least 12 must show interval asymmetry** (`max(I)/min(I) ≥
ASYMMETRY_MIN`, currently 1.5, measured on the realised envelope). Fewer than
that and the manifest is written `INCOMPLETE`.

## Per-clip requirements (Section 2)

| Requirement | Value | Checked by |
|---|---|---|
| Content | Accompaniment only, no vocal, no vocal-range lead melody | **You declare it** — not verifiable |
| Duration | 8.0–12.0 s | Importer |
| Meter | 4/4 only | **You declare it** — not verifiable |
| Tempo | 70–140 BPM | Importer |
| Tempo stability | constant within ±2% | Importer (halves compared) |
| Pulse | audible percussive or clearly articulated harmonic pulse | Importer (grid-match rate ≥ 0.60 **and** onset density ≤ 1.5 per eighth) |
| Format | WAV, PCM, ≥44.1 kHz, ≥16-bit | Importer |
| Level | peak ≤ −1.0 dBFS, no clipped samples | Importer |
| Language | English (US) | **You declare it** — not verifiable |
| Interval asymmetry | supports an authored mask with `max(I)/min(I) ≥ ASYMMETRY_MIN` | Importer |

The three declared fields are recorded as declarations and stamped as such in the
manifest. The pipeline cannot check them and does not pretend to.

## CSV columns

| Column | Meaning |
|---|---|
| `file` | filename inside `intake/` |
| `clip_id` | short stable id, e.g. `F2_01` |
| `slot_mask_id` | which F6 mask is authored **for this clip** (Section 5 requires the mask to be authored per clip) |
| `authored_meter` | `4/4` |
| `authored_content` | e.g. `accompaniment only, no vocal` |
| `authored_language` | `English (US)` |
| `source_attribution` | where the recording came from and under what rights |

## Choosing `slot_mask_id`

The F6 inventory has 8 masks. For a clip intended to carry the primary contrast,
pick one of the four asymmetric masks, and make sure the pair of clips you intend
to use as the two contexts of a trial use **mirror** masks:

* `M5_short_first_4` ↔ `M6_long_first_4` (4 slots)
* `M7_short_first_6` ↔ `M8_long_first_6` (6 slots)

Mirror pairs have identical metrical-strength sequences and opposite interval
sequences, which is what keeps `Score_B` constant across the two contexts of a
trial so that only the accompaniment differs.

The mask must fit inside the clip: its last eighth position must land before the
end of the audio at the clip's measured tempo.

## What happens after import

`manifest.json` is written with the measured properties of every accepted clip,
stamped `measurement_source: "HEAR"` to distinguish them from the
ground-truth-by-construction values the synthetic fixtures carry. F8 annotation
worksheets are then generated from that manifest.
