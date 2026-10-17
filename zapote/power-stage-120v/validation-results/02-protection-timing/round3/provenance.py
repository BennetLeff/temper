#!/usr/bin/env python3
"""Write input and artifact hashes for this one-off validation run."""
from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
UNIT = HERE.parents[2]
ROOT = UNIT.parents[1]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    kit = UNIT / "validation-plan/sim-kit"
    inputs = [
        UNIT / "native-15/section.kicad_pcb", UNIT / "frozen/default.net",
        UNIT / "frozen/default.csv", kit / "common/options.inc",
        kit / "02-chain/ct_frontend.cir", kit / "02-chain/ocp_frontend.cir",
        kit / "models/vendor/IFX_CFD7_650V.lib",
        kit / "models/vendor/cfd7-650.zip",
        HERE / "sources/tlv3201.pdf",
    ]
    artifacts = sorted(path for path in HERE.rglob("*") if path.is_file()
                       and path.name not in ("provenance.json",) and "__pycache__" not in path.parts)
    record = {
        "measured_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip(),
        "working_tree_note": "source and board unchanged; this round3 evidence directory is uncommitted",
        "board_sha256": sha(inputs[0]),
        "runtime": {"ngspice": "45.2 /opt/homebrew/bin/ngspice",
                    "python": subprocess.check_output(["/Users/bennet/Miniforge3/bin/python3", "--version"], text=True).strip(),
                    "host": "macOS arm64", "operator_model": "Codex GPT-6"},
        "input_hashes": {str(path.relative_to(ROOT)): sha(path) for path in inputs},
        "artifact_hashes": {str(path.relative_to(HERE)): sha(path) for path in artifacts},
        "model_assumptions": ["generic CT clamp diode in SPICE", "ideal comparator decision and fixed 45/55 ns delay",
                              "shunt +50 C self-heating pending A6", "conditional 20 mV step-delay extrapolation is not a ramp guarantee"],
        "authoritative_result": "FAIL static shunt nuisance margin; BLOCKED complete protection/gate-off guarantee",
    }
    (HERE / "outputs/provenance.json").write_text(json.dumps(record, indent=2) + "\n")
    print(len(artifacts), "artifact hashes", len(inputs), "input hashes")


if __name__ == "__main__":
    main()
