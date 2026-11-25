"""C51: food-probe RTD, bay NTC and face-fan checks, with mutations of the frozen netlist.
Run: python3 -m unittest tests.test_c51 -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

UNIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(UNIT / "tools"))
sys.path.insert(0, str(UNIT / "tests"))

import controller_calcs as cc  # noqa: E402
import verify_controller as vc  # noqa: E402
import test_verify_mutations as tvm  # noqa: E402  (not the class: unittest would re-run its 10 min suite)

FROZEN, drop_node, move_node = tvm.FROZEN, tvm.drop_node, tvm.move_node


class C51(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = (FROZEN / "default.net").read_text()
        cls.nl = tvm.Mutations.load(cls.base)

    def failed(self, text: str) -> list[str]:
        rep = vc.Report()
        vc.check_c51(rep, tvm.Mutations.load(text))
        return rep.failed

    def mutate(self, want: str, text: str):
        self.assertIn("c51." + want, self.failed(text))

    def ref(self, path):
        return self.nl.ref_of(path)

    def test_baseline(self):
        self.assertEqual(self.failed(self.base), [])

    def test_food_spi_resistor_bypassed(self):
        self.mutate("food_spi_behind_1k", move_node(self.base, "U50", "17", "RTD_SDO"))

    def test_food_on_the_pan_supply(self):
        self.mutate("food_supply_is_its_own_bead", move_node(self.base, "U50", "3", "RTD_AVDD"))

    def test_food_cs_without_pullup(self):
        self.mutate("food_cs_p06_pulled_up", drop_node(self.base, self.ref("rtd_food.r_cs_pu"), "1"))

    def test_food_drdy_off_the_expander(self):
        self.mutate("food_drdy_p05", drop_node(self.base, "U50", "1"))

    def test_food_channel_touching_the_trip_chain(self):
        self.mutate("food_shares_only_listed_nets", move_node(self.base, "U50", "11", "rtd_sense_n"))

    def test_j9_pin_without_tvs(self):
        self.mutate("j9_2_cap_and_clamp", drop_node(self.base, self.ref("rtd_food.d_sp"), "3"))

    def test_j9_clamp_reversed(self):
        ref = self.ref("rtd_food.d_sp")
        self.mutate("j9_2_cap_and_clamp", move_node(self.base, ref, "1", "RTD2_AVDD"))

    def test_food_avdd_without_bulk(self):
        self.mutate("food_avdd_esd_bulk", drop_node(self.base, self.ref("rtd_food.c_avdd_bulk"), "1"))

    def test_food_tvs_leakage_would_fail(self):
        self.assertTrue(cc.rtd_food()["checks"]["pin_leakage_le_0p35K"])
        self.assertFalse(cc.rtd_food(leak_a=0.5e-6)["checks"]["pin_leakage_le_0p35K"])

    def test_bay_ntc_off_gpio8(self):
        self.mutate("bay_ntc_on_gpio8", move_node(self.base, "U4", "12", "COIL_ADC"))

    def test_fan_pwm_cascode_gate_grounded(self):
        self.mutate("fan2_pwm_cascode", move_node(self.base, self.ref("bay_fan.q_pwm"), "1", "selv_gnd"))

    def test_fan_pwm_straight_to_the_connector(self):
        self.mutate("fan2_pwm_cascode", move_node(self.base, "U52", "5", "J15_PWM"))

    def test_fan_controller_off_the_bus(self):
        self.mutate("fan2_on_internal_i2c", drop_node(self.base, "U52", "1"))

    def test_j15_pins_swapped(self):
        self.mutate("j15_pin_map", move_node(self.base, "J15", "2", "J15_PWM"))

    def test_fan_buck_on_the_logic_rail(self):
        self.mutate("fan2_buck_12v_from_v15_blw", move_node(self.base, "U51", "3", "v15_selv"))

    def test_ps3_mpm65_is_not_enough(self):
        self.assertFalse(cc.ps3_c51("MPM-65-15ST")["fits"])
        self.assertTrue(cc.ps3_c51("MPM-90-15ST")["fits"])

    def test_bay_divider_tells_open_from_cold(self):
        b = cc.bay_ntc()
        self.assertTrue(all(b["checks"].values()), b["checks"])
        self.assertFalse(all(cc.bay_ntc(rpu=10e3)["checks"].values()))

    def test_food_rtd_settles_inside_the_firmware_cycle(self):
        self.assertTrue(all(cc.rtd_food()["checks"].values()), cc.rtd_food()["checks"])
        self.assertFalse(cc.rtd_food(c_entry=220e-9)["checks"]["five_tau_le_5p5ms"])


class FoodUnplug(unittest.TestCase):
    """Unplug and single-open-lead transients of the J9 network (review 2026-11-25, catch 2)."""
    @classmethod
    def setUpClass(cls):
        cls.d = cc.rtd_food_unplug()

    def test_steady_state_plugged_matches_the_ratio_model(self):
        want = cc.rtd_food()["rows"]["100"]["code_ratio"]
        self.assertAlmostEqual(self.d["cases"]["plugged"]["final_ratio"], want, delta=2e-3)

    def test_full_unplug_trips_refin_high_fast(self):
        self.assertLess(self.d["cases"]["unplug"]["refin_high_ms"], 5.5)

    def test_full_unplug_conversion_is_not_a_reading(self):
        c = self.d["cases"]["unplug"]
        self.assertLess(c["ref_V_at_500ms"], 0.01)          # no reference current: the code carries no temperature

    def test_single_open_sense_leads_trip_the_window(self):
        for k in ("open_sense_p", "open_sense_n"):
            self.assertIsNotNone(self.d["cases"][k]["window_trip_ms"], k)
            self.assertGreater(self.d["cases"][k]["window_trip_ms"], 5.5, k)   # slower than the fault cycle's step

    def test_leaky_clamp_can_hide_an_open_sense_lead(self):
        self.assertLess(self.d["leak_hides_open_uA"], 2.0)
        self.assertTrue(self.d["checks"]["clamp_leak_below_hiding_level"])
        self.assertFalse(cc.rtd_food_unplug(leak_a=5e-6)["checks"]["clamp_leak_below_hiding_level"])



if __name__ == "__main__":
    unittest.main()
