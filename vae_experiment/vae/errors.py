"""Hard-failure taxonomy.

Spec discipline: the pipeline never degrades gracefully. Section 2 rejection is
mandatory (clips are *excluded*, not repaired); a missing F4 phone is a hard
error and never a silent default (Section 22 failure #10); an out-of-vocabulary
word abstains rather than guessing (Section 9).
"""


class VAEError(Exception):
    """Base class for every deliberate failure in the pipeline."""


class ClipRejected(VAEError):
    """Section 2 admission failure. The clip is excluded before analysis."""

    def __init__(self, reason_code: str, detail: str):
        self.reason_code = reason_code
        self.detail = detail
        super().__init__(f"{reason_code}: {detail}")


class MissingPhoneError(VAEError):
    """A phone required for budgeting is absent from F4. Never defaulted."""


class MissingOnsetTableError(VAEError):
    """The F5 legal-onset table is absent or does not cover a needed cluster."""


class FixtureUnpopulatedError(VAEError):
    """A fixture exists as a schema stub but carries no authored data yet."""

    def __init__(self, fixture_id: str, required_source: str):
        self.fixture_id = fixture_id
        self.required_source = required_source
        super().__init__(
            f"{fixture_id} is UNPOPULATED. Required source material: {required_source}"
        )


class NoLegalPronunciationError(VAEError):
    """Every CMUdict variant of some word uses an onset F5 does not license.

    Distinct from OOV: the word IS in the lexicon, but no pronunciation of it
    survives the legal-onset table.  The candidate is excluded deterministically
    rather than abstained, and never rescued by adding an onset to F5.
    """

    def __init__(self, word: str, offending_onsets: tuple[tuple[str, ...], ...]):
        self.word = word
        self.offending_onsets = offending_onsets
        rendered = ", ".join(" ".join(o) for o in offending_onsets)
        super().__init__(
            f"{word!r} has no pronunciation whose onset F5 licenses (tried: {rendered})"
        )


class DeterminismViolation(VAEError):
    """A rerun differed from its golden snapshot beyond the Section 15 contract."""


class ConfigError(VAEError):
    """The versioned config is missing a Section 18 parameter or has an extra one."""


class ContractError(VAEError):
    """A record violates a Section 20 data contract."""
