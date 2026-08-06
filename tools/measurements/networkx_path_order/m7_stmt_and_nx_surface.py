#!/usr/bin/env python3
"""M7 -- how many statements move bucket, and what is left of networkx.

Spike S3.  Reports, for ``router_v6/channel_mapping.py``:

  * ``stmts``  -- raw ``ast.stmt`` nodes, the metric the router_v6
    migration survey's per-module table uses (it lists this module at
    203).
  * ``exec``   -- ``stmts`` minus docstrings and imports, the metric that
    survey uses for its percentages.
  * every syntactic reference to the ``networkx`` alias, so the claim
    "deleting the dead branch removes networkx from this module
    entirely" is checked rather than eyeballed.

Usage::

    python3 m7_stmt_and_nx_surface.py --repo <repo-root> --out result.json
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

TARGETS = [
    "packages/temper-placer/src/temper_placer/router_v6/channel_mapping.py",
    "packages/temper-placer/src/temper_placer/router_v6/topology_extraction.py",
]
DEAD_BRANCH_LINES = range(327, 349)  # `if not channel_sequence:` block


def counts(tree: ast.Module) -> tuple[int, int]:
    stmts = [n for n in ast.walk(tree) if isinstance(n, ast.stmt)]
    docstrings = 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                docstrings += 1
    imports = sum(1 for s in stmts if isinstance(s, (ast.Import, ast.ImportFrom)))
    return len(stmts), len(stmts) - docstrings - imports


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    root = args.repo.resolve()
    report: dict = {}

    for rel in TARGETS:
        src = (root / rel).read_text(encoding="utf-8")
        tree = ast.parse(src)
        stmts, execs = counts(tree)
        nx_refs = sorted(
            {
                n.lineno
                for n in ast.walk(tree)
                if (isinstance(n, ast.Name) and n.id == "nx")
                or (
                    isinstance(n, ast.Attribute)
                    and isinstance(n.value, ast.Name)
                    and n.value.id == "nx"
                )
            }
        )
        nx_imports = sorted(
            n.lineno
            for n in ast.walk(tree)
            if isinstance(n, (ast.Import, ast.ImportFrom)) and "networkx" in ast.unparse(n)
        )
        outside = [ln for ln in nx_refs if ln not in DEAD_BRANCH_LINES and ln not in nx_imports]
        report[rel] = {
            "stmts": stmts,
            "exec": execs,
            "networkx_import_lines": nx_imports,
            "nx_reference_lines": nx_refs,
            "nx_refs_outside_dead_branch_and_import": outside,
        }

    cm = report[TARGETS[0]]
    report["conclusion"] = {
        "channel_mapping_stmts_moving_bucket": cm["stmts"],
        "channel_mapping_exec_moving_bucket": cm["exec"],
        "deleting_dead_branch_removes_networkx_entirely": not cm[
            "nx_refs_outside_dead_branch_and_import"
        ],
    }

    args.out.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
