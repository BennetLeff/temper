#!/usr/bin/env python3
"""Placement subprocess for the ``temper`` Rust driver (endgame Option E).

The Rust binary must not depend on pyo3, so CP-SAT stays a Python
subprocess behind a thin script boundary: this script takes a board and a
constraints YAML, calls ``solve_placement()`` (the single plain-dataclass
solve entry point from ``temper_placer.placer.cp_sat._encoder_solve`` —
no ortools types leak past it), and writes the result as JSON.

This is the exact shape the endgame assessment recommends
(``docs/evidence/2026-08-11-rust-driver-endgame-assessment.md``, Option E):
the solver call is the irreducible Python, and the driver orchestrates it.

Usage:
    uv run --no-sync python3 scripts/_placement_subprocess.py \
        --pcb pcb/temper.kicad_pcb \
        --constraints packages/temper-placer/configs/constraints/temper_induction_cooker.yaml \
        --output-json /tmp/placement.json

Exit codes: 0 = solve ran and JSON was written; 1 = hard failure (unparseable
board, unreadable constraints, or solve raised); 2 = solve returned an
infeasible/unknown status (still writes JSON — the driver decides).
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--pcb", type=Path, required=True, help="Path to .kicad_pcb")
    parser.add_argument(
        "--constraints",
        type=Path,
        required=True,
        help="Path to constraints YAML (load_constraints-compatible)",
    )
    parser.add_argument(
        "--output-json", type=Path, required=True, help="Where to write the result JSON"
    )
    parser.add_argument(
        "--timeout-ms", type=int, default=30_000,
        help="CP-SAT solve timeout in ms (default 30000)",
    )
    parser.add_argument("--seed", type=int, default=0, help="CP-SAT random seed (default 0)")
    args = parser.parse_args(argv)

    if not args.pcb.is_file():
        print(f"_placement_subprocess: no such pcb: {args.pcb}", file=sys.stderr)
        return 1
    if not args.constraints.is_file():
        print(f"_placement_subprocess: no such constraints: {args.constraints}", file=sys.stderr)
        return 1

    from temper_placer.io.config_loader import load_constraints
    from temper_placer.io.kicad_parser import parse_kicad_pcb
    from temper_placer.placer.cp_sat._encoder_solve import solve_placement

    parse_result = parse_kicad_pcb(args.pcb)
    netlist = parse_result.netlist
    board = parse_result.board
    if board is None:
        print("_placement_subprocess: board geometry parsing failed", file=sys.stderr)
        return 1

    constraints = load_constraints(args.constraints)
    pcl_constraints = list(getattr(constraints, "pcl_constraints", []))

    # Mirror the CLI's --no-loop wiring (cli/__init__.py optimize): a
    # `.references.yaml` manifest beside the constraints file reconciles
    # legacy config names against the live netlist/loops. Without it the
    # solver fails closed on UnresolvedConstraintRefsError for every
    # config that predates the current board's designators.
    reference_aliases: dict[str, str] = {}
    loop_aliases: dict[str, str] = {}
    manifest_path = args.constraints.with_suffix(".references.yaml")
    if manifest_path.is_file():
        from temper_io_types import load_reference_alias_manifest

        from temper_placer.placer.cp_sat._encoder_solve import _resolve_loop_components

        loop_names = _resolve_loop_components(netlist)
        manifest = load_reference_alias_manifest(
            manifest_path,
            component_refs=[component.ref for component in netlist.components],
            loop_names=loop_names,
        )
        reference_aliases = manifest.component_aliases
        loop_aliases = manifest.loop_aliases

    result = solve_placement(
        netlist=netlist,
        board=board,
        extra_constraints=pcl_constraints,
        timeout_ms=args.timeout_ms,
        seed=args.seed,
        reference_aliases=reference_aliases or None,
        loop_aliases=loop_aliases or None,
    )

    payload = dataclasses.asdict(result)
    # The report objects are only populated when their opt-in inputs are
    # passed; asdict leaves them as their default None. Strip any non-JSON
    # members defensively so a future non-None default cannot break the wire.
    payload = {k: v for k, v in payload.items() if v is not None}

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        f"_placement_subprocess: status={result.status} "
        f"placed={len(result.positions)} unplaced={len(result.unplaced_refs)} "
        f"solve_time_ms={result.solve_time_ms:.0f} -> {args.output_json}"
    )
    # Non-zero only for hard failures; infeasible is a valid solve outcome.
    return 0


if __name__ == "__main__":
    sys.exit(main())
