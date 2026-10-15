#!/usr/bin/env python3 -I
"""EMI evaluation over the s19b model's full compliance set, for arbitrary filter candidates.

Loads repo_copies/emi_s19b.py (a byte-identical copy of the committed
zapote/power-stage-120v/validation-results/07-conducted-emi/s19b/emi_s19b.py, sha256 in MANIFEST.json) as a module,
points its data paths at the read-only repo, and never calls its main() (so nothing is written anywhere).

Compliance set = exactly the scenarios s19b's verdict uses (emi_s19b.py main(): 'nominal' + every scenario not in the
excluded prefixes).  Nominal: 6 configs (170/198 V x pan_22A/pan_28A/nopan_22A; nopan_28A fault excluded), fs 35-60 kHz
step 0.5 kHz.  Sensitivities: 3 configs (170 V pan_22A, 198 V pan_28A, 198 V nopan_22A), step 1 kHz.
For a candidate, each sensitivity is applied to the candidate's own part values the same way s19b applies it to the
nominal (relative: Y -20 %, X -20 %, chokes -30 %, winding C x2, DM L x31/41; absolute: geometry, coil, ESL, PE bond,
edges).  For the s19b nominal these reproduce s19b's absolute numbers exactly (control in run_all.py).
"""
from __future__ import annotations

import os

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import importlib.util
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REPO_PS = Path(__file__).resolve().parents[4]   # zapote/power-stage-120v (committed copy, DECISIONS 47)
S19B_DIR = REPO_PS / "validation-results/07-conducted-emi/s19b"


def _load():
    spec = importlib.util.spec_from_file_location("emi_s19b_copy", HERE / "repo_copies/emi_s19b.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["emi_s19b_copy"] = m
    spec.loader.exec_module(m)
    m.D22 = REPO_PS / "validation-results/01-switching-parasitics/round17/delegation/out-D22"
    m.R3 = REPO_PS / "validation-results/07-conducted-emi/round3/outputs"
    m.COPPER = Path("/nonexistent")                      # force the committed reduced copper summary (read-only)
    m.COPPER_FALLBACK = S19B_DIR / "inputs/copper-dump-s19b-summary.json"
    m.HERE = HERE / "results"                            # any accidental write lands here, never in the repo
    _patch_rin(m)
    return m


def _patch_rin(m):
    """Optional tank variant (param RIN=True), for checking temper-8d's claim (sensor-c1-impulse-mining:
    output/temper-coil-driver-r1/emi_split_cap.py, variant RIN): the pan-reflected R is inside the winding
    (R/2 + L + R/2) and the coil-end capacitances hang on the coil's physical terminals (SW_A and the coil/bank node).
    With RIN absent/False the patched build() is the committed one (control: E00 must still reproduce s19b exactly)."""
    import inspect
    src = inspect.getsource(m.build)
    old = ('    n.R("sw_a", "tank_a", p["RPAN"])\n    n.L("Lcoil", "tank_a", "tank_b", p["LCOIL"])\n'
           '    n.C("tank_b", "sw_b", p["CRES"])\n')
    assert old in src, "tank block changed in the copy"
    new = ('    if p.get("RIN"):\n'
           '        n.R("sw_a", "tank_a", 1e-6)\n'
           '        n.R("tank_a", "coil_1", p["RPAN"] / 2)\n'
           '        n.L("Lcoil", "coil_1", "coil_2", p["LCOIL"])\n'
           '        n.R("coil_2", "tank_b", p["RPAN"] / 2)\n'
           '        n.C("tank_b", "sw_b", p["CRES"])\n'
           '    else:\n'
           '        n.R("sw_a", "tank_a", p["RPAN"])\n'
           '        n.L("Lcoil", "tank_a", "tank_b", p["LCOIL"])\n'
           '        n.C("tank_b", "sw_b", p["CRES"])\n')
    exec(compile(src.replace(old, new), "emi_s19b_copy.build(RIN-patched)", "exec"), m.__dict__)


m = _load()
import numpy as np  # noqa: E402

ALL6 = [(vc, cn) for vc in (170.0, 198.0) for cn in ("pan_22A", "pan_28A", "nopan_22A")]
REP3 = [(170.0, "pan_22A"), (198.0, "pan_28A"), (198.0, "nopan_22A")]
FS_NOM = list(np.arange(35000, 60001, 500.0))
FS_SENS = list(np.arange(35000, 60001, 1000.0))
NOM_CACHE = HERE / "results/nom_params_s19b.json"


def nominal_inputs():
    """cm capacitances and nominal params (the fringe Laplace solve takes ~10 s; cached)."""
    if NOM_CACHE.exists():
        d = json.loads(NOM_CACHE.read_text())
        return d["cm"], d["nom"]
    cm = m.cm_capacitances()
    nom = m.nominal_params(cm)
    cmj = {k: v for k, v in cm.items() if k != "geometry"}
    NOM_CACHE.parent.mkdir(exist_ok=True)
    NOM_CACHE.write_text(json.dumps({"cm": cmj, "nom": nom}, indent=1, default=float))
    return cmj, nom


def sens_set(cm, p):
    """s19b's 19 compliance sensitivities, applied to the candidate's full parameter dict p (BASE+nominal+candidate).
    Returns {name: (param_override, source_override)}."""
    lo, hi = cm["tab_C_range_F"]
    e0 = m.EPS0

    def enc(d):
        return (cm["fringe_sw_a_F"] + e0 * cm["pour_area_m2"]["sw_a"] / d,
                cm["fringe_sw_b_F"] + e0 * cm["pour_area_m2"]["sw_b"] / d)

    s = {}
    s["tabs_mismatch_AlN_range"] = ({"CTABA": hi, "CTABB": lo}, {})
    s["tabs_mismatch_reversed"] = ({"CTABA": lo, "CTABB": hi}, {})
    pa, pb = enc(5e-3)
    s["enclosure_metal_5mm"] = ({"CPOURA": pa, "CPOURB": pb}, {})
    pa, pb = enc(1e9)
    s["no_enclosure_coupling"] = ({"CPOURA": pa, "CPOURB": pb}, {})
    s["coil_caps_at_sw_nodes_(D-22 convention)"] = ({"COIL_AT_TANK": False}, {})
    s["coil_PE_study16_low_28p5pF"] = ({"CCOILA": 14.4e-12, "CCOILB": 14.1e-12}, {})
    s["coil_PE_study16_high_35p1pF"] = ({"CCOILA": 17.8e-12, "CCOILB": 17.3e-12}, {})
    s["coil_PE_study16_plus_board_51pF"] = ({"CCOILA": 25.7e-12, "CCOILB": 25.3e-12}, {})
    s["Y_caps_minus20pct"] = ({"CY": p["CY"] * 0.8, "CYADD": p["CYADD"] * 0.8, "CYHF": p["CYHF"] * 0.8}, {})
    s["Y_caps_ESL_x3"] = ({"ESLY": 45e-9, "ESLYADD": 45e-9, "ESLYHF": 30e-9}, {})
    s["L1_minus30pct_and_module_choke_minus30pct"] = ({"LCM": p["LCM"] * 0.7, "LCMADD": p["LCMADD"] * 0.7}, {})
    s["L1_winding_C_x2"] = ({"CCH": p["CCH"] * 2, "CCMADD": p["CCMADD"] * 2}, {})
    s["module_DM_80uH"] = ({"LNEW": p["LNEW"] * 31 / 41}, {})
    s["module_DM_L_parasitic_C_100pF"] = ({"CPNEW": 100e-12}, {})
    s["X_caps_minus20pct"] = ({"CX": p["CX"] * 0.8, "CXIN": p["CXIN"] * 0.8, "CXNEW": p["CXNEW"] * 0.8,
                               "CDAMP": p["CDAMP"] * 0.8}, {})
    s["PE_bond_200nH"] = ({"LPE": 200e-9}, {})
    s["edge_B_x1.2"] = ({}, {"edge_b": 1.2})
    s["edge_x0.5_slower"] = ({}, {"edge": 2.0})
    s["edge_x2_faster"] = ({}, {"edge": 0.5})
    return s


INFO = {"INFO_pan_earthed_91pF": ({"CCOILA": 46.2e-12, "CCOILB": 45.2e-12}, {})}


def _transfers(p, module, cfgs, fs_list):
    trs = {}
    for vc, cn in cfgs:
        trs[(vc, cn)] = {}
        for fs in fs_list:
            h = np.arange(1, int(30e6 / fs) + 1)
            t = m.transfers({**p, **m.tank_for(vc, m.case_at(vc, m.CASES[cn], fs), fs)}, module, h * fs)
            t["h"] = h
            trs[(vc, cn)][fs] = t
    return trs


def _worst(trs, cfgs, fs_list, edge=1.0, edge_b=1.0):
    best = None
    per_cfg = {}
    for vc, cn in cfgs:
        rows = m.aggregate(trs[(vc, cn)], None, vc, m.CASES[cn], fs_list, edge, edge_b)
        for band in ("lo", "hi"):
            w = m.worst(rows, "terminal", band)
            if not w:
                continue
            key = f"{int(vc)}V/{cn}"
            per_cfg.setdefault(key, {})[band] = w["margin_dB"]
            if best is None or w["margin_dB"] < best["margin_dB"]:
                best = dict(margin_dB=w["margin_dB"], band=band, cfg=key, f_hz=w["f_hz"], fs_hz=w["fs_hz"],
                            CM_dBuV=w["CM_dBuV"], DM_dBuV=w["DM_dBuV"])
    best["per_cfg"] = per_cfg
    return best


def evaluate(over: dict, nom: dict, cm: dict, full=True, info=False, fs_nom=None, fs_sens=None):
    """Return {'nominal': worst, 'sens': {name: worst}, 'min_dB', 'min_case'} for candidate override `over`."""
    over = dict(over)
    module = over.pop("_module", True)
    p = {**m.BASE, **nom, **over}
    fs_nom = fs_nom or FS_NOM
    fs_sens = fs_sens or FS_SENS
    out = {"nominal": _worst(_transfers(p, module, ALL6, fs_nom), ALL6, fs_nom)}
    if not full:
        out["min_dB"] = out["nominal"]["margin_dB"]
        out["min_case"] = "nominal"
        return out
    sens = {}
    base_tr = None
    sets = dict(sens_set(cm, p))
    if info:
        sets.update(INFO)
    for name, (pov, sov) in sets.items():
        if not pov:  # source-only (edge) scenario: reuse the candidate's own network
            if base_tr is None:
                base_tr = _transfers(p, module, REP3, fs_sens)
            tr = base_tr
        else:
            tr = _transfers({**p, **pov}, module, REP3, fs_sens)
        sens[name] = _worst(tr, REP3, fs_sens, sov.get("edge", 1.0), sov.get("edge_b", 1.0))
    out["sens"] = sens
    comp = {"nominal": out["nominal"]["margin_dB"], **{k: v["margin_dB"] for k, v in sens.items() if not k.startswith("INFO")}}
    out["min_case"] = min(comp, key=comp.get)
    out["min_dB"] = comp[out["min_case"]]
    return out
