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

import buck_host
import harness
import qualify_buck as task
from qualify_buck import ADAPTER


class BuckBoundaryTests(unittest.TestCase):
    def _prepared(self, root: Path, *, witness: bool = False) -> Path:
        directory = root / "trial"
        task.prepare(directory, "buck-dev-a")
        if witness:
            shutil.copyfile(
                directory / "witness.kicad_pcb", directory / "candidate.kicad_pcb"
            )
        return directory

    def test_full_buck_public_surface_and_nested_schema_are_rust_owned(self):
        self.assertEqual(
            [tool["name"] for tool in buck_host.TOOLS],
            ["inspect", "check", "place", "replace_copper", "execute"],
        )
        self.assertEqual(
            (buck_host.MAX_ACTIONS, buck_host.MAX_SECONDS, buck_host.MAX_OBJECTS),
            (200, 1200.0, 512),
        )
        replace = next(
            tool for tool in buck_host.TOOLS if tool["name"] == "replace_copper"
        )["inputSchema"]
        self.assertEqual(
            replace["properties"]["segments"]["items"]["properties"]["start_mm"][
                "minItems"
            ],
            2,
        )
        self.assertEqual(
            replace["properties"]["vias"]["items"]["properties"]["diameter_mm"][
                "const"
            ],
            0.8,
        )

    def test_full_buck_malformed_nested_requests_are_invalid_and_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = self._prepared(Path(tmp))
            before = harness.file_hash(directory / "candidate.kicad_pcb")
            session = buck_host.Session(directory, "buck-dev-a")
            try:
                unknown = session.call(
                    "replace_copper",
                    {
                        "net": "gnd",
                        "segments": [
                            {
                                "start_mm": [0, 0],
                                "end_mm": [1, 1],
                                "layer": "F.Cu",
                                "width_mm": 0.5,
                                "unknown": 1,
                            }
                        ],
                        "vias": [],
                        "zones": [],
                    },
                )
                nan = session.call(
                    "replace_copper",
                    {
                        "net": "gnd",
                        "segments": [
                            {
                                "start_mm": [0, float("nan")],
                                "end_mm": [1, 1],
                                "layer": "F.Cu",
                                "width_mm": 0.5,
                            }
                        ],
                        "vias": [],
                        "zones": [],
                    },
                )
                self.assertEqual(
                    (unknown["status"], nan["status"]), ("invalid", "invalid")
                )
                self.assertEqual(
                    harness.file_hash(directory / "candidate.kicad_pcb"), before
                )
                self.assertIn(
                    "invalid_number_repr", (directory / "operations.jsonl").read_text()
                )
                rows = [
                    json.loads(line)
                    for line in (directory / "operations.jsonl")
                    .read_text()
                    .splitlines()
                ]
                responses = [row for row in rows if row["kind"] == "response"]
                self.assertEqual(len(responses), 2)
                self.assertEqual(responses[-1]["result"]["sequence"], 2)
                self.assertIn("elapsed_s", responses[-1]["result"])
            finally:
                session.close()

    def test_full_buck_native_failure_rolls_back_and_is_indeterminate(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = self._prepared(Path(tmp))
            board = directory / "candidate.kicad_pcb"
            before = board.read_bytes()
            with patch.object(
                buck_host.Session, "_native", side_effect=RuntimeError("native crash")
            ):
                session = buck_host.Session(directory, "buck-dev-a")
                try:
                    result = session.call(
                        "place",
                        {"reference": "C9", "x_mm": 10, "y_mm": 10, "angle_deg": 0},
                    )
                    self.assertEqual(result["status"], "indeterminate")
                    self.assertEqual(board.read_bytes(), before)
                    self.assertEqual(session.actions, 0)
                    self.assertTrue((directory / "state-000001.kicad_pcb").exists())
                    self.assertTrue(
                        (directory / "attempt-000001" / "candidate.kicad_pcb").exists()
                    )
                    terminal = session.call(
                        "place",
                        {"reference": "C9", "x_mm": 11, "y_mm": 11, "angle_deg": 0},
                    )
                    self.assertEqual(terminal["status"], "indeterminate")
                    self.assertEqual(session.actions, 0)
                finally:
                    session.close()

    def test_full_buck_placement_leaves_existing_copper_stationary(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = self._prepared(Path(tmp), witness=True)
            before = harness.native(
                "measure", directory / "candidate.kicad_pcb", adapter=ADAPTER
            )["buck"]["tracks"]
            session = buck_host.Session(directory, "buck-dev-a")
            try:
                result = session.call(
                    "place", {"reference": "C9", "x_mm": 15, "y_mm": 20, "angle_deg": 0}
                )
                self.assertIn(result["status"], ("pass", "fail"))
                self.assertIn("drc", result)
                self.assertIn("rust", result)
                self.assertEqual(session.actions, 1)
                self.assertTrue(result["mutation_committed"])
                self.assertEqual(result["mutation_index"], 1)
                self.assertEqual(result["native_verdict"], result["status"])
                after = result["measurement"]["buck"]["tracks"]
                self.assertEqual(
                    sorted(
                        (t["uuid"], t["net"], t["start_mm"], t["end_mm"])
                        for t in before
                    ),
                    sorted(
                        (t["uuid"], t["net"], t["start_mm"], t["end_mm"]) for t in after
                    ),
                )
            finally:
                session.close()

    def test_full_buck_replace_one_net_preserves_other_nets(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = self._prepared(Path(tmp), witness=True)
            before = harness.native(
                "measure", directory / "candidate.kicad_pcb", adapter=ADAPTER
            )["buck"]["tracks"]
            session = buck_host.Session(directory, "buck-dev-a")
            try:
                before_revision = session.revision
                result = session.call(
                    "replace_copper",
                    {"net": "sw", "segments": [], "vias": [], "zones": []},
                )
                self.assertIn(result["status"], ("pass", "fail"))
                self.assertIn("drc", result)
                self.assertIn("rust", result)
                self.assertEqual(session.actions, 1)
                self.assertNotEqual(session.revision, before_revision)
                after = result["measurement"]["buck"]["tracks"]
                before_other = sorted(
                    (t["uuid"], t["net"], t["start_mm"], t["end_mm"])
                    for t in before
                    if t["net"] != "sw"
                )
                after_other = sorted(
                    (t["uuid"], t["net"], t["start_mm"], t["end_mm"])
                    for t in after
                    if t["net"] != "sw"
                )
                self.assertEqual(before_other, after_other)
                self.assertEqual([t for t in after if t["net"] == "sw"], [])
            finally:
                session.close()

    def test_full_buck_replace_copper_uses_native_zone_and_through_via(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = self._prepared(Path(tmp))
            session = buck_host.Session(directory, "buck-dev-a")
            try:
                result = session.call(
                    "replace_copper",
                    {
                        "net": "gnd",
                        "segments": [
                            {
                                "start_mm": [8.8625, 29.05],
                                "end_mm": [12, 29.05],
                                "layer": "B.Cu",
                                "width_mm": 0.6,
                            }
                        ],
                        "vias": [
                            {
                                "position_mm": [8.8625, 29.05],
                                "diameter_mm": 0.8,
                                "drill_mm": 0.4,
                            },
                            {
                                "position_mm": [12, 29.05],
                                "diameter_mm": 0.8,
                                "drill_mm": 0.4,
                            },
                        ],
                        "zones": [
                            {
                                "layer": "B.Cu",
                                "outline_mm": [[5, 5], [45, 5], [45, 35], [5, 35]],
                            }
                        ],
                    },
                )
                self.assertIn(result["status"], ("pass", "fail"))
                self.assertIn("drc", result)
                self.assertIn("rust", result)
                tracks = result["measurement"]["buck"]["tracks"]
                self.assertEqual(
                    {item["kind"] for item in tracks}, {"segment", "via", "zone"}
                )
                zone = next(item for item in tracks if item["kind"] == "zone")
                self.assertTrue(zone["filled"])
                self.assertGreater(zone["filled_area_mm2"], 0)
                self.assertTrue(
                    any(
                        "U3.1" in cluster["pads"] and cluster["tracks"]
                        for cluster in result["measurement"]["buck"]["connectivity"]
                    )
                )
                self.assertEqual(
                    next(item for item in tracks if item["kind"] == "via")["layer"],
                    "F.Cu-B.Cu",
                )
            finally:
                session.close()

    def test_full_buck_protected_terminal_and_stale_external_state_reject(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = self._prepared(Path(tmp))
            session = buck_host.Session(directory, "buck-dev-a")
            try:
                before = session.revision
                protected = session.call(
                    "place", {"reference": "J1", "x_mm": 4, "y_mm": 18, "angle_deg": 0}
                )
                self.assertEqual(protected["status"], "invalid")
                self.assertEqual(session.revision, before)
                (directory / "candidate.kicad_pcb").write_bytes(b"external")
                stale = session.call("inspect", {})
                self.assertEqual(stale["status"], "invalid")
            finally:
                session.close()

        with tempfile.TemporaryDirectory() as tmp:
            directory = self._prepared(Path(tmp))
            session = buck_host.Session(directory, "buck-dev-a")
            try:
                before = session.revision
                (directory / "candidate.kicad_dru").write_text("external rules")
                context_stale = session.call(
                    "place", {"reference": "C9", "x_mm": 10, "y_mm": 10, "angle_deg": 0}
                )
                self.assertEqual(context_stale["status"], "invalid")
                self.assertEqual(session.revision, before)
            finally:
                session.close()

    def test_full_buck_shared_budget_is_one_public_counter(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = self._prepared(Path(tmp))
            fake_measure = {
                "protected_sha256": json.loads(task.CONTRACT.read_text())["variants"][
                    0
                ]["protected_sha256"]
            }
            with (
                patch.object(buck_host.Session, "_native"),
                patch.object(
                    buck_host.Session,
                    "_check_stage",
                    return_value={
                        "status": "pass",
                        "measurement": fake_measure,
                        "drc": {},
                        "rust": {"status": "pass"},
                    },
                ),
            ):
                session = buck_host.Session(directory, "buck-dev-a")
                try:
                    for _ in range(buck_host.MAX_ACTIONS):
                        self.assertEqual(
                            session.call(
                                "place",
                                {
                                    "reference": "C9",
                                    "x_mm": 10,
                                    "y_mm": 10,
                                    "angle_deg": 0,
                                },
                            )["status"],
                            "pass",
                        )
                    self.assertEqual(
                        session.call(
                            "place",
                            {"reference": "C9", "x_mm": 10, "y_mm": 10, "angle_deg": 0},
                        )["status"],
                        "invalid",
                    )
                    self.assertEqual(session.actions, buck_host.MAX_ACTIONS)
                finally:
                    session.close()

    def test_full_buck_witness_replays_through_public_operations(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = self._prepared(Path(tmp))
            witness = harness.native(
                "measure", directory / "witness.kicad_pcb", adapter=ADAPTER
            )
            session = buck_host.Session(directory, "buck-dev-a")
            try:
                initial = session.call("inspect", {})
                self.assertEqual(initial["measurement"]["buck"]["tracks"], [])
                self.assertIsNone(initial["native_verdict"])
                for fp in witness["footprints"]:
                    if fp["reference"] in task.FUNCTIONAL_REFS:
                        self.assertTrue(
                            session.call(
                                "place",
                                {
                                    "reference": fp["reference"],
                                    "x_mm": fp["position_mm"][0],
                                    "y_mm": fp["position_mm"][1],
                                    "angle_deg": int(fp["angle_deg"]),
                                },
                            )["mutation_committed"],
                        )
                for net in task.NETS:
                    copper = [
                        item for item in witness["buck"]["tracks"] if item["net"] == net
                    ]
                    segments = [
                        {
                            k: item[k]
                            for k in ("start_mm", "end_mm", "layer", "width_mm")
                        }
                        for item in copper
                        if item["kind"] == "segment"
                    ]
                    vias = [
                        {
                            "position_mm": item["start_mm"],
                            "diameter_mm": 0.8,
                            "drill_mm": 0.4,
                        }
                        for item in copper
                        if item["kind"] == "via"
                    ]
                    result = session.call(
                        "replace_copper",
                        {"net": net, "segments": segments, "vias": vias, "zones": []},
                    )
                    self.assertTrue(result["mutation_committed"], result)
                checked = session.call("check", {})
                self.assertEqual(checked["status"], "pass", checked)
                self.assertEqual(session.actions, 15)
                original = session.board.read_bytes()
                again = session.call("check", {})
                self.assertEqual(again["status"], "pass", again)
                self.assertEqual(again["measurement"]["board_sha256"], session.revision)
                self.assertEqual(session.board.read_bytes(), original)
                self.assertNotEqual(again["sequence"], checked["sequence"])
                rows = [
                    json.loads(line)
                    for line in (directory / "operations.jsonl")
                    .read_text()
                    .splitlines()
                ]
                self.assertEqual(rows[-1]["result"], again)
                self.assertIsInstance(rows[-1]["result"]["elapsed_s"], float)
            finally:
                session.close()

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
