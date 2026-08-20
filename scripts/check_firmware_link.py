#!/usr/bin/env python3
"""Firmware link ratchet: the ESP32-S3 image must compile, and its set of
undefined symbols must only ever SHRINK.

Why this exists
---------------
The production firmware has never linked. Until 2026-08-20 nothing in PR or
push CI ever ran ``idf.py build``: it appears in exactly two workflows --
``release-artifacts.yml`` (``release: published`` only) and
``firmware-perf-record.yml`` (needs a ``[self-hosted, esp32]`` runner whose own
header says it was never provisioned). So five independently fatal build-system
defects and four silently-excluded components accumulated without a single red
check.

The worst of them was silent by construction: ESP-IDF reports a component
directory with no ``CMakeLists.txt`` with an *informational* message --
"Component directory ... does not contain a CMakeLists.txt file. No component
will be added" -- and then configures, compiles and links happily without it.
``components/control`` and ``components/safety`` were dropped from the image
that way, which is why ``read_dc_bus_current`` (dispatching the IGBT
short-circuit and over-current trips at state_machine.c:400,404) and
``read_heatsink_temperature`` were missing.

What this gate does NOT do
--------------------------
It does not make the build green. The firmware genuinely has no sensor
peripheral layer: ``read_dc_bus_current``, ``read_heatsink_temperature``,
``is_fan_running`` and ``read_rtd_resistance`` are declared ``extern`` in
safety.c's ``#else`` (non-simulation) arm and defined nowhere. An honest link
failure is the correct state, and this gate's job is to hold that state
*stable and visible* rather than to hide it. Stubbing any of those would
silently fabricate a protection path -- far worse than a red link.

Why a ratchet rather than a pass/fail build
-------------------------------------------
A gate that ships red gets switched off; this repo has several tripwires that
died exactly that way. So the ratchet is GREEN when the undefined-symbol set
matches the committed ledger exactly, and RED on any drift, in either
direction. It follows ``scripts/check_hash_order_determinism.py`` /
``.hash-order-inventory``:

  * a symbol not in the ledger FAILS (``NEW_SYMBOL``) -- a regression, or new
    code calling something that does not exist;
  * a ledger symbol that no longer fires FAILS (``STALE_ENTRY``) -- debt paid
    must be recorded in the same diff, or the ledger silently stops shrinking;
  * the build failing anywhere BEFORE the link FAILS (``COMPILE_REGRESSION``) --
    a configure or compile error must never be reported as "no undefined
    symbols", which is how a fail-open ratchet would read it;
  * a component directory silently excluded for want of a CMakeLists.txt, and
    not on ``ALLOWED_UNBUILT_COMPONENT_DIRS``, FAILS (``SILENT_EXCLUSION``) --
    this is the original defect class and it must never be silent again.

The ledger is keyed on symbol NAMES, not on the raw ``undefined reference``
count: the reference count moves with inlining and optimisation decisions,
while the symbol set is a property of the source. Both numbers are printed on
every run so the count is visible in the job output regardless of verdict.

Simulation-code guard
---------------------
``--check-sim-symbols BUILD_DIR`` additionally asserts that no ``sim_state`` or
``*_sim_*`` symbol is DEFINED anywhere in the built objects. safety.c defines a
static simulated ``read_dc_bus_current()`` returning ``sim_state.dc_bus_current``,
guarded by ``#ifndef ESP_PLATFORM``; pll_control.c and zvs_monitor.c have the
same shape. ESP-IDF defines ``ESP_PLATFORM`` for every target build so those
blocks are preprocessed away -- but that is exactly the kind of invariant that
holds until someone changes a guard, and linking simulated sensor reads into a
production cooktop image is the worst outcome available here.

Usage
-----
  # in the espressif/idf:release-v5.3 container, from firmware/
  idf.py build 2>&1 | tee /tmp/idf-build.log || true
  python3 scripts/check_firmware_link.py --log /tmp/idf-build.log \\
      --check-sim-symbols firmware/build

  # record a shrunken ledger after genuinely implementing a symbol
  python3 scripts/check_firmware_link.py --log /tmp/idf-build.log --write-ledger

Exit codes
----------
  0 - the undefined-symbol set matches the ledger exactly
  1 - drift in either direction, a pre-link build failure, a newly silent
      component exclusion, or simulation code found in the image
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LEDGER_PATH = REPO_ROOT / ".firmware-link-inventory"

# Component directories legitimately without a CMakeLists.txt. Anything else
# appearing in IDF's "No component will be added" message is a silent
# exclusion and fails the gate.
#
#   sensors - its sources ARE built: main/CMakeLists.txt compiles
#             max31865.c and rtd_service.c directly, because rtd_service.c
#             includes main's state_machine.h and registering sensors as its
#             own component would make main and sensors mutually dependent.
#             Giving it a CMakeLists.txt would compile those sources twice and
#             produce duplicate symbols at link.
#   testing - header-only (test_macros.h) and, as of 2026-08-20, has zero
#             consumers anywhere in the repo. Registering it would push test
#             scaffolding onto the production include path for no benefit.
ALLOWED_UNBUILT_COMPONENT_DIRS = frozenset({"sensors", "testing"})

_UNDEF_RE = re.compile(r"undefined reference to `([^']+)'")
_NO_COMPONENT_RE = re.compile(
    r"Component directory (\S+) does not contain a CMakeLists\.txt file"
)
# IDF prints this once per *fresh* configure. An incremental rebuild reuses the
# existing cache and prints neither it nor the "No component will be added"
# lines -- so without this marker an incremental log would show zero silent
# exclusions and the gate would pass for the wrong reason. Fail closed instead:
# this gate is only meaningful against a clean build.
_CONFIGURE_MARKER = "Building ESP-IDF components for target"
# Ninja names the object or binary it could not produce.
_FAILED_RE = re.compile(r"^FAILED:\s+(\S+)", re.MULTILINE)
# The final image. A FAILED line naming anything else is a pre-link failure.
_LINK_TARGETS = ("induction_cooker.elf",)


def parse_ledger(path: Path) -> set[str]:
    if not path.exists():
        return set()
    symbols = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        symbols.add(line)
    return symbols


def write_ledger(path: Path, symbols: set[str], total_refs: int) -> None:
    header = f"""\
# Undefined symbols in the ESP32-S3 firmware image. See
# scripts/check_firmware_link.py for what this file is and why it is a ratchet
# rather than a suppression list.
#
# Format: one linker symbol name per line, sorted.
# Regenerate with: python3 scripts/check_firmware_link.py --log <build.log> --write-ledger
#
# The production firmware has never linked. These symbols are declared and
# called but defined nowhere in the repo -- there is no peripheral/sensor
# implementation layer. This ledger is expected to SHRINK, one symbol at a
# time, as that layer is genuinely implemented.
#
# A symbol here that no longer fires is a FAILURE, not a pass: delete its line
# in the same commit that implements it. A symbol NOT here is also a failure.
#
# DO NOT shrink this ledger by stubbing. Four of these entries --
# read_dc_bus_current, read_heatsink_temperature, is_fan_running and
# read_rtd_resistance -- are the sensor reads that the IGBT short-circuit,
# over-current, thermal and fan-failure trips dispatch on
# (firmware/main/state_machine.c, firmware/components/safety/safety.c). A stub
# returning a safe-looking constant would silently fabricate protection and is
# strictly worse than this honest link failure. Implement them against real
# hardware or leave them here.
#
# At the time of writing: {len(symbols)} distinct symbols, {total_refs} undefined references.
"""
    body = "\n".join(sorted(symbols))
    path.write_text(header + "\n" + body + "\n", encoding="utf-8")


def check_sim_symbols(build_dir: Path, nm: str) -> list[str]:
    """Return a list of DEFINED simulation symbols found in the built objects."""
    objs = sorted(build_dir.rglob("*.obj")) + sorted(build_dir.rglob("*.o"))
    if not objs:
        return ["<no object files found under %s>" % build_dir]
    found: list[str] = []
    # Chunk to stay under ARG_MAX on large trees.
    for i in range(0, len(objs), 200):
        batch = [str(p) for p in objs[i : i + 200]]
        try:
            out = subprocess.run(
                [nm, "--defined-only", *batch],
                capture_output=True,
                text=True,
                check=False,
            ).stdout
        except FileNotFoundError:
            return ["<%s not found; run this inside the ESP-IDF container>" % nm]
        for line in out.splitlines():
            parts = line.split()
            if len(parts) < 2:
                continue
            name = parts[-1]
            if "sim_state" in name or "_sim_" in name:
                found.append(name)
    return sorted(set(found))


def emit(text: str) -> None:
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--log", required=True, type=Path,
                    help="captured output of `idf.py build`")
    ap.add_argument("--write-ledger", action="store_true",
                    help="rewrite the ledger from this log instead of checking")
    ap.add_argument("--check-sim-symbols", type=Path, default=None,
                    metavar="BUILD_DIR",
                    help="assert no simulation symbol is defined in the built objects")
    ap.add_argument("--nm", default="xtensa-esp32s3-elf-nm",
                    help="nm binary used by --check-sim-symbols")
    args = ap.parse_args()

    if not args.log.exists():
        print(f"FAIL: build log {args.log} does not exist", file=sys.stderr)
        return 1
    log = args.log.read_text(encoding="utf-8", errors="replace")

    failures: list[str] = []

    # ---- 1. Silently excluded components -----------------------------------
    configured_fresh = _CONFIGURE_MARKER in log
    excluded = set()
    for m in _NO_COMPONENT_RE.finditer(log):
        excluded.add(Path(m.group(1)).name)
    unexpected = sorted(excluded - ALLOWED_UNBUILT_COMPONENT_DIRS)

    # ---- 2. Did the build reach the linker? --------------------------------
    failed_targets = _FAILED_RE.findall(log)
    pre_link_failures = sorted(
        {t for t in failed_targets if not t.endswith(_LINK_TARGETS)}
    )

    # ---- 3. Undefined symbols ----------------------------------------------
    refs = _UNDEF_RE.findall(log)
    symbols = set(refs)
    total_refs = len(refs)

    # ---- Report (always, regardless of verdict) ----------------------------
    emit("## Firmware link ratchet")
    emit("")
    emit(f"* undefined symbols (distinct): **{len(symbols)}**")
    emit(f"* undefined references (total): **{total_refs}**")
    emit(f"* ledger: `{LEDGER_PATH.relative_to(REPO_ROOT)}`")
    emit(f"* components excluded for want of a CMakeLists.txt: "
         f"{sorted(excluded) or 'none'}")
    emit(f"* build targets that failed before the link: "
         f"{pre_link_failures or 'none'}")
    emit("")

    if args.write_ledger:
        write_ledger(LEDGER_PATH, symbols, total_refs)
        emit(f"Wrote {len(symbols)} symbols to {LEDGER_PATH}")
        return 0

    if not configured_fresh:
        failures.append(
            f"NOT_A_CLEAN_BUILD: the log has no {_CONFIGURE_MARKER!r} line, so it "
            f"came from an incremental rebuild. IDF only reports silently "
            f"excluded component directories during a fresh configure, so this "
            f"gate cannot tell a clean tree from a dropped component here. "
            f"Delete firmware/build and re-run `idf.py build`."
        )

    if unexpected:
        failures.append(
            "SILENT_EXCLUSION: component director"
            + ("ies" if len(unexpected) > 1 else "y")
            + f" {unexpected} ha"
            + ("ve" if len(unexpected) > 1 else "s")
            + " no CMakeLists.txt, so ESP-IDF dropped "
            + ("them" if len(unexpected) > 1 else "it")
            + " from the image without failing the build. Add a CMakeLists.txt, "
              "or add the directory to ALLOWED_UNBUILT_COMPONENT_DIRS in "
              "scripts/check_firmware_link.py with the reason."
        )

    if pre_link_failures:
        failures.append(
            f"COMPILE_REGRESSION: the build failed before reaching the linker: "
            f"{pre_link_failures}. The firmware must configure and compile "
            f"cleanly; only the final link may fail. Undefined-symbol counts "
            f"from this run are not meaningful."
        )

    # ---- 4. Simulation-code guard ------------------------------------------
    if args.check_sim_symbols is not None:
        sim = check_sim_symbols(args.check_sim_symbols, args.nm)
        if sim:
            failures.append(
                f"SIMULATION_CODE_IN_IMAGE: these simulation symbols are DEFINED "
                f"in the built objects: {sim}. safety.c / pll_control.c / "
                f"zvs_monitor.c keep their simulated sensor reads behind "
                f"`#ifndef ESP_PLATFORM`; if one is reachable in a target build, "
                f"a production image can dispatch a safety trip on a simulated "
                f"value. Fix the guard -- do not add the symbol to any ledger."
            )
        else:
            emit("* simulation symbols defined in the image: **none**")
            emit("")

    # ---- 5. Ratchet ---------------------------------------------------------
    if not pre_link_failures:
        ledger = parse_ledger(LEDGER_PATH)
        new_symbols = sorted(symbols - ledger)
        stale = sorted(ledger - symbols)

        if new_symbols:
            failures.append(
                f"NEW_SYMBOL: {len(new_symbols)} undefined symbol(s) not in the "
                f"ledger: {new_symbols}. Either the code newly calls something "
                f"that does not exist, or a component was dropped from the "
                f"build again."
            )
        if stale:
            failures.append(
                f"STALE_ENTRY: {len(stale)} ledger symbol(s) no longer undefined: "
                f"{stale}. If you implemented them, delete their lines from "
                f"{LEDGER_PATH.name} in this same commit so the ledger records "
                f"the progress. If they vanished because a component stopped "
                f"being built, that is a regression, not progress."
            )

    if failures:
        emit("### FAIL")
        emit("")
        for f in failures:
            emit(f"* {f}")
        return 1

    emit("### PASS")
    emit("")
    emit(f"The firmware configures and compiles; the link fails with exactly the "
         f"{len(symbols)} undefined symbols recorded in the ledger. That is the "
         f"expected state -- see the ledger header before trying to make it green.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
