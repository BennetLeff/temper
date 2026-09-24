"""Verify both frozen build receipts before running the Rust connector audit."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_hash(path: Path, expected: str) -> None:
    actual = sha256(path)
    if actual != expected:
        raise ValueError(f"frozen source hash mismatch: {path}: {actual} != {expected}")


def verify_snapshot(snapshot: Path, expected_receipt: str, adapter: Path) -> dict:
    receipt_path = snapshot / "build-receipt.json"
    require_hash(receipt_path, expected_receipt)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt["status"] != "compiled-and-exported" or receipt["returncode"] != 0:
        raise ValueError(f"{snapshot} has no successful source build")
    require_hash(adapter, receipt["adapter_sha256"])
    expected_sources = receipt["source_hashes"]
    actual_sources = {str(path.relative_to(snapshot)) for path in snapshot.rglob("*.ato")}
    if actual_sources != set(expected_sources):
        raise ValueError(f"{snapshot} source file inventory differs from receipt")
    for relative, digest in expected_sources.items():
        require_hash(snapshot / relative, digest)
    require_hash(snapshot / "resolved-components.json", receipt["export_sha256"])
    for artifact, key in [("build/default.net", "netlist_sha256"), ("build/default.csv", "bom_sha256")]:
        if key in receipt:
            require_hash(snapshot / artifact, receipt[key])
    return receipt


def verify(root: Path) -> tuple[Path, Path, Path, Path]:
    lock = json.loads((root / "assembly-source-lock.json").read_text(encoding="utf-8"))
    if lock["schema"] != "temper.power-entry.assembly-source-lock.v1":
        raise ValueError("unexpected assembly source lock schema")
    rev38 = root / "source-build-04"
    cooker = root / "cooker-source-02"
    verify_snapshot(rev38, lock["rev38"]["receipt_sha256"], root / "tools/build_source.py")
    verify_snapshot(cooker, lock["cooker"]["receipt_sha256"], root / "tools/build_cooker_mate_source.py")
    require_hash(rev38 / "ato.yaml", lock["rev38"]["ato_yaml_sha256"])
    require_hash(cooker / "ato.yaml", lock["cooker"]["ato_yaml_sha256"])
    # The earlier Rev38 receipt did not record netlist and BOM digests.
    require_hash(rev38 / "build/default.net", lock["rev38"]["netlist_sha256"])
    require_hash(rev38 / "build/default.csv", lock["rev38"]["bom_sha256"])
    return (
        rev38 / "build/default.net", rev38 / "build/default.csv",
        cooker / "build/default.net", cooker / "build/default.csv",
    )


def main() -> None:
    artifacts = verify(ROOT)
    with tempfile.TemporaryDirectory(prefix="temper-assembly-audit-") as directory:
        audit = Path(directory) / "audit"
        subprocess.run(["rustc", "--edition=2021", str(ROOT / "audit.rs"), "-o", str(audit)], check=True)
        subprocess.run([str(audit), "--assembly-harness", *(str(path) for path in artifacts)], check=True)
    print("both frozen source receipts and artifact hashes PASS")


if __name__ == "__main__":
    main()
