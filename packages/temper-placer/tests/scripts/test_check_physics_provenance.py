"""Tests for ``scripts/check_physics_provenance.py``.

Uses temporary directories with synthetic ``.py`` files to exercise every
codepath: happy paths, edge cases, error paths, init mode, and shrink mode.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check_physics_provenance.py"
REPO_ROOT = Path(__file__).resolve().parents[4]


def _run_gate(
    tmp: Path,
    physics_dir: Path | None = None,
    *,
    init: bool = False,
    check_shrink: bool = False,
    allowlist: Path | None = None,
    expect_fail: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run the gate script against a temporary physics directory."""
    if physics_dir is None:
        physics_dir = tmp / "physics"
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--physics-dir",
        str(physics_dir),
        "--allowlist",
        str(allowlist if allowlist is not None else tmp / ".physics-provenance-allowlist"),
    ]
    if init:
        cmd.append("--init")
    if check_shrink:
        cmd.append("--check-shrink")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=tmp,
        env=env,
    )
    if expect_fail:
        assert result.returncode != 0, (
            f"Expected non-zero exit. stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    else:
        assert result.returncode == 0, (
            f"Expected exit 0. stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


# ---------------------------------------------------------------------------
# direct-function tests (import the module for unit-level checks)
# ---------------------------------------------------------------------------

def _import_module():
    """Import the gate script as a module for direct function calls."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "check_physics_provenance", str(SCRIPT)
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["check_physics_provenance"] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# happy path
# ---------------------------------------------------------------------------


def test_same_line_source_comment_passes(tmp_path: Path) -> None:
    phys = tmp_path / "physics"
    phys.mkdir()
    (phys / "constants.py").write_text("MY_CONST = 3.14  # source: IEEE 1234\n")
    _run_gate(tmp_path, phys)


def test_preceding_line_source_comment_passes(tmp_path: Path) -> None:
    phys = tmp_path / "physics"
    phys.mkdir()
    (phys / "constants.py").write_text("# source: IEEE 1234\nMY_CONST = 3.14\n")
    _run_gate(tmp_path, phys)


def test_no_module_level_floats_passes(tmp_path: Path) -> None:
    phys = tmp_path / "physics"
    phys.mkdir()
    (phys / "empty.py").write_text(
        "def helper(x: float = 3.14) -> float:\n"
        "    y = 2.72\n"
        "    return x + y\n"
    )
    _run_gate(tmp_path, phys)


def test_init_populates_allowlist(tmp_path: Path) -> None:
    phys = tmp_path / "physics"
    phys.mkdir()
    (phys / "a.py").write_text("ALPHA = 1.0  # source: somewhere\n")
    (phys / "b.py").write_text("BETA = 2.0\n")

    result = _run_gate(tmp_path, phys, init=True)
    assert "Allowlist populated with 1 entries" in result.stdout

    al = tmp_path / ".physics-provenance-allowlist"
    content = al.read_text()
    assert "BETA" in content
    assert "ALPHA" not in content


def test_init_empty_all_documented(tmp_path: Path) -> None:
    phys = tmp_path / "physics"
    phys.mkdir()
    (phys / "a.py").write_text("ALPHA = 1.0  # source: somewhere\n")
    result = _run_gate(tmp_path, phys, init=True)
    assert "Allowlist populated with 0 entries" in result.stdout


# ---------------------------------------------------------------------------
# edge cases
# ---------------------------------------------------------------------------


def test_float_in_function_body_skipped(tmp_path: Path) -> None:
    phys = tmp_path / "physics"
    phys.mkdir()
    (phys / "func.py").write_text("def f():\n    x = 3.14\n")
    _run_gate(tmp_path, phys)


def test_float_in_class_body_skipped(tmp_path: Path) -> None:
    phys = tmp_path / "physics"
    phys.mkdir()
    (phys / "cls.py").write_text("class C:\n    x = 3.14\n")
    _run_gate(tmp_path, phys)


def test_int_constant_skipped(tmp_path: Path) -> None:
    phys = tmp_path / "physics"
    phys.mkdir()
    (phys / "ints.py").write_text("N = 5\n")
    _run_gate(tmp_path, phys)


def test_string_constant_skipped(tmp_path: Path) -> None:
    phys = tmp_path / "physics"
    phys.mkdir()
    (phys / "strs.py").write_text('NAME = "foo"\n')
    _run_gate(tmp_path, phys)


def test_float_default_in_signature_skipped(tmp_path: Path) -> None:
    phys = tmp_path / "physics"
    phys.mkdir()
    (phys / "sig.py").write_text("def f(x=3.14):\n    pass\n")
    _run_gate(tmp_path, phys)


def test_preceding_line_from_doc_comment_block(tmp_path: Path) -> None:
    phys = tmp_path / "physics"
    phys.mkdir()
    (phys / "doc.py").write_text(
        "# This is a doc-comment block\n"
        "# that explains context\n"
        "# source: from the datasheet page 42\n"
        "MY_CONST = 1.23\n"
    )
    _run_gate(tmp_path, phys)


def test_underscore_prefixed_private_file_skipped(tmp_path: Path) -> None:
    phys = tmp_path / "physics"
    phys.mkdir()
    (phys / "_internal.py").write_text("MY_CONST = 1.0\n")
    _run_gate(tmp_path, phys)


def test_syntax_error_file_skipped(tmp_path: Path) -> None:
    phys = tmp_path / "physics"
    phys.mkdir()
    (phys / "broken.py").write_text("this is not valid python {{{")
    _run_gate(tmp_path, phys)


# ---------------------------------------------------------------------------
# error paths
# ---------------------------------------------------------------------------


def test_missing_source_comment_fails(tmp_path: Path) -> None:
    phys = tmp_path / "physics"
    phys.mkdir()
    (phys / "missing.py").write_text("BAD_CONST = 99.9\n")
    result = _run_gate(tmp_path, phys, expect_fail=True)
    assert "FAIL" in result.stdout
    assert "BAD_CONST" in result.stdout
    assert "99.9" in result.stdout


def test_multiple_violations_reported(tmp_path: Path) -> None:
    phys = tmp_path / "physics"
    phys.mkdir()
    (phys / "a.py").write_text("BAD_A = 1.0\n")
    (phys / "b.py").write_text("BAD_B = 2.0\n")
    result = _run_gate(tmp_path, phys, expect_fail=True)
    assert "BAD_A" in result.stdout
    assert "BAD_B" in result.stdout


def test_allowlist_ticket_missing_fails(tmp_path: Path) -> None:
    phys = tmp_path / "physics"
    phys.mkdir()
    (phys / "a.py").write_text("X = 1.0\n")
    al = tmp_path / ".physics-provenance-allowlist"
    al.write_text("a.py::X  # missing ticket\n")
    result = _run_gate(tmp_path, phys, expect_fail=True)
    assert "missing ticket" in result.stdout


def test_allowlist_absorbs_violation(tmp_path: Path) -> None:
    phys = tmp_path / "physics"
    phys.mkdir()
    (phys / "a.py").write_text("X = 1.0\n")
    al = tmp_path / ".physics-provenance-allowlist"
    al.write_text("a.py::X  # TODO: temper-999\n")
    _run_gate(tmp_path, phys)


def test_stale_entry_warning(tmp_path: Path) -> None:
    phys = tmp_path / "physics"
    phys.mkdir()
    (phys / "a.py").write_text("X = 1.0  # source: now documented\n")
    al = tmp_path / ".physics-provenance-allowlist"
    al.write_text("a.py::X  # TODO: temper-999\n")
    result = _run_gate(tmp_path, phys)
    assert "WARNING" in result.stdout


def test_allowlist_header_comments_ignored(tmp_path: Path) -> None:
    phys = tmp_path / "physics"
    phys.mkdir()
    (phys / "a.py").write_text("X = 1.0\n")
    al = tmp_path / ".physics-provenance-allowlist"
    al.write_text(
        "# header comment\n"
        "a.py::X  # TODO: temper-999\n"
        "# another comment\n"
    )
    _run_gate(tmp_path, phys)


# ---------------------------------------------------------------------------
# --check-shrink integration
# ---------------------------------------------------------------------------


def test_check_shrink_skip_when_no_origin_main(tmp_path: Path) -> None:
    phys = tmp_path / "physics"
    phys.mkdir()
    (phys / "a.py").write_text("X = 1.0  # source: ok\n")
    al = tmp_path / ".physics-provenance-allowlist"
    al.write_text("")
    result = _run_gate(tmp_path, phys, check_shrink=True)
    assert "skipping" in result.stdout.lower()
    assert "shrink check" in result.stdout.lower()


def test_check_shrink_fails_on_removal_without_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    phys = tmp_path / "physics"
    phys.mkdir()
    (phys / "a.py").write_text("X = 1.0\n")

    mod = _import_module()
    monkeypatch.setattr(
        mod, "git_show_main_allowlist",
        lambda: "a.py::X  # TODO: temper-999\n",
    )
    failures = mod.check_shrink_mode({"a.py::X": "TODO: temper-999"}, phys)
    assert failures == 0  # entry is NOT removed in this case; test the actual removal

    # Actually test removal: current has {} but main had a.py::X
    failures = mod.check_shrink_mode({}, phys)
    assert failures > 0


def test_check_shrink_passes_on_removal_with_source(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    phys = tmp_path / "physics"
    phys.mkdir()
    (phys / "a.py").write_text("X = 1.0  # source: added now\n")

    mod = _import_module()
    monkeypatch.setattr(
        mod, "git_show_main_allowlist",
        lambda: "a.py::X  # TODO: temper-999\n",
    )
    failures = mod.check_shrink_mode({}, phys)
    assert failures == 0


def test_check_shrink_passes_on_removal_deleted_constant(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    phys = tmp_path / "physics"
    phys.mkdir()
    (phys / "a.py").write_text("Y = 2.0  # source: something\n")

    mod = _import_module()
    monkeypatch.setattr(
        mod, "git_show_main_allowlist",
        lambda: "a.py::X  # TODO: temper-999\n",
    )
    failures = mod.check_shrink_mode({}, phys)
    assert failures == 0


def test_check_shrink_fails_on_add_without_ticket(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    phys = tmp_path / "physics"
    phys.mkdir()

    mod = _import_module()
    monkeypatch.setattr(
        mod, "git_show_main_allowlist",
        lambda: "",
    )
    failures = mod.check_shrink_mode(
        {"a.py::X": "no ticket here"}, phys
    )
    assert failures > 0
