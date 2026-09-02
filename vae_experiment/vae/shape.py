"""SHAPE — Section 6 effective interval, Section 7 partition and diagnostic caps.

Two rules carry the v1.0 defect fixes and are enforced here:

*   **All downstream budgeting uses ``I_effective``, never ``I_k``.**  The raw
    interval is logged (Section 16) and never budgeted against (Section 24).
*   **``d_pre_max`` / ``d_post_max`` are diagnostic only.**  They are emitted on
    every slot and read by no scoring function — scoring them alongside the
    residual was the v1.0 double-counting bug (defect 2).

``shape()`` does not branch on ``provenance``.  If it did, the oracle would not
be a control (Section 12).  ``tests/test_no_provenance_branch.py`` asserts this
both statically and behaviourally.

Two interpretations where Section 6/7 is silent, both stated rather than hidden:

*   The final slot's interval is ``PHRASE_TAIL`` and the first slot's
    pre-interval is ``LEAD_IN``.  Neither has a second measured endpoint, so the
    uncertainty term uses the one real anchor's sigma with the configured
    endpoint contributing zero.  Uncertainty that exists still shrinks the
    budget; uncertainty that does not exist is not invented.
"""

from __future__ import annotations

import math

from .config import Config
from .contracts import AcousticEvidence, Anchor, EnvelopeSequence, EnvelopeSlot
from .errors import ContractError
from .slots import SlotMask


def effective_interval(interval_s: float, sigma_a: float, sigma_b: float, config: Config) -> float:
    """I_effective = max( I_MIN, I - SIGMA_COEF * sqrt(sigma_a^2 + sigma_b^2) ).

    Time you cannot localise is time you cannot budget against (Section 6).
    ``SIGMA_COEF = 0`` is an explicit sweep point and reduces this to the
    identity, so the sweep *answers* whether uncertainty modelling matters.
    """
    shrink = config.SIGMA_COEF * math.sqrt(sigma_a * sigma_a + sigma_b * sigma_b)
    return max(config.I_MIN, interval_s - shrink)


def shape(evidence: AcousticEvidence, config: Config, mask: SlotMask) -> EnvelopeSequence:
    """``shape(AcousticEvidence, Config) -> EnvelopeSequence`` (Section 21).

    The mask is passed alongside because ``metrical_strength`` is authored with
    the mask (Section 5) and ``AcousticEvidence`` carries only its id.  Pure: no
    I/O, no globals, no history, no state.
    """
    if evidence.slot_mask_id != mask.mask_id:
        raise ContractError(
            f"evidence names slot mask {evidence.slot_mask_id!r} but {mask.mask_id!r} was supplied"
        )
    anchors = evidence.anchors
    if len(anchors) != mask.slot_count:
        raise ContractError(
            f"{mask.mask_id}: {mask.slot_count} slots but {len(anchors)} anchors"
        )

    event_beat = {e.id: e.matched_beat_index for e in evidence.events}
    last = len(anchors) - 1
    slots: list[EnvelopeSlot] = []

    for k, anchor in enumerate(anchors):
        # I_k = anchor_{k+1} - anchor_k; final slot: PHRASE_TAIL.
        if k < last:
            interval = anchors[k + 1].time_s - anchor.time_s
            sigma_next = anchors[k + 1].sigma_s
        else:
            interval = config.PHRASE_TAIL
            sigma_next = 0.0
        interval_effective = effective_interval(interval, anchor.sigma_s, sigma_next, config)

        # Diagnostic caps (Section 7).  Slot 0's pre-interval is LEAD_IN.
        if k == 0:
            prev_effective = effective_interval(config.LEAD_IN, 0.0, anchor.sigma_s, config)
        else:
            prev_effective = slots[k - 1].interval_effective_s
        d_pre_max = config.PRE_CAP_FRAC * prev_effective
        d_post_max = config.POST_CAP_FRAC * interval_effective

        neighbours: tuple[Anchor, ...] = (anchor,) if k == last else (anchor, anchors[k + 1])
        event_ids = tuple(sorted({eid for a in neighbours for eid in a.supporting_event_ids}))
        beat_indices = tuple(sorted({
            b for eid in event_ids
            if (b := event_beat.get(eid)) is not None
        }))

        slots.append(
            EnvelopeSlot(
                index=k,
                interval_s=float(interval),
                interval_effective_s=float(interval_effective),
                anchor=anchor,
                d_pre_max_s=float(d_pre_max),
                d_post_max_s=float(d_post_max),
                metrical_strength=mask.metrical_strength[k],
                uncertainty_anchor_sigma_s=float(anchor.sigma_s),
                uncertainty_source=anchor.method,
                derived_from_event_ids=event_ids,
                derived_from_beat_indices=beat_indices,
            )
        )

    return EnvelopeSequence(
        audio_id=evidence.audio_id,
        engine_version=evidence.engine_version,
        provenance=evidence.provenance,
        slot_mask_id=evidence.slot_mask_id,
        slots=tuple(slots),
    )


def lead_in_effective(first_anchor_sigma_s: float, config: Config) -> float:
    """The pre-slot interval that ``D_pre(0)`` is drawn from (Section 7)."""
    return effective_interval(config.LEAD_IN, 0.0, first_anchor_sigma_s, config)


def realized_asymmetry(envelope: EnvelopeSequence) -> float:
    """max(I)/min(I) over the realised inter-anchor intervals (Section 2)."""
    intervals = [s.interval_s for s in envelope.slots[:-1]]
    if not intervals or min(intervals) <= 0.0:
        return 1.0
    return max(intervals) / min(intervals)


def realized_asymmetry_direction(envelope: EnvelopeSequence, config: Config) -> str:
    """Section 13.1 ``asym`` read off the realised envelope."""
    intervals = [s.interval_s for s in envelope.slots[:-1]]
    if len(intervals) < 2 or abs(intervals[0] - intervals[1]) <= config.epsilon_num:
        return "SYMMETRIC"
    return "SHORT_FIRST" if intervals[0] < intervals[1] else "LONG_FIRST"
