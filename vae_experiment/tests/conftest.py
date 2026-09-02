from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from vae.config import load_config  # noqa: E402
from vae.lexicon import load_lexicon  # noqa: E402
from vae.slots import load_slot_masks  # noqa: E402
from vae.tables import load_duration_table, load_onset_table  # noqa: E402

SYNTHETIC_F4 = ROOT / "tests" / "data" / "F4_synthetic.json"
SYNTHETIC_F5 = ROOT / "tests" / "data" / "F5_synthetic.json"


@pytest.fixture(scope="session")
def config():
    return load_config()


@pytest.fixture(scope="session")
def masks():
    return load_slot_masks()


@pytest.fixture(scope="session")
def lexicon():
    return load_lexicon()


@pytest.fixture(scope="session")
def synthetic_durations():
    """SYNTHETIC_TEST_ONLY F4.  Exercises code paths; produces no reportable number."""
    return load_duration_table(SYNTHETIC_F4, allow_synthetic=True)


@pytest.fixture(scope="session")
def real_onsets():
    """The populated F5 inventory (Kivisto-de Souza 2017, Table 1)."""
    return load_onset_table()


@pytest.fixture(scope="session")
def synthetic_onsets():
    """SYNTHETIC_TEST_ONLY F5.  Deliberately incomplete; not a phonotactics inventory."""
    return load_onset_table(SYNTHETIC_F5, allow_synthetic=True)
