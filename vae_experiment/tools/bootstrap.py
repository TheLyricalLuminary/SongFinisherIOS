"""Regenerate every generated fixture, in dependency order.

The audio fixtures are deterministic functions of their generators and are not
committed; the F9 goldens are.  Running this then `python3 tools/steps.py 1`
verifies a regenerated fixture set against the committed goldens, which checks
the generators as well as the pipeline.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ("make_f1.py", "make_f3.py", "make_f2_synth.py", "make_synthetic_oracle.py")


def main() -> int:
    for script in SCRIPTS:
        print(f"--- {script} ---", flush=True)
        result = subprocess.run([sys.executable, str(ROOT / "tools" / script)], check=False)
        if result.returncode != 0:
            return result.returncode
    print("\nfixtures regenerated. Verify determinism with:")
    print("  python3 tools/steps.py 1        # compares against the committed F9 goldens")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
