"""Section 5 — slot derivation.  Authored, never inferred.

Slot placement is *not under test*.  Inferring it would add a failure mode that
confounds the primary contrast, so the mask is authored per clip, stored as
fixture data (F6), and consumed identically by the HEAR and oracle branches.

    slot_positions = mask.positions            # eighth-note indices
    g_k            = beat_grid[0] + position_k * (60 / tempo) / 2

Metrical strength comes from the mask, never from a detected downbeat — which
is why bar-phase ambiguity in HEAR is harmless (Section 5 "Consequence") and why
downbeat identification could be removed from scope (Section 4, Section 19).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .constants import (
    BEATS_PER_BAR,
    MASK_POSITION_COUNT,
    METRICAL_STRENGTHS,
    SUBDIVISIONS_PER_BEAT,
)
from .errors import ContractError
from .version import sha256_file

DEFAULT_MASK_PATH = (
    Path(__file__).resolve().parent.parent / "fixtures" / "F6_slot_masks" / "slot_masks.json"
)


@dataclass(frozen=True)
class SlotMask:
    mask_id: str
    positions: tuple[int, ...]          # eighth-note indices on a 2-bar lattice
    metrical_strength: tuple[str, ...]  # authored, one per occupied position
    description: str = ""

    @property
    def slot_count(self) -> int:
        return len(self.positions)

    def slot_times(self, beat0_s: float, tempo_bpm: float) -> np.ndarray:
        """g_k = beat_grid[0] + position_k * (60 / tempo) / 2 (Section 5)."""
        eighth = (60.0 / tempo_bpm) / SUBDIVISIONS_PER_BEAT
        return beat0_s + np.asarray(self.positions, dtype=np.float64) * eighth

    @property
    def nominal_gaps(self) -> tuple[int, ...]:
        """Inter-position gaps in eighths.  The final slot's interval is PHRASE_TAIL."""
        return tuple(
            self.positions[i + 1] - self.positions[i] for i in range(len(self.positions) - 1)
        )

    @property
    def nominal_asymmetry(self) -> float:
        """max(I)/min(I) over the mask's own intervals — tempo-independent."""
        gaps = self.nominal_gaps
        if not gaps:
            return 1.0
        return max(gaps) / min(gaps)

    def asymmetry_direction(self) -> str:
        """Section 13.1 ``asym``: SHORT_FIRST / LONG_FIRST / SYMMETRIC."""
        gaps = self.nominal_gaps
        if len(gaps) < 2 or gaps[0] == gaps[1]:
            return "SYMMETRIC"
        return "SHORT_FIRST" if gaps[0] < gaps[1] else "LONG_FIRST"

    def is_asymmetric(self, asymmetry_min: float) -> bool:
        return self.nominal_asymmetry >= asymmetry_min

    def duration_eighths(self) -> int:
        return self.positions[-1] - self.positions[0] if self.positions else 0


@dataclass(frozen=True)
class SlotMaskInventory:
    masks: tuple[SlotMask, ...]
    source_path: str
    sha256: str

    def by_id(self, mask_id: str) -> SlotMask:
        for mask in self.masks:
            if mask.mask_id == mask_id:
                return mask
        raise KeyError(f"unknown slot mask: {mask_id}")

    def with_slot_count(self, slot_count: int) -> tuple[SlotMask, ...]:
        return tuple(m for m in self.masks if m.slot_count == slot_count)


def _validate(mask: SlotMask) -> None:
    if not mask.positions:
        raise ContractError(f"{mask.mask_id}: empty position list")
    if list(mask.positions) != sorted(set(mask.positions)):
        raise ContractError(f"{mask.mask_id}: positions must be strictly increasing and unique")
    if not all(0 <= p < MASK_POSITION_COUNT for p in mask.positions):
        raise ContractError(
            f"{mask.mask_id}: positions must lie on the {MASK_POSITION_COUNT}-slot "
            f"{BEATS_PER_BAR}/4 eighth lattice"
        )
    if len(mask.metrical_strength) != len(mask.positions):
        raise ContractError(f"{mask.mask_id}: one metrical strength per occupied position")
    bad = [s for s in mask.metrical_strength if s not in METRICAL_STRENGTHS]
    if bad:
        raise ContractError(f"{mask.mask_id}: unknown metrical strength {bad}")


def load_slot_masks(path: Path | str | None = None) -> SlotMaskInventory:
    path = Path(path) if path is not None else DEFAULT_MASK_PATH
    doc = json.loads(path.read_bytes().decode("utf-8"))
    masks = tuple(
        SlotMask(
            mask_id=str(entry["mask_id"]),
            positions=tuple(int(p) for p in entry["positions"]),
            metrical_strength=tuple(str(s) for s in entry["metrical_strength"]),
            description=str(entry.get("description", "")),
        )
        for entry in doc["masks"]
    )
    for mask in masks:
        _validate(mask)
    ids = [m.mask_id for m in masks]
    if len(set(ids)) != len(ids):
        raise ContractError(f"{path}: duplicate mask_id")
    return SlotMaskInventory(masks=masks, source_path=str(path), sha256=sha256_file(path))
