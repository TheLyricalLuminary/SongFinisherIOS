"""The six conditions of Section 1.

    B          count + timing + stress.  Context-blind: predicts NO reversal.
    C          system under test, HEAR envelope.
    C_FLAT     envelope replaced by a fixed synthetic uniform grid.
    C_SHUFFLED envelope from a *different* clip, slot-count matched.
    C_ORACLE   same as C, human-annotated evidence.
    A          deliberately mismatched syllable count and stress (manipulation check).

``C_FLAT`` and ``C_SHUFFLED`` are the controls v1.0 lacked.  If ``C_FLAT``
matches ``C``, the audio analysis contributes nothing and the entire HEAR stage
is decorative.  If ``C_SHUFFLED`` matches ``C``, the envelope is not
clip-specific and the result is an artifact.

Both are built here as ``EnvelopeSequence`` values so that ``sound()`` and
``rank()`` consume them through exactly the same path as ``C`` — no condition
flag reaches the scorer.
"""

from __future__ import annotations

from .config import Config
from .constants import METHOD_GRID_ONLY, PROVENANCE_HEAR
from .contracts import Anchor, EnvelopeSequence, EnvelopeSlot
from .errors import ContractError
from .shape import effective_interval
from .slots import SlotMask

FLAT_AUDIO_ID_PREFIX = "FLAT:"
SHUFFLED_AUDIO_ID_PREFIX = "SHUFFLED:"


def flat_envelope(mask: SlotMask, config: Config, engine_version: str) -> EnvelopeSequence:
    """C_FLAT: a fixed synthetic uniform grid — constant I_k, constant sigma.

    The constants are taken from the versioned config (``I_reference`` and
    ``SIGMA_GRID_ONLY``) rather than from any clip, which is the whole point:
    nothing audio-derived may reach this envelope.  Structure still comes from
    the authored mask, since the mask is shared by every condition (Section 5).
    """
    interval = config.I_reference
    sigma = config.SIGMA_GRID_ONLY
    last = mask.slot_count - 1
    slots: list[EnvelopeSlot] = []
    for k in range(mask.slot_count):
        raw = interval if k < last else config.PHRASE_TAIL
        sigma_next = sigma if k < last else 0.0
        eff = effective_interval(raw, sigma, sigma_next, config)
        prev_eff = (
            effective_interval(config.LEAD_IN, 0.0, sigma, config)
            if k == 0
            else slots[k - 1].interval_effective_s
        )
        slots.append(
            EnvelopeSlot(
                index=k,
                interval_s=float(raw),
                interval_effective_s=float(eff),
                anchor=Anchor(
                    slot_index=k,
                    time_s=float(k * interval),
                    sigma_s=float(sigma),
                    method=METHOD_GRID_ONLY,
                    supporting_event_ids=(),
                    rise_time_ms=0.0,
                ),
                d_pre_max_s=float(config.PRE_CAP_FRAC * prev_eff),
                d_post_max_s=float(config.POST_CAP_FRAC * eff),
                metrical_strength=mask.metrical_strength[k],
                uncertainty_anchor_sigma_s=float(sigma),
                uncertainty_source="C_FLAT_SYNTHETIC_GRID",
                derived_from_event_ids=(),
                derived_from_beat_indices=(),
            )
        )
    return EnvelopeSequence(
        audio_id=f"{FLAT_AUDIO_ID_PREFIX}{mask.mask_id}",
        engine_version=engine_version,
        provenance=PROVENANCE_HEAR,
        slot_mask_id=mask.mask_id,
        slots=tuple(slots),
    )


def select_shuffled_donor(
    target_audio_id: str, pool: dict[str, EnvelopeSequence]
) -> EnvelopeSequence:
    """Pick the donor clip for C_SHUFFLED deterministically.

    ``pool`` must already be slot-count matched.  Selection is the
    lexicographically next ``audio_id`` after the target, wrapping around — a
    fixed rule with no RNG and no dict-ordering dependence (Section 15).
    """
    ids = sorted(aid for aid in pool if aid != target_audio_id)
    if not ids:
        raise ContractError(
            f"C_SHUFFLED needs a slot-count-matched donor other than {target_audio_id[:16]}..."
        )
    later = [aid for aid in ids if aid > target_audio_id]
    return pool[later[0] if later else ids[0]]


def shuffled_envelope(
    target_audio_id: str, pool: dict[str, EnvelopeSequence], mask: SlotMask
) -> EnvelopeSequence:
    """C_SHUFFLED: the donor's envelope, relabelled, structure from the target's mask.

    Only the *envelope* is borrowed.  The slot mask is the target's, so the
    control differs from ``C`` in the audio-derived quantities alone.
    """
    donor = select_shuffled_donor(target_audio_id, pool)
    if donor.slot_mask_id != mask.mask_id:
        raise ContractError(
            f"C_SHUFFLED donor uses mask {donor.slot_mask_id!r}, target uses {mask.mask_id!r}"
        )
    if len(donor.slots) != mask.slot_count:
        raise ContractError("C_SHUFFLED donor is not slot-count matched")
    return EnvelopeSequence(
        audio_id=f"{SHUFFLED_AUDIO_ID_PREFIX}{target_audio_id}<-{donor.audio_id}",
        engine_version=donor.engine_version,
        provenance=donor.provenance,
        slot_mask_id=mask.mask_id,
        slots=donor.slots,
    )
