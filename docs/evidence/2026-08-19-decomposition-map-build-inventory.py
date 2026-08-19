#!/usr/bin/env python3
"""Build the decomposition-map inventory from static candidates + execution evidence.

Evidence classes (the whole point of this file):
  E1-execution-live      -- observed executing a function body in >=1 runtime probe
  E2-execution-absent    -- measured by >=1 probe, zero function-body lines executed
                            in ALL probes, and zero static/dynamic references
  E3-static-only         -- no runtime probe can speak to this unit (e.g. a script
                            no probe invokes). CANDIDATE only, never a finding.
  E4-owned-elsewhere     -- another live agent owns this surface
  E5-protected           -- pinned differential oracle; permanently `keep`
"""

from __future__ import annotations

import ast
import json
import os
import re
import sys
from pathlib import Path

import coverage

ROOT = Path("/home/bennet/Desktop/temper")
S = Path(os.environ.get("DECOMP_WORKDIR", "/tmp/decomp-map"))
EX = {
    ".git",
    ".claude",
    ".worktrees",
    ".venv",
    "__pycache__",
    "target-shared",
    "target",
    "node_modules",
    ".mypy_cache",
}

PROBES = {
    "route": "scripts/route_board.py --pcb pcb/temper.kicad_pcb (real production route)",
    "closure": "scripts/ci_closure_test.py --require-all-stages (full pipeline, the metrics-record.yml CI job)",
    "regression": "temper-placer regression (golden-board suite, the golden-check.yml CI gate)",
    "tests": "pytest packages/temper-placer/tests elec/validation",
    "tests_wf": "pytest packages/temper-workflow/tests",
}

# Surfaces owned by other live agents this session -- read, do not edit.
OWNED = [
    r"router_v6/clearance_floor\.py$",
    r"scripts/check_router_clearance_floor\.py$",
    r"placer/cp_sat/isolation_barrier\.py$",
    r"scripts/check_isolation_keepout\.py$",
    r"scripts/measure_cross_domain_creepage\.py$",
    r"scripts/check_creepage_clearance_drift\.py$",
    r"placer/cp_sat/_encoder_solve\.py$",
    r"placer/cp_sat/_loop_.*\.py$",
    r"placer/cp_sat/loop\.py$",
    r"deterministic/feedback/drc_parser\.py$",
    r"scripts/check_rust_coverage_illusions\.py$",
    r"scripts/.*(report|summar|digest|scorecard).*\.py$",
]


def body_lines(path: Path) -> set[int]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (SyntaxError, OSError):
        return set()
    out: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for st in node.body:
                for n in ast.walk(st):
                    if hasattr(n, "lineno"):
                        out.add(n.lineno)
    return out


def load(name: str) -> dict[str, set[int]] | None:
    f = S / f"cov/.coverage.{name}"
    if not f.exists():
        return None
    cov = coverage.Coverage(data_file=str(f))
    cov.load()
    data = cov.get_data()
    res: dict[str, set[int]] = {}
    for p in data.measured_files():
        try:
            rel = str(Path(p).resolve().relative_to(ROOT))
        except ValueError:
            continue
        res[rel] = set(data.lines(p) or [])
    return res


covs = {k: load(k) for k in PROBES}
available = [k for k, v in covs.items() if v is not None]
print(f"probes available: {available}", file=sys.stderr)

# rust twin index
rs_by_stem: dict[str, list[str]] = {}
for p in ROOT.rglob("*.rs"):
    if EX & set(p.parts):
        continue
    rs_by_stem.setdefault(p.stem, []).append(str(p.relative_to(ROOT)))

# script invocation graph (existing repo machinery, static)
inv = json.load(open(ROOT / "scripts/invocation_graph.json"))

units = json.load(open(S / "static.json"))
rows = []
for path, u in sorted(units.items()):
    p = ROOT / path
    if not p.exists():
        continue
    bl = body_lines(p)
    ex: dict[str, dict] = {}
    for k in PROBES:
        c = covs[k]
        if c is None:
            ex[k] = {"probe_ran": False}
            continue
        lines = c.get(path)
        ex[k] = {
            "probe_ran": True,
            "file_measured": lines is not None,
            "body_lines_executed": len(lines & bl) if lines else 0,
            "total_lines_executed": len(lines) if lines else 0,
        }
    live_in = [k for k in PROBES if ex[k].get("body_lines_executed", 0) > 0]
    imported_in = [
        k for k in PROBES if ex[k].get("total_lines_executed", 0) > 0 and k not in live_in
    ]

    stem = Path(path).stem.lstrip("_")
    twins = rs_by_stem.get(stem, [])
    owned = any(re.search(r, path) for r in OWNED)
    is_oracle = bool(re.match(r"_.*_py_oracle\.py$", p.name))
    refs = (
        u["n_static_importers"] > 0
        or u["rust_imports_module"]
        or bool(u["rust_getattr_names"])
        or bool(u.get("ci_referenced"))
        or bool(u.get("in_manifest"))
    )
    if u["kind"] == "script":
        callers = inv.get(Path(path).name, [])
        refs = refs or bool(callers)
    else:
        callers = []

    # A "production reference" excludes importers that live in a test tree --
    # the convention check_unwired_kernels.py / check_orphaned_python_modules.py
    # already use. NOTE the 2026-08-17 near-miss: files under
    # packages/temper-placer/tests/requirements/validators/ are NOT tests, they
    # are real REQ-EMC validator logic, so they count as production here.
    def _is_test(ip: str) -> bool:
        return "/tests/" in ip and "tests/requirements/validators/" not in ip

    nontest = [ip for ip in u["static_importers"] if not _is_test(ip)]
    prod_refs = (
        bool(nontest)
        or u["rust_imports_module"]
        or bool(u["rust_getattr_names"])
        or bool(u.get("ci_referenced"))
        or bool(u.get("in_manifest"))
        or bool(callers)
    )
    prod_ref_why = (
        "; ".join(
            filter(
                None,
                [
                    f"{len(nontest)} non-test Python importer(s): {', '.join(nontest[:4])}"
                    if nontest
                    else "",
                    "named by a Rust py.import()" if u["rust_imports_module"] else "",
                    ("Rust getattr() names: " + ",".join(u["rust_getattr_names"][:4]))
                    if u["rust_getattr_names"]
                    else "",
                    "named in CI/Makefile" if u.get("ci_referenced") else "",
                ],
            )
        )
        or "none"
    )

    # ---- evidence class + disposition -----------------------------------
    if is_oracle:
        ec, disp = "E5-protected", "keep"
        basis = "pinned differential oracle -- permanently keep, never consolidate"
    elif owned:
        ec, disp = "E4-owned-elsewhere", "owned-elsewhere"
        basis = "surface owned by another live agent this session; read-only here"
    elif live_in:
        ec = "E1-execution-live"
        PROD = ("route", "closure", "regression")
        if any(k in PROD for k in live_in):
            disp = "port-to-rust" if twins else "keep"
            basis = (
                "function bodies executed in production-path probe(s): "
                + ",".join(live_in)
                + ("; same-stem Rust file exists (twin liveness NOT verified)" if twins else "")
            )
        elif not prod_refs:
            # Runs only because a test runs it, and nothing outside the test
            # tree references it on either language surface. Deletable, but the
            # deletion necessarily removes its tests too -- P2, not P1.
            disp = "delete-with-its-tests-candidate"
            basis = (
                "function bodies executed ONLY under the test suite ("
                + ",".join(live_in)
                + "); no production-path probe entered"
                " it; zero non-test Python importers; zero Rust"
                " py.import/getattr references; not named in CI or manifest"
            )
        else:
            disp = "unknown-needs-instrumentation"
            basis = (
                "executes only under the test suite ("
                + ",".join(live_in)
                + "); no production-path probe entered it, but a non-test"
                " reference exists: " + prod_ref_why
            )
    elif u["kind"] == "script":
        ec, disp = "E3-static-only", "unknown-needs-instrumentation"
        basis = (
            "scripts are not invoked by any runtime probe here; liveness is"
            " governed by scripts/manifest.yaml + invocation_graph.json +"
            " check_script_sunset.py, all of which are STATIC."
        )
    elif p.name in ("__init__.py", "__main__.py"):
        # Structural: a package marker's importers attach to its submodules,
        # and `__main__.py` is a `python -m` entry point by definition. Neither
        # is decidable by reference-counting -- never a delete-now candidate.
        ec, disp = "E3-static-only", "unknown-needs-instrumentation"
        basis = (
            "package marker / `python -m` entry point -- structural, not"
            " reference-counted; deadness is not decidable this way"
        )
    elif not refs and not imported_in:
        ec, disp = "E2-execution-absent", "delete-now-candidate"
        basis = (
            "zero function-body lines executed under all "
            f"{len(available)} probes; zero Python importers; zero Rust"
            " py.import/getattr references; not named in CI or manifest"
        )
    else:
        ec, disp = "E3-static-only", "unknown-needs-instrumentation"
        reason = []
        if imported_in:
            reason.append(
                "module body executed (imported) but no function body entered in "
                + ",".join(imported_in)
            )
        if u["n_static_importers"]:
            reason.append(f"{u['n_static_importers']} static Python importer(s)")
        if u["rust_imports_module"]:
            reason.append("named by a Rust py.import()")
        if u["rust_getattr_names"]:
            reason.append(
                "defines symbol(s) a Rust getattr() names: " + ",".join(u["rust_getattr_names"][:4])
            )
        basis = "; ".join(reason) or "no probe reached it, but references exist"

    rows.append(
        {
            "path": path,
            "kind": u["kind"],
            "loc": u["loc"],
            "evidence_class": ec,
            "disposition": disp,
            "disposition_basis": basis,
            "executed_in": live_in,
            "imported_only_in": imported_in,
            "rust_twin_candidates": twins,
            "static": {
                "n_python_importers": u["n_static_importers"],
                "python_importers": u["static_importers"][:12],
                "rust_py_import": u["rust_imports_module"],
                "rust_getattr_symbols": u["rust_getattr_names"],
                "in_scripts_manifest": u.get("in_manifest"),
                "named_in_ci_or_makefile": u.get("ci_referenced"),
                "invocation_graph_callers": callers[:8],
            },
            "execution": ex,
        }
    )

out = {
    "schema_version": 1,
    "generated_from": "scratchpad/decomp-map/build_inventory.py",
    "probes": {k: {"command": v, "ran": covs[k] is not None} for k, v in PROBES.items()},
    "evidence_class_legend": {
        "E1-execution-live": "observed executing a function body in >=1 runtime probe",
        "E2-execution-absent": "measured by the probes, zero function-body lines executed anywhere, zero static/dynamic references",
        "E3-static-only": "CANDIDATE ONLY -- no runtime probe can speak to this unit",
        "E4-owned-elsewhere": "another live agent owns this surface",
        "E5-protected": "pinned differential oracle; permanently keep",
    },
    "units": rows,
}
json.dump(out, open(S / "inventory.json", "w"), indent=1)

import collections

c = collections.Counter()
l = collections.Counter()
for r in rows:
    c[r["disposition"]] += 1
    l[r["disposition"]] += r["loc"]
print(f"{'disposition':32s} {'files':>6s} {'loc':>8s}")
for k in sorted(c):
    print(f"{k:32s} {c[k]:6d} {l[k]:8d}")
e = collections.Counter(r["evidence_class"] for r in rows)
print(dict(e))
