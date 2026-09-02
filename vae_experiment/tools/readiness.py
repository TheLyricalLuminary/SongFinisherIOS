"""Report fixture and code readiness for the work that follows step 8.

Answers one question per fixture: is it real data, and if not, exactly what is
missing.  Nothing here infers, substitutes, or estimates -- a fixture that is not
populated is reported as not populated.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from vae.constants import V1_DEFERRED_CONSONANTS  # noqa: E402
from vae.intake import F4_REQUIRED_CONSONANTS, validate_f4  # noqa: E402
from vae.tables import load_duration_table, load_onset_table  # noqa: E402

F2_MANIFEST = ROOT / "fixtures" / "F2_clips" / "manifest.json"
F7_PAIRS = ROOT / "fixtures" / "F7_pairs" / "pairs.json"
F8_DIR = ROOT / "fixtures" / "F8_oracle"


def _f4() -> tuple[str, list[str]]:
    deferred = f"deferred from V1: {' '.join(V1_DEFERRED_CONSONANTS)} (no row, hard error on lookup)"
    table = load_duration_table()
    if table.is_populated:
        covered = set(table.covered_phones())
        gaps = sorted(set(F4_REQUIRED_CONSONANTS) - covered)
        if gaps:
            return "INCOMPLETE", [f"uncovered phones: {' '.join(gaps)}", deferred]
        return "POPULATED", [deferred]
    intake = validate_f4(ROOT / "fixtures" / "F4_phone_durations" / "intake_f4.csv")
    return "UNPOPULATED", [
        f"{len(intake.gaps)}/{len(F4_REQUIRED_CONSONANTS)} required consonants "
        f"have no sourced value",
        deferred,
        "needs: the exact numeric transcription of Klatt (1979) Table 1 -- "
        "INHDUR -> d_nominal, MINDUR -> d_floor",
        "note: d_floor is a model-derived lower bound (Klatt's MINDUR), not a "
        "physiological minimum",
        "note: Festival / Allen, Hunnicutt & Klatt (1987) is diagnostic only and is "
        "never imported, averaged or substituted",
    ]


def _f5() -> tuple[str, list[str]]:
    table = load_onset_table()
    if table.is_populated:
        return "POPULATED", [f"{table.n_onsets} onsets, max length {table.max_onset_length}"]
    return "UNPOPULATED", [
        "needs: a named phonotactics reference, transcribed to ARPAbet",
        "candidates: Roach (2009) ch.8; Cruttenden, Gimson's Pronunciation of English §5.5",
        "WARNING both describe SSBE; the lexicon is CMUdict / General American",
    ]


F2_REQUIRED_CLIPS = 20
F2_REQUIRED_ASYMMETRIC = 12
F2_REAL_PROVENANCE = "REAL_RECORDED_ACCOMPANIMENT"


def _f2() -> tuple[str, list[str]]:
    """Derive F2's status from what the manifest CONTAINS, never from what it claims.

    Reading ``doc["status"]`` made the readiness gate a self-report: a manifest
    saying POPULATED over zero clips and synthetic provenance turned the screen
    green -- verified, not hypothetical. The counts and the provenance marker are
    recomputed here from the clip list, so nothing can declare itself complete.
    """
    if not F2_MANIFEST.exists():
        return "UNPOPULATED", [
            "no clips supplied; see fixtures/F2_clips/INTAKE_CHECKLIST.md",
            "needs: 20 DISTINCT real accompaniment recordings, >=12 with interval asymmetry",
        ]
    doc = json.loads(F2_MANIFEST.read_text())
    clips = doc.get("clips", [])
    provenance = doc.get("provenance", "")
    distinct = len({c.get("audio_id") for c in clips if c.get("audio_id")})
    asymmetric = sum(1 for c in clips if c.get("meets_asymmetry_min"))

    notes = [
        f"{len(clips)}/{F2_REQUIRED_CLIPS} accepted, "
        f"{asymmetric}/{F2_REQUIRED_ASYMMETRIC} asymmetric, {distinct} distinct AudioIDs",
        f"{len(doc.get('rejected', []))} rejected by Section 2",
        f"provenance: {provenance or '(none declared)'}",
    ]
    if provenance != F2_REAL_PROVENANCE:
        notes.append(
            f"REFUSED: provenance is not {F2_REAL_PROVENANCE!r}; only real recorded "
            f"accompaniment counts as F2"
        )
        return "UNPOPULATED", notes
    if distinct != len(clips):
        notes.append("REFUSED: duplicate recordings among the accepted clips")
        return "INCOMPLETE", notes
    if len(clips) < F2_REQUIRED_CLIPS or asymmetric < F2_REQUIRED_ASYMMETRIC:
        return "INCOMPLETE", notes
    if doc.get("status") != "POPULATED":
        # The contents qualify but the importer did not say so: the manifest was
        # not written by this importer, or was edited after it was.
        notes.append(f"REFUSED: manifest status is {doc.get('status')!r}, not 'POPULATED'")
        return "INCOMPLETE", notes
    return "POPULATED", notes


def _f8() -> tuple[str, list[str]]:
    human = []
    for path in sorted(F8_DIR.glob("*.json")):
        doc = json.loads(path.read_text())
        if doc.get("annotation_source") == "HUMAN_BY_EAR":
            human.append(path.name)
    synthetic = len(list(F8_DIR.glob("*.json"))) - len(human)
    if human:
        return "PARTIAL" if _f2()[0] != "POPULATED" else "POPULATED", [
            f"{len(human)} human annotation(s); {synthetic} ground-truth-by-construction (synthetic fixtures)"
        ]
    return "UNPOPULATED", [
        f"0 human annotations; {synthetic} ground-truth-by-construction (synthetic fixtures only)",
        "needs: two independent annotators + a third adjudicator, per "
        "fixtures/F8_oracle/ANNOTATOR_INSTRUCTIONS.md",
        "blocked on F2",
    ]


def main() -> int:
    f4, f5 = _f4(), _f5()
    f2, f8 = _f2(), _f8()
    gates = {"F4": f4[0], "F5": f5[0], "F2": f2[0], "F8": f8[0]}
    f7_ready = all(status == "POPULATED" for status in gates.values())
    f7 = ("POPULATED" if F7_PAIRS.exists() else "BLOCKED", [
        "authoring is gated on F4, F5, F2 and F8",
        f"blocking: {', '.join(k for k, v in sorted(gates.items()) if v != 'POPULATED') or 'none'}",
        "gate code is implemented and tested (vae.pairs.check_pair / run_gate)",
        "eligibility guard implemented and tested (vae.pairs.screen_pairs): a line is "
        "ineligible if ANY CMUdict variant uses a deferred phone",
    ] if not f7_ready else ["all prerequisites met; F7 authoring can begin"])

    print("FIXTURE READINESS")
    for name, (status, notes) in (("F4", f4), ("F5", f5), ("F2", f2),
                                  ("F8", f8), ("F7", f7)):
        print(f"  {name}: {status}")
        for note in notes:
            print(f"      - {note}")

    print("\nCODE READINESS")
    for label, state in (
        ("F4 loader (hard error on gap, Section 22 #10)", "ready"),
        ("F5 loader (hard error on unlisted onset)", "ready"),
        ("F4/F5 intake validators + importers", "ready"),
        ("F2 importer + Section 2 validation + manifest", "ready"),
        ("F8 worksheet generator + adjudicator (>20 ms rule)", "ready"),
        ("HEAR-vs-oracle reporting (Section 12 / 16 cross-cut)", "ready"),
        ("provenance + hashes on every fixture", "ready"),
        ("Section 11 pair gate", "ready, awaiting F7 data"),
        ("F7 eligibility guard (deferred CH/JH, any variant)", "ready"),
    ):
        print(f"  {label}: {state}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
