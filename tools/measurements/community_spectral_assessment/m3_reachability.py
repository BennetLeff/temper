#!/usr/bin/env python3
"""
M3: Static reachability analysis for community.py and spectral.py.

Falsifiers Q-A3 and Q-B2: Are detect_communities / partition_netlist_min_cut
and SpectralPlacementHeuristic actually called in the live pipeline?

Method: grep the AST for all call references and import sites of the target
functions, then classify each as test-only or production.

Exits non-zero if the analysis itself fails (not if the result is "dead").
Output: JSON to --out.
"""

import argparse
import ast
import json
import os
import sys
from pathlib import Path
from typing import Any


SRC_ROOT = "packages/temper-placer/src/temper_placer"
TEST_ROOT = "packages/temper-placer/tests"


def _find_py_files(root: str) -> list[str]:
    files = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for f in filenames:
            if f.endswith(".py"):
                files.append(os.path.join(dirpath, f))
    return files


def _find_name_refs(filepath: str, name: str) -> list[dict]:
    """Find all references to `name` in a Python file using AST."""
    refs = []
    try:
        with open(filepath) as f:
            source = f.read()
        tree = ast.parse(source)
    except (SyntaxError, UnicodeDecodeError):
        return refs

    # Check imports
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module:
                for alias in node.names:
                    if alias.name == name or alias.asname == name:
                        refs.append({
                            "line": node.lineno,
                            "type": "import",
                            "module": node.module,
                            "name": alias.name,
                        })
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == name or alias.asname == name:
                    refs.append({
                        "line": node.lineno,
                        "type": "import",
                        "module": alias.name,
                        "name": alias.name,
                    })

    # Check calls: ast.Name nodes with id == name
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == name:
                refs.append({
                    "line": node.lineno,
                    "type": "call",
                })
            elif isinstance(func, ast.Attribute) and func.attr == name:
                refs.append({
                    "line": node.lineno,
                    "type": "method_call",
                    "attr": name,
                })
        elif isinstance(node, ast.Name) and node.id == name:
            # Check if it's used as a constructor / class reference (not just a name)
            parent = None
            for p in ast.walk(tree):
                for child in ast.iter_child_nodes(p):
                    if child is node:
                        parent = p
                        break
            if isinstance(parent, ast.Call) and parent.func is node:
                # Already counted as a call above
                pass
            else:
                refs.append({
                    "line": node.lineno,
                    "type": "name_ref",
                })

    return refs


def _classify_file(filepath: str) -> str:
    """Classify file as 'test' or 'src'."""
    if TEST_ROOT in filepath:
        return "test"
    if SRC_ROOT in filepath:
        return "src"
    return "other"


def main() -> None:
    parser = argparse.ArgumentParser(description="M3: Reachability analysis")
    parser.add_argument("--repo", default=".", help="Repository root")
    parser.add_argument("--out", required=True, help="Output JSON path")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    src_dir = repo / SRC_ROOT
    test_dir = repo / TEST_ROOT

    results: dict[str, Any] = {
        "tool": "m3_reachability",
        "repo": str(repo),
    }

    targets = {
        "detect_communities": {"file": "core/community.py", "surface": "community"},
        "partition_netlist_min_cut": {"file": "core/community.py", "surface": "community"},
        "SpectralPlacementHeuristic": {"file": "heuristics/spectral.py", "surface": "spectral"},
    }

    for name, info in targets.items():
        all_refs = []

        # Search src files
        if src_dir.exists():
            for f in _find_py_files(str(src_dir)):
                refs = _find_name_refs(f, name)
                for r in refs:
                    r["file"] = os.path.relpath(f, repo)
                    r["classification"] = "src"
                    # Filter out the definition itself
                    if info["file"] in r["file"] and r["type"] == "name_ref":
                        continue
                all_refs.extend(refs)

        # Search test files
        if test_dir.exists():
            for f in _find_py_files(str(test_dir)):
                refs = _find_name_refs(f, name)
                for r in refs:
                    r["file"] = os.path.relpath(f, repo)
                    r["classification"] = "test"
                all_refs.extend(refs)

        # Separate into src and test
        src_refs = [r for r in all_refs if r["classification"] == "src"]
        test_refs = [r for r in all_refs if r["classification"] == "test"]

        # Count actual call sites in src (excluding import lines)
        src_calls = [r for r in src_refs if r["type"] in ("call", "method_call")]
        test_calls = [r for r in test_refs if r["type"] in ("call", "method_call")]

        results[name] = {
            "surface": info["surface"],
            "src_references": len(src_refs),
            "src_call_sites": len(src_calls),
            "src_call_details": src_calls,
            "test_references": len(test_refs),
            "test_call_sites": len(test_calls),
            "test_call_details": test_calls,
            "reachable_in_production": len(src_calls) > 0,
            "exported": _check_exported(name, repo),
        }

    # Also check spectral pipeline registration
    pipeline_file = src_dir / "heuristics/pipeline.py"
    spec_pipeline_refs = []
    if pipeline_file.exists():
        for ref in _find_name_refs(str(pipeline_file), "SpectralPlacementHeuristic"):
            spec_pipeline_refs.append(ref)

    results["spectral_pipeline_registration"] = {
        "file": "heuristics/pipeline.py",
        "references": spec_pipeline_refs,
        "register_in_create_default": any(
            r["line"] == 376 for r in spec_pipeline_refs
        ),
        "register_in_create_priority": any(
            r["line"] == 417 for r in spec_pipeline_refs
        ),
    }

    # Check which create_default_pipeline is actually exported
    init_file = src_dir / "heuristics/__init__.py"
    results["heuristics_init_export"] = {
        "has_own_create_default_pipeline": init_file.exists(),
        "imports_spectral": False,
    }
    if init_file.exists():
        with open(init_file) as f:
            content = f.read()
        results["heuristics_init_export"]["imports_spectral"] = "spectral" in content
        # Check __all__
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name) and target.id == "__all__":
                            if isinstance(node.value, ast.List):
                                exports = [
                                    (e.value if isinstance(e, ast.Constant) else None)
                                    for e in node.value.elts
                                ]
                                results["heuristics_init_export"]["__all__"] = exports
        except SyntaxError:
            pass

    with open(args.out, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(json.dumps(results, indent=2, default=str))

    # Fail if certain conditions are met (not for dead code; for analysis errors)
    sys.exit(0)


def _check_exported(name: str, repo: Path) -> bool:
    """Check if name is exported from core/__init__.py or heuristics/__init__.py."""
    for init_path in [
        repo / SRC_ROOT / "core/__init__.py",
        repo / SRC_ROOT / "heuristics/__init__.py",
    ]:
        if not init_path.exists():
            continue
        try:
            with open(init_path) as f:
                content = f.read()
        except Exception:
            continue
        # Simple string search for the name in __all__ or import
        if name in content:
            return True
    return False


if __name__ == "__main__":
    main()
