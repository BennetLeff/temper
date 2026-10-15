#!/usr/bin/env python3
"""Exact superposition of body-model solves that share one matrix (same pitch, same parts present, same lead G).

The 2.5-D model is linear in its sources: the A4 copper rows, each part's watts and the lead tie temperature t_rise
enter only the right-hand side. From c28-basis component solves with saved fields (solve.py save_field):
    F0    reference (A4 tank rows x1, tank-current part rows x1, t_rise t0 = T_case(c28) - 55)
    Fa    A4 tank rows x0.5                     -> dA  = 2 (F0 - Fa)        per unit A4 tank factor
    Fr    R5 x0.5                               -> dR  = 2 (F0 - Fr)        per unit R5 factor
    Fp    all tank-current part rows x0.5       -> dP  = 2 (F0 - Fp) - dR   per unit factor, R5 excluded
    Fb    t_rise t0 - 6 (bay 61)                -> dt  = (F0 - Fb) / 6      per K of lead tie temperature
    T(A, P, R, t) = F0 + (A-1) dA + (P-1) dP + (P R - 1) dR + (t - t0) dt
for fields, part junctions and the energy receipt. A ceiling c is A = P = k = (1.05 c / 29.4)^2 (the run_basis / solve.py
construction: every A4 row but the line rows and every body_runs.TANK_ROWS part scale with I_t^2), t = T_case(c) - bay.
Metrics are recomputed from the combined field with body_runs.report_entries / pad_stats and a copy of run_case's
1 mm-block and FET-row code, then written as ordinary run JSONs so evaluate.py / the committed gate read them.
Validation (validate()): F0's own metrics reproduce its JSON, and the superposed c22 reproduces the direct c22 solve.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CACHE, MOD_CONV, PITCHES, RUNS  # noqa: E402

sys.path.insert(0, str(MOD_CONV))
import body_runs as br  # noqa: E402
import thermal_body as tb  # noqa: E402

T = tb.T
SYN = RUNS / "syn"
_BRD = {}


def board():
    if "b" not in _BRD:
        _BRD["b"] = tb.Board(br.rs.GEOM, CACHE)
    return _BRD["b"]


def tag(p):
    return f"p{str(p).replace('.', 'p')}"


def load(config, case, pitch):
    f = RUNS / config / f"{case}_{tag(pitch)}.json"
    j = json.loads(f.read_text())
    z = np.load(f.with_suffix(".npz"))
    assert str(z["job_key"]) == j["job_key"], f
    return j, z["rise"]


def metrics(rise, pitch):
    """1 mm-block peak and FET-row max, exactly as body_runs.run_case (global solve)."""
    brd = board()
    nx, ny = brd.grid_n(pitch)
    x = brd.xmin + (np.arange(0, nx) + 0.5) * pitch
    y = brd.ymin + (np.arange(0, ny) + 0.5) * pitch
    if ("wa", pitch) not in _BRD:
        _BRD[("wa", pitch)] = brd.window_arrays(pitch, 0, nx, 0, ny)
    bmask, cfrac = _BRD[("wa", pitch)]
    sblk = max(int(round(1.0 / pitch)), 1)
    b1 = None
    for layer, z in T.CU_INDEX.items():
        nb_x, nb_y = nx // sblk, ny // sblk
        r_ = rise[z][:nb_x * sblk, :nb_y * sblk].reshape(nb_x, sblk, nb_y, sblk)
        m_ = bmask[:nb_x * sblk, :nb_y * sblk].reshape(nb_x, sblk, nb_y, sblk).all(axis=(1, 3))
        cf = cfrac[layer][:nb_x * sblk, :nb_y * sblk].reshape(nb_x, sblk, nb_y, sblk).mean(axis=(1, 3))
        mean_ = np.where(m_ & (cf > 0.05), r_.mean(axis=(1, 3)), -np.inf)
        if np.isfinite(mean_).any():
            ia, ja = np.unravel_index(np.argmax(mean_), mean_.shape)
            cand = {"temperature_c": tb.TAMB_C + float(mean_[ia, ja]), "layer": layer,
                    "x_mm": float(x[ia * sblk] - pitch / 2 + 0.5), "y_mm": float(y[ja * sblk] - pitch / 2 + 0.5)}
            if b1 is None or cand["temperature_c"] > b1["temperature_c"]:
                b1 = cand
    fet_sel = np.ix_(x <= 80, y <= 12.5)
    fet_row = tb.TAMB_C + float(max(rise[z][fet_sel].max() for z in T.CU_INDEX.values()))
    return b1, fet_row


def part_pad_max(rise, ref, pad_numbers, pitch):
    brd = board()
    nx, ny = brd.grid_n(pitch)
    key = ("re", ref, pitch)
    if key not in _BRD:
        _BRD[key] = br.report_entries(brd, ref, pad_numbers, pitch, 0, 0, nx, ny)
    layer, ent = _BRD[key]
    st = br.pad_stats(rise[T.CU_INDEX[layer]], ent, pitch)
    return tb.TAMB_C + st["max_cell_k"], tb.TAMB_C + st["mean_k"]


class Basis:
    """Components for one pitch on one model (heat file + lead G)."""

    def __init__(self, pitch, f0, fa, fr, fp, fb, dt_bay=6.0, fq=None):
        self.pitch = pitch
        (self.j0, self.r0), (ja, ra), (jr, rr), (jp, rp), (jb, rb) = (load(*c, pitch) for c in (f0, fa, fr, fp, fb))
        assert ja["job"]["tank_factor"] == 0.5 and jr["job"]["part_scale"] == {"R5": 0.5}
        assert jp["job"]["part_scale"].get("R5") == 0.5 and len(jp["job"]["part_scale"]) == 9
        assert abs((self.j0["job"]["leads"]["bay_c"] - jb["job"]["leads"]["bay_c"]) + dt_bay) < 1e-9
        for j in (ja, jr, jp, jb):
            assert j["job"]["leads"]["g"] == self.j0["job"]["leads"]["g"] and j["job"]["heat"] == self.j0["job"]["heat"]
        self.t0 = self.j0["job"]["leads"]["t_case_c"]["Q3"] - self.j0["job"]["leads"]["bay_c"]
        self.comp = {}
        for name, (j, r) in {"a": (ja, ra), "r": (jr, rr), "p": (jp, rp), "b": (jb, rb)}.items():
            self.comp[name] = (j, r)
        self.dA = 2 * (self.r0 - ra)
        self.dR = 2 * (self.r0 - rr)
        self.dP = 2 * (self.r0 - rp) - self.dR
        self.dt = (self.r0 - rb) / dt_bay
        self.parts0 = {p["ref"]: p for p in self.j0["parts"]}

        def dj(jx, fac):
            return {p["ref"]: fac * (self.parts0[p["ref"]]["tj_c"] - p["tj_c"]) for p in jx["parts"] if "tj_c" in p}
        self.tA, self.tR = dj(ja, 2.0), dj(jr, 2.0)
        tp = dj(jp, 2.0)
        self.tP = {k: tp[k] - self.tR[k] for k in tp}
        self.tT = dj(jb, 1.0 / dt_bay)

        def db(jx, fac):
            return {k: fac * (self.j0["balance"][k] - jx["balance"][k]) for k in ("source_w", "convection_w", "body_air_w", "lead_sink_w")}
        self.bA, self.bR = db(ja, 2.0), db(jr, 2.0)
        bp = db(jp, 2.0)
        self.bP = {k: bp[k] - self.bR[k] for k in bp}
        self.bT = db(jb, 1.0 / dt_bay)
        self.heat = {p["ref"]: p for p in json.loads(Path(self.j0["job"]["heat"]).read_text())["parts"]}
        self.dQ = None
        if fq is not None:      # heat-basis component: (datasheet-Q heat file) - (reference heat file), same factors / t
            jq, rq = load(*fq, pitch)
            assert jq["job"]["leads"] == self.j0["job"]["leads"] and jq["job"]["tank_factor"] == 1.0 and not jq["job"]["part_scale"]
            self.dQ = rq - self.r0
            self.tQ = {p["ref"]: p["tj_c"] - self.parts0[p["ref"]]["tj_c"] for p in jq["parts"] if "tj_c" in p}
            self.wQ = {p["ref"]: p["watts_into_model"] for p in jq["parts"]}
            self.bQ = {k: jq["balance"][k] - self.j0["balance"][k] for k in ("source_w", "convection_w", "body_air_w", "lead_sink_w")}

    def combine(self, A, P, R, t, q=0.0):
        """q = 1 swaps the frequency-set / gate rows to the datasheet-Q heat file (exact: those rows do not scale)."""
        cA, cP, cR, cT = A - 1.0, P - 1.0, P * R - 1.0, t - self.t0
        rise = self.r0 + cA * self.dA + cP * self.dP + cR * self.dR + cT * self.dt
        if q:
            rise = rise + q * self.dQ
        b1, fet_row = metrics(rise, self.pitch)
        parts = []
        for p0 in self.j0["parts"]:
            p = dict(p0)
            ref = p["ref"]
            if "tj_c" in p:
                p["tj_c"] = p0["tj_c"] + cA * self.tA[ref] + cP * self.tP[ref] + cR * self.tR[ref] + cT * self.tT[ref] + (q * self.tQ[ref] if q else 0.0)
            p["pad_max_cell_c"], p["pad_mean_c"] = part_pad_max(rise, ref, self.heat[ref].get("pad_numbers"), self.pitch)
            if ref in br.TANK_ROWS:
                p["watts_into_model"] = p0["watts_into_model"] * (P * R if ref == "R5" else P)
            elif q:
                p["watts_into_model"] = p0["watts_into_model"] + q * (self.wQ[ref] - p0["watts_into_model"])
            parts.append(p)
        bal = {k: self.j0["balance"][k] + cA * self.bA[k] + cP * self.bP[k] + cR * self.bR[k] + cT * self.bT[k]
               + (q * self.bQ[k] if q else 0.0) for k in ("source_w", "convection_w", "body_air_w", "lead_sink_w")}
        bal["balance_rel"] = (bal["source_w"] - bal["convection_w"] - bal["body_air_w"] - bal["lead_sink_w"]) / bal["source_w"]
        out = {"peak_1mm_block": b1, "fet_row_max_c": fet_row, "parts": parts, "balance": bal,
               "board_sha256": self.j0["board_sha256"], "superposition": {"A": A, "P": P, "R": R, "t_rise": t, "basis": self.j0["job"]["config"]},
               "leads": [{"ref": "Q*", "t_case_c": tb.TAMB_C + t, "g_w_per_k": self.j0["job"]["leads"]["g"]}]}
        return out, rise


def bases(prefix_f0="HL_central_b55", prefix_fb="HL_central_b61", dsq="HLdsqF_central_b55"):
    use_q = all((RUNS / dsq / f"c28_h10_{tag(p)}.npz").exists() for p in PITCHES)
    return {p: Basis(p, (prefix_f0, "c28_h10"), ("SP_a4tank_half", "c28_h10"), ("SP_r5_half", "c28_h10"),
                     ("SP_tankparts_half", "c28_h10"), (prefix_fb, "c28_h10"), fq=(dsq, "c28_h10") if use_q else None)
            for p in PITCHES}


def k_of(ceil):
    return 1.0 if ceil == 28.0 else (1.05 * ceil / 29.4) ** 2


def write(name, case, per_pitch):
    d = SYN / name
    d.mkdir(parents=True, exist_ok=True)
    for p, j in per_pitch.items():
        (d / f"{case}_{tag(p)}.json").write_text(json.dumps(j, indent=1) + "\n")
    return d


def validate(B):
    """S1: F0 metrics recomputed from its own field = its JSON; S2: superposed c22 = direct c22 (HL_central_b55)."""
    import sink_model
    worst1, worst2 = 0.0, 0.0
    for p, b in B.items():
        j, r = b.combine(1.0, 1.0, 1.0, b.t0)
        d = [abs(j["peak_1mm_block"]["temperature_c"] - b.j0["peak_1mm_block"]["temperature_c"]), abs(j["fet_row_max_c"] - b.j0["fet_row_max_c"])]
        d += [abs(x["pad_max_cell_c"] - y["pad_max_cell_c"]) for x, y in zip(j["parts"], b.j0["parts"])]
        worst1 = max(worst1, max(d))
        k = k_of(22.0)
        t22 = sink_model.t_case(22.0, "central")[0]["Q3"] - 55.0
        js, _ = b.combine(k, k, 1.0, t22)
        jd = json.loads((RUNS / "HL_central_b55" / f"c22_h10_{tag(p)}.json").read_text())
        d = [abs(js["peak_1mm_block"]["temperature_c"] - jd["peak_1mm_block"]["temperature_c"]), abs(js["fet_row_max_c"] - jd["fet_row_max_c"])]
        for x, y in zip(js["parts"], jd["parts"]):
            assert x["ref"] == y["ref"]
            d.append(abs(x["pad_max_cell_c"] - y["pad_max_cell_c"]))
            if "tj_c" in x:
                d.append(abs(x["tj_c"] - y["tj_c"]))
            d.append(abs(x["watts_into_model"] - y["watts_into_model"]))
        worst2 = max(worst2, max(d))
    return {"S1_self_reproduction_max_K": worst1, "S2_c22_superposed_vs_direct_max_K": worst2,
            "pass": worst1 < 1e-9 and worst2 < 2e-3,
            "note": "S2 tolerance 2e-3 K: run_study.cases() and solve.py round each A4 scale factor to 6 significant digits"}


if __name__ == "__main__":
    print(validate(bases()))
