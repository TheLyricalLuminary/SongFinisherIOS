"""Section 11 — trial construction and the five mandatory pre-registration checks.

    Trial = pair x two contexts.  Each pair is presented under two clips with
    OPPOSITE interval asymmetry, giving four cells: {X, Y} x {context1, context2}.

The five checks, run offline before any human data:

    1. |Score_B(X) - Score_B(Y)| <= eps_tie in BOTH contexts.  B is indifferent
       everywhere.
    2. Score_C prefers DIFFERENT members in the two contexts — an actual reversal.
    3. Reversal margin |Delta Score_C| >= MARGIN_MIN in both contexts.
    4. Nominal load sum d_nominal(c) matched between X and Y within LOAD_TOL.
       MUST use d_nominal, not d(c): the tempo-scaled d(c) legitimately differs
       between X and Y because the cluster sits in a different interval, and that
       difference *is the effect under test*.  Filtering on d(c) would discard
       exactly the valid pairs.
    5. C_FLAT produces NO reversal for the pair.

Any pair failing any check is discarded before the human phase.  No exceptions,
no post-hoc admission.  This module *discards*; it never admits with a warning.

Ahead of those five checks sits an *eligibility* guard, which is not one of them.
The checks judge a pair's behaviour once scored; the guard decides whether the
pair can be scored at all.  V1 budgets 22 scalar consonants — CH and JH are
deferred and F4 has no row for either — so a line containing an affricate in any
pronunciation variant would reach a hard duration-table error inside SOUND.  The
guard keeps such lines out of the pool at authoring time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from .config import Config
from .constants import V1_DEFERRED_CONSONANTS
from .contracts import CompatibilityReport
from .errors import ContractError
from .lexicon import Lexicon, tokenize

CHECK_IDS = (
    "C1_B_TIED_BOTH_CONTEXTS",
    "C2_SCORE_C_REVERSAL",
    "C3_REVERSAL_MARGIN",
    "C4_NOMINAL_LOAD_MATCHED",
    "C5_C_FLAT_NO_REVERSAL",
)


@dataclass(frozen=True)
class PairSpec:
    """An authored positional-permutation pair (F7)."""

    pair_id: str
    line_x: str
    line_y: str
    context_1_id: str            # (clip, mask) context with one asymmetry direction
    context_2_id: str            # the opposite direction
    # Authoring metadata that Section 11 requires to be matched by construction.
    syllable_count: int
    stress_pattern: tuple[str, ...]
    zipf_decile: int
    syntactic_form: str
    heavy_cluster_syllable_x: int
    heavy_cluster_syllable_y: int
    predicted_preferred_context_1: str    # "X" | "Y", pre-registered per trial
    predicted_preferred_context_2: str


# --------------------------------------------------------------------------- #
# F7 eligibility — applied BEFORE a pair is ever scored
# --------------------------------------------------------------------------- #

ELIGIBLE = "ELIGIBLE"
INELIGIBLE_DEFERRED_PHONE = "INELIGIBLE_DEFERRED_PHONE"
INELIGIBLE_OOV = "INELIGIBLE_OOV"


@dataclass(frozen=True)
class EligibilityVerdict:
    """Whether a line may enter the F7 pool, and if not, precisely why."""

    subject: str                                  # the line, or a pair_id
    reason: str                                   # one of the three codes above
    offending: tuple[tuple[str, int, str], ...] = ()   # (word, variant_index, phone)
    oov_words: tuple[str, ...] = ()

    @property
    def eligible(self) -> bool:
        return self.reason == ELIGIBLE

    def detail(self) -> str:
        if self.reason == INELIGIBLE_OOV:
            return f"out of vocabulary: {', '.join(self.oov_words)}"
        if self.reason == INELIGIBLE_DEFERRED_PHONE:
            return "; ".join(
                f"{word}({index}) uses {phone}" for word, index, phone in self.offending
            )
        return ""


def check_line_eligibility(
    line: str,
    lexicon: Lexicon,
    deferred: Iterable[str] = V1_DEFERRED_CONSONANTS,
) -> EligibilityVerdict:
    """Reject a line that any CMUdict variant would cost against a deferred phone.

    V1 budgets 22 scalar consonants; CH and JH are deferred and F4 carries no row
    for either (``vae.constants.V1_DEFERRED_CONSONANTS``).  A duration lookup for
    one is a hard error by Section 22 failure #10 — correct, but it would fire
    deep inside SOUND, mid-experiment, on an authored line.  This guard moves the
    refusal to authoring time, where it costs a line rather than a run.

    The test is over EVERY variant, not the best or the first.  Section 9 has
    SOUND score all variants and report the best, so a single deferred phone in a
    single secondary pronunciation is enough to reach the failing lookup —
    ``amateur`` is ``AE M AH T ER`` but also ``AE M AH CH ER``.  Restricting the
    check to the primary variant would admit exactly the lines that later crash.

    A phone is looked for anywhere in the pronunciation, not just the onset: an
    affricate in a coda is budgeted by Section 7 the same way.

    Out-of-vocabulary words are ineligible rather than eligible.  Their
    pronunciation is unknown, so their phones are unknown, and Section 11
    requires F7 members to be free of OOV words in any case.

    ``deferred`` is a parameter so the same guard can be pointed at whatever a
    later F4 actually covers; the default is the V1 decision.
    """
    deferred_set = frozenset(deferred)
    words = tokenize(line)
    if not words:
        raise ContractError("empty candidate line")

    oov = tuple(dict.fromkeys(w for w in words if w not in lexicon))
    if oov:
        return EligibilityVerdict(line, INELIGIBLE_OOV, oov_words=oov)

    offending: list[tuple[str, int, str]] = []
    for word in dict.fromkeys(words):              # deduplicated, order preserved
        for pron in lexicon.variants(word):
            for phone in pron.phones:
                if phone in deferred_set:
                    offending.append((word, pron.variant_index, phone))
    if offending:
        return EligibilityVerdict(
            line, INELIGIBLE_DEFERRED_PHONE, offending=tuple(offending)
        )
    return EligibilityVerdict(line, ELIGIBLE)


def check_pair_eligibility(
    spec: PairSpec,
    lexicon: Lexicon,
    deferred: Iterable[str] = V1_DEFERRED_CONSONANTS,
) -> EligibilityVerdict:
    """A pair is eligible only if BOTH members are.

    Dropping one member and keeping the other is not an option: Section 11 tests
    a reversal between X and Y, which needs both.
    """
    x = check_line_eligibility(spec.line_x, lexicon, deferred)
    y = check_line_eligibility(spec.line_y, lexicon, deferred)
    for verdict in (x, y):
        if not verdict.eligible:
            return EligibilityVerdict(
                spec.pair_id, verdict.reason,
                offending=x.offending + y.offending,
                oov_words=x.oov_words + y.oov_words,
            )
    return EligibilityVerdict(spec.pair_id, ELIGIBLE)


def screen_pairs(
    specs: Iterable[PairSpec],
    lexicon: Lexicon,
    deferred: Iterable[str] = V1_DEFERRED_CONSONANTS,
) -> tuple[tuple[PairSpec, ...], tuple[EligibilityVerdict, ...]]:
    """Partition an authored pool into (eligible pairs, rejection verdicts).

    Run this before scoring anything.  Like ``run_gate``, it discards rather than
    admitting with a warning, and the rejections are returned so the pool's
    shortfall against the 60-pair target is visible rather than silent.
    """
    eligible: list[PairSpec] = []
    rejected: list[EligibilityVerdict] = []
    for spec in specs:
        verdict = check_pair_eligibility(spec, lexicon, deferred)
        if verdict.eligible:
            eligible.append(spec)
        else:
            rejected.append(verdict)
    return tuple(eligible), tuple(rejected)


@dataclass(frozen=True)
class CellReports:
    """The four cells of one trial, plus the C_FLAT control cells."""

    c_x1: CompatibilityReport
    c_y1: CompatibilityReport
    c_x2: CompatibilityReport
    c_y2: CompatibilityReport
    flat_x1: CompatibilityReport
    flat_y1: CompatibilityReport
    flat_x2: CompatibilityReport
    flat_y2: CompatibilityReport


@dataclass(frozen=True)
class CheckResult:
    check_id: str
    passed: bool
    detail: str
    value: Optional[float] = None


@dataclass(frozen=True)
class PairVerdict:
    pair_id: str
    admitted: bool
    checks: tuple[CheckResult, ...]
    preferred_context_1: Optional[str]
    preferred_context_2: Optional[str]
    delta_c_context_1: Optional[float]
    delta_c_context_2: Optional[float]
    nominal_load_delta_s: Optional[float]

    def failed_checks(self) -> tuple[str, ...]:
        return tuple(c.check_id for c in self.checks if not c.passed)


def _prefers(x: CompatibilityReport, y: CompatibilityReport, config: Config) -> Optional[str]:
    """Which member Score_C prefers.  ``None`` when the difference is within eps_tie."""
    delta = x.score_c - y.score_c
    if abs(delta) <= config.epsilon_tie:
        return None
    return "X" if delta > 0.0 else "Y"


def check_pair(spec: PairSpec, cells: CellReports, config: Config) -> PairVerdict:
    """Run all five Section 11 checks.  Returns a verdict; never mutates state."""
    for name, report in (
        ("c_x1", cells.c_x1), ("c_y1", cells.c_y1),
        ("c_x2", cells.c_x2), ("c_y2", cells.c_y2),
    ):
        if report.pair_id != spec.pair_id:
            raise ContractError(f"{name}: pair_id {report.pair_id!r} != {spec.pair_id!r}")

    checks: list[CheckResult] = []

    # --- Check 1: B is indifferent in both contexts -------------------------
    b1 = abs(cells.c_x1.score_b - cells.c_y1.score_b)
    b2 = abs(cells.c_x2.score_b - cells.c_y2.score_b)
    b_ok = b1 <= config.epsilon_tie and b2 <= config.epsilon_tie
    checks.append(CheckResult(
        CHECK_IDS[0], b_ok,
        f"|dScore_B| ctx1={b1:.3e} ctx2={b2:.3e} (eps_tie={config.epsilon_tie:.1e})",
        max(b1, b2),
    ))

    # --- Check 2: Score_C prefers different members in the two contexts ------
    pref1 = _prefers(cells.c_x1, cells.c_y1, config)
    pref2 = _prefers(cells.c_x2, cells.c_y2, config)
    reversal = pref1 is not None and pref2 is not None and pref1 != pref2
    checks.append(CheckResult(
        CHECK_IDS[1], reversal, f"Score_C prefers ctx1={pref1} ctx2={pref2}"
    ))

    # --- Check 3: reversal margin in both contexts --------------------------
    d1 = cells.c_x1.score_c - cells.c_y1.score_c
    d2 = cells.c_x2.score_c - cells.c_y2.score_c
    margin_ok = abs(d1) >= config.MARGIN_MIN and abs(d2) >= config.MARGIN_MIN
    checks.append(CheckResult(
        CHECK_IDS[2], margin_ok,
        f"|dScore_C| ctx1={abs(d1):.4f} ctx2={abs(d2):.4f} (MARGIN_MIN={config.MARGIN_MIN})",
        min(abs(d1), abs(d2)),
    ))

    # --- Check 4: nominal load matched (d_nominal, never d(c)) --------------
    load_delta = abs(
        cells.c_x1.total_nominal_consonant_duration_s
        - cells.c_y1.total_nominal_consonant_duration_s
    )
    load_ok = load_delta <= config.LOAD_TOL
    checks.append(CheckResult(
        CHECK_IDS[3], load_ok,
        f"|d sum d_nominal| = {load_delta:.4f} s (LOAD_TOL={config.LOAD_TOL})",
        load_delta,
    ))

    # --- Check 5: C_FLAT produces no reversal -------------------------------
    flat1 = _prefers(cells.flat_x1, cells.flat_y1, config)
    flat2 = _prefers(cells.flat_x2, cells.flat_y2, config)
    flat_reversal = flat1 is not None and flat2 is not None and flat1 != flat2
    checks.append(CheckResult(
        CHECK_IDS[4], not flat_reversal, f"C_FLAT prefers ctx1={flat1} ctx2={flat2}"
    ))

    return PairVerdict(
        pair_id=spec.pair_id,
        admitted=all(c.passed for c in checks),
        checks=tuple(checks),
        preferred_context_1=pref1,
        preferred_context_2=pref2,
        delta_c_context_1=d1,
        delta_c_context_2=d2,
        nominal_load_delta_s=load_delta,
    )


@dataclass(frozen=True)
class GateReport:
    """Step-8 output.  The step-9 blocking gate reads ``n_admitted`` against 60."""

    n_evaluated: int
    n_admitted: int
    admitted_pair_ids: tuple[str, ...]
    verdicts: tuple[PairVerdict, ...]
    failure_counts: tuple[tuple[str, int], ...]

    @property
    def target_pairs(self) -> int:
        return 60          # Section 11 target and the Section 23 step-9 floor

    def step9_would_pass(self) -> bool:
        """Reported, never acted on here.  Step 9 is a separate, gated step."""
        return self.n_admitted >= self.target_pairs


def run_gate(verdicts: list[PairVerdict] | tuple[PairVerdict, ...]) -> GateReport:
    """Aggregate pair verdicts.  Failing pairs are DISCARDED, not flagged."""
    admitted = tuple(sorted(v.pair_id for v in verdicts if v.admitted))
    counts: dict[str, int] = {check_id: 0 for check_id in CHECK_IDS}
    for verdict in verdicts:
        for failed in verdict.failed_checks():
            counts[failed] += 1
    return GateReport(
        n_evaluated=len(verdicts),
        n_admitted=len(admitted),
        admitted_pair_ids=admitted,
        verdicts=tuple(sorted(verdicts, key=lambda v: v.pair_id)),
        failure_counts=tuple((check_id, counts[check_id]) for check_id in CHECK_IDS),
    )
