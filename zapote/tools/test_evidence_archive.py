"""Tests for evidence_archive. Run: python3 zapote/tools/test_evidence_archive.py"""
from __future__ import annotations

import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evidence_archive as ea  # noqa: E402


def git_repo(files: dict[str, bytes]) -> Path:
    root = Path(tempfile.mkdtemp())
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    for rel, data in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    return root


class IsBulk(unittest.TestCase):
    def test_suffix_rule(self):
        self.assertTrue(ea.is_bulk("zapote/a/waves.raw.gz", 10))
        self.assertTrue(ea.is_bulk("zapote/a/field.npz", 10))
        self.assertFalse(ea.is_bulk("zapote/a/report.json", 10))

    def test_size_rule_is_strictly_greater(self):
        self.assertFalse(ea.is_bulk("zapote/a.csv", 100, max_bytes=100))
        self.assertTrue(ea.is_bulk("zapote/a.csv", 101, max_bytes=100))


class PlanAssets(unittest.TestCase):
    def test_groups_in_path_order_under_limit(self):
        groups = ea.plan_assets([("b", 6), ("a", 5), ("c", 5)], max_asset_bytes=10)
        self.assertEqual(groups, [[("a", 5)], [("b", 6)], [("c", 5)]])

    def test_single_oversize_file_is_an_error(self):
        with self.assertRaises(ValueError):
            ea.plan_assets([("a", 11)], max_asset_bytes=10)


class RoundTrip(unittest.TestCase):
    def setUp(self):
        self.repo = git_repo({
            "zapote/v/run.raw.gz": b"g" * 50,
            "zapote/v/big.csv": b"c" * 300,
            "zapote/v/keep.json": b"{}",
            "other/huge.bin": b"x" * 500,  # outside zapote: never selected
        })
        self.out = Path(tempfile.mkdtemp())

    def test_pack_selects_only_zapote_bulk_and_extract_restores_bytes(self):
        m = ea.pack(self.repo, self.out, "rel-x", max_asset_bytes=320, max_bytes=100)
        self.assertEqual(m["schema"], ea.SCHEMA)
        self.assertEqual(sorted(f["path"] for f in m["files"]), ["zapote/v/big.csv", "zapote/v/run.raw.gz"])
        self.assertEqual(len(m["assets"]), 2)  # 300 B + 50 B exceed one 320 B asset
        dest = Path(tempfile.mkdtemp())
        ea.extract(m, self.out, dest)
        self.assertEqual((dest / "zapote/v/big.csv").read_bytes(), b"c" * 300)
        self.assertEqual((dest / "zapote/v/run.raw.gz").read_bytes(), b"g" * 50)

    def test_extract_rejects_tampered_asset(self):
        m = ea.pack(self.repo, self.out, "rel-x", max_asset_bytes=1000, max_bytes=100)
        part = self.out / m["assets"][0]["name"]
        part.write_bytes(part.read_bytes()[:-10])
        with self.assertRaises(ValueError):
            ea.extract(m, self.out, Path(tempfile.mkdtemp()))

    def test_extract_ignores_members_not_in_manifest(self):
        m = ea.pack(self.repo, self.out, "rel-x", max_asset_bytes=1000, max_bytes=100)
        part = self.out / m["assets"][0]["name"]
        evil = self.out / "evil.txt"
        evil.write_bytes(b"x")
        with tarfile.open(part, "a") as tar:
            tar.add(evil, arcname="../escape.txt")
        m["assets"][0]["sha256"] = ea.sha256_file(part)
        dest = Path(tempfile.mkdtemp())
        ea.extract(m, self.out, dest)
        self.assertFalse((dest.parent / "escape.txt").exists())


class Check(unittest.TestCase):
    def test_flags_tracked_bulk(self):
        repo = git_repo({"zapote/a.npz": b"n", "zapote/b.json": b"{}"})
        problems = ea.check(repo)
        self.assertEqual(len(problems), 1)
        self.assertIn("zapote/a.npz", problems[0])

    def test_clean_tree_passes(self):
        self.assertEqual(ea.check(git_repo({"zapote/b.json": b"{}"})), [])


class Gitignore(unittest.TestCase):
    def test_lists_only_paths_not_covered_by_suffix_globs(self):
        m = {"files": [{"path": "zapote/v/a.gz"}, {"path": "zapote/v/big.csv"}]}
        block = ea.gitignore_block(m)
        self.assertIn("/v/big.csv", block)
        self.assertNotIn("a.gz", block)
        self.assertIn("*.gz", block)


if __name__ == "__main__":
    unittest.main()
