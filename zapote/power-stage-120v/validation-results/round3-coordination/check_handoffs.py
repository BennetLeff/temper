"""Audit copied evidence identity and A4 heat transfer, not design acceptance."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
RESULTS = HERE.parent
UNIT = RESULTS.parent
REPO = UNIT.parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    # Keep the full board identity explicit; truncated digests are not receipts.
    expected_board = "a3ac1249f5052afe52944804cdc3f6ef0e8f895668360e79c1fa7b6fb7322155"
    assert sha256(UNIT / "native-15/section.kicad_pcb") == expected_board
    a3 = RESULTS / "02-protection-timing/round3"
    provenance = json.loads((a3 / "outputs/provenance.json").read_text())
    verified, external = [], []
    for kind, root in (("input_hashes", REPO), ("artifact_hashes", a3)):
        for name, digest in provenance[kind].items():
            path = root / name
            if not path.exists() and "/models/vendor/" in name:
                external.append({"path": name, "expected_sha256": digest})
                continue
            assert sha256(path) == digest, f"A3 identity mismatch: {path}"
            verified.append(name)

    a4 = RESULTS / "04-board-current-thermal/round3/a4-copper"
    heat_checks = []
    for path in sorted((a4 / "outputs").glob("*.json")):
        result = json.loads(path.read_text())
        if not isinstance(result, dict) or "nodal_heat_file" not in result:
            continue
        assert result["board_sha256"] == expected_board
        assert result["script_sha256"] == sha256(a4 / "run_board.py")
        assert result["input_sha256"] == sha256(a4 / "inputs/power_copper.json.gz")
        assert result["kit_sha256"] == sha256(UNIT / "validation-plan/sim-kit/04-current/sheet_solver.py")
        heat_path = path.parent / result["nodal_heat_file"]
        with np.load(heat_path, allow_pickle=False) as heat:
            nodal_w = 0.0
            for key in heat.files:
                if key.endswith("_joule_w"):
                    values = heat[key]
                    assert np.isfinite(values).all(), (path.name, key)
                    assert (values >= 0).all(), (path.name, key)
                    nodal_w += float(values.sum())
        barrel_w = sum(
            sum(barrel["layer_joule_w"].values())
            for barrel in result["barrel_heat_by_layer"]
        )
        residual = nodal_w + barrel_w - result["loss_w"]
        assert abs(residual) < 1e-8, (path.name, residual)
        heat_checks.append({
            "case": path.name, "case_sha256": sha256(path),
            "heat_sha256": sha256(heat_path), "loss_w": result["loss_w"],
            "nodal_w": nodal_w, "barrel_w": barrel_w, "residual_w": residual,
        })
    assert len(heat_checks) >= 35, "Incomplete A4 handoff"
    report = {
        "scope": "Evidence identity and electrical-to-thermal transfer only",
        "board_sha256": expected_board,
        "a3_verified_files": len(verified), "external_vendor_inputs": external,
        "a4_heat_checks": heat_checks,
        "status": "PASS; external vendor inputs listed separately; no engineering acceptance",
    }
    (HERE / "handoff-checks.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(f"Verified {len(verified)} A3 files and {len(heat_checks)} A4 heat transfers")


if __name__ == "__main__":
    main()
