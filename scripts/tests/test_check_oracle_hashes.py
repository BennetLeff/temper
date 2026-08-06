"""Tests for the oracle content-hash gate (scripts/check_oracle_hashes.py).

The gate's whole reason to exist is that an oracle edit is invisible to the
differential suites -- so these tests must prove the gate fires on the
three shapes that edit can take, against synthetic trees that do not depend
on whatever the real repo contains on any given day:

  - DRIFTED      the file's bytes changed (hash no longer matches)
  - DELETED      the file is gone
  - UNREGISTERED a NEW oracle appeared with no registry entry (the
                 anti-vacuity direction -- the registry cannot go stale by
                 omission)

Plus the vacuous shapes that must fail closed: a malformed/empty registry
and a run that discovers zero files both return tool_error (exit 5), never
a clean pass. ``test_gate_is_not_vacuous_by_construction`` is the most
important test in this file: it removes an oracle, adds an oracle, and
drifts an oracle, and requires a finding for each.

The generator (scripts/update_oracle_hashes.py) is pinned by two round-trip
tests: a generated registry is byte-stable across runs (idempotent) and the
check passes against the tree it was generated from.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_oracle_hashes as gate  # noqa: E402
import update_oracle_hashes as generator  # noqa: E402

EXIT_CLEAN = gate.EXIT_CLEAN
EXIT_DRIFT = gate.EXIT_DRIFT
EXIT_TOOL_ERROR = gate.EXIT_TOOL_ERROR


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _make_repo(tmp_path: Path, oracle_names: list[str]) -> tuple[Path, Path, dict]:
    """A synthetic repo: packages/<pkg>/tests/<name>_py_oracle.py files.

    Returns (repo_root, registry_path, expected_files) where
    expected_files maps the relative path to its sha256.
    """
    root = tmp_path / "repo"
    registry_path = root / "scripts" / "oracle_hashes.json"
    expected: dict[str, str] = {}
    for name in oracle_names:
        rel = f"packages/temper-placer/tests/core/_{name}_py_oracle.py"
        _write(root / rel, f"# oracle {name}\nVALUE = {len(name)}\n")
        expected[rel] = generator.sha256_file(root / rel)
    payload = {"version": 1, "algo": "sha256", "files": expected}
    _write(registry_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return root, registry_path, expected


class TestDriftShapes:
    def test_drifted_oracle_fails(self, tmp_path):
        root, registry_path, expected = _make_repo(tmp_path, ["a", "b"])
        _write(root / "packages/temper-placer/tests/core/_a_py_oracle.py",
               "# oracle a\nVALUE = 999\n")
        report = gate.run(root, registry_path)
        assert gate.EXIT_DRIFT and report.findings
        assert any(f.status == gate.DRIFTED for f in report.findings)

    def test_deleted_oracle_fails(self, tmp_path):
        root, registry_path, _ = _make_repo(tmp_path, ["a", "b"])
        (root / "packages/temper-placer/tests/core/_b_py_oracle.py").unlink()
        report = gate.run(root, registry_path)
        assert report.findings
        assert any(f.status == gate.DELETED for f in report.findings)

    def test_new_unregistered_oracle_fails(self, tmp_path):
        root, registry_path, _ = _make_repo(tmp_path, ["a"])
        _write(root / "packages/temper-placer/tests/core/_sneaky_py_oracle.py", "# new\n")
        report = gate.run(root, registry_path)
        assert report.findings
        assert any(f.status == gate.UNREGISTERED for f in report.findings)

    def test_gate_is_not_vacuous_by_construction(self, tmp_path):
        """A single tree that drifts, deletes AND adds -- all three fire."""
        root, registry_path, _ = _make_repo(tmp_path, ["a", "b", "c"])
        _write(root / "packages/temper-placer/tests/core/_a_py_oracle.py", "# drifted\n")
        (root / "packages/temper-placer/tests/core/_b_py_oracle.py").unlink()
        _write(root / "packages/temper-placer/tests/core/_d_py_oracle.py", "# new\n")
        report = gate.run(root, registry_path)
        statuses = {f.status for f in report.findings}
        assert statuses == {gate.DRIFTED, gate.DELETED, gate.UNREGISTERED}


class TestCleanPass:
    def test_clean_registry_passes(self, tmp_path):
        root, registry_path, _ = _make_repo(tmp_path, ["a", "b", "c"])
        report = gate.run(root, registry_path)
        assert report.tool_error is None
        assert not report.findings
        assert report.clean_count == 3


class TestFailClosed:
    def test_missing_registry_is_tool_error(self, tmp_path):
        root, registry_path, _ = _make_repo(tmp_path, ["a"])
        registry_path.unlink()
        report = gate.run(root, registry_path)
        assert report.tool_error is not None

    def test_empty_registry_is_tool_error(self, tmp_path):
        root, registry_path, _ = _make_repo(tmp_path, ["a"])
        _write(registry_path, json.dumps({"version": 1, "algo": "sha256", "files": {}}))
        report = gate.run(root, registry_path)
        assert report.tool_error is not None

    def test_garbage_registry_is_tool_error(self, tmp_path):
        root, registry_path, _ = _make_repo(tmp_path, ["a"])
        _write(registry_path, "not json{")
        report = gate.run(root, registry_path)
        assert report.tool_error is not None

    def test_bad_version_is_tool_error(self, tmp_path):
        root, registry_path, _ = _make_repo(tmp_path, ["a"])
        data = json.loads(registry_path.read_text())
        data["version"] = 99
        _write(registry_path, json.dumps(data))
        report = gate.run(root, registry_path)
        assert report.tool_error is not None

    def test_zero_files_on_disk_fails_closed(self, tmp_path):
        root, registry_path, _ = _make_repo(tmp_path, ["a"])
        (root / "packages/temper-placer/tests/core/_a_py_oracle.py").unlink()
        report = gate.run(root, registry_path)
        # registry non-empty but every file gone: tool_error, not clean
        assert report.tool_error is not None

    def test_excluded_dirs_are_not_discovered(self, tmp_path):
        root, registry_path, expected = _make_repo(tmp_path, ["a"])
        _write(root / "packages/temper-placer/.venv/x/_junk_py_oracle.py", "# junk\n")
        report = gate.run(root, registry_path)
        assert report.tool_error is None
        assert not report.findings


class TestGenerator:
    def test_generated_registry_matches_tree_and_is_idempotent(self, tmp_path):
        root, registry_path, _ = _make_repo(tmp_path, [])
        oracles = generator.discover_oracles(root)
        assert oracles == []  # synthetic tree has no real oracles yet
        _write(root / "packages/temper-placer/tests/core/_a_py_oracle.py", "# oracle a\nX=1\n")
        _write(root / "packages/temper-placer/tests/core/_b_py_oracle.py", "# oracle b\nY=2\n")
        payload = generator.registry_payload(generator.discover_oracles(root), root)
        assert len(payload["files"]) == 2
        # idempotent: regenerating from the same tree yields identical bytes
        assert generator.registry_payload(
            generator.discover_oracles(root), root
        ) == payload
        # and the check passes against a registry generated from its tree
        _write(registry_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
        report = gate.run(root, registry_path)
        assert report.tool_error is None
        assert not report.findings

    def test_generator_refuses_empty_tree(self, tmp_path):
        root, registry_path, _ = _make_repo(tmp_path, [])
        (root / "packages").mkdir(parents=True, exist_ok=True)
        result = _run_generator(root, registry_path)
        assert result.returncode == 1
        assert "refusing to write a vacuous registry" in result.stderr

    def test_generator_rewrites_changed_hash(self, tmp_path):
        root, registry_path, expected = _make_repo(tmp_path, ["a"])
        rel = "packages/temper-placer/tests/core/_a_py_oracle.py"
        original_hash = expected[rel]
        _write(root / rel, "# changed\n")
        _run_generator(root, registry_path)
        data = json.loads(registry_path.read_text())
        assert data["files"][rel] != original_hash
        report = gate.run(root, registry_path)
        assert not report.findings


def _run_generator(root: Path, registry_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "scripts/update_oracle_hashes.py",
         "--repo-root", str(root), "--registry", str(registry_path)],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
    )
