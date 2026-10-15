"""sensor-r3 bench host logger: records one set-down from logger_fw over USB serial.

Writes runs/<pan>__<condition>__r<repeat>.csv with a metadata header that fit.py reads,
passes device records through unchanged, and prints a live readout. At the end it checks
the Pt100 sample rate (must be >= 20 Hz; the MAX31865 auto mode gives ~60 Hz).

  pip install pyserial
  python logger.py --port /dev/cu.usbmodem1101 --pan lodge_10in --pan-class cast_iron_as_cast \\
      --condition dry_nominal --repeat 1 --seconds 20
  python logger.py --selftest          # parses a synthetic stream; no hardware needed
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
A, B = 3.9083e-3, -5.775e-7
CONDITIONS = ("dry_nominal", "dry_force_low", "dry_force_high", "dry_proud_0p5", "dry_proud_0p7",
              "oiled", "paste_cal", "hot_230")


def rtd_C(reg: int, rref: float = 430.0) -> float:
    r = ((reg >> 1) & 0x7FFF) * rref / 32768.0
    return (-A + (A * A - 4 * B * (1 - r / 100.0)) ** 0.5) / (2 * B)


class Recorder:
    def __init__(self):
        self.lines, self.n_r, self.t_first, self.t_last, self.last_rtd, self.last_tc, self.faults = [], 0, None, None, None, None, 0

    def handle(self, line: str):
        line = line.strip()
        if not line:
            return
        f = line.split(",")
        if f[0] == "R" and len(f) == 3:
            t = int(f[1])
            self.t_first = t if self.t_first is None else self.t_first
            self.t_last = t
            self.n_r += 1
            self.last_rtd = rtd_C(int(f[2]))
        elif f[0] == "T" and len(f) == 4:
            self.last_tc = int(f[2]) / 128.0
        elif f[0] == "F":
            self.faults += 1
        elif f[0] not in ("M", "#"):
            return                          # drop garbage (partial lines at start)
        self.lines.append(line if not line.startswith("#,") else "# " + line[2:])

    def rate_hz(self):
        if self.n_r < 2:
            return 0.0
        return (self.n_r - 1) / ((self.t_last - self.t_first) * 1e-6)


def header(a) -> list[str]:
    return [f"# pan: {a.pan}", f"# pan_class: {a.pan_class}", f"# condition: {a.condition}",
            f"# repeat: {a.repeat}", f"# probe: {a.probe}", f"# pan_temp_target_C: {a.pan_temp}",
            f"# operator_note: {a.note}", f"# host_time: {time.strftime('%Y-%m-%dT%H:%M:%S')}"]


def selftest() -> int:
    rec = Recorder()
    rec.handle("R,10")                     # partial line, dropped
    for i in range(120):
        t = i * 16700
        code = int(round(100 * (1 + A * 150 + B * 150**2) / 430 * 32768))
        rec.handle(f"R,{t},{code << 1}")
        if i % 6 == 0:
            rec.handle(f"T,{t},{150 * 128},{25 * 64}")
    rec.handle("M,5000,1")
    ok = abs(rec.last_rtd - 150.0) < 0.05 and abs(rec.last_tc - 150.0) < 1e-6 and 55 < rec.rate_hz() < 65
    print(f"logger selftest: rtd {rec.last_rtd:.3f} C, tc {rec.last_tc:.2f} C, rate {rec.rate_hz():.1f} Hz ->",
          "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--port")
    ap.add_argument("--pan")
    ap.add_argument("--pan-class", default="unknown")
    ap.add_argument("--condition", default="dry_nominal", choices=CONDITIONS)
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--probe", default="S1")
    ap.add_argument("--pan-temp", type=float, default=150.0)
    ap.add_argument("--note", default="")
    ap.add_argument("--seconds", type=float, default=20.0)
    ap.add_argument("--out-dir", default=str(HERE / "runs"))
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())
    if not (a.port and a.pan):
        ap.error("--port and --pan are required")
    import serial  # pyserial

    out_dir = Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{a.pan}__{a.condition}__r{a.repeat}.csv"
    if path.exists():
        sys.exit(f"{path} exists; bump --repeat")
    rec = Recorder()
    with serial.Serial(a.port, 921600, timeout=0.2) as ser:
        ser.reset_input_buffer()
        t_end = time.time() + a.seconds
        t_print = 0.0
        print("recording; set the pan down within the first 5 s, press BOOT as you release it")
        while time.time() < t_end:
            raw = ser.readline()
            if raw:
                rec.handle(raw.decode("ascii", "replace"))
            if time.time() > t_print:
                t_print = time.time() + 0.5
                if rec.last_rtd is not None:
                    tc = f"{rec.last_tc:7.2f}" if rec.last_tc is not None else "   n/a"
                    print(f"\r  Pt100 {rec.last_rtd:7.2f} C   pan TC {tc} C   rate {rec.rate_hz():5.1f} Hz", end="")
    print()
    path.write_text("\n".join(header(a) + rec.lines) + "\n")
    rate = rec.rate_hz()
    print(f"wrote {path} ({rec.n_r} Pt100 samples, {rate:.1f} Hz, {rec.faults} faults)")
    if rate < 20:
        print("WARNING: Pt100 rate < 20 Hz; check the MAX31865 auto-conversion config (RTD_CFG 0xC2)")
    if rec.faults:
        print("WARNING: MAX31865 faults logged; check wiring before using this run")


if __name__ == "__main__":
    main()
