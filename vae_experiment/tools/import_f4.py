"""Import a hand-extracted F4 duration table into the fixture, with provenance.

Reads fixtures/F4_phone_durations/intake_f4.csv, validates it against the
acceptance requirements, and writes the fixture only if every one of the 24
ARPAbet consonants is covered.  A partial table is REPORTED as a gap list and
never written as POPULATED -- Section 22 failure #10 makes a duration-table gap
a hard error, and a half-filled fixture would turn that into a surprise at
scoring time rather than a refusal at load time.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from vae.intake import ARPABET_CONSONANTS, validate_f4  # noqa: E402

FIXTURE = ROOT / "fixtures" / "F4_phone_durations" / "phone_durations.json"
INTAKE = ROOT / "fixtures" / "F4_phone_durations" / "intake_f4.csv"


def main() -> int:
    result = validate_f4(INTAKE)
    doc = json.loads(FIXTURE.read_text())

    if result.errors:
        print("F4 intake REJECTED:")
        for error in result.errors:
            print(f"  - {error}")
        return 1

    if result.gaps:
        print(f"F4 remains UNPOPULATED: {len(result.gaps)} of "
              f"{len(ARPABET_CONSONANTS)} consonants have no sourced value.")
        print(f"  covered ({len(result.rows)}): "
              f"{' '.join(r['arpabet'] for r in result.rows) or '(none)'}")
        print(f"  UNCOVERED ({len(result.gaps)}): {' '.join(result.gaps)}")
        print("\nThese phones need d_nominal and d_floor from the sources named in")
        print(f"{FIXTURE.name} -> required_source_material, or from a forced-aligned")
        print("singing corpus (Section 17 F4). Nothing has been guessed or defaulted.")
        doc["status"] = "UNPOPULATED"
        doc["uncovered_phones"] = result.gaps
        FIXTURE.write_text(json.dumps(doc, indent=2) + "\n")
        return 2

    phones = {
        row["arpabet"]: {
            "d_nominal_s": row["d_nominal_s"],
            "d_floor_s": row["d_floor_s"],
            "source": row["source"],
            "page_or_table": row["page_or_table"],
            **({"notes": row["notes"]} if row["notes"] else {}),
        }
        for row in result.rows
    }
    sources = sorted({row["source"] for row in result.rows})
    doc["status"] = "POPULATED"
    doc["phones"] = phones
    doc.pop("uncovered_phones", None)
    doc.pop("blocked_reason", None)
    doc["provenance"] = {
        "sources": sources,
        "intake_file": INTAKE.name,
        "intake_sha256": hashlib.sha256(INTAKE.read_bytes()).hexdigest(),
        "n_phones": len(phones),
    }
    FIXTURE.write_text(json.dumps(doc, indent=2) + "\n")
    print(f"F4 POPULATED: {len(phones)}/{len(ARPABET_CONSONANTS)} consonants")
    for source in sources:
        print(f"  source: {source}")
    print(f"  fixture sha256: {hashlib.sha256(FIXTURE.read_bytes()).hexdigest()}")
    print("  NOTE: this changes duration_table_hash and therefore EngineVersion on every record.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
