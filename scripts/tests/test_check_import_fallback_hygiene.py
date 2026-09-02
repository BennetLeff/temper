"""Tests for check_import_fallback_hygiene.py.

Four groups, matching the structure of test_check_stale_extensions.py:

1. ``TestDetection`` -- the R1/R2 classifiers fire on the exact shapes
   that motivated the gate (``except ImportError: return None`` around a
   first-party import; silent ``pass``/``return []``) and stay quiet on
   the shapes that are correct (re-raise, exception carried into an
   explicit non-passing result, degradation recorded into a diagnostics
   list).
2. ``TestAllowlist`` -- entries must carry a reason; stale entries are
   reported so an exemption cannot outlive the problem it excused.
3. ``TestRealTree`` -- the gate is clean on the tree as shipped, and the
   real motivating regressions are caught if reintroduced.
4. ``TestAntiVacuity`` -- the gate fails closed rather than passing
   silently when it cannot actually inspect anything: no first-party
   packages discovered, no source files, no handlers found. A gate that
   passes because it looked at nothing is the failure mode this repo has
   been bitten by repeatedly, so these are the load-bearing tests.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_import_fallback_hygiene import (  # noqa: E402
    EXIT_OK,
    EXIT_VIOLATIONS,
    Finding,
    GateError,
    Report,
    analyze_file,
    decide,
    first_party_prefixes,
    load_allowlist,
    main,
    run,
)

PREFIXES = frozenset({"temper_placer", "temper_geometry", "temper_drc_rs"})
REPO_ROOT = Path(__file__).resolve().parents[2]


def _analyze(tmp_path: Path, src: str) -> list[Finding]:
    p = tmp_path / "sample.py"
    p.write_text(textwrap.dedent(src), encoding="utf-8")
    _, findings = analyze_file(p, "sample.py", PREFIXES)
    return findings


def _fake_repo(tmp_path: Path, module_src: str, n_packages: int = 6) -> Path:
    """A minimal repo the gate will accept as non-vacuous."""
    for i in range(n_packages):
        pkg = tmp_path / "packages" / f"temper-pkg{i}"
        pkg.mkdir(parents=True)
        (pkg / "pyproject.toml").write_text(
            f'[project]\nname = "temper-pkg{i}"\n', encoding="utf-8"
        )
    src = tmp_path / "packages" / "temper-pkg0" / "src" / "temper_pkg0"
    src.mkdir(parents=True)
    (src / "mod.py").write_text(textwrap.dedent(module_src), encoding="utf-8")
    return tmp_path


# ---------------------------------------------------------------------------
# 1. detection
# ---------------------------------------------------------------------------


class TestDetection:
    def test_r1_fires_on_the_gate_drive_regression(self, tmp_path: Path) -> None:
        """The exact shape that kept the gate-drive safety check UNMEASURED."""
        findings = _analyze(
            tmp_path,
            """
            def _resolve(p):
                try:
                    from temper_placer.io.kicad_parser import parse_kicad_pcb
                except ImportError:
                    return None
            """,
        )
        assert [f.rule for f in findings] == ["R1"]
        assert "temper_placer.io.kicad_parser" in findings[0].first_party

    def test_r1_fires_on_false_zero_return(self, tmp_path: Path) -> None:
        """`return 0` on a loop-AREA check is the most-passing value."""
        findings = _analyze(
            tmp_path,
            """
            def area():
                try:
                    import temper_geometry
                except ImportError:
                    return 0
            """,
        )
        assert [f.rule for f in findings] == ["R1"]

    def test_r1_fires_on_silent_pass(self, tmp_path: Path) -> None:
        findings = _analyze(
            tmp_path,
            """
            def fence():
                try:
                    from temper_placer.router_v6.stage_validators import run_validators
                except ImportError:
                    pass
            """,
        )
        assert [f.rule for f in findings] == ["R1"]

    def test_r1_silent_on_reraise(self, tmp_path: Path) -> None:
        """drc_inflate.py's shape -- the model this gate points people at."""
        assert (
            _analyze(
                tmp_path,
                """
                def f():
                    try:
                        import temper_drc_rs
                    except ImportError as e:
                        raise ImportError("... build it with: make extensions") from e
                """,
            )
            == []
        )

    def test_r1_silent_when_exception_carried_into_result(self, tmp_path: Path) -> None:
        """gates.py's shape: UNMEASURED is a distinct non-passing state and
        the reason travels with it, so the evidence is not destroyed."""
        assert (
            _analyze(
                tmp_path,
                """
                def check():
                    try:
                        from temper_placer.physics.gate_drive import gate_drive_spacing
                    except ImportError as exc:
                        return GateResult(UNMEASURED, error_message=f"gate-drive: {exc}")
                """,
            )
            == []
        )

    def test_r1_fires_when_exception_is_only_logged(self, tmp_path: Path) -> None:
        findings = _analyze(
            tmp_path,
            """
            def f():
                try:
                    import temper_geometry
                except ImportError as exc:
                    logger.warning("missing: %s", exc)
                    return None
            """,
        )
        assert [f.rule for f in findings] == ["R1"]

    def test_nested_raise_does_not_exempt_handler(self, tmp_path: Path) -> None:
        findings = _analyze(
            tmp_path,
            """
            def f():
                try:
                    import temper_geometry
                except ImportError:
                    def unreachable():
                        raise RuntimeError("not executed")
                    return None
            """,
        )
        assert [f.rule for f in findings] == ["R1"]

    def test_r2_fires_on_silent_third_party_empty_return(self, tmp_path: Path) -> None:
        findings = _analyze(
            tmp_path,
            """
            def f():
                try:
                    import yaml
                except ImportError:
                    return []
            """,
        )
        assert [f.rule for f in findings] == ["R2"]

    def test_r2_silent_when_degradation_is_recorded(self, tmp_path: Path) -> None:
        """gate_input_registry.py's shape -- `continue` is fine when the
        failure is appended to an errors list first. R2 tests for silence,
        not for the control-flow keyword."""
        assert (
            _analyze(
                tmp_path,
                """
                def f(errors):
                    for spec in specs:
                        try:
                            import optional_thing
                        except (ImportError, ValueError) as exc:
                            errors.append(f"unresolvable: {exc}")
                            continue
                """,
            )
            == []
        )

    def test_r2_silent_when_logged(self, tmp_path: Path) -> None:
        assert (
            _analyze(
                tmp_path,
                """
                def f():
                    try:
                        import matplotlib.pyplot
                    except ImportError:
                        logger.warning("plotting disabled: matplotlib absent")
                        return None
                """,
            )
            == []
        )

    def test_tuple_handler_is_detected(self, tmp_path: Path) -> None:
        findings = _analyze(
            tmp_path,
            """
            def f():
                try:
                    from temper_placer.io.kicad_parser import parse_kicad_pcb
                except (ImportError, OSError):
                    return None
            """,
        )
        assert [f.rule for f in findings] == ["R1"]

    def test_bare_except_is_not_this_gates_problem(self, tmp_path: Path) -> None:
        assert (
            _analyze(
                tmp_path,
                """
                def f():
                    try:
                        from temper_placer.io.kicad_parser import parse_kicad_pcb
                    except:
                        return None
                """,
            )
            == []
        )

    def test_relative_import_is_not_treated_as_first_party_module(
        self, tmp_path: Path
    ) -> None:
        """`from . import x` carries no absolute module name; it must not be
        silently miscategorised as a third-party import."""
        findings = _analyze(
            tmp_path,
            """
            def f():
                try:
                    from . import sibling
                except ImportError:
                    return None
            """,
        )
        assert [f.rule for f in findings] == ["R2"]


# ---------------------------------------------------------------------------
# 2. allowlist
# ---------------------------------------------------------------------------


class TestAllowlist:
    def test_entry_without_reason_is_rejected(self, tmp_path: Path) -> None:
        p = tmp_path / "a.yaml"
        p.write_text("exemptions:\n  - key: 'x::y::z'\n", encoding="utf-8")
        with pytest.raises(GateError, match="no `reason`"):
            load_allowlist(p)

    def test_entry_without_key_is_rejected(self, tmp_path: Path) -> None:
        p = tmp_path / "a.yaml"
        p.write_text("exemptions:\n  - reason: 'because'\n", encoding="utf-8")
        with pytest.raises(GateError, match="missing its `key`"):
            load_allowlist(p)

    def test_missing_file_is_empty_not_an_error(self, tmp_path: Path) -> None:
        assert load_allowlist(tmp_path / "nope.yaml") == {}

    def test_allowlisted_finding_is_suppressed(self) -> None:
        f = Finding("a.py", 1, "q", ("m",), ("m",), "R1", "d")
        live, stale = decide(Report(findings=[f]), {f.key: "reason"})
        assert live == [] and stale == []

    def test_stale_entry_is_reported(self) -> None:
        live, stale = decide(Report(findings=[]), {"gone::x::y": "reason"})
        assert live == [] and stale == ["gone::x::y"]


# ---------------------------------------------------------------------------
# 3. the real tree
# ---------------------------------------------------------------------------


class TestRealTree:
    def test_gate_is_clean_on_the_shipped_tree(self) -> None:
        assert main(["--repo-root", str(REPO_ROOT)]) == EXIT_OK

    def test_real_tree_has_many_handlers(self) -> None:
        """Guards against the detector silently matching nothing."""
        report = run(REPO_ROOT)
        assert report.handlers_seen > 20
        assert report.files_scanned > 100

    def test_first_party_prefixes_include_the_repos_own_packages(self) -> None:
        prefixes = first_party_prefixes(REPO_ROOT)
        assert {"temper_placer", "temper_geometry", "temper_drc_rs"} <= prefixes


# ---------------------------------------------------------------------------
# 4. anti-vacuity -- the gate must never pass by looking at nothing
# ---------------------------------------------------------------------------


class TestAntiVacuity:
    def test_fails_closed_when_no_packages_discovered(self, tmp_path: Path) -> None:
        with pytest.raises(GateError, match="would be vacuous"):
            first_party_prefixes(tmp_path)

    def test_fails_closed_on_too_few_packages(self, tmp_path: Path) -> None:
        """A partial checkout must not silently shrink the first-party set:
        every prefix that goes missing turns an R1 into a non-finding."""
        for i in range(3):
            pkg = tmp_path / "packages" / f"p{i}"
            pkg.mkdir(parents=True)
            (pkg / "pyproject.toml").write_text(
                f'[project]\nname = "p{i}"\n', encoding="utf-8"
            )
        with pytest.raises(GateError, match="only 3 first-party"):
            first_party_prefixes(tmp_path)

    def test_fails_closed_on_zero_source_files(self, tmp_path: Path) -> None:
        for i in range(6):
            pkg = tmp_path / "packages" / f"temper-pkg{i}"
            pkg.mkdir(parents=True)
            (pkg / "pyproject.toml").write_text(
                f'[project]\nname = "temper-pkg{i}"\n', encoding="utf-8"
            )
        with pytest.raises(GateError, match="zero Python files"):
            run(tmp_path)

    def test_fails_closed_when_no_handlers_found(self, tmp_path: Path) -> None:
        """If the detector stops recognising handlers it must fail, not pass."""
        repo = _fake_repo(tmp_path, "x = 1\n")
        with pytest.raises(GateError, match="zero `except ImportError` handlers"):
            run(repo)

    def test_unparseable_source_fails_closed(self, tmp_path: Path) -> None:
        repo = _fake_repo(tmp_path, "def broken(:\n")
        with pytest.raises(GateError, match="could not parse"):
            run(repo)

    def test_main_returns_violations_exit_code_on_a_dirty_tree(
        self, tmp_path: Path
    ) -> None:
        repo = _fake_repo(
            tmp_path,
            """
            def f():
                try:
                    import temper_pkg0.thing
                except ImportError:
                    return None
            """,
        )
        assert main(["--repo-root", str(repo), "--allowlist", str(tmp_path / "n.yaml")]) == (
            EXIT_VIOLATIONS
        )

    def test_gate_error_surfaces_as_failure_not_success(self, tmp_path: Path) -> None:
        """A gate that cannot run must never report OK."""
        assert main(["--repo-root", str(tmp_path)]) == EXIT_VIOLATIONS
