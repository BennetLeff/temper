"""Transient safety-envelope contract for RTD faults and RTD_AVDD brownout."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "elec/validation/rtd_fault_latch_transient.cir.in"
MAX_RESPONSE_S = 100e-3


@dataclass(frozen=True)
class Scenario:
    name: str
    rtd_source: str
    avdd_source: str
    reset_source: str
    event_s: float
    tstep: str
    tstop: str
    tmeasure: str


SCENARIOS = (
    Scenario(
        "rtd_short_transition",
        "V_RTD rtd 0 PWL(0 0.50 1m 0.50 1.001m 0.10 5m 0.10)",
        "V_AVDD avdd 0 3.3",
        "V_RESET_N reset_n 0 3.3",
        1e-3,
        "10n",
        "5m",
        "4m",
    ),
    Scenario(
        "rtd_open_transition",
        "V_RTD rtd 0 PWL(0 0.50 1m 0.50 1.001m 1.00 5m 1.00)",
        "V_AVDD avdd 0 3.3",
        "V_RESET_N reset_n 0 3.3",
        1e-3,
        "10n",
        "5m",
        "4m",
    ),
    Scenario(
        "avdd_brownout_fast_ramp",
        "V_RTD rtd 0 0.50",
        "V_AVDD avdd 0 PWL(0 3.3 1m 3.3 1.001m 2.70 8m 2.70)",
        "V_RESET_N reset_n 0 3.3",
        1e-3,
        "1u",
        "8m",
        "7m",
    ),
    Scenario(
        "avdd_brownout_slow_ramp",
        "V_RTD rtd 0 0.50",
        "V_AVDD avdd 0 PWL(0 3.3 1m 3.3 11m 2.70 30m 2.70)",
        "V_RESET_N reset_n 0 3.3",
        1e-3,
        "10u",
        "31m",
        "30m",
    ),
    Scenario(
        "short_pulse_reset_cannot_clear_live_fault",
        "V_RTD rtd 0 PWL(0 0.50 1m 0.50 1.001m 0.10 2m 0.10 2.001m 0.50 5m 0.50)",
        "V_AVDD avdd 0 3.3",
        "V_RESET_N reset_n 0 PWL(0 3.3 1.5m 3.3 1.501m 0 1.8m 0 1.801m 3.3 5m 3.3)",
        1e-3,
        "10n",
        "5m",
        "4m",
    ),
)


def _seconds(value: str) -> float:
    """Convert ngspice's plain/scientific measurement output to seconds."""

    return float(value)


def _run_transient(tmp_path: Path, scenario: Scenario) -> tuple[float, float]:
    rendered = TEMPLATE.read_text(encoding="utf-8")
    rendered = rendered.replace("{{RTD_SOURCE}}", scenario.rtd_source)
    rendered = rendered.replace("{{AVDD_SOURCE}}", scenario.avdd_source)
    rendered = rendered.replace("{{RESET_SOURCE}}", scenario.reset_source)
    rendered = rendered.replace("{{TSTEP}}", scenario.tstep)
    rendered = rendered.replace("{{TSTOP}}", scenario.tstop)
    rendered = rendered.replace("{{TMEASURE}}", scenario.tmeasure)
    deck = tmp_path / f"{scenario.name}.cir"
    deck.write_text(rendered, encoding="utf-8")

    result = subprocess.run(
        ["ngspice", "-b", str(deck)], check=True, capture_output=True, text=True
    )
    timing = re.search(r"t_shutdown\s*=\s*([-+0-9.eE]+)", result.stdout)
    final = re.search(r"v_shutdown_end\s*=\s*([-+0-9.eE]+)", result.stdout)
    assert timing is not None, result.stdout
    assert final is not None, result.stdout
    return _seconds(timing.group(1)), float(final.group(1))


@pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice is required")
@pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda item: item.name)
def test_rtd_fault_or_brownout_latches_shutdown_within_100ms(
    tmp_path: Path, scenario: Scenario
) -> None:
    """Each RTD fault/brownout must reach active-high UCC DIS and stay latched."""

    t_shutdown, shutdown_end = _run_transient(tmp_path, scenario)

    assert t_shutdown >= scenario.event_s
    assert t_shutdown - scenario.event_s < MAX_RESPONSE_S
    assert shutdown_end > 2.5


def test_transient_timing_envelope_declares_conservative_source_parameters() -> None:
    """Keep all non-vendor timing assumptions conspicuous and reviewable."""

    deck = TEMPLATE.read_text(encoding="utf-8")
    assert "TLV_TPD_MAX=55n" in deck
    assert "HC00_TPD_MAX=23n" in deck
    assert "TPS3700_TPD_CONSERVATIVE=450u" in deck
    assert "C_LATCH latch_q 0 {LATCH_SET_US*1m/1.65}" in deck
    assert "set-dominant" in deck
    assert "UCC21550 DIS" in deck
