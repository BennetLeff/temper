"""Tests for scripts/check_firmware_link.py.

Covers the four ways the firmware link ratchet must fail, plus the one way it
passes. Each case is driven by a synthetic `idf.py build` log, so these run
without docker or the ESP-IDF toolchain.

The gate's whole value is that it fails CLOSED: the original defect was a build
that reported success while silently omitting the safety and control
components, so "no undefined symbols were found" must never be reachable from a
build that did not actually get to the linker.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_firmware_link import (  # noqa: E402
    ALLOWED_UNBUILT_COMPONENT_DIRS,
    LEDGER_PATH,
    main as gate_main,
    parse_ledger,
)

CONFIGURE_BANNER = "-- Building ESP-IDF components for target esp32s3\n"


def _log(*, excluded=(), failed=(), undefined=(), configured=True) -> str:
    parts = []
    for name in excluded:
        parts.append(
            f"-- Component directory /work/firmware/components/{name} does not "
            f"contain a CMakeLists.txt file. No component will be added\n"
        )
    if configured:
        parts.append(CONFIGURE_BANNER)
    for target in failed:
        parts.append(f"FAILED: {target} \n")
    for sym in undefined:
        parts.append(f"ld: foo.c.obj:(.text+0x1c): undefined reference to `{sym}'\n")
    return "".join(parts)


def _run(tmp_path: Path, log_text: str, argv_extra=()) -> int:
    log = tmp_path / "build.log"
    log.write_text(log_text, encoding="utf-8")
    argv = ["check_firmware_link.py", "--log", str(log), *argv_extra]
    old = sys.argv
    sys.argv = argv
    try:
        return gate_main()
    finally:
        sys.argv = old


@pytest.fixture()
def ledger_symbols() -> set[str]:
    return parse_ledger(LEDGER_PATH)


def test_ledger_is_non_empty_and_holds_the_protection_symbols(ledger_symbols):
    """The committed ledger must still record the safety-critical reads.

    If these ever disappear from the ledger it means either that a real sensor
    layer landed (in which case this test should be updated deliberately, in
    that same commit) or that someone stubbed them. The second is the outcome
    this whole gate exists to prevent, so it must not pass silently.
    """
    assert ledger_symbols, "ledger is empty; the firmware is not expected to link"
    for sym in (
        "read_dc_bus_current",
        "read_heatsink_temperature",
        "is_fan_running",
        "read_rtd_resistance",
    ):
        assert sym in ledger_symbols


def test_passes_when_undefined_set_matches_ledger(tmp_path, ledger_symbols):
    log = _log(
        excluded=sorted(ALLOWED_UNBUILT_COMPONENT_DIRS),
        failed=("induction_cooker.elf",),
        undefined=sorted(ledger_symbols),
    )
    assert _run(tmp_path, log) == 0


def test_new_symbol_fails(tmp_path, ledger_symbols):
    log = _log(
        excluded=sorted(ALLOWED_UNBUILT_COMPONENT_DIRS),
        failed=("induction_cooker.elf",),
        undefined=sorted(ledger_symbols) + ["brand_new_missing_symbol"],
    )
    assert _run(tmp_path, log) == 1


def test_stale_entry_fails(tmp_path, ledger_symbols):
    """A symbol that stopped being undefined must be recorded, not absorbed."""
    shrunk = sorted(ledger_symbols)[1:]
    log = _log(
        excluded=sorted(ALLOWED_UNBUILT_COMPONENT_DIRS),
        failed=("induction_cooker.elf",),
        undefined=shrunk,
    )
    assert _run(tmp_path, log) == 1


def test_compile_failure_is_not_reported_as_a_clean_ratchet(tmp_path):
    """A pre-link failure must fail, even though it yields zero undefined refs."""
    log = _log(
        excluded=sorted(ALLOWED_UNBUILT_COMPONENT_DIRS),
        failed=("esp-idf/safety/CMakeFiles/__idf_safety.dir/safety.c.obj",),
        undefined=(),
    )
    assert _run(tmp_path, log) == 1


def test_silently_excluded_component_fails(tmp_path, ledger_symbols):
    """The original defect: a component dropped for want of a CMakeLists.txt."""
    log = _log(
        excluded=sorted(ALLOWED_UNBUILT_COMPONENT_DIRS) + ["safety"],
        failed=("induction_cooker.elf",),
        undefined=sorted(ledger_symbols),
    )
    assert _run(tmp_path, log) == 1


def test_incremental_log_fails_closed(tmp_path, ledger_symbols):
    """Without a fresh configure the exclusion check is blind, so refuse."""
    log = _log(
        failed=("induction_cooker.elf",),
        undefined=sorted(ledger_symbols),
        configured=False,
    )
    assert _run(tmp_path, log) == 1
