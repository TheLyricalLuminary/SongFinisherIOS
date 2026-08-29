"""Intake and validation for the F4 and F5 data-extraction fixtures.

Neither fixture may be guessed (Section 17, Section 22 failure #10).  These
helpers exist so that a table extracted BY HAND from a named source can be
imported with its provenance intact and validated before it is ever consulted.

The validators are deliberately strict and refuse partial data silently: an
uncovered phone is REPORTED as a gap, never filled.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

# The 24 ARPAbet consonants.  Vowels are not required: only consonants are
# budgeted (Section 7), the nucleus being the residual.
ARPABET_CONSONANTS = (
    "B", "CH", "D", "DH", "F", "G", "HH", "JH", "K", "L", "M", "N",
    "NG", "P", "R", "S", "SH", "T", "TH", "V", "W", "Y", "Z", "ZH",
)


@dataclass
class IntakeResult:
    rows: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors and not self.gaps


def read_csv_rows(path: Path | str) -> list[dict]:
    """Read a '#'-commented CSV into dicts, preserving file order."""
    lines = [
        line for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    return list(csv.DictReader(lines))


def validate_f4(path: Path | str) -> IntakeResult:
    """Validate an F4 intake CSV against the acceptance requirements."""
    result = IntakeResult()
    seen: dict[str, dict] = {}

    for i, row in enumerate(read_csv_rows(path), start=2):
        phone = (row.get("arpabet") or "").strip().upper()
        if not phone:
            result.errors.append(f"row {i}: empty arpabet column")
            continue
        if phone not in ARPABET_CONSONANTS:
            result.errors.append(f"row {i}: {phone!r} is not an ARPAbet consonant")
            continue
        if phone in seen:
            result.errors.append(f"row {i}: duplicate entry for {phone}")
            continue

        nominal = (row.get("d_nominal_ms") or "").strip()
        floor = (row.get("d_floor_ms") or "").strip()
        source = (row.get("source") or "").strip()
        locator = (row.get("page_or_table") or "").strip()

        if not nominal and not floor and not source:
            result.gaps.append(phone)          # left blank on purpose: a reported gap
            continue

        missing = [
            name for name, value in
            (("d_nominal_ms", nominal), ("d_floor_ms", floor),
             ("source", source), ("page_or_table", locator))
            if not value
        ]
        if missing:
            result.errors.append(
                f"row {i} ({phone}): partially filled, missing {missing}. "
                f"Leave the whole row blank to report a gap, or complete it."
            )
            continue

        try:
            nominal_ms, floor_ms = float(nominal), float(floor)
        except ValueError:
            result.errors.append(f"row {i} ({phone}): durations must be numeric")
            continue
        if nominal_ms <= 0.0 or floor_ms <= 0.0:
            result.errors.append(f"row {i} ({phone}): durations must be positive")
            continue
        if floor_ms > nominal_ms:
            result.errors.append(
                f"row {i} ({phone}): d_floor_ms {floor_ms} exceeds d_nominal_ms {nominal_ms}; "
                f"the floor is incompressible and cannot exceed the nominal duration"
            )
            continue

        seen[phone] = {
            "d_nominal_s": nominal_ms / 1000.0,
            "d_floor_s": floor_ms / 1000.0,
            "source": source,
            "page_or_table": locator,
            "notes": (row.get("notes") or "").strip(),
        }

    result.gaps.extend(p for p in ARPABET_CONSONANTS if p not in seen and p not in result.gaps)
    result.gaps.sort()
    result.rows = [{"arpabet": p, **seen[p]} for p in sorted(seen)]
    return result


def validate_f5(path: Path | str, valid_symbols: frozenset[str]) -> IntakeResult:
    """Validate an F5 intake CSV against the acceptance requirements."""
    result = IntakeResult()
    seen: set[tuple[str, ...]] = set()

    for i, row in enumerate(read_csv_rows(path), start=2):
        raw = (row.get("onset") or "").strip().upper()
        if not raw:
            result.errors.append(f"row {i}: empty onset column")
            continue
        cluster = tuple(raw.split())
        unknown = [p for p in cluster if p not in valid_symbols]
        if unknown:
            result.errors.append(f"row {i}: not ARPAbet consonants: {unknown}")
            continue
        if cluster in seen:
            result.errors.append(f"row {i}: duplicate onset {' '.join(cluster)!r}")
            continue
        source = (row.get("source") or "").strip()
        locator = (row.get("page_or_table") or "").strip()
        if not source or not locator:
            result.errors.append(
                f"row {i} ({' '.join(cluster)}): 'source' and 'page_or_table' are mandatory"
            )
            continue
        seen.add(cluster)
        result.rows.append({
            "phones": list(cluster),
            "source": source,
            "page_or_table": locator,
            "dialect": (row.get("dialect") or "").strip(),
            "notes": (row.get("notes") or "").strip(),
        })

    if not result.rows:
        result.errors.append("no onsets supplied")
        return result

    singletons = {c["phones"][0] for c in result.rows if len(c["phones"]) == 1}
    if not singletons:
        result.errors.append(
            "no singleton onsets listed. The Maximum Onset Principle consults this table at "
            "every syllable boundary, so every consonant that can open a syllable must appear "
            "as a one-element entry, not only the clusters."
        )
    result.rows.sort(key=lambda c: (len(c["phones"]), c["phones"]))
    return result
