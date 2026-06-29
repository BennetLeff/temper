"""
Generate golden fixture JSON files for Router V6 Stage 2 micro-stages.

Runs Stage2Orchestrator on each canonical test board and captures
per-sub-step output as JSON under tests/fixtures/stage2_goldens/.

Usage:
    python tests/router_v6/generate_stage2_goldens.py           # Generate fixtures
    python tests/router_v6/generate_stage2_goldens.py --regenerate  # Force overwrite
"""

from __future__ import annotations

import json
import sys
from enum import Enum
from pathlib import Path

import networkx as nx
import numpy as np
from networkx.readwrite import node_link_data
from shapely.geometry import MultiPolygon, Polygon

HERE = Path(__file__).resolve().parent
GOLDEN_DIR = HERE.parent / "fixtures" / "stage2_goldens"
TEST_BOARDS_MODULE = HERE.parent.parent / "src" / "temper_placer" / "router_v6" / "test_boards.py"


class GoldenEncoder(json.JSONEncoder):
    """Custom JSON encoder for channel-analysis data types."""

    def default(self, obj):
        if isinstance(obj, Enum):
            return obj.value
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, (MultiPolygon, Polygon)):
            return obj.wkt
        if hasattr(obj, "__dataclass_fields__"):
            result = {}
            for f_name in obj.__dataclass_fields__:
                val = getattr(obj, f_name)
                result[f_name] = self._encode_field(val)
            return result
        return super().default(obj)

    def _encode_field(self, val):
        if isinstance(val, Enum):
            return val.value
        if isinstance(val, np.ndarray):
            return self._encode_grid(val)
        if isinstance(val, np.integer):
            return int(val)
        if isinstance(val, np.floating):
            return float(val)
        if isinstance(val, (MultiPolygon, Polygon)):
            return val.wkt
        if isinstance(val, nx.Graph):
            return node_link_data(val)
        if hasattr(val, "graph") and hasattr(val, "node_count"):  # ChannelSkeleton-like
            return {
                "layer_name": getattr(val, "layer_name", ""),
                "total_length": getattr(val, "total_length", 0.0),
                "node_count": getattr(val, "node_count", 0),
                "edge_count": getattr(val, "edge_count", 0),
                "graph": node_link_data(getattr(val, "graph", None)),
            }
        if isinstance(val, dict):
            return {str(k): self._encode_field(v) for k, v in val.items()}
        if isinstance(val, (list, tuple)):
            return [self._encode_field(v) for v in val]
        return val

    @staticmethod
    def _encode_grid(grid: np.ndarray) -> dict:
        """Encode a numpy grid array as summary metadata + hash."""
        import hashlib
        grid_bytes = grid.tobytes()
        return {
            "_type": "ndarray_summary",
            "dtype": str(grid.dtype),
            "shape": list(grid.shape),
            "sha256": hashlib.sha256(grid_bytes).hexdigest(),
            "free_count": int(np.sum(grid == 0)),
            "blocked_count": int(np.sum(grid != 0)),
        }


def generate_goldens(regenerate: bool = False):
    """Generate golden fixtures for all available test boards."""
    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
    from temper_placer.router_v6.dense_package_detection import identify_dense_packages
    from temper_placer.router_v6.escape_via_generator import generate_escape_vias
    from temper_placer.router_v6.stage2_orchestrator import Stage2Orchestrator
    from temper_placer.router_v6.test_boards import get_available_boards

    boards = get_available_boards()

    if not boards:
        print("ERROR: No test boards available. Check fixture paths.")
        sys.exit(1)

    for board in boards:
        print(f"\n{'='*60}")
        print(f"Board: {board.name} ({board.domain}, {board.layers}L)")
        print(f"Path: {board.path}")
        print(f"{'='*60}")

        board_golden_dir = GOLDEN_DIR / board.name
        if not regenerate and board_golden_dir.exists():
            print("  Skipping (fixtures exist, use --regenerate to force)")
            continue

        board_golden_dir.mkdir(parents=True, exist_ok=True)

        print("  Loading PCB...")
        pcb = parse_kicad_pcb_v6(str(board.path))

        print("  Generating escape vias...")
        dense_packages = identify_dense_packages(pcb.components)
        escape_vias = []
        for dp in dense_packages:
            vias = generate_escape_vias(dp, pcb.design_rules, strategy="dog-bone")
            if not vias:
                vias = generate_escape_vias(dp, pcb.design_rules, strategy="via-in-pad")
            escape_vias.extend(vias)

        print("  Running Stage2Orchestrator...")
        orch = Stage2Orchestrator(verbose=False)
        state = orch.run(pcb, escape_vias)

        # Save per-stage outputs
        stage_outputs = {
            "obstacle_maps": state.obstacle_maps,
            "routing_spaces": state.routing_spaces,
            "channel_skeletons": state.channel_skeletons,
            "channel_widths": state.channel_widths,
            "occupancy_grids": state.occupancy_grids,
            "layer_capacities": state.layer_capacities,
            "routing_demand": state.routing_demand,
            "bottleneck_analysis": state.bottleneck_analysis,
        }

        for stage_name, data in stage_outputs.items():
            out_path = board_golden_dir / f"{stage_name}.json"
            with open(out_path, "w") as f:
                json.dump(data, f, cls=GoldenEncoder, indent=2)
            print(f"    Wrote: {out_path}")

    print(f"\nDone. Golden fixtures in: {GOLDEN_DIR}")


if __name__ == "__main__":
    regenerate = "--regenerate" in sys.argv
    generate_goldens(regenerate=regenerate)
