#!/usr/bin/env python3
"""CI entry point: closure test (Benders -> Router -> DRC).

Runs the full parse -> Benders placement -> Router V6 routing -> KiCad DRC pipeline.
Exits 0 if all assertions pass, non-zero on failure.
"""

import argparse
import os
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
    parser.add_argument("--metrics-dir", type=str, default=None, help="Directory for pipeline_metrics.jsonl")
    parser.add_argument(
        "--require-all-stages",
        action="store_true",
        default=False,
        help="Fail if any pipeline stage is skipped (promotes import/runtime warnings to errors)",
    )
    parser.add_argument(
        "--backend",
        type=str,
        default="python",
        choices=["python", "rust", "both"],
        help="DRC backend: 'python' (KiCad CLI, default), 'rust' (temper_drc_rs), or 'both' (run both and report discrepancies)",
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

    from temper_placer.pipeline.dag_observability import PipelineExecutionLog
    from temper_placer.pipeline.metrics_observer import MetricsObserver
    from temper_placer.regression.closure_test import ClosureTest

    seed = ClosureTest.load_seed(seed_path)
    test = ClosureTest(
        pcb_path=pcb_path,
        seed=seed,
        repo_root=repo_root,
        require_all_stages=args.require_all_stages,
    )

    # U2: Attach MetricsObserver for per-stage timing records
    metrics_dir = args.metrics_dir
    if metrics_dir:
        metrics_dir = os.path.abspath(metrics_dir)
    else:
        metrics_dir = str(
            repo_root / "power_pcb_dataset" / "metrics"
        )
    execution_log = PipelineExecutionLog()
    observer = MetricsObserver(
        metrics_dir,
        execution_log,
        board=pcb_path.stem,
    )
    result = test.run(_observer=observer)
    observer.on_pipeline_complete(
        success=result.passed,
        total_duration_s=result.wall_clock_seconds,
        stage_timings={},
    )

    print(result.summary())

    # ── Rust DRC backend (U9) ──────────────────────────────────────────
    # When --backend=rust or --backend=both, also run the Rust DRC engine
    # and report its violations alongside the KiCad results.
    rust_drc_errors = 0
    rust_drc_warnings = 0
    rust_drc_available = False
    if args.backend in ("rust", "both"):
        try:
            import temper_drc_rs  # type: ignore[import-untyped]

            rust_drc_available = True
        except ImportError as exc:
            msg = f"Rust DRC backend requested but temper_drc_rs not available: {exc}"
            print(f"WARNING: {msg}", file=sys.stderr)
            if args.backend == "rust":
                result.errors.append(msg)

        if rust_drc_available:
            try:
                # Build K1-schema board dict by parsing the PCB file
                from temper_placer.io.kicad_parser import parse_kicad_pcb_v6

                parsed = parse_kicad_pcb_v6(pcb_path)
                netlist = parsed.netlist

                components = []
                for c in netlist.components:
                    x, y = c.initial_position or (0.0, 0.0)
                    rotation = float(c.initial_rotation * 90) if c.initial_rotation is not None else 0.0
                    side = "bottom" if c.initial_side is not None and c.initial_side == 1 else "top"
                    components.append({
                        "ref": c.ref,
                        "x": x,
                        "y": y,
                        "rot": rotation,
                        "side": side,
                        "width": float(c.width),
                        "height": float(c.height),
                        "net_class": c.net_class,
                        "package_type": "smd",
                        "power_dissipation_w": None,
                        "is_magnetic": False,
                        "is_electrolytic": False,
                        "vent_direction": None,
                        "footprint_polygon": None,
                    })

                nets = {}
                net_classes = {}
                for net in netlist.nets:
                    comp_refs = list({ref for ref, _ in net.pins})
                    nets[net.name] = comp_refs
                    net_classes[net.name] = net.net_class

                board_dict = {
                    "board": {
                        "width_mm": float(parsed.board.width),
                        "height_mm": float(parsed.board.height),
                        "margin_mm": 3.0,
                    },
                    "components": components,
                    "nets": nets,
                    "net_classes": net_classes,
                    "net_class_rules": {},
                }

                constraints_dict = {
                    "clearances": [],
                    "hv_clearance_mm": 10.0,
                    "board_width": float(parsed.board.width),
                    "board_height": float(parsed.board.height),
                }

                violations = temper_drc_rs.run_drc(board_dict, constraints_dict)
                rust_drc_errors = sum(
                    1 for v in violations
                    if v.get("severity", "").upper() in ("ERROR", "CRITICAL")
                )
                rust_drc_warnings = sum(
                    1 for v in violations
                    if v.get("severity", "").upper() == "WARNING"
                )

                print(f"\n  Rust DRC: {rust_drc_errors} errors, {rust_drc_warnings} warnings")

                if args.backend == "both":
                    # Report discrepancies between KiCad and Rust DRC
                    kicad_errors = result.drc_errors
                    kicad_warnings = result.drc_warnings
                    if rust_drc_errors != kicad_errors or rust_drc_warnings != kicad_warnings:
                        diff_msg = (
                            f"DRC discrepancy: KiCad ({kicad_errors}e/{kicad_warnings}w) "
                            f"vs Rust ({rust_drc_errors}e/{rust_drc_warnings}w)"
                        )
                        print(f"  NOTE: {diff_msg}")
                        result.warnings.append(diff_msg)

            except Exception as exc:
                msg = f"Rust DRC backend failed: {exc}"
                print(f"WARNING: {msg}", file=sys.stderr)
                if args.backend == "rust":
                    result.errors.append(msg)

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
                    "rust_drc_errors": rust_drc_errors,
                    "rust_drc_warnings": rust_drc_warnings,
                    "rust_drc_available": rust_drc_available,
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
