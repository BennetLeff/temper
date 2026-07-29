#!/usr/bin/env python3
"""Footprint-drift gate: catch a corrected footprint that never reached the board.

Motivation (docs/hardware/2026-07-29-open-safety-gate-actions.md; PR #448):
this project has now hit the SAME defect class three confirmed times. A
component's footprint is corrected in the design source
(``elec/src/*.ato``, surfacing as a new ``footprint`` field in the compiled
netlist) and the change is never propagated into ``pcb/temper.kicad_pcb``.
The board silently keeps the OLD land pattern -- nothing in CI notices,
because every other board/netlist gate in this repo (``check_domain_
partition.py``, ``check_copper_net_consistency.py``) reads NET identity
(which pin belongs to which electrical net), never the FOOTPRINT string
itself. A pad-for-pad-compatible footprint substitution with a smaller
land pattern is completely invisible to those checks: the pad numbers and
net assignments are identical, only creepage/clearance geometry changes.
On a mains-connected 1.8kW induction heater, that geometry IS the safety
margin (REQ-SAFE-01 reinforced creepage, MIN_BARRIER_WIDTH_MM in
``check_isolation_keepout.py``) -- so this is a safety gate, not
bookkeeping.

Confirmed instances (see the evidence doc and PR #448 for detail):
  - C6  (power_in.y_cap_pe): .ato corrected to a 10mm-pitch Y1 disc
    (Capacitor_THT:C_Disc_D12.5mm_W5.0mm_P10.00mm); board still has the
    5mm-pitch stub (Capacitor_THT:C_Disc_D10.0mm_W5.0mm_P5.00mm).
  - U3  (power_in.zcd_opto): .ato corrected to the wide-lead-form DIP-6
    (Package_DIP:DIP-6_W10.16mm, docs/evidence/
    2026-07-28-tank-cap-and-isolator-footprints.md); board still has the
    narrow DIP-6 (Package_DIP:DIP-6_W7.62mm) -- 6.020mm HV<->SELV pad
    separation against the 8.0mm REQ-SAFE-01 minimum.
  - c_x2 (power_in.c_x2, ref C1): PR #448 corrects the X2 mains cap to a
    15mm-pitch MKP box (Capacitor_THT:C_Rect_L18.0mm_W7.0mm_P15.00mm_
    FKS3_FKP3); until that PR merges, C1 will not appear here (source and
    board still agree on the old disc footprint) -- this gate reports
    what is actually inconsistent RIGHT NOW, not what a pending PR will
    make inconsistent once it lands. The moment that PR merges without a
    board resync, this gate starts reporting C1 for exactly this reason,
    with no further changes required here.

Comparison surface: the compiled netlist (``elec/build/default.net``, the
same source of truth ``check_copper_net_consistency.py`` and ``check_
domain_partition.py`` already use) against ``pcb/temper.kicad_pcb`` read
directly via kiutils -- NOT ``elec/src/*.ato`` directly. atopile has
already turned every ``.footprint = "..."`` assignment (including ones
buried in loops/inheritance/component-library defaults) into one
``(footprint "...")`` field per compiled ``(comp (ref ...))``, so parsing
the netlist gets the same information a from-scratch .ato parser would
have to reconstruct, without re-implementing atopile's own module
resolution.

Identity key: SHEETPATH, not reference designator. This repo has already
been bitten by refdes-identity assumptions -- adding one component
upstream in designator order renumbers every later same-prefix
designator (docs/solutions/logic-errors/
fixed-positions-ref-fragility-across-renumbering.md; a recent change
nearly renumbered 50 resistors, see ``elec/src/modules.ato``'s "R30"
pin-designator-freeze comment). ``preflight_identity`` (``packages/
temper-placer/.../design_bundle_preflight.py``) compares refdes *sets* at
a 95% overlap threshold -- that check cannot see a wholesale renumber
because it never looks at what moved WHERE, only whether the same names
mostly still exist. ``resync_pcb_netlist.py`` itself already solved this
problem the same way this gate does: it matches old-board footprints to
new-netlist components by the footprint's own ``Sheetpath`` property
(``old_by_sheetpath`` in that script), the exact convention this gate
reuses. The sheetpath string is normalised with the same rule ``gen_pcb_
skeleton.py._full_sheetpath`` uses (deliberately re-implemented here, not
imported -- see the parser note below): split the netlist's ``(sheetpath
(names "...:Top::a.b.c") ...)`` on ``"::"`` and keep everything after the
first occurrence, giving ``"a.b.c"`` -- stable across designator
renumbering because it is derived from the .ato module-instantiation
path, not atopile's positional-per-prefix numbering.

Three outcome classes per sheetpath (deliberately NOT lumped together --
"classify them separately" is the explicit design requirement here,
because conflating "renamed/moved" with "genuinely wrong" is exactly the
kind of blurring that lets defects hide):
  1. MISMATCH: sheetpath exists on both sides, footprint strings differ.
     The core defect class this gate exists for.
  2. MISSING-FROM-BOARD: sheetpath is in the netlist, no board footprint
     carries it -- the board has never been resynced to include this
     component at all (a real, current instance: ``tank.c_tank3``, added
     by commit 3ae26dfe, has no footprint on the board with sheetpath
     "tank.c_tank3" -- see docs/evidence/
     2026-07-30-copper-net-consistency-drift.md for the same underlying
     incident from the net-identity side).
  3. MISSING-FROM-NETLIST: a board footprint's ``Sheetpath`` property
     doesn't match anything in the compiled netlist -- either a stale
     board carrying a component the schematic no longer has, or (rare) a
     board footprint with a corrupted/hand-edited Sheetpath property.

All three classes fail this gate (EXIT_VIOLATION). An unresynced-away
component is not a lesser defect than a mismatched footprint -- it is the
same "board silently drifted from source" failure mode, just at the
"never even looked at" end of the spectrum rather than the
"looked-at-and-still-wrong" end. Reporting them in separate buckets
(rather than silently skipping, or silently merging into "mismatch") is
what makes this gate's output actionable: a human fixing MISSING-FROM-
BOARD needs to place a new component; a human fixing MISMATCH needs to
swap a land pattern in place.

Self-contained S-expression netlist parser: this is a DELIBERATE copy of
the equivalent parser in ``check_copper_net_consistency.py`` (itself
explained there as deliberately not importing ``gen_pcb_skeleton.py``'s
version) -- this gate's correctness must not depend on any generator
script's internal representation changing out from under it.

Fail-closed contract (METHODOLOGY.md Sec 4/5): never exits 0 unless it
positively confirms it ran a real check on real, fresh, non-empty data.
Exits non-zero for every one of:
  - the board file is missing or fails to parse
  - the netlist file is missing, empty, or fails to parse
  - the netlist is STALE (older than any elec/src/*.ato file)
  - the netlist has zero components, or the board has zero footprints
  - two components in the netlist (or two footprints on the board) share
    the same sheetpath -- identity is ambiguous, nothing downstream of
    this can be trusted, so this is a GATE ERROR, not "0 violations"

No allowlist: unlike ``mpn_fabrication_gate.py``, a footprint mismatch has
no legitimate "expected" case to suppress. Every finding here is either a
resync that still needs to happen, or (rarer) a board footprint whose
Sheetpath property has rotted. Never add an allowlist/baseline/ratchet to
this gate to accommodate a known instance -- the correct fix for a known
instance is to resync the board, not to silence the gate.

Exit codes:
  0 - PASSED: 0 violations across a real, fresh, non-empty check
  3 - VIOLATION: at least one footprint mismatch or unmatched component
  5 - GATE ERROR: the gate could not run a trustworthy check at all

Usage:
  uv run python scripts/check_footprint_drift.py
  uv run python scripts/check_footprint_drift.py --board PATH --netlist PATH
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.repo import find_repo_root
from _lib.github_summary import get_github_summary_path

REPO_ROOT = find_repo_root()
DEFAULT_BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"
DEFAULT_NETLIST = REPO_ROOT / "elec" / "build" / "default.net"
DEFAULT_SRC_DIR = REPO_ROOT / "elec" / "src"

EXIT_OK = 0
EXIT_VIOLATION = 3
EXIT_GATE_ERROR = 5


class GateError(Exception):
    """Raised for any condition that must fail closed (exit 5)."""


# ---------------------------------------------------------------------------
# Self-contained S-expression netlist parser (see module docstring: a
# deliberate copy, not an import, of check_copper_net_consistency.py's own
# copy of the same parser).
# ---------------------------------------------------------------------------

_TOKEN = re.compile(r'\s*(?:(\()|(\))|("(?:\\.|[^"\\])*")|([^\s()]+))', re.S)


def _sexp(text: str) -> list[Any]:
    tokens: list[str] = []
    pos = 0
    while pos < len(text):
        match = _TOKEN.match(text, pos)
        if not match:
            if text[pos:].strip():
                raise GateError(f"invalid netlist syntax at byte {pos}")
            break
        pos = match.end()
        tokens.append(match.group(1) or match.group(2) or match.group(3) or match.group(4))
    root: list[Any] = []
    stack: list[list[Any]] = [root]
    for token in tokens:
        if token == "(":
            node: list[Any] = []
            stack[-1].append(node)
            stack.append(node)
        elif token == ")":
            if len(stack) == 1:
                raise GateError("unbalanced netlist: unmatched ')'")
            stack.pop()
        else:
            stack[-1].append(json.loads(token) if token.startswith('"') else token)
    if len(stack) != 1:
        raise GateError("unbalanced netlist: unmatched '('")
    return root


def _children(node: list[Any], name: str) -> list[list[Any]]:
    return [c for c in node if isinstance(c, list) and c and c[0] == name]


def _field(node: list[Any], name: str, *, required: bool = True) -> str:
    fields = _children(node, name)
    if len(fields) > 1 or (required and not fields):
        raise GateError(f"invalid {name!r} field in {node[0]!r}")
    if not fields:
        return ""
    if len(fields[0]) != 2 or not isinstance(fields[0][1], str):
        raise GateError(f"malformed {name!r} field in {node[0]!r}")
    return fields[0][1]


def _full_sheetpath(sheetpath_node: list[Any]) -> str | None:
    """Same normalisation as gen_pcb_skeleton.py's ``_full_sheetpath``:
    keep everything after the first ``"::"`` in the sheetpath's ``names``
    field (e.g. ``".../main.ato:Top::power_in.c_x2"`` -> ``"power_in.c_x2"``),
    stable across designator renumbering because it is the .ato
    module-instantiation path, not atopile's positional numbering."""
    for child in _children(sheetpath_node, "names"):
        names = child[1] if len(child) > 1 and isinstance(child[1], str) else ""
        if "::" in names:
            return names.split("::", 1)[1]
    return None


@dataclass
class NetlistComponent:
    ref: str
    footprint: str
    sheetpath: str


@dataclass
class Netlist:
    by_sheetpath: dict[str, NetlistComponent]


def parse_netlist(path: Path) -> Netlist:
    if not path.is_file():
        raise GateError(f"netlist not found: {path}")
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise GateError(f"netlist file is empty: {path}")
    parsed = _sexp(text)
    export = next(
        (item for item in parsed if isinstance(item, list) and item[:1] == ["export"]), None
    )
    if export is None:
        raise GateError(f"netlist has no 'export' block: {path}")

    components_block = _children(export, "components")
    if len(components_block) != 1:
        raise GateError("netlist must contain exactly one 'components' block")

    by_sheetpath: dict[str, NetlistComponent] = {}
    for node in _children(components_block[0], "comp"):
        ref = _field(node, "ref")
        footprint = _field(node, "footprint", required=False)
        sheetpath_nodes = _children(node, "sheetpath")
        sheetpath = _full_sheetpath(sheetpath_nodes[0]) if sheetpath_nodes else None
        if sheetpath is None:
            raise GateError(
                f"netlist component {ref!r} has no usable 'sheetpath' field -- "
                "cannot establish a designator-renumbering-safe identity for it"
            )
        if sheetpath in by_sheetpath:
            raise GateError(
                f"netlist has two components sharing sheetpath {sheetpath!r} "
                f"({by_sheetpath[sheetpath].ref!r} and {ref!r}) -- identity is "
                "ambiguous, refusing to guess which one a board footprint "
                "matches"
            )
        by_sheetpath[sheetpath] = NetlistComponent(ref=ref, footprint=footprint, sheetpath=sheetpath)

    if not by_sheetpath:
        raise GateError(f"netlist contains zero components: {path}")

    return Netlist(by_sheetpath=by_sheetpath)


def check_netlist_freshness(netlist_path: Path, src_dir: Path) -> None:
    """Fail closed if the compiled netlist predates any .ato source file --
    identical contract to check_copper_net_consistency.py's own freshness
    guard (itself matching check_domain_partition.py's), which has already
    caught this exact staleness failure mode on this project."""
    if not netlist_path.is_file():
        raise GateError(
            f"netlist not found: {netlist_path} -- run `make netlist` first "
            "(elec/build/ is gitignored, so it must be built locally/in-CI, "
            "never assumed to already exist)"
        )
    netlist_mtime = netlist_path.stat().st_mtime
    if not src_dir.is_dir():
        raise GateError(f"elec source directory not found: {src_dir}")
    source_files = sorted(src_dir.rglob("*.ato"))
    if not source_files:
        raise GateError(f"no .ato source files found under {src_dir}")
    stale_against = [f for f in source_files if f.stat().st_mtime > netlist_mtime]
    if stale_against:
        newest = max(stale_against, key=lambda f: f.stat().st_mtime)
        raise GateError(
            f"netlist is STALE: {newest} was modified after {netlist_path} "
            "was built. Run `make netlist` to rebuild before running this "
            f"gate ({len(stale_against)} source file(s) newer than the "
            "compiled netlist)."
        )


# ---------------------------------------------------------------------------
# Board parsing (kiutils -- the same library resync_pcb_netlist.py itself
# uses to read/write this exact file format).
# ---------------------------------------------------------------------------


@dataclass
class BoardComponent:
    ref: str
    footprint: str | None
    sheetpath: str | None


@dataclass
class BoardData:
    components: list[BoardComponent]


def load_board(board_path: Path) -> BoardData:
    if not board_path.is_file():
        raise GateError(f"board not found: {board_path}")
    try:
        from kiutils.board import Board
    except ImportError as exc:
        raise GateError(f"kiutils is not installed: {exc}") from exc
    try:
        board = Board.from_file(str(board_path))
    except Exception as exc:  # kiutils raises plain Exception/ValueError on malformed input
        raise GateError(f"failed to parse board {board_path}: {exc}") from exc

    if not board.footprints:
        raise GateError(f"board has zero footprints: {board_path}")

    components: list[BoardComponent] = []
    for fp in board.footprints:
        props = fp.properties or {}
        ref = props.get("Reference")
        if not ref:
            continue
        footprint = props.get("Footprint") or (fp.libId or None)
        sheetpath = props.get("Sheetpath") or None
        components.append(BoardComponent(ref=ref, footprint=footprint, sheetpath=sheetpath))

    if not components:
        raise GateError(f"board has zero footprints with a 'Reference' property: {board_path}")

    return BoardData(components=components)


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


@dataclass
class Violation:
    check: str  # "mismatch" | "missing-from-board" | "missing-from-netlist" | "no-sheetpath"
    detail: str


@dataclass
class Report:
    matched: int
    violations: list[Violation] = field(default_factory=list)


def run_checks(netlist: Netlist, board: BoardData) -> Report:
    board_by_sheetpath: dict[str, BoardComponent] = {}
    violations: list[Violation] = []

    for comp in board.components:
        if comp.sheetpath is None:
            violations.append(
                Violation(
                    "no-sheetpath",
                    f"{comp.ref}: board footprint has no 'Sheetpath' property -- "
                    "cannot be identity-matched against the netlist at all",
                )
            )
            continue
        if comp.sheetpath in board_by_sheetpath:
            raise GateError(
                f"board has two footprints sharing Sheetpath "
                f"{comp.sheetpath!r} ({board_by_sheetpath[comp.sheetpath].ref!r} "
                f"and {comp.ref!r}) -- identity is ambiguous, refusing to guess "
                "which one a netlist component matches"
            )
        board_by_sheetpath[comp.sheetpath] = comp

    matched = 0
    for sheetpath, ncomp in sorted(netlist.by_sheetpath.items()):
        bcomp = board_by_sheetpath.get(sheetpath)
        if bcomp is None:
            violations.append(
                Violation(
                    "missing-from-board",
                    f"{ncomp.ref} (sheetpath {sheetpath!r}): netlist declares "
                    f"footprint {ncomp.footprint!r}, but no board footprint "
                    "carries this sheetpath -- the board has never been "
                    "resynced to include this component",
                )
            )
            continue
        matched += 1
        if bcomp.footprint != ncomp.footprint:
            violations.append(
                Violation(
                    "mismatch",
                    f"{ncomp.ref} (sheetpath {sheetpath!r}): source/netlist says "
                    f"{ncomp.footprint!r}, board still has {bcomp.footprint!r} "
                    f"(board ref {bcomp.ref!r})",
                )
            )

    for sheetpath, bcomp in sorted(board_by_sheetpath.items()):
        if sheetpath not in netlist.by_sheetpath:
            violations.append(
                Violation(
                    "missing-from-netlist",
                    f"{bcomp.ref} (sheetpath {sheetpath!r}): board footprint "
                    f"{bcomp.footprint!r} has no matching component in the "
                    "compiled netlist -- stale board, or a corrupted "
                    "Sheetpath property",
                )
            )

    return Report(matched=matched, violations=violations)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run(board_path: Path, netlist_path: Path, src_dir: Path, skip_freshness: bool = False) -> int:
    try:
        if not skip_freshness:
            check_netlist_freshness(netlist_path, src_dir)
        netlist = parse_netlist(netlist_path)
        board = load_board(board_path)

        # Anti-vacuous-truth: re-assert non-empty data before any verdict is
        # trusted, even though parse_netlist/load_board should already
        # guarantee it -- protects against a future refactor silently
        # dropping that guarantee (same pattern as check_copper_net_
        # consistency.py's own belt-and-suspenders re-assertion).
        if len(netlist.by_sheetpath) == 0:
            raise GateError("no components in netlist (should have been caught earlier)")
        if len(board.components) == 0:
            raise GateError("no footprints on board (should have been caught earlier)")

        report = run_checks(netlist, board)
    except GateError as exc:
        print("=== FOOTPRINT-DRIFT GATE ERROR ===", file=sys.stderr)
        print(f"Reason: {exc}", file=sys.stderr)
        print(
            "GATE RESULT: ERROR -- not PASSED, not a violation. The gate "
            "could not run a trustworthy check.",
            file=sys.stderr,
        )
        gh = get_github_summary_path()
        if gh:
            with open(gh, "a") as f:
                f.write("### Footprint-Drift Gate -- GATE ERROR\n")
                f.write(f"{exc}\n")
        return EXIT_GATE_ERROR

    print(f"Board: {board_path}")
    print(f"Netlist: {netlist_path}")
    print(
        f"Components: {len(netlist.by_sheetpath)} in netlist, "
        f"{report.matched} matched by sheetpath against the board."
    )

    gh = get_github_summary_path()

    if not report.violations:
        print(f"\nPASSED -- 0 violations across {report.matched} matched component(s).")
        if gh:
            with open(gh, "a") as f:
                f.write("### Footprint-Drift Gate -- PASSED\n")
                f.write(f"0 violations across {report.matched} matched component(s).\n")
        return EXIT_OK

    by_check: dict[str, list[Violation]] = {}
    for v in report.violations:
        by_check.setdefault(v.check, []).append(v)

    print(f"\n=== VIOLATIONS: {len(report.violations)} ===")
    gh_lines: list[str] = []
    for check_name, vs in sorted(by_check.items()):
        print(f"\n  [{check_name}] {len(vs)} violation(s):")
        for v in vs:
            print(f"    {v.detail}")
            gh_lines.append(f"- `[{check_name}]` {v.detail}")

    if gh:
        with open(gh, "a") as f:
            f.write("### Footprint-Drift Gate -- FAILED\n")
            f.write(f"{len(report.violations)} violation(s)\n\n")
            for line in gh_lines[:200]:
                f.write(line + "\n")

    print(f"\nFAILED -- {len(report.violations)} violation(s)")
    return EXIT_VIOLATION


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--board", type=Path, default=DEFAULT_BOARD)
    parser.add_argument("--netlist", type=Path, default=DEFAULT_NETLIST)
    parser.add_argument("--src-dir", type=Path, default=DEFAULT_SRC_DIR)
    parser.add_argument(
        "--skip-freshness-check",
        action="store_true",
        help="Skip the netlist-vs-source mtime staleness check (test fixtures only).",
    )
    args = parser.parse_args()
    sys.exit(run(args.board, args.netlist, args.src_dir, args.skip_freshness_check))


if __name__ == "__main__":
    main()
