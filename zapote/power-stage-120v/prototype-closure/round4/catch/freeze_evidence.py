"""Fail-closed consistency check and full-file evidence inventory; not release approval."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
OUT = ROOT / "output/temper-prototype-closure/round4/catch"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict:
    return json.loads(path.read_text())


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> None:
    receipt = OUT / "replay.json"
    receipt.write_text('{"status":"INCOMPLETE"}\n')
    interface = read(HERE / "interface.json")
    carrier = read(OUT / "carrier-checks.json")
    require(carrier["input_sha256"] == sha(HERE / "interface.json"), "Stale carrier interface")
    require(carrier["builder_sha256"] == sha(HERE / "build_carrier.py"), "Stale carrier builder")
    require(carrier["export"]["sha256"] == sha(ROOT / carrier["export"]["path"]), "Stale STEP")
    require(not carrier["carrier_vs_context"], "Carrier context collision")
    require(not carrier["sense_allocation_vs_context"], "Sensor context collision")
    require(
        [(r["new"], r["context"]) for r in carrier["harness_vs_context"]]
        == [("FUSED_P_TO_ANODE_INSULATED_WIRE_MAX", "CATCH_US141_ROTATED")],
        "Unexpected harness context collision",
    )
    require(
        interface["native19_sha256"]
        == sha(ROOT / "zapote/power-stage-120v/native-19/section.kicad_pcb"),
        "Native19 identity changed",
    )
    require(
        interface["baseline_step_sha256"] == sha(ROOT / interface["baseline_step"]),
        "Baseline STEP changed",
    )
    verification = read(OUT / "bleed-verification.json")
    require(
        verification["status"] == "PASS_EXPORTED_CONNECTIVITY_ONLY", "Connectivity not verified"
    )
    for r in verification["inputs"]:
        require(r["sha256"] == sha(ROOT / r["path"]), f"Stale connectivity input {r['path']}")
    require(
        len(verification["negative_controls"]) == 3
        and set(verification["negative_controls"].values()) == {"REJECTED"},
        "Connectivity negative controls missing",
    )
    sch = HERE / "native/catch-bleed.kicad_sch"
    pcb = HERE / "native/catch-bleed.kicad_pcb"
    for i in (1, 2, 3):
        path = OUT / f"drc-{i}.json"
        drc = read(path)
        require(
            not drc["violations"] and not drc["unconnected_items"] and not drc["schematic_parity"],
            f"DRC sample{i} not clean",
        )
        require(
            path.stat().st_mtime >= max(sch.stat().st_mtime, pcb.stat().st_mtime),
            "DRC predates source",
        )
    erc_path = OUT / "erc.json"
    erc = read(erc_path)
    require(not any(s["violations"] for s in erc["sheets"]), "ERC not clean")
    require(erc_path.stat().st_mtime >= sch.stat().st_mtime, "ERC predates source")
    internal = read(OUT / "internal-checks.json")
    require(
        internal["status"] == "PASS_CLASSIFIED_CONTACTS_NOT_RELEASE"
        and not internal["unclassified"],
        "Unclassified assembly intersection",
    )
    require(internal["step_sha256"] == carrier["export"]["sha256"], "Internal check on stale STEP")
    calc = read(OUT / "electrical-screen.json")
    routes = read(OUT / "route-geometry.json")["routes"]
    require(
        all(
            math.isfinite(r["length_mm"])
            and r["length_mm"] > 0
            and r["minimum_tangent_margin_mm"] > 0
            for r in routes
        ),
        "Invalid route",
    )
    require(
        abs(sum(r["length_mm"] for r in routes) - calc["wire_length_mm"]) < 1e-6,
        "Stale route calculation",
    )
    require(calc["inductance_extracted"] is False, "Unsubstantiated extracted inductance claim")
    require(
        "4 passed; 0 failed" in (OUT / "electrical-screen-tests.txt").read_text(),
        "Rust checks not passed",
    )
    paths = sorted(
        p
        for folder in (HERE, OUT)
        for p in folder.rglob("*")
        if p.is_file()
        and "__pycache__" not in p.parts
        and p.name not in {"manifest.json", "replay.json"}
        and not p.name.endswith((".lck", ".bak"))
    )
    manifest = {
        "status": "REVIEWABLE_ENGINEERING_DESIGN_NOT_RELEASED",
        "inputs_and_outputs": [
            {"path": str(p.relative_to(ROOT)), "sha256": sha(p), "bytes": p.stat().st_size}
            for p in paths
        ],
        "verified": {
            "native_bleed_erc": 0,
            "native_bleed_drc_samples": 3,
            "native_bleed_drc_violations_each": 0,
            "connectivity_negative_controls": 3,
            "rust_tests": 4,
            "step_valid_solids": carrier["export"]["valid_solids"],
            "internal_unique_pair_tests": internal["pair_tests"],
            "unclassified_internal_intersections": 0,
        },
        "unreleased": [
            "Actual US141 terminal positions/sideways mounting/hinge sweep",
            "Lug-insulation tolerance and crimp tool/height",
            "Native diode power copper / clamp / thermal joint",
            "Native AMC3330 sensor board layout / mating harness",
            "Laminate/PEEK/PTFE insulation and thermal material qualification",
            "Full-loop field extraction including actual terminal and native-board closure",
            "DC fuse arc/protection coordination and hardware hot-pulse / discharge / thermal tests",
        ],
    }
    (HERE / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    receipt.write_text(
        json.dumps(
            {
                "status": manifest["status"],
                "manifest_sha256": sha(HERE / "manifest.json"),
                "checks": manifest["verified"],
            },
            indent=2,
        )
        + "\n"
    )
    print(receipt.read_text())


if __name__ == "__main__":
    main()
