"""Differential tests: Rust RTD safety core vs the pure-Python reference
(temper_thermal.rtd vs temper_placer.validation.rtd_safety).

The pre-migration implementations are pinned here as oracles (verbatim
semantics, including floor/ceil rounding and the derivation arithmetic
order).  Any change to the Rust core or the delegation that disagrees
with the oracle fails here, bit-exactly.
"""

from __future__ import annotations

import random
from math import ceil, floor

import pytest

from temper_placer.validation.rtd_safety import (
    Max31865RtdWindowCorners,
    RtdWindowCorners,
    derive_hardware_window,
    derive_max31865_hardware_window,
    hardware_window_voltage,
    max31865_rtd_current_a,
    max31865_rtd_voltage_v,
    reference_divider_voltage_v,
    resistance_to_code,
    spi_rc_rise_time_ns,
    threshold_adc_codes,
)

ADC_FULL_SCALE = 1 << 15


def _oracle_resistance_to_code(resistance_ohm, rref_ohm):
    if resistance_ohm <= 0.0:
        return 0
    return min(ADC_FULL_SCALE - 1, floor(ADC_FULL_SCALE * resistance_ohm / rref_ohm))


def _oracle_threshold_adc_codes(rref_ohm, short_ohm, open_ohm):
    low = ceil(ADC_FULL_SCALE * short_ohm / rref_ohm)
    high = floor(ADC_FULL_SCALE * open_ohm / rref_ohm)
    return low, high


def _oracle_derive_window(corners: RtdWindowCorners):
    current_min = corners.bias_current_min_a
    current_max = corners.bias_current_max_a
    offset = corners.comparator_offset_abs_v
    divider_low = 1.0 - corners.divider_tolerance_fraction
    divider_high = 1.0 + corners.divider_tolerance_fraction
    margin = 1.0 + corners.required_margin_fraction
    short_voltage_max = corners.short_max_ohm * current_max
    valid_voltage_min = corners.valid_min_ohm * current_min
    valid_voltage_max = corners.valid_max_ohm * current_max
    open_voltage_min = corners.open_min_ohm * current_min
    low_min = (short_voltage_max + offset) / divider_low
    low_max = (valid_voltage_min / margin - offset) / divider_high
    high_min = (valid_voltage_max * margin + offset) / divider_low
    high_max = (open_voltage_min - offset) / divider_high
    return (low_min, low_max, high_min, high_max)


def _oracle_derive_max31865(corners: Max31865RtdWindowCorners):
    rref_min = corners.rref_nominal_ohm * (1.0 - corners.rref_tolerance_fraction)
    rref_max = corners.rref_nominal_ohm * (1.0 + corners.rref_tolerance_fraction)
    offset = corners.comparator_offset_abs_v
    divider_low = 1.0 - corners.divider_tolerance_fraction
    divider_high = 1.0 + corners.divider_tolerance_fraction
    margin = 1.0 + corners.required_margin_fraction
    v = lambda r, vb, rr: r * (vb / (rr + r))  # max31865_rtd_voltage_v semantics
    short_voltage_max = v(corners.short_max_ohm, corners.vbias_max_v, rref_min)
    valid_voltage_min = v(corners.valid_min_ohm, corners.vbias_min_v, rref_max)
    valid_voltage_max = v(corners.valid_max_ohm, corners.vbias_max_v, rref_min)
    open_voltage_min = v(corners.open_min_ohm, corners.vbias_min_v, rref_max)
    low_min = (short_voltage_max + offset) / divider_low
    low_max = (valid_voltage_min / margin - offset) / divider_high
    high_min = (valid_voltage_max * margin + offset) / divider_low
    high_max = (open_voltage_min - offset) / divider_high
    return (low_min, low_max, high_min, high_max)


def test_resistance_to_code_matches_oracle():
    rng = random.Random(20260731)
    for _ in range(1000):
        r = rng.uniform(0.0, 500.0)
        rref = rng.uniform(100.0, 1000.0)
        assert resistance_to_code(r, rref) == _oracle_resistance_to_code(r, rref)


def test_threshold_adc_codes_matches_oracle():
    rng = random.Random(3)
    for _ in range(500):
        rref = rng.uniform(100.0, 1000.0)
        short = rng.uniform(1.0, 50.0)
        open_ = rng.uniform(100.0, 500.0)
        assert threshold_adc_codes(rref_ohm=rref, short_ohm=short, open_ohm=open_) == (
            _oracle_threshold_adc_codes(rref, short, open_)
        )


def test_voltage_functions_match_oracle():
    rng = random.Random(5)
    for _ in range(500):
        r = rng.uniform(0.0, 500.0)
        vbias = rng.uniform(1.5, 2.5)
        rref = rng.uniform(100.0, 1000.0)
        exc = rng.uniform(0.0, 0.005)
        # Module semantics: current = vbias/(rref+r); voltage = r * current
        # (two ops — NOT (r*vbias)/(rref+r)).
        assert max31865_rtd_current_a(r, vbias_v=vbias, rref_ohm=rref) == vbias / (rref + r)
        assert max31865_rtd_voltage_v(r, vbias_v=vbias, rref_ohm=rref) == r * (vbias / (rref + r))
        assert hardware_window_voltage(r, exc) == r * exc


def test_reference_divider_and_spi_match_oracle():
    rng = random.Random(7)
    for _ in range(500):
        ref = rng.uniform(0.5, 2.5)
        top = rng.uniform(100.0, 200_000.0)
        bottom = rng.uniform(100.0, 200_000.0)
        assert reference_divider_voltage_v(reference_v=ref, top_ohm=top, bottom_ohm=bottom) == (
            ref * bottom / (top + bottom)
        )
        rout = rng.uniform(1.0, 100.0)
        rser = rng.uniform(1.0, 100.0)
        cap = rng.uniform(1.0, 100.0)
        assert spi_rc_rise_time_ns(
            driver_output_ohm=rout, series_resistor_ohm=rser, load_capacitance_pf=cap
        ) == (2.2 * (rout + rser) * cap / 1000.0)


def test_derive_hardware_window_matches_oracle():
    rng = random.Random(11)
    for _ in range(300):
        lo = rng.uniform(0.0005, 0.002)
        corners = RtdWindowCorners(
            bias_current_min_a=lo,
            bias_current_max_a=rng.uniform(lo, 0.002),
            comparator_offset_abs_v=rng.uniform(0.0, 0.01),
            divider_tolerance_fraction=rng.uniform(0.0, 0.02),
            short_max_ohm=10.0,
            valid_min_ohm=rng.uniform(50.0, 120.0),
            valid_max_ohm=rng.uniform(150.0, 250.0),
            open_min_ohm=300.0,
            required_margin_fraction=rng.uniform(0.0, 0.3),
        )
        expect = _oracle_derive_window(corners)
        # If the oracle bounds overlap, the derivation must raise; the Rust
        # status code must agree.
        if expect[0] > expect[1] or expect[2] > expect[3]:
            with pytest.raises(ValueError):
                derive_hardware_window(corners)
            continue
        got = derive_hardware_window(corners)
        assert got.low_trip_voltage_v == (expect[0] + expect[1]) / 2.0
        assert got.high_trip_voltage_v == (expect[2] + expect[3]) / 2.0


def test_derive_max31865_hardware_window_matches_oracle():
    rng = random.Random(13)
    for _ in range(300):
        corners = Max31865RtdWindowCorners(
            comparator_offset_abs_v=rng.uniform(0.0, 0.01),
            divider_tolerance_fraction=rng.uniform(0.0, 0.02),
            vbias_min_v=1.95,
            vbias_max_v=2.06,
            rref_nominal_ohm=430.0,
            rref_tolerance_fraction=0.001,
            short_max_ohm=10.0,
            valid_min_ohm=rng.uniform(50.0, 120.0),
            valid_max_ohm=rng.uniform(150.0, 250.0),
            open_min_ohm=300.0,
            required_margin_fraction=rng.uniform(0.0, 0.3),
        )
        expect = _oracle_derive_max31865(corners)
        if expect[0] > expect[1] or expect[2] > expect[3]:
            with pytest.raises(ValueError):
                derive_max31865_hardware_window(corners)
            continue
        got = derive_max31865_hardware_window(corners)
        assert got.low_trip_voltage_v == (expect[0] + expect[1]) / 2.0
        assert got.high_trip_voltage_v == (expect[2] + expect[3]) / 2.0
