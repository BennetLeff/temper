"""
TDD Test for PCB Renderer.

Verifies command generation for kicad-cli export.
"""

import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import os

# We will create this module later
# import temper_placer.io.render as render


class TestPCBRenderer(unittest.TestCase):
    def test_export_svg_command(self):
        """Verify kicad-cli command arguments."""
        pcb_path = Path("test.kicad_pcb")
        output_dir = Path("output")
        layers = ["F.Cu", "B.Cu"]

        # Mock subprocess.run
        with patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0

            # Import function inside test to allow TDD implementation later
            from temper_placer.io.render import export_layers_svg

            export_layers_svg(pcb_path, output_dir, layers)

            # Check calls
            # Expect one call per layer? or one call with multiple layers?
            # kicad-cli pcb export svg supports --layers "L1,L2"

            self.assertEqual(mock_run.call_count, 1)
            args = mock_run.call_args[0][0]

            # Verify command structure
            self.assertEqual(args[0], "kicad-cli")
            self.assertEqual(args[1], "pcb")
            self.assertEqual(args[2], "export")
            self.assertEqual(args[3], "svg")

            # Check inputs
            self.assertIn(str(pcb_path), args)
            self.assertIn("--layers", args)
            self.assertIn("F.Cu,B.Cu", args)
            self.assertIn("--output", args)

    def test_missing_cli(self):
        """Verify handling of missing kicad-cli."""
        with patch("shutil.which", return_value=None):
            from temper_placer.io.render import export_layers_svg

            with self.assertRaises(RuntimeError) as cm:
                export_layers_svg(Path("t.kicad_pcb"), Path("out"), ["F.Cu"])

            self.assertIn("kicad-cli not found", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
