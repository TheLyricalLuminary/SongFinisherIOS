# F8 — instructions for the two annotators and the adjudicator

Section 12 requires **two annotators working independently**, plus a **third
adjudicator** for disagreements greater than 20 ms. The oracle exists to be an
*independent* measurement of the same quantity HEAR estimates. If it is derived
from HEAR output — or if the two annotators confer — it stops being a control and
the Section 12 diagnostic becomes meaningless.

**Nothing in this repository can produce these annotations. They must be made by
people, by ear, in a DAW.**

## What each annotator produces, per clip

One worksheet file, generated for you by:

```bash
python3 tools/make_f8_worksheets.py --annotator A
```

Each worksheet lists the clip, its authored slot mask, and one row per slot. You
fill in two things:

1. **`beat_times_s`** — the time of every beat you hear, in seconds from the
   start of the file.
2. **`anchor_time_s`** — per slot, **where a sung vowel nucleus would
   perceptually land**.

### The anchor is not an onset time and not a grid time

This is the single most important instruction. Section 6 defines an anchor as
where a sung vowel *nucleus* would perceptually land. It is not:

* the attack transient of the drum or chord at that position,
* the mathematically exact grid position,
* the start of the note.

It is the perceptual centre of the moment a singer would land the vowel on. On a
sound with a slow attack this is typically **later** than the physical onset.

### Method

* Work in a DAW at a fixed zoom, with the clip at unity gain.
* Loop each slot region and place a marker where you would sing the vowel.
* Do **not** snap to a grid. Do **not** look at the waveform's transient markers
  as the answer; use your ear and check against the waveform afterwards.
* Do **not** consult the pipeline's output, another annotator's file, or any
  automatically detected onsets.
* Record times in seconds to at least millisecond precision.

## Adjudication

Run:

```bash
python3 tools/adjudicate_f8.py
```

It compares annotator A and annotator B slot by slot and reports every
disagreement. Slots differing by **more than 20 ms** must be resolved by a third
annotator, who marks them independently; their value is taken as final and the
slot is recorded in `adjudicated_slots`.

Slots within 20 ms are averaged, and the spread is carried through as the
annotation's `anchor_sigma_s`, so genuine annotator uncertainty reaches
`I_effective` rather than being discarded.

## What the tooling then produces

`adjudicate_f8.py` writes one `<audio_id>.<slot_mask_id>.json` per clip and mask,
in the schema the oracle branch already consumes. From there the existing
HEAR-vs-oracle diagnostic (Section 12, Section 16 cross-cut) runs unchanged and
reports `mean |anchor_HEAR − anchor_oracle|` per clip and per slot — the single
most useful diagnostic the experiment produces, and the thing that separates "our
DSP was wrong" from "the hypothesis is wrong".

The Section 25 R1 guard also runs: any clip whose HEAR anchors sit a systematic
whole beat away from the oracle is **excluded** before the human phase, not
corrected.

## Scale of the job

20 clips × the slot count of each clip's authored mask (4 or 6 slots), by two
annotators independently, plus adjudication. Roughly 100–120 anchor judgements
per annotator, plus beat marking on each clip.
