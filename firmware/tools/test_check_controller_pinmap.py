"""Tests for firmware/tools/check_controller_pinmap.py.

The guard runs against the committed controller.ato snapshot (always), against the
live ``controller-layout`` branch when this clone has it, and against mutated copies
of the ato / header / sources to show that each class of drift is caught.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_controller_pinmap as guard  # noqa: E402


def _fixture_text() -> str:
    text, _ = guard.load_fixture()
    return text


def _run(ato_text: str, pins_h: str | None = None, board_c: str | None = None,
         sources: dict[str, str] | None = None) -> list[str]:
    return guard.check(
        guard.parse_ato(ato_text),
        pins_h if pins_h is not None else guard.PINS_H.read_text(),
        board_c if board_c is not None else guard.BOARD_C.read_text(),
        sources if sources is not None else {},
    )


def _has_ref(ref: str) -> bool:
    return subprocess.run(
        ["git", "-C", str(guard.REPO), "cat-file", "-e", f"{ref}:{guard.ATO_PATH_IN_REPO}"],
        capture_output=True,
    ).returncode == 0


def test_fixture_matches_firmware_map():
    assert guard.main([]) == guard.EXIT_OK


def test_fixture_is_byte_exact_snapshot():
    text, prov = guard.load_fixture()
    assert guard.git_blob_id(text.encode()) == prov["git_blob"]
    assert prov["path"] == guard.ATO_PATH_IN_REPO


def test_parse_reads_the_l2_moves():
    ato = guard.parse_ato(_fixture_text())
    assert ato.gpio["run_en"] == 14
    assert ato.gpio["i2c_sda"] == 37 and ato.gpio["boot_io0"] == 0
    assert ato.gpio["rim_adc"] == 9
    assert ato.gpio["ui_miso"] == 44  # mcu.RXD0
    assert {n: ato.gpio[n] for n in ("ui_sck", "ui_mosi", "ui_cs_oled_n", "ui_dc", "ui_cs_exp_n")} == {
        "ui_sck": 40, "ui_mosi": 41, "ui_cs_oled_n": 47, "ui_dc": 45, "ui_cs_exp_n": 48}
    assert ato.expander["rtd_drdy"] == 7 and ato.expander["sup_run_ok_rb"] == 12
    assert "rtd_drdy" not in ato.gpio and "sup_run_ok_rb" not in ato.gpio
    assert guard.derived_pull(ato, "run_en") == "DOWN"
    assert guard.derived_pull(ato, "ui_dc") == "DOWN"
    assert guard.derived_pull(ato, "boot_io0") == "UP"
    assert guard.derived_pull(ato, "pwm_ha_mcu") == "DOWN"  # 10 k behind the 33 R series
    assert guard.derived_pull(ato, "fan_tach") == "UP"      # 10 k behind the 1 k series


def test_live_branch_matches_firmware_map():
    if not _has_ref("controller-layout"):
        pytest.skip("controller-layout branch not in this clone")
    assert guard.main(["--git-ref", "controller-layout"]) == guard.EXIT_OK


def test_layout_l2_commit_differs_only_by_the_l3_blower_lines():
    ref = "bdddaee88"
    if not _has_ref(ref):
        pytest.skip("layout L2 commit not in this clone")
    errors = _run(guard.load_git_ref(ref), sources={})
    assert errors and all("fan_off" in e or "fan_pwm" in e or "FAN_PWM" in e or "FAN_OFF" in e
                          for e in errors), errors


@pytest.mark.parametrize(
    "old,new,needle",
    [
        ("mcu.IO14 ~ run_en", "mcu.IO13 ~ run_en", "run_en"),            # moved GPIO
        ("mcu.IO9 ~ rim_adc", "mcu.IO10 ~ rim_adc", "rim_adc"),          # ADC channel too
        ("u_io.P07 ~ rtd_drdy", "u_io.P06 ~ rtd_drdy", "rtd_drdy"),      # expander bit
        ("    r_run_en_pd.p2 ~ selv_gnd\n", "", "run_en"),                # RUN_EN pull-down gone
        ("    r_dc_pd.p2 ~ selv_gnd\n", "", "ui_dc"),                     # GPIO45 strap pull-down gone
        ("    r_scl_pu.p1 ~ v3v3\n", "", "boot_io0"),                     # GPIO0 strap pull-up gone
        ("mcu.IO3 ~ fan_tach\n", "mcu.IO3 ~ fan_tach\n    mcu.IO26 ~ spi_flash\n", "spi_flash"),
    ],
)
def test_hardware_drift_is_caught(old, new, needle):
    text = _fixture_text()
    assert old in text, old
    errors = _run(text.replace(old, new, 1))
    assert any(needle in e for e in errors), errors


def test_header_drift_is_caught():
    pins_h = guard.PINS_H.read_text()
    bad = pins_h.replace("#define CTRL_GPIO_RUN_EN           14", "#define CTRL_GPIO_RUN_EN           15")
    assert bad != pins_h
    errors = _run(_fixture_text(), pins_h=bad)
    assert any("CTRL_GPIO_RUN_EN" in e for e in errors)
    assert any("GPIO15 defined twice" in e for e in errors)


def test_board_table_drift_is_caught():
    board_c = guard.BOARD_C.read_text()
    bad = board_c.replace(
        'ROW(CTRL_GPIO_RUN_EN, "run_en", CTRL_FN_GPIO_OUT, CTRL_OWNER_BOARD, CTRL_PULL_NONE, CTRL_PULL_DOWN',
        'ROW(CTRL_GPIO_RUN_EN, "run_en", CTRL_FN_GPIO_OUT, CTRL_OWNER_BOARD, CTRL_PULL_NONE, CTRL_PULL_NONE')
    assert bad != board_c
    assert any("run_en external_pull" in e for e in _run(_fixture_text(), board_c=bad))


def test_source_rules():
    errors = _run(_fixture_text(), sources={
        "firmware/main/x.c": '#include "temper_pins.h"\n',
        "firmware/main/y.c": "uart_driver_install(UART_NUM_0, 256, 0, 0, NULL, 0);\n",
    })
    assert any("temper_pins.h" in e for e in errors)
    assert any("UART0" in e for e in errors)
    # The real controller sources are clean.
    assert _run(_fixture_text(), sources=guard.controller_sources()) == []


def test_gate_error_on_unparseable_ato(tmp_path):
    p = tmp_path / "empty.ato"
    p.write_text("module Nothing:\n    pass\n")
    assert guard.main(["--ato", str(p)]) == guard.EXIT_GATE_ERROR
