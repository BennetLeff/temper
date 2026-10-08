"""Regression against pcbnew's actual placement, including an asymmetric 45° pad.

Run with KiCad's Python. Temporary fixtures never replace a candidate board.
"""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

import pcbnew

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "zapote/current-sense/tools"))
from initialize_current_sense_native import initialize  # noqa: E402


class NativeInitializationOracle(unittest.TestCase):
    def fixture(self, folder):
        library = folder / "candidate-libs/Oracle.pretty"
        library.mkdir(parents=True)
        (library / "Asymmetric.kicad_mod").write_text('''(footprint "Asymmetric"
          (version 20240108) (generator pcbnew) (layer "F.Cu")
          (pad "1" smd rect (at 10 4 30) (size 4 1) (layers "F.Cu" "F.Paste" "F.Mask"))
          (pad "2" smd rect (at -3 2) (size 1 2) (layers "F.Cu" "F.Paste" "F.Mask")))''')
        board = pcbnew.BOARD()
        fp = pcbnew.FootprintLoad(str(library), "Asymmetric")
        fp.SetFPID(pcbnew.LIB_ID("Oracle", "Asymmetric"))
        fp.SetReference("U1")
        fp.SetOrientationDegrees(45)
        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(30), pcbnew.FromMM(30)))
        board.Add(fp)
        expected = {p.GetNumber(): (p.GetPosition(), p.GetOrientationDegrees()) for p in fp.Pads()}
        # Reproduce the donor defect: right native positions, wrong body angles.
        for pad in fp.Pads():
            pad.SetOrientationDegrees(30 if pad.GetNumber() == "1" else 0)
        path = folder / "section.kicad_pcb"
        pcbnew.SaveBoard(str(path), board)
        return path, expected

    def test_repairs_body_angle_against_external_placement_and_preserves_position(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            path, expected = self.fixture(folder)
            before = pcbnew.LoadBoard(str(path))
            ids = {p.GetNumber(): p.m_Uuid.AsString() for f in before.GetFootprints() for p in f.Pads()}
            receipt = folder / "receipt.json"
            with contextlib.redirect_stdout(io.StringIO()):
                initialize(REPO, path, receipt)
            after = pcbnew.LoadBoard(str(path))
            for footprint in after.GetFootprints():
                for pad in footprint.Pads():
                    position, angle = expected[pad.GetNumber()]
                    self.assertEqual(pad.GetPosition(), position)
                    self.assertAlmostEqual(pad.GetOrientationDegrees(), angle)
                    self.assertEqual(pad.m_Uuid.AsString(), ids[pad.GetNumber()])
            self.assertEqual(len(json.loads(receipt.read_text())["pad_orientation_repairs"]), 2)

    def test_does_not_launder_a_wrong_pad_position(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            path, _ = self.fixture(folder)
            board = pcbnew.LoadBoard(str(path))
            pad = next(iter(next(iter(board.GetFootprints())).Pads()))
            pad.SetPosition(pad.GetPosition() + pcbnew.VECTOR2I(pcbnew.FromMM(1), 0))
            pcbnew.SaveBoard(str(path), board)
            before = path.read_bytes()
            with self.assertRaisesRegex(ValueError, "pad-position oracle mismatch"):
                initialize(REPO, path, folder / "receipt.json")
            self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
