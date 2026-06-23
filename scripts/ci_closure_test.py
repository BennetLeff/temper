#!/usr/bin/env python3
"""CI entry point: closure test (Benders -> Router -> DRC).

Runs the full parse -> Benders placement -> Router V6 routing -> KiCad DRC pipeline.
Exits 0 if all assertions pass, non-zero on failure.
"""

import argparse
import sys
from pathlib import Path


def _find_repo_root() -> Path:
    p = Path.cwd()
    while not (p / ".git").exists() and p != p.parent:
        p = p.parent
    return p


def _setup_path(repo_root: Path) -> None:
    import sys

    src_path = repo_root / "packages" / "temper-placer" / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Benders->Router closure test")
    parser.add_argument("--pcb", type=str, required=True, help="Path to input .kicad_pcb file")
    parser.add_argument("--seed", type=str, default=None, help="Path to seed.json file")
    parser.add_argument("--output", type=str, default=None, help="Output path for JSON summary")
    parser.add_argument(
        "--require-all-stages",
        action="store_true",
        default=False,
        help="Fail if any pipeline stage is skipped (promotes import/runtime warnings to errors)",
    )
    args = parser.parse_args()

    repo_root = _find_repo_root()
    _setup_path(repo_root)
    pcb_path = Path(args.pcb)
    if not pcb_path.is_absolute():
        pcb_path = repo_root / pcb_path

    if not pcb_path.exists():
        print(f"PCB file not found: {pcb_path}", file=sys.stderr)
        return 1

    if args.seed:
        seed_path = Path(args.seed)
    else:
        seed_path = repo_root / "packages" / "temper-placer" / "src" / "temper_placer" / "regression" / "seed.json"

    from temper_placer.regression.closure_test import ClosureTest

    seed = ClosureTest.load_seed(seed_path)
    test = ClosureTest(
        pcb_path=pcb_path,
        seed=seed,
        repo_root=repo_root,
        require_all_stages=args.require_all_stages,
    )
    result = test.run()

    print(result.summary())

    if args.output:
        import json

        output_path = Path(args.output)
        with open(output_path, "w") as f:
            json.dump(
                {
                    "passed": result.passed,
                    "board_id": result.board_id,
                    "benders_iterations": result.benders_iterations,
                    "benders_cuts": result.benders_cuts,
                    "router_completion_pct": result.router_completion_pct,
                    "drc_errors": result.drc_errors,
                    "drc_warnings": result.drc_warnings,
                    "wall_clock_seconds": result.wall_clock_seconds,
                    "stages_exercised": result.stages_exercised,
                    "errors": result.errors,
                    "warnings": result.warnings,
                },
                f,
                indent=2,
            )

    return 0 if result.passed else 1


if __name__ == "__main__":
    sys.exit(main())
