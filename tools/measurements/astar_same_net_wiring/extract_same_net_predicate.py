#!/usr/bin/env python3
"""F-A1: Extract and document the exact same-net blocking predicate.

Reads the Python reference A* and the OccupancyGrid rasterization
functions to enumerate every cell-value code path.  This is a
read-only analysis -- no code is modified, no Rust is built.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ROUTER_V6 = REPO / "packages" / "temper-placer" / "src" / "temper_placer" / "router_v6"


def read_file(path: Path) -> str:
    return path.read_text()


def main() -> None:
    # 1. Parse the OccupancyGrid class to confirm the cell-value dtype and
    #    the marking functions' net_id convention.
    occ_text = read_file(ROUTER_V6 / "occupancy_grid.py")
    occ_tree = ast.parse(occ_text)

    # Find CellState enum values
    print("=== CellState enum ===")
    for node in ast.walk(occ_tree):
        if isinstance(node, ast.ClassDef) and node.name == "CellState":
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name):
                            val = ast.literal_eval(item.value) if isinstance(item.value, ast.Constant) else "?"
                            print(f"  {target.id} = {val}")

    # 2. Confirm marking functions pass net_id as cell value
    print("\n=== Marking function signatures ===")
    for node in ast.walk(occ_tree):
        if isinstance(node, ast.FunctionDef) and node.name in (
            "mark_path_blocked",
            "mark_via_blocked",
            "mark_segment_blocked",
        ):
            args = [a.arg for a in node.args.args]
            print(f"  {node.name}({', '.join(args)})")
            # Count the net_id argument position (always last in these three)
            for a in node.args.args:
                if a.arg == "net_id":
                    if a.annotation and isinstance(a.annotation, ast.Name):
                        print(f"    net_id type: {a.annotation.id}")

    # 3. Extract the exact A* inner-loop predicate from _astar_search
    print("\n=== _astar_search same-net predicate (exact source lines) ===")
    astar_text = read_file(ROUTER_V6 / "astar_core.py")
    astar_tree = ast.parse(astar_text)
    for node in ast.walk(astar_tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_astar_search":
            # Find the net_id >= 0 branch
            src = astar_text
            lines = src.split("\n")
            # Extract lines 327-336 (the net_id >= 0 branch)
            # These are the exact lines from the source
            for lineno in range(327, 360):
                print(f"  {lineno}: {lines[lineno - 1]}")
            break

    # 4. Extract _SAME_NET_COST_DISCOUNT
    print("\n=== Cost constants ===")
    for node in ast.walk(astar_tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in (
                    "_SAME_NET_COST_DISCOUNT",
                    "_BASE_DIAGONAL_COST",
                    "DIAGONAL_COST_FACTOR",
                ):
                    val = ast.literal_eval(node.value) if isinstance(node.value, ast.Constant) else "?"
                    print(f"  {target.id} = {val}")

    # 5. Summarize the predicate
    print("\n=== PREDICATE SUMMARY ===")
    print("For net_id >= 0, evaluating destination cell (nx, ny):")
    print()
    print("  1. BOUNDS:  if not in_bounds(nx, ny, ...): BLOCKED")
    print("  2. CORRIDOR: if corridor_mask is not None and not corridor_mask[ny, nx]: BLOCKED")
    print("  3. OCCUPANCY: cell_value = grid.grid[ny, nx]")
    print("     a) cell_value == 0          → FREE, traversable (cost 1.0 or √2)")
    print("     b) cell_value == net_id     → SAME-NET, traversable (cost × 0.25)")
    print("     c) cell_value != 0, != net_id → FOREIGN/STATIC, BLOCKED")
    print()
    print("Grid cell values are int8.  Sources of net_id entries on the grid:")
    print("  - mark_path_blocked(path, ..., net_id)      → stores net_id in cells")
    print("  - mark_via_blocked(x, y, ..., net_id)       → stores net_id in cells")
    print("  - mark_segment_blocked(p1, p2, ..., net_id) → stores net_id in cells")
    print("  - static_mask (board outline/keepouts)       → stores -1 in cells")
    print()
    print("Therefore same-net traversability covers: traces, pads, vias.")
    print("All are represented by the same net_id integer on the grid.")
    print()
    print("For net_id < 0:")
    print("  The neighbor_validity tensor 'dst_free == 0' treats ALL non-zero")
    print("  cells as blocked -- no same-net exemption.  This is correct for")
    print("  coarse-to-fine corridor search (net_id < 0 is only used there).")


if __name__ == "__main__":
    main()
