#!/usr/bin/env python3
"""Exercise the complementary CFD7 deck with explicitly non-board reference L.

This is a one-off model-mechanics check, not a native-13 acceptance gate.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import math
import sys
from bisect import bisect_left
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT = HERE.parents[2] / "validation-plan" / "sim-kit"
sys.path.insert(0, str(KIT / "common"))
from run_ngspice import read_raw, run  # noqa: E402

DECK = HERE / "complementary_leg.cir"
OUT = HERE / "outputs"
BOARD = HERE.parents[2] / "native-13" / "section.kicad_pcb"
MODEL = KIT / "models" / "vendor" / "IFX_CFD7_650V.lib"
EXPECTED_BOARD_HASH = "8056fc952675bc6987bcc9d32c12a88eebc4cec9bc3696f8cbd4876700a39129"
EXPECTED_MODEL_HASH = "02ac6634f47c25be04e8de3c6eec4ec8cf403b659001b7f176c8f98bb6e9ce3b"
T1 = 2e-6
VBUS = 198.0
NEEDED = {
    "vds_ls_die_pk", "vds_hs_die_pk", "vgs_ls_die_max", "vgs_ls_die_min",
    "vgs_hs_die_max", "vgs_hs_die_min",
}
VECTORS = (
    "v(sw)", "v(xql.g)", "v(xql.s)", "v(xqh.g)", "v(xqh.s)",
    "v(xql.dd)", "v(xqh.dd)", "v(gl_cmd)", "v(kret)", "v(gh_cmd)", "v(s_hs)",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sample_before(time: list[float], values: list[float], at: float) -> float:
    i = bisect_left(time, at)
    if i == 0 or i == len(time):
        raise ValueError(f"sample time outside waveform: {at}")
    return values[i - 1]


def crossing_after(time: list[float], values: list[float], at: float, level: float, rise: bool) -> float:
    start = bisect_left(time, at)
    for i in range(max(1, start), len(time)):
        a, b = values[i - 1], values[i]
        if (a < level <= b) if rise else (a > level >= b):
            fraction = (level - a) / (b - a)
            return time[i - 1] + fraction * (time[i] - time[i - 1])
    raise ValueError(f"no {'rising' if rise else 'falling'} crossing of {level} after {at}")


def save_window(path: Path, wave: dict[str, list[float]], values: dict[str, list[float]]) -> None:
    """Keep every simulator point around the commutation, with useful die nodes."""
    keys = ("sw", "gl_die", "gh_die", "vds_l_die", "vds_h_die", "cmd_l", "cmd_h")
    with gzip.open(path, "wt", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("time_s", *keys))
        for i, t in enumerate(wave["time"]):
            if 1.9e-6 <= t <= 2.85e-6:
                writer.writerow((format(t, ".12g"), *(format(values[k][i], ".9g") for k in keys)))


def check_case(direction: int, current: int, deadtime_ns: int, step_ns: float) -> dict:
    label = f"dir{direction}_i{current}_dt{deadtime_ns}_step{step_ns:g}ns"
    work = OUT / "runs" / label
    params = {
        "VBUS": "198", "IL": str(current), "DIR": str(direction),
        "DT": f"{deadtime_ns}n", "TRMAX": f"{step_ns}n",
        # Deliberately the starter kit's reference board L and capacitor ESL.
        "LD_HS": "4n", "LS_HS": "4n", "LD_LS": "4n", "LS_LS": "4n",
        "LCAP": "3n", "LBULK": "30n", "LCS": "1n", "LG": "20n",
    }
    result = run(DECK, params, keep=work, raw=True)
    (work / "run-result.json").write_text(json.dumps(result, indent=2) + "\n")
    if result["aborted"] or result["failed"] or NEEDED - result["meas"].keys():
        raise RuntimeError(f"ngspice failed in {label}: {result}")
    if result["returncode"] != 0 or result["raw_returncode"] != 0:
        raise RuntimeError(f"nonzero ngspice return code in {label}")
    wave = read_raw(work / "waves.raw")
    if any(key not in wave for key in VECTORS):
        raise RuntimeError(f"required raw node missing in {label}")
    time = wave["time"]
    expected_end = T1 + deadtime_ns * 1e-9 + 0.8e-6
    if not time or time[-1] < expected_end - 1e-12:
        raise RuntimeError(f"raw waveform ended early in {label}: {time[-1] if time else 'empty'}")
    values = {
        "sw": wave["v(sw)"],
        "gl_die": [a - b for a, b in zip(wave["v(xql.g)"], wave["v(xql.s)"])],
        "gh_die": [a - b for a, b in zip(wave["v(xqh.g)"], wave["v(xqh.s)"])],
        "vds_l_die": [a - b for a, b in zip(wave["v(xql.dd)"], wave["v(xql.s)"])],
        "vds_h_die": [a - b for a, b in zip(wave["v(xqh.dd)"], wave["v(xqh.s)"])],
        "cmd_l": [a - b for a, b in zip(wave["v(gl_cmd)"], wave["v(kret)"])],
        "cmd_h": [a - b for a, b in zip(wave["v(gh_cmd)"], wave["v(s_hs)"])],
    }
    incoming = "h" if direction == 0 else "l"
    outgoing = "l" if direction == 0 else "h"
    if sample_before(time, values[f"cmd_{outgoing}"], T1 - 10e-9) < 14.0:
        raise RuntimeError(f"outgoing command did not start high in {label}")
    if sample_before(time, values[f"cmd_{incoming}"], T1 - 10e-9) > 1.0:
        raise RuntimeError(f"incoming command did not start low in {label}")
    if sample_before(time, values[f"cmd_{incoming}"], expected_end - 10e-9) < 14.0:
        raise RuntimeError(f"incoming command did not finish high in {label}")
    if sample_before(time, values[f"cmd_{outgoing}"], expected_end - 10e-9) > 1.0:
        raise RuntimeError(f"outgoing command did not finish low in {label}")
    if any(a > 7.5 and b > 7.5 for a, b in zip(values["cmd_l"], values["cmd_h"])):
        raise RuntimeError(f"overlapping drive commands in {label}")
    command_off = crossing_after(time, values[f"cmd_{outgoing}"], T1 - 10e-9, 7.5, False)
    command_on = crossing_after(time, values[f"cmd_{incoming}"], T1, 7.5, True)
    measured_gap = command_on - command_off
    if abs(measured_gap - deadtime_ns * 1e-9) > 1e-9:
        raise RuntimeError(f"command dead time mismatch in {label}: {measured_gap}")
    window = [i for i, t in enumerate(time) if T1 <= t <= command_on + 0.25e-6]
    proxy_overlap = sum(
        time[i] - time[i - 1] for i in window if i > 0
        and values["gl_die"][i] > 3.0 and values["gh_die"][i] > 3.0
    )
    pre_vds = sample_before(time, values[f"vds_{incoming}_die"], command_on - 1e-9)
    pre_sw = sample_before(time, values["sw"], command_on - 1e-9)
    gate_proxy_time = crossing_after(time, values[f"g{incoming}_die"], command_on, 3.0, True)
    gate_proxy_vds = sample_before(time, values[f"vds_{incoming}_die"], gate_proxy_time)
    preceding_indices = [i for i, t in enumerate(time)
                         if command_on - 20e-9 <= t < command_on - 1e-9]
    low_vds_before_command = bool(preceding_indices) and all(
        abs(values[f"vds_{incoming}_die"][i]) <= 0.05 * VBUS for i in preceding_indices
    )
    peak_low = max(values["vds_l_die"][i] for i, t in enumerate(time) if T1 <= t <= expected_end - 0.05e-6)
    peak_high = max(values["vds_h_die"][i] for i, t in enumerate(time) if T1 <= t <= expected_end - 0.05e-6)
    for name, raw_peak in (("vds_ls_die_pk", peak_low), ("vds_hs_die_pk", peak_high)):
        if not math.isclose(raw_peak, result["meas"][name], rel_tol=0.002):
            raise RuntimeError(f"meas/raw disagreement in {label}: {name} {raw_peak} != {result['meas'][name]}")
    save_window(work / "commutation.csv.gz", wave, values)
    (work / "waves.raw").unlink()  # Regenerable from the copied deck, params and run script.
    (work / MODEL.name).unlink()  # Vendor-licensed model is fetched separately.
    (work / "run.log").rename(work / "run.txt")
    (work / "raw_run.log").rename(work / "raw_run.txt")
    record = {
        "case": label, "params": params, "end_s": time[-1], "sample_count": len(time),
        "command_off_s": command_off, "command_on_s": command_on,
        "command_gap_ns": measured_gap * 1e9,
        "die_gate_overlap_above_3v_ns": proxy_overlap * 1e9,
        "incoming_die_vds_before_command_v": pre_vds,
        "incoming_die_gate_3v_crossing_s": gate_proxy_time,
        "incoming_die_vds_at_gate_3v_v": gate_proxy_vds,
        "switch_node_before_command_v": pre_sw,
        "model_zvs_at_command_5pct_proxy": abs(pre_vds) <= 0.05 * VBUS,
        "low_vds_for_20ns_before_command_5pct_proxy": low_vds_before_command,
        "ngspice_returncode": result["returncode"], "raw_returncode": result["raw_returncode"],
    }
    if (current, deadtime_ns) != (37, 348):
        record["raw_peak_vds_l_v"] = peak_low
        record["raw_peak_vds_h_v"] = peak_high
    return record


def check_resolution(cases: list[dict]) -> list[dict]:
    """Require <2% change in both reported peaks when the max step halves."""
    by_key = {(c["params"]["DIR"], c["params"]["IL"], c["params"]["DT"],
               c["params"]["TRMAX"]): c for c in cases}
    checks = []
    for coarse in cases:
        if coarse["params"]["TRMAX"] != "0.2n" or "raw_peak_vds_l_v" not in coarse:
            continue
        key = (coarse["params"]["DIR"], coarse["params"]["IL"], coarse["params"]["DT"], "0.1n")
        fine = by_key[key]
        for peak in ("raw_peak_vds_l_v", "raw_peak_vds_h_v"):
            delta = abs(coarse[peak] - fine[peak]) / max(abs(fine[peak]), 1e-12)
            checks.append({"coarse_case": coarse["case"], "fine_case": fine["case"],
                           "metric": peak, "coarse_v": coarse[peak], "fine_v": fine[peak],
                           "relative_change": delta})
            if delta >= 0.02:
                raise RuntimeError(f"half-step peak change >=2%: {checks[-1]}")
    if len(checks) != 8:
        raise RuntimeError(f"expected 8 peak resolution checks, got {len(checks)}")
    return checks


def main() -> None:
    if digest(BOARD) != EXPECTED_BOARD_HASH or digest(MODEL) != EXPECTED_MODEL_HASH:
        raise RuntimeError("board or vendor model SHA-256 changed")
    OUT.mkdir(parents=True, exist_ok=True)
    cases = [
        (direction, current, deadtime_ns, 0.2)
        for direction in (0, 1)
        for current, deadtime_ns in ((2, 348), (37, 250), (37, 348))
    ]
    # Independent numerical-resolution check on the light-load hard edge and
    # on the short-deadtime condition in each direction.
    cases += [(direction, current, deadtime_ns, 0.1)
              for direction in (0, 1) for current, deadtime_ns in ((2, 348), (37, 250))]
    results = []
    for case in cases:
        result = check_case(*case)
        results.append(result)
        print("PASS", result["case"], flush=True)
    payload = {
        "evidence_class": "model-based reference case only",
        "board_sha256": digest(BOARD), "vendor_sha256": digest(MODEL),
        "deck_sha256": digest(DECK), "reference_l_not_board_extracted": True,
        "cases": results,
        "resolution_checks": check_resolution(results),
    }
    (OUT / "reference_cases.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps({"cases": len(results), "completed": [r["case"] for r in results]}, indent=2))


if __name__ == "__main__":
    main()
