import json
import sys
from pathlib import Path

import numpy as np

root = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(root / "validation-plan/sim-kit/common"))
from run_ngspice import read_raw  # noqa: E402

folder = Path(sys.argv[1])
wave = {key: np.asarray(value) for key, value in read_raw(folder / "waves.raw").items()}
t = wave["time"]
vds_l = wave["v(xql.dd)"] - wave["v(xql.s)"]
vds_h = wave["v(xqh.dd)"] - wave["v(xqh.s)"]
vgs_l = wave["v(xql.g)"] - wave["v(xql.s)"]
vgs_h = wave["v(xqh.g)"] - wave["v(xqh.s)"]
chan_l = wave["i(v.xql.x1.v_ichannel)"]
chan_h = wave["i(v.xqh.x1.v_ichannel)"]
diode_l = -wave["i(v.xql.x1.v_sense2)"]
diode_h = -wave["i(v.xqh.x1.v_sense2)"]
cmd_l = wave["v(gl_cmd)"] - wave["v(kret)"]
cmd_h = wave["v(gh_cmd)"] - wave["v(s_hs)"]
post = t >= 2.0025e-6
ipk = np.flatnonzero(post)[np.argmax(vds_l[post])]
igk = np.flatnonzero(t >= 2.3505e-6)[np.argmax(vgs_l[t >= 2.3505e-6])]
both_channel = (t >= 2.3505e-6) & (chan_l > 1.0) & (chan_h > 1.0)
idx = np.flatnonzero(both_channel)

def point(i):
    return {"time_s": float(t[i]), "vds_ls_v": float(vds_l[i]), "vds_hs_v": float(vds_h[i]),
            "vgs_ls_v": float(vgs_l[i]), "vgs_hs_v": float(vgs_h[i]),
            "gchan_ls_a_includes_breakdown": float(chan_l[i]),
            "gchan_hs_a_includes_breakdown": float(chan_h[i]),
            "idiode_forward_ls_a": float(diode_l[i]), "idiode_forward_hs_a": float(diode_h[i]),
            "idrain_external_ls_a": float(wave["i(vids)"][i]),
            "idrain_external_hs_a": float(wave["i(vidh)"][i]),
            "switch_v": float(wave["v(sw)"][i]),
            "cap_bus_v": float(wave["v(capm)"][i]),
            "driver_ls_v": float(wave["v(gdl)"][i] - wave["v(kret)"][i]),
            "driver_hs_v": float(wave["v(gdh)"][i] - wave["v(s_hs)"][i]),
            "cmd_ls_v": float(cmd_l[i]), "cmd_hs_v": float(cmd_h[i])}

out = {"peak_vds": point(ipk), "peak_off_vgs": point(igk),
       "both_gchan_positive_1a_samples_not_shootthrough": len(idx),
       "both_gchan_first_not_shootthrough": point(idx[0]) if len(idx) else None,
       "both_gchan_last_not_shootthrough": point(idx[-1]) if len(idx) else None,
       "both_gchan_max_min_a_not_shootthrough": float(np.max(np.minimum(chan_l[idx],chan_h[idx]))) if len(idx) else None,
       "last_time_s": float(t[-1]), "samples": len(t)}
for when in (2.3505e-6, 2.359061e-6, 2.41804e-6, 2.492115e-6, 3.095563e-6):
    i = int(np.argmin(abs(t-when)))
    out[f"near_{when:.9g}"] = point(i)
print(json.dumps(out, indent=2))
