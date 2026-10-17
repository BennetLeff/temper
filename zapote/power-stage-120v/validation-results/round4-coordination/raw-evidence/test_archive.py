#!/usr/bin/env python3
"""Focused failure tests for the round-4 archive transport."""

from __future__ import annotations

import hashlib
import io
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import restore as restore_module
from restore import existing_path, extract_part, matches, verify_asset_files


class ArchiveFailureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.row = {"path": "run/result.bin", "bytes": 3, "sha256": hashlib.sha256(b"abc").hexdigest()}

    def make_tar(self, members: list[tuple[str, bytes, bytes]]) -> Path:
        path = self.root / "part.tar"
        with tarfile.open(path, "w") as tar:
            for name, kind, content in members:
                info = tarfile.TarInfo(name)
                info.type = kind
                info.size = len(content) if kind == tarfile.REGTYPE else 0
                tar.addfile(info, io.BytesIO(content) if kind == tarfile.REGTYPE else None)
        return path

    def test_missing_and_corrupted_asset(self) -> None:
        metadata = {"assets": [{"name": "part.tar", "bytes": 3, "sha256": hashlib.sha256(b"abc").hexdigest()}]}
        with self.assertRaisesRegex(ValueError, "missing"):
            verify_asset_files(metadata, self.root)
        (self.root / "part.tar").write_bytes(b"abd")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            verify_asset_files(metadata, self.root)

    def test_unsafe_and_unexpected_members(self) -> None:
        for name, kind in [
            ("../run/result.bin", tarfile.REGTYPE),
            ("/run/result.bin", tarfile.REGTYPE),
            ("unexpected.bin", tarfile.REGTYPE),
            ("run/result.bin", tarfile.SYMTYPE),
            ("run/result.bin", tarfile.DIRTYPE),
        ]:
            with self.subTest(name=name, kind=kind):
                archive = self.make_tar([(name, kind, b"abc")])
                with self.assertRaisesRegex(ValueError, "unsafe"):
                    extract_part(archive, [self.row], self.root / "stage")

    def test_duplicate_and_missing_member(self) -> None:
        archive = self.make_tar([
            ("run/result.bin", tarfile.REGTYPE, b"abc"),
            ("run/result.bin", tarfile.REGTYPE, b"abc"),
        ])
        with self.assertRaisesRegex(ValueError, "duplicate"):
            extract_part(archive, [self.row], self.root / "stage")
        archive = self.make_tar([])
        with self.assertRaisesRegex(ValueError, "missing"):
            extract_part(archive, [self.row], self.root / "empty-stage")

    def test_corrupt_and_truncated_member(self) -> None:
        archive = self.make_tar([("run/result.bin", tarfile.REGTYPE, b"abd")])
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            extract_part(archive, [self.row], self.root / "stage")
        archive = self.make_tar([("run/result.bin", tarfile.REGTYPE, b"abc")])
        data = archive.read_bytes()
        archive.write_bytes(data[:513])
        with self.assertRaises((ValueError, EOFError, tarfile.ReadError, OSError)):
            extract_part(archive, [self.row], self.root / "truncated-stage")

    def test_concurrent_mismatching_file_is_not_overwritten(self) -> None:
        archive = self.make_tar([("run/result.bin", tarfile.REGTYPE, b"abc")])
        metadata = {"file_count": 1, "file_bytes": 3, "assets": [{
            "name": archive.name, "bytes": archive.stat().st_size,
            "sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}]}
        destination = self.root / self.row["path"]
        original_matches = restore_module.matches
        calls = 0

        def insert_competing_file(path, row):
            nonlocal calls
            result = original_matches(path, row)
            calls += 1
            if calls == 2:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"xyz")
            return result

        with (patch.object(restore_module, "checked_assets", return_value=(metadata, [[self.row]])),
              patch.object(restore_module, "matches", side_effect=insert_competing_file)):
            with self.assertRaisesRegex(ValueError, "existing file differs"):
                restore_module.restore(self.root, self.root)
        self.assertEqual(destination.read_bytes(), b"xyz")

    def test_existing_file_changed_during_extraction_is_rejected(self) -> None:
        archive = self.make_tar([("run/result.bin", tarfile.REGTYPE, b"abc")])
        metadata = {"file_count": 1, "file_bytes": 3, "assets": [{
            "name": archive.name, "bytes": archive.stat().st_size,
            "sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}]}
        destination = self.root / self.row["path"]
        destination.parent.mkdir()
        destination.write_bytes(b"abc")
        original_extract = restore_module.extract_part

        def change_existing_file(asset_path, expected, stage):
            original_extract(asset_path, expected, stage)
            destination.write_bytes(b"xyz")

        with (patch.object(restore_module, "checked_assets", return_value=(metadata, [[self.row]])),
              patch.object(restore_module, "extract_part", side_effect=change_existing_file)):
            with self.assertRaisesRegex(ValueError, "existing file differs"):
                restore_module.restore(self.root, self.root)
        self.assertEqual(destination.read_bytes(), b"xyz")

    def test_existing_file_deleted_during_extraction_is_restored(self) -> None:
        archive = self.make_tar([("run/result.bin", tarfile.REGTYPE, b"abc")])
        metadata = {"file_count": 1, "file_bytes": 3, "assets": [{
            "name": archive.name, "bytes": archive.stat().st_size,
            "sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}]}
        destination = self.root / self.row["path"]
        destination.parent.mkdir()
        destination.write_bytes(b"abc")
        original_extract = restore_module.extract_part

        def delete_existing_file(asset_path, expected, stage):
            original_extract(asset_path, expected, stage)
            destination.unlink()

        with (patch.object(restore_module, "checked_assets", return_value=(metadata, [[self.row]])),
              patch.object(restore_module, "extract_part", side_effect=delete_existing_file)):
            restore_module.restore(self.root, self.root)
        self.assertEqual(destination.read_bytes(), b"abc")

    def test_existing_file_and_parent_symlink(self) -> None:
        destination = self.root / self.row["path"]
        destination.parent.mkdir()
        destination.write_bytes(b"abd")
        with self.assertRaisesRegex(ValueError, "existing file differs"):
            matches(existing_path(self.root, self.row["path"]), self.row)
        destination.unlink()
        destination.parent.rmdir()
        (self.root / "run").symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "destination symlink"):
            existing_path(self.root, self.row["path"])


if __name__ == "__main__":
    unittest.main()
