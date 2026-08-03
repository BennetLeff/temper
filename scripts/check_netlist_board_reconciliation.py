#!/usr/bin/env python3
"""Netlist <-> board reconciliation gate (plan 2026-08-02-021, R16).

Compares the netlist extracted from the actual board file
(``pcb/temper.kicad_pcb``) against the compiled design netlist
(``elec/build/default.net``) keyed by INSTANCE PATH and NET MEMBERSHIP -- not
by reference designator. This is the identity authority the board maintainer
actually trusts: ``preflight_identity``'s 95% refdes-overlap check passes a
wholesale renumber by construction (a permutation of the same refdes set) and
is blind to a reused designator (board ``C27`` = ``tank.c_tank3`` vs the
netlist's ``C27`` = ``ct_sense.c_filter``: one ref, two components). This gate
reports, per component path and per net:

  - MISSING       -- design component with no board footprint (the
                     tank-capacitor class; on the CURRENT board this is
                     PASS-for-missing: ``tank.c_tank3`` IS in the board file,
                     staged off-outline -- the off-board staging is a
                     containment defect owned by the R26 plan)
  - EXTRA         -- board footprint with no design counterpart
  - RENUMBERED    -- same path, different refs on each side
  - REUSE         -- one ref naming two components, on either side
  - UNKEYABLE     -- board footprint with no Sheetpath property
  - NET-MISSING   -- design net (non-empty) with no board counterpart
  - NET-EXTRA     -- board net with no design counterpart
  - NET-MEMBERSHIP -- net on both sides with differing component membership
                     (the owning finding of the R39 dropped-net class)

Fail-closed contract (METHODOLOGY.md Sec 4/5), matching
check_domain_partition.py / check_footprint_drift.py: never exits 0 unless it
positively confirms it ran a real check on real, fresh, non-empty data. Exits
non-zero for every one of:
  - the board file is missing or fails to parse
  - the netlist file is missing, empty, or fails to parse
  - the netlist is STALE (older than any elec/src/*.ato file, or its content
    hash no longer matches the sources' -- see check_domain_partition.py)
  - the netlist has zero components, or the board has zero footprints
  - two components on either side share an instance path (identity ambiguous)

No allowlist: every finding here is a real board/netlist disagreement to be
resolved by a resync, never a false positive to waive.

Exit codes:
  0 - PASSED: 0 findings across a real, fresh, non-empty check
  3 - VIOLATION: at least one reconciliation finding
  5 - GATE ERROR: the gate could not run a trustworthy check at all

Usage:
  uv run python scripts/check_netlist_board_reconciliation.py
  uv run python scripts/check_netlist_board_reconciliation.py --board PATH --netlist PATH
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parent.parent
        / "packages"
        / "temper-placer"
        / "src"
    ),
)

from _lib.github_summary import get_github_summary_path  # noqa: E402
from _lib.repo import find_repo_root  # noqa: E402

REPO_ROOT = find_repo_root()
DEFAULT_BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"
DEFAULT_NETLIST = REPO_ROOT / "elec" / "build" / "default.net"
DEFAULT_SRC_DIR = REPO_ROOT / "elec" / "src"

EXIT_OK = 0
EXIT_VIOLATION = 3
EXIT_GATE_ERROR = 5


def run(
    board_path: Path,
    netlist_path: Path,
    src_dir: Path,
    skip_freshness: bool = False,
) -> int:
    from check_domain_partition import GateError as _DomainGateError  # the canonical freshness gate
    from check_domain_partition import check_netlist_freshness

    from temper_placer.validation.netlist_reconciliation import (
        ReconciliationGateError,
        extract_board_netlist,
        parse_design_netlist,
        reconcile,
    )

    try:
        if not skip_freshness:
            check_netlist_freshness(netlist_path, src_dir)
        board = extract_board_netlist(board_path)
        design = parse_design_netlist(netlist_path)

        # Anti-vacuous-truth: re-assert non-empty data before any verdict is
        # trusted (already guaranteed by extract/parse raising on empty input;
        # re-asserted so a future refactor cannot silently drop that contract).
        if len(board.components) == 0:
            raise ReconciliationGateError("no footprints on board (should have been caught earlier)")
        if len(design.components) == 0:
            raise ReconciliationGateError(
                "no components in netlist (should have been caught earlier)"
            )

        report = reconcile(board, design)
    except (ReconciliationGateError, _DomainGateError) as exc:
        print("=== NETLIST-BOARD RECONCILIATION GATE ERROR ===", file=sys.stderr)
        print(f"Reason: {exc}", file=sys.stderr)
        print(
            "GATE RESULT: ERROR -- not PASSED, not a violation. The gate "
            "could not run a trustworthy check.",
            file=sys.stderr,
        )
        gh = get_github_summary_path()
        if gh:
            with open(gh, "a") as f:
                f.write("### Netlist-Board Reconciliation Gate -- GATE ERROR\n")
                f.write(f"{exc}\n")
        return EXIT_GATE_ERROR

    print(f"Board: {board_path}")
    print(f"Netlist: {netlist_path}")
    print(
        f"Components: {len(design.components)} in netlist, "
        f"{len(board.components)} on board, {report.matched_paths} matched by "
        f"instance path. Nets: {report.design_nets_nonempty} design / "
        f"{report.board_nets} board."
    )

    gh = get_github_summary_path()

    if report.passed:
        print(f"\nPASSED -- 0 findings across {report.matched_paths} matched component(s).")
        print(
            "(tank-capacitor class: PASS-for-missing -- tank.c_tank3 IS present "
            "in the board file, staged off-outline; the off-board staging is a "
            "containment defect owned by the R26 plan)"
        )
        if gh:
            with open(gh, "a") as f:
                f.write("### Netlist-Board Reconciliation Gate -- PASSED\n")
                f.write(
                    f"0 findings across {report.matched_paths} matched component(s).\n"
                )
        return EXIT_OK

    by_kind: dict[str, list] = {}
    for finding in report.findings:
        by_kind.setdefault(finding.kind, []).append(finding)

    print(f"\n=== FINDINGS: {len(report.findings)} ===")
    gh_lines: list[str] = []
    for kind, findings in sorted(by_kind.items()):
        print(f"\n  [{kind}] {len(findings)} finding(s):")
        for f in findings:
            print(f"    {f.detail}")
            gh_lines.append(f"- `[{kind}]` {f.detail}")

    if gh:
        with open(gh, "a") as f:
            f.write("### Netlist-Board Reconciliation Gate -- FAILED\n")
            f.write(f"{len(report.findings)} finding(s)\n\n")
            for line in gh_lines[:200]:
                f.write(line + "\n")

    print(f"\nFAILED -- {len(report.findings)} finding(s)")
    return EXIT_VIOLATION


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--board", type=Path, default=DEFAULT_BOARD)
    parser.add_argument("--netlist", type=Path, default=DEFAULT_NETLIST)
    parser.add_argument("--src-dir", type=Path, default=DEFAULT_SRC_DIR)
    parser.add_argument(
        "--skip-freshness-check",
        action="store_true",
        help="Skip the netlist-vs-source staleness check (test fixtures only).",
    )
    args = parser.parse_args()
    sys.exit(run(args.board, args.netlist, args.src_dir, args.skip_freshness_check))


if __name__ == "__main__":
    main()
