import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import run_scenarios


def _measurements(names, *, nonfinite=None):
    lines = []
    for name in names:
        value = "nan" if name == nonfinite else "1.0"
        lines.append(f"{name} = {value}")
    return "\n".join(lines) + "\n"


class ScenarioRunnerTests(unittest.TestCase):
    def _fake_simulator(self, output, log_text=None, timeout=False):
        def fake_run(command, **kwargs):
            if command[-1] == "--version":
                return SimpleNamespace(stdout="ngspice-test\n")
            if timeout:
                raise subprocess.TimeoutExpired(command, kwargs["timeout"])
            kwargs["stdout"].write(log_text or "")
            Path(kwargs["cwd"], "waveform.raw").write_bytes(b"raw")
            return SimpleNamespace(returncode=0)

        return fake_run

    def test_success_requires_and_records_all_finite_measurements(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "run"
            log = _measurements(run_scenarios.MEASUREMENT_NAMES)
            fake_run = self._fake_simulator(output, log_text=log)
            with (
                patch.object(run_scenarios.shutil, "which", return_value="ngspice"),
                patch.object(run_scenarios.subprocess, "run", side_effect=fake_run),
            ):
                run_scenarios.run(output, ["startup"], 20)

            receipt = json.loads((output / "receipt.json").read_text())
            item = receipt["runs"][0]
            self.assertEqual(item["missing_measurements"], [])
            self.assertEqual(set(item["measurements"]), set(run_scenarios.MEASUREMENT_NAMES))
            self.assertNotIn("failures", item)

    def test_missing_or_nonfinite_measurement_is_recorded_before_raise(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "run"
            log = _measurements(
                run_scenarios.MEASUREMENT_NAMES[:-1],
                nonfinite=run_scenarios.MEASUREMENT_NAMES[-2],
            )
            fake_run = self._fake_simulator(output, log_text=log)
            with (
                patch.object(run_scenarios.shutil, "which", return_value="ngspice"),
                patch.object(run_scenarios.subprocess, "run", side_effect=fake_run),
            ):
                with self.assertRaises(RuntimeError):
                    run_scenarios.run(output, ["startup"], 20)

            item = json.loads((output / "receipt.json").read_text())["runs"][0]
            self.assertIn("missing or non-finite native measurements", item["failures"])
            self.assertIn(run_scenarios.MEASUREMENT_NAMES[-2], item["missing_measurements"])
            self.assertIn(run_scenarios.MEASUREMENT_NAMES[-1], item["missing_measurements"])
            self.assertTrue((output / "startup" / "simulator.log").is_file())
            self.assertTrue((output / "startup" / "waveform.raw").is_file())

    def test_timeout_is_recorded_before_raise_and_artifacts_remain(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "run"
            fake_run = self._fake_simulator(output, timeout=True)
            with (
                patch.object(run_scenarios.shutil, "which", return_value="ngspice"),
                patch.object(run_scenarios.subprocess, "run", side_effect=fake_run),
            ):
                with self.assertRaises(RuntimeError):
                    run_scenarios.run(output, ["startup"], 20)

            item = json.loads((output / "receipt.json").read_text())["runs"][0]
            self.assertTrue(item["timed_out"])
            self.assertIn("simulator timeout", item["failures"])
            self.assertIsNone(item["returncode"])
            self.assertTrue((output / "startup" / "bench.cir").is_file())
            self.assertTrue((output / "startup" / "simulator.log").is_file())


if __name__ == "__main__":
    unittest.main()
