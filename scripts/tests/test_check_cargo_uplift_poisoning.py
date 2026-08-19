"""Tests for check_cargo_uplift_poisoning.py.

The gate exists because of a measured mechanism, reproduced 2026-08-18 on this
repo's own temper-geometry with real cargo and real maturin in an isolated
target dir:

    after `maturin build` (--features python,pyo3/extension-module)
        release/libtemper_geometry.so   5,966,640 bytes   PyInit_... x2
    after `cargo build` (no features), SAME directory
        release/libtemper_geometry.so     527,152 bytes   PyInit_... x0

In the steady state each flip took ~95 ms and printed no `Compiling` line --
cargo re-hardlinks a cached artifact of the other feature set over the single
uplift path, which is not keyed on features.

These tests use synthetic crate trees and byte payloads rather than real
compilation, for the same reason test_check_stale_extensions.py does: a real
`maturin develop` is slow and environment-dependent. The live reproduction
against the real crate is recorded in AGENTS.md instead. What is pinned here is
the gate's logic, including the two ways it could be quietly worthless -- a
vacuous pass, and checking the wrong symbol name.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_cargo_uplift_poisoning import (  # noqa: E402
    EXIT_OK,
    EXIT_TOOL_ERROR,
    EXIT_VIOLATION,
    cdylib_stem,
    clean_command,
    main,
    poisoned,
    scan,
)
from check_stale_extensions import discover_crates  # noqa: E402

GOOD = b"\x00\x00ELF-ish\x00" + b"PyInit_{}" + b"\x00"


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))
    return path


def _crate(
    repo: Path,
    *,
    package: str,
    module: str | None = None,
    lib_name: str | None = None,
) -> Path:
    root = repo / "packages" / package
    _write(
        root / "Cargo.toml",
        f"""\
        [package]
        name = "{package}"
        version = "0.1.0"
        edition = "2021"

        [lib]
        name = "{lib_name or (module or package).replace('-', '_')}"
        crate-type = ["cdylib", "rlib"]

        [dependencies]
        pyo3 = {{ version = "0.29", optional = true }}
        """,
    )
    module_line = f'module-name = "{module}"\n' if module else ""
    _write(
        root / "pyproject.toml",
        f"""\
        [build-system]
        requires = ["maturin>=1.8"]
        build-backend = "maturin"

        [project]
        name = "{package}"
        version = "0.1.0"

        [tool.maturin]
        features = ["pyo3/extension-module"]
        {module_line}
        """,
    )
    _write(root / "src" / "lib.rs", "// minimal\n")
    return root


def _uplift(target_dir: Path, stem: str, *, symbol: str | None, profile: str = "release") -> Path:
    """Write a fake uplifted cdylib. *symbol* None = the poisoned variant."""
    art = target_dir / profile / f"lib{stem}.so"
    art.parent.mkdir(parents=True, exist_ok=True)
    payload = b"\x00fake-cdylib\x00"
    if symbol:
        payload += symbol.encode() + b"\x00"
    art.write_bytes(payload)
    return art


class TestScan:
    def test_healthy_artifact_passes(self, tmp_path: Path) -> None:
        _crate(tmp_path, package="temper-geometry", module="temper_geometry")
        crates = discover_crates(tmp_path)
        td = tmp_path / "target-shared-pyext"
        _uplift(td, "temper_geometry", symbol="PyInit_temper_geometry")
        assert poisoned(scan(crates, td)) == []

    def test_poisoned_artifact_is_found(self, tmp_path: Path) -> None:
        """The regression itself: a cdylib with no init symbol."""
        _crate(tmp_path, package="temper-geometry", module="temper_geometry")
        crates = discover_crates(tmp_path)
        td = tmp_path / "target-shared-pyext"
        _uplift(td, "temper_geometry", symbol=None)
        bad = poisoned(scan(crates, td))
        assert len(bad) == 1
        assert bad[0].crate.name == "temper-geometry"

    def test_debug_profile_is_checked_too(self, tmp_path: Path) -> None:
        """A poisoned debug artifact misleads exactly as much as a release one."""
        _crate(tmp_path, package="temper-geometry", module="temper_geometry")
        crates = discover_crates(tmp_path)
        td = tmp_path / "target-shared-pyext"
        _uplift(td, "temper_geometry", symbol=None, profile="debug")
        assert len(poisoned(scan(crates, td))) == 1

    def test_pymodexport_counts_as_loadable(self, tmp_path: Path) -> None:
        """pyo3's multi-phase export must not be flagged.

        A gate that fires on every crate the day pyo3 changes export style
        gets switched off rather than fixed.
        """
        _crate(tmp_path, package="temper-geometry", module="temper_geometry")
        crates = discover_crates(tmp_path)
        td = tmp_path / "target-shared-pyext"
        _uplift(td, "temper_geometry", symbol="PyModExport_temper_geometry")
        assert poisoned(scan(crates, td)) == []


class TestSymbolIsDerivedFromModuleNotFilename:
    """temper-design-bundle is why this is a test and not an implementation detail.

    Its cdylib is `libtemper_design_bundle.so` but its init symbol is
    `PyInit_temper_design_bundle_python`. A gate that derived the symbol from
    the FILENAME would look correct, run clean, and check a symbol that never
    exists -- reporting every healthy build as poisoned, or (if inverted) every
    poisoned build as healthy.
    """

    def test_module_name_differing_from_lib_name_is_handled(self, tmp_path: Path) -> None:
        _crate(
            tmp_path,
            package="temper-design-bundle",
            module="temper_design_bundle_python",
            lib_name="temper_design_bundle",
        )
        crates = discover_crates(tmp_path)
        assert cdylib_stem(crates[0]) == "temper_design_bundle"
        assert crates[0].module_name == "temper_design_bundle_python"

        td = tmp_path / "target-shared-pyext"
        # The artifact carries the CORRECT symbol for its module name.
        _uplift(td, "temper_design_bundle", symbol="PyInit_temper_design_bundle_python")
        assert poisoned(scan(crates, td)) == [], (
            "a healthy temper-design-bundle build was flagged -- the gate is "
            "checking PyInit_<filename> instead of PyInit_<module-name>"
        )

    def test_filename_derived_symbol_would_be_wrong(self, tmp_path: Path) -> None:
        """Falsifier for the above: the filename-derived symbol IS absent."""
        _crate(
            tmp_path,
            package="temper-design-bundle",
            module="temper_design_bundle_python",
            lib_name="temper_design_bundle",
        )
        td = tmp_path / "target-shared-pyext"
        art = _uplift(
            td, "temper_design_bundle", symbol="PyInit_temper_design_bundle_python"
        )
        assert b"PyInit_temper_design_bundle\x00" not in art.read_bytes()


class TestAntiVacuity:
    def test_zero_crates_is_a_tool_error_not_a_pass(self, tmp_path: Path) -> None:
        """"0 checked, PASSED" is the shape docs/METHODOLOGY.md Sec 4/5 warns about."""
        (tmp_path / "packages").mkdir()
        assert (
            main(["--repo-root", str(tmp_path), "--target-dir", str(tmp_path / "td")])
            == EXIT_TOOL_ERROR
        )

    def test_missing_target_dir_is_not_reported_as_verified(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Nothing built is not a violation -- but it must not read as a check.

        Exit 0 here is correct (a fresh host has no cache yet), so the honesty
        has to live in the output, or a green run gets cited as evidence the
        cache was inspected and found clean.
        """
        _crate(tmp_path, package="temper-geometry", module="temper_geometry")
        code = main(
            ["--repo-root", str(tmp_path), "--target-dir", str(tmp_path / "absent")]
        )
        assert code == EXIT_OK
        out = capsys.readouterr().out
        assert "not evidence" in out

    def test_empty_target_dir_says_zero_checked(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _crate(tmp_path, package="temper-geometry", module="temper_geometry")
        td = tmp_path / "td"
        (td / "release").mkdir(parents=True)
        assert main(["--repo-root", str(tmp_path), "--target-dir", str(td)]) == EXIT_OK
        assert "0 checked" in capsys.readouterr().out


class TestCli:
    def test_poisoned_cache_exits_violation(self, tmp_path: Path) -> None:
        _crate(tmp_path, package="temper-geometry", module="temper_geometry")
        td = tmp_path / "target-shared-pyext"
        _uplift(td, "temper_geometry", symbol=None)
        assert (
            main(["--repo-root", str(tmp_path), "--target-dir", str(td)]) == EXIT_VIOLATION
        )

    def test_finding_names_the_fix(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A bare "poisoned" verdict sends the reader back to the dead end."""
        _crate(tmp_path, package="temper-geometry", module="temper_geometry")
        td = tmp_path / "target-shared-pyext"
        _uplift(td, "temper_geometry", symbol=None)
        main(["--repo-root", str(tmp_path), "--target-dir", str(td)])
        err = capsys.readouterr().err
        assert "cargo clean -p temper-geometry" in err
        assert "PyInit_temper_geometry" in err

    def test_clean_command_is_scoped_to_one_crate(self, tmp_path: Path) -> None:
        """Never a blanket `cargo clean` -- the fleet shares this directory.

        A whole-directory clean here would cold-rebuild every worktree on the
        host, which is how a fix for a silent problem becomes a louder one.
        """
        _crate(tmp_path, package="temper-geometry", module="temper_geometry")
        crates = discover_crates(tmp_path)
        td = tmp_path / "target-shared-pyext"
        _uplift(td, "temper_geometry", symbol=None)
        cmd = clean_command(scan(crates, td)[0], td)
        assert cmd[:4] == ["cargo", "clean", "-p", "temper-geometry"]
        assert "--target-dir" in cmd


class TestRepairMode:
    """`--clean` is a repair step, so a successful repair is exit 0.

    This is what lets `make extensions` call the pre-flight WITHOUT `|| true`.
    Masking the exit code there would also mask the eviction failing, which is
    the single outcome the build must not proceed past -- and this repo's rules
    forbid `|| true` precisely because it erases that distinction.
    """

    def _poisoned_repo(self, tmp_path: Path) -> tuple[Path, Path]:
        _crate(tmp_path, package="temper-geometry", module="temper_geometry")
        td = tmp_path / "target-shared-pyext"
        _uplift(td, "temper_geometry", symbol=None)
        return tmp_path, td

    def test_successful_eviction_exits_ok(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo, td = self._poisoned_repo(tmp_path)
        calls: list[list[str]] = []

        def fake_run(cmd, **kwargs):  # noqa: ANN001, ANN202
            calls.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(subprocess, "run", fake_run)
        code = main(["--repo-root", str(repo), "--target-dir", str(td), "--clean"])
        assert code == EXIT_OK
        assert calls and calls[0][:3] == ["cargo", "clean", "-p"]

    def test_failed_eviction_still_exits_violation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The cache is still poisoned -- the build must not continue."""
        repo, td = self._poisoned_repo(tmp_path)

        def fake_run(cmd, **kwargs):  # noqa: ANN001, ANN202
            return subprocess.CompletedProcess(cmd, 1, "", "no such package")

        monkeypatch.setattr(subprocess, "run", fake_run)
        assert (
            main(["--repo-root", str(repo), "--target-dir", str(td), "--clean"])
            == EXIT_VIOLATION
        )

    def test_report_mode_never_repairs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without --clean nothing is evicted, and the verdict stays a violation.

        A gate that silently mutated the fleet's shared cache as a side effect
        of being *asked a question* would be a worse instrument than the one it
        replaced.
        """
        repo, td = self._poisoned_repo(tmp_path)
        calls: list[list[str]] = []
        monkeypatch.setattr(
            subprocess,
            "run",
            lambda cmd, **kw: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0, "", ""),
        )
        assert main(["--repo-root", str(repo), "--target-dir", str(td)]) == EXIT_VIOLATION
        assert calls == []
