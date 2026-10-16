#!/usr/bin/env python3
"""Tests for the B3 airflow region, the HF film-cap body-to-air path (b3-ratings/jet-2026-10-15) and the PS2 module
body-to-air path and rating row (OPEN-ITEMS S18, 11-candidates/s18-ps2-body). No board solves.

    python3 validation-results/04-board-current-thermal/round5-native21/b3-ratings/test_b3_airflow.py
"""
import math
import sys
from pathlib import Path

import numpy as np

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
UNIT = HERE.parents[3]
sys.path.insert(0, str(HERE.parent / "b3-convergence"))
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(UNIT / "native-21/layout/gates"))
import thermal_body as tb  # noqa: E402
import b3_ratings_gate as gate  # noqa: E402
import run_basis as rb  # noqa: E402
import jet_strip_height as jsh  # noqa: E402

fails = 0


def ok(cond, msg):
    global fails
    print(("ok   " if cond else "FAIL ") + msg)
    fails += 0 if cond else 1


# ---- film-cap body-to-air conductance
area = tb.film_body_area_mm2() * 1e-6
ok(abs(tb.film_body_area_mm2() - (9.0 * 18.0 + 2 * 17.5 * 18.0 + 2 * 9.0 * 17.5)) < 1e-9,
   "exposed area = top + two sides + two ends of the p.14 9.0 x 17.5 x 18.0 mm box (1107 mm^2)")
hs = [1, 5, 10, 35, 60, 100, 150]
gs = [tb.film_body_g_air(h) for h in hs]
ok(all(b > a for a, b in zip(gs, gs[1:])), "g_air rises with h")
ok(all(g <= h * area + 1e-15 for h, g in zip(hs, gs)), "g_air never exceeds the bare-area h A (fin efficiency <= 1)")
ok(abs(tb.film_body_g_air(1e-6) / (1e-6 * area) - 1) < 1e-3, "g_air -> h A as h -> 0 (isothermal body)")
ok(0.80 < tb.film_body_g_air(10) / (10 * area) < 0.83, f"h 10: {tb.film_body_g_air(10) / (10 * area):.3f} of h A")
ok(tb.film_body_g_air(0) == 0.0, "no air path at h 0")
# TDK's own rating: 5.4 A at 100 kHz, ESR typ 14.0 mOhm, self-heating <= 20 K (p.14) => >= 0.0204 W/K body-to-ambient
ok(tb.film_body_g_air(10) < 5.4 ** 2 * 0.014 / 20.0, "h-10 path is below the conductance implied by TDK's 20 K rating")

ok(tb.FILM_HF_AIR_RISE_K == 15.0, "film_hf body air defaults to bay + 15 K (board-heated air, jet-2026-10-15)")
# the committed release case equals the cap-air +15 K sensitivity (zero-area region crediting C38-C41 at bay + 15 K)
import json  # noqa: E402
cap_air = HERE / "jet-2026-10-15/cap-air.json"
margins = json.loads((HERE / "margins.json").read_text())
REL = next(c for c, v in gate.BASIS.items() if v["role"] == "release")
if REL not in margins["basis"]["cases"] or "copper" in margins["basis"]["cases"][REL]:
    print("skip cap-air.json is a 20 C copper record; margins.json is on hot copper since OPEN-ITEMS S17")
elif cap_air.exists():
    sens = json.loads(cap_air.read_text())["cases"].get("c18_h10@61 cap air +15 K")
    rel = {r["item"]: r["margin_k"] for r in margins["cases"]["c18_h10"]}
    ok(sens is not None and all(abs(rel[k] - v) <= 0.05 for k, v in sens["rows"].items()),
       "margins.json c18_h10 reproduces cap-air.json's +15 K rows")
g_s = tb.film_strong_coupling_g()
ok(g_s > 50 * tb.film_body_g_air(10), f"strong tie {g_s:.3f} W/K >> body-to-air {tb.film_body_g_air(10):.4f} W/K")
b = tb.film_top_bound_rise(60.0, 0.05, tb.film_body_g_air(10))
ok(60.0 - 1.0 < b < 60.0, f"strong-tie bound sits within 1 K of the hot pad (60 K rise -> {b:.2f} K)")
ok(abs(tb.film_top_bound_rise(60.0, 0.05, 0.0) - (60.0 + 0.05 / g_s)) < 1e-12, "no air path: hot pad + P / g_strong")

# ---- region solve: h_top == h with air at the bay is the still-air model, bit for bit; energy closes with a region
nx = ny = 40
board = np.ones((nx, ny), bool)
k = np.full((2, nx, ny), tb.K_CU)
thk = np.array([70e-6, 70e-6])
heat = np.zeros((2, nx, ny))
heat[0, 20, 20] = 0.5
pitch_m = 0.5e-3
part = tb.NetPart("P", 0.2, "test")
part.groups.append((np.array([10 * ny + 10]), np.array([1.0]), 0.05, "pad"))
part.g_air = 0.01
links = [(0, 5, 5, 1, 0.3)]
r0, j0, rec0 = tb.solve_system(board, k, thk, heat, 10.0, pitch_m, links, [part])
mask = np.zeros((nx, ny), bool)
mask[15:30, 15:30] = True
r1, j1, rec1 = tb.solve_system(board, k, thk, heat, 10.0, pitch_m, links, [part], top_region=(mask, 10.0, 0.0))
ok(np.array_equal(r0, r1) and np.array_equal(j0, j1), "region at h_top = h, air at the bay: identical solution")
r2, j2, rec2 = tb.solve_system(board, k, thk, heat, 10.0, pitch_m, links, [part], top_region=(mask, 100.0, 0.0))
ok(r2[0][20, 20] < r0[0][20, 20] and abs(rec2["balance_rel"]) < 1e-8, f"h_top 100 cools the region; balance "
   f"{rec2['balance_rel']:.1e}")
part.t_air = -5.0
r3, j3, rec3 = tb.solve_system(board, k, thk, heat, 10.0, pitch_m, links, [part], top_region=(mask, 100.0, -5.0))
ok(r3[0][20, 20] < r2[0][20, 20] and abs(rec3["balance_rel"]) < 1e-8, f"cooler jet air cools further; balance "
   f"{rec3['balance_rel']:.1e}")
reg = tb.TopRegion(rb.JET_REGION, 60.0)
ok(reg.contains(38.5, 12.6) and not reg.contains(31.7, 28.2), "R5 is centred in the jet region, C40 is not")

# ---- case grammar and roles
ok(gate.case_ceiling_h("c18_h10") == (18.0, 10) and gate.case_jet("c18_h10") is None, "still-air case parses")
ok(gate.case_ceiling_h("c28_h10_jet100") == (28.0, 10) and gate.case_jet("c28_h10_jet100") == {"h_top": 100.0,
   "air_c": None}, "jet case parses")
ok(gate.case_jet("c26_h10_jet35a50") == {"h_top": 35.0, "air_c": 50.0}, "jet case with its own air temperature")
try:
    gate.case_ceiling_h("c28_jet100")
    ok(False, "a malformed case is refused")
except SystemExit:
    ok(True, "a malformed case is refused")
try:
    gate.run(HERE, ["c28_h10_jet100@61"], None, ["c28_h10_jet100"])
    ok(False, "an airflow case cannot be a release case")
except SystemExit as e:
    ok("cannot be release" in str(e), "an airflow case cannot be a release case")
try:
    gate.parse_cases("c28_h10_jet35@55,c28_h10_jet35@61", None)
    ok(False, "one case at two bays is refused (its run files would collide)")
except SystemExit:
    ok(True, "one case at two bays is refused (its run files would collide)")
ok(all(b["role"] != "airflow" and gate.case_jet(c) is None for c, b in gate.BASIS.items()),
   "the default BASIS has no airflow case")

# ---- one region definition, and the jet-strip keep-out covers it
x0, x1, y0, y1 = rb.JET_REGION
g0, g1, h0, h1 = jsh.REGION
ok(g0 <= x0 and x1 <= g1 and h0 <= y0 and y1 <= h1, f"jet_strip_height keep-out {jsh.REGION} contains the B3 jet "
   f"region {rb.JET_REGION}")

# ================================================================ PS2 module body-to-air path and its rating row (S18)
import tempfile  # noqa: E402
from shapely.geometry import box as sbox  # noqa: E402

# ---- controls
ok(abs(tb.module_body_area_mm2() - (52.4 * 27.2 + 2 * (52.4 + 27.2) * 24.0)) < 1e-9,
   f"PS2 exposed area = top + four sides of the p.2 52.4 x 27.2 x 24 mm case ({tb.module_body_area_mm2():.0f} mm^2)")
ok(abs(tb.module_body_g_air(10) - 10 * tb.module_body_area_mm2() * 1e-6) < 1e-15 and tb.module_body_g_air(0) == 0.0,
   f"isothermal potted case: g_air = h A ({tb.module_body_g_air(10):.4f} W/K at h 10), none at h 0")
ok(tb.MODULE_AIR_RISE_K == tb.FILM_HF_AIR_RISE_K == 15.0, "PS2 air = bay + 15 K, the film caps' rule (one value)")
ok(abs(tb.layer_factor(17.5) - 0.24) < 0.005 and abs(tb.layer_factor(24.0) - 0.178) < 0.001,
   f"layer factor: {tb.layer_factor(17.5):.3f} at the caps' 17.5 mm (the rule's 0.24), {tb.layer_factor(24.0):.3f} at 24 mm")
ok(tb.SPECS["meanwell"]["body_air"] == "module_box", "the meanwell class has a body-to-air path")
heat28 = json.loads((HERE.parent / "b3/inputs/native21-board-heat-sources-c28.json").read_text())
ps2 = next(p for p in heat28["parts"] if p["ref"] == "PS2")
i_ch = (382.6e-9 + 61e-9) * 60e3 + 0.0044 + 0.003 + 0.0015 + 0.014      # make_heat_sources C28_F (C55 etc. 4.7 nF: +61 nC)
p_out = 2 * 17.0 * i_ch / 0.45 + 24 * (2 * i_ch + 0.030) + 24 * 0.010
M = gate.MODULES["PS2"]
ok(abs(ps2["watts_nominal"] - p_out * (1 / M["eta_heat"] - 1)) < 1e-9 and abs(p_out - 7.08) < 0.005,
   f"control: c28 heat row = P_out (1/{M['eta_heat']} - 1) at the make_heat_sources load {p_out:.3f} W "
   f"({ps2['watts_nominal']:.4f} W); the gate's P_out back-out is exact")
ok(ps2["board_fraction"] + ps2["sink_fraction"] == 1.0, "the heat row's board + case shares cover the whole loss")
ok(gate.bom_mpns()["PS2"] == M["mpn"], "the frozen BOM places MPM-20-24 at PS2")
pts = [gate.curve_ambient_limit(L, M["curve"], M["t_max_c"]) for L in (100.0, 70.0, 50.0, 30.0, 10.0)]
ok(pts == [55.0, 60.0, 70.0, 85.0, 85.0], f"p.3 curve points read back: {pts}")
lim_as_built = gate.curve_ambient_limit(100 * p_out / 21.6 / 0.9, M["curve"], M["t_max_c"])
ok(abs(gate.curve_ambient_limit(100 * p_out / 21.6, M["curve"], M["t_max_c"]) - 82.9) < 0.05 and abs(lim_as_built - 80.2) < 0.05,
   f"limit at 7.08 W: 82.9 C on the curve, {lim_as_built:.1f} C under the 90 % rule")

# ---- the network: whole loss into the body node, pins + case-to-air; the pins-only control is the pre-S18 model
class FakeBoard:
    def pads_of(self, ref):
        return {str(n): [("F.Cu", sbox(x - 1, y - 1, x + 1, y + 1))] for n, (x, y) in
                {1: (163.7, 3.6), 2: (163.7, 24.4), 3: (208.7, 3.6), 4: (208.7, 11.6)}.items()}


FP = {"PS2": {"fp": "Converter_ACDC:Converter_ACDC_MeanWell_IRM-20-xx_THT", "mpn": "MPM-20-24", "at": [163.7, 3.6],
              "fab": [-3.4, -3.2, 49.0, 24.0], "layer": "F.Cu"}}
NX, NY, X0, Y0, PITCH = 80, 40, 150.0, -5.0, 1.0


def build(sens, row=None):
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "heat.json"
        f.write_text(json.dumps({"parts": [row or ps2]}))
        return tb.build_network_parts(FakeBoard(), f, "nominal", 1, NX, NY, X0, Y0, PITCH, 0, 0, 10.0, FP, sens,
                                      lambda x, y: True)[0][0]


mod, pins = build({}), build({"module_pins_only": True})
ok(abs(mod.watts - ps2["watts_nominal"]) < 1e-12 and abs(mod.g_air - tb.module_body_g_air(10)) < 1e-15 and
   mod.t_air == 15.0 and mod.meta["body_air_model"] == "module_box",
   f"module: the body node carries the whole {mod.watts:.3f} W, case to air at bay + 15 K")
ok(abs(pins.watts - 0.5 * ps2["watts_nominal"]) < 1e-12 and pins.g_air == 0.0 and pins.t_air == 0.0 and
   "body_air_model" not in pins.meta and len(pins.groups) == len(mod.groups),
   "control: module_pins_only is the pre-S18 network (half the loss, pins only)")
ok(abs(sum(g for _, _, g, _ in mod.groups) - 1 / 15.0) < 1e-12, "the pin path is the class 15 K/W, split by pad area")
ok(max(abs(a - b) for a, b in zip(tb.body_box_mm(FP["PS2"]), (160.3, 0.4, 212.7, 27.6))) < 1e-9,
   "body box = footprint origin (pin 1) + F.Fab offsets: 52.4 x 27.2 mm")
gap = build({"module_gap_mm": 1.0})
gg = [g for _, _, g, t in gap.groups if t == "gap"]
ok(len(gap.groups) == len(mod.groups) + len(gg) and all(len(gi) == 1 for gi, _, _, t in gap.groups if t == "gap") and
   abs(sum(gg) - tb.K_AIR * 52.4 * 27.2 * 1e-6 / 1e-3) < 1e-3 * sum(gg),
   f"sensitivity: the bottom-face gap ties each cell under the body box locally ({len(gg)} ties, {sum(gg):.4f} W/K)")
bd = np.ones((NX, NY), bool)
kk = np.full((1, NX, NY), tb.K_FR4 + 0.2 * (tb.K_CU - tb.K_FR4))
rs_, rj, rec = tb.solve_system(bd, kk, np.array([1.6e-3]), np.zeros((1, NX, NY)), 10.0, 1e-3, [], [mod])
flat = rs_.ravel()
q_pins = sum(g * (rj[0] - float((flat[gi] * w).sum())) for gi, w, g, _ in mod.groups)
q_air = mod.g_air * (rj[0] - mod.t_air)
ok(abs(q_pins + q_air - mod.watts) < 1e-9 and abs(rec["balance_rel"]) < 1e-8 and q_pins > 0 and q_air > 0,
   f"both paths carry heat: pins {q_pins:.3f} W + air {q_air:.3f} W = {mod.watts:.3f} W (balance {rec['balance_rel']:.0e})")

# ---- the gate row: rates local air, never the pad
def mrun(pins_w=0.4, ring=70.0, air=15.0, model="module_box", loss=None, sens=None, case=90.0):
    p = {"ref": "PS2", "spec": "meanwell", "body_air_model": model, "loss_w": loss or ps2["watts_nominal"],
         "module_air_rise_k": air, "pins_w": pins_w, "board_ring_c": ring, "layer_factor": tb.layer_factor(24.0),
         "case_c": case, "pad_max_cell_c": 100.0, "env_upper_c": 80.0}
    if model is None:
        p = {k: v for k, v in p.items() if k in ("ref", "spec", "pad_max_cell_c")}
    return {"parts": [p], "sens": sens or {}}


BOM = {"PS2": "MPM-20-24"}
r = gate.module_rows("c", mrun(), mrun(), 61.0, mpns=BOM)[0]
ok(r["gated"] and abs(r["est_c"] - 76.0) < 1e-9 and abs(r["limit_c"] - lim_as_built) < 1e-9 and r["pad_max_c"] == 111.0,
   f"row: local air 76.0 C (bay 61 + 15) vs {r['limit_c']:.1f} C; the 111 C pad is reported, not rated")
r = gate.module_rows("c", mrun(ring=160.0), mrun(ring=160.0), 61.0, mpns=BOM)[0]
ok(abs(r["est_c"] - (61.0 + tb.layer_factor(24.0) * (160.0 + 11.0 - 61.0))) < 1e-9 and r["air_layer_k"] > 15,
   f"a board ring hot enough to beat the 15 K rule sets the air ({r['est_c']:.1f} C)")
ok(gate.module_rows("c", mrun(model=None, sens={"module_pins_only": True}), mrun(model=None, sens={"module_pins_only": True}),
                    61.0, mpns=BOM, allow_pins_only=True) == [], "control: pins-only runs carry no row (pre-S18 margins)")
# ---- refusals
bad_split = {**ps2, "sink_fraction": 0.4}
try:
    build({}, bad_split)
    ok(False, "a module heat row whose shares do not cover the loss is refused")
except ValueError:
    ok(True, "a module heat row whose shares do not cover the loss is refused")
try:
    tb.body_box_mm({"at": [0, 0, 90], "fab": [0, 0, 1, 1]})
    ok(False, "a rotated body box is refused, not guessed")
except NotImplementedError:
    ok(True, "a rotated body box is refused, not guessed")
for name, a, b, kw in (("pins-only runs without --allow-module-pins-only",
                        mrun(model=None, sens={"module_pins_only": True}), mrun(model=None, sens={"module_pins_only": True}), {}),
                       ("old runs with no body model, even with the control flag", mrun(model=None), mrun(model=None),
                        {"allow_pins_only": True}),
                       ("pins carrying heat into the module", mrun(pins_w=-0.01), mrun(), {}),
                       ("meshes at different air rules", mrun(air=15.0), mrun(air=10.0), {}),
                       ("a load over the 90 % rule at any ambient", mrun(loss=20.0 * (1 / 0.84 - 1)),
                        mrun(loss=20.0 * (1 / 0.84 - 1)), {}),
                       ("another module MPN on the BOM", mrun(), mrun(), {"mpns": {"PS2": "IRM-20-24"}})):
    try:
        gate.module_rows("c", a, b, 61.0, **{"mpns": BOM, **kw})
        ok(False, f"PS2 row refuses: {name}")
    except SystemExit:
        ok(True, f"PS2 row refuses: {name}")

print(f"\n{fails} failure(s)")
sys.exit(1 if fails else 0)
