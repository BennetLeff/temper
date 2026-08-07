"""Tests for check_migration_narrowing.py.

Exercises Check A (const-ification) and Check B (numeric narrowing at the
pyo3 boundary) against synthetic ``tmp_path`` fixture trees shaped like
``packages/<crate>/src/...`` + ``packages/temper-placer/src/...``, rather
than the real repo tree — this suite pins the detection *logic*
independent of whatever the real repo happens to contain on any given day.

``TestRealRepoAntiVacuity`` is the one exception: it runs the gate against
the actual repo root and asserts the two historically-confirmed instances
(``H_CONV_BACKGROUND`` in heat_removal.rs/py, and ``rotation`` in
escape_via.rs) are still detected as real findings (i.e. not silently
absorbed into the allowlist) as long as the underlying source still has the
narrowed shape. If a fix lands and narrows the source differently the test
xfails loudly rather than silently passing — see the test body.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_migration_narrowing as gate  # noqa: E402


def _write(root: Path, rel: str, content: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


# ---------------------------------------------------------------------------
# Check A: const-ification
# ---------------------------------------------------------------------------


class TestCheckA:
    def test_flags_unthreaded_constant(self, tmp_path):
        _write(
            tmp_path,
            "packages/temper-widget/src/lib.rs",
            'pub const H_CONV_BACKGROUND: f64 = 10.0;\n',
        )
        _write(
            tmp_path,
            "packages/temper-placer/src/temper_placer/physics/widget.py",
            "import temper_widget as _tw\n"
            "\n"
            "H_CONV_BACKGROUND = 10.0\n"
            "\n"
            "def build(cs, ox):\n"
            "    return _tw.build_py(cs, ox)\n",
        )
        findings = gate.check_a(tmp_path)
        names = {f.name for f in findings}
        assert "H_CONV_BACKGROUND" in names

    def test_does_not_flag_when_name_is_passed(self, tmp_path):
        _write(
            tmp_path,
            "packages/temper-widget/src/lib.rs",
            'pub const H_CONV_BACKGROUND: f64 = 10.0;\n',
        )
        _write(
            tmp_path,
            "packages/temper-placer/src/temper_placer/physics/widget.py",
            "import temper_widget as _tw\n"
            "\n"
            "H_CONV_BACKGROUND = 10.0\n"
            "\n"
            "def build(cs, ox):\n"
            "    return _tw.build_py(cs, ox, H_CONV_BACKGROUND)\n",
        )
        findings = gate.check_a(tmp_path)
        assert findings == []

    def test_does_not_flag_when_no_delegate_call_exists(self, tmp_path):
        """A same-named constant with no call into the crate at all should
        not fire — there's no call site to fail to thread it into."""
        _write(
            tmp_path,
            "packages/temper-widget/src/lib.rs",
            'pub const SOME_CONST: f64 = 10.0;\n',
        )
        _write(
            tmp_path,
            "packages/temper-placer/src/temper_placer/physics/widget.py",
            "SOME_CONST = 10.0\n"
            "\n"
            "def local_only():\n"
            "    return SOME_CONST * 2\n",
        )
        findings = gate.check_a(tmp_path)
        assert findings == []

    def test_does_not_flag_unrelated_crate_import(self, tmp_path):
        """Name collision with a constant in a python file that imports a
        DIFFERENT crate's module should not fire."""
        _write(
            tmp_path,
            "packages/temper-widget/src/lib.rs",
            'pub const SHARED_NAME: f64 = 1.0;\n',
        )
        _write(
            tmp_path,
            "packages/temper-placer/src/temper_placer/physics/other.py",
            "import temper_other as _to\n"
            "\n"
            "SHARED_NAME = 1.0\n"
            "\n"
            "def build():\n"
            "    return _to.build_py()\n",
        )
        findings = gate.check_a(tmp_path)
        assert findings == []

    def test_flags_from_import_call_form(self, tmp_path):
        """`from crate import func` + bare `func(...)` call should also be
        recognised as a delegate call, not just `alias.func(...)`."""
        _write(
            tmp_path,
            "packages/temper-widget/src/lib.rs",
            'pub const H_CONV_BACKGROUND: f64 = 10.0;\n',
        )
        _write(
            tmp_path,
            "packages/temper-placer/src/temper_placer/physics/widget.py",
            "from temper_widget import build_py\n"
            "\n"
            "H_CONV_BACKGROUND = 10.0\n"
            "\n"
            "def build(cs):\n"
            "    return build_py(cs)\n",
        )
        findings = gate.check_a(tmp_path)
        assert {f.name for f in findings} == {"H_CONV_BACKGROUND"}


# ---------------------------------------------------------------------------
# Check B: numeric narrowing at the pyo3 boundary
# ---------------------------------------------------------------------------


class TestCheckB:
    def test_flags_option_i64_matching_float_annotation(self, tmp_path):
        _write(
            tmp_path,
            "packages/temper-geo/src/lib.rs",
            "fn parse(pkg: &Bound<'_, PyAny>) -> PyResult<()> {\n"
            "    let rotation: Option<i64> = pkg.get_item(1)?.extract()?;\n"
            "    Ok(())\n"
            "}\n",
        )
        _write(
            tmp_path,
            "packages/temper-placer/src/temper_placer/core/thing.py",
            "def _normalize_rotation(rotation: int | float | None) -> float:\n"
            "    return float(rotation)\n",
        )
        findings = gate.check_b(tmp_path)
        assert any(f.name == "rotation" for f in findings)

    def test_flags_float_call_form(self, tmp_path):
        _write(
            tmp_path,
            "packages/temper-geo/src/lib.rs",
            "fn parse(pkg: &Bound<'_, PyAny>) -> PyResult<()> {\n"
            "    let side: i64 = pkg.get_item(2)?.extract()?;\n"
            "    Ok(())\n"
            "}\n",
        )
        _write(
            tmp_path,
            "packages/temper-placer/src/temper_placer/core/thing.py",
            "def use(comp):\n"
            "    angle = float(comp.side) * 2.0\n",
        )
        findings = gate.check_b(tmp_path)
        assert any(f.name == "side" for f in findings)

    def test_flags_turbofish_extract_form(self, tmp_path):
        _write(
            tmp_path,
            "packages/temper-geo/src/lib.rs",
            "fn parse(pkg: &Bound<'_, PyAny>) -> PyResult<()> {\n"
            "    let rotation = pkg.get_item(1)?.extract::<Option<i64>>()?;\n"
            "    Ok(())\n"
            "}\n",
        )
        _write(
            tmp_path,
            "packages/temper-placer/src/temper_placer/core/thing.py",
            "def use(comp):\n"
            "    angle = float(comp.rotation) * 2.0\n",
        )
        findings = gate.check_b(tmp_path)
        assert any(f.name == "rotation" for f in findings)

    def test_does_not_flag_when_python_has_no_float_admission(self, tmp_path):
        _write(
            tmp_path,
            "packages/temper-geo/src/lib.rs",
            "fn parse(pkg: &Bound<'_, PyAny>) -> PyResult<()> {\n"
            "    let count: i64 = pkg.get_item(1)?.extract()?;\n"
            "    Ok(())\n"
            "}\n",
        )
        _write(
            tmp_path,
            "packages/temper-placer/src/temper_placer/core/thing.py",
            "def use(comp):\n"
            "    return comp.count + 1\n",
        )
        findings = gate.check_b(tmp_path)
        assert findings == []

    def test_matches_initial_prefixed_variant(self, tmp_path):
        _write(
            tmp_path,
            "packages/temper-geo/src/lib.rs",
            "fn parse(pkg: &Bound<'_, PyAny>) -> PyResult<()> {\n"
            "    let rotation: Option<i64> = pkg.get_item(1)?.extract()?;\n"
            "    Ok(())\n"
            "}\n",
        )
        _write(
            tmp_path,
            "packages/temper-placer/src/temper_placer/core/thing.py",
            "def use(comp):\n"
            "    if comp.initial_rotation is not None:\n"
            "        angle = float(comp.initial_rotation) * math.pi / 2.0\n",
        )
        findings = gate.check_b(tmp_path)
        assert any(f.name == "rotation" and f.matched_variant == "initial_rotation" for f in findings)

    def test_does_not_flag_plain_i64_binding_without_extract(self, tmp_path):
        """A `let x: i64 = ...` that is NOT sourced from `.extract()` is not
        a pyo3-boundary narrowing at all — must not fire."""
        _write(
            tmp_path,
            "packages/temper-geo/src/lib.rs",
            "fn compute() -> i64 {\n"
            "    let rotation: i64 = 4;\n"
            "    rotation\n"
            "}\n",
        )
        _write(
            tmp_path,
            "packages/temper-placer/src/temper_placer/core/thing.py",
            "def use(comp):\n"
            "    return float(comp.rotation)\n",
        )
        findings = gate.check_b(tmp_path)
        assert findings == []


# ---------------------------------------------------------------------------
# Allowlist parsing
# ---------------------------------------------------------------------------


class TestAllowlist:
    def test_loads_valid_entries(self, tmp_path):
        p = tmp_path / ".migration-narrowing-allowlist"
        p.write_text(
            "# comment\n"
            "\n"
            "CHECK_A|packages/foo/src/lib.rs|NAME|packages/temper-placer/src/x.py  # reason: coincidence\n"
            "CHECK_B|packages/bar/src/lib.rs|other|packages/temper-placer/src/y.py  # reason: also coincidence\n"
        )
        entries = gate.load_allowlist(p)
        assert entries == {
            ("CHECK_A", "packages/foo/src/lib.rs", "NAME", "packages/temper-placer/src/x.py"),
            ("CHECK_B", "packages/bar/src/lib.rs", "other", "packages/temper-placer/src/y.py"),
        }

    def test_missing_file_returns_empty(self, tmp_path):
        assert gate.load_allowlist(tmp_path / "nope") == set()

    def test_unparseable_line_exits_5(self, tmp_path):
        p = tmp_path / ".migration-narrowing-allowlist"
        p.write_text("this is not a valid entry line\n")
        with pytest.raises(SystemExit) as exc_info:
            gate.load_allowlist(p)
        assert exc_info.value.code == 5


# ---------------------------------------------------------------------------
# End-to-end main() against a fixture tree with a real .git marker
# ---------------------------------------------------------------------------


class TestMainExitCodes:
    def _make_repo(self, tmp_path):
        (tmp_path / ".git").mkdir()
        return tmp_path

    def test_exits_3_on_new_finding_not_allowlisted(self, tmp_path, monkeypatch):
        root = self._make_repo(tmp_path)
        _write(root, "packages/temper-widget/src/lib.rs", 'pub const NAME: f64 = 1.0;\n')
        _write(
            root,
            "packages/temper-placer/src/temper_placer/physics/widget.py",
            "import temper_widget as _tw\nNAME = 1.0\n\ndef build(cs):\n    return _tw.build_py(cs)\n",
        )
        allowlist_path = root / ".migration-narrowing-allowlist"
        allowlist_path.write_text("")

        monkeypatch.setattr(gate, "REPO_ROOT", root)
        monkeypatch.setattr(gate, "ALLOWLIST_PATH", allowlist_path)
        monkeypatch.setattr(sys, "argv", ["check_migration_narrowing.py"])
        assert gate.main() == 3

    def test_exits_0_when_finding_is_allowlisted(self, tmp_path, monkeypatch):
        root = self._make_repo(tmp_path)
        _write(root, "packages/temper-widget/src/lib.rs", 'pub const NAME: f64 = 1.0;\n')
        py_rel = "packages/temper-placer/src/temper_placer/physics/widget.py"
        _write(
            root,
            py_rel,
            "import temper_widget as _tw\nNAME = 1.0\n\ndef build(cs):\n    return _tw.build_py(cs)\n",
        )
        allowlist_path = root / ".migration-narrowing-allowlist"
        allowlist_path.write_text(
            f"CHECK_A|packages/temper-widget/src/lib.rs|NAME|{py_rel}  # reason: test fixture\n"
        )

        monkeypatch.setattr(gate, "REPO_ROOT", root)
        monkeypatch.setattr(gate, "ALLOWLIST_PATH", allowlist_path)
        monkeypatch.setattr(sys, "argv", ["check_migration_narrowing.py"])
        assert gate.main() == 0

    def test_exits_4_on_stale_allowlist_entry(self, tmp_path, monkeypatch):
        root = self._make_repo(tmp_path)
        # No Rust/Python fixtures at all -> no findings -> the allowlist
        # entry below is stale.
        allowlist_path = root / ".migration-narrowing-allowlist"
        allowlist_path.write_text(
            "CHECK_A|packages/gone/src/lib.rs|GONE|packages/temper-placer/src/gone.py  # reason: stale\n"
        )

        monkeypatch.setattr(gate, "REPO_ROOT", root)
        monkeypatch.setattr(gate, "ALLOWLIST_PATH", allowlist_path)
        monkeypatch.setattr(sys, "argv", ["check_migration_narrowing.py"])
        assert gate.main() == 4

    def test_init_mode_writes_allowlist_and_returns_0(self, tmp_path, monkeypatch):
        root = self._make_repo(tmp_path)
        _write(root, "packages/temper-widget/src/lib.rs", 'pub const NAME: f64 = 1.0;\n')
        _write(
            root,
            "packages/temper-placer/src/temper_placer/physics/widget.py",
            "import temper_widget as _tw\nNAME = 1.0\n\ndef build(cs):\n    return _tw.build_py(cs)\n",
        )
        allowlist_path = root / ".migration-narrowing-allowlist"

        monkeypatch.setattr(gate, "REPO_ROOT", root)
        monkeypatch.setattr(sys, "argv", ["check_migration_narrowing.py", "--init", "--allowlist", str(allowlist_path)])
        assert gate.main() == 0
        assert allowlist_path.exists()
        assert "CHECK_A|packages/temper-widget/src/lib.rs|NAME|" in allowlist_path.read_text()


# ---------------------------------------------------------------------------
# Anti-vacuity: the gate must actually fire on the real, historically
# confirmed instances if their narrowed shape is still present on disk.
# ---------------------------------------------------------------------------


class TestRealRepoAntiVacuity:
    """Pins detection of the two seeded historical instances against the
    real repo tree. These tests read real source files and are expected to
    track whatever the pre-fix/post-fix state of the repo is at HEAD; they
    exist to prove the gate is not vacuous, not to enforce a particular
    fix status (that's what the gate itself -- run manually / in CI -- is
    for).
    """

    def test_h_conv_background_shape_is_detected_if_present(self):
        root = gate.REPO_ROOT
        rust_file = root / "packages/temper-thermal/src/heat_removal.rs"
        text = rust_file.read_text()
        buggy_marker = "let h_bg = H_CONV_BACKGROUND * cell_area_m2 / (cs * cs);"
        if buggy_marker not in text:
            pytest.skip(
                "heat_removal.rs no longer has the narrowed shape (fix landed); "
                "nothing to pin here."
            )
        findings = gate.check_a(root)
        assert any(
            f.name == "H_CONV_BACKGROUND"
            and f.rust_file == "packages/temper-thermal/src/heat_removal.rs"
            for f in findings
        ), "gate failed to detect the known H_CONV_BACKGROUND const-ification shape"

    def test_escape_via_rotation_shape_is_detected_if_present(self):
        root = gate.REPO_ROOT
        rust_file = root / "packages/temper-geometry/src/escape_via.rs"
        text = rust_file.read_text()
        if "let rotation: Option<i64> = pkg.get_item(1)?.extract()?;" not in text:
            pytest.skip(
                "escape_via.rs no longer has the narrowed shape (fix landed); "
                "nothing to pin here."
            )
        findings = gate.check_b(root)
        assert any(
            f.name == "rotation"
            and f.rust_file == "packages/temper-geometry/src/escape_via.rs"
            for f in findings
        ), "gate failed to detect the known escape_via.rs rotation narrowing shape"
