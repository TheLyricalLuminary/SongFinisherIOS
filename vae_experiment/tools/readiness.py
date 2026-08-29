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

from vae.intake import ARPABET_CONSONANTS, validate_f4  # noqa: E402
from vae.tables import load_duration_table, load_onset_table  # noqa: E402

F2_MANIFEST = ROOT / "fixtures" / "F2_clips" / "manifest.json"
F7_PAIRS = ROOT / "fixtures" / "F7_pairs" / "pairs.json"
F8_DIR = ROOT / "fixtures" / "F8_oracle"


def _f4() -> tuple[str, list[str]]:
    table = load_duration_table()
    if table.is_populated:
        covered = set(table.covered_phones())
        gaps = sorted(set(ARPABET_CONSONANTS) - covered)
        if gaps:
            return "INCOMPLETE", [f"uncovered phones: {' '.join(gaps)}"]
        return "POPULATED", []
    intake = validate_f4(ROOT / "fixtures" / "F4_phone_durations" / "intake_f4.csv")
    return "UNPOPULATED", [
        f"{len(intake.gaps)}/{len(ARPABET_CONSONANTS)} consonants have no sourced value",
        "needs: Klatt (1976) JASA 59(5) 1208-1221 and Crystal & House (1988) JASA 83(4) 1553-1573",
        "note: d_floor corresponds to Klatt's MINDUR, published in Klatt (1979) / MITalk, "
        "not in Klatt (1976)",
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


def _f2() -> tuple[str, list[str]]:
    if not F2_MANIFEST.exists():
        return "UNPOPULATED", ["no clips supplied; see fixtures/F2_clips/ACCEPTANCE.md",
                               "needs: 20 real accompaniment clips, >=12 with interval asymmetry"]
    doc = json.loads(F2_MANIFEST.read_text())
    req = doc.get("requirements", {})
    return doc.get("status", "UNKNOWN"), [
        f"{req.get('clips_accepted', 0)}/{req.get('clips_required', 20)} accepted, "
        f"{req.get('asymmetric_accepted', 0)}/{req.get('asymmetric_required', 12)} asymmetric",
        f"{len(doc.get('rejected', []))} rejected by Section 2",
    ]


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
    ):
        print(f"  {label}: {state}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
