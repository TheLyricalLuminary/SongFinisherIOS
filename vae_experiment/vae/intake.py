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

from .oracle import ADJUDICATION_THRESHOLD_S

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


ACCEPTED_GA_DIALECTS = ("GA", "GENERAL AMERICAN", "AMERICAN ENGLISH", "US", "ENGLISH (US)")


def validate_f5_attestation(attestation: dict, rows: list[dict]) -> list[str]:
    """Check a submitted onset table against its completeness attestation.

    The pipeline cannot know English phonotactics, so it cannot decide on its own
    whether an inventory is complete -- and it must not invent an expected list or
    an expected count in order to pretend otherwise.  What it CAN check is that
    the transcription matches what the person who read the named reference says
    that reference contains, and that a spec owner approved the source.  That is
    what makes the completeness mechanically established rather than assumed.

    Returns a list of reasons the table may NOT be marked POPULATED.
    """
    errors: list[str] = []

    if not attestation.get("approved_by_spec_owner"):
        errors.append(
            "approved_by_spec_owner is not true. The onset inventory decides every syllable "
            "boundary the experiment produces, so the source must be approved before it is used."
        )

    reference = attestation.get("reference") or {}
    for key in ("author", "title", "section_or_table"):
        if not str(reference.get(key) or "").strip():
            errors.append(f"reference.{key} is empty; the source must be named")

    dialect = str(attestation.get("dialect") or "").strip()
    if not dialect:
        errors.append("dialect is empty")
    elif dialect.upper() not in ACCEPTED_GA_DIALECTS:
        errors.append(
            f"dialect {dialect!r} is not General American. The lexicon is CMUdict; an SSBE "
            f"inventory would admit onsets CMUdict never produces."
        )

    if not str(attestation.get("transcriber") or "").strip():
        errors.append("transcriber is empty")

    declared_total = attestation.get("declared_total_onsets")
    if declared_total is None:
        errors.append(
            "declared_total_onsets is null. Completeness is established by declaring how many "
            "onsets the named reference lists and checking the transcription against it."
        )
    elif int(declared_total) != len(rows):
        errors.append(
            f"table has {len(rows)} onsets but the reference is declared to list "
            f"{int(declared_total)}. The transcription is incomplete or over-complete."
        )

    declared_by_length = attestation.get("declared_counts_by_length") or {}
    actual_by_length: dict[int, int] = {}
    for row in rows:
        length = len(row["phones"])
        actual_by_length[length] = actual_by_length.get(length, 0) + 1
    if not declared_by_length or any(v is None for v in declared_by_length.values()):
        errors.append("declared_counts_by_length has unfilled entries")
    else:
        for key, declared in sorted(declared_by_length.items()):
            actual = actual_by_length.get(int(key), 0)
            if int(declared) != actual:
                errors.append(
                    f"length-{key} onsets: reference declared {int(declared)}, table has {actual}"
                )
        undeclared = sorted(set(actual_by_length) - {int(k) for k in declared_by_length})
        for length in undeclared:
            errors.append(
                f"table contains {actual_by_length[length]} onset(s) of length {length}, "
                f"which the attestation does not declare"
            )
    return errors


def attested_cmudict_onsets(lexicon, valid_symbols: frozenset[str]) -> set[tuple[str, ...]]:
    """Word-initial consonant clusters actually attested in the pinned lexicon.

    Used only as a REPORTED completeness diagnostic: a table that fails to license
    an onset the lexicon contains will hard-error on those words at
    syllabification.  It is not used to derive or extend the inventory -- a
    frequency-derived inventory is a different object from a phonotactic one.
    """
    attested: set[tuple[str, ...]] = set()
    for word in lexicon._entries:                                   # noqa: SLF001
        for pronunciation in lexicon.variants(word):
            cluster: list[str] = []
            for phone in pronunciation.phones:
                if phone in valid_symbols:
                    cluster.append(phone)
                else:
                    break
            if cluster:
                attested.add(tuple(cluster))
    return attested


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


# --------------------------------------------------------------------------- #
# F8 annotation merging (Section 12)
# --------------------------------------------------------------------------- #

@dataclass
class MergeResult:
    """The outcome of combining two independent annotations of one clip."""

    beat_times_s: list[float] = field(default_factory=list)
    anchor_times_s: list[float] = field(default_factory=list)
    anchor_sigma_s: list[float] = field(default_factory=list)
    adjudicated_slots: list[int] = field(default_factory=list)
    adjudicated_beats: list[int] = field(default_factory=list)
    tempo_bpm: float = 0.0
    needs_adjudication: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors and not self.needs_adjudication


def validate_annotation(doc: dict, expected_slot_count: int, label: str) -> list[str]:
    """Structural validation of one annotator's file, before anything is combined.

    Metadata and slot indices are checked here rather than assumed, so that two
    files describing different clips, different masks, or differently ordered
    slots can never be merged into a plausible-looking oracle.
    """
    errors: list[str] = []
    for key in ("audio_id", "slot_mask_id"):
        if not str(doc.get(key) or "").strip():
            errors.append(f"{label}: missing {key}")

    beats = doc.get("beat_times_s") or []
    if not beats:
        errors.append(f"{label}: beat_times_s is empty")
    else:
        try:
            values = [float(b) for b in beats]
        except (TypeError, ValueError):
            errors.append(f"{label}: beat_times_s contains a non-numeric value")
            values = []
        if values and any(b <= a for a, b in zip(values, values[1:])):
            errors.append(f"{label}: beat_times_s must be strictly increasing")

    slots = doc.get("slots") or []
    if len(slots) != expected_slot_count:
        errors.append(
            f"{label}: {len(slots)} slots annotated but the mask has {expected_slot_count}"
        )
    else:
        indices = [s.get("slot_index") for s in slots]
        if indices != list(range(expected_slot_count)):
            errors.append(
                f"{label}: slot_index must be 0..{expected_slot_count - 1} in order, got {indices}"
            )
        missing = [s.get("slot_index") for s in slots if s.get("anchor_time_s") is None]
        if missing:
            errors.append(f"{label}: slots {missing} have no anchor_time_s")
    return errors


def _resolve_pairs(
    values_a: list[float],
    values_b: list[float],
    values_c: list[float] | None,
    threshold: float,
    what: str,
) -> tuple[list[float], list[float], list[int], list[str]]:
    """Pair-wise resolution shared by beats and anchors.

    Corresponding marks are paired BY INDEX and never merged as a set: two
    annotators marking the same event a few milliseconds apart describe one
    event, not two, and unioning them would fabricate an extra one.
    """
    resolved: list[float] = []
    spreads: list[float] = []
    adjudicated: list[int] = []
    pending: list[str] = []

    for i, (a, b) in enumerate(zip(values_a, values_b)):
        spread = abs(a - b)
        if spread > threshold:
            if values_c is None:
                pending.append(f"{what} {i} differs by {1000 * spread:.1f} ms")
                continue
            resolved.append(values_c[i])
            adjudicated.append(i)
        else:
            resolved.append((a + b) / 2.0)
        spreads.append(spread / 2.0)
    return resolved, spreads, adjudicated, pending


def merge_annotations(
    doc_a: dict,
    doc_b: dict,
    doc_c: dict | None,
    expected_slot_count: int,
    threshold: float = ADJUDICATION_THRESHOLD_S,
) -> MergeResult:
    """Combine two independent annotations, adjudicating BOTH beats and anchors.

    Section 12 has the annotators mark beat positions *and* per-slot anchors, so
    both are adjudicated on the same > 20 ms rule.  Beats are paired by index;
    combining the two beat lists as a set would turn one beat marked at 0.501 and
    0.503 into two beats and corrupt both the beat grid and the derived tempo.
    """
    result = MergeResult()

    result.errors.extend(validate_annotation(doc_a, expected_slot_count, "annotator A"))
    result.errors.extend(validate_annotation(doc_b, expected_slot_count, "annotator B"))
    if doc_c is not None:
        result.errors.extend(validate_annotation(doc_c, expected_slot_count, "adjudicator"))
    if result.errors:
        return result

    for key in ("audio_id", "slot_mask_id"):
        values = {doc_a[key], doc_b[key]} | ({doc_c[key]} if doc_c else set())
        if len(values) != 1:
            result.errors.append(f"annotations disagree on {key}: {sorted(values)}")
    if result.errors:
        return result

    beats_a = [float(b) for b in doc_a["beat_times_s"]]
    beats_b = [float(b) for b in doc_b["beat_times_s"]]
    if len(beats_a) != len(beats_b):
        result.errors.append(
            f"annotators marked different numbers of beats ({len(beats_a)} vs {len(beats_b)}); "
            f"they cannot be paired, so the clip needs re-annotation rather than merging"
        )
        return result
    beats_c = None
    if doc_c is not None:
        beats_c = [float(b) for b in doc_c["beat_times_s"]]
        if len(beats_c) != len(beats_a):
            result.errors.append(
                f"adjudicator marked {len(beats_c)} beats, annotators marked {len(beats_a)}"
            )
            return result

    beats, _beat_spreads, result.adjudicated_beats, beat_pending = _resolve_pairs(
        beats_a, beats_b, beats_c, threshold, "beat"
    )
    anchors_a = [float(s["anchor_time_s"]) for s in doc_a["slots"]]
    anchors_b = [float(s["anchor_time_s"]) for s in doc_b["slots"]]
    anchors_c = [float(s["anchor_time_s"]) for s in doc_c["slots"]] if doc_c else None
    anchors, sigmas, result.adjudicated_slots, slot_pending = _resolve_pairs(
        anchors_a, anchors_b, anchors_c, threshold, "slot"
    )

    result.needs_adjudication = beat_pending + slot_pending
    if result.needs_adjudication:
        return result

    if any(b <= a for a, b in zip(beats, beats[1:])):
        result.errors.append("resolved beat sequence is not strictly increasing")
        return result
    if len(beats) < 2:
        result.errors.append("at least two beats are needed to derive a tempo")
        return result

    # Tempo from the RESOLVED sequence.  The mean inter-beat interval of a
    # constant-tempo grid is (last - first) / (n - 1).
    result.beat_times_s = beats
    result.anchor_times_s = anchors
    result.anchor_sigma_s = sigmas
    result.tempo_bpm = 60.0 * (len(beats) - 1) / (beats[-1] - beats[0])
    return result
