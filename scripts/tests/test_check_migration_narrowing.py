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


# A Check A finding requires the constant to be a LIVE configuration surface:
# some production module other than the definer must actually read it (see
# `is_live_config_surface`). Fixtures that want a Check A finding must model
# that consumer; without one `check_a` correctly reports nothing, because a
# constant nobody reads cannot be silently de-configured by const-ification.
_CONSUMER_OF_NAME_PY = (
    "from temper_placer.physics.widget import NAME\n"
    "\n"
    "def scaled():\n"
    "    return NAME / 1e6\n"
)
_CONSUMER_REL = "packages/temper-placer/src/temper_placer/physics/consumer.py"


# ---------------------------------------------------------------------------
# Check A: const-ification
# ---------------------------------------------------------------------------


class TestCheckA:
    def test_flags_unthreaded_constant(self, tmp_path):
        """The H_CONV_BACKGROUND defect shape: live surface, hardcoded in Rust.

        The consumer module is load-bearing, not scenery. Check A reports only
        constants some OTHER production module reads (`is_live_config_surface`),
        because a constant nobody reads is not configurable and const-ifying it
        breaks nothing. Drop `consumer.py` and this stops being a defect.
        """
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
        _write(
            tmp_path,
            "packages/temper-placer/src/temper_placer/physics/consumer.py",
            "from temper_placer.physics.widget import H_CONV_BACKGROUND\n"
            "\n"
            "def scaled():\n"
            "    return H_CONV_BACKGROUND / 1e6\n",
        )
        findings = gate.check_a(tmp_path)
        names = {f.name for f in findings}
        assert "H_CONV_BACKGROUND" in names

    def test_does_not_flag_retained_differential_oracle(self, tmp_path):
        """A constant kept as a pinned oracle, read by nobody, is not a defect.

        This is the shape `migration-pipeline.md` stage 3 REQUIRES every
        migration to produce, and it is structurally identical to the defect
        above except that no other module reads the constant. Without the
        liveness filter Check A fires here, and its false-positive rate then
        grows with every completed migration.

        Modelled on `router_v6/net_classification.py`, whose docstring says the
        constants are "retained, unchanged and unused in production".
        """
        _write(
            tmp_path,
            "packages/temper-widget/src/lib.rs",
            'pub const GROUND_NET_PATTERNS: [&str; 1] = ["GND"];\n',
        )
        _write(
            tmp_path,
            "packages/temper-placer/src/temper_placer/router_v6/netclass.py",
            "import temper_widget as _tw\n"
            "\n"
            "GROUND_NET_PATTERNS = frozenset({'GND'})\n"
            "\n"
            "def _matches_any(name, patterns):\n"
            "    return name in patterns\n"
            "\n"
            "def _oracle(name):\n"
            "    return _matches_any(name, GROUND_NET_PATTERNS)\n"
            "\n"
            "def is_ground_net(name):\n"
            "    return _tw.is_ground_net(name)\n",
        )
        findings = gate.check_a(tmp_path)
        assert not [f for f in findings if f.name == "GROUND_NET_PATTERNS"]

    def test_does_not_treat_a_same_named_constant_elsewhere_as_a_reference(
        self, tmp_path
    ):
        """Another module DEFINING the same name is not a reference to this one.

        `core/net_classification.py` and `router_v6/net_classification.py`
        independently define seven identically-named pattern sets. Counting
        Store-context names as references makes each one look cross-referenced
        and resurrects all seven false positives.
        """
        _write(
            tmp_path,
            "packages/temper-widget/src/lib.rs",
            'pub const HV_NET_PATTERNS: [&str; 1] = ["PE"];\n',
        )
        _write(
            tmp_path,
            "packages/temper-placer/src/temper_placer/router_v6/netclass.py",
            "import temper_widget as _tw\n"
            "\n"
            "HV_NET_PATTERNS = frozenset({'PE'})\n"
            "\n"
            "def is_hv_net(name):\n"
            "    return _tw.is_hv_net(name)\n",
        )
        # A DIFFERENT module with its own same-named constant, which it reads.
        _write(
            tmp_path,
            "packages/temper-placer/src/temper_placer/core/netclass.py",
            "HV_NET_PATTERNS = frozenset({'PE'})\n"
            "\n"
            "def check(name):\n"
            "    return name in HV_NET_PATTERNS\n",
        )
        findings = gate.check_a(tmp_path)
        assert not [f for f in findings if f.name == "HV_NET_PATTERNS"]

    def test_flags_constant_reached_by_patch_object_string(self, tmp_path):
        """`mock.patch.object(mod, "NAME", ...)` is a real configuration read.

        This is how `validation/dead_parameter_probe.py` reaches
        `heat_removal.H_CONV_BACKGROUND` -- the constant's name appears only as
        a string literal, so identifier matching alone misses it and the
        original defect goes unreported.
        """
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
        _write(
            tmp_path,
            "packages/temper-placer/src/temper_placer/validation/probe.py",
            "from unittest import mock\n"
            "\n"
            "from temper_placer.physics import widget\n"
            "\n"
            "def probe(value):\n"
            "    with mock.patch.object(widget, 'H_CONV_BACKGROUND', value):\n"
            "        return widget.build(None, None)\n",
        )
        findings = gate.check_a(tmp_path)
        assert any(f.name == "H_CONV_BACKGROUND" for f in findings)

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
        # Consumer required: Check A reports only live configuration surfaces.
        _write(
            tmp_path,
            "packages/temper-placer/src/temper_placer/physics/consumer.py",
            "from temper_placer.physics.widget import H_CONV_BACKGROUND\n"
            "\n"
            "def scaled():\n"
            "    return H_CONV_BACKGROUND / 1e6\n",
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

    def test_does_not_flag_binding_shorter_than_min_name_len(self, tmp_path):
        """A 1-character binding is a scratch variable, not a boundary field.

        Regression pin for the 2026-08-10 tuning: `let v: i64` in
        `drc_oracle_marshal.rs` (a generic `get_attr_opt_i64` helper) and in
        `pcl_contracts.rs` (an enum's `.value`) both matched the `v` of
        `[float(v) for v in board_bounds]` in an unrelated file's unrelated
        crate. Four allowlist entries existed solely to suppress this shape.
        The Rust below is deliberately the exact `float(v) for v in ...`
        collision, so this test fails if the guard is removed.
        """
        _write(
            tmp_path,
            "packages/temper-geo/src/lib.rs",
            "fn parse(obj: &Bound<'_, PyAny>) -> PyResult<()> {\n"
            "    let v: i64 = obj.getattr(\"value\")?.extract()?;\n"
            "    Ok(())\n"
            "}\n",
        )
        _write(
            tmp_path,
            "packages/temper-placer/src/temper_placer/core/thing.py",
            "def payload(board_bounds):\n"
            "    return [float(v) for v in board_bounds]\n",
        )
        assert not [f for f in gate.check_b(tmp_path) if f.name == "v"]

    def test_flags_binding_at_exactly_min_name_len(self, tmp_path):
        """The guard is a floor, not a blanket short-name ban.

        Pins the boundary: a 3-character name is still a plausible field
        (`pad`, `via`, `net`) and must survive, so the guard can't be
        loosened into discarding real boundary fields.
        """
        assert gate.MIN_CHECK_B_NAME_LEN == 3
        _write(
            tmp_path,
            "packages/temper-geo/src/lib.rs",
            "fn parse(pkg: &Bound<'_, PyAny>) -> PyResult<()> {\n"
            "    let via: Option<i64> = pkg.get_item(1)?.extract()?;\n"
            "    Ok(())\n"
            "}\n",
        )
        _write(
            tmp_path,
            "packages/temper-placer/src/temper_placer/core/thing.py",
            "def use(comp):\n"
            "    return float(comp.via) * 2.0\n",
        )
        assert any(f.name == "via" for f in gate.check_b(tmp_path))

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
        _write(root, _CONSUMER_REL, _CONSUMER_OF_NAME_PY)
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
        _write(root, _CONSUMER_REL, _CONSUMER_OF_NAME_PY)
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
        _write(root, _CONSUMER_REL, _CONSUMER_OF_NAME_PY)
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
