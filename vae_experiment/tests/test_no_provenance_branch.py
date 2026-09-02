"""shape() must consume oracle and HEAR identically (Section 12, Section 24).

"if it branches, the oracle is not a control."  Checked twice: statically, so a
future edit cannot reintroduce a branch, and behaviourally, so a branch that
evades the static check still fails.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
from pathlib import Path

from vae import shape as shape_module
from vae.constants import METHOD_ONSET_SUPPORTED, PROVENANCE_HEAR, PROVENANCE_ORACLE
from vae.contracts import AcousticEvidence, Anchor
from vae.shape import shape


def _evidence(provenance: str, mask) -> AcousticEvidence:
    anchors = tuple(
        Anchor(slot_index=i, time_s=0.3 * i, sigma_s=0.01, method=METHOD_ONSET_SUPPORTED,
               supporting_event_ids=(), rise_time_ms=4.0)
        for i in range(mask.slot_count)
    )
    return AcousticEvidence(
        audio_id="AID", engine_version="EV", provenance=provenance, tempo_bpm=100.0,
        beat_times_s=(0.0, 0.6, 1.2), slot_mask_id=mask.mask_id, anchors=anchors, events=(),
    )


def test_shape_source_never_compares_against_a_provenance_literal():
    tree = ast.parse(Path(inspect.getfile(shape_module)).read_text())
    literals = {PROVENANCE_HEAR, PROVENANCE_ORACLE}
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value in literals:
            raise AssertionError(
                f"shape.py mentions provenance literal {node.value!r} at line {node.lineno}"
            )
        if isinstance(node, ast.Attribute) and node.attr == "provenance":
            # Passing it through is fine; branching on it is not.
            parent_is_compare = False
            for candidate in ast.walk(tree):
                if isinstance(candidate, ast.Compare) and any(
                    isinstance(c, ast.Attribute) and c.attr == "provenance"
                    for c in [candidate.left] + list(candidate.comparators)
                ):
                    parent_is_compare = True
            assert not parent_is_compare, "shape.py compares on .provenance"


def test_shape_output_is_identical_except_for_the_passed_through_provenance(config, masks):
    mask = masks.by_id("M5_short_first_4")
    hear_env = shape(_evidence(PROVENANCE_HEAR, mask), config, mask)
    oracle_env = shape(_evidence(PROVENANCE_ORACLE, mask), config, mask)
    assert hear_env.provenance == PROVENANCE_HEAR
    assert oracle_env.provenance == PROVENANCE_ORACLE
    assert dataclasses.replace(hear_env, provenance="X") == dataclasses.replace(
        oracle_env, provenance="X"
    )
