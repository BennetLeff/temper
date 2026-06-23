#!/usr/bin/env python3
r"""Invocation tracer: scan repo for all call sites of scripts/ files.

Parses CI workflows, shell scripts, Makefile, Python source files, and
pyproject.toml to build a call graph mapping each scripts/<name>.py to its
caller paths. Excludes stale worktree references and self-references.

Output: scripts/invocation_graph.json (committed, so CI can diff it).

Usage:
    uv run python scripts/trace_invocations.py [--repo-root PATH]
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

CI_RUN_RE = re.compile(r"""scripts/([\w_-]+\.py)""")
PYTHON_STR_RE = re.compile(r"""(["'])(.*?scripts/([\w_-]+\.py).*?)\1""")


def is_stale_worktree_path(caller: str) -> bool:
    stale_prefixes = (".worktrees/", ".claude/")
    return caller.startswith(stale_prefixes)


def scan_ci_workflows(repo_root: Path) -> dict[str, list[str]]:
    call_graph: dict[str, list[str]] = {}
    workflows_dir = repo_root / ".github" / "workflows"
    if not workflows_dir.is_dir():
        return call_graph
    for wf_path in sorted(workflows_dir.glob("*.yml")):
        rel = str(wf_path.relative_to(repo_root))
        try:
            content = wf_path.read_text()
        except Exception:
            continue
        for line in content.splitlines():
            for m in CI_RUN_RE.finditer(line):
                script_name = m.group(1)
                if script_name.endswith(".py"):
                    call_graph.setdefault(script_name, []).append(rel)
    return call_graph


def scan_shell_scripts(repo_root: Path) -> dict[str, list[str]]:
    call_graph: dict[str, list[str]] = {}
    candidates = list(repo_root.rglob("*.sh"))
    makefile = repo_root / "Makefile"
    if makefile.is_file():
        candidates.append(makefile)
    exclude_prefix = str(repo_root / "benchmarks" / "downloads")
    for file_path in sorted(candidates):
        if str(file_path).startswith(exclude_prefix):
            continue
        rel = str(file_path.relative_to(repo_root))
        try:
            content = file_path.read_text()
        except Exception:
            continue
        for line in content.splitlines():
            for m in CI_RUN_RE.finditer(line):
                script_name = m.group(1)
                if script_name.endswith(".py"):
                    call_graph.setdefault(script_name, []).append(rel)
    return call_graph


def scan_python_string_refs(repo_root: Path) -> dict[str, list[str]]:
    call_graph: dict[str, list[str]] = {}
    exclude_dirs = {
        str(repo_root / "benchmarks" / "downloads"),
        str(repo_root / "scripts" / "__pycache__"),
    }
    for py_path in sorted(repo_root.rglob("*.py")):
        if any(str(py_path).startswith(d) for d in exclude_dirs):
            continue
        rel = str(py_path.relative_to(repo_root))
        try:
            content = py_path.read_text()
        except Exception:
            continue
        for m in PYTHON_STR_RE.finditer(content):
            script_name = m.group(3)
            if script_name.endswith(".py"):
                call_graph.setdefault(script_name, []).append(rel)
    return call_graph


def scan_pyproject_toml(repo_root: Path) -> dict[str, list[str]]:
    call_graph: dict[str, list[str]] = {}
    ppt = repo_root / "pyproject.toml"
    if not ppt.is_file():
        return call_graph
    try:
        content = ppt.read_text()
    except Exception:
        return call_graph
    for line in content.splitlines():
        for m in CI_RUN_RE.finditer(line):
            script_name = m.group(1)
            if script_name.endswith(".py"):
                call_graph.setdefault(script_name, []).append("pyproject.toml")
    return call_graph


def merge_call_graphs(*graphs: dict[str, list[str]]) -> dict[str, list[str]]:
    merged: dict[str, list[str]] = {}
    for g in graphs:
        for script_name, callers in g.items():
            existing = merged.setdefault(script_name, [])
            for caller in callers:
                if caller not in existing:
                    existing.append(caller)
    return merged


def filter_call_graph(call_graph: dict[str, list[str]]) -> dict[str, list[str]]:
    filtered: dict[str, list[str]] = {}
    for script_name, callers in call_graph.items():
        clean = []
        for c in callers:
            if is_stale_worktree_path(c):
                continue
            if c == f"scripts/{script_name}":
                continue
            clean.append(c)
        filtered[script_name] = sorted(set(clean))
    return filtered


def main():
    parser = argparse.ArgumentParser(
        description="Trace script invocations across the repo"
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Path to repository root",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path for JSON call graph (default: scripts/invocation_graph.json)",
    )
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()

    ci_graph = scan_ci_workflows(repo_root)
    shell_graph = scan_shell_scripts(repo_root)
    py_string_graph = scan_python_string_refs(repo_root)
    ppt_graph = scan_pyproject_toml(repo_root)

    raw_graph = merge_call_graphs(ci_graph, shell_graph, py_string_graph, ppt_graph)
    call_graph = filter_call_graph(raw_graph)

    all_scripts = sorted(f.name for f in (repo_root / "scripts").glob("*.py"))

    invoked = [n for n in all_scripts if call_graph.get(n)]
    uninvoked = [n for n in all_scripts if not call_graph.get(n)]

    output = {
        "repository_root": str(repo_root),
        "call_graph": {name: call_graph.get(name, []) for name in all_scripts},
        "summary": {
            "total_scripts": len(all_scripts),
            "invoked_scripts": len(invoked),
            "uninvoked_scripts": len(uninvoked),
        },
    }

    output_path = args.output or (repo_root / "scripts" / "invocation_graph.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2)
        f.write("\n")

    print(f"Traced {output['summary']['total_scripts']} scripts")
    print(f"  Invoked: {output['summary']['invoked_scripts']}")
    print(f"  Uninvoked: {output['summary']['uninvoked_scripts']}")
    if invoked:
        print("\nInvoked scripts:")
        for name in invoked:
            callers = ", ".join(call_graph[name])
            print(f"  {name} <- {callers}")
    print(f"\nCall graph written to {output_path}")


if __name__ == "__main__":
    main()
