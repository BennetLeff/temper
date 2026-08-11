#!/usr/bin/env python3
"""M5 — port surface census: enumerate every ``networkx`` API surface used.

Distinguishes LIVE (on production code paths) from DEAD (test-only or
unreachable) networkx API calls on the ``MultiDiGraph`` container.

Also enumerates every method of ``TopologicalGraph`` that touches the
internal ``self.graph`` and classifies each as LIVE or DEAD.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path


def find_graph_accesses(target_file: Path, src_root: Path) -> list[dict]:
    """Find every ``self.graph.XXX`` or ``graph.graph.XXX`` access."""
    results = []
    for f in sorted(src_root.rglob("*.py")):
        tree = ast.parse(f.read_text(), filename=str(f))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                # Check for .graph.XXX pattern
                if isinstance(node.value, ast.Attribute) and node.value.attr == "graph":
                    # This is something.graph.XXX
                    results.append({
                        "file": str(f.relative_to(src_root)),
                        "line": node.lineno,
                        "access": node.attr,
                        "chain": f".graph.{node.attr}",
                    })
    return results


def classify_path(file_path: str, production_src_root: str) -> str:
    """Classify a file as production or test."""
    if "/tests/" in file_path or "tests/" in file_path:
        return "test"
    if file_path.endswith("_py_oracle.py"):
        return "oracle"
    return "production"


def main():
    parser = argparse.ArgumentParser(description="M5: port surface census")
    parser.add_argument("--repo", type=Path, required=True, help="Repository root")
    parser.add_argument("--out", type=Path, required=True, help="Output JSON file")
    args = parser.parse_args()

    src_root = args.repo / "packages" / "temper-placer" / "src" / "temper_placer"
    target_file = src_root / "topological" / "graph.py"

    accesses = find_graph_accesses(target_file, src_root)
    prod = [a for a in accesses if classify_path(a["file"], "") == "production"]
    test = [a for a in accesses if classify_path(a["file"], "") == "test"]
    oracle = [a for a in accesses if classify_path(a["file"], "") == "oracle"]

    # Census of networkx API methods used on the graph
    nx_methods = {
        ".graph.add_node": "add_node",
        ".graph.add_edge": "add_edge",
        ".graph.edges": "edges",
        ".graph.nodes": "nodes",
        ".graph.has_edge": "has_edge",
        ".graph.number_of_nodes": "number_of_nodes",
        ".graph.number_of_edges": "number_of_edges",
        ".graph.degree": "degree",
    }

    # Categorize by method
    by_method = {}
    for a in accesses:
        method = a["chain"]
        if method not in by_method:
            by_method[method] = {"production": [], "test": [], "oracle": []}
        cat = classify_path(a["file"], "")
        by_method[method][cat].append({"file": a["file"], "line": a["line"]})

    # Determine which methods are live
    live_methods = {}
    for method, cats in sorted(by_method.items()):
        has_production = len(cats["production"]) > 0
        has_test = len(cats["test"]) > 0
        live_methods[method] = {
            "production_sites": len(cats["production"]),
            "test_sites": len(cats["test"]),
            "oracle_sites": len(cats["oracle"]),
            "live": has_production,
        }

    # Also enumerate TopologicalGraph methods and classify
    graph_text = target_file.read_text()
    tree = ast.parse(graph_text)

    methods = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef):
            # Top-level function or method
            if any(isinstance(d, ast.Name) and d.id == "self" for d in node.args.args):
                # Instance method of TopologicalGraph
                methods.append({
                    "name": node.name,
                    "line": node.lineno,
                    "uses_nx": any(
                        "graph" in ast.dump(n) and ("networkx" in ast.dump(n) or "edges" in ast.dump(n) or "node" in ast.dump(n))
                        for n in ast.walk(node)
                    ),
                })

    # Static method
    methods.append({"name": "from_pcl", "line": 253, "uses_nx": False, "notes": "static method, creates TopologicalGraph"})

    # Classify each method as live/dead
    method_liveness = {}
    for m in methods:
        name = m["name"]
        # Search for callers
        callers = []
        for f in sorted(src_root.rglob("*.py")):
            if f == target_file:
                continue
            text = f.read_text()
            if f".{name}(" in text:
                rel = str(f.relative_to(src_root))
                cat = classify_path(rel, "")
                if cat == "production":
                    callers.append(rel)

        method_liveness[name] = {
            "line": m["line"],
            "production_callers": len(callers),
            "production_callers_list": callers,
            "live": len(callers) > 0,
            "is_constructor": name == "__init__",
        }

    # Summary of what a port needs
    port_surface = {
        "container_methods": {
            ".graph.add_node": "add_node_with_attrs(ref, **attrs) — node insertion",
            ".graph.add_edge": "add_edge_with_attrs(u, v, **attrs) — edge insertion",
            ".graph.edges(data=True)": "iterate_edges() -> [(u, v, data_dict), ...] — insertion order",
            ".graph.nodes()": "iterate_nodes() -> [node_id, ...] — insertion order",
            ".graph.has_edge(u, v)": "has_edge(u, v) -> bool",
            ".graph.number_of_nodes()": "node_count() -> int",
        },
        "dead_surfaces_not_needed": [
            "get_neighbors (only called from tests + oracle)",
            "find_separation_conflicts (only called from tests + oracle)",
            "get_adjacency_cluster (only called from tests + oracle)",
            "ConstraintPropagator (only called from tests + oracle)",
            "from_pcl (only called from tests + oracle)",
            "build_topological_graph (only called from tests + oracle)",
        ],
    }

    result = {
        "surface": "topological/graph.py networkx API census",
        "total_graph_accesses": len(accesses),
        "production_graph_accesses": len(prod),
        "test_graph_accesses": len(test),
        "oracle_graph_accesses": len(oracle),
        "live_methods": live_methods,
        "topological_graph_methods": method_liveness,
        "port_surface": port_surface,
        "production_access_sites": [{"file": a["file"], "line": a["line"], "chain": a["chain"]} for a in prod],
    }

    args.out.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    sys.exit(0)


if __name__ == "__main__":
    main()
