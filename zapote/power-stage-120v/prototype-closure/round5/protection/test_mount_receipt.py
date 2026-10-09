"""Reject the historical HS400 mounting-pitch error in the replay gate."""

import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import freeze_evidence


class MountReceiptTest(unittest.TestCase):
    def test_old_pitch_invalidates_success(self) -> None:
        original = freeze_evidence.OUT
        # The receipt records repository-relative paths, so isolate inside its
        # output directory. Never change the live CAD or its successful receipt.
        with tempfile.TemporaryDirectory(prefix="mount-test-", dir=original) as scratch:
            destination = Path(scratch)
            for name in (
                "hardware-geometry.json",
                "calculation-status.json",
                "calculation-tests.txt",
            ):
                shutil.copy2(original / name, destination / name)
            with patch.object(freeze_evidence, "OUT", destination):
                with contextlib.redirect_stdout(io.StringIO()):
                    freeze_evidence.main()
                result = destination / "replay.json"
                self.assertEqual(
                    json.loads(result.read_text())["status"],
                    "REPRODUCED_WITH_ENGINEERING_HOLDS",
                )
                receipt = destination / "hardware-geometry.json"
                value = json.loads(receipt.read_text())
                value["precharge_mount_holes_xz_d_mm"][1][1] -= 0.3
                receipt.write_text(json.dumps(value))
                with self.assertRaisesRegex(ValueError, "45 mm transverse pitch"):
                    freeze_evidence.main()
                self.assertEqual(json.loads(result.read_text())["status"], "INCOMPLETE")


if __name__ == "__main__":
    unittest.main()
