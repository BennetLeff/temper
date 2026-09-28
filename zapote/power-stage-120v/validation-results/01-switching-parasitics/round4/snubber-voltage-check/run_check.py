#!/usr/bin/env python3
"""Probe actual external 1 nF snubber voltage on selected frozen C1 cases."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
POWER = HERE.parents[3]
A1 = POWER / "validation-results/01-switching-parasitics/round3/a1-zvs"
KIT = POWER / "validation-plan/sim-kit"
VENDOR = KIT / "models/vendor/IFX_CFD7_650V.lib"
ORIGINAL = A1 / "complementary_leg.cir"
PROBE = HERE / "probe.cir"
OUTPUTS = HERE / "outputs"
C1_DEFAULT = Path(
    "/Users/bennet/.codex/worktrees/ps-r4-c1/temper/zapote/power-stage-120v/"
    "validation-results/01-switching-parasitics/round4/c1-zvs"
)
EXPECTED_SOURCE = {
    ORIGINAL: "b2da52e71a9538d090f3c8828d29509d7c4870a6774667738d582abc52c9b902",
    A1 / "run_a1.py": "10607cee98257b8ac52ef282dfe2f78676a29b126437fcc7cde724f66a449377",
    KIT / "common/options.inc": "ae752d460d50fdbbcaaf03b29871b3b039cf27f018707efe4aa50d0fc3529330",
    VENDOR: "02ac6634f47c25be04e8de3c6eec4ec8cf403b659001b7f176c8f98bb6e9ce3b",
}
# Exact C1 grid cases. Each tuple is (bus V, DIR, RDT kΩ, current A).
# 39 kΩ includes hard, near-threshold and 40 A ZVS cases; 51 kΩ
# includes both sides of its threshold and 40 A ZVS cases.
SELECTION = (
    (120, 0, 39, 4),
    (120, 0, 39, 20),
    (120, 0, 39, 40),
    (120, 1, 39, 4),
    (120, 1, 39, 24),
    (120, 1, 39, 40),
    (198, 0, 39, 4),
    (198, 0, 39, 20),
    (198, 0, 39, 40),
    (198, 1, 39, 4),
    (198, 1, 39, 24),
    (198, 1, 39, 40),
    (120, 0, 51, 8),
    (120, 0, 51, 40),
    (120, 1, 51, 12),
    (120, 1, 51, 40),
    (198, 0, 51, 8),
    (198, 0, 51, 40),
    (198, 1, 51, 12),
    (198, 1, 51, 40),
)
TIMING_NS = {39: 348.4, 51: 451.6}
CAP_F = 1e-9


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def load_a1():
    spec = importlib.util.spec_from_file_location("frozen_a1", A1 / "run_a1.py")
    require(spec is not None and spec.loader is not None, "cannot import A1 runner")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def select_cases(c1: Path) -> list[dict]:
    with (c1 / "outputs/waveform_metrics.csv").open(newline="") as handle:
        catalog = list(csv.DictReader(handle))
    selected = []
    for bus, direction, ohm, current in SELECTION:
        matches = [
            row
            for row in catalog
            if int(row["bus_v"]) == bus
            and int(row["direction"]) == direction
            and abs(float(row["deadtime_ns"]) - TIMING_NS[ohm]) < 0.01
            and float(row["current_a"]) == current
            and float(row["board_l_scale"]) == 1.0
            and float(row["max_step_ns"]) == 0.2
        ]
        require(len(matches) == 1, f"expected one frozen C1 case: {(bus, direction, ohm, current)}")
        source_path = c1 / matches[0]["case_json"]
        wave_path = c1 / matches[0]["waveform"]
        source = json.loads(source_path.read_text())
        require(source["ngspice_returncode"] == 0, f"{source_path}: failed original run")
        require(matches[0]["incoming_channel_current_onset_s"], f"{source_path}: no valid onset")
        selected.append(
            {
                "rdt_kohm": ohm,
                "source_case": source,
                "source_onset_s": float(matches[0]["incoming_channel_current_onset_s"]),
                "source_case_path": str(source_path),
                "source_case_sha256": digest(source_path),
                "source_waveform_path": str(wave_path),
                "source_waveform_sha256": digest(wave_path),
            }
        )
    return selected


def channel_onset(wave: dict[str, np.ndarray], source: dict, new: dict) -> float | None:
    side = "xqh" if source["direction"] == 0 else "xql"
    time = wave["time"]
    channel = np.abs(wave[f"i(v.{side}.x1.v_ichannel)"])
    gate = wave[f"v({side}.g)"] - wave[f"v({side}.s)"]
    floor = max(0.1, 0.1 * source["current_a"])
    at = np.flatnonzero(
        (time >= new["command_on_s"])
        & (time + 2e-9 <= time[-1])
        & (channel >= floor)
        & (np.interp(time + 2e-9, time, channel) >= floor)
        & (gate >= 3.5)
        & (np.interp(time + 2e-9, time, gate) >= 3.5)
    )
    return float(time[at[0]]) if len(at) else None


def run_one(selected: dict, a1, ngspice_version: str, prior_manifest: dict | None) -> dict:
    source = selected["source_case"]
    key = Path(selected["source_case_path"]).parent.name
    folder = OUTPUTS / "runs" / key
    folder.mkdir(parents=True, exist_ok=True)
    result_path = folder / "case.json"
    if result_path.exists():
        cached = json.loads(result_path.read_text())
        require(
            cached["source_case_sha256"] == selected["source_case_sha256"], f"{key}: stale C1 case"
        )
        require(
            cached.get("source_waveform_sha256") == selected["source_waveform_sha256"],
            f"{key}: stale C1 waveform",
        )
        require(
            cached.get("frozen_channel_onset_s") == selected["source_onset_s"],
            f"{key}: stale C1 onset",
        )
        if "ngspice_version" in cached:
            require(cached["ngspice_version"] == ngspice_version, f"{key}: simulator changed")
        else:
            # Legacy cases predate per-case version capture. The original
            # selected_cases.json independently records their simulator/input identity.
            require(prior_manifest is not None, f"{key}: missing legacy provenance")
            require(prior_manifest["ngspice_version"] == ngspice_version,
                    f"{key}: legacy simulator changed")
            prior = next((row for row in prior_manifest["selected"]
                          if Path(row["source_case_path"]).parent.name == key), None)
            require(prior is not None and all(prior[field] == selected[field] for field in (
                "source_case_sha256", "source_waveform_sha256", "source_onset_s")),
                f"{key}: legacy source identity changed")
        require(cached["probe_deck_sha256"] == digest(PROBE), f"{key}: stale probe deck")
        require(
            digest(folder / "waves.raw.gz") == cached["raw_sha256_gzip"],
            f"{key}: incomplete cached raw",
        )
        require(
            digest(folder / "ngspice.log.gz") == cached["ngspice_log_sha256_gzip"],
            f"{key}: changed cached log",
        )
        return cached

    with tempfile.TemporaryDirectory(prefix="snubber-probe-") as temporary:
        work = Path(temporary)
        deck_text = PROBE.read_text().replace("../common/", str(KIT / "common") + "/")
        (work / PROBE.name).write_text(deck_text)
        params_text = "".join(f".param {k}={v}\n" for k, v in source["params"].items())
        (work / "params.inc").write_text(params_text)
        (work / ".spiceinit").write_text("set ngbehavior=psa\nset filetype=ascii\n")
        shutil.copyfile(VENDOR, work / VENDOR.name)
        proc = subprocess.run(
            ["/opt/homebrew/bin/ngspice", "-b", "-r", "waves.raw", PROBE.name],
            cwd=work,
            capture_output=True,
            text=True,
            timeout=1800,
        )
        log = proc.stdout + proc.stderr
        with gzip.open(folder / "ngspice.log.gz", "wt") as handle:
            handle.write(log)
        require(
            proc.returncode == 0
            and (work / "waves.raw").is_file()
            and not re.search(
                r"Timestep too small|simulation\(s\) aborted|singular matrix|fatal error", log, re.I
            ),
            f"{key}: ngspice failure rc={proc.returncode}, tail={log.splitlines()[-12:]}",
        )
        wave = a1.read_raw_selected(work / "waves.raw")
        require(all(np.isfinite(value).all() for value in wave.values()), f"{key}: nonfinite raw")
        with (
            (work / "waves.raw").open("rb") as source_file,
            gzip.open(folder / "waves.raw.gz", "wb") as saved,
        ):
            shutil.copyfileobj(source_file, saved)

    new = a1.analyze(
        wave,
        source["bus_v"],
        source["direction"],
        source["deadtime_ns"],
        source["current_a"],
        source["board_l_scale"],
        source["max_step_ns"],
    )
    t = wave["time"]
    frozen_onset = selected["source_onset_s"]
    onset = channel_onset(wave, source, new)
    require(onset is not None and abs(onset - frozen_onset) <= 1e-9, f"{key}: changed onset")
    side = "xqh" if source["direction"] == 0 else "xql"
    external = (
        wave["v(d_hs)"] - wave["v(s_hs)"]
        if source["direction"] == 0
        else wave["v(d_ls)"] - wave["v(s_ls)"]
    )
    die = wave[f"v({side}.dd)"] - wave[f"v({side}.s)"]
    cap_v = float(np.interp(frozen_onset, t, external))
    die_v = float(np.interp(frozen_onset, t, die))
    cap_j = 0.5 * CAP_F * cap_v**2
    proxy_j = 0.5 * CAP_F * die_v**2
    comparisons = {}
    for field in (
        "peak_die_vds_l_v",
        "peak_die_vds_h_v",
        "turnoff_model_dissipative_sum_j",
        "command_off_s",
        "command_on_s",
    ):
        baseline = source[field]
        candidate = new[field]
        comparisons[field] = {"frozen": baseline, "probe": candidate, "delta": candidate - baseline}
        tolerance = (
            max(0.1, 0.002 * abs(baseline))
            if field.startswith("peak_")
            else max(1e-10, 0.002 * abs(baseline))
            if field.endswith("_j")
            else 0.5e-9
        )
        require(abs(candidate - baseline) <= tolerance, f"{key}: probe changed {field}")
    require(new["zvs_20ns_5pct"] == source["zvs_20ns_5pct"], f"{key}: changed ZVS flag")
    result = {
        "case_id": key,
        "bus_v": source["bus_v"],
        "direction": source["direction"],
        "rdt_kohm": selected["rdt_kohm"],
        "deadtime_ns": source["deadtime_ns"],
        "current_a": source["current_a"],
        "zvs_20ns_5pct": source["zvs_20ns_5pct"],
        "source_case_sha256": selected["source_case_sha256"],
        "source_waveform_sha256": selected["source_waveform_sha256"],
        "params": source["params"],
        "probe_deck_sha256": digest(PROBE),
        "raw_sha256_gzip": digest(folder / "waves.raw.gz"),
        "ngspice_log_sha256_gzip": digest(folder / "ngspice.log.gz"),
        "frozen_channel_onset_s": frozen_onset,
        "probe_channel_onset_s": onset,
        "incoming_external_snubber_voltage_at_onset_v": cap_v,
        "incoming_die_vds_at_onset_v": die_v,
        "external_cap_energy_at_onset_j": cap_j,
        "die_vds_proxy_energy_at_onset_j": proxy_j,
        "proxy_minus_external_energy_j": proxy_j - cap_j,
        "proxy_over_external_ratio": proxy_j / cap_j if cap_j > 0 else None,
        "probe_comparisons": comparisons,
        "ngspice_returncode": proc.returncode,
        "ngspice_version": ngspice_version,
    }
    result_path.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print("PASS", key, f"proxy={proxy_j * 1e6:.4g}uJ actual={cap_j * 1e6:.4g}uJ", flush=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--c1-root", type=Path, default=C1_DEFAULT)
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    require(1 <= args.jobs <= 2, "at most two ngspice workers")
    for path, expected in EXPECTED_SOURCE.items():
        require(digest(path) == expected, f"source hash mismatch: {path}")
    source_deck = ORIGINAL.read_text()
    expected_probe = source_deck.replace(
        next(line for line in source_deck.splitlines() if line.startswith(".save ")),
        next(line for line in source_deck.splitlines() if line.startswith(".save "))
        + " v(d_hs) v(d_ls) v(s_ls)",
    )
    require(
        PROBE.read_text() == expected_probe, "probe deck changes more than saved external nodes"
    )
    selected = select_cases(args.c1_root)
    a1 = load_a1()
    OUTPUTS.mkdir(exist_ok=True)
    prior_path = HERE / "selected_cases.json"
    prior_manifest = json.loads(prior_path.read_text()) if prior_path.is_file() else None
    ngspice_version = next(
        line.strip()
        for line in subprocess.check_output(
            ["/opt/homebrew/bin/ngspice", "--version"],
            text=True, stderr=subprocess.STDOUT,
        ).splitlines()
        if "ngspice-" in line
    )
    provenance = {
        "source_revision": "829ee9debc08ce239bc2dffe0938c4fec2429545",
        "evidence_class": "20 selected frozen C1 reference-deck cases; diagnostic only",
        "source_hashes": {str(p.relative_to(POWER)): h for p, h in EXPECTED_SOURCE.items()},
        "probe_deck_sha256": digest(PROBE),
        "c1_catalog_sha256": digest(args.c1_root / "outputs/waveform_metrics.csv"),
        "selected": selected,
        "ngspice_version": ngspice_version,
    }
    with ThreadPoolExecutor(max_workers=args.jobs) as executor:
        futures = {executor.submit(run_one, row, a1, ngspice_version, prior_manifest): row
                   for row in selected}
        results = [future.result() for future in as_completed(futures)]
    results.sort(
        key=lambda row: (row["bus_v"], row["direction"], row["rdt_kohm"], row["current_a"])
    )
    (HERE / "selected_cases.json").write_text(
        json.dumps(provenance, indent=2, allow_nan=False) + "\n"
    )
    (HERE / "summary.json").write_text(json.dumps(results, indent=2, allow_nan=False) + "\n")
    fields = (
        "case_id",
        "bus_v",
        "direction",
        "rdt_kohm",
        "current_a",
        "zvs_20ns_5pct",
        "incoming_external_snubber_voltage_at_onset_v",
        "incoming_die_vds_at_onset_v",
        "external_cap_energy_at_onset_j",
        "die_vds_proxy_energy_at_onset_j",
        "proxy_minus_external_energy_j",
        "proxy_over_external_ratio",
    )
    with (HERE / "summary.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({name: row[name] for name in fields} for row in results)
    print("PASS", len(results), "selected cases", flush=True)


if __name__ == "__main__":
    main()
