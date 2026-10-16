#!/usr/bin/env python3
"""Copper-temperature basis gate (OPEN-ITEMS S17: a new class of model gap).

    python3 -I native-21/layout/gates/cu_temp_basis.py [--root UNIT] [--registry cu_temp_registry.json]
                                                       [--report OUT.json] [--list] [--fail-waived] [--today YYYY-MM-DD]

Why: the task-04 A4 loss fields are solved at 20 C copper (sheet_solver.Net default temp_c=20) and B3 scaled them by I^2
only, while the tank copper runs at 83-112 C at the release case (x1.25-1.36 loss). Nothing forced a script that builds
the sheet solver, or computes copper resistance / I^2 R, to say what copper temperature it means. This gate does.

What it finds (static, stdlib `ast`, a few seconds, no board data read). In every .py file matched by registry
`scan.include` (minus `scan.exclude`):

  net      a call to `Net(...)` / `<mod>.Net(...)` in a file that loads sheet_solver (the kit solver; default temp_c = 20)
  rho      a copper-resistivity constant (1.68e-8, 1.72e-8, 1.724e-8, 1.7241e-8, 0.01724) or a name RHO* / ALPHA_CU*
  a4field  a reader of the task-04 A4 loss fields (the string 'heat.npz' or '_joule_w', or an import of a module in
           scan.a4_modules that reads them): inherits their 20 C basis
  ipc      the IPC-2221 external-trace rise formula (constants 0.048 and 0.725 in one file): copper temperature implicit
  derived  (registry-only kind) a file that consumes a registered producer's output and holds no copper constant of its
           own, e.g. kelvin_budget.py reading plane-TAG.json; its `pin` regex must match the file

A finding is EXPLICIT (needs no registry entry) only when the code itself carries a temperature above 25 C:
  net      the call passes temp_c=<expr> and the expr is not a literal <= 25
  rho      every statement that uses a resistivity constant also uses 0.00393 or an ALPHA name (a TCR scaling)
  a4field  never explicit (the fields are 20 C by construction until B3 iterates a hot-copper correction)
Anything else must have a registry entry (cu_temp_registry.json, keyed by file) giving the consumer, the basis
temperature, the direction ("hot is conservative" / "cold is conservative" / "both corners") and the justification.

Fails (exit 1) on:
  1. an unregistered, non-explicit finding;
  2. a registered file with no remaining finding, or a registered file that is gone (stale entry);
  3. direction "hot is conservative" with basis below hot_floor_c (default 100), or "cold is conservative" with basis
     above cold_ceil_c (default 25), unless the entry carries an unexpired waiver {id, reason, expires};
  4. direction "both corners" whose `markers` (>= 2 regexes) are not all found in the file;
  5. a `pin` regex (ties the declared basis to the code, e.g. 'TEMP = 125') that no longer matches the file;
  6. a registry kind that is not found in the file, or an expired waiver.
--fail-waived also fails while any waiver is open (use once the S17 hot-copper iteration lands).
Limits: README.md in the audit folder (static, syntactic; cannot see a temperature passed through a function argument,
a JSON file, or a shell-composed command line; the registry text is a human claim that `pin` and `markers` only anchor).
"""
import argparse
import ast
import datetime
import fnmatch
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNIT = HERE.parents[2]                                    # zapote/power-stage-120v
DIRECTIONS = ("hot is conservative", "cold is conservative", "both corners", "not a claim (self-test)")
RHO_VALUES = (1.68e-8, 1.72e-8, 1.724e-8, 1.7241e-8, 0.01724)
ALPHA_VALUE = 0.00393
RHO_NAME = re.compile(r"^(RHO_?CU\d*|RHO\d*|ALPHA_CU\w*)$", re.I)
ALPHA_NAME = re.compile(r"^ALPHA_CU", re.I)
KINDS = ("net", "rho", "a4field", "ipc", "derived")
A4_MODULES = ("thermal", "thermal_body", "body_runs", "a4_fields", "a4_cases", "thermal_snap", "thermal_lead")


def _isnum(node, vals, tol=1e-12):
    return isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and any(
        abs(node.value - v) <= tol * max(1.0, abs(v)) for v in vals)


def _names(node):
    return {n.id for n in ast.walk(node) if isinstance(n, ast.Name)} | {n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)}


def _has_alpha(node):
    return any(_isnum(n, (ALPHA_VALUE,)) for n in ast.walk(node)) or any(ALPHA_NAME.match(x) for x in _names(node))


def _stmt_parents(tree):
    """Map every node to the nearest enclosing simple statement (Assign / Expr / Return / AugAssign / ...)."""
    parent = {}
    def visit(node, stmt):
        for ch in ast.iter_child_nodes(node):
            s = ch if isinstance(ch, ast.stmt) and not isinstance(ch, (ast.FunctionDef, ast.ClassDef, ast.For, ast.While, ast.If, ast.With, ast.Try)) else stmt
            parent[ch] = s
            visit(ch, s)
    visit(tree, tree)
    return parent


def scan_source(text, a4_modules=A4_MODULES):
    """Findings for one source text: {kind: {"lines": [...], "explicit": bool, "detail": str}}."""
    try:
        tree = ast.parse(text)
    except SyntaxError as e:
        return {"_syntax_error": {"lines": [e.lineno or 0], "explicit": False, "detail": str(e)}}
    out = {}
    uses_kit = "sheet_solver" in text or "kit_solver" in text
    parent = _stmt_parents(tree)
    # net
    if uses_kit:
        lines, unexplicit = [], []
        for n in ast.walk(tree):
            if isinstance(n, ast.Call):
                f = n.func
                if (isinstance(f, ast.Name) and f.id == "Net") or (isinstance(f, ast.Attribute) and f.attr == "Net"):
                    lines.append(n.lineno)
                    kw = {k.arg: k.value for k in n.keywords}
                    t = kw.get("temp_c")
                    if t is None:
                        unexplicit.append(n.lineno)
                    elif isinstance(t, ast.Constant) and isinstance(t.value, (int, float)) and t.value <= 25:
                        unexplicit.append(n.lineno)
        if lines:
            out["net"] = {"lines": sorted(lines), "explicit": not unexplicit,
                          "detail": "Net() without temp_c (default 20 C) or with temp_c <= 25 at line(s) %s" % unexplicit if unexplicit
                          else "every Net() passes temp_c"}
    # rho
    rlines, bad = [], []
    for n in ast.walk(tree):
        hit = _isnum(n, RHO_VALUES) or (isinstance(n, ast.Name) and RHO_NAME.match(n.id) and not ALPHA_NAME.match(n.id) and isinstance(n.ctx, ast.Load))
        if isinstance(n, ast.Name) and RHO_NAME.match(n.id) and not ALPHA_NAME.match(n.id) and isinstance(n.ctx, ast.Store):
            hit = True
        if hit:
            rlines.append(n.lineno)
            st = parent.get(n)
            if st is None or not _has_alpha(st):
                bad.append(n.lineno)
    if rlines:
        out["rho"] = {"lines": sorted(set(rlines)), "explicit": not bad,
                      "detail": "resistivity statement(s) without a TCR term at line(s) %s" % sorted(set(bad)) if bad
                      else "every resistivity statement carries 0.00393 / ALPHA"}
    # a4field
    alines = [n.lineno for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
              and ("heat.npz" in n.value or "_joule_w" in n.value)]
    for n in ast.walk(tree):         # an import of a module that reads the A4 fields inherits their basis
        mods = [a.name.split(".")[0] for a in n.names] if isinstance(n, ast.Import) else \
               [n.module.split(".")[0]] if isinstance(n, ast.ImportFrom) and n.module else []
        alines += [n.lineno for m in mods if m in a4_modules]
    if alines:
        out["a4field"] = {"lines": sorted(set(alines)), "explicit": False,
                          "detail": "reads, or imports a module that reads, the task-04 A4 loss fields (solved at 20 C copper)"}
    # ipc: the IPC-2221 external-layer rise formula (k = 0.048, exponents 0.44 / 0.725). Its copper temperature is implicit
    # (ambient ~25 C + the rise), so it can never be explicit
    if any(_isnum(n, (0.048,)) for n in ast.walk(tree)) and any(_isnum(n, (0.725,)) for n in ast.walk(tree)):
        out["ipc"] = {"lines": sorted(n.lineno for n in ast.walk(tree) if _isnum(n, (0.048,))), "explicit": False,
                      "detail": "IPC-2221 trace-rise formula (copper temperature implicit in the fit)"}
    return out


def collect(root, scan):
    files = set()
    for pat in scan["include"]:
        for p in root.glob(pat):
            if p.is_file() and p.suffix == ".py":
                files.add(p)
    ex = scan.get("exclude", [])
    keep = []
    for p in sorted(files):
        rel = p.relative_to(root).as_posix()
        if "__pycache__" in rel or any(fnmatch.fnmatch(rel, e) for e in ex):
            continue
        keep.append((rel, p))
    return keep


def check(root, registry, today=None, fail_waived=False):
    root = Path(root)
    today = today or datetime.date.today().isoformat()
    d = registry.get("defaults", {})
    hot_floor, cold_ceil = d.get("hot_floor_c", 100.0), d.get("cold_ceil_c", 25.0)
    errors, warnings, rows = [], [], []
    by_file = {}
    for e0 in registry.get("consumers", []):
        files = e0.get("files") or ([e0["file"]] if e0.get("file") else [])
        if not files:
            errors.append(f"{e0.get('id', '?')}: registry entry has neither 'file' nor 'files'")
        for k in ("id", "consumer", "kinds", "direction", "justification"):
            if not e0.get(k):
                errors.append(f"{e0.get('id', files[:1])}: registry entry lacks '{k}'")
        if e0.get("direction") not in DIRECTIONS:
            errors.append(f"{e0.get('id')}: direction {e0.get('direction')!r} is not one of {DIRECTIONS}")
        for f in files:
            for rel in (sorted(x.relative_to(root).as_posix() for x in root.glob(f)) or [f]) if any(c in f for c in "*?[") else [f]:
                if rel in by_file:
                    errors.append(f"{rel}: covered by two registry entries ({by_file[rel]['id']}, {e0['id']})")
                by_file[rel] = {**e0, "file": rel}
    seen = set()
    for rel, p in collect(root, registry["scan"]):
        text = p.read_text(errors="replace")
        found = scan_source(text, tuple(registry["scan"].get("a4_modules", A4_MODULES)))
        if "_syntax_error" in found:
            errors.append(f"{rel}: cannot parse ({found['_syntax_error']['detail']})")
            continue
        e = by_file.get(rel)
        for kind, f in found.items():
            if e is None and f["explicit"]:
                rows.append({"file": rel, "kind": kind, "status": "explicit", "lines": f["lines"]})
            elif e is None:
                errors.append(f"{rel}:{f['lines'][0]}: UNREGISTERED copper-temperature consumer [{kind}] - {f['detail']}. "
                              f"Pass temp_c=<hot value> / carry a TCR term, or add an entry to cu_temp_registry.json")
        if e is None:
            continue
        seen.add(rel)
        kinds_found = set(found)
        for k in e["kinds"]:
            if k not in KINDS:
                errors.append(f"{rel}: unknown kind {k!r}")
        real = [k for k in e["kinds"] if k != "derived"]
        if real and not (set(real) & kinds_found):
            errors.append(f"{rel}: none of the registered kinds {real} is found in the file any more (stale entry, or the code changed)")
        for k in kinds_found - set(e["kinds"]):
            if not found[k]["explicit"]:
                errors.append(f"{rel}:{found[k]['lines'][0]}: new non-explicit finding [{k}] not covered by the entry's kinds {e['kinds']}")
        status = "registered"
        b, dr = e.get("basis_temp_c"), e.get("direction")
        w = e.get("waiver")
        wok = False
        if w:
            if not all(w.get(k) for k in ("id", "reason", "expires")):
                errors.append(f"{rel}: waiver needs id, reason and expires")
            elif w["expires"] < today:
                errors.append(f"{rel}: waiver {w['id']} expired {w['expires']}")
            else:
                wok = True
                if fail_waived:
                    errors.append(f"{rel}: waiver {w['id']} still open (--fail-waived)")
        if dr == "hot is conservative":
            floor = e.get("hot_floor_c", hot_floor)
            if not isinstance(b, (int, float)):
                errors.append(f"{rel}: 'hot is conservative' needs a numeric basis_temp_c")
            elif b < floor and not wok:
                errors.append(f"{rel}: basis {b} C is on the NON-conservative side for 'hot is conservative' (needs >= {floor} C). "
                              f"Raise the basis or carry a waiver {{id, reason, expires}}")
            elif b < floor:
                status = "waived"; warnings.append(f"{rel}: basis {b} C < {floor} C, waiver {w['id']} until {w['expires']}")
        elif dr == "cold is conservative":
            ceil = e.get("cold_ceil_c", cold_ceil)
            if not isinstance(b, (int, float)):
                errors.append(f"{rel}: 'cold is conservative' needs a numeric basis_temp_c")
            elif b > ceil and not wok:
                errors.append(f"{rel}: basis {b} C is on the NON-conservative side for 'cold is conservative' (needs <= {ceil} C)")
            elif b > ceil:
                status = "waived"; warnings.append(f"{rel}: basis {b} C > {ceil} C, waiver {w['id']} until {w['expires']}")
        elif dr == "both corners":
            mk = e.get("markers") or []
            if len(mk) < 2:
                errors.append(f"{rel}: 'both corners' needs >= 2 `markers` (regexes for the hot and the cold evaluation)")
            for m in mk:
                if not re.search(m, text):
                    errors.append(f"{rel}: 'both corners' marker {m!r} not found - the file no longer evaluates both corners")
        pin = e.get("pin")
        if pin and not re.search(pin, text):
            errors.append(f"{rel}: pin {pin!r} no longer matches - the declared basis ({b} C) may have drifted from the code")
        rows.append({"file": rel, "id": e["id"], "kinds": sorted(kinds_found), "status": status, "direction": dr, "basis_temp_c": b})
    for rel, e in by_file.items():
        if rel not in seen and set(e["kinds"]) == {"derived"} and (root / rel).exists():
            text = (root / rel).read_text(errors="replace")
            if not e.get("pin"):
                errors.append(f"{rel}: a 'derived' entry needs a `pin` regex")
            elif not re.search(e["pin"], text):
                errors.append(f"{rel}: pin {e['pin']!r} no longer matches the derived consumer")
            rows.append({"file": rel, "id": e["id"], "kinds": ["derived"], "status": "registered", "direction": e["direction"],
                         "basis_temp_c": e.get("basis_temp_c")})
            b, dr = e.get("basis_temp_c"), e["direction"]
            if dr == "hot is conservative" and isinstance(b, (int, float)) and b < e.get("hot_floor_c", hot_floor) and not e.get("waiver"):
                errors.append(f"{rel}: basis {b} C below the hot floor and no waiver")
            continue
        if rel not in seen:
            if not (root / rel).exists():
                errors.append(f"{rel}: registered but the file is gone")
            elif not any(rel == r for r, _ in collect(root, registry["scan"])):
                errors.append(f"{rel}: registered but outside scan.include (or excluded)")
            else:
                errors.append(f"{rel}: registered but no copper-temperature finding remains (stale entry)")
    return {"errors": errors, "warnings": warnings, "rows": rows, "n_files_scanned": len(collect(root, registry["scan"])),
            "n_registered": len(by_file), "today": today}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--root", default=str(UNIT))
    ap.add_argument("--registry", default=str(HERE / "cu_temp_registry.json"))
    ap.add_argument("--report")
    ap.add_argument("--list", action="store_true", help="print every finding, registered or not")
    ap.add_argument("--fail-waived", action="store_true")
    ap.add_argument("--today")
    a = ap.parse_args(argv)
    reg = json.loads(Path(a.registry).read_text())
    res = check(a.root, reg, a.today, a.fail_waived)
    if a.report:
        Path(a.report).write_text(json.dumps(res, indent=1) + "\n")
    if a.list:
        for r in res["rows"]:
            print(f"  {r['status']:10s} {r['file']}  {r.get('kinds', r.get('kind'))}  {r.get('direction', '')} {r.get('basis_temp_c', '')}")
    groups = {}
    for w in res["warnings"]:
        m = re.search(r"waiver (\S+?) until (\S+)", w)
        groups.setdefault(m.groups() if m else ("?", "?"), []).append(w.split(":")[0])
    for (wid, until), fs in sorted(groups.items()):
        print(f"WARN waiver {wid} (expires {until}) covers {len(fs)} file(s): " + ", ".join(Path(f).name for f in fs[:4]) + (" ..." if len(fs) > 4 else ""))
    for e in res["errors"]:
        print("FAIL", e)
    print(f"cu_temp_basis: {res['n_files_scanned']} files scanned, {res['n_registered']} registered, "
          f"{len(res['warnings'])} waived, {len(res['errors'])} failures -> {'FAIL' if res['errors'] else 'PASS'}")
    return 1 if res["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
