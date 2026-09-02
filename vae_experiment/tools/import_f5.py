"""Import a hand-transcribed F5 legal-onset inventory into the fixture.

F5 becomes POPULATED only when its completeness is mechanically established:
the submitted table must match, exactly, the counts that the person who read the
named reference declares that reference contains, and a spec owner must have
approved the source.  No expected inventory and no expected count is hard-coded
anywhere in this repository, so a small or partial table cannot slip through as
"populated" -- it is reported as incomplete and F5 stays blocked.

That matters because the onset inventory decides every syllable boundary the
experiment produces.  A partial table would pass load and then hard-error at
syllabification, turning a load-time refusal into a scoring-time surprise.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from vae.intake import attested_cmudict_onsets, validate_f5, validate_f5_attestation  # noqa: E402
from vae.lexicon import load_lexicon  # noqa: E402

FIXTURE = ROOT / "fixtures" / "F5_onset_clusters" / "legal_onsets.json"
INTAKE = ROOT / "fixtures" / "F5_onset_clusters" / "intake_f5.csv"
ATTESTATION = ROOT / "fixtures" / "F5_onset_clusters" / "attestation_f5.json"


def _blocked(doc: dict, reasons: list[str]) -> int:
    print("F5 remains UNPOPULATED:")
    for reason in reasons:
        print(f"  - {reason}")
    print(f"\nSee {ATTESTATION.name} for what establishes completeness. Nothing has been "
          f"invented or inferred to fill the gap.")
    doc["status"] = "UNPOPULATED"
    doc["completeness_blockers"] = reasons
    FIXTURE.write_text(json.dumps(doc, indent=2) + "\n")
    return 2


def main() -> int:
    lexicon = load_lexicon()
    symbols = frozenset(
        line.split("\t")[0]
        for line in (ROOT / "fixtures" / "lexicon" / "cmudict.phones")
        .read_text(encoding="utf-8").splitlines() if line.strip()
    ) - lexicon.vowels

    doc = json.loads(FIXTURE.read_text())
    result = validate_f5(INTAKE, symbols)
    if result.errors:
        print("F5 intake REJECTED:")
        for error in result.errors:
            print(f"  - {error}")
        return 1

    if not ATTESTATION.exists():
        return _blocked(doc, [f"{ATTESTATION.name} is absent"])
    attestation = json.loads(ATTESTATION.read_text())
    blockers = validate_f5_attestation(attestation, result.rows)
    if blockers:
        return _blocked(doc, blockers)

    # Reported completeness evidence: onsets the pinned lexicon actually contains
    # that this table would refuse. Not used to extend the inventory.
    licensed = {tuple(row["phones"]) for row in result.rows}
    unlicensed = sorted(attested_cmudict_onsets(lexicon, symbols) - licensed)

    doc["status"] = "POPULATED"
    doc["onsets"] = result.rows
    doc.pop("blocked_reason", None)
    doc.pop("completeness_blockers", None)
    doc["provenance"] = {
        "reference": attestation["reference"],
        "dialect": attestation["dialect"],
        "approved_by_spec_owner": True,
        "transcriber": attestation.get("transcriber", ""),
        "declared_total_onsets": attestation["declared_total_onsets"],
        "n_onsets": len(result.rows),
        "intake_file": INTAKE.name,
        "intake_sha256": hashlib.sha256(INTAKE.read_bytes()).hexdigest(),
        "attestation_sha256": hashlib.sha256(ATTESTATION.read_bytes()).hexdigest(),
        "cmudict_word_initial_onsets_not_licensed": [" ".join(c) for c in unlicensed],
    }
    FIXTURE.write_text(json.dumps(doc, indent=2) + "\n")

    by_length: dict[int, int] = {}
    for row in result.rows:
        by_length[len(row["phones"])] = by_length.get(len(row["phones"]), 0) + 1
    print(f"F5 POPULATED: {len(result.rows)} onsets ("
          + ", ".join(f"{n} of length {k}" for k, n in sorted(by_length.items())) + ")")
    print(f"  matches the {attestation['declared_total_onsets']} declared by "
          f"{attestation['reference'].get('author', '?')}, "
          f"{attestation['reference'].get('section_or_table', '?')}")
    if unlicensed:
        print(f"  NOTE {len(unlicensed)} word-initial onset(s) attested in CMUdict are not "
              f"licensed by this table. Pronunciation variants using them are SKIPPED and "
              f"logged (Section 9); a word is excluded only if NO variant survives.")
        print(f"       Recorded in provenance. First few: "
              f"{', '.join(' '.join(c) for c in unlicensed[:8])}")
    print(f"  fixture sha256: {hashlib.sha256(FIXTURE.read_bytes()).hexdigest()}")
    print("  NOTE: this changes onset_table_hash and therefore EngineVersion on every record.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
