"""Analytical edges/charge oracles, malformed captures, and real D2 regression."""
from __future__ import annotations

import copy
import json
import unittest
import tempfile
from pathlib import Path

from bench_verdict import Trace, load_csv, recovery, verdict

T = tuple(i * 1e-9 for i in range(2001))


def trace(points: list[tuple[float, float]]) -> Trace:
    source = Trace(tuple(x * 1e-9 for x, _ in points), tuple(y for _, y in points))
    return Trace(T, tuple(source.at(t) for t in T))


def falling(at: float, high: float = 3.3) -> Trace:
    return trace([(0, high), (at - 5, high), (at + 5, 0), (2000, 0)])


def rising(at: float, high: float = 3.3) -> Trace:
    f = falling(at, high)
    return Trace(f.t, tuple(high - y for y in f.y))


def capture(test: str) -> tuple[dict[str, Trace], dict]:
    waves = {
        "B0": {"r35_kelvin_v": trace([(0, .001), (2000, .001)]), "u5_kelvin_v": trace([(0, -.002), (2000, -.002)])},
        "B1": {"permit_v": falling(100), "permit_gate_v": falling(200), "dis_v": rising(315), "out_a_v": falling(350, 15), "out_b_v": falling(360, 15)},
        "B2": {"incoming_cmd_v": rising(300), "outgoing_vgs_v": trace([(0, 0), (300, 0), (400, 2), (500, 0), (2000, 0)])},
        "B3": {"incoming_cmd_v": rising(300), "outgoing_cmd_v": falling(100), "incoming_out_v": rising(340, 15), "outgoing_out_v": falling(140, 15), "incoming_vgs_v": rising(360, 15), "outgoing_vgs_v": falling(160, 15), "incoming_vds_v": trace([(0, 400), (2000, 0)]), "outgoing_vds_v": trace([(0, 0), (2000, 450)]), "diode_id_a": trace([(0, -20), (350, -20), (550, 20), (750, 0), (2000, 0)])},
        "B4": {"bus_fault_v": rising(300), "load_current_a": trace([(0, 60), (2000, 100)]), "comparator_v": falling(100), "conducting_out_v": falling(550, 15), "conducting_vgs_v": falling(600, 15), "die_vds_v": trace([(0, 0), (700, 450), (2000, 50)])},
    }[test]
    meta = {"test": test, "leg": "A", "bus_v": 0 if test in ("B0", "B1") else 50,
            "capture_ok": True, "board_manifest_sha256": "0" * 64,
            "deskew_s": dict.fromkeys(waves, 0), "window_s": [10e-9, 1900e-9],
            "uncertainty": {"gate_v": .1, "vds_v": 5, "current_a": 1, "offset_v": .00001, "timing_s": 2e-9},
            "logic_threshold_v": 1.65, "driver_high_v": 15, "vds_reference": "die"}
    return waves, meta


class VerdictTests(unittest.TestCase):
    def test_every_criterion_passes_and_fails(self) -> None:
        mutations = {
            "B0": [("r35_kelvin_v", trace([(0, .003), (2000, .003)]), "r35_kelvin_v"), ("u5_kelvin_v", trace([(0, -.003), (2000, -.003)]), "u5_kelvin_v")],
            "B1": [("permit_gate_v", falling(285), "permit_to_gate"), ("dis_v", rising(340), "gate_to_dis"), ("out_a_v", falling(500, 15), "permit_to_out_a_v"), ("out_b_v", falling(500, 15), "permit_to_out_b_v")],
            "B2": [("outgoing_vgs_v", trace([(0, 0), (400, 3), (2000, 0)]), "partner_vgs_peak")],
            "B3": [("outgoing_vgs_v", trace([(0, 15), (200, 0), (400, 3), (500, 0), (2000, 0)]), "partner_vgs_peak"), ("outgoing_vgs_v", trace([(0, 15), (200, 0), (400, 3), (500, 0), (2000, 0)]), "partner_vgs_output_window"), ("incoming_vds_v", trace([(0, 600), (2000, 600)]), "incoming_vds_peak"), ("outgoing_vds_v", trace([(0, 600), (2000, 600)]), "outgoing_vds_peak"), ("incoming_vgs_v", rising(360, 21), "incoming_gate_rating"), ("outgoing_vgs_v", falling(160, 21), "outgoing_gate_rating")],
            "B4": [("load_current_a", trace([(0, 100), (2000, 100)]), "trip_current"), ("conducting_out_v", falling(700, 15), "comparator_to_driver_out_low"), ("die_vds_v", trace([(0, 530), (2000, 530)]), "die_vds_peak")],
        }
        for test, cases in mutations.items():
            waves, meta = capture(test)
            baseline = verdict(waves, meta)
            self.assertEqual(baseline["status"], "PASS", baseline)
            self.assertEqual({row[2] for row in cases}, {c["name"] for c in baseline["criteria"]})
            for channel, changed, criterion in cases:
                with self.subTest(test=test, criterion=criterion):
                    result = verdict({**waves, channel: changed}, meta)
                    self.assertEqual(result["status"], "FAIL", result)
                    self.assertEqual(next(c["status"] for c in result["criteria"] if c["name"] == criterion), "FAIL")

    def test_known_measurements(self) -> None:
        waves, meta = capture("B1")
        rows = {c["name"]: c["value"] for c in verdict(waves, meta)["criteria"]}
        self.assertAlmostEqual(rows["permit_to_gate"], 103.0303030303)
        self.assertAlmostEqual(rows["gate_to_dis"], 113.9393939394)
        self.assertAlmostEqual(rows["permit_to_out_a_v"], 254)
        waves, meta = capture("B4")
        self.assertAlmostEqual(verdict(waves, meta)["criteria"][0]["value"], 66)
        waves, _ = capture("B3")
        r = recovery(waves["diode_id_a"], 300e-9, 1900e-9, 2e-9)
        self.assertAlmostEqual(r["Qrr_C"] / 1e-6, 2.98, places=6)
        self.assertAlmostEqual(r["trr_s"] / 1e-9, 280, places=6)
        self.assertAlmostEqual(r["softness"], 1.8, places=6)
        self.assertAlmostEqual(r["di_dt_20ns_A_per_us"], 200, places=6)

    def test_noise_and_ringing_do_not_select_false_edge(self) -> None:
        noisy = trace([(0, 3.3), (50, 3.3), (51, 0), (52, 3.3), (98, 3.3), (100, 0), (101, 2), (103, 0), (2000, 0)])
        self.assertEqual(len(noisy.crossings(1.65, False)), 3)
        self.assertAlmostEqual(noisy.edge(1.65, False, 0, 3e-9) / 1e-9, 101.35)

    def test_deskew_sign(self) -> None:
        waves, meta = capture("B1")
        baseline = verdict(waves, meta)["criteria"][0]["value"]
        original = waves["permit_gate_v"]
        waves["permit_gate_v"] = Trace(tuple(t + 5e-9 for t in original.t), original.y)
        meta["deskew_s"]["permit_gate_v"] = 5e-9
        self.assertAlmostEqual(verdict(waves, meta)["criteria"][0]["value"], baseline)

    def test_invalid_inputs_never_pass(self) -> None:
        self.assertEqual(verdict({}, None)["status"], "INVALID")
        for test in ("B0", "B1", "B2", "B3", "B4"):
            waves, meta = capture(test)
            bad = copy.deepcopy(meta)
            bad["capture_ok"] = False
            self.assertEqual(verdict(waves, bad)["status"], "INVALID")
            bad = copy.deepcopy(meta)
            bad["deskew_s"] = {}
            self.assertEqual(verdict(waves, bad)["status"], "INVALID")
            bad = copy.deepcopy(meta)
            bad["window_s"][1] = 3e-6
            self.assertEqual(verdict(waves, bad)["status"], "INVALID")
        waves, meta = capture("B2")
        waves["incoming_cmd_v"] = trace([(0, 3.3), (2000, 3.3)])
        self.assertEqual(verdict(waves, meta)["status"], "INVALID")
        waves, meta = capture("B4")
        meta["vds_reference"] = "package"
        self.assertEqual(verdict(waves, meta)["status"], "INVALID")

    def test_malformed_csv(self) -> None:
        bad = ("time_s,x,x\n0,1,1\n1,2,2\n2,3,3\n",
               "time_s,x\n0,1\n1\n2,3\n",
               "time_s,x\n0,1\n0,2\n2,3\n",
               "time_s,x\n0,1\n1,nan\n2,3\n",
               "time_s,x\n0,1\n1,2\n")
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.csv"
            for text in bad:
                with self.subTest(text=text):
                    path.write_text(text)
                    with self.assertRaises(ValueError):
                        load_csv(path)

    def test_real_ngspice_fixture(self) -> None:
        out = Path(__file__).parents[1] / "validation-results/01-switching-parasitics/round17/delegation/out-D34"
        result = verdict(load_csv(out / "d2.csv"), json.loads((out / "d2.json").read_text()))
        expected = json.loads((out / "d2-verdict.json").read_text())
        self.assertEqual(result["status"], expected["status"])
        self.assertNotEqual(result["status"], "INVALID", result)
        self.assertAlmostEqual(result["criteria"][0]["value"], expected["criteria"][0]["value"], places=9)


if __name__ == "__main__":
    unittest.main()
