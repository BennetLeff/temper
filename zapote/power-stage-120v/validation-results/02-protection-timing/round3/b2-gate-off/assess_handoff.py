"""Compare existing same-state trip results; no assumed shutdown-chain delay."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = HERE.parents[2]


def main() -> None:
    trip_path = RESULTS / "05-resonant-tank-envelope/round3/outputs/trip/summary.json"
    threshold_path = HERE.parent / "outputs/thresholds.json"
    trip = json.loads(trip_path.read_text())
    thresholds = json.loads(threshold_path.read_text())
    ovp = thresholds["extreme"]["ovp_v"]
    comparisons = []
    for row in trip["cases"]:
        # A passive isolated lumped model cannot give the bus more than all
        # its initial stored energy. This does not bound a different trip
        # state, extra source energy, or local inductive voltage overshoot.
        energy_ceiling = math.sqrt(
            2 * row["initial_total_stored_energy_j"] / row["bus_capacitance_f"]
        )
        comparisons.append({
            "case": row["tolerance_case"], "bus_peak_v": row["bus_peak_v"],
            "ovp_static_min_v": ovp["min"], "ovp_static_max_v": ovp["max"],
            "exceeds_static_ovp_min": row["bus_peak_v"] > ovp["min"],
            "d3_standoff_v": 295.0,
            "headroom_to_d3_standoff_v": 295.0 - row["bus_peak_v"],
            "same_state_isolated_model_energy_ceiling_v": energy_ceiling,
            "ceiling_scope": "No replenishment, no spatial overshoot, exactly A5's initial state",
        })
    result = {
        "status": "BLOCKED: actual gate-off current and dynamic F3",
        "inputs": {str(p.relative_to(RESULTS)): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in (trip_path, threshold_path)},
        "same_state_trip_comparisons": comparisons,
        "missing": [
            "Comparator latency qualified for the actual ramp/overdrive waveform",
            "Downstream interlock/PERMIT timing and actual persistent gate-off state",
            "Same-time tank current and capacitor voltage at that gate-off instant",
            "Qualified commutation/clamp parasitics, hot clamp pulse and repetition limits",
        ],
    }
    (HERE / "comparison.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
