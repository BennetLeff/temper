"""Router-v6 migration survey: per-file measurement.

Emits one JSON record per module under ``router_v6/``. Every number the
survey document cites comes from here, so a reviewer can re-run it and
diff.

Fields
------
stmts          raw ``ast.stmt`` node count (the survey's statement metric)
stmts_nodoc    same, minus module/class/function docstring ``Expr`` nodes
body_stmts     ``stmts_nodoc`` minus imports and ``def``/``class`` headers
loc            physical lines
delegates      module imports a non-``temper_placer`` ``temper_*`` crate
crates         which ones
deps           third-party top-level imports (numpy, scipy, shapely, ...)
binops/loops   arithmetic and iteration node counts -- the compute-density proxy
ann_fields     class-level ``AnnAssign`` (dataclass/TypedDict field declarations)
raises/logs    control-flow-only statements that never leave Python cheaply

Usage: python .survey/measure.py <router_v6 dir> <repo root> > .survey/rows.json
"""

from __future__ import annotations

import ast
import json
import pathlib
import sys

STDLIB_ISH = {
    "__future__",
    "abc",
    "collections",
    "contextlib",
    "copy",
    "dataclasses",
    "enum",
    "functools",
    "heapq",
    "itertools",
    "json",
    "logging",
    "math",
    "os",
    "pathlib",
    "random",
    "re",
    "statistics",
    "sys",
    "time",
    "types",
    "typing",
    "warnings",
    "argparse",
    "hashlib",
    "textwrap",
    "traceback",
    "importlib",
    "bisect",
    "operator",
    "string",
    "subprocess",
    "shutil",
    "tempfile",
    "uuid",
    "datetime",
    "csv",
}


def _is_docstring_holder(node: ast.AST) -> bool:
    return isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))


def analyse(path: pathlib.Path, repo: pathlib.Path) -> dict:
    src = path.read_text()
    tree = ast.parse(src)

    stmts = 0
    docstrings = 0
    imports = 0
    funcs = 0
    classes = 0
    binops = 0
    loops = 0
    raises = 0
    ann_fields = 0
    calls = 0

    for node in ast.walk(tree):
        if isinstance(node, ast.stmt):
            stmts += 1
        if _is_docstring_holder(node):
            body = getattr(node, "body", None)
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                docstrings += 1
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imports += 1
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs += 1
        elif isinstance(node, ast.ClassDef):
            classes += 1
            ann_fields += sum(1 for b in node.body if isinstance(b, ast.AnnAssign))
        elif isinstance(node, (ast.BinOp, ast.AugAssign)):
            binops += 1
        elif isinstance(node, (ast.For, ast.While, ast.comprehension)):
            loops += 1
        elif isinstance(node, ast.Raise):
            raises += 1
        elif isinstance(node, ast.Call):
            calls += 1

    crates: set[str] = set()
    deps: set[str] = set()
    local: set[str] = set()
    for node in ast.walk(tree):
        heads: list[str] = []
        if isinstance(node, ast.Import):
            heads = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                local.add((node.module or "").split(".")[0])
                continue
            heads = [node.module or ""]
        for full in heads:
            head = full.split(".")[0]
            if not head:
                continue
            if head.startswith("temper_") and head != "temper_placer":
                crates.add(head)
            elif full.startswith("temper_placer.router_v6."):
                local.add(full.split(".")[2])
            elif head == "temper_placer":
                local.add("temper_placer:" + full.split(".")[1] if "." in full else "temper_placer")
            elif head not in STDLIB_ISH:
                deps.add(head)

    return {
        "path": str(path.relative_to(repo)),
        "name": path.stem,
        "stmts": stmts,
        "stmts_nodoc": stmts - docstrings,
        "body_stmts": stmts - docstrings - imports - funcs - classes,
        "loc": len(src.splitlines()),
        "imports": imports,
        "funcs": funcs,
        "classes": classes,
        "binops": binops,
        "loops": loops,
        "raises": raises,
        "ann_fields": ann_fields,
        "calls": calls,
        "deps": sorted(deps),
        "crates": sorted(crates),
        "delegates": bool(crates),
        "local_imports": sorted(m for m in local if m),
    }


def main() -> None:
    root = pathlib.Path(sys.argv[1]).resolve()
    repo = pathlib.Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else root
    rows = [analyse(p, repo) for p in sorted(root.rglob("*.py"))]
    json.dump(rows, sys.stdout, indent=1)


if __name__ == "__main__":
    main()
