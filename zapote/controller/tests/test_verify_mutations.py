"""Mutation tests: each deliberate miswire of the frozen netlist must fail the
check that owns it. Run: python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

UNIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(UNIT / "tools"))

import verify_controller as vc  # noqa: E402
from netlist import attach_resolved, read_netlist  # noqa: E402

FROZEN = UNIT / "frozen"
N21 = UNIT / "inputs/native-21"
CALCS = json.loads((UNIT / "evidence/controller_calcs.json").read_text())


def node(ref: str, pin: str) -> str:
    return f'(node (ref "{ref}") (pin "{pin}") (pintype "stereo"))'


def move_node(text: str, ref: str, pin: str, to_net: str) -> str:
    """Detach (ref, pin) from its net and attach it to ``to_net``."""
    line_re = re.compile(r"\n\s*" + re.escape(node(ref, pin)))
    assert line_re.search(text), (ref, pin)
    text = line_re.sub("", text, count=1)
    head = re.compile(r'(\(net \(code "\d+"\) \(name "' + re.escape(to_net) + r'"\))')
    assert head.search(text), to_net
    return head.sub(lambda m: m.group(1) + "\n      " + node(ref, pin), text, count=1)


def add_node(text: str, ref: str, pin: str, to_net: str) -> str:
    head = re.compile(r'(\(net \(code "\d+"\) \(name "' + re.escape(to_net) + r'"\))')
    return head.sub(lambda m: m.group(1) + "\n      " + node(ref, pin), text, count=1)


def drop_node(text: str, ref: str, pin: str) -> str:
    return re.sub(r"\n\s*" + re.escape(node(ref, pin)), "", text, count=1)


class Mutations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = (FROZEN / "default.net").read_text()
        cls.n21 = attach_resolved(read_netlist(N21 / "default.net"), N21 / "resolved-components.json")
        cls.base_nl = cls.load(cls.base)

    def ref(self, path: str) -> str:
        return self.base_nl.ref_of(path)

    @staticmethod
    def load(text: str):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "default.net"
            p.write_text(text)
            return attach_resolved(read_netlist(p), FROZEN / "resolved-components.json")

    def run_checks(self, text: str) -> list[str]:
        nl = self.load(text)
        rep = vc.Report()
        for fn in (lambda: vc.check_j4(rep, nl, self.n21), lambda: vc.check_adc1(rep, nl, CALCS),
                   lambda: vc.check_trip(rep, nl, CALCS), lambda: vc.check_misc(rep, nl),
                   lambda: vc.check_ct_rms(rep, nl, CALCS), lambda: vc.check_ui_bus(rep, nl, CALCS), lambda: vc.check_blower(rep, nl, CALCS),
                   lambda: vc.check_v3v3(rep, nl, self.n21, CALCS), lambda: vc.check_blwin(rep, nl, CALCS),
                   lambda: vc.check_sensor_io(rep, nl), lambda: vc.check_capmode(rep, nl, CALCS)):
            fn()
        return rep.failed

    def test_baseline_passes(self):
        self.assertEqual(self.run_checks(self.base), [])

    def test_j4_pin_swap_fails(self):
        t = move_node(self.base, "J4", "5", "pwm_la")
        t = move_node(t, "J4", "6", "pwm_ha")
        self.assertTrue(any(f.startswith("j4.pin5") for f in self.run_checks(t)))

    def test_permit_on_gpio_fails(self):
        t = add_node(self.base, "U4", "29", "permit")           # GPIO36 straight onto PERMIT
        failed = self.run_checks(t)
        self.assertIn("j4.pin9_permit_is_latch_and_run_en_gate", failed)

    def test_wdi_into_trip_cone_fails(self):
        inv = self.ref("interlock.control_inv")
        t = move_node(self.base, inv, "9", "IL_WDI")            # interlock SENSOR_LIVE input fed by GPIO18
        self.assertIn("trip.only_firmware_inputs_are_reset_request_and_run_en", self.run_checks(t))

    def test_run_en_alone_asserting_permit_fails(self):
        gate = self.ref("u_permit")
        t = move_node(self.base, gate, "1", "RUN_EN")           # gate A off the latch: PERMIT = RUN_EN
        failed = self.run_checks(t)
        self.assertIn("trip.run_en_alone_cannot_assert_permit", failed)
        self.assertIn("trip.every_specified_source_reaches_permit", failed)   # the latch no longer gates it

    def test_run_en_into_latch_fails(self):
        latch = self.ref("interlock.latch")
        t = move_node(self.base, latch, "7", "RUN_EN")          # RUN_EN onto the latch's /PRE
        failed = self.run_checks(t)
        self.assertIn("trip.run_en_feeds_only_the_permit_gate", failed)

    def test_run_en_without_pulldown_fails(self):
        r = self.ref("r_run_en_pd")
        t = drop_node(self.base, r, "2")
        self.assertIn("trip.run_en_defaults_low_with_pulldown", self.run_checks(t))

    def test_run_en_pulled_up_fails(self):
        r = self.ref("r_run_en_pd")
        t = move_node(self.base, r, "2", "v3v3")
        self.assertIn("trip.run_en_defaults_low_with_pulldown", self.run_checks(t))

    def test_disconnected_heatsink_fault_fails(self):
        inv = self.ref("interlock.fault_inv")
        t = move_node(self.base, inv, "5", "selv_gnd")          # HS input tied healthy
        failed = self.run_checks(t)
        self.assertIn("trip.every_specified_source_reaches_permit", failed)

    def test_inverted_runaway_polarity_fails(self):
        comp = self.ref("u_runaway")
        t = move_node(self.base, comp, "3", "RUNAWAY_TH")
        window = self.base_nl.net_of(comp, "3")                # the RTDIN+ window node
        t = move_node(t, comp, "4", window)
        failed = self.run_checks(t)
        self.assertIn("trip.runaway_inp_observes_j3_sense_plus_via_window_branch", failed)
        self.assertIn("trip.runaway_inn_is_bias_divider_referenced_to_j3_sense_minus", failed)

    # ---- sensor-r3 CR-1..CR-6 (DECISIONS C37, C38, C40)
    def test_runaway_divider_back_on_gnd_fails(self):           # CR-3 regression
        t = move_node(self.base, self.ref("r_runaway_bot"), "2", "selv_gnd")
        self.assertIn("trip.runaway_inn_is_bias_divider_referenced_to_j3_sense_minus", self.run_checks(t))

    def test_window_branch_on_adc_side_fails(self):             # CR-2 regression
        t = move_node(self.base, self.ref("rtd_pan.r_window_sense_p"), "1", "rtd_sense_p")
        self.assertIn("trip.runaway_inp_observes_j3_sense_plus_via_window_branch", self.run_checks(t))

    def test_rtdin_bypassing_the_filter_fails(self):             # CR-1 regression
        t = move_node(self.base, self.ref("rtd_pan.adc"), "10", "rtd_sense_p_ext")
        self.assertIn("trip.rtdin_reaches_j3_through_two_stage_filter", self.run_checks(t))

    def test_rim_trip_polarity_swapped_fails(self):
        u = self.ref("u_rim_trip")
        t = move_node(self.base, u, "3", "rim_filt")
        t = move_node(t, u, "4", "RIM_TRIP_TH")
        failed = self.run_checks(t)
        self.assertIn("trip.rim_trip_inp_is_v3v3_divider", failed)
        self.assertIn("trip.rim_trip_inn_observes_rim_ntc_filter_node", failed)

    def test_rim_trip_not_ored_into_runaway_fails(self):        # CR-5 regression
        t = move_node(self.base, self.ref("u_runaway_or"), "2", "selv_gnd")
        self.assertIn("trip.every_specified_source_reaches_permit", self.run_checks(t))

    def test_j3_pin_without_tvs_fails(self):
        t = drop_node(self.base, self.ref("rtd_pan.d_j_sn"), "1")
        self.assertIn("sensor_io.j3_3_220nF_and_tvs_to_gnd", self.run_checks(t))

    def test_j12_drain_floating_fails(self):                     # CR-4 regression
        t = drop_node(self.base, self.ref("j_rim"), "3")
        self.assertIn("sensor_io.j12_rim_sense_return_and_drain", self.run_checks(t))

    def test_rim_tvs_vrwm_below_v3v3_fails(self):               # CR-6 regression
        nl = self.load(self.base)
        nl.mpn[nl.ref_of("d_rim")] = "ESD5Z3.3T1G"
        rep = vc.Report()
        vc.check_sensor_io(rep, nl)
        self.assertIn("sensor_io.rim_sense_tvs_vrwm_ge_v3v3_max", rep.failed)

    # ---- capacitive-mode detector (DECISIONS C39)
    def test_cap_fault_tied_off_fails(self):
        il = self.ref("interlock.fault_inv")
        t = move_node(self.base, il, "3", "selv_gnd")
        failed = self.run_checks(t)
        self.assertIn("capmode.cap_fault_enters_the_interlock_ovp_input", failed)
        self.assertIn("trip.every_specified_source_reaches_permit", failed)

    def test_cm_clocks_swapped_fails(self):
        ff = self.ref("u_cm_ff")
        t = move_node(self.base, ff, "3", "CM_CLK_LA")
        t = move_node(t, ff, "11", "CM_CLK_HA")
        failed = self.run_checks(t)
        self.assertIn("capmode.ff1_clock_is_the_inverted_ha_command", failed)
        self.assertIn("capmode.inductive_operation_never_faults_1_to_89_deg", failed)

    def test_cm_polarity_strap_removed_fails(self):
        t = drop_node(self.base, self.ref("r_cm_pol"), "2")
        failed = self.run_checks(t)
        self.assertIn("capmode.polarity_strap_fitted_0ohm_to_gnd_with_pullup_alternative", failed)
        self.assertIn("capmode.inductive_operation_never_faults_1_to_89_deg", failed)

    def test_cm_run_en_on_the_wrong_async_pin_fails(self):
        ff = self.ref("u_cm_ff")
        t = move_node(self.base, ff, "4", "v3v3")               # 1PRE released
        t = move_node(t, ff, "1", "RUN_EN")                      # RUN_EN onto 1CLR: holds 1Q-bar high
        failed = self.run_checks(t)
        self.assertIn("capmode.run_en_low_presets_ff1_and_clears_ff2", failed)
        self.assertIn("capmode.run_en_low_holds_healthy_from_the_fault_power_up_state", failed)

    def test_cm_d_from_mcu_gpio_fails(self):
        ff = self.ref("u_cm_ff")
        t = move_node(self.base, ff, "2", "CT_ZC_MCU" if "CT_ZC_MCU" in self.base else "ct_zc")
        self.assertIn("capmode.both_d_inputs_are_ct_zc_through_the_polarity_xor", self.run_checks(t))

    # ---- item 4 (DECISIONS C41)
    def test_en_on_a_harness_connector_fails(self):
        en = self.base_nl.net_of("U4", "3")
        t = move_node(self.base, "J12", "3", en)
        self.assertIn("misc.en_reaches_only_the_flush_debug_land", self.run_checks(t))

    def test_vbus_on_adc2_fails(self):
        r = self.ref("r_vbus_adc")
        t = move_node(self.base, "U4", "38", "RTD_SCK")        # GPIO2 off the ADC net
        t = move_node(t, "U4", "19", "VBUS_ADC")               # GPIO11 (ADC2) onto it
        failed = self.run_checks(t)
        self.assertIn("adc1.VBUS_ADC_on_one_adc1_gpio", failed)
        self.assertTrue(r)

    def test_missing_pwm_pulldown_fails(self):
        r = self.ref("rpd_pwm_hb")
        t = drop_node(self.base, r, "1")
        self.assertIn("j4.pwm_hb_pulldown_le_10k", self.run_checks(t))

    def test_bus_fault_without_pullup_fails(self):
        r = self.ref("interlock.ocp_pullup")
        t = drop_node(self.base, r, "2")
        self.assertIn("j4.pin10_bus_fault_into_interlock_ocp_with_pullup", self.run_checks(t))

    def test_rms_adc_input_disconnected_fails(self):
        adc = self.ref("u_adc")
        t = move_node(self.base, adc, "2", "selv_gnd")          # CH0 no longer sees the RMS output
        self.assertIn("ct_rms.rms_output_reaches_adc_ch0_through_series_r", self.run_checks(t))

    def test_rms_clamp_removed_fails(self):
        d = self.ref("d_rms_clamp")
        t = drop_node(self.base, d, "3")
        self.assertIn("ct_rms.adc_ch0_clamped_to_v3v3_and_gnd", self.run_checks(t))

    def test_rms_input_dc_coupled_fails(self):
        u = self.ref("u_rms")
        t = move_node(self.base, u, "6", self.base_nl.net_of(self.ref("u_buf1"), "1"))
        self.assertIn("ct_rms.rms_input_ac_coupled_from_ct_mon_buffer", self.run_checks(t))

    # ---- R33 J7 UI bus
    def test_j7_signal_straight_to_gpio_fails(self):
        t = move_node(self.base, "U4", "33", "J7_SCK")           # GPIO40 pad wired to the connector side
        self.assertIn("ui.J7_SCK_series_33_100_ohm_to_gpio40", self.run_checks(t))

    def test_j7_pin_swap_fails(self):
        t = move_node(self.base, "J7", "4", "selv_gnd")
        t = move_node(t, "J7", "5", "J7_SCK")
        self.assertIn("ui.j7_pin_map", self.run_checks(t))

    def test_j7_signal_without_gnd_neighbour_fails(self):
        t = move_node(self.base, "J7", "8", "v3v3")              # MISO (7) and CS_OLED (9) lose their GND
        failed = self.run_checks(t)
        self.assertIn("ui.every_j7_signal_beside_a_gnd", failed)

    def test_ui_bus_on_rtd_spi_fails(self):
        r = self.ref("rs_ui_sck")
        t = move_node(self.base, r, "1", "RTD_SCK")              # UI clock taken from the RTD/ADC bus
        self.assertIn("ui.ui_bus_separate_from_rtd_adc_spi", self.run_checks(t))

    def test_j7_esd_removed_fails(self):
        t = drop_node(self.base, self.ref("u_esd_ui1"), "1")
        self.assertIn("ui.J7_SCK_esd_clamped", self.run_checks(t))

    def test_ui_cs_pullup_removed_fails(self):
        t = drop_node(self.base, self.ref("r_cs_oled_pu"), "2")
        self.assertIn("ui.J7_CS_OLED_N_deselected_at_reset_pullup", self.run_checks(t))

    def test_unmodelled_part_on_v3v3_fails_closed(self):
        saved = vc.MODELS.pop("TLV9062IDR")
        try:
            with self.assertRaises(ValueError):
                vc.v3v3_load(self.base_nl, "controller", {})
        finally:
            vc.MODELS["TLV9062IDR"] = saved

    def test_rim_ntc_unbuffered_fails(self):
        u = self.ref("u_buf3")
        t = move_node(self.base, u, "1", "RIM_SENSE")          # follower output shorted onto its input node
        failed = self.run_checks(t)
        self.assertIn("adc1.RIM_ADC_driven_by_TLV9061IDBVR_buffer", failed)

    def test_strap_pullup_on_gpio46_fails(self):
        r = self.ref("r_fan_pwm_pd")
        t = move_node(self.base, r, "2", "v3v3")
        self.assertIn("misc.gpio46_reads_0_at_reset", self.run_checks(t))


    # ---- L3 thermal ladder (DECISIONS C32): restoring the old 120 C coil reference must fail
    def test_coil_trip_below_firmware_trip_fails(self):
        nl = self.load(self.base)
        nl.value[nl.ref_of("thermal.coil_top")] = "20kohm +/- 1%"
        nl.value[nl.ref_of("thermal.coil_bottom")] = "8.06kohm +/- 1%"
        rep = vc.Report()
        vc.check_thermal(rep, nl)
        self.assertIn("thermal.coil_trip_low_corner_above_fw_165", rep.failed)

    # ---- L3 blower and NTC-filter checks (DECISIONS C28/C29)
    def test_blower_pwm_pullup_breaks_full_speed_failsafe(self):
        t = add_node(self.base, self.ref("r_fan_pwm_pd"), "2", "v3v3")
        t = drop_node(t, self.ref("r_fan_pwm_pd"), "2")
        failed = self.run_checks(t)
        self.assertIn("blower.gpio46_low_at_reset_is_full_speed", failed)

    def test_fg_straight_to_gpio_fails(self):
        t = move_node(self.base, "J10", "3", "FAN_TACH")
        self.assertIn("blower.j10_pin_map", self.run_checks(t))

    def test_ntc_filter_cap_removed_fails(self):
        t = drop_node(self.base, self.ref("c_coil_filt"), "1")
        self.assertIn("adc1.COIL_ADC_input_rc_le_1kHz", self.run_checks(t))

    # ---- stage 16 blower supply from PS3 (DECISIONS C33)
    def test_u2_back_on_logic_15v_fails(self):
        t = move_node(self.base, "U2", "3", "v15_selv")
        failed = self.run_checks(t)
        self.assertIn("blwin.u2_vin_en_caps_on_v15_blw", failed)
        self.assertIn("j4.pin1_feeds_3v3_buck_only", failed)

    def test_part_bridging_v15_blw_and_v15_selv_fails(self):
        t = move_node(self.base, self.ref("c_blw_bulk"), "2", "v15_selv")
        failed = self.run_checks(t)
        self.assertIn("blwin.no_part_bridges_v15_blw_and_v15_selv", failed)
        self.assertIn("blwin.bulk_cap_on_v15_blw", failed)

    def test_j13_pins_swapped_fails(self):
        t = move_node(self.base, "J13", "1", "selv_gnd")
        t = move_node(t, "J13", "2", "V15_BLW")
        self.assertIn("blwin.j13_pin_map", self.run_checks(t))

    def test_blw_pg_off_p16_fails(self):
        t = move_node(self.base, self.ref("u_io"), "19", "selv_gnd")
        self.assertIn("blwin.blw_pg_divider_into_p16", self.run_checks(t))


if __name__ == "__main__":
    unittest.main()
