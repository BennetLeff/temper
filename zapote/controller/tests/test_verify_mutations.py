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
                   lambda: vc.check_trip(rep, nl, CALCS), lambda: vc.check_misc(rep, nl)):
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
        self.assertIn("j4.pin9_permit_driven_only_by_interlock_latch", failed)

    def test_wdi_into_trip_cone_fails(self):
        inv = self.ref("interlock.control_inv")
        t = move_node(self.base, inv, "9", "IL_WDI")            # interlock SENSOR_LIVE input fed by GPIO18
        self.assertIn("trip.only_firmware_input_is_reset_request", self.run_checks(t))

    def test_disconnected_heatsink_fault_fails(self):
        inv = self.ref("interlock.fault_inv")
        t = move_node(self.base, inv, "5", "OVP_TIE")           # HS input tied healthy
        failed = self.run_checks(t)
        self.assertIn("trip.every_specified_source_reaches_permit", failed)

    def test_inverted_runaway_polarity_fails(self):
        comp = self.ref("u_runaway")
        t = move_node(self.base, comp, "3", "RUNAWAY_TH")
        window = self.base_nl.net_of(comp, "3")                # the RTDIN+ window node
        t = move_node(t, comp, "4", window)
        failed = self.run_checks(t)
        self.assertIn("trip.runaway_inp_observes_rtdin_plus_via_window_branch", failed)
        self.assertIn("trip.runaway_inn_is_bias_divider", failed)

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

    def test_unmodelled_part_on_v3v3_fails_closed(self):
        saved = vc.MODELS.pop("TLV9062IDR")
        try:
            with self.assertRaises(ValueError):
                vc.v3v3_load(self.base_nl, "controller", {})
        finally:
            vc.MODELS["TLV9062IDR"] = saved

    def test_strap_pullup_on_gpio46_fails(self):
        r = self.ref("r_fan_off_pd")
        t = move_node(self.base, r, "2", "v3v3")
        self.assertIn("misc.gpio46_reads_0_at_reset", self.run_checks(t))


if __name__ == "__main__":
    unittest.main()
