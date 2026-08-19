#!/usr/bin/env python3
"""For each candidate module: are ALL its importers test files that import
nothing else from temper_placer? Such a test file is *dedicated* -- deleting
the module and that file removes no coverage of any other module."""

from __future__ import annotations

import ast
import json
import os
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
D = Path(os.environ.get("DECOMP_WORKDIR", "/tmp/decomp-map"))


def imported_tp_modules(path: Path) -> set[str]:
    """temper_placer modules a file imports (top-level name resolution only)."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, OSError):
        return set()
    out: set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.name.startswith("temper_placer."):
                    out.add(a.name)
        elif isinstance(n, ast.ImportFrom) and n.module and n.module.startswith("temper_placer."):
            out.add(n.module)
    return out


inv = json.load(open(D / "inventory.json"))
static = json.load(open(D / "static.json"))
cands = []
for r in inv["units"]:
    if r["kind"] != "src-module" or r["evidence_class"] == "E5-protected":
        continue
    if r["disposition"] in ("owned-elsewhere", "port-to-rust"):
        continue
    if any(k in ("route", "closure", "regression") for k in r["executed_in"]):
        continue  # live on a production probe
    imps = static[r["path"]]["static_importers"]
    if not imps:
        continue
    if any("/tests/" not in i or "tests/requirements/validators/" in i for i in imps):
        continue  # a non-test importer exists
    if static[r["path"]]["rust_imports_module"] or static[r["path"]]["rust_getattr_names"]:
        continue
    mod = static[r["path"]]["module"]
    dedicated, mixed = [], []
    for i in imps:
        others = imported_tp_modules(ROOT / i) - {mod}
        others = {o for o in others if not o.startswith(mod + ".")}
        (dedicated if not others else mixed).append(i)
    cands.append(
        {
            "path": r["path"],
            "loc": r["loc"],
            "module": mod,
            "executed_in": r["executed_in"],
            "imported_only_in": r["imported_only_in"],
            "dedicated_test_importers": dedicated,
            "mixed_test_importers": mixed,
        }
    )
cands.sort(key=lambda c: (bool(c["mixed_test_importers"]), -c["loc"]))
clean = [c for c in cands if not c["mixed_test_importers"]]
print(f"{len(cands)} cold, test-only-imported modules; {len(clean)} have NO mixed-file importer")
print(f"clean LOC total: {sum(c['loc'] for c in clean):,}\n")
for c in clean:
    print(
        f"  {c['loc']:5d}  {c['path'].replace('packages/temper-placer/src/temper_placer/', 'TP/')}"
    )
    for t in c["dedicated_test_importers"]:
        print(f"          dedicated test: {t}")
json.dump(cands, open(D / "dedicated.json", "w"), indent=1)
