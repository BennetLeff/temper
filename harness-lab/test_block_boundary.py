"""P1 U3 profile boundary tests: block judge decisions over synthetic input.

Drives the shared Rust dispatcher (``src/main.rs``) through the same stdin
path as the runner. Scenarios: a scripted valid MCU candidate passes while
removed ground, shorted IO, keepout intrusion, moved protected port, and a
hidden missing part fail; a 45-degree asymmetric footprint transform agrees
with KiCad (live pcbnew probe) and negative angles normalize; malformed or
capped native reports become indeterminate, never a zero-error pass; old
buck admission semantics are unchanged.
"""

from __future__ import annotations

import json
import math
import subprocess
import tempfile
import unittest
from pathlib import Path

import harness

ROOT = Path(__file__).parent
KICAD_VERSION = "10.0.4"
DIGEST = "ab" * 32


def judge(payload: dict, *, timeout: float = 10.0) -> tuple[int, dict]:
    binary = Path(harness.JUDGE)
    result = subprocess.run(
        [str(binary)],
        input=json.dumps(payload, allow_nan=False),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    try:
        answer = json.loads(result.stdout)
    except (ValueError, TypeError) as error:
        raise AssertionError(f"judge returned no JSON: {result.stderr!r}") from error
    return result.returncode, answer


def contract() -> dict:
    return {
        "profile": "block",
        "kicad_version": KICAD_VERSION,
        "protected_sha256": DIGEST,
        "outline_mm": [0.0, 0.0, 50.0, 40.0],
        "physical_copper_order": [
            "F.Cu",
            "In3.Cu",
            "In1.Cu",
            "In2.Cu",
            "In4.Cu",
            "B.Cu",
        ],
        "supported_layers": ["F.Cu", "B.Cu"],
        "allowed_copper_kinds": ["segment", "via", "zone"],
        "min_power_width_mm": 0.6,
        "min_signal_width_mm": 0.3,
        "power_nets": ["vcc"],
        "signal_nets": ["gnd"],
        "movable_refs": ["C1", "U1"],
        "protected_ports": {"J1": {"position_mm": [5.0, 5.0], "net": "vcc"}},
        "pad_census": {"C1": 2, "U1": 2, "J1": 1},
        "net_mapping": {
            "C1.1": "vcc",
            "C1.2": "gnd",
            "U1.1": "vcc",
            "U1.2": "gnd",
            "J1.1": "vcc",
        },
        "obligations": {"vcc": ["C1.1", "U1.1"], "gnd": ["C1.2", "U1.2"]},
        "boundary": {},
        "keepouts": [
            {"id": "antenna_keepout", "x1": 40.0, "y1": 30.0, "x2": 50.0, "y2": 40.0}
        ],
        "zone_nets": ["gnd"],
        "via_diameter_mm": 0.8,
        "via_drill_mm": 0.4,
    }


def footprint(reference: str, pads: list[tuple[str, str, list[float]]]) -> dict:
    return {
        "reference": reference,
        "position_mm": [10.0, 10.0],
        "angle_deg": 0.0,
        "bounds_mm": [8.0, 8.0, 12.0, 12.0],
        "pads": [
            {"number": number, "net": net, "position_mm": pos}
            for number, net, pos in pads
        ],
    }


def measurement() -> dict:
    return {
        "kicad_version": KICAD_VERSION,
        "board_sha256": DIGEST,
        "protected_sha256": DIGEST,
        "footprints": [
            footprint("U1", [("1", "vcc", [10.0, 10.0]), ("2", "gnd", [11.0, 10.0])]),
            footprint("C1", [("1", "vcc", [20.0, 10.0]), ("2", "gnd", [21.0, 10.0])]),
            {
                "reference": "J1",
                "position_mm": [5.0, 5.0],
                "angle_deg": 0.0,
                "bounds_mm": [4.0, 4.0, 6.0, 6.0],
                "pads": [{"number": "1", "net": "vcc", "position_mm": [5.0, 5.0]}],
            },
        ],
        "block": {
            "tracks": [
                {
                    "uuid": "t-vcc",
                    "kind": "segment",
                    "net": "vcc",
                    "layer": "F.Cu",
                    "width_mm": 0.6,
                    "start_mm": [20.0, 10.0],
                    "end_mm": [10.0, 10.0],
                    "bounds_mm": [10.0, 10.0, 20.0, 10.0],
                },
                {
                    "uuid": "t-gnd",
                    "kind": "segment",
                    "net": "gnd",
                    "layer": "B.Cu",
                    "width_mm": 0.3,
                    "start_mm": [21.0, 10.0],
                    "end_mm": [11.0, 10.0],
                    "bounds_mm": [11.0, 10.0, 21.0, 10.0],
                },
            ],
            "connectivity": [
                {"pad": "C1.1", "pads": ["C1.1", "U1.1"], "tracks": ["t-vcc"]},
                {"pad": "U1.1", "pads": ["C1.1", "U1.1"], "tracks": ["t-vcc"]},
                {"pad": "C1.2", "pads": ["C1.2", "U1.2"], "tracks": ["t-gnd"]},
                {"pad": "U1.2", "pads": ["C1.2", "U1.2"], "tracks": ["t-gnd"]},
                {"pad": "J1.1", "pads": ["J1.1"], "tracks": []},
            ],
        },
    }


def drc() -> dict:
    return {
        "$schema": "https://schemas.kicad.org/drc.v1.json",
        "coordinate_units": "mm",
        "source": "candidate.kicad_pcb",
        "kicad_version": KICAD_VERSION,
        "violations": [],
        "unconnected_items": [],
        "ignored_checks": [],
        "included_severities": ["error", "warning", "exclusion"],
        "schematic_parity": [],
    }


def finding_ids(answer: dict) -> list[str]:
    return [finding["id"] for finding in answer.get("findings", [])]


class BlockBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assertTrue(
            Path(harness.JUDGE).is_file(),
            "harness judge is not built; run `cargo build --locked` in harness-lab",
        )

    def evaluate(self, m: dict, c: dict | None = None) -> tuple[int, dict]:
        return judge({"measurement": m, "contract": c or contract(), "drc": drc()})

    def test_valid_candidate_passes(self) -> None:
        code, answer = self.evaluate(measurement())
        self.assertEqual(code, 0, answer)
        self.assertEqual(answer["status"], "pass", answer)
        self.assertEqual(answer.get("findings"), [])

    def test_removed_ground_fails_unrouted(self) -> None:
        m = measurement()
        for cluster in m["block"]["connectivity"]:
            if cluster["pad"] in ("C1.2", "U1.2"):
                cluster["pads"] = [cluster["pad"]]
                cluster["tracks"] = []
        m["block"]["tracks"] = [t for t in m["block"]["tracks"] if t["uuid"] != "t-gnd"]
        code, answer = self.evaluate(m)
        self.assertEqual(answer["status"], "fail", answer)
        self.assertTrue(
            any(i.startswith("unrouted:") for i in finding_ids(answer)), answer
        )

    def test_shorted_io_fails(self) -> None:
        m = measurement()
        for cluster in m["block"]["connectivity"]:
            if cluster["pad"] in ("C1.1", "U1.1"):
                cluster["pads"] = ["C1.1", "U1.1", "U1.2"]
        code, answer = self.evaluate(m)
        self.assertEqual(answer["status"], "fail", answer)
        self.assertTrue(
            any(i.startswith("shorted_cluster:") for i in finding_ids(answer)), answer
        )

    def test_keepout_intrusion_fails(self) -> None:
        m = measurement()
        for fp in m["footprints"]:
            if fp["reference"] == "C1":
                fp["bounds_mm"] = [41.0, 31.0, 43.0, 33.0]
        code, answer = self.evaluate(m)
        self.assertEqual(answer["status"], "fail", answer)
        self.assertTrue(
            any(i.startswith("keepout_intrusion:") for i in finding_ids(answer)), answer
        )

    def test_moved_protected_port_fails(self) -> None:
        m = measurement()
        for fp in m["footprints"]:
            if fp["reference"] == "J1":
                fp["position_mm"] = [6.0, 5.0]
        code, answer = self.evaluate(m)
        self.assertEqual(answer["status"], "fail", answer)
        self.assertIn("protected_port_moved:J1", finding_ids(answer))

    def test_hidden_missing_part_fails(self) -> None:
        m = measurement()
        m["footprints"] = [fp for fp in m["footprints"] if fp["reference"] != "C1"]
        code, answer = self.evaluate(m)
        self.assertEqual(code, 0, answer)
        self.assertEqual(answer["status"], "fail", answer)
        self.assertIn("missing_footprint:C1", finding_ids(answer))

    def test_negative_angle_normalizes_without_finding(self) -> None:
        m = measurement()
        for fp in m["footprints"]:
            if fp["reference"] == "C1":
                fp["angle_deg"] = -90.0
        code, answer = self.evaluate(m)
        self.assertEqual(code, 0, answer)
        self.assertEqual(answer["status"], "pass", answer)

    def test_non_orthogonal_angle_fails(self) -> None:
        m = measurement()
        for fp in m["footprints"]:
            if fp["reference"] == "C1":
                fp["angle_deg"] = 45.0
        code, answer = self.evaluate(m)
        self.assertEqual(answer["status"], "fail", answer)
        self.assertIn("unsupported_orientation:C1", finding_ids(answer))

    def test_missing_native_report_is_indeterminate(self) -> None:
        m = measurement()
        del m["block"]
        code, answer = self.evaluate(m)
        self.assertEqual(code, 2, answer)
        self.assertEqual(answer["status"], "indeterminate", answer)

    def test_truncated_connectivity_cannot_pass(self) -> None:
        m = measurement()
        m["block"]["connectivity"] = [
            c for c in m["block"]["connectivity"] if c["pad"] != "U1.2"
        ]
        code, answer = self.evaluate(m)
        self.assertNotEqual(answer.get("status"), "pass", answer)

    def test_asymmetric_transform_agrees_with_kicad_live(self) -> None:
        """Live pcbnew probe: (dx,dy)=(10,4) at 45deg must land at the
        R(-theta) answer, ruling out the standard-math R(+theta) mirror."""
        fixture = ROOT / "fixtures" / "buck" / "buck-dev-a" / "candidate.kicad_pcb"
        self.assertTrue(fixture.is_file(), "buck fixture board missing")
        with tempfile.TemporaryDirectory(prefix="temper-block-oracle-") as tmp:
            board = Path(tmp) / "probe.kicad_pcb"
            board.write_bytes(fixture.read_bytes())
            script = (
                "import json, math, pcbnew; "
                "b = pcbnew.PCB_IO_KICAD_SEXPR().LoadBoard(r'"
                + str(board)
                + "', None); "
                "fps = {f.GetReference(): f for f in b.GetFootprints()}; "
                "fp = fps['C9']; "
                "fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(30), pcbnew.FromMM(20))); "
                "fp.SetOrientationDegrees(0); "
                "pad = next(p for p in fp.Pads() if p.GetNumber() == '1'); "
                "w0 = list(pcbnew.ToMM(pad.GetPosition())); "
                "fp.SetOrientationDegrees(45); "
                "w1 = list(pcbnew.ToMM(pad.GetPosition())); "
                "print(json.dumps({'pos': list(pcbnew.ToMM(fp.GetPosition())), 'w0': w0, 'w1': w1}))"
            )
            result = subprocess.run(
                [harness.KICAD_PYTHON, "-c", script],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr[-2000:])
            observed = json.loads(result.stdout)
        pos, w0, w1 = observed["pos"], observed["w0"], observed["w1"]
        dx, dy = w0[0] - pos[0], w0[1] - pos[1]
        self.assertGreater(abs(dx - dy), 0.5, (observed, "probe must be asymmetric"))
        theta = math.radians(45.0)
        expected = [
            pos[0] + dx * math.cos(theta) + dy * math.sin(theta),
            pos[1] - dx * math.sin(theta) + dy * math.cos(theta),
        ]
        wrong = [
            pos[0] + dx * math.cos(theta) - dy * math.sin(theta),
            pos[1] + dx * math.sin(theta) + dy * math.cos(theta),
        ]
        got = [w1[0] - expected[0], w1[1] - expected[1]]
        self.assertLess(
            abs(got[0]) + abs(got[1]),
            abs(w1[0] - wrong[0]) + abs(w1[1] - wrong[1]),
            (observed, expected, wrong),
        )
        self.assertLess(abs(got[0]) + abs(got[1]), 0.01, (observed, expected))

    def test_two_layer_runner_control_geometry_evaluates(self) -> None:
        c = contract()
        c["physical_copper_order"] = ["F.Cu", "B.Cu"]
        code, answer = self.evaluate(measurement(), c)
        self.assertEqual(code, 0, answer)
        self.assertEqual(answer["status"], "pass", answer)

    def test_block_operation_schema_has_five_tools(self) -> None:
        code, answer = judge(
            {"profile": "block-operation", "operation": "schema", "arguments": {}}
        )
        self.assertEqual(code, 0, answer)
        self.assertEqual(len(answer["tools"]), 5, answer)
        self.assertIn("start_mm", json.dumps(answer))

    def test_block_operation_rejects_without_task_context(self) -> None:
        code, answer = judge(
            {
                "profile": "block-operation",
                "operation": "place",
                "arguments": {
                    "reference": "U1",
                    "x_mm": 30,
                    "y_mm": 40,
                    "angle_deg": 0,
                },
            }
        )
        self.assertEqual(answer["status"], "invalid", answer)

    def test_buck_admission_semantics_unchanged(self) -> None:
        code, answer = judge(
            {
                "profile": "buck-operation",
                "operation": "place",
                "arguments": {
                    "reference": "J1",
                    "x_mm": 1,
                    "y_mm": 1,
                    "angle_deg": 0,
                },
            }
        )
        self.assertEqual(answer["status"], "invalid", answer)
        markers = ("block-operation", "block_native", "block.rs", "block::")
        for path in (
            "src/buck.rs",
            "src/buck_operations.rs",
            "src/routing.rs",
            "buck_host.py",
            "buck_native.py",
            "qualify_buck.py",
        ):
            text = (ROOT / path).read_text()
            for marker in markers:
                self.assertNotIn(
                    marker, text, f"block profile leaked into buck owner {path}"
                )


if __name__ == "__main__":
    unittest.main()
