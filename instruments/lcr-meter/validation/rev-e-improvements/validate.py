#!/usr/bin/env python3
"""Cross-check the reduced Rev E network (revE_front.py) against the SPICE-derived virtual instrument.

V1 noise: 1-sigma fitted |dZ/Z| on the Rev D topology (R_src 100 Ohm, 2T) against
   ../rev-e-codec/results/noise_codec.json (TAC5112), same capture times.
V2 lead movement: 2T, R_iso 22, 200 pF on each DUT terminal moved to 240 pF after calibration,
   perfect standards, no noise, against ../virtual-instrument/results/leadmove.csv
   (lm_riso22_c200_to240, real host-equivalent chain from the SPICE transfers).
    validate.py -> results/validation.json
"""
import csv
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import study as s  # noqa: E402
import revE_front as fe  # noqa: E402

vm = s.vm


def v1():
    pts = json.loads((HERE.parent / "rev-e-codec/results/noise_codec.json").read_text())["points"]
    out = []
    seen = set()
    for p in pts:
        if p["codec"] != "TAC5112" or (p["dut"], p["hz"]) in seen:
            continue
        seen.add((p["dut"], p["hz"]))
        z = complex(*p["z_true"])
        pf = dict(rc=np.zeros((1, 4)), c2t=np.zeros((1, 2)), cx=np.zeros((1, 4)), lser=np.zeros(1))
        d = fe.nominal_drift(1)
        a, b = fe.measure(p["hz"], False, np.array([z]), pf, d, rsrc=100.0)
        sig = fe.phasor_sigma(p["capture_s"])
        rel = math.sqrt(2 * sig ** 2 * (1 / abs(a[0]) ** 2 + 1 / abs(b[0]) ** 2))
        out.append(dict(dut=p["dut"], hz=p["hz"], this=rel, noise_codec=p["sigma_rel_z"],
                        ratio=rel / p["sigma_rel_z"], a_pin_this=abs(a[0]), a_pin_codec=p["a_peak_v"]))
    return out


def v2():
    vi = {r["target"]: float(r["lm_riso22_c200_to240_bias"]) for r in
          csv.DictReader(open(HERE.parent / "virtual-instrument/results/leadmove.csv"))}
    cfg = s.Cfg("v2", "2T lead move", kit="dmm")
    data = {}
    for f in sorted({x for v in s.dut_freqs().values() for x in v}):
        w = 2 * math.pi * f

        def meas(z, cl):
            n = 1
            pf = dict(rc=np.zeros((n, 4)), c2t=np.full((n, 2), cl), cx=np.zeros((n, 4)), lser=np.zeros(n))
            d = fe.nominal_drift(n)
            d["C100"][:] = 0.0          # VI 'riso22' transfers have no DUT_LO capacitor
            a, b = fe.measure(f, False, np.array([z]), pf, d, rsrc=100.0)
            return fe.raw(a, b)
        abc = vm.cal_coeffs(meas(1e-6 + 0j, 200e-12), meas(20 + 0j, 200e-12), 20.0, meas(100 + 0j, 200e-12), 100.0)
        for dn, fl in s.dut_freqs().items():
            if f in fl:
                zt = complex(vm.DUTS[dn].z(f))
                zm = vm.correct(meas(zt, 240e-12), abc)
                data[(dn, f)] = (np.array([zm[0], zm[0]]), zt)
    ev = s.evaluate(data)
    return [dict(target=t, this=abs(v["bias"]), vi=vi[t], ratio=abs(v["bias"]) / vi[t] if vi[t] else None)
            for t, v in ev.items()]


def main():
    r1, r2 = v1(), v2()
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results/validation.json").write_text(json.dumps(dict(noise=r1, leadmove=r2), indent=1))
    rat = np.array([x["ratio"] for x in r1])
    print(f"V1 noise vs noise_codec.json: ratio median {np.median(rat):.3f}, range {rat.min():.3f}-{rat.max():.3f} "
          f"over {len(rat)} points")
    for x in r2:
        print(f"V2 {x['target']:16s} this {x['this']:.3g}  VI {x['vi']:.3g}  ratio {x['ratio'] if x['ratio'] is None else round(x['ratio'], 3)}")


if __name__ == "__main__":
    main()
