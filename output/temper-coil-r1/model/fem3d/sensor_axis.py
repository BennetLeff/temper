"""B on the sensor axis from a 3D discrete-bar sector solve (peak T per amp of coil current, and at 28 A rms).

  <cadenv python> sensor_axis.py PVTU_OR_VTU_DIR CASE_LABEL  ->  results/sensor_axis_CASE_LABEL.json

Reads the VTU the run3d.py cases write (1 A per turn, 18 deg wedge with mirror planes, so the wedge contains the
coil axis). Samples the axis and r = 1.5 mm at the sensor's heights: Z95 (spring top), Z105 (capillary) and Z109.5
(Pt100 chip, glass top Z110). Harmonic runs carry re/im parts; |B| is the peak magnitude.
"""
import json, math, sys
from pathlib import Path
import numpy as np
import pyvista as pv

src, label = Path(sys.argv[1]), sys.argv[2]
files = sorted(src.glob("*.pvtu")) or sorted(src.glob("*.vtu"))
g = pv.read(str(files[-1]))
keys = list(g.point_data.keys())
print("point arrays:", keys)
re_ = next((k for k in keys if k.startswith("magnetic flux density re") and "e" not in k.split("density re")[1]), None)
if re_ and "magnetic flux density im" in keys:
    comp = lambda d: np.abs(d["magnetic flux density re"] + 1j * d["magnetic flux density im"])
else:
    comp = lambda d: np.abs(d["magnetic flux density"])
Z = {"Z95": 0.095, "Z105": 0.105, "Z109.5": 0.1095}
I_PK = 28 * math.sqrt(2)
out = {"label": label, "I_pk_A": I_PK, "points": {}}
for rname, (x, y) in {"axis": (1e-4, 1e-5), "r1.5mm": (1.5e-3, 1e-4)}.items():
    for zn, z in Z.items():
        pt = pv.PolyData(np.array([[x, y, z]]))
        s = pt.sample(g)
        v = comp(s.point_data)[0]
        B = np.sqrt(np.sum(np.abs(v) ** 2))
        valid = bool(s.point_data["vtkValidPointMask"][0])
        out["points"][f"{rname}_{zn}"] = dict(valid=valid, B_T_per_A=float(B), B_mT_at_28Arms=float(B * I_PK * 1e3),
                                              Bz_mT_at_28Arms=float(abs(v[2]) * I_PK * 1e3), Br_mT_at_28Arms=float(math.hypot(abs(v[0]), abs(v[1])) * I_PK * 1e3))
bz95, bz105 = (out["points"][f"axis_{k}"]["Bz_mT_at_28Arms"] for k in ("Z95", "Z105"))
out["dBz_dz_T_per_m"] = abs(bz105 - bz95) * 1e-3 / 10e-3
Path(__file__).parent.joinpath("results", f"sensor_axis_{label}.json").write_text(json.dumps(out, indent=1) + "\n")
print(json.dumps(out, indent=1))
