#!/usr/bin/env python3
"""Rev F vs Rev E: relative magnetic near-field pickup from the TPS65131, and which tones a
switcher harmonic can reach.

RELATIVE ESTIMATE, NOT A BOUND. The absolute leakage of the switch loops and inductors is unknown
(no measurement, no field solve), so this script says only how much the coupling CHANGES between two
layouts with the same circuit and currents. Out of scope: the In1.Cu GND plane's eddy-current
shielding (same plane in both revisions, taken to cancel in the ratio), conducted and capacitive
coupling, and the enclosure.

Part A, pickup. Sources: the TPS65131 switching loops, each a closed polyline through pad centres,
and L1/L2 as vertical point dipoles at the part centre (semi-shielded drum cores; same part and
current in both revisions, so only position matters). Victims: closed polylines through pad centres.
Between two pads on the same net the polyline follows the routed copper (shortest path over
routing.json tracks and vias) in board mode, or the straight pad-to-pad line in plan mode (both
revisions alike, so the ratio compares like with like). Between two pins of one part, and on the
closing edge, and on GND hops (the In1.Cu plane), it is straight: the plane return is taken to run
along that line. That is the low-frequency return; at the MHz switching harmonics a plane return
follows the trace and the true area of those plane-return loops is smaller (both revisions alike).
Coupling = mutual inductance by the Neumann double line integral over the two polylines (loops) or
the flux of the point dipole's vector potential round the victim (inductors); the coplanar dipole
estimate mu0 A_s A_v / (4 pi r^3) is reported beside it as a cross-check.

Part A2, harmonics: rev_e_spurs.switcher() for each tone (fsw uniform 1.25-1.50 MHz, free running).
That collision chance depends on the frequency plan only, not the layout; the near-field ratio of
part A scales the error IF a collision happens.

  python3 switcher_pickup.py                    Rev E (git 48b012771) vs Rev F plan (floorplan.json)
  python3 switcher_pickup.py --rev-f ROOT       Rev E vs a built Rev F tree (build/pad-coordinates.json
                                                and cad/routing.json), routed copper on both sides
  options: --rev-e ROOT (default: the Rev E commit), --out FILE (default switcher_pickup.json here)
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib

import numpy as np

import copper as cu
import rev_e_spurs as rs

HERE = pathlib.Path(__file__).resolve().parent
FLOORPLAN = HERE.parent / "rev-f-floorplan/floorplan.json"
MU0_4PI = 1e-7
STEP_MM = 0.25                       # polyline subdivision for the Neumann sum
TONES = [1500.0, 27500.0, 35500.0, 40500.0, 50500.0, 60500.0, 85000.0]


# ------------------------------------------------------------------ loop definitions
def nearest_pad(pads, net, to, prefix="C", exclude=()):
    best = min(((math.dist(xy[:2], to), r, n) for r, pins in pads.items() if r.startswith(prefix)
                and r not in exclude for n, xy in pins.items() if xy[2] == net), default=None)
    return (best[1], best[2]) if best else None


def other_pin(pads, ref, net):
    return next(n for n, xy in pads[ref].items() if xy[2] == net)


def loops(pads):
    """Pad sequences (ref, pin). Consecutive pads on one net follow that net's copper."""
    at = lambda r, n: pads[r][n][:2]
    cin_p = nearest_pad(pads, "5V", at("L1", "1"))                  # boost input cap at L1
    cin_n = nearest_pad(pads, "5V", at("U13", "5"))                 # inverter input cap at VIN
    cop = nearest_pad(pads, "RAW_P", at("D2", "1"))
    con = nearest_pad(pads, "RAW_N", at("D3", "2"))
    g = lambda ref: (ref, other_pin(pads, ref, "GND"))
    src = {
        "boost hot loop (SW_P-D2-C_RAWP-GND-PGND)": [("U13", "1"), ("D2", "2"), ("D2", "1"), cop, g(cop[0]), ("U13", "2")],
        "boost on-phase (C5V-L1-SW_P-PGND)": [cin_p, ("L1", "1"), ("L1", "2"), ("U13", "1"), ("U13", "2"), g(cin_p[0])],
        "boost off-phase (C5V-L1-D2-C_RAWP)": [cin_p, ("L1", "1"), ("L1", "2"), ("D2", "2"), ("D2", "1"), cop, g(cop[0]), g(cin_p[0])],
        "inverter hot loop (C5V-VIN-SW_N-D3-C_RAWN)": [cin_n, ("U13", "5"), ("U13", "13"), ("D3", "1"), ("D3", "2"), con, g(con[0]), g(cin_n[0])],
        "inverter on-phase (C5V-VIN-SW_N-L2-GND)": [cin_n, ("U13", "5"), ("U13", "13"), ("L2", "1"), ("L2", "2"), g(cin_n[0])],
    }
    def gnd_near(ref, pin, jack):
        """Return path: the GND pad of the capacitor nearest the follower input, then the jack's
        nearest shell pin."""
        shell = min((n for n, xy in pads[jack].items() if xy[2] == "GND"),
                    key=lambda n: math.dist(pads[jack][n][:2], at(ref, pin)))
        return [nearest_pad(pads, "GND", at(ref, pin)), (jack, shell)]
    vic = {
        "codec ch1 input legs (R71-U14.15/16-R70)": [("R71", "2"), ("R71", "1"), ("U14", "15"), ("U14", "16"), ("R70", "1"), ("R70", "2")],
        "codec ch2 input legs (R69-U14.17/18-R68)": [("R69", "2"), ("R69", "1"), ("U14", "17"), ("U14", "18"), ("R68", "1"), ("R68", "2")],
        "TIA C104 loop (U7.1-C104-U7.2)": [("U7", "1"), ("C104", "2"), ("C104", "1"), ("U7", "2")],
        "TIA RF100K loop (U7.1-K3-R45-U7.2)": [("U7", "1"), ("K3", "8"), ("K3", "7"), ("R45", "2"), ("R45", "1"), ("U7", "2")],
        "U6 EXCITE input (U5.1-U6.3, return via the nearest GND capacitor pads)":
            [("U5", "1"), ("U6", "3"), nearest_pad(pads, "GND", at("U6", "3")), nearest_pad(pads, "GND", at("U5", "1"))],
        "HPOT input (J7.5-U6.5, GND return)": [("J7", "5"), ("U6", "5")] + gnd_near("U6", "5", "J7"),
        "LPOT input (J8.5-U7.5, GND return)": [("J8", "5"), ("U7", "5")] + gnd_near("U7", "5", "J8"),
    }
    return src, vic


def polyline(seq, pads, cop):
    """Closed polyline (N x 2, mm) for a pad sequence; returns points and whether every same-net
    hop was routed copper (None in plan mode)."""
    pts, routed = [], True
    for (r1, n1), (r2, n2) in zip(seq, seq[1:] + seq[:1]):
        a, b = pads[r1][n1], pads[r2][n2]
        if cop is not None and a[2] == b[2] != "GND" and (r1, n1) != seq[-1]:   # GND hops: the In1.Cu plane
            p = cop.path(a[2], [(r1, n1)], [(r2, n2)], weight="mm")
            routed &= p["routed"]
            seg = p["points"]
        else:
            seg = [tuple(a[:2]), tuple(b[:2])]
        pts.extend(seg if not pts else seg[1:] if math.dist(pts[-1], seg[0]) < 1e-9 else seg)
    return np.array(pts, dtype=float), (routed if cop is not None else None)


def area_centroid(p):
    x, y = p[:, 0], p[:, 1]
    xs, ys = np.roll(x, -1), np.roll(y, -1)
    cr = x * ys - xs * y
    a = cr.sum() / 2
    if abs(a) < 1e-9:
        return 0.0, p.mean(axis=0)
    return a, np.array([((x + xs) * cr).sum(), ((y + ys) * cr).sum()]) / (6 * a)


def pieces(p):
    """Midpoints and vectors (m) of a closed polyline cut into <= STEP_MM pieces."""
    q = np.vstack([p, p[:1]])
    mids, vecs = [], []
    for a, b in zip(q, q[1:]):
        n = max(1, int(math.ceil(np.linalg.norm(b - a) / STEP_MM)))
        t = (np.arange(n) + 0.5) / n
        mids.append(a + np.outer(t, b - a))
        vecs.append(np.repeat(((b - a) / n)[None], n, axis=0))
    return np.vstack(mids) * 1e-3, np.vstack(vecs) * 1e-3


def neumann(p1, p2):
    m1, v1 = pieces(p1)
    m2, v2 = pieces(p2)
    r = np.linalg.norm(m1[:, None] - m2[None], axis=2)
    return MU0_4PI * float(((v1 @ v2.T) / r).sum())


def dipole_flux(centre_mm, p):
    """Flux through polyline p of a unit vertical dipole (A m^2) at centre: closed integral of
    A = mu0/(4 pi) (z x r)/r^3 along the loop."""
    m, v = pieces(p)
    d = m - np.asarray(centre_mm) * 1e-3
    r3 = np.linalg.norm(d, axis=1) ** 3
    a = np.stack([-d[:, 1], d[:, 0]], axis=1) / r3[:, None]
    return MU0_4PI * float((a * v).sum())


# ------------------------------------------------------------------ geometry sources
def plan_pads(pads_e):
    """Rev E pads moved rigidly to the floorplan.json anchors. A part with no anchor follows the
    nearest anchored part that shares a net with it (Rev E positions)."""
    fp = json.loads(FLOORPLAN.read_text())["anchors"]
    inv = json.loads(cu.INVENTORY.read_text())["parts"]
    nets = {r: {xy[2] for xy in p.values()} - {"GND", ""} for r, p in pads_e.items()}
    out = {}
    for ref, pins in pads_e.items():
        host = ref if ref in fp else min((h for h in fp if h in inv and nets[h] & nets.get(ref, set())),
                                         key=lambda h: math.dist(inv[h]["at"], inv[ref]["at"]), default=None)
        if host is None:
            continue
        (xe, ye), re_ = inv[host]["at"], inv[host]["rot"]
        xf, yf, rf = fp[host]["at"]
        t = math.radians(rf - re_)
        c, s = math.cos(t), math.sin(t)
        # KiCad: y down, positive angle counter-clockwise on screen
        out[ref] = {n: [xf + (x - xe) * c + (y - ye) * s, yf - (x - xe) * s + (y - ye) * c, net]
                    for n, (x, y, net) in pins.items()}
    return out


def evaluate(pads, cop):
    src, vic = loops(pads)
    S = {k: polyline(v, pads, cop) for k, v in src.items()}
    V = {k: polyline(v, pads, cop) for k, v in vic.items()}
    inductors = {f"{r} shielded inductor (vertical dipole)": np.mean([xy[:2] for xy in pads[r].values()], axis=0)
                 for r in ("L1", "L2")}
    res = {"sources": {}, "victims": {}, "coupling": {}}
    for k, (p, ok) in S.items():
        a, cen = area_centroid(p)
        res["sources"][k] = {"area_mm2": round(abs(a), 3), "centroid_mm": cen.round(2).tolist(), "copper_routed": ok}
    for k, cen in inductors.items():
        res["sources"][k] = {"centroid_mm": cen.round(2).tolist()}
    for k, (p, ok) in V.items():
        a, cen = area_centroid(p)
        res["victims"][k] = {"area_mm2": round(abs(a), 3), "centroid_mm": cen.round(2).tolist(), "copper_routed": ok,
                             "perimeter_mm": round(float(np.linalg.norm(np.diff(np.vstack([p, p[:1]]), axis=0), axis=1).sum()), 2)}
        for s, (q, _) in S.items():
            asrc, csrc = area_centroid(q)
            r = float(np.linalg.norm(cen - csrc))
            res["coupling"][f"{k} | {s}"] = {"M_H": neumann(q, p), "r_mm": round(r, 2),
                                             "M_dipole_H": MU0_4PI * abs(asrc * a) * 1e-12 / (r * 1e-3) ** 3}
        for s, csrc in inductors.items():
            r = float(np.linalg.norm(cen - csrc))
            res["coupling"][f"{k} | {s}"] = {"M_H": dipole_flux(csrc, p), "r_mm": round(r, 2),
                                             "M_dipole_H": MU0_4PI * abs(a) * 1e-6 / (r * 1e-3) ** 3}
    return res


def db(new, old):
    return round(20 * math.log10(abs(new) / abs(old)), 2) if new and old else None


def pickup(args):
    if args.rev_e:
        pads_e, half_e, pads_e_src = cu.load_pads(args.rev_e)
    else:
        inv = json.loads(cu.INVENTORY.read_text())["parts"]
        pads_e, half_e, pads_e_src = ({r: p["pads"] for r, p in inv.items()},
                                      {r: p.get("pad_half", {}) for r, p in inv.items()}, str(cu.INVENTORY))
    rt_e, rt_e_src = cu.load_routing(args.rev_e)
    if args.rev_f:
        pads_f, half_f, pads_f_src = cu.load_pads(args.rev_f)
        rt_f, rt_f_src = cu.load_routing(args.rev_f)
        mode = "board: routed copper on both revisions"
        cop_e, cop_f = cu.Copper(rt_e, pads_e, half_e), cu.Copper(rt_f, pads_f, half_f)
    else:
        pads_f, pads_f_src, rt_f_src = plan_pads(pads_e), str(FLOORPLAN), None
        mode = "plan: pad-centre polylines on both revisions (Rev F parts moved rigidly to floorplan.json anchors)"
        cop_e = cop_f = None
    e, f = evaluate(pads_e, cop_e), evaluate(pads_f, cop_f)
    rows = {}
    for key in e["coupling"]:
        ce, cf = e["coupling"][key], f["coupling"][key]
        rows[key] = {"rev_e_r_mm": ce["r_mm"], "rev_f_r_mm": cf["r_mm"],
                     "rev_e_M_nH": ce["M_H"] * 1e9, "rev_f_M_nH": cf["M_H"] * 1e9,
                     "ratio_db": db(cf["M_H"], ce["M_H"]), "dipole_ratio_db": db(cf["M_dipole_H"], ce["M_dipole_H"])}
    by_victim = {}
    for v in e["victims"]:
        rs_ = {k.split(" | ")[1]: r for k, r in rows.items() if k.startswith(v + " | ")}
        tot_e = sum(abs(r["rev_e_M_nH"]) for s, r in rs_.items() if "inductor" not in s)
        tot_f = sum(abs(r["rev_f_M_nH"]) for s, r in rs_.items() if "inductor" not in s)
        by_victim[v] = {"rev_e_area_mm2": e["victims"][v]["area_mm2"], "rev_f_area_mm2": f["victims"][v]["area_mm2"],
                        "loops_sum_ratio_db": db(tot_f, tot_e),
                        "inductor_ratio_db": {s.split()[0]: r["ratio_db"] for s, r in rs_.items() if "inductor" in s},
                        "worst_source_ratio_db": max(r["ratio_db"] for r in rs_.values() if r["ratio_db"] is not None)}
    by_source = {s: {"rev_e_area_mm2": e["sources"][s].get("area_mm2"), "rev_f_area_mm2": f["sources"][s].get("area_mm2"),
                     "ratio_db_by_victim": {k.split(" | ")[0]: r["ratio_db"] for k, r in rows.items() if k.endswith(" | " + s)}}
                 for s in e["sources"]}
    return {"mode": mode,
            "units": "M_nH is mutual inductance in nH for loop sources; for the inductor dipoles it is the flux "
                     "per unit dipole moment, Wb/(A m^2) x 1e9. Only the ratios carry meaning.",
            "inputs": {"rev_e_pads": pads_e_src, "rev_e_routing": rt_e_src, "rev_f_pads": pads_f_src, "rev_f_routing": rt_f_src},
            "by_victim": by_victim, "by_source": by_source, "pairs": rows,
            "rev_e_geometry": e, "rev_f_geometry": f}


def harmonics():
    """A2: rev_e_spurs.switcher() collision chance per tone (layout independent)."""
    out = {}
    for hz in TONES:
        p = rs.plan(hz)
        sw = rs.switcher(p, {})
        w = sw["line_response_width_hz"]
        out[f"{p['f_hz']:.1f}"] = {
            "record_s": p["seconds"], "line_response_width_hz": w,
            "transition_band_image": rs.FS - p["f_hz"] < rs.ADC_STOP,
            "by_modulator_rate": {
                name: {"probability_unattenuated": v["probability_unattenuated"],
                       "probability_stopband_any_at_-90.5_dB": v["probability_stopband_any"],
                       "collision_count": v["unattenuated_collision_count"],
                       "fsw_windows_hz_top10": [{"m": h["m"], "k": h["k"], "fsw_hz": round(h["fsw_hz"], 1),
                                                 "half_width_hz": round(w / 2 / h["m"], 2),
                                                 "probability": h["probability"]}
                                                for h in v["largest_collisions"]]}
                for name, v in sw["by_modulator_rate"].items()}}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--rev-e", type=pathlib.Path)
    ap.add_argument("--rev-f", type=pathlib.Path)
    ap.add_argument("--out", type=pathlib.Path, default=HERE / "switcher_pickup.json")
    args = ap.parse_args()
    out = {"note": "RELATIVE estimate, NOT a bound: Rev F/Rev E change in magnetic near-field coupling for the same "
                   "circuit and currents. The absolute switcher leakage is unknown. The GND plane's shielding, "
                   "conducted and capacitive paths and the enclosure are not modelled.",
           "method": __doc__.split("\n\n")[2].replace("\n", " "),
           "pickup": pickup(args), "harmonics": harmonics()}
    args.out.write_text(json.dumps(out, indent=1, default=float) + "\n")
    pk = out["pickup"]
    print(pk["mode"])
    for v, r in pk["by_victim"].items():
        ind = ", ".join(f"{k} {x:+.1f}" if x is not None else f"{k} n/a" for k, x in r["inductor_ratio_db"].items())
        print(f"  {v:46s} area E/F {r['rev_e_area_mm2']:7.2f}/{r['rev_f_area_mm2']:7.2f} mm2  loops {r['loops_sum_ratio_db']:+6.1f} dB"
              f"  inductors {ind}  worst {r['worst_source_ratio_db']:+.1f} dB")
    for t, h in out["harmonics"].items():
        print(f"  {t:>8s} Hz  P(collision) " + ", ".join(f"{n.split()[0]} {v['probability_unattenuated']:.1e}"
                                                       for n, v in h["by_modulator_rate"].items()))
    print(f"-> {args.out}")


if __name__ == "__main__":
    main()
