#!/usr/bin/env python3
"""Replay frozen D2 waveforms with integrity checks and both VDS peak windows."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from run_integrity import check_result, check_wave, require

HERE = Path(__file__).resolve().parent
RESULT = HERE.parent
UNIT = HERE.parents[4]
sys.path.insert(0, str(UNIT / "validation-plan/sim-kit/common"))
from run_ngspice import read_raw  # noqa: E402

START = 2e-6
COMMAND_ON = 2.3505e-6
CLAMP_CENTRE = 2.345e-6
LEGACY_MEASURE_END = START + 348e-9 + 0.75e-6
CASES = (
    ("legacy_control", "0.2"),
    ("extended_instrumented", "0.2"),
    ("extended_instrumented", "0.1"),
    ("heuristic_ideal_offgate", "0.2"),
    ("heuristic_ideal_offgate", "0.1"),
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def one(name: str, step_ns: str, frozen: dict) -> dict:
    key = f"{name}_{step_ns}"
    folder = RESULT / "outputs/runs" / key
    pinned = frozen["runs"][key]
    raw = folder / "waves.raw"
    if (folder / "run-result.json").is_file():
        check_result(json.loads((folder / "run-result.json").read_text()))
    else:
        require(not pinned["exit_status_recorded"], f"{key}: recorded run status is missing")

    wave = {vector: np.asarray(values) for vector, values in read_raw(raw).items()}
    expected_end = START + 348e-9 + (0.8e-6 if name == "legacy_control" else 1.02e-6)
    t = check_wave(folder, wave, expected_end)
    for filename, field in (
        (f"{name}.cir", "copied_deck_sha256"),
        ("params.inc", "params_inc_sha256"),
        ("run.log", "run_log_sha256"),
        ("raw_run.log", "raw_run_log_sha256"),
        ("waves.raw", "raw_sha256"),
    ):
        require(
            digest(folder / filename) == pinned[field], f"{key}: {filename} differs from frozen run"
        )

    vds_l = wave["v(xql.dd)"] - wave["v(xql.s)"]
    vgs_l = wave["v(xql.g)"] - wave["v(xql.s)"]
    window = np.flatnonzero((t >= START) & (t <= LEGACY_MEASURE_END))
    full = np.flatnonzero(t >= START)
    after = np.flatnonzero(t >= COMMAND_ON)
    require(bool(len(window) and len(full) and len(after)), f"{key}: empty measurement window")
    i = window[int(np.argmax(vds_l[window]))]
    k = full[int(np.argmax(vds_l[full]))]
    j = after[int(np.argmax(vgs_l[after]))]
    out = {
        "case": name,
        "step_ns": float(step_ns),
        "raw_sha256": pinned["raw_sha256"],
        "samples": len(t),
        "last_time_s": float(t[-1]),
        "ls_die_vds_peak_v": float(vds_l[i]),
        "ls_die_vds_peak_time_s": float(t[i]),
        "ls_die_vgs_at_vds_peak_v": float(vgs_l[i]),
        "ls_die_vds_full_post_t1_peak_v": float(vds_l[k]),
        "ls_die_vds_full_post_t1_peak_time_s": float(t[k]),
        "ls_die_vgs_at_full_post_t1_peak_v": float(vgs_l[k]),
        "ls_die_vgs_after_partner_on_peak_v": float(vgs_l[j]),
        "ls_die_vgs_after_partner_on_peak_time_s": float(t[j]),
    }
    if "i(vidh)" in wave:
        out.update(
            {
                "ls_external_drain_at_vds_peak_a": float(wave["i(vids)"][i]),
                "hs_external_drain_at_vds_peak_a": float(wave["i(vidh)"][i]),
                "ls_gchan_including_breakdown_at_vds_peak_a": float(
                    wave["i(v.xql.x1.v_ichannel)"][i]
                ),
                "ls_epi_at_vds_peak_a": float(wave["i(v.xql.x1.v_iepi)"][i]),
                "ls_forward_body_diode_at_vds_peak_a": -float(wave["i(v.xql.x1.v_sense2)"][i]),
                "hs_forward_body_diode_at_vds_peak_a": -float(wave["i(v.xqh.x1.v_sense2)"][i]),
                "switch_at_vds_peak_v": float(wave["v(sw)"][i]),
                "local_cap_bus_at_vds_peak_v": float(wave["v(capm)"][i]),
            }
        )
    return out


def main() -> None:
    frozen = json.loads((RESULT / "outputs/frozen-run-provenance.json").read_text())
    require(
        set(frozen["runs"]) == {f"{name}_{step}" for name, step in CASES}, "frozen run set differs"
    )
    runs = [one(name, step, frozen) for name, step in CASES]
    by = {(r["case"], r["step_ns"]): r for r in runs}

    def peak(name: str, step: float) -> float:
        return by[name, step]["ls_die_vds_peak_v"]

    inputs = frozen["frozen_inputs_sha256"]
    comparison = {
        "source_revision": frozen["source_revision"],
        "evidence_class": frozen["evidence_class"],
        "board_sha256": inputs["board"],
        "frozen_netlist_reported_sha256": inputs["frozen_netlist_reported"],
        "original_deck_sha256": inputs["original_deck"],
        "heuristic_a2_sha256": inputs["heuristic_a2"],
        "vendor_model_sha256": inputs["vendor_model"],
        "decks_sha256": frozen["decks_sha256"],
        "frozen_run_provenance_sha256": digest(RESULT / "outputs/frozen-run-provenance.json"),
        "commands_s": {"ls_off": 2.0025e-6, "hs_on": COMMAND_ON},
        "delayed_gate_to_die_source_clamp_centre_s": CLAMP_CENTRE,
        "runs": runs,
        "instrumented_peak_step_change_fraction": abs(
            peak("extended_instrumented", 0.1) - peak("extended_instrumented", 0.2)
        )
        / peak("extended_instrumented", 0.1),
        "clamp_peak_step_change_fraction": abs(
            peak("heuristic_ideal_offgate", 0.1) - peak("heuristic_ideal_offgate", 0.2)
        )
        / peak("heuristic_ideal_offgate", 0.1),
        "legacy_to_instrumented_peak_change_fraction": abs(
            peak("legacy_control", 0.2) - peak("extended_instrumented", 0.2)
        )
        / peak("legacy_control", 0.2),
        "clamp_peak_reduction_v": peak("extended_instrumented", 0.1)
        - peak("heuristic_ideal_offgate", 0.1),
        "criteria_v": {"S1_normal": 520, "S2_fault": 585},
    }
    target = RESULT / "outputs/legacy-comparison.json"
    target.write_text(json.dumps(comparison, indent=2, allow_nan=False) + "\n")
    print(target)


if __name__ == "__main__":
    main()
