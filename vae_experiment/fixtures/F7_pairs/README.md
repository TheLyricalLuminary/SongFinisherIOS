# F7 — 60 positional-permutation pairs, all five Section 11 checks passed

**Status: UNPOPULATED — BLOCKED ON F4 AND F5.**

Authoring F7 is not a writing task that can be done and checked later. Section 11
check 4 matches pair members on `Σ d_nominal(c)` within `LOAD_TOL`, and
`d_nominal` comes from **F4**. Syllable onset/coda boundaries — which decide
*where* the heavy cluster sits, the entire independent variable — come from
Maximum Onset Principle syllabification against **F5**. Without both tables:

* a pair cannot be checked for matched nominal load (check 4);
* `Score_C` cannot be computed, so reversal (check 2), margin (check 3) and the
  `C_FLAT` control (check 5) cannot be evaluated;
* lines authored against a guessed syllabification would silently carry their
  cluster in a different position than intended.

Authoring lines now and validating them later would mean authoring against an
unknown syllabifier. The gate that discards failing pairs
(`vae.pairs.check_pair` / `run_gate`) is implemented, tested, and runs the
moment F4 and F5 are populated.

## Per-pair fields required (see `vae.pairs.PairSpec`)

`pair_id`, `line_x`, `line_y`, `context_1_id`, `context_2_id`,
`syllable_count`, `stress_pattern`, `zipf_decile`, `syntactic_form`,
`heavy_cluster_syllable_x`, `heavy_cluster_syllable_y`,
`predicted_preferred_context_1`, `predicted_preferred_context_2`.

Members must share matched nominal articulatory load, identical syllable count
and syllable→slot assignment, identical lexical stress pattern position-for-
position, word frequency within one Zipf decile, comparable syntactic form, and
no OOV words — and differ **only** in which syllable position carries the heavy
cluster.

The two contexts must have **opposite** interval asymmetry. F6 supplies two
mirror mask pairs for exactly this: `M5_short_first_4`/`M6_long_first_4` at four
slots, and `M7_short_first_6`/`M8_long_first_6` at six.
