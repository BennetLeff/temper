#!/usr/bin/env python3
"""Jet bench host logger: reads logger_fw/jet_logger_fw.ino over USB, runs the guard loop, writes 1 Hz run CSVs.

  pip install pyserial
  python jet_logger.py --port /dev/cu.usbmodem1101 --run d055_r1 --condition d055 --minutes 30
  python jet_logger.py --port ... --run gap_plus3 --condition d055 --guard-offset 3 --minutes 30
  python jet_logger.py --selftest          # parser + guard loop on synthetic data; no hardware

Writes runs/<run>.csv: '# key: value' header (run, condition, H_mm, guard_offset_K, room_C, flow_slpm, notes,
bench_json_sha256), then one row per second with the RAW converted channels (thermocouples NOT offset-corrected;
fit.py applies bench.json's in-situ offsets, so a later zero run can re-correct old runs):
  t_s, tc0..tc6 (C), cj_C, pt100_C, v_bus_V, i_A, dp_Pa, duty, p_guard_W, marker
The guard loop (GuardPI) holds mean(guard TCs) = mean(plate TCs) + guard_offset_K, using bench.json offsets.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
N_TC = 7
A_RTD, B_RTD = 3.9083e-3, -5.775e-7
COLS = ["t_s"] + [f"tc{i}" for i in range(N_TC)] + ["cj_C", "pt100_C", "v_bus_V", "i_A", "dp_Pa", "duty", "p_guard_W", "marker"]


def load_bench(path: Path = HERE / "bench.json") -> dict:
    p = path if path.exists() else HERE / "bench.example.json"
    return json.loads(p.read_text())


def rtd_C(reg: int, rref: float) -> float:
    r = ((reg >> 1) & 0x7FFF) * rref / 32768.0
    return (-A_RTD + (A_RTD * A_RTD - 4 * B_RTD * (1 - r / 100.0)) ** 0.5) / (2 * B_RTD)


class GuardPI:
    """Guard heater power from the plate-guard temperature error; anti-windup clamp; duty for a 10-bit PWM."""

    def __init__(self, cfg: dict):
        g = cfg["guard"]
        self.kp, self.ki = g["kp_W_per_K"], g["ki_W_per_Ks"]
        self.pmax = g["supply_V"] ** 2 / g["heater_ohm"]
        self.i = 0.0

    def step(self, err_K: float, dt: float) -> tuple[int, float]:
        p_unclamped = self.kp * err_K + self.i + self.ki * err_K * dt
        if 0.0 < p_unclamped < self.pmax:
            self.i += self.ki * err_K * dt
        p = min(max(self.kp * err_K + self.i, 0.0), self.pmax)
        return round(1023 * p / self.pmax), p


class Recorder:
    """Bins device records into 1 s rows of converted values."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.rows, self.bin, self.t0, self.cur = [], {}, None, None
        self.duty, self.p_guard, self.marker, self.faults = 0, 0.0, 0, []

    def _acc(self, key, v):
        s = self.bin.setdefault(key, [0.0, 0])
        s[0] += v
        s[1] += 1

    def handle(self, line: str):
        f = line.strip().split(",")
        if not f or not f[0] or f[0] == "#":
            if "ALARM" in line or "FAULT" in line:
                self.faults.append(line.strip())
            return None
        try:
            t = int(f[1]) * 1e-6
        except (IndexError, ValueError):
            return None
        if self.t0 is None:
            self.t0, self.cur = t, 0
        sec = int(t - self.t0)
        done = None
        if sec > self.cur:
            done = self.flush()
            self.cur = sec
        ina = self.cfg["ina226"]
        if f[0] == "K" and len(f) == 6:
            ch, ltc, cj, sr = int(f[2]), int(f[3]), int(f[4]), int(f[5])
            if sr & 0x01 or sr & 0x02:                       # open / over-under-voltage
                self.faults.append(f"tc{ch} SR=0x{sr:02x}")
            else:
                self._acc(f"tc{ch}", ltc / 128.0)
                self._acc("cj_C", cj / 64.0)
        elif f[0] == "R" and len(f) == 3:
            reg = int(f[2])
            if not reg & 1:
                self._acc("pt100_C", rtd_C(reg, self.cfg["rref_ohm"]))
        elif f[0] == "P" and len(f) == 4:
            self._acc("i_A", int(f[2]) * 2.5e-6 / ina["r_shunt_ohm"] * ina["i_gain"])
            self._acc("v_bus_V", int(f[3]) * 1.25e-3 * ina["v_gain"])
        elif f[0] == "D" and len(f) == 5 and int(f[4]) > 0:
            self._acc("dp_Pa", int(f[2]) / int(f[4]) - self.cfg.get("dp_zero_Pa", 0.0))
        elif f[0] == "G" and len(f) == 3:
            self.duty = int(f[2])
        elif f[0] == "M" and len(f) == 3:
            self.marker = int(f[2])
        return done

    def flush(self):
        if self.cur is None:
            return None
        row = {"t_s": float(self.cur)}
        for k, (s, n) in self.bin.items():
            row[k] = s / n
        row.update(duty=self.duty, p_guard_W=round(self.p_guard, 4), marker=self.marker)
        self.bin = {}
        self.rows.append(row)
        return row


def corrected(row: dict, cfg: dict, names: list[str]) -> float | None:
    vals = []
    for n in names:
        k = f"tc{cfg['tc_channels'][n]}"
        if k not in row:
            return None
        vals.append(row[k] - cfg["tc_offsets_K"].get(n, 0.0))
    return sum(vals) / len(vals)


def write_csv(path: Path, meta: dict, rows: list[dict]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as fh:
        for k, v in meta.items():
            fh.write(f"# {k}: {v}\n")
        fh.write(",".join(COLS) + "\n")
        for r in rows:
            fh.write(",".join("" if r.get(c) is None else (f"{r[c]:.5f}" if isinstance(r.get(c), float) else str(r[c]))
                              for c in COLS) + "\n")


def run(a):
    import serial  # pyserial

    cfg = load_bench()
    cfg_path = HERE / "bench.json" if (HERE / "bench.json").exists() else HERE / "bench.example.json"
    meta = {"run": a.run, "condition": a.condition, "H_mm": a.H_mm, "guard_offset_K": a.guard_offset, "room_C": a.room_C,
            "flow_slpm": a.flow_slpm if a.flow_slpm is not None else "", "notes": a.notes,
            "bench_json_sha256": hashlib.sha256(cfg_path.read_bytes()).hexdigest(), "started": time.strftime("%Y-%m-%d %H:%M:%S")}
    rec, pi = Recorder(cfg), GuardPI(cfg)
    out = HERE / "runs" / f"{a.run}.csv"
    ser = serial.Serial(a.port, 921600, timeout=0.2)
    t_end = time.time() + 60 * a.minutes
    last_save = time.time()
    try:
        while time.time() < t_end:
            line = ser.readline().decode(errors="replace")
            row = rec.handle(line) if line else None
            if row is None:
                continue
            tp = corrected(row, cfg, cfg["plate_tcs"])
            tg = corrected(row, cfg, cfg["guard_tcs"])
            if a.guard and tp is not None and tg is not None:
                duty, rec.p_guard = pi.step(tp + a.guard_offset - tg, 1.0)
                ser.write(f"G {duty}\n".encode())
            elif not a.guard:
                ser.write(b"G 0\n")
            ta = corrected(row, cfg, [cfg["jet_air_tc"]])
            p = row.get("v_bus_V", 0.0) * row.get("i_A", 0.0)
            if tp is not None and ta is not None:
                print(f"t {row['t_s']:6.0f}  Tp {tp:7.3f}  Tg-Tp {tg - tp if tg is not None else float('nan'):+6.3f}  "
                      f"Tjet {ta:7.3f}  P {p:6.3f} W  dp {row.get('dp_Pa', float('nan')):6.2f} Pa  guard {rec.p_guard:5.2f} W"
                      + (f"  h~{p / (cfg['plate']['area_m2'] * (tp - ta)):6.1f}" if tp - ta > 1 else ""), flush=True)
            if time.time() - last_save > 30:
                write_csv(out, meta, rec.rows)
                last_save = time.time()
    finally:
        ser.write(b"G 0\n")
        write_csv(out, meta, rec.rows)
        if rec.faults:
            print("faults:", rec.faults[:20])
        print(f"wrote {out} ({len(rec.rows)} rows)")


def selftest():
    cfg = json.loads((HERE / "bench.example.json").read_text())
    rec = Recorder(cfg)
    truth = {"tc0": 48.123, "tc3": 47.9, "tc5": 23.456, "i_A": 0.4321, "v_bus_V": 8.642, "dp_Pa": 15.43, "pt100_C": 23.5}
    lines = ["#,jet_logger_fw,n_tc=7,ina=1,sdp=1"]
    r_pt = 100 * (1 + A_RTD * 23.5 + B_RTD * 23.5 ** 2)
    reg = int(round(r_pt / cfg["rref_ohm"] * 32768)) << 1
    for k in range(25):                                  # 5 s of records at the firmware's rates
        t = 1_000_000 + k * 200_000
        for ch, key in ((0, "tc0"), (3, "tc3"), (5, "tc5")):
            lines.append(f"K,{t},{ch},{round(truth[key] * 128)},{round(24.0 * 64)},0")
        lines.append(f"R,{t},{reg}")
        lines.append(f"P,{t},{round(truth['i_A'] * cfg['ina226']['r_shunt_ohm'] / 2.5e-6)},{round(truth['v_bus_V'] / 1.25e-3)}")
        lines.append(f"D,{t},{round(truth['dp_Pa'] * 240)},{round(24 * 200)},240")
    lines.append("K,6000000,1,0,0,1")                        # an open-circuit fault record
    for ln in lines:
        rec.handle(ln)
    rec.flush()
    rows = rec.rows
    tol = {"tc0": 0.004, "tc3": 0.004, "tc5": 0.004, "i_A": 1e-5, "v_bus_V": 6.25e-4, "dp_Pa": 0.005, "pt100_C": 0.02}
    parse_err = {k: max(abs(r[k] - truth[k]) for r in rows[:-1]) for k in truth}
    ok_parse = all(parse_err[k] <= tol[k] for k in truth) and len(rows) >= 5 and any("SR=0x01" in f for f in rec.faults)

    # guard loop on a lumped plant: C_g dTg/dt = P_g - G_env (Tg - Troom) + G_gap (Tp - Tg), plate held at Troom + 25
    pi, tg, tp, troom = GuardPI(cfg), 23.0, 48.0, 23.0
    cg, genv, ggap = 40.0, 0.08, 0.13
    errs = []
    for k in range(3600):
        duty, p = pi.step(tp - tg, 1.0)
        tg += (p - genv * (tg - troom) + ggap * (tp - tg)) / cg
        errs.append(tp - tg)
    settle = next((k for k in range(len(errs)) if all(abs(e) < 0.05 for e in errs[k:])), None)
    ok_pi = settle is not None and settle < 1800 and abs(errs[-1]) < 0.01
    res = {"parse_max_abs_error": {k: round(v, 6) for k, v in parse_err.items()}, "parse_tolerance": tol, "rows": len(rows),
           "faults_seen": rec.faults, "pi_settle_s_to_0.05K": settle, "pi_final_error_K": round(errs[-1], 5),
           "pass": ok_parse and ok_pi}
    (HERE / "logger-selftest.json").write_text(json.dumps(res, indent=1) + "\n")
    print(json.dumps(res, indent=1))
    return res["pass"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--port")
    ap.add_argument("--run")
    ap.add_argument("--condition", choices=["zero", "still", "floor", "d055", "full", "sweep", "gap", "transient", "height", "flowcal"])
    ap.add_argument("--minutes", type=float, default=30.0)
    ap.add_argument("--guard-offset", type=float, default=0.0)
    ap.add_argument("--no-guard", dest="guard", action="store_false")
    ap.add_argument("--H-mm", type=float, default=6.0)
    ap.add_argument("--room-C", type=float, default=None)
    ap.add_argument("--flow-slpm", type=float, default=None)
    ap.add_argument("--notes", default="")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(0 if selftest() else 1)
    if not (a.port and a.run and a.condition):
        ap.error("--port, --run and --condition are required")
    run(a)


if __name__ == "__main__":
    main()
