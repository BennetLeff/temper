#!/usr/bin/env python3
"""Round 18: wall time and peak memory of the native-21 chain, current vs proposed (ESTIMATES).

    python3 chain_estimate.py [../logs/history.tsv]

Model (every output is an estimate, not a measurement):
- Per-case wall = the measured wall of the matching native-19 leg-B case
  (sum of its four port solves, history.tsv) x a per-leg time factor =
  (measured native-21 coarse h1 wall) / (native-19 leg-B coarse h1 wall).
  Measured native-21 coarse h1 (live chain, campaign.log DONE lines, 2026-10-08):
  A21 7567 + 7568 + 6847 + 6758 s (12.7-14.1 k iterations per port; the first
  ~10 h of it with our 2-rank experiments beside it, which cost the chain ~18 %),
  B21 2321 + 2314 + 3064 + 2196 s.
  Wall per port is iterations x seconds per iteration, and seconds per
  iteration grow ~linearly with tets at fixed ranks (history: 1.6-2.0
  s*rank/(it*Mtet)); iteration counts are taken as unchanged.
- Native-21 tets: leg A coarse h1 = 3,373,055 (measured, live chain). Other
  heights / crop scale as the native-19 leg-B ladder. Leg B21 coarse = 0.818 x
  leg A21 (README: 4.73 M vs 5.78 M tets at 0.7 mm edges). Fine/coarse tet
  ratio at h = 1: 3.45 (leg B n19) to 3.59 (leg A n17); fine h2, h3 scale as
  leg A n17 (8.91/7.94, 9.88/7.94).
- Memory = 6.1 kB per tet (measured: 6.08-6.14 kB/tet on every fine run,
  6.1 on the live coarse run; GNU time max RSS x 12 ranks).
- Machine: 62 GB RAM, 1 GB swap.
"""
import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
hist = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent / "logs" / "history.tsv"
rows = list(csv.DictReader(open(hist), delimiter="\t"))


def case(prefix: str) -> tuple[float, int]:
    rs = [r for r in rows if prefix in r["run"] and r["converged"] == "True" and r["np"] == "12"]
    assert len(rs) == 4, (prefix, len(rs))
    return sum(float(r["wall_s"]) for r in rs), int(rs[0]["tets"])


KB_PER_TET, RAM_GB = 6.1, 62.0
A21_H1 = 3_373_055
B21_H1 = 2_715_967                       # measured (live chain)
WALL_N21 = {"A21": 7567 + 7568 + 6847 + 6758.0, "B21": 2321.27 + 2314.15 + 3064.23 + 2196.0}
B19 = {k: case(v) for k, v in {
    "h1": "b19c/legB-h1-e1p0-n19-", "h0p5": "b19corr/legB-h0p5-e1p0-n19-", "h2": "b19corr/legB-h2-e1p0-n19-",
    "h3": "b19corr/legB-h3-e1p0-n19-", "m20": "b19corr/legB-h1-e1p0-m20-a10-n19-",
    "fine_h1": "campB19/legB-h1-e0p35-n19-"}.items()}
A17F = {k: case(f"camp2/legA-{k}-e0p35-P") if k != "h1" else case("camp-v1-gs-at-h-plus-1mm/legA-h1-e0p35-")
        for k in ("h1", "h2", "h3")}
# fine B19 h2/h3 were never run: scale B19 fine h1 by leg A n17's fine ladder
for k in ("h2", "h3"):
    ratio = A17F[k][1] / A17F["h1"][1]
    wall_ratio = A17F[k][0] / A17F["h1"][0]
    B19["fine_" + k] = (B19["fine_h1"][0] * wall_ratio, int(B19["fine_h1"][1] * ratio))

leg_scale = {"A21": A21_H1 / B19["h1"][1], "B21": B21_H1 / B19["h1"][1]}
time_scale = {k: WALL_N21[k] / B19["h1"][0] for k in WALL_N21}
print(f"tet scale vs native-19 leg B: A21 {leg_scale['A21']:.3f}, B21 {leg_scale['B21']:.3f} (measured h1 meshes)")
print(f"time scale vs native-19 leg B (measured coarse h1 walls): A21 {time_scale['A21']:.2f}, B21 {time_scale['B21']:.2f}")
print(f"fine/coarse ratio check: B19 {B19['fine_h1'][1] / B19['h1'][1]:.2f}, A17 {A17F['h1'][1] / 2214123:.2f}")
print()
order_coarse = ["h1", "h0p5", "h2", "h3", "m20"]
order_fine = ["fine_h1", "fine_h2", "fine_h3"]
tot = {"current": 0.0, "proposed": 0.0}
print(f"{'case':22s} {'tets(M)':>8s} {'wall(h)':>8s} {'mem(GB)':>8s}  fits?  in current / proposed")
for leg in ("A21", "B21"):
    for k in order_coarse + order_fine:
        w, t = B19[k]
        s = leg_scale[leg]
        tets, wall = t * s, w * time_scale[leg] / 3600
        mem = tets * KB_PER_TET / 1e6
        fits = mem < RAM_GB - 4      # leave ~4 GB for the OS, campaign and page cache
        prop = k not in ("fine_h2", "fine_h3")
        tot["current"] += wall
        tot["proposed"] += wall if prop else 0
        print(f"{leg + ' ' + k:22s} {tets / 1e6:8.2f} {wall:8.1f} {mem:8.1f}  {'yes' if fits else 'NO '}   "
              f"yes / {'yes' if prop else 'no'}")
print()
for k, v in tot.items():
    print(f"{k:9s} chain: {v:6.1f} h = {v / 24:4.1f} days (estimate)")
print(f"saving from dropping fine h2/h3: {tot['current'] / tot['proposed']:.2f}x")
for f in (0.85, 0.71):
    print(f"  with Krylov time x{f} (looser stop, if qualified): {tot['proposed'] * f:6.1f} h -> "
          f"{tot['current'] / (tot['proposed'] * f):.2f}x")
