"""Stage assembly (Section 21) and the Section 16 provenance log.

    ingest(path)                              -> CanonicalAudio
    hear(CanonicalAudio, SlotMask)            -> AcousticEvidence
    load_oracle(audio_id, SlotMask)           -> AcousticEvidence   // same contract
    shape(AcousticEvidence, Config)           -> EnvelopeSequence
    sound(EnvelopeSequence, Candidate, Lexicon, Config)
                                              -> CompatibilityReport
    rank(CompatibilityReport[], mode)         -> RankedCandidateList

``Engine`` is a container for the versioned inputs — config, lexicon, tables,
masks — not a stage.  Stages remain pure functions of their arguments; nothing
here holds mutable state between calls.

Insufficient logging is the most likely cause of an uninterpretable null
(Section 16), so every stage has a ``*_with_log`` sibling and ``Engine`` knows
how to serialise the lot deterministically.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .canonical import ingest
from .config import Config, load_config
from .contracts import to_jsonable
from .hear import HearLog, hear_with_log
from .lexicon import Lexicon, load_lexicon
from .slots import SlotMask, SlotMaskInventory, load_slot_masks
from .tables import DurationTable, OnsetTable, load_duration_table, load_onset_table
from .version import EngineVersion, build_engine_version

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Engine:
    config: Config
    lexicon: Lexicon
    durations: DurationTable
    onsets: OnsetTable
    masks: SlotMaskInventory
    engine_version: EngineVersion

    @property
    def version(self) -> str:
        return self.engine_version.value

    @property
    def fixture_status(self) -> dict:
        """Surfaced on every run so a synthetic table can never pass unnoticed."""
        return {
            "F4_duration_table": self.durations.status,
            "F5_onset_table": self.onsets.status,
            "F6_slot_masks": "AUTHORED",
            "lexicon": "CMUdict 0.7b (pinned)",
            "uses_synthetic_tables": self.durations.is_synthetic or self.onsets.is_synthetic,
        }

    def ingest(self, path: Path | str):
        return ingest(path, self.version)

    def hear_with_log(self, audio, mask: SlotMask):
        return hear_with_log(audio, mask, self.config)


def build_engine(
    config: Optional[Config] = None,
    *,
    duration_table_path: Path | str | None = None,
    onset_table_path: Path | str | None = None,
    allow_synthetic_tables: bool = False,
) -> Engine:
    config = config or load_config()
    lexicon = load_lexicon()
    durations = load_duration_table(duration_table_path, allow_synthetic=allow_synthetic_tables)
    onsets = load_onset_table(onset_table_path, allow_synthetic=allow_synthetic_tables)
    masks = load_slot_masks()
    engine_version = build_engine_version(
        config_hash=config.config_hash,
        cmudict_hash=lexicon.sha256,
        onset_table_hash=onsets.sha256,
        duration_table_hash=durations.sha256,
        slot_mask_hash=masks.sha256,
    )
    return Engine(
        config=config,
        lexicon=lexicon,
        durations=durations,
        onsets=onsets,
        masks=masks,
        engine_version=engine_version,
    )


# --------------------------------------------------------------------------- #
# Section 16 logging
# --------------------------------------------------------------------------- #

def hear_log_record(log: HearLog) -> dict:
    """Section 16 HEAR: every ODF peak including rejected ones with reason;
    tempo candidates with autocorrelation scores; per-onset delta; grid-match rate."""
    return {
        "audio_id": log.audio_id,
        "tempo_bpm": log.tempo_bpm,
        "tempo_candidates": [
            {"bpm": c.bpm, "autocorrelation_score": c.score} for c in log.tempo_candidates
        ],
        "tempo_first_half_bpm": log.tempo_first_half_bpm,
        "tempo_second_half_bpm": log.tempo_second_half_bpm,
        "tempo_drift_frac": log.tempo_drift_frac,
        "beat_phase_s": log.beat_phase_s,
        "n_beats": log.n_beats,
        "grid_match_rate": log.grid_match_rate,
        "onset_density_per_eighth": log.onset_density_per_eighth,
        "n_onsets": log.n_onsets,
        "onset_deltas_s": list(log.onset_deltas_s),
        "grid_only_slot_count": log.grid_only_slot_count,
        "rejected_odf_peaks": [
            {"frame": p.frame, "time_s": p.time_s, "salience": p.salience, "reason": p.reason}
            for p in log.rejected_peaks
        ],
    }


def shape_log_record(envelope) -> dict:
    """Section 16 SHAPE: per slot — I_k, I_effective_k, anchor, sigma, method,
    supporting_event_ids, D_pre_max, D_post_max, metrical strength (with mask
    provenance), full chain from onset IDs to envelope field."""
    return {
        "audio_id": envelope.audio_id,
        "provenance": envelope.provenance,
        "slot_mask_id": envelope.slot_mask_id,
        "slots": [
            {
                "index": s.index,
                "interval_s": s.interval_s,
                "interval_effective_s": s.interval_effective_s,
                "anchor_time_s": s.anchor.time_s,
                "anchor_sigma_s": s.anchor.sigma_s,
                "anchor_method": s.anchor.method,
                "supporting_event_ids": list(s.anchor.supporting_event_ids),
                "d_pre_max_s": s.d_pre_max_s,
                "d_post_max_s": s.d_post_max_s,
                "metrical_strength": s.metrical_strength,
                "metrical_strength_provenance": f"authored slot mask {envelope.slot_mask_id}",
                "derived_from_event_ids": list(s.derived_from_event_ids),
                "derived_from_beat_indices": list(s.derived_from_beat_indices),
            }
            for s in envelope.slots
        ],
    }


def sound_log_record(log) -> dict:
    """Section 16 SOUND: per candidate per slot — CMUdict variant chosen,
    syllabification, per-phoneme d(c) with rho and gamma applied, realized
    D_pre/D_nucleus/D_post, s_fit, feasibility tier."""
    return {
        "candidate_id": log.candidate_id,
        "audio_id": log.audio_id,
        "provenance": log.provenance,
        "cmudict_variant_index": log.chosen_variant_index,
        "n_variants_evaluated": log.n_variants_evaluated,
        "per_word_variant": list(log.per_word_variant),
        "syllabification": list(log.syllable_texts),
        "rho_per_slot": list(log.rho_per_slot),
        "d_pre_s": list(log.d_pre_s),
        "d_nucleus_s": list(log.d_nucleus_s),
        "d_post_s": list(log.d_post_s),
        "per_phone_d_s": [{"phone": p, "d_s": d} for p, d in log.per_phone_d_s],
        "feasibility_tiers": list(log.tiers),
        "duration_table_is_synthetic": log.duration_table_is_synthetic,
        "f5_rejected_variants": [
            {"word": r.word, "variant_index": r.variant_index, "onset": " ".join(r.onset)}
            for r in log.rejected_variants
        ],
        "exclusion_reason": log.exclusion_reason,
    }


def write_json(path: Path | str, payload) -> None:
    """Deterministic serialisation: sorted keys, fixed separators, trailing newline."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(to_jsonable(payload), sort_keys=True, indent=2) + "\n"
    path.write_text(text, encoding="utf-8")
