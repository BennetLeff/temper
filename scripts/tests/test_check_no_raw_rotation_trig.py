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
        report = gate.run(tmp_path, include_rust=False)
        assert report.violations == []
        assert report.files_checked == 1

    def test_unrelated_trig_free_file_is_clean(self, tmp_path, monkeypatch):
        _write(tmp_path, "a.py", "def f():\n    return 1 + 1\n")
        monkeypatch.setattr(gate, "GUARDED_FILES", ("a.py",))
        monkeypatch.setattr(gate, "EXEMPT_FUNCTIONS", frozenset())
        report = gate.run(tmp_path, include_rust=False)
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
        report = gate.run(tmp_path, include_rust=False)
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
        report = gate.run(tmp_path, include_rust=False)
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
        report = gate.run(tmp_path, include_rust=False)
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
        report = gate.run(tmp_path, include_rust=False)
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
        report = gate.run(tmp_path, include_rust=False)
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
        report = gate.run(tmp_path, include_rust=False)
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
        report = gate.run(tmp_path, include_rust=False)
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
        report = gate.run(tmp_path, include_rust=False)
        assert len(report.violations) == 1
        assert report.violations[0].path == "b.py"


class TestAntiVacuity:
    def test_missing_guarded_file_is_gate_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(gate, "GUARDED_FILES", ("does_not_exist.py",))
        monkeypatch.setattr(gate, "EXEMPT_FUNCTIONS", frozenset())
        with pytest.raises(gate.GateError, match="does not exist"):
            gate.run(tmp_path, include_rust=False)

    def test_empty_guarded_files_is_gate_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(gate, "GUARDED_FILES", ())
        monkeypatch.setattr(gate, "EXEMPT_FUNCTIONS", frozenset())
        with pytest.raises(gate.GateError, match="empty"):
            gate.run(tmp_path, include_rust=False)

    def test_unparseable_file_is_gate_error(self, tmp_path, monkeypatch):
        _write(tmp_path, "a.py", "def f(:\n    pass\n")
        monkeypatch.setattr(gate, "GUARDED_FILES", ("a.py",))
        monkeypatch.setattr(gate, "EXEMPT_FUNCTIONS", frozenset())
        with pytest.raises(gate.GateError, match="could not parse"):
            gate.run(tmp_path, include_rust=False)


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

        assert gate.run(tmp_path, include_rust=False).violations == []

        path.write_text(
            "import math\n\ndef f(x, y, theta):\n"
            "    c, s = math.cos(theta), math.sin(theta)\n"
            "    return (x * c - y * s, x * s + y * c)\n"
        )
        report = gate.run(tmp_path, include_rust=False)
        assert len(report.violations) == 2

        path.write_text(
            "from temper_placer.geometry.kicad_transform import rotate_local_to_world\n"
            "\n"
            "def f(x, y, theta):\n"
            "    return rotate_local_to_world(x, y, theta)\n"
        )
        assert gate.run(tmp_path, include_rust=False).violations == []


class TestRealRepo:
    """Pins the real repo's post-migration state: the 18 guarded files as
    they exist in this tree today must be clean."""

    def test_real_guarded_files_are_clean(self):
        repo_root = Path(__file__).resolve().parents[2]
        report = gate.run(repo_root)
        assert report.violations == [], report.violations
        assert report.files_checked == len(gate.GUARDED_FILES)


# ===========================================================================
# The Rust half (added 2026-08-18)
# ===========================================================================


def _rust_env(tmp_path, monkeypatch, files, exempt=frozenset(), twins=()):
    """Point the Rust registries at a synthetic tree. The sanctioned file
    must exist for run() to proceed, so every fixture creates one."""
    sanctioned = "packages/temper-geometry/src/kicad_transform.rs"
    _write(tmp_path, sanctioned, "// the one sanctioned copy\n")
    monkeypatch.setattr(gate, "SANCTIONED_RUST_FILE", sanctioned)
    monkeypatch.setattr(gate, "GUARDED_RUST_FILES", tuple(files))
    monkeypatch.setattr(gate, "RUST_EXEMPT_FUNCTIONS", frozenset(exempt))
    monkeypatch.setattr(gate, "RUST_QUADRANT_TABLE_TWINS", tuple(twins))


class TestRustDetection:
    def test_delegating_to_kicad_transform_is_clean(self, tmp_path, monkeypatch):
        _write(
            tmp_path,
            "a.rs",
            "fn rotate_local_to_world(x: f64, y: f64, t: f64) -> (f64, f64) {\n"
            "    crate::kicad_transform::rotate_local_to_world(x, y, t)\n"
            "}\n",
        )
        _rust_env(tmp_path, monkeypatch, ["a.rs"])
        report = gate.run(tmp_path, include_python=False)
        assert report.violations == []
        assert report.rust_files_checked == 1

    @pytest.mark.parametrize(
        "call",
        [
            "let c = theta.cos();",
            "let s = theta.sin();",
            "let (s, c) = theta.sin_cos();",
            "let c = f64::cos(theta);",
            "let c = host_math::cos(theta);",
            "let c = crate::host_math::sin(theta);",
            "let (c, s) = math_cos_sin(theta);",
            "let c = math_cos(theta);",
            "let (c, s) = cos_sin(theta)?;",
            "let c = pymath::cos(theta);",
            "let c = hostmath::sin(theta);",
        ],
    )
    def test_every_trig_spelling_the_sweep_found_is_caught(self, tmp_path, monkeypatch, call):
        """A lint keyed only on ``.cos()`` would have missed five of the ten
        Rust sites -- they call this repo's dlsym host-libm shims, not
        ``f64::cos``. Each spelling is pinned individually."""
        _write(tmp_path, "a.rs", "fn f(theta: f64) {\n    " + call + "\n}\n")
        _rust_env(tmp_path, monkeypatch, ["a.rs"])
        report = gate.run(tmp_path, include_python=False)
        assert len(report.violations) == 1, report.violations
        assert report.violations[0].path == "a.rs"

    def test_comments_are_not_violations(self, tmp_path, monkeypatch):
        _write(
            tmp_path,
            "a.rs",
            "/// R(-theta) is `let (c, s) = math_cos_sin(t); (x*c + y*s, -x*s + y*c)`\n"
            "// let c = theta.cos();\n"
            "fn f(x: f64) -> f64 {\n"
            "    x // theta.sin() mentioned in a trailing comment\n"
            "}\n",
        )
        _rust_env(tmp_path, monkeypatch, ["a.rs"])
        assert gate.run(tmp_path, include_python=False).violations == []

    def test_double_slash_inside_a_string_literal_is_not_a_comment(self, tmp_path, monkeypatch):
        """The comment stripper must not truncate at a ``//`` inside a
        string, or a rotation written after one would be MISSED -- the only
        direction of error this gate cannot tolerate."""
        _write(
            tmp_path,
            "a.rs",
            'fn f(t: f64) -> f64 {\n    let _u = "https://example.invalid"; let c = t.cos(); c\n}\n',
        )
        _rust_env(tmp_path, monkeypatch, ["a.rs"])
        assert len(gate.run(tmp_path, include_python=False).violations) == 1

    def test_exemption_is_per_function_not_per_file(self, tmp_path, monkeypatch):
        _write(
            tmp_path,
            "a.rs",
            "fn exempted(t: f64) -> f64 {\n    t.cos()\n}\n"
            "\n"
            "fn sneaky(x: f64, y: f64, t: f64) -> (f64, f64) {\n"
            "    let c = t.cos();\n"
            "    let s = t.sin();\n"
            "    (x * c + y * s, -x * s + y * c)\n"
            "}\n",
        )
        _rust_env(tmp_path, monkeypatch, ["a.rs"], exempt={("a.rs", "exempted")})
        report = gate.run(tmp_path, include_python=False)
        assert len(report.violations) == 2
        assert all("sneaky" in v.detail for v in report.violations)

    def test_nested_block_does_not_leak_the_exemption(self, tmp_path, monkeypatch):
        """A brace-depth bug that let an exemption leak past its function's
        closing brace would silently exempt the next function."""
        _write(
            tmp_path,
            "a.rs",
            "fn exempted(t: f64) -> f64 {\n"
            "    if t > 0.0 {\n"
            "        return t.cos();\n"
            "    }\n"
            "    t.sin()\n"
            "}\n"
            "\n"
            "fn after(t: f64) -> f64 {\n"
            "    t.cos()\n"
            "}\n",
        )
        _rust_env(tmp_path, monkeypatch, ["a.rs"], exempt={("a.rs", "exempted")})
        report = gate.run(tmp_path, include_python=False)
        assert len(report.violations) == 1
        assert "after" in report.violations[0].detail


class TestRustAntiVacuity:
    def test_empty_rust_registry_is_gate_error(self, tmp_path, monkeypatch):
        _rust_env(tmp_path, monkeypatch, [])
        with pytest.raises(gate.GateError, match="empty"):
            gate.run(tmp_path, include_python=False)

    def test_missing_guarded_rust_file_is_gate_error(self, tmp_path, monkeypatch):
        _rust_env(tmp_path, monkeypatch, ["gone.rs"])
        with pytest.raises(gate.GateError, match="does not exist"):
            gate.run(tmp_path, include_python=False)

    def test_missing_sanctioned_file_is_gate_error(self, tmp_path, monkeypatch):
        _write(tmp_path, "a.rs", "fn f() {}\n")
        _rust_env(tmp_path, monkeypatch, ["a.rs"])
        monkeypatch.setattr(gate, "SANCTIONED_RUST_FILE", "packages/gone/kicad_transform.rs")
        with pytest.raises(gate.GateError, match="sanctioned"):
            gate.run(tmp_path, include_python=False)

    def test_guarding_the_sanctioned_file_is_gate_error(self, tmp_path, monkeypatch):
        """The one place the formula may live must never be scanned against
        itself -- doing so would push someone to delete the formula from the
        only file allowed to have it."""
        _rust_env(tmp_path, monkeypatch, ["packages/temper-geometry/src/kicad_transform.rs"])
        with pytest.raises(gate.GateError, match="never be guarded"):
            gate.run(tmp_path, include_python=False)

    def test_both_halves_disabled_is_gate_error(self, tmp_path):
        with pytest.raises(gate.GateError, match="vacuous"):
            gate.run(tmp_path, include_python=False, include_rust=False)


class TestRustMutation:
    """Flip a sign / drop a delegation and require the gate to catch it.

    A gate that only ever runs against a clean tree proves nothing about
    what it would do to a dirty one.
    """

    def test_reverting_a_migrated_site_to_the_inline_formula_fails(self, tmp_path, monkeypatch):
        path = _write(
            tmp_path,
            "a.rs",
            "fn rotate_local_to_world(x: f64, y: f64, t: f64) -> (f64, f64) {\n"
            "    crate::kicad_transform::rotate_local_to_world(x, y, t)\n"
            "}\n",
        )
        _rust_env(tmp_path, monkeypatch, ["a.rs"])
        assert gate.run(tmp_path, include_python=False).violations == []

        # The exact pre-2026-08-18 body of clearance_geometry.rs's copy.
        path.write_text(
            "fn rotate_local_to_world(x: f64, y: f64, t: f64) -> (f64, f64) {\n"
            "    let (c, s) = math_cos_sin(t);\n"
            "    (x * c + y * s, -x * s + y * c)\n"
            "}\n"
        )
        assert len(gate.run(tmp_path, include_python=False).violations) == 1

        path.write_text(
            "fn rotate_local_to_world(x: f64, y: f64, t: f64) -> (f64, f64) {\n"
            "    crate::kicad_transform::rotate_local_to_world(x, y, t)\n"
            "}\n"
        )
        assert gate.run(tmp_path, include_python=False).violations == []

    def test_a_wrong_sign_inline_copy_is_caught_just_like_a_right_one(self, tmp_path, monkeypatch):
        """The gate removes the CAPABILITY to type the formula; it does not
        try to decide which sign a locally-typed copy used. Both must fail,
        or the wrong one could be argued past review as 'just like the
        other copies'."""
        for body in (
            "    (x * c + y * s, -x * s + y * c)\n",  # R(-theta), correct
            "    (x * c - y * s, x * s + y * c)\n",  # R(+theta), the bug
        ):
            path = _write(
                tmp_path,
                "a.rs",
                "fn f(x: f64, y: f64, t: f64) -> (f64, f64) {\n"
                "    let (c, s) = math_cos_sin(t);\n" + body + "}\n",
            )
            _rust_env(tmp_path, monkeypatch, ["a.rs"])
            assert len(gate.run(tmp_path, include_python=False).violations) == 1, path.read_text()


class TestQuadrantTableTwins:
    _GOOD = (
        "fn project_onto_barrier_axis(local_x: f64, local_y: f64, rot_value: i64) -> f64 {\n"
        "    let (gx, gy) = match rot_value {\n"
        "        0 => (local_x, local_y),\n"
        "        1 => (local_y, -local_x),\n"
        "        2 => (-local_x, -local_y),\n"
        "        _ => (-local_y, local_x),\n"
        "    };\n"
        "    gx + gy\n"
        "}\n"
    )

    def _env(self, tmp_path, monkeypatch, a_src, b_src):
        _write(tmp_path, "a.rs", a_src)
        _write(tmp_path, "b.rs", b_src)
        _rust_env(
            tmp_path,
            monkeypatch,
            ["a.rs", "b.rs"],
            exempt={("a.rs", "project_onto_barrier_axis"), ("b.rs", "project_onto_barrier_axis")},
            twins=[("a.rs", "project_onto_barrier_axis", "b.rs", "project_onto_barrier_axis")],
        )

    def test_agreeing_twins_are_clean(self, tmp_path, monkeypatch):
        self._env(tmp_path, monkeypatch, self._GOOD, self._GOOD)
        report = gate.run(tmp_path, include_python=False)
        assert report.violations == []
        assert report.quadrant_twins_checked == 1

    def test_one_twin_drifting_fails(self, tmp_path, monkeypatch):
        """The failure mode the twins exist for: someone edits one copy of a
        table whose other copy is in a different crate."""
        mutated = self._GOOD.replace("1 => (local_y, -local_x),", "1 => (-local_y, local_x),")
        self._env(tmp_path, monkeypatch, self._GOOD, mutated)
        report = gate.run(tmp_path, include_python=False)
        assert len(report.violations) == 1
        assert report.violations[0].path == "b.rs"

    def test_both_twins_drifting_together_still_fails(self, tmp_path, monkeypatch):
        """Comparing the copies only against EACH OTHER would pass this.
        They are compared against a stated R(-theta) expectation instead."""
        mutated = self._GOOD.replace("1 => (local_y, -local_x),", "1 => (-local_y, local_x),")
        self._env(tmp_path, monkeypatch, mutated, mutated)
        report = gate.run(tmp_path, include_python=False)
        assert len(report.violations) == 2

    def test_a_dropped_arm_widened_into_the_catchall_fails(self, tmp_path, monkeypatch):
        """`_ =>` is normalized to arm 3 only when it IS the fourth arm."""
        short = self._GOOD.replace("        2 => (-local_x, -local_y),\n", "")
        self._env(tmp_path, monkeypatch, short, self._GOOD)
        report = gate.run(tmp_path, include_python=False)
        assert any(v.path == "a.rs" for v in report.violations)

    def test_missing_registered_twin_function_is_gate_error(self, tmp_path, monkeypatch):
        self._env(tmp_path, monkeypatch, "fn something_else() {}\n", self._GOOD)
        with pytest.raises(gate.GateError, match="was not found"):
            gate.run(tmp_path, include_python=False)


class TestRustRealRepo:
    def test_real_guarded_rust_files_are_clean(self):
        repo_root = Path(__file__).resolve().parents[2]
        report = gate.run(repo_root, include_python=False)
        assert report.violations == [], report.violations
        assert report.rust_files_checked == len(gate.GUARDED_RUST_FILES)
        assert report.quadrant_twins_checked == len(gate.RUST_QUADRANT_TABLE_TWINS)

    def test_every_registered_rust_exemption_names_a_real_function(self):
        """An exemption for a function that no longer exists is dead weight
        that reads as coverage. Each entry must still resolve."""
        repo_root = Path(__file__).resolve().parents[2]
        for rel, fn in sorted(gate.RUST_EXEMPT_FUNCTIONS):
            path = repo_root / rel
            assert path.is_file(), rel
            names = set(gate._rust_enclosing_functions(path.read_text().splitlines()))
            assert fn in names, f"{rel}: exemption names '{fn}', which no longer exists"

    def test_the_gate_catches_the_pre_fix_clearance_geometry_from_git(self):
        """Anti-vacuity against the REAL pre-fix source, loaded from git --
        not a retyped imitation. `clearance_geometry.rs` at origin/main
        contained the inline `math_cos_sin` rotation this change removed;
        the gate must fire on those exact bytes.
        """
        import subprocess

        repo_root = Path(__file__).resolve().parents[2]
        rel = "packages/temper-geometry/src/clearance_geometry.rs"
        r = subprocess.run(
            ["git", "show", f"origin/main:{rel}"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if r.returncode != 0:
            pytest.skip(f"origin/main not available in this checkout: {r.stderr.strip()[:200]}")
        lines = r.stdout.splitlines()
        owners = gate._rust_enclosing_functions(lines)
        hits = [
            (i + 1, owners[i])
            for i, raw in enumerate(lines)
            if any(rx.search(gate._strip_rust_comments(raw)) for rx, _ in gate._RUST_TRIG_RE)
        ]
        # The pre-fix file had raw trig in BOTH shapely_rotation_cos_sin
        # (exempt today, deliberately) and rotate_local_to_world (migrated
        # today). The second is the one the gate now forbids.
        assert any(owner == "rotate_local_to_world" for _, owner in hits), hits
