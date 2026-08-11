#!/usr/bin/env python3
"""M1 — reachability census: is ``topological/graph.py``'s ``TopologicalGraph`` live?

Counts every reference to ``TopologicalGraph`` imported from
``topological.graph`` in production code (``src/``), distinguishing
production call sites from test-only call sites.

Exits non-zero if the surface appears dead (0 production references),
so a future edit that removes the production path fails loudly.

NOTE: This distinguishes the *networkx* ``TopologicalGraph`` from
``topological/graph.py`` from the plain-dataclass ``TopologicalGraph`` in
``core/topology.py``. They share a name but are different classes.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path


def find_imports_of(file_path: Path, src_root: Path, base_package: str) -> list[dict]:
    """Find all files in ``src_root`` that import from ``file_path``.

    Searches for both the relative module path (e.g. ``topological.graph``)
    and the full package path (e.g. ``temper_placer.topological.graph``).
    """
    rel = str(file_path.relative_to(src_root).with_suffix("")).replace("/", ".")
    full = f"{base_package}.{rel}"
    candidates = {rel, full}
    results = []
    for f in sorted(src_root.rglob("*.py")):
        if f == file_path:
            continue
        tree = ast.parse(f.read_text(), filename=str(f))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module in candidates:
                    for alias in node.names:
                        results.append({
                            "file": str(f.relative_to(src_root)),
                            "line": node.lineno,
                            "imported_name": alias.name,
                            "module": node.module,
                        })
    return results


def find_callers_of_class(class_name: str, src_root: Path) -> list[dict]:
    """Find all files that construct ``class_name``."""
    results = []
    for f in sorted(src_root.rglob("*.py")):
        tree = ast.parse(f.read_text(), filename=str(f))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Direct construction: ClassName()
                if isinstance(node.func, ast.Name) and node.func.id == class_name:
                    results.append({
                        "file": str(f.relative_to(src_root)),
                        "line": node.lineno,
                        "kind": "constructor",
                    })
    return results


def main():
    parser = argparse.ArgumentParser(description="M1: TopologicalGraph reachability census")
    parser.add_argument("--repo", type=Path, required=True, help="Repository root")
    parser.add_argument("--out", type=Path, required=True, help="Output JSON file")
    args = parser.parse_args()

    src_root = args.repo / "packages" / "temper-placer" / "src" / "temper_placer"
    target_file = src_root / "topological" / "graph.py"

    if not target_file.exists():
        print(f"ERROR: target file not found: {target_file}", file=sys.stderr)
        sys.exit(2)

    # Who imports from topological.graph?
    imports = find_imports_of(target_file, src_root, "temper_placer")

    # Production vs test distinction
    production_imports = [i for i in imports if "/tests/" not in i["file"] and "tests/" not in i["file"] and "_py_oracle" not in i["file"]]
    test_imports = [i for i in imports if "/tests/" in i["file"] or "tests/" in i["file"]]
    oracle_imports = [i for i in imports if "_py_oracle" in i["file"]]

    # Count TopologicalGraph constructors in production code
    constructors = find_callers_of_class("TopologicalGraph", src_root)
    prod_constructors = [c for c in constructors if "/tests/" not in c["file"]]

    result = {
        "surface": "topological/graph.py::TopologicalGraph",
        "imports_total": len(imports),
        "imports_production": len(production_imports),
        "imports_test_only": len(test_imports),
        "production_importers": [i["file"] for i in production_imports],
        "production_constructors": prod_constructors,
        "reachable_in_production": len(production_imports) > 0 and len(prod_constructors) > 0,
        "notes": [],
    }

    # The pipeline registration check
    pipeline_file = src_root / "heuristics" / "__init__.py"
    pipeline_text = pipeline_file.read_text()
    if "TopologicalInitializationHeuristic" in pipeline_text:
        result["pipeline_registered"] = True
        # Check if it is actually called in create_default_pipeline
        if "TopologicalInitializationHeuristic(" in pipeline_text:
            result["pipeline_called"] = True
        else:
            result["pipeline_called"] = False
            result["notes"].append("TopologicalInitializationHeuristic imported but not constructed in create_default_pipeline")
    else:
        result["pipeline_registered"] = False

    # Also check: is ConstraintPropagator (propagation.py) called from production?
    propagation_file = src_root / "topological" / "propagation.py"
    propagator_imports = find_imports_of(propagation_file, src_root, "temper_placer")
    propagator_prod = [i for i in propagator_imports if "/tests/" not in i["file"] and "_py_oracle" not in i["file"]]
    result["constraint_propagator_production_callers"] = len(propagator_prod)
    if propagator_prod:
        result["notes"].append(f"ConstraintPropagator has {len(propagator_prod)} production callers")

    # Check: is get_neighbors called from production?
    graph_text = target_file.read_text()
    # Just grep for get_neighbors in src/ (excluding graph.py itself)
    gn_callers = []
    for f in sorted(src_root.rglob("*.py")):
        if f == target_file:
            continue
        text = f.read_text()
        if ".get_neighbors(" in text:
            gn_callers.append(str(f.relative_to(src_root)))
    result["get_neighbors_callers"] = gn_callers
    result["get_neighbors_production"] = [c for c in gn_callers if "/tests/" not in c]

    # Check: is find_separation_conflicts or get_adjacency_cluster called from production?
    fsc_callers = []
    gac_callers = []
    for f in sorted(src_root.rglob("*.py")):
        if f == target_file:
            continue
        text = f.read_text()
        if "find_separation_conflicts(" in text:
            fsc_callers.append(str(f.relative_to(src_root)))
        if "get_adjacency_cluster(" in text:
            gac_callers.append(str(f.relative_to(src_root)))
    result["find_separation_conflicts_production"] = [c for c in fsc_callers if "/tests/" not in c]
    result["get_adjacency_cluster_production"] = [c for c in gac_callers if "/tests/" not in c]

    # Summary
    is_live = result["reachable_in_production"] and result.get("pipeline_registered", False)
    result["verdict"] = "LIVE" if is_live else "DEAD"

    args.out.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))

    if not is_live:
        print("F-T1 FIRED: surface is DEAD — 0 production reachability", file=sys.stderr)
        sys.exit(1)
    else:
        print("F-T1 DID NOT FIRE: surface is LIVE", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
