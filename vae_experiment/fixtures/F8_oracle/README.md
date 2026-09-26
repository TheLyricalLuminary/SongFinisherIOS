# F8 — Oracle annotations (beats + anchors) for all F2

**Status: PARTIAL — F1 present by construction, F2 BLOCKED.**

## What Section 12 requires

Two annotators independently mark, per clip, beat positions and **per-slot
anchor times**, by ear in a DAW against the authored slot mask. Disagreements
> 20 ms are adjudicated by a third annotator. The output conforms to the same
`AcousticEvidence` contract as HEAR, including `anchors[]`.

This is human annotation work. It cannot be produced in this environment, and
it must not be synthesised: `shape()` consumes oracle and HEAR evidence with
zero branching on provenance precisely so that the oracle is an *independent*
measurement. An oracle the pipeline generated from its own HEAR output would
compare HEAR to itself and the Section 12 diagnostic would read as a pass no
matter how wrong the DSP was.

Blocked because F8 for F2 depends on F2, which is itself blocked.

## What is present

`F1_*.json` — anchor times for the F1 click tracks, which are **known exactly by
construction** rather than annotated by ear. These exist so that the Section 12
and Section 16 cross-cut machinery (`vae.oracle.anchor_deltas`,
`summarize_anchor_deltas`, and the R1 whole-beat-offset guard) is exercised and
measured against a ground truth that is genuinely independent of HEAR.

They are **not** a substitute for the F2 oracle:

* a click track has one unambiguous perceptual anchor per event, which is the
  easy case the oracle exists to go beyond;
* the diagnostic that matters — `C ≈ C_ORACLE` (HEAR adequate) versus
  `C_ORACLE ≫ C` (HEAR is the bottleneck) — is about real accompaniment, where
  anchor placement is a perceptual judgement and not a construction.

Each file carries `annotation_source` so the two can never be confused.

## File naming

`<audio_id>.<slot_mask_id>.json`, with fields:
`audio_id`, `slot_mask_id`, `tempo_bpm`, `beat_times_s[]`, `anchor_times_s[]`,
`anchor_sigma_s[]`, `annotation_source`, `annotator_ids[]`,
`adjudicated_slots[]`.
