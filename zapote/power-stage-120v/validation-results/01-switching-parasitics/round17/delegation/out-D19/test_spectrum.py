"""Independent normalization, phase, limit and measurement-reference checks."""

import unittest
import numpy as np
from spectrum import combine, limits
from source_metrics import tank_current


class SpectrumTests(unittest.TestCase):
    def test_resonant_tank_current(self):
        n = 32768
        phase = np.arange(n) / n
        voltage = 5 * np.cos(2 * np.pi * phase + 0.3)
        spectrum = 2 * np.fft.rfft(voltage + 9) / n
        resonance = 1 / (2 * np.pi * np.sqrt(70e-6 * 0.54e-6))
        current = tank_current(spectrum, resonance, 2)
        np.testing.assert_allclose(current, voltage / 2, atol=1e-12)
        self.assertAlmostEqual(2 * np.mean(current**2), 6.25)

    def test_fourier_peak_and_rms(self):
        count = 32768
        t = np.arange(count) / count
        wave = 3 + 4 * np.cos(2 * np.pi * 5 * t + 0.3)
        spectrum = 2 * np.fft.rfft(wave) / count
        self.assertAlmostEqual(spectrum[0].real / 2, 3)
        self.assertAlmostEqual(abs(spectrum[5]), 4)
        self.assertAlmostEqual(np.angle(spectrum[5]), 0.3)
        self.assertAlmostEqual(abs(spectrum[5]) / np.sqrt(2), np.sqrt(np.mean((wave - 3) ** 2)))

    def test_phase_and_receiver_reference(self):
        # Same PE displacement on both probes must disappear across Rsense.
        f = np.array([150e3, 30e6])
        transfers = {}
        for source in ("A", "B", "DM"):
            transfers[source] = {
                "frequency": f,
                "v(lisn_l)": np.array([3 + 1j] * 2),
                "v(lisn_n)": np.array([1 + 1j] * 2),
                "v(pe)": np.array([1j] * 2),
            }
        signals = {
            "v(swa)": np.array([2j] * 2),
            "v(swb)": np.array([-2j] * 2),
            "bus_current_A": np.array([1.0] * 2),
        }
        result = combine(transfers, signals, f)
        np.testing.assert_allclose(result["l_pe"], 3)
        np.testing.assert_allclose(result["n_pe"], 1)
        np.testing.assert_allclose(result["l_earth"], 3 + 1j)

    def test_limits_and_excluded_bands(self):
        qp, av, mask = limits(
            np.array([150e3, 500e3, 5e6, 5e6 + 1, 6.78e6, 13.56e6, 27.12e6, 30e6])
        )
        np.testing.assert_allclose(qp, [66, 56, 56, 60, 60, 60, 60, 60])
        np.testing.assert_allclose(qp - av, 10)
        self.assertEqual(mask.tolist(), [True, True, True, True, False, False, False, True])

    def test_logarithmic_limit_midpoint(self):
        qp, _, _ = limits(np.array([np.sqrt(150e3 * 500e3)]))
        self.assertAlmostEqual(qp[0], 61)


if __name__ == "__main__":
    unittest.main()
