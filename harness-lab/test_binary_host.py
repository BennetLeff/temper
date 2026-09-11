"""Focused host tests for the native binary waveform handoff."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import engineering_host
import simulation_host


class BinaryHostTests(unittest.TestCase):
    def collect_fixture(self, first_spec: dict, *, oversized: bool = False):
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("model.lib", "evidence.txt", "deck.cir"):
                (root / name).write_text("fixture")
            profiles = [
                {"id": "continuous_50mA_to_500mA", "low_a": 0.05, "high_a": 0.5},
                {"id": "pulse_50mA_to_1A", "low_a": 0.05, "high_a": 1.0},
            ]
            specs = [
                {"name": "startup", **first_spec},
                {"name": "input_variation"},
                *[{"name": "load_variation", "profile_id": p["id"]} for p in profiles],
            ]
            for spec in specs:
                spec.update(
                    deck="deck.cir",
                    deck_sha256=simulation_host._sha256(root / "deck.cir"),
                )
            requirements = json.dumps(
                {"requirements": [{"id": "load_step_endpoints", "profiles": profiles}]}
            )
            requirements_hash = hashlib.sha256(requirements.encode()).hexdigest()
            model_hash = simulation_host._sha256(root / "model.lib")
            model = {
                "path": "model.lib",
                "sha256": model_hash,
                "circuit_sha256": "a" * 64,
                "requirements_sha256": requirements_hash,
                "qualification": {
                    "evidence_path": "evidence.txt",
                    "evidence_sha256": simulation_host._sha256(root / "evidence.txt"),
                    "model_sha256": model_hash,
                },
                "scenarios": specs,
            }

            def fake_run(argv, **kwargs):
                if "-b" in argv:
                    calls.append((argv, kwargs))
                    path = Path(argv[argv.index("-r") + 1])
                    with path.open("wb") as stream:
                        if oversized and len(calls) == 1:
                            stream.truncate(8 * 1024**3 + 1)
                        else:
                            stream.write(b"native fixture bytes")
                return mock.Mock(returncode=0, stdout='{"status":"pass"}', stderr="")

            with (
                mock.patch.object(simulation_host.harness, "JUDGE", root / "judge"),
                mock.patch.object(
                    simulation_host.shutil, "which", return_value="ngspice"
                ),
                mock.patch.object(
                    simulation_host.subprocess, "run", side_effect=fake_run
                ),
                mock.patch.dict(os.environ, {"SPICE_ASCIIRAWFILE": "1"}),
            ):
                receipt = simulation_host.collect(
                    root,
                    root / "out",
                    model,
                    circuit_identity="a" * 64,
                    requirements_identity=requirements_hash,
                    requirements_manifest_text=requirements,
                    timeout_seconds=17,
                )
            return receipt, calls

    def test_binary_collection_uses_file_descriptor_and_reviewed_settings(self) -> None:
        receipt, calls = self.collect_fixture(
            {
                "raw_format": "ngspice-binary-le64",
                "timeout_seconds": 120,
                "max_step_s": 2e-8,
            }
        )
        self.assertEqual(receipt["status"], "collected")
        scenario = receipt["scenarios"][0]
        self.assertEqual(scenario["raw_file"], "startup/waveform.raw")
        self.assertNotIn("raw_waveform", scenario)
        self.assertEqual(
            scenario["artifact_sha256"],
            hashlib.sha256(b"native fixture bytes").hexdigest(),
        )
        self.assertIn("-n", calls[0][0])
        self.assertNotIn("SPICE_ASCIIRAWFILE", calls[0][1]["env"])
        self.assertEqual(calls[0][1]["timeout"], 120)
        self.assertEqual(calls[1][1]["timeout"], 17)
        self.assertEqual(calls[1][1]["env"]["SPICE_ASCIIRAWFILE"], "1")
        declared = json.loads(receipt["settings_manifest"])
        self.assertEqual(declared, [s["spec"] for s in receipt["scenarios"]])
        self.assertEqual(
            receipt["settings_sha256"], simulation_host._identity(declared)
        )

    def test_ascii_does_not_inherit_binary_runtime_override(self) -> None:
        receipt, calls = self.collect_fixture({"timeout_seconds": 9999})
        self.assertEqual(receipt["status"], "collected")
        self.assertEqual(calls[0][1]["timeout"], 17)
        self.assertIn("raw_waveform", receipt["scenarios"][0])

    def test_invalid_binary_settings_do_not_launch_simulator(self) -> None:
        for value in (0, -1, 3601, "120", float("inf")):
            with self.subTest(timeout=value):
                receipt, calls = self.collect_fixture(
                    {"raw_format": "ngspice-binary-le64", "timeout_seconds": value}
                )
                self.assertEqual(receipt["status"], "blocked")
                self.assertEqual(calls, [])
        receipt, calls = self.collect_fixture({"raw_format": "unknown"})
        self.assertEqual(receipt["findings"][0]["id"], "raw_format_invalid")
        self.assertEqual(calls, [])

    def test_oversized_binary_is_rejected_before_hashing(self) -> None:
        receipt, _ = self.collect_fixture(
            {"raw_format": "ngspice-binary-le64"}, oversized=True
        )
        self.assertEqual(receipt["scenarios"][0]["status"], "truncated")
        self.assertNotIn("artifact_sha256", receipt["scenarios"][0])

    def test_stream_hash_matches_sha256(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "large.raw"
            path.write_bytes(b"waveform" * 10000)
            self.assertEqual(
                simulation_host._sha256(path),
                hashlib.sha256(path.read_bytes()).hexdigest(),
            )

    def test_judge_sets_and_clears_trusted_binary_root(self) -> None:
        calls = []

        def fake_run(*args, **kwargs):
            calls.append(kwargs["env"])
            return mock.Mock(
                returncode=0, stdout=json.dumps({"status": "pass"}), stderr=""
            )

        with (
            mock.patch.object(engineering_host.subprocess, "run", side_effect=fake_run),
            mock.patch.dict(
                os.environ, {"TEMPER_SIMULATION_RAW_ROOT": "/untrusted-inherited-root"}
            ),
        ):
            with tempfile.TemporaryDirectory() as directory:
                engineering_host.judge(
                    {
                        "profile": "engineering-simulation",
                        "scenarios": [{"raw_file": "case/waveform.raw"}],
                    },
                    simulation_raw_root=Path(directory),
                )
            engineering_host.judge({"profile": "engineering"})

        self.assertEqual(
            calls[0]["TEMPER_SIMULATION_RAW_ROOT"], str(Path(directory).resolve())
        )
        self.assertNotIn("TEMPER_SIMULATION_RAW_ROOT", calls[1])


if __name__ == "__main__":
    unittest.main()
