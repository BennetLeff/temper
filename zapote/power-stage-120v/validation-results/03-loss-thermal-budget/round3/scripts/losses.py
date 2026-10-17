#!/usr/bin/env python3
"""Reproduce task 03 conditional loss/thermal screens from pinned round-3 inputs.

These are one-off engineering calculations, not permanent validation rules.
Unknown loads and unqualified material properties remain null in the outputs.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
INPUT = HERE / "inputs"
OUTPUT = HERE / "outputs"
SOURCE = HERE / "sources"
BOARD_HASH = "a3ac1249f5052afe52944804cdc3f6ef0e8f895668360e79c1fa7b6fb7322155"
MOS_REFS = ("Q2", "Q3", "Q5", "Q6")
GATE_REFS = ("R10", "R12", "R18", "R20")
BLEED_REFS = ("R22", "R23", "R24", "R25")


def rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(name: str, value: object) -> None:
    (OUTPUT / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def interpolate(x: float, points: list[tuple[float, float]]) -> float:
    assert points[0][0] <= x <= points[-1][0]
    for (xa, ya), (xb, yb) in zip(points, points[1:]):
        if xa <= x <= xb:
            return ya + (yb - ya) * (x - xa) / (xb - xa)
    return points[-1][1]


def main() -> None:
    OUTPUT.mkdir(exist_ok=True)
    assert digest(HERE.parents[2] / "native-15" / "section.kicad_pcb") == BOARD_HASH
    board = json.loads((INPUT / "board-parts.json").read_text())
    assert board["board_sha256"] == BOARD_HASH
    parts = board["parts"]
    assert all(parts[ref]["part"] == "IPW65R018CFD7" for ref in MOS_REFS)
    assert parts["BR1"]["part"] == "GBJ2510-F"
    assert parts["R5"]["part"] == "WSK2512R0010FEA"

    cases = {row["run_id"]: row for row in rows(INPUT / "cases.csv")}
    shunt = {row["run_id"]: row for row in rows(INPUT / "shunt-grid.csv")}
    a3 = json.loads((INPUT / "a3-thresholds.json").read_text())
    assert a3["board_sha256"] == BOARD_HASH
    ct_max = max(float(data[side]["max"])
                 for data in a3["temperature_corners"].values()
                 for side in ("ct_pos_a", "ct_neg_a"))
    full_power = [row for row in cases.values() if row["target_w"] == "1710"]
    shunt_over_rating = [row for row in full_power
                         if float(row["i_rms_a"]) ** 2 * 0.001 > 1.0]
    write_json("grid_rating_screen.json", {
        "board_sha256": BOARD_HASH,
        "full_power_case_count": len(full_power),
        "r5_over_1w_nominal_count": len(shunt_over_rating),
        "a3_static_ct_max_a": ct_max,
        "r5_over_1w_all_above_a3_ct_static_max": all(
            float(row["i_pk_a"]) > ct_max for row in shunt_over_rating),
        "r5_over_1w_cases": [{"run_id": row["run_id"],
            "r5_nominal_w": float(row["i_rms_a"]) ** 2 * 0.001,
            "tank_peak_a": float(row["i_pk_a"])} for row in shunt_over_rating],
        "qualification": "ideal steady waveform only; static threshold does not establish actual fault-trip timing, thermal pulse duty or protection integrity",
    })
    selected = {
        "nominal_example": "cast_iron-high-120v-1710w",
        "high_current_unprotected_stress": "offset_or_small_pan-low-108v-1710w",
    }
    # A1 is a 27 C device-model calculation. Each ideal bridge transition
    # turns off one high-side and one low-side device. Keep the two directions
    # separate: the vendor model gives materially different dissipative heat.
    energy: dict[int, dict[float, dict[float, float]]] = {0: defaultdict(dict), 1: defaultdict(dict)}
    for row in rows(INPUT / "turnoff_energy.csv"):
        if (row["deadtime_ns"] == "348" and row["board_l_scale"] == "1.0"
                and row["max_step_ns"] == "0.2"):
            direction = int(row["direction"])
            assert row["outgoing_device"] == {0: "LS", 1: "HS"}[direction]
            bus, current = float(row["bus_v"]), float(row["current_a"])
            assert current not in energy[direction][bus], (direction, bus, current, "duplicate A1 energy point")
            energy[direction][bus][current] = float(row["turnoff_model_dissipative_sum_j"])
    energy_points = {
        direction: {bus: sorted(values.items()) for bus, values in grid.items()}
        for direction, grid in energy.items()
    }
    assert all(set(grid) == {120.0, 170.0, 198.0} for grid in energy_points.values())
    expected_currents = {1.0, 2.0, 3.0, 4.0, 6.0, 8.0, 10.0, 15.0, 20.0, 37.0}
    assert all(set(points) == expected_currents for grid in energy.values() for points in grid.values())
    event_rows: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for row in rows(INPUT / "switching-events.csv"):
        if row["run_id"] in selected.values():
            event_rows[row["run_id"]].append(
                (abs(float(row["tank_current_a"])), float(row["bus_voltage_v"]))
            )

    loss_records: list[dict[str, object]] = []
    summaries: dict[str, dict[str, object]] = {}

    def add(scenario: str, ref: str, mechanism: str, watts: float | None,
            basis: str, path: str, sink_fraction: float | None) -> None:
        assert ref in parts, ref
        loss_records.append({
            "scenario": scenario, "ref": ref, "mechanism": mechanism,
            "watts": None if watts is None else round(watts, 8),
            "basis": basis, "source": path, "sink_fraction": sink_fraction,
            "board_fraction": None if sink_fraction is None else 1.0 - sink_fraction,
        })

    for scenario, run_id in selected.items():
        case, sh = cases[run_id], shunt[run_id]
        i_rms = float(case["i_rms_a"])
        f = float(case["frequency_hz"])
        r5_rms = float(sh["line_average_r5_rms_a"])
        assert abs(r5_rms - i_rms) < 0.001
        # Linear interpolation of *typical* 25/150 C characterization at 10 V.
        # It is not a guaranteed hot maximum, and no self-consistent Tj is claimed.
        rds_hot_typ = 0.015 + (0.033 - 0.015) * (125 - 25) / (150 - 25)
        p_cond = 0.5 * i_rms * i_rms * rds_hot_typ
        for ref in MOS_REFS:
            add(scenario, ref, "conduction_typical_125c", p_cond,
                "I_tank,rms²/2 × linear interpolated 25-to-150 C typical RDS(on), VGS=10 V",
                "Infineon Rev2 p5 Table4; cases.csv", 1.0)

        # Evaluate only events inside A1's current domain. Below 120 V, use
        # its 120 V curve as a stated proxy; never extrapolate current >37 A.
        event_energy = {0: 0.0, 1: 0.0}
        covered = 0
        out_of_domain = 0
        low_bus = 0
        for current, bus in event_rows[run_id]:
            if current < 1.0 or current > 37.0:
                out_of_domain += 1
                continue
            if bus < 120.0:
                low_bus += 1
            capped_bus = max(120.0, min(bus, 198.0))
            for direction in (0, 1):
                per_bus = [(b, interpolate(current, energy_points[direction][b]))
                           for b in sorted(energy_points[direction])]
                event_energy[direction] += interpolate(capped_bus, per_bus)
            covered += 1
        duration_s = 1 / 120  # one rectified line half-cycle, 60 Hz input
        p_switch_partial_per_mos = {direction: 0.5 * e / duration_s
                                    for direction, e in event_energy.items()}
        for ref in MOS_REFS:
            direction = 1 if ref in ("Q2", "Q5") else 0
            add(scenario, ref, "turnoff_covered_events_27c_model", p_switch_partial_per_mos[direction],
                "1 outgoing HS+1 LS per event, shared by 2 of each device; A1 heat only for 1-37 A events; low bus uses 120 V proxy",
                "A1 turnoff_energy.csv; A5 switching-events.csv", 1.0)
            add(scenario, ref, "turnoff_uncovered_events", None,
                f"{out_of_domain} of {len(event_rows[run_id])} events outside 1-37 A model domain",
                "A1 turnoff_energy.csv; A5 switching-events.csv", 1.0)
            add(scenario, ref, "body_diode_deadtime", None,
                "A5 ideal bridge omits dead-time diode current and Qrr; cannot assign thermal watts",
                "ROUND-3.md A5.2", 1.0)
            add(scenario, ref, "lost_zvs_turnon", None,
                "Requires A5 ZVS map and Eoss(V)/integrated Coss; Co(tr) is time-equivalent only",
                "Infineon Rev2 p5 Table5; ROUND-3.md B4", 1.0)

        # A nominal sinusoidal 15 A rms *input* assumption gives two forward
        # junctions at all instants. 1.05 V is only a 25 C, 12.5 A max point.
        i_input_rms = 15.0
        i_input_abs_mean = i_input_rms * 2 * math.sqrt(2) / math.pi
        bridge_total = 2 * 1.05 * i_input_abs_mean
        add(scenario, "BR1", "forward_sinusoidal_screen", bridge_total,
            "2×1.05 V×E|Iin|, 15 A rms sinusoid; 1.05 V at IF=12.5 A/Tj25 only, not a waveform bound",
            "Diodes GBJ Rev11 p2; 00-MASTER-PLAN.md envelope", 1.0)
        add(scenario, "BR1", "reverse_recovery", None,
            "No reverse-recovery loss estimate for unfiltered input bridge", "GBJ datasheet", 1.0)

        r5 = r5_rms * r5_rms * 0.001
        if scenario != "nominal_example":
            r5 *= 1.01 * (1 + 250e-6 * 50)  # 1% tolerance, assumed +50 C
        add(scenario, "R5", "resistive", r5,
            "I_R5,rms² × 1mΩ; stress uses +1% tolerance and +50 C×250ppm/C",
            "A5 shunt-grid.csv; Vishay WSK2512 Rev2023 p1-2", 0.0)

        # Exact CDE part rows provide only *typical 100 kHz ESR*. These
        # watts are a nominal screen, not hot 30-60 kHz loss bounds.
        for ref, esr, field in (("C21", 0.006, "c21_i_rms_a"),
                                ("C22", 0.006, "c22_i_rms_a"),
                                ("C23", 0.005, "c23_i_rms_a")):
            add(scenario, ref, "esr_typical_100khz_screen", float(case[field]) ** 2 * esr,
                f"I_rms² × {esr}Ω typical at 100 kHz; actual 30-60 kHz/hot ESR unknown",
                "CDE 942C catalog p3; A5 cases.csv", 0.0)
        for ref in BLEED_REFS:
            add(scenario, ref, "bleed", float(case["bleed_each_p_avg_w"]),
                "A5 average V²/R from ideal tank waveform; 470kΩ per resistor",
                "A5 cases.csv; frozen/default.csv", 0.0)
        add(scenario, "R39", "ct_burden_ideal", (i_rms / 100) ** 2 * 1.5,
            "(tank rms/100)²×1.5Ω; ideal CT ratio, no saturation/core heat",
            "A5 cases.csv; ROUND-3.md A5; frozen/default.csv", 0.0)
        add(scenario, "T1", "core_and_winding", None,
            "CT winding/core loss requires burden waveform and vendor winding data",
            "CST3015 datasheet needed", None)
        add(scenario, "L1", "dc_copper_typical", 2 * 0.0045 * i_input_rms ** 2,
            "two windings × 4.5mΩ typical × 15A²; AC/thermal copper rise excluded",
            "TDK B82726S22x3 May2026 p4; validation-results/07-conducted-emi/sources", 0.0)
        for ref in GATE_REFS:
            add(scenario, ref, "gate_resistor", None,
                "Qg234nC applies 0-10V; 15V gate swing and resistor/driver division unavailable",
                "Infineon Rev2 p5 Table6; frozen board", 0.0)
        for ref in ("U1", "U2"):
            add(scenario, ref, "gate_driver", None,
                "driver output plus quiescent heat; 15V charge and exact loads unknown",
                "Infineon Rev2 p5 Table6; UCC21550 data needed", 0.0)
        add(scenario, "U3", "ldo_quiescent_only", 15 * 0.0038,
            "15V×3.8mA typical input bias, excludes (15-5)V×Ihot5",
            "onsemi MC78L00A p3/5; hot5 load missing", 0.0)
        add(scenario, "U3", "ldo_load", None,
            "10V×measured HOT5 output current; no full native-15 current budget",
            "MC78L00A; HOT5 measurement required", 0.0)
        for ref, efficiency in (("PS1", 0.84), ("PS2", 0.75)):
            add(scenario, ref, "conversion_loss", None,
                f"Pout×(1/{efficiency}-1) is rated-load/230Vac/25C typical only; actual load unknown",
                "Mean Well IRM-20 2025-11-21 p2 or IRM-05 2025-08-08 p2", 0.0)
        for ref in ("C1", "C2", "C5", "C6", "C12", "C13", "C19", "C20",
                    "C38", "C39", "C40", "C41", "R26", "R27", "R28", "R29", "D3"):
            add(scenario, ref, "secondary_power_part_unquantified", None,
                "actual RMS/ripple/edge or hot ESR/leakage unavailable; no zero-heat claim",
                "frozen/default.csv; board-parts.json; electrical waveforms needed", 0.0)

        summaries[scenario] = {
            "run_id": run_id, "tank_rms_a": i_rms,
            "tank_peak_a": float(case["i_pk_a"]), "frequency_hz": f,
            "r5_crest_interval_rms_a": float(sh["crest_interval_r5_rms_a"]),
            "r5_w": r5, "r5_rating_w_at_70c": 1.0,
            "r5_rating_screen": "FAIL" if r5 > 1.0 else "conditional below rating; board temperature unknown",
            "switching_events": len(event_rows[run_id]),
            "switching_covered_events": covered,
            "switching_out_of_domain_events": out_of_domain,
            "switching_low_bus_proxy_events": low_bus,
            "switching_partial_w_per_mos_hs": p_switch_partial_per_mos[1],
            "switching_partial_w_per_mos_ls": p_switch_partial_per_mos[0],
            "mos_conduction_typical_125c_w_per_mos": p_cond,
            "bridge_forward_screen_w": bridge_total,
            "gate_0_to_10v_test_source_w_per_device": 234e-9 * 10 * f,
        }

    # Minimum metal rectangle from Infineon drawing p12, excluding largest
    # mounting hole. Area scaling of ASTM D5470 impedance remains heuristic.
    mos_area_mm2 = 12.38 * 13.08 - math.pi * (3.70 / 2) ** 2
    bridge_area_mm2 = 29.70 * 19.70  # optimistic whole-back body area
    pads = {
        "SIL_PAD_400_0p229mm": {"thickness_mm": 0.229, "epsilon_r_1khz": 5.5,
                                   "impedance_c_in2_per_w_50psi": 1.45,
                                   "source_page": "Henkel guide printed p63"},
        "SIL_PAD_K10_0p152mm": {"thickness_mm": 0.152, "epsilon_r_1khz": 3.7,
                                  "impedance_c_in2_per_w_50psi": 0.41,
                                  "source_page": "Henkel guide printed p75"},
    }
    for pad in pads.values():
        z = pad["impedance_c_in2_per_w_50psi"]
        pad["mos_tab_area_min_mm2"] = mos_area_mm2
        pad["mos_tab_area_max_mm2"] = 14.15 * 17.65 - math.pi * (3.50 / 2) ** 2
        pad["bridge_assumed_whole_back_area_mm2"] = bridge_area_mm2
        pad["rtheta_cs_mos_typical_50psi_c_per_w"] = z / (mos_area_mm2 / 645.16)
        pad["rtheta_cs_bridge_optimistic_c_per_w"] = z / (bridge_area_mm2 / 645.16)
        pad["c_tab_to_pe_min_pf_1khz_epsilon"] = 8.8541878128e-12 * pad["epsilon_r_1khz"] * (mos_area_mm2 * 1e-6) / (pad["thickness_mm"] * 1e-3) * 1e12
        pad["c_tab_to_pe_max_pf_1khz_epsilon"] = 8.8541878128e-12 * pad["epsilon_r_1khz"] * (pad["mos_tab_area_max_mm2"] * 1e-6) / (pad["thickness_mm"] * 1e-3) * 1e12
        pad["qualification"] = "typical 50psi material data; actual TO-247 pressure/contact and RF epsilon unknown"
    write_json("pad_options.json", {"board_sha256": BOARD_HASH, "pads": pads})

    thermal: list[dict[str, object]] = []
    for scenario, summary in summaries.items():
        p_hs = summary["mos_conduction_typical_125c_w_per_mos"] + summary["switching_partial_w_per_mos_hs"]
        p_ls = summary["mos_conduction_typical_125c_w_per_mos"] + summary["switching_partial_w_per_mos_ls"]
        p_bridge = summary["bridge_forward_screen_w"]
        p_sink = 2 * p_hs + 2 * p_ls + p_bridge
        for pad_name, pad in pads.items():
            # Four junctions in a bridge: each dissipates one quarter of
            # package total under the symmetric sinusoidal assumption.
            ts_mos = 125 - max(p_hs, p_ls) * (0.28 + pad["rtheta_cs_mos_typical_50psi_c_per_w"])
            ts_bridge = 125 - p_bridge * (pad["rtheta_cs_bridge_optimistic_c_per_w"] + 1.0 / 4)
            ts_max = min(ts_mos, ts_bridge)
            for ambient in (50, 65):
                thermal.append({
                    "scenario": scenario, "pad": pad_name, "ambient_c": ambient,
                    "sink_power_included_w": p_sink,
                    "sink_temperature_max_mos_c": ts_mos,
                    "sink_temperature_max_bridge_c": ts_bridge,
                    "sink_temperature_max_c": ts_max,
                    "rtheta_sa_required_c_per_w": (ts_max - ambient) / p_sink,
                    "feasible_with_ideal_sink": ts_max > ambient,
                    "status": "CONDITIONAL_SCREEN_ONLY",
                    "exclusions": ["uncovered switching events", "lost ZVS/diode heat",
                                   "bridge waveform/hot VF", "interface pressure/contact",
                                   "package thermal asymmetry"],
                })
    write_json("heatsink_requirement.json", {"board_sha256": BOARD_HASH, "cases": thermal,
        "aavid_63730_reference": {"length_required_mm": 153,
            "profile_width_mm": 76.2, "profile_height_mm": 57.15,
            "natural_c_per_w_catalog": 1.88,
            "forced_curve_status": "present but not digitized/qualified as numerical input",
            "warning": "curve is for 10W, centered 25.4mm source; not validated at approximately 50-150W, 153mm cut length, enclosure or distributed package placement"}})

    # Partition is explicit. Sink-mounted parts send all modeled heat to the
    # sink for this handoff; lead/board coupling requires B3 sensitivity.
    heat_sources = []
    for ref in sorted({x["ref"] for x in loss_records}):
        records = [x for x in loss_records if x["ref"] == ref]
        def total(scenario: str) -> float | None:
            known = [float(x["watts"]) for x in records
                     if x["scenario"] == scenario and x["watts"] is not None]
            return sum(known) if known else None
        fraction = next((x["sink_fraction"] for x in records if x["sink_fraction"] is not None), None)
        pad_xy = [pad["centre_mm"] for pad in parts[ref]["pads"]]
        assert pad_xy, ref
        pos = [(min(pt[axis] for pt in pad_xy) + max(pt[axis] for pt in pad_xy)) / 2
               for axis in (0, 1)]
        nominal, worst = total("nominal_example"), total("high_current_unprotected_stress")
        heat_sources.append({"ref": ref, "part": parts[ref]["part"], "x_mm": pos[0], "y_mm": pos[1],
            "xy_method": "midpoint of pad-centre bounding box; body thermal centroid unverified",
            "footprint_anchor_mm": parts[ref]["centre_mm"],
            "watts_nominal": None if nominal is None else round(nominal, 8),
            "watts_worst": None if worst is None else round(worst, 8),
            "board_fraction": None if fraction is None else 1 - fraction,
            "sink_fraction": fraction,
            "has_unquantified_loss": any(x["watts"] is None for x in records),
            "use_as_complete_b3_heat_source": False})
    write_json("board_heat_sources.json", {"board_sha256": BOARD_HASH,
        "status": "partial conditional heat map; not a complete B3 input",
        "nominal_run_id": selected["nominal_example"],
        "worst_run_id": selected["high_current_unprotected_stress"],
        "parts": heat_sources})

    with (OUTPUT / "losses.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(loss_records[0]))
        writer.writeheader()
        writer.writerows(loss_records)
    write_json("losses.json", {"board_sha256": BOARD_HASH,
        "status": "partial conditional calculations, unknown entries retained as null",
        "summaries": summaries, "records": loss_records})
    paths = [*INPUT.glob("*"), *SOURCE.glob("*.pdf")]
    write_json("provenance.json", {"board_sha256": BOARD_HASH,
        "source_commit": "44417ae1489fd00e2d652fd3b2c1582b76d17630",
        "input_sha256": {str(p.relative_to(HERE)): digest(p) for p in sorted(paths)}})


if __name__ == "__main__":
    main()
