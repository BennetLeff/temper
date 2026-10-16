#!/usr/bin/env python3
"""Controls on depmap.json: does the dependency map cover every card entry, agree with the 13-coupling verification
layer, and claim every file the keyed steps' scripts name?

    python3 -I depmap_check.py [--card validation-results/10-benchmark/scorecard-native21s43.json] [--json OUT]

  C1  every entry of the card has a producer step; every entry a step claims exists on the card (or is listed legacy)
  C2  every metric / gate of 13-coupling verification.json maps to a depmap step; the mapping is printed with the
      differences in read model (global vs scoped, read-set widths)
  C3  explicit read sets (task 04 power nets, F1 necks nets, OCP pickup nets / parts) contain verification.json's
  C4  static scan of the keyed steps' scripts (and chain.sh / regate.sh / incr_iter.sh / scorecard.py): every repo path
      literal they name is classified so that a change to it reaches the step (input of that step, board input, full
      chain, or the step's own output); a literal classed not_read / doc / test is a hole in the map
  C5  firmware: the only firmware file a step names is the one depmap routes to b3_ratings
  C6  imports: every repo module a keyed step's script imports (looked up in the script's folder and the folders the
      thermal scripts put on sys.path) reaches the step, recursively
Exit 1 on any failed control.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import scoped_lib as L  # noqa: E402

U = L.UNIT
R5 = "validation-results/04-board-current-thermal/round5-native21"
SCRIPTS = {
    "task04": [f"{R5}/run_cases.py", f"{R5}/run_board.py", f"{R5}/summarize.py", f"{R5}/compare_native17.py",
               "validation-results/04-board-current-thermal/round3/scripts/kit_topology_native13.py",
               "validation-plan/sim-kit/04-current/sheet_solver.py", "tools/export_power_copper.py"],
    "b3_study": [f"{R5}/b3/run_study.py", f"{R5}/b3/thermal.py", f"{R5}/b3/ceiling_sweep.py", f"{R5}/b3/make_heat_sources.py"],
    "b3_ratings": [f"{R5}/b3-ratings/run_basis.py", f"{R5}/b3-ratings/b3_ratings_gate.py", f"{R5}/b3-ratings/fet_case.py",
                   f"{R5}/a4_fields.py", f"{R5}/b3-convergence/thermal_body.py", f"{R5}/b3-convergence/body_runs.py"],
    "chain": ["native-21/layout/gates/chain.sh", "native-21/layout/gates/regate.sh", "native-21/layout/incr_iter.sh",
              "native-21/layout/gates/scorecard.py"],
}
TOPS = ("validation-results/", "validation-plan/", "native-21/", "tools/", "prototype-closure/", "firmware/", "frozen/", "libraries/")
LIT = re.compile(r"""["'(/ ]((?:\.\./|\./)*(?:[A-Za-z0-9_.\-]+/)+[A-Za-z0-9_.\-{}*]+\.(?:py|json|gz|csv|h|net|sh|yaml|kicad_\w+))""")
# card entries no step produces any more but old cards carry
LEGACY = set()
# literals in code that name a file without reading it (citations / messages), reviewed by hand 2026-10-15
CITATIONS = {
    ("validation-results/04-board-current-thermal/round5-native21/b3-ratings/fet_case.py", "firmware/config.yaml"):
        "inside the asserted thermal_mgmt.h comment text (fet_case asserts the header cites it); not opened",
    ("validation-results/04-board-current-thermal/round5-native21/b3-convergence/thermal_body.py", "../stage17-r5/screen.py"):
        "cite= string of a derating row (the value is hard-coded); not opened",
}
# outputs of the steps upstream of a keyed step: covered by its key (copper_key / heat files / task-04 key)
UPSTREAM = {"build", "core_exports", "heat_sources", "task04"}


def literals(rel: str) -> list[str]:
    """Path literals in the code: '#' comments and the module docstring are dropped first."""
    t = (U / rel).read_text(errors="replace")
    if rel.endswith(".py"):
        t = "\n".join(re.sub(r"(^|\s)#.*$", "", line) for line in t.split("\n"))
        t = re.sub(r'^\s*(?:r|u)?("""|\'\'\')(?:.|\n)*?\1', "", t, count=1)
    elif rel.endswith(".sh"):
        t = "\n".join(re.sub(r"(^|\s)#.*$", "", line) for line in t.split("\n"))
    out = set()
    for m in LIT.finditer(t):
        s = m.group(1)
        if "{" in s or "*" in s or "$" in s:
            continue
        out.add(s)
    return sorted(out)


def resolve(rel_script: str, lit: str) -> str | None:
    if lit.startswith("../") or lit.startswith("./"):
        p = (U / rel_script).parent / lit
        try:
            return str(p.resolve().relative_to(U.resolve()))
        except ValueError:
            r = p.resolve()
            try:
                return "@repo/" + str(r.relative_to(L.REPO.resolve()))
            except ValueError:
                return None
    if lit.startswith("firmware/"):
        return "@repo/" + lit
    if lit.startswith(TOPS):
        return lit
    # a bare name relative to the script's folder (e.g. "inputs/x.json" inside b3/)
    p = (U / rel_script).parent / lit
    if p.exists():
        return str(p.resolve().relative_to(U.resolve()))
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--card", default="validation-results/10-benchmark/scorecard-native21s43.json")
    ap.add_argument("--json")
    a = ap.parse_args()
    res = {"controls": []}

    def control(name, ok, detail):
        res["controls"].append({"control": name, "pass": bool(ok), "detail": detail})
        print(("PASS " if ok else "FAIL ") + name + (f": {detail}" if detail and not ok else ""))

    card = json.loads((U / a.card).read_text())
    # C1
    entries = [f"{g}.{k}" for g in ("gates", "performance", "cost") for k in card[g]]
    orphan = [e for e in entries if L.producers(e) == ["card"] and e not in L.STEPS["card"]["card"]
              and e not in L.DEPMAP.get("entry_producers", {})]
    claimed = {e for s in L.STEPS.values() for e in s["card"] if not e.endswith(".*")} | {e for e in L.DEPMAP["entry_producers"] if "." in e}
    missing = sorted(e for e in claimed if e not in entries and e not in LEGACY)
    control("C1 every card entry has a producer step", not orphan, orphan)
    control("C1 every claimed entry is on the card", not missing, missing)
    res["entries"] = {e: L.producers(e) for e in entries}

    # C2
    vpath = U / "validation-results/13-coupling/results/verification.json"
    ver = json.loads(vpath.read_text())
    vmap = {"audit_rs": "audit_rs", "cost_parts_lines_stock": "fab+card", "cpl_rotation_audit": "fab",
            "task04_dc_cases": "task04", "vias": "core_dfm", "cmti_table_all_rows": "card (desk, not on the card)",
            "b3_c28_h25_peak_C": "b3_study", "b3_nominal_h10_peak_C": "b3_study"}
    rows, unmapped = [], []
    for m, r in ver["reads"].items():
        step = vmap.get(m)
        if step is None:
            e = next((x for x in entries if x.split(".", 1)[1] == m), None)
            step = "+".join(L.producers(e)) if e else None
        if step is None:
            unmapped.append(m)
            continue
        sname = step.split("+")[0].split(" ")[0]
        st = L.STEPS.get(sname, {})
        rd = st.get("reads", {})
        model = ("all" if rd.get("board") == "all" or rd.get("parts") == "all" else
                 "verification read set" if rd.get("verification_metrics") else
                 f"{len(rd.get('net_fill', []))} nets" if rd.get("net_fill") else "files only")
        rows.append({"metric": m, "verification_global": r["global"], "verification_nets": len(r["nets"]),
                     "verification_parts": len(r["parts"]), "step": step, "policy": st.get("policy"), "depmap_read_model": model})
    control("C2 every verification.json metric maps to a depmap step", not unmapped, unmapped)
    newer = sorted(e for e in entries if e.split(".", 1)[1] not in ver["reads"] and not e.startswith("cost."))
    res["verification_map"] = rows
    res["card_entries_newer_than_verification_json"] = newer
    print(f"     {len(rows)} verification metrics mapped; {len(newer)} card entries postdate it (s32): {', '.join(newer)}")

    # C3
    holes = []
    for step, metric in (("task04", "task04_dc_cases"), ("necks", "fuse_copper_fusing_ratio"), ("ocp_pickup", "ocp_pickup_stack_pan60_A")):
        rd = L.STEPS[step]["reads"]
        nets = set(rd.get("net_fill", []))
        vn = set(ver["reads"][metric]["nets"])
        if not vn <= nets:
            holes.append((step, sorted(vn - nets)))
        if step == "ocp_pickup":
            vp = set(ver["reads"][metric]["parts"])
            if not vp <= set(rd.get("parts_geom", [])):
                holes.append((step, sorted(vp - set(rd.get("parts_geom", [])))))
    control("C3 explicit read sets contain verification.json's", not holes, holes)

    # C4 / C5
    scan, bad, fw = [], [], set()
    for step, scripts in SCRIPTS.items():
        for sc in scripts:
            if not (U / sc).exists():
                bad.append((step, sc, "script missing"))
                continue
            for lit in literals(sc):
                p = resolve(sc, lit)
                if p is None:
                    continue
                if p.startswith("@repo/firmware/") and (sc, lit) not in CITATIONS:
                    fw.add(p)
                r = L.classify_path(p)
                c, steps = r["class"], set(r.get("steps", [])) | set(r.get("also_steps", []))
                ok = (c in ("build", "full", "unknown")
                      or (c == "input" and (step == "chain" or step in steps
                                            or (step == "b3_study" and bool(steps & {"heat_sources", "b3_study", "ceiling_sweep"}))))
                      or (c == "output" and (step == "chain" or step in steps or bool(steps & UPSTREAM)))
                      or (sc, lit) in CITATIONS)
                row = {"step": step, "script": sc, "literal": lit, "path": p, "class": c, "steps": sorted(steps), "ok": ok}
                scan.append(row)
                if not ok:
                    bad.append((step, sc, lit, c, sorted(steps)))
    res["static_scan"] = scan
    res["citations_allowlisted"] = [{"script": k[0], "literal": k[1], "why": v} for k, v in CITATIONS.items()]
    control("C4 every path the keyed steps' scripts name reaches the step", not bad, bad)
    # C6 imports, recursively
    MODDIRS = [f"{R5}", f"{R5}/b3", f"{R5}/b3-convergence", f"{R5}/b3-ratings", "native-21/layout", "native-21/layout/gates",
               "validation-plan/sim-kit/04-current", "tools"]
    imp_bad, seen = [], set()

    def walk(step, rel):
        if (step, rel) in seen:
            return
        seen.add((step, rel))
        t = (U / rel).read_text(errors="replace")
        names = set(re.findall(r"^\s*(?:from\s+([A-Za-z_][\w]*)\s+import|import\s+([A-Za-z_][\w]*))", t, re.M))
        for a_, b_ in names:
            n = a_ or b_
            for d in [str(Path(rel).parent)] + MODDIRS:
                f = f"{d}/{n}.py"
                if (U / f).exists():
                    r = L.classify_path(f)
                    st = set(r.get("steps", [])) | set(r.get("also_steps", []))
                    if not (r["class"] in ("build", "full") or (r["class"] == "input" and step in st)):
                        imp_bad.append((step, rel, f, r["class"], sorted(st)))
                    walk(step, f)
                    break
    for step in ("task04", "b3_study", "b3_ratings"):
        for sc in SCRIPTS[step]:
            walk(step, sc)
    res["imports"] = sorted({f"{st} <- {f}" for st, f in seen})
    control("C6 every repo module a keyed step imports reaches the step", not imp_bad, imp_bad)
    fw_ok = set(fw) <= {"@repo/firmware/components/control/thermal_mgmt.h"}
    control("C5 firmware read only through thermal_mgmt.h (b3_ratings)", fw_ok, sorted(fw))
    res["firmware_literals"] = sorted(fw)
    if a.json:
        Path(a.json).write_text(json.dumps(res, indent=1) + "\n")
    raise SystemExit(0 if all(c["pass"] for c in res["controls"]) else 1)


if __name__ == "__main__":
    main()
