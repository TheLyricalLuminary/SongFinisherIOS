"""Section 6 I_effective, Section 7 partition, Section 8 tiers."""

from __future__ import annotations

import dataclasses

import pytest

from vae.constants import (
    METHOD_GRID_ONLY, METHOD_ONSET_SUPPORTED, TIER_BELOW_FLOOR, TIER_BORDERLINE,
    TIER_HARD_INFEASIBLE, TIER_OK,
)
from vae.contracts import AcousticEvidence, Anchor, EnvelopeSlot
from vae.shape import effective_interval, shape
from vae.sound import consonant_duration, feasibility_floor, feasibility_tier, s_fit


def _evidence(mask, sigma=0.01, spacing=0.30):
    anchors = tuple(
        Anchor(slot_index=i, time_s=spacing * i, sigma_s=sigma,
               method=METHOD_ONSET_SUPPORTED, supporting_event_ids=(f"E{i:04d}",),
               rise_time_ms=5.0)
        for i in range(mask.slot_count)
    )
    return AcousticEvidence(
        audio_id="AID", engine_version="EV", provenance="HEAR", tempo_bpm=100.0,
        beat_times_s=(0.0,), slot_mask_id=mask.mask_id, anchors=anchors, events=(),
    )


def test_i_effective_shrinks_with_uncertainty_and_floors_at_i_min(config):
    assert effective_interval(0.4, 0.0, 0.0, config) == 0.4
    shrunk = effective_interval(0.4, 0.05, 0.05, config)
    assert shrunk < 0.4
    assert effective_interval(0.05, 0.5, 0.5, config) == config.I_MIN


def test_sigma_coef_zero_reduces_i_effective_to_the_identity(config):
    zero = config.with_overrides(SIGMA_COEF=0.0)
    assert effective_interval(0.4, 0.09, 0.07, zero) == 0.4


def test_final_slot_interval_is_phrase_tail(config, masks):
    mask = masks.by_id("M5_short_first_4")
    envelope = shape(_evidence(mask), config, mask)
    assert envelope.slots[-1].interval_s == config.PHRASE_TAIL


def test_envelope_slot_has_no_feasibility_floor_field():
    """Section 20: feasibility_floor_s is candidate-specific and lives in the report."""
    names = {f.name for f in dataclasses.fields(EnvelopeSlot)}
    assert "feasibility_floor_s" not in names
    assert {"d_pre_max_s", "d_post_max_s", "interval_s", "interval_effective_s"} <= names


def test_partition_sums_back_to_the_effective_interval(
    config, masks, lexicon, synthetic_durations, synthetic_onsets
):
    """I_effective_k = D_nucleus(k) + D_post(k) + D_pre(k+1), exactly."""
    from vae.sound import Candidate, sound

    mask = masks.by_id("M5_short_first_4")
    envelope = shape(_evidence(mask), config, mask)
    report, log = sound(envelope, Candidate("c", "stop the rain now"), lexicon, config,
                        synthetic_durations, synthetic_onsets)
    for k, slot in enumerate(envelope.slots):
        d_pre_next = log.d_pre_s[k + 1] if k + 1 < len(log.d_pre_s) else 0.0
        total = log.d_nucleus_s[k] + log.d_post_s[k] + d_pre_next
        assert abs(total - slot.interval_effective_s) < 1e-12


def test_consonants_compress_less_than_proportionally(config, synthetic_durations):
    """gamma < 1: the same cluster takes a LARGER fraction of a shorter interval."""
    long_i, short_i = 0.60, 0.20
    d_long = consonant_duration("S", long_i, synthetic_durations, config)
    d_short = consonant_duration("S", short_i, synthetic_durations, config)
    assert d_short < d_long                          # it does shrink
    assert d_short / short_i > d_long / long_i       # but not proportionally


@pytest.mark.parametrize(
    "d_nucleus,expected",
    [(-0.01, TIER_HARD_INFEASIBLE), (0.0, TIER_HARD_INFEASIBLE),
     (0.05, TIER_BELOW_FLOOR), (0.10, TIER_BORDERLINE), (0.20, TIER_OK)],
)
def test_four_static_tiers(d_nucleus, expected, config):
    assert feasibility_tier(d_nucleus, config.F_MIN_BASE, config) == expected


def test_tiers_have_no_history(config):
    """No hysteresis (v1.0 defect 4): the tier depends only on the current value."""
    floor = config.F_MIN_BASE
    sequence_up = [feasibility_tier(v, floor, config) for v in (0.05, 0.10, 0.20)]
    sequence_down = [feasibility_tier(v, floor, config) for v in (0.20, 0.10, 0.05)]
    assert sequence_up == list(reversed(sequence_down))


def test_diphthong_floor_is_scaled(config):
    assert feasibility_floor("AY", config) == config.F_MIN_BASE * config.DIPHTHONG_FACTOR
    assert feasibility_floor("IH", config) == config.F_MIN_BASE


def test_s_fit_is_clamped_to_the_unit_interval(config):
    floor = config.F_MIN_BASE
    assert s_fit(floor - 0.1, floor, config) == 0.0
    assert s_fit(config.NUCLEUS_COMFORT + 1.0, floor, config) == 1.0
    assert 0.0 < s_fit((floor + config.NUCLEUS_COMFORT) / 2.0, floor, config) < 1.0


def test_grid_only_anchors_inflate_sigma_and_shrink_the_budget(config, masks):
    """Section 22 failure #3: sigma inflates I_effective automatically."""
    mask = masks.by_id("M5_short_first_4")
    confident = shape(_evidence(mask, sigma=0.002), config, mask)
    uncertain = shape(
        dataclasses.replace(
            _evidence(mask),
            anchors=tuple(
                dataclasses.replace(a, sigma_s=config.SIGMA_GRID_ONLY, method=METHOD_GRID_ONLY)
                for a in _evidence(mask).anchors
            ),
        ),
        config, mask,
    )
    for a, b in zip(confident.slots, uncertain.slots):
        assert b.interval_effective_s <= a.interval_effective_s
