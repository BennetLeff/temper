#!/usr/bin/env python3
"""Analyze the TDK archive; keep licensed sources outside the repository."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import tarfile
import subprocess
import tempfile

ARCHIVE_SHA256 = "5eb5219af01c3fdaf80e68343fe9815960cc9d6696e216eccc9ddb78d9574df2"
MODEL_NAMES = {"B32652A0104K": 100e-9, "B32656G0275J": 2.7e-6}


def parallel(z1: complex, z2: complex) -> complex:
    return z1 * z2 / (z1 + z2)


def impedance(p: dict[str, float], frequency_hz: float) -> complex:
    """Exact BASE1 topology at the pinned library hash, not a single RLC fit."""
    jw = 2j * math.pi * frequency_hz
    z = sum(parallel(p[f"Rp{i}1"], 1 / (jw * p[f"Cp{i}1"])) for i in range(1, 5))
    z += parallel(p["Rp51"], p["RC51"] + 1 / (jw * p["Cp51"]))
    z += sum(parallel(p[f"Rp{i}1"], jw * p[f"Lp{i}1"]) for i in (6, 7))
    z += 1 / (jw * p["Cs1"]) + jw * p["Ls1"]
    return parallel(z, p["Rp1"])


def analyze(library: str, name: str, capacitance_f: float) -> dict[str, object]:
    match = re.search(rf"^\.subckt {name}\b[^\n]*\n.*?^\.ENDS[^\n]*$", library, re.M | re.S | re.I)
    if match is None:
        raise ValueError(f"missing exact subcircuit {name}")
    block = match.group(0)
    params = {key: float(value) for key, value in re.findall(r"(\w+)=([-+0-9.eE]+)", block)}
    if "TDK_B32651-8_BASE1" not in block or len(params) != 18:
        raise ValueError(f"unexpected topology/parameter count for {name}")
    # Bracket the first capacitive-to-inductive zero, then refine it.
    low = 1e3
    if impedance(params, low).imag >= 0:
        raise ValueError("model does not start capacitive")
    for step in range(1, 6001):
        high = 10 ** (3 + step / 1000)
        if impedance(params, high).imag >= 0:
            break
        low = high
    else:
        raise ValueError("no first resonance found in 1 kHz to 1 GHz")
    for _ in range(80):
        middle = (low + high) / 2
        if impedance(params, middle).imag < 0:
            low = middle
        else:
            high = middle
    srf = (low + high) / 2
    equivalent_l = 1 / ((2 * math.pi * srf) ** 2 * capacitance_f)
    z_at_srf = impedance(params, srf)
    if abs(z_at_srf.imag) > 1e-12:
        raise ValueError("resonance root failed residual check")
    return {
        "model": name, "nominal_capacitance_f": capacitance_f,
        "subcircuit_lines": [library[:match.start()].count("\n") + 1,
                             library[:match.end()].count("\n") + 1],
        "model_series_capacitance_f": params["Cs1"],
        "inductor_parameters_nh": {key: params[key] * 1e9 for key in ("Ls1", "Lp61", "Lp71")},
        "rl_branch_resistors_ohm": {key: params[key] for key in ("Rp61", "Rp71")},
        "low_frequency_inductor_sum_nh": sum(params[key] for key in ("Ls1", "Lp61", "Lp71")) * 1e9,
        "model_first_srf_mhz": srf / 1e6,
        "srf_equivalent_esl_nominal_c_nh": equivalent_l * 1e9,
        "z_at_srf_real_ohm": z_at_srf.real, "z_at_srf_imag_ohm": z_at_srf.imag,
        "reading_uncertainty": "none: analytic evaluation of pinned typical model; model/assembly uncertainty unspecified",
    }


def ngspice_check(library_bytes: bytes, executable: Path, models: list[dict[str, object]]) -> dict[str, object]:
    """Independent AC solve of the complete, byte-unmodified vendor library."""
    with tempfile.TemporaryDirectory(prefix="d7-tdk-ac-") as directory:
        work = Path(directory)
        (work / "vendor.lib").write_bytes(library_bytes)
        (work / ".spiceinit").write_text("set ngbehavior=ps\n")
        deck = """D7 exact TDK capacitor model AC verification
.include vendor.lib
Ilocal 0 local AC 1
Xlocal local 0 B32652A0104K
Ibulk 0 bulk AC 1
Xbulk bulk 0 B32656G0275J
.control
set numdgt=15
set wr_singlescale
set wr_vecnames
ac dec 1000 1k 1g
wrdata ac.txt v(local) v(bulk)
quit
.endc
.end
"""
        (work / "check.cir").write_text(deck)
        run = subprocess.run([str(executable), "-b", "check.cir"], cwd=work,
                             text=True, capture_output=True, timeout=60, check=False)
        if run.returncode:
            raise RuntimeError(run.stdout + run.stderr)
        lines = (work / "ac.txt").read_text().splitlines()
        rows = [[float(value) for value in line.split()] for line in lines[1:]]
        if len(rows) != 6001 or any(len(row) != 5 for row in rows):
            raise ValueError("unexpected ngspice AC output")
        library = library_bytes.decode("utf-8")
        results = []
        for index, model in enumerate(models):
            name = str(model["model"])
            block = re.search(rf"^\.subckt {name}\b[^\n]*\n.*?^\.ENDS[^\n]*$", library, re.M | re.S | re.I)
            if block is None:
                raise ValueError(name)
            params = {k: float(v) for k, v in re.findall(r"(\w+)=([-+0-9.eE]+)", block.group(0))}
            offset = 1 + index * 2
            errors = []
            samples = []
            root = None
            previous = None
            for row in rows:
                frequency = row[0]
                measured = complex(row[offset], row[offset + 1])
                calculated = impedance(params, frequency)
                errors.append(abs(measured - calculated) / abs(calculated))
                if previous is not None and previous[1] < 0 <= measured.imag and root is None:
                    f0, imag0 = previous
                    root = f0 + (frequency - f0) * (-imag0) / (measured.imag - imag0)
                previous = (frequency, measured.imag)
                if any(math.isclose(frequency, f, rel_tol=1e-10) for f in (1e4, 1e5, 1e6, 1e7, 1e8)):
                    samples.append({"frequency_hz": frequency, "ngspice_z_real_ohm": measured.real,
                                    "ngspice_z_imag_ohm": measured.imag})
            if root is None or max(errors) > 1e-5:
                raise ValueError(f"ngspice mismatch {name}: max_relative_error={max(errors)}, root={root}, samples={samples}")
            analytic_root = float(model["model_first_srf_mhz"]) * 1e6
            if abs(root / analytic_root - 1) > 1e-5:
                raise ValueError("ngspice resonance mismatch")
            results.append({"model": name, "ngspice_interpolated_srf_mhz": root / 1e6,
                            "srf_relative_difference": abs(root / analytic_root - 1),
                            "maximum_complex_impedance_relative_error": max(errors), "samples": samples})
        version = subprocess.run([str(executable), "--version"], text=True,
                                 capture_output=True, timeout=10, check=True).stdout
        return {"version": next(line.strip() for line in version.splitlines() if "ngspice-" in line),
                "points_per_model": len(rows), "frequency_hz": [rows[0][0], rows[-1][0]],
                "points_per_decade": 1000, "relative_agreement_acceptance": 1e-5, "library_unmodified": True, "ngbehavior": "ps",
                "log_sha256": hashlib.sha256((run.stdout + run.stderr).encode()).hexdigest(),
                "parts": results}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--ngspice", type=Path)
    args = parser.parse_args()
    digest = hashlib.sha256(args.archive.read_bytes()).hexdigest()
    if digest != ARCHIVE_SHA256:
        raise ValueError(f"unrecognized archive SHA-256: {digest}")
    with tarfile.open(args.archive) as archive:
        blobs = {}
        for name in ("Readme.txt", "History.txt", "Disclaimer.txt", "TDK_B32651-8.lib"):
            member = archive.getmember(name)
            if not member.isfile():
                raise ValueError(f"not a regular archive member: {name}")
            handle = archive.extractfile(member)
            if handle is None:
                raise ValueError(f"unreadable member: {name}")
            blobs[name] = handle.read()
    library = blobs["TDK_B32651-8.lib"].decode("utf-8")
    result = {
        "evidence_class": "vendor typical model, not mounted-assembly measurement or production bound",
        "archive_sha256": digest,
        "member_sha256": {name: hashlib.sha256(blob).hexdigest() for name, blob in blobs.items()},
        "library_version": "1.10", "library_date": "2025-03-21",
        "topology": "BASE1 series RC dispersion, two R||L branches, Cs1 and Ls1; whole path shunted by Rp1",
        "parts": [analyze(library, name, capacitance) for name, capacitance in MODEL_NAMES.items()],
    }
    if args.ngspice is not None:
        result["ngspice_check"] = ngspice_check(blobs["TDK_B32651-8.lib"], args.ngspice, result["parts"])
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
