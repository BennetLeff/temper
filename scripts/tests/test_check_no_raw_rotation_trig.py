"""Tests for check_no_raw_rotation_trig.py.

Most tests here monkeypatch ``GUARDED_FILES``/``EXEMPT_FUNCTIONS`` to point
at synthetic ``tmp_path`` fixtures rather than the real repo tree, so this
suite exercises the AST-detection logic itself (qualified calls, aliased
imports, bare ``from X import cos`` forms, the per-function exemption
mechanism, and the anti-vacuity backstops) independent of whatever the real
guarded files happen to contain on any given day.

``TestRealRepo`` is the one exception: it runs the gate against the actual
repo root with the real, hardcoded ``GUARDED_FILES``, pinning the
post-migration state (see the PR this test shipped with: 12 files
consolidated into ``temper_placer.geometry.kicad_transform``) as a
regression check -- if a future edit reintroduces raw trig into any of
those files, this test (and the real CI gate) both fail.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_no_raw_rotation_trig as gate  # noqa: E402


def _write(tmp_path: Path, rel: str, content: str) -> Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


class TestCleanSites:
    def test_sanctioned_import_only_is_clean(self, tmp_path, monkeypatch):
        _write(
            tmp_path,
            "a.py",
            "from temper_placer.geometry.kicad_transform import rotate_local_to_world\n"
            "\n"
            "def f(x, y, theta):\n"
            "    return rotate_local_to_world(x, y, theta)\n",
        )
        monkeypatch.setattr(gate, "GUARDED_FILES", ("a.py",))
        monkeypatch.setattr(gate, "EXEMPT_FUNCTIONS", frozenset())
        report = gate.run(tmp_path)
        assert report.violations == []
        assert report.files_checked == 1

    def test_unrelated_trig_free_file_is_clean(self, tmp_path, monkeypatch):
        _write(tmp_path, "a.py", "def f():\n    return 1 + 1\n")
        monkeypatch.setattr(gate, "GUARDED_FILES", ("a.py",))
        monkeypatch.setattr(gate, "EXEMPT_FUNCTIONS", frozenset())
        report = gate.run(tmp_path)
        assert report.violations == []


class TestViolations:
    def test_qualified_math_cos_sin(self, tmp_path, monkeypatch):
        _write(
            tmp_path,
            "a.py",
            "import math\n\ndef f(x, y, a):\n    return (x * math.cos(a), y * math.sin(a))\n",
        )
        monkeypatch.setattr(gate, "GUARDED_FILES", ("a.py",))
        monkeypatch.setattr(gate, "EXEMPT_FUNCTIONS", frozenset())
        report = gate.run(tmp_path)
        assert len(report.violations) == 2
        assert {v.lineno for v in report.violations} == {4}

    def test_qualified_numpy_alias(self, tmp_path, monkeypatch):
        _write(
            tmp_path,
            "a.py",
            "import numpy as np\n\ndef f(a):\n    return np.cos(a)\n",
        )
        monkeypatch.setattr(gate, "GUARDED_FILES", ("a.py",))
        monkeypatch.setattr(gate, "EXEMPT_FUNCTIONS", frozenset())
        report = gate.run(tmp_path)
        assert len(report.violations) == 1

    def test_aliased_math_import(self, tmp_path, monkeypatch):
        """import math as m; m.cos(...) must still be caught."""
        _write(
            tmp_path,
            "a.py",
            "import math as m\n\ndef f(a):\n    return m.cos(a)\n",
        )
        monkeypatch.setattr(gate, "GUARDED_FILES", ("a.py",))
        monkeypatch.setattr(gate, "EXEMPT_FUNCTIONS", frozenset())
        report = gate.run(tmp_path)
        assert len(report.violations) == 1

    def test_bare_from_import_form(self, tmp_path, monkeypatch):
        """from math import cos, sin; cos(a) must still be caught."""
        _write(
            tmp_path,
            "a.py",
            "from math import cos, sin\n\ndef f(a):\n    return (cos(a), sin(a))\n",
        )
        monkeypatch.setattr(gate, "GUARDED_FILES", ("a.py",))
        monkeypatch.setattr(gate, "EXEMPT_FUNCTIONS", frozenset())
        report = gate.run(tmp_path)
        assert len(report.violations) == 2

    def test_function_local_import_still_caught(self, tmp_path, monkeypatch):
        """A guarded file importing math inside a function (not top-level)
        is exactly as capable of hosting the bug -- must still be caught."""
        _write(
            tmp_path,
            "a.py",
            "def f(x, y, a):\n    import math\n    return (x * math.cos(a), y * math.sin(a))\n",
        )
        monkeypatch.setattr(gate, "GUARDED_FILES", ("a.py",))
        monkeypatch.setattr(gate, "EXEMPT_FUNCTIONS", frozenset())
        report = gate.run(tmp_path)
        assert len(report.violations) == 2

    def test_unrelated_math_calls_not_flagged(self, tmp_path, monkeypatch):
        """math.radians/math.hypot/math.sqrt etc. must not trip this gate --
        only cos/sin are the rotation-formula signature."""
        _write(
            tmp_path,
            "a.py",
            "import math\n\ndef f(a, x, y):\n"
            "    r = math.radians(a)\n"
            "    d = math.hypot(x, y)\n"
            "    return math.sqrt(d) + r\n",
        )
        monkeypatch.setattr(gate, "GUARDED_FILES", ("a.py",))
        monkeypatch.setattr(gate, "EXEMPT_FUNCTIONS", frozenset())
        report = gate.run(tmp_path)
        assert report.violations == []


class TestExemptFunctions:
    def test_exempted_function_is_not_flagged(self, tmp_path, monkeypatch):
        _write(
            tmp_path,
            "a.py",
            "import math\n\n"
            "def _corners(a):\n    return math.cos(a), math.sin(a)\n\n"
            "def _rotate(a):\n    return math.cos(a), math.sin(a)\n",
        )
        monkeypatch.setattr(gate, "GUARDED_FILES", ("a.py",))
        monkeypatch.setattr(gate, "EXEMPT_FUNCTIONS", frozenset({("a.py", "_corners")}))
        report = gate.run(tmp_path)
        # Only _rotate's two calls should be flagged; _corners' two are exempt.
        assert len(report.violations) == 2
        assert all(v.lineno == 7 for v in report.violations)

    def test_exemption_scoped_to_named_file_only(self, tmp_path, monkeypatch):
        """An exemption for a.py::_corners must not exempt b.py::_corners."""
        _write(tmp_path, "a.py", "def _corners():\n    return 1\n")
        _write(
            tmp_path,
            "b.py",
            "import math\n\ndef _corners(a):\n    return math.cos(a)\n",
        )
        monkeypatch.setattr(gate, "GUARDED_FILES", ("a.py", "b.py"))
        monkeypatch.setattr(gate, "EXEMPT_FUNCTIONS", frozenset({("a.py", "_corners")}))
        report = gate.run(tmp_path)
        assert len(report.violations) == 1
        assert report.violations[0].path == "b.py"


class TestAntiVacuity:
    def test_missing_guarded_file_is_gate_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(gate, "GUARDED_FILES", ("does_not_exist.py",))
        monkeypatch.setattr(gate, "EXEMPT_FUNCTIONS", frozenset())
        with pytest.raises(gate.GateError, match="does not exist"):
            gate.run(tmp_path)

    def test_empty_guarded_files_is_gate_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(gate, "GUARDED_FILES", ())
        monkeypatch.setattr(gate, "EXEMPT_FUNCTIONS", frozenset())
        with pytest.raises(gate.GateError, match="empty"):
            gate.run(tmp_path)

    def test_unparseable_file_is_gate_error(self, tmp_path, monkeypatch):
        _write(tmp_path, "a.py", "def f(:\n    pass\n")
        monkeypatch.setattr(gate, "GUARDED_FILES", ("a.py",))
        monkeypatch.setattr(gate, "EXEMPT_FUNCTIONS", frozenset())
        with pytest.raises(gate.GateError, match="could not parse"):
            gate.run(tmp_path)


class TestFailBeforePassAfter:
    """Explicit before/after pair, without git stash, per this repo's own
    falsifier convention (mirrors test_check_isolation_keepout.py's
    TestFailBeforePassAfter)."""

    def test_reintroducing_raw_trig_fails_then_fixing_it_passes(self, tmp_path, monkeypatch):
        path = _write(
            tmp_path,
            "a.py",
            "from temper_placer.geometry.kicad_transform import rotate_local_to_world\n"
            "\n"
            "def f(x, y, theta):\n"
            "    return rotate_local_to_world(x, y, theta)\n",
        )
        monkeypatch.setattr(gate, "GUARDED_FILES", ("a.py",))
        monkeypatch.setattr(gate, "EXEMPT_FUNCTIONS", frozenset())

        assert gate.run(tmp_path).violations == []

        path.write_text(
            "import math\n\ndef f(x, y, theta):\n"
            "    c, s = math.cos(theta), math.sin(theta)\n"
            "    return (x * c - y * s, x * s + y * c)\n"
        )
        report = gate.run(tmp_path)
        assert len(report.violations) == 2

        path.write_text(
            "from temper_placer.geometry.kicad_transform import rotate_local_to_world\n"
            "\n"
            "def f(x, y, theta):\n"
            "    return rotate_local_to_world(x, y, theta)\n"
        )
        assert gate.run(tmp_path).violations == []


class TestRealRepo:
    """Pins the real repo's post-migration state: the 12 guarded files as
    they exist in this tree today must be clean."""

    def test_real_guarded_files_are_clean(self):
        repo_root = Path(__file__).resolve().parents[2]
        report = gate.run(repo_root)
        assert report.violations == [], report.violations
        assert report.files_checked == len(gate.GUARDED_FILES)
