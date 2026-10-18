"""Unit and mutation tests for evidence_compare (run: python3 -m pytest -q output/temper-sensor-r3)."""

import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evidence_compare as EC  # noqa: E402

BOX, MAC = "linux-x86_64", "darwin-arm64"


def evidence(platform=BOX):
    return {
        "reference_platform": platform,
        "summary": {"hazardous_runs": 277, "before_300": 69, "glass_bound_C": 246.482361, "all_pass": True},
        "leak_rows": [{"r_leak_ohm": 2319.9, "T_c_max": 301.9, "first_latch_s": 1195.5, "hazardous": True,
                       "first_latch": {"rule": "rim_limit"}}],
        "apparatus": {"input_sha256": {"output/temper-sensor-r3/firmware/leak-checks.json": "aa" * 32,
                                       "firmware/components/control/pan_rim_limit.c": "bb" * 32},
                      "library_sha256": "cc" * 32,
                      "source_inputs_dirty_against_base": []},
    }


def mac(e):
    e = copy.deepcopy(e)
    e["reference_platform"] = MAC
    return e


def test_identical_same_platform_passes():
    assert EC.compare(evidence(), evidence()).ok


def test_count_plus_one_fails_on_both_rules():
    for fresh in (evidence(), mac(evidence())):
        fresh["summary"]["hazardous_runs"] += 1
        assert not EC.compare(evidence(), fresh).ok


def test_row_temperature_drift_passes_cross_but_not_same_platform():
    same, cross = evidence(), mac(evidence())
    same["leak_rows"][0]["T_c_max"] += 0.3
    cross["leak_rows"][0]["T_c_max"] += 0.3
    assert not EC.compare(evidence(), same).ok
    assert EC.compare(evidence(), cross).ok


def test_row_drift_beyond_tolerance_fails_without_an_outlier_allowance():
    cross = mac(evidence())
    cross["leak_rows"][0]["T_c_max"] += 1.8
    assert not EC.compare(evidence(), cross).ok


def test_rows_file_allows_listed_outliers():
    rows = {"250": {"nominal": [{"T_c_steady": 425.2}]}}
    fresh = {"250": {"nominal": [{"T_c_steady": 423.4}]}}
    res = EC.compare(rows, fresh, name="setpoint-cap-rows.json.gz", cross=True)
    assert res.ok and len(res.outliers) == 1


def test_summary_float_is_tight_across_platforms():
    cross = mac(evidence())
    cross["summary"]["glass_bound_C"] += 0.3
    assert not EC.compare(evidence(), cross).ok
    cross["summary"]["glass_bound_C"] = 246.482361 + 1.6e-5
    assert EC.compare(evidence(), cross).ok


def test_flipped_hazard_flag_fails():
    cross = mac(evidence())
    cross["leak_rows"][0]["hazardous"] = False
    assert not EC.compare(evidence(), cross).ok


def test_changed_latch_rule_fails():
    cross = mac(evidence())
    cross["leak_rows"][0]["first_latch"]["rule"] = "leak"
    assert not EC.compare(evidence(), cross).ok


def test_gate_boolean_fails():
    cross = mac(evidence())
    cross["summary"]["all_pass"] = False
    assert not EC.compare(evidence(), cross).ok


def test_generated_hash_ignored_but_source_hash_exact_across_platforms():
    cross = mac(evidence())
    cross["apparatus"]["input_sha256"]["output/temper-sensor-r3/firmware/leak-checks.json"] = "dd" * 32
    cross["apparatus"]["library_sha256"] = "ee" * 32
    assert EC.compare(evidence(), cross).ok
    cross["apparatus"]["input_sha256"]["firmware/components/control/pan_rim_limit.c"] = "ff" * 32
    assert not EC.compare(evidence(), cross).ok


def test_generated_hash_exact_on_same_platform():
    same = evidence()
    same["apparatus"]["library_sha256"] = "ee" * 32
    assert not EC.compare(evidence(), same).ok


def test_dirty_lists_drop_generated_names_across_platforms():
    cross = mac(evidence())
    cross["apparatus"]["source_inputs_dirty_against_base"] = ["output/temper-sensor-r3/firmware/cold-soak.json"]
    assert EC.compare(evidence(), cross).ok
    cross["apparatus"]["source_inputs_dirty_against_base"] = ["firmware/main/pan_control.c"]
    assert not EC.compare(evidence(), cross).ok


def test_missing_key_fails():
    cross = mac(evidence())
    del cross["summary"]["before_300"]
    assert not EC.compare(evidence(), cross).ok


def test_text_numbers_compare_with_tolerance_and_integers_exactly():
    a = "| 200 | 99/179 (55.3) | 301.12 |"
    assert EC.compare(a, "| 200 | 99/179 (55.3) | 301.30 |", name="x/NOTES-t2.md", cross=True).ok
    assert not EC.compare(a, "| 200 | 98/179 (55.3) | 301.12 |", name="x/NOTES-t2.md", cross=True).ok
    assert not EC.compare(a, "| 200 | 99/179 (55.3) | 301.30 |", name="x/NOTES-t2.md", cross=False).ok


def test_stamp_puts_platform_first():
    out = EC.stamp({"a": 1, "reference_platform": "old"})
    assert list(out) == ["reference_platform", "a"] and out["reference_platform"] == EC.platform_id()


def test_no_platform_on_either_side_is_exact():
    a = {"x": 1.0}
    assert not EC.compare(a, {"x": 1.0 + 1e-9}).ok


def test_rounded_h_model_is_a_row_float_but_other_ints_stay_exact():
    a = {"reference_platform": BOX, "rows": [{"h_model_end": 386, "cs_events": [[12.0, "accept", 386]],
                                              "cs_accepts": 3}]}
    b = copy.deepcopy(a)
    b["reference_platform"] = MAC
    b["rows"][0]["h_model_end"] = 387
    b["rows"][0]["cs_events"][0][2] = 387
    assert EC.compare(a, b).ok
    b["rows"][0]["h_model_end"] = 389
    assert not EC.compare(a, b).ok
    b["rows"][0]["h_model_end"] = 387
    assert not EC.compare(a, {**b, "reference_platform": BOX}).ok
    b["rows"][0]["cs_accepts"] = 4
    assert not EC.compare(a, b).ok


def test_d1_lost_case_diagnostics_are_rows_but_their_count_is_exact():
    a = {"reference_platform": BOX, "caps": {"230": {"lost_count": 1, "lost_cases": [
        {"diagnostics": {"events": [{"point": {"p_applied_W": 88.99288940429688}}]}}]}}}
    b = copy.deepcopy(a)
    b["reference_platform"] = MAC
    b["caps"]["230"]["lost_cases"][0]["diagnostics"]["events"][0]["point"]["p_applied_W"] = 88.9818115234375
    assert EC.compare(a, b).ok
    b["caps"]["230"]["lost_count"] = 2
    assert not EC.compare(a, b).ok
