"""Section 15 determinism contract and the F9 golden harness.

| Level              | Required | Definition                                        |
|--------------------|----------|---------------------------------------------------|
| Bit-identical float| No       | Explicitly waived across devices                  |
| Numerical          | Yes      | eps_num = 1e-6 relative same-platform; 1e-4 cross |
| Discrete-decision  | Yes      | Identical onset counts, feasibility tiers, verdicts|
| Ordering           | Yes      | Identical ranked lists                            |
| Semantic           | N/A      | No LM in V1                                       |

Discrete fields must match exactly; float fields must match within the
tolerance.  A discrete mismatch is never absorbed into the numeric tolerance —
that is the whole point of having two levels.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contracts import to_jsonable
from .errors import DeterminismViolation

EPS_NUM_SAME_PLATFORM = 1e-6
EPS_NUM_CROSS_PLATFORM = 1e-4


@dataclass(frozen=True)
class Difference:
    path: str
    left: Any
    right: Any
    kind: str          # "DISCRETE" | "NUMERICAL" | "STRUCTURE"


def compare(left: Any, right: Any, eps: float = EPS_NUM_SAME_PLATFORM,
            path: str = "$") -> list[Difference]:
    """Structural diff honouring the Section 15 levels."""
    if isinstance(left, bool) or isinstance(right, bool):
        return [] if left == right else [Difference(path, left, right, "DISCRETE")]
    if isinstance(left, float) or isinstance(right, float):
        if not isinstance(left, (int, float)) or not isinstance(right, (int, float)):
            return [Difference(path, left, right, "STRUCTURE")]
        a, b = float(left), float(right)
        scale = max(1.0, abs(a), abs(b))
        return [] if abs(a - b) <= eps * scale else [
            Difference(path, a, b, "NUMERICAL")
        ]
    if isinstance(left, dict) and isinstance(right, dict):
        out: list[Difference] = []
        for key in sorted(set(left) | set(right)):
            if key not in left or key not in right:
                out.append(Difference(f"{path}.{key}", left.get(key), right.get(key), "STRUCTURE"))
            else:
                out.extend(compare(left[key], right[key], eps, f"{path}.{key}"))
        return out
    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            return [Difference(f"{path}[]", len(left), len(right), "STRUCTURE")]
        out = []
        for i, (a, b) in enumerate(zip(left, right)):
            out.extend(compare(a, b, eps, f"{path}[{i}]"))
        return out
    return [] if left == right else [Difference(path, left, right, "DISCRETE")]


def assert_matches_golden(
    produced: Any, golden_path: Path | str, eps: float = EPS_NUM_SAME_PLATFORM
) -> None:
    golden_path = Path(golden_path)
    if not golden_path.exists():
        raise DeterminismViolation(f"no golden snapshot at {golden_path}")
    golden = json.loads(golden_path.read_text(encoding="utf-8"))
    diffs = compare(golden, to_jsonable(produced), eps)
    if diffs:
        head = "\n".join(
            f"  [{d.kind}] {d.path}: golden={d.left!r} produced={d.right!r}" for d in diffs[:20]
        )
        raise DeterminismViolation(
            f"{golden_path.name}: {len(diffs)} difference(s) vs golden\n{head}"
        )


def discrete_fields(payload: Any, path: str = "$") -> dict[str, Any]:
    """Extract only the discrete-decision fields, for the strictest comparison."""
    out: dict[str, Any] = {}
    if isinstance(payload, dict):
        for key in sorted(payload):
            out.update(discrete_fields(payload[key], f"{path}.{key}"))
    elif isinstance(payload, list):
        for i, item in enumerate(payload):
            out.update(discrete_fields(item, f"{path}[{i}]"))
    elif isinstance(payload, bool) or isinstance(payload, int) or isinstance(payload, str):
        out[path] = payload
    return out
