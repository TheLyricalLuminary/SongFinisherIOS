"""Section 24: run F1+F2 twice, diff against F9, assert discrete-decision identity
and eps_num.  Section 15 is the contract being enforced."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vae.determinism import EPS_NUM_SAME_PLATFORM, compare
from vae.errors import DeterminismViolation
from vae.pipeline import build_engine

import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools.steps import F1_DIR, F2_SYNTH_DIR, F9_DIR, golden_payload  # noqa: E402


def _targets():
    f1 = json.loads((F1_DIR / "manifest.json").read_text())["clips"]
    f2 = json.loads((F2_SYNTH_DIR / "manifest.json").read_text())["clips"]
    return [F1_DIR / c["file"] for c in f1] + [F2_SYNTH_DIR / c["file"] for c in f2]


@pytest.fixture(scope="module")
def engine():
    return build_engine()


def test_every_clip_has_a_golden():
    for path in _targets():
        assert (F9_DIR / f"{path.stem}.golden.json").exists(), f"no golden for {path.name}"


def test_reruns_match_the_goldens_exactly(engine):
    """Discrete fields must match exactly; floats within eps_num relative."""
    discrete, numerical = [], []
    for path in _targets():
        golden = json.loads((F9_DIR / f"{path.stem}.golden.json").read_text())
        for _ in range(2):                              # run twice, per Section 24
            for diff in compare(golden, golden_payload(engine, path), EPS_NUM_SAME_PLATFORM):
                (numerical if diff.kind == "NUMERICAL" else discrete).append(
                    (path.name, diff.path, diff.left, diff.right)
                )
    assert not discrete, f"discrete-decision drift: {discrete[:5]}"
    assert not numerical, f"numerical drift beyond eps_num: {numerical[:5]}"


def test_two_runs_in_the_same_process_are_identical(engine):
    path = _targets()[0]
    assert golden_payload(engine, path) == golden_payload(engine, path)


def test_a_seeded_difference_is_actually_detected():
    """The harness must fail when it should — otherwise it proves nothing."""
    golden = {"tier": "OK", "value": 1.0}
    assert not compare(golden, {"tier": "OK", "value": 1.0 + 1e-9})
    assert compare(golden, {"tier": "BORDERLINE", "value": 1.0})[0].kind == "DISCRETE"
    assert compare(golden, {"tier": "OK", "value": 1.1})[0].kind == "NUMERICAL"


def test_missing_golden_raises_rather_than_passing_silently(tmp_path):
    from vae.determinism import assert_matches_golden
    with pytest.raises(DeterminismViolation):
        assert_matches_golden({"a": 1}, tmp_path / "absent.json")
