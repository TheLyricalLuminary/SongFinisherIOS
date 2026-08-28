"""Section 9 — pronunciation and G2P.

    Lexicon                  CMUdict, pinned version, hash in EngineVersion
    Phone set                ARPAbet with stress digits
    Multiple pronunciations  Evaluate all variants; report best-scoring; log winner
    Syllabification          Deterministic Maximum Onset Principle against F5
    Stress mapping           1 -> primary, 2 -> secondary, 0 -> unstressed
    OOV                      ABSTAIN -> ABSTAIN_OOV, excluded, logged
    Neural G2P               DEFERRED.  Not built.

Abstention is a feature.  A neural fallback would inject a stochastic
unversioned component into the deterministic core for the sake of words an
authored pool can simply exclude.

Syllabification is applied **per word**.  Cross-word resyllabification is not
performed: it is not specified, it would make a line's syllable boundaries
depend on its neighbours, and Section 11 requires pair members to be comparable
position-for-position.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .constants import STRESS_DIGIT_MAP, STRESS_UNSTRESSED
from .errors import ContractError
from .tables import OnsetTable
from .version import sha256_file

DEFAULT_LEXICON_PATH = (
    Path(__file__).resolve().parent.parent / "fixtures" / "lexicon" / "cmudict.dict"
)

_VARIANT_RE = re.compile(r"^(?P<word>.+?)(?:\((?P<index>\d+)\))?$")
_WORD_SPLIT_RE = re.compile(r"[^a-z'\-]+")

# ARPAbet vowels carry a stress digit; consonants never do.  This is a property
# of the pinned symbol set, read from cmudict.phones rather than hard-coded.
_VOWEL_CLASS = "vowel"


@dataclass(frozen=True)
class Pronunciation:
    """One CMUdict variant of one word."""

    word: str
    variant_index: int
    phones: tuple[str, ...]        # stress digits stripped
    stresses: tuple[str, ...]      # one per vowel, in order


@dataclass(frozen=True)
class Lexicon:
    """CMUdict, pinned.  ``sha256`` is one of the seven EngineVersion inputs."""

    source_path: str
    sha256: str
    vowels: frozenset[str]
    _entries: dict[str, tuple[Pronunciation, ...]]

    def __contains__(self, word: str) -> bool:
        return word.lower() in self._entries

    def variants(self, word: str) -> tuple[Pronunciation, ...]:
        return self._entries.get(word.lower(), ())

    def is_vowel(self, phone: str) -> bool:
        return phone in self.vowels

    @property
    def size(self) -> int:
        return len(self._entries)


def load_lexicon(path: Path | str | None = None) -> Lexicon:
    path = Path(path) if path is not None else DEFAULT_LEXICON_PATH
    phones_path = path.parent / "cmudict.phones"
    vowels = frozenset(
        line.split("\t")[0]
        for line in phones_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and line.split("\t")[1].strip() == _VOWEL_CLASS
    )

    entries: dict[str, list[Pronunciation]] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        head, *tokens = line.split()
        match = _VARIANT_RE.match(head)
        if match is None:                                    # pragma: no cover
            raise ContractError(f"unparsable CMUdict entry: {raw!r}")
        word = match.group("word").lower()
        index = int(match.group("index") or 1) - 1

        bare: list[str] = []
        stresses: list[str] = []
        for token in tokens:
            if token[-1].isdigit():
                bare.append(token[:-1])
                stresses.append(STRESS_DIGIT_MAP[token[-1]])
            else:
                bare.append(token)
        entries.setdefault(word, []).append(
            Pronunciation(word=word, variant_index=index, phones=tuple(bare),
                          stresses=tuple(stresses))
        )

    ordered = {
        word: tuple(sorted(variants, key=lambda p: p.variant_index))
        for word, variants in entries.items()
    }
    return Lexicon(
        source_path=str(path), sha256=sha256_file(path), vowels=vowels, _entries=ordered
    )


# --------------------------------------------------------------------------- #
# Syllabification
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Syllable:
    onset: tuple[str, ...]
    nucleus: str
    coda: tuple[str, ...]
    stress: str
    word: str

    @property
    def phones(self) -> tuple[str, ...]:
        return self.onset + (self.nucleus,) + self.coda

    def text(self) -> str:
        return " ".join(self.phones)


def syllabify(
    pronunciation: Pronunciation, lexicon: Lexicon, onsets: OnsetTable
) -> tuple[Syllable, ...]:
    """Deterministic Maximum Onset Principle against the fixed F5 table.

    Of the consonants between two vowels, the longest suffix that F5 lists as a
    legal onset opens the following syllable; the remainder closes the previous
    one.  A word-initial cluster F5 does not list is a hard error — F5 governs
    the boundary, so a gap in it cannot be papered over.
    """
    phones = pronunciation.phones
    vowel_positions = [i for i, p in enumerate(phones) if lexicon.is_vowel(p)]
    if not vowel_positions:
        raise ContractError(f"{pronunciation.word!r}: pronunciation has no vowel")

    initial = tuple(phones[: vowel_positions[0]])
    onsets.require_legal_onset(initial)

    syllable_onsets: list[tuple[str, ...]] = [initial]
    codas: list[tuple[str, ...]] = []
    for a, b in zip(vowel_positions, vowel_positions[1:]):
        between = tuple(phones[a + 1 : b])
        split = len(between)                       # maximum onset: try longest first
        while split > 0 and not onsets.is_legal_onset(between[len(between) - split :]):
            split -= 1
        codas.append(between[: len(between) - split])
        syllable_onsets.append(between[len(between) - split :])
    codas.append(tuple(phones[vowel_positions[-1] + 1 :]))

    stresses = pronunciation.stresses
    return tuple(
        Syllable(
            onset=syllable_onsets[i],
            nucleus=phones[vowel_positions[i]],
            coda=codas[i],
            stress=stresses[i] if i < len(stresses) else STRESS_UNSTRESSED,
            word=pronunciation.word,
        )
        for i in range(len(vowel_positions))
    )


def tokenize(line: str) -> tuple[str, ...]:
    """Deterministic word tokenisation.  No normalisation beyond case folding."""
    return tuple(w for w in _WORD_SPLIT_RE.split(line.lower().strip()) if w)


@dataclass(frozen=True)
class LineVariant:
    """One combination of per-word CMUdict variants for a whole line."""

    variant_index: int
    per_word_variant: tuple[int, ...]
    syllables: tuple[Syllable, ...]


def line_variants(
    line: str, lexicon: Lexicon, onsets: OnsetTable, max_variants: int = 64
) -> tuple[LineVariant, ...]:
    """Every pronunciation variant of a line, in a fixed lexicographic order.

    Section 9 says "evaluate all variants; report best-scoring; log winner".  The
    cap exists only so a pathological line cannot blow up combinatorially; it is
    applied in a deterministic order and the truncation is visible to the caller
    through the returned count.
    """
    words = tokenize(line)
    if not words:
        raise ContractError("empty candidate line")
    missing = tuple(w for w in words if w not in lexicon)
    if missing:
        raise KeyError(missing)                    # caller turns this into ABSTAIN_OOV

    combos: list[tuple[int, ...]] = [()]
    for word in words:
        variants = lexicon.variants(word)
        combos = [c + (v.variant_index,) for c in combos for v in variants]
        combos.sort()
        if len(combos) > max_variants:
            combos = combos[:max_variants]

    out: list[LineVariant] = []
    for n, combo in enumerate(combos):
        syllables: list[Syllable] = []
        for word, variant_index in zip(words, combo):
            pron = next(
                p for p in lexicon.variants(word) if p.variant_index == variant_index
            )
            syllables.extend(syllabify(pron, lexicon, onsets))
        out.append(LineVariant(variant_index=n, per_word_variant=combo,
                               syllables=tuple(syllables)))
    return tuple(out)
