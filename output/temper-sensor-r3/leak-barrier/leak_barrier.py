"""T1: reproduce the sampled leak barrier and expose its metrology/lifetime limits.

Uses the committed leak sweep and imports its Pt100 conversion unchanged; compiles
and calls the production MAX31865 conversion as an independent digital check.
No existing evidence is regenerated. See NOTES.md for the finite-grid limitation.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import math
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import evidence_compare as EC  # noqa: E402  (platform stamp and cross-platform check)


def rounded(value):
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite result")
        return float(f"{value:.12g}")
    if isinstance(value, dict):
        return {str(k): rounded(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [rounded(v) for v in value]
    return value


def derive(repo):
    fw = repo / "output/temper-sensor-r3/firmware"
    sys.path.insert(0, str(fw))
    import hs_ntc as H
    import leak_checks as LC
    import numpy as np
    import xcheck_cosim as X

    evidence = json.loads((fw / "leak-checks.json").read_text())
    soak_budget = json.loads((fw / "hs-ntc.json").read_text())
    rows = evidence["leak_rows"]
    bar = LC.T_BAR
    hazardous = [r for r in rows if LC.hazardous(r)]
    worst = max(r["r_leak_ohm"] for r in hazardous)
    next_r = min(r for r in evidence["r_leak_ohm"] if r > worst)
    next_rows = [r for r in rows if r["r_leak_ohm"] == next_r]
    assert not any(LC.hazardous(r) for r in next_rows)
    grouped = defaultdict(list)
    for r in rows:
        grouped[(r["pan"], r["delta"], r["corner"])].append(r)
    per_corner = []
    for (pan, delta, corner), rr in sorted(grouped.items()):
        hh = [r for r in rr if LC.hazardous(r)]
        per_corner.append({
            "pan": pan, "glass_offset_K": delta, "bead_corner": corner,
            "sample_count": len(rr), "hazardous_count": len(hh),
            "highest_sampled_hazardous_ohm": max((r["r_leak_ohm"] for r in hh), default=None),
            "highest_sampled_hazardous_by_onset_ohm": {
                onset: max((r["r_leak_ohm"] for r in hh if r["onset"] == onset), default=None)
                for onset in LC.ONSETS},
            "next_sample_max_steady_C": max(r["T_c_steady"] for r in rr if r["r_leak_ohm"] == next_r),
            "next_sample_max_transient_C": max(r["T_c_max"] for r in rr if r["r_leak_ohm"] == next_r),
        })
    hazard = {
        "criterion": ("the untripped T_c crosses bar_C at any time, transient overshoot included "
                      "(leak_checks.hazardous; owner 2026-10-16, was T_c_steady > bar_C)"),
        "bar_C": bar, "runs": len(rows), "hazardous_runs": len(hazardous),
        "latched_before_bar": sum(r["latched_before_300"] for r in hazardous),
        "highest_sampled_hazardous_ohm": worst,
        "highest_sampled_hazardous_max_steady_C": max(r["T_c_steady"] for r in rows if r["r_leak_ohm"] == worst),
        "highest_sampled_hazardous_max_transient_C": max(r["T_c_max"] for r in rows if r["r_leak_ohm"] == worst),
        "highest_sampled_hazardous_runs_over_bar": sum(LC.hazardous(r) for r in rows if r["r_leak_ohm"] == worst),
        "highest_sampled_runs": sum(r["r_leak_ohm"] == worst for r in rows),
        "continuous_hazardous_threshold_ohm": None,
        "continuous_status": "not identified by finite samples; no monotonicity or convergence certificate",
        "next_sample_ohm": next_r, "unsampled_gap_ohm": next_r - worst,
        "next_sample_max_steady_C": max(r["T_c_steady"] for r in next_rows),
        "next_sample_steady_headroom_K": bar - max(r["T_c_steady"] for r in next_rows),
        "next_sample_max_transient_C": max(r["T_c_max"] for r in next_rows),
        "next_sample_runs_transient_over_bar": sum(r["T_c_max"] > bar for r in next_rows),
        "next_sample_max_abs_tail_drift_K": max(abs(r["T_c_drift_last_100s"]) for r in next_rows),
        "source_steady_rounding_K": 0.1, "source_tail_window_s": 100,
        "source_duration_s": evidence["t_end_s"], "source_fry_setpoint_C": evidence["sp_fry_C"],
        "glass_offsets_K": list(LC.DELTAS), "bead_tolerance_at_250C_K": 10.2,
        "per_pan_corner": per_corner,
    }

    def error(t, resistance):
        return t - X.pt100_read(t, resistance)

    def limit(error_k):
        lo, hi = 1e3, 1e10
        assert error(bar, lo) > error_k > error(bar, hi)
        for _ in range(100):
            mid = math.sqrt(lo * hi)
            if error(bar, mid) > error_k:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    # The co-sim uses a continuous IEC conversion. The actual firmware also
    # quantizes to ADC codes and subtracts self-heating; keep these distinct.
    class Params(ctypes.Structure):
        _fields_ = [("r_ref_ohm", ctypes.c_float), ("r0_ohm", ctypes.c_float),
                    ("loading_correction", ctypes.c_bool), ("loading_k1", ctypes.c_float),
                    ("loading_k0_ohm", ctypes.c_float), ("self_heating_k", ctypes.c_float)]

    sensors = repo / "firmware/components/sensors"
    with tempfile.TemporaryDirectory(prefix="temper-t1-") as tmp:
        lib_path = Path(tmp) / "rtd.so"
        subprocess.run(["cc", "-std=c99", "-O2", "-shared", "-fPIC", "-Wall", "-Wextra", "-Werror",
                        f"-I{sensors / 'include'}", str(sensors / "rtd_convert.c"), "-lm", "-o", str(lib_path)],
                       check=True, capture_output=True, text=True)
        lib = ctypes.CDLL(str(lib_path))
        lib.rtd_convert_default_params.argtypes = [ctypes.POINTER(Params)]
        lib.rtd_convert_ohm_to_c.argtypes = [ctypes.c_float, ctypes.c_float]
        lib.rtd_convert_ohm_to_c.restype = ctypes.c_float
        lib.rtd_convert_code_to_c.argtypes = [ctypes.POINTER(Params), ctypes.c_uint16]
        lib.rtd_convert_code_to_c.restype = ctypes.c_float
        p = Params()
        lib.rtd_convert_default_params(ctypes.byref(p))
        errors = []
        c_disagreement = []
        for t in (25.0, 150.0, 250.0, bar):
            r = 100 * (1 + X.A * t + X.B * t * t)
            intact_code = int(math.floor(r / p.r_ref_ohm * 32768 + 0.5))
            intact_c = lib.rtd_convert_code_to_c(ctypes.byref(p), intact_code)
            for leak in (worst, next_r, 1.04e6, 10e6, 100e6):
                parallel = r * leak / (r + leak)
                analog = X.pt100_read(t, leak)
                c_analog = lib.rtd_convert_ohm_to_c(parallel, p.r0_ohm)
                code = int(math.floor(parallel / p.r_ref_ohm * 32768 + 0.5))
                digital = lib.rtd_convert_code_to_c(ctypes.byref(p), code)
                c_disagreement.append(abs(c_analog - analog))
                errors.append({"true_C": t, "parallel_ohm": leak, "element_ohm": r,
                               "ideal_reading_C": analog, "ideal_reading_low_K": t - analog,
                               "firmware_analog_C": c_analog, "intact_adc_code": intact_code,
                               "leaky_adc_code": code, "firmware_leaky_C": digital,
                               "firmware_intact_C": intact_c, "digital_incremental_low_K": intact_c - digital})
        converter = {"r_ref_ohm": p.r_ref_ohm, "adc_codes": 32768,
                     "self_heating_subtraction_K": p.self_heating_k,
                     "loading_correction": p.loading_correction,
                     "max_analog_C_vs_python_difference_K": max(c_disagreement),
                     "agreement_gate_K": 0.0001,
                     "meaning": "nominal ADC illustration, nearest-code rounding, no noise or analog tolerances; not a 10 Mohm measurement"}

    insulation = {"minimum_ohm": 10e6, "test_C": bar, "lifetime_hazard_multiplier": 10,
                  "candidate_supplier_ohm": 100e6, "candidate_supplier_C": 350,
                  "candidate_bores": 4, "candidate_status": "pending supplier confirmation; no material measurement available",
                  "margin_to_sampled_hazard": {str(int(r)): r / worst for r in (10e6, 100e6)},
                  "margin_to_next_sample_sensitivity_only": {str(int(r)): r / next_r for r in (10e6, 100e6)}}
    # A positive element deviation can hide a negative parallel-leak error.
    # Do not silently assume ideal elements or calibrate away a final-test leak.
    metrology = {"reference_bound_K": 0.10, "fixture_gradient_bound_K": 0.10,
                 "readout_bound_K": 0.05, "positive_element_bound_K": float(H.PT_CLASS_K(bar)),
                 "status": "proposed bounded allowances, not measured uncertainties; validate the fixture before release"}
    measurement_bound = sum(metrology[k] for k in ("reference_bound_K", "fixture_gradient_bound_K", "readout_bound_K"))
    metrology["measurement_bound_K"] = measurement_bound
    metrology["positive_mask_bound_K"] = measurement_bound + metrology["positive_element_bound_K"]
    acceptance = []
    for a in (0.25, 0.5, 1.0):
        ideal = limit(a)
        reference = limit(a + metrology["reference_bound_K"])
        guaranteed = limit(a + metrology["positive_mask_bound_K"])
        acceptance.append({"measured_acceptance_K": a, "ideal_boundary_ohm": ideal,
                           "reference_only_boundary_ohm": reference,
                           "full_mask_budget_boundary_ohm": guaranteed,
                           "ideal_margin_to_sampled_hazard": ideal / worst,
                           "full_budget_margin_to_sampled_hazard": guaranteed / worst,
                           "full_budget_margin_to_next_sample": guaranteed / next_r,
                           "accepted_true_error_bound_K": a + measurement_bound,
                           "guaranteed_detection": "strictly below boundary, with all stated bounds valid; equality may pass"})

    # Arrhenius conduction R(T) alone contains no time variable. A separate,
    # conditional exponential damage law is required for any lifetime budget.
    k_b = 8.617333262145e-5
    r0 = insulation["minimum_ohm"]
    target = worst * insulation["lifetime_hazard_multiplier"]
    log_budget = math.log(r0 / target)
    screen_floor = next(r["full_mask_budget_boundary_ohm"] for r in acceptance
                        if r["measured_acceptance_K"] == 0.5)
    example_k = 0.001
    ageing_rows = []
    for ea in (0.3, 0.6, 0.9, 1.2):
        for t in (250.0, 275.0, 300.0):
            relative_rate = math.exp(-ea / k_b * (1 / (t + 273.15) - 1 / (bar + 273.15)))
            for hours in (1000, 3000, 10000):
                equivalent = hours * relative_rate
                r_after = r0 * math.exp(-example_k * equivalent)
                ageing_rows.append({"Ea_eV": ea, "ageing_C": t, "hours": hours,
                                    "rate_relative_to_300C": relative_rate,
                                    "equivalent_300C_hours": equivalent,
                                    "maximum_k300_per_hour": log_budget / equivalent,
                                    "minimum_tau300_hours": equivalent / log_budget,
                                    "example_R300_after_ohm": r_after,
                                    "example_above_target": r_after > target,
                                    "verdict_from_production_test_alone": "undetermined"})
    ageing = {"law": "R300(t)=R300(0)*exp(-k300*sum(hours*exp(-Ea/kB*(1/T-1/T300))))",
              "temperature_units": "kelvin in the exponent; resistance always evaluated at 300 C after ageing",
              "initial_R300_ohm": r0, "target_R300_ohm": target,
              "log_degradation_budget": log_budget, "k_B_eV_per_K": k_b,
              "Ea_scope_eV": [0.3, 1.2],
              "material_interpretation": "sensitivity values for thermally activated ionic transport/contamination in glass or ceramic and seal/polymer degradation; no Ea is assigned to this silica, alumina, seal or enamel without supplier data; conduction Ea is not ageing Ea",
              "example_k300_per_hour": example_k, "example_status": "illustrative, unmeasured; never a qualification pass",
              "supplier_rate_or_life_anchor": None,
              "example_max_equivalent_300C_hours": log_budget / example_k,
              "initial_condition_status": "a hot-accuracy pass alone does not establish the assumed initial 10 Mohm across the connected element",
              "accuracy_screen_only_resistance_floor_ohm": screen_floor,
              "accuracy_screen_only_log_budget": math.log(screen_floor / target),
              "accuracy_screen_only_example_equivalent_hours": math.log(screen_floor / target) / example_k,
              "rows": ageing_rows}

    production = {"coverage_percent": 100, "ir_temperatures_C": [25, bar], "ir_voltage_Vdc": 100,
                  "ir_current_limit_mA": 1, "ir_dwell_s": 60,
                  "ir_relative_error_bound": 0.05,
                  "ir_relative_error_basis": "fraction of indicated resistance, including fixture and temperature effects",
                  "ir_accept_rounding_ohm": 10000,
                  "ir_display_accept_min_ohm": math.ceil(r0 / (1 - 0.05) / 10000) * 10000,
                  "accuracy_temperatures_C": [25, 150, 250, bar], "hot_measured_acceptance_K": 0.5,
                  "accuracy_stability_window_min": 5, "accuracy_stability_range_K": 0.05,
                  "max_readout_current_mA": 1,
                  "ir_voltage_status": "proposed; supplier must validate nondestructive stress for each insulation path; never across the connected Pt100",
                  "accuracy_other_points_status": "record all points and reject discontinuities; hot acceptance at 300 C is the quantified shunt screen",
                  "release_status": "proposed specification, not qualified; complete metrology and supplier/lifetime evidence first"}
    qualification = {
        "lots": 3, "per_group_assemblies": 24, "controls": 12, "ageing_assemblies": 36,
        "methods": ["IEC 60068-2-78 damp heat, steady state", "IEC 60068-2-14 change of temperature",
                    "IEC 60068-2-30 damp heat, cyclic", "dishwasher/wash exposure", "oil/fat soak at temperature",
                    "combined wash, thermal cycling and oil/fat exposure"],
        "standard_text_read": False,
        "standard_severities": "laboratory to select and approve from licensed method text and measured service profile; no compliance claim",
        "wash_cycles_proposed": 100, "wash_water_max_C_proposed": 70,
        "oil_hot_face_C_proposed": 250, "oil_hours_proposed": 168,
        "ageing_temperatures_C": [250, 275, 300], "ageing_read_hours": [1000, 3000, 10000],
        "allowed_failures": 0, "post_IR_ohm": r0, "post_IR_C": bar, "post_accuracy_acceptance_K": 0.5,
        "confidence_level": 0.95,
        "zero_failure_binomial_upper_failure_fraction": 1 - 0.05 ** (1 / 24),
    }
    qualification["total_assemblies"] = len(qualification["methods"]) * qualification["per_group_assemblies"] + qualification["controls"] + qualification["ageing_assemblies"]
    layers = {"glass_offset_K": list(LC.DELTAS), "bead_stack_at_250C_K": 10.2,
              "cold_soak_unknown_rail_threshold_K": soak_budget["cold_soak_budget"]["threshold_K"],
              "cold_soak_measured_rail_threshold_K": soak_budget["cold_soak_budget_rail_measured"]["threshold_K"],
              "cr5_original_glass_trip_band_C": list(X.CR5_BAND),
              "coverage": "none of leak-chain, rim-limit, cold-soak or CR-5 guarantees the first-crossing bar for all faults"}
    original = evidence["summary"]["requirements"]
    half = next(x for x in acceptance if x["measured_acceptance_K"] == 0.5)
    audit = {
        "D_LEAK_1": {"requirement_10Mohm_300C": "design input, not experimentally reproduced",
                     "supplier_4_bore_100Mohm_350C": "not reproducible; pending supplier confirmation",
                     "highest_hazard_ohm": worst, "ratio_10Mohm_to_hazard": round(r0 / worst),
                     "quoted_0_013K_reproduced": round(error(bar, 10e6), 3),
                     "quoted_0_001K_reproduced": round(error(bar, 100e6), 3)},
        "D_LEAK_2": {"quoted_acceptance_K": 0.5,
                     "legacy_rounded_boundary_ohm": original["hot_check_detects_parallel_r_below_ohm"],
                     "unrounded_ideal_boundary_ohm": half["ideal_boundary_ohm"],
                     "ratio_legacy_boundary_to_hazard": round(original["hot_check_detects_parallel_r_below_ohm"] / worst),
                     "status": "252 kohm reproduces only the ideal zero-uncertainty calculation; see acceptance for masked limits"},
        "D_LEAK_3": {"post_requirement_ohm": r0, "post_temperature_C": bar,
                     "status": "requirement input; no seal qualification evidence in this study"},
    }
    # Model and evidence inputs only: the decision documents are not read, and
    # hashing them failed this gate on every documentation edit.
    paths = [fw / name for name in ("leak-checks.json", "leak_checks.py", "xcheck_cosim.py", "hs_ntc.py",
                                   "hs-ntc.json", "ref.py", "cosim.py", "cosim_shim.c", "build_lib.sh")]
    paths += [sensors / "rtd_convert.c", sensors / "include/rtd_convert.h",
              repo / "output/temper-sensor-r3/screen.py", repo / "output/temper-sensor-r2/estimator_study.py"]
    controls = repo / "firmware/components/control"
    paths += sorted(controls.glob("*.c")) + sorted(controls.glob("*.h"))
    input_names = [str(p.relative_to(repo)) for p in paths]
    # Generated evidence inputs that differ from HEAD only by the platform's float
    # drift (evidence_compare) are not dirty; any source byte change is.
    dirty = bool(EC.dirty_inputs(repo, "HEAD", input_names))
    provenance = {"input_sha256": {str(p.relative_to(repo)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
                  "study_base_revision": "87edb1b329a39ffff54c4cc13e6a2bbac7f0c0e4",
                  "source_inputs_dirty": bool(dirty),
                  "derivation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  "numpy_version": np.__version__, "python_version": sys.version.split()[0],
                  "compiler": subprocess.check_output(["cc", "--version"], text=True).splitlines()[0],
                  "seed": "no random draws; reads the committed sweep including its deterministic seeds",
                  "scope": "model/evidence derivation, no physical measurements"}
    gates = {
        "source_inputs_clean": not dirty,
        "source_sweep_passed": evidence["all_pass"] and all(evidence["gate"].values()),
        "hazard_recomputed_matches_source": worst == original["highest_hazardous_r_leak_ohm"],
        "analog_conversion_agrees_with_C": max(c_disagreement) < converter["agreement_gate_K"],
        "ideal_boundary_reproduces_legacy_kohm": round(half["ideal_boundary_ohm"], -3) == original["hot_check_detects_parallel_r_below_ohm"],
        "uncertainty_reduces_detection": all(x["full_mask_budget_boundary_ohm"] < x["reference_only_boundary_ohm"] < x["ideal_boundary_ohm"] for x in acceptance),
        "production_IR_lower_bound_meets_design": production["ir_display_accept_min_ohm"]
            * (1 - production["ir_relative_error_bound"]) >= insulation["minimum_ohm"],
        "ageing_reference_rate_independent_of_Ea": all(r["rate_relative_to_300C"] == 1
                                                       for r in ageing_rows if r["ageing_C"] == bar),
        "ageing_example_retains_failure_cases": any(r["example_above_target"] for r in ageing_rows)
                                                and any(not r["example_above_target"] for r in ageing_rows),
    }
    return rounded({"task": "T1", "provenance": provenance, "hazard": hazard, "conversion": converter,
                    "reading_errors": errors, "insulation": insulation, "metrology": metrology,
                    "accuracy_acceptance": acceptance, "ageing": ageing, "production": production,
                    "qualification": qualification, "residual_layers": layers, "claim_audit": audit,
                    "gates": gates, "all_pass": all(gates.values())})


TOOLCHAIN_KEYS = ("compiler", "numpy_version", "python_version")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="compare regenerated evidence with the committed file (evidence_compare rule), without writing")
    ap.add_argument("--repo", type=Path, default=HERE.parent.parent.parent)
    ap.add_argument("--out", type=Path, default=HERE / "leak-barrier.json")
    args = ap.parse_args()
    try:
        result = derive(args.repo.resolve())
        result = EC.stamp(result)
        encoded = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
        if not result["all_pass"]:
            failed = [k for k, passed in result["gates"].items() if not passed]
            raise ValueError("derivation gates failed: " + ", ".join(failed))
        if args.check:
            # Toolchain strings are ignored; on the reference platform every other
            # value must match exactly, elsewhere within evidence_compare's rule.
            EC.assert_same(EC.strip_keys(json.loads(args.out.read_text()), "provenance", TOOLCHAIN_KEYS),
                           EC.strip_keys(result, "provenance", TOOLCHAIN_KEYS),
                           name="leak-barrier.json", label="T1")
        else:
            args.out.write_text(encoded)
        print("T1 PASS")
        return 0
    except (OSError, ValueError, KeyError, ImportError, AssertionError, subprocess.CalledProcessError) as exc:
        print(f"T1 FAIL: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
