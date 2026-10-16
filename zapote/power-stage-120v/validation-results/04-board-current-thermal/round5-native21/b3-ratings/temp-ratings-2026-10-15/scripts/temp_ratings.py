#!/usr/bin/env python3
"""Temperature ratings of the native-21 s47 BOM lines whose datasheet-ledger entry carries no temperature rating, against
the B3 hot-copper local temperature at the release case (c17.5_h10 @ 61 C) and the c28 ratchet case (c28_h10 @ 55 C).

    python3 -I scripts/temp_ratings.py        -> results.json, results.md (beside scripts/)

Read only. Inputs (all copies in ../snap, taken 2026-10-15 22:3x from PS = worktrees/ps-integrate/zapote/power-stage-120v):
  * snap/ledger-HEAD.json, snap/default-HEAD.csv, snap/margins-HEAD.json: `git show HEAD:` of the s47 records
    (PS HEAD 4446e08a1; the s47 ledger / B3 commit da9ec7ec3 / e3586ecf7);
  * snap/runs/*: the B3 BASIS run files (b3-ratings/runs, gitignored). They are a re-solve stamped board 63aba33f (the
    other agent's working tree), not 4139c87b; the copied gate reproduces all 288 rows of the s47 margins.json from them
    with zero difference at the file's 0.1 K rounding, and the s47 monitor sweep within 0.06 K (checked below, stops if not).
Estimator (b3_ratings_gate.est, vendor copy): Q(0.25) + 3 |Q(0.25) - Q(0.5)| + (bay - 50) on
  * the pad-copper maximum (run-file probes; monitor_sweep's pad proxy), plus P x Rth for a junction or self-heated
    part (the gate's probe-row rule), or
  * the body model's tj_c where B3 carries a heat row for the part (U1/U2, U3/U37-U39, R39, R53-R58, R67-R70), as the
    gate does for its gated part rows.
Resistors: the terminal (pad) against the derating line T_max - (T_max - T_knee) P / (0.8 P_rated) (the gate's 20 %
power-margin rule, G6), plus the element (body model) against T_max where B3 has a body.

Re-base on a later B3 model (S18, 2026-10-15: PS2's body-to-air path moves the neighbours 0-3.1 K):

    python3 -I scripts/temp_ratings.py --snap DIR --rebase

DIR holds the same four inputs, with runs/ and margins-HEAD.json from one chain (the run files the committed margins.json
was solved from) and ledger-HEAD.json the pre-S21 ledger (the 73 lines are the ones it left unrated). The equivalence is
then: the vendor gate reproduces every row of that margins.json from those runs (both on one board); the c47 monitor sweep
is a pre-S18 record, so its difference is reported, not asserted.
"""
import argparse
import csv
import json
import os
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
_ap = argparse.ArgumentParser()
_ap.add_argument("--snap", default=str(ROOT / "snap"), help="input snapshot directory (default ../snap)")
_ap.add_argument("--rebase", action="store_true",
                 help="the snapshot's margins / runs are a later model on one board: assert their equivalence, report the "
                      "c47 sweep difference instead of asserting it")
ARGS = _ap.parse_args() if __name__ == "__main__" else _ap.parse_args([])
SNAP = Path(ARGS.snap).resolve()
os.environ["TEMP_RATINGS_SNAP"] = str(SNAP)    # read by the vendor gate's BOM_CSV
sys.path.insert(0, str(HERE / "vendor"))
if not ARGS.rebase:                     # the s47 records: the pre-S18 gate (no MODULES row) they were made with
    sys.path.insert(0, str(HERE / "vendor" / "s47"))
sys.path.insert(0, str(HERE))
import b3_ratings_gate as gate          # noqa: E402  (vendor copy of PS HEAD; BOM_CSV -> snap/default-HEAD.csv)
import power_table as pt               # noqa: E402
import ratings_table as rt             # noqa: E402

CASES = {"c17.5_h10": 61.0, "c22_h10": 55.0, "c28_h10": 55.0}
REL, C28 = "c17.5_h10", "c28_h10"
C47_SWEEP = Path("/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v/validation-results/"
                 "11-candidates/c47-ref25-grade/results/monitor-sweep-s47.json")
S47_BOARD = "4139c87b8a10b0110435d42ecc2751c19ff03b565056d8771d6e771a8e28d33c"
TEMP_UNITS = ("C", "K")


def unrated_lines(led, bom_rows):
    out = []
    for row in bom_rows:
        m = row["LCSC"].strip()
        e = led[m]
        if any(r.get("unit") in TEMP_UNITS for r in e["ratings"]):
            continue
        out.append({"mpn": m, "refs": [d.strip() for d in row["Designator"].split(",") if d.strip()],
                    "footprint": row["Footprint"].split(":")[-1], "class": e["class"], "status": e["status"],
                    "ledger_ratings": [r["parameter"] for r in e["ratings"]]})
    return out


def load_runs():
    data = {c: [json.loads((SNAP / "runs" / f"{c}_p0p{m}.json").read_text()) for m in ("25", "5")] for c in CASES}
    for c, (a, b) in data.items():
        assert a["board_sha256"] == b["board_sha256"], c
        assert a["copper_temp_model"]["model"] == "hot-iterated" and abs(a["copper_temp_model"]["air_c"] - CASES[c]) < 1e-9, c
    return data


def equivalence(data):
    """The snapshot run files must reproduce the s47 records: margins.json (HEAD) rows and the c47 monitor sweep."""
    res = gate.run(SNAP / "runs", {c: b for c, b in CASES.items()})
    head = json.loads((SNAP / "margins-HEAD.json").read_text())
    board = S47_BOARD
    if ARGS.rebase:
        board = data[REL][0]["board_sha256"]
        assert all(data[c][0]["board_sha256"] == board for c in CASES), "rebase: run files from more than one board"
    assert set(head["board_sha256"].values()) == {board}, (set(head["board_sha256"].values()), board)
    dmax, n = 0.0, 0
    for c, rows in head["cases"].items():
        new = {" ".join(r["item"].split()[:3]): r for r in res["cases"][c]}
        if ARGS.rebase:
            assert set(new) == {" ".join(r["item"].split()[:3]) for r in rows}, f"rebase: {c} row sets differ"
        for r in rows:
            q = new[" ".join(r["item"].split()[:3])]
            dmax, n = max(dmax, abs(q["est_c"] - r["est_c"]), abs(q["limit_c"] - r["limit_c"])), n + 1
    sw = json.loads(C47_SWEEP.read_text())
    assert sw["board_sha256"] == S47_BOARD
    smax = 0.0
    for r in sw["sweep_unrated"] + sw["sweep_rated_le_105c"]:
        for c in (REL, C28):
            smax = max(smax, abs(pad(data, c, r["ref"]) - r["pad_est_c"][c]))
    assert dmax <= 0.05 and (ARGS.rebase or smax <= 0.06), (dmax, smax)
    out = {"margins_rows": n, "margins_max_abs_diff_c": round(dmax, 3), "sweep_refs": len(sw["sweep_unrated"]) + len(sw["sweep_rated_le_105c"]),
           "sweep_max_abs_diff_c": round(smax, 3), "run_board_sha256": data[REL][0]["board_sha256"], "s47_board_sha256": S47_BOARD,
           "head_margins": head, "gate_rows": res}
    if ARGS.rebase:
        out["rebase"] = {"margins_board_sha256": board, "sweep_asserted": False,
                         "note": "re-based run files (later B3 model); the c47 monitor sweep is the pre-S18 s47 record, so "
                                 "sweep_max_abs_diff_c is the model's move, not an equivalence"}
    return out


def pad(data, c, ref):
    a, b = data[c]
    return gate.est(a["probes"][ref]["pad_max_cell_c"], b["probes"][ref]["pad_max_cell_c"], CASES[c])


def body(data, c, ref):
    a, b = data[c]
    pa = {p["ref"]: p for p in a["parts"]}.get(ref)
    pb = {p["ref"]: p for p in b["parts"]}.get(ref)
    if pa is None or pb is None:
        return None
    return {"tj": gate.est(pa["tj_c"], pb["tj_c"], CASES[c]), "w": pa["watts_into_model"], "label_mpn": pa.get("mpn"),
            "spec": pa.get("spec")}


def evaluate(line, data, P):
    R = rt.RATINGS[line["mpn"]]
    rows = []
    for ref in line["refs"]:
        if ref not in data[REL][0]["probes"]:
            rows.append({"ref": ref, "no_probe": True})
            continue
        row = {"ref": ref, "cases": {}}
        for c in CASES:
            t_pad = pad(data, c, ref)
            b = body(data, c, ref)
            if R["model"] == "res":
                prated, tknee, tmax = R["res"]
                if b is not None:
                    w, wb = b["w"], f"B3 heat row {b['w']:.4f} W ({c})"
                else:
                    w, wb = P[ref]
                lim = tmax - (tmax - tknee) * w / (0.8 * prated)
                cs = {"pad_c": round(t_pad, 1), "est_c": round(t_pad, 1), "limit_c": round(lim, 1), "p_w": w, "p_basis": wb,
                      "what": "terminal (pad) vs derating line at P, 20 % margin"}
                if b is not None:
                    cs["element_c"] = round(b["tj"], 1)
                    cs["element_margin_k"] = round(tmax - b["tj"], 1)
                cs["margin_k"] = round(lim - t_pad, 1)
                cs["bare_margin_k"] = round(tmax - t_pad, 1)
            elif R["model"] == "body" and b is not None:
                cs = {"pad_c": round(t_pad, 1), "est_c": round(b["tj"], 1), "limit_c": R["limit_c"], "p_w": b["w"],
                      "p_basis": f"B3 heat row {b['w']:.4f} W, body model {b['spec']} (run-file label {b['label_mpn']})",
                      "what": "B3 body-model junction (tj_c)", "margin_k": round(R["limit_c"] - b["tj"], 1)}
            else:
                if b is not None:
                    w, wb = b["w"], f"B3 heat row {b['w']:.4f} W (body tj_c {b['tj']:.1f} C)"
                elif ref in gate.MONITORS:
                    k = gate.MONITORS[ref][0]
                    w, wb = gate.MONITOR_SELF[k], f"b3_ratings_gate MONITOR_SELF['{k}']"
                else:
                    w, wb = P.get(ref, (0.0, "negligible (no circuit dissipation)"))
                rth = R.get("rth")
                sh = w * rth[0] if rth else 0.0
                est = t_pad + sh + R.get("extra_k", 0.0)
                cs = {"pad_c": round(t_pad, 1), "self_heat_k": round(sh, 2), "est_c": round(est, 1), "limit_c": R["limit_c"],
                      "p_w": w, "p_basis": wb, "what": R.get("what", "pad + P x Rth"),
                      "margin_k": round(R["limit_c"] - est, 1)}
                if R.get("extra_k"):
                    cs["extra_k"] = R["extra_k"]
                    cs["extra_basis"] = R["extra_basis"]
            row["cases"][c] = cs
        rows.append(row)
    probed = [r for r in rows if not r.get("no_probe")]
    worst = {c: min(probed, key=lambda r: r["cases"][c]["margin_k"]) for c in CASES} if probed else {}
    return rows, worst


def verdict(m_rel, m_28):
    if m_rel < 0:
        return "VIOLATION (release)"
    v = "c28 gap (airflow route)" if m_28 < 0 else "pass"
    if m_rel < 10:
        v += "; < 10 K at release"
    return v


def short_refs(refs):
    return ", ".join(refs) if len(refs) <= 6 else ", ".join(refs[:5]) + f" ... ({len(refs)})"


def render_md(res):
    import results_text as tx
    eq = res["equivalence"]
    L = [(tx.HEAD_REBASE if "rebase" in eq else tx.HEAD).format(n=res["n_lines"], refs=res["n_refs"],
                                                                  board8=eq["run_board_sha256"][:8], **eq), ""]
    ls = res["lines"]
    f = lambda w: f"{w['ref']} {w['est_c']} / {w['limit_c']} C ({w['margin_k']:+.1f} K)"
    viol = [r for r in ls if r["release"]["margin_k"] < 0]
    gaps = sorted([r for r in ls if r["c28"]["margin_k"] < 0], key=lambda r: r["c28"]["margin_k"])
    thin = [r for r in ls if 0 <= r["release"]["margin_k"] < 10]
    L.append("## Summary")
    L.append("")
    L.append(f"- **Release-case violations: {len(viol)}**" + ("" if not viol else ": " + "; ".join(f"{r['mpn']} {f(r['release'])}" for r in viol)))
    L.append(f"- **Under 10 K at release: {len(thin)}**: " + "; ".join(f"{r['mpn']} {f(r['release'])}" for r in thin))
    L.append(f"- **c28 gaps (airflow route): {len(gaps)}**: " + "; ".join(f"{r['mpn']} {f(r['c28'])}" for r in gaps))
    nop = [x for r in ls for x in r["no_probe"]]
    L.append(f"- **Parts with no probe: {len(nop)}**" + (": " + ", ".join(nop) if nop else " (all refs are on the board's probe list)"))
    L.append("")
    L.append("| # | MPN | refs | rating (applies to) and source | release c17.5_h10 @ 61: ref, est / limit, margin | "
             "c28_h10 @ 55: ref, est / limit, margin | verdict |")
    L.append("|---|---|---|---|---|---|---|")
    for i, r in enumerate(res["lines"], 1):
        R = r["rating"]
        rel, c28 = r["release"], r["c28"]
        def cell(w):
            extra = ""
            if w.get("self_heat_k"):
                extra = f" (pad {w['pad_c']} + {w['self_heat_k']} K)"
            if w.get("extra_k"):
                extra = f" (pad {w['pad_c']} + {w['extra_k']} K rise)"
            if "element_c" in w:
                extra = f" (element {w['element_c']} / {R['t_max_c']:g})"
            return f"{w['ref']}: {w['est_c']} / {w['limit_c']}{extra}, **{w['margin_k']:+.1f} K**"
        rat = f"{R['t_max_c']:g} C {R['applies']}; {R['source']}"
        if r["model"] == "res":
            rat = (f"{R['t_max_c']:g} C ({R['res'][0]:g} W at {R['res'][1]:g} C to 0 W at {R['res'][2]:g} C; terminal "
                   f"limit at P with 20 % margin); {R['source']}")
        L.append(f"| {i} | {r['mpn']} | {short_refs(r['refs'])} | {rat} | {cell(rel)} | {cell(c28)} | {r['verdict']} |")
    L.append("")
    L.append("## Bases and gaps per line")
    L.append("")
    for r in res["lines"]:
        R = r["rating"]
        rel = r["release"]
        L.append(f"- **{r['mpn']}** ({r['class']}, ledger {r['status']}): {R['basis']}. Release worst {rel['ref']}: "
                 f"{rel['what']}; P = {rel['p_w']:.3g} W ({rel['p_basis']})." + (f" Gap: {R['gap']}." if R.get("gap") else ""))
    L.append("")
    L.append(tx.TAIL)
    return "\n".join(L) + "\n"


def main():
    led = json.loads((SNAP / "ledger-HEAD.json").read_text())["entries"]
    bom_rows = list(csv.DictReader(open(SNAP / "default-HEAD.csv", newline="")))
    lines = unrated_lines(led, bom_rows)
    data = load_runs()
    eq = equivalence(data)
    P = pt.resistor_powers()
    P.update(pt.ic_powers(rt.DS))
    out = []
    missing = [l["mpn"] for l in lines if l["mpn"] not in rt.RATINGS]
    assert not missing, f"no rating for {missing}"
    for line in lines:
        R = rt.RATINGS[line["mpn"]]
        rows, worst = evaluate(line, data, P)
        rec = {**line, "rating": {k: v for k, v in R.items() if k not in ("model",)}, "model": R["model"], "per_ref": rows,
               "no_probe": [r["ref"] for r in rows if r.get("no_probe")]}
        if worst:
            wr, w28 = worst[REL], worst[C28]
            rec["release"] = {"ref": wr["ref"], **wr["cases"][REL]}
            rec["c22"] = {"ref": worst["c22_h10"]["ref"], **worst["c22_h10"]["cases"]["c22_h10"]}
            rec["c28"] = {"ref": w28["ref"], **w28["cases"][C28]}
            rec["verdict"] = verdict(rec["release"]["margin_k"], rec["c28"]["margin_k"])
        else:
            rec["verdict"] = "no probe"
        out.append(rec)
    out.sort(key=lambda r: r.get("release", {}).get("margin_k", 1e9))
    eqs = {k: v for k, v in eq.items() if k not in ("head_margins", "gate_rows")}
    res = {"cases": CASES, "release_case": REL, "n_lines": len(lines), "n_refs": sum(len(l["refs"]) for l in lines),
           "equivalence": eqs, "lines": out}
    (ROOT / "results.json").write_text(json.dumps(res, indent=1) + "\n")
    (ROOT / "results.md").write_text(render_md(res))
    for r in out:
        if "release" in r:
            print(f"{r['mpn'][:20]:20} {r['release']['ref']:5} {r['release']['est_c']:6.1f}/{r['release']['limit_c']:6.1f} "
                  f"{r['release']['margin_k']:+6.1f} | {r['c28']['ref']:5} {r['c28']['est_c']:6.1f} {r['c28']['margin_k']:+6.1f} | {r['verdict']}")
    print("lines", len(lines), "refs", res["n_refs"], "equivalence", eqs)


if __name__ == "__main__":
    main()
