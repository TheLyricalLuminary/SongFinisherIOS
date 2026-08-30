"""F4 and F5 must fail loudly rather than default (Section 22 failure #10)."""

from __future__ import annotations

import pytest

from vae.errors import FixtureUnpopulatedError, MissingOnsetTableError, MissingPhoneError
from vae.tables import load_duration_table, load_onset_table
from tests.conftest import SYNTHETIC_F4, SYNTHETIC_F5


def test_shipped_f4_is_unpopulated_and_raises_on_lookup():
    table = load_duration_table()
    assert not table.is_populated
    with pytest.raises(FixtureUnpopulatedError) as excinfo:
        table.d_nominal("S")
    assert "Klatt" in str(excinfo.value)


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
