#!/usr/bin/env python3
"""Option P: the committed heartbeat-pump deck (c24-monitor-fmea m1_pump_spice.py, design J) driven as P drives it.

    python3 -I pump_p_spice.py [PS_ROOT]   -> results/pump_p_spice.json (needs ngspice on PATH)

Under P, U46 = NAND(A = PERMIT via R135 10 k, B = heartbeat). PERMIT low -> U46.Y static HIGH (whatever the heartbeat
does), so the pump always rests with its input high; PERMIT high -> U46.Y = NOT heartbeat (a square wave). The deck,
the BAT54 model, the G17 (U40) thresholds, the oscillator period range and the corner set are imported unchanged from
the committed script, so this inherits its datasheet basis (SCES351Y, DS11005, SCES546E).

Waveform per corner:  static high 0..T0 (PERMIT low since power-up) | wave T0..T1 (first start) |
                      static high T1..T1+T_OFF (PERMIT pulse low) | wave from T1+T_OFF (restart) to the end.
Measured:  t_start1  T0 -> hold >= VT+max(VCC)           (BIAS_GOOD can assert; first start from rest-high)
           t_trip    T1 -> hold <= VT-min(VCC)           (PERMIT stop path through the heartbeat; None if T_OFF too short)
           t_start2  T1+T_OFF -> hold >= VT+max(VCC)     (restart after a short PERMIT low)
           margin    min(hold) over the last 50 us - VT+max (the committed 'start' check, > 0.1 V passes)
The PERMIT phase relative to the heartbeat is swept (0 and half a period).
"""
import importlib.util
import itertools
import json
import re
import subprocess
import sys
import tempfile
from multiprocessing import Pool
from pathlib import Path

sys.dont_write_bytecode = True   # read-only on the repo: no __pycache__ beside the imported scripts

HERE = Path(__file__).resolve().parent
PS = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    "/Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/power-stage-120v")
SRC = PS / "validation-results/11-candidates/c24-monitor-fmea/scripts/m1_pump_spice.py"
spec = importlib.util.spec_from_file_location("m1", SRC)
m1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m1)

T0, T1 = 100e-6, 300e-6
T_OFFS = (5e-6, 30e-6, 1e-3)
TAIL = 200e-6
EXTRA = """meas tran tup1 WHEN v(hold)={vtp} TD={t0} RISE=1
meas tran ttrip WHEN v(hold)={vtm} TD={t1} FALL=1
meas tran tup2 WHEN v(hold)={vtp} TD={t2} RISE=1
meas tran hend MIN v(hold) from={e0} to={e1}
meas tran hoff MIN v(hold) from={t1} to={t2}
"""


def run(deck):
    with tempfile.NamedTemporaryFile("w", suffix=".cir", delete=False) as fh:
        fh.write(deck)
    r = subprocess.run(["ngspice", "-b", fh.name], capture_output=True, text=True, timeout=900)
    Path(fh.name).unlink()
    vals = {}
    for k in ("tup1", "ttrip", "tup2", "hend", "hoff"):
        m = re.search(rf"^{k}\s*=\s*([-+0-9.eE]+)", r.stdout, re.M)
        vals[k] = float(m.group(1)) if m else None
    return vals


def one(args):
    design, vcc, temp, per, rout_i, ileak, shorted, phase, toff = args
    rs, cc, rb, rx, drv = m1.DESIGNS[design]
    rout = m1.DRIVERS[drv][0][rout_i]
    th = m1.g17_th(vcc)
    t0 = T0 + phase * per
    t2 = T1 + toff
    tend = t2 + TAIL
    wave = (f"(time < {t0}) ? {vcc} : ((time < {T1}) ? v(clk) : ((time < {t2}) ? {vcc} : v(clk)))")
    deck = m1.DECK.format(temp=temp, per=per, ton=per / 2, tstop=T1, vcc=vcc, wave=wave, rout=rout, ileak=ileak,
                          tend=tend, m0=t2, m1=tend, vtp=th["vtp_max"], trip="",
                          rs=max(rs, 1e-3), cc=cc, cc2=(1e-3 if shorted else cc), rb=rb,
                          rx=(f"Rx x 0 {rx}" if rx else ""))
    deck = deck.replace("meas tran tup WHEN", "* (unused) meas tran tup WHEN")
    deck = deck.replace("quit", EXTRA.format(vtp=th["vtp_max"], vtm=th["vtm_min"], t0=t0, t1=T1, t2=t2,
                                             e0=tend - 50e-6, e1=tend) + "quit")
    v = run(deck)
    us = lambda t, ref: None if t is None else round((t - ref) * 1e6, 2)
    return dict(design=design, pump_cap_shorted=shorted, vcc2=vcc, temp_C=temp, osc_period_us=round(per * 1e6, 3),
                r_out=rout, i_leak_uA=ileak * 1e6, phase=phase, t_off_us=round(toff * 1e6, 1),
                t_start1_us=us(v["tup1"], t0), t_trip_us=us(v["ttrip"], T1), t_start2_us=us(v["tup2"], t2),
                margin_end_V=None if v["hend"] is None else round(v["hend"] - th["vtp_max"], 3),
                hold_min_during_off_V=None if v["hoff"] is None else round(v["hoff"], 3),
                stayed_above_vtp_max=v["hoff"] is not None and v["hoff"] >= th["vtp_max"],
                g17_vtp_max=round(th["vtp_max"], 3), g17_vtm_min=round(th["vtm_min"], 3))


def main():
    pmin, pmax = m1.osc_periods()
    jobs = [("J", *c) for c in itertools.product((3.135, 3.465), (-40, 25, 125), (pmin, pmax), (0, 1),
                                                 (-5e-6, 5e-6), (False, True), (0.0, 0.5), T_OFFS)]
    with Pool(8) as pool:
        rows = pool.map(one, jobs)
    summ = {}
    for shorted in (False, True):
        for toff in T_OFFS:
            rr = [r for r in rows if r["pump_cap_shorted"] == shorted and r["t_off_us"] == round(toff * 1e6, 1)]
            key = f"J{'+1short' if shorted else ''} T_OFF={round(toff * 1e6, 1)}us"
            def mx(k):
                vals = [r[k] for r in rr if r[k] is not None]
                return max(vals) if vals else None
            summ[key] = dict(corners=len(rr),
                             t_start1_us_max=mx("t_start1_us"),
                             t_start1_us_min=min(r["t_start1_us"] for r in rr),
                             t_start2_us_max=mx("t_start2_us"),
                             restart_not_needed=sum(r["stayed_above_vtp_max"] for r in rr),
                             restart_missing=sum(r["t_start2_us"] is None and not r["stayed_above_vtp_max"] for r in rr),
                             t_trip_us_max=mx("t_trip_us"),
                             t_trip_none=sum(r["t_trip_us"] is None for r in rr),
                             margin_end_V_min=min(r["margin_end_V"] for r in rr))
    out = dict(source_deck=str(SRC.relative_to(PS)), design="J", osc_period_us=[round(pmin * 1e6, 3), round(pmax * 1e6, 3)],
               summary=summ, rows=rows)
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results/pump_p_spice.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(summ, indent=1))
    bad = [k for k, s in summ.items() if s["margin_end_V_min"] <= 0.1 or s["restart_missing"]
           or any(r["t_start1_us"] is None for r in rows)]
    print("FAIL" if bad else "PASS", bad)
    raise SystemExit(1 if bad else 0)


if __name__ == "__main__":
    main()
