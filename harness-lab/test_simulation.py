"""Fail-closed tests for the U8 simulation boundary."""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from unittest import mock

import simulation_host


class SimulationHostTests(unittest.TestCase):
    def test_four_flat_specs_use_distinct_load_profile_folders(self) -> None:
        import tempfile

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in (
                "model.lib",
                "evidence.txt",
                "start.cir",
                "input.cir",
                "load500.cir",
                "load1a.cir",
            ):
                (root / name).write_text("fixture")
            profiles = (
                {"id": "continuous_50mA_to_500mA", "low_a": 0.05, "high_a": 0.5},
                {"id": "pulse_50mA_to_1A", "low_a": 0.05, "high_a": 1.0},
            )
            specs = [
                {
                    "name": "startup",
                    "deck": "start.cir",
                    "deck_sha256": simulation_host._sha256(root / "start.cir"),
                },
                {
                    "name": "input_variation",
                    "deck": "input.cir",
                    "deck_sha256": simulation_host._sha256(root / "input.cir"),
                },
                {
                    "name": "load_variation",
                    "profile_id": profiles[0]["id"],
                    "load_low_a": 0.05,
                    "load_high_a": 0.5,
                    "deck": "load500.cir",
                    "deck_sha256": simulation_host._sha256(root / "load500.cir"),
                },
                {
                    "name": "load_variation",
                    "profile_id": profiles[1]["id"],
                    "load_low_a": 0.05,
                    "load_high_a": 1.0,
                    "deck": "load1a.cir",
                    "deck_sha256": simulation_host._sha256(root / "load1a.cir"),
                },
            ]
            model = {
                "mpn": "LMR51430XDDCR",
                "path": "model.lib",
                "sha256": simulation_host._sha256(root / "model.lib"),
                "reference_voltage": 0.6,
                "frequency_hz": 500000,
                "mode": "PFM",
                "circuit_sha256": "a" * 64,
                "requirements_sha256": "b" * 64,
                "qualification": {
                    "model_sha256": "a" * 64,
                    "evidence_path": "evidence.txt",
                    "evidence_sha256": simulation_host._sha256(root / "evidence.txt"),
                    "source": "fixture",
                    "license": "fixture",
                    "reviewed_by": "fixture",
                    "status": "pass",
                },
                "scenarios": specs,
            }
            model["qualification"]["model_sha256"] = model["sha256"]
            manifest = root / "model.json"
            req = json.dumps(
                {"requirements": [{"id": "load_step_endpoints", "profiles": profiles}]}
            )
            req_hash = hashlib.sha256(req.encode()).hexdigest()
            model["requirements_sha256"] = req_hash
            manifest.write_text(json.dumps(model))

            def fake_run(argv, **kwargs):
                if argv[0] == str(root / "judge"):
                    return mock.Mock(
                        returncode=0, stdout=json.dumps({"status": "pass"}), stderr=""
                    )
                if argv == ["ngspice", "--version"]:
                    return mock.Mock(returncode=0, stdout="ngspice fixture", stderr="")
                raw = Path(argv[argv.index("-r") + 1])
                raw.write_text("fixture raw")
                return mock.Mock(returncode=0, stdout="", stderr="")

            with (
                mock.patch.object(simulation_host.harness, "JUDGE", root / "judge"),
                mock.patch.object(
                    simulation_host.shutil, "which", return_value="ngspice"
                ),
                mock.patch.object(
                    simulation_host.subprocess, "run", side_effect=fake_run
                ),
            ):
                receipt = simulation_host.collect(
                    root,
                    root / "out",
                    manifest,
                    circuit_identity="a" * 64,
                    requirements_identity=req_hash,
                    requirements_manifest_text=req,
                )
            self.assertEqual(receipt["status"], "collected")
            self.assertEqual(receipt["requirements_manifest"], req)
            self.assertEqual(receipt["requirements_sha256"], req_hash)
            folders = {p.name for p in (root / "out").iterdir()}
            self.assertIn(
                "load_variation-"
                + hashlib.sha256(profiles[0]["id"].encode()).hexdigest()[:16],
                folders,
            )
            self.assertIn(
                "load_variation-"
                + hashlib.sha256(profiles[1]["id"].encode()).hexdigest()[:16],
                folders,
            )

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
