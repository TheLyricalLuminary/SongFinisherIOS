"""V1 defers CH and JH: F4 requires 22 scalar consonants, and F7 excludes the rest.

Spec-owner decision, [CHATGPT HANDOFF - F4 source transcription + affricate
correction].  Deferring a phone is not the same as leaving a gap in it, and these
tests pin the difference in three places:

*   intake refuses a row for a deferred phone, filled or blank;
*   a duration lookup for one is still a HARD error, never a default or a zero;
*   the F7 eligibility guard keeps any line that could reach that lookup out of
    the pool, judged over EVERY pronunciation variant rather than the primary.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vae.constants import ARPABET_CONSONANTS, V1_DEFERRED_CONSONANTS
from vae.errors import ContractError, MissingPhoneError
from vae.intake import F4_REQUIRED_CONSONANTS, validate_f4
from vae.pairs import (
    ELIGIBLE,
    INELIGIBLE_DEFERRED_PHONE,
    INELIGIBLE_OOV,
    PairSpec,
    check_line_eligibility,
    check_pair_eligibility,
    screen_pairs,
)

ROOT = Path(__file__).resolve().parent.parent
F4_FIXTURE = ROOT / "fixtures" / "F4_phone_durations" / "phone_durations.json"
F4_INTAKE = ROOT / "fixtures" / "F4_phone_durations" / "intake_f4.csv"
HEADER_F4 = "arpabet,d_nominal_ms,d_floor_ms,source,page_or_table,notes\n"


def _f4(tmp_path, body):
    path = tmp_path / "f4.csv"
    path.write_text(HEADER_F4 + body)
    return validate_f4(path)


def _spec(pair_id: str, line_x: str, line_y: str) -> PairSpec:
    return PairSpec(
        pair_id=pair_id, line_x=line_x, line_y=line_y,
        context_1_id="M5_short_first_4", context_2_id="M6_long_first_4",
        syllable_count=4, stress_pattern=("PRIMARY",) * 4, zipf_decile=5,
        syntactic_form="NP", heavy_cluster_syllable_x=0, heavy_cluster_syllable_y=3,
        predicted_preferred_context_1="X", predicted_preferred_context_2="Y",
    )


# --------------------------------------------------------------------------- #
# The requirement is 22, and the two deferred phones are named
# --------------------------------------------------------------------------- #

def test_v1_requires_22_of_the_24_arpabet_consonants():
    assert len(ARPABET_CONSONANTS) == 24
    assert V1_DEFERRED_CONSONANTS == ("CH", "JH")
    assert len(F4_REQUIRED_CONSONANTS) == 22
    assert set(F4_REQUIRED_CONSONANTS) == set(ARPABET_CONSONANTS) - {"CH", "JH"}


def test_shipped_intake_csv_has_no_row_for_a_deferred_phone():
    rows = [
        line.split(",")[0].strip()
        for line in F4_INTAKE.read_text().splitlines()
        if line.strip() and not line.startswith("#") and not line.startswith("arpabet")
    ]
    assert len(rows) == 22
    assert not (set(rows) & set(V1_DEFERRED_CONSONANTS))


def test_fixture_records_the_deferral_and_still_lists_22_uncovered():
    doc = json.loads(F4_FIXTURE.read_text())
    assert doc["status"] == "UNPOPULATED"
    assert doc["v1_deferred_phones"]["phones"] == list(V1_DEFERRED_CONSONANTS)
    assert len(doc["uncovered_phones"]) == 22
    assert not (set(doc["uncovered_phones"]) & set(V1_DEFERRED_CONSONANTS))


# --------------------------------------------------------------------------- #
# Intake: a deferred phone takes no row at all
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("phone", V1_DEFERRED_CONSONANTS)
def test_a_filled_row_for_a_deferred_phone_is_an_error(tmp_path, phone):
    """Supplying a value would undefer the phone without the decision to do so."""
    result = _f4(tmp_path, f"{phone},110,50,Klatt (1979),Table 1,\n")
    assert any("DEFERRED" in e and phone in e for e in result.errors)
    assert phone not in result.gaps
    assert not any(r["arpabet"] == phone for r in result.rows)


@pytest.mark.parametrize("phone", V1_DEFERRED_CONSONANTS)
def test_a_blank_row_for_a_deferred_phone_is_also_an_error(tmp_path, phone):
    """A blank row would read as a gap still to be filled.  It is not one."""
    result = _f4(tmp_path, f"{phone},,,,,\n")
    assert any("DEFERRED" in e and phone in e for e in result.errors)
    assert phone not in result.gaps


def test_22_complete_rows_validate_clean_without_the_affricates(tmp_path):
    """The behavioural change: full coverage no longer means all 24."""
    body = "".join(f"{p},80,40,Klatt (1979),Table 1,\n" for p in F4_REQUIRED_CONSONANTS)
    result = _f4(tmp_path, body)
    assert result.ok
    assert result.errors == []
    assert result.gaps == []
    assert len(result.rows) == 22


# --------------------------------------------------------------------------- #
# Deferred is not defaulted: the lookup still fails hard
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("phone", V1_DEFERRED_CONSONANTS)
def test_lookup_of_a_deferred_phone_is_a_hard_error(tmp_path, phone):
    from vae.tables import load_duration_table

    path = tmp_path / "F4.json"
    path.write_text(json.dumps({
        "fixture_id": "F4",
        "status": "POPULATED",
        "phones": {
            p: {"d_nominal_s": 0.08, "d_floor_s": 0.04, "source": "TEST"}
            for p in F4_REQUIRED_CONSONANTS
        },
    }))
    table = load_duration_table(path)
    assert table.is_populated
    assert len(table.covered_phones()) == 22

    for lookup in (table.d_nominal, table.d_floor):
        with pytest.raises(MissingPhoneError) as excinfo:
            lookup(phone)
        assert "DEFERRED" in str(excinfo.value)


# --------------------------------------------------------------------------- #
# F7 eligibility guard
# --------------------------------------------------------------------------- #

def test_a_line_free_of_deferred_phones_is_eligible(lexicon):
    verdict = check_line_eligibility("stop the rain now", lexicon)
    assert verdict.eligible
    assert verdict.reason == ELIGIBLE
    assert verdict.offending == ()


def test_a_line_with_an_affricate_is_ineligible(lexicon):
    verdict = check_line_eligibility("choose the bright road", lexicon)
    assert not verdict.eligible
    assert verdict.reason == INELIGIBLE_DEFERRED_PHONE
    assert any(word == "choose" and phone == "CH" for word, _, phone in verdict.offending)
    assert "choose" in verdict.detail()


def test_the_guard_reads_every_variant_not_just_the_primary(lexicon):
    """``amateur`` is AE M AH T ER, and also AE M AH CH ER.

    The premise is asserted first: if CMUdict ever stopped listing the affricate
    variant this test would pass vacuously and stop protecting anything.
    """
    variants = lexicon.variants("amateur")
    assert len(variants) >= 2
    assert "CH" not in variants[0].phones                  # primary is clean
    assert any("CH" in v.phones for v in variants[1:])      # a secondary is not

    verdict = check_line_eligibility("the amateur sings", lexicon)
    assert not verdict.eligible
    assert verdict.reason == INELIGIBLE_DEFERRED_PHONE
    assert all(word == "amateur" for word, _, _ in verdict.offending)


def test_an_affricate_in_a_coda_is_caught_too(lexicon):
    """Section 7 budgets codas as well as onsets, so the scan is whole-pronunciation."""
    assert "CH" in lexicon.variants("watch")[0].phones
    assert not check_line_eligibility("watch the road", lexicon).eligible


def test_an_oov_word_is_ineligible_not_eligible(lexicon):
    verdict = check_line_eligibility("zzzqx the road", lexicon)
    assert not verdict.eligible
    assert verdict.reason == INELIGIBLE_OOV
    assert verdict.oov_words == ("zzzqx",)


def test_an_empty_line_is_a_contract_error(lexicon):
    with pytest.raises(ContractError):
        check_line_eligibility("   ", lexicon)


def test_the_deferred_set_is_a_parameter_not_a_hard_coded_assumption(lexicon):
    """Point the same guard at a different table's coverage and it follows."""
    assert check_line_eligibility("stop the rain now", lexicon).eligible
    verdict = check_line_eligibility("stop the rain now", lexicon, deferred={"S"})
    assert not verdict.eligible
    assert any(phone == "S" for _, _, phone in verdict.offending)


def test_one_bad_member_disqualifies_the_whole_pair(lexicon):
    """Section 11 tests a reversal between X and Y; keeping one member is not an option."""
    spec = _spec("P01", "stop the rain now", "choose the rain now")
    verdict = check_pair_eligibility(spec, lexicon)
    assert not verdict.eligible
    assert verdict.subject == "P01"
    assert verdict.reason == INELIGIBLE_DEFERRED_PHONE


def test_screen_pairs_partitions_and_reports_rather_than_warning(lexicon):
    good = _spec("P_OK", "stop the rain now", "drop the rain now")
    bad = _spec("P_CH", "stop the rain now", "watch the rain now")
    oov = _spec("P_OOV", "stop the rain now", "zzzqx the rain now")

    eligible, rejected = screen_pairs([good, bad, oov], lexicon)
    assert [s.pair_id for s in eligible] == ["P_OK"]
    assert [v.subject for v in rejected] == ["P_CH", "P_OOV"]
    assert [v.reason for v in rejected] == [INELIGIBLE_DEFERRED_PHONE, INELIGIBLE_OOV]
