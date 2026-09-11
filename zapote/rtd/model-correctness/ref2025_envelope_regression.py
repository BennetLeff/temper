#!/usr/bin/env python3
"""Regression for the REF2025 corner envelope in the RTD static model.

The frozen model used 3/8 ppm/V/mA and measured line/load deltas around 3.3 V.
REF2025's quoted initial accuracy is at VIN=5 V, with 35 ppm/V maximum line
regulation and 20 ppm/mA maximum load regulation.  This proof compares the
frozen generator with the revised copy without changing the frozen artifact.
It is a model-envelope regression, not a PVT or physical-accuracy proof.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[3]
OLD = ROOT / "zapote" / "rtd" / "circuit" / "rtdin_comparator_model.py"
REVISED = Path(__file__).resolve().parent / "revised" / "rtdin_comparator_model.py"
OUT = Path(__file__).resolve().parent / "ref2025_envelope_regression.json"

# REF2025AIDDCR datasheet traceability is retained by the parent audit in
# model-correctness/sources/ref20-sbos600f.pdf and its datasheet-audit.json.
NOMINAL_V = 1.25
VIN_TEST_V = 5.0
VIN_MIN_V = 3.135
VIN_MAX_V = 3.465
INITIAL_FRACTION = 0.0005
DRIFT_PPM_PER_C = 8.0
LINE_PPM_PER_V = 35.0
LOAD_PPM_PER_MA = 20.0
DELTA_C = 60.0
# Rounded upward from 0.096343 mA: minimum 61.9 kΩ/10 kΩ and 5.9 kΩ/10 kΩ
# divider sums evaluated at the corrected maximum VBIAS.
VBIAS_LOAD_MA = 0.096350


def load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def actual_fraction() -> float:
    line_span = max(abs(VIN_MIN_V - VIN_TEST_V), abs(VIN_MAX_V - VIN_TEST_V))
    return (
        INITIAL_FRACTION
        + DRIFT_PPM_PER_C * 1e-6 * DELTA_C
        + LINE_PPM_PER_V * 1e-6 * line_span
        + LOAD_PPM_PER_MA * 1e-6 * VBIAS_LOAD_MA
    )


def vref_range(module: ModuleType) -> tuple[float, float]:
    values = tuple(c.vref for c in module.corners())
    return min(values), max(values)


def representative_rows(module: ModuleType, vref: float) -> dict[str, dict[str, float | bool]]:
    # Hold all non-reference parameters at their nominal midpoint.  This
    # isolates the effect of the corrected reference envelope.
    nominal = module.Corner(
        vb=2.0,
        rref=430.0,
        vref=vref,
        rlt=61900.0,
        rlb=10000.0,
        rht=5900.0,
        rhb=10000.0,
        rdiag_p=1e6,
        rdiag_n=1e6,
        voffl=0.0,
        voffh=0.0,
        ileak_max_sensep=0.0,
        ileak_sensem=0.0,
        ileak_windowp=0.0,
        ileak_lowth=0.0,
        ileak_highth=0.0,
    )
    result: dict[str, dict[str, float | bool]] = {}
    for case in ("healthy", "FORCE+", "SENSE+", "SENSE-", "FORCE-"):
        row = module.solve(case, 194.1, 1.0, nominal)
        result[case] = {
            "low_margin_v": row.low_margin,
            "high_margin_v": row.high_margin,
            "fault_polarity_matches": (
                (row.low_margin > 0 and row.high_margin > 0)
                if case == "healthy"
                else (row.low_margin < 0 if case in ("FORCE+", "SENSE-") else row.high_margin < 0)
            ),
        }
    return result


def main() -> None:
    old = load("old_rtd_model", OLD)
    revised = load("revised_rtd_model", REVISED)
    required = actual_fraction()
    old_min, old_max = vref_range(old)
    new_min, new_max = vref_range(revised)
    self_consistent_load = revised.self_consistent_vbias_load_ma()
    required_min = NOMINAL_V * (1.0 - required)
    required_max = NOMINAL_V * (1.0 + required)
    receipt = {
        "schema": "rtd_ref2025_model_envelope_regression.v1",
        "old_model": str(OLD),
        "revised_model": str(REVISED),
        "datasheet_inputs": {
            "nominal_v": NOMINAL_V,
            "initial_accuracy_fraction": INITIAL_FRACTION,
            "initial_accuracy_test_vin": VIN_TEST_V,
            "vin_contract_v": [VIN_MIN_V, VIN_MAX_V],
            "line_regulation_max_ppm_per_v": LINE_PPM_PER_V,
            "load_regulation_max_ppm_per_ma": LOAD_PPM_PER_MA,
            "temperature_drift_ppm_per_c": DRIFT_PPM_PER_C,
            "temperature_delta_c": DELTA_C,
            "declared_vbias_load_ma": VBIAS_LOAD_MA,
            "self_consistent_vbias_load_ma": self_consistent_load,
            "self_consistency_margin_ua": (VBIAS_LOAD_MA - self_consistent_load) * 1e3,
            "self_consistency_assumption": (
                "sensem >= 0 V; minimum divider resistances; +5 nA at each comparator input"
            ),
        },
        "required_vref_v": [required_min, required_max],
        "old_vref_v": [old_min, old_max],
        "revised_vref_v": [new_min, new_max],
        "old_underbound_lower_v": old_min > required_min,
        "old_underbound_upper_v": old_max < required_max,
        "revised_meets_lower_v": new_min <= required_min,
        "revised_meets_upper_v": new_max >= required_max,
        "representative_classification": {
            "old_low": representative_rows(old, old_min),
            "old_high": representative_rows(old, old_max),
            "revised_low": representative_rows(revised, new_min),
            "revised_high": representative_rows(revised, new_max),
        },
    }
    assert receipt["old_underbound_lower_v"] and receipt["old_underbound_upper_v"]
    assert receipt["revised_meets_lower_v"] and receipt["revised_meets_upper_v"]
    assert self_consistent_load <= VBIAS_LOAD_MA
    for group in receipt["representative_classification"].values():
        assert all(row["fault_polarity_matches"] for row in group.values())
    OUT.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
