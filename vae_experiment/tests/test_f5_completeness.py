"""F5 completeness: a partial onset table must never become POPULATED.

No expected inventory or expected count is hard-coded anywhere. Completeness is
established by checking the transcription against what the person who read the
named reference declares it contains, plus spec-owner approval.
"""

from __future__ import annotations

import json
from pathlib import Path

from vae.intake import validate_f5_attestation

ROOT = Path(__file__).resolve().parent.parent
ATTESTATION = ROOT / "fixtures" / "F5_onset_clusters" / "attestation_f5.json"


def _rows(n_single=3, n_double=2, n_triple=1):
    rows = []
    for i in range(n_single):
        rows.append({"phones": [["S", "T", "R"][i % 3]]})
    for i in range(n_double):
        rows.append({"phones": ["S", ["T", "P"][i % 2]]})
    for _ in range(n_triple):
        rows.append({"phones": ["S", "T", "R"]})
    return rows


def _attestation(**overrides):
    doc = {
        "approved_by_spec_owner": True,
        "reference": {"author": "Roach, P.", "title": "English Phonetics and Phonology",
                      "edition": "4th", "year": 2009, "section_or_table": "ch. 8",
                      "isbn_or_doi": ""},
        "dialect": "General American",
        "declared_total_onsets": 6,
        "declared_counts_by_length": {"1": 3, "2": 2, "3": 1},
        "transcriber": "mark",
        "transcription_date": "2026-08-29",
    }
    doc.update(overrides)
    return doc


def test_shipped_attestation_is_unapproved_so_f5_cannot_populate():
    doc = json.loads(ATTESTATION.read_text())
    assert doc["approved_by_spec_owner"] is False
    assert validate_f5_attestation(doc, _rows())


def test_a_matching_transcription_is_accepted():
    assert validate_f5_attestation(_attestation(), _rows()) == []


def test_a_partial_table_is_rejected_against_the_declared_total():
    """The reported defect: a small table used to pass and become POPULATED."""
    errors = validate_f5_attestation(_attestation(declared_total_onsets=68), _rows())
    assert any("table has 6 onsets but the reference is declared to list 68" in e
               for e in errors)


def test_a_partial_table_is_rejected_per_length():
    errors = validate_f5_attestation(
        _attestation(declared_total_onsets=6,
                     declared_counts_by_length={"1": 23, "2": 2, "3": 1}),
        _rows(),
    )
    assert any("length-1 onsets: reference declared 23, table has 3" in e for e in errors)


def test_unapproved_source_blocks_population():
    errors = validate_f5_attestation(_attestation(approved_by_spec_owner=False), _rows())
    assert any("approved_by_spec_owner is not true" in e for e in errors)


def test_unnamed_reference_blocks_population():
    ref = dict(_attestation()["reference"], author="", title="", section_or_table="")
    errors = validate_f5_attestation(_attestation(reference=ref), _rows())
    assert sum("must be named" in e for e in errors) == 3


def test_ssbe_dialect_is_refused_against_a_cmudict_lexicon():
    errors = validate_f5_attestation(_attestation(dialect="SSBE"), _rows())
    assert any("not General American" in e for e in errors)


def test_missing_declared_total_blocks_population():
    errors = validate_f5_attestation(_attestation(declared_total_onsets=None), _rows())
    assert any("declared_total_onsets is null" in e for e in errors)


def test_unfilled_counts_by_length_block_population():
    errors = validate_f5_attestation(
        _attestation(declared_counts_by_length={"1": None, "2": None, "3": None}), _rows()
    )
    assert any("unfilled entries" in e for e in errors)


def test_undeclared_length_class_is_reported():
    rows = _rows() + [{"phones": ["S", "T", "R", "W"]}]
    errors = validate_f5_attestation(
        _attestation(declared_total_onsets=7), rows
    )
    assert any("length 4, which the attestation does not declare" in e for e in errors)


def test_no_expected_inventory_is_hard_coded_in_the_package():
    """The fix must not smuggle in an invented onset list."""
    import ast
    banned = {"SPL", "SPR", "STR", "SKR", "SKW", "SPJ", "STJ", "SKJ"}
    for source in (ROOT / "vae").glob("*.py"):
        for node in ast.walk(ast.parse(source.read_text())):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert node.value.replace(" ", "").upper() not in banned, (
                    f"{source.name}:{node.lineno} hard-codes an onset cluster"
                )
