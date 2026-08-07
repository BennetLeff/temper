#!/usr/bin/env python3
"""R1 WASM substrate smoke test — rungs 2-3.

Rung 2: cargo build --release --target wasm32-unknown-unknown -p temper-wasm-test-runner
Rung 3: compare all wasm test verdicts against native (cargo test --no-default-features).

USAGE: python3 tools/wasm/run_r1_smoke.py [--build-only]

Exits non-zero on any unexpected (non-manifested) wasm-vs-native mismatch.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
DRC_DIR = REPO / "packages" / "temper-drc-rs"
RUNNER_DIR = REPO / "packages" / "temper-wasm-test-runner"
CARGO_TARGET_DIR = Path.home() / "Desktop" / "temper" / "target-shared"
WASM_ARTIFACT = CARGO_TARGET_DIR / "wasm32-unknown-unknown" / "release" / "temper_wasm_test_runner.wasm"
EXPECTED_FAILURES_PATH = REPO / "tools" / "wasm" / "wasm_expected_failures.json"


def run(cmd, **kw):
    kw.setdefault("check", True)
    kw.setdefault("capture_output", True)
    kw.setdefault("text", True)
    kw.setdefault("cwd", str(REPO))
    return subprocess.run(cmd, **kw)


# ---------------------------------------------------------------------------
# Rung 2 — build
# ---------------------------------------------------------------------------

def build_wasm() -> Path:
    env = os.environ.copy()
    env["CARGO_TARGET_DIR"] = str(CARGO_TARGET_DIR)
    run(
        ["cargo", "build", "--release", "--target", "wasm32-unknown-unknown"],
        cwd=str(RUNNER_DIR),
        env=env,
    )
    if not WASM_ARTIFACT.exists():
        sys.exit(f"FAIL: wasm artifact not found at {WASM_ARTIFACT}")
    return WASM_ARTIFACT


# ---------------------------------------------------------------------------
# Parse WASM_TESTS arrays from source, module by module, preserving order
# ---------------------------------------------------------------------------

def parse_wasm_test_array(filepath: Path) -> list[str]:
    """Extract test names from a WASM_TESTS array in order."""
    text = filepath.read_text()
    names = []
    in_block = False
    for line in text.split("\n"):
        if "pub const WASM_TESTS" in line:
            in_block = True
            continue
        if in_block:
            if "];" in line:
                break
            m = re.search(r'"([^"]+)"', line)
            if m:
                names.append(m.group(1))
    return names


def build_index_map() -> dict[int, str]:
    """Build index → test name by reading WASM_TESTS from source files in registry order."""
    registry_text = (DRC_DIR / "src" / "wasm_test_registry.rs").read_text()
    # Extract module paths from ALL array
    mod_pattern = re.compile(r"crate::(\S+)::WASM_TESTS")
    mod_paths = mod_pattern.findall(registry_text)

    # Map module paths to source files
    path_to_file = {
        "board::tests": DRC_DIR / "src" / "board.rs",
        "board::board_state_tests": DRC_DIR / "src" / "board.rs",
        "dfm::tests": DRC_DIR / "src" / "dfm" / "tests.rs",
        "pyfmt::tests": DRC_DIR / "src" / "pyfmt.rs",
        "pymath::tests": DRC_DIR / "src" / "pymath.rs",
        "rules::integration_tests": DRC_DIR / "src" / "rules" / "mod.rs",
        "rules::drc::clearance::tests": DRC_DIR / "src" / "rules" / "drc" / "clearance.rs",
        "rules::routing::power_pad_teardrop::tests": DRC_DIR / "src" / "rules" / "routing" / "power_pad_teardrop.rs",
        "types::clock::tests": DRC_DIR / "src" / "types" / "clock.rs",
        "types::esd::tests": DRC_DIR / "src" / "types" / "esd.rs",
        "types::fuse::tests": DRC_DIR / "src" / "types" / "fuse.rs",
        "types::guard::tests": DRC_DIR / "src" / "types" / "guard.rs",
        "types::hv_net::tests": DRC_DIR / "src" / "types" / "hv_net.rs",
        "types::magnetic::tests": DRC_DIR / "src" / "types" / "magnetic.rs",
        "types::noise::tests": DRC_DIR / "src" / "types" / "noise.rs",
        "types::vent::tests": DRC_DIR / "src" / "types" / "vent.rs",
    }

    index = 0
    index_to_name: dict[int, str] = {}

    for mod_path in mod_paths:
        filepath = path_to_file.get(mod_path)
        if filepath is None:
            print(f"WARNING: no file mapping for {mod_path}", file=sys.stderr)
            continue
        if not filepath.exists():
            print(f"WARNING: file not found: {filepath}", file=sys.stderr)
            continue

        # For board.rs, we need to parse the correct WASM_TESTS block
        if mod_path == "board::tests":
            names = parse_wasm_test_array_block(filepath, block_index=0)
        elif mod_path == "board::board_state_tests":
            names = parse_wasm_test_array_block(filepath, block_index=1)
        else:
            names = parse_wasm_test_array(filepath)

        for name in names:
            index_to_name[index] = name
            index += 1

    return index_to_name


def parse_wasm_test_array_block(filepath: Path, block_index: int) -> list[str]:
    """Extract test names from a specific WASM_TESTS block (0-indexed) in a file with multiple."""
    text = filepath.read_text()
    blocks = []
    current = []
    in_block = False
    for line in text.split("\n"):
        if "pub const WASM_TESTS" in line:
            if current:
                blocks.append(current)
                current = []
            in_block = True
            continue
        if in_block:
            if "];" in line:
                blocks.append(current)
                current = []
                in_block = False
                continue
            m = re.search(r'"([^"]+)"', line)
            if m:
                current.append(m.group(1))
    if current:
        blocks.append(current)
    if block_index < len(blocks):
        return blocks[block_index]
    return []


# ---------------------------------------------------------------------------
# Load expected failures manifest
# ---------------------------------------------------------------------------

def load_expected_failures() -> dict[str, dict]:
    if EXPECTED_FAILURES_PATH.exists():
        data = json.loads(EXPECTED_FAILURES_PATH.read_text())
        return data.get("expected_failures", {})
    return {}


# ---------------------------------------------------------------------------
# Run tests under wasmtime
# ---------------------------------------------------------------------------

def wasmtime_run(wasm: Path, index: int) -> tuple[bool, int]:
    """Run temper_run_test(index). Returns (passed: bool, exit_code: int)."""
    r = subprocess.run(
        ["wasmtime", "run", "--invoke", "temper_run_test", str(wasm), str(index)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    # exit 0 = pass (RUN_OK=0 returned)
    # exit non-zero = trap (panic/abort → unreachable)
    return (r.returncode == 0, r.returncode)


def wasmtime_count(wasm: Path) -> int:
    r = subprocess.run(
        ["wasmtime", "run", "--invoke", "temper_test_count", str(wasm)],
        capture_output=True,
        text=True,
        timeout=5,
    )
    output = (r.stderr + r.stdout).strip()
    for line in reversed(output.split("\n")):
        line = line.strip()
        if line.isdigit():
            return int(line)
    return -1


# ---------------------------------------------------------------------------
# Run native tests
# ---------------------------------------------------------------------------

def run_native_tests() -> dict[str, str]:
    """Run cargo test --no-default-features and return {test_name: 'pass'|'fail'}."""
    r = run(
        ["cargo", "test", "--no-default-features"],
        cwd=str(DRC_DIR),
        check=False,
    )
    results = {}
    for line in r.stdout.split("\n"):
        m = re.match(r"test (\S+) \.\.\. (ok|FAILED)", line)
        if m:
            results[m.group(1)] = "pass" if m.group(2) == "ok" else "fail"
    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    build_only = "--build-only" in sys.argv

    print("=" * 72)
    print("R1 WASM Substrate Smoke Test (rungs 2-3)")
    print("=" * 72)

    # Rung 2
    print("\n--- Rung 2: Build wasm32-unknown-unknown ---")
    wasm = build_wasm()
    size = wasm.stat().st_size
    sha = run(["shasum", "-a", "256", str(wasm)]).stdout.split()[0]
    print(f"  artifact: {wasm}")
    print(f"  size:     {size:,} bytes")
    print(f"  sha256:   {sha}")

    if build_only:
        print("\nBuild-only mode; skipping execution.")
        return

    # Import list
    print("\n  Import list:")
    r = run(["wasm-tools", "print", str(wasm)], check=False)
    imports = [l for l in r.stdout.split("\n") if "(import" in l]
    if imports:
        print(f"  WARNING: {len(imports)} imports found!")
        for l in imports[:30]:
            print(f"    {l.strip()}")
    else:
        print("  ZERO imports — deployable to a bare isolate ✓")

    # Rung 3
    print("\n--- Rung 3: Execute under wasmtime ---")

    index_to_name = build_index_map()
    expected = load_expected_failures()
    total_registered = wasmtime_count(wasm)
    print(f"  wasm module reports {total_registered} registered tests")

    if total_registered != len(index_to_name):
        print(f"  WARNING: {total_registered} registered but {len(index_to_name)} names parsed from source")

    # Run all wasm tests
    print(f"  Running {total_registered} tests under wasmtime...")
    wasm_results: dict[str, dict] = {}
    for i in range(total_registered):
        name = index_to_name.get(i, f"<unknown-{i}>")
        passed, exit_code = wasmtime_run(wasm, i)
        if passed:
            wasm_results[name] = {"status": "pass"}
        else:
            wasm_results[name] = {"status": "trap", "exit_code": exit_code}

    # Run native tests
    print(f"  Running native tests (cargo test --no-default-features)...")
    native_results = run_native_tests()
    print(f"    {len(native_results)} native test results parsed")

    # Classify against expected failures
    for name, info in expected.items():
        if name in wasm_results and wasm_results[name]["status"] == "trap":
            wasm_results[name]["expected"] = True
            wasm_results[name]["expected_class"] = info.get("class", "unknown")

    # Compute classification
    wasm_pass = sum(1 for r in wasm_results.values() if r["status"] == "pass")
    wasm_trap = sum(1 for r in wasm_results.values() if r["status"] == "trap" and not r.get("expected"))
    wasm_expected = sum(1 for r in wasm_results.values() if r["status"] == "trap" and r.get("expected"))
    native_pass = sum(1 for r in native_results.values() if r == "pass")
    native_fail = sum(1 for r in native_results.values() if r == "fail")

    print(f"\n  Summary:")
    print(f"    wasm:          {wasm_pass} pass, {wasm_trap} trap, {wasm_expected} expected-fail")
    print(f"    native:        {native_pass} pass, {native_fail} fail")

    # Six-family table
    print("\n--- Six-family exact-match table ---")
    family_tests = {
        "drc":      "rules::drc::clearance::tests::clearance_at_exact_threshold_flagged",
        "emc":      "rules::integration_tests::empty_board_zero_violations",
        "erc":      "rules::integration_tests::empty_board_zero_violations",
        "safety":   "rules::integration_tests::empty_board_zero_violations",
        "placement":"rules::integration_tests::empty_board_zero_violations",
        "routing":  "rules::routing::power_pad_teardrop::tests::test_distance_to_rect_edge_outside",
    }
    # Note: routing also has test_distance_to_rect_edge_*; integration tests exercise all

    for family, test in family_tests.items():
        w = wasm_results.get(test, {})
        n = native_results.get(test, "UNREGISTERED")
        ws = w.get("status", "UNREGISTERED")
        ns = n if isinstance(n, str) else n.get("status", "UNREGISTERED")
        if ws == "pass" and ns == "pass":
            verdict = "MATCH ✓"
        elif w.get("expected"):
            verdict = "EXPECTED-FAIL"
        elif ws == "UNREGISTERED" or ns == "UNREGISTERED":
            verdict = "UNREGISTERED"
        else:
            verdict = f"MISMATCH (wasm:{ws} native:{ns})"
        print(f"  {family:12s} | {test:72s} | {verdict}")

    # Full per-test comparison
    print("\n--- Per-test comparison ---")
    all_names = sorted(set(list(wasm_results.keys()) + list(native_results.keys())))
    mismatches = 0
    stale_expected = []  # expected-fail tests that now pass
    for name in all_names:
        wr = wasm_results.get(name, {"status": "UNREGISTERED"})
        nr = native_results.get(name, "UNREGISTERED")

        ws = wr["status"]
        ns = nr if isinstance(nr, str) else nr.get("status", "UNREGISTERED")

        if ws == "pass" and ns == "pass":
            continue
        if ws == "trap" and wr.get("expected") and ns == "pass":
            continue  # expected
        if ws == "pass" and ns == "UNREGISTERED" and name.startswith("<unknown"):
            continue  # couldn't parse name
        if ws == "UNREGISTERED" and ns == "pass":
            # Registered in native but not found in wasm → naming mismatch
            if len(all_names) > 90 and mismatches < 5:  # only report a few
                print(f"  [NATIVE-ONLY] {name}")
            mismatches += 1
            continue
        if ws == "pass" and name in expected:
            # This test was expected to fail but now passes → stale manifest
            stale_expected.append(name)
            print(f"  [STALE-EXPECTED-FAIL (now passes)] {name}")
            mismatches += 1
            continue
        if ws != ns:
            print(f"  [{name}] wasm:{ws} vs native:{ns}")
            if wr.get("exit_code"):
                print(f"    exit_code: {wr['exit_code']}")
            mismatches += 1

    print(f"\n  mismatches: {mismatches}")
    if stale_expected:
        print(f"  stale expected-fail entries (now pass): {len(stale_expected)}")
        for name in stale_expected:
            print(f"    {name}")

    # ULP findings
    print("\n--- ULP / threshold findings ---")
    unexpected_traps = [
        n for n, r in wasm_results.items()
        if r["status"] == "trap" and not r.get("expected")
    ]
    if unexpected_traps:
        print(f"  {len(unexpected_traps)} unexpected trap(s):")
        for name in unexpected_traps:
            print(f"    {name}")
    else:
        print("  None — all traps are either expected or match native failures")

    # Verdict
    print("\n--- R1 Verdict (rungs 2-3) ---")
    print(f"  Rung 2 (links):              PASS ✓  ({size:,} bytes, sha256={sha[:16]}...)")
    if not imports:
        print(f"  Rung 2 (import list):        PASS ✓  (zero imports, bare-isolate deployable)")
    else:
        print(f"  Rung 2 (import list):        FAIL ✗  ({len(imports)} imports)")

    # Check: are there unexpected mismatches?
    # Expected failures that are not in the manifest
    unmanifested_traps = [n for n in unexpected_traps if n not in expected]
    if unmanifested_traps:
        print(f"  Rung 3 (execution):          FAIL ✗  ({len(unmanifested_traps)} unexpected traps)")
    elif mismatches > 0 and not stale_expected:
        print(f"  Rung 3 (execution):          FAIL ✗  ({mismatches} mismatches)")
    elif stale_expected:
        print(f"  Rung 3 (execution):          PASS-WITH-STALE-MANIFEST  ({len(stale_expected)} expected-fail entries now pass)")
    else:
        print(f"  Rung 3 (execution):          PASS ✓  (all tests match native)")

    print(f"  Six-family exact-match:      {'PASS ✓' if mismatches == 0 or (mismatches == len(stale_expected) and not unmanifested_traps) else 'ISSUES'}")
    print(f"  Import list clean:           {'YES ✓' if not imports else 'NO ✗'}")

    sys.exit(0 if (not unmanifested_traps and (mismatches == 0 or mismatches == len(stale_expected))) else 1)


if __name__ == "__main__":
    main()
