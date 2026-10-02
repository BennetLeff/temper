"""Read licensed local TDK TAR; solve its RLC graph without copying it to Git.

Standalone research replay only; no production engineering rule or verdict.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import sys
import tarfile

EXPECTED = "e534e423ccaf7566b3eef32fb8120ffff53bb27e33a7cd17e5eca50a10f55f0a"


def solve(a: list[list[complex]], b: list[complex]) -> list[complex]:
    """Dense elimination with partial pivoting for the small passive graph."""
    n = len(b)
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(a[row][col]))
        a[col], a[pivot] = a[pivot], a[col]
        b[col], b[pivot] = b[pivot], b[col]
        scale = a[col][col]
        if abs(scale) == 0:
            raise ValueError("singular model")
        a[col] = [v / scale for v in a[col]]
        b[col] /= scale
        for row in range(n):
            if row == col:
                continue
            factor = a[row][col]
            a[row] = [v - factor * w for v, w in zip(a[row], a[col])]
            b[row] -= factor * b[col]
    return b


def impedance(elements: list[tuple[str, str, str, float]], f: float) -> complex:
    nodes = sorted({x for _, u, v, _ in elements for x in (u, v)} - {"A2"})
    index = {node: i for i, node in enumerate(nodes)}
    a = [[0j] * len(nodes) for _ in nodes]
    b = [0j] * len(nodes)
    b[index["A1"]] = 1
    omega = 2 * math.pi * f
    for kind, u, v, value in elements:
        y = {"R": lambda: 1 / value, "C": lambda: 1j * omega * value,
             "L": lambda: 1 / (1j * omega * value)}[kind]()
        for x, z in ((u, v), (v, u)):
            if x != "A2":
                a[index[x]][index[x]] += y
                if z != "A2":
                    a[index[x]][index[z]] -= y
    return solve(a, b)[index["A1"]]


def main() -> None:
    archive = Path(sys.argv[1])
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest != EXPECTED:
        raise ValueError("TDK archive changed; review the source before repinning")
    with tarfile.open(archive) as tar:
        member = tar.extractfile("TDK_B32651-8.sub")
        if member is None:
            raise ValueError("model member absent")
        raw = member.read()
    source = raw.decode("utf-8")
    blocks = {m.group(1): m.group(2) for m in re.finditer(
        r"(?im)^\.subckt\s+(\S+)([\s\S]*?)^\.ends", source)}
    base = blocks["TDK_B32651-8_BASE1"]
    results = {}
    for part, nominal in (("B32652A0104K", 100e-9), ("B32656G0275J", 2.7e-6)):
        params = {k: float(v) for k, v in re.findall(
            r"(\w+)=([\d.eE+-]+)", blocks[part])}
        elements = []
        for line in base.splitlines():
            if not line or line[0] not in "RCL":
                continue
            fields = line.split()
            name, u, v, parameter = fields[:4]
            # Vendor's zero Rpar/Rser annotations request ideal RLC primitives.
            if any(x not in ("Rpar=0", "Rser=0") for x in fields[4:]):
                raise ValueError("unreviewed primitive parameter")
            key = parameter.strip("{}").removesuffix("_a")
            elements.append((name[0], u, v, params[key]))
        lo, hi = 1e3, 1e8
        if not impedance(elements, lo).imag < 0 < impedance(elements, hi).imag:
            raise ValueError("SRF not bracketed")
        for _ in range(70):
            mid = (lo + hi) / 2
            if impedance(elements, mid).imag < 0:
                lo = mid
            else:
                hi = mid
        srf = (lo + hi) / 2
        samples = []
        crosscheck_error = 0.0
        for f in (1e5, 5e5, 1e6, 2e6, 5e6, 1e7, 2e7):
            z = impedance(elements, f)
            w = 2 * math.pi * f
            # Independent series/parallel reduction checks parsed nodal topology.
            def parallel(x: complex, y: complex) -> complex:
                return x * y / (x + y)
            reduced = sum(parallel(params[f"Rp{i}1"], 1 / (1j*w*params[f"Cp{i}1"]))
                          for i in range(1, 5))
            reduced += parallel(params["Rp51"], params["RC51"] + 1 / (1j*w*params["Cp51"]))
            reduced += sum(parallel(params[f"Rp{i}1"], 1j*w*params[f"Lp{i}1"])
                           for i in (6, 7))
            reduced += 1 / (1j*w*params["Cs1"]) + 1j*w*params["Ls1"]
            reduced = parallel(reduced, params["Rp1"])
            crosscheck_error = max(crosscheck_error, abs(reduced - z))
            assert abs(reduced - z) < 1e-9
            samples.append({"frequency_Hz": f, "Z_real_ohm": z.real,
                            "Z_imag_ohm": z.imag,
                            "L_equiv_nH_using_nominal_C": (z.imag + 1 / (w * nominal)) / w * 1e9,
                            "below_model_SRF": f < srf})
        results[part] = {"C_nominal_F": nominal, "Cs_model_F": params["Cs1"],
                         "Ls_series_nH": params["Ls1"] * 1e9,
                         "SRF_Hz": srf,
                         "L_SRF_nH_using_nominal_C": 1e9 / ((2 * math.pi * srf)**2 * nominal),
                         "L_SRF_nH_using_model_Cs": 1e9 / ((2 * math.pi * srf)**2 * params["Cs1"]),
                         "nodal_vs_reduction_max_error_ohm": crosscheck_error, "samples": samples}
    # Independent closed-form series-RLC sanity check of nodal solver and signs.
    f = 2e6
    actual = impedance([("R", "A1", "x", 0.02), ("L", "x", "y", 10e-9),
                        ("C", "y", "A2", 100e-9)], f)
    expected = 0.02 + 1j * (2 * math.pi * f * 10e-9 - 1 / (2 * math.pi * f * 100e-9))
    assert abs(actual - expected) < 1e-12
    print(json.dumps({"archive_sha256": digest, "library_sha256": hashlib.sha256(raw).hexdigest(),
                      "solver_RLC_sanity_error_ohm": abs(actual - expected),
                      "parts": results}, indent=2))


if __name__ == "__main__":
    main()
