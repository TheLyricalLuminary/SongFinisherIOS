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


class DeterminismViolation(VAEError):
    """A rerun differed from its golden snapshot beyond the Section 15 contract."""


class ConfigError(VAEError):
    """The versioned config is missing a Section 18 parameter or has an extra one."""


class ContractError(VAEError):
    """A record violates a Section 20 data contract."""
