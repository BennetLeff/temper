"""Tests for firmware/tools/board_derivation_lib.py (plan 2026-08-02-027, U1).

Pins the SHARED derivation arithmetic -- the formula library used by BOTH
``scripts/check_pll_range_consistency.py`` and
``scripts/check_firmware_board_contract.py`` -- to hand-computed reference
vectors, so a bug in the formula cannot make both consumers agree with it.

Reference vectors (hand-derived, from the committed declarations):

PLL floor, as-committed (elec/src/main.ato):
    L_loaded(worst) = 88uH * (1 - 0.10) * 0.68       = 53.856uH
    C(worst)        = 300nF * (1 - 0.10)             = 270nF
    f_res,loaded    = 1/(2*pi*sqrt(53.856uH*270nF))  = 41.737kHz
    required floor  = 1.05 * 41.737kHz               = 43.824kHz
    round-kHz floor = 44000  (PLL_MIN_FREQ_HZ)

MAX31865 words, as-committed (firmware/config.yaml, RREF 430 ohm):
    low  (10 ohm):  ceil(10/430 * 2^15)     = 763  -> word 1526
    high (300 ohm): floor(300/430 * 2^15)   = 22861 -> word 45722
"""

from __future__ import annotations

import pytest
from board_derivation_lib import (
    ZVS_MARGIN_MIN,
    max31865_high_threshold_word,
    max31865_low_threshold_word,
    parse_si_value,
    pll_min_freq_floor,
    pll_min_freq_hz,
    round_up_to_khz,
)


class TestPllFloorHappyPath:
    def test_derives_the_documented_44khz_floor_from_declared_inputs(self) -> None:
        """U1 test scenario 1: re-derived from the declared inputs (88uH,
        300nF, ratio 0.68, both +/-10%) the floor is 43.824kHz and the
        round-kHz firmware value is 44000."""
        floor = pll_min_freq_floor(
            l_nominal_h=88e-6,
            c_nominal_farads=300e-9,
            loaded_ratio=0.68,
            l_tolerance=0.10,
            c_tolerance=0.10,
        )
        assert floor.l_loaded_worst_case_h == pytest.approx(53.856e-6)
        assert floor.c_worst_case_farads == pytest.approx(270e-9)
        assert floor.f_res_worst_case_hz == pytest.approx(41737.0, rel=1e-4)
        assert floor.required_floor_hz == pytest.approx(43824.0, rel=1e-4)
        assert pll_min_freq_hz(floor) == 44000

    def test_round_up_to_khz(self) -> None:
        assert round_up_to_khz(43823.85) == 44000
        assert round_up_to_khz(44000.0) == 44000
        assert round_up_to_khz(41737.0) == 42000
        assert round_up_to_khz(0.0) == 0

    def test_zvs_margin_constant_matches_the_documented_value(self) -> None:
        assert ZVS_MARGIN_MIN == 1.05

    def test_floor_keys_off_worst_case_both_components(self) -> None:
        """f_res ~ 1/sqrt(LC): minimum L AND minimum C must give the
        highest resonance / highest floor -- not nominal for either."""
        floor = pll_min_freq_floor(
            l_nominal_h=88e-6,
            c_nominal_farads=300e-9,
            loaded_ratio=0.68,
            l_tolerance=0.10,
            c_tolerance=0.10,
        )
        assert floor.f_res_worst_case_hz > floor.f_res_nominal_hz
        assert floor.c_worst_case_farads < floor.c_nominal_farads
        assert floor.l_worst_case_h < floor.l_nominal_h


class TestPllFloorIntermediates:
    def test_intermediates_exposed_for_attribution(self) -> None:
        """U1 test scenario 3: every intermediate quantity is on the
        result object, so a derivation change is attributable."""
        floor = pll_min_freq_floor(
            l_nominal_h=88e-6,
            c_nominal_farads=300e-9,
            loaded_ratio=0.68,
            l_tolerance=0.10,
            c_tolerance=0.10,
        )
        assert floor.l_nominal_h == pytest.approx(88e-6)
        assert floor.l_worst_case_h == pytest.approx(79.2e-6)
        assert floor.l_loaded_worst_case_h == pytest.approx(53.856e-6)
        assert floor.c_nominal_farads == pytest.approx(300e-9)
        assert floor.c_worst_case_farads == pytest.approx(270e-9)
        assert floor.loaded_ratio == 0.68
        assert floor.l_tolerance == 0.10
        assert floor.c_tolerance == 0.10
        assert floor.zvs_margin == 1.05

    def test_missing_a_capacitor_raises_the_floor(self) -> None:
        """One tank cap absent: C drops 300nF -> 200nF, worst-case C 270nF
        -> 180nF, and the required floor rises to ~53.7kHz -- above the
        committed 44kHz. This is the defect the oracle catches."""
        floor = pll_min_freq_floor(
            l_nominal_h=88e-6,
            c_nominal_farads=200e-9,
            loaded_ratio=0.68,
            l_tolerance=0.10,
            c_tolerance=0.10,
        )
        assert floor.required_floor_hz == pytest.approx(53673.0, rel=1e-4)
        assert pll_min_freq_hz(floor) == 54000


class TestPllFloorValidation:
    @pytest.mark.parametrize(
        "kwargs",
        [
            {"l_nominal_h": 0.0},
            {"c_nominal_farads": -1e-9},
            {"loaded_ratio": 0.0},
            {"loaded_ratio": 1.5},
            {"l_tolerance": 1.0},
            {"c_tolerance": -0.1},
            {"zvs_margin": 1.0},
        ],
    )
    def test_invalid_inputs_raise_value_error(self, kwargs) -> None:
        base = {
            "l_nominal_h": 88e-6,
            "c_nominal_farads": 300e-9,
            "loaded_ratio": 0.68,
            "l_tolerance": 0.10,
            "c_tolerance": 0.10,
        }
        base.update(kwargs)
        with pytest.raises(ValueError):
            pll_min_freq_floor(**base)


class TestMax31865HappyPath:
    def test_words_reproduce_the_committed_values(self) -> None:
        """U1 test scenario 2: a 430 ohm reference resistor and the 10 /
        300 ohm PT100 boundaries reproduce the committed threshold words."""
        assert max31865_low_threshold_word(10.0, 430.0) == 1526
        assert max31865_high_threshold_word(300.0, 430.0) == 45722

    def test_words_are_the_left_shifted_15_bit_code(self) -> None:
        """Register words are the 15-bit ratiometric code shifted left
        one bit: low 763 -> 1526, high 22861 -> 45722."""
        assert max31865_low_threshold_word(10.0, 430.0) == 763 << 1
        assert max31865_high_threshold_word(300.0, 430.0) == 22861 << 1

    def test_asymmetric_rounding_is_pinned(self) -> None:
        """Low rounds UP (smallest code strictly above the boundary, so
        AT-or-below trips); high rounds DOWN (largest code at-or-below
        the boundary, so AT-or-above trips). A single shared rounding
        choice would disagree with one of the committed words."""
        # If both rounded the same way, one of these would differ:
        assert max31865_low_threshold_word(10.0, 430.0) == 1526  # ceil
        assert max31865_high_threshold_word(300.0, 430.0) == 45722  # floor

    def test_reference_resistor_drift_moves_the_words(self) -> None:
        """A board whose RREF differs from 430 ohm must change both
        words -- the oracle's failure mode for a swapped reference."""
        low = max31865_low_threshold_word(10.0, 500.0)
        high = max31865_high_threshold_word(300.0, 500.0)
        assert low == 1312  # ceil(10/500*32768)=656 << 1
        assert high == 39320  # floor(300/500*32768)=19660 << 1
        assert low != 1526
        assert high != 45722

    def test_code_clamped_at_maximum(self) -> None:
        assert max31865_high_threshold_word(1e9, 1.0) == 32767 << 1


class TestMax31865Validation:
    def test_non_positive_r_ref_raises(self) -> None:
        with pytest.raises(ValueError):
            max31865_low_threshold_word(10.0, 0.0)

    def test_negative_rtd_raises(self) -> None:
        with pytest.raises(ValueError):
            max31865_high_threshold_word(-1.0, 430.0)


class TestParseSiValue:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("100nF", 100e-9),
            ("300nF", 300e-9),
            ("1uF", 1e-6),
            ("2.2uF", 2.2e-6),
            ("88uH", 88e-6),
            ("1.5mH", 1.5e-3),
            ("430ohm", 430.0),
            ("3.24kohm", 3240.0),
            ("1Mohm", 1e6),
            ("10Ω", 10.0),
            ("47kHz", 47000.0),
            ("0.03MHz", 30000.0),
        ],
    )
    def test_parses_si_values(self, text, expected) -> None:
        assert parse_si_value(text) == pytest.approx(expected)

    @pytest.mark.parametrize("bad", ["?", "", "TBD", "100", "10%", "100nF +/- 5%", None, 42])
    def test_unparseable_values_return_none(self, bad) -> None:
        assert parse_si_value(bad) is None
