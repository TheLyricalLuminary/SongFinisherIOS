"""Section 18 config completeness and Section 15 EngineVersion composition."""

from __future__ import annotations

import json

import pytest

from vae.config import SECTION_18_PARAMETERS, DEFAULT_CONFIG_PATH, load_config
from vae.errors import ConfigError
from vae.version import build_engine_version


def test_every_section_18_parameter_is_present_and_no_others():
    doc = json.loads(DEFAULT_CONFIG_PATH.read_text())
    assert set(doc["parameters"]) == set(SECTION_18_PARAMETERS)


def test_sigma_coef_zero_is_a_valid_sweep_point(config):
    """Section 6: SIGMA_COEF = 0 must be configurable, not a special case."""
    assert config.with_overrides(SIGMA_COEF=0.0).SIGMA_COEF == 0.0


def test_unknown_override_is_rejected(config):
    with pytest.raises(ConfigError):
        config.with_overrides(NOT_A_PARAMETER=1.0)


def test_gamma_must_be_strictly_between_zero_and_one(tmp_path):
    doc = json.loads(DEFAULT_CONFIG_PATH.read_text())
    doc["parameters"]["gamma"] = 1.0
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(doc))
    with pytest.raises(ConfigError):
        load_config(path)


def test_sweep_point_changes_the_config_hash(config):
    assert config.with_overrides(SIGMA_COEF=0.0).config_hash != config.config_hash


def test_engine_version_uses_exactly_seven_inputs(config, masks):
    version = build_engine_version(
        config_hash=config.config_hash, cmudict_hash="a", onset_table_hash="b",
        duration_table_hash="c", slot_mask_hash=masks.sha256,
    )
    record = version.to_record()
    assert set(record) - {"engine_version"} == {
        "code_version", "config_hash", "cmudict_hash", "onset_table_hash",
        "duration_table_hash", "slot_mask_hash", "resampler_version",
    }
    # Every input must actually move the hash.
    base = version.value
    for field in ("cmudict_hash", "onset_table_hash", "duration_table_hash",
                  "slot_mask_hash", "resampler_version", "config_hash", "code_version"):
        import dataclasses
        assert dataclasses.replace(version, **{field: "CHANGED"}).value != base
