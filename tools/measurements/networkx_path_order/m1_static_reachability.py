#!/usr/bin/env python3
"""M1 -- regression guard: ``networkx`` must stay absent from
``router_v6/channel_mapping.py``.

History.  Spike S3 (2026-08-04) originally proved a dominance argument:
both ``nx.shortest_path`` calls lived inside ``_extract_waypoints``'s
``if not channel_sequence:`` branch, that function had exactly one call
site, and that call site was preceded by ``if not channel_sequence:
return None`` with no rebinding in between -- so the branch was
statically unreachable.  The spike's recommendation 2 was to delete the
dead branch as a behaviour-preserving change (docs/evidence/
2026-08-04-networkx-path-order-spike.md, SS8).

That deletion landed on 2026-08-10.  The invariant therefore flips from
"the ``nx.shortest_path`` branch is unreachable" to "there is no
``networkx`` in the module at all": no import, no ``nx.`` attribute
call, no ``nx`` name reference.  Reintroducing any of them -- a port
that resurrects the tie-sensitive path-selection code, which the spike
measured as not a stable target even within Python -- makes this guard
exit non-zero and fail loudly instead of silently re-opening the hazard
(SS4, H2).

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

    # --- 1. is there any networkx reference left in the module? -----
    src = Path(TARGET).read_text(encoding="utf-8")
    tree = ast.parse(src)
    nx_imports = [
        n.lineno
        for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom)
        and n.module == "networkx"
        or isinstance(n, ast.Import)
        and any(a.name == "networkx" for a in n.names)
    ]
    nx_name_refs = [
        n.lineno
        for n in ast.walk(tree)
        if isinstance(n, ast.Name) and n.id == "nx"
        or isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "nx"
    ]
    nx_attr_calls = [
        n.lineno
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and isinstance(n.func.value, ast.Name)
        and n.func.value.id == "nx"
    ]
    checks["networkx_import_lines"] = nx_imports
    checks["nx_name_reference_lines"] = nx_name_refs
    checks["nx_attribute_call_lines"] = nx_attr_calls
    checks["module_has_no_networkx"] = not (nx_imports or nx_name_refs or nx_attr_calls)
    ok = ok and checks["module_has_no_networkx"]

    # --- 2. the dominance argument must still hold for the callers ----
    # The guard chain that made the old nx branch unreachable is
    # orthogonal to networkx's absence; it is what guarantees an empty
    # ``channel_sequence`` never reaches ``_extract_waypoints`` at all.
    # A future edit that re-introduces a caller without the guard would
    # silently re-open the reachability question, so keep checking it.
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

    checks["VERDICT_module_has_no_networkx"] = ok

    args.out.write_text(json.dumps(checks, indent=2) + "\n")
    print(json.dumps(checks, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
