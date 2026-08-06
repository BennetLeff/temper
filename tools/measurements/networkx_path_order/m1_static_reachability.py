#!/usr/bin/env python3
"""M1 -- static reachability of the ``nx.shortest_path`` call sites in
``router_v6/channel_mapping.py`` (lines 339 and 343).

Spike S3.  The claim under test is a dominance argument:

    Both ``nx.shortest_path`` calls live inside
    ``_extract_waypoints``'s ``if not channel_sequence:`` branch.
    ``_extract_waypoints`` has exactly one call site in the repository.
    That call site is preceded, in the same (unconditional) statement
    list, by ``if not channel_sequence: return None``, and
    ``channel_sequence`` is not rebound in between.
    Therefore ``channel_sequence`` is truthy at every entry to
    ``_extract_waypoints``, the ``if not channel_sequence:`` branch is
    never taken, and lines 339/343 are unreachable.

Every step is checked mechanically against the AST rather than asserted,
and the script exits non-zero if any step fails -- so a future edit that
breaks the dominance makes this measurement fail loudly instead of
silently going stale.

Usage::

    python3 m1_static_reachability.py --repo <repo-root> --out result.json
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

TARGET = "packages/temper-placer/src/temper_placer/router_v6/channel_mapping.py"
FUNC_UNDER_TEST = "_extract_waypoints"
CALLER = "_map_net_to_channels"
GUARDED_VAR = "channel_sequence"

SKIP_DIRS = {".git", ".venv", "node_modules", "build", "target", "__pycache__", ".claude"}


def iter_py_files(root: Path):
    for p in root.rglob("*.py"):
        # Only inspect the path *relative to the repo root* -- the repo may
        # itself live under a skipped-looking directory (e.g. a worktree
        # under .claude/worktrees/), which would otherwise skip everything.
        if any(part in SKIP_DIRS for part in p.relative_to(root).parts):
            continue
        yield p


def find_references(root: Path, name: str) -> list[dict]:
    """Every syntactic reference to *name* in the repo, call or not."""
    hits: list[dict] = []
    for path in iter_py_files(root):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            is_ref = (isinstance(node, ast.Name) and node.id == name) or (
                isinstance(node, ast.Attribute) and node.attr == name
            )
            if not is_ref:
                continue
            hits.append(
                {
                    "file": str(path.relative_to(root)),
                    "line": node.lineno,
                    "kind": type(node).__name__,
                }
            )
        # def-site is a FunctionDef, not a Name -- record separately
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == name:
                hits.append(
                    {
                        "file": str(path.relative_to(root)),
                        "line": node.lineno,
                        "kind": "FunctionDef",
                    }
                )
    return sorted(hits, key=lambda h: (h["file"], h["line"]))


def get_func(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise LookupError(name)


def is_falsy_guard(stmt: ast.stmt, var: str) -> bool:
    """``if not <var>: return None`` (or any unconditional return)."""
    if not isinstance(stmt, ast.If):
        return False
    t = stmt.test
    if not (isinstance(t, ast.UnaryOp) and isinstance(t.op, ast.Not)):
        return False
    if not (isinstance(t.operand, ast.Name) and t.operand.id == var):
        return False
    return len(stmt.body) == 1 and isinstance(stmt.body[0], ast.Return)


def calls_func(node: ast.AST, name: str) -> bool:
    return any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == name
        for n in ast.walk(node)
    )


def rebinds(stmt: ast.stmt, var: str) -> bool:
    for n in ast.walk(stmt):
        if isinstance(n, ast.Name) and n.id == var and isinstance(n.ctx, ast.Store):
            return True
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    root = args.repo.resolve()
    target = root / TARGET
    tree = ast.parse(target.read_text(encoding="utf-8"))

    checks: dict[str, object] = {}
    ok = True

    # --- 1. where does nx.shortest_path get called? -----------------
    fn = get_func(tree, FUNC_UNDER_TEST)
    nx_calls = [
        n.lineno
        for n in ast.walk(fn)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "shortest_path"
    ]
    checks["nx_shortest_path_lines"] = nx_calls

    # Are they all inside the `if not channel_sequence:` branch?
    guard_in_callee = next(
        (s for s in fn.body if is_falsy_guard_block(s, GUARDED_VAR)),
        None,
    )
    if guard_in_callee is None:
        ok = False
        checks["callee_guard_block"] = None
    else:
        span = (
            guard_in_callee.lineno,
            max(getattr(n, "lineno", 0) for n in ast.walk(guard_in_callee)),
        )
        checks["callee_guard_block"] = {"if_line": span[0], "last_line": span[1]}
        inside = all(span[0] <= ln <= span[1] for ln in nx_calls)
        checks["all_nx_calls_inside_empty_sequence_branch"] = inside
        ok = ok and inside and bool(nx_calls)

    # --- 2. how many call sites does _extract_waypoints have? -------
    refs = find_references(root, FUNC_UNDER_TEST)
    call_sites = [r for r in refs if r["kind"] == "Name"]
    checks["all_references"] = refs
    checks["call_site_count"] = len(call_sites)
    checks["call_sites"] = call_sites
    single = len(call_sites) == 1
    checks["exactly_one_call_site"] = single
    ok = ok and single

    # --- 3. is that call site dominated by the truthiness guard? ----
    caller = get_func(tree, CALLER)
    guard_idx = next((i for i, s in enumerate(caller.body) if is_falsy_guard(s, GUARDED_VAR)), None)
    call_idx = next((i for i, s in enumerate(caller.body) if calls_func(s, FUNC_UNDER_TEST)), None)
    checks["caller"] = CALLER
    checks["guard_stmt_index"] = guard_idx
    checks["call_stmt_index"] = call_idx
    if guard_idx is None or call_idx is None:
        ok = False
        checks["guard_dominates_call"] = False
    else:
        checks["guard_line"] = caller.body[guard_idx].lineno
        checks["call_line"] = caller.body[call_idx].lineno
        dominates = guard_idx < call_idx
        between = caller.body[guard_idx + 1 : call_idx]
        rebound = [s.lineno for s in between if rebinds(s, GUARDED_VAR)]
        checks["guard_dominates_call"] = dominates
        checks["rebinding_lines_between"] = rebound
        checks["no_rebinding_between"] = not rebound
        ok = ok and dominates and not rebound

    checks["VERDICT_nx_branch_statically_unreachable"] = ok

    args.out.write_text(json.dumps(checks, indent=2) + "\n")
    print(json.dumps(checks, indent=2))
    return 0 if ok else 1


def is_falsy_guard_block(stmt: ast.stmt, var: str) -> bool:
    """``if not <var>:`` with an arbitrary body (the callee's branch)."""
    if not isinstance(stmt, ast.If):
        return False
    t = stmt.test
    return (
        isinstance(t, ast.UnaryOp)
        and isinstance(t.op, ast.Not)
        and isinstance(t.operand, ast.Name)
        and t.operand.id == var
    )


if __name__ == "__main__":
    sys.exit(main())
