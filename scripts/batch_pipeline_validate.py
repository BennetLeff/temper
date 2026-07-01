#!/usr/bin/env python3
"""Batch pipeline validation — feed corpus boards through parse→placement→route.

Reads benchmarks/downloads_digital_iot/manifest.yaml, runs each parseable
board through a lightweight placement test, and quarantines failures.

Usage:
    uv run python scripts/batch_pipeline_validate.py [--max-boards N] [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import yaml


def run_placement(board_path: Path) -> dict:
    from temper_placer.io.kicad_parser import parse_kicad_pcb

    result: dict = {
        "board_id": str(board_path.name),
        "path": str(board_path),
        "stage": "placement",
        "success": False,
        "wall_time_ms": 0,
        "components": 0,
        "nets": 0,
        "error": None,
    }

    t0 = time.perf_counter()
    try:
        parsed = parse_kicad_pcb(board_path)
        netlist = parsed.netlist
        board = parsed.board
        result["components"] = netlist.n_components
        result["nets"] = netlist.n_nets

        try:
            from temper_placer.losses import (
                BoundaryLoss, CompositeLoss, OverlapLoss, WeightedLoss, WirelengthLoss,
            )
            from temper_placer.losses.base import LossContext
            from temper_placer.optimizer import OptimizerConfig, train

            composite = CompositeLoss([
                WeightedLoss(WirelengthLoss(), weight=1.0),
                WeightedLoss(OverlapLoss(), weight=10.0),
                WeightedLoss(BoundaryLoss(), weight=5.0),
            ])
            context = LossContext.from_netlist_and_board(netlist, board)
            config = OptimizerConfig.fast_test()
            config.epochs = 5  # minimal for validation

            train_result = train(netlist, board, composite, context, config)
            result["success"] = (
                hasattr(train_result, "best_state")
                and train_result.best_state is not None
            )
        except ImportError as e:
            result["stage"] = "placement_unavailable"
            result["error"] = str(e)
        except Exception as e:
            result["error"] = f"{type(e).__name__}: {e}"

    except ImportError as e:
        result["stage"] = "parse_unavailable"
        result["error"] = str(e)
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"

    result["wall_time_ms"] = round((time.perf_counter() - t0) * 1000)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch pipeline validation")
    parser.add_argument("--max-boards", type=int, default=0, help="Limit boards (0=all)")
    parser.add_argument("--dry-run", action="store_true", help="Print what would run")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("benchmarks/downloads_digital_iot/manifest.yaml"),
    )
    parser.add_argument(
        "--quarantine-dir",
        type=Path,
        default=Path("power_pcb_dataset/quarantine"),
    )
    args = parser.parse_args()

    if not args.manifest.exists():
        print(f"ERROR: manifest not found: {args.manifest}", file=sys.stderr)
        print("Run 'uv run python scripts/scan_external_corpus.py' first.", file=sys.stderr)
        sys.exit(1)

    with open(args.manifest) as f:
        manifest = yaml.safe_load(f)

    boards = manifest.get("boards", [])
    parseable = [b for b in boards if b.get("parse_success")]

    if args.max_boards > 0:
        parseable = parseable[: args.max_boards]

    print(f"Manifest: {len(boards)} total, {len(parseable)} parseable")
    print(f"Running placement on {len(parseable)} boards...")
    if args.dry_run:
        for b in parseable:
            print(f"  would run: {b['id']} ({b['components']} comps, {b.get('nets', 0)} nets)")
        return

    from temper_placer.testing.quarantine import quarantine_error

    success = 0
    failed = 0
    quarantined = 0

    t_start = time.perf_counter()
    for i, board in enumerate(parseable):
        pcb_path = Path(board["pcb"])
        if not pcb_path.exists():
            print(f"[{i+1}/{len(parseable)}] {board['id']} SKIP (file not found)", flush=True)
            continue

        print(f"[{i+1}/{len(parseable)}] {board['id']} ... ", end="", flush=True)
        result = run_placement(pcb_path)

        if result["success"]:
            success += 1
            print(f"OK ({result['wall_time_ms']}ms)", flush=True)
        else:
            failed += 1
            error_msg = result.get("error", "unknown")
            print(f"FAIL: {error_msg}", flush=True)

            try:
                raise RuntimeError(error_msg)
            except RuntimeError as e:
                quarantine_error(
                    args.quarantine_dir,
                    board["id"],
                    pcb_path,
                    result["stage"],
                    e,
                )
                quarantined += 1

    t_elapsed = time.perf_counter() - t_start
    print(f"\nResults: {success} OK, {failed} failed, {quarantined} quarantined")
    print(f"Total time: {t_elapsed:.0f}s ({t_elapsed / max(len(parseable), 1):.1f}s avg)")

    if args.quarantine_dir.exists():
        from temper_placer.testing.quarantine import quarantine_summary
        print(f"\n{quarantine_summary(args.quarantine_dir)}")


if __name__ == "__main__":
    main()
