"""Section 9 variant handling against the populated F5 inventory.

A CMUdict word may carry optional secondary pronunciations. One of them being
illegal under F5 must not disqualify a word whose primary pronunciation is
perfectly legal -- but F5 is never extended to rescue anything, and a word with
no legal pronunciation at all is excluded deterministically rather than
abstained.
"""

from __future__ import annotations

import pytest

from vae.constants import VERDICT_ABSTAIN_OOV, VERDICT_REJECT_HARD
from vae.contracts import AcousticEvidence, Anchor
from vae.errors import NoLegalPronunciationError
from vae.lexicon import line_variants
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


def test_f5_is_populated_at_the_approved_size(real_onsets):
    assert real_onsets.is_populated
    assert real_onsets.n_onsets == 64
    assert real_onsets.max_onset_length == 3


@pytest.mark.parametrize("word", ["what", "when"])
def test_wh_words_survive_via_their_legal_w_pronunciation(word, lexicon, real_onsets):
    """`what` = W AH T (legal) and HH W AH T (HH W is unlicensed)."""
    onsets = {tuple(p.phones[:2]) for p in lexicon.variants(word)}
    assert ("HH", "W") in onsets, "fixture assumption: an HH W secondary variant exists"

    parsed = line_variants(word, lexicon, real_onsets)
    assert parsed.variants, f"{word} must remain usable"
    assert any(r.onset == ("HH", "W") for r in parsed.rejected)
    assert all(v.syllables[0].onset != ("HH", "W") for v in parsed.variants)


def test_an_illegal_secondary_variant_does_not_kill_the_line(
    config, masks, lexicon, real_onsets, synthetic_durations
):
    envelope = _envelope(config, masks.by_id("M5_short_first_4"))
    report, log = sound(envelope, Candidate("c", "what a day now"), lexicon, config,
                        synthetic_durations, real_onsets)
    assert report.verdict != VERDICT_REJECT_HARD
    assert report.slots, "the line must be scored, not excluded"
    assert any(r.onset == ("HH", "W") for r in log.rejected_variants), \
        "the skipped variant must be logged, not silently dropped"


def test_rejected_variants_are_logged_with_word_and_index(lexicon, real_onsets):
    parsed = line_variants("what", lexicon, real_onsets)
    rejected = [r for r in parsed.rejected if r.onset == ("HH", "W")]
    assert rejected
    assert rejected[0].word == "what"
    assert rejected[0].variant_index >= 0


def test_a_word_with_no_legal_variant_raises(lexicon, real_onsets):
    """`schwa` = SH W AA; SH W is unlicensed and it is the only pronunciation."""
    assert all(p.phones[:2] == ("SH", "W") for p in lexicon.variants("schwa"))
    with pytest.raises(NoLegalPronunciationError) as excinfo:
        line_variants("schwa", lexicon, real_onsets)
    assert excinfo.value.word == "schwa"
    assert ("SH", "W") in excinfo.value.offending_onsets


def test_no_legal_variant_is_excluded_deterministically_and_is_not_oov(
    config, masks, lexicon, real_onsets, synthetic_durations
):
    envelope = _envelope(config, masks.by_id("M5_short_first_4"))
    first, log = sound(envelope, Candidate("c", "schwa"), lexicon, config,
                       synthetic_durations, real_onsets)
    assert first.verdict == VERDICT_REJECT_HARD
    assert first.verdict != VERDICT_ABSTAIN_OOV, "the word IS in the lexicon"
    assert "NO_LEGAL_PRONUNCIATION" in log.exclusion_reason
    second, _ = sound(envelope, Candidate("c", "schwa"), lexicon, config,
                      synthetic_durations, real_onsets)
    assert first == second, "exclusion must be deterministic"


def test_a_genuinely_oov_word_still_abstains(
    config, masks, lexicon, real_onsets, synthetic_durations
):
    """The new path must not swallow the OOV case."""
    envelope = _envelope(config, masks.by_id("M5_short_first_4"))
    report, log = sound(envelope, Candidate("c", "zzqqx the rain now"), lexicon, config,
                        synthetic_durations, real_onsets)
    assert report.verdict == VERDICT_ABSTAIN_OOV
    assert "OOV" in log.exclusion_reason


def test_f5_is_not_expanded_from_cmudict(real_onsets, lexicon):
    """Populating F5 must not have absorbed onsets the lexicon happens to attest."""
    from pathlib import Path
    from vae.intake import attested_cmudict_onsets

    root = Path(__file__).resolve().parent.parent
    symbols = frozenset(
        line.split("\t")[0] for line in
        (root / "fixtures" / "lexicon" / "cmudict.phones").read_text().splitlines()
        if line.strip()
    ) - lexicon.vowels
    attested = attested_cmudict_onsets(lexicon, symbols)
    licensed = {c for c in attested if real_onsets.is_legal_onset(c)}
    assert real_onsets.n_onsets == 64
    assert len(attested - licensed) > 0, \
        "F5 must remain narrower than what CMUdict attests; equality would mean it was derived"


def test_legal_variant_ordering_is_deterministic(lexicon, real_onsets):
    runs = [
        [v.per_word_variant for v in line_variants("record the rain", lexicon, real_onsets).variants]
        for _ in range(5)
    ]
    assert all(r == runs[0] for r in runs)
    assert runs[0] == sorted(runs[0]), "combinations stay lexicographically ordered"


def test_scoring_is_unchanged_for_a_line_with_no_rejected_variants(
    config, masks, lexicon, real_onsets, synthetic_durations
):
    """The fix must not perturb candidates that never had an illegal variant."""
    envelope = _envelope(config, masks.by_id("M5_short_first_4"))
    report, log = sound(envelope, Candidate("c", "stop the rain now"), lexicon, config,
                        synthetic_durations, real_onsets)
    assert log.rejected_variants == ()
    assert report.verdict == "ACCEPT"
    assert len(report.slots) == 4
