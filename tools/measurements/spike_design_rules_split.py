"""S5 Part 2 measurement: does `ClearanceMatrix` carve out of
`router_v6/constraints_design_rules.py` cleanly, leaving the kiutils/KiCad
parser at the boundary?

The module mixes three things: a duck-typed KiCad parser (`DesignRulesParser`,
`infer_zones`), a GEOS-backed spatial index (`ZoneManager`, `RoutingZone`), and
a pure lookup table (`ClearanceMatrix`).  A carve-out is only real if the table
half touches no third-party primitive of its own and nothing outside it depends
on the seam moving.

This script reports, per top-level definition:

  * statement count (``ast.stmt`` nodes -- the convention the 2026-08-04
    router_v6 migration survey used, reproduced here so the numbers compare),
  * which third-party packages the definition's own body reaches, counting
    module-level imports actually referenced *and* function-local imports,
  * intra-module references between definitions (the carve-out seam),
  * whether the definition is reachable from anywhere outside the module.

Usage:
    python tools/measurements/spike_design_rules_split.py [MODULE.py ...]

Writes a JSON summary to stdout.  Read-only; touches no production code.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
DEFAULT_MODULES = [
    REPO / "packages/temper-placer/src/temper_placer/router_v6/constraints_design_rules.py",
]
THIRD_PARTY = ("kiutils", "shapely", "numpy", "scipy", "networkx")
SEARCH_ROOTS = ["packages", "scripts", "benchmarks", "tools"]


def _stmt_count(node: ast.AST) -> int:
    return sum(1 for n in ast.walk(node) if isinstance(n, ast.stmt))


def _module_import_bindings(tree: ast.Module) -> dict[str, str]:
    """Map module-level bound name -> originating top-level package.

    TYPE_CHECKING-guarded imports are included but tagged by the caller: with
    `from __future__ import annotations` in force they never execute, so they
    are a typing-only reference to the package, not a runtime dependency.
    """
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out[(a.asname or a.name).split(".")[0]] = a.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module:
            for a in node.names:
                out[a.asname or a.name] = node.module.split(".")[0]
    return out


def _type_checking_names(tree: ast.Module) -> set[str]:
    """Names bound only inside an `if TYPE_CHECKING:` block."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.If):
            continue
        test = node.test
        guarded = (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
            isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
        )
        if not guarded:
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.ImportFrom | ast.Import):
                for a in sub.names:
                    names.add(a.asname or a.name)
    return names


def _local_imports(node: ast.AST) -> set[str]:
    """Top-level packages imported *inside* a definition body (runtime)."""
    out: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Import):
            out |= {a.name.split(".")[0] for a in sub.names}
        elif isinstance(sub, ast.ImportFrom) and sub.module:
            out.add(sub.module.split(".")[0])
    return out


def _referenced_names(node: ast.AST) -> set[str]:
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)} | {
        n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)
    }


def _annotation_names(node: ast.AST) -> set[str]:
    """Names appearing in annotations only (string or not)."""
    out: set[str] = set()
    for sub in ast.walk(node):
        ann = getattr(sub, "annotation", None) or getattr(sub, "returns", None)
        if ann is not None:
            out |= _referenced_names(ann)
    return out


def _external_refs(name: str, module_path: Path) -> list[str]:
    """Files outside `module_path` that mention `name` (ripgrep-free)."""
    cmd = ["grep", "-rln", "--include=*.py", "-e", name, *SEARCH_ROOTS]
    proc = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, check=False)
    rel = str(module_path.relative_to(REPO))
    return sorted(p for p in proc.stdout.split() if p and p != rel)


def analyse(module_path: Path) -> dict[str, Any]:
    tree = ast.parse(module_path.read_text())
    bindings = _module_import_bindings(tree)
    tc_names = _type_checking_names(tree)
    top_level = [
        n for n in tree.body if isinstance(n, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
    ]
    top_names = {n.name for n in top_level}

    defs: list[dict[str, Any]] = []
    for node in top_level:
        refs = _referenced_names(node)
        ann_only = _annotation_names(node)
        runtime_refs = refs - ann_only

        third_party: dict[str, str] = {}
        for pkg in _local_imports(node):
            if pkg in THIRD_PARTY:
                third_party[pkg] = "runtime (function-local import)"
        for bound, pkg in bindings.items():
            if pkg not in THIRD_PARTY or bound not in refs:
                continue
            if bound in tc_names:
                third_party.setdefault(pkg, "typing-only (TYPE_CHECKING)")
            elif bound in runtime_refs:
                third_party[pkg] = "runtime (module-level import)"
            else:
                third_party.setdefault(pkg, "typing-only (annotation)")

        defs.append(
            {
                "name": node.name,
                "kind": type(node).__name__,
                "lineno": node.lineno,
                "end_lineno": node.end_lineno,
                "stmts": _stmt_count(node),
                "third_party": third_party,
                "intra_module_refs": sorted((refs & top_names) - {node.name}),
                "external_consumer_files": _external_refs(node.name, module_path),
            }
        )

    return {
        "module": str(module_path.relative_to(REPO)),
        "module_stmts": _stmt_count(tree),
        "module_level_third_party_imports": sorted(
            {p for p in bindings.values() if p in THIRD_PARTY}
        ),
        "type_checking_only_names": sorted(tc_names),
        "definitions": defs,
    }


def kiutils_branch_probe() -> dict[str, Any]:
    """Is the kiutils branch of `ClearanceMatrix.parse` reachable at all?

    `ClearanceMatrix.parse` dispatches on `hasattr(board, "netClasses")` and
    `DesignRulesParser.parse` gates its net-class loop the same way.  The repo
    already records (``io/_parse_nets.py``) that kiutils 1.4.8 exposes no
    ``board.netClasses``; this re-measures it against the installed version so
    the Part 2 verdict does not rest on a comment.
    """
    from importlib.metadata import version

    from kiutils.board import Board

    board = Board()
    return {
        "kiutils_version": version("kiutils"),
        "Board_has_netClasses": hasattr(board, "netClasses"),
        "Board_attributes": sorted(vars(board)),
    }


def zone_manager_probe(board_path: Path) -> dict[str, Any]:
    """How much of `ClearanceMatrix`'s GEOS-backed spatial path is live?

    `ClearanceMatrix` holds no third-party import of its own, but its optional
    `zone_manager` field is a shapely STRtree and `get_clearance(a, b, x, y)`
    delegates to it -- and `DRCOracle` calls the four-argument form.  This
    probe builds the matrix from the real board and measures whether the
    spatial branch ever changes the answer.
    """
    from temper_placer.io.kicad_parser import parse_kicad_pcb
    from temper_placer.router_v6.constraints_design_rules import ClearanceMatrix

    parsed = parse_kicad_pcb(str(board_path))
    board = parsed.board
    matrix = ClearanceMatrix.parse(board)
    zm = matrix.zone_manager
    net_names = sorted({n.name for n in getattr(parsed.netlist, "nets", [])})
    net_names = net_names or sorted(matrix._net_to_class)

    import random

    rng = random.Random(20260804)
    xs = [p[0] for z in getattr(board, "zones", []) for p in (z.polygon or [])]
    ys = [p[1] for z in getattr(board, "zones", []) for p in (z.polygon or [])]
    x0, x1 = (min(xs), max(xs)) if xs else (0.0, 1.0)
    y0, y1 = (min(ys), max(ys)) if ys else (0.0, 1.0)

    differing = 0
    samples = 4000
    for _ in range(samples):
        a, b = rng.choice(net_names), rng.choice(net_names)
        x, y = rng.uniform(x0, x1), rng.uniform(y0, y1)
        if matrix.get_clearance(a, b, x, y) != matrix.get_clearance(a, b):
            differing += 1

    return {
        "board_zones": len(getattr(board, "zones", [])),
        "zone_manager_built": zm is not None,
        "routing_zones": len(zm.zones) if zm else 0,
        "zone_names_sample": [z.name for z in zm.zones[:5]] if zm else [],
        "any_zone_named_HV": bool(zm and any(z.name == "HV" for z in zm.zones)),
        "net_names_used": len(net_names),
        "samples": samples,
        "spatial_vs_nonspatial_differing": differing,
    }


def main() -> int:
    paths = [Path(a).resolve() for a in sys.argv[1:]] or DEFAULT_MODULES
    out = {
        "modules": [analyse(p) for p in paths],
        "kiutils_branch_probe": kiutils_branch_probe(),
        "zone_manager_probe": zone_manager_probe(REPO / "pcb/temper.kicad_pcb"),
    }
    json.dump(out, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
