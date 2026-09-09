"""Fail-closed tests for the U8 simulation boundary."""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

import simulation_host


class SimulationHostTests(unittest.TestCase):
    def test_missing_exact_model_is_blocked(self) -> None:
        import tempfile

        receipt = simulation_host.collect(
            Path(__file__).parents[1], Path(tempfile.mkdtemp()) / "out"
        )
        self.assertEqual(receipt["status"], "blocked")
        self.assertEqual(receipt["findings"][0]["id"], "exact_model_missing")
        self.assertEqual(receipt["scenarios"], [])

    def test_legacy_average_model_is_rejected(self) -> None:
        import tempfile

        tmp_path = Path(tempfile.mkdtemp())
        model = tmp_path / "legacy.json"
        model.write_text(
            json.dumps(
                {
                    "mpn": "LMR51430XDDCR",
                    "path": "simulation/models/LMR51430_avg.lib",
                    "qualified": True,
                    "reference_voltage": 0.8,
                }
            )
        )
        receipt = simulation_host.collect(
            Path(__file__).parents[1], tmp_path / "out", model
        )
        self.assertEqual(receipt["status"], "blocked")
        self.assertTrue(
            any(f["id"] == "legacy_model_rejected" for f in receipt["findings"])
        )

    def test_unqualified_exact_model_does_not_run(self) -> None:
        import tempfile

        tmp_path = Path(tempfile.mkdtemp())
        model_file = tmp_path / "model.lib"
        model_file.write_text("* fixture")
        model = tmp_path / "model.json"
        model.write_text(
            json.dumps(
                {
                    "mpn": "LMR51430XDDCR",
                    "path": str(model_file),
                    "qualified": False,
                }
            )
        )
        receipt = simulation_host.collect(
            Path(__file__).parents[1], tmp_path / "out", model
        )
        self.assertEqual(receipt["status"], "blocked")
        self.assertEqual(receipt["scenarios"], [])

    def test_model_artifact_paths_cannot_escape_repository(self) -> None:
        import tempfile

        for path in ("/tmp/model.lib", "../model.lib"):
            with tempfile.TemporaryDirectory() as output:
                receipt = simulation_host.collect(
                    Path(__file__).parents[1],
                    Path(output) / "run",
                    {"mpn": "LMR51430XDDCR", "path": path, "sha256": "a" * 64},
                )
                self.assertEqual(receipt["status"], "blocked")
                self.assertIn("artifact paths", receipt["findings"][0]["message"])

    def test_identity_hash_is_stable(self) -> None:
        self.assertEqual(
            simulation_host._identity({"b": 2, "a": 1}),
            hashlib.sha256(b'{"a":1,"b":2}').hexdigest(),
        )
