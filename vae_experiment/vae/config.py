"""Versioned configuration (Section 18).

A single versioned file holds every Section 18 *parameterized* value.  Nothing
here may be tuned on the evaluation set (Section 10), and nothing may change
after human data collection begins (Section 14 Void, Section 22 failure #13).

``Config`` is frozen and hashable: ``Config.config_hash`` is computed over the
*effective* parameter set actually in force, so a sweep point produces a
different hash — and therefore a different ``EngineVersion`` — than the base
configuration.  That is what makes post-hoc tuning detectable rather than
invisible.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .errors import ConfigError

# The Section 18 "Parameterized" list, verbatim and complete.  ``gamma`` is the
# spec's Greek gamma (CONSONANT_COMPRESSION_EXPONENT); ``epsilon_tie`` and
# ``epsilon_num`` are the spec's eps_tie and eps_num.
SECTION_18_PARAMETERS = (
    "W_match",
    "SIGMA_FLOOR_BASE",
    "SIGMA_ATTACK_COEF",
    "SIGMA_GRID_ONLY",
    "SIGMA_COEF",
    "I_MIN",
    "I_reference",
    "gamma",
    "F_MIN_BASE",
    "DIPHTHONG_FACTOR",
    "BORDERLINE_FACTOR",
    "NUCLEUS_COMFORT",
    "PRE_CAP_FRAC",
    "POST_CAP_FRAC",
    "LEAD_IN",
    "PHRASE_TAIL",
    "ASYMMETRY_MIN",
    "MARGIN_MIN",
    "LOAD_TOL",
    "epsilon_tie",
    "epsilon_num",
    "W_stress",
    "W_count",
    "W_anchor",
    "W_fit",
)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "config_v1.json"


@dataclass(frozen=True)
class Config:
    config_id: str
    source_path: str
    source_file_sha256: str
    _values: Mapping[str, float]

    def __getattr__(self, name: str) -> float:
        try:
            return object.__getattribute__(self, "_values")[name]
        except KeyError as exc:  # pragma: no cover - defensive
            raise AttributeError(name) from exc

    def __getitem__(self, name: str) -> float:
        return self._values[name]

    def as_dict(self) -> dict:
        return dict(self._values)

    @property
    def config_hash(self) -> str:
        """sha256 over the canonical serialisation of the effective parameters."""
        canonical = json.dumps(
            {k: _canon_float(self._values[k]) for k in SECTION_18_PARAMETERS},
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def with_overrides(self, **overrides: float) -> "Config":
        """Return a sweep point.  Unknown keys are a hard error, never ignored."""
        unknown = sorted(set(overrides) - set(SECTION_18_PARAMETERS))
        if unknown:
            raise ConfigError(f"not Section 18 parameters: {unknown}")
        values = dict(self._values)
        values.update(overrides)
        return Config(
            config_id=self.config_id,
            source_path=self.source_path,
            source_file_sha256=self.source_file_sha256,
            _values=values,
        )


def _canon_float(value: Any) -> str:
    """Repr floats deterministically so the hash cannot drift on formatting."""
    return repr(float(value))


def load_config(path: Path | str | None = None) -> Config:
    path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    raw_bytes = path.read_bytes()
    doc = json.loads(raw_bytes.decode("utf-8"))
    params = doc.get("parameters")
    if not isinstance(params, dict):
        raise ConfigError(f"{path}: missing 'parameters' object")

    present = set(params)
    required = set(SECTION_18_PARAMETERS)
    missing = sorted(required - present)
    extra = sorted(present - required)
    if missing:
        raise ConfigError(f"{path}: missing Section 18 parameters: {missing}")
    if extra:
        raise ConfigError(f"{path}: parameters not in Section 18: {extra}")

    values = {k: float(params[k]) for k in SECTION_18_PARAMETERS}
    _validate(values)
    return Config(
        config_id=str(doc.get("config_id", path.stem)),
        source_path=str(path),
        source_file_sha256=hashlib.sha256(raw_bytes).hexdigest(),
        _values=values,
    )


def _validate(values: Mapping[str, float]) -> None:
    if not 0.0 < values["gamma"] < 1.0:
        raise ConfigError("Section 7 requires 0 < gamma < 1")
    if values["SIGMA_COEF"] < 0.0:
        raise ConfigError("SIGMA_COEF must be non-negative")
    if values["I_MIN"] <= 0.0:
        raise ConfigError("I_MIN must be positive")
    if values["NUCLEUS_COMFORT"] <= values["F_MIN_BASE"]:
        raise ConfigError("NUCLEUS_COMFORT must exceed F_MIN_BASE for s_fit to be defined")
    if values["BORDERLINE_FACTOR"] <= 1.0:
        raise ConfigError("BORDERLINE_FACTOR must exceed 1.0")
    if values["DIPHTHONG_FACTOR"] < 1.0:
        raise ConfigError("DIPHTHONG_FACTOR must be at least 1.0")
    if values["ASYMMETRY_MIN"] <= 1.0:
        raise ConfigError("ASYMMETRY_MIN must exceed 1.0 to mean anything")
    for weight in ("W_stress", "W_count", "W_anchor", "W_fit"):
        if values[weight] < 0.0:
            raise ConfigError(f"{weight} must be non-negative")


def load_sweep_points(path: Path | str | None = None) -> dict:
    path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    doc = json.loads(Path(path).read_bytes().decode("utf-8"))
    return dict(doc.get("sweep", {}).get("points", {}))
