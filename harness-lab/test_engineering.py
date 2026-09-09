"""Focused subprocess controls for the Rust engineering judge."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import harness  # noqa: E402

ROOT = Path(__file__).parent


class EngineeringControls(unittest.TestCase):
    def run_judge(self, payload: dict) -> dict:
        proc = subprocess.run(
            [str(harness.JUDGE)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertTrue(proc.stdout, proc.stderr)
        return json.loads(proc.stdout)

    def test_real_manifest_keeps_unresolved_inputs_visible(self) -> None:
        requirements = json.loads((ROOT / "engineering/requirements.json").read_text())
        result = self.run_judge(
            {"profile": "engineering", "requirements": requirements}
        )
        self.assertEqual(result["status"], "blocked")
        self.assertFalse(result["hardware_validated"])
        self.assertEqual(result["stages"][-1]["status"], "not_run")

    def test_wrong_profile_is_rejected(self) -> None:
        requirements = json.loads((ROOT / "engineering/requirements.json").read_text())
        proc = subprocess.run(
            [str(harness.JUDGE)],
            input=json.dumps({"profile": "wrong", "requirements": requirements}),
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertNotEqual(proc.returncode, 0)


if __name__ == "__main__":
    unittest.main()
