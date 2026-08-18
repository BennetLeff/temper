#!/usr/bin/env python3
"""Discovery sweep for clone-pair CANDIDATES: same-directory Python file
pairs sharing several def names, ranked by normalized-AST structural
similarity (reuses ``clone_drift_registry.normalize_function_ast``/
``similarity`` -- the identical mechanism ``check_clone_drift.py`` gates
with, so a candidate's reported score is directly comparable to a
registered pair's floor).

NOT wired into CI. This is a human-run audit tool, same limitation
``check_duplicate_predicates.py``'s own docstring states for finding a
brand-new duplicate-predicate family: "this is a measurement/audit
exercise ... not a mechanical gate." A full O(n^2) all-pairs comparison
across every non-test Python file in the repo is not something any PR
should have to pay for on every push; registering a genuine finding in
``scripts/clone_drift_registry.py`` (a reviewed, deliberate act) is what
turns a candidate into an enforced regression guard.

WHY DIRECTORY-SCOPED, NOT WHOLE-REPO ALL-PAIRS
------------------------------------------------
Whole-repo all-pairs (~700 non-test files) is a few hundred thousand file
pairs; most share zero def names and cost nothing, but the ones that DO
share names are frequently siblings implementing a common ABC/Protocol
(e.g. this repo's ``placer/heuristics/*.py`` — every file defines
``apply``/``name``/``description``/``priority`` because they all subclass
``Heuristic``) — expected polymorphism, not accidental cloning, and pure
name-overlap ranking drowns in it. Scoping to same-DIRECTORY pairs is a
deliberate, reviewable choice (mirrors ``check_duplicate_predicates.py``'s
own ``scan_paths`` philosophy: "the gate's coverage is a visible,
falsifiable, reviewable decision") that both bounds the cost and,
empirically (2026-08-18 run), still finds the real incident pair
(``_power_islands.py``/``_ground_plane.py``, both under ``router_v6/``)
at a high rank. It will NOT find a clone pair split across two different
directories — a real blind spot, stated plainly rather than assumed away;
widen ``--all-pairs`` if that is ever suspected.

USAGE
    uv run python scripts/find_clone_pairs.py
    uv run python scripts/find_clone_pairs.py --min-jaccard 0.1 --top 60
    uv run python scripts/find_clone_pairs.py --all-pairs   # whole-repo, slow
"""

from __future__ import annotations

import argparse
import ast
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import clone_drift_registry as registry  # noqa: E402
from _lib.repo import find_repo_root  # noqa: E402

EXCLUDE_SUBSTR = (
    "/tests/",
    "_py_oracle",
    "/target/",
    "/target-shared/",
    "/.venv/",
    "/node_modules/",
)

SCAN_ROOTS = ("packages", "scripts", "elec", "firmware")

#: Below this, a candidate's normalized body is too short for the
#: similarity score to mean anything (a one-line property getter matches
#: almost anything else with a `return NAME.ATTR` shape).
MIN_BODY_TOKENS = 25


def _iter_py_files(repo_root: Path):
    for root in SCAN_ROOTS:
        base = repo_root / root
        if not base.exists():
            continue
        for p in base.rglob("*.py"):
            s = str(p)
            if any(x in s for x in EXCLUDE_SUBSTR):
                continue
            yield p


def _all_defs(path: Path) -> dict[str, ast.AST]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return {}
    defs, _ambiguous = registry._all_qualified_defs(tree)
    return defs


def find_candidate_file_pairs(
    repo_root: Path, *, min_jaccard: float, min_shared: int, all_pairs: bool
) -> list[tuple[float, int, Path, Path, set[str]]]:
    files = sorted(_iter_py_files(repo_root))
    by_dir: dict[Path, list[Path]] = defaultdict(list)
    for f in files:
        by_dir[Path(".") if all_pairs else f.parent].append(f)

    defs_cache: dict[Path, dict[str, ast.AST]] = {}

    def get_defs(p: Path) -> dict[str, ast.AST]:
        if p not in defs_cache:
            defs_cache[p] = _all_defs(p)
        return defs_cache[p]

    out: list[tuple[float, int, Path, Path, set[str]]] = []
    for filelist in by_dir.values():
        if len(filelist) < 2:
            continue
        for i in range(len(filelist)):
            for j in range(i + 1, len(filelist)):
                fa, fb = filelist[i], filelist[j]
                defs_a, defs_b = get_defs(fa), get_defs(fb)
                if not defs_a or not defs_b:
                    continue
                names_a = {n.rsplit(".", 1)[-1] for n in defs_a}
                names_b = {n.rsplit(".", 1)[-1] for n in defs_b}
                shared = {
                    n for n in (names_a & names_b) if not n.startswith("__") and len(n) > 2
                }
                if len(shared) < min_shared:
                    continue
                jaccard = len(shared) / len(names_a | names_b)
                if jaccard < min_jaccard:
                    continue
                out.append((jaccard, len(shared), fa, fb, shared))
    return out


def rank_function_pairs(
    repo_root: Path,
    candidates: list[tuple[float, int, Path, Path, set[str]]],
) -> list[tuple[float, int, Path, str, Path, str]]:
    defs_cache: dict[Path, dict[str, ast.AST]] = {}

    def get_defs(p: Path) -> dict[str, ast.AST]:
        if p not in defs_cache:
            defs_cache[p] = _all_defs(p)
        return defs_cache[p]

    ranked: list[tuple[float, int, Path, str, Path, str]] = []
    for _jaccard, _nshared, fa, fb, shared in candidates:
        defs_a, defs_b = get_defs(fa), get_defs(fb)
        for name in shared:
            qa = [q for q in defs_a if q.rsplit(".", 1)[-1] == name]
            qb = [q for q in defs_b if q.rsplit(".", 1)[-1] == name]
            for a in qa:
                for b in qb:
                    ta = registry.normalize_function_ast(defs_a[a])
                    tb = registry.normalize_function_ast(defs_b[b])
                    tok_len = min(len(ta.split()), len(tb.split()))
                    if tok_len < MIN_BODY_TOKENS:
                        continue
                    r = registry.similarity(defs_a[a], defs_b[b])
                    ranked.append((r, tok_len, fa, a, fb, b))
    ranked.sort(key=lambda t: -t[0])
    return ranked


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--min-jaccard", type=float, default=0.15)
    ap.add_argument("--min-shared", type=int, default=3)
    ap.add_argument("--top", type=int, default=40)
    ap.add_argument(
        "--all-pairs",
        action="store_true",
        help="compare every file against every other file (ignore directory "
        "scoping) -- slow, whole-repo O(n^2)",
    )
    args = ap.parse_args()

    repo_root = find_repo_root()
    candidates = find_candidate_file_pairs(
        repo_root,
        min_jaccard=args.min_jaccard,
        min_shared=args.min_shared,
        all_pairs=args.all_pairs,
    )
    print(f"{len(candidates)} candidate file pair(s) "
          f"(shared def-name count >= {args.min_shared}, jaccard >= {args.min_jaccard}).\n")

    ranked = rank_function_pairs(repo_root, candidates)
    print(
        f"Ranked by normalized-AST structural similarity "
        f"(body token len >= {MIN_BODY_TOKENS}), top {args.top}:\n"
    )
    for r, tok_len, fa, a, fb, b in ranked[: args.top]:
        print(
            f"sim={r:.3f} toklen={tok_len:4d}  "
            f"{fa.relative_to(repo_root)}::{a}  <->  {fb.relative_to(repo_root)}::{b}"
        )


if __name__ == "__main__":
    main()
