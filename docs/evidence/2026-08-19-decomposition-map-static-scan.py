#!/usr/bin/env python3
"""Static candidate generator for the decomposition map.

Produces CANDIDATES ONLY. Nothing here promotes a unit to a finding; that
requires execution evidence (coverage over the real route + the real suite).
"""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path("/home/bennet/Desktop/temper")
SRC = ROOT / "packages/temper-placer/src/temper_placer"
WF = ROOT / "packages/temper-workflow/src"
SCRIPTS = ROOT / "scripts"

EXCLUDE_PARTS = {
    ".git",
    ".claude",
    ".worktrees",
    ".venv",
    "__pycache__",
    "target-shared",
    "node_modules",
    "target",
}


def walk_py(base: Path):
    for p in base.rglob("*.py"):
        if EXCLUDE_PARTS & set(p.parts):
            continue
        yield p


# ---- 1. unit table -------------------------------------------------------
units = {}


def modname_for(p: Path) -> str | None:
    """Dotted module name for a file under either src root."""
    for base, top in ((SRC, "temper_placer"), (WF / "temper_workflow", "temper_workflow")):
        try:
            rel = p.relative_to(base)
            break
        except ValueError:
            continue
    else:
        return None
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][:-3]
    return ".".join([top] + parts)


for p in walk_py(SRC):
    loc = sum(1 for _ in p.open(encoding="utf-8", errors="replace"))
    units[str(p.relative_to(ROOT))] = {
        "path": str(p.relative_to(ROOT)),
        "kind": "src-module",
        "module": modname_for(p),
        "loc": loc,
    }
for p in walk_py(WF):
    loc = sum(1 for _ in p.open(encoding="utf-8", errors="replace"))
    units[str(p.relative_to(ROOT))] = {
        "path": str(p.relative_to(ROOT)),
        "kind": "src-module",
        "module": modname_for(p),
        "loc": loc,
    }
for p in sorted(SCRIPTS.rglob("*.py")):
    if EXCLUDE_PARTS & set(p.parts):
        continue
    loc = sum(1 for _ in p.open(encoding="utf-8", errors="replace"))
    units[str(p.relative_to(ROOT))] = {
        "path": str(p.relative_to(ROOT)),
        "kind": "script",
        "module": None,
        "loc": loc,
    }

# ---- 2. import graph over all consumer roots -----------------------------
CONSUMER_ROOTS = [
    SRC,
    WF,
    SCRIPTS,
    ROOT / "packages/temper-placer/tests",
    ROOT / "packages/temper-workflow/tests",
    ROOT / "tools",
    ROOT / "benchmarks",
    ROOT / "elec",
    ROOT / "simulation",
    ROOT / "dashboard",
    ROOT / "firmware",
    ROOT / "metrics",
]

# map module name -> unit path
mod_to_path = {u["module"]: u["path"] for u in units.values() if u.get("module")}

importers: dict[str, set[str]] = {p: set() for p in units}


def record(mod: str, consumer: Path):
    # resolve mod and all its prefixes that name a real unit
    if mod in mod_to_path:
        importers[mod_to_path[mod]].add(str(consumer.relative_to(ROOT)))


def resolve_rel(consumer: Path, level: int, mod: str | None) -> str | None:
    for base, top in ((SRC, "temper_placer"), (WF / "temper_workflow", "temper_workflow")):
        try:
            rel = consumer.relative_to(base)
            break
        except ValueError:
            continue
    else:
        return None
    pkg = [top] + list(rel.parts[:-1])
    if consumer.name != "__init__.py":
        base = pkg
    else:
        base = pkg
    # level 1 = current package
    if level - 1 > 0:
        base = base[: len(base) - (level - 1)]
    if not base:
        return None
    return ".".join(base + ([mod] if mod else []))


for croot in CONSUMER_ROOTS:
    if not croot.exists():
        continue
    for c in walk_py(croot):
        try:
            tree = ast.parse(c.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    record(a.name, c)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    base = resolve_rel(c, node.level, node.module)
                    if base:
                        record(base, c)
                        for a in node.names:
                            record(f"{base}.{a.name}", c)
                elif node.module:
                    record(node.module, c)
                    for a in node.names:
                        record(f"{node.module}.{a.name}", c)

# ---- 3. dynamic-dispatch surfaces ----------------------------------------
rust_imports = set()
rust_getattrs = set()
for rs in ROOT.rglob("*.rs"):
    if EXCLUDE_PARTS & set(rs.parts):
        continue
    t = rs.read_text(encoding="utf-8", errors="replace")
    # NOTE: matching only `py.import("...")` is NOT enough. pyo3 call chains
    # get rustfmt-wrapped, so the receiver often ends up on the previous line
    # and the call reads `    .import("temper_placer.io.isolation_slot_geometry")?`
    # (zone_aware_slot_generation_stage.rs:258 -- a real runtime Rust->Python
    # import this scanner missed on its first pass). Match the method call
    # itself, not the receiver.
    rust_imports.update(re.findall(r'\.import\(\s*"([^"]+)"\s*\)', t))
    rust_imports.update(re.findall(r'import_module\(\s*"([^"]+)"\s*\)', t))
    rust_imports.update(re.findall(r'PyModule::import\([^,]*,\s*"([^"]+)"', t))
    rust_getattrs.update(re.findall(r'getattr\("([^"]+)"\)', t))

manifest_paths = set()
mtxt = (SCRIPTS / "manifest.yaml").read_text(encoding="utf-8")
manifest_paths.update(re.findall(r"^- path: (.+)$", mtxt, re.M))

# CI / Makefile / manifest textual references
ref_blobs = []
for f in (
    list((ROOT / ".github/workflows").rglob("*.yml"))
    + list((ROOT / ".github/workflows").rglob("*.yaml"))
    + [ROOT / "Makefile"]
):
    if f.exists():
        ref_blobs.append(f.read_text(encoding="utf-8", errors="replace"))
CI_TEXT = "\n".join(ref_blobs)

# top-level names defined per module (for rust getattr matching)
for path, u in units.items():
    p = ROOT / path
    try:
        tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        tree = None
    names = set()
    if tree:
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name):
                        names.add(t.id)
    u["defines"] = sorted(names)
    u["static_importers"] = sorted(importers[path])
    u["n_static_importers"] = len(importers[path])
    mod = u.get("module")
    u["rust_imports_module"] = bool(mod and mod in rust_imports)
    u["rust_getattr_names"] = sorted(names & rust_getattrs)
    if u["kind"] == "script":
        rel = path[len("scripts/") :]
        u["in_manifest"] = rel in manifest_paths
        u["ci_referenced"] = path in CI_TEXT or rel in CI_TEXT
    else:
        u["in_manifest"] = None
        u["ci_referenced"] = path in CI_TEXT
    u["is_oracle"] = bool(re.match(r"_.*_py_oracle\.py$", p.name))

json.dump(units, open(sys.argv[1], "w"), indent=1, sort_keys=True)
print(f"units={len(units)}  rust_imports={len(rust_imports)} rust_getattrs={len(rust_getattrs)}")
