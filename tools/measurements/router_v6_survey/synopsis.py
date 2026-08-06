"""Router-v6 migration survey: per-module synopsis.

Prints the first docstring line plus every top-level ``def``/``class`` name
for each module, so a reviewer can see at a glance what a module exposes
without opening 100 files.
"""

from __future__ import annotations

import ast
import pathlib
import sys

root = pathlib.Path(sys.argv[1]).resolve()
only = sys.argv[2] if len(sys.argv) > 2 else ""

for path in sorted(root.rglob("*.py")):
    key = str(path.relative_to(root))
    if only and only not in key:
        continue
    tree = ast.parse(path.read_text())
    doc = (ast.get_docstring(tree) or "").strip().splitlines()
    head = doc[0] if doc else "(no docstring)"
    print(f"\n### {key}\n{head}")
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            n_stmt = sum(1 for x in ast.walk(node) if isinstance(x, ast.stmt))
            print(f"  def {node.name}  [{n_stmt}]")
        elif isinstance(node, ast.ClassDef):
            n_stmt = sum(1 for x in ast.walk(node) if isinstance(x, ast.stmt))
            bases = ",".join(ast.unparse(b) for b in node.bases)
            decs = ",".join(ast.unparse(d) for d in node.decorator_list)
            print(f"  class {node.name}({bases}) @{decs}  [{n_stmt}]")
