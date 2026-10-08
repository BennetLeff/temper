"""Copy round5 check receipts and summarize them; no electrical rule implementation.

Run from the repository root after boards/check.sh. The Rust validator owns the
power-direction verdict. KiCad/verify_native.py own the ERC/DRC/parity verdicts.
"""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[6]
BOARDS = ROOT / "zapote/power-stage-120v/prototype-closure/round5/boards"
OUTPUT = ROOT / "output/temper-prototype-closure/round5/boards"
BASE = "841a66d9408e16b3fcd71d9e46131b62df00bb65"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    after = HERE / "after"
    after.mkdir(exist_ok=True)
    patterns = ["*-erc.json", "*-drc-[123].json", "verification-summary.json",
                "native-pin-oracle.json", "power-direction.*", "power-direction-tests.log"]
    for pattern in patterns:
        for path in sorted(OUTPUT.glob(pattern)):
            destination = after / path.name
            if destination.suffix == ".log":
                destination = destination.with_suffix(".txt")
            if destination.suffix == ".txt":
                destination.write_text(path.read_text().rstrip() + "\n")
            else:
                shutil.copyfile(path, destination)
    shutil.copyfile(OUTPUT / "central-netlist.xml", after / "central-netlist.xml")
    shutil.copyfile(BOARDS / "central/generated/pins.tsv", after / "central-pins.tsv")
    board_hashes = {str(p.relative_to(ROOT)): digest(p)
                    for p in sorted(BOARDS.rglob("*.kicad_pcb"))}
    (after / "board-hashes.json").write_text(json.dumps(board_hashes, indent=2) + "\n")
    baseline = json.loads((HERE / "before/board-hashes.json").read_text())
    assert board_hashes == baseline, "A PCB changed; D-30 is a metadata-only ECO"
    with (after / "power-direction.tsv").open() as stream:
        audit_rows = list(csv.DictReader(stream, delimiter="\t"))
    summary = {}
    for board in ["central", "catch", "bus", "line", "pre", "out", "tank", "iproof", "iline"]:
        table = BOARDS / ("central/generated/pins.tsv" if board == "central" else f"{board}-pins.tsv")
        with table.open() as stream:
            pins = list(csv.DictReader(stream, delimiter="\t"))
        summary[board] = {
            "pins": len(pins),
            "connector_pins": sum(r["reference"].startswith("J") for r in pins),
            "power_in_pins": sum(r["type"] == "power_in" for r in pins),
            "audit_rows": sum(r["board"] == board for r in audit_rows),
        }
    inputs = [BOARDS / n for n in ["partition.rs", "render_central.py", "power_direction.rs",
              "verify_native.py", "check.sh", "central/generated/pins.tsv",
              "central/native/supervisor.kicad_sch", "central/native/supervisor.kicad_sym",
              "central/native/CONTROLLER_1.kicad_sch"]]
    inputs += sorted(BOARDS.glob("*-pins.tsv"))
    record = {
        "base_commit": BASE,
        "measurement_identity": "SHA-256 of saved inputs; local working tree before commit",
        "tools": {name: subprocess.check_output(args, text=True).strip() for name, args in {
            "rustc": ["rustc", "--version"], "kicad-cli": ["kicad-cli", "--version"],
            "python": ["python3", "--version"]}.items()},
        "boards": summary,
        "all_nine_pcb_files_byte_identical_to_baseline": True,
        "inputs_sha256": {str(p.relative_to(ROOT)): digest(p) for p in inputs},
        "release_status": "HOLD_DIGITAL_AND_PHYSICAL_QUALIFICATION",
    }
    (HERE / "evidence.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
