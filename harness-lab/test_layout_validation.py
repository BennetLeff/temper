"""Software controls for the engineering-layout judge.

The compact fixtures are synthetic controls, never engineering evidence.  The
native test additionally exercises one saved KiCad witness.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import harness

ROOT = Path(__file__).parent
JUDGE = (
    os.environ.get("ENGINEERING_JUDGE")
    or os.environ.get("TEMPER_E00_JUDGE")
    or str(harness.JUDGE)
)


def fixture() -> dict:
    def pad(ref: str, number: str, net: str, x: float, y: float) -> dict:
        return {
            "reference": ref,
            "number": number,
            "net": net,
            "position_mm": [x, y],
            "layer": "F.Cu",
        }

    footprints = [
        {
            "reference": "C9",
            "pads": [pad("C9", "1", "+15V", 0, 0), pad("C9", "2", "gnd", 0, 10)],
        },
        {
            "reference": "U3",
            "pads": [pad("U3", "1", "gnd", 5, 10), pad("U3", "3", "+15V", 5, 0)],
        },
    ]

    def segment(
        uuid: str, net: str, a: list[float], b: list[float], width: float = 0.6
    ) -> dict:
        return {
            "uuid": uuid,
            "kind": "segment",
            "net": net,
            "layer": "F.Cu",
            "start_mm": a,
            "end_mm": b,
            "width_mm": width,
        }

    tracks = [
        segment("p1", "+15V", [0, 0], [2, 0]),
        segment("p2", "+15V", [2, 0], [5, 0]),
        segment("g1", "gnd", [0, 10], [2, 10]),
        segment("g2", "gnd", [2, 10], [5, 10]),
    ]
    return {
        "profile": "engineering-layout",
        "measurement": {"footprints": footprints, "buck": {"tracks": tracks}},
        "contract": json.loads((ROOT / "engineering/layout-contract.json").read_text()),
        "base_result": {"status": "pass", "findings": []},
        "presentation": {
            "labels": [
                {
                    "text": "C9",
                    "layer": "F.SilkS",
                    "height_mm": 1.0,
                    "bounds_mm": [-2, -2, -1, -1],
                },
                {
                    "text": "U3",
                    "layer": "F.SilkS",
                    "height_mm": 1.0,
                    "bounds_mm": [7, 7, 8, 8],
                },
            ]
        },
    }


class LayoutJudgeControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.judge = Path(JUDGE)
        cls.tmp = tempfile.TemporaryDirectory(prefix="layout-native-")
        try:
            import qualify_buck

            contract = json.loads((ROOT / "fixtures/buck-contract.json").read_text())
            vid = contract["variants"][0]["id"]
            directory = Path(cls.tmp.name) / "witness"
            qualify_buck.prepare(directory, vid)
            shutil.copyfile(
                directory / "witness.kicad_pcb", directory / "candidate.kicad_pcb"
            )
            cls.base = qualify_buck.evaluate(
                directory, contract, vid, directory / "evaluation"
            )
            if cls.base.get("status") != "pass":
                raise RuntimeError(f"native witness did not pass: {cls.base}")
            cls.native_board = directory / "candidate.kicad_pcb"
        except Exception as error:
            cls.base = {"status": "blocked", "error": str(error)}
            cls.native_board = None

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def run_judge(self, payload: dict) -> dict:
        proc = subprocess.run(
            [str(self.judge)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertTrue(proc.stdout, proc.stderr)
        return json.loads(proc.stdout)

    def test_positive_baseline_and_exact_dogleg_length(self) -> None:
        result = self.run_judge(fixture())
        self.assertEqual(result["status"], "pass")
        self.assertEqual(
            result["measurements"]["copper_path_mm"]["ground_return"]["length_mm"], 5.0
        )

    def test_long_ground_return_fails_even_with_via_at_pad(self) -> None:
        payload = fixture()
        payload["measurement"]["buck"]["tracks"] = [
            {
                "uuid": "v",
                "kind": "via",
                "net": "gnd",
                "layer": "F.Cu-B.Cu",
                "start_mm": [0, 10],
                "end_mm": [0, 10],
                "width_mm": 0.8,
            },
            {
                "uuid": "a",
                "kind": "segment",
                "net": "gnd",
                "layer": "F.Cu",
                "start_mm": [0, 10],
                "end_mm": [0, 40],
                "width_mm": 0.6,
            },
            {
                "uuid": "b",
                "kind": "segment",
                "net": "gnd",
                "layer": "F.Cu",
                "start_mm": [0, 40],
                "end_mm": [5, 40],
                "width_mm": 0.6,
            },
            {
                "uuid": "c",
                "kind": "segment",
                "net": "gnd",
                "layer": "F.Cu",
                "start_mm": [5, 40],
                "end_mm": [5, 10],
                "width_mm": 0.6,
            },
        ]
        result = self.run_judge(payload)
        self.assertTrue(any(f["id"] == "ground_return" for f in result["findings"]))

    def test_neckdown_and_feedback_switching_controls(self) -> None:
        payload = fixture()
        payload["measurement"]["buck"]["tracks"][0]["width_mm"] = 0.1
        payload["measurement"]["buck"]["tracks"] += [
            {
                "uuid": "fb",
                "kind": "segment",
                "net": "fb",
                "layer": "F.Cu",
                "start_mm": [1, 1],
                "end_mm": [4, 1],
                "width_mm": 0.3,
            },
            {
                "uuid": "sw",
                "kind": "segment",
                "net": "sw",
                "layer": "F.Cu",
                "start_mm": [1, 1.2],
                "end_mm": [4, 1.2],
                "width_mm": 0.6,
            },
        ]
        result = self.run_judge(payload)
        ids = {f["id"] for f in result["findings"]}
        self.assertIn("power_neckdown", ids)
        self.assertIn("fb_sw_separation", ids)

    def test_presentation_controls_and_missing_models_are_separate(self) -> None:
        payload = fixture()
        payload["presentation"]["labels"][1]["bounds_mm"] = [-2, -2, -1, -1]
        self.assertEqual(self.run_judge(payload)["layout"]["presentation"], "fail")
        payload = fixture()
        payload["presentation"]["missing_3d_models"] = ["U3"]
        self.assertEqual(self.run_judge(payload)["layout"]["electrical"], "pass")

    def test_base_drc_failure_and_unsupported_zone_block(self) -> None:
        payload = fixture()
        payload["base_result"]["status"] = "fail"
        self.assertNotEqual(self.run_judge(payload)["status"], "pass")
        payload = fixture()
        payload["measurement"]["buck"]["tracks"].append(
            {"uuid": "z", "kind": "zone", "net": "gnd", "layer": "F.Cu"}
        )
        self.assertEqual(self.run_judge(payload)["status"], "indeterminate")

    def test_midsegment_crossing_and_t_junction(self) -> None:
        for endpoint in (True, False):
            payload = fixture()
            payload["measurement"]["footprints"][1]["pads"][0]["position_mm"] = [3, 15]
            tracks = payload["measurement"]["buck"]["tracks"]
            tracks[2]["end_mm"] = [3 if endpoint else 5, 10]
            tracks[3]["start_mm"] = [3, 8]
            tracks[3]["end_mm"] = [3, 15]
            result = self.run_judge(payload)
            self.assertEqual(result["status"], "pass")
            self.assertEqual(
                result["measurements"]["copper_path_mm"]["ground_return"]["length_mm"],
                8.0,
            )
            tracks[3]["layer"] = "B.Cu"
            self.assertEqual(self.run_judge(payload)["status"], "indeterminate")

    def test_native_saved_pad_coordinates_and_labels(self) -> None:
        if self.native_board is None:
            self.fail("native witness unavailable: " + self.base["error"])
        import layout_native

        with tempfile.TemporaryDirectory(prefix="layout-evidence-") as output:
            payload = layout_native.collect(
                ROOT.parent, Path(output) / "fresh", self.native_board, self.base
            )
            pads = [
                p
                for fp in payload["measurement"]["footprints"]
                for p in fp["pads"]
                if fp["reference"] == "U3" and p["number"] == "1"
            ]
            self.assertEqual(len(pads), 1)
            self.assertEqual(len(pads[0]["position_mm"]), 2)
            self.assertIn("labels", payload["presentation"])
