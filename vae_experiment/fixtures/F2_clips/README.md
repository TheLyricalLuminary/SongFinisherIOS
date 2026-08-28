# F2 — 20 accompaniment clips meeting Section 2, ≥12 with interval asymmetry

**Status: UNPOPULATED — BLOCKED ON SOURCE MATERIAL.**

F2 is real recorded accompaniment. It cannot be produced offline from anything
in this environment, and it must not be simulated: the hypothesis under test is
that an envelope derived from *accompaniment audio* predicts articulatory
preference, so synthetic audio would test the pipeline and nothing else.

## What is required

20 clips, each satisfying every Section 2 row:

| Requirement | Value |
|---|---|
| Content | Accompaniment only, no vocal, no vocal-range lead melody |
| Duration | 8.0–12.0 s |
| Meter | 4/4 only |
| Tempo | 70–140 BPM, constant within ±2% |
| Pulse | Audible percussive or clearly articulated harmonic pulse |
| Format | WAV, PCM, ≥44.1 kHz, ≥16-bit |
| Level | Peak ≤ −1.0 dBFS, no clipped samples |
| Language | English (US) |
| Interval asymmetry | ≥12 of the 20 must support an authored slot mask whose interval sequence has `max(I)/min(I) ≥ ASYMMETRY_MIN` |

Content, meter and language are authored metadata: the pipeline cannot verify
them and records them as declared. Everything else is checked and enforced —
`vae.canonical.check_source_format` for format, duration and level;
`vae.hear.hear_with_log` for tempo range, drift and pulse. Failing clips are
**excluded and logged**, never degraded (Section 2).

## Per-clip manifest fields required

`clip_id`, `file`, `authored_meter`, `authored_content`, `authored_language`,
`slot_mask_id` (which F6 mask is authored for this clip — Section 5 requires the
mask to be authored *per clip*), and `source_attribution`.

## Pipeline exercise stand-in

`fixtures/F2_SYNTH_pipeline_exercise/` holds synthesised clips used **only** to
exercise SHAPE, the conditions and RANK end-to-end. They are not F2, are never
counted as F2, and no result computed from them is a result about the
hypothesis. Every runner that touches them stamps `uses_synthetic_fixtures` on
its output.
