"""d_pre_max / d_post_max are logged but never read by scoring (Section 7, 24).

Scoring them alongside the D_nucleus residual was the v1.0 double-counting bug.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
from pathlib import Path

from vae import rank as rank_module
from vae import sound as sound_module
from vae.constants import METHOD_ONSET_SUPPORTED
from vae.contracts import AcousticEvidence, Anchor
from vae.shape import shape
from vae.sound import Candidate, sound

DIAGNOSTIC_FIELDS = {"d_pre_max_s", "d_post_max_s", "d_pre_max", "d_post_max"}


def test_scoring_modules_never_reference_the_diagnostic_caps():
    for module in (sound_module, rank_module):
        tree = ast.parse(Path(inspect.getfile(module)).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in DIAGNOSTIC_FIELDS:
                raise AssertionError(
                    f"{module.__name__} reads {node.attr} at line {node.lineno}"
                )
            if isinstance(node, ast.Constant) and node.value in DIAGNOSTIC_FIELDS:
                raise AssertionError(f"{module.__name__} mentions {node.value!r}")


def test_perturbing_the_caps_does_not_change_any_score(
    config, masks, lexicon, synthetic_durations, synthetic_onsets
):
    mask = masks.by_id("M5_short_first_4")
    anchors = tuple(
        Anchor(slot_index=i, time_s=0.25 * i, sigma_s=0.008,
               method=METHOD_ONSET_SUPPORTED, supporting_event_ids=(), rise_time_ms=3.0)
        for i in range(mask.slot_count)
    )
    evidence = AcousticEvidence(
        audio_id="AID", engine_version="EV", provenance="HEAR", tempo_bpm=110.0,
        beat_times_s=(0.0,), slot_mask_id=mask.mask_id, anchors=anchors, events=(),
    )
    envelope = shape(evidence, config, mask)
    candidate = Candidate(candidate_id="c1", text="stop the rain now")

    baseline, _ = sound(envelope, candidate, lexicon, config,
                        synthetic_durations, synthetic_onsets)
    perturbed = dataclasses.replace(
        envelope,
        slots=tuple(
            dataclasses.replace(s, d_pre_max_s=s.d_pre_max_s * 17.0 + 3.0,
                                d_post_max_s=-999.0)
            for s in envelope.slots
        ),
    )
    after, _ = sound(perturbed, candidate, lexicon, config,
                     synthetic_durations, synthetic_onsets)
    assert after.score_b == baseline.score_b
    assert after.score_c == baseline.score_c
    assert [s.feasibility for s in after.slots] == [s.feasibility for s in baseline.slots]
