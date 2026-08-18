"""Tests for the inline-oracle content-hash gate (scripts/check_inline_oracles.py).

The gate exists because ``check_oracle_hashes.py`` can only see oracles that
live in their own ``_*_py_oracle.py`` file, and a large share of this repo's
oracles are inline blocks inside test files instead. ``TestHistoricalReplay``
below is the anti-vacuity evidence that matters: it replays the real commit
that motivated the gate (35e3f914a) and asserts the gate goes RED on it.
A gate that passes on the code that motivated it is worth nothing.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_inline_oracles import (  # noqa: E402
    DELETED,
    DRIFTED,
    EXIT_CLEAN,
    EXIT_DRIFT,
    EXIT_TOOL_ERROR,
    SUPPORTED_ALGO,
    SUPPORTED_VERSION,
    UNREGISTERED,
    block_key,
    discover,
    discover_blocks,
    extract_blocks,
    load_registry,
    run,
    sha256_text,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

ORACLE_SRC = '''\
def _oracle_add(a, b):
    """Verbatim pre-migration implementation. DO NOT EDIT."""
    return a + b


class _OracleThing:
    value = 1


def helper_not_an_oracle():
    return 0
'''


def _make_tree(root: Path, files: dict[str, str]) -> None:
    for rel, body in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)


def _write_registry(path: Path, blocks: dict[str, str], files: dict[str, str] | None = None,
                    **over) -> None:
    payload = {
        "algo": SUPPORTED_ALGO,
        "blocks": blocks,
        "files": files or {},
        "version": SUPPORTED_VERSION,
    }
    payload.update(over)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))


def _seed(tmp_path: Path) -> tuple[Path, str]:
    rel = "packages/temper-placer/tests/core/test_thing_rust_differential.py"
    _make_tree(tmp_path, {rel: ORACLE_SRC})
    return tmp_path / "scripts" / "inline_oracle_hashes.json", rel


# ---------------------------------------------------------------------------
# TestDiscovery -- what does and does not count as an inline oracle block
# ---------------------------------------------------------------------------


class TestDiscovery:
    def test_extracts_function_and_class_blocks(self):
        blocks = dict(extract_blocks(ORACLE_SRC))
        assert set(blocks) == {"_oracle_add", "_OracleThing"}

    def test_ignores_non_oracle_symbols(self):
        assert "helper_not_an_oracle" not in dict(extract_blocks(ORACLE_SRC))

    def test_block_hash_is_of_the_block_not_the_file(self, tmp_path):
        """A block's pin must survive unrelated edits elsewhere in the file --
        otherwise every new test forces a re-pin and nobody reads the diff."""
        registry, rel = _seed(tmp_path)
        before, _, _ = discover_blocks(tmp_path)
        (tmp_path / rel).write_text(ORACLE_SRC + "\n\ndef test_new_unrelated():\n    assert True\n")
        after, _, _ = discover_blocks(tmp_path)
        assert before == after

    def test_registered_oracle_files_are_not_double_pinned(self, tmp_path):
        """``_*_py_oracle.py`` is already pinned by check_oracle_hashes.py."""
        _make_tree(
            tmp_path,
            {"packages/temper-placer/tests/core/_thing_py_oracle.py": ORACLE_SRC},
        )
        blocks, files, _, _ = discover(tmp_path)
        assert blocks == {} and files == {}

    def test_oracle_package_dir_modules_get_a_whole_file_pin(self, tmp_path):
        """Tier 2a: check_oracle_hashes.py's file-glob cannot see modules whose
        *directory* carries the oracle name -- 18 real modules today."""
        rel = "packages/temper-placer/tests/explainability/explain_oracle/decision_oracle.py"
        _make_tree(tmp_path, {rel: "class Decision:\n    pass\n"})
        _blocks, files, _, _ = discover(tmp_path)
        assert rel in files

    def test_unprefixed_oracle_inside_a_banner_region_is_pinned(self, tmp_path):
        """The oracle is pasted under its ORIGINAL names, so no naming rule
        can find it. The banner-region rule does -- this is the shape of the
        ~740-line DRCOracle block, the largest inline oracle in the repo."""
        rel = "packages/temper-placer/tests/router_v6/test_drc_oracle_rust_differential.py"
        _make_tree(
            tmp_path,
            {rel: "# Oracle block -- verbatim copy of constraints_drc_oracle.py\n"
                  "class Violation:\n    pass\n\n\n"
                  "class DRCOracle:\n    pass\n\n\n"
                  "def test_thing():\n    assert True\n"},
        )
        blocks, _files, _, _ = discover(tmp_path)
        names = {k.split("::")[-1] for k in blocks}
        assert {"Violation", "DRCOracle"} <= names

    def test_region_closes_at_the_first_test(self, tmp_path):
        """Helpers written after the tests begin are not oracle content --
        pinning them would create churn that trains people to ignore the diff."""
        src = (
            "# Oracle block -- verbatim\n"
            "class Violation:\n    pass\n\n\n"
            "def test_a():\n    assert True\n\n\n"
            "def later_helper():\n    return 1\n"
        )
        names = {n for n, _ in extract_blocks(src)}
        assert "Violation" in names
        assert "later_helper" not in names

    def test_explicit_end_marker_closes_the_region(self):
        src = (
            "# Oracle block -- verbatim\n"
            "class Violation:\n    pass\n\n"
            "# End of oracle block -- the reference is fixed above.\n"
            "class NotAnOracle:\n    pass\n"
        )
        names = {n for n, _ in extract_blocks(src)}
        assert names == {"Violation"}

    def test_broadened_symbol_families_are_detected(self):
        """_ref_/_reference_/_scipy_/_numpy_ are real oracle spellings here."""
        src = (
            "def _ref_a():\n    return 1\n\n"
            "def _reference_b():\n    return 2\n\n"
            "def _scipy_c():\n    return 3\n\n"
            "def _numpy_d():\n    return 4\n\n"
            "def _some_thing_oracle():\n    return 5\n\n"
            "def unrelated():\n    return 6\n"
        )
        names = {n for n, _ in extract_blocks(src)}
        assert names == {"_ref_a", "_reference_b", "_scipy_c", "_numpy_d", "_some_thing_oracle"}

    def test_nested_defs_are_not_blocks(self, tmp_path):
        """Only top-level definitions are pinned -- a helper closure named
        ``_oracle_x`` inside a test is not a verbatim pin."""
        src = "def test_a():\n    def _oracle_inner():\n        return 1\n    assert _oracle_inner()\n"
        assert extract_blocks(src) == []


# ---------------------------------------------------------------------------
# TestDriftShapes
# ---------------------------------------------------------------------------


class TestDriftShapes:
    def test_clean_registry_passes(self, tmp_path):
        registry, _ = _seed(tmp_path)
        blocks, _, _ = discover_blocks(tmp_path)
        _write_registry(registry, blocks)
        report = run(tmp_path, registry)
        assert report.findings == []
        assert report.clean_count == 2

    def test_drifted_block_fails(self, tmp_path):
        registry, rel = _seed(tmp_path)
        blocks, _, _ = discover_blocks(tmp_path)
        _write_registry(registry, blocks)
        (tmp_path / rel).write_text(ORACLE_SRC.replace("return a + b", "return a - b"))
        report = run(tmp_path, registry)
        assert [f.status for f in report.findings] == [DRIFTED]
        assert report.findings[0].key.endswith("::_oracle_add")

    def test_deleted_block_fails(self, tmp_path):
        """The 35e3f914a shape: the block's file is swept away."""
        registry, rel = _seed(tmp_path)
        blocks, _, _ = discover_blocks(tmp_path)
        _write_registry(registry, blocks)
        # keep one block so the scan is not vacuous, remove the other
        (tmp_path / rel).write_text("class _OracleThing:\n    value = 1\n")
        report = run(tmp_path, registry)
        assert [f.status for f in report.findings] == [DELETED]
        assert report.findings[0].key.endswith("::_oracle_add")

    def test_new_unregistered_block_fails(self, tmp_path):
        """Anti-vacuity direction: the registry cannot go stale by omission."""
        registry, rel = _seed(tmp_path)
        blocks, _, _ = discover_blocks(tmp_path)
        _write_registry(registry, blocks)
        (tmp_path / rel).write_text(ORACLE_SRC + "\n\ndef _oracle_brand_new():\n    return 42\n")
        report = run(tmp_path, registry)
        assert [f.status for f in report.findings] == [UNREGISTERED]
        assert report.findings[0].key.endswith("::_oracle_brand_new")


# ---------------------------------------------------------------------------
# TestFailClosed
# ---------------------------------------------------------------------------


class TestFailClosed:
    def test_missing_registry_is_tool_error(self, tmp_path):
        _seed(tmp_path)
        report = run(tmp_path, tmp_path / "nope.json")
        assert report.tool_error and "not found" in report.tool_error

    def test_empty_registry_is_tool_error(self, tmp_path):
        registry, _ = _seed(tmp_path)
        _write_registry(registry, {})
        assert "vacuous" in (run(tmp_path, registry).tool_error or "")

    def test_garbage_registry_is_tool_error(self, tmp_path):
        registry, _ = _seed(tmp_path)
        registry.parent.mkdir(parents=True, exist_ok=True)
        registry.write_text("{not json")
        assert "unparseable" in (run(tmp_path, registry).tool_error or "")

    def test_bad_version_is_tool_error(self, tmp_path):
        registry, _ = _seed(tmp_path)
        blocks, _, _ = discover_blocks(tmp_path)
        _write_registry(registry, blocks, version=99)
        assert "version" in (run(tmp_path, registry).tool_error or "")

    def test_bad_algo_is_tool_error(self, tmp_path):
        registry, _ = _seed(tmp_path)
        blocks, _, _ = discover_blocks(tmp_path)
        _write_registry(registry, blocks, algo="md5")
        assert "algo" in (run(tmp_path, registry).tool_error or "")

    def test_malformed_digest_is_tool_error(self, tmp_path):
        registry, rel = _seed(tmp_path)
        _write_registry(registry, {block_key(rel, "_oracle_add"): "tooshort"})
        assert "malformed" in (run(tmp_path, registry).tool_error or "")

    def test_malformed_key_is_tool_error(self, tmp_path):
        registry, _ = _seed(tmp_path)
        _write_registry(registry, {"no-separator": "a" * 64})
        assert "malformed" in (run(tmp_path, registry).tool_error or "")

    def test_unparseable_test_file_is_tool_error(self, tmp_path):
        """A syntax error must not be silently skipped into a clean verdict."""
        registry, _ = _seed(tmp_path)
        blocks, _, _ = discover_blocks(tmp_path)
        _write_registry(registry, blocks)
        _make_tree(
            tmp_path,
            {"packages/temper-placer/tests/core/test_broken.py": "def (:\n"},
        )
        assert "unparseable" in (run(tmp_path, registry).tool_error or "")


# ---------------------------------------------------------------------------
# TestAntiVacuity -- the gate must be incapable of reporting a vacuous pass
# ---------------------------------------------------------------------------


class TestAntiVacuity:
    def test_zero_blocks_on_disk_fails_closed(self, tmp_path):
        """An empty tree must NOT report clean -- this is precisely how the
        file-based gate reported success while the thing it protects had
        just been deleted."""
        registry = tmp_path / "scripts" / "inline_oracle_hashes.json"
        _write_registry(registry, {"packages/temper-placer/tests/x.py::_oracle_a": "a" * 64})
        report = run(tmp_path, registry)
        assert report.tool_error is not None
        assert "refusing to report clean" in report.tool_error

    def test_gate_is_not_vacuous_by_construction(self, tmp_path):
        """A clean pass must be backed by a non-zero number of checked blocks."""
        registry, _ = _seed(tmp_path)
        blocks, _, _ = discover_blocks(tmp_path)
        _write_registry(registry, blocks)
        report = run(tmp_path, registry)
        assert report.findings == []
        assert report.clean_count > 0
        assert report.clean_count == report.disk_block_count == report.registry_block_count

    def test_denominator_equals_checked_count(self):
        """Every discovered block in the REAL tree is checked -- the
        denominator is never a subset."""
        blocks, file_pins, files, errors = discover(REPO_ROOT)
        assert errors == []
        assert len(blocks) > 0 and files > 0
        registry, err = load_registry(REPO_ROOT / "scripts" / "inline_oracle_hashes.json")
        assert err is None
        assert set(registry) == set(blocks) | set(file_pins)

    def test_real_tree_is_clean_and_nonempty(self):
        """The committed registry matches the committed tree."""
        report = run(REPO_ROOT, REPO_ROOT / "scripts" / "inline_oracle_hashes.json")
        assert report.tool_error is None
        assert report.findings == []
        assert report.disk_block_count > 100, "scan collapsed -- gate would be near-vacuous"


# ---------------------------------------------------------------------------
# TestHistoricalReplay -- the gate fails on the tree that motivated it
# ---------------------------------------------------------------------------

_SWEEP = "35e3f914a"
_SWEPT_FILE = "packages/temper-placer/tests/core/test_core_graph_cluster_rust_differential.py"


def _git_show(rev: str, path: str) -> str | None:
    proc = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "show", f"{rev}:{path}"],
        capture_output=True, text=True,
    )
    return proc.stdout if proc.returncode == 0 else None


def _have_sweep_commit() -> bool:
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), "cat-file", "-e", f"{_SWEEP}^{{commit}}"],
        capture_output=True,
    ).returncode == 0


class TestHistoricalReplay:
    """Replay of PR #1314 / commit 35e3f914a -- the incident this gate exists
    for. The sweep deleted a test file that carried 13 pinned inline oracle
    blocks; the file-based registry check ran, correctly found nothing, and
    reported success.

    These tests are skipped only if the commit is absent from the clone (a
    shallow checkout). They must never be *softened* to pass.
    """

    @pytest.mark.skipif(not _have_sweep_commit(), reason=f"{_SWEEP} not in this clone")
    def test_swept_file_carried_inline_oracle_blocks(self):
        src = _git_show(f"{_SWEEP}^", _SWEPT_FILE)
        assert src is not None, "pre-sweep file should exist"
        names = {n for n, _ in extract_blocks(src)}
        assert len(names) >= 13, f"expected >=13 inline oracle blocks, found {len(names)}"
        # the specific oracle PR #1348 had to reconstruct by hand
        assert "_oracle_coo_matmul" in names

    @pytest.mark.skipif(not _have_sweep_commit(), reason=f"{_SWEEP} not in this clone")
    def test_sweep_deleted_the_file_entirely(self):
        assert _git_show(_SWEEP, _SWEPT_FILE) is None, "file should be gone after the sweep"

    @pytest.mark.skipif(not _have_sweep_commit(), reason=f"{_SWEEP} not in this clone")
    def test_gate_goes_red_on_the_sweep(self, tmp_path):
        """THE anti-vacuity assertion: pin the pre-sweep blocks, apply the
        sweep, and the gate must report DELETED -- not success."""
        pre = _git_show(f"{_SWEEP}^", _SWEPT_FILE)
        assert pre is not None

        # A tree pinned before the sweep...
        _make_tree(tmp_path, {_SWEPT_FILE: pre})
        # ...plus one unrelated file so the post-sweep scan is non-vacuous
        survivor = "packages/temper-placer/tests/core/test_survivor_rust_differential.py"
        _make_tree(tmp_path, {survivor: ORACLE_SRC})

        registry = tmp_path / "scripts" / "inline_oracle_hashes.json"
        blocks, _, _ = discover_blocks(tmp_path)
        _write_registry(registry, blocks)
        assert run(tmp_path, registry).findings == [], "pre-sweep tree should be clean"

        # ...and now the sweep deletes the file, exactly as 35e3f914a did.
        (tmp_path / _SWEPT_FILE).unlink()

        report = run(tmp_path, registry)
        deleted = [f for f in report.findings if f.status == DELETED]
        assert len(deleted) >= 13, (
            "gate must flag every pinned inline oracle the sweep destroyed; "
            f"got {len(deleted)}"
        )
        assert any(f.key.endswith("::_oracle_coo_matmul") for f in deleted)

    @pytest.mark.skipif(not _have_sweep_commit(), reason=f"{_SWEEP} not in this clone")
    def test_file_based_gate_could_not_see_them(self):
        """Why the gate was needed: none of the destroyed blocks lived in a
        file the ``_*_py_oracle.py`` registry could ever have matched."""
        assert not Path(_SWEPT_FILE).name.startswith("_")
        assert not Path(_SWEPT_FILE).name.endswith("_py_oracle.py")


# ---------------------------------------------------------------------------
# TestCli
# ---------------------------------------------------------------------------


def _cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "check_inline_oracles.py"), *args],
        capture_output=True, text=True,
    )


class TestCli:
    def test_exit_clean_on_real_tree(self):
        assert _cli("--repo-root", str(REPO_ROOT)).returncode == EXIT_CLEAN

    def test_exit_drift_on_unregistered(self, tmp_path):
        registry, rel = _seed(tmp_path)
        _write_registry(registry, {block_key(rel, "_oracle_add"): sha256_text("x")})
        proc = _cli("--repo-root", str(tmp_path), "--registry", str(registry))
        assert proc.returncode == EXIT_DRIFT

    def test_exit_tool_error_on_missing_registry(self, tmp_path):
        _seed(tmp_path)
        proc = _cli("--repo-root", str(tmp_path), "--registry", str(tmp_path / "nope.json"))
        assert proc.returncode == EXIT_TOOL_ERROR


class TestGenerator:
    def test_generated_registry_matches_tree_and_is_idempotent(self, tmp_path):
        _seed(tmp_path)
        gen = REPO_ROOT / "scripts" / "update_inline_oracle_hashes.py"
        registry = tmp_path / "scripts" / "inline_oracle_hashes.json"
        first = subprocess.run(
            [sys.executable, str(gen), "--repo-root", str(tmp_path), "--registry", str(registry)],
            capture_output=True, text=True,
        )
        assert first.returncode == 0
        assert run(tmp_path, registry).findings == []
        body = registry.read_text()
        second = subprocess.run(
            [sys.executable, str(gen), "--repo-root", str(tmp_path), "--registry", str(registry)],
            capture_output=True, text=True,
        )
        assert second.returncode == 0
        assert registry.read_text() == body, "generator must be idempotent"

    def test_generator_refuses_empty_tree(self, tmp_path):
        gen = REPO_ROOT / "scripts" / "update_inline_oracle_hashes.py"
        registry = tmp_path / "scripts" / "inline_oracle_hashes.json"
        proc = subprocess.run(
            [sys.executable, str(gen), "--repo-root", str(tmp_path), "--registry", str(registry)],
            capture_output=True, text=True,
        )
        assert proc.returncode == 1
        assert "vacuous" in proc.stderr
        assert not registry.exists()
