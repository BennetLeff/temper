#!/usr/bin/env python3
"""Stamp `pcb/temper.kicad_pcb` with the netlist it was last reconciled against.

Motivation (2026-08-13 board/netlist desync postmortem)
---------------------------------------------------------
`pcb/temper.kicad_pcb` and `elec/build/default.net` drifted apart for five
days without anyone noticing: ``U6``/``U7`` came to name different physical
parts on the two sides, four schematic components had no board footprint,
and dozens of components were renumbered in the schematic while the board
kept old designators. ``scripts/check_netlist_board_reconciliation.py``
detects exactly this class -- and does so correctly, keyed by instance path,
not refdes -- but it is a comprehensive, whole-board comparison: nothing
forces anyone to have run it (or to have looked at its result) since the
last time the board was actually good.

This tool is the write-side of a much narrower, cheaper, complementary
signal: a committed, git-diff-visible CLAIM, sitting right next to the board
file, of exactly which compiled netlist that board was last verified
against. It follows the SAME content-hash stamp mechanism already used
twice in this repo for the identical shape of problem
(`scripts/write_extension_stamps.py` for pyo3 `.so` freshness,
`scripts/write_build_stamp.py` for `elec/build/default.net` freshness
against `elec/src/**`) -- see `scripts/_lib/freshness.py`.

What gets hashed, and why the board's OWN bytes are an input
--------------------------------------------------------------
The stamp records a digest over TWO files' current content:
  1. `elec/build/default.net` -- the compiled netlist this board was
     compared against.
  2. `pcb/temper.kicad_pcb` itself -- the board file the stamp sits beside.

Including the board's own bytes is deliberate, not redundant: a stamp that
only recorded the netlist's digest would go stale only when the NETLIST
changed, and would stay silently "fresh" if someone hand-edited the board
afterward (e.g. reintroducing exactly the renumber/missing-footprint defect
class this mechanism exists to catch) without the netlist moving at all.
Folding the board's own content into the same digest means ANY edit to
EITHER side invalidates the stamp -- the claim is "this exact board, as of
this exact byte content, was verified against this exact netlist," not
merely "some netlist, once."

Refusing to write a dishonest stamp
--------------------------------------
A stamp is only as trustworthy as the check that produced it. This tool
therefore runs `scripts/check_netlist_board_reconciliation.py` itself,
right now, against the given board/netlist, and REFUSES to write a stamp
unless that gate exits 0 (PASSED -- zero findings). Stamping a desynced
board as "verified" would be strictly worse than no stamp at all: it turns
a knowable-if-you-look defect into a covered-up one.

Usage (after a real resync -- `scripts/resync_pcb_netlist.py` or manual):
    make netlist
    uv run --no-sync python scripts/check_netlist_board_reconciliation.py  # must PASS first
    uv run --no-sync python scripts/write_board_sync_stamp.py

Exit codes (mirrors write_build_stamp.py's 0/1 build-tool contract, not the
0/3/5 gate contract -- this is a developer/CI action, not a check):
    0  stamp written
    1  board/netlist missing, reconciliation did not pass, or the stamp
       could not be written
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.freshness import write_stamp  # noqa: E402
from _lib.repo import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root()
DEFAULT_BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"
DEFAULT_NETLIST = REPO_ROOT / "elec" / "build" / "default.net"
DEFAULT_SRC_DIR = REPO_ROOT / "elec" / "src"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--board", type=Path, default=DEFAULT_BOARD)
    parser.add_argument("--netlist", type=Path, default=DEFAULT_NETLIST)
    parser.add_argument("--src-dir", type=Path, default=DEFAULT_SRC_DIR)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Root the stamp's digest paths are relativised against (test fixtures only; "
        "must match the --repo-root check_board_sync_stamp.py is later run with).",
    )
    parser.add_argument(
        "--skip-freshness-check",
        action="store_true",
        help="Skip the netlist-vs-source staleness check (test fixtures only).",
    )
    args = parser.parse_args(argv)

    if not args.board.is_file():
        print(
            f"[write-board-sync-stamp] ERROR: board not found: {args.board}",
            file=sys.stderr,
        )
        return 1
    if not args.netlist.is_file():
        print(
            f"[write-board-sync-stamp] ERROR: netlist not found: {args.netlist} "
            "-- run `make netlist` first",
            file=sys.stderr,
        )
        return 1

    # Import here (not top-level) so this tool's own import errors, if any,
    # are distinguishable from a genuine reconciliation failure -- and so it
    # shares check_netlist_board_reconciliation's exact verdict rather than
    # re-deriving one, per this repo's "one loader/one derivation" precedent
    # (temper_placer.io.real_board's own docstring).
    import check_netlist_board_reconciliation as recon

    print("[write-board-sync-stamp] verifying reconciliation before stamping...")
    rc = recon.run(args.board, args.netlist, args.src_dir, args.skip_freshness_check)
    if rc != recon.EXIT_OK:
        print(
            "\n[write-board-sync-stamp] ERROR: refusing to stamp -- "
            f"check_netlist_board_reconciliation.py did not pass (exit {rc}). "
            "A stamp written now would assert this board is verified against "
            "the netlist above it, when it is not. Resync the board first "
            "(see the gate's own findings above), confirm it exits 0, then "
            "re-run this tool.",
            file=sys.stderr,
        )
        return 1

    # Hash the board's own bytes AND the netlist's bytes (see module
    # docstring "What gets hashed") -- both are `source_files` for
    # `write_stamp`'s purposes; `args.board` is simultaneously the artifact
    # the stamp is written beside and one of its own hashed inputs, which
    # `compute_inputs_digest` supports directly (it only ever reads the
    # listed files' current content; it never reads the `.source-digest`
    # stamp file itself).
    digest = write_stamp(args.board, [args.board, args.netlist], args.repo_root)
    print(
        f"[write-board-sync-stamp] {args.board}: reconciled against "
        f"{args.netlist} -- digest {digest[:12]}…"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
