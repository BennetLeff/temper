"""Immutable artifact contents, compiler evidence, and Rust identities."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import artifacts


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = artifacts.Store(Path(self.temp.name) / "revisions")

    def test_base_roundtrip_immutable_and_tamper_detected(self):
        base = self.store.base("base notes", "def value():\n    return 1\n")
        self.assertEqual(self.store.read(base["revision_sha256"]), base)
        with self.assertRaises(FileExistsError):
            self.store.base("base notes", "def value():\n    return 1\n")
        path = self.store.root / base["revision_sha256"] / "skills.py"
        path.chmod(0o644)
        path.write_text("def value(): return 9\n")
        with self.assertRaises(ValueError):
            self.store.read(base["revision_sha256"])

    def test_bad_source_and_escaping_identity_fail(self):
        with self.assertRaises(SyntaxError):
            self.store.base("", "def bad(:")
        with self.assertRaises(ValueError):
            self.store.base("x" * 65536, "x = 1")
        for identity in ("../escape", "/tmp/escape", "A" * 64):
            with self.assertRaises(ValueError):
                self.store.read(identity)

    def test_symlink_root_and_file_rejected(self):
        link = Path(self.temp.name) / "link"
        link.symlink_to(self.store.root)
        with self.assertRaises(ValueError):
            artifacts.Store(link)
        base = self.store.base("", "x = 1")
        directory = self.store.root / base["revision_sha256"]
        path = directory / "notes.md"
        directory.chmod(0o755)
        path.unlink()
        path.symlink_to(Path(self.temp.name) / "outside")
        with self.assertRaises(ValueError):
            self.store.read(base["revision_sha256"])
