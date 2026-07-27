"""Tests for check_undeclared_imports.py.

See docs/evidence/2026-07-27-undeclared-import-gate.md for the full
write-up, including the mutation-verification against the real repo
(temporarily un-declaring jinja2/sympy and confirming the gate fails
naming them) -- that part is done by hand against the live tree, not as a
pytest fixture, since it requires mutating the real pyproject.toml and
re-running ``uv sync``.

Three groups here:

1. `TestHistoricalDefectReconstruction` -- rebuilds the jinja2 and sympy
   incidents as small, isolated fixture trees (a first-party module
   importing a package that ``find_spec`` cannot locate, simulating
   "declared nowhere") and asserts the gate fails, naming the exact
   module. Also proves guarded/optional imports (the ``pcbnew`` case) and
   local sibling modules are *not* false-positived.
2. `TestAntiVacuity` -- asserts the gate fails CLOSED (state ==
   "tool_error", never "clean") on every degenerate input: a scan root
   that doesn't exist, zero files found, a file that fails to parse, and
   an allowlist entry with no justification.
3. `TestClassificationUnits` -- unit tests for the AST extraction and
   classification helpers in isolation.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_undeclared_imports import (  # noqa: E402
    GateError,
    ScanTarget,
    extract_module_level_imports,
    is_local_module,
    load_allowlist,
    run,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))
    return path


# ---------------------------------------------------------------------------
# TestHistoricalDefectReconstruction
# ---------------------------------------------------------------------------


class TestHistoricalDefectReconstruction:
    """Fixture reconstructions of the two real 2026-07-26 incidents, plus
    the guarded-import / local-module controls that prove the gate does
    not fire on the shapes it is supposed to ignore.

    ``find_spec`` genuinely resolves ``jinja2``/``sympy`` in *this*
    development environment (they are real, installed dependencies here).
    To reconstruct "declared nowhere, not resolvable" faithfully without
    depending on this environment's actual package set, these tests patch
    ``importlib.util.find_spec`` to simulate the undeclared state for the
    specific fixture module names, while leaving real stdlib resolution
    (used by every other check in the same run) untouched.
    """

    def _fake_find_spec(self, unresolvable: set[str]):
        import importlib.util as real_importlib_util

        real_find_spec = real_importlib_util.find_spec

        def fake(name, *args, **kwargs):
            if name in unresolvable:
                return None
            return real_find_spec(name, *args, **kwargs)

        return fake

    def test_jinja2_incident_reconstructed(self, tmp_path):
        """scripts/gen_domain_models.py imported jinja2 top-level; it was
        declared nowhere. Reconstruction: a fixture 'scripts/' file does
        the same import; jinja2 is made unresolvable via the patched
        find_spec (simulating "never installed"); the gate must fail,
        naming jinja2 and the exact file/line.
        """
        scripts_dir = tmp_path / "scripts"
        _write(
            scripts_dir / "gen_domain_models.py",
            """\
            import yaml
            from jinja2 import Environment, FileSystemLoader

            def main():
                pass
            """,
        )
        target = ScanTarget("scripts (fixture)", scripts_dir, "*.py", (scripts_dir,))

        with patch(
            "check_undeclared_imports.importlib.util.find_spec",
            side_effect=self._fake_find_spec({"jinja2"}),
        ):
            state, report = run(tmp_path, tmp_path / "no-allowlist", [target])

        assert state == "undeclared"
        assert len(report.violations) == 1
        v = report.violations[0]
        assert v.module == "jinja2"
        assert v.file == "scripts/gen_domain_models.py"
        assert v.lineno == 2

    def test_sympy_incident_reconstructed(self, tmp_path):
        """packages/temper-placer/tests/physics/test_thermal_fdm_mms.py
        imported sympy top-level for the MMS convergence proof; it was
        declared nowhere. Reconstruction: a fixture test-tree file does the
        same import; sympy made unresolvable; gate must fail naming sympy.
        """
        placer = tmp_path / "packages" / "temper-placer"
        tests_dir = placer / "tests" / "physics"
        _write(
            tests_dir / "test_thermal_fdm_mms.py",
            """\
            from __future__ import annotations

            import numpy as np
            import pytest
            import sympy as sp

            def test_convergence():
                assert sp is not None
            """,
        )
        target = ScanTarget(
            "placer tests (fixture)", tests_dir, "*.py", (placer / "src", placer)
        )

        with patch(
            "check_undeclared_imports.importlib.util.find_spec",
            side_effect=self._fake_find_spec({"sympy"}),
        ):
            state, report = run(tmp_path, tmp_path / "no-allowlist", [target])

        assert state == "undeclared"
        assert len(report.violations) == 1
        v = report.violations[0]
        assert v.module == "sympy"
        assert v.file == "packages/temper-placer/tests/physics/test_thermal_fdm_mms.py"

    def test_control_declared_dependency_passes_clean(self, tmp_path):
        """Same shape as the two incidents above, but the module IS
        resolvable (not patched away) -- proves the gate isn't
        unconditionally pessimistic and only fires on genuinely
        unresolvable imports.
        """
        scripts_dir = tmp_path / "scripts"
        _write(
            scripts_dir / "gen_domain_models.py",
            """\
            import yaml
            from jinja2 import Environment, FileSystemLoader
            """,
        )
        target = ScanTarget("scripts (fixture)", scripts_dir, "*.py", (scripts_dir,))

        # jinja2 and yaml are both real, installed packages in this dev
        # environment -- no patching, so find_spec resolves them for real.
        state, report = run(tmp_path, tmp_path / "no-allowlist", [target])

        assert state == "clean"
        assert report.violations == []

    def test_guarded_import_inside_function_not_flagged(self, tmp_path):
        """The real pcbnew case (scripts/kicad_fill_zones.py): pcbnew is
        imported inside a function, guarded by try/except ImportError,
        specifically because it requires a different interpreter than the
        one this gate runs under. Must not be flagged even though pcbnew
        is certainly not resolvable here.
        """
        scripts_dir = tmp_path / "scripts"
        _write(
            scripts_dir / "kicad_fill_zones.py",
            """\
            import sys

            def main(argv):
                try:
                    import pcbnew
                except ImportError as e:
                    print(f"pcbnew not importable: {e}", file=sys.stderr)
                    return 2
                return 0
            """,
        )
        target = ScanTarget("scripts (fixture)", scripts_dir, "*.py", (scripts_dir,))

        state, report = run(tmp_path, tmp_path / "no-allowlist", [target])

        assert state == "clean"
        assert report.violations == []
        # The guarded import must never even reach classification -- it is
        # not in tree.body, so it is not among the imports counted at all.
        assert report.import_statements_seen == 1  # only the top-level `import sys`

    def test_guarded_import_in_try_except_at_module_level_not_flagged(self, tmp_path):
        """A module-level try/except ImportError block (the general
        pattern, distinct from the function-scoped pcbnew case) must also
        not be flagged: the import is a child of ast.Try, not of the
        module body directly.

        A sibling file with a real top-level import is included so the
        run's aggregate import count isn't zero (that is a *separate*
        anti-vacuity backstop under its own dedicated test below; this
        test isolates just the guarded-import behavior).
        """
        scripts_dir = tmp_path / "scripts"
        _write(scripts_dir / "unrelated.py", "import os\n")
        _write(
            scripts_dir / "optional_dep.py",
            """\
            try:
                import definitely_not_a_real_package_xyz
            except ImportError:
                definitely_not_a_real_package_xyz = None
            """,
        )
        target = ScanTarget("scripts (fixture)", scripts_dir, "*.py", (scripts_dir,))

        state, report = run(tmp_path, tmp_path / "no-allowlist", [target])

        assert state == "clean"
        assert report.import_statements_seen == 1  # only unrelated.py's `import os`

    def test_type_checking_guarded_import_not_flagged(self, tmp_path):
        """`if TYPE_CHECKING:` imports are also nested (child of ast.If),
        not a direct child of the module body -- excluded the same way."""
        scripts_dir = tmp_path / "scripts"
        _write(
            scripts_dir / "typed_thing.py",
            """\
            from typing import TYPE_CHECKING

            if TYPE_CHECKING:
                import some_type_only_package_not_installed
            """,
        )
        target = ScanTarget("scripts (fixture)", scripts_dir, "*.py", (scripts_dir,))

        state, report = run(tmp_path, tmp_path / "no-allowlist", [target])

        assert state == "clean"
        assert report.import_statements_seen == 1  # only `from typing import ...`

    def test_local_sibling_module_not_flagged(self, tmp_path):
        """scripts/tests/test_capacity_budget_gate.py imports
        capacity_budget_gate (a sibling module one directory up, made
        importable by that test file's own sys.path.insert). Reconstructed
        here as a fixture: a local module with no installed package
        anywhere must resolve via the local_roots mechanism, not fail.
        """
        scripts_dir = tmp_path / "scripts"
        _write(scripts_dir / "capacity_budget_gate.py", "VALUE = 1\n")
        _write(
            scripts_dir / "tests" / "test_capacity_budget_gate.py",
            """\
            from capacity_budget_gate import VALUE

            def test_value():
                assert VALUE == 1
            """,
        )
        target = ScanTarget(
            "scripts/tests (fixture)",
            scripts_dir / "tests",
            "*.py",
            (scripts_dir, scripts_dir / "tests"),
        )

        state, report = run(tmp_path, tmp_path / "no-allowlist", [target])

        assert state == "clean"
        assert report.local_count == 1
        assert report.violations == []


# ---------------------------------------------------------------------------
# TestAntiVacuity
# ---------------------------------------------------------------------------


class TestAntiVacuity:
    def test_scan_root_missing_fails_closed(self, tmp_path):
        target = ScanTarget(
            "missing root", tmp_path / "does-not-exist", "*.py", (tmp_path,)
        )
        state, report = run(tmp_path, tmp_path / "no-allowlist", [target])
        assert state == "tool_error"
        assert any("does not exist" in e.reason for e in report.tool_errors)

    def test_zero_files_found_fails_closed(self, tmp_path):
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        target = ScanTarget("empty dir", empty_dir, "*.py", (empty_dir,))
        state, report = run(tmp_path, tmp_path / "no-allowlist", [target])
        assert state == "tool_error"
        assert any("zero files found" in e.reason for e in report.tool_errors)

    def test_unparseable_file_fails_closed(self, tmp_path):
        scan_dir = tmp_path / "scripts"
        _write(scan_dir / "broken.py", "def f(:\n    this is not python\n")
        target = ScanTarget("scripts (fixture)", scan_dir, "*.py", (scan_dir,))
        state, report = run(tmp_path, tmp_path / "no-allowlist", [target])
        assert state == "tool_error"
        assert any("could not parse" in e.reason for e in report.tool_errors)
        assert any("broken.py" in e.where for e in report.tool_errors)

    def test_zero_config_scan_targets_fails_closed(self, tmp_path):
        state, report = run(tmp_path, tmp_path / "no-allowlist", [])
        assert state == "tool_error"
        assert any("zero scan targets" in e.reason for e in report.tool_errors)

    def test_zero_import_statements_across_run_fails_closed(self, tmp_path):
        """Every file parses fine but contains zero top-level imports at
        all -- the vacuous-run backstop, independent of the per-file
        checks above.
        """
        scan_dir = tmp_path / "scripts"
        _write(scan_dir / "no_imports.py", "VALUE = 1\n\ndef f():\n    return VALUE\n")
        target = ScanTarget("scripts (fixture)", scan_dir, "*.py", (scan_dir,))
        state, report = run(tmp_path, tmp_path / "no-allowlist", [target])
        assert state == "tool_error"
        assert any("vacuous run" in e.reason for e in report.tool_errors)

    def test_allowlist_entry_without_justification_fails_closed(self, tmp_path):
        allowlist_path = tmp_path / ".undeclared-imports-allowlist"
        allowlist_path.write_text("some_module::scripts/a.py\n")  # no '# justification'
        scan_dir = tmp_path / "scripts"
        _write(scan_dir / "a.py", "import os\n")
        target = ScanTarget("scripts (fixture)", scan_dir, "*.py", (scan_dir,))
        state, report = run(tmp_path, allowlist_path, [target])
        assert state == "tool_error"
        assert any("justification" in e.reason for e in report.tool_errors)

    def test_allowlist_entry_with_empty_justification_fails_closed(self, tmp_path):
        allowlist_path = tmp_path / ".undeclared-imports-allowlist"
        allowlist_path.write_text("some_module::scripts/a.py  #\n")
        with pytest.raises(GateError, match="empty justification"):
            load_allowlist(allowlist_path)

    def test_allowlist_entry_without_file_scope_fails_closed(self, tmp_path):
        """A bare module name with no '::file-glob' must be rejected --
        this gate deliberately does not support module-wide exemptions.
        """
        allowlist_path = tmp_path / ".undeclared-imports-allowlist"
        allowlist_path.write_text("some_module  # missing the :: separator\n")
        with pytest.raises(GateError, match="module::file-glob"):
            load_allowlist(allowlist_path)

    def test_allowlist_missing_file_is_not_an_error(self, tmp_path):
        # A missing allowlist is a common, valid state (no exemptions
        # needed) -- distinct from a malformed one.
        entries = load_allowlist(tmp_path / "does-not-exist")
        assert entries == []

    def test_allowlist_entry_scoped_to_one_file_does_not_exempt_another(self, tmp_path):
        """The jax precedent: an allowlist entry for module X in file A
        must not silently exempt the same module in an unrelated file B.
        """
        allowlist_path = tmp_path / ".undeclared-imports-allowlist"
        allowlist_path.write_text(
            "definitely_not_a_real_package_xyz::scripts/allowed.py  # known pre-existing gap\n"
        )
        scan_dir = tmp_path / "scripts"
        _write(scan_dir / "allowed.py", "import definitely_not_a_real_package_xyz\n")
        _write(scan_dir / "not_allowed.py", "import definitely_not_a_real_package_xyz\n")
        target = ScanTarget("scripts (fixture)", scan_dir, "*.py", (scan_dir,))

        state, report = run(tmp_path, allowlist_path, [target])

        assert state == "undeclared"
        assert report.allowlisted_count == 1
        assert len(report.violations) == 1
        assert report.violations[0].file == "scripts/not_allowed.py"


# ---------------------------------------------------------------------------
# TestClassificationUnits
# ---------------------------------------------------------------------------


class TestClassificationUnits:
    def test_extract_module_level_imports_basic(self):
        refs = extract_module_level_imports(
            "import os\nimport sys as s\nfrom pathlib import Path\n"
        )
        assert [(r.module, r.lineno) for r in refs] == [
            ("os", 1),
            ("sys", 2),
            ("pathlib", 3),
        ]

    def test_extract_module_level_imports_dotted_import_uses_top_component(self):
        refs = extract_module_level_imports("import os.path\n")
        assert refs[0].module == "os"

    def test_extract_module_level_imports_skips_relative_imports(self):
        refs = extract_module_level_imports("from . import sibling\nfrom .foo import bar\n")
        assert refs == []

    def test_extract_module_level_imports_skips_nested(self):
        src = (
            "import os\n"
            "def f():\n"
            "    import json\n"
            "try:\n"
            "    import yaml\n"
            "except ImportError:\n"
            "    yaml = None\n"
        )
        refs = extract_module_level_imports(src)
        assert [r.module for r in refs] == ["os"]

    def test_extract_module_level_imports_raises_syntax_error(self):
        with pytest.raises(SyntaxError):
            extract_module_level_imports("def f(:\n")

    def test_is_local_module_finds_sibling_file(self, tmp_path):
        (tmp_path / "helper.py").write_text("X = 1\n")
        importing_file = tmp_path / "main.py"
        importing_file.write_text("from helper import X\n")
        assert is_local_module("helper", importing_file, ()) is True

    def test_is_local_module_finds_package_dir(self, tmp_path):
        pkg = tmp_path / "_lib"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        importing_file = tmp_path / "main.py"
        assert is_local_module("_lib", importing_file, ()) is True

    def test_is_local_module_checks_extra_local_roots(self, tmp_path):
        other_root = tmp_path / "elsewhere"
        other_root.mkdir()
        (other_root / "shared.py").write_text("Y = 1\n")
        nested_file = tmp_path / "sub" / "dir" / "main.py"
        nested_file.parent.mkdir(parents=True)
        assert is_local_module("shared", nested_file, (other_root,)) is True

    def test_is_local_module_false_for_real_third_party_name(self, tmp_path):
        importing_file = tmp_path / "main.py"
        assert is_local_module("numpy", importing_file, ()) is False


# ---------------------------------------------------------------------------
# Integration: the real repo, as configured by build_scan_targets. Skipped
# if this checkout isn't a synced uv workspace (defensive; CI always is).
# ---------------------------------------------------------------------------


class TestRealRepoIntegration:
    def test_real_repo_is_clean(self):
        """Against the real, current tree (jinja2/sympy declared, jax
        precisely allowlisted for its two known files), the gate must
        report clean with zero tool errors and zero violations -- proving
        it isn't vacuous (files were actually inspected, imports actually
        checked) while also not being a false-positive machine.
        """
        from check_undeclared_imports import DEFAULT_ALLOWLIST_NAME, run

        allowlist_path = REPO_ROOT / DEFAULT_ALLOWLIST_NAME
        state, report = run(REPO_ROOT, allowlist_path)

        assert report.tool_errors == []
        assert report.violations == []
        assert state == "clean"
        assert report.files_inspected > 100
        assert report.import_statements_seen > 1000
        # The two known, precisely-scoped jax entries are expected to be
        # exercised every run -- if this drops to 0, either the files
        # were removed/fixed (update the allowlist) or the scan stopped
        # reaching them (investigate).
        assert report.allowlisted_count == 2
