"""Fail-closed checks for D2 ngspice logs and saved ASCII transient waves."""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np

MEAS_NAMES = {
    "vds_ls_die_pk",
    "vds_hs_die_pk",
    "vgs_ls_die_max",
    "vgs_ls_die_min",
    "vgs_hs_die_max",
    "vgs_hs_die_min",
}
ABORT = re.compile(
    r"timestep too small|simulation\(s\) aborted|singular matrix|fatal error|"
    r"\bfailed\b",
    re.IGNORECASE,
)
ROWS = re.compile(r"No\. of Data Rows\s*:\s*(\d+)")
MEAS = re.compile(r"^\s*([a-z_][a-z0-9_]*)\s*=\s*([-+0-9.eE]+)", re.IGNORECASE)
NPOINTS = re.compile(r"^No\. Points:\s*(\d+)", re.MULTILINE)
NVARS = re.compile(r"^No\. Variables:\s*(\d+)", re.MULTILINE)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def check_log(path: Path, *, measurements: bool) -> int:
    log = path.read_text()
    require(not ABORT.search(log), f"{path}: aborted or failed")
    rows = ROWS.findall(log)
    require(len(rows) == 1 and int(rows[0]) > 1, f"{path}: missing or ambiguous row count")
    require("Total analysis time (seconds)" in log, f"{path}: no completed analysis")
    if measurements:
        values = {
            m.group(1).lower(): float(m.group(2))
            for line in log.splitlines()
            if (m := MEAS.match(line))
        }
        require(
            MEAS_NAMES <= values.keys(),
            f"{path}: missing measurements {MEAS_NAMES - values.keys()}",
        )
        require(
            all(np.isfinite(values[name]) for name in MEAS_NAMES), f"{path}: nonfinite measurement"
        )
    return int(rows[0])


def check_result(result: dict, *, raw: bool = True) -> None:
    require(result.get("aborted") is False, "ngspice reported an aborted run")
    require(result.get("returncode") == 0, "ngspice measurement run did not exit cleanly")
    if raw:
        require(result.get("raw_returncode") == 0, "ngspice raw run did not exit cleanly")
    require(result.get("failed") == [], "ngspice reported a failed measurement")
    meas = result.get("meas", {})
    require(MEAS_NAMES <= meas.keys(), f"missing measurements {MEAS_NAMES - meas.keys()}")
    require(all(np.isfinite(meas[name]) for name in MEAS_NAMES), "nonfinite measurement")


def check_wave(folder: Path, wave: dict, expected_end: float) -> np.ndarray:
    measured_rows = check_log(folder / "run.log", measurements=True)
    raw_rows = check_log(folder / "raw_run.log", measurements=False)
    with (folder / "waves.raw").open() as handle:
        header = handle.read(1024)
    points = NPOINTS.search(header)
    variables = NVARS.search(header)
    require(points is not None and variables is not None, f"{folder}: incomplete raw header")
    require(
        measured_rows == raw_rows == int(points.group(1)), f"{folder}: log/raw row counts differ"
    )
    require(len(wave) == int(variables.group(1)), f"{folder}: raw vector count differs")
    for name, values in wave.items():
        array = np.asarray(values)
        require(len(array) == raw_rows, f"{folder}: {name} has incomplete samples")
        require(
            np.isrealobj(array) and np.all(np.isfinite(array)),
            f"{folder}: {name} has nonfinite or complex samples",
        )
    required = {"time", "v(xql.dd)", "v(xql.g)", "v(xql.s)"}
    require(required <= wave.keys(), f"{folder}: missing vectors {required - wave.keys()}")
    t = np.asarray(wave["time"])
    require(t[0] == 0 and np.all(np.diff(t) > 0), f"{folder}: invalid time axis")
    require(t[-1] >= expected_end - 1e-12, f"{folder}: transient stopped early")
    return t
