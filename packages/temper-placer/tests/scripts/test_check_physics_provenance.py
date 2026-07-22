"""Tests for scripts/check_physics_provenance.py."""

from __future__ import annotations

import ast
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

# Inject scripts/ so we can import the gate script
_SCRIPTS = Path(__file__).resolve().parent.parent.parent.parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS))

import check_physics_provenance as gate

PHYS_PREFIX = "packages/temper-placer/src/temper_placer/physics"


def _key(filename: str, name: str) -> str:
    """Build an allowlist key with the standard repo-relative path prefix."""
    return f"{PHYS_PREFIX}/{filename}::{name}"


@pytest.fixture
def tmp_repo():
    """Create a temp repo-root with a physics/ subdir, yield paths."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        phys = root / "packages" / "temper-placer" / "src" / "temper_placer" / "physics"
        phys.mkdir(parents=True)
        yield root, phys


# ---------------------------------------------------------------------------
# Unit tests for internal functions
# ---------------------------------------------------------------------------


class TestFloatConstants:
    def test_simple_float(self):
        tree = ast.parse("X = 3.14")
        node = tree.body[0]
        assert gate._float_constants(node.value) == [3.14]

    def test_int_skipped(self):
        tree = ast.parse("X = 5")
        node = tree.body[0]
        assert gate._float_constants(node.value) == []

    def test_string_skipped(self):
        tree = ast.parse('X = "hello"')
        node = tree.body[0]
        assert gate._float_constants(node.value) == []

    def test_tuple_of_floats(self):
        tree = ast.parse("a, b = 1.0, 2.0")
        node = tree.body[0]
        assert gate._float_constants(node.value) == [1.0, 2.0]

    def test_binop_skipped(self):
        tree = ast.parse("X = 4 * 3.14")
        node = tree.body[0]
        assert gate._float_constants(node.value) == []

    def test_call_skipped(self):
        tree = ast.parse("X = float(5)")
        node = tree.body[0]
        assert gate._float_constants(node.value) == []

    def test_none_skipped(self):
        tree = ast.parse("X = None")
        node = tree.body[0]
        assert gate._float_constants(node.value) == []


class TestHasSourceComment:
    def test_same_line_source(self):
        lines = ["X = 3.14  # source: IEEE 1234"]
        assert gate._has_source_comment(lines, 1, 1) is True

    def test_preceding_line_source(self):
        lines = ["# source: IEEE 1234", "X = 3.14"]
        assert gate._has_source_comment(lines, 2, 2) is True

    def test_no_source(self):
        lines = ["X = 3.14"]
        assert gate._has_source_comment(lines, 1, 1) is False

    def test_because_not_source(self):
        lines = ["X = 3.14  # because: some reason"]
        assert gate._has_source_comment(lines, 1, 1) is False

    def test_source_on_line_before_with_gap(self):
        lines = ["# source: IEEE", "", "X = 3.14"]
        assert gate._has_source_comment(lines, 3, 3) is False

    def test_preceding_line_only_checked_one_back(self):
        lines = ["# source: IEEE 1234", "# another comment", "X = 3.14"]
        assert gate._has_source_comment(lines, 3, 3) is False

    def test_multi_line_span(self):
        lines = [
            "X = (",
            "    3.14  # source: IEEE",
            ")",
        ]
        assert gate._has_source_comment(lines, 1, 3) is True


class TestLoadAllowlist:
    def test_empty(self, tmp_path):
        p = tmp_path / "nonexistent.txt"
        assert gate.load_allowlist(p) == {}

    def test_basic_entries(self, tmp_path):
        p = tmp_path / "allowlist.txt"
        p.write_text(
            "path/to/file.py::CONST  # TODO: temper-123\n"
            "path/other.py::OTHER  # TODO: temper-xxx\n"
        )
        entries = gate.load_allowlist(p)
        assert entries == {
            "path/to/file.py::CONST": "TODO: temper-123",
            "path/other.py::OTHER": "TODO: temper-xxx",
        }

    def test_skips_header_comments(self, tmp_path):
        p = tmp_path / "allowlist.txt"
        p.write_text(
            "# Header comment\n"
            "# Another header\n"
            "\n"
            "key::NAME  # TODO: temper-1\n"
        )
        entries = gate.load_allowlist(p)
        assert "key::NAME" in entries

    def test_no_ticket_comment(self, tmp_path):
        p = tmp_path / "allowlist.txt"
        p.write_text("key::NAME\n")
        entries = gate.load_allowlist(p)
        assert entries == {"key::NAME": ""}


# ---------------------------------------------------------------------------
# Integration tests using temp files
# ---------------------------------------------------------------------------


class TestFindUndocumentedConstants:
    def test_happy_same_line(self, tmp_repo):
        root, phys = tmp_repo
        (phys / "test_mod.py").write_text("X = 3.14  # source: IEEE 1234\n")
        result = gate.find_undocumented_constants(phys, root)
        assert result == {}

    def test_happy_preceding_line(self, tmp_repo):
        root, phys = tmp_repo
        (phys / "test_mod.py").write_text(
            "# source: IEEE 1234\n"
            "X = 3.14\n"
        )
        result = gate.find_undocumented_constants(phys, root)
        assert result == {}

    def test_missing_source_triggers(self, tmp_repo):
        root, phys = tmp_repo
        (phys / "test_mod.py").write_text("X = 3.14\n")
        result = gate.find_undocumented_constants(phys, root)
        assert len(result) == 1
        for key, (lineno, val, name) in result.items():
            assert name == "X"
            assert val == 3.14
            assert lineno == 1

    def test_skips_function_body(self, tmp_repo):
        root, phys = tmp_repo
        (phys / "test_mod.py").write_text(
            "def f():\n"
            "    x = 3.14\n"
        )
        result = gate.find_undocumented_constants(phys, root)
        assert result == {}

    def test_skips_class_body(self, tmp_repo):
        root, phys = tmp_repo
        (phys / "test_mod.py").write_text(
            "class C:\n"
            "    x = 3.14\n"
        )
        result = gate.find_undocumented_constants(phys, root)
        assert result == {}

    def test_skips_function_default(self, tmp_repo):
        root, phys = tmp_repo
        (phys / "test_mod.py").write_text(
            "def f(x=3.14):\n"
            "    pass\n"
        )
        result = gate.find_undocumented_constants(phys, root)
        assert result == {}

    def test_skips_int(self, tmp_repo):
        root, phys = tmp_repo
        (phys / "test_mod.py").write_text("N = 5\n")
        result = gate.find_undocumented_constants(phys, root)
        assert result == {}

    def test_skips_string(self, tmp_repo):
        root, phys = tmp_repo
        (phys / 'test_mod.py').write_text('NAME = "foo"\n')
        result = gate.find_undocumented_constants(phys, root)
        assert result == {}

    def test_no_module_level_floats(self, tmp_repo):
        root, phys = tmp_repo
        (phys / "test_mod.py").write_text("# just a comment\n")
        result = gate.find_undocumented_constants(phys, root)
        assert result == {}

    def test_tuple_assignment_handled(self, tmp_repo):
        root, phys = tmp_repo
        (phys / "test_mod.py").write_text("a, b = 1.0, 2.0\n")
        result = gate.find_undocumented_constants(phys, root)
        # Tuple unpacked floats are matched — by _float_constants
        assert len(result) >= 1

    def test_multiple_violations(self, tmp_repo):
        root, phys = tmp_repo
        (phys / "test_mod.py").write_text(
            "A = 1.0\n"
            "B = 2.0\n"
        )
        result = gate.find_undocumented_constants(phys, root)
        assert len(result) == 2

    def test_skips_init_py(self, tmp_repo):
        root, phys = tmp_repo
        (phys / "__init__.py").write_text("X = 3.14\n")
        result = gate.find_undocumented_constants(phys, root)
        assert result == {}

    def test_preceding_line_docstring_not_false_positive(self, tmp_repo):
        root, phys = tmp_repo
        (phys / "test_mod.py").write_text(
            '"""Module docstring."""\n'
            "\n"
            "X = 3.14  # source: IEEE\n"
        )
        result = gate.find_undocumented_constants(phys, root)
        assert result == {}

    def test_because_not_source(self, tmp_repo):
        root, phys = tmp_repo
        (phys / "test_mod.py").write_text("X = 3.14  # because: reason\n")
        result = gate.find_undocumented_constants(phys, root)
        assert len(result) == 1


# ---------------------------------------------------------------------------
# --init mode tests
# ---------------------------------------------------------------------------


class TestInitMode:
    def test_populates_allowlist(self, tmp_repo, tmp_path):
        root, phys = tmp_repo
        (phys / "a.py").write_text("X = 1.0\nY = 2.0\n")
        (phys / "b.py").write_text("Z = 3.0  # source: IEEE\n")

        al_path = tmp_path / ".physics-provenance-allowlist"

        with mock.patch.object(sys, "argv", [
            "check_physics_provenance.py",
            "--init",
            "--physics-dir", str(phys),
            "--allowlist", str(al_path),
            "--repo-root", str(root),
        ]):
            try:
                gate.main()
            except SystemExit as e:
                assert e.code == 0

        content = al_path.read_text()
        assert "# Physics provenance allowlist" in content
        assert _key("a.py", "X") in content
        assert _key("a.py", "Y") in content
        assert "b.py::Z" not in content  # has source comment
        assert "TODO: temper-xxx" in content


# ---------------------------------------------------------------------------
# Default gate mode tests
# ---------------------------------------------------------------------------


class TestGateMode:
    def test_passes_when_all_documented(self, tmp_repo, tmp_path):
        root, phys = tmp_repo
        (phys / "m.py").write_text("X = 1.0  # source: IEEE\n")

        al_path = tmp_path / ".physics-provenance-allowlist"
        al_path.write_text("# empty allowlist\n")

        with mock.patch.object(sys, "argv", [
            "check_physics_provenance.py",
            "--physics-dir", str(phys),
            "--allowlist", str(al_path),
            "--repo-root", str(root),
        ]):
            try:
                gate.main()
            except SystemExit as e:
                assert e.code == 0

    def test_fails_on_undocumented(self, tmp_repo, tmp_path):
        root, phys = tmp_repo
        (phys / "m.py").write_text("X = 1.0\n")

        al_path = tmp_path / ".physics-provenance-allowlist"
        al_path.write_text("# empty\n")

        with mock.patch.object(sys, "argv", [
            "check_physics_provenance.py",
            "--physics-dir", str(phys),
            "--allowlist", str(al_path),
            "--repo-root", str(root),
        ]):
            try:
                gate.main()
            except SystemExit as e:
                assert e.code == 1

    def test_allowlisted_passes(self, tmp_repo, tmp_path):
        root, phys = tmp_repo
        (phys / "m.py").write_text("X = 1.0\n")

        al_path = tmp_path / ".physics-provenance-allowlist"
        al_path.write_text(f"{_key('m.py', 'X')}  # TODO: temper-123\n")

        with mock.patch.object(sys, "argv", [
            "check_physics_provenance.py",
            "--physics-dir", str(phys),
            "--allowlist", str(al_path),
            "--repo-root", str(root),
        ]):
            try:
                gate.main()
            except SystemExit as e:
                assert e.code == 0

    def test_warns_on_stale_entry(self, tmp_repo, tmp_path, capsys):
        root, phys = tmp_repo
        (phys / "m.py").write_text("X = 1.0  # source: IEEE\n")

        al_path = tmp_path / ".physics-provenance-allowlist"
        al_path.write_text(f"{_key('m.py', 'X')}  # TODO: temper-123\n")

        with mock.patch.object(sys, "argv", [
            "check_physics_provenance.py",
            "--physics-dir", str(phys),
            "--allowlist", str(al_path),
            "--repo-root", str(root),
        ]):
            try:
                gate.main()
            except SystemExit as e:
                assert e.code == 0

        captured = capsys.readouterr()
        assert "WARNING" in captured.out or "WARNING" in captured.err

    def test_fails_allowlist_missing_ticket(self, tmp_repo, tmp_path):
        root, phys = tmp_repo
        (phys / "m.py").write_text("X = 1.0\n")

        al_path = tmp_path / ".physics-provenance-allowlist"
        al_path.write_text(f"{_key('m.py', 'X')}\n")  # no TODO

        with mock.patch.object(sys, "argv", [
            "check_physics_provenance.py",
            "--physics-dir", str(phys),
            "--allowlist", str(al_path),
            "--repo-root", str(root),
        ]):
            try:
                gate.main()
            except SystemExit as e:
                assert e.code == 1

    def test_fails_missing_physics_dir(self, tmp_path):
        al_path = tmp_path / ".physics-provenance-allowlist"
        al_path.write_text("# empty\n")

        with mock.patch.object(sys, "argv", [
            "check_physics_provenance.py",
            "--physics-dir", str(tmp_path / "nonexistent"),
            "--allowlist", str(al_path),
            "--repo-root", str(tmp_path),
        ]):
            try:
                gate.main()
            except SystemExit as e:
                assert e.code == 1


# ---------------------------------------------------------------------------
# --check-shrink mode tests
# ---------------------------------------------------------------------------


class TestCheckShrinkMode:
    def test_skip_when_main_unavailable(self, tmp_repo, tmp_path):
        root, phys = tmp_repo
        (phys / "m.py").write_text("X = 1.0\n")
        al_path = tmp_path / ".physics-provenance-allowlist"
        al_path.write_text(f"{_key('m.py', 'X')}  # TODO: temper-xxx\n")

        with mock.patch.object(gate, "git_show_main_allowlist", return_value=None):
            result = gate.check_shrink_mode(
                gate.load_allowlist(al_path), phys, root,
                ".physics-provenance-allowlist",
            )
            assert result == 0

    def test_addition_without_ticket_fails(self, tmp_repo, tmp_path):
        root, phys = tmp_repo
        (phys / "m.py").write_text("X = 1.0\n")
        al_path = tmp_path / ".physics-provenance-allowlist"
        al_path.write_text(f"{_key('m.py', 'X')}\n")  # no ticket

        with mock.patch.object(gate, "git_show_main_allowlist", return_value=""):
            result = gate.check_shrink_mode(
                gate.load_allowlist(al_path), phys, root,
                ".physics-provenance-allowlist",
            )
            assert result == 1

    def test_addition_with_ticket_passes(self, tmp_repo, tmp_path):
        root, phys = tmp_repo
        (phys / "m.py").write_text("X = 1.0\n")
        al_path = tmp_path / ".physics-provenance-allowlist"
        al_path.write_text(f"{_key('m.py', 'X')}  # TODO: temper-123\n")

        with mock.patch.object(gate, "git_show_main_allowlist", return_value=""):
            result = gate.check_shrink_mode(
                gate.load_allowlist(al_path), phys, root,
                ".physics-provenance-allowlist",
            )
            assert result == 0

    def test_removal_with_source_gained_passes(self, tmp_repo, tmp_path):
        root, phys = tmp_repo
        (phys / "m.py").write_text("X = 1.0  # source: IEEE\n")
        al_path = tmp_path / ".physics-provenance-allowlist"
        al_path.write_text("# empty\n")

        with mock.patch.object(gate, "git_show_main_allowlist",
                               return_value=f"{_key('m.py', 'X')}  # TODO: temper-123\n"):
            result = gate.check_shrink_mode(
                gate.load_allowlist(al_path), phys, root,
                ".physics-provenance-allowlist",
            )
            assert result == 0

    def test_removal_with_constant_deleted_passes(self, tmp_repo, tmp_path):
        root, phys = tmp_repo
        (phys / "m.py").write_text("# empty file\n")
        al_path = tmp_path / ".physics-provenance-allowlist"
        al_path.write_text("# empty\n")

        with mock.patch.object(gate, "git_show_main_allowlist",
                               return_value=f"nonexistent/file.py::DELETED  # TODO: temper-123\n"):
            result = gate.check_shrink_mode(
                gate.load_allowlist(al_path), phys, root,
                ".physics-provenance-allowlist",
            )
            assert result == 0

    def test_removal_without_source_fails(self, tmp_repo, tmp_path):
        root, phys = tmp_repo
        (phys / "m.py").write_text("X = 1.0\n")
        al_path = tmp_path / ".physics-provenance-allowlist"
        al_path.write_text("# empty\n")

        with mock.patch.object(gate, "git_show_main_allowlist",
                               return_value=f"{_key('m.py', 'X')}  # TODO: temper-123\n"):
            result = gate.check_shrink_mode(
                gate.load_allowlist(al_path), phys, root,
                ".physics-provenance-allowlist",
            )
            assert result == 1

    def test_no_changes_passes(self, tmp_repo, tmp_path):
        root, phys = tmp_repo
        (phys / "m.py").write_text("X = 1.0\n")
        al_path = tmp_path / ".physics-provenance-allowlist"
        al_path.write_text(f"{_key('m.py', 'X')}  # TODO: temper-123\n")

        with mock.patch.object(gate, "git_show_main_allowlist",
                               return_value=f"{_key('m.py', 'X')}  # TODO: temper-123\n"):
            result = gate.check_shrink_mode(
                gate.load_allowlist(al_path), phys, root,
                ".physics-provenance-allowlist",
            )
            assert result == 0
