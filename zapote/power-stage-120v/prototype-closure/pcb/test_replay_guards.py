"""Exercise real builders in disposable copies with KiCad's Python.

Usage: test_replay_guards.py /path/to/native18/section.kicad_pcb
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import build_candidate
import build_schematic
from source_snapshot import EXPORT_NAMES

UNIT = Path(__file__).resolve().parents[2]
BASELINE = None


def hashes(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }


class ReplayGuards(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="temper-replay-guards-")
        self.addCleanup(self.temp.cleanup)
        self.unit = Path(self.temp.name)
        shutil.copytree(UNIT / "frozen", self.unit / "frozen")
        shutil.copytree(UNIT / "native-19", self.unit / "native-19")
        for module in (build_candidate, build_schematic):
            context = patch.object(module, "UNIT", self.unit)
            context.start()
            self.addCleanup(context.stop)

    def builders(self):
        return (lambda: build_candidate.build(BASELINE), build_schematic.main)

    def assert_no_design_write(self, run, exception, message) -> None:
        before = hashes(self.unit / "native-19")
        with self.assertRaisesRegex(exception, message):
            run()
        self.assertEqual(before, hashes(self.unit / "native-19"))

    def test_different_exports_rejected_by_both_builders(self) -> None:
        for name in EXPORT_NAMES:
            audited = self.unit / "frozen" / name
            original = audited.read_bytes()
            audited.write_bytes(original + b"\nchanged source\n")
            for run in self.builders():
                with self.subTest(export=name, builder=run):
                    self.assert_no_design_write(run, ValueError, "source snapshot differs")
            audited.write_bytes(original)

    def test_missing_exports_rejected_by_both_builders(self) -> None:
        for name in EXPORT_NAMES:
            native = self.unit / "native-19/frozen" / name
            original = native.read_bytes()
            native.unlink()
            for run in self.builders():
                with self.subTest(export=name, builder=run):
                    self.assert_no_design_write(run, FileNotFoundError, name)
            native.write_bytes(original)

    def test_replay_uses_only_local_footprints_without_replacing_them(self) -> None:
        libraries = self.unit / "native-19/candidate-libs"
        before = hashes(libraries)
        real_load = build_candidate.pcbnew.FootprintLoad
        loaded = []

        def local_only(library, name):
            self.assertTrue(Path(library).resolve().is_relative_to(libraries.resolve()))
            loaded.append((library, name))
            return real_load(library, name)

        def reject_copy(*_args, **_kwargs):
            self.fail("PCB replay attempted to replace a committed footprint")

        with (
            patch.object(build_candidate.pcbnew, "FootprintLoad", local_only),
            patch.object(shutil, "copy2", reject_copy),
        ):
            build_candidate.build(BASELINE)
        self.assertTrue(loaded)
        self.assertEqual(before, hashes(libraries))
        # The documented schematic command uses host Python (3.10+), while
        # KiCad's pcbnew interpreter is 3.9 and cannot execute strict zip.
        subprocess.run(
            [
                shutil.which("python3"),
                "-c",
                f"import sys; sys.path.insert(0, {str(Path(__file__).resolve().parent)!r}); "
                "import build_schematic; from pathlib import Path; "
                f"build_schematic.UNIT = Path({str(self.unit)!r}); build_schematic.main()",
            ],
            check=True,
        )
        self.assertEqual(
            (UNIT / "native-19/section.kicad_sch").read_bytes(),
            (self.unit / "native-19/section.kicad_sch").read_bytes(),
        )

    def test_missing_local_shunt_footprint_fails_before_design_write(self) -> None:
        path = self.unit / "native-19/candidate-libs/Resistor_SMD.pretty"
        (path / "R_Shunt_Vishay_WSK2512_6332Metric_T2.21mm.kicad_mod").unlink()
        self.assert_no_design_write(
            lambda: build_candidate.build(BASELINE),
            FileNotFoundError,
            "missing committed footprint",
        )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: test_replay_guards.py /path/to/native18/section.kicad_pcb")
    BASELINE = Path(sys.argv.pop()).resolve()
    unittest.main(verbosity=2)
