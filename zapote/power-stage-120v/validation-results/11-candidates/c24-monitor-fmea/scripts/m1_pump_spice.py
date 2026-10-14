#!/usr/bin/env python3
"""Candidate 24 / M1: ngspice corner sweep of the SELV heartbeat charge pump (FMEA.md condition 2).

    python3 -I validation-results/11-candidates/c24-monitor-fmea/scripts/m1_pump_spice.py
    -> results/m1_pump_spice.json, exit 1 if any corner fails a check

Circuit (FMEA.md section 2, "P2 + M1"): U32 ISO7710 OUT (square wave, VCC2 = J4.3 3.3 V rail, output resistance R_OUT)
-> 100 nF + 100 nF in series -> node X; BAT54S: shunt diode GND->X, series diode X->HOLD; C_hold 1 nF || R_bleed 100 k;
HOLD -> U40 SN74LVC1G17 input (input leakage I_LEAK, either sign). The wave stops at T_STOP (stuck low or stuck high).

Datasheet bases (texts in evidence/ds, sha256 in MANIFEST.txt; BAT54 fetched 2026-10-14, Diodes DS11005, sha256 50b04e4e...):
- ISO7710 (SLLSER9E 5.11, 3.3 V supply): VOH >= VCC2 - 0.3 V at -2 mA -> R_OUT <= 150 ohm (50 ohm also run).
- SN74LVC1G17 (SCES351Y Table 5-1, -40..125 C): at 3 V VT+ 1.48-1.92, VT- 0.89-1.20; at 4.5 V VT+ 2.19-2.74, VT- 1.51-1.97.
  Thresholds at VCC2 are linearly interpolated between the 3 V and 4.5 V rows (assumption, stated in the output).
  II = +-5 uA (0..5.5 V).
- SN74LVC1G132 (SCES546E 5.5, -40..125 C) on LS 5 V (taken as 4.75-5.25 V): VT+ 2.16-2.74 / 2.61-3.33 and VT- 1.41-1.84 /
  1.87-2.33 at 4.5 / 5.5 V, interpolated. Oscillator 4.99 k (1 %) / 330 pF (C0G 5 %): period range below.
- BAT54 (Diodes DS11005 Electrical Characteristics, max at 25 C): VF <= 240 mV @0.1 mA, 320 @1 mA, 400 @10 mA, 500 @30 mA.
  Model fitted to those MAXIMA (N 1.25, IS 5.7e-8, RS 1.2 -> 240 / 314 / 400 / 460 mV), EG 0.69, XTI 2 for temperature.
Designs: see DESIGNS. "fmea" is FMEA.md's hand-sized M1 (pump driven by U32 directly, 2 x 100 nF, 100 k bleed).
CHOSEN (the exit code gates on it) is the design adopted in FMEA.md section 6a.
Checks per corner:
  start: hold settles above VT+max(VCC2) (BIAS_GOOD can assert)        margin_start_V = min(hold, last 50 us) - VT+max
  run:   one dropped heartbeat period never brings hold below VT-max   margin_missed_V
  trip:  wave stopped -> hold below VT-min(VCC2) within LIMIT_US       t_trip_us
  drive: steady-state ISO7710 output current peak                      i_out_ss_mA (report; IOH/IOL rec. 2 mA)
"""
import itertools
import json
import math
import re
import subprocess
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "results" / "m1_pump_spice.json"
LIMIT_US = 150.0
CHOSEN = "J"               # design the exit code gates on (set after the sweep; see summary)            # trip budget used here; FMEA hand figure 89 us; rail faults are ms-scale (FMEA 1)

def interp(v, lo, hi):      # (vcc, value) rows
    (v0, a), (v1, b) = lo, hi
    return a + (b - a) * (v - v0) / (v1 - v0)

def g17_th(vcc):
    return dict(vtp_max=interp(vcc, (3.0, 1.92), (4.5, 2.74)), vtm_min=interp(vcc, (3.0, 0.89), (4.5, 1.51)),
                vtm_max=interp(vcc, (3.0, 1.20), (4.5, 1.97)))

def osc_periods():
    per = []
    for vcc in (4.75, 5.25):
        tp = [interp(vcc, (4.5, 2.16), (5.5, 2.61)), interp(vcc, (4.5, 2.74), (5.5, 3.33))]
        tm = [interp(vcc, (4.5, 1.41), (5.5, 1.87)), interp(vcc, (4.5, 1.84), (5.5, 2.33))]
        for vtp, vtm, r, c in itertools.product(tp, tm, (4.99e3 * 0.99, 4.99e3 * 1.01), (330e-12 * 0.95, 330e-12 * 1.05)):
            if vtp - vtm < 0.3:                     # hysteresis floor (>= 0.66 V min at 4.5 V): skip non-physical pairs
                continue
            per.append(r * c * (math.log((vcc - vtm) / (vcc - vtp)) + math.log(vtp / vtm)) + 2 * 7e-9)
    return min(per), max(per)

DECK = """* M1 pump corner
.temp {temp}
.model bat54m D(IS=5.7e-8 N=1.25 RS=1.2 CJO=10p M=0.5 EG=0.69 XTI=2 BV=30)
.param per={per} ton={ton} tstop={tstop}
Vclk clk 0 PULSE(0 {vcc} 0 2n 2n {{ton}} {{per}})
Bsrc src 0 V = {wave}
Rout src out {rout}
Vsense out out_s 0
Rs out_s s1 {rs}
C1 s1 m {cc}
C2 m x {cc2}
{rx}
Dsh 0 x bat54m
Dser x hold bat54m
Chold hold 0 1n
Rbleed hold 0 {rb}
Ileak 0 hold DC {ileak}
.tran 5n {tend} 0 5n
.control
run
meas tran hmin MIN v(hold) from={m0} to={m1}
meas tran hmax MAX v(hold) from={m0} to={m1}
meas tran ipk MAX i(Vsense) from={m0} to={m1}
meas tran imn MIN i(Vsense) from={m0} to={m1}
meas tran tup WHEN v(hold)={vtp} RISE=1
{trip}
quit
.endc
.end
"""

def run(deck):
    with tempfile.NamedTemporaryFile("w", suffix=".cir", delete=False) as fh:
        fh.write(deck)
    r = subprocess.run(["ngspice", "-b", fh.name], capture_output=True, text=True, timeout=600)
    Path(fh.name).unlink()
    vals = {}
    for k in ("hmin", "hmax", "ipk", "imn", "tup", "ttrip"):
        m = re.search(rf"^{k}\s*=\s*([-+0-9.eE]+)", r.stdout, re.M)
        vals[k] = float(m.group(1)) if m else None
    return vals

# name: (series R, each pump cap, R_bleed, X-to-GND R or None, pump driver)
# driver "iso": U32 ISO7710 OUT drives the pump directly (R_OUT 50 / 150 ohm; recommended |IO| <= 2 mA at 3.3 V,
#   SLLSER9E 5.3; absolute maximum 15 mA, 6.1).
# driver "g17": U32 OUT -> a SN74LVC1G17 buffer on the 3.3 V rail -> pump. R_OUT 10 / 37.5 ohm (VOH >= 2.4 V at
#   -16 mA at 3 V, SCES351Y 5.5; recommended |IO| <= 24 mA at 3 V, 5.3; absolute maximum 50 mA, 5.1). Limit used: 16 mA.
DRIVERS = {"iso": ((50, 150), 2.5), "g17": ((10, 37.5), 16.0)}
DESIGNS = {
    "fmea": (0, 100e-9, 100e3, None, "iso"),
    "A": (1.5e3, 2.2e-9, 47e3, None, "iso"),
    "B": (1.5e3, 1.0e-9, 47e3, None, "iso"),
    "C": (1.0e3, 2.2e-9, 47e3, None, "iso"),
    "D": (1.5e3, 2.2e-9, 68e3, None, "iso"),
    "E": (1.5e3, 2.2e-9, 47e3, 22e3, "iso"),
    "F": (220, 1.0e-9, 47e3, None, "g17"),
    "G": (220, 2.2e-9, 47e3, None, "g17"),
    "H": (220, 1.0e-9, 33e3, None, "g17"),
    "I": (1e3, 1.0e-9, 49.9e3, None, "g17"),     # existing BOM lines only (1 k, 1 nF C0G, 49.9 k)
    "J": (220, 1.0e-9, 49.9e3, None, "g17"),
}


def one(args):
    design, vcc, temp, per, rout, ileak, stuck, shorted = args
    rs, cc, rb, rx, drv = DESIGNS[design]
    rout = DRIVERS[drv][0][rout]
    i_max = DRIVERS[drv][1]
    par = dict(rs=max(rs, 1e-3), cc=cc, cc2=(1e-3 if shorted else cc), rb=rb, rx=(f"Rx x 0 {rx}" if rx else ""))
    th = g17_th(vcc)
    tstop = 200e-6
    wave = f"time < {tstop} ? v(clk) : {vcc if stuck == 'high' else 0}"
    trip = f"meas tran ttrip WHEN v(hold)={th['vtm_min']:.4f} TD={tstop} FALL=1"
    v = run(DECK.format(temp=temp, per=per, ton=per / 2, tstop=tstop, vcc=vcc, wave=wave, rout=rout, ileak=ileak,
                        tend=tstop + 1000e-6, m0=tstop - 50e-6, m1=tstop - 1e-6, vtp=th["vtp_max"], trip=trip, **par))
    tm0, tm1 = 150e-6, 150e-6 + per
    wave_m = f"(time > {tm0} && time < {tm1}) ? 0 : v(clk)"
    vm = run(DECK.format(temp=temp, per=per, ton=per / 2, tstop=tstop, vcc=vcc, wave=wave_m, rout=rout, ileak=ileak,
                         tend=tstop, m0=tm0, m1=tm0 + 10e-6, vtp=th["vtp_max"], trip="", **par))
    t_trip = None if v["ttrip"] is None else (v["ttrip"] - tstop) * 1e6
    row = dict(design=design, pump_cap_shorted=shorted, vcc2=vcc, temp_C=temp, osc_period_us=round(per * 1e6, 3), r_out=rout,
               i_leak_uA=ileak * 1e6, stuck=stuck, hold_min_V=round(v["hmin"], 3), hold_max_V=round(v["hmax"], 3),
               g17_vtp_max=round(th["vtp_max"], 3), g17_vtm_min=round(th["vtm_min"], 3), g17_vtm_max=round(th["vtm_max"], 3),
               margin_start_V=round(v["hmin"] - th["vtp_max"], 3), margin_missed_V=round(vm["hmin"] - th["vtm_max"], 3),
               t_startup_us=None if v["tup"] is None else round(v["tup"] * 1e6, 2),
               t_trip_us=None if t_trip is None else round(t_trip, 1),
               i_out_ss_mA=round(max(abs(v["ipk"]), abs(v["imn"])) * 1e3, 3))
    bad = []
    if row["margin_start_V"] <= 0.1: bad.append("start margin <= 0.1 V")
    if row["margin_missed_V"] <= 0.1: bad.append("missed-pulse margin <= 0.1 V")
    if t_trip is None or t_trip > LIMIT_US: bad.append(f"trip > {LIMIT_US} us")
    if row["i_out_ss_mA"] > i_max: bad.append(f"pump driver output peak > {i_max} mA")
    row["fail"] = bad
    return row


def main():
    from multiprocessing import Pool
    pmin, pmax = osc_periods()
    jobs = []
    for design in DESIGNS:
        for shorted in (False, True):
            for c in itertools.product((3.135, 3.465), (-40, 25, 125), (pmin, pmax), (0, 1), (-5e-6, 5e-6), ("low", "high")):
                jobs.append((design, *c, shorted))
    with Pool(8) as pool:
        allrows = pool.map(one, jobs)
    designs = {}
    for design in DESIGNS:
        for shorted in (False, True):
            rows = [r for r in allrows if r["design"] == design and r["pump_cap_shorted"] == shorted]
            fails = [r for r in rows if r["fail"]]
            def worst(k, f=min):
                r = f(rows, key=lambda r: (r[k] if r[k] is not None else 1e9))
                return {k: r[k], "corner": {x: r[x] for x in ("vcc2", "temp_C", "osc_period_us", "r_out", "i_leak_uA", "stuck")}}
            designs[f"{design}{'+1short' if shorted else ''}"] = dict(
                params=dict(zip(("r_series", "pump_cap_each", "r_bleed", "r_x_to_gnd", "driver"), DESIGNS[design])),
                corners=len(rows), fails=len(fails), fail_kinds=sorted({k for r in fails for k in r["fail"]}),
                worst_start_margin=worst("margin_start_V"), worst_missed_margin=worst("margin_missed_V"),
                worst_trip=worst("t_trip_us", max), worst_startup=worst("t_startup_us", max),
                worst_iout_ss=worst("i_out_ss_mA", max))
    summ = dict(osc_period_us=[round(pmin * 1e6, 3), round(pmax * 1e6, 3)], limit_trip_us=LIMIT_US,
                drivers=DRIVERS, designs=designs,
                assumptions=["G17 thresholds linearly interpolated between the 3 V and 4.5 V rows",
                             "BAT54 model fitted to Diodes DS11005 VF maxima at 25 C; temperature by EG/XTI",
                             "LS 5 V taken as 4.75-5.25 V; G132 thresholds interpolated 4.5-5.5 V",
                             "ISO7710 modelled as ideal edges behind R_OUT 50/150 ohm; its 11 ns delay is irrelevant here",
                             "'+1short' = one of the two series pump caps shorted (FMEA H10, a first fault that is otherwise silent)"])
    OUT.write_text(json.dumps({"summary": summ, "rows_chosen_design": [r for r in allrows if r["design"] == CHOSEN]},
                              indent=1) + "\n")
    for k, d in designs.items():
        print(k, d["params"], "fails", d["fails"], d["fail_kinds"], "| start", d["worst_start_margin"]["margin_start_V"],
              "missed", d["worst_missed_margin"]["margin_missed_V"], "trip", d["worst_trip"]["t_trip_us"],
              "iout", d["worst_iout_ss"]["i_out_ss_mA"])
    base = [d for k, d in designs.items() if k == CHOSEN][0]
    raise SystemExit(1 if base["fails"] else 0)


if __name__ == "__main__":
    main()
