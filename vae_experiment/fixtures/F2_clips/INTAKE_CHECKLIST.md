# F2 intake checklist — what to supply for each clip

This is the hand-off sheet for the person supplying the audio. `ACCEPTANCE.md`
states the requirements; this file is the working checklist.

**Nothing here is generated.** No synthetic audio is substituted, no audio is
downloaded, and the importer has no path that accepts manufactured clips as F2.
Until real recordings arrive, F2 reports `UNPOPULATED`.

---

## What to supply

**20 distinct recordings**, of which **at least 12** must come out asymmetric
(`max(I)/min(I) ≥ ASYMMETRY_MIN`, currently 1.5, measured on the realised
envelope — the importer decides this, you don't have to).

Twenty is twenty *different* recordings. The importer rejects a repeat of the
same file, the same file renamed, and any two clips whose canonical audio is
identical. It cannot tell that twenty different exports of one performance are
one performance — that is what `source_attribution` is for.

## Where the audio should come from

Safest, in order:

1. **Original or self-authored accompaniment** you recorded or produced.
2. **Recordings you have explicit permission to use and retain** for this
   experiment — written permission you could produce later if asked.

Record the basis in `permission_note` for every clip — the importer now requires
it. If a clip came from somewhere you cannot describe in one line, it is not
ready to submit.

This checklist takes no position on the copyright status of commercial
recordings; that is a question for the experiment owner and, if needed, a
lawyer. What the record needs is that each clip's origin and permission basis
are written down before it enters the fixture.

---

## Per-clip form

Copy this block once per clip:

```
clip_id:
filename:
authored_meter: 4/4
authored_content: accompaniment only; no vocal; no vocal-range lead melody
authored_language: English (US)
slot_mask_id:
source_attribution:
permission_note:            <- REQUIRED; a blank one rejects the clip
```

`authored_meter`, `authored_content` and `authored_language` are **declarations**.
The pipeline cannot hear whether a clip has a vocal on it, and it does not
pretend to. It does require the declarations to be present and exactly right —
a missing or wrong one rejects the clip.

`permission_note` is **required**. A blank or whitespace-only value rejects the
clip as `PERMISSION_NOTE_MISSING` — a provenance gate, not an acoustic one, so a
clip excluded this way failed nothing about the recording itself. It is never
inferred from `source_attribution`: knowing where a recording came from is not a
statement that it may be used and retained, and that inference is precisely what
this gate exists to prevent. The field records **your stated basis** for use and
retention. Nothing verifies the claim, and nothing here makes a legal
determination that a source is or is not licensed.

Examples of a usable note:

* `self-authored; recorded by me 2026-02-14`
* `written permission from <rights holder>, 2026-01-30, retained in <location>`
* `CC0 / public domain dedication, <url>, retrieved 2026-02-01`

`slot_mask_id` must name one of the 8 masks in the F6 inventory. Use mirror pairs
for the two contexts of a trial: `M5_short_first_4` ↔ `M6_long_first_4`, or
`M7_short_first_6` ↔ `M8_long_first_6`.

---

## What the importer checks, so you don't have to

Supply the audio; these are measured and enforced, and a failing clip is
**rejected with a reason code**, never repaired:

| Property | Requirement | Reason code on failure |
|---|---|---|
| Container | WAV **PCM** (not IEEE float) | `NOT_PCM` |
| Sample rate | ≥ 44.1 kHz | `SAMPLE_RATE_TOO_LOW` |
| Bit depth | ≥ 16-bit | `BIT_DEPTH_TOO_LOW` |
| Clipping | no full-scale samples | `CLIPPED_SAMPLES` |
| Duration | 8.0–12.0 s | `DURATION_OUT_OF_RANGE` |
| Peak level | ≤ −1.0 dBFS | `LEVEL_TOO_HOT` |
| Not silent | — | `SILENT` |
| Tempo | 70–140 BPM | `TEMPO_OUT_OF_RANGE` |
| Tempo stability | constant within ±2% | `TEMPO_DRIFT` |
| Pulse present | ≥ 60% of grid beats carry an onset | `NO_AUDIBLE_PULSE` |
| Pulse articulated | ≤ 1.5 onsets per eighth | `NO_AUDIBLE_PULSE` (detail says which) |
| Distinct recording | not a repeat of another clip | `DUPLICATE_FILE`, `DUPLICATE_AUDIO`, `DUPLICATE_CLIP_ID` |
| Mask exists | `slot_mask_id` is in the F6 inventory | `UNKNOWN_SLOT_MASK` |
| Declarations | present and exact | `DECLARATION_MISSING`, `DECLARATION_INVALID` |
| Permission recorded | `permission_note` non-blank | `PERMISSION_NOTE_MISSING` |

### Practical notes

* **Export at −1 dBFS or lower.** A clip mastered to 0 dBFS will be rejected
  twice over, for level and for clipping. −3 dBFS is a comfortable target.
* **Keep the tempo fixed.** The importer compares the first and second halves of
  the clip and rejects more than 2% between them, so a ritardando or a live
  performance that breathes will not pass.
* **Trim to a whole number of bars** between 8 and 12 seconds. At 100 BPM, four
  bars is 9.6 s; at 120 BPM, five bars is 10 s.
* **Percussion helps.** A clip with no clear attack — a pad wash, a legato string
  bed — fails the pulse checks, because the detector is then firing on texture
  rather than articulation.

---

## Submitting

1. Put the WAV files in `fixtures/F2_clips/intake/`.
2. Fill one row per clip in `fixtures/F2_clips/intake_f2.csv`.
3. Run `python3 tools/import_f2.py`.
4. Read the rejections. Every one names the clip and why.

The manifest is written `INCOMPLETE` until 20 distinct clips pass with ≥12
asymmetric. `python3 tools/readiness.py` reports the same state, derived from the
manifest's contents rather than from anything the manifest claims about itself.
