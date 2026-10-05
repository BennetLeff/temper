"""Record and verify R7 artifacts while preserving historical CAD index identities."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STUDY = ROOT.parent
REPO = ROOT.parents[4]
ARCHIVED_INDEX = {
    "CURRENT.md": "history/R5-CURRENT.md",
    "current-cad.json": "history/R5-current-cad.json",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_history() -> None:
    old = json.loads((STUDY / "revision5/source-provenance.json").read_text())
    for name, expected in (old["inherited_files"] | old["files"]).items():
        original = REPO / name
        replacement = ARCHIVED_INDEX.get(original.name) if original.parent == STUDY else None
        actual = ROOT / replacement if replacement else original
        if digest(actual) != expected:
            raise ValueError(f"Historical R5 identity changed: {name}")
    r6 = json.loads((STUDY / "revision6/source-provenance.json").read_text())
    for name, expected in r6["artifacts"].items():
        if digest(STUDY / "revision6" / name) != expected:
            raise ValueError(f"Historical R6 identity changed: {name}")


def main() -> None:
    check_history()
    manifest = ROOT / "source-provenance.json"
    mode = sys.argv[1] if len(sys.argv) == 2 else ""
    if mode == "write":
        current = {
            "schema": "temper-glass-sensor-current-cad-v1",
            "revision": "R7",
            "status": "EXPERIMENTAL_COUPON_COMPARISON_NOT_RELEASED",
            "physical_result": "NOT_RUN",
            "comparison_candidate": "revision7/mechanical/R7-M222_thin_0075-rest.step",
            "reference_control": "revision7/mechanical/R7-M222_control_010-rest.step",
            "additional_comparison": "revision7/mechanical/R7-IST308_thin_0075-rest.step",
            "historical_reference": "revision5/mechanical/R5-D6-rest.step",
            "pressure_apparatus": "SEPARATE_CONNECTED_TEST_CELL_NOT_A_CARTRIDGE_SEAL",
            "paths_relative_to": "packages/temper-thermal/studies/glass_sensor",
            "files": {
                str(p.relative_to(STUDY)): digest(p)
                for p in sorted((ROOT / "mechanical").glob("R7-*.step"))
            },
        }
        for name in ("thermal_geometry.csv", "geometry.json", "independent-audit.json"):
            p = ROOT / "mechanical" / name
            current["files"][str(p.relative_to(STUDY))] = digest(p)
        (STUDY / "current-cad.json").write_text(json.dumps(current, indent=2) + "\n")
        artifacts = {
            str(p.relative_to(ROOT)): digest(p)
            for p in sorted(ROOT.rglob("*"))
            if p.is_file() and p != manifest and "__pycache__" not in p.parts
        }
        payload = {
            "schema": "temper-r7-artifact-identities-v1",
            "status": "EXPERIMENTAL_CAD_SIMULATION_AND_PREPARATION_PHYSICAL_NOT_RUN",
            "baseline_commit": "fa31c1021",
            "artifacts_relative_to": "revision7",
            "artifacts": artifacts,
            "current_index_relative_to": "glass_sensor",
            "current_index": {name: digest(STUDY / name) for name in ARCHIVED_INDEX},
            "historical_index_archives": ARCHIVED_INDEX,
            "historical_manifest_identities": {
                revision: digest(STUDY / revision / "source-provenance.json")
                for revision in ("revision5", "revision6")
            },
            "meaning": "Content identity, not physical validation. R5 mutable index bytes are archived unchanged; its historical manifest is not rewritten.",
        }
        manifest.write_text(json.dumps(payload, indent=2) + "\n")
    elif mode == "verify":
        payload = json.loads(manifest.read_text())
        for name, expected in payload["artifacts"].items():
            if digest(ROOT / name) != expected:
                raise ValueError(f"R7 artifact identity changed: {name}")
        for name, expected in payload["current_index"].items():
            if digest(STUDY / name) != expected:
                raise ValueError(f"Current index changed: {name}")
        print("PASS: R7 artifact identities and historical R5/R6 evidence")
    else:
        raise SystemExit("usage: provenance.py write|verify")


if __name__ == "__main__":
    main()
