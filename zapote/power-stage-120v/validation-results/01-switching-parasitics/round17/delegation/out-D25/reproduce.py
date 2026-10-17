"""D25 evidence transport. C owns register interpretation; no firmware is edited.

fetch: materialize hash-pinned inputs in cache only.
run: compile the bounded host probes in cache and compare recorded stdout.
check: read-only hashes, source identity and QEMU capability receipt checks.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "cache"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check_inputs() -> None:
    manifest = json.loads((ROOT / "sources.json").read_text())
    for row in manifest:
        path = CACHE / row["file"]
        if not path.is_file() or sha(path.read_bytes()) != row["sha256"]:
            raise RuntimeError(f"Missing or changed source: {row['file']}; run fetch, never repin silently")


def fetch() -> None:
    CACHE.mkdir(exist_ok=True)
    for row in json.loads((ROOT / "sources.json").read_text()):
        path = CACHE / row["file"]
        if path.is_file() and sha(path.read_bytes()) == row["sha256"]:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["curl", "-fLsS", row["url"], "-o", str(path)], check=True)
    check_inputs()
    print("PASS: all source bytes match sources.json")


def extract_function(source: str, name: str) -> str:
    match = re.search(r"^static inline [^\n]+\b" + re.escape(name) + r"\([^\n]+\)\n\{", source, re.M)
    if match is None:
        raise RuntimeError(f"Cannot extract pinned function: {name}")
    depth = 1
    end = match.end()
    while depth:
        char = source[end]
        depth += (char == "{") - (char == "}")
        end += 1
    return source[match.start():end] + "\n"


def qemu_receipt() -> str:
    tree = json.loads((CACHE / "qemu-tree.json").read_text())
    if tree.get("truncated") is not False:
        raise RuntimeError("Truncated QEMU tree: cannot establish source inventory")
    matches = [item["path"] for item in tree["tree"] if "mcpwm" in item["path"].lower()]
    board = (CACHE / "qemu_esp32s3.c").read_text()
    if matches or re.search(r"mcpwm|DR_REG_PWM", board, re.I):
        raise RuntimeError("New MCPWM evidence: re-review QEMU capability; do not assume unsupported")
    return (
        "QEMU commit: febae182e132e4055529be423a818225ebddaa3a\n"
        "Recursive source tree truncated=false; MCPWM path matches=0\n"
        "ESP32-S3 machine source MCPWM/DR_REG_PWM references=0\n"
        "Manual source review: no MCPWM device instantiated or mapped in esp32s3.c.\n"
        "Generic unsupported IO handler: reads return zero, writes discarded (461-476).\n"
        "Pinned support table: GPIO matrix / IOMUX unsupported for ESP32-S3.\n"
        "EMULATION NOT RUN: no MCPWM/GPIO-matrix model capable of the requested observation.\n"
    )


def run() -> None:
    check_inputs()
    names = [
        "mcpwm_ll_gen_set_continue_force_level", "mcpwm_ll_gen_disable_continue_force_action",
        "mcpwm_ll_deadtime_bypass_path", "mcpwm_ll_deadtime_red_select_generator",
        "mcpwm_ll_deadtime_fed_select_generator", "mcpwm_ll_deadtime_enable_deb",
        "mcpwm_ll_deadtime_invert_outpath", "mcpwm_ll_deadtime_swap_out_path",
        "mcpwm_ll_deadtime_set_rising_delay", "mcpwm_ll_deadtime_set_falling_delay",
    ]
    source = (CACHE / "mcpwm_ll.h").read_text()
    (CACHE / "ll_subset.h").write_text("\n".join(extract_function(source, name) for name in names))
    sdk = CACHE / "d21/firmware/test/pwm_sdk_stub"
    include = CACHE / "d21/firmware/components/hal/include"
    for stem in ["register_check", "cleanup_probe"]:
        binary = CACHE / stem
        command = ["cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-I", str(CACHE),
                   "-I", str(sdk), "-I", str(include), str(ROOT / f"{stem}.c"), "-o", str(binary)]
        subprocess.run(command, check=True, cwd=ROOT)
        result = subprocess.run([str(binary)], check=False, capture_output=True, text=True)
        (CACHE / f"{stem}.txt").write_text(result.stdout)
        (CACHE / f"{stem}.stderr.txt").write_text(result.stderr)
        if result.returncode != 0:
            raise RuntimeError(f"{stem}: INDETERMINATE; exit {result.returncode}; stderr: {result.stderr}")
        expected = ROOT / f"{stem}.txt"
        if expected.exists() and expected.read_text() != result.stdout:
            raise RuntimeError(f"Output differs from committed evidence: {stem}.txt")
        print(result.stdout, end="")
    receipt = qemu_receipt()
    (CACHE / "qemu-capability.txt").write_text(receipt)
    if (ROOT / "qemu-capability.txt").exists() and (ROOT / "qemu-capability.txt").read_text() != receipt:
        raise RuntimeError("QEMU receipt differs")
    print(receipt, end="")


def check() -> None:
    check_inputs()
    for line in (ROOT / "evidence.sha256").read_text().splitlines():
        expected, filename = line.split("  ", 1)
        if sha((ROOT / filename).read_bytes()) != expected:
            raise RuntimeError(f"Changed committed evidence: {filename}")
    if (ROOT / "qemu-capability.txt").read_text() != qemu_receipt():
        raise RuntimeError("QEMU receipt differs")
    print("PASS: pinned source hashes, committed evidence hashes, and QEMU inventory checks")
    print("RESULT: force polarity correct; failed-init active-low claim contradicted; hardware levels INDETERMINATE")


if __name__ == "__main__":
    actions = {"fetch": fetch, "run": run, "check": check}
    if len(sys.argv) != 2 or sys.argv[1] not in actions:
        raise SystemExit("usage: python3 -B reproduce.py {fetch|run|check}")
    actions[sys.argv[1]]()
