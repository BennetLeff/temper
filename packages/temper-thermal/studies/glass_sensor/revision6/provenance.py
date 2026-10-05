"""Write file identities for the completed R6 study; does not validate physics."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    inherited = [
        "model.rs",
        "revision5/thermal/main.rs",
        "revision5/mechanical/thermal_geometry.csv",
        "revision5/source-provenance.json",
    ]
    artifacts = {
        str(p.relative_to(ROOT)): digest(p)
        for p in sorted(ROOT.rglob("*"))
        if p.is_file() and p.name != "source-provenance.json" and "__pycache__" not in p.parts
    }
    result = {
        "status": "SIMULATION_ONLY_PHYSICAL_NOT_RUN",
        "cad_status": "R5_REFERENCE_UNCHANGED_R6_CANDIDATES_PARAMETRIC_NOT_CAD_RELEASED",
        "baseline_commit": "9d301c17678aee3ec5e2928db3ca317375a0eb7b",
        "hash_algorithm": "SHA256",
        "artifact_path_base": "revision6",
        "artifacts": artifacts,
        "inherited_path_base": "glass_sensor",
        "inherited": {name: digest(ROOT.parent / name) for name in inherited},
        "meaning": "Content identities only. Contact runner enforces its input pins; no hardware validation is implied.",
    }
    (ROOT / "source-provenance.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    main()
