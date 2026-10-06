"""External IEC 2010 Annex C 120 V/60 Hz test points (Tables 1a, 2a, 5).

The scale is calibrated at 8.8 Hz sine; all other points are independent.
Reference source and applicable limitations are in out-D35/README.md.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

import numpy as np

from flickermeter import measure, modulation, pinst, plt, pst

SINE = ((.5, 2.453), (1.5, 1.126), (8.8, .321), (20, .977), (100 / 3, 2.570), (40, 4.393))
SQUARE = ((.5, .598), (3.5, .408), (8.8, .252), (18, .626), (22, .851), (25.5, 1.072), (100 / 3, 1.823), (37, 1.304), (40, 3.451))
CLASSIFIER = ((1, 3.181), (2, 2.564), (7, 1.694), (39, 1.040), (110, .844), (1620, .548), (4800, 4.837))


def performance() -> list[dict]:
    rows = []
    for kind, cases in (("sine", SINE), ("square", SQUARE)):
        for hz, depth in cases:
            # Continuous modulation after settling: response is periodic Pinst,max.
            wave = modulation(kind, hz, depth, seconds=660)
            inst = pinst(wave)[(180 + 60) * 4800:]
            value = float(np.max(inst))
            rows.append({"kind": kind, "hz": hz, "depth_pct": depth, "quantity": "Pinst_max", "value": value, "tolerance": .08, "pass": abs(value - 1) <= .08})
    for cpm, depth in CLASSIFIER:
        value = measure(modulation("square", cpm / 120, depth))["Pst"]
        rows.append({"kind": "classifier", "cpm": cpm, "depth_pct": depth, "quantity": "Pst", "value": value, "tolerance": .05, "pass": abs(value - 1) <= .05})
    return rows


class FlickerTests(unittest.TestCase):
    def test_standard_performance_points(self) -> None:
        rows = performance()
        out = Path(__file__).parents[2] / "01-switching-parasitics/round17/delegation/out-D35"
        out.mkdir(parents=True, exist_ok=True)
        (out / "performance.json").write_text(json.dumps(rows, indent=2) + "\n")
        for row in rows:
            with self.subTest(row=row):
                self.assertTrue(row["pass"])

    def test_classifier_oracles(self) -> None:
        self.assertAlmostEqual(pst(np.full(1000, 4.)), np.sqrt(4 * (.0314 + .0525 + .0657 + .28 + .08)))
        self.assertAlmostEqual(plt([.65] * 12), .65)
        self.assertAlmostEqual(plt([0] * 6 + [1] * 6), .5**(1 / 3))
        with self.assertRaises(ValueError):
            plt([1])
        with self.assertRaises(ValueError):
            pst(np.array([float("nan")]))

    def test_input_contract(self) -> None:
        with self.assertRaises(ValueError):
            pinst(np.ones(2400), fs=2399)
        with self.assertRaises(ValueError):
            pinst(np.full(2400, float("nan")), fs=2400)
        with self.assertRaises(ValueError):
            measure(np.ones(2400), fs=2400, warmup=0)

    def test_constant_voltage_and_amplitude_scaling(self) -> None:
        # The specified finite carrier filter leaves a small 120 Hz residual.
        self.assertLess(measure(modulation("sine", 8.8, 0))["Pst"], .005)
        a = measure(modulation("sine", 8.8, .1))["Pst"]
        b = measure(modulation("sine", 8.8, .2))["Pst"]
        self.assertAlmostEqual(b / a, 2, delta=.002)


if __name__ == "__main__":
    unittest.main()
