#!/usr/bin/env python3
"""Precise importer census for a candidate module: resolves absolute imports,
relative imports, __init__ re-exports, and Rust py.import()/getattr()."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path("/home/bennet/Desktop/temper")
SRC = ROOT / "packages/temper-placer/src/temper_placer"
EX = {
    ".git",
    ".claude",
    ".worktrees",
    ".venv",
    "__pycache__",
    ".mypy_cache",
    "target-shared",
    "target",
}
ROOTS = [
    SRC,
    ROOT / "packages/temper-workflow",
    ROOT / "scripts",
    ROOT / "tools",
    ROOT / "benchmarks",
    ROOT / "elec",
    ROOT / "packages/temper-placer/tests",
    ROOT / "simulation",
    ROOT / "dashboard",
    ROOT / "metrics",
    ROOT / "firmware",
]


def modname(p: Path) -> str:
    rel = p.relative_to(SRC)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][:-3]
    return ".".join(["temper_placer"] + parts)


def rel_base(c: Path, level: int, mod: str | None) -> str | None:
    try:
        rel = c.relative_to(SRC)
    except ValueError:
        return None
    base = ["temper_placer"] + list(rel.parts[:-1])
    if level - 1 > 0:
        base = base[: len(base) - (level - 1)]
    if not base:
        return None
    return ".".join(base + ([mod] if mod else []))


target = sys.argv[1]  # dotted module path
leaf = target.rsplit(".", 1)[-1]
hits: list[str] = []
for r in ROOTS:
    if not r.exists():
        continue
    for c in r.rglob("*.py"):
        if EX & set(c.parts):
            continue
        if (
            str(c.relative_to(ROOT))
            == target.replace(
                "temper_placer.", "packages/temper-placer/src/temper_placer/"
            ).replace(".", "/")
            + ".py"
        ):
            continue
        try:
            tree = ast.parse(c.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        names: set[str] = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                names.update(a.name for a in n.names)
            elif isinstance(n, ast.ImportFrom):
                base = rel_base(c, n.level, n.module) if n.level else n.module
                if base:
                    names.add(base)
                    names.update(f"{base}.{a.name}" for a in n.names)
        if target in names:
            rp = str(c.relative_to(ROOT))
            kind = "TEST" if "/tests/" in rp or "/tests" in rp.split("/")[:-1] else "PROD"
            hits.append(f"  [{kind}] {rp}")
print(f"Python importers of {target}: {len(hits)}")
for h in sorted(hits):
    print(h)
rust = []
for rs in ROOT.rglob("*.rs"):
    if EX & set(rs.parts):
        continue
    t = rs.read_text(encoding="utf-8", errors="replace")
    if target in t or re.search(rf'getattr\("{re.escape(leaf)}"\)', t):
        rust.append(str(rs.relative_to(ROOT)))
print(f"Rust files naming '{target}' or getattr('{leaf}'): {len(rust)}")
for r in sorted(rust):
    print("  ", r)
