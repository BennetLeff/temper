"""Conducted-EMI effect of splitting the series resonant capacitor across both coil ends.

Reuses the power-stage session's stage-19b MNA model READ-ONLY (imported from its
worktree; nothing there is edited): same receiver, filter, sources, cases and
limits. The only change is the tank:

  as built   SW_A -R- tank_a -L- tank_b -C- SW_B           (C = 0.54 uF)
  split      SW_A -R- x -2C- tank_a -L- tank_b -2C- SW_B   (same series C)

The coil-to-PE capacitances stay at the coil ends (tank_a / tank_b), as in the
model's nominal COIL_AT_TANK convention. With the bank on one side, the coil's
mean potential carries half the capacitor voltage at the switching frequency;
splitting it symmetrically cancels that drive when the two coil-end
capacitances are equal.

Two placements of the pan-reflected resistance are run. Upstream (s19b) puts
RPAN in series at SW_A, outside the coil-end capacitance node; physically the
reflected R is inside the winding, so variant RIN places R/2 + L + R/2 between
the coil's outer terminals and hangs the coil-end capacitances there.

Usage: python3 emi_split_cap.py [path-to-emi_s19b.py]   -> emi_split_cap.json
"""
import importlib.util
import inspect
import json
import sys
from pathlib import Path

DEFAULT = Path("/Users/bennet/Desktop/temper/worktrees/ps-layers/zapote/power-stage-120v/"
               "validation-results/07-conducted-emi/s19b/emi_s19b.py")
CUSTOM = {  # Impulse-style coil electrostatic shield (fraction of coil capacitance returned to bus_n) with the pan earthed
    "pan_earthed_91pF+shield_75pct": ({"CCOILA": 46.2e-12, "CCOILB": 45.2e-12, "COIL_SHIELD_FRAC": 0.75}, {}),
    "pan_earthed_91pF+shield_90pct": ({"CCOILA": 46.2e-12, "CCOILB": 45.2e-12, "COIL_SHIELD_FRAC": 0.90}, {}),
    "asym_100pF_70_30+shield_90pct": ({"CCOILA": 70e-12, "CCOILB": 30e-12, "COIL_SHIELD_FRAC": 0.90}, {}),
}
SCEN = ["nominal", "INFO_pan_earthed_91pF", "INFO_pan_earthed_102pF", "coil_PE_100pF_one_sided_100_0",
        "INFO_assumed_100pF_asym_70_30", "coil_PE_study16_plus_board_51pF", "REC3_coil_shield_75pct_to_bus_n"]


def load(path):
    spec = importlib.util.spec_from_file_location("emi_s19b", path)
    m = importlib.util.module_from_spec(spec)
    sys.argv = [sys.argv[0]]          # the model reads --quick from argv at import
    spec.loader.exec_module(m)
    src = inspect.getsource(m.build)
    old = '    n.R("sw_a", "tank_a", p["RPAN"])\n    n.L("Lcoil", "tank_a", "tank_b", p["LCOIL"])\n    n.C("tank_b", "sw_b", p["CRES"])\n'
    assert old in src, "tank block changed upstream; update the patch"
    # RIN: the pan-reflected R sits INSIDE the coil (R/2 + L + R/2) and the coil-end
    # capacitances hang on the coil's outer terminals tank_a / tank_b.
    new = ('    if p.get("RIN"):\n'
           '        a_end = "tank_a" if p.get("SPLIT") else "sw_a"\n'
           '        if p.get("SPLIT"):\n'
           '            n.C("sw_a", "tank_a", 2 * p["CRES"])\n'
           '        else:\n'
           '            n.R("sw_a", "tank_a", 1e-6)\n'
           '        n.R("tank_a", "coil_1", p["RPAN"] / 2)\n'
           '        n.L("Lcoil", "coil_1", "coil_2", p["LCOIL"])\n'
           '        n.R("coil_2", "tank_b", p["RPAN"] / 2)\n'
           '        n.C("tank_b", "sw_b", (2 if p.get("SPLIT") else 1) * p["CRES"])\n'
           '    elif p.get("SPLIT"):\n'
           '        n.R("sw_a", "tank_x", p["RPAN"])\n'
           '        n.C("tank_x", "tank_a", 2 * p["CRES"])\n'
           '        n.L("Lcoil", "tank_a", "tank_b", p["LCOIL"])\n'
           '        n.C("tank_b", "sw_b", 2 * p["CRES"])\n'
           '    else:\n' + old.replace("\n    ", "\n        ").replace("    n.R", "        n.R", 1))
    exec(compile(src.replace(old, new), str(path), "exec"), m.__dict__)
    return m


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    sha = __import__("hashlib").sha256(path.read_bytes()).hexdigest()
    m = load(path)
    import numpy as np
    cm = m.cm_capacitances()
    nom = m.nominal_params(cm)
    scen = {**m.scenarios(cm, nom), **CUSTOM}
    cfgs = [(170.0, "pan_22A"), (198.0, "pan_28A"), (198.0, "nopan_22A")]
    fs_list = list(np.arange(35000, 60001, 1000.0))
    out = {"model": str(path), "model_sha256": sha, "fs_grid_hz": [fs_list[0], fs_list[-1], 1000.0],
           "configs": [f"{int(v)}V/{c}" for v, c in cfgs], "rows": {}}
    for name in SCEN + list(CUSTOM):
        pov, sov = scen[name]
        pov = dict(pov)
        module = pov.pop("_module", True)
        for rin, split in ((False, False), (False, True), (True, False), (True, True)):
            params = {**nom, **pov, "SPLIT": split, "RIN": rin}
            worst = None
            for vc, cn in cfgs:
                trs = {}
                for fs in fs_list:
                    h = np.arange(1, int(30e6 / fs) + 1)
                    t = m.transfers({**params, **m.tank_for(vc, m.case_at(vc, m.CASES[cn], fs), fs)}, module, h * fs)
                    t["h"] = h
                    trs[fs] = t
                rows = m.aggregate(trs, None, vc, m.CASES[cn], fs_list, sov.get("edge", 1.0), sov.get("edge_b", 1.0))
                for band in ("lo", "hi"):
                    w = m.worst(rows, "terminal", band)
                    if w and (worst is None or w["margin_dB"] < worst["margin_dB"]):
                        worst = {**w, "config": f"{int(vc)}V/{cn}", "band": band}
            key = f"{name}|{'R_in_coil' if rin else 'R_at_sw_a(upstream)'}|{'split' if split else 'as_built'}"
            out["rows"][key] = {k: (round(v, 2) if isinstance(v, float) else v) for k, v in worst.items()}
            print(f"{key:55s} margin {worst['margin_dB']:6.2f} dB at {worst['f_hz']/1e3:7.1f} kHz "
                  f"(h{worst['harmonic']}, {worst['config']}, CM {worst['CM_dBuV']:.1f} DM {worst['DM_dBuV']:.1f})", flush=True)
    Path(__file__).with_name("emi_split_cap.json").write_text(json.dumps(out, indent=1) + "\n")


if __name__ == "__main__":
    main()
