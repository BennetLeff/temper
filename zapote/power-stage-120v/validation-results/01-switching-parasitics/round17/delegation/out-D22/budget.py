#!/usr/bin/env python3
"""Transparent component and enclosure estimates; no production layout mutation."""

import ast
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    rows = []
    for line in (120, 140):
        # Planning values, not datasheet maxima: 6 mOhm hot per winding and 35 mOhm X ESR.
        frequency = 60
        rd = 3.9 * 1.05
        cd = 4.7e-6 * 1.1
        damping_i = line / math.hypot(rd, 1 / (2 * math.pi * frequency * cd))
        rows.append(
            {
                "line_RMS_V": line,
                "line_peak_V": line * math.sqrt(2),
                "choke_copper_typical_20C_W": 2 * 15**2 * 0.0045,
                "choke_copper_hot_6mOhm_estimate_W": 2 * 15**2 * 0.006,
                "damping_line_RMS_A": damping_i,
                "damping_line_W": damping_i**2 * rd,
                "bleed_pair_max_initial_W": line**2 / (30000 * 0.95),
                "bleed_each_max_initial_W": line**2 / (4 * 15000 * 0.95),
                "bleed_each_max_initial_RMS_V": line * 1.05 / (1.05 + 0.95),
                "Y_leakage_added_one_energized_plus20pct_mA": 2
                * math.pi
                * frequency
                * 8.28e-9
                * line
                * 1000,
                "X2p2_line_RMS_A": 2 * math.pi * frequency * 2.42e-6 * line,
                "X4p7_line_RMS_A": 2 * math.pi * frequency * 5.17e-6 * line,
                "damper_cold_start_energy_J": 0.5 * cd * (line * math.sqrt(2)) ** 2,
                "damper_opposite_polarity_reclose_energy_J": 0.5
                * cd
                * (2 * line * math.sqrt(2)) ** 2,
            }
        )
    # Existing two 1 uF X caps conservatively assigned +/-20%; added parts +/-10%.
    capacitance = (2 * 1.2 + 11.6 * 1.1) * 1e-6
    # Initial tolerance +5%, 80 K at 250 ppm/K +2%, 1000 h drift +5%: multiplicative worst-sign stack for this stated 1000-hour scenario.
    resistance = 30000 * 1.05 * 1.02 * 1.05 + 0.2
    tau = resistance * capacitance
    bleed = {
        "capacitance_assumed_max_F": capacitance,
        "resistance_stacked_assumption_Ohm": resistance,
        "time_constant_s": tau,
        "time_198V_to_34V_s": tau * math.log(140 * math.sqrt(2) / 34),
        "voltage_after_1s_from_140Vrms_crest_V": 140 * math.sqrt(2) * math.exp(-1 / tau),
        "scope": "all stated connected X capacitors; healthy resistor pair; no active backfeed or rectifier DC-link discharge credit",
    }
    costs = {
        "choke": 13.73,
        "X2p2u": 2.05,
        "two_X4p7u": 2 * 3.38,
        "two_Y4p7n_allowance": 2 * 1.0,
        "two_Y2p2n_allowance": 2 * 1.0,
        "damper_allowance": 2.0,
        "two_bleed_allowance": 1.0,
        "carrier_terminals_cover_allowance": 15.0,
    }
    budget = {
        "line_checks": rows,
        "bleed": bleed,
        "planning_cost_USD": costs,
        "parts_subtotal_USD": sum(
            v for k, v in costs.items() if k != "carrier_terminals_cover_allowance"
        ),
        "module_material_estimate_USD": sum(costs.values()),
        "module_envelope_mm": [110, 80, 50],
        "module_volume_L": 110 * 80 * 50 / 1e6,
        "module_heat_allocation_W": 8,
    }
    (HERE / "budget.json").write_text(json.dumps(budget, indent=2) + "\n")
    mesher = HERE.parents[1] / "scripts/mesh25d_hybrid.py"
    tree = ast.parse(mesher.read_text())
    legs = next(
        ast.literal_eval(n.value)
        for n in tree.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "LEGS" for t in n.targets)
    )
    regions = {k: [x0 - 20, y0 - 20, x1 + 20, y1 + 20] for k, (x0, y0, x1, y1) in legs.items()}
    proposed = {"module": [-120, 10, -10, 90], "wire_and_PE_corridor": [-10, -10, 60, 90]}
    overlaps = {}
    for label, (x0, y0, x1, y1) in proposed.items():
        overlaps[label] = {
            leg: max(0, min(x1, r[2]) - max(x0, r[0])) * max(0, min(y1, r[3]) - max(y0, r[1]))
            for leg, r in regions.items()
        }
    assert all(area == 0 for group in overlaps.values() for area in group.values())
    placement = {
        "mesher": str(mesher.relative_to(HERE.parents[5])),
        "leg_regions_mm": regions,
        "proposed_envelopes_mm": proposed,
        "intersection_area_mm2": overlaps,
        "rightmost_new_conductor_x_mm": 60,
        "nearest_region_left_x_mm": min(r[0] for r in regions.values()),
        "condition": "reservation only; keep all new metal/wiring within these boxes and keep original leg copper/stackup/mounting unchanged",
    }
    (HERE / "placement.json").write_text(json.dumps(placement, indent=2) + "\n")
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    fig, ax = plt.subplots(figsize=(11, 4.5))
    for label, (x0, y0, x1, y1) in {**regions, **proposed}.items():
        color = "#c26742" if label in regions else "#327a70"
        ax.add_patch(
            Rectangle((x0, y0), x1 - x0, y1 - y0, facecolor=color, alpha=0.2, edgecolor=color)
        )
        ax.text((x0 + x1) / 2, (y0 + y1) / 2, label.replace("_", "\n"), ha="center", va="center")
    ax.set(
        xlim=(-130, 195),
        ylim=(100, -25),
        xlabel="Board x (mm): mains / left → coil / right",
        ylabel="Board y (mm)",
        title="D-22 enclosure reservation — not a PCB placement",
    )
    ax.set_aspect("equal")
    ax.grid(alpha=0.15)
    fig.tight_layout()
    fig.savefig(HERE / "placement.png", dpi=160)
    plt.close(fig)
    print(json.dumps(budget, indent=2))


if __name__ == "__main__":
    main()
