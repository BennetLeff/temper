#!/usr/bin/env python3
"""Netlist-mutation corpus runner (plan 2026-08-02-021, R39 / U7).

A standing check that applies the R39 mutation classes -- wholesale
renumbering, dropped nets, reused refdes -- to a copy of the compiled design
netlist (``elec/build/default.net``) and proves each class fails its owning
identity check, while the clean netlist passes every check (anti-vacuity).
This is the corpus-runner shape shared with the R38 board-defect corpus and
the R19 incident corpus: per-class expected-failing check, anti-vacuity
control on the clean artifact, fail-closed on a missing tool or stale input.

Class-to-check table (the corpus's contract -- a class with no owning check
fails the run as uncovered):

  class           mutation        owning check (must FAIL)
  --------------  --------------  -------------------------------------------
  renumber        renumber        sheetpath oracle: RENUMBERED finding
                                   AND the 95% refdes-overlap check must PASS
                                   (the headline proof: the overlap check is
                                   structurally blind to a set-preserving
                                   permutation -- it never looks at what moved
                                   WHERE, only whether the same names mostly
                                   still exist)
  dropped-net     drop-net        net-level membership: NET-MEMBERSHIP finding
                                   naming the net whose nodes vanished
  reused-refdes   reuse           REUSE finding naming the ref shared by two
                                   components

The identity check set run against every netlist (clean and mutated):
  1. ``preflight_identity``     -- the 95% refdes-overlap boundary (secondary
     signal; the renumber class must PASS it, documenting the blind spot)
  2. ``run_all_preflight_checks`` -- the preflight surface, which now embeds
     the reconciliation oracle as its identity authority
  3. the U2/U3 reconciliation   -- the sheetpath/net-membership oracle itself

Fail-closed contract (METHODOLOGY.md Sec 4/5): never exits 0 unless it
positively confirms every class bit and the clean netlist passed. Exits
non-zero for every one of:
  - the board file is missing or fails to parse
  - the netlist file is missing, empty, or fails to parse
  - the netlist is STALE (older than any elec/src/*.ato file)
  - the ``temper_design_bundle_python`` extension (preflight_identity's
    boundary) is not importable -- a missing tool is a GATE ERROR, not a pass
  - a mutation cannot be applied (fewer than 2 components, no droppable net)
  - the clean netlist fails any identity check (anti-vacuity broken)
  - any mutation class's owning check does not fail (uncovered class)

Exit codes:
  0 - PASSED: all three classes bite, clean netlist passes every check
  3 - VIOLATION: an uncovered class, or the clean netlist failed a check
  5 - GATE ERROR: the corpus could not run a trustworthy check at all

Usage:
  uv run python scripts/check_netlist_mutation_corpus.py
  uv run python scripts/check_netlist_mutation_corpus.py --board PATH --netlist PATH
"""

from __future__ import annotations

import argparse
import sys
import tempfile
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

RENUMBER_SEED = 7
DROP_NET_SEED = 3
REUSE_SEED = 11

#: Class-to-check table -- the corpus's contract (see module docstring).
#: ``owning_kinds`` are the reconciliation finding kinds that prove the class
#: bites; ``overlap_must_pass`` marks the headline renumber proof.
MUTATION_CLASSES: dict[str, dict] = {
    "renumber": {
        "mutation": "renumber",
        "seed": RENUMBER_SEED,
        "owning_kinds": ("RENUMBERED",),
        "overlap_must_pass": True,
    },
    "dropped-net": {
        "mutation": "drop-net",
        "seed": DROP_NET_SEED,
        "owning_kinds": ("NET-MEMBERSHIP",),
        "overlap_must_pass": False,
    },
    "reused-refdes": {
        "mutation": "reuse",
        "seed": REUSE_SEED,
        "owning_kinds": ("REUSE",),
        "overlap_must_pass": False,
    },
}


def evaluate_netlist(board_path: Path, netlist_path: Path) -> dict:
    """Run the identity check set (overlap, preflight surface, reconciliation
    oracle) against one netlist file and return structured outcomes:

    ``{"overlap": {"passed": bool, "error": str|None},
        "preflight": {"passed": bool, "error": str|None},
        "reconciliation": {"passed": bool, "findings": list[str], "error": str|None}}``

    The three legs never raise: every failure mode is captured in the outcome
    (an unimportable Rust extension or an unparseable netlist lands in
    ``error`` with ``passed`` False), so the corpus can distinguish 'check
    failed' from 'check could not run' at the top level.
    """
    outcome: dict = {
        "overlap": {"passed": False, "error": None},
        "preflight": {"passed": False, "error": None},
        "reconciliation": {"passed": False, "findings": [], "error": None},
    }

    # Leg 1: preflight_identity (95% refdes-overlap boundary).
    try:
        from temper_placer.io.design_bundle_preflight import preflight_identity

        preflight_identity(board_path, netlist_path)
        outcome["overlap"]["passed"] = True
    except Exception as exc:  # noqa: BLE001 -- every failure is captured, never raised
        outcome["overlap"]["error"] = str(exc)

    # Leg 2: run_all_preflight_checks with the reconciliation embedded.
    try:
        from temper_placer.validation.preflight import run_all_preflight_checks

        result = run_all_preflight_checks(
            None,
            None,
            check_tools=False,
            board_path=board_path,
            design_netlist_path=netlist_path,
        )
        outcome["preflight"]["passed"] = result.passed
        if not result.passed:
            outcome["preflight"]["error"] = "; ".join(
                i.code for i in result.issues if i.severity.name == "ERROR"
            )
    except Exception as exc:  # noqa: BLE001
        outcome["preflight"]["error"] = f"preflight surface raised: {exc}"

    # Leg 3: the U2/U3 reconciliation oracle directly.
    try:
        from temper_placer.validation.netlist_reconciliation import (
            extract_board_netlist,
            parse_design_netlist,
            reconcile,
        )

        report = reconcile(
            extract_board_netlist(board_path), parse_design_netlist(netlist_path)
        )
        outcome["reconciliation"]["passed"] = report.passed
        outcome["reconciliation"]["findings"] = [f.kind for f in report.findings]
    except Exception as exc:  # noqa: BLE001
        outcome["reconciliation"]["error"] = str(exc)

    return outcome


def run_corpus(
    board_path: Path,
    netlist_path: Path,
    src_dir: Path,
    skip_freshness: bool = False,
    seed_overrides: dict[str, int] | None = None,
) -> int:
    from check_domain_partition import check_netlist_freshness
    from netlist_mutator import (
        MutatorError,
        load_netlist,
        mutate_drop_net,
        mutate_renumber,
        mutate_reuse_refdes,
        pick_droppable_net,
        write_netlist,
    )

    errors: list[str] = []

    try:
        if not skip_freshness:
            check_netlist_freshness(netlist_path, src_dir)
        clean = load_netlist(netlist_path)
        if not clean.components or not clean.nets:
            raise MutatorError(
                "netlist has zero components or zero nets -- nothing to mutate"
            )

        clean_outcome = evaluate_netlist(board_path, netlist_path)
        clean_ok = (
            clean_outcome["overlap"]["passed"]
            and clean_outcome["preflight"]["passed"]
            and clean_outcome["reconciliation"]["passed"]
        )
    except Exception as exc:  # noqa: BLE001 -- fail closed on any setup failure
        return _gate_error(f"corpus could not run: {exc}", errors)

    if not clean_ok:
        print("=== NETLIST-MUTATION CORPUS: ANTI-VACUITY FAILURE ===", file=sys.stderr)
        print("The CLEAN netlist failed an identity check:", file=sys.stderr)
        for leg, label in (
            ("overlap", "refdes-overlap check"),
            ("preflight", "preflight surface"),
            ("reconciliation", "reconciliation oracle"),
        ):
            status = clean_outcome[leg]
            print(f"  {label}: passed={status['passed']}", file=sys.stderr)
            if status.get("error"):
                print(f"    {status['error']}", file=sys.stderr)
        return _violation("anti-vacuity: the clean netlist failed an identity check", errors)

    gh = get_github_summary_path()
    print(f"Board: {board_path}")
    print(f"Netlist: {netlist_path}")
    print(
        f"Clean netlist: {len(clean.components)} component(s), {len(clean.nets)} net(s) "
        "-- every identity check passed (anti-vacuity control green)."
    )
    if gh:
        with open(gh, "a") as f:
            f.write("### Netlist-Mutation Corpus\n")
            f.write("Clean netlist passed every identity check (anti-vacuity).\n")

    seeds = dict(seed_overrides or {})

    with tempfile.TemporaryDirectory(prefix="netlist-corpus-") as tmpdir:
        tmp = Path(tmpdir)
        for class_name, spec in sorted(MUTATION_CLASSES.items()):
            mutation = spec["mutation"]
            seed = seeds.get(class_name, spec["seed"])
            mutated_path = tmp / f"{class_name}.net"
            try:
                mutated = load_netlist(netlist_path)
                if mutation == "renumber":
                    mutated, summary = mutate_renumber(mutated, seed)
                elif mutation == "drop-net":
                    net_name = pick_droppable_net(mutated, seed)
                    mutated, summary = mutate_drop_net(mutated, net_name)
                elif mutation == "reuse":
                    mutated, summary = mutate_reuse_refdes(mutated, seed)
                else:  # pragma: no cover -- table is module-local
                    raise MutatorError(f"unknown mutation {mutation!r}")
                write_netlist(mutated, mutated_path)
            except Exception as exc:  # noqa: BLE001
                return _gate_error(
                    f"class {class_name!r}: mutation could not be applied: {exc}", errors
                )

            outcome = evaluate_netlist(board_path, mutated_path)

            owning_kinds = spec["owning_kinds"]
            fired = [k for k in owning_kinds if k in outcome["reconciliation"]["findings"]]
            overlap_ok = outcome["overlap"]["passed"]
            preflight_failed = not outcome["preflight"]["passed"]

            problems: list[str] = []
            if not fired:
                problems.append(
                    f"owning finding {owning_kinds} did not fire "
                    f"(findings: {outcome['reconciliation']['findings'] or 'none'})"
                )
            if spec.get("overlap_must_pass") and not overlap_ok:
                problems.append(
                    f"overlap check must PASS for this class but failed: "
                    f"{outcome['overlap'].get('error')}"
                )
            if not preflight_failed:
                problems.append("preflight surface did not fail on the mutated netlist")

            summary_line = (
                f"[{class_name}] mutation={mutation} seed={seed} -- "
                f"reconciliation findings: "
                f"{', '.join(sorted(set(outcome['reconciliation']['findings']))) or 'none'}"
            )
            if not problems:
                print(f"  PASS  {summary_line}")
                if class_name == "renumber":
                    print(
                        "        (headline proof: the 95% refdes-overlap check "
                        "PASSED while the sheetpath oracle reported "
                        f"{len(outcome['reconciliation']['findings'])} RENUMBERED finding(s))"
                    )
                if gh:
                    with open(gh, "a") as f:
                        f.write(f"- PASS `{class_name}` -- {summary_line}\n")
            else:
                print(f"  FAIL  {summary_line}")
                for problem in problems:
                    print(f"        {problem}")
                errors.append(f"class {class_name!r}: {problems[0]}")

    if errors:
        return _violation("; ".join(errors), errors)
    print("\nPASSED -- all 3 mutation classes bite; clean netlist green.")
    return EXIT_OK


def _violation(message: str, errors: list[str]) -> int:
    print(f"\nCORPUS RESULT: FAILED ({message})", file=sys.stderr)
    gh = get_github_summary_path()
    if gh:
        with open(gh, "a") as f:
            f.write("### Netlist-Mutation Corpus -- FAILED\n")
            f.write(f"{message}\n")
    return EXIT_VIOLATION


def _gate_error(message: str, errors: list[str]) -> int:
    print("=== NETLIST-MUTATION CORPUS GATE ERROR ===", file=sys.stderr)
    print(f"Reason: {message}", file=sys.stderr)
    print(
        "GATE RESULT: ERROR -- not PASSED, not a violation. The corpus could "
        "not run a trustworthy check.",
        file=sys.stderr,
    )
    gh = get_github_summary_path()
    if gh:
        with open(gh, "a") as f:
            f.write("### Netlist-Mutation Corpus -- GATE ERROR\n")
            f.write(f"{message}\n")
    return EXIT_GATE_ERROR


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
    sys.exit(run_corpus(args.board, args.netlist, args.src_dir, args.skip_freshness_check))


if __name__ == "__main__":
    main()
