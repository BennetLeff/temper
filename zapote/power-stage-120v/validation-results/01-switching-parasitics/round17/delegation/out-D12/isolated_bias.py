"""Reproduce independent F6 bias sizing/BOM; analytical proposal, not qualification."""

from __future__ import annotations

import csv
import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent


def add_part(parts: Counter[str], roles: dict[str, str], part: str, qty: int, role: str) -> None:
    parts[part] += qty
    roles[part] = role


def main() -> None:
    with HERE.joinpath("isolated_prices.csv").open(newline="") as stream:
        prices = {row["role"]: row for row in csv.DictReader(stream)}
    raw_span = 2.5 * (1 + (49900 + 31600) / 11000)
    raw_negative = 2.5 * (1 + 69800 / 49900)
    positive = raw_span - raw_negative
    results = {
        "status": "proposal, no circuit transient/startup/hardware qualification",
        "variants": {},
    }
    for name, top, window_tops in (
        ("2V", 6980, (4420, 7620, 120000, 133000)),
        ("4V", 23700, (18700, 25300, 137000, 147000)),
    ):
        negative = 1.176 * (1 + top / 10000)
        swing = positive + negative
        # +/-1.5% module split accuracy scenario and +/-2.5% LDO plus divider error.
        raw_min = raw_negative * 0.985
        regulated_max = negative * 1.027
        scenarios = []
        for frequency in (0, 36000, 40000, 80000):
            iq_gate = (400e-9 + 1e-9 * swing) * frequency
            # Both rails conservatively charged for driver, monitor, Rgs, preloads.
            current = iq_gate + 0.0044 + 0.015 + positive / 10000 + negative / 1000 + 0.001
            power = raw_span * current
            scenarios.append(
                {
                    "frequency_Hz": frequency,
                    "raw_span_current_sizing_A": current,
                    "module_output_power_sizing_W": power,
                    "four_modules_input_at_45pct_W": 4 * power / 0.45,
                    "four_modules_input_at_35pct_W": 4 * power / 0.35,
                    "negative_ldo_heat_sizing_W": (raw_negative - negative) * current
                    + raw_negative * 0.001,
                    "within_100mA_and_1_5W_at_90C_scenario": current <= 0.1 and power <= 1.5,
                }
            )
        parts = Counter()
        roles = {}

        for part, qty, role in (
            ("R15C2T25/R-R", 4, "module"),
            ("TPS7A3001DGNR", 4, "negative_ldo"),
            ("IRM-20-15", 1, "ps2"),
            ("LM339BIDR", 4, "monitor"),
            ("TL431AIDBZR", 4, "reference"),
            ("VO617A-3X017T", 4, "opto"),
            ("MMBT3904-7-F", 4, "npn"),
            ("1N4148W-7-F", 4, "silicon_diode"),
            ("SN74LVC32APWR", 2, "logic"),
            ("UMK325AB7106KM-T", 44, "10u"),
            ("C0603C104K5RACTU", 14, "100n"),
            ("C0603C331J5GACTU", 12, "330p"),
            ("C0603C102J5GACTU", 4, "cgs"),
        ):
            add_part(parts, roles, part, qty, role)
        # Per-channel module dividers, LDO bottom and monitor/pull resistors.
        for code, per_channel in (
            ("49K9", 2),
            ("31K6", 1),
            ("11K", 1),
            ("69K8", 1),
            ("10K", 9),
            ("1K", 1),
        ):
            add_part(parts, roles, f"RT0603BRD07{code}L", 4 * per_channel, "precision_resistor")
        add_part(
            parts, roles, "RT0603BRD0710KL", 6, "precision_resistor"
        )  # 4 opto pullups + 2 DIS pullups
        add_part(
            parts,
            roles,
            "RT0603BRD07" + ("6K98" if name == "2V" else "23K7") + "L",
            4,
            "precision_resistor",
        )
        codes = (
            ("4K42", "7K62", "120K", "133K") if name == "2V" else ("18K7", "25K3", "137K", "147K")
        )
        for code in codes:
            add_part(parts, roles, f"RT0603BRD07{code}L", 4, "precision_resistor")
        for code in ("261R", "1K", "2K2", "2K7"):
            add_part(parts, roles, f"RC1206FR-07{code}L", 4, "power_resistor")
        if name == "2V":
            add_part(parts, roles, "PMEG6030EP,115", 4, "discharge_diode")
            add_part(parts, roles, "RC1206FR-071RL", 4, "power_resistor")
        bom = [
            {
                "part": part,
                "qty": qty,
                "unit_estimate_USD": prices[roles[part]]["unit_usd"],
                "price_role": roles[part],
            }
            for part, qty in sorted(parts.items())
        ]
        cost = sum((Decimal(row["unit_estimate_USD"]) * row["qty"] for row in bom), Decimal(0))
        results["variants"][name] = {
            "raw_span_nominal_V": raw_span,
            "raw_negative_nominal_V": -raw_negative,
            "positive_nominal_V": positive,
            "negative_nominal_V": -negative,
            "driver_span_nominal_V": swing,
            "ldo_headroom_scenario_V": raw_min - regulated_max,
            "ldo_required_accuracy_headroom_V": 1.0,
            "minimum_negative_to_positive_cap_ratio": positive / raw_negative * 1.1,
            "selected_ratio_at_independent_tolerance_and_X7R_extremes_before_DC_bias": (
                50 * 0.9 * 0.85
            )
            / (10 * 1.1 * 1.15),
            "nominal_monitor_thresholds_bias_low_high_span_low_high_V": [
                2.495 / 2 * (1 + r / 10000) for r in window_tops
            ],
            "scenarios": scenarios,
            "bom": bom,
            "purchased_parts": sum(parts.values()),
            "material_purchase_estimate_USD": str(cost.quantize(Decimal(".01"))),
            "removed_parts": ["PS2 IRM-05-15", "D1 UF4007", "D2 UF4007"],
            "cost_note": "purchase estimate before removed-part credit, PCB, labor, qualification; resistor-family estimates explicitly marked in CSV",
        }
        assert raw_min - regulated_max >= 1
        assert swing < 25
        assert all(row["within_100mA_and_1_5W_at_90C_scenario"] for row in scenarios)
    HERE.joinpath("isolated_bias.json").write_text(json.dumps(results, indent=2) + "\n")
    for name, row in results["variants"].items():
        print(
            name,
            row["positive_nominal_V"],
            row["negative_nominal_V"],
            row["material_purchase_estimate_USD"],
            row["purchased_parts"],
            row["scenarios"],
        )


if __name__ == "__main__":
    main()
