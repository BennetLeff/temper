"""
Generate golden fixture JSON files for Router V6 Stage 3 topology stage.

Runs the corrected Python topology solver on canonical test boards
and captures Stage3Output as JSON under tests/fixtures/stage3_goldens/.

Usage:
    python tests/router_v6/generate_stage3_goldens.py                    # Generate all
    python tests/router_v6/generate_stage3_goldens.py --board temper     # Single board
    python tests/router_v6/generate_stage3_goldens.py --regenerate       # Force overwrite
    python tests/router_v6/generate_stage3_goldens.py --out-dir /tmp/X   # Custom output dir

Origin: U2 of docs/plans/2026-06-28-001-feat-router-v6-rust-topology-plan.md
"""

from __future__ import annotations

import argparse
import json
import sys
from enum import Enum
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np
from networkx.readwrite import node_link_data
from shapely.geometry import MultiPolygon, Polygon

HERE = Path(__file__).resolve().parent
GOLDEN_DIR = HERE.parent / "fixtures" / "stage3_goldens"


class GoldenEncoder(json.JSONEncoder):
    """Custom JSON encoder for topology-stage data types."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, Enum):
            return obj.value
        if isinstance(obj, (np.ndarray,)):
            return self._encode_grid(obj)
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, (MultiPolygon, Polygon)):
            return obj.wkt
        if isinstance(obj, nx.Graph):
            return node_link_data(obj)
        if isinstance(obj, nx.DiGraph):
            return node_link_data(obj)
        if hasattr(obj, "__dataclass_fields__"):
            result: dict[str, Any] = {}
            for f_name in obj.__dataclass_fields__:
                val = getattr(obj, f_name)
                result[f_name] = self._encode_field(val)
            return result
        return super().default(obj)

    def _encode_field(self, val: Any) -> Any:
        if isinstance(val, Enum):
            return val.value
        if isinstance(val, (np.ndarray,)):
            return self._encode_grid(val)
        if isinstance(val, (np.integer,)):
            return int(val)
        if isinstance(val, (np.floating,)):
            return float(val)
        if isinstance(val, (MultiPolygon, Polygon)):
            return val.wkt
        if isinstance(val, (nx.Graph, nx.DiGraph)):
            return node_link_data(val)
        if hasattr(val, "__dataclass_fields__"):
            return self.default(val)
        if isinstance(val, dict):
            return {str(k): self._encode_field(v) for k, v in val.items()}
        if isinstance(val, (list, tuple)):
            return [self._encode_field(v) for v in val]
        return val

    @staticmethod
    def _encode_grid(grid: np.ndarray) -> dict:
        return {
            "shape": list(grid.shape),
            "dtype": str(grid.dtype),
            "nonzero_count": int(np.count_nonzero(grid)),
            "min": float(grid.min()) if grid.size else 0.0,
            "max": float(grid.max()) if grid.size else 0.0,
        }


# ---------------------------------------------------------------------------
# Board definitions
# ---------------------------------------------------------------------------

# Primary board: the Temper induction cooker PCB.
TEMPER_PCB = (
    Path(__file__).resolve().parents[5]
    / "pcb"
    / "temper_agent_optimized.kicad_pcb"
)

BOARDS: dict[str, Path] = {
    "temper": TEMPER_PCB,
}


def _discover_external_boards() -> dict[str, Path]:
    """Discover additional boards from the external fixtures cache."""
    cache = HERE.parent / "fixtures" / "external" / ".cache"
    if not cache.exists():
        return {}
    discovered: dict[str, Path] = {}
    for d in sorted(cache.iterdir()):
        if not d.is_dir():
            continue
        for f in d.iterdir():
            if f.suffix == ".kicad_pcb":
                discovered[d.name] = f
                break
    return discovered


# ---------------------------------------------------------------------------
# Stage 3 capture
# ---------------------------------------------------------------------------


def capture_stage3_output(board_name: str, board_path: Path) -> dict | None:
    """Run the topology stage on a board and capture Stage3Output as a dict.

    Returns None if the board cannot be routed.
    """
    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
    from temper_placer.router_v6.channel_skeleton import ChannelSkeleton
    from temper_placer.router_v6.channel_widths import ChannelWidths
    from temper_placer.router_v6.constraint_model import (
        ConstraintModel,
        ModelBuilder,
    )
    from temper_placer.router_v6.diff_pair_inference import infer_differential_pairs
    from temper_placer.router_v6.sat_model import (
        build_sat_model,
        populate_sat_from_constraints,
    )
    from temper_placer.router_v6.stage0_data import ParsedPCB
    from temper_placer.router_v6.stage2_orchestrator import Stage2Orchestrator
    from temper_placer.router_v6.topology_extraction import extract_topology_solution
    from temper_placer.router_v6.topology_solver import solve_topology

    assert board_path.exists(), f"Board not found: {board_path}"
    pcb: ParsedPCB = parse_kicad_pcb_v6(str(board_path))

    # Minimal Stage 2 to get skeletons and channel widths.
    orch = Stage2Orchestrator(verbose=False)
    stage2_state = orch.run(pcb, escape_vias=[])

    skeletons: dict[str, ChannelSkeleton] = stage2_state.channel_skeletons or {}
    widths: dict[str, ChannelWidths] = stage2_state.channel_widths or {}

    # Build constraint model.
    diff_pairs = infer_differential_pairs([net.name for net in pcb.nets])
    builder = ModelBuilder(
        skeletons=skeletons,
        nets=pcb.nets,
        channel_widths=widths,
        design_rules=pcb.design_rules,
        diff_pairs=diff_pairs,
        pcb=pcb,
    )
    constraint_model: ConstraintModel = builder.build()

    # SAT encode and solve.
    sat_model = build_sat_model()
    net_names = [net.name for net in pcb.nets]
    populate_sat_from_constraints(sat_model, constraint_model, net_names)
    solution = solve_topology(sat_model)

    # Topology extraction.
    topology_graph = None
    if solution.is_satisfiable:
        topology_graph = extract_topology_solution(solution, net_names)

    encoder = GoldenEncoder()
    return {
        "board_name": board_name,
        "board_path": str(board_path),
        "constraint_model": {
            "variable_count": constraint_model.variable_count,
            "constraint_count": constraint_model.constraint_count,
            "net_channel_var_count": len(constraint_model.net_channel_vars),
            "via_var_count": len(constraint_model.via_vars),
            "capacity_constraints": sum(
                1
                for c in constraint_model.constraints
                if type(c).__name__ == "CapacityConstraint"
            ),
            "diff_pair_constraints": sum(
                1
                for c in constraint_model.constraints
                if type(c).__name__ == "DiffPairConstraint"
            ),
            "layer_constraints": sum(
                1
                for c in constraint_model.constraints
                if type(c).__name__ == "LayerConstraint"
            ),
        },
        "sat_model": {
            "variable_count": sat_model.variable_count,
            "clause_count": sat_model.clause_count,
        },
        "solution": encoder.default(solution),
        "topology_graph": encoder.default(topology_graph) if topology_graph else None,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate Stage 3 golden fixtures for Router V6."
    )
    parser.add_argument(
        "--board",
        help="Generate fixtures for a specific board (default: all available)",
    )
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help="Force overwrite existing fixtures",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=GOLDEN_DIR,
        help="Output directory for fixture JSON files",
    )
    args = parser.parse_args()

    all_boards = dict(BOARDS)
    all_boards.update(_discover_external_boards())

    if args.board:
        if args.board not in all_boards:
            print(f"Unknown board: {args.board}. Available: {list(all_boards)}")
            sys.exit(1)
        boards = {args.board: all_boards[args.board]}
    else:
        boards = all_boards

    args.out_dir.mkdir(parents=True, exist_ok=True)

    for name, path in sorted(boards.items()):
        out_file = args.out_dir / name / "stage3_topology.json"
        if out_file.exists() and not args.regenerate:
            print(f"Skipping {name} (fixture exists, use --regenerate to overwrite)")
            continue

        print(f"Generating fixture for {name} ({path}) ...")
        try:
            data = capture_stage3_output(name, path)
            if data is None:
                print(f"  FAIL: could not capture Stage 3 output for {name}")
                continue
        except Exception as exc:
            print(f"  FAIL: {type(exc).__name__}: {exc}")
            continue

        out_file.parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, "w") as f:
            json.dump(data, f, indent=2, cls=GoldenEncoder)
        print(f"  -> {out_file}")


if __name__ == "__main__":
    main()
