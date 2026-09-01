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


def test_shipped_f4_template_is_entirely_gaps():
    """22 gaps, not 24: the shipped template carries no row for the deferred affricates."""
    from vae.intake import validate_f4 as v
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    result = v(root / "fixtures" / "F4_phone_durations" / "intake_f4.csv")
    assert not result.errors
    assert sorted(result.gaps) == sorted(F4_REQUIRED_CONSONANTS)
    assert len(result.gaps) == 22
    assert result.rows == []


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
