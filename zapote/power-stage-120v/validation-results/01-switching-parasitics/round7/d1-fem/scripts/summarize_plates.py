"""Classify every generated round-7 plate mesh and direct-solve attempt."""

import json
import math
import re
from pathlib import Path

RAW = Path("raw/fixtures")
ENERGY = re.compile(r"Magnetic Coenergy:\s+(\S+)")
FIELD_ENERGY = re.compile(r"Magnetic Field Energy:\s+(\S+)")
ERROR = re.compile(r"(?:ERROR::|\bFATAL\b|\bSTOP\s+[1-9]\b|Error occurred)", re.IGNORECASE)
EDGES = re.compile(r"Volume tree edges: \d+ of total: (\d+)")


def require_one_amp_source(label: str) -> list[float]:
    """These fixed fixtures use 1 A; refuse changed or stale source metadata."""
    source = json.loads((RAW / f"{label}-source.json").read_text())
    if Path(source["mesh"]).name != label + ".msh":
        raise ValueError(f"{label}: source audit references a different mesh")
    sif_reference = Path(source["sif"])
    if sif_reference.name == label + ".sif":
        sif_path = RAW / sif_reference.name
    elif sif_reference.parent == Path("fixtures"):
        # The first two runs used committed SIFs, before per-run raw SIFs.
        sif_path = RAW.parent.parent / sif_reference
    else:
        raise ValueError(f"{label}: source audit references an unrecognized SIF")
    currents = list(source["sampled_cut_currents_A"].values())
    if len(currents) < 3 or any(not math.isfinite(i) or
                              not math.isclose(i, 1.0, rel_tol=0, abs_tol=1e-10)
                              for i in currents):
        raise ValueError(f"{label}: source audit must establish 1 A on all cuts")
    expected_box = [-5, 50, .25 if "-half-" in label else 0, 5, 50, .5]
    box = source["port_bbox_mm"]
    if len(box) != 6 or any(not math.isclose(a, b, rel_tol=0, abs_tol=1e-8)
                           for a, b in zip(box, expected_box, strict=True)):
        raise ValueError(f"{label}: source audit has unexpected port geometry")
    if source["constant_source_density_A_per_m"] != 100:
        raise ValueError(f"{label}: source audit has unexpected current density")
    sif = sif_path.read_text()
    if sif.count(f'"raw/fixtures/{label}-elmer"') != 2:
        raise ValueError(f"{label}: SIF does not reference the paired mesh")
    for axis, expected in ((1, 0), (2, 0), (3, 100)):
        values = re.findall(rf"^\s*Magnetic Field Strength {axis} = Real (\S+)\s*$",
                            sif, re.MULTILINE)
        if len(values) != 1 or float(values[0]) != expected:
            raise ValueError(f"{label}: SIF source differs from the audited 1 A vector")
    return [min(currents), max(currents)]


def final_energy(log: str) -> float | None:
    """Require final energy/coenergy, never an earlier successful value."""
    values = []
    for pattern in (ENERGY, FIELD_ENERGY):
        matches = pattern.findall(log)
        try:
            value = float(matches[-1]) if matches else math.nan
        except ValueError:
            return None
        if not math.isfinite(value) or value <= 0:
            return None
        values.append(value)
    if not math.isclose(values[0], values[1], rel_tol=1e-10, abs_tol=0):
        return None
    return values[0]


def summarize(label: str) -> dict:
    mesh = json.loads((RAW / f"{label}-mesh.json").read_text())
    report = {"label": label, "tetrahedra": mesh["tetrahedra"],
              "air_margin_mm": mesh["air_margin_mm"],
              "gap_size_mm": mesh.get("gap_size_mm", mesh.get("near_size_mm")),
              "far_size_mm": mesh["far_size_mm"]}
    audit_path = RAW / f"{label}-audit.json"
    if audit_path.is_file():
        audit = json.loads(audit_path.read_text())
        report["plate_edge_mm_quantiles"] = audit["plates"]["1"]["edge_mm_quantiles"]
    exit_path = RAW / f"{label}-exit.txt"
    if not exit_path.is_file():
        report["status"] = "generated_only"
        return report
    code = int(exit_path.read_text().strip())
    report["exit_code"] = code
    log = (RAW / f"{label}.log").read_text()
    report["all_done"] = "Elmer Solver: ALL DONE" in log
    edges = EDGES.search(log)
    if edges:
        report["edge_unknowns"] = int(edges.group(1))
    joules = final_energy(log)
    if code == 0 and report["all_done"] and joules is not None and not ERROR.search(log):
        report["source_current_sampled_range_A"] = require_one_amp_source(label)
        report["energy_J"] = joules
        report["inductance_nH"] = (4 if "-half-" in label else 2) * joules * 1e9
        if "-half-" in label:
            report["status"] = "rejected_half_symmetry"
        elif not 2.85 <= report["inductance_nH"] <= 3.14:
            report["status"] = "solved_outside_band"
        else:
            report["status"] = "solved_in_band_requires_convergence"
    elif "umf4num:   -1" in log:
        report["status"] = "umfpack_out_of_memory"
    else:
        report["status"] = "solver_failed_other"
    return report


if __name__ == "__main__":
    labels = sorted(path.name.removesuffix("-mesh.json")
                    for path in RAW.glob("plates-*-mesh.json"))
    print(json.dumps([summarize(label) for label in labels], indent=2))
