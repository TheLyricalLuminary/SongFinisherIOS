"""Section 1 conditions, Section 10/15 ranking, Section 11 pair checks."""

from __future__ import annotations

import dataclasses

import pytest

from vae.conditions import flat_envelope, select_shuffled_donor, shuffled_envelope
from vae.constants import CONDITIONS, VERDICT_ACCEPT, VERDICT_REJECT_HARD
from vae.contracts import AcousticEvidence, Anchor, CompatibilityReport
from vae.errors import ContractError
from vae.pairs import CHECK_IDS, CellReports, PairSpec, check_pair, run_gate
from vae.rank import rank
from vae.shape import shape


def _envelope(config, mask, spacing=0.32, audio_id="AID"):
    anchors = tuple(
        Anchor(slot_index=i, time_s=spacing * i, sigma_s=0.008,
               method="ONSET_SUPPORTED", supporting_event_ids=(), rise_time_ms=4.0)
        for i in range(mask.slot_count)
    )
    evidence = AcousticEvidence(
        audio_id=audio_id, engine_version="EV", provenance="HEAR", tempo_bpm=110.0,
        beat_times_s=(0.0,), slot_mask_id=mask.mask_id, anchors=anchors, events=(),
    )
    return shape(evidence, config, mask)


def _report(candidate_id, score_b, score_c, pair_id=None, nominal=0.5,
            verdict=VERDICT_ACCEPT):
    return CompatibilityReport(
        audio_id="AID", engine_version="EV", provenance="HEAR",
        candidate_id=candidate_id, pair_id=pair_id, context_id=None, pair_role=None,
        predicted_preferred=None, pronunciation_variant_index=0, verdict=verdict,
        score_b=score_b, score_c=score_c, total_consonant_duration_s=0.4,
        total_nominal_consonant_duration_s=nominal, slots=(),
    )


# --- conditions ------------------------------------------------------------- #

def test_all_six_conditions_exist():
    assert set(CONDITIONS) == {"A", "B", "C", "C_FLAT", "C_SHUFFLED", "C_ORACLE"}


def test_c_flat_is_uniform_and_carries_no_audio(config, masks):
    mask = masks.by_id("M5_short_first_4")
    flat = flat_envelope(mask, config, "EV")
    intervals = [s.interval_s for s in flat.slots[:-1]]
    assert len(set(intervals)) == 1                       # constant I_k
    assert len({s.uncertainty_anchor_sigma_s for s in flat.slots}) == 1   # constant sigma
    assert all(s.derived_from_event_ids == () for s in flat.slots)
    # Structure still comes from the authored mask.
    assert [s.metrical_strength for s in flat.slots] == list(mask.metrical_strength)


def test_c_flat_is_identical_for_the_two_mirror_contexts(config, masks):
    """The audio-free control cannot distinguish SHORT_FIRST from LONG_FIRST."""
    short = flat_envelope(masks.by_id("M5_short_first_4"), config, "EV")
    long_ = flat_envelope(masks.by_id("M6_long_first_4"), config, "EV")
    strip = lambda e: [(s.interval_effective_s, s.metrical_strength) for s in e.slots]
    assert strip(short) == strip(long_)


def test_c_shuffled_donor_selection_is_deterministic(config, masks):
    mask = masks.by_id("M5_short_first_4")
    pool = {f"AID{i}": _envelope(config, mask, audio_id=f"AID{i}") for i in range(4)}
    picks = {select_shuffled_donor("AID1", pool).audio_id for _ in range(20)}
    assert picks == {"AID2"}                              # lexicographically next, stable
    assert select_shuffled_donor("AID3", pool).audio_id == "AID0"   # wraps


def test_c_shuffled_borrows_a_different_clips_envelope(config, masks):
    mask = masks.by_id("M5_short_first_4")
    pool = {
        "AIDa": _envelope(config, mask, spacing=0.20, audio_id="AIDa"),
        "AIDb": _envelope(config, mask, spacing=0.50, audio_id="AIDb"),
    }
    shuffled = shuffled_envelope("AIDa", pool, mask)
    assert [s.interval_s for s in shuffled.slots] == [s.interval_s for s in pool["AIDb"].slots]
    assert shuffled.slot_mask_id == mask.mask_id


def test_c_shuffled_requires_a_slot_count_matched_donor(config, masks):
    mask = masks.by_id("M5_short_first_4")
    with pytest.raises(ContractError):
        shuffled_envelope("only", {"only": _envelope(config, mask, audio_id="only")}, mask)


# --- rank ------------------------------------------------------------------- #

def test_rank_orders_by_score_then_breaks_ties_lexicographically(config):
    reports = [
        _report("zeta", 0.5, 0.80), _report("alpha", 0.5, 0.80), _report("mid", 0.5, 0.90),
    ]
    ranked = rank(reports, "C", config)
    assert [e.candidate_id for e in ranked.ranked] == ["mid", "alpha", "zeta"]
    assert [e.tiebreak_applied for e in ranked.ranked] == [False, True, True]


def test_rank_is_invariant_to_input_order(config):
    reports = [_report("b", 0.5, 0.8), _report("a", 0.5, 0.8), _report("c", 0.5, 0.9)]
    forward = rank(reports, "C", config)
    backward = rank(list(reversed(reports)), "C", config)
    assert forward.ranked == backward.ranked


def test_condition_b_reads_score_b_and_c_reads_score_c(config):
    reports = [_report("x", 0.9, 0.1), _report("y", 0.1, 0.9)]
    assert [e.candidate_id for e in rank(reports, "B", config).ranked] == ["x", "y"]
    assert [e.candidate_id for e in rank(reports, "C", config).ranked] == ["y", "x"]


def test_reject_hard_is_excluded_from_ranking(config):
    reports = [_report("ok", 0.5, 0.9), _report("bad", 0.9, 0.99, verdict=VERDICT_REJECT_HARD)]
    ranked = rank(reports, "C", config)
    assert [e.candidate_id for e in ranked.ranked] == ["ok"]


# --- Section 11 pair checks ------------------------------------------------- #

def _spec():
    return PairSpec(
        pair_id="P01", line_x="x line", line_y="y line",
        context_1_id="ctx1", context_2_id="ctx2", syllable_count=4,
        stress_pattern=("PRIMARY", "UNSTRESSED", "PRIMARY", "UNSTRESSED"),
        zipf_decile=5, syntactic_form="SVO",
        heavy_cluster_syllable_x=1, heavy_cluster_syllable_y=0,
        predicted_preferred_context_1="X", predicted_preferred_context_2="Y",
    )


def _cells(*, b_x=0.5, b_y=0.5, cx1=0.80, cy1=0.70, cx2=0.70, cy2=0.80,
           fx1=0.75, fy1=0.75, fx2=0.75, fy2=0.75, nx=0.50, ny=0.50, pair_id="P01"):
    r = lambda cid, b, c, nominal: _report(cid, b, c, pair_id=pair_id, nominal=nominal)
    return CellReports(
        c_x1=r("X", b_x, cx1, nx), c_y1=r("Y", b_y, cy1, ny),
        c_x2=r("X", b_x, cx2, nx), c_y2=r("Y", b_y, cy2, ny),
        flat_x1=r("X", b_x, fx1, nx), flat_y1=r("Y", b_y, fy1, ny),
        flat_x2=r("X", b_x, fx2, nx), flat_y2=r("Y", b_y, fy2, ny),
    )


def test_a_clean_reversal_is_admitted(config):
    verdict = check_pair(_spec(), _cells(), config)
    assert verdict.admitted
    assert verdict.preferred_context_1 == "X" and verdict.preferred_context_2 == "Y"


def test_untied_b_is_discarded(config):
    verdict = check_pair(_spec(), _cells(b_x=0.5, b_y=0.6), config)
    assert not verdict.admitted
    assert CHECK_IDS[0] in verdict.failed_checks()


def test_no_reversal_is_discarded(config):
    """Section 22 failure #5: Score_C prefers the same member in both contexts."""
    verdict = check_pair(_spec(), _cells(cx2=0.80, cy2=0.70), config)
    assert not verdict.admitted
    assert CHECK_IDS[1] in verdict.failed_checks()


def test_a_reversal_below_margin_min_is_discarded(config):
    tiny = config.MARGIN_MIN / 4.0
    verdict = check_pair(
        _spec(), _cells(cx1=0.75 + tiny, cy1=0.75, cx2=0.75, cy2=0.75 + tiny), config
    )
    assert not verdict.admitted
    assert CHECK_IDS[2] in verdict.failed_checks()


def test_unmatched_nominal_load_is_discarded(config):
    """Section 22 failure #6, and it must be d_nominal, not the tempo-scaled d(c)."""
    verdict = check_pair(_spec(), _cells(nx=0.50, ny=0.50 + 10 * config.LOAD_TOL), config)
    assert not verdict.admitted
    assert CHECK_IDS[3] in verdict.failed_checks()


def test_c_flat_reversal_is_discarded(config):
    verdict = check_pair(_spec(), _cells(fx1=0.80, fy1=0.70, fx2=0.70, fy2=0.80), config)
    assert not verdict.admitted
    assert CHECK_IDS[4] in verdict.failed_checks()


def test_gate_discards_rather_than_flags(config):
    good = check_pair(_spec(), _cells(), config)
    bad = check_pair(dataclasses.replace(_spec(), pair_id="P02"),
                     _cells(cx2=0.80, cy2=0.70, pair_id="P02"), config)
    report = run_gate([good, bad])
    assert report.n_evaluated == 2
    assert report.n_admitted == 1
    assert report.admitted_pair_ids == ("P01",)
    assert report.target_pairs == 60
    assert not report.step9_would_pass()
