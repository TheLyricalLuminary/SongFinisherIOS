"""SOUND — Section 7 partition, Section 8 tiers, Section 10 scoring.

The partition is the fix for v1.0 defect 2.  The post-nucleus allowance of slot
k and the pre-nucleus allowance of slot k+1 are **not independent**: they
compete for one interval.

    I_effective_k  =  D_nucleus(k)  +  D_post(k)  +  D_pre(k+1)

    D_pre(k+1)   = sum d(c) for c in onset(k+1)
    D_post(k)    = sum d(c) for c in coda(k)
    D_nucleus(k) = I_effective_k - D_post(k) - D_pre(k+1)      # residual

    d(c)  = max( d_floor(c),  d_nominal(c) * rho_k ** gamma )
    rho_k = I_effective_k / I_reference

gamma < 1 encodes the single empirically supported non-trivial assumption: that
consonants compress proportionally less than vowels as rate increases (Gay 1978;
Max & Caruso 1997).  The vowel absorbs the squeeze.  Everything else here is
interval arithmetic carrying no scientific claim.

**This equation is not validated science and no output of this module may
describe it as such** (Section 7).  It is a partly-supported heuristic, and that
framing is part of the spec.

Scoring is three subscores in B and four in C.  ``s_fit`` is the only
articulatory term: it carries the whole hypothesis.  ``d_pre_max`` /
``d_post_max`` are never read here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .config import Config
from .constants import (
    ARPABET_DIPHTHONGS,
    STRESS_STRENGTH_TABLE,
    TIER_BELOW_FLOOR,
    TIER_BORDERLINE,
    TIER_HARD_INFEASIBLE,
    TIER_OK,
    VERDICT_ABSTAIN_OOV,
    VERDICT_ACCEPT,
    VERDICT_REJECT_HARD,
)
from .contracts import CompatibilityReport, EnvelopeSequence, ReportSlot
from .errors import NoLegalPronunciationError
from .lexicon import Lexicon, LineVariant, RejectedVariant, Syllable, line_variants
from .shape import lead_in_effective
from .tables import DurationTable


@dataclass(frozen=True)
class Candidate:
    """An authored lyric line.  Trial metadata is pre-registered, never inferred."""

    candidate_id: str
    text: str
    pair_id: Optional[str] = None
    context_id: Optional[str] = None
    pair_role: Optional[str] = None            # "X" | "Y"
    predicted_preferred: Optional[bool] = None


# --------------------------------------------------------------------------- #
# Section 7 — consonant duration under tempo
# --------------------------------------------------------------------------- #

def consonant_duration(
    phone: str, interval_effective_s: float, durations: DurationTable, config: Config
) -> float:
    """d(c) = max( d_floor(c), d_nominal(c) * rho^gamma ).

    Partly-supported heuristic (Section 7), never described as validated.
    """
    rho = interval_effective_s / config.I_reference
    scaled = durations.d_nominal(phone) * (rho ** config.gamma)
    return max(durations.d_floor(phone), scaled)


def cluster_duration(
    cluster: tuple[str, ...], interval_effective_s: float,
    durations: DurationTable, config: Config,
) -> float:
    return sum(
        consonant_duration(p, interval_effective_s, durations, config) for p in cluster
    )


def nominal_cluster_duration(cluster: tuple[str, ...], durations: DurationTable) -> float:
    """Tempo-independent load.  Section 11 check 4 matches on this, never on d(c)."""
    return sum(durations.d_nominal(p) for p in cluster)


# --------------------------------------------------------------------------- #
# Section 8 — feasibility tiers.  Four static tiers, no hysteresis.
# --------------------------------------------------------------------------- #

def feasibility_floor(nucleus: str, config: Config) -> float:
    """F_min(monophthong) = F_MIN_BASE;  F_min(diphthong) = F_MIN_BASE * DIPHTHONG_FACTOR."""
    base = config.F_MIN_BASE
    return base * config.DIPHTHONG_FACTOR if nucleus in ARPABET_DIPHTHONGS else base


def feasibility_tier(d_nucleus_s: float, floor_s: float, config: Config) -> str:
    """Static four-tier band, evaluated independently under every configuration.

    No hysteresis (v1.0 defect 4): it required history, contradicting the
    pure-function contract, and would have masked the very instability the
    sweep exists to detect.
    """
    if d_nucleus_s <= 0.0:
        return TIER_HARD_INFEASIBLE
    if d_nucleus_s < floor_s:
        return TIER_BELOW_FLOOR
    if d_nucleus_s < floor_s * config.BORDERLINE_FACTOR:
        return TIER_BORDERLINE
    return TIER_OK


# --------------------------------------------------------------------------- #
# Section 10 — subscores
# --------------------------------------------------------------------------- #

def s_stress(syllable_stress: str, metrical_strength: str) -> float:
    """Fixed 3x3 lookup, hard-coded and never tuned on the evaluation set."""
    return STRESS_STRENGTH_TABLE[(syllable_stress, metrical_strength)]


def s_fit(d_nucleus_s: float, floor_s: float, config: Config) -> float:
    """clamp01( (D_nucleus - F_min) / (NUCLEUS_COMFORT - F_min) ).

    One articulatory term, not three.  It carries the whole hypothesis: after the
    shared interval is partitioned, is there enough nucleus left?
    """
    span = config.NUCLEUS_COMFORT - floor_s
    if span <= 0.0:
        return 0.0
    return min(1.0, max(0.0, (d_nucleus_s - floor_s) / span))


# --------------------------------------------------------------------------- #
# The stage
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class SoundLog:
    """Section 16 SOUND logging.  Not part of the Section 20 contract."""

    candidate_id: str
    audio_id: str
    provenance: str
    chosen_variant_index: Optional[int]
    n_variants_evaluated: int
    per_word_variant: tuple[int, ...]
    syllable_texts: tuple[str, ...]
    rho_per_slot: tuple[float, ...]
    d_pre_s: tuple[float, ...]
    d_nucleus_s: tuple[float, ...]
    d_post_s: tuple[float, ...]
    per_phone_d_s: tuple[tuple[str, float], ...]
    tiers: tuple[str, ...]
    duration_table_is_synthetic: bool
    rejected_variants: tuple[RejectedVariant, ...] = ()
    exclusion_reason: str = ""


def _score_variant(
    variant: LineVariant, envelope: EnvelopeSequence, durations: DurationTable, config: Config
) -> tuple[float, float, tuple[ReportSlot, ...], SoundLog, float, float]:
    syllables: tuple[Syllable, ...] = variant.syllables
    slots = envelope.slots
    n_syll, n_slots = len(syllables), len(slots)
    n = min(n_syll, n_slots)

    count_ok = 1.0 if n_syll == n_slots else 0.0
    anchor_ok = count_ok            # Section 10: syllable index -> slot index, binary in V1

    # Pass 1: the interval each cluster is budgeted against.  D_pre(k+1) competes
    # for I_effective_k, so syllable k's onset is costed against slot k-1's
    # interval; slot 0's onset is drawn from LEAD_IN (Section 7).
    lead_eff = lead_in_effective(slots[0].anchor.sigma_s, config) if n else config.LEAD_IN
    pre_interval = [lead_eff if k == 0 else slots[k - 1].interval_effective_s for k in range(n)]
    post_interval = [slots[k].interval_effective_s for k in range(n)]

    d_pre = [
        cluster_duration(syllables[k].onset, pre_interval[k], durations, config)
        for k in range(n)
    ]
    d_post = [
        cluster_duration(syllables[k].coda, post_interval[k], durations, config)
        for k in range(n)
    ]
    # D_nucleus(k) = I_effective_k - D_post(k) - D_pre(k+1), the shared-partition
    # residual.  The final slot has no following onset to fund.
    d_nucleus = [
        post_interval[k] - d_post[k] - (d_pre[k + 1] if k + 1 < n else 0.0)
        for k in range(n)
    ]

    # Pass 2: tiers, subscores, and the Section 16 per-phone log.
    report_slots: list[ReportSlot] = []
    per_phone: list[tuple[str, float]] = []
    rhos: list[float] = []
    tiers: list[str] = []
    total_scaled = 0.0
    total_nominal = 0.0

    for k in range(n):
        syllable = syllables[k]
        rhos.append(post_interval[k] / config.I_reference)
        floor = feasibility_floor(syllable.nucleus, config)
        tier = feasibility_tier(d_nucleus[k], floor, config)
        tiers.append(tier)

        for phone in syllable.onset:
            per_phone.append(
                (phone, consonant_duration(phone, pre_interval[k], durations, config))
            )
        for phone in syllable.coda:
            per_phone.append(
                (phone, consonant_duration(phone, post_interval[k], durations, config))
            )
        total_scaled += d_pre[k] + d_post[k]
        total_nominal += nominal_cluster_duration(syllable.onset, durations)
        total_nominal += nominal_cluster_duration(syllable.coda, durations)

        report_slots.append(
            ReportSlot(
                index=k,
                syllable=syllable.text(),
                phones=syllable.phones,
                stress=syllable.stress,
                d_pre_s=float(d_pre[k]),
                d_nucleus_s=float(d_nucleus[k]),
                d_post_s=float(d_post[k]),
                feasibility_floor_s=float(floor),
                feasibility=tier,
                s_stress=s_stress(syllable.stress, slots[k].metrical_strength),
                s_count=count_ok,
                s_anchor=anchor_ok,
                s_fit=s_fit(d_nucleus[k], floor, config),
            )
        )

    # Syllables beyond the slot count are still costed against the load total, so
    # a condition-A candidate cannot look cheap merely by overflowing the mask.
    for syllable in syllables[n:]:
        total_nominal += nominal_cluster_duration(syllable.onset, durations)
        total_nominal += nominal_cluster_duration(syllable.coda, durations)

    # Arithmetic mean across slots.  No learned aggregation, no softmax, no
    # pool-dependent normalisation (Section 10).
    if report_slots:
        mean_stress = sum(s.s_stress for s in report_slots) / len(report_slots)
        mean_fit = sum(s.s_fit for s in report_slots) / len(report_slots)
    else:
        mean_stress = mean_fit = 0.0

    score_b = (
        config.W_stress * mean_stress + config.W_count * count_ok + config.W_anchor * anchor_ok
    )
    score_c = score_b + config.W_fit * mean_fit

    log = SoundLog(
        candidate_id="",
        audio_id=envelope.audio_id,
        provenance=envelope.provenance,
        chosen_variant_index=variant.variant_index,
        n_variants_evaluated=0,
        per_word_variant=variant.per_word_variant,
        syllable_texts=tuple(s.text() for s in syllables),
        rho_per_slot=tuple(rhos),
        d_pre_s=tuple(float(v) for v in d_pre),
        d_nucleus_s=tuple(float(v) for v in d_nucleus),
        d_post_s=tuple(float(v) for v in d_post),
        per_phone_d_s=tuple(per_phone),
        tiers=tuple(tiers),
        duration_table_is_synthetic=durations.is_synthetic,
    )
    return score_b, score_c, tuple(report_slots), log, total_scaled, total_nominal


def sound(
    envelope: EnvelopeSequence,
    candidate: Candidate,
    lexicon: Lexicon,
    config: Config,
    durations: DurationTable,
    onsets,
) -> tuple[CompatibilityReport, SoundLog]:
    """``sound(EnvelopeSequence, Candidate, Lexicon, Config) -> CompatibilityReport``.

    ``durations`` (F4) and ``onsets`` (F5) are passed explicitly rather than
    read from module state: Section 21 requires pure functions with no globals.
    """
    common = dict(
        audio_id=envelope.audio_id,
        engine_version=envelope.engine_version,
        provenance=envelope.provenance,
        candidate_id=candidate.candidate_id,
        pair_id=candidate.pair_id,
        context_id=candidate.context_id,
        pair_role=candidate.pair_role,
        predicted_preferred=candidate.predicted_preferred,
    )

    def _excluded(verdict: str, reason: str, rejected=()) -> tuple:
        log = SoundLog(
            candidate_id=candidate.candidate_id, audio_id=envelope.audio_id,
            provenance=envelope.provenance, chosen_variant_index=None,
            n_variants_evaluated=0, per_word_variant=(), syllable_texts=(),
            rho_per_slot=(), d_pre_s=(), d_nucleus_s=(), d_post_s=(),
            per_phone_d_s=(), tiers=(),
            duration_table_is_synthetic=durations.is_synthetic,
            rejected_variants=tuple(rejected), exclusion_reason=reason,
        )
        return (
            CompatibilityReport(
                **common, pronunciation_variant_index=None, verdict=verdict,
                score_b=0.0, score_c=0.0, total_consonant_duration_s=0.0,
                total_nominal_consonant_duration_s=0.0, slots=(),
            ),
            log,
        )

    try:
        parsed = line_variants(candidate.text, lexicon, onsets)
    except KeyError as missing:
        # Section 9: OOV -> ABSTAIN.  Excluded and logged, never guessed.
        return _excluded(VERDICT_ABSTAIN_OOV, f"OOV: {missing.args[0]}")
    except NoLegalPronunciationError as exc:
        # The word IS in the lexicon but no pronunciation survives F5, so this is
        # NOT abstention.  Excluded deterministically from ranking; F5 is never
        # extended to rescue it.
        return _excluded(
            VERDICT_REJECT_HARD,
            f"NO_LEGAL_PRONUNCIATION: {exc}",
            tuple(RejectedVariant(exc.word, -1, o) for o in exc.offending_onsets),
        )
    variants = parsed.variants

    scored = [
        _score_variant(variant, envelope, durations, config) for variant in variants
    ]
    # Best-scoring variant on Score_C, ties broken lexicographically on the
    # variant's per-word index tuple.  Never on dict or iteration order.
    best_index = min(
        range(len(scored)),
        key=lambda i: (-scored[i][1], variants[i].per_word_variant),
    )
    score_b, score_c, slots, log, total_scaled, total_nominal = scored[best_index]

    verdict = (
        VERDICT_REJECT_HARD
        if any(s.feasibility == TIER_HARD_INFEASIBLE for s in slots)
        else VERDICT_ACCEPT
    )

    log = SoundLog(
        candidate_id=candidate.candidate_id,
        rejected_variants=parsed.rejected,
        audio_id=log.audio_id,
        provenance=log.provenance,
        chosen_variant_index=variants[best_index].variant_index,
        n_variants_evaluated=len(variants),
        per_word_variant=log.per_word_variant,
        syllable_texts=log.syllable_texts,
        rho_per_slot=log.rho_per_slot,
        d_pre_s=log.d_pre_s,
        d_nucleus_s=log.d_nucleus_s,
        d_post_s=log.d_post_s,
        per_phone_d_s=log.per_phone_d_s,
        tiers=log.tiers,
        duration_table_is_synthetic=log.duration_table_is_synthetic,
    )
    return (
        CompatibilityReport(
            **common,
            pronunciation_variant_index=variants[best_index].variant_index,
            verdict=verdict,
            score_b=float(score_b),
            score_c=float(score_c),
            total_consonant_duration_s=float(total_scaled),
            total_nominal_consonant_duration_s=float(total_nominal),
            slots=slots,
        ),
        log,
    )


def hard_infeasible_slots(report: CompatibilityReport) -> tuple[int, ...]:
    """Section 8: the offending slot is logged when a candidate is REJECT_HARD."""
    return tuple(s.index for s in report.slots if s.feasibility == TIER_HARD_INFEASIBLE)
