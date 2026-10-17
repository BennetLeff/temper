import numpy as np, json, sys, re
from pathlib import Path
O = Path(sys.argv[1]); IT = float(sys.argv[2]) if len(sys.argv) > 2 else 23.1
sys.path.insert(0, str(O.parent / "b3"))
tank = (IT/18.7)**2; leg = (IT/2**0.5/18.7)**2; ret = (IT/34.0)**2
rows = [("sw_a-p00625-pl18", 0.5*tank), ("sw_a_low-p00625-pl18", 0.5*tank), ("sw_b_high-p00625-pl18", 0.5*tank), ("sw_b_low-p00625-pl18", 0.5*tank),
        ("res_a-p0125-pl18", tank), ("coil_feed-p0125-pl18", tank),
        ("leg_a_18p7-p00625-pl18", leg), ("leg_b_18p7-p00625-pl18", leg),
        ("hv_mixed_a-p00625-pl18", 0.5*ret), ("hv_mixed_b-p00625-pl18", 0.5*ret),
        ("bus_mixed_q2-p0125-pl18", 0.5*ret), ("bus_mixed_q5-p0125-pl18", 0.5*ret)]
HX, HY = 39.5, 15.5; RAD = 15.0
tot = {}; cells = {}; board = {}
for name, k in rows:
    z = np.load(O / f"{name}-heat.npz")
    j = json.load(open(O / f"{name}.json"))
    case = name.split("-")[0]
    for lay in ("F_Cu", "In1_Cu", "In2_Cu", "B_Cu"):
        x = z[f"{lay}_x_mm"]; y = z[f"{lay}_y_mm"]; w = z[f"{lay}_joule_w"] * k
        board[(case, lay)] = w.sum()
        X, Y = np.meshgrid(x, y, indexing="ij")
        m = (X-HX)**2 + (Y-HY)**2 <= RAD**2
        tot[(case, lay)] = w[m].sum()
        # 2 mm bins
        bx = np.floor(X[m]/2)*2; by = np.floor(Y[m]/2)*2
        for a, b, v in zip(bx, by, w[m]):
            if v: cells[(case, lay, a, b)] = cells.get((case, lay, a, b), 0) + v
    bh = j.get("barrel_hop_heat")
print("c22 I_t", IT)
print("== Joule within 15 mm of (39.5,15.5) by case/layer (W), and board total")
for k_, v in sorted(tot.items(), key=lambda kv: -kv[1])[:20]:
    print(f"{k_[0]:14s} {k_[1]:7s} {v:7.3f}  board {board[k_]:7.3f}")
print("sum within", sum(tot.values()), "board", sum(board.values()))
print("== top 2 mm cells")
for k_, v in sorted(cells.items(), key=lambda kv: -kv[1])[:40]:
    print(f"{k_[0]:14s} {k_[1]:7s} x{k_[2]:5.0f}-{k_[2]+2:<4.0f} y{k_[3]:5.0f}-{k_[3]+2:<4.0f} {v*1000:7.1f} mW")
