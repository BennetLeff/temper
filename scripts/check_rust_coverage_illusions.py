#!/usr/bin/env python3
"""Coverage-illusion gate: a Rust module that SHARES A PYTHON MODULE'S NAME
is not a Rust module that IMPLEMENTS it.

Motivating incidents (2026-08-18, four in one day)
=====================================================
Four times in a single session, a Rust file existed with the right-looking
name while the live Python path ran somewhere else entirely. Every one was
mistaken for coverage that did not exist -- repeatedly, and including by the
agent coordinating the work:

1. ``packages/temper-rust-router-core/src/astar.rs::astar_kernel_3d`` is,
   despite the name, a **2D** 8-connected grid kernel; the ``_3d`` suffix is
   inherited from a retired JIT kernel. Its own sibling says so
   (``astar_nlayer.rs:4-7``). The N-layer path stayed Python until #1346, and
   ``router_v6/astar_core.py`` -- still live, called by
   ``_corridor_backbone.py:523`` for the ground-plane and power-island
   backbones -- calls no Rust at all.
2. ``packages/temper-orchestration/src/courtyard_check_stage.rs`` ports
   ``deterministic/stages/courtyard_check.py``. It does NOT port
   ``core/courtyard.py``, whose ``check_overlap`` and shapely ``Polygon``
   construction are live pure Python with three production importers.
3. ``packages/temper-design-bundle/src/hypergraph_factory.rs`` ports
   ``extraction/hypergraph_factory.py``. It does NOT port
   ``core/hypergraph.py``, whose dataclasses are live pure Python.
4. ``packages/temper-rust-router/src/net_ordering.rs`` serves the
   deterministic stages, while the live A* path orders through pure-Python
   ``router_v6/_astar_ordering.py`` -- which imports no Rust whatsoever.
   (Sharper still: ``route_stage.py:99`` assigns ``order_nets(...)`` to
   ``_lex_order`` and never reads it.)

Existing gates could not see any of this. ``check_unwired_kernels.py`` asks
"is this Rust symbol called by anything?" -- ``astar_kernel_3d_py``,
``run_courtyard_check``, the ``HypergraphFactory`` pyclass and ``order_nets_py``
are all called by *something*, so all four pass. ``check_orphaned_python_modules.py``
asks "is this Python module imported by anything?" -- all four Python modules
are, so all four pass. Neither gate asks the question that was actually being
got wrong, which is about the PAIRING.

What this gate checks
========================
For every Python module reachable from a production entry point:

    Does a Rust module actually implement it, or merely share its name?

"Implements" is decided by **call-path reachability**, never by filename. A
Rust file R implements Python module P only if P references, in code, at
least one Python-visible symbol that R registers. Sharing a name buys
nothing.

An **illusion** is reported when a production-reachable Python module P has
at least one Rust *namesake* -- a ``.rs`` file whose filename or registered
symbol names share a significant word with P's -- that P does not call. The
report names both sides, plus which Rust files P genuinely does call and
which Python modules the namesake genuinely does serve, because "who really
calls this" is the fact that was missing every one of the four times.

Note the direction of the check. It is deliberately keyed on the PYTHON
module, not on the Rust file, because the mistake being prevented is always
made while looking at Python and asking "is this already ported?".

Why name-similarity is scored at all, given it proves nothing
---------------------------------------------------------------
Name-similarity is not evidence of coverage; it is evidence of a *hazard*.
This gate uses it only to decide what is worth a human's attention, and then
answers the question from the call graph. A pair is flagged precisely when
the name says one thing and the call graph says another -- which is the only
situation in which anyone was ever misled.

Anti-vacuity
===============
A gate that passes on the code that motivated it is worth nothing. Two
structural defences, both of which fail the gate rather than warn:

* ``--self-test`` (and ``tests/scripts/test_rust_coverage_illusion_gate.py``)
  asserts that the four incidents above are present IN THE COMPUTED
  FINDINGS, keyed by the exact (python module, rust file) pairs, and that
  each is flagged for the right reason. This runs against the analysis, not
  against the ledger, so parking the four in the ledger -- the normal and
  expected disposition -- cannot silence the demonstration. If a future
  refactor genuinely resolves one of them, the self-test's expectation must
  be deleted deliberately, with the pairing named in the diff.
* Empty-denominator checks. Discovering zero entry points, zero
  production-reachable modules, zero registered Rust symbols, or zero
  namesake relations is always a bug in this scan, never a legitimate
  "nothing to check" -- so each is a hard failure. This repo's history is
  emphatic on the point: ``compile_fail`` doctests here passed with a wrong
  error code and with snippets that never touched the guard, and a
  file-based oracle registry was blind to 841 inline pins across 152 files.

Ledger
=========
``.rust-coverage-illusion-inventory``, tab-separated
``<python.module>\\t<rust file>[,<rust file>...]\\t<reason>``, shrink-only in
the same style as ``.unwired-kernel-inventory`` and
``.orphaned-python-module-inventory``:

* ``NEW_ILLUSION`` -- a pairing not in the ledger. Hard failure. Either the
  Python is genuinely uncovered (port it, or record why not), or the naming
  is misleading (rename it).
* ``STALE_ENTRY`` -- a ledgered pairing that no longer holds. Hard failure,
  so resolving one forces the ledger to shrink rather than silently
  accumulating dead triage.

Exit codes: 0 clean, 3 findings, 5 tool error.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import tomllib
from collections import deque
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INVENTORY = REPO_ROOT / ".rust-coverage-illusion-inventory"

EXIT_OK = 0
EXIT_FINDINGS = 3
EXIT_TOOL_ERROR = 5

# ---------------------------------------------------------------------------
# Rust registration parsing.
#
# Lifted deliberately from check_unwired_kernels.py rather than imported: that
# gate resolves a symbol -> file map for its own purposes and its regexes
# encode two hard-won corrections that must not be re-derived by hand here --
# registration is frequently PATH-QUALIFIED (`wrap_pyfunction!(fdm::solve_py, m)`,
# 113 of 572 on 2026-08-06), and `#[pyclass(name = "...")]` renames are
# declared in one module and registered from another, so renames resolve
# repo-wide rather than per file.
# ---------------------------------------------------------------------------
ADD_FUNCTION = re.compile(
    r"wrap_pyfunction!\(\s*(?:[A-Za-z_][A-Za-z0-9_]*\s*::\s*)*([A-Za-z_][A-Za-z0-9_]*)"
)
ADD_CLASS = re.compile(
    r"add_class::<\s*(?:[A-Za-z_][A-Za-z0-9_]*\s*::\s*)*([A-Za-z_][A-Za-z0-9_]*)"
)
PYCLASS_NAME = re.compile(r'#\[pyclass\([^)]*name\s*=\s*"([^"]+)"')
PYFUNCTION_NAME = re.compile(r'#\[pyfunction\([^)]*name\s*=\s*"([^"]+)"')
PYO3_NAME = re.compile(r'#\[pyo3\([^)]*name\s*=\s*"([^"]+)"')

# Tokens that carry no discriminating meaning in either language's naming
# conventions. Stripping them is what lets `astar.rs` be recognised as a
# namesake of `astar_core.py`, and `courtyard_check_stage.rs` of
# `core/courtyard.py`. They are NOT stripped from the "does P call R" test --
# that test never looks at names at all.
GENERIC_TOKENS = frozenset(
    {
        "py",
        "rs",
        "rust",
        "core",
        "base",
        "common",
        "util",
        "utils",
        "helper",
        "helpers",
        "lib",
        "main",
        "mod",
        "impl",
        "types",
        "type",
        "kernel",
        "kernels",
        "stage",
        "stages",
        "contracts",
        "contract",
        "v6",
        "v2",
        "2d",
        "3d",
        "temper",
        "data",
        "model",
        "models",
        "api",
        "run",
    }
)

# Rust files that register nothing Python-visible cannot be mistaken for
# coverage of a Python module, because nothing could ever call them.
# Excluded before namesake matching so they do not inflate the ledger.


def _rel(p: Path) -> str:
    return str(p.relative_to(REPO_ROOT))


def _tokens(name: str) -> frozenset[str]:
    """Significant lowercase word tokens of an identifier or file stem."""
    raw = re.split(r"[^A-Za-z0-9]+", re.sub(r"(?<!^)(?=[A-Z])", "_", name))
    return frozenset(t.lower() for t in raw if t and t.lower() not in GENERIC_TOKENS)


# ---------------------------------------------------------------------------
# Python source discovery and the production import graph
# ---------------------------------------------------------------------------


def _is_test_path(rel: str) -> bool:
    return (
        "/tests/" in rel
        or rel.startswith("tests/")
        or "/test_" in rel
        or "/_py_oracle" in rel
        or rel.endswith("_py_oracle.py")
        or "/conftest.py" in rel
        or rel.endswith("/conftest.py")
    )


def src_roots() -> list[Path]:
    return sorted(p for p in REPO_ROOT.glob("packages/*/src") if p.is_dir())


def module_map() -> dict[str, Path]:
    """Dotted module name -> file, for every non-test module under packages/*/src."""
    out: dict[str, Path] = {}
    for root in src_roots():
        for py in root.rglob("*.py"):
            rel = _rel(py)
            if "/target" in rel or "/.venv/" in rel or _is_test_path(rel):
                continue
            parts = list(py.relative_to(root).with_suffix("").parts)
            if parts[-1] == "__init__":
                parts.pop()
            if not parts:
                continue
            out.setdefault(".".join(parts), py)
    return out


def _resolve_relative(pkg_parts: list[str], level: int, module: str | None) -> str:
    base = pkg_parts[: len(pkg_parts) - (level - 1)] if level > 1 else pkg_parts
    return ".".join([*base, *(module.split(".") if module else [])])


def imports_of(path: Path, dotted: str) -> set[str]:
    """Dotted modules imported by one file, relative imports resolved."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return set()
    pkg_parts = dotted.split(".")
    if path.name != "__init__.py":
        pkg_parts = pkg_parts[:-1]
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            target = (
                _resolve_relative(pkg_parts, node.level, node.module)
                if node.level
                else (node.module or "")
            )
            if target:
                out.add(target)
                for a in node.names:
                    out.add(f"{target}.{a.name}")
    return out


def entry_points(modules: dict[str, Path]) -> tuple[set[str], list[str]]:
    """Production entry points, as dotted modules, plus a human-readable trace.

    Three sources, all of them things an operator can actually invoke:
      * ``[project.scripts]`` console-script targets in every pyproject.toml
      * every ``__main__`` module
      * every dotted module referenced by name from ``scripts/`` or ``tools/``
        (``make route`` runs ``scripts/route_board.py``, which is not itself
        an importable module, so its imports seed the graph)
    """
    eps: set[str] = set()
    trace: list[str] = []

    for pj in REPO_ROOT.glob("packages/*/pyproject.toml"):
        try:
            data = tomllib.loads(pj.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            continue
        for name, target in (data.get("project", {}).get("scripts", {}) or {}).items():
            mod = target.split(":", 1)[0]
            if mod in modules:
                eps.add(mod)
                trace.append(f"console-script {name} -> {mod}")

    for dotted in modules:
        if dotted.endswith("__main__"):
            eps.add(dotted)
            trace.append(f"__main__ module -> {dotted}")

    for base in ("scripts", "tools"):
        d = REPO_ROOT / base
        if not d.is_dir():
            continue
        for py in d.rglob("*.py"):
            rel = _rel(py)
            if _is_test_path(rel) or "/.venv/" in rel:
                continue
            for imp in imports_of(py, "__driver__"):
                cand = imp
                while cand:
                    if cand in modules:
                        if cand not in eps:
                            trace.append(f"{rel} imports -> {cand}")
                        eps.add(cand)
                        break
                    cand = cand.rpartition(".")[0]
    return eps, trace


def reachable_modules(modules: dict[str, Path]) -> tuple[set[str], list[str]]:
    """Breadth-first closure of the import graph from the production entry points."""
    eps, trace = entry_points(modules)
    seen: set[str] = set()
    queue: deque[str] = deque(eps)
    while queue:
        dotted = queue.popleft()
        if dotted in seen or dotted not in modules:
            continue
        seen.add(dotted)
        for imp in imports_of(modules[dotted], dotted):
            cand = imp
            while cand:
                if cand in modules and cand not in seen:
                    queue.append(cand)
                    break
                cand = cand.rpartition(".")[0]
    return seen, trace


# ---------------------------------------------------------------------------
# Rust side
# ---------------------------------------------------------------------------


RUST_DEF = re.compile(
    r"^\s*(?:pub(?:\s*\([^)]*\))?\s+)?(?:async\s+|unsafe\s+|extern\s+\"[^\"]*\"\s+)*"
    r"(?:fn|struct|enum)\s+([A-Za-z_][A-Za-z0-9_]*)",
    re.MULTILINE,
)


def rust_registrations() -> dict[str, set[str]]:
    """``.rs`` file (repo-relative) -> the Python-visible symbols it OWNS.

    "Owns" is not "registers", and the difference is the whole gate. Most
    crates centralise registration in ``lib.rs``: ``astar_kernel_3d_py`` and
    ``run_courtyard_check`` are both ``wrap_pyfunction!``'d from a ``lib.rs``
    while living in ``astar.rs`` and ``courtyard_check_stage.rs``. Attributing
    a symbol to its registration site collapses every crate onto its
    ``lib.rs``, which has no meaningful name to collide with -- so the two
    incidents that motivated this gate hardest would both go unreported.

    A symbol is therefore attributed to every file that:
      * registers it (the fallback, and correct when registration is local),
      * declares it (``pub fn <name>``), or
      * declares the kernel it wraps. This repo's pyo3 convention is
        ``<name>_py`` for the boundary and ``<name>`` for the implementation
        -- often in a different crate entirely
        (``astar_kernel_3d_py`` in ``temper-rust-router/src/lib.rs`` wraps
        ``astar_kernel_3d`` in ``temper-rust-router-core/src/astar.rs``).
        Following that one hop is what makes ``astar.rs`` visible as
        ``astar_core.py``'s namesake.
    """
    sources: list[tuple[str, str]] = []
    for rs in REPO_ROOT.glob("packages/*/src/**/*.rs"):
        rel = _rel(rs)
        if "/target" in rel:
            continue
        try:
            sources.append((rel, rs.read_text(encoding="utf-8")))
        except OSError:
            continue

    # Renames must resolve repo-wide: a `#[pyclass(name = "X")]` is routinely
    # declared in one module and registered from another (`PyDsnCircle` is
    # `DSNCircle` to Python but registered from lib.rs). A per-file map reports
    # the Rust name, which no Python caller ever writes.
    renames: dict[str, str] = {}
    declared_in: dict[str, set[str]] = {}
    for rel, text in sources:
        renames.update(_renames_in(text, PYCLASS_NAME, r"pub\s+struct\s+"))
        renames.update(_renames_in(text, PYFUNCTION_NAME, r"pub\s+fn\s+"))
        for m in RUST_DEF.finditer(text):
            declared_in.setdefault(m.group(1), set()).add(rel)

    out: dict[str, set[str]] = {}
    for rel, text in sources:
        for rx in (ADD_FUNCTION, ADD_CLASS):
            for m in rx.finditer(text):
                rust_name = m.group(1)
                py_name = renames.get(rust_name, rust_name)
                owners = {rel}
                owners |= declared_in.get(rust_name, set())
                if rust_name.endswith("_py"):
                    owners |= declared_in.get(rust_name[: -len("_py")], set())
                for owner in owners:
                    out.setdefault(owner, set()).add(py_name)
    return out


def _renames_in(text: str, attr_rx: re.Pattern[str], decl_rx: str) -> dict[str, str]:
    """Map Rust item name -> Python-visible name for ``name = "..."`` renames."""
    out: dict[str, str] = {}
    decl = re.compile(decl_rx + r"([A-Za-z_][A-Za-z0-9_]*)")
    for m in attr_rx.finditer(text):
        tail = text[m.end() : m.end() + 400]
        d = decl.search(tail)
        if d:
            out[d.group(1)] = m.group(1)
    return out


def code_identifiers(src: str) -> set[str]:
    """Names REFERENCED BY CODE, from the AST -- never from comments or prose.

    Text matching cannot tell a call from an explanation, and that is not
    hypothetical here: ``net_ordering.py``'s docstring names
    ``net_priority_key_py`` while explaining that nothing constructs a
    ``NetPriority`` any more, and a substring scan once read that explanation
    as proof of liveness (PR #839). Whole string literals count, because this
    repo dispatches through string tables; substrings never do.
    """
    tree = ast.parse(src)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.alias):
            names.add(node.name.rsplit(".", 1)[-1])
            if node.asname:
                names.add(node.asname)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            v = node.value.strip()
            if v:
                names.add(v)
                names.update(v.split("."))
    return names


# ---------------------------------------------------------------------------
# The analysis
# ---------------------------------------------------------------------------


# Severity, computed from the call graph and from how strongly each name
# overlaps -- NOT a confidence score about the naming itself.
#
#   NO_RUST        the module calls no Rust at all, yet Rust exists whose
#                  name overlaps its own. This is the exact shape of the
#                  astar_core.py and _astar_ordering.py incidents: someone
#                  reads the Rust filename, concludes "ported", and the
#                  Python keeps running.
#   NAMESAKE_MISS  the module does call Rust, but an UNCALLED namesake
#                  overlaps its name at least as strongly as anything it
#                  does call. The core/courtyard.py and core/hypergraph.py
#                  incidents: real Rust adjacency, wrong Rust file.
#   INCIDENTAL     the module calls a strictly better-matching Rust file
#                  than the uncalled namesake. `channel_skeleton.py` is
#                  served by `channel_skeleton.rs` and merely shares the
#                  word "channel" with `channel_widths.rs`. Reported for
#                  completeness, NOT ledgered and NOT failed on -- ledgering
#                  it would bury the two classes above in shared-word noise.
SEV_NO_RUST = "NO_RUST"
SEV_NAMESAKE_MISS = "NAMESAKE_MISS"
SEV_INCIDENTAL = "INCIDENTAL"
LEDGERED_SEVERITIES = (SEV_NO_RUST, SEV_NAMESAKE_MISS)


class Finding:
    __slots__ = ("module", "path", "namesakes", "called", "servers", "severity")

    def __init__(
        self,
        module: str,
        path: str,
        namesakes: list[str],
        called: list[str],
        servers: dict[str, list[str]],
        severity: str,
    ) -> None:
        self.module = module
        self.path = path
        self.namesakes = namesakes
        self.called = called
        self.servers = servers
        self.severity = severity

    @property
    def key(self) -> str:
        return self.module

    @property
    def rust_field(self) -> str:
        return ",".join(self.namesakes)


def analyse() -> tuple[list[Finding], dict[str, object]]:
    modules = module_map()
    if not modules:
        raise SystemExit("no production Python modules discovered -- scan is broken")

    reachable, ep_trace = reachable_modules(modules)
    registrations = rust_registrations()

    stats: dict[str, object] = {
        "python_modules": len(modules),
        "reachable_modules": len(reachable),
        "rust_files_registering_symbols": len(registrations),
        "rust_symbols": sum(len(v) for v in registrations.values()),
        "entry_point_trace_len": len(ep_trace),
    }

    # Empty denominators are always a bug in this scan, never "nothing to
    # check". Each is fatal rather than a warning.
    if not reachable:
        raise SystemExit("zero production-reachable Python modules -- scan is broken")
    if not registrations:
        raise SystemExit("zero Rust files register Python symbols -- scan is broken")

    sym_to_files: dict[str, set[str]] = {}
    for rel, syms in registrations.items():
        for s in syms:
            sym_to_files.setdefault(s, set()).add(rel)

    # Which Rust files does each production-reachable Python module actually
    # call? This is the whole answer; names play no part in it.
    calls: dict[str, set[str]] = {}
    for dotted in sorted(reachable):
        try:
            ids = code_identifiers(modules[dotted].read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            ids = set()
        hit: set[str] = set()
        for s in ids & sym_to_files.keys():
            hit |= sym_to_files[s]
        calls[dotted] = hit

    # Each Rust file's name-token set, from its FILE STEM ONLY.
    #
    # Registered-symbol names were tried here as well and removed: with
    # ownership now resolved through `pub fn` definitions, the stem already
    # carries the whole signal (`astar.rs` -> {astar}, enough to match
    # `astar_core.py`), while symbol tokens made every crate's `lib.rs` a
    # namesake of nearly every Python module -- `lib` is generic, so its stem
    # contributes nothing, but the hundreds of symbols it registers
    # contributed everything. That inflated the ledger from 243 rows to a
    # wall of `lib.rs` noise in which the four real incidents were
    # indistinguishable, which is the failure mode this gate exists to
    # prevent rather than reproduce.
    #
    # A Rust file whose stem is entirely generic (`lib`, `mod`, `types`)
    # therefore has no name to be mistaken for anyone's, and is not matched.
    rust_tokens: dict[str, frozenset[str]] = {}
    for rel in registrations:
        toks = _tokens(Path(rel).stem)
        if toks:
            rust_tokens[rel] = toks

    namesake_relations = 0
    findings: list[Finding] = []
    for dotted in sorted(reachable):
        py_toks = _tokens(Path(modules[dotted].name).stem)
        if not py_toks:
            continue
        namesakes = sorted(
            rel for rel, toks in rust_tokens.items() if py_toks & toks
        )
        namesake_relations += len(namesakes)
        uncalled = [r for r in namesakes if r not in calls[dotted]]
        if not uncalled:
            continue

        # How strongly does the best Rust file this module ACTUALLY calls
        # overlap its name? Anything uncalled that matches at least as well
        # is a namesake the call graph contradicts; anything that matches
        # less well is a shared word.
        best_called = max(
            (len(py_toks & rust_tokens[r]) for r in calls[dotted] if r in rust_tokens),
            default=0,
        )
        strong = [r for r in uncalled if len(py_toks & rust_tokens[r]) >= best_called]

        if not calls[dotted]:
            severity, reported = SEV_NO_RUST, uncalled
        elif strong:
            severity, reported = SEV_NAMESAKE_MISS, strong
        else:
            severity, reported = SEV_INCIDENTAL, uncalled

        servers = {
            r: sorted(m for m in reachable if r in calls[m]) for r in reported
        }
        findings.append(
            Finding(
                dotted,
                _rel(modules[dotted]),
                reported,
                sorted(calls[dotted]),
                servers,
                severity,
            )
        )

    stats["namesake_relations"] = namesake_relations
    if namesake_relations == 0:
        raise SystemExit(
            "zero namesake relations found -- tokenisation is broken, and the "
            "gate would pass vacuously"
        )
    return findings, stats


# ---------------------------------------------------------------------------
# Anti-vacuity self-test
# ---------------------------------------------------------------------------

# The four 2026-08-18 incidents, as (python module, rust file) pairs. These
# are the cases that motivated the gate; a gate that does not flag them is
# worth nothing. Kept here rather than only in a test so `--self-test` is
# runnable in CI alongside the gate itself.
KNOWN_INCIDENTS: tuple[tuple[str, str, str], ...] = (
    (
        "temper_placer.router_v6.astar_core",
        "packages/temper-rust-router-core/src/astar.rs",
        "astar_kernel_3d is a 2D kernel; astar_core.py's _astar_search is live "
        "pure Python called from _corridor_backbone.py:523",
    ),
    (
        "temper_placer.core.courtyard",
        "packages/temper-orchestration/src/courtyard_check_stage.rs",
        "courtyard_check_stage.rs ports deterministic/stages/courtyard_check.py, "
        "not core/courtyard.py",
    ),
    (
        "temper_placer.core.hypergraph",
        "packages/temper-design-bundle/src/hypergraph_factory.rs",
        "hypergraph_factory.rs ports extraction/hypergraph_factory.py, "
        "not core/hypergraph.py",
    ),
    (
        "temper_placer.router_v6._astar_ordering",
        "packages/temper-rust-router/src/net_ordering.rs",
        "net_ordering.rs serves the deterministic stages; the live A* path "
        "orders through pure-Python _astar_ordering.py",
    ),
)


def self_test(findings: list[Finding]) -> list[str]:
    """Assert the four motivating incidents are IN THE FINDINGS.

    Runs against the analysis, never against the ledger, so the normal and
    expected disposition -- parking all four in the ledger -- cannot silence
    the demonstration that the gate sees them.
    """
    by_module = {f.module: f for f in findings}
    problems: list[str] = []
    for module, rust_file, why in KNOWN_INCIDENTS:
        f = by_module.get(module)
        if f is None:
            problems.append(
                f"SELF-TEST FAILED: {module} is not reported at all "
                f"(expected: {why})"
            )
            continue
        if rust_file not in f.namesakes:
            problems.append(
                f"SELF-TEST FAILED: {module} is reported, but not against "
                f"{rust_file} (got {f.namesakes}) (expected: {why})"
            )
    return problems


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------


def load_inventory() -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    if not INVENTORY.exists():
        return out
    for line in INVENTORY.read_text(encoding="utf-8").splitlines():
        line = line.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        out[parts[0]] = (parts[1], parts[2])
    return out


def write_inventory(findings: list[Finding], previous: dict[str, tuple[str, str]]) -> None:
    lines = [
        "# Rust-coverage-illusion ledger -- see scripts/check_rust_coverage_illusions.py",
        "#",
        "# Each row is a production-reachable Python module that has a Rust",
        "# NAMESAKE it does not call. The namesake does not implement it; the",
        "# names merely overlap. Rows are triage, not permission: the correct",
        "# resolutions are to port the Python, or to rename the Rust so it stops",
        "# implying coverage it does not provide.",
        "#",
        "# Shrink-only. A new row fails CI (NEW_ILLUSION); a row that no longer",
        "# holds also fails (STALE_ENTRY), so resolving one forces this file to",
        "# shrink instead of accumulating dead triage.",
        "#",
        "# <python.module>\t<rust file>[,<rust file>...]\t<reason>",
    ]
    for f in sorted(findings, key=lambda x: x.key):
        if f.severity not in LEDGERED_SEVERITIES:
            continue
        reason = (
            previous.get(f.key, ("", ""))[1]
            or f"{f.severity}: recorded at gate introduction; not triaged"
        )
        lines.append(f"{f.key}\t{f.rust_field}\t{reason}")
    INVENTORY.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write-inventory", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--show", metavar="MODULE", help="explain one module's finding")
    args = ap.parse_args()

    try:
        findings, stats = analyse()
    except SystemExit as exc:
        print(f"TOOL ERROR: {exc}", file=sys.stderr)
        return EXIT_TOOL_ERROR

    if args.json:
        print(
            json.dumps(
                {
                    "stats": stats,
                    "findings": [
                        {
                            "module": f.module,
                            "path": f.path,
                            "severity": f.severity,
                            "uncalled_namesakes": f.namesakes,
                            "rust_actually_called": f.called,
                            "namesake_real_servers": f.servers,
                        }
                        for f in findings
                    ],
                },
                indent=2,
            )
        )
        return EXIT_OK

    if args.show:
        for f in findings:
            if f.module == args.show:
                print(f"{f.module}  ({f.path})  [{f.severity}]")
                print(f"  Rust it ACTUALLY calls : {f.called or '(none)'}")
                for r in f.namesakes:
                    print(f"  namesake NOT called    : {r}")
                    print(f"      really serves      : {f.servers[r] or '(nothing reachable)'}")
                return EXIT_OK
        print(f"{args.show}: no finding")
        return EXIT_OK

    problems = self_test(findings)
    if args.self_test:
        print(
            f"Coverage-illusion gate self-test: {len(KNOWN_INCIDENTS)} known "
            f"incidents checked against {len(findings)} findings."
        )
        for p in problems:
            print(f"  {p}")
        if problems:
            return EXIT_FINDINGS
        for module, rust_file, why in KNOWN_INCIDENTS:
            print(f"  [FLAGGED] {module}  vs  {rust_file}")
            print(f"            {why}")
        print("SELF-TEST PASSED -- the gate flags every case that motivated it.")
        return EXIT_OK

    previous = load_inventory()

    if args.write_inventory:
        write_inventory(findings, previous)
        n = sum(1 for f in findings if f.severity in LEDGERED_SEVERITIES)
        print(
            f"wrote {INVENTORY.name}: {n} entries "
            f"({len(findings) - n} incidental overlaps omitted)"
        )
        return EXIT_OK

    print(
        f"Coverage-illusion gate -- {stats['reachable_modules']} of "
        f"{stats['python_modules']} production Python modules reachable from an "
        f"entry point; {stats['rust_symbols']} Python-visible symbols across "
        f"{stats['rust_files_registering_symbols']} .rs files; "
        f"{stats['namesake_relations']} namesake relations examined."
    )

    if problems:
        # The gate's own demonstration is broken -- report before anything
        # else, because every other verdict below is now untrustworthy.
        for p in problems:
            print(f"  {p}")
        print(
            "FAILED -- the gate no longer flags the cases it was built for. "
            "Fix the gate before trusting the ledger."
        )
        return EXIT_FINDINGS

    ledgered = [f for f in findings if f.severity in LEDGERED_SEVERITIES]
    incidental = [f for f in findings if f.severity == SEV_INCIDENTAL]
    by_sev = {s_: sum(1 for f in findings if f.severity == s_) for s_ in
              (SEV_NO_RUST, SEV_NAMESAKE_MISS, SEV_INCIDENTAL)}
    print(
        f"  {by_sev[SEV_NO_RUST]} NO_RUST, {by_sev[SEV_NAMESAKE_MISS]} "
        f"NAMESAKE_MISS (both ledgered); {by_sev[SEV_INCIDENTAL]} INCIDENTAL "
        f"(shared word only, not ledgered)."
    )
    current = {f.key: f for f in ledgered}
    new = sorted(set(current) - set(previous))
    stale = sorted(set(previous) - set(current))

    for key in new:
        f = current[key]
        print(f"  NEW_ILLUSION [{f.severity}]  {key}  ({f.path})")
        print(f"      Rust it actually calls: {', '.join(f.called) or '(none)'}")
        for r in f.namesakes:
            served = ", ".join(f.servers[r]) or "(nothing reachable)"
            print(f"      namesake not called   : {r}")
            print(f"          really serves     : {served}")
    for key in stale:
        print(f"  STALE_ENTRY   {key} -- no longer an illusion; remove the row")

    if new or stale:
        print(
            f"FAILED -- {len(new)} new, {len(stale)} stale. A Rust file sharing "
            f"a Python module's name is not coverage: either port the Python, "
            f"or rename the Rust."
        )
        return EXIT_FINDINGS

    print(
        f"PASSED -- {len(ledgered)} known illusions, all ledgered; none new, "
        f"none stale ({len(incidental)} incidental name overlaps not ledgered)."
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
