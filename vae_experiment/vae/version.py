"""EngineVersion (Section 15).

    EngineVersion = hash( code_version || config_hash || cmudict_hash ||
                          onset_table_hash || duration_table_hash ||
                          slot_mask_hash || resampler_version )

Exactly those seven inputs, in that order.  Nothing else may enter the hash —
runtime environment details are logged separately (Section 16) so that they are
visible without silently redefining the engine identity.

``code_version`` is a sha256 over the sorted source files of the ``vae``
package, so an edit to any stage changes the stamp on every record it produces.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .constants import RESAMPLER_VERSION

_PACKAGE_DIR = Path(__file__).resolve().parent
_SEPARATOR = b"\x1f"  # unit separator: unambiguous concatenation, no field collisions


def sha256_file(path: Path | str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def code_version() -> str:
    digest = hashlib.sha256()
    for source in sorted(_PACKAGE_DIR.glob("*.py")):
        digest.update(source.name.encode("utf-8"))
        digest.update(_SEPARATOR)
        digest.update(source.read_bytes())
        digest.update(_SEPARATOR)
    return digest.hexdigest()


@dataclass(frozen=True)
class EngineVersion:
    code_version: str
    config_hash: str
    cmudict_hash: str
    onset_table_hash: str
    duration_table_hash: str
    slot_mask_hash: str
    resampler_version: str

    @property
    def value(self) -> str:
        digest = hashlib.sha256()
        for part in (
            self.code_version,
            self.config_hash,
            self.cmudict_hash,
            self.onset_table_hash,
            self.duration_table_hash,
            self.slot_mask_hash,
            self.resampler_version,
        ):
            digest.update(part.encode("utf-8"))
            digest.update(_SEPARATOR)
        return digest.hexdigest()

    def to_record(self) -> dict:
        return {
            "engine_version": self.value,
            "code_version": self.code_version,
            "config_hash": self.config_hash,
            "cmudict_hash": self.cmudict_hash,
            "onset_table_hash": self.onset_table_hash,
            "duration_table_hash": self.duration_table_hash,
            "slot_mask_hash": self.slot_mask_hash,
            "resampler_version": self.resampler_version,
        }


def build_engine_version(
    *,
    config_hash: str,
    cmudict_hash: str,
    onset_table_hash: str,
    duration_table_hash: str,
    slot_mask_hash: str,
) -> EngineVersion:
    return EngineVersion(
        code_version=code_version(),
        config_hash=config_hash,
        cmudict_hash=cmudict_hash,
        onset_table_hash=onset_table_hash,
        duration_table_hash=duration_table_hash,
        slot_mask_hash=slot_mask_hash,
        resampler_version=RESAMPLER_VERSION,
    )
