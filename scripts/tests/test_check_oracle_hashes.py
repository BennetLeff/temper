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

Two more shapes, added 2026-08-13 to close a confirmed discovery blind
spot: ``TestPackageOracleDiscovery`` proves a multi-file pinned-oracle
PACKAGE (a directory ending in ``_oracle``, e.g. the real
``clearance_oracle/``) is discovered and drift-checked even though none of
its individual files match the flat ``_*_py_oracle.py`` glob; it also
proves the widened discovery does not sweep in unrelated ``*oracle*``
directories. ``TestAntiVacuityFloor`` proves the registry's ``min_files``
floor fails the gate closed if discovery ever finds fewer oracles than a
prior run recorded, and that the generator refuses to silently lower that
floor without ``--allow-shrink``.
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


def _run_generator(
    root: Path, registry_path: Path, extra_args: list[str] | None = None
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "scripts/update_oracle_hashes.py",
         "--repo-root", str(root), "--registry", str(registry_path), *(extra_args or [])],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
    )


class TestPackageOracleDiscovery:
    """2026-08-13 blind-spot fix: a directory whose name ends in ``_oracle``
    is a multi-file pinned-oracle package (e.g. real
    ``clearance_oracle/``, ``explain_oracle/``, ``_parse_engine_py_oracle/``)
    -- none of its files individually match ``_*_py_oracle.py``, so only
    the directory-based discovery path in ``_lib/oracle_discovery.py`` can
    see them at all.
    """

    def test_package_style_oracle_directory_is_discovered(self, tmp_path):
        root = tmp_path / "repo"
        # Plainly-named files inside a "*_oracle"-suffixed directory -- the
        # exact shape of the real clearance_oracle/ package, none of which
        # match the flat _*_py_oracle.py glob.
        _write(root / "packages/temper-placer/tests/requirements/clearance_oracle/__init__.py", "")
        _write(root / "packages/temper-placer/tests/requirements/clearance_oracle/clearance.py", "X = 1\n")
        _write(root / "packages/temper-placer/tests/requirements/clearance_oracle/_copper.py", "Y = 2\n")
        oracles = generator.discover_oracles(root)
        rels = {str(p.relative_to(root)) for p in oracles}
        assert rels == {
            "packages/temper-placer/tests/requirements/clearance_oracle/__init__.py",
            "packages/temper-placer/tests/requirements/clearance_oracle/clearance.py",
            "packages/temper-placer/tests/requirements/clearance_oracle/_copper.py",
        }

    def test_a_directory_that_merely_contains_oracle_in_its_name_is_not_swept_in(self, tmp_path):
        """Name-based sweeps undercount by missing shapes; the fix must not
        overcount by sweeping in unrelated directories either. A hyphenated
        crate-style name (``temper-quality-oracle``, the real Rust crate's
        shape) and a bare ``oracle`` directory (the real
        ``temper-drc-rs/src/rules/oracle`` shape) must NOT be treated as
        pinned-oracle packages -- only an ``_oracle`` (underscore) suffix
        counts, matching every real oracle-package name in this repo."""
        root = tmp_path / "repo"
        _write(root / "packages/temper-quality-oracle/src/not_a_pin.py", "X = 1\n")
        _write(root / "packages/temper-drc-rs/src/rules/oracle/mod.py", "Y = 2\n")
        oracles = generator.discover_oracles(root)
        assert oracles == []

    def test_gate_reports_drift_inside_a_package_style_oracle(self, tmp_path):
        root = tmp_path / "repo"
        pkg = "packages/temper-placer/tests/requirements/clearance_oracle"
        _write(root / pkg / "__init__.py", "")
        _write(root / pkg / "clearance.py", "X = 1\n")
        expected = {
            f"{pkg}/__init__.py": generator.sha256_file(root / pkg / "__init__.py"),
            f"{pkg}/clearance.py": generator.sha256_file(root / pkg / "clearance.py"),
        }
        registry_path = root / "scripts" / "oracle_hashes.json"
        _write(registry_path, json.dumps(
            {"version": 1, "algo": "sha256", "files": expected}, indent=2, sort_keys=True,
        ) + "\n")
        # clean before the edit
        assert not gate.run(root, registry_path).findings
        # an edit inside the package -- exactly the shape the flat glob
        # cannot see at all, and the whole point of this fix
        _write(root / pkg / "clearance.py", "X = 999  # accidental edit\n")
        report = gate.run(root, registry_path)
        assert any(f.status == gate.DRIFTED and f.rel_path == f"{pkg}/clearance.py"
                   for f in report.findings)


class TestAntiVacuityFloor:
    """``min_files`` must make the registry fail closed if discovery itself
    regresses -- the failure mode a DELETED/UNREGISTERED finding cannot
    catch, because both only fire for files that ARE registered. This is
    the case where discovery narrows AND the registry is regenerated
    against that narrower discovery in the same change, so the registry
    stays internally consistent (files == registry) while quietly covering
    less than before.
    """

    def test_check_fails_closed_when_disk_count_is_below_min_files(self, tmp_path):
        root, registry_path, expected = _make_repo(tmp_path, ["a", "b", "c"])
        data = json.loads(registry_path.read_text())
        data["min_files"] = 5  # a prior run saw 5; this tree only has 3
        _write(registry_path, json.dumps(data, indent=2, sort_keys=True) + "\n")
        report = gate.run(root, registry_path)
        assert report.tool_error is not None
        assert "min_files" in report.tool_error or "floor" in report.tool_error

    def test_check_passes_when_disk_count_meets_min_files(self, tmp_path):
        root, registry_path, expected = _make_repo(tmp_path, ["a", "b", "c"])
        data = json.loads(registry_path.read_text())
        data["min_files"] = 3
        _write(registry_path, json.dumps(data, indent=2, sort_keys=True) + "\n")
        report = gate.run(root, registry_path)
        assert report.tool_error is None

    def test_registry_without_min_files_is_not_penalized(self, tmp_path):
        """Older/synthetic registries that predate this field must still load."""
        root, registry_path, _ = _make_repo(tmp_path, ["a"])
        report = gate.run(root, registry_path)
        assert report.tool_error is None

    def test_bad_min_files_type_is_tool_error(self, tmp_path):
        root, registry_path, _ = _make_repo(tmp_path, ["a"])
        data = json.loads(registry_path.read_text())
        data["min_files"] = "lots"
        _write(registry_path, json.dumps(data))
        report = gate.run(root, registry_path)
        assert report.tool_error is not None

    def test_generator_ratchets_min_files_up(self, tmp_path):
        root, registry_path, _ = _make_repo(tmp_path, ["a"])
        _run_generator(root, registry_path)
        data = json.loads(registry_path.read_text())
        assert data["min_files"] == 1
        _write(root / "packages/temper-placer/tests/core/_b_py_oracle.py", "# b\n")
        _run_generator(root, registry_path)
        data = json.loads(registry_path.read_text())
        assert data["min_files"] == 2

    def test_generator_refuses_to_silently_shrink_min_files(self, tmp_path):
        root, registry_path, _ = _make_repo(tmp_path, ["a", "b", "c"])
        _run_generator(root, registry_path)
        assert json.loads(registry_path.read_text())["min_files"] == 3
        (root / "packages/temper-placer/tests/core/_c_py_oracle.py").unlink()
        result = _run_generator(root, registry_path)
        assert result.returncode == 1
        assert "min_files" in result.stderr or "floor" in result.stderr
        # registry unchanged -- refusal must not partially write
        assert json.loads(registry_path.read_text())["min_files"] == 3

    def test_generator_allow_shrink_lowers_the_floor_deliberately(self, tmp_path):
        root, registry_path, _ = _make_repo(tmp_path, ["a", "b", "c"])
        _run_generator(root, registry_path)
        (root / "packages/temper-placer/tests/core/_c_py_oracle.py").unlink()
        result = _run_generator(root, registry_path, extra_args=["--allow-shrink"])
        assert result.returncode == 0
        data = json.loads(registry_path.read_text())
        assert data["min_files"] == 2
        # and the gate is clean against the deliberately-shrunk registry
        report = gate.run(root, registry_path)
        assert report.tool_error is None
        assert not report.findings
