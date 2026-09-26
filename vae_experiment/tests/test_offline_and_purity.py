"""Section 24: offline only, no network calls anywhere; no RNG, wall-clock or state."""

from __future__ import annotations

import ast
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent.parent / "vae"

NETWORK_MODULES = {
    "socket", "ssl", "urllib", "urllib2", "urllib3", "http", "httplib", "requests",
    "ftplib", "telnetlib", "smtplib", "asyncio", "aiohttp", "xmlrpc", "webbrowser",
}
NONDETERMINISM_MODULES = {"random", "secrets", "uuid"}
WALL_CLOCK_MODULES = {"time", "datetime", "calendar"}
FORBIDDEN_CALLS = {"getrandbits", "randint", "shuffle", "sample", "monotonic", "perf_counter"}

# Section 19 DO NOT BUILD, as importable-name evidence.
DO_NOT_BUILD_HINTS = {
    "torch", "tensorflow", "keras", "sklearn", "librosa", "madmom", "essentia",
    "demucs", "spleeter", "crepe", "pyin", "transformers", "openai", "anthropic",
}


def _module_sources():
    return sorted(PACKAGE.glob("*.py"))


def _imported_roots(tree: ast.AST) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def test_no_network_capable_imports_anywhere_in_the_package():
    for source in _module_sources():
        roots = _imported_roots(ast.parse(source.read_text()))
        offending = roots & NETWORK_MODULES
        assert not offending, f"{source.name} imports {sorted(offending)}"


def test_no_rng_and_no_wall_clock_in_the_package():
    for source in _module_sources():
        roots = _imported_roots(ast.parse(source.read_text()))
        assert not roots & NONDETERMINISM_MODULES, f"{source.name} imports an RNG"
        assert not roots & WALL_CLOCK_MODULES, f"{source.name} imports a clock"


def test_no_forbidden_nondeterministic_calls():
    for source in _module_sources():
        for node in ast.walk(ast.parse(source.read_text())):
            if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_CALLS:
                raise AssertionError(f"{source.name}:{node.lineno} calls {node.attr}")


def test_nothing_on_the_section_19_do_not_build_list_is_imported():
    for source in _module_sources():
        roots = _imported_roots(ast.parse(source.read_text()))
        offending = roots & DO_NOT_BUILD_HINTS
        assert not offending, f"{source.name} imports {sorted(offending)} (Section 19)"


def test_no_module_level_mutable_state():
    """Section 21: no shared mutable state, no globals, no history."""
    allowed = {"tables", "lexicon"}         # frozen dataclass instances only
    for source in _module_sources():
        tree = ast.parse(source.read_text())
        for node in tree.body:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if not isinstance(target, ast.Name):
                    continue
                value = node.value
                if isinstance(value, (ast.List, ast.Dict, ast.Set)):
                    assert source.stem in allowed, (
                        f"{source.name}:{node.lineno} defines mutable module state "
                        f"{target.id}"
                    )
