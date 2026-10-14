#!/usr/bin/env python3
"""Datasheet ratings ledger gate for native-21 (stdlib only; run as `python3 -I gate.py`).

Reads native-21/frozen/default.csv and ledger.json and fails (exit 1) when
  * a BOM MPN has no ledger entry, or the designators drifted from the BOM,
  * any ledger entry is malformed or internally inconsistent,
  * any entry is VIOLATION,
  * a SAFETY or POWER class line is UNAUDITED.
--strict additionally fails on every non-VERIFIED entry.
Writes ledger-report.json next to the ledger (or --report).
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNIT_ROOT = HERE.parents[2]  # .../power-stage-120v
STATUSES = ("VERIFIED", "PARTIAL", "UNAUDITED", "VIOLATION")
CLASSES = ("SAFETY", "POWER", "SIGNAL")
SEVERITIES = ("violation", "gap")
PATH_RE = re.compile(
    r"(?<![\w/.\-])([A-Za-z0-9_./+\-]+\.(?:md|py|json|ato|csv|txt|pdf|yaml|sh|rs))"
    r"(?::(\d+)(?:[\-–](\d+))?)?"
)


def load_bom(path):
    lines = {}
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            mpn = row["LCSC"].strip()
            des = {d.strip() for d in row["Designator"].split(",") if d.strip()}
            lines.setdefault(mpn, set()).update(des)
    return lines


def check_refs(text, root, where, errors, cache):
    """Every path[:line] token in `text` must exist under the unit root."""
    for m in PATH_RE.finditer(text or ""):
        rel, a, b = m.group(1), m.group(2), m.group(3)
        p = root / rel
        if not p.is_file():
            errors.append(f"{where}: evidence path not found: {rel}")
            continue
        if a:
            if p not in cache:
                try:
                    cache[p] = sum(1 for _ in open(p, "rb"))
                except OSError:
                    cache[p] = 0
            last = int(b) if b else int(a)
            if last > cache[p]:
                errors.append(f"{where}: {rel}:{last} beyond end of file ({cache[p]} lines)")


def compute_checks(entry, errors, where):
    """Recompute stress/limit for each check; compare with the stored margin."""
    ratings = {r.get("parameter"): r for r in entry.get("ratings", [])}
    stresses = {s.get("parameter"): s for s in entry.get("stresses", [])}
    out = []
    for chk in entry.get("checks", []):
        cid = chk.get("id", "?")
        w = f"{where} check {cid}"
        r, s = ratings.get(chk.get("rating")), stresses.get(chk.get("stress"))
        if r is None or s is None:
            errors.append(f"{w}: rating/stress parameter not found ({chk.get('rating')!r}, {chk.get('stress')!r})")
            continue
        lim, val = r.get("datasheet_limit"), s.get("worst_case_value")
        if not isinstance(lim, (int, float)) or not isinstance(val, (int, float)) or lim <= 0:
            errors.append(f"{w}: limit and stress must be numeric, limit > 0")
            continue
        if r.get("unit") != s.get("unit"):
            errors.append(f"{w}: unit mismatch {r.get('unit')!r} vs {s.get('unit')!r}")
            continue
        sev = chk.get("severity")
        if sev not in SEVERITIES or not isinstance(chk.get("max_ratio"), (int, float)):
            errors.append(f"{w}: needs severity in {SEVERITIES} and numeric max_ratio")
            continue
        ratio = val / lim
        ok = ratio <= chk["max_ratio"] + 1e-9
        stored = chk.get("ratio")
        if not isinstance(stored, (int, float)) or abs(stored - ratio) > 1e-3 * max(1.0, ratio):
            errors.append(f"{w}: stored ratio {stored!r} != recomputed {ratio:.4f}")
        out.append({"id": cid, "rating": chk["rating"], "stress": chk["stress"], "ratio": round(ratio, 4),
                    "max_ratio": chk["max_ratio"], "severity": sev, "ok": ok})
    return out


def validate_entry(mpn, e, bom_des, root, cache):
    errors, warnings = [], []
    w = f"[{mpn}]"
    for k in ("mpn", "designators", "function", "class", "status", "datasheet", "ratings", "stresses",
              "derating_rule", "checks", "layout_guidance", "gaps"):
        if k not in e:
            errors.append(f"{w} missing field {k}")
    if errors:
        return errors, warnings, []
    if e["mpn"] != mpn:
        errors.append(f"{w} key != mpn field {e['mpn']!r}")
    if set(e["designators"]) != bom_des:
        errors.append(f"{w} designators differ from BOM: ledger-only {sorted(set(e['designators']) - bom_des)}, "
                      f"BOM-only {sorted(bom_des - set(e['designators']))}")
    if e["status"] not in STATUSES:
        errors.append(f"{w} bad status {e['status']!r}")
        return errors, warnings, []
    if e["class"] not in CLASSES:
        errors.append(f"{w} bad class {e['class']!r}")
    for i, lg in enumerate(e["layout_guidance"]):
        if not lg.get("item") or not lg.get("enforced_by"):
            errors.append(f"{w} layout_guidance[{i}] needs item and enforced_by (use 'UNCHECKED')")
        elif not lg["enforced_by"].startswith("UNCHECKED"):
            check_refs(lg["enforced_by"], root, f"{w} layout_guidance[{i}]", errors, cache)
    ds = e["datasheet"]
    if ds:
        if ds.get("repo_copy"):
            check_refs(ds["repo_copy"], root, f"{w} datasheet.repo_copy", errors, cache)
            if not (root / ds["repo_copy"].split(":")[0]).is_file():
                pass  # already reported
    for s in e["stresses"]:
        check_refs(s.get("evidence", ""), root, f"{w} stress {s.get('parameter')}", errors, cache)
    checks = compute_checks(e, errors, w)
    failed_v = [c for c in checks if not c["ok"] and c["severity"] == "violation"]
    failed_g = [c for c in checks if not c["ok"] and c["severity"] == "gap"]
    st = e["status"]
    if failed_v and st != "VIOLATION":
        errors.append(f"{w} status {st} but violation-severity check(s) fail: {[c['id'] for c in failed_v]}")
    if failed_g and st not in ("PARTIAL", "VIOLATION"):
        errors.append(f"{w} status {st} but gap-severity check(s) fail: {[c['id'] for c in failed_g]}")
    if st == "VERIFIED":
        if not (ds and (ds.get("url") or ds.get("repo_copy"))):
            errors.append(f"{w} VERIFIED needs a datasheet url or repo_copy")
        if not e["ratings"] or not e["stresses"] or not checks:
            errors.append(f"{w} VERIFIED needs ratings, stresses and at least one computed check")
        if e["gaps"]:
            errors.append(f"{w} VERIFIED must have no gaps")
        for r in e["ratings"]:
            if not r.get("source"):
                errors.append(f"{w} rating {r.get('parameter')} has no source page/table")
        for s in e["stresses"]:
            if not s.get("evidence"):
                errors.append(f"{w} stress {s.get('parameter')} has no evidence")
    elif st == "PARTIAL":
        if not e["gaps"]:
            errors.append(f"{w} PARTIAL must state its gaps")
        if not (e["ratings"] or e["stresses"]):
            errors.append(f"{w} PARTIAL has neither ratings nor stresses (that is UNAUDITED)")
    elif st == "VIOLATION":
        if not e.get("finding"):
            errors.append(f"{w} VIOLATION needs a 'finding'")
    return errors, warnings, checks


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ledger", default=str(HERE / "ledger.json"))
    ap.add_argument("--bom", default=str(UNIT_ROOT / "native-21/frozen/default.csv"))
    ap.add_argument("--root", default=str(UNIT_ROOT), help="unit root for evidence paths")
    ap.add_argument("--report", default=None, help="default: ledger-report.json beside the ledger")
    ap.add_argument("--strict", action="store_true", help="fail on any non-VERIFIED entry")
    args = ap.parse_args(argv)

    root = Path(args.root)
    bom = load_bom(args.bom)
    ledger_path = Path(args.ledger)
    data = json.loads(ledger_path.read_text(encoding="utf-8"))
    entries = data.get("entries", {})
    errors, warnings, cache = [], [], {}
    report_entries = {}

    missing = sorted(set(bom) - set(entries))
    extra = sorted(set(entries) - set(bom))
    for m in missing:
        errors.append(f"BOM MPN missing from ledger: {m} ({','.join(sorted(bom[m]))[:80]})")
    for m in extra:
        warnings.append(f"ledger entry not in BOM (stale): {m}")

    for mpn, e in sorted(entries.items()):
        if mpn not in bom:
            continue
        errs, warns, checks = validate_entry(mpn, e, bom[mpn], root, cache)
        errors += errs
        warnings += warns
        report_entries[mpn] = {"designators": sorted(bom[mpn]), "class": e.get("class"), "status": e.get("status"),
                               "function": e.get("function"), "checks": checks,
                               "gaps": e.get("gaps", []), "finding": e.get("finding"),
                               "unchecked_layout": [x["item"] for x in e.get("layout_guidance", [])
                                                    if str(x.get("enforced_by", "")).startswith("UNCHECKED")]}

    violations = [m for m, r in report_entries.items() if r["status"] == "VIOLATION"]
    unaud_power = [m for m, r in report_entries.items()
                   if r["status"] == "UNAUDITED" and r["class"] in ("SAFETY", "POWER")]
    unaud_other = [m for m, r in report_entries.items()
                   if r["status"] == "UNAUDITED" and r["class"] not in ("SAFETY", "POWER")]
    partial = [m for m, r in report_entries.items() if r["status"] == "PARTIAL"]
    non_verified = [m for m, r in report_entries.items() if r["status"] != "VERIFIED"]

    failures = list(errors)
    failures += [f"VIOLATION: {m} ({','.join(report_entries[m]['designators'])[:60]}): "
                 f"{report_entries[m]['finding']}" for m in violations]
    failures += [f"SAFETY/POWER line UNAUDITED: {m} ({','.join(report_entries[m]['designators'])[:60]})"
                 for m in unaud_power]
    if args.strict:
        failures += [f"--strict: {m} is {report_entries[m]['status']}" for m in non_verified
                     if m not in violations and m not in unaud_power]
    if unaud_other:
        warnings.append(f"{len(unaud_other)} SIGNAL-class lines are UNAUDITED (allowed; listed in the report)")

    # summary table
    cls_rows = {c: {s: 0 for s in STATUSES} for c in CLASSES}
    for r in report_entries.values():
        if r["class"] in cls_rows and r["status"] in STATUSES:
            cls_rows[r["class"]][r["status"]] += 1
    totals = {s: sum(cls_rows[c][s] for c in CLASSES) for s in STATUSES}
    print(f"Datasheet ledger: {len(bom)} BOM lines, {len(entries)} ledger entries")
    print(f"{'class':8}" + "".join(f"{s:>11}" for s in STATUSES) + f"{'lines':>8}")
    for c in CLASSES:
        print(f"{c:8}" + "".join(f"{cls_rows[c][s]:>11}" for s in STATUSES) + f"{sum(cls_rows[c].values()):>8}")
    print(f"{'TOTAL':8}" + "".join(f"{totals[s]:>11}" for s in STATUSES) + f"{sum(totals.values()):>8}")
    n_unchecked = sum(len(r["unchecked_layout"]) for r in report_entries.values())
    print(f"layout-guidance items marked UNCHECKED: {n_unchecked}")
    for m in partial:
        r = report_entries[m]
        print(f"PARTIAL {m} ({','.join(r['designators'])[:40]}): {len(r['gaps'])} gap(s): {r['gaps'][0][:110]}")
    for wmsg in warnings:
        print("WARN  " + wmsg)
    for f in failures:
        print("FAIL  " + f)
    print("RESULT: " + ("FAIL" if failures else "PASS") + (" (strict)" if args.strict else ""))

    report = {"bom_lines": len(bom), "entries": len(entries), "strict": args.strict,
              "counts_by_class": cls_rows, "totals": totals,
              "violations": violations, "partial": partial, "unaudited_safety_power": unaud_power,
              "unaudited_other": unaud_other, "missing_from_ledger": missing,
              "unchecked_layout_items": n_unchecked, "errors": errors, "warnings": warnings,
              "failures": failures, "result": "FAIL" if failures else "PASS", "entries_detail": report_entries}
    rep = Path(args.report) if args.report else ledger_path.parent / "ledger-report.json"
    rep.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
