"""Fast evidence-integrity tests; no C builds or co-simulation sweep required."""
from __future__ import annotations

import copy
import json
import math
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FW = REPO / "output/temper-sensor-r3/firmware"
sys.path.insert(0, str(FW))
sys.path.insert(0, str(FW.parent / "leak-barrier"))
import d1_nuisance as d1  # noqa: E402
import setpoint_cap  # noqa: E402


@pytest.fixture
def evidence():
    return {
        "toolchain": dict.fromkeys(("python", "numpy", "scipy", "matplotlib", "machine", "compiler"), "original"),
        "source_sha256": {"contact_check.c": "a" * 64},
        "caps": {"250": {"d1_lost_events": 2, "duration_s": 1.0}}, "gate": True,
    }


def test_check_ignores_only_named_toolchain_strings(evidence, monkeypatch, tmp_path, capsys):
    output = tmp_path / "evidence.json"
    monkeypatch.setattr(d1, "build_library", lambda *args: tmp_path / "unused.so")
    monkeypatch.setattr(d1, "run", lambda *args: evidence)
    monkeypatch.setattr(sys, "argv", ["d1_nuisance.py", "--check", "--out", str(output)])
    for key in ("python", "numpy", "scipy", "matplotlib", "machine", "compiler"):
        expected = copy.deepcopy(evidence)
        expected["toolchain"][key] = "different toolchain"
        output.write_text(json.dumps(expected))
        before = output.read_bytes()
        assert d1.main() == 0
        assert output.read_bytes() == before
    for path, value in (
        (("source_sha256", "contact_check.c"), "b" * 64),
        (("caps", "250", "d1_lost_events"), 1),
        (("caps", "250", "duration_s"), math.nextafter(1.0, math.inf)),
        (("toolchain", "unlisted_string"), "must not be ignored"),
        (("compiler",), "not a toolchain field at this location"),
    ):
        expected = copy.deepcopy(evidence)
        cursor = expected
        for part in path[:-1]:
            cursor = cursor[part]
        cursor[path[-1]] = value
        output.write_text(json.dumps(expected))
        assert d1.main() == 1
    assert "D1 nuisance evidence: MISMATCH" in capsys.readouterr().out
    evidence["toolchain"]["python"] = 42
    with pytest.raises(ValueError, match="must be a string"):
        d1.comparable(evidence)


@pytest.mark.parametrize("cap", [250, 230])
def test_factory_matches_cap_study_including_down_step(cap):
    previous = d1.LC.SP_FRY
    try:
        actual = d1.capped_cases(cap)
        assert d1.LC.SP_FRY == previous
        assert actual == setpoint_cap.capped_cases(cap)["stress_benign"]
        assert len(actual) == 132
        down = [case for case in actual if case["kind"] == "sp_down" and case["pan"] != "disc_pot_water_1l5"]
        assert down
        assert all(case["sp_profile"][-1] == (900.0, cap - 100.0) for case in down)
    finally:
        d1.LC.SP_FRY = previous


def test_off_interval_continues_after_restored_and_has_separate_censoring(monkeypatch):
    # Exercise actual event/interval extraction; the regression is orthogonal to duration accounting.
    monkeypatch.setattr(d1, "decision", lambda window, params, retry: {"n": len(window)})
    params = {"trig_window": 20, "dt_s": 0.1, "trig_rate_k_per_s": -0.8,
              "trig_pmin_frac": 0.4, "p_max_w": 1800.0}
    records = []
    for k in range(401):
        state = 0 if k == 0 or k >= 381 else 1 if k < 182 else 2 if k < 201 else 3
        event = {1: 1, 181: 3, 381: 4}.get(k, 0)
        if k == 181:
            state = 2
        output = {"cc_state": state, "cc_event": event, "t_hat": 25.0, "p_pid": 100.0}
        records.append({
            "t_s": round(k * 0.1, 1), "output": output, "contact_shift": {"event": 0},
            "forced": False, "xcheck": False, "p_applied_W": 0.0,
            "p_next_W": 100.0 if k in (0, 390) else 0.0, "supervisor": {"cut_power": False},
            **dict.fromkeys(("y_C", "rim_effective_C", "sp_C", "true_pan_C", "true_glass_C", "rim_raw_C"), 25.0),
            "rim_state": 0,
        })
    result = d1.analyse(records, params)
    assert [probe["decision"]["n"] for probe in result["probes"]] == [181, 181]
    lost = result["lost_episodes"][0]
    assert lost["t_restored_s"] == 38.1
    assert lost["first_resumed_power_s"] == 39.0
    assert lost["continuous_off_duration_s"] == 38.9
    assert not lost["continuous_off_right_censored"]
    records[390]["p_next_W"] = 0.0
    lost = d1.analyse(records, params)["lost_episodes"][0]
    assert not lost["right_censored"]
    assert lost["continuous_off_right_censored"]
    assert lost["first_resumed_power_s"] is None
    assert lost["continuous_off_duration_s"] == 40.0


def test_supplied_library_must_match_fresh_source_build(monkeypatch, tmp_path):
    supplied = tmp_path / "supplied.so"
    supplied.write_bytes(b"stale source")
    calls = []

    def build(command, *, check):
        calls.append(command)
        assert check
        (Path(command[1]) / "libpantemp.so").write_bytes(b"current source")

    monkeypatch.setattr(d1.subprocess, "run", build)
    with pytest.raises(RuntimeError, match="does not match the fresh build"):
        d1.build_library(tmp_path, supplied)
    supplied.write_bytes(b"current source")
    assert d1.build_library(tmp_path, supplied) == supplied.resolve()
    assert len(calls) == 2
    assert all(command[0] == str(d1.HERE / "build_lib.sh") for command in calls)
