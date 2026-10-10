#!/usr/bin/env python3
"""Round 5 B3: native-21 board temperature at 50 °C ambient (stage 14 board since 2026-10-09).

Copper Joule heat: round-5 A4 cases at 18 µm plating, each scaled to an operating point by
(I_operating / I_case)^2 and summed. Distinct nets add exactly; time-disjoint paths on one net
(the two legs, SW_B's two states, the A / B return paths) add with weights 0.5.
Component heat: inputs/native21-board-heat-sources.json (make_heat_sources.py), nominal or worst.
Convection: 10 W/m²K both faces (still air) or 25 W/m²K (fan airflow over the board).

    python3 run_study.py  ->  outputs/<run>.json / .png, outputs/summary.json
"""
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "outputs"
UNIT = HERE.parents[3]
GEOM = UNIT / "native-21/verification/native21s14-all-copper.json.gz"
HEAT = HERE / "inputs/native21-board-heat-sources.json"
# Operating points (task 05 round 3 / task 03 round 3): tank RMS I_t through the bridge, R5 and
# the tank; line current P / V. Copper heat scales as (I_operating / I_case)^2.
OPS = {"nominal": {"I_t": 21.47, "I_line": 1710 / 120, "parts": "nominal",
                   "basis": "120 V, 1710 W cast-iron/high tank case (task 03 round 3)"},
       "extreme": {"I_t": 44.70, "I_line": 1710 / 108, "parts": "worst",
                   "basis": "108 V low-R full-power grid extreme: max tank / R5 RMS (task 05 round 3)"}}


def cases(op):
    it, il = OPS[op]["I_t"], OPS[op]["I_line"]
    tank = (it / 18.7) ** 2
    leg = (it / 2 ** 0.5 / 18.7) ** 2          # each leg's low side conducts half the time
    ret = (it / 34.0) ** 2                     # R5 RMS = I_t; A4 mixed cases drive 34 A from R5 / into J8
    line = (il / 15.0) ** 2
    rows = [("sw_a-p00625-pl18", tank), ("sw_b_high-p00625-pl18", 0.5 * tank), ("sw_b_low-p00625-pl18", 0.5 * tank),
            ("res_a-p0125-pl18", tank), ("coil_feed-p0125-pl18", tank),
            ("leg_a_18p7-p00625-pl18", leg), ("leg_b_18p7-p00625-pl18", leg),
            ("hv_mixed_a-p00625-pl18", 0.5 * ret), ("hv_mixed_b-p00625-pl18", 0.5 * ret),
            ("bus_mixed_q2-p0125-pl18", 0.5 * ret), ("bus_mixed_q5-p0125-pl18", 0.5 * ret),
            ("ac_n_main-p0125-pl18", line), ("ac_l_main-p0125-pl18", line)]
    return ",".join(f"{c}:{k:.6g}" for c, k in rows)


JOBS = [(f"{op}_h{h}_p{str(p).replace('.', 'p')}", op, p, h) for op in ("nominal", "extreme")
        for h in (10, 25) for p in (1.0, 0.5)]


def main():
    OUT.mkdir(exist_ok=True)
    runs = {}
    for name, op, pitch, h in JOBS:
        path = OUT / f"{name}.json"
        subprocess.run([sys.executable, str(HERE / "thermal.py"), "--geometry", str(GEOM), "--case", cases(op),
                        "--pitch-mm", str(pitch), "--h", str(h), "--a6-heat", str(HEAT), "--a6-mode", OPS[op]["parts"],
                        "--output", str(path)], check=True, stdout=subprocess.DEVNULL)
        r = json.loads(path.read_text())
        parts = sorted(r["a6_parts_applied"], key=lambda p: -p.get("conditional_pad_cell_max_c", 0))[:8]
        runs[name] = {"peak": r["peak"], "balance": r["balance"], "hottest_parts": [
            {k: p.get(k) for k in ("ref", "watts_to_board", "conditional_pad_cell_max_c")} for p in parts]}
        print(f"{name}: peak {r['peak']['temperature_c']:.1f} C at {r['peak'].get('x_mm')},{r['peak'].get('y_mm')} "
              f"({r['peak'].get('layer')}), source {r['balance']['source_w']:.2f} W", flush=True)
    (OUT / "summary.json").write_text(json.dumps({"operating_points": OPS, "cases": {op: cases(op) for op in OPS},
                                                  "runs": runs}, indent=1) + "\n")


if __name__ == "__main__":
    main()
