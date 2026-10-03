"""Reject incomplete source evidence; preserve the round-3 receiver fixture."""

import unittest
import numpy as np
from periodic import analyze, read_binary
from filter_stage import BASE_DECK, MODEL, deck_text
from pathlib import Path
import tempfile


class EvidenceTests(unittest.TestCase):
    def test_binary_capture_and_truncation(self):
        header = b"Title: test\nFlags: real\nNo. Variables: 2\nNo. Points: 3\nVariables:\n\t0\ttime\ttime\n\t1\tv(out)\tvoltage\nBinary:\n"
        payload = np.array([[0.0, 1.0], [1e-9, 2.0], [2e-9, 3.0]], dtype=np.float64).tobytes()
        waves = read_binary(header + payload)
        np.testing.assert_array_equal(waves["v(out)"], [1.0, 2.0, 3.0])
        for removed in (8, 16):
            with self.assertRaises(ValueError):
                read_binary(header + payload[:-removed])

    def test_no_stage_keeps_every_passive_and_reference(self):
        original = BASE_DECK.read_text()
        for source in ("A", "B", "DM"):
            result = deck_text({}, source, False)
            original_lines = [
                line for line in original.splitlines() if not line.startswith(".param EXC_")
            ]
            result_lines = [
                line for line in result.splitlines() if not line.startswith(".param EXC_")
            ]
            self.assertEqual(original_lines, result_lines)

    def test_reference_shift_cancels_and_complex_sources_interfere(self):
        f = np.array([175000.0, 210000.0])
        tr = {
            source: {
                "frequency": f,
                "v(lisn_l)": np.full(2, 3 + 4j),
                "v(lisn_n)": np.full(2, 1 + 2j),
                "v(pe)": np.full(2, 2j),
            }
            for source in ("A", "B", "DM")
        }
        signals = {
            "v(swa)": np.full(2, 2j),
            "v(swb)": np.full(2, -2j),
            "bus_current_A": np.zeros(2),
        }
        result = MODEL["combine"](tr, signals, f)
        np.testing.assert_allclose(result["l_pe"], 0, atol=1e-12)
        signals["v(swb)"] *= 0
        first = MODEL["combine"](tr, signals, f)
        for waves in tr.values():
            for key in ("v(lisn_l)", "v(lisn_n)", "v(pe)"):
                waves[key] += 100 + 200j
        second = MODEL["combine"](tr, signals, f)
        np.testing.assert_allclose(first["l_pe"], second["l_pe"], atol=1e-12)
        np.testing.assert_allclose(first["l_pe"], np.full(2, -4 + 6j), atol=1e-12)

    def test_truncated_time_window_cannot_be_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "endpoint"):
                analyze(
                    {"time": np.array([0.0, 1e-9])},
                    {"FREQ": "35000", "CYCLES": "24", "VBUS": "170"},
                    Path(directory),
                )

    def test_fourier_peak_amplitude_phase_and_dc_power(self):
        frequency = 35000
        end = 2e-6 + 24 / frequency
        time = np.linspace(end - 2 / frequency, end, 262145)
        phase = 2 * np.pi * (time - 2e-6) * frequency
        waves = {
            "time": time,
            "v(swa)": 3 + 2 * np.cos(phase),
            "v(swb)": 3 - 2 * np.cos(phase),
            "i(v.xla.vfeed)": 1 + 0.1 * np.sin(phase),
            "i(v.xlb.vfeed)": 2 + 0.2 * np.sin(phase),
        }
        with tempfile.TemporaryDirectory() as directory:
            result = analyze(
                waves, {"FREQ": "35000", "CYCLES": "24", "VBUS": "170"}, Path(directory)
            )
            self.assertEqual(result["status"], "complete")
            self.assertAlmostEqual(result["input_power_estimate_W"], 510, places=8)
            with np.load(Path(directory) / "fft.npz") as fft:
                np.testing.assert_allclose(fft["v(swa)"][:2], [6, 2], atol=1e-8)
                np.testing.assert_allclose(fft["bus_current_A"][:2], [6, -0.3j], atol=1e-8)

    def test_incomplete_convergence_coverage_never_qualifies(self):
        from summarize import qualified
        from qualify_filter import scenarios

        rows = [
            {
                "comparison": "case" + suffix,
                "scenario": scenario,
                "terminal": terminal,
                "passes_0p2dB_target": True,
            }
            for suffix in ("-step", "-cycle")
            for scenario in scenarios()
            for terminal in ("l_pe", "n_pe")
        ]
        self.assertTrue(qualified(rows, "case"))
        self.assertFalse(qualified(rows[:-1], "case"))
        self.assertFalse(qualified(rows + [rows[0]], "case"))
        rows[0]["passes_0p2dB_target"] = False
        self.assertFalse(qualified(rows, "case"))

    def test_unknown_ac_parameter_is_rejected(self):
        with self.assertRaises(ValueError):
            deck_text({"TYPO_INDUCTANCE": 1e-3}, "DM")


if __name__ == "__main__":
    unittest.main()
