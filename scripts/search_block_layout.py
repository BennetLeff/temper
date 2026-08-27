#!/usr/bin/env python3
"""Bounded rigid-block floorplan search with router-in-the-loop evaluation.

Rust owns the finite translation schedule, safety verdict, and final candidate
selection.  This file is the thin adapter for KiCad board serialization and
the production router.  By default it performs only the cheap geometric
preflight; ``--route`` spends the separately-capped routing budget.
"""

from __future__ import annotations

# ruff: noqa: E402
import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import evaluate_regional_layout as regional
import measure_cross_domain_creepage as creepage
import route_board
import temper_design_bundle_python as _tdb
import temper_quality_oracle as quality

from temper_placer.io.kicad_writer import PlacementUpdate, write_placements_to_pcb

DEFAULT_BOARD = REPO_ROOT / "pcb" / "temper.kicad_pcb"
DEFAULT_RULES = REPO_ROOT / "packages/temper-placer/configs/netclass_rules.yaml"


def _positions(board: Path) -> dict[str, tuple[float, float, float]]:
    info = _tdb.parse_engine.extract_footprint_info_py(board.read_text(encoding="utf-8"))
    return {
        str(item["ref"]): (float(item["x"]), float(item["y"]), float(item["angle"]))
        for item in info
        if item["ref"]
    }


def _pair_set(board: Path, manifest: Path, threshold_mm: float) -> set[str]:
    identities = regional._stable_ref_map(board)
    report, _, _ = creepage.measure(board, manifest, threshold_mm)
    if report.pairs_examined == 0:
        raise RuntimeError(f"{board}: cross-domain preflight examined zero pairs")
    return {
        regional._stable_pair_label(f"{item.hv.label}<->{item.selv.label}", identities)
        for item in report.violations
    }


def _preflight(
    baseline_pairs: set[str],
    baseline_bodies: dict[str, float],
    candidate: Path,
    manifest: Path,
    threshold_mm: float,
) -> dict:
    pairs = _pair_set(candidate, manifest, threshold_mm)
    bodies = regional._body_overlaps(candidate)
    # DRC and connectivity are deliberately neutral here: committed copper
    # still terminates at the old block position until the router runs.
    return dict(
        quality.evaluate_regional_candidate_py(
            sorted(baseline_pairs),
            sorted(pairs),
            {},
            {},
            baseline_bodies,
            bodies,
            [],
            [],
            [],
            [],
            0.01,
            [],
        )
    )


def _copy_board_context(board: Path, destination: Path) -> Path:
    """Copy the full KiCad sibling context required by DRC and routing."""
    copied = destination / "pcb"
    shutil.copytree(board.parent, copied)
    return copied / board.name


def search(
    board: Path,
    manifest: Path,
    rules: Path,
    refs: list[str],
    *,
    step_mm: float,
    max_rings: int,
    max_candidates: int,
    max_routed_candidates: int,
    threshold_mm: float,
    bounds: tuple[float, float, float, float],
    route: bool,
) -> dict:
    if not refs:
        raise ValueError("at least one --ref is required")
    positions = _positions(board)
    missing = sorted(set(refs) - positions.keys())
    if missing:
        raise ValueError(f"block references absent from board: {', '.join(missing)}")

    baseline_pairs = _pair_set(board, manifest, threshold_mm)
    baseline_bodies = regional._body_overlaps(board)
    schedule = quality.block_translation_schedule_py(step_mm, max_rings, max_candidates)
    xmin, ymin, xmax, ymax = bounds
    records: list[dict] = []
    routed_for_rust: list[tuple] = []

    with tempfile.TemporaryDirectory(prefix="temper-block-search-") as raw_tmp:
        candidate_board = _copy_board_context(board, Path(raw_tmp))
        routed_count = 0
        for candidate_id, (dx, dy, ring) in enumerate(schedule, start=1):
            moved = {
                ref: PlacementUpdate(ref, x + dx, y + dy, angle)
                for ref, (x, y, angle) in positions.items()
                if ref in refs
            }
            if any(
                not (xmin <= update.x <= xmax and ymin <= update.y <= ymax)
                for update in moved.values()
            ):
                records.append(
                    {
                        "candidate_id": candidate_id,
                        "dx_mm": dx,
                        "dy_mm": dy,
                        "ring": ring,
                        "preflight_accepted": False,
                        "reasons": ["translated block origin leaves configured floorplan bounds"],
                    }
                )
                continue

            write_placements_to_pcb(board, candidate_board, moved)
            preflight = _preflight(
                baseline_pairs, baseline_bodies, candidate_board, manifest, threshold_mm
            )
            record = {
                "candidate_id": candidate_id,
                "dx_mm": dx,
                "dy_mm": dy,
                "ring": ring,
                "preflight_accepted": bool(preflight["accepted"]),
                "removed_cross_domain_pairs": len(preflight["removed_cross_domain_pairs"]),
                "new_cross_domain_pairs": preflight["new_cross_domain_pairs"],
                "new_or_worsened_body_pairs": preflight["new_or_worsened_body_pairs"],
                "reasons": list(preflight["reasons"]),
            }
            records.append(record)
            if not route or not preflight["accepted"] or routed_count >= max_routed_candidates:
                continue

            routed_count += 1
            routed = route_board.route_once(candidate_board, rules)
            content = routed.get("routed_pcb_content") or ""
            if not content:
                record["reasons"].append("router emitted no PCB content")
                continue
            candidate_board.write_text(content, encoding="utf-8")
            verdict = regional.evaluate(board, candidate_board, manifest, threshold_mm, 0.01)
            connectivity = routed.get("pad_connectivity") or {}
            connected = int(connectivity.get("fully_connected", 0))
            unrouted = int(routed.get("unrouted", 0))
            record.update(
                {
                    "routed": True,
                    "route_completion": float(routed.get("completion_rate", 0.0)),
                    "pad_connected_nets": connected,
                    "unrouted_nets": unrouted,
                    "final_accepted": bool(verdict["accepted"]),
                    "final_reasons": list(verdict["reasons"]),
                    "drc_errors": int(verdict["candidate"]["drc_errors"]),
                }
            )
            routed_for_rust.append(
                (
                    candidate_id,
                    dx,
                    dy,
                    ring,
                    bool(verdict["accepted"]),
                    len(verdict["removed_cross_domain_pairs"]),
                    int(verdict["candidate"]["drc_errors"]),
                    connected,
                    unrouted,
                )
            )

    winner = quality.select_routed_block_candidate_py(routed_for_rust)
    collision_feedback = [
        pair
        for record in records
        for pair in record.get("new_or_worsened_body_pairs", [])
        if not record.get("new_cross_domain_pairs")
    ]
    return {
        "board": str(board),
        "block_refs": refs,
        "search_budget": {
            "step_mm": step_mm,
            "max_rings": max_rings,
            "max_candidates": max_candidates,
            "max_routed_candidates": max_routed_candidates,
        },
        "baseline_cross_domain_pairs": len(baseline_pairs),
        "candidates": records,
        "suggested_block_expansion": [
            {"ref": ref, "blocking_candidates": count}
            for ref, count in quality.block_expansion_candidates_py(refs, collision_feedback)
        ],
        "winner": dict(winner) if winner is not None else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--board", type=Path, default=DEFAULT_BOARD)
    parser.add_argument("--manifest", type=Path, default=regional.DEFAULT_MANIFEST)
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    parser.add_argument("--ref", action="append", default=[])
    parser.add_argument("--step-mm", type=float, default=5.0)
    parser.add_argument("--max-rings", type=int, default=3)
    parser.add_argument("--max-candidates", type=int, default=24)
    parser.add_argument("--max-routed-candidates", type=int, default=3)
    parser.add_argument("--min-creepage-mm", type=float, default=12.6)
    parser.add_argument("--bounds", type=float, nargs=4, default=(20.0, 20.0, 172.0, 254.0))
    parser.add_argument("--route", action="store_true")
    parser.add_argument("--json", type=Path)
    args = parser.parse_args()
    try:
        result = search(
            args.board,
            args.manifest,
            args.rules,
            args.ref,
            step_mm=args.step_mm,
            max_rings=args.max_rings,
            max_candidates=args.max_candidates,
            max_routed_candidates=args.max_routed_candidates,
            threshold_mm=args.min_creepage_mm,
            bounds=tuple(args.bounds),
            route=args.route,
        )
    except Exception as exc:
        print(f"BLOCK SEARCH ERROR: {exc}", file=sys.stderr)
        return 2
    rendered = json.dumps(result, indent=2)
    print(rendered)
    if args.json:
        args.json.write_text(rendered + "\n", encoding="utf-8")
    return 0 if result["winner"] is not None or not args.route else 1


if __name__ == "__main__":
    raise SystemExit(main())
