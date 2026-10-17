#!/usr/bin/env python3
"""Build the controller with pinned atopile 0.2.69, export, and freeze.

  1. ato build (build/ is gitignored), gated on return code AND report text
  2. tools/circuit_export.py (verbatim copy of harness-lab/circuit_export.py)
  3. copy default.net / default.csv / resolved-components.json into frozen/,
     replacing this unit's absolute path with "UNIT" so the frozen bytes do
     not depend on the checkout location
  4. frozen/build-receipt.json: command, tool version, source and output hashes

``--check`` rebuilds into build/ and fails if the normalized outputs differ
from frozen/ (use it to prove frozen/ is fresh).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

UNIT = Path(__file__).resolve().parents[1]
ENTRY_FILE = "elec/src/controller.ato"
ENTRY = "SelvController"
PINNED = "0.2.69"
OUTPUTS = ("default.net", "default.csv", "resolved-components.json")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=UNIT, capture_output=True, text=True, timeout=900)


def build() -> dict:
    cmd = ["uv", "tool", "run", "--offline", "--from", f"atopile=={PINNED}", "ato",
           "--non-interactive", "build", f"{ENTRY_FILE}:{ENTRY}"]
    proc = run(cmd)
    if proc.returncode != 0 or "FAILED" in proc.stdout:
        sys.stderr.write(proc.stdout[-3000:] + proc.stderr[-2000:])
        raise SystemExit("ato build failed; artifacts unqualified")
    # The exporter hashes every file in build/, including a resolved export left
    # by the previous run; remove it so the export depends only on this build.
    (UNIT / "build/resolved-components.json").unlink(missing_ok=True)
    exp = ["uv", "tool", "run", "--offline", "--from", f"atopile=={PINNED}", "python",
           "tools/circuit_export.py", str(UNIT), str(UNIT / "build/resolved-components.json"),
           "--entry-file", ENTRY_FILE, "--entry", ENTRY]
    proc2 = run(exp)
    if proc2.returncode != 0:
        sys.stderr.write(proc2.stderr[-3000:])
        raise SystemExit("resolved export failed")
    warnings = proc.stdout.count("WARNING")
    return {"build_command": " ".join(cmd), "export_command": " ".join(exp), "returncode": proc.returncode,
            "build_report_failed": False, "warning_lines": warnings,
            "warning_kinds": sorted({line.split("WARNING", 1)[1].strip()[:60]
                                     for line in proc.stdout.splitlines() if "WARNING" in line})}


def normalized(name: str) -> bytes:
    data = (UNIT / "build" / name).read_bytes()
    if name == "resolved-components.json":
        # the exporter hashes build/default.net as written, which embeds the checkout's absolute
        # path; record the hash of the normalized netlist instead, so --check holds in any checkout
        raw = (UNIT / "build/default.net").read_bytes()
        data = data.replace(sha(raw).encode(), sha(raw.replace(str(UNIT).encode(), b"UNIT")).encode())
    return data.replace(str(UNIT).encode(), b"UNIT")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    info = build()
    if args.check:
        diff = [n for n in OUTPUTS if normalized(n) != (UNIT / "frozen" / n).read_bytes()]
        print("frozen fresh" if not diff else f"frozen STALE: {diff}")
        return 1 if diff else 0
    (UNIT / "frozen").mkdir(exist_ok=True)
    out_hashes = {}
    for n in OUTPUTS:
        data = normalized(n)
        (UNIT / "frozen" / n).write_bytes(data)
        out_hashes[n] = sha(data)
    src = {str(p.relative_to(UNIT)): sha(p.read_bytes()) for p in sorted((UNIT / "elec/src").rglob("*.ato"))}
    receipt = {"schema": "temper.controller.source-build.v1", "atopile": PINNED,
               "entry": f"{ENTRY_FILE}:{ENTRY}", **info,
               "exporter_sha256": sha((UNIT / "tools/circuit_export.py").read_bytes()),
               "source_sha256": src, "frozen_sha256": out_hashes,
               "normalization": "absolute unit path replaced by 'UNIT'"}
    (UNIT / "frozen/build-receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": "frozen", "outputs": out_hashes}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
