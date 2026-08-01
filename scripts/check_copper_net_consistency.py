#!/usr/bin/env python3
"""Board-copper / netlist consistency gate: catch corrupted net ordinals.

Motivation (docs/evidence/2026-07-27-resync-net-ordinal-fix.md): KiCad
stores each segment's/via's/zone's net as a bare ORDINAL INDEX into the
board's own net table, not a name. `scripts/resync_pcb_netlist.py` used to
rebuild that table (sorted alphabetically, renumbered 1..N) without
remapping the ordinals stored on `board.traceItems`/`board.zones` -- a bug
that, measured on the real board, would have silently reassigned 79% of
segments and 75% of vias to the wrong electrical net. Nothing else in this
project's CI can see board copper at all: `check_domain_partition` reads
the *netlist*, the clearance checks read component *positions*, and
`mpn_fabrication_gate` reads part *identity*. A board with corrupted net
assignments passes every one of those unchanged. This gate closes that
blind spot by reading `pcb/temper.kicad_pcb` directly.

What this checks, over every segment/arc/via/zone in the board (net == 0,
"no net", is skipped -- see NOTE below) and every footprint pad:

  1. ORDINAL RESOLVES: every copper item's net ordinal must exist as a
     number in the board's own net table. A dangling index is the direct
     signature of the corruption class this gate exists for.
  2. NAME EXISTS IN NETLIST: the net name each copper item's ordinal
     resolves to must exist in the compiled netlist. A name that resolves
     but isn't in the netlist is orphaned copper -- either a stale,
     not-yet-resynced board, or the deleted-resistor case (a net removed
     from the schematic while copper for it is still routed).
  3. PAD/NETLIST AGREEMENT: for every footprint pad whose (Reference, pad
     number) has an EXACT match in the compiled netlist, the pad's actual
     net name on the board must equal what the netlist declares for that
     pin. This is the strongest of the three checks -- it catches
     designator/net misattribution directly, independent of the net-table
     ordinal question. Pads that only match via resync's POSITIONAL
     fallback (e.g. relay 'A1'/'A2'/'13'/'14', whose pad numbers don't
     line up with netlist pin numbers) are not enforced here and are
     reported separately as SKIPPED, not silently counted as checked --
     recomputing that heuristic independently would either duplicate
     resync's exact matching logic (a second implementation to keep in
     sync) or trust a different one; this gate only asserts what it can
     verify by EXACT identity.

Net-set asymmetry (deliberately NOT enforced): this gate does not require
the board's net table to equal the netlist's net set. A netlist net with
zero board copper (not yet routed) is normal and not a violation -- most
nets are in that state well before layout is complete. Only a NAMED
mismatch actually referenced by real copper (checks 1/2/3 above) is
treated as a defect; an unrouted-but-declared net is informational only.

Fail-closed contract (METHODOLOGY.md Sec 4/5), matching
check_domain_partition.py's contract: never exits 0 unless it positively
confirms it ran a real check on real, fresh, non-empty data. Exits non-zero
for every one of:
  - the board file is missing or fails to parse
  - the netlist file is missing, empty, or fails to parse
  - the netlist is STALE (older than any elec/src/*.ato file)
  - the board's net table has zero entries
  - the netlist has zero nets
  - zero copper items (segments+arcs+vias+zones) exist on the board
  - zero footprints, or zero pads across all footprints, exist on the board

No allowlist: unlike mpn_fabrication_gate.py (hand-curated, human-reasoned
suppressions for known-benign cases), a net-identity mismatch has no
legitimate "expected" case to suppress -- every finding here is either a
bug in resync or a board that needs resyncing, never a false positive to
be waived.

Exit codes:
  0 - PASSED: 0 violations across a real, fresh, non-empty check
  3 - VIOLATION: a dangling ordinal, orphaned copper net, or pad/netlist
      mismatch was found
  5 - GATE ERROR: the gate could not run a trustworthy check at all (see
      list above) -- never treated as "0 violations"

Usage:
  uv run python scripts/check_copper_net_consistency.py
  uv run python scripts/check_copper_net_consistency.py --board PATH --netlist PATH
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

from _lib.freshness import check_freshness
from _lib.github_summary import get_github_summary_path
from _lib.repo import find_repo_root

REPO_ROOT = find_repo_root()
DEFAULT_BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"
DEFAULT_NETLIST = REPO_ROOT / "elec" / "build" / "default.net"
DEFAULT_SRC_DIR = REPO_ROOT / "elec" / "src"

EXIT_OK = 0
EXIT_VIOLATION = 3
EXIT_GATE_ERROR = 5

NO_NET_NAME = ""  # KiCad's implicit ordinal-0 "no net" name


class GateError(Exception):
    """Raised for any condition that must fail closed (exit 5)."""


# ---------------------------------------------------------------------------
# Self-contained S-expression netlist parser (deliberately NOT imported from
# gen_pcb_skeleton.py/resync_pcb_netlist.py/check_domain_partition.py: this
# gate's correctness must not depend on a generator script's internal
# representation changing out from under it -- same reasoning
# check_domain_partition.py itself documents for its own copy).
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


@dataclass
class Netlist:
    nets: dict[str, str]  # code -> name
    pin_net: dict[tuple[str, str], str]  # (ref, pin) -> net code


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

    nets_block = _children(export, "nets")
    if len(nets_block) != 1:
        raise GateError("netlist must contain exactly one 'nets' block")
    nets: dict[str, str] = {}
    pin_net: dict[tuple[str, str], str] = {}
    for node in _children(nets_block[0], "net"):
        code = _field(node, "code")
        name = _field(node, "name")
        if code in nets:
            raise GateError(f"duplicate net code in netlist: {code!r}")
        nets[code] = name
        for nn in _children(node, "node"):
            ref = _field(nn, "ref")
            pin = _field(nn, "pin")
            pin_net[(ref, pin)] = code  # first-writer-wins is fine: exact-match lookup only

    if not nets:
        raise GateError(f"netlist contains zero nets: {path}")

    return Netlist(nets=nets, pin_net=pin_net)


def check_netlist_freshness(netlist_path: Path, src_dir: Path) -> None:
    """Fail closed if the compiled netlist was not built from current sources.

    A stale netlist checking yesterday's design and reporting "0 violations"
    is indistinguishable from a correct check on today's design -- and is
    exactly the failure mode this class of gate has hit repeatedly on this
    project. `elec/build/` is gitignored; nothing else guarantees freshness.

    Freshness is decided by CONTENT when `make netlist` left a build stamp
    beside the netlist, and by the legacy mtime comparison when it did not.
    See scripts/_lib/freshness.py for why: mtime cannot distinguish "rebuilt
    from unchanged sources" from "restored from cache", because `git checkout`
    stamps every source with the checkout time. That made a cached netlist
    permanently, wrongly STALE -- measured on CI 2026-07-31 on this gate
    (runs 30645135140 / 30610662266, "8 source file(s) newer than the
    compiled netlist" on a byte-identical netlist restored from the netlist
    actions/cache). The identical fix already landed in
    check_domain_partition.py.

    Content is also strictly stronger than mtime, not merely cache-friendly:
    a source edited and then back-dated older than the netlist passes the
    mtime check and fails the content check.
    """
    if not netlist_path.is_file():
        raise GateError(
            f"netlist not found: {netlist_path} -- run `make netlist` first "
            "(elec/build/ is gitignored, so it must be built locally/in-CI, "
            "never assumed to already exist)"
        )
    if not src_dir.is_dir():
        raise GateError(f"elec source directory not found: {src_dir}")
    source_files = sorted(src_dir.rglob("*.ato"))
    if not source_files:
        raise GateError(f"no .ato source files found under {src_dir}")

    result = check_freshness(netlist_path, source_files, src_dir)
    if not result.fresh:
        raise GateError(
            f"netlist is STALE: {result.detail}. Run `make netlist` to rebuild "
            f"before running this gate (freshness checked by {result.method})."
        )


# ---------------------------------------------------------------------------
# Board parsing (kiutils -- the same library resync_pcb_netlist.py itself
# uses to read/write this exact file format).
# ---------------------------------------------------------------------------


@dataclass
class CopperItem:
    kind: str  # "Segment" | "Arc" | "Via" | "Zone"
    ident: str  # tstamp, or "<Zone index N>" (zones in this board carry no tstamp)
    net_ordinal: int
    zone_net_name: str | None = None  # Zone.netName, for the redundancy check


@dataclass
class PadRef:
    ref: str
    pad_number: str
    actual_net_name: str  # "" if pad.net is None (unconnected)


@dataclass
class BoardData:
    net_number_to_name: dict[int, str]
    copper: list[CopperItem]
    pads: list[PadRef]


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

    if not board.nets:
        raise GateError(f"board net table is empty: {board_path}")

    net_number_to_name = {0: NO_NET_NAME}
    for n in board.nets:
        net_number_to_name[n.number] = n.name

    copper: list[CopperItem] = []
    for item in board.traceItems:
        kind = type(item).__name__
        ident = getattr(item, "tstamp", None) or f"<{kind} with no tstamp>"
        copper.append(CopperItem(kind=kind, ident=ident, net_ordinal=item.net))
    for i, zone in enumerate(board.zones):
        ident = zone.tstamp or f"<Zone index {i}>"
        copper.append(
            CopperItem(
                kind="Zone", ident=ident, net_ordinal=zone.net, zone_net_name=zone.netName
            )
        )

    if not copper:
        raise GateError(
            f"board has zero copper items (0 segments/arcs/vias/zones): {board_path} "
            "-- this gate has nothing to check against an unrouted board "
            "(anti-vacuous-truth: report as a gate error, not '0 violations')"
        )

    if not board.footprints:
        raise GateError(f"board has zero footprints: {board_path}")

    pads: list[PadRef] = []
    for fp in board.footprints:
        ref = (fp.properties or {}).get("Reference")
        if not ref:
            continue
        for pad in fp.pads:
            actual_name = pad.net.name if pad.net is not None else NO_NET_NAME
            pads.append(PadRef(ref=ref, pad_number=pad.number, actual_net_name=actual_name))

    if not pads:
        raise GateError(f"board has zero pads across {len(board.footprints)} footprint(s)")

    return BoardData(net_number_to_name=net_number_to_name, copper=copper, pads=pads)


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


@dataclass
class Violation:
    check: str  # "dangling-ordinal" | "orphaned-net" | "zone-name-mismatch" | "pad-mismatch"
    detail: str


@dataclass
class Report:
    copper_checked: int
    copper_by_type: dict[str, int]
    copper_skipped_no_net: int
    pads_checked: int
    pads_skipped_no_exact_match: int
    violations: list[Violation] = field(default_factory=list)


def run_checks(board: BoardData, netlist: Netlist) -> Report:
    netlist_net_names = set(netlist.nets.values())

    violations: list[Violation] = []
    copper_by_type: dict[str, int] = {}
    copper_checked = 0
    copper_skipped_no_net = 0

    for item in board.copper:
        copper_by_type[item.kind] = copper_by_type.get(item.kind, 0) + 1
        if item.net_ordinal == 0:
            copper_skipped_no_net += 1
            continue
        copper_checked += 1

        # Check 1: ordinal resolves against the board's OWN net table.
        name = board.net_number_to_name.get(item.net_ordinal)
        if name is None:
            violations.append(
                Violation(
                    "dangling-ordinal",
                    f"{item.kind} {item.ident}: net ordinal {item.net_ordinal} "
                    "does not exist in the board's own net table",
                )
            )
            continue

        # Zone-specific: the redundant net_name field must agree with what
        # the ordinal itself resolves to.
        if item.kind == "Zone" and item.zone_net_name != name:
            violations.append(
                Violation(
                    "zone-name-mismatch",
                    f"Zone {item.ident}: net_name {item.zone_net_name!r} disagrees "
                    f"with ordinal {item.net_ordinal} (resolves to {name!r})",
                )
            )
            continue

        # Check 2: the resolved name must exist in the compiled netlist.
        if name not in netlist_net_names:
            violations.append(
                Violation(
                    "orphaned-net",
                    f"{item.kind} {item.ident}: net {name!r} (ordinal "
                    f"{item.net_ordinal}) does not exist in the compiled "
                    "netlist -- stale board (needs a resync) or orphaned "
                    "copper on a deleted net",
                )
            )

    # Check 3: pad/netlist agreement, EXACT (ref, pad_number) matches only.
    pads_checked = 0
    pads_skipped = 0
    for pad in board.pads:
        code = netlist.pin_net.get((pad.ref, pad.pad_number))
        if code is None:
            pads_skipped += 1
            continue
        pads_checked += 1
        expected_name = netlist.nets[code]
        if pad.actual_net_name != expected_name:
            violations.append(
                Violation(
                    "pad-mismatch",
                    f"{pad.ref} pad {pad.pad_number}: board has net "
                    f"{pad.actual_net_name!r}, compiled netlist declares "
                    f"{expected_name!r} for this pin",
                )
            )

    return Report(
        copper_checked=copper_checked,
        copper_by_type=copper_by_type,
        copper_skipped_no_net=copper_skipped_no_net,
        pads_checked=pads_checked,
        pads_skipped_no_exact_match=pads_skipped,
        violations=violations,
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run(board_path: Path, netlist_path: Path, src_dir: Path, skip_freshness: bool = False) -> int:
    try:
        if not skip_freshness:
            check_netlist_freshness(netlist_path, src_dir)
        netlist = parse_netlist(netlist_path)
        board = load_board(board_path)

        # Anti-vacuous-truth: confirm real, non-empty data before any
        # verdict is trusted (should already be guaranteed by load_board/
        # parse_netlist raising GateError, re-asserted here so a future
        # refactor cannot silently drop that guarantee).
        if board.copper_checked_total() if hasattr(board, "copper_checked_total") else len(board.copper) == 0:
            raise GateError("no copper items to check (should have been caught earlier)")
        if len(netlist.nets) == 0:
            raise GateError("no nets in netlist (should have been caught earlier)")

        report = run_checks(board, netlist)
    except GateError as exc:
        print("=== COPPER-NET CONSISTENCY GATE ERROR ===", file=sys.stderr)
        print(f"Reason: {exc}", file=sys.stderr)
        print(
            "GATE RESULT: ERROR -- not PASSED, not a violation. The gate "
            "could not run a trustworthy check.",
            file=sys.stderr,
        )
        gh = get_github_summary_path()
        if gh:
            with open(gh, "a") as f:
                f.write("### Copper-Net Consistency Gate -- GATE ERROR\n")
                f.write(f"{exc}\n")
        return EXIT_GATE_ERROR

    total_copper = sum(report.copper_by_type.values())
    print(f"Board: {board_path}")
    print(f"Netlist: {netlist_path}")
    print(
        f"Copper: {total_copper} item(s) total "
        f"({', '.join(f'{k}={v}' for k, v in sorted(report.copper_by_type.items()))}), "
        f"{report.copper_checked} checked (net != 0), "
        f"{report.copper_skipped_no_net} skipped (net == 0, no-net)."
    )
    print(
        f"Pads: {report.pads_checked} checked (exact ref+pin match in "
        f"netlist), {report.pads_skipped_no_exact_match} skipped "
        "(no exact match -- resync's positional-fallback candidates, not "
        "independently verified by this gate)."
    )

    gh = get_github_summary_path()

    if not report.violations:
        print(
            f"\nPASSED -- 0 violations across {report.copper_checked} "
            f"copper item(s) and {report.pads_checked} pad(s) checked."
        )
        if gh:
            with open(gh, "a") as f:
                f.write("### Copper-Net Consistency Gate -- PASSED\n")
                f.write(
                    f"0 violations across {report.copper_checked} copper "
                    f"item(s), {report.pads_checked} pad(s).\n"
                )
        return EXIT_OK

    by_check: dict[str, list[Violation]] = {}
    for v in report.violations:
        by_check.setdefault(v.check, []).append(v)

    print(f"\n=== VIOLATIONS: {len(report.violations)} ===")
    gh_lines: list[str] = []
    for check_name, vs in sorted(by_check.items()):
        print(f"\n  [{check_name}] {len(vs)} violation(s):")
        for v in vs[:50]:
            print(f"    {v.detail}")
            gh_lines.append(f"- `[{check_name}]` {v.detail}")
        if len(vs) > 50:
            print(f"    ... and {len(vs) - 50} more")

    if gh:
        with open(gh, "a") as f:
            f.write("### Copper-Net Consistency Gate -- FAILED\n")
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
