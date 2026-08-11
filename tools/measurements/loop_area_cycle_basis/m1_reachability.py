#!/usr/bin/env python3
"""M1 — reachability: does cycle_basis fire on the production board?

Answers F2: is the cycle_basis path actually reached on the production
board? Which nets have cycles? Does the trace graph contain any cycle at all?

Usage:
    PYTHONPATH="packages/temper-placer/src:$PYTHONPATH" \
        .venv/bin/python3 tools/measurements/loop_area_cycle_basis/m1_reachability.py \
        --pcb pcb/temper.kicad_pcb --out m1.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# --- path setup ---
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "packages" / "temper-placer" / "src"))


def _load_board(pcb_path: str) -> dict:
    """Load PCB and extract commutation-loop relevant data."""
    from temper_placer.core.loop import LoopType
    from temper_placer.core.loop_extractor import auto_extract_loops
    from temper_placer.io.kicad_parser import parse_kicad_pcb

    result = {"pcb": str(pcb_path), "parse_ok": False, "error": None}

    try:
        parsed = parse_kicad_pcb(Path(pcb_path))
        result["parse_ok"] = True
    except Exception as exc:
        result["error"] = f"parse_kicad_pcb: {exc}"
        return result

    netlist = parsed.netlist
    result["n_nets"] = len(netlist.nets)
    result["n_components"] = len(netlist.components)
    result["n_traces"] = len(parsed.traces)

    # Find commutation loops
    try:
        loops = auto_extract_loops(netlist)
        comm_loops = loops.get_loops_by_type(LoopType.COMMUTATION)
        result["n_comm_loops"] = len(comm_loops)
    except Exception as exc:
        result["error"] = f"auto_extract_loops: {exc}"
        return result

    if not comm_loops:
        result["cycle_basis_reachable"] = False
        result["reason"] = "no commutation loops found"
        return result

    loop = comm_loops[0]
    net_names: set[str] = set(loop.nets)
    result["comm_loop_nets"] = sorted(net_names)

    # Filter traces
    loop_traces = [t for t in parsed.traces if t.net in net_names]
    result["n_loop_traces"] = len(loop_traces)

    if len(loop_traces) < 2:
        result["cycle_basis_reachable"] = False
        result["reason"] = f"only {len(loop_traces)} traces on loop nets"
        return result

    # Build the trace graph (same logic as _compute_area_from_traces)
    import networkx as nx
    import math

    G: nx.Graph = nx.Graph()
    for t in loop_traces:
        u = (round(t.start[0], 3), round(t.start[1], 3))
        v = (round(t.end[0], 3), round(t.end[1], 3))
        if u == v:
            continue
        length = math.hypot(v[0] - u[0], v[1] - u[1])
        G.add_edge(u, v, weight=length)

    result["graph_nodes"] = G.number_of_nodes()
    result["graph_edges"] = G.number_of_edges()

    if G.number_of_nodes() == 0:
        result["cycle_basis_reachable"] = False
        result["reason"] = "empty trace graph (zero nodes)"
        return result

    # Largest connected component
    largest_cc = max(nx.connected_components(G), key=len)
    subgraph = G.subgraph(largest_cc).copy()
    result["largest_cc_nodes"] = subgraph.number_of_nodes()
    result["largest_cc_edges"] = subgraph.number_of_edges()

    # cycle_basis
    cycles = list(nx.cycle_basis(subgraph))
    result["n_cycles_in_basis"] = len(cycles)

    if cycles:
        longest = max(cycles, key=len)
        result["longest_cycle_len"] = len(longest)
        result["cycle_basis_reachable"] = True
    else:
        result["cycle_basis_reachable"] = False
        result["reason"] = "no cycles in largest connected component"
        # Check if ANY CC has a cycle
        any_cycle = False
        for cc in nx.connected_components(G):
            sg = G.subgraph(cc).copy()
            if list(nx.cycle_basis(sg)):
                any_cycle = True
                break
        result["any_cc_has_cycle"] = any_cycle
        result["n_cc"] = nx.number_connected_components(G)

    return result


def main() -> None:
    ap = argparse.ArgumentParser(description="M1 — cycle_basis reachability on production board")
    ap.add_argument("--pcb", required=True, help="Path to .kicad_pcb")
    ap.add_argument("--out", default=None, help="Write JSON output to file")
    args = ap.parse_args()

    data = _load_board(args.pcb)
    print(json.dumps(data, indent=2, default=str))

    if args.out:
        with open(args.out, "w") as f:
            json.dump(data, f, indent=2, default=str)


if __name__ == "__main__":
    main()
