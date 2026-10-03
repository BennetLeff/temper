#!/usr/bin/env python3
"""Summarize the evaluated 135 cases without claiming continuous-envelope bounds."""
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

TASK = Path(__file__).resolve().parents[1]
OUT = TASK / "outputs"


def main() -> None:
    with (OUT / "cases.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 135 or len({r["run_id"] for r in rows}) != 135:
        raise RuntimeError(f"expected 135 distinct cases, got {len(rows)}")
    quantities = (
        "frequency_hz", "f_res_hz", "i_rms_a", "i_pk_a", "vc_pk_v",
        "vc_rms_v", "c21_i_rms_a", "c22_i_rms_a", "c23_i_rms_a",
        "bleed_each_v_pk_v", "bleed_each_p_avg_w", "c_energy_pk_j",
    )
    extrema = {
        q: {
            "min": {"value": float(v[q]), "run_id": v["run_id"]}
                   if (v := min(rows, key=lambda r: float(r[q]))) else None,
            "max": {"value": float(v[q]), "run_id": v["run_id"]}
                   if (v := max(rows, key=lambda r: float(r[q]))) else None,
        }
        for q in quantities
    }
    a3_bytes = (TASK / "sources/a3-thresholds.json").read_bytes()
    a3 = json.loads(a3_bytes)
    ct_min = min(a3["extreme"][k]["min"] for k in ("ct_pos_a", "ct_neg_a"))
    ct_max = max(a3["extreme"][k]["max"] for k in ("ct_pos_a", "ct_neg_a"))
    ocp_min = a3["extreme"]["shunt_a"]["min"]
    ocp_max = a3["extreme"]["shunt_a"]["max"]
    def over(threshold):
        return [r["run_id"] for r in rows if float(r["i_pk_a"]) >= threshold]
    report = {
        "case_count": len(rows), "status_counts": dict(Counter(r["status"] for r in rows)),
        "evaluated_grid_only": True,
        "pan_classes": sorted({r["pan"] for r in rows}),
        "corners": sorted({r["corner"] for r in rows}),
        "line_vrms": sorted({float(r["vrms_v"]) for r in rows}),
        "power_targets_w": sorted({float(r["target_w"]) for r in rows}),
        "extrema": extrema,
        "capacitor_current_verdict": "BLOCKED: exact 942C12P22K-F and 942C12P1K-F current limit at operating frequency and 70-85 C not published",
        "zvs_verdict": "BLOCKED: qualified board ZVS thresholds unavailable; reference thresholds fail the independence gate",
        "r5_rms_rule": "ideal diagonal conduction: R5 RMS equals tank RMS; switching dead-time correction unquantified",
        "bleed_resistor_screen": {
            "maximum_working_voltage_v": 200,
            "working_voltage_basis": "DC or AC RMS; not instantaneous peak",
            "datasheet_source": "sources/rc1206.pdf printed pages 4-5, Yageo RC1206 V.2",
            "maximum_per_resistor_rms_v": max(float(r["vc_rms_v"]) / 4 for r in rows),
            "cases_above_working_voltage": [r["run_id"] for r in rows if float(r["vc_rms_v"]) / 4 > 200],
            "cases_with_peak_above_200_v": [r["run_id"] for r in rows if float(r["bleed_each_v_pk_v"]) > 200],
            "interpretation": "Each 470-kohm resistor sees nominal one-quarter tank-bank voltage. No evaluated RMS voltage exceeds the 200 V continuous DC/AC-RMS rating. Two peaks exceed 200 V, which is not itself a working-voltage failure. Repetitive waveform/peak stress, temperature and actual sharing require their own qualification."
        },
        "ct_88a_task_screen": {
            "cases_above_88a": [r["run_id"] for r in rows if float(r["i_pk_a"]) > 88],
            "interpretation": "Three unconstrained low-coupling full-power cases exceed the task's 88 A screen; Coilcraft labels 88 A sensed-current thermal reference, not an absolute instantaneous peak limit."
        },
        "protection_screen": {
            "source_file": "sources/a3-thresholds.json",
            "source_sha256": hashlib.sha256(a3_bytes).hexdigest(),
            "source_evidence_class": a3["evidence_class"],
            "ct_static_threshold_range_a": [ct_min, ct_max],
            "ocp_static_threshold_range_a": [ocp_min, ocp_max],
            "ct_nominal_a": a3["nominal"]["ct_pos_a"],
            "ocp_nominal_a": a3["nominal"]["shunt_a"],
            "ct_peak_above_min_cases": over(ct_min),
            "ct_peak_above_nominal_cases": over(a3["nominal"]["ct_pos_a"]),
            "ct_peak_above_max_cases": over(ct_max),
            "ocp_peak_above_min_cases": over(ocp_min),
            "ocp_peak_above_nominal_cases": over(a3["nominal"]["shunt_a"]),
            "ocp_peak_above_max_cases": over(ocp_max),
            "interpretation": "Instantaneous peak compared with static thresholds only; delay and phase duration still need A3 dynamic timing. Unconstrained requested-power cases crossing a threshold are not automatically sustainable thermal operating points; all simulated stresses remain retained."
        },
    }
    (OUT / "grid-summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
