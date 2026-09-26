"""End-to-end exercise of steps 6-8 against the SYNTHETIC_TEST_ONLY tables.

**Nothing this script prints is a result.**  F4 and F5 are unpopulated, so every
number below is computed from arbitrary placeholder durations and a deliberately
incomplete onset inventory.  Its only purpose is to establish that steps 6, 7 and
8 are implemented and functional, so that the blocker is understood to be the
*data* and not the code.

The step-9 gate reads none of this.  Pair yield reported here is not F7 yield.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vae.conditions import flat_envelope  # noqa: E402
from vae.contracts import AcousticEvidence, Anchor  # noqa: E402
from vae.pairs import CellReports, PairSpec, check_pair, run_gate  # noqa: E402
from vae.pipeline import build_engine, write_json  # noqa: E402
from vae.shape import shape  # noqa: E402
from vae.sound import Candidate, sound  # noqa: E402
from tools import steps  # noqa: E402

SYNTH_F4 = ROOT / "tests" / "data" / "F4_synthetic.json"
SYNTH_F5 = ROOT / "tests" / "data" / "F5_synthetic.json"

WARNING = (
    "SYNTHETIC_TEST_ONLY. F4 and F5 are UNPOPULATED; every number here is computed "
    "from arbitrary placeholder durations and a deliberately incomplete onset "
    "inventory. Nothing here is a result, and none of it is an input to the step-9 "
    "reversal-existence gate."
)

# Demonstration pairs.  These are NOT F7: they exist to drive the five Section 11
# checks through real code paths.  They are matched on syllable count and stress
# pattern and are positional permutations of the same material.
DEMO_PAIRS = [
    ("D1", "hold the standing river", "standing hold the river"),
    ("D2", "bright and steady morning", "steady bright and morning"),
    ("D3", "strong and easy water", "easy strong and water"),
    ("D4", "carry the stranded moment", "stranded carry the moment"),
    ("D5", "stress the golden hour", "golden stress the hour"),
    ("D6", "wander the frosted meadow", "frosted wander the meadow"),
]

CONTEXT_TEMPO_BPM = 100.0


def _envelope(engine, mask, bpm=CONTEXT_TEMPO_BPM):
    """Anchors placed exactly on the mask's nominal grid — the audio-free ideal case."""
    eighth = (60.0 / bpm) / 2.0
    anchors = tuple(
        Anchor(slot_index=i, time_s=position * eighth, sigma_s=0.006,
               method="ONSET_SUPPORTED", supporting_event_ids=(), rise_time_ms=4.0)
        for i, position in enumerate(mask.positions)
    )
    evidence = AcousticEvidence(
        audio_id=f"EXERCISE:{mask.mask_id}", engine_version=engine.version,
        provenance="HEAR", tempo_bpm=bpm, beat_times_s=(0.0,),
        slot_mask_id=mask.mask_id, anchors=anchors, events=(),
    )
    return shape(evidence, engine.config, mask)


def main() -> int:
    engine = build_engine(duration_table_path=SYNTH_F4, onset_table_path=SYNTH_F5,
                          allow_synthetic_tables=True)
    cfg = engine.config
    m5 = engine.masks.by_id("M5_short_first_4")     # SHORT_FIRST context
    m6 = engine.masks.by_id("M6_long_first_4")      # LONG_FIRST  context

    envelopes = {
        "ctx1_short_first": _envelope(engine, m5),
        "ctx2_long_first": _envelope(engine, m6),
        "flat_ctx1": flat_envelope(m5, cfg, engine.version),
        "flat_ctx2": flat_envelope(m6, cfg, engine.version),
    }

    def score(line, envelope, pair_id, role):
        candidate = Candidate(candidate_id=role, text=line, pair_id=pair_id,
                              pair_role=role)
        return sound(envelope, candidate, engine.lexicon, cfg,
                     engine.durations, engine.onsets)[0]

    verdicts, rows = [], []
    for pair_id, line_x, line_y in DEMO_PAIRS:
        cells = CellReports(
            c_x1=score(line_x, envelopes["ctx1_short_first"], pair_id, "X"),
            c_y1=score(line_y, envelopes["ctx1_short_first"], pair_id, "Y"),
            c_x2=score(line_x, envelopes["ctx2_long_first"], pair_id, "X"),
            c_y2=score(line_y, envelopes["ctx2_long_first"], pair_id, "Y"),
            flat_x1=score(line_x, envelopes["flat_ctx1"], pair_id, "X"),
            flat_y1=score(line_y, envelopes["flat_ctx1"], pair_id, "Y"),
            flat_x2=score(line_x, envelopes["flat_ctx2"], pair_id, "X"),
            flat_y2=score(line_y, envelopes["flat_ctx2"], pair_id, "Y"),
        )
        spec = PairSpec(
            pair_id=pair_id, line_x=line_x, line_y=line_y,
            context_1_id=m5.mask_id, context_2_id=m6.mask_id,
            syllable_count=len(cells.c_x1.slots),
            stress_pattern=tuple(s.stress for s in cells.c_x1.slots),
            zipf_decile=0, syntactic_form="DEMO",
            heavy_cluster_syllable_x=-1, heavy_cluster_syllable_y=-1,
            predicted_preferred_context_1="X", predicted_preferred_context_2="Y",
        )
        verdict = check_pair(spec, cells, cfg)
        verdicts.append(verdict)
        rows.append({
            "pair_id": pair_id, "line_x": line_x, "line_y": line_y,
            "admitted": verdict.admitted,
            "failed_checks": list(verdict.failed_checks()),
            "score_b_x": cells.c_x1.score_b, "score_b_y": cells.c_y1.score_b,
            "delta_c_context_1": verdict.delta_c_context_1,
            "delta_c_context_2": verdict.delta_c_context_2,
            "preferred_context_1": verdict.preferred_context_1,
            "preferred_context_2": verdict.preferred_context_2,
            "nominal_load_delta_s": verdict.nominal_load_delta_s,
            "checks": [{"check_id": c.check_id, "passed": c.passed, "detail": c.detail}
                       for c in verdict.checks],
        })

    gate = run_gate(verdicts)
    report = {
        "WARNING": WARNING,
        "not_f7": "DEMO_PAIRS are demonstration material, not F7 pairs.",
        "fixture_status": engine.fixture_status,
        "step6": steps.step6(
            candidates=[Candidate("k1", "stop the rain now"),
                        Candidate("k2", "strong winter evening"),
                        Candidate("k3", "zzqqx unknown word")],
            duration_table_path=SYNTH_F4, onset_table_path=SYNTH_F5, allow_synthetic=True,
        ),
        "step7": steps.step7(
            candidates=[Candidate("k1", "stop the rain now"),
                        Candidate("k2", "strong winter evening"),
                        Candidate("k3", "hold the standing river")],
            duration_table_path=SYNTH_F4, onset_table_path=SYNTH_F5, allow_synthetic=True,
        ),
        "step8_mechanism_exercise": {
            "context_1": {"mask": m5.mask_id, "direction": m5.asymmetry_direction(),
                          "interval_effective_s": [s.interval_effective_s
                                                   for s in envelopes["ctx1_short_first"].slots]},
            "context_2": {"mask": m6.mask_id, "direction": m6.asymmetry_direction(),
                          "interval_effective_s": [s.interval_effective_s
                                                   for s in envelopes["ctx2_long_first"].slots]},
            "n_demo_pairs": gate.n_evaluated,
            "n_admitted": gate.n_admitted,
            "failure_counts": [{"check_id": k, "n_failed": v} for k, v in gate.failure_counts],
            "pairs": rows,
            "interpretation": (
                "Admission counts here measure the CODE, not the hypothesis. They are "
                "not F7 yield and are not an input to the step-9 gate."
            ),
        },
    }
    write_json(ROOT / "reports" / "exercise_synthetic_tables.json", report)

    print(WARNING)
    print()
    s6, s7 = report["step6"], report["step7"]
    print(f"step 6 runs: blocked={s6['blocked']}  candidates scored={len(s6['candidates'])}")
    for c in s6["candidates"]:
        print(f"    {c['candidate_id']:<4} {c['verdict']:<12} score_b={c['score_b']:.4f} "
              f"score_c={c['score_c']:.4f} tiers={c['feasibility_tiers']}")
    print(f"\nstep 7 runs: blocked={s7['blocked']}  conditions:")
    for name in ("A", "B", "C", "C_FLAT", "C_SHUFFLED", "C_ORACLE"):
        entry = s7["conditions"][name]
        if entry["blocked"]:
            print(f"    {name:<11} BLOCKED: {str(entry['blocker'])[:70]}")
        else:
            order = " > ".join(f"{e['candidate_id']}({e['score']:.4f})" for e in entry["ranked"])
            print(f"    {name:<11} {order}")
    print(f"\nstep 8 gate mechanism: {gate.n_admitted}/{gate.n_evaluated} demo pairs admitted")
    for check_id, n in gate.failure_counts:
        print(f"    {check_id:<26} failed by {n} pair(s)")
    print("\nwrote reports/exercise_synthetic_tables.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
