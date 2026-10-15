#!/usr/bin/env python3
"""Jet bench BOM (temper-airflow-r1/bench): lean kit to measure the R45 jet box's board-face h.

    python3 bom.py        -> bom.json and a markdown table on stdout

All prices are ESTIMATES (USD, single quantity, before shipping and tax), not quotes. JLCCNC parts: quote online
from cad/plate.step and cad/guard_tray.step. Kinds:
  buy              must buy for this kit
  shared_sensor    already on the sensor-r3 lean order (output/temper-sensor-r3/bench/bom.py); the jet bench reuses
                   the same logger, so order once and run both benches on one day
  shared_enclosure the R45 enclosure bench (HANDOFF A1/A3) needs the same part; buy once
  own_or_borrow    assumed on hand (counted 0)
  optional         improves the result; RIG.md says by how much
"""
from __future__ import annotations

import json
from pathlib import Path

# (group, item, part / source, qty, est unit USD, note, kind)
ROWS = [
    ("plate", "Test plate", "6061-T6, 90 x 16.5 x 3.0 mm, top fine-milled, 3 x D1.0 x 2.0 blind holes (cad/plate.step, JLCCNC)", 1, 20, "the strip, area-averaged h", "buy"),
    ("plate", "Guard tray", "6061-T6 per cad/guard_tray.step (JLCCNC)", 1, 35, "nulls back and edge losses", "buy"),
    ("plate", "Heaters", "TO-220 thick-film power resistor 10 ohm 1 % 20-35 W, isolated tab (Bourns PWR220T-20-10R0F class)", 6, 3, "2 plate + 2 guard + 2 spare", "buy"),
    ("plate", "Over-temperature cut-outs", "KSD9700 bimetal thermostat, 70 C, normally closed, 5-pack", 1, 6, "one in each heater circuit (XPS limit 75 C)", "buy"),
    ("plate", "Thermal adhesive", "electrically insulating thermally conductive epoxy (MG Chemicals 8329TCM / Arctic Alumina class)", 1, 15, "heaters, thermocouples, lead anchors", "buy"),
    ("plate", "Gap seal", "high-temperature RTV silicone, small tube", 1, 8, "1 mm plate-guard seam", "buy"),
    ("plate", "Supports and fixings", "nylon M3 x 6 set screws (4) + M3/M2 screw assortment", 1, 8, "plate height set flush", "buy"),
    ("plate", "Insulation", "XPS foam board, 50 mm (or 2 x 25 mm), ~250 x 150 mm offcut", 1, 15, "under the deck and tray", "buy"),
    ("sense", "Thermocouples", "type-K, 36 AWG, special limits, PFA insulated exposed junction, 1 m, 5-pack, one lot (Omega 5TC-TT-K-36-36 class)", 1, 45, "plate x3, guard x2 from one lot", "buy"),
    ("sense", "Thermocouple converters", "MAX31856 breakout (generic or Adafruit 3263)", 5, 8, "+ the sensor kit's one = 6 channels", "buy"),
    ("sense", "Heater power monitor", "INA226 breakout, 0.1 ohm shunt (I2C)", 1, 6, "V and I of the plate heater", "buy"),
    ("sense", "Manifold pressure", "Sensirion SDP810-125Pa differential pressure sensor (I2C)", 1, 40, "the set variable; 3 % of reading", "buy"),
    ("sense", "Tubing", "silicone tube 3 mm ID x 1 m + 1/8 in (3.2 mm) OD brass tube 50 mm", 1, 10, "tap to sensor", "buy"),
    ("sense", "Hood air reference", "Pt100 class A 4-wire probe, 3 mm sheath", 1, 12, "on the shared MAX31865; the zero reference", "buy"),
    ("drive", "Guard switch", "logic-level MOSFET module (AOD4184 / D4184 class, 3.3 V gate)", 1, 3, "GPIO 7 PWM", "buy"),
    ("drive", "Blower trim", "adjustable buck converter module with V/A display", 1, 8, "sets the blower volts", "buy"),
    ("drive", "12 V supply", "12 V 2 A adapter", 1, 10, "blower + guard heater", "buy"),
    ("tools", "Jet drill", "D3.0 mm HSS jobber drill (new) + pin vise", 1, 8, "printed jets opened to D3.0 by hand", "buy"),
    ("tools", "Height gauges", "D5.9 / 6.0 / 6.1 mm HSS drills (shanks as go/no-go pins)", 1, 8, "jet floor 6.0 +-0.1 mm", "buy"),
    ("logger", "ESP32-S3 devkit", "as sensor-r3 lean", 1, 15, "", "shared_sensor"),
    ("logger", "Pt100 converter", "Adafruit 3328 MAX31865", 1, 15, "", "shared_sensor"),
    ("logger", "Thermocouple converter", "MAX31856 module", 1, 8, "channel 0 here", "shared_sensor"),
    ("logger", "Type-K beads", "2-pack", 1, 10, "jet-air and exit-air channels", "shared_sensor"),
    ("air", "Blower", "Delta BFB1012VH-F00 (the product blower)", 1, 25, "same part for the enclosure A1/A3 bench", "shared_enclosure"),
    ("own", "Plate heater supply", "bench DC supply 0-30 V 1 A (or a second buck module from a 19-24 V brick)", 1, 0, "", "own_or_borrow"),
    ("own", "DMM", "4.5 digit or better", 1, 0, "INA226 gain check", "own_or_borrow"),
    ("own", "Caliper, straightedge, feeler gauges", "", 1, 0, "", "own_or_borrow"),
    ("own", "3D printer + PETG/ASA", "or a print service", 1, 0, "cad/*.stl", "own_or_borrow"),
    ("own", "Scale 0.01 g", "the sensor kit's milligram scale", 1, 0, "plate heat capacity", "own_or_borrow"),
    ("own", "Laptop, USB cable, soldering iron", "", 1, 0, "", "own_or_borrow"),
    ("opt", "Flow meter", "thermal mass flow meter for air, 0-30 SLPM, +-2-3 % of reading, low pressure drop, display (Siargo MF5700-series class)", 1, 60, "measured Cd: U95 3.4 % -> 2.0 % (selftest.json)", "optional"),
    ("opt", "Exit-air channel", "MAX31856 breakout", 1, 8, "energy-balance check only", "optional"),
]


def main():
    rows = [dict(group=g, item=i, part=p, qty=q, est_unit_usd=u, est_usd=q * u, note=n, kind=k) for g, i, p, q, u, n, k in ROWS]

    def total(kind):
        return sum(r["est_usd"] for r in rows if r["kind"] == kind)

    out = {"scope": __doc__.strip(), "rows": rows,
           "must_buy_est_usd": total("buy"), "shared_sensor_est_usd": total("shared_sensor"),
           "shared_enclosure_est_usd": total("shared_enclosure"), "optional_est_usd": total("optional"),
           "must_buy_by_group_usd": {g: sum(r["est_usd"] for r in rows if r["kind"] == "buy" and r["group"] == g)
                                     for g in sorted({r["group"] for r in rows if r["kind"] == "buy"})},
           "assumes_owned": [r["item"] for r in rows if r["kind"] == "own_or_borrow"]}
    Path(__file__).with_name("bom.json").write_text(json.dumps(out, indent=1) + "\n")
    print("| Group | Item | Part / source | Qty | Est. USD | Kind |\n|---|---|---|---|---|---|")
    for r in rows:
        print(f"| {r['group']} | {r['item']} | {r['part']} | {r['qty']} | {r['est_usd']} | {r['kind']} |")
    print(f"\nMUST-BUY (estimate): ${out['must_buy_est_usd']}  by group {out['must_buy_by_group_usd']}\n"
          f"shared with the sensor kit: ${out['shared_sensor_est_usd']}; shared with the enclosure bench: "
          f"${out['shared_enclosure_est_usd']}; optional: ${out['optional_est_usd']}")


if __name__ == "__main__":
    main()
