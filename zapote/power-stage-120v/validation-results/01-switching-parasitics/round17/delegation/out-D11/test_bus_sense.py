"""Arithmetic acceptance tests for the D-11 proposal, not circuit qualification."""
from __future__ import annotations

import unittest
from unittest.mock import patch

import bus_sense as sense


class BusSenseTests(unittest.TestCase):
    def test_nominal_divider_includes_bottom_resistor(self) -> None:
        self.assertAlmostEqual(sense.K * 239.9746835443038, 2.0)
        self.assertAlmostEqual(2.5 * 140 / 150 / sense.K, 279.97046413502113)

    def test_receiver_retains_common_mode_error(self) -> None:
        # Four independent resistors need a common-mode error budget, even at zero.
        lo, hi = sense.receiver_interval(0, sense.CORNERS[0])
        self.assertLess(lo, .25)
        self.assertGreater(hi, .25)
        self.assertGreater(hi-lo, .002)

    def test_no_linear_accuracy_claim_above_endpoint(self) -> None:
        for c in sense.CORNERS:
            self.assertIsNotNone(sense.measurement(198, c)["max_abs_error_v_if_linear"])
            for vbus in (240, 260, 280):
                with self.subTest(profile=c.name, bus=vbus):
                    self.assertIsNone(sense.measurement(vbus, c)["max_abs_error_v_if_linear"])

    def test_negative_leakage_uses_largest_gain_at_zero(self) -> None:
        c = sense.CORNERS[1]
        _, _, rth = sense.divider(c)
        vin = -(c.amc_bias+c.u7_bias)*rth
        diff = vin*(1+c.amc_gain)-c.amc_offset-.0008
        expected = sense.receiver_interval(diff, c)[0]-sense.ADC_ERROR
        self.assertAlmostEqual(sense.measurement(0, c)["adc_interval_v_if_linear"][0], expected)

    def test_guard_crossings_and_zero_fault_separation(self) -> None:
        result = sense.calculations()
        for c in sense.CORNERS:
            p = result["profiles"][c.name]
            self.assertTrue(p["normal_198V_no_false_overrange_under_assumptions"])
            self.assertGreater(p["adc_min_at_vin_2_v"], sense.OVERRANGE_ADC)
            self.assertGreater(p["zero_adc_interval_v"][0], .100)
            early, late = p["overrange_threshold_bus_crossing_v"]
            self.assertLess(early, late)
            self.assertLess(late, p["ovp_expanded_partial_stack_v"][0])
            # The old fixed upper-search limit of 235 V must not truncate the late endpoint.
            self.assertGreater(late, 235)

    def test_threshold_above_linear_limit_is_rejected(self) -> None:
        with patch.object(sense, "OVERRANGE_ADC", 1.300):
            with self.assertRaises(AssertionError):
                sense.calculations()


if __name__ == "__main__":
    unittest.main()
