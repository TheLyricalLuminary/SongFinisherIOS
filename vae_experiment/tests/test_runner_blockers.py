"""The step runners must report a blocker, never crash and never pass vacuously.

Populating F4 removed the table gate that had been short-circuiting steps 6 and 7
before they touched their candidate pool.  With the gate gone, step 7 handed
``rank`` an empty list and took a ContractError, and step 6 reported
``blocked: false`` over zero candidates.

``rank`` is right to refuse an empty list (Section 20) -- an empty ranking is not
a result.  What was wrong was the runner calling it with one.  These tests pin
the corrected behaviour so the crash cannot come back the next time a gate is
removed.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.steps import step6, step7  # noqa: E402


def test_step6_reports_a_blocker_rather_than_a_vacuous_pass():
    report = step6()
    assert report["blocked"] is True
    assert "F7" in report["blocker"]
    assert report["F4_status"] == "POPULATED"
    assert "candidates" not in report          # no empty list masquerading as a result


def test_step7_reports_a_blocker_rather_than_raising():
    """Previously: ContractError('rank: no reports')."""
    report = step7()
    assert report["blocked"] is True
    assert "F7" in report["blocker"]
    assert report["F4_status"] == "POPULATED"


def test_the_blocker_names_the_pool_not_the_tables():
    """F4/F5 gate the tables; F7 supplies the candidates.  Naming F4 here would be false."""
    report = step7()
    assert report["F4_status"] == "POPULATED"
    assert report["F5_status"] == "POPULATED"
    assert report["F7_status"] == "UNPOPULATED"
    assert "UNPOPULATED" in report["blocker"] and "F4" not in report["blocker"]
