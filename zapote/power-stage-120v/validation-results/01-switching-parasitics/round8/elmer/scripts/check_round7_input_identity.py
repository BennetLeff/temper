"""Prove Big Umfpack reruns used round 7's exact Elmer fixture meshes."""

import argparse
import hashlib
import json
from pathlib import Path

LABELS = (
    "coax-port0p10-vol0p30",
    "coax-port0p08-vol0p25",
    "plates-box0p4-far4-m20",
)
MESH_FILES = (
    "mesh.nodes",
    "mesh.elements",
    "mesh.boundary",
    "mesh.header",
    "mesh.names",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check(round7_root: Path, round8_root: Path) -> dict:
    cases = []
    for label in LABELS:
        old = round7_root / "raw" / "fixtures"
        new = round8_root / "raw" / "fixtures"
        hashes = {}
        for name in MESH_FILES:
            old_hash = sha256(old / f"{label}-elmer" / name)
            new_hash = sha256(new / f"{label}-big-elmer" / name)
            if old_hash != new_hash:
                raise ValueError(f"{label}: {name} changed")
            hashes[name] = old_hash

        prior_sif = (old / f"{label}.sif").read_text()
        current_sif = (new / f"{label}-big.sif").read_text()
        old_mesh = f"raw/fixtures/{label}-elmer"
        if prior_sif.count(old_mesh) != 2:
            raise ValueError(f"{label}: original SIF does not name its mesh twice")
        old_method = "Linear System Direct Method = UMFPack"
        if prior_sif.count(old_method) != 1:
            raise ValueError(f"{label}: original SIF does not name UMFPACK once")
        expected = prior_sif.replace(old_mesh, f"raw/fixtures/{label}-big-elmer")
        expected = expected.replace(old_method, "Linear System Direct Method = Big Umfpack")
        if current_sif != expected:
            raise ValueError(f"{label}: SIF changed beyond backend and result path")
        cases.append({"label": label, "mesh_file_sha256": hashes,
                      "sif_change": "backend and result path only"})
    return {"round7_root": str(round7_root), "round8_root": str(round8_root),
            "cases": cases, "all_inputs_matched": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("round7_root", type=Path)
    parser.add_argument("round8_root", type=Path)
    args = parser.parse_args()
    print(json.dumps(check(args.round7_root, args.round8_root), indent=2))
