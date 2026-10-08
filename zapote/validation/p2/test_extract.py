#!/usr/bin/env python3
"""Live pcbnew oracle probes for the manufacturing transport."""
import json
import tempfile
import unittest
from pathlib import Path

import pcbnew
import wx
from extract import extract


def xy(x, y):
    return pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y))


class NativeExtraction(unittest.TestCase):
    def test_asymmetric_rotated_pad_slot_via_and_diagonal_track(self):
        with tempfile.TemporaryDirectory(prefix="zapote-native-oracle-") as directory:
            path = Path(directory) / "probe.kicad_pcb"
            board = pcbnew.BOARD()
            edge = pcbnew.PCB_SHAPE(board)
            edge.SetShape(pcbnew.SHAPE_T_RECT)
            edge.SetLayer(pcbnew.Edge_Cuts)
            edge.SetStart(xy(0, 0))
            edge.SetEnd(xy(40, 40))
            board.Add(edge)
            fp = pcbnew.FOOTPRINT(board)
            fp.SetReference("J1")
            fp.SetPosition(xy(10, 20))
            board.Add(fp)
            pad = pcbnew.PAD(fp)
            pad.SetNumber("1")
            pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
            pad.SetLayerSet(pcbnew.LSET.AllCuMask())
            pad.SetShape(pcbnew.PAD_SHAPE_OVAL)
            pad.SetSize(xy(4, 2))
            pad.SetDrillShape(pcbnew.PAD_DRILL_SHAPE_OBLONG)
            pad.SetDrillSize(xy(2, 0.8))
            pad.SetPosition(xy(20, 24))
            fp.Add(pad)
            fp.SetOrientationDegrees(45)
            marker = pcbnew.PCB_SHAPE(fp)
            marker.SetShape(pcbnew.SHAPE_T_CIRCLE)
            marker.SetLayer(pcbnew.F_Fab)
            marker.SetCenter(xy(10.5, 20.5))
            marker.SetRadius(pcbnew.FromMM(0.4))
            fp.Add(marker)
            # pcbnew is the external position oracle: the asymmetric R(-theta)
            # probe distinguishes the opposite-sign convention.
            position = pad.GetPosition()
            self.assertAlmostEqual(pcbnew.ToMM(position.x), 19.899495, places=5)
            self.assertAlmostEqual(pcbnew.ToMM(position.y), 15.757359, places=5)
            track = pcbnew.PCB_TRACK(board)
            track.SetStart(xy(3, 4))
            track.SetEnd(xy(9, 8))
            track.SetWidth(pcbnew.FromMM(0.2))
            track.SetLayer(pcbnew.F_Cu)
            board.Add(track)
            via = pcbnew.PCB_VIA(board)
            via.SetPosition(xy(9, 8))
            via.SetWidth(pcbnew.FromMM(0.6))
            via.SetDrill(pcbnew.FromMM(0.3))
            via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            board.Add(via)
            pcbnew.SaveBoard(str(path), board)
            data = extract(path)
            self.assertEqual(data["native_census"], {"footprints": 1, "pads": 1, "tracks": 1, "vias": 1, "zones": 0})
            self.assertNotIn("p2_population", data)  # Only Rust evaluates rules.
            geometry = data["input"]
            for physical in geometry["pads"]:
                self.assertTrue(physical["inner_copper_polygons"])
            self.assertEqual(len(geometry["bodies"]), 0)
            self.assertTrue(any("Circle detail/body role" in gap for gap in geometry["unsupported"]))
            self.assertEqual(len(geometry["holes"]), 2)
            slot = next(h for h in geometry["holes"] if h["id"].startswith("J1.1"))
            self.assertGreater(len(slot["polygon"]["vertices_mm"]), 8)
            pad_shape = next(c for c in geometry["copper"] if c["id"].startswith("J1.1"))
            points = pad_shape["polygon"]["vertices_mm"]
            self.assertAlmostEqual((min(p[0] for p in points) + max(p[0] for p in points))/2, 19.899495, places=3)
            self.assertAlmostEqual((min(p[1] for p in points) + max(p[1] for p in points))/2, 15.757359, places=3)
            diagonal = next(c for c in geometry["copper"] if c["id"].startswith(track.m_Uuid.AsString()))
            points = diagonal["polygon"]["vertices_mm"]
            self.assertAlmostEqual(min(p[0] for p in points), 2.9, delta=0.002)
            self.assertAlmostEqual(max(p[1] for p in points), 8.1, delta=0.002)
            self.assertTrue(any("no closed native F.Fab" in gap for gap in geometry["unsupported"]))


if __name__ == "__main__":
    app = wx.App(False)
    unittest.main()
