#!/usr/bin/env python3
"""Bounded functional-block floorplan search with router-in-the-loop evaluation.

Rust owns the finite transforms, dimension-derived internal slots, safety
verdict, and final candidate selection.  This file is the thin adapter for
KiCad board serialization and the production router.  By default it performs
only the cheap geometric preflight; ``--route`` spends the separately-capped
routing budget on the best preflight candidates.
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
import temper_geometry as geometry
import temper_quality_oracle as quality

from temper_placer.io.fab_body_extraction import extract_fab_bodies
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


def _body_dimensions(board: Path, refs: set[str]) -> dict[str, tuple[float, float]]:
    bodies = extract_fab_bodies(board)
    missing = sorted(refs - bodies.keys())
    if missing:
        raise ValueError(f"block references lack F.Fab bodies: {', '.join(missing)}")
    dimensions: dict[str, tuple[float, float]] = {}
    for ref in refs:
        xs = [point[0] for point in bodies[ref].points]
        ys = [point[1] for point in bodies[ref].points]
        dimensions[ref] = (max(xs) - min(xs), max(ys) - min(ys))
    return dimensions


def _arrangements(
    positions: dict[str, tuple[float, float, float]],
    refs: list[str],
    anchor_ref: str,
    pivot_ref: str | None,
    dimensions: dict[str, tuple[float, float]],
    pivot_quarter_turns: list[int],
    orbit_gap_mm: float,
) -> list[tuple[str, dict[str, tuple[float, float, float]]]]:
    base = {ref: positions[ref] for ref in refs}
    out = [("as-is", base)]
    if pivot_ref is None:
        return out
    anchor_x, anchor_y, _ = positions[anchor_ref]
    anchor_width, anchor_height = dimensions[anchor_ref]
    pivot_width, pivot_height = dimensions[pivot_ref]
    pivot_angle = positions[pivot_ref][2]
    for quarter_turn in pivot_quarter_turns:
        slots = geometry.block_orbit_slots_py(
            anchor_x,
            anchor_y,
            anchor_width,
            anchor_height,
            pivot_width,
            pivot_height,
            orbit_gap_mm,
            quarter_turn,
        )
        for slot_name, x, y, _ in slots:
            arranged = dict(base)
            arranged[pivot_ref] = (
                float(x),
                float(y),
                (pivot_angle + quarter_turn * 90.0) % 360.0,
            )
            out.append((f"{pivot_ref}:{slot_name}:q{quarter_turn}", arranged))
    return out


def _transform(
    arrangement: dict[str, tuple[float, float, float]],
    anchor_ref: str,
    quarter_turn: int,
    dx_mm: float,
    dy_mm: float,
) -> dict[str, PlacementUpdate]:
    anchor_x, anchor_y, _ = arrangement[anchor_ref]
    moved = geometry.block_transform_py(
        [(ref, *position) for ref, position in arrangement.items()],
        anchor_x,
        anchor_y,
        quarter_turn,
        dx_mm,
        dy_mm,
    )
    return {
        ref: PlacementUpdate(ref, float(x), float(y), float(angle))
        for ref, x, y, angle in moved
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
    anchor_ref: str | None = None,
    pivot_ref: str | None = None,
    block_quarter_turns: list[int] | None = None,
    pivot_quarter_turns: list[int] | None = None,
    orbit_gap_mm: float = 1.0,
    winner_board: Path | None = None,
) -> dict:
    if not refs:
        raise ValueError("at least one --ref is required")
    positions = _positions(board)
    missing = sorted(set(refs) - positions.keys())
    if missing:
        raise ValueError(f"block references absent from board: {', '.join(missing)}")
    anchor_ref = anchor_ref or refs[0]
    if anchor_ref not in refs:
        raise ValueError("--anchor-ref must also be named by --ref")
    if pivot_ref is not None and pivot_ref not in refs:
        raise ValueError("--pivot-ref must also be named by --ref")
    if pivot_ref == anchor_ref:
        raise ValueError("--pivot-ref must differ from --anchor-ref")
    block_quarter_turns = block_quarter_turns or [0]
    pivot_quarter_turns = pivot_quarter_turns or [0]
    if any(turn not in range(4) for turn in block_quarter_turns + pivot_quarter_turns):
        raise ValueError("quarter turns must be in 0..=3")

    baseline_pairs = _pair_set(board, manifest, threshold_mm)
    baseline_bodies = regional._body_overlaps(board)
    dimension_refs = {anchor_ref, pivot_ref} if pivot_ref else set()
    arrangements = _arrangements(
        positions,
        refs,
        anchor_ref,
        pivot_ref,
        _body_dimensions(board, dimension_refs),
        pivot_quarter_turns,
        orbit_gap_mm,
    )
    schedule = quality.block_search_schedule_py(
        step_mm,
        max_rings,
        len(arrangements),
        block_quarter_turns,
        max_candidates,
    )
    xmin, ymin, xmax, ymax = bounds
    records: list[dict] = []
    preflight_candidates: list[tuple[int, dict[str, PlacementUpdate]]] = []
    routed_for_rust: list[tuple] = []
    routed_contents: dict[int, str] = {}

    with tempfile.TemporaryDirectory(prefix="temper-block-search-") as raw_tmp:
        candidate_board = _copy_board_context(board, Path(raw_tmp))
        for candidate_id, candidate in enumerate(schedule, start=1):
            arrangement_index, quarter_turn, dx, dy, ring = candidate
            arrangement_name, arrangement = arrangements[arrangement_index]
            moved = _transform(arrangement, anchor_ref, quarter_turn, dx, dy)
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
                        "arrangement": arrangement_name,
                        "block_quarter_turn": quarter_turn,
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
                "arrangement": arrangement_name,
                "block_quarter_turn": quarter_turn,
                "preflight_accepted": bool(preflight["accepted"]),
                "removed_cross_domain_pairs": len(preflight["removed_cross_domain_pairs"]),
                "new_cross_domain_pairs": preflight["new_cross_domain_pairs"],
                "new_or_worsened_body_pairs": preflight["new_or_worsened_body_pairs"],
                "reasons": list(preflight["reasons"]),
            }
            records.append(record)
            if preflight["accepted"]:
                preflight_candidates.append((candidate_id, moved))

        ranked = sorted(
            preflight_candidates,
            key=lambda candidate: (
                -records[candidate[0] - 1]["removed_cross_domain_pairs"],
                candidate[0],
            ),
        )
        for candidate_id, moved in ranked[:max_routed_candidates] if route else []:
            record = records[candidate_id - 1]
            write_placements_to_pcb(board, candidate_board, moved)
            routed = route_board.route_once(candidate_board, rules)
            content = routed.get("routed_pcb_content") or ""
            if not content:
                record["reasons"].append("router emitted no PCB content")
                continue
            candidate_board.write_text(content, encoding="utf-8")
            routed_contents[candidate_id] = content
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
                    record["dx_mm"],
                    record["dy_mm"],
                    record["ring"],
                    bool(verdict["accepted"]),
                    len(verdict["removed_cross_domain_pairs"]),
                    int(verdict["candidate"]["drc_errors"]),
                    connected,
                    unrouted,
                )
            )

    winner = quality.select_routed_block_candidate_py(routed_for_rust)
    if winner is not None and winner_board is not None:
        winner_board.write_text(
            routed_contents[int(winner["candidate_id"])], encoding="utf-8"
        )
    collision_feedback = [
        pair
        for record in records
        for pair in record.get("new_or_worsened_body_pairs", [])
        if not record.get("new_cross_domain_pairs")
    ]
    return {
        "board": str(board),
        "block_refs": refs,
        "anchor_ref": anchor_ref,
        "pivot_ref": pivot_ref,
        "search_budget": {
            "step_mm": step_mm,
            "max_rings": max_rings,
            "max_candidates": max_candidates,
            "max_routed_candidates": max_routed_candidates,
            "block_quarter_turns": block_quarter_turns,
            "pivot_quarter_turns": pivot_quarter_turns,
            "orbit_gap_mm": orbit_gap_mm,
        },
        "baseline_cross_domain_pairs": len(baseline_pairs),
        "candidates": records,
        "suggested_block_expansion": [
            {"ref": ref, "blocking_candidates": count}
            for ref, count in quality.block_expansion_candidates_py(refs, collision_feedback)
        ],
        "winner": dict(winner) if winner is not None else None,
        "winner_board": str(winner_board) if winner is not None and winner_board else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--board", type=Path, default=DEFAULT_BOARD)
    parser.add_argument("--manifest", type=Path, default=regional.DEFAULT_MANIFEST)
    parser.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    parser.add_argument("--ref", action="append", default=[])
    parser.add_argument("--anchor-ref")
    parser.add_argument("--pivot-ref")
    parser.add_argument("--block-quarter-turn", action="append", type=int, dest="block_turns")
    parser.add_argument("--pivot-quarter-turn", action="append", type=int, dest="pivot_turns")
    parser.add_argument("--orbit-gap-mm", type=float, default=1.0)
    parser.add_argument("--step-mm", type=float, default=5.0)
    parser.add_argument("--max-rings", type=int, default=3)
    parser.add_argument("--max-candidates", type=int, default=24)
    parser.add_argument("--max-routed-candidates", type=int, default=3)
    parser.add_argument("--min-creepage-mm", type=float, default=12.6)
    parser.add_argument("--bounds", type=float, nargs=4, default=(20.0, 20.0, 172.0, 254.0))
    parser.add_argument("--route", action="store_true")
    parser.add_argument("--json", type=Path)
    parser.add_argument("--winner-board", type=Path)
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
            anchor_ref=args.anchor_ref,
            pivot_ref=args.pivot_ref,
            block_quarter_turns=args.block_turns,
            pivot_quarter_turns=args.pivot_turns,
            orbit_gap_mm=args.orbit_gap_mm,
            winner_board=args.winner_board,
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
