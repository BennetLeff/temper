#!/usr/bin/env python3
"""Board-sync-stamp freshness gate: is the board's provenance claim still true?

Motivation
----------
`scripts/check_netlist_board_reconciliation.py` is the authoritative,
comprehensive check that `pcb/temper.kicad_pcb` and `elec/build/default.net`
actually agree, component-by-component and net-by-net, keyed by instance
path. It is correct and it is wired fail-closed into CI. What it is NOT is
a standing, self-evident CLAIM: its verdict only exists for the duration of
the CI run that computed it. Between runs -- or across the days it can take
a PR that touches `elec/src/` to land while a separate PR touches
`pcb/temper.kicad_pcb`, or vice versa -- nothing records what the board was
last actually checked against. The 2026-08-13 desync (`U6`/`U7` renamed to
different physical parts, 4 missing footprints, dozens of renumbers)
persisted five days before anyone looked at the reconciliation gate's
output and acted on it.

This gate does not re-derive the reconciliation gate's verdict (that would
duplicate it, which this repo's own conventions and this task explicitly
avoid). It asks a narrower, structurally different question: **does the
board still carry a stamp -- written by `scripts/write_board_sync_stamp.py`,
which itself refuses to run unless the reconciliation gate just passed --
whose recorded digest still matches the board's and the netlist's CURRENT
content?** A missing or stale stamp means one of:
  - the board has never been through the stamping tool at all (no
    provenance claim exists), or
  - the netlist changed since the board was last verified against it
    (an elec/src/ edit landed without a matching board resync+restamp), or
  - the board itself changed since it was last verified (a hand-edit, or a
    resync that was never followed by a fresh `write_board_sync_stamp.py`
    run) -- caught because the stamp's digest covers the board's OWN bytes,
    not merely the netlist's (see `write_board_sync_stamp.py`'s docstring).

Any of these is real, actionable information this gate reports -- it is the
trip-wire meant to fire the moment drift is introduced (a PR diff that
touches `elec/src/**` or `pcb/temper.kicad_pcb` without the stamp file
moving is visible to a reviewer without running anything), rather than
whenever someone next happens to run and read the comprehensive gate.

Both sides' freshness matters, not just their agreement
-----------------------------------------------------------
A stamp that merely says "board digest == netlist digest" is worthless if
the netlist itself is a stale artifact -- e.g. restored from a CI cache
keyed on a hash that did not change even though the true upstream sources
did (this exact failure mode is why `scripts/_lib/freshness.py` and
`check_domain_partition.check_netlist_freshness` exist: a cached
`elec/build/default.net` can silently predate `elec/src/**`). This gate
therefore ALWAYS calls `check_netlist_freshness` first and fails closed
(GATE ERROR) if the netlist itself is not proven fresh against
`elec/src/**` -- a digest comparison against a stale netlist is not
trusted, on the same principle `check_netlist_board_reconciliation.py`
itself already follows.

Deliberately does NOT reuse `_lib.freshness.check_freshness`'s mtime
fallback
--------------------------------------------------------------------------
Every other consumer of `scripts/_lib/freshness.py` (`check_stale_extensions
.py`, `check_domain_partition.py`) falls back to an mtime comparison when no
stamp is present, because their artifacts are REBUILT on every CI run --
"no stamp" there means "built by a path that predates this mechanism," and
failing closed on that would break every tree that has not adopted it yet
(see that module's own "Fallback, deliberately" section). `pcb/temper.
kicad_pcb` is different: it is a tracked, hand-authored SOURCE file, never
rebuilt, so there is no "freshly rebuilt, mtime is meaningful" story to fall
back to. A missing stamp here always means exactly what it says -- nobody
has ever attested this board content against a netlist -- so it fails
closed unconditionally, per this repo's stated fail-closed doctrine
(`check_netlist_board_reconciliation.py`: "never exits 0 unless it
positively confirms it ran a real check").

Exit codes:
  0 - PASSED: a stamp is present and its digest matches the board's and the
      netlist's current content.
  3 - VIOLATION: no stamp is present, or the stamp is stale (board and/or
      netlist content changed since the board was last verified and
      stamped) -- resync, re-run check_netlist_board_reconciliation.py
      until it passes, then run write_board_sync_stamp.py.
  5 - GATE ERROR: the board or netlist file is missing, or the netlist is
      not proven fresh against elec/src/**.

Usage:
  uv run python scripts/check_board_sync_stamp.py
  uv run python scripts/check_board_sync_stamp.py --board PATH --netlist PATH
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.freshness import compute_inputs_digest, read_stamp  # noqa: E402
from _lib.github_summary import get_github_summary_path  # noqa: E402
from _lib.repo import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root()
DEFAULT_BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"
DEFAULT_NETLIST = REPO_ROOT / "elec" / "build" / "default.net"
DEFAULT_SRC_DIR = REPO_ROOT / "elec" / "src"

EXIT_OK = 0
EXIT_VIOLATION = 3
EXIT_GATE_ERROR = 5


class GateError(Exception):
    """Fail-closed condition: this gate could not run a trustworthy check."""


def run(
    board_path: Path,
    netlist_path: Path,
    src_dir: Path,
    skip_freshness: bool = False,
    repo_root: Path = REPO_ROOT,
) -> int:
    from check_domain_partition import GateError as _DomainGateError
    from check_domain_partition import check_netlist_freshness

    gh = get_github_summary_path()

    try:
        if not board_path.is_file():
            raise GateError(f"board not found: {board_path}")
        if not netlist_path.is_file():
            raise GateError(
                f"netlist not found: {netlist_path} -- run `make netlist` first "
                "(elec/build/ is gitignored, so it must be built locally/in-CI, "
                "never assumed to already exist)"
            )
        # Both sides' freshness matters, not just their agreement: a stale
        # cached netlist could byte-match a stale stamp and this gate would
        # be none the wiser. See module docstring. `skip_freshness` exists
        # only for test fixtures that cannot easily backdate/order mtimes
        # (mirrors check_netlist_board_reconciliation.py's own flag).
        if not skip_freshness:
            check_netlist_freshness(netlist_path, src_dir)
    except (GateError, _DomainGateError) as exc:
        print("=== BOARD-SYNC STAMP GATE ERROR ===", file=sys.stderr)
        print(f"Reason: {exc}", file=sys.stderr)
        print(
            "GATE RESULT: ERROR -- not PASSED, not a violation. The gate "
            "could not run a trustworthy check.",
            file=sys.stderr,
        )
        if gh:
            with open(gh, "a") as f:
                f.write(f"### Board-Sync Stamp Gate -- GATE ERROR\n{exc}\n")
        return EXIT_GATE_ERROR

    print(f"Board: {board_path}")
    print(f"Netlist: {netlist_path} (freshness against {src_dir}: confirmed)")

    recorded = read_stamp(board_path)

    if recorded is None:
        print(
            "\nNo board-sync stamp found. This board carries no recorded "
            "provenance for which netlist it was last verified against.",
            file=sys.stderr,
        )
        print(
            "FAILED -- run `scripts/check_netlist_board_reconciliation.py`, "
            "resolve any findings, then `scripts/write_board_sync_stamp.py`.",
        )
        if gh:
            with open(gh, "a") as f:
                f.write(
                    "### Board-Sync Stamp Gate -- FAILED\n"
                    "No stamp found beside pcb/temper.kicad_pcb.\n"
                )
        return EXIT_VIOLATION

    current = compute_inputs_digest([board_path, netlist_path], repo_root)
    if current != recorded:
        print(
            f"\nSTALE: recorded digest {recorded[:12]}… does not match the "
            f"board's + netlist's current content digest {current[:12]}… -- "
            "the board and/or the netlist changed since this board was last "
            "verified and stamped.",
            file=sys.stderr,
        )
        print(
            "FAILED -- re-run `scripts/check_netlist_board_reconciliation.py`, "
            "resolve any findings, then `scripts/write_board_sync_stamp.py`.",
        )
        if gh:
            with open(gh, "a") as f:
                f.write(
                    "### Board-Sync Stamp Gate -- FAILED\n"
                    f"Stamp digest {recorded[:12]}… != current digest {current[:12]}…\n"
                )
        return EXIT_VIOLATION

    print(f"\nPASSED -- stamp digest {recorded[:12]}… matches current board + netlist content.")
    if gh:
        with open(gh, "a") as f:
            f.write(
                "### Board-Sync Stamp Gate -- PASSED\n"
                f"digest {recorded[:12]}…\n"
            )
    return EXIT_OK


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--board", type=Path, default=DEFAULT_BOARD)
    parser.add_argument("--netlist", type=Path, default=DEFAULT_NETLIST)
    parser.add_argument("--src-dir", type=Path, default=DEFAULT_SRC_DIR)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Root the stamp's digest paths are relativised against (test fixtures only; "
        "must match the --repo-root write_board_sync_stamp.py was run with).",
    )
    parser.add_argument(
        "--skip-freshness-check",
        action="store_true",
        help="Skip the netlist-vs-source staleness check (test fixtures only).",
    )
    args = parser.parse_args()

    sys.exit(
        run(
            args.board,
            args.netlist,
            args.src_dir,
            args.skip_freshness_check,
            args.repo_root,
        )
    )


if __name__ == "__main__":
    main()
