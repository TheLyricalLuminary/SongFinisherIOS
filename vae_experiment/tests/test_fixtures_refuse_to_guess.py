"""F4 and F5 must fail loudly rather than default (Section 22 failure #10)."""

from __future__ import annotations

import pytest

from vae.errors import FixtureUnpopulatedError, MissingOnsetTableError, MissingPhoneError
from vae.tables import load_duration_table, load_onset_table
from tests.conftest import SYNTHETIC_F4, SYNTHETIC_F5


def test_shipped_f4_is_populated_but_still_refuses_phones_it_does_not_carry():
    """F4 is populated from Klatt (1979) Table 1; the hard-error guarantee survives.

    Retargeted from an earlier assertion that F4 was UNPOPULATED. The property
    worth protecting was never "F4 is empty" but "F4 never invents a duration",
    and that is what is asserted here.
    """
    table = load_duration_table()
    assert table.is_populated
    assert not table.is_synthetic
    assert len(table.covered_phones()) == 22
    assert table.d_nominal("S") == 0.125 and table.d_floor("S") == 0.050

    with pytest.raises(MissingPhoneError):
        table.d_nominal("NOT_A_PHONE")
    # The deferred affricates are absent, and absent means refused, not defaulted.
    for phone in ("CH", "JH"):
        with pytest.raises(MissingPhoneError) as excinfo:
            table.d_nominal(phone)
        assert "DEFERRED" in str(excinfo.value)


def test_shipped_f5_is_populated_but_still_refuses_unlisted_onsets():
    """F5 is populated under spec-owner approval; the hard-error guarantee survives.

    Retargeted from an earlier assertion that F5 was UNPOPULATED. The property
    worth protecting was never "F5 is empty" but "F5 never invents an onset",
    and that is what is asserted here.
    """
    table = load_onset_table()
    assert table.is_populated
    assert table.n_onsets == 64
    assert table.is_legal_onset(("S", "T"))
    assert not table.is_legal_onset(("S", "V"))          # attested in CMUdict, not licensed
    with pytest.raises(MissingOnsetTableError):
        table.require_legal_onset(("S", "V"))


def test_an_unpopulated_duration_table_still_refuses_every_lookup(tmp_path):
    """Keeps the UNPOPULATED branch covered now that the shipped F4 is populated.

    Without this, populating F4 would silently retire the guarantee that an
    unpopulated table raises rather than returning something.
    """
    import json

    path = tmp_path / "F4_empty.json"
    path.write_text(json.dumps({
        "fixture_id": "F4",
        "status": "UNPOPULATED",
        "required_source_material": ["Klatt (1979), Table 1"],
        "phones": {},
    }))
    table = load_duration_table(path)
    assert not table.is_populated
    with pytest.raises(FixtureUnpopulatedError) as excinfo:
        table.d_nominal("S")
    assert "Klatt" in str(excinfo.value)


def test_synthetic_tables_are_refused_without_explicit_opt_in():
    with pytest.raises(FixtureUnpopulatedError):
        load_duration_table(SYNTHETIC_F4)
    with pytest.raises(FixtureUnpopulatedError):
        load_onset_table(SYNTHETIC_F5)


def test_synthetic_tables_announce_themselves(synthetic_durations, synthetic_onsets):
    assert synthetic_durations.is_synthetic
    assert synthetic_onsets.is_synthetic
    assert not synthetic_durations.is_populated
    assert not synthetic_onsets.is_populated


def test_missing_phone_is_a_hard_error_not_a_default(synthetic_durations):
    with pytest.raises(MissingPhoneError):
        synthetic_durations.d_nominal("NOT_A_PHONE")


def test_illegal_onset_is_a_hard_error(synthetic_onsets):
    with pytest.raises(MissingOnsetTableError):
        synthetic_onsets.require_legal_onset(("Z", "G", "B"))
