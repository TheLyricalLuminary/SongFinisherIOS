"""F4/F5 intake validation: refuse partial data, never default it."""

from __future__ import annotations


from vae.intake import F4_REQUIRED_CONSONANTS, validate_f4, validate_f5

HEADER_F4 = "arpabet,d_nominal_ms,d_floor_ms,source,page_or_table,notes\n"
HEADER_F5 = "onset,source,page_or_table,dialect,notes\n"


def _f4(tmp_path, body):
    path = tmp_path / "f4.csv"
    path.write_text(HEADER_F4 + body)
    return validate_f4(path)


def _f5(tmp_path, body, symbols=frozenset({"S", "T", "R", "P", "L", "K"})):
    path = tmp_path / "f5.csv"
    path.write_text(HEADER_F5 + body)
    return validate_f5(path, symbols)


def test_shipped_f4_intake_is_complete_and_matches_the_shipped_fixture():
    """Retargeted from an assertion that the shipped template was entirely gaps.

    The template has since been filled from Klatt (1979) Table 1. What still needs
    protecting is that the intake validates clean at 22 rows and that the fixture
    on disk is the one that intake produces -- a hand-edited fixture that had
    drifted from its own source CSV would carry provenance it did not earn.
    """
    import hashlib
    import json
    from pathlib import Path

    from vae.intake import validate_f4 as v

    root = Path(__file__).resolve().parent.parent
    intake = root / "fixtures" / "F4_phone_durations" / "intake_f4.csv"
    result = v(intake)

    assert result.ok
    assert result.errors == []
    assert result.gaps == []
    assert len(result.rows) == 22
    assert sorted(r["arpabet"] for r in result.rows) == sorted(F4_REQUIRED_CONSONANTS)
    for row in result.rows:
        assert row["source"] == "Klatt (1979)"
        assert row["page_or_table"] == "Table 1"
        assert 0.0 < row["d_floor_s"] <= row["d_nominal_s"]

    doc = json.loads((root / "fixtures" / "F4_phone_durations" / "phone_durations.json").read_text())
    assert doc["provenance"]["intake_sha256"] == hashlib.sha256(intake.read_bytes()).hexdigest()
    assert doc["provenance"]["sources"] == ["Klatt (1979)"]
    assert {r["arpabet"]: r["d_nominal_s"] for r in result.rows} == {
        p: e["d_nominal_s"] for p, e in doc["phones"].items()
    }


def test_blank_row_is_a_reported_gap_not_a_default(tmp_path):
    result = _f4(tmp_path, "B,,,,,\n")
    assert "B" in result.gaps
    assert not any("B" == r["arpabet"] for r in result.rows)


def test_partially_filled_row_is_an_error_not_a_gap(tmp_path):
    result = _f4(tmp_path, "B,70,,,\n")
    assert any("partially filled" in e for e in result.errors)


def test_floor_above_nominal_is_rejected(tmp_path):
    result = _f4(tmp_path, "B,50,90,Klatt 1976,Table II,\n")
    assert any("incompressible" in e for e in result.errors)


def test_non_arpabet_symbol_is_rejected(tmp_path):
    assert any("not an ARPAbet consonant" in e for e in _f4(tmp_path, "Q,70,30,x,y,\n").errors)


def test_duplicate_phone_is_rejected(tmp_path):
    body = "B,70,30,src,tbl,\nB,71,31,src,tbl,\n"
    assert any("duplicate" in e for e in _f4(tmp_path, body).errors)


def test_full_coverage_validates_and_converts_to_seconds(tmp_path):
    body = "".join(f"{p},80,40,SRC,TBL,\n" for p in F4_REQUIRED_CONSONANTS)
    result = _f4(tmp_path, body)
    assert result.ok
    assert len(result.rows) == len(F4_REQUIRED_CONSONANTS)
    assert result.rows[0]["d_nominal_s"] == 0.080
    assert result.rows[0]["d_floor_s"] == 0.040


def test_f5_requires_a_source_on_every_entry(tmp_path):
    assert any("mandatory" in e for e in _f5(tmp_path, "S T,,,,\n").errors)


def test_f5_rejects_unknown_symbols(tmp_path):
    assert any("not ARPAbet" in e for e in _f5(tmp_path, "S Q,Roach 2009,ch8,GA,\n").errors)


def test_f5_requires_singleton_onsets(tmp_path):
    """MOP consults the table at every boundary, not only for clusters."""
    result = _f5(tmp_path, "S T,Roach 2009,ch8,GA,\nS T R,Roach 2009,ch8,GA,\n")
    assert any("singleton" in e for e in result.errors)


def test_f5_accepts_a_well_formed_inventory(tmp_path):
    body = ("S,R,p1,GA,\nT,R,p1,GA,\nR,R,p1,GA,\nP,R,p1,GA,\nL,R,p1,GA,\nK,R,p1,GA,\n"
            "S T,R,p1,GA,\nS T R,R,p1,GA,\n")
    result = _f5(tmp_path, body)
    assert result.ok
    assert [r["phones"] for r in result.rows][-1] == ["S", "T", "R"]   # sorted by length


def test_f5_rejects_an_empty_inventory(tmp_path):
    assert any("no onsets supplied" in e for e in _f5(tmp_path, "").errors)
