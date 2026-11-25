"""Land-pattern gate: every fitted part's KiCad pads must sit on JLC's pads for the same LCSC part.

Found by this gate's predecessor not existing (C51): U30 MAX31865AAP+ is a 5.3 mm SSOP-20 and sat on a 3.9 mm QSOP
land on C48 and C49. The CPL audit computed the 0.89 mm misfit and used it only to pick a rotation.
Run: python3 -m unittest tests.test_land_patterns -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

UNIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(UNIT / "tools"))

import check_land_patterns as lp  # noqa: E402


class Gate(unittest.TestCase):
    def test_frozen_netlist_passes(self):
        rep = lp.run()
        self.assertEqual(rep["failed"], [])
        self.assertGreater(rep["checked"], 80)

    def test_qsop_land_under_the_ssop_part_fails(self):
        fit = lp.fit(lp.kicad_pads("Package_SO:SSOP-20_3.9x8.7mm_P0.635mm"), lp.jlc_pads()["C89608"]["pads"])
        self.assertGreater(fit, lp.LIMIT_MM)

    def test_ssop_land_under_the_ssop_part_passes(self):
        fit = lp.fit(lp.kicad_pads("Package_SO:SSOP-20_5.3x7.2mm_P0.65mm"), lp.jlc_pads()["C779509"]["pads"])
        self.assertLess(fit, lp.LIMIT_MM)

    def test_wrong_pad_count_fails(self):
        self.assertEqual(lp.fit(lp.kicad_pads("Package_SO:SSOP-20_5.3x7.2mm_P0.65mm"),
                                lp.jlc_pads()["C148036"]["pads"]), float("inf"))

    def test_part_without_jlc_record_is_a_failure_not_a_pass(self):
        rep = lp.run(drop={"C89608", "C779509"})
        self.assertTrue(any("MAX31865" in f and "no JLC" in f for f in rep["failed"]), rep["failed"])

    def test_stale_exception_fails(self):
        rep = lp.run(exceptions={"NOT-A-PART": "x"})
        self.assertTrue(any("NOT-A-PART" in f for f in rep["failed"]), rep["failed"])


if __name__ == "__main__":
    unittest.main()
