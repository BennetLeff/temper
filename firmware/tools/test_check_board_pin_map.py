"""Tests for firmware/tools/check_board_pin_map.py (zapote/controller pin map).

The committed temper_pins.h must pass, and each class of disagreement the gate
exists for must fail: a pin on the wrong GPIO, a wired pin firmware does not
name, an untagged define, a GPIO claimed for a net the board puts on the
expander, hard-coded GPIO numbers, a mis-bound ADC channel, and a second WDI or
RUN_EN writer.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import check_board_pin_map as gate  # noqa: E402

ROOT = gate.REPO_ROOT
SNAPSHOT = json.loads((ROOT / gate.SNAPSHOT_REL).read_text(encoding="utf-8"))
PINS = (ROOT / gate.PINS_H_REL).read_text(encoding="utf-8")
SOURCES = gate._load_sources(ROOT)


def _errs(pins: str = PINS, sources: dict[str, str] | None = None) -> list[str]:
    return gate.check(SNAPSHOT, pins, SOURCES if sources is None else sources)


def _replace_define(pins: str, name: str, value: str) -> str:
    out, n = re.subn(rf"(#define\s+{name}\s+)\S+", rf"\g<1>{value}", pins, count=1)
    assert n == 1, name
    return out


def test_committed_pin_map_passes():
    assert _errs() == []


def test_main_exits_zero():
    assert gate.main([]) == gate.EXIT_OK


def test_known_board_facts():
    gpio = SNAPSHOT["gpio"]
    assert gpio["3"] == "FAN_TACH"          # not the heatsink NTC (item 13)
    assert gpio["6"] == "HS_ADC"
    assert gpio["9"] == "RIM_ADC"           # not RTD DRDY (D-RIM pin-header note)
    assert gpio["14"] == "RUN_EN"
    assert gpio["18"] == "IL_WDI"
    assert SNAPSHOT["expander"]["P07"] == "RTD_DRDY"
    assert "RTD_DRDY" not in gpio.values()


def test_wrong_gpio_fails():
    errs = _errs(_replace_define(PINS, "PIN_RUN_EN", "15"))
    assert any("PIN_RUN_EN = GPIO15 tagged RUN_EN" in e and "pwm_hb_mcu" in e for e in errs)


def test_legacy_heatsink_channel_fails():
    errs = _errs(_replace_define(PINS, "ADC_CH_HS_NTC", "2"))
    assert any("ADC_CH_HS_NTC = ADC1_CH2 (GPIO3)" in e and "FAN_TACH" in e for e in errs)


def test_drdy_on_gpio9_fails():
    pins = PINS.replace(
        "#define PIN_RTD_DRDY            HAL_PIN_INVALID /**< @not-gpio RTD_DRDY */",
        "#define PIN_RTD_DRDY            9   /**< @net RTD_DRDY */",
    )
    assert pins != PINS
    errs = _errs(pins)
    assert any("GPIO9 tagged RTD_DRDY" in e and "RIM_ADC" in e for e in errs)


def test_not_gpio_needs_invalid_pin():
    pins = PINS.replace("HAL_PIN_INVALID /**< @not-gpio", "9 /**< @not-gpio")
    assert any("must be HAL_PIN_INVALID" in e for e in _errs(pins))


def test_missing_define_fails():
    pins = "\n".join(l for l in PINS.splitlines() if "PIN_IL_WDI" not in l)
    errs = _errs(pins)
    assert any("GPIO18 to IL_WDI; no @net define" in e for e in errs)


def test_missing_expander_define_fails():
    pins = "\n".join(l for l in PINS.splitlines() if "EXP_SUP_RUN_OK_RB" not in l)
    assert any("P14 to SUP_RUN_OK_RB; no @exp define" in e for e in _errs(pins))


def test_wrong_expander_pin_fails():
    errs = _errs(_replace_define(PINS, "EXP_RTD_DRDY", "6"))
    assert any("P06" in e and "RTD_DRDY is P07" in e for e in errs)


def test_untagged_define_fails():
    pins = PINS + "\n#define PIN_SPARE 2\n"
    assert any("PIN_SPARE needs exactly one" in e for e in _errs(pins))


def test_host_mock_must_not_be_a_pad():
    pins = PINS.replace("63  /**< @host-mock */", "9  /**< @host-mock */")
    assert pins != PINS
    assert any("@host-mock value must be > 48" in e for e in _errs(pins))


def test_hardcoded_gpio_num_fails():
    sources = dict(SOURCES)
    rel = "firmware/components/safety/safety.h"
    sources[rel] += "\n#define WDI_GPIO_NUM GPIO_NUM_7\n"
    assert any(e.startswith(f"{rel}:") and "GPIO_NUM_7" in e for e in _errs(sources=sources))


def test_gpio_num_in_comment_is_ignored():
    sources = dict(SOURCES)
    sources["firmware/main/main.c"] += "\n/* legacy: WDI was GPIO_NUM_7 */\n"
    assert _errs(sources=sources) == []


def test_adc_consumer_mismatch_fails():
    sources = dict(SOURCES)
    rel = "firmware/components/sensors/hs_ntc_board.c"
    sources[rel] = re.sub(r"\(\(hal_adc_channel_t\)5\)", "((hal_adc_channel_t)2)", sources[rel])
    assert any(e.startswith(rel) and "HS_ADC is on GPIO6" in e for e in _errs(sources=sources))


@pytest.mark.parametrize(
    "rel,line",
    [
        ("firmware/main/state_machine.c", "\nvoid x(void) { watchdog_hardware_write_wdi(true); }\n"),
        ("firmware/main/state_handlers.c", "\nstatic int x = PIN_IL_WDI;\n"),
        ("firmware/main/board_peripherals.c", "\nstatic int y = PIN_RUN_EN;\n"),
    ],
)
def test_second_wdi_or_run_en_writer_fails(rel, line):
    sources = dict(SOURCES)
    sources[rel] += line
    assert any(e.startswith(f"{rel}:") and "is used only in" in e for e in _errs(sources=sources))


def test_strip_c_comments_keeps_lines_and_strings():
    text = 'a /* x\ny */ b // z\n"/* not */" c\n'
    out = gate.strip_c_comments(text)
    assert out.count("\n") == text.count("\n")
    assert "x" not in out and "z" not in out
    assert '"/* not */"' in out


def _board_ref_available() -> bool:
    return (
        subprocess.run(
            ["git", "cat-file", "-e", f"{gate.DEFAULT_BOARD_REF}^{{commit}}"],
            cwd=ROOT,
            capture_output=True,
        ).returncode
        == 0
    )


@pytest.mark.skipif(not _board_ref_available(), reason="board commit not in this clone")
def test_snapshot_rederives_from_board():
    fresh = gate.derive(gate.DEFAULT_BOARD_REF)
    assert gate._board_content(fresh) == gate._board_content(SNAPSHOT)
