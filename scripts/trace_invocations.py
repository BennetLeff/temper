#!/usr/bin/env python3
r"""Invocation tracer: scan repo for all call sites of scripts/ files.

Parses CI workflows, shell scripts, Makefile, Python source files, and
pyproject.toml to build a call graph mapping each scripts/<name>.py to its
caller paths. Excludes stale worktree references and self-references.
Output: scripts/invocation_graph.json.
Usage: uv run python scripts/trace_invocations.py [--repo-root PATH]
"""

import argparse, json, re, sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CI_RUN_RE = re.compile(r"""scripts/([\w_-]+\.py)""")
PYTHON_STR_RE = re.compile(r"""(["'])(.*?scripts/([\w_-]+\.py).*?)\1""")

def is_stale(caller): return caller.startswith((".worktrees/", ".claude/"))

def scan_ci(repo):
    g = {}
    d = repo / ".github" / "workflows"
    if not d.is_dir(): return g
    for p in sorted(d.glob("*.yml")):
        rel = str(p.relative_to(repo))
        try:
            for m in CI_RUN_RE.finditer(p.read_text()):
                n = m.group(1)
                if n.endswith(".py"): g.setdefault(n, []).append(rel)
        except: pass
    return g

def scan_sh(repo):
    g = {}
    cand = list(repo.rglob("*.sh")) + [repo / "Makefile"]
    ex = str(repo / "benchmarks" / "downloads")
    for p in sorted(cand):
        if str(p).startswith(ex): continue
        rel = str(p.relative_to(repo))
        try:
            for m in CI_RUN_RE.finditer(p.read_text()):
                n = m.group(1)
                if n.endswith(".py"): g.setdefault(n, []).append(rel)
        except: pass
    return g

def scan_py(repo):
    g = {}
    ex = {str(repo / "benchmarks" / "downloads"), str(repo / "scripts" / "__pycache__")}
    for p in sorted(repo.rglob("*.py")):
        if any(str(p).startswith(d) for d in ex): continue
        rel = str(p.relative_to(repo))
        try:
            for m in PYTHON_STR_RE.finditer(p.read_text()):
                n = m.group(3)
                if n.endswith(".py"): g.setdefault(n, []).append(rel)
        except: pass
    return g

def scan_ppt(repo):
    g = {}
    ppt = repo / "pyproject.toml"
    if not ppt.is_file(): return g
    for m in CI_RUN_RE.finditer(ppt.read_text()):
        n = m.group(1)
        if n.endswith(".py"): g.setdefault(n, []).append("pyproject.toml")
    return g

def merge(*gs):
    m = {}
    for g in gs:
        for n, cs in g.items():
            ex = m.setdefault(n, [])
            for c in cs:
                if c not in ex: ex.append(c)
    return m

def filter_graph(g):
    f = {}
    for n, cs in g.items():
        clean = [c for c in cs if not is_stale(c) and c != f"scripts/{n}"]
        f[n] = sorted(set(clean))
    return f

def main():
    p = argparse.ArgumentParser(description="Trace script invocations")
    p.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    p.add_argument("--output", type=Path, default=None)
    a = p.parse_args()
    r = a.repo_root.resolve()
    cg = filter_graph(merge(scan_ci(r), scan_sh(r), scan_py(r), scan_ppt(r)))
    scripts = sorted(f.name for f in (r / "scripts").glob("*.py"))
    invoked = [n for n in scripts if cg.get(n)]
    out = {"repository_root": str(r), "call_graph": {n: cg.get(n, []) for n in scripts},
           "summary": {"total_scripts": len(scripts), "invoked_scripts": len(invoked),
                       "uninvoked_scripts": len(scripts) - len(invoked)}}
    op = a.output or (r / "scripts" / "invocation_graph.json")
    with open(op, "w") as f: json.dump(out, f, indent=2); f.write("\n")
    print(f"Traced {out['summary']['total_scripts']} scripts, {out['summary']['invoked_scripts']} invoked")
    if invoked:
        for n in invoked: print(f"  {n} <- {', '.join(cg[n])}")
    print(f"Written to {op}")
if __name__ == "__main__": main()
