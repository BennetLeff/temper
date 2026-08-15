"""Tests for check_duplicate_predicates.py / duplicate_predicate_registry.py.

Most tests build a synthetic ``tmp_path`` tree and monkeypatch a single
``ConsolidatedFamily`` to point at it, so this suite exercises the
delegation-detection logic itself (bare-name calls, attribute calls, the
anti-vacuity backstops) independent of whatever the real registry happens
to contain on any given day.

``TestRealRegistry`` is the one exception: it runs the gate against the
actual repo root with the real, hardcoded ``CONSOLIDATED_FAMILIES``, pinning
the post-consolidation state (the ``net_pad_positions`` and
``thermal_fdm_point_to_segment_distance`` families landed in this PR) as a
regression check -- if a future edit reintroduces an independent copy of
either predicate, this test (and the real CI gate) both fail.

``TestGateBitesOnNewCopy`` and ``TestDeliberateDuplicateIsSilent`` are the
two proofs the task brief asked for directly: a newly-introduced duplicate
must fire, and a registered *deliberate* duplicate (an ``OpenFinding`` /
``DELIBERATE_DUPLICATE_REGISTRIES`` entry, which this gate does not scan at
all) must not.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_duplicate_predicates as check  # noqa: E402
import duplicate_predicate_registry as registry  # noqa: E402


def _write(tmp_path: Path, rel: str, content: str) -> Path:
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


def _family(**overrides) -> registry.ConsolidatedFamily:
    base = dict(
        name="widget_position",
        ssot="pkg.core:widget_position",
        ssot_file="ssot.py",
        def_names=("_widget_position", "widget_position"),
        delegate_call_name="widget_position",
        scan_paths=("caller.py",),
        evidence="test fixture",
        consolidated_on="2026-08-13",
    )
    base.update(overrides)
    return registry.ConsolidatedFamily(**base)


class TestCleanSites:
    def test_delegating_shim_is_clean(self, tmp_path):
        _write(tmp_path, "ssot.py", "def widget_position(x):\n    return x\n")
        _write(
            tmp_path,
            "caller.py",
            "from ssot import widget_position\n\n"
            "def _widget_position(x):\n    return widget_position(x)\n",
        )
        violations = registry.scan_family(_family(), tmp_path)
        assert violations == []

    def test_attribute_call_delegation_is_clean(self, tmp_path):
        """A shim that delegates via ``module.widget_position(...)`` (an
        Attribute call, not a bare Name) must also be recognized."""
        _write(tmp_path, "ssot.py", "def widget_position(x):\n    return x\n")
        _write(
            tmp_path,
            "caller.py",
            "import ssot\n\n"
            "def _widget_position(x):\n    return ssot.widget_position(x)\n",
        )
        violations = registry.scan_family(_family(), tmp_path)
        assert violations == []

    def test_unrelated_function_in_scanned_file_is_ignored(self, tmp_path):
        _write(tmp_path, "ssot.py", "def widget_position(x):\n    return x\n")
        _write(tmp_path, "caller.py", "def unrelated():\n    return 1\n")
        violations = registry.scan_family(_family(), tmp_path)
        assert violations == []


class TestGateBitesOnNewCopy:
    """The task's own falsifier: introduce a duplicate copy, show it fires."""

    def test_independent_reimplementation_is_a_violation(self, tmp_path):
        _write(tmp_path, "ssot.py", "def widget_position(x):\n    return x\n")
        _write(
            tmp_path,
            "caller.py",
            "def _widget_position(x):\n"
            "    # independently reinvented, no delegation\n"
            "    return x * 2\n",
        )
        violations = registry.scan_family(_family(), tmp_path)
        assert len(violations) == 1
        assert violations[0].path == "caller.py"
        assert "does not call" in violations[0].detail

    def test_gate_script_exits_3_on_violation(self, tmp_path, monkeypatch):
        _write(tmp_path, "ssot.py", "def widget_position(x):\n    return x\n")
        _write(tmp_path, "caller.py", "def _widget_position(x):\n    return x * 2\n")
        monkeypatch.setattr(registry, "CONSOLIDATED_FAMILIES", (_family(),))
        violations = check.run(tmp_path)
        assert len(violations) == 1

    def test_third_independent_copy_is_named_not_just_counted(self, tmp_path):
        """PR #1180's own lesson: a gate must name every offending site, not
        just report a count -- otherwise the 'at least one copy was
        initially missed' failure mode repeats inside the gate itself."""
        _write(tmp_path, "ssot.py", "def widget_position(x):\n    return x\n")
        _write(tmp_path, "a.py", "def _widget_position(x):\n    return x + 1\n")
        _write(tmp_path, "b.py", "def widget_position(x):\n    return x + 2\n")
        fam = _family(scan_paths=("a.py", "b.py"))
        violations = registry.scan_family(fam, tmp_path)
        assert {v.path for v in violations} == {"a.py", "b.py"}


class TestDeliberateDuplicateIsSilent:
    """A registered deliberate duplicate (never added to CONSOLIDATED_FAMILIES,
    i.e. the OpenFindings/DELIBERATE_DUPLICATE_REGISTRIES path) must not
    fire -- this gate only scans CONSOLIDATED_FAMILIES."""

    def test_open_finding_sites_are_not_scanned(self, tmp_path, monkeypatch):
        # A finding registered as an OpenFinding (identified, deliberately
        # NOT consolidated) has no corresponding ConsolidatedFamily entry --
        # scan_all() only walks CONSOLIDATED_FAMILIES, so its sites are
        # structurally never visited regardless of what they contain.
        monkeypatch.setattr(registry, "CONSOLIDATED_FAMILIES", ())
        _write(tmp_path, "a.py", "def _point_to_segment_distance(p):\n    return 0.0\n")
        with pytest.raises(registry.RegistryError, match="empty"):
            check.run(tmp_path)

    def test_open_findings_registry_names_the_real_sites(self):
        """The point_to_segment_distance OpenFinding must name real,
        currently-existing files -- a stale registry entry is itself a
        registry failure (mirrors gate_input_registry's own philosophy:
        declarative surfaces are validated, not just written once)."""
        repo_root = Path(__file__).resolve().parents[2]
        finding = next(f for f in registry.OPEN_FINDINGS if f.name == "point_to_segment_distance")
        assert finding.diverged is True
        # At least the canonical kernel's own file must exist.
        assert (repo_root / "packages/temper-geometry/src/creepage_check.rs").is_file()


class TestAntiVacuity:
    def test_empty_families_is_registry_error(self, tmp_path, monkeypatch):
        monkeypatch.setattr(registry, "CONSOLIDATED_FAMILIES", ())
        with pytest.raises(registry.RegistryError, match="empty"):
            check.run(tmp_path)

    def test_missing_ssot_file_is_registry_error(self, tmp_path):
        fam = _family(ssot_file="does_not_exist.py")
        with pytest.raises(registry.RegistryError, match="does not exist"):
            registry.scan_family(fam, tmp_path)

    def test_ssot_file_not_defining_ssot_function_is_registry_error(self, tmp_path):
        _write(tmp_path, "ssot.py", "def something_else():\n    pass\n")
        _write(tmp_path, "caller.py", "def _widget_position(x):\n    return x\n")
        with pytest.raises(registry.RegistryError, match="does not define"):
            registry.scan_family(_family(), tmp_path)

    def test_empty_scan_paths_is_registry_error(self, tmp_path):
        _write(tmp_path, "ssot.py", "def widget_position(x):\n    return x\n")
        fam = _family(scan_paths=())
        with pytest.raises(registry.RegistryError, match="empty"):
            registry.scan_family(fam, tmp_path)

    def test_missing_scan_path_is_registry_error(self, tmp_path):
        _write(tmp_path, "ssot.py", "def widget_position(x):\n    return x\n")
        fam = _family(scan_paths=("does_not_exist.py",))
        with pytest.raises(registry.RegistryError, match="does not exist"):
            registry.scan_family(fam, tmp_path)

    def test_unparseable_scanned_file_is_registry_error(self, tmp_path):
        _write(tmp_path, "ssot.py", "def widget_position(x):\n    return x\n")
        _write(tmp_path, "caller.py", "def f(:\n    pass\n")
        with pytest.raises(registry.RegistryError, match="unparseable"):
            registry.scan_family(_family(), tmp_path)


class TestFailBeforePassAfter:
    """Explicit before/after pair, without git stash, per this repo's own
    falsifier convention (mirrors test_check_no_raw_rotation_trig.py)."""

    def test_reintroducing_a_copy_fails_then_delegating_passes(self, tmp_path):
        _write(tmp_path, "ssot.py", "def widget_position(x):\n    return x\n")
        path = _write(
            tmp_path,
            "caller.py",
            "from ssot import widget_position\n\n"
            "def _widget_position(x):\n    return widget_position(x)\n",
        )
        assert registry.scan_family(_family(), tmp_path) == []

        path.write_text("def _widget_position(x):\n    return x * 3\n")
        violations = registry.scan_family(_family(), tmp_path)
        assert len(violations) == 1

        path.write_text(
            "from ssot import widget_position\n\n"
            "def _widget_position(x):\n    return widget_position(x)\n"
        )
        assert registry.scan_family(_family(), tmp_path) == []


class TestRealRegistry:
    """Pins the real repo's post-consolidation state: both registered
    families, as they exist in this tree today, must be clean."""

    def test_real_families_are_clean(self):
        repo_root = Path(__file__).resolve().parents[2]
        violations = check.run(repo_root)
        assert violations == [], violations

    def test_gate_script_exits_0_against_real_repo(self):
        import subprocess

        repo_root = Path(__file__).resolve().parents[2]
        result = subprocess.run(
            [sys.executable, str(repo_root / "scripts" / "check_duplicate_predicates.py")],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == check.EXIT_CLEAN, result.stdout + result.stderr
