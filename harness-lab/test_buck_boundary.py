"""Buck nine-component profile admission and measurement boundaries."""

import copy
import json
import math
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import harness
import qualify_buck as task
from qualify_buck import ADAPTER


class BuckBoundaryTests(unittest.TestCase):
    def test_only_the_seven_buck_tools_are_admitted(self):
        self.assertEqual(
            [t["name"] for t in task.TOOLS],
            [
                "inspect",
                "place",
                "route",
                "remove_route",
                "add_via",
                "add_zone",
                "check",
            ],
        )
        for tool in task.TOOLS:
            schema = json.dumps(tool["inputSchema"])
            for forbidden in ("path", "command", "code", "script", "shell"):
                self.assertNotIn(f'"{forbidden}"', schema)

    def test_contract_freezes_four_variants_with_obligation_coverage(self):
        contract = json.loads(task.CONTRACT.read_text())
        self.assertEqual(
            [v["id"] for v in contract["variants"]],
            ["buck-dev-a", "buck-dev-b", "buck-res-a", "buck-res-b"],
        )
        self.assertEqual(
            [v["split"] for v in contract["variants"]],
            ["development", "development", "reserved", "reserved"],
        )
        obligated = {pad for pads in contract["obligations"].values() for pad in pads}
        self.assertEqual(obligated, set(contract["net_mapping"]))
        self.assertEqual(contract["outline_mm"], [0, 0, 50, 40])
        self.assertEqual(contract["kicad_version"], "10.0.4")

    def test_initial_boards_are_pinned_and_unknown_variants_rejected(self):
        contract = json.loads(task.CONTRACT.read_text())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for variant in contract["variants"]:
                directory = root / variant["id"]
                task.prepare(directory, variant["id"])
                self.assertEqual(
                    harness.file_hash(directory / "candidate.kicad_pcb"),
                    variant["initial_board_sha256"],
                )
                self.assertEqual(
                    harness.file_hash(directory / "initial.kicad_pcb"),
                    variant["initial_board_sha256"],
                )
            with self.assertRaises(ValueError):
                task.prepare(root / "bad", "buck-dev-c")
            self.assertFalse((root / "bad").exists())

    def test_tampered_start_is_rejected_before_copy(self):
        contract = json.loads(task.CONTRACT.read_text())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "fixtures" / "buck-dev-a"
            shutil.copytree(task.FIXTURES / "buck-dev-a", source)
            (source / "candidate.kicad_pcb").write_bytes(b"tampered")
            with patch.object(task, "FIXTURES", root / "fixtures"):
                with self.assertRaises(ValueError):
                    task.prepare(root / "tampered", "buck-dev-a")
            self.assertFalse((root / "tampered").exists())
            _ = contract

    def test_staging_boards_carry_no_copper(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "trial"
            task.prepare(directory, "buck-dev-a")
            measured = harness.native(
                "measure", directory / "candidate.kicad_pcb", adapter=ADAPTER
            )
            self.assertEqual(measured["buck"]["tracks"], [])
            self.assertEqual(len(measured["buck"]["connectivity"]), 28)

    def test_protected_terminals_reject_moves_without_mutation(self):
        contract = json.loads(task.CONTRACT.read_text())
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "trial"
            task.prepare(directory, "buck-dev-a")
            session = task.Session(directory, contract, "buck-dev-a")
            before = harness.file_hash(session.board)
            try:
                self.assertEqual(
                    session.call(
                        "place",
                        {"reference": "J1", "x_mm": 4, "y_mm": 18, "angle_deg": 0},
                    )["status"],
                    "indeterminate",
                )
                self.assertEqual(harness.file_hash(session.board), before)
                self.assertEqual(session.edits, 0)
            finally:
                session.log.close()

    def test_asymmetric_rotation_oracle_uses_kicad_clockwise_convention(self):
        # C10.1 sits at local offset (-0.775, 0): dx != dy, so R(-45) and
        # R(+45) disagree by over a millimeter. Only pcbnew decides.
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "trial"
            task.prepare(directory, "buck-dev-a")
            board = directory / "candidate.kicad_pcb"
            before = harness.native("measure", board, adapter=ADAPTER)

            def positions(measured):
                fps = {f["reference"]: f for f in measured["footprints"]}
                pads = {
                    f["reference"] + "." + p["number"]: p["position_mm"]
                    for f in measured["footprints"]
                    for p in f["pads"]
                }
                return fps["C10"]["position_mm"], pads["C10.1"]

            origin, world0 = positions(before)
            local = [world0[0] - origin[0], world0[1] - origin[1]]
            self.assertNotAlmostEqual(abs(local[0]), abs(local[1]), places=3)
            task.mutate(board, "f['C10'].SetOrientationDegrees(45)")
            origin1, world1 = positions(
                harness.native("measure", board, adapter=ADAPTER)
            )
            self.assertAlmostEqual(origin1[0], origin[0], places=6)
            theta = math.radians(45)
            clockwise = [
                origin1[0] + local[0] * math.cos(theta) + local[1] * math.sin(theta),
                origin1[1] - local[0] * math.sin(theta) + local[1] * math.cos(theta),
            ]
            counter = [
                origin1[0] + local[0] * math.cos(theta) - local[1] * math.sin(theta),
                origin1[1] + local[0] * math.sin(theta) + local[1] * math.cos(theta),
            ]
            error_cw = math.dist(world1, clockwise)
            error_ccw = math.dist(world1, counter)
            self.assertLess(error_cw, 0.01)
            self.assertGreater(error_ccw, 1.0)

    def test_missing_buck_evidence_is_indeterminate(self):
        contract = json.loads(task.CONTRACT.read_text())
        packet = {
            "measurement": {
                "kicad_version": "10.0.4",
                "board_sha256": "0" * 64,
                "protected_sha256": "0" * 64,
                "footprints": [],
            },
            "contract": task.variant_contract(contract, "buck-dev-a"),
            "drc": {
                "$schema": "https://schemas.kicad.org/drc.v1.json",
                "coordinate_units": "mm",
                "source": "candidate.kicad_pcb",
                "kicad_version": "10.0.4",
                "violations": [],
                "unconnected_items": [],
                "ignored_checks": [],
                "included_severities": ["error", "warning", "exclusion"],
                "schematic_parity": [],
            },
        }
        process = subprocess.run(
            [str(harness.JUDGE)],
            input=json.dumps(packet),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(process.returncode, 2)
        self.assertEqual(json.loads(process.stdout)["status"], "indeterminate")
        broken = copy.deepcopy(packet)
        broken["measurement"]["protected_sha256"] = "short"
        process = subprocess.run(
            [str(harness.JUDGE)],
            input=json.dumps(broken),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(process.returncode, 2)


if __name__ == "__main__":
    unittest.main()
