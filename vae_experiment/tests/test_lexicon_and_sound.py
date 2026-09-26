"""Section 9 G2P and Section 10 scoring."""

from __future__ import annotations

import pytest

from vae.constants import (
    STRESS_PRIMARY, STRESS_UNSTRESSED, VERDICT_ABSTAIN_OOV, VERDICT_ACCEPT,
)
from vae.contracts import AcousticEvidence, Anchor
from vae.errors import ContractError
from vae.lexicon import syllabify
from vae.shape import shape
from vae.sound import Candidate, sound


def _envelope(config, mask, spacing=0.32):
    anchors = tuple(
        Anchor(slot_index=i, time_s=spacing * i, sigma_s=0.008,
               method="ONSET_SUPPORTED", supporting_event_ids=(), rise_time_ms=4.0)
        for i in range(mask.slot_count)
    )
    evidence = AcousticEvidence(
        audio_id="AID", engine_version="EV", provenance="HEAR", tempo_bpm=110.0,
        beat_times_s=(0.0,), slot_mask_id=mask.mask_id, anchors=anchors, events=(),
    )
    return shape(evidence, config, mask)


def test_stress_digits_map_to_the_three_levels(lexicon):
    pron = lexicon.variants("record")[0]
    assert pron.stresses == (STRESS_UNSTRESSED, STRESS_PRIMARY)


def test_all_pronunciation_variants_are_available(lexicon):
    assert len(lexicon.variants("record")) >= 2
    assert [p.variant_index for p in lexicon.variants("record")] == sorted(
        p.variant_index for p in lexicon.variants("record")
    )


def test_maximum_onset_principle_puts_the_longest_legal_onset_forward(
    lexicon, synthetic_onsets
):
    # "astray" = AH0 S T R EY1 -> AH . STR EY, because STR is a legal onset.
    pron = lexicon.variants("astray")[0]
    syllables = syllabify(pron, lexicon, synthetic_onsets)
    assert len(syllables) == 2
    assert syllables[0].coda == ()
    assert syllables[1].onset == ("S", "T", "R")


def test_syllable_count_equals_vowel_count(lexicon, synthetic_onsets):
    for word in ("rain", "window", "remember"):
        pron = lexicon.variants(word)[0]
        syllables = syllabify(pron, lexicon, synthetic_onsets)
        assert len(syllables) == sum(1 for p in pron.phones if lexicon.is_vowel(p))


def test_oov_abstains_and_is_never_guessed(config, masks, lexicon,
                                           synthetic_durations, synthetic_onsets):
    envelope = _envelope(config, masks.by_id("M5_short_first_4"))
    report, log = sound(envelope, Candidate("oov", "zzqqx the rain now"), lexicon,
                        config, synthetic_durations, synthetic_onsets)
    assert report.verdict == VERDICT_ABSTAIN_OOV
    assert report.slots == ()
    assert report.score_b == 0.0 and report.score_c == 0.0
    assert log.chosen_variant_index is None


def test_accepts_an_in_vocabulary_line(config, masks, lexicon,
                                       synthetic_durations, synthetic_onsets):
    envelope = _envelope(config, masks.by_id("M5_short_first_4"))
    report, log = sound(envelope, Candidate("ok", "stop the rain now"), lexicon,
                        config, synthetic_durations, synthetic_onsets)
    assert report.verdict == VERDICT_ACCEPT
    assert len(report.slots) == 4
    assert log.n_variants_evaluated >= 1


def test_score_b_ignores_the_articulatory_term(config, masks, lexicon,
                                               synthetic_durations, synthetic_onsets):
    """B is context-blind: Score_B must not move when the envelope changes."""
    mask = masks.by_id("M5_short_first_4")
    candidate = Candidate("c", "stop the rain now")
    wide, _ = sound(_envelope(config, mask, spacing=0.55), candidate, lexicon, config,
                    synthetic_durations, synthetic_onsets)
    narrow, _ = sound(_envelope(config, mask, spacing=0.18), candidate, lexicon, config,
                      synthetic_durations, synthetic_onsets)
    assert wide.score_b == narrow.score_b
    assert wide.score_c != narrow.score_c        # C is not blind


def test_score_c_is_score_b_plus_the_single_fit_term(config, masks, lexicon,
                                                     synthetic_durations, synthetic_onsets):
    envelope = _envelope(config, masks.by_id("M5_short_first_4"))
    report, _ = sound(envelope, Candidate("c", "stop the rain now"), lexicon, config,
                      synthetic_durations, synthetic_onsets)
    mean_fit = sum(s.s_fit for s in report.slots) / len(report.slots)
    assert abs(report.score_c - (report.score_b + config.W_fit * mean_fit)) < 1e-12


def test_aggregation_is_the_arithmetic_mean(config, masks, lexicon,
                                            synthetic_durations, synthetic_onsets):
    envelope = _envelope(config, masks.by_id("M5_short_first_4"))
    report, _ = sound(envelope, Candidate("c", "stop the rain now"), lexicon, config,
                      synthetic_durations, synthetic_onsets)
    mean_stress = sum(s.s_stress for s in report.slots) / len(report.slots)
    expected_b = (config.W_stress * mean_stress + config.W_count * report.slots[0].s_count
                  + config.W_anchor * report.slots[0].s_anchor)
    assert abs(report.score_b - expected_b) < 1e-12


def test_syllable_count_mismatch_zeroes_count_and_anchor(config, masks, lexicon,
                                                         synthetic_durations, synthetic_onsets):
    """Condition A's manipulation: deliberately mismatched syllable count."""
    envelope = _envelope(config, masks.by_id("M5_short_first_4"))
    report, _ = sound(envelope, Candidate("a", "rain"), lexicon, config,
                      synthetic_durations, synthetic_onsets)
    assert report.slots[0].s_count == 0.0
    assert report.slots[0].s_anchor == 0.0


def test_sound_is_pure_and_repeatable(config, masks, lexicon,
                                      synthetic_durations, synthetic_onsets):
    envelope = _envelope(config, masks.by_id("M5_short_first_4"))
    candidate = Candidate("c", "stop the rain now")
    first, _ = sound(envelope, candidate, lexicon, config, synthetic_durations, synthetic_onsets)
    second, _ = sound(envelope, candidate, lexicon, config, synthetic_durations, synthetic_onsets)
    assert first == second


def test_empty_line_is_a_contract_error(config, masks, lexicon,
                                        synthetic_durations, synthetic_onsets):
    envelope = _envelope(config, masks.by_id("M5_short_first_4"))
    with pytest.raises(ContractError):
        sound(envelope, Candidate("e", "   "), lexicon, config,
              synthetic_durations, synthetic_onsets)
