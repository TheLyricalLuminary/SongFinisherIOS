"""Import a hand-transcribed F5 legal-onset inventory into the fixture.

Reads fixtures/F5_onset_clusters/intake_f5.csv, validates it, and writes the
fixture with provenance.  The onset inventory decides every syllable boundary
the experiment produces, so the dialect each entry was taken from is recorded
and a mismatch against the CMUdict (General American) lexicon is reported rather
than absorbed.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from vae.intake import validate_f5  # noqa: E402
from vae.lexicon import load_lexicon  # noqa: E402

FIXTURE = ROOT / "fixtures" / "F5_onset_clusters" / "legal_onsets.json"
INTAKE = ROOT / "fixtures" / "F5_onset_clusters" / "intake_f5.csv"
LEXICON_DIALECT = "GA"          # CMUdict is General American (Section 9)


def main() -> int:
    lexicon = load_lexicon()
    symbols = frozenset(
        line.split("\t")[0]
        for line in (ROOT / "fixtures" / "lexicon" / "cmudict.phones")
        .read_text(encoding="utf-8").splitlines() if line.strip()
    ) - lexicon.vowels

    result = validate_f5(INTAKE, symbols)
    if result.errors:
        print("F5 intake REJECTED:")
        for error in result.errors:
            print(f"  - {error}")
        return 1

    dialects = sorted({row["dialect"] for row in result.rows if row["dialect"]})
    mismatched = [d for d in dialects if d.upper() not in (LEXICON_DIALECT, "GENERAL AMERICAN")]

    doc = json.loads(FIXTURE.read_text())
    doc["status"] = "POPULATED"
    doc["onsets"] = result.rows
    doc.pop("blocked_reason", None)
    doc["provenance"] = {
        "sources": sorted({row["source"] for row in result.rows}),
        "dialects": dialects,
        "lexicon_dialect": LEXICON_DIALECT,
        "dialect_mismatch": mismatched,
        "intake_file": INTAKE.name,
        "intake_sha256": hashlib.sha256(INTAKE.read_bytes()).hexdigest(),
        "n_onsets": len(result.rows),
    }
    FIXTURE.write_text(json.dumps(doc, indent=2) + "\n")

    by_length: dict[int, int] = {}
    for row in result.rows:
        by_length[len(row["phones"])] = by_length.get(len(row["phones"]), 0) + 1
    print(f"F5 POPULATED: {len(result.rows)} onsets "
          + ", ".join(f"{n} of length {k}" for k, n in sorted(by_length.items())))
    if mismatched:
        print(f"  WARNING dialect mismatch: entries from {mismatched} against a "
              f"{LEXICON_DIALECT} lexicon. Recorded in provenance.dialect_mismatch, not absorbed.")
    print(f"  fixture sha256: {hashlib.sha256(FIXTURE.read_bytes()).hexdigest()}")
    print("  NOTE: this changes onset_table_hash and therefore EngineVersion on every record.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
