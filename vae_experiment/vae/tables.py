"""F4 (phone durations) and F5 (legal onsets): strict loaders.

Both fixtures are data-extraction items (Section 17).  Neither may be guessed.
The loaders therefore have exactly three states:

*   ``POPULATED``      — authored from the named sources, usable.
*   ``UNPOPULATED``    — the schema stub exists so ``EngineVersion`` can hash it,
                         but *any lookup raises*.  Nothing silently defaults.
*   ``SYNTHETIC_TEST_ONLY`` — a placeholder used to exercise code paths in the
                         unit tests.  It is refused unless the caller passes
                         ``allow_synthetic=True``, and every table loaded this
                         way reports ``is_synthetic``, which the runners stamp
                         onto their output so no number produced from it can be
                         mistaken for a result.

Section 22 failure #10: "Duration table gap -> Missing phone in F4 -> Hard error,
never a silent default."
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .constants import ARPABET_CONSONANTS, V1_DEFERRED_CONSONANTS
from .errors import FixtureUnpopulatedError, MissingOnsetTableError, MissingPhoneError
from .version import sha256_file

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
DEFAULT_DURATION_PATH = FIXTURES / "F4_phone_durations" / "phone_durations.json"
DEFAULT_ONSET_PATH = FIXTURES / "F5_onset_clusters" / "legal_onsets.json"

STATUS_POPULATED = "POPULATED"
STATUS_UNPOPULATED = "UNPOPULATED"
STATUS_SYNTHETIC = "SYNTHETIC_TEST_ONLY"


@dataclass(frozen=True)
class PhoneDuration:
    d_nominal_s: float
    d_floor_s: float
    source: str


@dataclass(frozen=True)
class DurationTable:
    """F4.  ``duration_table_hash`` is one of the seven EngineVersion inputs."""

    status: str
    source_path: str
    sha256: str
    required_source_material: tuple[str, ...]
    _phones: dict[str, PhoneDuration]

    @property
    def is_populated(self) -> bool:
        return self.status == STATUS_POPULATED

    @property
    def is_synthetic(self) -> bool:
        return self.status == STATUS_SYNTHETIC

    def covered_phones(self) -> tuple[str, ...]:
        return tuple(sorted(self._phones))

    def d_nominal(self, phone: str) -> float:
        return self._lookup(phone).d_nominal_s

    def d_floor(self, phone: str) -> float:
        return self._lookup(phone).d_floor_s

    def _lookup(self, phone: str) -> PhoneDuration:
        if self.status == STATUS_UNPOPULATED:
            raise FixtureUnpopulatedError("F4", "; ".join(self.required_source_material))
        try:
            return self._phones[phone]
        except KeyError:
            if phone in V1_DEFERRED_CONSONANTS:
                raise MissingPhoneError(
                    f"{phone!r} is DEFERRED from V1: F4 budgets "
                    f"{len(ARPABET_CONSONANTS) - len(V1_DEFERRED_CONSONANTS)} scalar "
                    f"consonants and carries no row for either affricate "
                    f"({', '.join(V1_DEFERRED_CONSONANTS)}). This is still a hard error, "
                    f"never a silent default (Section 22 failure #10). Reaching this "
                    f"lookup means the F7 eligibility guard (vae.pairs) was not applied: "
                    f"a candidate line containing a deferred phone must be excluded from "
                    f"the pool, not scored."
                ) from None
            raise MissingPhoneError(
                f"F4 has no entry for ARPAbet phone {phone!r}. Section 22 failure #10: a "
                f"duration-table gap is a hard error, never a silent default. Populate it "
                f"from the sources named in {self.source_path}."
            ) from None


@dataclass(frozen=True)
class OnsetTable:
    """F5.  ``onset_table_hash`` is one of the seven EngineVersion inputs."""

    status: str
    source_path: str
    sha256: str
    required_source_material: tuple[str, ...]
    _onsets: frozenset[tuple[str, ...]]
    _max_length: int

    @property
    def is_populated(self) -> bool:
        return self.status == STATUS_POPULATED

    @property
    def is_synthetic(self) -> bool:
        return self.status == STATUS_SYNTHETIC

    @property
    def max_onset_length(self) -> int:
        return self._max_length

    @property
    def n_onsets(self) -> int:
        return len(self._onsets)

    def is_legal_onset(self, cluster: tuple[str, ...]) -> bool:
        if self.status == STATUS_UNPOPULATED:
            raise FixtureUnpopulatedError("F5", "; ".join(self.required_source_material))
        return len(cluster) == 0 or tuple(cluster) in self._onsets

    def require_legal_onset(self, cluster: tuple[str, ...]) -> None:
        if not self.is_legal_onset(cluster):
            raise MissingOnsetTableError(
                f"F5 does not list {' '.join(cluster)!r} as a legal English onset. "
                f"Populate it from the reference named in {self.source_path}."
            )


def _check_status(status: str, fixture_id: str, allow_synthetic: bool) -> None:
    if status not in (STATUS_POPULATED, STATUS_UNPOPULATED, STATUS_SYNTHETIC):
        raise ValueError(f"{fixture_id}: unknown status {status!r}")
    if status == STATUS_SYNTHETIC and not allow_synthetic:
        raise FixtureUnpopulatedError(
            fixture_id,
            "the file on disk is a SYNTHETIC_TEST_ONLY placeholder, not authored data. "
            "Pass allow_synthetic=True only from tests, never from a run whose numbers "
            "will be reported.",
        )


def load_duration_table(
    path: Path | str | None = None, *, allow_synthetic: bool = False
) -> DurationTable:
    path = Path(path) if path is not None else DEFAULT_DURATION_PATH
    doc = json.loads(path.read_bytes().decode("utf-8"))
    status = str(doc.get("status", STATUS_UNPOPULATED))
    _check_status(status, "F4", allow_synthetic)

    phones: dict[str, PhoneDuration] = {}
    for phone in sorted(doc.get("phones", {})):
        entry = doc["phones"][phone]
        source = str(entry.get("source", "")).strip()
        if status == STATUS_POPULATED and not source:
            raise ValueError(
                f"F4 entry {phone!r} has no 'source'. An entry without a source is not "
                f"populated data (see population_instructions in {path})."
            )
        phones[phone] = PhoneDuration(
            d_nominal_s=float(entry["d_nominal_s"]),
            d_floor_s=float(entry["d_floor_s"]),
            source=source,
        )
    return DurationTable(
        status=status,
        source_path=str(path),
        sha256=sha256_file(path),
        required_source_material=tuple(doc.get("required_source_material", ())),
        _phones=phones,
    )


def load_onset_table(
    path: Path | str | None = None, *, allow_synthetic: bool = False
) -> OnsetTable:
    path = Path(path) if path is not None else DEFAULT_ONSET_PATH
    doc = json.loads(path.read_bytes().decode("utf-8"))
    status = str(doc.get("status", STATUS_UNPOPULATED))
    _check_status(status, "F5", allow_synthetic)

    onsets: set[tuple[str, ...]] = set()
    for entry in doc.get("onsets", []):
        cluster = tuple(str(p) for p in (entry["phones"] if isinstance(entry, dict) else entry))
        if status == STATUS_POPULATED and isinstance(entry, dict) and not entry.get("source"):
            raise ValueError(f"F5 entry {cluster} has no 'source'.")
        onsets.add(cluster)
    return OnsetTable(
        status=status,
        source_path=str(path),
        sha256=sha256_file(path),
        required_source_material=tuple(doc.get("required_source_material", ())),
        _onsets=frozenset(onsets),
        _max_length=max((len(c) for c in onsets), default=0),
    )
