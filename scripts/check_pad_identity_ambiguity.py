#!/usr/bin/env python3
"""Fail closed when a duplicate-pad-number footprint meets an unsafe
``(ref, pin)``-only consumer.

**Why this exists, and how it differs from
``check_net_pin_identity_pad_correspondence.py``.** That gate (PR #1177)
is a NET-accounting invariant: it flags a net whose entire
``(component_ref, pad_number)`` pin-identity view collapses to <=1
distinct tuple while its real physical pad count is >1 -- the shape that
made ``discharge.k_dis1-no``/``discharge.k_dis2-no`` look like trivial,
nothing-to-connect nets. It does NOT, by design, catch a net that has
*other*, genuinely distinct pins alongside a duplicated one: K2/K3's pad
``"1"`` (``PWR_RTN``/``DC_BUS_RTN``) and pad ``"4"``
(``discharge.k_dis1-nc``/``k_dis2-nc``) never collapse to a single tuple
for the whole net (other components' pins keep the distinct-tuple count
above 1), so that gate is silent for them even though a first-match
consumer would still mis-resolve K2/K3's own duplicated pad within that
net. See ``docs/evidence/2026-08-13-pad-identity-ssot.md`` for the full
duplicate-pad-number survey this gate's board-side half is built from.

**This gate is COMPONENT-level, not net-level.** It asks a structurally
different, more general question: does any footprint IN USE on the board
declare more than one physical pad under the same pad number/name (a
manufacturer current-sharing contact, a ganged mechanical/NPTH hole, or
anything a future footprint change adds), and if so, does any production
code still resolve "the" pin for that footprint via a bare
``(ref, pin_name)`` lookup that assumes uniqueness -- ``Component.get_pin``
(the pyo3 first-match method), called directly outside the reviewed,
occurrence-safe wrappers in ``temper_placer.core.pad_identity``? Both
halves are real and independent; only their CONJUNCTION is a defect:
either half alone is fine (a duplicate-pad footprint with no unsafe
consumer is harmless; an unsafe-shaped consumer with no duplicate-pad
footprint in play never actually collapses two pads).

**Self-contained by design** (same posture as
``check_net_pin_identity_pad_correspondence.py``): the board half reads
``pcb/temper.kicad_pcb`` directly with its own paren-balanced regex
extraction, deliberately NOT importing ``temper_placer`` (no compiled
extension needed). The code half is a plain ``ast`` walk over
``packages/*/src/**/*.py`` -- no import of the scanned modules either, so
this gate cannot be defeated by an import-time failure in the code it is
checking.

**What counts as "keys on (ref, pin) alone".** A direct
``<expr>.get_pin(...)`` method-call AST node in production source
(``packages/*/src/**/*.py``, excluding ``tests/`` and
``docs/evidence/``). This is deliberately a narrower, syntactic signal
than "any first-match pin resolution shape" -- a bare inline
``for pin in comp.pins: if pin.name == x or pin.number == x: ...``
scan (the shape ``router_v6/congestion.py`` and
``router_v6/bottleneck_geometry.py`` both had before this task) is NOT
caught by this gate; nothing currently in the tree needs it caught
because every known instance of that shape was migrated onto
``temper_placer.core.pad_identity`` in the same change that added this
gate, but this is a real, stated enforcement gap, not a silent one -- see
the module docstring of ``temper_placer.core.pad_identity`` for the
full call-site audit and the "Left unenforced" note in
``docs/evidence/2026-08-13-pad-identity-ssot.md``.

**Allowlist.** ``ALLOWED_GET_PIN_CALL_SITES`` names every reviewed
``.get_pin(`` call site that is safe DESPITE a duplicate-pad-number
footprint being in play, with the reasoning inline. Today that is exactly
one: ``core/loop_extractor.py``'s ``get_pin_net``, which only needs pin
EXISTENCE and NET membership -- every physical pad sharing a pad number is,
by construction, wired to the same net (that is what "duplicate contact
pad for current sharing" means), so which physical occurrence answers the
question is irrelevant. Any OTHER ``.get_pin(`` call site is NOT
pre-approved and fails this gate until reviewed and either fixed (use
``temper_placer.core.pad_identity``) or added here with a reason.

Fail-closed contract, matching this repo's other board-reading gates:
never exits 0 unless it positively confirms it ran a real check on real,
non-empty data.

Exit codes:
  0 - PASSED: either no footprint in use has a duplicate pad number, or
      every ``.get_pin(`` call site in production source is on the
      reviewed allowlist
  3 - VIOLATION: a duplicate-pad-number footprint is in use AND an
      unreviewed ``.get_pin(`` call site exists in production source
  5 - GATE ERROR: the board is missing/unreadable, has zero footprints,
      or the source scan found zero ``.py`` files (a real check did not run)

Usage:
  uv run python scripts/check_pad_identity_ambiguity.py
  uv run python scripts/check_pad_identity_ambiguity.py --board PATH --packages-root PATH
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.github_summary import get_github_summary_path
from _lib.repo import find_repo_root

REPO_ROOT = find_repo_root()
DEFAULT_BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"
DEFAULT_PACKAGES_ROOT = REPO_ROOT / "packages"

EXIT_OK = 0
EXIT_VIOLATION = 3
EXIT_GATE_ERROR = 5

# Hand-curated, human-reasoned suppressions -- NOT a way to silence this
# gate, a record of call sites where a bare `Component.get_pin(...)` is
# verified safe despite a duplicate-pad-number footprint being in play.
# Keyed on (path relative to `packages/`, enclosing function name) rather
# than line number, so the allowlist survives unrelated line churn in the
# file -- a real code change (renaming the function, or moving the call to
# a different function) correctly falls off the allowlist and must be
# re-reviewed.
#
# core/loop_extractor.py::get_pin_net: tries several candidate pin NAMES
# (e.g. ["DRAIN", "D"]) and returns the first match's NET, never a
# position. Safe unconditionally: every physical pad sharing a pad
# number/name is wired to the same net by construction (that is what a
# manufacturer-duplicated current-sharing contact IS), so it is impossible
# for two occurrences of one pad number to disagree on which net they
# belong to. Audited 2026-08-13 against K1/K2/K3 (this board's only
# duplicate-pad-number footprints): confirmed on the real board -- every
# K2/K3 duplicate pad pair (numbers "1", "3", "4") carries one net per
# pair, and K1's duplicated "" pads are unconnected NPTH holes with no net
# at all, so `pin.net` is falsy and the loop simply continues.
ALLOWED_GET_PIN_CALL_SITES: frozenset[tuple[str, str]] = frozenset(
    {
        ("temper_placer/core/loop_extractor.py", "get_pin_net"),
    }
)

# Directories under `packages/*/src/temper_*/` (or the crate-relative
# equivalent) never scanned for the code half: generated/vendored, tests,
# and this repo's frozen-evidence convention (docs/evidence/ scripts are
# historical analysis, not maintained code -- see AGENTS.md's "make regen"
# section).
_SKIP_DIR_PARTS = {"tests", "target", "target-shared", ".venv", "node_modules", "docs"}


class GateError(Exception):
    """Raised for any condition that must fail closed (exit 5)."""


# ---------------------------------------------------------------------------
# Board half: which footprints IN USE have a duplicate pad number.
# Self-contained raw-text extraction, same technique as
# check_net_pin_identity_pad_correspondence.py / net_batching.py.
# ---------------------------------------------------------------------------

_FOOTPRINT_START_RE = re.compile(r'\n\s*\(footprint\s+"')
_REFERENCE_RE = re.compile(r'\(property\s+"Reference"\s+"([^"]*)"\)')
_PAD_START_RE = re.compile(r'\(pad\s+"([^"]*)"')


def _extract_footprint_blocks(content: str) -> list[str]:
    """Paren-balanced extraction of every top-level ``(footprint ...)``
    block (split on footprint-start markers, each slice runs to the next
    one -- identical technique to the sibling gate)."""
    starts = [m.start() for m in _FOOTPRINT_START_RE.finditer(content)]
    starts.append(len(content))
    return [content[starts[i] : starts[i + 1]] for i in range(len(starts) - 1)]


def _pad_numbers(footprint_block: str) -> list[str]:
    """Every ``(pad "N" ...)`` occurrence's pad number, in file order --
    ALL of them, connected or not (an NPTH mechanical pad has no ``(net
    ...)`` clause but still occupies a pad-number slot, e.g. K1's four
    ``""``-numbered mounting holes)."""
    return [m.group(1) for m in _PAD_START_RE.finditer(footprint_block)]


@dataclass(frozen=True)
class DuplicatePadFootprint:
    ref: str
    footprint: str
    duplicate_pad_numbers: dict[str, int]


def find_duplicate_pad_footprints(board_path: Path) -> list[DuplicatePadFootprint]:
    """Every footprint instance on *board_path* that declares more than
    one physical pad under the same pad number/name."""
    if not board_path.exists():
        raise GateError(f"board not found: {board_path}")
    try:
        content = board_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise GateError(f"failed to read board {board_path}: {exc}") from exc

    blocks = _extract_footprint_blocks(content)
    if not blocks:
        raise GateError(f"board {board_path} has zero footprints -- gate did not run a real check")

    out: list[DuplicatePadFootprint] = []
    for block in blocks:
        ref_m = _REFERENCE_RE.search(block)
        fp_m = re.match(r'\(footprint\s+"([^"]+)"', block.lstrip())
        if not ref_m or not fp_m:
            continue
        ref = ref_m.group(1)
        footprint = fp_m.group(1)
        counts: dict[str, int] = defaultdict(int)
        for number in _pad_numbers(block):
            counts[number] += 1
        dups = {number: count for number, count in counts.items() if count > 1}
        if dups:
            out.append(DuplicatePadFootprint(ref=ref, footprint=footprint, duplicate_pad_numbers=dups))
    return out


# ---------------------------------------------------------------------------
# Code half: every `.get_pin(...)` call site in production source.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GetPinCallSite:
    relpath: str  # relative to `packages/`
    lineno: int
    function: str  # enclosing function/method name, or "<module>"


def _iter_production_py_files(packages_root: Path) -> list[Path]:
    out: list[Path] = []
    for path in packages_root.glob("**/src/**/*.py"):
        parts = set(path.parts)
        if parts & _SKIP_DIR_PARTS:
            continue
        out.append(path)
    return out


def _enclosing_function_name(tree: ast.AST, call_node: ast.Call) -> str:
    """Name of the nearest enclosing FunctionDef/AsyncFunctionDef around
    *call_node*, or ``"<module>"`` if the call is at module scope."""
    best: str = "<module>"
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                if child is call_node:
                    best = node.name
    return best


def _src_relative_path(path_under_packages: Path) -> str:
    """Drop the ``<crate-dir>/src/`` (or ``<crate-dir>/src/<pkg>-<version>/``)
    prefix from a path relative to ``packages/``, so the allowlist key is
    stable under a crate being renamed/relocated and matches the form a
    reviewer actually reads in a traceback
    (``temper_placer/core/loop_extractor.py``, not
    ``temper-placer/src/temper_placer/core/loop_extractor.py``)."""
    parts = path_under_packages.parts
    if "src" in parts:
        idx = parts.index("src")
        return str(Path(*parts[idx + 1 :]))
    return str(path_under_packages)


def find_get_pin_call_sites(packages_root: Path) -> list[GetPinCallSite]:
    """Every direct ``<expr>.get_pin(...)`` call in production source
    under *packages_root*."""
    files = _iter_production_py_files(packages_root)
    if not files:
        raise GateError(f"found zero .py files under {packages_root} -- gate did not run a real check")

    sites: list[GetPinCallSite] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError:
            continue
        relpath = _src_relative_path(path.relative_to(packages_root))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "get_pin"
            ):
                sites.append(
                    GetPinCallSite(
                        relpath=relpath,
                        lineno=node.lineno,
                        function=_enclosing_function_name(tree, node),
                    )
                )
    return sites


def unreviewed_get_pin_call_sites(
    sites: list[GetPinCallSite],
    allowlist: frozenset[tuple[str, str]] = ALLOWED_GET_PIN_CALL_SITES,
) -> list[GetPinCallSite]:
    return [s for s in sites if (s.relpath, s.function) not in allowlist]


# ---------------------------------------------------------------------------


def run(board_path: Path, packages_root: Path) -> int:
    try:
        duplicate_footprints = find_duplicate_pad_footprints(board_path)
        call_sites = find_get_pin_call_sites(packages_root)
    except GateError as exc:
        print(f"GATE ERROR: {exc}", file=sys.stderr)
        return EXIT_GATE_ERROR

    unreviewed = unreviewed_get_pin_call_sites(call_sites)
    allowed = [s for s in call_sites if s not in unreviewed]

    print(f"Board: {board_path}")
    print(f"Footprints with a duplicate pad number: {len(duplicate_footprints)}")
    for fp in duplicate_footprints:
        dup_str = ", ".join(f'"{n}"x{c}' for n, c in sorted(fp.duplicate_pad_numbers.items()))
        print(f"  {fp.ref} ({fp.footprint}): {dup_str}")

    print(f"\n.get_pin( call sites in production source: {len(call_sites)}")
    if allowed:
        print(f"  reviewed, allowlisted ({len(allowed)}):")
        for s in allowed:
            print(f"    {s.relpath}:{s.lineno} in {s.function}()")
    if unreviewed:
        print(f"  UNREVIEWED ({len(unreviewed)}):")
        for s in unreviewed:
            print(f"    {s.relpath}:{s.lineno} in {s.function}()")

    gh = get_github_summary_path()

    if not duplicate_footprints or not unreviewed:
        reason = (
            "no footprint in use has a duplicate pad number"
            if not duplicate_footprints
            else "every .get_pin( call site is reviewed and allowlisted"
        )
        print(f"\nPASSED -- {reason}.")
        if gh:
            with open(gh, "a") as f:
                f.write("### Pad-Identity Ambiguity Gate -- PASSED\n")
                f.write(f"{reason}.\n")
        return EXIT_OK

    print(
        f"\nFAILED -- {len(duplicate_footprints)} duplicate-pad-number footprint(s) "
        f"in use AND {len(unreviewed)} unreviewed .get_pin( call site(s): a caller "
        "asking for \"pad 3\" on a component with two of them can silently get "
        "either one. Fix the call site to use temper_placer.core.pad_identity "
        "(nth_matching_pin / get_unique_pin / resolve_net_pins), or -- only if "
        "verified safe, e.g. the call only needs pin existence/net-membership, "
        "never position -- add it to ALLOWED_GET_PIN_CALL_SITES with a reason."
    )
    if gh:
        with open(gh, "a") as f:
            f.write("### Pad-Identity Ambiguity Gate -- FAILED\n")
            f.write(
                f"{len(duplicate_footprints)} duplicate-pad-number footprint(s) AND "
                f"{len(unreviewed)} unreviewed `.get_pin(` call site(s).\n\n"
            )
            for s in unreviewed:
                f.write(f"- `{s.relpath}:{s.lineno}` in `{s.function}()`\n")
    return EXIT_VIOLATION


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--board", type=Path, default=DEFAULT_BOARD)
    parser.add_argument("--packages-root", type=Path, default=DEFAULT_PACKAGES_ROOT)
    args = parser.parse_args()
    sys.exit(run(args.board, args.packages_root))


if __name__ == "__main__":
    main()
