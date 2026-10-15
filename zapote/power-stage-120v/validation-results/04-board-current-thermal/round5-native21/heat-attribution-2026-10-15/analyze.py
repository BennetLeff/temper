#!/usr/bin/env python3
"""Heat attribution on the B3 body-level model (step 2 of 2): synthesize cases from the unit-term solves, check
superposition against the gate's own solves, attribute every gated row, rank levers by ceiling amps.

    python3 analyze.py [--snap SNAPSHOT_ROOT] [--gate-runs gate-runs]   -> results.json, tables.md

Inputs: cache/p0p25, cache/p0p5 from solve_terms.py; gate-runs/ from the snapshot's own run_basis.py
(`run_basis.py --cases c18_h10@61,c22_h10@55 --runs gate-runs --out gate-runs/margins-repro.json`).

Gate estimate per quantity (b3_ratings_gate.est): Q(0.25) + 3 |Q(0.25) - Q(0.5)| + (bay - 50). With Q = 50 + rise:
    est = bay + rise_0.25 + 3 |rise_0.25 - rise_0.5|
and rise_0.25 = sum over terms of coef_t * unit_t(at the 0.25 mm locator) exactly (linear model, fixed locator).
Attribution terms: bay air (the bay temperature itself), FET-case tie (tie_hs + tie_ls, t_case - bay), each A4
copper field, each part-heat group, and the mesh correction 3 |dQ| as its own (non-linear) term.
Locators for max-type quantities (1 mm block peak, FET-row copper max, a part's hottest full pad cell) are taken from
the synthesized 0.25 mm field of the case, so the per-term values at that point sum exactly to the reported value.
The gate's rows and limits come from b3_ratings_gate.evaluate itself, run unrounded.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import solve_terms as st  # noqa: E402

PITCHES = (0.25, 0.5)
LAYERS = ("F.Cu", "In1.Cu", "In2.Cu", "B.Cu")
K_MESH = 3.0
# net -> groups with pads on it (11-candidates/GROUPS.md interface / internal net lists; the stage-19c map that
# 13-coupling assign32 carries forward). Owner = the group a copper change on that net is reviewed in.
NET_GROUPS = {"sw_a": ("G03", ["G03", "G05", "G06", "G07", "G09"]),
              "sw_b": ("G03", ["G03", "G04", "G05", "G06", "G07"]),
              "res_a": ("G04", ["G04"]),
              "coil_feed": ("G04", ["G04", "G09"]),
              "leg_ret": ("G03", ["G03", "G05", "G06", "G07", "G08"]),
              "hv_ret": ("G08", ["G02", "G03", "G08"]),
              "bus_p": ("G03", ["G02", "G03", "G08"]),
              "ac_n_in": ("G01", ["G01"]),
              "ac_l_in": ("G01", ["G01"])}
GROUP_NAMES = {"G01": "mains_emi_rectifier", "G02": "dc_link_clamp", "G03": "bridge_power_stage", "G04": "resonant_tank",
               "G05": "gate_drive", "G06": "bias_supplies", "G07": "bias_monitors_isolation", "G08": "sense_protect",
               "G09": "ct_zc_detect", "G10": "selv_interface_aux"}


# ------------------------------------------------------------------------------------------------ loading
class Basis:
    def __init__(self, snap):
        self.e = st.env(snap)
        self.rb, self.rs, self.fc, self.gate, self.br = (self.e[k] for k in ("run_basis", "rs", "fet_case", "gate", "br"))
        case18, heat18, _ = st.release_inputs(self.e, st.CACHE / "inputs" / "c18", 18.0, "c18")
        self.a4 = st.a4_names(case18)
        self.terms = st.all_terms(case18)
        self.heat18 = {p["ref"]: p for p in json.loads(Path(heat18).read_text())["parts"]}
        self.u, self.meta, self.mpad = {}, {}, {}
        for p in PITCHES:
            d = st.CACHE / f"p{str(p).replace('.', 'p')}"
            self.meta[p] = dict(np.load(d / "meta.npz"))
            mj = json.loads((d / "meta.json").read_text())
            self.mpad[p] = {r: (v["layer"], np.array(v["ii"]), np.array(v["jj"]), np.array(v["a"])) for r, v in mj["pads"].items()}
            self.u[p] = {}
            for t in self.terms:
                z = np.load(d / f"{t.replace(':', '__')}.npz")
                self.u[p][t] = (z["cu"], dict(zip(z["tj_refs"].tolist(), z["tj"].tolist())))
            j = json.loads((d / f"{self.terms[0].replace(':', '__')}.json").read_text())
            self.spec = {r["ref"]: r.get("spec") for r in j["rows"]}
            self.w18 = {r["ref"]: r["watts_into_model"] for r in j["rows"]}
            self.board_sha = j["board_sha256"]
        self.loss_a4 = {n: json.loads((self.br.T.A4 / f"{n}.json").read_text())["loss_w"] for n in self.a4}
        self.it18 = self.rb.i_trip(18.0)

    # ---------------------------------------------------------------------------------------- coefficients
    def coefs(self, ceil, bay, scale=None):
        """term -> multiplier on its unit solve for the gate case at `ceil` (I_trip = run_basis.i_trip) and `bay`;
        scale: {term: factor} applied on top (a lever)."""
        it = self.rb.i_trip(ceil)
        self.rs.OPS["attr"] = {"I_t": it, "I_line": self.rb.I_LINE_A, "parts": "nominal", "heat": "c28"}
        c = {f"a4:{n}": float(k) for n, k in (item.split(":") for item in self.rs.cases("attr").split(","))}
        kt = (it / 29.4) ** 2 / (self.it18 / 29.4) ** 2
        for g, refs in st.PART_GROUPS.items():
            tank = {r in self.br.TANK_ROWS for r in refs}
            assert len(tank) == 1, g
            c[f"part:{g}"] = kt if tank.pop() else 1.0
        tc = self.fc.t_case(ceil, i_line=self.rb.I_LINE_A)
        for t, refs in st.TIES.items():
            vals = {round(tc[r], 12) for r in refs}
            assert len(vals) == 1, (t, vals)
            c[f"tie:{t}"] = tc[refs[0]] - bay
        for k, v in (scale or {}).items():
            c[k] *= v
        return c

    def watts(self, coefs):
        """Watts into the model per term at these coefficients (ties: none)."""
        w = {}
        for t, k in coefs.items():
            kind, n = t.split(":")
            if kind == "a4":
                w[t] = k * self.loss_a4[n]
            elif kind == "part":
                w[t] = k * sum(self.w18[r] for r in st.PART_GROUPS[n])
        return w

    # ---------------------------------------------------------------------------------------- synthesis
    def synth(self, p, coefs):
        cu = np.zeros(self.u[p][self.terms[0]][0].shape)
        tj = {}
        for t, k in coefs.items():
            f, j = self.u[p][t]
            cu += f * np.float64(k)
            for r, v in j.items():
                tj[r] = tj.get(r, 0.0) + k * v
        return cu, tj

    def ref_group_coef(self, coefs, ref):
        g = next(g for g, refs in st.PART_GROUPS.items() if ref in refs)
        return coefs[f"part:{g}"]

    # ---------------------------------------------------------------------------------------- metrics (run_case's)
    def locate(self, p, cu, tj):
        """Values (rise, K) and locators of every gate quantity on one synthesized field (body_runs.run_case logic)."""
        m = self.meta[p]
        board, cfrac, x, y = m["board"], m["cfrac"], m["x"], m["y"]
        nx, ny = board.shape
        s = max(int(round(1.0 / p)), 1)
        nbx, nby = nx // s, ny // s
        mk = board[:nbx * s, :nby * s].reshape(nbx, s, nby, s).all(axis=(1, 3))
        best = None
        for li in range(4):
            r_ = cu[li][:nbx * s, :nby * s].reshape(nbx, s, nby, s).mean(axis=(1, 3))
            cf = cfrac[li][:nbx * s, :nby * s].reshape(nbx, s, nby, s).mean(axis=(1, 3))
            r_ = np.where(mk & (cf > 0.05), r_, -np.inf)
            ia, ja = np.unravel_index(np.argmax(r_), r_.shape)
            if best is None or r_[ia, ja] > best[0]:
                best = (float(r_[ia, ja]), li, int(ia), int(ja))
        out = {"block": (best[0], ("block", best[1], best[2], best[3]))}
        xi, yj = np.nonzero(x <= 80)[0], np.nonzero(y <= 12.5)[0]
        sub = cu[:, :xi.max() + 1, :yj.max() + 1]
        li, i, j = np.unravel_index(np.argmax(sub), sub.shape)
        out["fet"] = (float(sub[li, i, j]), ("cell", int(li), int(i), int(j)))
        for ref, (li, ii, jj, a) in self.mpad[p].items():
            v = cu[li][ii, jj]
            full = a >= 0.5 * p * p
            if full.any():
                k = np.nonzero(full)[0][np.argmax(v[full])]
            else:
                k = int(np.argmax(a))
            out[("pad", ref)] = (float(v[k]), ("cell", int(li), int(ii[k]), int(jj[k])))
            out[("tj", ref)] = (tj[ref], ("tj", ref))
        out["_xy"] = (x, y, s)
        return out

    def at(self, p, loc, cu_or_term):
        """Value of a field (array) or a unit term (name) at a locator."""
        if isinstance(cu_or_term, str):
            f, j = self.u[p][cu_or_term]
        else:
            f, j = cu_or_term
        if loc[0] == "tj":
            return j[loc[1]]
        if loc[0] == "cell":
            return float(f[loc[1], loc[2], loc[3]])
        _, li, ia, ja = loc
        s = max(int(round(1.0 / p)), 1)
        return float(f[li, ia * s:(ia + 1) * s, ja * s:(ja + 1) * s].mean())

    def run_dict(self, p, met, coefs):
        """A run_case-shaped dict for b3_ratings_gate.evaluate."""
        x, y, s = met["_xy"]
        _, (_, li, ia, ja) = met["block"]
        parts = []
        for ref in self.mpad[p]:
            parts.append({"ref": ref, "spec": self.spec.get(ref), "tj_c": 50.0 + met[("tj", ref)][0],
                          "pad_max_cell_c": 50.0 + met[("pad", ref)][0],
                          "watts_into_model": self.w18[ref] * self.ref_group_coef(coefs, ref)})
        return {"peak_1mm_block": {"temperature_c": 50.0 + met["block"][0], "layer": LAYERS[li],
                                   "x_mm": float(x[ia * s] - p / 2 + 0.5), "y_mm": float(y[ja * s] - p / 2 + 0.5)},
                "fet_row_max_c": 50.0 + met["fet"][0], "parts": parts}

    # ---------------------------------------------------------------------------------------- gate rows
    @contextlib.contextmanager
    def unrounded(self):
        self.gate.round = lambda v, n=None: v          # module global shadows the builtin inside evaluate()
        try:
            yield
        finally:
            del self.gate.round

    def case(self, ceil, bay, scale=None):
        """Synthesize the gate case; returns rows (unrounded evaluate output + quantity key) and the fields."""
        c = self.coefs(ceil, bay, scale)
        f, met, rd = {}, {}, {}
        for p in PITCHES:
            f[p] = self.synth(p, c)
            met[p] = self.locate(p, *f[p])
            rd[p] = self.run_dict(p, met[p], c)
        with self.unrounded():
            rows = self.gate.evaluate(rd[0.25], rd[0.5], bay)
        for r in rows:
            r["q"] = qkey(r["item"])
            v25, v05 = met[0.25][r["q"]][0], met[0.5][r["q"]][0]
            mine = bay + v25 + K_MESH * abs(v25 - v05)
            assert abs(mine - r["est_c"]) < 1e-9, (r["item"], mine, r["est_c"])
            r["rise25"], r["rise05"], r["mesh_k"] = v25, v05, K_MESH * abs(v25 - v05)
            r["loc25"] = met[0.25][r["q"]][1]
        return {"coefs": c, "rows": rows, "fields": f, "met": met, "rd": rd, "ceil": ceil, "bay": bay}

    def attribute(self, cs, row):
        """Per-term K at the row (0.25 mm locator) + bay + mesh; sums to the gate estimate."""
        loc = row["loc25"]
        a = {t: k * self.at(0.25, loc, t) for t, k in cs["coefs"].items()}
        a["bay_air"] = cs["bay"]
        a["mesh_corr"] = row["mesh_k"]
        return a

    def margin(self, ceil, bay, scale=None, pick=None):
        cs = self.case(ceil, bay, scale)
        rows = [r for r in cs["rows"] if r["gated"] and (pick is None or pick(r))]
        w = min(rows, key=lambda r: r["limit_c"] - r["est_c"])
        return w["limit_c"] - w["est_c"], w["item"]

    def ceiling(self, bay, scale=None, pick=None, lo=8.0, hi=34.0, tol=0.005):
        """Highest ceiling (A) with every picked gated row >= 0 margin, by bisection on the synthesized gate case."""
        mlo, _ = self.margin(lo, bay, scale, pick)
        if mlo < 0:
            return 0.0, self.margin(lo, bay, scale, pick)[1]
        mhi, _ = self.margin(hi, bay, scale, pick)
        if mhi >= 0:
            return hi, None
        while hi - lo > tol:
            mid = 0.5 * (lo + hi)
            if self.margin(mid, bay, scale, pick)[0] >= 0:
                lo = mid
            else:
                hi = mid
        return lo, self.margin(hi, bay, scale, pick)[1]


def qkey(item):
    if item.startswith("laminate: 1 mm-block"):
        return "block"
    if item.startswith("laminate: FET-row"):
        return "fet"
    ref = item.split(":")[0]
    return ("pad", ref) if "terminal derating" in item else ("tj", ref)


def short(item):
    if item.startswith("laminate: 1 mm"):
        return "laminate 1 mm block"
    if item.startswith("laminate: FET"):
        return "laminate FET row"
    ref = item.split(":")[0]
    if "terminal derating" in item:
        return f"{ref} terminal derating"
    if "element" in item:
        return f"{ref} element"
    if "Tj" in item or "TJ" in item:
        return f"{ref} Tj"
    if "MKP" in item:
        return f"{ref} body"
    return item[:40]


TERM_INFO = {}


def term_info(b: Basis, t):
    kind, n = t.split(":") if ":" in t else (t, t)
    if kind == "a4":
        net = json.loads((b.br.T.A4 / f"{n}.json").read_text())["net"]
        own, gs = NET_GROUPS[net]
        scal = "line (I_line 13.5 A, fixed)" if net.startswith("ac_") else "tank I^2"
        return {"kind": f"copper loss in net {net}", "net": net, "group": own, "groups_on_net": gs, "scales": scal}
    if kind == "part":
        asg = json.loads((b.e["snap"] / "zapote/power-stage-120v/validation-results/13-coupling/results/assignment.json")
                         .read_text())["assignment"]
        refs = st.PART_GROUPS[n]
        gs = sorted({asg.get(r, "?") for r in refs})
        tank = refs[0] in b.br.TANK_ROWS
        scal = ("tank I^2" if tank else "line (I_line 13.5 A, fixed)" if n == "L1" else
                "frequency/charge-set (60 kHz window top, deck Q)" if n in ("R_on", "R_off", "drivers", "RECOM", "U26", "PS2")
                else "fixed estimate")
        return {"kind": "part heat", "refs": refs, "group": "/".join(gs), "scales": scal}
    if kind == "tie":
        return {"kind": "FET-case tie (sink side)", "group": "G03", "scales": "t_case(ceiling) - bay"}
    return {"kind": t, "group": "-", "scales": "-"}


def label(t):
    if t.startswith("a4:"):
        return t[3:].split("-p")[0]
    if t.startswith("part:"):
        return "part " + t[5:]
    if t.startswith("tie:"):
        return t[4:]
    return t


def combine(a):
    """Merge the two tie terms into one, and bay + tie into the 'bay air + FET case ties' term."""
    out = {k: v for k, v in a.items() if not k.startswith("tie:")}
    out["fet_tie"] = a["tie:tie_hs"] + a["tie:tie_ls"]
    return out


# ------------------------------------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snap", default=str(st.DEFAULT_SNAP))
    ap.add_argument("--gate-runs", default=str(HERE / "gate-runs"))
    a = ap.parse_args()
    b = Basis(a.snap)
    res = {"board_sha256": b.board_sha, "terms": {t: term_info(b, t) for t in b.terms}, "checks": {}}
    gr = Path(a.gate_runs)

    # ---------------- superposition checks
    cases = {"c18_h10": (18.0, 61.0), "c22_h10": (22.0, 55.0)}
    syn = {c: b.case(*v) for c, v in cases.items()}
    chk = {}
    # (1) field level, 0.5 mm: synthesized sum vs the full-case solve with every term at once
    for c, (ceil, bay) in cases.items():
        name = "full:" + c.split("_")[0]
        d = st.CACHE / "p0p5"
        z = np.load(d / f"{name.replace(':', '__')}.npz")
        full_cu = z["cu"].astype(np.float64)
        full_tj = dict(zip(z["tj_refs"].tolist(), z["tj"].tolist()))
        cu, tj = syn[c]["fields"][0.5]
        chk[f"{c} field 0.5 mm: max |sum of terms - full solve| on copper (K)"] = float(np.abs(cu - full_cu).max())
        chk[f"{c} field 0.5 mm: max |sum - full| junction nodes (K)"] = max(abs(tj[r] - full_tj[r]) for r in full_tj)
    # (2) metric level, both pitches: synthesized quantities vs the gate's own run files
    for c, (ceil, bay) in cases.items():
        for p in PITCHES:
            f = gr / f"{c}_p{str(p).replace('.', 'p')}.json"
            g = json.loads(f.read_text())
            rd = syn[c]["rd"][p]
            gp = {r["ref"]: r for r in g["parts"]}
            dmax = max(max(abs(r["tj_c"] - gp[r["ref"]]["tj_c"]), abs(r["pad_max_cell_c"] - gp[r["ref"]]["pad_max_cell_c"]))
                       for r in rd["parts"])
            dmax = max(dmax, abs(rd["peak_1mm_block"]["temperature_c"] - g["peak_1mm_block"]["temperature_c"]),
                       abs(rd["fet_row_max_c"] - g["fet_row_max_c"]))
            same_loc = (rd["peak_1mm_block"]["x_mm"], rd["peak_1mm_block"]["y_mm"], rd["peak_1mm_block"]["layer"]) == \
                (g["peak_1mm_block"]["x_mm"], g["peak_1mm_block"]["y_mm"], g["peak_1mm_block"]["layer"])
            chk[f"{c} {p} mm: max |synth - gate run| over tj / pad / block / FET row (K)"] = dmax
            chk[f"{c} {p} mm: block peak at the gate run's location"] = same_loc
            assert g["board_sha256"] == b.board_sha
    # (3) gate estimate: sum of attribution terms vs margins (reproduced here and committed)
    rep = json.loads((gr / "margins-repro.json").read_text())
    com = json.loads((b.e["snap"] / "zapote/power-stage-120v/validation-results/04-board-current-thermal/round5-native21/"
                      "b3-ratings/margins.json").read_text())
    for c in cases:
        cs = syn[c]
        worst_sum, worst_rep, worst_com = 0.0, 0.0, 0.0
        rr = {r["item"]: r for r in rep["cases"][c]}
        cr = {r["item"]: r for r in com["cases"][c]}
        for r in cs["rows"]:
            at = b.attribute(cs, r)
            s = sum(at.values())
            worst_sum = max(worst_sum, abs(s - r["est_c"]))
            worst_rep = max(worst_rep, abs(s - rr[r["item"]]["est_c"]))
            worst_com = max(worst_com, abs(s - cr[r["item"]]["est_c"]))
        chk[f"{c}: max |sum of terms - synthesized gate est| (K)"] = worst_sum
        chk[f"{c}: max |sum of terms - margins-repro.json est_c (0.1 K rounded)| (K)"] = worst_rep
        chk[f"{c}: max |sum of terms - committed margins.json est_c (0.1 K rounded)| (K)"] = worst_com
        chk[f"{c}: rows compared"] = len(cs["rows"])
    # (4) term coefficients equal the gate's heat files (run_basis.inputs) at c22 and c28
    for ceil, op in ((22.0, "c22"), (28.0, "c28")):
        _, hj, _ = st.release_inputs(b.e, st.CACHE / "inputs" / op, ceil, op)
        hw = {p["ref"]: p["watts_nominal"] * p["board_fraction"] for p in json.loads(Path(hj).read_text())["parts"]
              if p.get("board_fraction")}
        cf = b.coefs(ceil, 55.0)
        chk[f"part watts at {op}: max |unit x coef - run_basis.inputs| (W)"] = max(
            abs(b.w18[r] * b.ref_group_coef(cf, r) - hw[r]) for r in hw if hw[r])
    # (5) energy: each unit solve's balance
    worst_bal = 0.0
    for p in PITCHES:
        for t in b.terms:
            j = json.loads((st.CACHE / f"p{str(p).replace('.', 'p')}" / f"{t.replace(':', '__')}.json").read_text())
            worst_bal = max(worst_bal, abs(j["balance"]["balance_w"]))
    chk["max |energy balance| over unit solves (W)"] = worst_bal
    res["checks"] = chk

    # ---------------- attribution tables
    GATED_REQ = ["C40", "C38", "C41", "C39", "R10", "R12", "R18", "R20", "U26", "U41", "U42", "R5"]
    res["attribution"] = {}
    for c, cs in syn.items():
        out = []
        for r in sorted(cs["rows"], key=lambda r: r["limit_c"] - r["est_c"]):
            if not r["gated"]:
                continue
            at = combine(b.attribute(cs, r))
            heat = {k: v for k, v in at.items() if k not in ("bay_air", "fet_tie", "mesh_corr")}
            rise_total = r["est_c"] - cs["bay"]
            out.append({"item": r["item"], "short": short(r["item"]), "est_c": r["est_c"], "limit_c": r["limit_c"],
                        "margin_k": r["limit_c"] - r["est_c"], "bay_c": cs["bay"], "loc25": list(map(str, r["loc25"])),
                        "terms_k": at, "sum_check_k": sum(at.values()) - r["est_c"],
                        "heat_total_k": sum(heat.values()), "bay_plus_tie_k": at["bay_air"] + at["fet_tie"],
                        "rise_over_bay_k": rise_total})
        res["attribution"][c] = out

    # ---------------- ceilings (direct, synthesized gate case, every gated row)
    ceil = {}
    for bay in (61.0, 55.0):
        cval, row = b.ceiling(bay)
        ceil[f"bay{bay:g}"] = {"ceiling_a": round(cval, 2), "binding_row": row}
    # I_trip^2 control (ceilings.py method on synthesized c22 / c28 at bay 61, as DECISIONS 56)
    m22 = b.case(22.0, 61.0)
    m28 = b.case(28.0, 61.0)
    ctl = {}
    i22, i28 = 1.05 * 22.0, 1.05 * 28.0
    best = None
    rows28 = {short(r["item"]): r for r in m28["rows"] if r["gated"]}
    for r in m22["rows"]:
        if not r["gated"]:
            continue
        s28 = rows28[short(r["item"])]
        ma, mb = r["limit_c"] - r["est_c"], s28["limit_c"] - s28["est_c"]
        slope = (mb - ma) / (i28 ** 2 - i22 ** 2)
        if slope >= 0:
            continue
        x = i22 ** 2 - ma / slope
        cv = 0.0 if x <= 0 else math.sqrt(x) / 1.05
        if best is None or cv < best[0]:
            best = (cv, short(r["item"]))
    ceil["bay61 I_trip^2 method (c22/c28 synthesized at bay 61; ceilings.py)"] = {"ceiling_a": round(best[0], 2),
                                                                                  "binding_row": best[1]}
    res["ceilings"] = ceil

    # ---------------- levers: K per 10 % cut at the binding rows, ceiling per cut
    binding = ["C40 body", "R10 terminal derating", "laminate 1 mm block"]
    base = syn["c18_h10"]

    def row_by(cs, sh):
        return next(r for r in cs["rows"] if short(r["item"]) == sh)

    cands = set()
    for sh in binding:
        r = row_by(base, sh)
        at = b.attribute(base, r)
        top = sorted((k for k in at if k.startswith(("a4:", "part:"))), key=lambda k: -at[k])[:6]
        cands.update(top)
    cands = sorted(cands)
    lev = {}
    c61 = ceil["bay61"]["ceiling_a"]
    for t in cands:
        e = {"label": label(t), **term_info(b, t), "watts_c18": b.watts(base["coefs"])[t]}
        cut = b.case(18.0, 61.0, {t: 0.9})
        e["dK_per_10pct_c18"] = {}
        for sh2 in binding + ["C41 body", "R20 terminal derating", "laminate FET row", "C38 body"]:
            r0 = row_by(base, sh2)
            r1 = row_by(cut, sh2)
            e["dK_per_10pct_c18"][sh2] = r0["est_c"] - r1["est_c"]
            e.setdefault("K_per_W_c18", {})[sh2] = b.attribute(base, r0)[t] / e["watts_c18"] if e["watts_c18"] else None
        cv, row = b.ceiling(61.0, {t: 0.9})
        e["ceiling_bay61_cut10"] = {"ceiling_a": round(cv, 2), "gain_a": round(cv - c61, 2), "binding_row": row}
        lev[t] = e
    res["levers_10pct"] = lev

    # combined / plausible changes (stated assumptions, see README)
    scen = {
        "R_on 0.217 -> 0.17 W (bench IR at the simulated value, DECISIONS 56)": {"part:R_on": 0.17 / 0.217},
        "sw_b copper -20 % (both states)": {"a4:sw_b_high-p00625-pl18": 0.8, "a4:sw_b_low-p00625-pl18": 0.8},
        "sw_a copper -20 % (both states)": {"a4:sw_a-p00625-pl18": 0.8, "a4:sw_a_low-p00625-pl18": 0.8},
        "hv_ret copper -20 % (hv_mixed a/b)": {"a4:hv_mixed_a-p00625-pl18": 0.8, "a4:hv_mixed_b-p00625-pl18": 0.8},
        "leg_ret copper -20 % (leg a/b)": {"a4:leg_a_18p7-p00625-pl18": 0.8, "a4:leg_b_18p7-p00625-pl18": 0.8},
        "bus_p copper -20 % (bus_mixed q2/q5)": {"a4:bus_mixed_q2-p0125-pl18": 0.8, "a4:bus_mixed_q5-p0125-pl18": 0.8},
        "all tank copper -20 % (every tank-scaled A4 field)": {t: 0.8 for t in b.terms if t.startswith("a4:")
                                                              and not t.startswith("a4:ac_")},
        "HF film self-heat 0 (C38-C41 rows 0.05 -> 0 W)": {"part:HF_film": 0.0},
        "RECOM U41/U42 -20 %": {"part:RECOM": 0.8},
        "U26 -20 %": {"part:U26": 0.8},
        "drivers U1/U2 -20 %": {"part:drivers": 0.8},
        "R_off -20 %": {"part:R_off": 0.8},
        "bank ESR -20 %": {"part:bank": 0.8},
        "R5 0.5 mOhm (row x0.5)": {"part:R5": 0.5},
        "sw_b copper -10 % (both states)": {"a4:sw_b_high-p00625-pl18": 0.9, "a4:sw_b_low-p00625-pl18": 0.9},
        "HF film self-heat halved (0.05 -> 0.025 W each)": {"part:HF_film": 0.5},
        "fan sink setpoint 88.6 -> 83.6 C (firmware FAN_SINK_SETPOINT_C)": ("setpoint", 83.6),
        "fan sink setpoint 88.6 -> 78.6 C": ("setpoint", 78.6),
        "R_on 0.17 W + sw_b -20 %": {"part:R_on": 0.17 / 0.217, "a4:sw_b_high-p00625-pl18": 0.8,
                                      "a4:sw_b_low-p00625-pl18": 0.8},
    }
    out = {}
    for name, sc in scen.items():
        if isinstance(sc, tuple):                    # fet_case.t_case reads the module global at call time
            orig = b.fc.FAN_SINK_SETPOINT_C
            b.fc.FAN_SINK_SETPOINT_C = sc[1]
            try:
                c61s, row61 = b.ceiling(61.0)
                c55s, row55 = b.ceiling(55.0)
            finally:
                b.fc.FAN_SINK_SETPOINT_C = orig
        else:
            c61s, row61 = b.ceiling(61.0, sc)
            c55s, row55 = b.ceiling(55.0, sc)
        out[name] = {"bay61": {"ceiling_a": round(c61s, 2), "gain_a": round(c61s - c61, 2), "binding_row": row61},
                     "bay55": {"ceiling_a": round(c55s, 2), "gain_a": round(c55s - ceil["bay55"]["ceiling_a"], 2),
                               "binding_row": row55}}
    res["scenarios"] = out

    # ---------------- per-row ceilings at bay 61 / 55 (how many rows stand behind the binding one)
    per = {}
    gated_rows = sorted({short(r["item"]) for r in base["rows"] if r["gated"]})
    for bay in (61.0, 55.0):
        d = {}
        for sh in gated_rows:
            cv, _ = b.ceiling(bay, None, pick=lambda r, _s=sh: short(r["item"]) == _s, hi=40.0)
            d[sh] = round(cv, 2)
        per[f"bay{bay:g}"] = dict(sorted(d.items(), key=lambda kv: kv[1]))
    res["per_row_ceilings"] = per

    # ---------------- bay sensitivity: d est / d bay per row (1 - the tie's unit response) and ceiling per K of bay
    sens = {}
    b1 = b.case(18.0, 62.0)
    for sh in ("C40 body", "R10 terminal derating", "C41 body", "R20 terminal derating", "laminate 1 mm block",
               "laminate FET row", "U26 Tj", "U42 Tj"):
        r = row_by(base, sh)
        r1 = row_by(b1, sh)                      # exact: the case re-synthesized at bay + 1 K (mesh term included)
        sens[sh] = {"dest_dbay_K_per_K": r1["est_c"] - r["est_c"]}
    sens["ceiling_A_per_K_bay (61 -> 55)"] = (ceil["bay55"]["ceiling_a"] - ceil["bay61"]["ceiling_a"]) / 6.0
    tc18, tc22 = b.fc.t_case(18.0, i_line=b.rb.I_LINE_A), b.fc.t_case(22.0, i_line=b.rb.I_LINE_A)
    sens["t_case_c18_C"] = {k: round(v, 2) for k, v in tc18.items()}
    sens["t_case_c22_C"] = {k: round(v, 2) for k, v in tc22.items()}
    res["bay_sensitivity"] = sens

    # ---------------- c22 / bay 55: dK per 10 % cut at its failing rows (the ranking at a raised ceiling)
    c22 = syn["c22_h10"]
    lev22 = {}
    for t in sorted(set(cands) | {"a4:hv_mixed_a-p00625-pl18", "a4:hv_mixed_b-p00625-pl18", "a4:bus_mixed_q5-p0125-pl18"}):
        cut = b.case(22.0, 55.0, {t: 0.9})
        lev22[t] = {"label": label(t), "watts_c22": b.watts(c22["coefs"])[t],
                    "dK_per_10pct": {sh: row_by(c22, sh)["est_c"] - row_by(cut, sh)["est_c"]
                                     for sh in ("C40 body", "laminate 1 mm block", "R12 terminal derating",
                                                "R10 terminal derating", "laminate FET row", "C38 body")}}
    res["levers_10pct_c22"] = lev22

    # ---------------- sensitivity outside the model: copper TCR (A4 fields are 20 C copper, DC; ../outputs/*.json
    # "assumptions"). First order: each tank field's loss x (1 + ALPHA (T_w - 20)), T_w = its heat-weighted copper
    # temperature on the c18 field (bay + rise at 0.25 mm). One Picard step, no feedback: a lower bound on the effect.
    ALPHA = 0.00393                                     # 1/K, annealed copper at 20 C (IACS handbook value)
    m = b.meta[0.25]
    cu18, _ = base["fields"][0.25]
    zs = [b.br.T.CU_INDEX[n] for n in LAYERS]
    tcr = {}
    for t in b.terms:
        if not t.startswith("a4:") or t.startswith("a4:ac_"):
            continue
        heat = np.zeros((len(b.br.T.LAYER_NAMES),) + m["board"].shape)
        b.br.T.remap_a4(t[3:], m["x"], m["y"], m["board"], heat, 1.0)
        h4 = heat[zs]
        tw = 61.0 + float((h4 * cu18).sum() / h4.sum())
        tcr[t] = {"T_w_C": round(tw, 1), "scale": 1.0 + ALPHA * (tw - 20.0)}
    sc = {t: v["scale"] for t, v in tcr.items()}
    cut = b.case(18.0, 61.0, sc)
    rows_t = {}
    for sh in ("C40 body", "R10 terminal derating", "laminate 1 mm block", "C41 body", "R20 terminal derating"):
        rows_t[sh] = row_by(cut, sh)["est_c"] - row_by(base, sh)["est_c"]
    cv, row = b.ceiling(61.0, sc)
    res["copper_tcr_first_order"] = {"alpha_per_K": ALPHA, "fields": tcr, "dK_c18_bay61": rows_t,
                                     "ceiling_bay61": {"ceiling_a": round(cv, 2), "gain_a": round(cv - c61, 2),
                                                       "binding_row": row}}

    # ---------------- local copper deposit by layer near the binding rows (pointer for which layer to widen)
    near = {}
    for sh in ("C40 body", "R10 terminal derating", "laminate 1 mm block"):
        r = next(r for r in base["rows"] if short(r["item"]) == sh)
        loc = r["loc25"]
        x, y, s = base["met"][0.25]["_xy"]
        if loc[0] == "tj":
            ref = loc[1]
            xc, yc = b.heat18[ref]["x_mm"], b.heat18[ref]["y_mm"]
        elif loc[0] == "cell":
            xc, yc = float(x[loc[2]]), float(y[loc[3]])
        else:
            xc, yc = float(x[loc[2] * s] - 0.125 + 0.5), float(y[loc[3] * s] - 0.125 + 0.5)
        dd = {"xy_mm": [round(xc, 2), round(yc, 2)], "loc_layer": LAYERS[loc[1]] if loc[0] != "tj" else "junction"}
        for t in b.terms:
            if not t.startswith("a4:"):
                continue
            n = t[3:]
            arr = np.load(b.br.T.A4 / f"{n}-heat.npz")
            k = base["coefs"][t]
            per = {}
            for L in LAYERS:
                pre = L.replace(".", "_")
                if pre + "_joule_w" not in arr:
                    continue
                src = arr[pre + "_joule_w"]
                X, Y = np.meshgrid(arr[pre + "_x_mm"], arr[pre + "_y_mm"], indexing="ij")
                m = (X - xc) ** 2 + (Y - yc) ** 2 <= 5.0 ** 2
                per[L] = float(k * src[m].sum())
            if sum(per.values()) > 0.005:
                dd[label(t)] = {L: round(v, 4) for L, v in per.items()}
        near[sh] = dd
    res["copper_within_5mm_W"] = near

    (HERE / "results.json").write_text(json.dumps(res, indent=1, default=str) + "\n")
    write_tables(b, res)
    print(json.dumps(res["checks"], indent=1))
    print(json.dumps(res["ceilings"], indent=1))


def write_tables(b, res):
    L = []
    L.append("## Checks\n")
    L.append("| check | value |\n|---|---|")
    for k, v in res["checks"].items():
        L.append(f"| {k} | {v:.2e} |" if isinstance(v, float) else f"| {k} | {v} |")
    for c, rows in res["attribution"].items():
        bay = rows[0]["bay_c"]
        L.append(f"\n## Attribution {c} (bay {bay:g} C): every gated row\n")
        L.append("K at the row, 0.25 mm locator. 'bay+tie' = bay air + FET-case tie; 'heat' = all heat terms; "
                 "'mesh' = 3|Q(0.25)-Q(0.5)|. Top 5 heat terms with K and share of the rise over bay.\n")
        L.append("| row | est C | limit C | margin K | bay+tie (tie) | heat K | mesh K | top heat terms (K, share of rise over bay) |")
        L.append("|---|---|---|---|---|---|---|---|")
        for r in rows:
            t = r["terms_k"]
            heat = {k: v for k, v in t.items() if k.startswith(("a4:", "part:"))}
            top = sorted(heat, key=lambda k: -heat[k])[:5]
            rise = r["rise_over_bay_k"]
            tops = "; ".join(f"{label(k)} {heat[k]:.1f} ({100 * heat[k] / rise:.0f} %)" for k in top)
            L.append(f"| {r['short']} | {r['est_c']:.1f} | {r['limit_c']:.1f} | {r['margin_k']:+.1f} | "
                     f"{r['bay_plus_tie_k']:.1f} ({t['fet_tie']:+.1f}) | {r['heat_total_k']:.1f} | {t['mesh_corr']:.1f} | {tops} |")
    # full per-term table for the binding rows
    for c, rows in res["attribution"].items():
        pick = [r for r in rows if r["short"] in ("C40 body", "C38 body", "C41 body", "R10 terminal derating",
                                                  "R12 terminal derating", "R20 terminal derating",
                                                  "laminate 1 mm block", "laminate FET row", "U26 Tj", "U42 Tj",
                                                  "U41 Tj", "R5 element", "R5 terminal derating", "R10 element")]
        L.append(f"\n## Full term breakdown, {c} (K at the row)\n")
        terms = [k for k in pick[0]["terms_k"]]
        L.append("| term | group | scales | " + " | ".join(r["short"] for r in pick) + " |")
        L.append("|---|---|---|" + "---|" * len(pick))
        order = ["bay_air", "fet_tie"] + sorted([k for k in terms if k.startswith("a4:")]) + \
            [f"part:{g}" for g in st.PART_GROUPS] + ["mesh_corr"]
        for k in order:
            info = res["terms"].get(k, {"group": "-", "scales": "-"}) if k != "fet_tie" else \
                {"group": "G03 (sink)", "scales": "t_case - bay"}
            L.append(f"| {label(k)} | {info['group']} | {info['scales']} | " +
                     " | ".join(f"{r['terms_k'][k]:.2f}" for r in pick) + " |")
        L.append("| **sum = est** | | | " + " | ".join(f"**{sum(r['terms_k'].values()):.2f}**" for r in pick) + " |")
    # roll-ups: by kind of change and by coupling-study group
    for c, rows in res["attribution"].items():
        pick = [r for r in rows if r["short"] in ("C40 body", "R10 terminal derating", "C41 body", "R20 terminal derating",
                                                  "C38 body", "laminate 1 mm block", "R12 terminal derating",
                                                  "laminate FET row", "U26 Tj", "U42 Tj")]
        kinds, groups = {}, {}
        for r in pick:
            for k, v in r["terms_k"].items():
                if k in ("bay_air", "mesh_corr"):
                    kk, gg = k, k
                elif k == "fet_tie":
                    kk, gg = "FET-case tie (sink)", "G03 (sink tie)"
                else:
                    ti = res["terms"][k]
                    kk = ("copper loss, " if ti["kind"].startswith("copper") else "part heat, ") + ti["scales"]
                    gg = ti["group"]
                kinds.setdefault(kk, {})[r["short"]] = kinds.get(kk, {}).get(r["short"], 0.0) + v
                groups.setdefault(gg, {})[r["short"]] = groups.get(gg, {}).get(r["short"], 0.0) + v
        for title, d in (("kind of change", kinds), ("group (G01-G10)", groups)):
            L.append(f"\n## {c}: K at the row by {title}\n")
            L.append("| | " + " | ".join(r["short"] for r in pick) + " |\n|---|" + "---|" * len(pick))
            for k in sorted(d, key=lambda k: -sum(d[k].values())):
                L.append(f"| {k} | " + " | ".join(f"{d[k].get(r['short'], 0.0):.1f}" for r in pick) + " |")
    L.append("\n## Ceilings (synthesized gate case, every gated row)\n")
    for k, v in res["ceilings"].items():
        L.append(f"- {k}: {v['ceiling_a']} A ({v['binding_row']})")
    L.append("\n## Levers: one term cut 10 %, c18 / bay 61\n")
    L.append("| term | kind | group | scales | W at c18 | dK C40 | dK R10 term. | dK lam. block | K/W at C40 | K/W at R10 | ceiling bay 61 (gain) | binding after |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for t, e in sorted(res["levers_10pct"].items(), key=lambda kv: -kv[1]["ceiling_bay61_cut10"]["gain_a"]):
        d = e["dK_per_10pct_c18"]
        kw = e["K_per_W_c18"]
        L.append(f"| {e['label']} | {e['kind']} | {e['group']} | {e['scales']} | {e['watts_c18']:.3f} | "
                 f"{d['C40 body']:.2f} | {d['R10 terminal derating']:.2f} | {d['laminate 1 mm block']:.2f} | "
                 f"{kw['C40 body']:.1f} | {kw['R10 terminal derating']:.1f} | "
                 f"{e['ceiling_bay61_cut10']['ceiling_a']} ({e['ceiling_bay61_cut10']['gain_a']:+.2f}) | "
                 f"{short(e['ceiling_bay61_cut10']['binding_row'] or '-')} |")
    L.append("\n## Scenarios (stated cuts), ceilings\n")
    L.append("| change | ceiling bay 61 (gain) | binding | ceiling bay 55 (gain) | binding |")
    L.append("|---|---|---|---|---|")
    for k, v in res["scenarios"].items():
        L.append(f"| {k} | {v['bay61']['ceiling_a']} ({v['bay61']['gain_a']:+.2f}) | {short(v['bay61']['binding_row'] or '-')} | "
                 f"{v['bay55']['ceiling_a']} ({v['bay55']['gain_a']:+.2f}) | {short(v['bay55']['binding_row'] or '-')} |")
    L.append("\n## Per-row ceilings (each gated row alone; A)\n")
    L.append("| row | bay 61 | bay 55 |\n|---|---|---|")
    for sh, v in res["per_row_ceilings"]["bay61"].items():
        L.append(f"| {sh} | {v} | {res['per_row_ceilings']['bay55'][sh]} |")
    L.append("\n## Bay sensitivity (c18)\n")
    for k, v in res["bay_sensitivity"].items():
        L.append(f"- {k}: {v if not isinstance(v, dict) else json.dumps(v)}")
    L.append("\n## Levers at c22 / bay 55: K gained per 10 % cut of one term\n")
    hdr = ("C40 body", "laminate 1 mm block", "R12 terminal derating", "R10 terminal derating", "laminate FET row", "C38 body")
    L.append("| term | W at c22 | " + " | ".join(hdr) + " |\n|---|---|" + "---|" * len(hdr))
    for t, e in sorted(res["levers_10pct_c22"].items(), key=lambda kv: -kv[1]["dK_per_10pct"]["C40 body"]):
        L.append(f"| {e['label']} | {e['watts_c22']:.3f} | " + " | ".join(f"{e['dK_per_10pct'][h]:.2f}" for h in hdr) + " |")
    tc = res["copper_tcr_first_order"]
    L.append("\n## Outside the model: copper TCR, first order (c18 / bay 61)\n")
    L.append("- heat-weighted copper temperature and loss scale per field: " + "; ".join(
        f"{label(k)} {v['T_w_C']} C x{v['scale']:.2f}" for k, v in tc["fields"].items()))
    L.append("- added K at the row: " + "; ".join(f"{k} +{v:.1f}" for k, v in tc["dK_c18_bay61"].items()))
    L.append(f"- ceiling bay 61: {tc['ceiling_bay61']['ceiling_a']} A ({tc['ceiling_bay61']['gain_a']:+.2f}), "
             f"{short(tc['ceiling_bay61']['binding_row'] or '-')}")
    L.append("\n## Tank copper deposited within 5 mm of the binding rows (W, c18, by layer)\n")
    for sh, d in res["copper_within_5mm_W"].items():
        L.append(f"- **{sh}** at {d['xy_mm']} ({d['loc_layer']}): " + "; ".join(
            f"{k} " + "/".join(f"{L_[0:3]} {v:.3f}" for L_, v in vv.items() if v > 0.0005)
            for k, vv in d.items() if isinstance(vv, dict)))
    (HERE / "tables.md").write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    main()
