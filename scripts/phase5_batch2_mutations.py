#!/usr/bin/env python3
"""Phase-5 Batch-2 mutation campaign driver (slot_generation / zone_geometry /
zone_assignment deterministic-stage kernels).

For each mutation: apply a one-line edit to the Rust kernel source, rebuild
the temper-design-bundle extension, run the six Batch-2 suites (3 differential
+ 3 PBT), expect FAILURE, then revert. A mutation that does NOT fail the
differential is a survivor — the campaign either closes it with a
discriminating case or records it. After the last mutant the driver rebuilds
from pristine source and re-runs the suites, so the campaign ends bit-exact
(the per-mutant revert alone would leave the installed .so carrying the
final mutant — the revert does not recompile).

Run: python3 scripts/phase5_batch2_mutations.py  (from repo root)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path("/private/tmp/wt5-deterministic")
CARGO = ROOT / "packages/temper-design-bundle/Cargo.toml"
PLACER = ROOT / "packages/temper-placer"
SUITES = [
    "tests/deterministic/stages/test_slot_generation_rust_differential.py",
    "tests/deterministic/stages/test_zone_geometry_rust_differential.py",
    "tests/deterministic/stages/test_zone_assignment_rust_differential.py",
    "tests/deterministic/stages/test_slot_generation_pbt.py",
    "tests/deterministic/stages/test_zone_geometry_pbt.py",
    "tests/deterministic/stages/test_zone_assignment_pbt.py",
]


def run(cmd, cwd=ROOT, timeout=1800):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return r.returncode, r.stdout + r.stderr


def rebuild():
    r = subprocess.run(
        [
            "uv",
            "run",
            "--no-sync",
            "maturin",
            "develop",
            "--release",
            "--manifest-path",
            str(CARGO),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    if r.returncode != 0:
        raise RuntimeError(f"rebuild failed: {r.stdout + r.stderr}"[-2000:])


def run_suites():
    code, out = run(
        ["uv", "run", "--no-sync", "python", "-m", "pytest"]
        + SUITES
        + ["-p", "no:cacheprovider", "-q", "--tb=line", "--maxfail=5"],
        cwd=PLACER,
    )
    return code, out


MUTATIONS = [
    # (label, file, old, new, expected-to-fail)
    (
        "M1 slots: outer bound <= instead of strict <",
        "packages/temper-design-bundle/src/deterministic_stages.rs",
        "    while x < x_max {",
        "    while x <= x_max {",
    ),
    (
        "M2 slots: inner bound <= instead of strict <",
        "packages/temper-design-bundle/src/deterministic_stages.rs",
        "        while y < y_max {",
        "        while y <= y_max {",
    ),
    (
        "M3 slots: anchor min + spacing instead of min + spacing/2",
        "packages/temper-design-bundle/src/deterministic_stages.rs",
        "    let mut x = x_min + spacing / 2.0;",
        "    let mut x = x_min + spacing;",
    ),
    (
        "M4 slots: inner anchor min instead of min + spacing/2",
        "packages/temper-design-bundle/src/deterministic_stages.rs",
        "        let mut y = y_min + spacing / 2.0;",
        "        let mut y = y_min;",
    ),
    (
        "M5 layout: Power boundary 0.6 -> 0.7",
        "packages/temper-design-bundle/src/deterministic_stages.rs",
        "        power_x_max: board_width * 0.6,",
        "        power_x_max: board_width * 0.7,",
    ),
    (
        "M6 layout: Signal boundary 0.9 -> 0.8",
        "packages/temper-design-bundle/src/deterministic_stages.rs",
        "        signal_x_max: board_width * 0.9,",
        "        signal_x_max: board_width * 0.8,",
    ),
    (
        "M7 scale: y scaled by width instead of height",
        "packages/temper-design-bundle/src/deterministic_stages.rs",
        "    (r0 * w, r1 * h, r2 * w, r3 * h)",
        "    (r0 * w, r1 * w, r2 * w, r3 * h)",
    ),
    (
        "M8 scale: x2/y2 swapped",
        "packages/temper-design-bundle/src/deterministic_stages.rs",
        "    (r0 * w, r1 * h, r2 * w, r3 * h)",
        "    (r0 * w, r1 * h, r3 * w, r2 * h)",
    ),
    (
        "M9 assign: U_MCU prefix without underscore",
        "packages/temper-design-bundle/src/deterministic_stages.rs",
        '    if r#ref.starts_with("U_MCU") {',
        '    if r#ref.starts_with("UMCU") {',
    ),
    (
        "M10 assign: drop UART from protocol scan",
        "packages/temper-design-bundle/src/deterministic_stages.rs",
        '        if ["SPI", "I2C", "UART"].iter().any(|proto| upper.contains(proto)) {',
        '        if ["SPI", "I2C"].iter().any(|proto| upper.contains(proto)) {',
    ),
    (
        "M11 assign: HighVoltage net-class spelled wrong",
        "packages/temper-design-bundle/src/deterministic_stages.rs",
        '        if net_class_map.get(net_name).map(String::as_str) == Some("HighVoltage") {',
        '        if net_class_map.get(net_name).map(String::as_str) == Some("HighVoltageX") {',
    ),
    (
        "M12 assign: Power checked before HV (rule-order swap)",
        "packages/temper-design-bundle/src/deterministic_stages.rs",
        """    // Rule 3: HV zone by net class.
    for net_name in nets {
        if net_class_map.get(net_name).map(String::as_str) == Some("HighVoltage") {
            return "HV".to_string();
        }
    }
    // Rule 4: Power zone by net class.
    for net_name in nets {
        if net_class_map.get(net_name).map(String::as_str) == Some("Power") {
            return "Power".to_string();
        }
    }""",
        """    // Rule 3 (mutated): Power zone by net class.
    for net_name in nets {
        if net_class_map.get(net_name).map(String::as_str) == Some("Power") {
            return "Power".to_string();
        }
    }
    // Rule 4 (mutated): HV zone by net class.
    for net_name in nets {
        if net_class_map.get(net_name).map(String::as_str) == Some("HighVoltage") {
            return "HV".to_string();
        }
    }""",
    ),
]


def main() -> int:
    results = []
    for label, rel, old, new in MUTATIONS:
        path = ROOT / rel
        src = path.read_text()
        assert old in src, f"{label}: anchor not found in {rel}"
        src2 = src.replace(old, new, 1)
        assert src2 != src, f"{label}: replace was a no-op"
        path.write_text(src2)
        try:
            rebuild()
            code, out = run_suites()
        except RuntimeError as exc:
            code, out = 2, str(exc)
        finally:
            path.write_text(src)  # revert
        killed = code != 0
        results.append((label, killed, out))
        print(f"{'KILLED' if killed else 'SURVIVED'}: {label}")
        if not killed:
            print(out[-1500:])
    print("\n=== SUMMARY ===")
    for label, killed, _ in results:
        print(f"{'PASS(killed)' if killed else 'SURVIVED'}: {label}")
    # The LAST mutation's rebuild happens while the mutant is still applied
    # (the revert in `finally` does not recompile), so the installed .so
    # still carries the final mutant afterwards. Rebuild from pristine
    # source and re-run the suites so the campaign ends bit-exact.
    rebuild()
    code, out = run_suites()
    print(f"PRISTINE REBUILD + SUITES: exit={code}")
    if code != 0:
        print(out[-2000:])
        return 1
    return 0 if all(k for _, k, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
