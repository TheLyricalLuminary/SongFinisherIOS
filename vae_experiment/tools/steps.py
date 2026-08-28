"""Section 23 implementation order, steps 1-8.

    1. Canonical ingest + AudioID + determinism harness (F9 goldens).
       Gate: nothing proceeds until reruns are identical.
    2. HEAR on F1.  Gate: anchor error < 5.8 ms on all F1.
    3. Author F6 slot mask inventory.  Populate F4, F5.
    4. SHAPE + I_effective on F2.
    5. Oracle annotation of F2 (parallel with 4).  Gate: report HEAR-vs-oracle
       anchor error.
    6. SOUND — pronunciation, syllabification, partition, tiers, s_fit.
    7. RANK + all six conditions.
    8. Author F7 pairs.  Run all five Section 11 checks.

Step 9 is a BLOCKING GATE and is **not** crossed here.  Step 10 is outstanding
and no statistical analysis code exists in this repository.

Each step returns a JSON-serialisable report and refuses to fabricate a result
it cannot compute.  Where a fixture is blocked, the step reports the blocker and
the source material required, rather than substituting something.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vae.conditions import flat_envelope, shuffled_envelope  # noqa: E402
from vae.constants import HOP_SECONDS  # noqa: E402
from vae.contracts import to_jsonable  # noqa: E402
from vae.determinism import compare  # noqa: E402
from vae.errors import ClipRejected, FixtureUnpopulatedError  # noqa: E402
from vae.hear import hear_with_log  # noqa: E402
from vae.oracle import anchor_deltas, load_oracle, summarize_anchor_deltas  # noqa: E402
from vae.config import load_sweep_points  # noqa: E402
from vae.pipeline import (  # noqa: E402
    build_engine, hear_log_record, shape_log_record, write_json,
)
from vae.rank import rank  # noqa: E402
from vae.shape import realized_asymmetry, realized_asymmetry_direction, shape  # noqa: E402
from vae.sound import Candidate, sound  # noqa: E402

F1_DIR = ROOT / "fixtures" / "F1_click_tracks"
F2_DIR = ROOT / "fixtures" / "F2_clips"
F2_SYNTH_DIR = ROOT / "fixtures" / "F2_SYNTH_pipeline_exercise"
F3_DIR = ROOT / "fixtures" / "F3_out_of_spec"
F9_DIR = ROOT / "fixtures" / "F9_goldens"
REPORTS = ROOT / "reports"

# Step 2 gate.  The spec states "< 5.8 ms"; Section 22 failure #1 states "> 1 hop".
# One hop is 5.805 ms, so the spec's literal 5.8 ms is the stricter of the two and
# is what is enforced.  Both are reported.
GATE_ANCHOR_ERROR_S = 0.0058


def oracle_clip_specs(f2_dir: Path, with_label: bool = False):
    """Every synthetic clip that has a ground-truth oracle annotation."""
    sources = [(F1_DIR, "F1 click tracks"), (f2_dir, f2_dir.name)]
    for source, label in sources:
        for clip in json.loads((source / "manifest.json").read_text())["clips"]:
            yield (source, label, clip) if with_label else (source, clip)


def golden_payload(engine, path: Path) -> dict:
    """The F9 snapshot for one clip: ingest, HEAR and SHAPE under every fitting mask.

    ``source_path`` and ``engine_version`` are excluded: an absolute path is not
    part of the Section 20 contract, and the engine stamp is compared separately
    so that a code edit produces one clear diff rather than one per record.
    """
    audio = engine.ingest(path)
    record = to_jsonable(audio.to_record())
    record.pop("source_path", None)
    record.pop("engine_version", None)
    payload: dict = {"ingest": record, "hear_shared": None, "anchors": {}, "shape": {}}
    for mask in engine.masks.masks:
        try:
            evidence, log = engine.hear_with_log(audio, mask)
        except ClipRejected as exc:
            payload["anchors"][mask.mask_id] = {"rejected": exc.reason_code}
            continue
        # Onsets, tempo, grid and the ODF peak log do not depend on the mask, so
        # they are snapshotted once per clip rather than eight times.
        if payload["hear_shared"] is None:
            payload["hear_shared"] = {
                "tempo_bpm": evidence.tempo_bpm,
                "beat_times_s": list(evidence.beat_times_s),
                "events": to_jsonable(evidence.events),
                "log": hear_log_record(log),
            }
        payload["anchors"][mask.mask_id] = to_jsonable(evidence.anchors)
        envelope_record = to_jsonable(shape(evidence, engine.config, mask))
        envelope_record.pop("engine_version", None)
        payload["shape"][mask.mask_id] = envelope_record
    return payload


def golden_pass(engine, targets: list[Path], write: bool) -> dict:
    """Write or verify the F9 goldens.  Discrete fields must match exactly."""
    result = {"written": 0, "verified": 0, "differences": [],
              "discrete_differences": 0, "numerical_differences": 0}
    F9_DIR.mkdir(parents=True, exist_ok=True)
    for path in sorted(targets):
        golden_path = F9_DIR / f"{path.stem}.golden.json"
        payload = golden_payload(engine, path)
        if write or not golden_path.exists():
            golden_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            result["written"] += 1
            continue
        diffs = compare(json.loads(golden_path.read_text()), payload)
        result["verified"] += 1
        for d in diffs:
            result["differences"].append(
                {"file": golden_path.name, "path": d.path, "golden": d.left,
                 "produced": d.right, "kind": d.kind}
            )
            if d.kind == "NUMERICAL":
                result["numerical_differences"] += 1
            else:
                result["discrete_differences"] += 1
    result["differences"] = result["differences"][:20]
    return result


def _f2_clips() -> tuple[list[dict], Path, bool]:
    """Real F2 if populated, otherwise the clearly-labelled synthetic stand-in."""
    manifest = F2_DIR / "manifest.json"
    if manifest.exists():
        return json.loads(manifest.read_text())["clips"], F2_DIR, False
    doc = json.loads((F2_SYNTH_DIR / "manifest.json").read_text())
    return doc["clips"], F2_SYNTH_DIR, True


# --------------------------------------------------------------------------- #
# Step 1
# --------------------------------------------------------------------------- #

def step1(write_goldens: bool = False) -> dict:
    """Canonical ingest + AudioID + determinism harness.  Gate: reruns identical."""
    engine = build_engine()
    clips, f2_dir, synthetic = _f2_clips()
    targets = [(F1_DIR / c["file"]) for c in json.loads((F1_DIR / "manifest.json").read_text())["clips"]]
    targets += [f2_dir / c["file"] for c in clips]

    rows, mismatches = [], []
    for path in sorted(targets):
        first = engine.ingest(path)
        second = engine.ingest(path)          # rerun on the same input
        identical = first.audio_id == second.audio_id
        if not identical:
            mismatches.append(str(path))
        rows.append({
            "file": path.name,
            "audio_id": first.audio_id,
            "n_samples": first.n_samples,
            "duration_s": first.n_samples / first.sample_rate,
            "audio_id_stable_across_reruns": identical,
        })

    goldens = golden_pass(engine, targets, write=write_goldens)

    return {
        "step": 1,
        "title": "Canonical ingest + AudioID + determinism harness (F9 goldens)",
        "engine_version": engine.engine_version.to_record(),
        "fixture_status": engine.fixture_status,
        "uses_synthetic_fixtures": synthetic,
        "n_clips": len(rows),
        "clips": rows,
        "audio_id_rerun_mismatches": mismatches,
        "f9_goldens": goldens,
        "gate_reruns_identical": not mismatches and not goldens["differences"],
    }


# --------------------------------------------------------------------------- #
# Step 2
# --------------------------------------------------------------------------- #

def step2() -> dict:
    """HEAR on F1.  Gate: anchor error < 5.8 ms on all F1."""
    engine = build_engine()
    manifest = json.loads((F1_DIR / "manifest.json").read_text())
    rows, logs = [], {}
    worst = 0.0
    for clip in manifest["clips"]:
        audio = engine.ingest(F1_DIR / clip["file"])
        bpm, phase, duration = clip["tempo_bpm"], clip["phase_s"], clip["duration_s"]
        eighth = (60.0 / bpm) / 2.0
        for mask in engine.masks.masks:
            if phase + mask.positions[-1] * eighth > duration - 0.05:
                continue
            evidence, log = engine.hear_with_log(audio, mask)
            errors = [
                abs(a.time_s - (phase + p * eighth))
                for a, p in zip(evidence.anchors, mask.positions)
            ]
            worst = max(worst, max(errors))
            rows.append({
                "clip_id": clip["clip_id"],
                "slot_mask_id": mask.mask_id,
                "true_tempo_bpm": bpm,
                "estimated_tempo_bpm": log.tempo_bpm,
                "tempo_error_pct": 100.0 * (log.tempo_bpm - bpm) / bpm,
                "true_phase_s": phase,
                "estimated_phase_s": log.beat_phase_s,
                "max_anchor_error_s": max(errors),
                "mean_anchor_error_s": sum(errors) / len(errors),
                "per_slot_anchor_error_s": errors,
                "grid_only_slots": log.grid_only_slot_count,
                "passes_gate": max(errors) < GATE_ANCHOR_ERROR_S,
            })
            logs[f"{clip['clip_id']}.{mask.mask_id}"] = hear_log_record(log)

    failures = [r for r in rows if not r["passes_gate"]]

    # Section 18 / Section 26: the sweep is REPORTED, never used to select a
    # favourable configuration.  W_match decides which onsets support an anchor,
    # so the step-2 gate could in principle hold only at the base value.  Whether
    # it does is a fact about parameter sensitivity and belongs in the record.
    sweep_rows = []
    for w_match in load_sweep_points()["W_match"]:
        swept = engine.config.with_overrides(W_match=w_match)
        worst_swept, n_eval, n_fail, grid_only = 0.0, 0, 0, 0
        for clip in manifest["clips"]:
            audio = engine.ingest(F1_DIR / clip["file"])
            eighth = (60.0 / clip["tempo_bpm"]) / 2.0
            for mask in engine.masks.masks:
                if clip["phase_s"] + mask.positions[-1] * eighth > clip["duration_s"] - 0.05:
                    continue
                try:
                    evidence, log = hear_with_log(audio, mask, swept)
                except ClipRejected:
                    n_fail += 1
                    continue
                errors = [
                    abs(a.time_s - (clip["phase_s"] + p * eighth))
                    for a, p in zip(evidence.anchors, mask.positions)
                ]
                worst_swept = max(worst_swept, max(errors))
                n_eval += 1
                n_fail += max(errors) >= GATE_ANCHOR_ERROR_S
                grid_only += log.grid_only_slot_count
        sweep_rows.append({
            "W_match": w_match,
            "config_hash": swept.config_hash,
            "n_evaluations": n_eval,
            "n_failing_gate": n_fail,
            "worst_anchor_error_s": worst_swept,
            "grid_only_slots": grid_only,
            "gate_passes": n_fail == 0,
        })

    return {
        "step": 2,
        "title": "HEAR on F1",
        "w_match_sweep": {
            "note": (
                "Section 18: reported, never used to select a favourable configuration. "
                "W_match decides which onsets support an anchor (Section 6), so this "
                "answers whether the step-2 gate is robust across the sweep or holds "
                "only at the base value."
            ),
            "gate_holds_at_every_sweep_point": all(r["gate_passes"] for r in sweep_rows),
            "sweep_is_informative": len({
                (r["worst_anchor_error_s"], r["grid_only_slots"]) for r in sweep_rows
            }) > 1,
            "inertness_caveat": (
                "If every row is identical, W_match changed nothing on this fixture "
                "family, and the sweep has NOT shown the gate to be robust to it. F1 "
                "click tracks are quantised: an onset is either well inside 50 ms of a "
                "slot position or well outside 90 ms, so no supporting set changes. Real "
                "accompaniment carries human microtiming that puts onsets at intermediate "
                "distances, which is where W_match bites. Read an identical sweep as "
                "'untested here', never as 'insensitive'."
            ),
            "rows": sweep_rows,
        },
        "gate": {
            "criterion_s": GATE_ANCHOR_ERROR_S,
            "criterion_text": "anchor error < 5.8 ms on all F1 (Section 23 step 2)",
            "one_hop_s": HOP_SECONDS,
            "worst_anchor_error_s": worst,
            "n_evaluations": len(rows),
            "n_failing": len(failures),
            "passed": not failures,
        },
        "evaluations": rows,
        "hear_logs": logs,
    }


# --------------------------------------------------------------------------- #
# Step 3
# --------------------------------------------------------------------------- #

def step3() -> dict:
    """Author F6.  Populate F4, F5."""
    engine = build_engine()
    masks = [
        {
            "mask_id": m.mask_id,
            "slot_count": m.slot_count,
            "positions": list(m.positions),
            "metrical_strength": list(m.metrical_strength),
            "nominal_gaps_eighths": list(m.nominal_gaps),
            "nominal_asymmetry": m.nominal_asymmetry,
            "asymmetry_direction": m.asymmetry_direction(),
            "is_asymmetric": m.is_asymmetric(engine.config.ASYMMETRY_MIN),
        }
        for m in engine.masks.masks
    ]
    n_asym = sum(1 for m in masks if m["is_asymmetric"])
    f4, f5 = engine.durations, engine.onsets
    return {
        "step": 3,
        "title": "Author F6 slot mask inventory; populate F4, F5",
        "F6": {
            "status": "AUTHORED",
            "n_masks": len(masks),
            "n_asymmetric": n_asym,
            "asymmetry_min": engine.config.ASYMMETRY_MIN,
            "requirement": "8 patterns, >=4 asymmetric, with authored metrical strength",
            "requirement_met": len(masks) == 8 and n_asym >= 4,
            "sha256": engine.masks.sha256,
            "masks": masks,
        },
        "F4": {
            "status": f4.status,
            "sha256": f4.sha256,
            "n_phones": len(f4.covered_phones()),
            "blocked": not f4.is_populated,
            "required_source_material": list(f4.required_source_material),
        },
        "F5": {
            "status": f5.status,
            "sha256": f5.sha256,
            "n_onsets": f5.n_onsets,
            "max_onset_length": f5.max_onset_length,
            "blocked": not f5.is_populated,
            "required_source_material": list(f5.required_source_material),
        },
        "blocked": not (f4.is_populated and f5.is_populated),
    }


# --------------------------------------------------------------------------- #
# Steps 4 and 5
# --------------------------------------------------------------------------- #

def step4_5() -> dict:
    """SHAPE + I_effective on F2, and the HEAR-vs-oracle anchor-error report."""
    engine = build_engine()
    clips, f2_dir, synthetic = _f2_clips()

    shape_rows, shape_logs, rejected = [], {}, []
    for clip in clips:
        mask = engine.masks.by_id(clip["slot_mask_id"])
        try:
            audio = engine.ingest(f2_dir / clip["file"])
            evidence, _log = engine.hear_with_log(audio, mask)
        except ClipRejected as exc:
            rejected.append({"clip_id": clip["clip_id"], "reason_code": exc.reason_code,
                             "detail": exc.detail})
            continue
        envelope = shape(evidence, engine.config, mask)
        shape_rows.append({
            "clip_id": clip["clip_id"],
            "audio_id": envelope.audio_id,
            "slot_mask_id": mask.mask_id,
            "interval_s": [s.interval_s for s in envelope.slots],
            "interval_effective_s": [s.interval_effective_s for s in envelope.slots],
            "shrinkage_s": [s.interval_s - s.interval_effective_s for s in envelope.slots],
            "anchor_sigma_s": [s.uncertainty_anchor_sigma_s for s in envelope.slots],
            "anchor_method": [s.anchor.method for s in envelope.slots],
            "metrical_strength": [s.metrical_strength for s in envelope.slots],
            "d_pre_max_s": [s.d_pre_max_s for s in envelope.slots],
            "d_post_max_s": [s.d_post_max_s for s in envelope.slots],
            "realized_asymmetry": realized_asymmetry(envelope),
            "realized_asymmetry_direction": realized_asymmetry_direction(envelope, engine.config),
            "meets_asymmetry_min": realized_asymmetry(envelope) >= engine.config.ASYMMETRY_MIN,
        })
        shape_logs[clip["clip_id"]] = shape_log_record(envelope)

    # Section 18 / Section 26: the sweep is REPORTED, never used to select a
    # favourable configuration.  SIGMA_COEF = 0 is the explicit sweep point that
    # answers whether uncertainty modelling earns its place (Section 6).
    sweep_rows = []
    for sigma_coef in load_sweep_points()["SIGMA_COEF"]:
        swept = engine.config.with_overrides(SIGMA_COEF=sigma_coef)
        shrinkages, floored = [], 0
        for clip in clips:
            mask = engine.masks.by_id(clip["slot_mask_id"])
            try:
                audio = engine.ingest(f2_dir / clip["file"])
                evidence, _ = engine.hear_with_log(audio, mask)
            except ClipRejected:
                continue
            envelope = shape(evidence, swept, mask)
            for slot in envelope.slots:
                shrinkages.append(slot.interval_s - slot.interval_effective_s)
                if abs(slot.interval_effective_s - swept.I_MIN) < 1e-12:
                    floored += 1
        sweep_rows.append({
            "SIGMA_COEF": sigma_coef,
            "config_hash": swept.config_hash,
            "n_slots": len(shrinkages),
            "mean_shrinkage_s": sum(shrinkages) / len(shrinkages) if shrinkages else None,
            "max_shrinkage_s": max(shrinkages) if shrinkages else None,
            "n_slots_at_I_MIN": floored,
        })

    w_match_rows = []
    for w_match in load_sweep_points()["W_match"]:
        swept = engine.config.with_overrides(W_match=w_match)
        deltas, grid_only = [], 0
        for source, clip in oracle_clip_specs(f2_dir):
            audio = engine.ingest(source / clip["file"])
            eighth = (60.0 / clip["tempo_bpm"]) / 2.0
            for mask in engine.masks.masks:
                if clip["phase_s"] + mask.positions[-1] * eighth > clip["duration_s"] - 0.05:
                    continue
                try:
                    hear_ev, log = hear_with_log(audio, mask, swept)
                except ClipRejected:
                    continue
                try:
                    oracle_ev = load_oracle(audio.audio_id, mask, engine.version)
                except FixtureUnpopulatedError:
                    continue
                deltas.extend(abs(d.delta_s) for d in anchor_deltas(hear_ev, oracle_ev))
                grid_only += log.grid_only_slot_count
        w_match_rows.append({
            "W_match": w_match,
            "config_hash": swept.config_hash,
            "n_slots": len(deltas),
            "mean_abs_delta_s": sum(deltas) / len(deltas) if deltas else None,
            "max_abs_delta_s": max(deltas) if deltas else None,
            "n_slots_over_one_hop": sum(1 for d in deltas if d > HOP_SECONDS),
            "grid_only_slots": grid_only,
        })

    oracle_rows, oracle_missing = [], []
    for source, label, clip in oracle_clip_specs(f2_dir, with_label=True):
        audio = engine.ingest(source / clip["file"])
        eighth = (60.0 / clip["tempo_bpm"]) / 2.0
        for mask in engine.masks.masks:
            if clip["phase_s"] + mask.positions[-1] * eighth > clip["duration_s"] - 0.05:
                continue
            try:
                hear_ev, log = engine.hear_with_log(audio, mask)
            except ClipRejected:
                continue
            try:
                oracle_ev = load_oracle(audio.audio_id, mask, engine.version)
            except FixtureUnpopulatedError as exc:
                oracle_missing.append(str(exc))
                continue
            deltas = anchor_deltas(hear_ev, oracle_ev)
            summary = summarize_anchor_deltas(deltas, log.tempo_bpm)
            hear_env = shape(hear_ev, engine.config, mask)
            oracle_env = shape(oracle_ev, engine.config, mask)
            oracle_rows.append({
                "clip_id": clip["clip_id"],
                "source_fixture": label,
                "slot_mask_id": mask.mask_id,
                "annotation_source": "GROUND_TRUTH_BY_CONSTRUCTION",
                "n_slots": summary.n_slots,
                "mean_abs_delta_s": summary.mean_abs_delta_s,
                "median_abs_delta_s": summary.median_abs_delta_s,
                "max_abs_delta_s": summary.max_abs_delta_s,
                "systematic_offset_s": summary.systematic_offset_s,
                "systematic_offset_beats": summary.systematic_offset_beats,
                "excluded_for_beat_offset_R1": summary.excluded_for_beat_offset,
                "per_slot_delta_s": [d.delta_s for d in deltas],
                "hear_method": [d.hear_method for d in deltas],
                "mean_abs_interval_effective_delta_s": (
                    sum(abs(h.interval_effective_s - o.interval_effective_s)
                        for h, o in zip(hear_env.slots, oracle_env.slots)) / len(hear_env.slots)
                ),
            })

    n = len(oracle_rows)
    return {
        "step": "4+5",
        "title": "SHAPE + I_effective; oracle annotation and HEAR-vs-oracle anchor error",
        "uses_synthetic_fixtures": synthetic,
        "synthetic_note": (
            "SHAPE was run on the F2 pipeline-exercise stand-in, not on F2. "
            "F2 requires real recorded accompaniment and is blocked."
            if synthetic else ""
        ),
        "shape": {
            "n_clips": len(shape_rows),
            "n_rejected": len(rejected),
            "rejected": rejected,
            "rows": shape_rows,
        },
        "shape_logs": shape_logs,
        "w_match_sweep": {
            "note": (
                "Section 18: reported, never used to select a favourable configuration. "
                "Identical rows mean W_match changed no supporting set on these fixtures "
                "— 'untested here', not 'insensitive'. Both fixture families are "
                "quantised; human microtiming is what makes W_match bite."
            ),
            "sweep_is_informative": len({
                (r["mean_abs_delta_s"], r["grid_only_slots"]) for r in w_match_rows
            }) > 1,
            "rows": w_match_rows,
        },
        "sigma_coef_sweep": {
            "note": (
                "Section 18: the sweep is reported, never used to select a favourable "
                "configuration. SIGMA_COEF = 0 reduces I_effective to the identity, so "
                "this table answers whether uncertainty modelling changes anything "
                "rather than assuming it does (Section 6, Section 26)."
            ),
            "rows": sweep_rows,
        },
        "oracle": {
            "f2_oracle_available": False,
            "f2_oracle_blocker": (
                "Section 12 requires two independent human annotations per clip with "
                ">20 ms disagreements adjudicated by a third. Blocked on F2 and on "
                "human annotators."
            ),
            "n_f1_comparisons": n,
            "mean_abs_anchor_delta_s": (
                sum(r["mean_abs_delta_s"] for r in oracle_rows) / n if n else None
            ),
            "max_abs_anchor_delta_s": max((r["max_abs_delta_s"] for r in oracle_rows), default=None),
            "n_excluded_for_beat_offset_R1": sum(
                1 for r in oracle_rows if r["excluded_for_beat_offset_R1"]
            ),
            "rows": oracle_rows,
            "n_missing_annotations": len(oracle_missing),
        },
    }


# --------------------------------------------------------------------------- #
# Steps 6, 7, 8
# --------------------------------------------------------------------------- #

def _sound_blocked_report(engine) -> dict:
    return {
        "blocked": True,
        "blocker": "F4 and F5 are UNPOPULATED",
        "F4_status": engine.durations.status,
        "F5_status": engine.onsets.status,
        "F4_required_source_material": list(engine.durations.required_source_material),
        "F5_required_source_material": list(engine.onsets.required_source_material),
        "why": (
            "SOUND cannot run without d_nominal/d_floor (Section 7 partition) or the "
            "legal-onset table (Section 9 syllabification). Section 22 failure #10 makes "
            "a duration-table gap a hard error, never a silent default, so no substitute "
            "is available."
        ),
    }


def step6(candidates: Optional[list[Candidate]] = None,
          duration_table_path: Path | str | None = None,
          onset_table_path: Path | str | None = None,
          allow_synthetic: bool = False) -> dict:
    """SOUND — pronunciation, syllabification, partition, tiers, s_fit."""
    engine = build_engine(
        duration_table_path=duration_table_path,
        onset_table_path=onset_table_path,
        allow_synthetic_tables=allow_synthetic,
    )
    if not (engine.durations.is_populated or engine.durations.is_synthetic):
        return {"step": 6, "title": "SOUND", **_sound_blocked_report(engine)}

    clips, f2_dir, synthetic = _f2_clips()
    clip = clips[0]
    mask = engine.masks.by_id(clip["slot_mask_id"])
    audio = engine.ingest(f2_dir / clip["file"])
    evidence, _ = engine.hear_with_log(audio, mask)
    envelope = shape(evidence, engine.config, mask)

    candidates = candidates or []
    rows = []
    for candidate in candidates:
        report, log = sound(
            envelope, candidate, engine.lexicon, engine.config, engine.durations, engine.onsets
        )
        rows.append({
            "candidate_id": candidate.candidate_id,
            "text": candidate.text,
            "verdict": report.verdict,
            "score_b": report.score_b,
            "score_c": report.score_c,
            "pronunciation_variant_index": report.pronunciation_variant_index,
            "n_variants_evaluated": log.n_variants_evaluated,
            "syllabification": list(log.syllable_texts),
            "d_pre_s": list(log.d_pre_s),
            "d_nucleus_s": list(log.d_nucleus_s),
            "d_post_s": list(log.d_post_s),
            "rho_per_slot": list(log.rho_per_slot),
            "feasibility_tiers": list(log.tiers),
            "s_fit": [s.s_fit for s in report.slots],
            "total_nominal_consonant_duration_s": report.total_nominal_consonant_duration_s,
        })
    return {
        "step": 6,
        "title": "SOUND — pronunciation, syllabification, partition, tiers, s_fit",
        "blocked": False,
        "uses_synthetic_tables": engine.durations.is_synthetic or engine.onsets.is_synthetic,
        "uses_synthetic_fixtures": synthetic,
        "clip_id": clip["clip_id"],
        "slot_mask_id": mask.mask_id,
        "candidates": rows,
    }


def step7(candidates: Optional[list[Candidate]] = None,
          duration_table_path: Path | str | None = None,
          onset_table_path: Path | str | None = None,
          allow_synthetic: bool = False) -> dict:
    """RANK + all six conditions."""
    engine = build_engine(
        duration_table_path=duration_table_path,
        onset_table_path=onset_table_path,
        allow_synthetic_tables=allow_synthetic,
    )
    if not (engine.durations.is_populated or engine.durations.is_synthetic):
        return {"step": 7, "title": "RANK + all six conditions", **_sound_blocked_report(engine)}

    clips, f2_dir, synthetic = _f2_clips()
    candidates = candidates or []

    # Build the HEAR envelope for every clip so C_SHUFFLED has a slot-count-matched pool.
    envelopes: dict[str, dict] = {}
    for clip in clips:
        mask = engine.masks.by_id(clip["slot_mask_id"])
        audio = engine.ingest(f2_dir / clip["file"])
        evidence, _ = engine.hear_with_log(audio, mask)
        envelopes[audio.audio_id] = {
            "clip": clip, "mask": mask, "envelope": shape(evidence, engine.config, mask),
        }

    target_id = sorted(envelopes)[0]
    target = envelopes[target_id]
    mask = target["mask"]
    pool = {
        aid: e["envelope"] for aid, e in envelopes.items()
        if e["mask"].mask_id == mask.mask_id
    }

    by_condition = {
        "C": target["envelope"],
        "B": target["envelope"],
        "A": target["envelope"],
        "C_FLAT": flat_envelope(mask, engine.config, engine.version),
        "C_SHUFFLED": shuffled_envelope(target_id, pool, mask),
    }
    try:
        audio = engine.ingest(f2_dir / target["clip"]["file"])
        oracle_ev = load_oracle(audio.audio_id, mask, engine.version)
        by_condition["C_ORACLE"] = shape(oracle_ev, engine.config, mask)
        oracle_blocker = None
    except FixtureUnpopulatedError as exc:
        oracle_blocker = str(exc)

    results = {}
    for condition in ("A", "B", "C", "C_FLAT", "C_SHUFFLED", "C_ORACLE"):
        if condition not in by_condition:
            results[condition] = {"blocked": True, "blocker": oracle_blocker}
            continue
        envelope = by_condition[condition]
        reports = [
            sound(envelope, c, engine.lexicon, engine.config, engine.durations, engine.onsets)[0]
            for c in candidates
        ]
        ranked = rank(reports, condition, engine.config)
        results[condition] = {
            "blocked": False,
            "envelope_audio_id": envelope.audio_id,
            "ranked": [
                {"candidate_id": e.candidate_id, "score": e.score,
                 "tiebreak_applied": e.tiebreak_applied}
                for e in ranked.ranked
            ],
            "excluded": [
                {"candidate_id": r.candidate_id, "verdict": r.verdict}
                for r in reports if r.verdict != "ACCEPT"
            ],
        }
    return {
        "step": 7,
        "title": "RANK + all six conditions",
        "blocked": False,
        "uses_synthetic_tables": engine.durations.is_synthetic or engine.onsets.is_synthetic,
        "uses_synthetic_fixtures": synthetic,
        "target_clip_id": target["clip"]["clip_id"],
        "slot_mask_id": mask.mask_id,
        "conditions": results,
    }


def step8() -> dict:
    """Author F7 pairs; run all five Section 11 checks."""
    engine = build_engine()
    f7_dir = ROOT / "fixtures" / "F7_pairs"
    spec_file = f7_dir / "pairs.json"
    if spec_file.exists():
        raise NotImplementedError("F7 present but the authored-pair runner is not wired up")
    return {
        "step": 8,
        "title": "Author F7 pairs; run all five Section 11 checks",
        "blocked": True,
        "F7_status": "UNPOPULATED",
        "blocker": "F7 cannot be authored: it depends on F4 and F5, both UNPOPULATED",
        "why": (
            "Section 11 check 4 matches pair members on sum d_nominal(c) within LOAD_TOL, "
            "and d_nominal comes from F4. Syllable onset/coda boundaries — which decide "
            "where the heavy cluster sits, the independent variable itself — come from "
            "Maximum Onset Principle syllabification against F5. Without both, checks 2, "
            "3, 4 and 5 cannot be evaluated and lines would be authored against an "
            "unknown syllabifier."
        ),
        "gate_implementation_status": "IMPLEMENTED AND TESTED (vae.pairs.check_pair, run_gate)",
        "checks_implemented": [
            "C1_B_TIED_BOTH_CONTEXTS", "C2_SCORE_C_REVERSAL", "C3_REVERSAL_MARGIN",
            "C4_NOMINAL_LOAD_MATCHED", "C5_C_FLAT_NO_REVERSAL",
        ],
        "n_pairs_authored": 0,
        "n_pairs_admitted": 0,
        "target_pairs": 60,
        "F4_status": engine.durations.status,
        "F5_status": engine.onsets.status,
    }


def main(argv: list[str]) -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)
    which = argv[1] if len(argv) > 1 else "all"
    runners = {
        "1": ("step1", lambda: step1(write_goldens="--write-goldens" in argv)),
        "2": ("step2", step2),
        "3": ("step3", step3),
        "45": ("step4_5", step4_5),
        "6": ("step6", step6),
        "7": ("step7", step7),
        "8": ("step8", step8),
    }
    keys = list(runners) if which == "all" else [which]
    for key in keys:
        name, fn = runners[key]
        report = fn()
        write_json(REPORTS / f"{name}.json", report)
        print(f"{name}: wrote reports/{name}.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
