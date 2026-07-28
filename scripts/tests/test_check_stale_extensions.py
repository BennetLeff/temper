"""Tests for check_stale_extensions.py.

The live, mutation-based falsifier demonstration against the real
temper-io-types crate (the exact 2026-07-27 incident: stale
temper_io_types.cpython-312-darwin.so missing ConfigBoardMismatchError) is
done by hand against the real tree, not as a pytest fixture -- it requires
a real `maturin develop` rebuild, which is slow and environment-dependent.
See docs/evidence/2026-07-27-stale-extension-gate.md for that write-up
(mirrors the convention in test_check_undeclared_imports.py's own
docstring for the same reason).

Four groups here, matching that same file's structure:

1. `TestDiscovery` -- discover_crates() correctly identifies pyo3/maturin
   extension crates and correctly rejects near-miss decoys (rlib-only,
   non-maturin backend, no pyo3 dependency), using small synthetic crate
   trees under tmp_path.
2. `TestSourceFreshness` -- newest_source_mtime()'s own-files behavior,
   transitive local path-dependency propagation, and its fail-closed
   GateError when a crate has no source files at all.
3. `TestModuleStatus` -- check_module()'s fresh/stale/missing
   classification, including the "resolve past the editable-install
   wrapper to the real .so" behavior that is this gate's core defense
   against the historical incident's exact failure shape.
4. `TestAntiVacuity` -- run() fails closed on zero discovered crates;
   decide_exit_code()'s pure exit-code matrix (tool-error > STALE always
   fatal > MISSING fatal only when required > PASSED).
"""

from __future__ import annotations

import importlib.util
import os
import sys
import textwrap
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from _lib.freshness import write_stamp  # noqa: E402
from check_stale_extensions import (  # noqa: E402
    EXIT_OK,
    EXIT_TOOL_ERROR,
    EXIT_VIOLATION,
    Crate,
    CrateResult,
    GateError,
    ModuleStatus,
    Report,
    _resolve_native_artifact,
    check_module,
    crate_source_files,
    decide_exit_code,
    digest_root,
    discover_crates,
    main,
    newest_source_mtime,
    read_artifact_stamp,
    run,
    stamp_file_for,
    stamp_key_path,
)
from write_extension_stamps import main as write_extension_stamps_main  # noqa: E402


def _write(path: Path, text: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))
    return path


def _make_pyo3_crate(
    root: Path,
    *,
    package_name: str,
    module_name: str | None = None,
    crate_type: str = '["cdylib", "rlib"]',
    with_pyo3_dep: bool = True,
    build_backend: str = "maturin",
) -> Path:
    """Write a minimal pyo3-shaped crate tree at *root* and return it."""
    deps = 'pyo3 = { version = "0.29", features = ["extension-module"] }\n' if with_pyo3_dep else ""
    _write(
        root / "Cargo.toml",
        f"""\
        [package]
        name = "{package_name}"
        version = "0.1.0"
        edition = "2021"

        [lib]
        name = "{(module_name or package_name).replace('-', '_')}"
        crate-type = {crate_type}

        [dependencies]
        {deps}
        """,
    )
    module_line = f'module-name = "{module_name}"\n' if module_name else ""
    _write(
        root / "pyproject.toml",
        f"""\
        [build-system]
        requires = ["maturin>=1.8"]
        build-backend = "{build_backend}"

        [project]
        name = "{package_name}"
        version = "0.1.0"

        [tool.maturin]
        features = ["pyo3/extension-module"]
        {module_line}
        """,
    )
    _write(root / "src" / "lib.rs", "// minimal\n")
    return root


def _crate_with_source(tmp_path: Path, source_mtime: float) -> Crate:
    """A synthetic pyo3 crate whose every source file has *source_mtime*.

    Shared by TestModuleStatus (mtime fallback) and TestContentStamp
    (content hashing) so both measure the same crate shape.
    """
    root = tmp_path / "packages" / "fake-crate"
    _make_pyo3_crate(root, package_name="fake-crate", module_name="fake_crate_ext")
    lib_rs = root / "src" / "lib.rs"
    os.utime(lib_rs, (source_mtime, source_mtime))
    os.utime(root / "Cargo.toml", (source_mtime, source_mtime))
    os.utime(root / "pyproject.toml", (source_mtime, source_mtime))
    return Crate(
        name="fake-crate",
        root=root,
        module_name="fake_crate_ext",
        pyproject=root / "pyproject.toml",
        cargo_toml=root / "Cargo.toml",
    )


def _install_wrapper_layout(
    site_packages: Path,
    module_name: str,
    native_mtime: float,
    wrapper_mtime: float | None = None,
    native_bytes: bytes = b"\x00",
) -> Path:
    """Build maturin's real on-disk layout: <module>/__init__.py (thin
    re-export) + <module>/<module>.cpython-*.so (the real artifact) --
    confirmed empirically against every pyo3 crate in this repo (see
    module docstring). Returns the __init__.py path (what find_spec
    resolves to)."""
    pkg_dir = site_packages / module_name
    pkg_dir.mkdir(parents=True)
    init_py = pkg_dir / "__init__.py"
    init_py.write_text(f"from .{module_name} import *\n")
    native = pkg_dir / f"{module_name}.cpython-312-darwin.so"
    native.write_bytes(native_bytes)
    os.utime(native, (native_mtime, native_mtime))
    os.utime(init_py, (wrapper_mtime if wrapper_mtime is not None else native_mtime,) * 2)
    return init_py


# ---------------------------------------------------------------------------
# TestDiscovery
# ---------------------------------------------------------------------------


class TestDiscovery:
    def test_discovers_valid_pyo3_crate(self, tmp_path: Path) -> None:
        repo = tmp_path
        _make_pyo3_crate(repo / "packages" / "real-crate", package_name="real-crate")
        crates = discover_crates(repo)
        assert [c.name for c in crates] == ["real-crate"]
        assert crates[0].module_name == "real_crate"

    def test_module_name_from_tool_maturin_overrides_default(self, tmp_path: Path) -> None:
        """temper-design-bundle's real shape: module-name != crate name
        with hyphens replaced. Guessing from the crate name would silently
        check the wrong (nonexistent) module."""
        repo = tmp_path
        _make_pyo3_crate(
            repo / "packages" / "design-bundle",
            package_name="design-bundle",
            module_name="design_bundle_python",
        )
        crates = discover_crates(repo)
        assert len(crates) == 1
        assert crates[0].module_name == "design_bundle_python"

    def test_module_name_falls_back_to_project_name(self, tmp_path: Path) -> None:
        repo = tmp_path
        _make_pyo3_crate(repo / "packages" / "no-module-name", package_name="no-module-name", module_name=None)
        crates = discover_crates(repo)
        assert len(crates) == 1
        assert crates[0].module_name == "no_module_name"

    def test_rejects_rlib_only_crate(self, tmp_path: Path) -> None:
        """A pyo3 dependency alone doesn't make something an extension
        module -- e.g. a shared bridge crate (temper-py-bridge) with no
        cdylib output is not independently importable and must not be
        double-counted."""
        repo = tmp_path
        _make_pyo3_crate(repo / "packages" / "bridge-only", package_name="bridge-only", crate_type='["rlib"]')
        assert discover_crates(repo) == []

    def test_rejects_non_maturin_backend(self, tmp_path: Path) -> None:
        repo = tmp_path
        _make_pyo3_crate(repo / "packages" / "setuptools-thing", package_name="setuptools-thing", build_backend="setuptools.build_meta")
        assert discover_crates(repo) == []

    def test_rejects_crate_without_pyo3_dependency(self, tmp_path: Path) -> None:
        """A cdylib built for some other reason (e.g. a C ABI library)
        must not be mistaken for a Python extension."""
        repo = tmp_path
        _make_pyo3_crate(repo / "packages" / "plain-cdylib", package_name="plain-cdylib", with_pyo3_dep=False)
        assert discover_crates(repo) == []

    def test_finds_nested_crate(self, tmp_path: Path) -> None:
        """temper-placer/temper-constraints lives one level deeper than
        the top-level packages/<name> crates."""
        repo = tmp_path
        _make_pyo3_crate(
            repo / "packages" / "temper-placer" / "temper-constraints",
            package_name="temper-constraints",
        )
        crates = discover_crates(repo)
        assert [c.name for c in crates] == ["temper-constraints"]

    def test_no_packages_dir_is_zero_crates_not_an_error(self, tmp_path: Path) -> None:
        assert discover_crates(tmp_path) == []

    def test_prunes_target_directory(self, tmp_path: Path) -> None:
        """A crate's own target/ build directory must never be walked --
        besides being wasted work, some build layouts drop intermediate
        pyproject.toml-shaped files there that must not be misdiscovered
        as a second crate."""
        repo = tmp_path
        crate_root = repo / "packages" / "real-crate"
        _make_pyo3_crate(crate_root, package_name="real-crate")
        # Plant a decoy inside target/ that would look like another crate.
        _make_pyo3_crate(crate_root / "target" / "decoy", package_name="decoy-crate")
        crates = discover_crates(repo)
        assert [c.name for c in crates] == ["real-crate"]


# ---------------------------------------------------------------------------
# TestSourceFreshness
# ---------------------------------------------------------------------------


class TestSourceFreshness:
    def _crate(self, root: Path, package_name: str = "c") -> Crate:
        _make_pyo3_crate(root, package_name=package_name)
        return Crate(
            name=package_name,
            root=root,
            module_name=package_name.replace("-", "_"),
            pyproject=root / "pyproject.toml",
            cargo_toml=root / "Cargo.toml",
        )

    def test_newest_is_own_src_file(self, tmp_path: Path) -> None:
        crate = self._crate(tmp_path / "crate")
        newer = _write(crate.root / "src" / "extra.rs", "// newer\n")
        # Make it unambiguously the newest.
        future = time.time() + 100
        os.utime(newer, (future, future))
        mtime, path = newest_source_mtime(crate)
        assert path == newer
        assert mtime == pytest.approx(future, abs=1)

    def test_local_path_dependency_propagates(self, tmp_path: Path) -> None:
        """A change to a shared core crate (path dependency) must count
        toward the DEPENDING crate's freshness -- the same way `cargo
        build` itself would trigger a rebuild."""
        dep_root = tmp_path / "core-crate"
        _write(
            dep_root / "Cargo.toml",
            """\
            [package]
            name = "core-crate"
            version = "0.1.0"
            edition = "2021"

            [lib]
            crate-type = ["rlib"]
            """,
        )
        dep_src = _write(dep_root / "src" / "lib.rs", "// core\n")

        crate_root = tmp_path / "packages" / "extension-crate"
        _make_pyo3_crate(crate_root, package_name="extension-crate")
        # Wire the path dependency in by hand (writer above didn't add one).
        (crate_root / "Cargo.toml").write_text(
            (crate_root / "Cargo.toml").read_text()
            + '\ncore-crate = { path = "../../core-crate" }\n'
        )
        crate = Crate(
            name="extension-crate",
            root=crate_root,
            module_name="extension_crate",
            pyproject=crate_root / "pyproject.toml",
            cargo_toml=crate_root / "Cargo.toml",
        )

        # Baseline: newest file is the extension crate's own lib.rs.
        mtime_before, _ = newest_source_mtime(crate)

        # Touch only the DEPENDENCY's source, strictly after everything else.
        future = time.time() + 1000
        os.utime(dep_src, (future, future))

        mtime_after, path_after = newest_source_mtime(crate)
        assert path_after == dep_src
        assert mtime_after > mtime_before

    def test_cycle_safe(self, tmp_path: Path) -> None:
        """Two crates that path-depend on each other (contrived, but the
        recursion must not infinite-loop on any cyclic graph)."""
        a_root = tmp_path / "a"
        b_root = tmp_path / "b"
        _write(a_root / "Cargo.toml", '[package]\nname = "a"\nversion = "0.1.0"\nedition = "2021"\n\n[dependencies]\nb = { path = "../b" }\n')
        _write(a_root / "src" / "lib.rs", "// a\n")
        _write(b_root / "Cargo.toml", '[package]\nname = "b"\nversion = "0.1.0"\nedition = "2021"\n\n[dependencies]\na = { path = "../a" }\n')
        _write(b_root / "src" / "lib.rs", "// b\n")

        crate = Crate(name="a", root=a_root, module_name="a", pyproject=a_root / "pyproject.toml", cargo_toml=a_root / "Cargo.toml")
        # Must terminate (not hang) and return a sane result.
        mtime, path = newest_source_mtime(crate)
        assert path.is_file()

    def test_no_source_files_raises_gate_error(self, tmp_path: Path) -> None:
        empty_root = tmp_path / "empty-crate"
        empty_root.mkdir()
        crate = Crate(
            name="empty-crate",
            root=empty_root,
            module_name="empty_crate",
            pyproject=empty_root / "pyproject.toml",
            cargo_toml=empty_root / "Cargo.toml",
        )
        with pytest.raises(GateError):
            newest_source_mtime(crate)


# ---------------------------------------------------------------------------
# TestModuleStatus -- the historical-incident reconstruction
# ---------------------------------------------------------------------------


class TestModuleStatus:
    """Reconstructs the shape of the 2026-07-27 incident (installed .so
    older than its crate's source) as a controlled fixture, plus the
    "editable-install wrapper" trap that makes resolving to the wrapper's
    own mtime insufficient.
    """

    def _crate_with_source(self, tmp_path: Path, source_mtime: float) -> Crate:
        return _crate_with_source(tmp_path, source_mtime)

    def _install_wrapper_layout(
        self, site_packages: Path, module_name: str, native_mtime: float, wrapper_mtime: float | None = None
    ) -> Path:
        return _install_wrapper_layout(site_packages, module_name, native_mtime, wrapper_mtime)

    def test_missing_when_not_importable(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        crate = self._crate_with_source(tmp_path, time.time())
        monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
        status = check_module(crate)
        assert status.state == "missing"

    def test_stale_when_artifact_predates_source(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Direct reconstruction of the 2026-07-27 incident's shape:
        installed artifact strictly older than the crate's current source."""
        source_time = time.time()
        crate = self._crate_with_source(tmp_path, source_time)

        site_packages = tmp_path / "site-packages"
        init_py = self._install_wrapper_layout(
            site_packages, "fake_crate_ext", native_mtime=source_time - 86400  # 1 day older
        )

        fake_spec = importlib.util.spec_from_file_location("fake_crate_ext", init_py)
        monkeypatch.setattr(importlib.util, "find_spec", lambda name: fake_spec if name == "fake_crate_ext" else None)

        status = check_module(crate)
        assert status.state == "stale"
        assert "predates" in status.detail

    def test_fresh_when_artifact_postdates_source(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        source_time = time.time()
        crate = self._crate_with_source(tmp_path, source_time)

        site_packages = tmp_path / "site-packages"
        init_py = self._install_wrapper_layout(
            site_packages, "fake_crate_ext", native_mtime=source_time + 86400  # 1 day newer
        )

        fake_spec = importlib.util.spec_from_file_location("fake_crate_ext", init_py)
        monkeypatch.setattr(importlib.util, "find_spec", lambda name: fake_spec if name == "fake_crate_ext" else None)

        status = check_module(crate)
        assert status.state == "fresh"

    def test_resolves_past_wrapper_to_native_artifact(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """The core defense this gate adds over "just stat find_spec's
        origin": maturin regenerates the thin __init__.py wrapper on every
        build, so its mtime alone would look fresh even when the actual
        compiled .so was NOT replaced (the exact "success message, stale
        artifact" trap from the incident -- independently reproduced live
        against the real repo while building this gate, see
        docs/evidence/2026-07-27-stale-extension-gate.md: a real `uv run`
        auto-sync silently reinstalled a stale cached wheel over a
        genuinely-just-rebuilt extension). Here: wrapper mtime is NEW
        (looks fresh) but the native .so is OLD (actually stale) --
        the gate must still report STALE.
        """
        source_time = time.time()
        crate = self._crate_with_source(tmp_path, source_time)

        site_packages = tmp_path / "site-packages"
        init_py = self._install_wrapper_layout(
            site_packages,
            "fake_crate_ext",
            native_mtime=source_time - 86400,  # native .so: stale
            wrapper_mtime=source_time + 86400,  # wrapper __init__.py: looks fresh
        )

        fake_spec = importlib.util.spec_from_file_location("fake_crate_ext", init_py)
        monkeypatch.setattr(importlib.util, "find_spec", lambda name: fake_spec if name == "fake_crate_ext" else None)

        status = check_module(crate)
        assert status.state == "stale", (
            "gate must resolve past the wrapper's own mtime to the real "
            "native artifact, or it would miss exactly the incident it "
            "exists to catch"
        )

    def test_resolve_native_artifact_passthrough_for_bare_so(self, tmp_path: Path) -> None:
        """Some layouts (a crate configured with no wrapper package)
        install a bare top-level .so directly -- must be returned as-is,
        not mistaken for a missing wrapper."""
        bare_so = tmp_path / "bare_module.cpython-312-darwin.so"
        bare_so.write_bytes(b"\x00")
        assert _resolve_native_artifact("bare_module", bare_so) == bare_so


# ---------------------------------------------------------------------------
# TestAntiVacuity
# ---------------------------------------------------------------------------


class TestAntiVacuity:
    def test_run_fails_closed_on_zero_crates(self, tmp_path: Path) -> None:
        with pytest.raises(GateError, match="zero pyo3/maturin"):
            run(tmp_path)

    def test_run_fails_closed_on_empty_packages_dir(self, tmp_path: Path) -> None:
        (tmp_path / "packages").mkdir()
        with pytest.raises(GateError, match="zero pyo3/maturin"):
            run(tmp_path)

    def _report(self, states: list[str]) -> Report:
        results = []
        for i, state in enumerate(states):
            crate = Crate(
                name=f"crate-{i}",
                root=Path(f"/fake/{i}"),
                module_name=f"crate_{i}",
                pyproject=Path(f"/fake/{i}/pyproject.toml"),
                cargo_toml=Path(f"/fake/{i}/Cargo.toml"),
            )
            results.append(CrateResult(crate=crate, status=ModuleStatus(state=state, detail="x")))
        return Report(crates_discovered=len(states), results=results)

    def test_decide_exit_code_all_fresh_is_ok(self) -> None:
        assert decide_exit_code(self._report(["fresh", "fresh"]), required=False) == EXIT_OK
        assert decide_exit_code(self._report(["fresh", "fresh"]), required=True) == EXIT_OK

    def test_decide_exit_code_stale_always_fatal(self) -> None:
        """STALE is never softened by the required flag -- see module
        docstring "The 'is staleness fatal here' signal"."""
        assert decide_exit_code(self._report(["fresh", "stale"]), required=False) == EXIT_VIOLATION
        assert decide_exit_code(self._report(["fresh", "stale"]), required=True) == EXIT_VIOLATION

    def test_decide_exit_code_missing_gated_by_required(self) -> None:
        assert decide_exit_code(self._report(["fresh", "missing"]), required=False) == EXIT_OK
        assert decide_exit_code(self._report(["fresh", "missing"]), required=True) == EXIT_VIOLATION

    def test_decide_exit_code_tool_error_always_fatal_and_takes_priority(self) -> None:
        """A tool error must never be conflated with 'clean' even when
        other crates are merely missing under a lenient flag."""
        assert decide_exit_code(self._report(["missing", "error"]), required=False) == EXIT_TOOL_ERROR
        assert decide_exit_code(self._report(["fresh", "error"]), required=True) == EXIT_TOOL_ERROR

    def test_denominator_equals_checked_count(self, tmp_path: Path) -> None:
        """Every discovered crate must be checked -- the denominator the
        task's own instructions require is never a subset."""
        repo = tmp_path
        _make_pyo3_crate(repo / "packages" / "one", package_name="one")
        _make_pyo3_crate(repo / "packages" / "two", package_name="two")
        report = run(repo)
        assert report.crates_discovered == 2
        assert len(report.results) == report.crates_discovered


# ---------------------------------------------------------------------------
# TestListCrates
# ---------------------------------------------------------------------------


class TestListCrates:
    """`--list-crates` is the machine-readable feed `make extensions`
    consumes so that target never hardcodes a crate list that can drift
    from this gate's own discover_crates() scan. It must reuse the exact
    same discovery function the gate uses for its freshness check, and it
    must never run (or be gated by) the freshness check itself."""

    def test_list_crates_prints_name_and_manifest_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _make_pyo3_crate(tmp_path / "packages" / "one", package_name="one")
        _make_pyo3_crate(
            tmp_path / "packages" / "temper-placer" / "temper-constraints",
            package_name="temper-constraints",
        )
        monkeypatch.setattr(
            sys, "argv", ["check_stale_extensions.py", "--list-crates", "--repo-root", str(tmp_path)]
        )
        exit_code = main()
        assert exit_code == EXIT_OK
        out = capsys.readouterr().out
        lines = sorted(out.strip().splitlines())
        assert lines == sorted(
            [
                f"one\t{tmp_path / 'packages' / 'one' / 'Cargo.toml'}",
                "temper-constraints\t"
                f"{tmp_path / 'packages' / 'temper-placer' / 'temper-constraints' / 'Cargo.toml'}",
            ]
        )

    def test_list_crates_does_not_run_freshness_check(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A crate with zero built artifact (MISSING in the normal gate)
        must not turn `--list-crates` into a failure -- it's a discovery
        dump, not a check."""
        _make_pyo3_crate(tmp_path / "packages" / "never-built", package_name="never-built")
        monkeypatch.setattr(
            sys, "argv", ["check_stale_extensions.py", "--list-crates", "--repo-root", str(tmp_path)]
        )
        assert main() == EXIT_OK
        assert "never-built" in capsys.readouterr().out

    def test_list_crates_on_zero_crates_is_empty_not_an_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Unlike the freshness gate, `--list-crates` must not fail closed
        on zero crates -- callers like `make extensions` treat an empty
        list as 'nothing to build', and the anti-vacuity backstop belongs
        to the gate's own run(), not this discovery dump."""
        monkeypatch.setattr(
            sys, "argv", ["check_stale_extensions.py", "--list-crates", "--repo-root", str(tmp_path)]
        )
        assert main() == EXIT_OK
        assert capsys.readouterr().out == ""


# ---------------------------------------------------------------------------
# TestContentStamp -- content hashing vs. the mtime comparison it replaces
# ---------------------------------------------------------------------------


class TestContentStamp:
    """The cases where content and mtime DISAGREE, which is the whole
    reason the stamp exists.

    A suite that only checked "fresh build passes, edited source fails"
    would pass equally well against the pure-mtime implementation this
    replaces, so every test below either pins a verdict mtime gets wrong
    or pins the fallback that must keep working when no stamp is present.
    Each disagreement case runs its own mtime control in-place: same
    filesystem state, stamp removed, opposite verdict.
    """

    def _installed(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        *,
        source_mtime: float,
        native_mtime: float,
        native_bytes: bytes = b"\x00",
    ) -> tuple[Crate, Path]:
        crate = _crate_with_source(tmp_path, source_mtime)
        init_py = _install_wrapper_layout(
            tmp_path / "site-packages",
            "fake_crate_ext",
            native_mtime=native_mtime,
            native_bytes=native_bytes,
        )
        artifact = init_py.parent / "fake_crate_ext.cpython-312-darwin.so"
        fake_spec = importlib.util.spec_from_file_location("fake_crate_ext", init_py)
        monkeypatch.setattr(
            importlib.util,
            "find_spec",
            lambda name: fake_spec if name == "fake_crate_ext" else None,
        )
        return crate, artifact

    def _stamp(self, crate: Crate, artifact: Path) -> str:
        sources = crate_source_files(crate)
        return write_stamp(stamp_key_path(artifact), sources, digest_root(sources))

    def test_cached_artifact_with_newer_sources_is_fresh(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """THE case this change exists for: a restored .venv cache or a
        prebuilt wheel baked into the CI image, after a checkout that
        stamped every .rs source with the checkout time.

        Sources are strictly newer than the .so and their content is
        unchanged. mtime says STALE -- which in this gate is
        unconditionally fatal -- and content says fresh. Content wins.
        """
        now = time.time()
        crate, artifact = self._installed(
            tmp_path, monkeypatch, source_mtime=now - 86400, native_mtime=now - 3600
        )
        self._stamp(crate, artifact)

        checkout_time = now + 10_000
        for src in crate_source_files(crate):
            os.utime(src, (checkout_time, checkout_time))
        assert all(
            s.stat().st_mtime > artifact.stat().st_mtime for s in crate_source_files(crate)
        )

        status = check_module(crate)
        assert status.state == "fresh"
        assert status.method == "content"

        # Control: identical filesystem state, stamp removed. This is the
        # verdict CI gets today, and it is why a baked wheel cannot be used.
        stamp_file_for(artifact).unlink()
        assert check_module(crate).state == "stale"
        assert check_module(crate).method == "mtime"

    def test_stamp_still_catches_a_real_edit(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Content hashing must not weaken the gate it replaces: a source
        genuinely changed after the build is still STALE, and STALE is
        still unconditionally fatal."""
        now = time.time()
        crate, artifact = self._installed(
            tmp_path, monkeypatch, source_mtime=now - 86400, native_mtime=now - 3600
        )
        self._stamp(crate, artifact)

        (crate.root / "src" / "lib.rs").write_text("// a symbol the .so does not contain\n")

        status = check_module(crate)
        assert status.state == "stale"
        assert status.method == "content"
        assert "does not match its build stamp" in status.detail
        assert decide_exit_code(
            Report(1, [CrateResult(crate=crate, status=status)]), required=False
        ) == EXIT_VIOLATION

    def test_stamp_catches_an_edit_that_mtime_misses(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Strictly stronger, not merely cache-friendlier.

        A source edited and then back-dated older than the .so -- os.utime,
        a restored backup, a tar/rsync that preserves timestamps, a
        coarse-granularity filesystem -- passes the mtime comparison. It
        must fail the content comparison. This is a case the previous
        implementation got WRONG, not merely slowly.
        """
        now = time.time()
        crate, artifact = self._installed(
            tmp_path, monkeypatch, source_mtime=now - 86400, native_mtime=now
        )
        self._stamp(crate, artifact)

        (crate.root / "src" / "lib.rs").write_text("// edited, then back-dated\n")
        past = now - 100_000
        for src in crate_source_files(crate):
            os.utime(src, (past, past))
        assert all(s.stat().st_mtime < artifact.stat().st_mtime for s in crate_source_files(crate))

        status = check_module(crate)
        assert status.state == "stale"
        assert status.method == "content"

        # Control: same edit, same timestamps, no stamp -> mtime is fooled.
        stamp_file_for(artifact).unlink()
        fooled = check_module(crate)
        assert fooled.state == "fresh"
        assert fooled.method == "mtime"

    def test_missing_stamp_falls_back_to_mtime_rather_than_failing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A missing stamp is the normal state of every developer tree and
        of every artifact built before this landed. Failing closed there
        would break everyone; the mtime answer is exactly as good as it
        was yesterday."""
        now = time.time()
        crate, artifact = self._installed(
            tmp_path, monkeypatch, source_mtime=now - 86400, native_mtime=now
        )
        assert read_artifact_stamp(artifact) is None
        status = check_module(crate)
        assert status.state == "fresh"
        assert status.method == "mtime"

    def test_corrupt_stamp_falls_back_to_mtime(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        now = time.time()
        crate, artifact = self._installed(
            tmp_path, monkeypatch, source_mtime=now - 86400, native_mtime=now
        )
        self._stamp(crate, artifact)
        stamp_file_for(artifact).write_text("garbage\n")
        status = check_module(crate)
        assert status.state == "fresh"
        assert status.method == "mtime"

    def test_stamp_sits_beside_the_installed_artifact(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """It must travel with the .so through the transports that matter
        -- an actions/cache restore of .venv, a container image layer with
        a prebuilt wheel. Anywhere in the repo tree would be erased by the
        very checkout this exists to survive."""
        now = time.time()
        crate, artifact = self._installed(
            tmp_path, monkeypatch, source_mtime=now, native_mtime=now
        )
        self._stamp(crate, artifact)
        stamp = stamp_file_for(artifact)
        assert stamp.is_file()
        assert stamp.parent == artifact.parent

    def test_stamp_is_not_inherited_by_a_replaced_artifact(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A wheel reinstall (uv sync / uv pip install) replaces the .so
        but leaves the stamp behind -- it is not in the wheel's RECORD.

        Keying the stamp filename on the .so's own bytes is what stops the
        orphan from being believed for a binary it does not describe: the
        replacement hashes differently, no stamp is found, and the gate
        falls back to mtime, which is the right answer for a file that was
        just installed.
        """
        now = time.time()
        crate, artifact = self._installed(
            tmp_path, monkeypatch, source_mtime=now - 86400, native_mtime=now - 3600
        )
        self._stamp(crate, artifact)
        orphan = stamp_file_for(artifact)
        assert read_artifact_stamp(artifact) is not None

        artifact.write_bytes(b"\x00a different build of the same crate")
        os.utime(artifact, (now, now))

        assert orphan.is_file(), "the orphan is still on disk -- that is the hazard"
        assert read_artifact_stamp(artifact) is None
        status = check_module(crate)
        assert status.method == "mtime"

    def test_digest_root_is_repo_layout_relative(self, tmp_path: Path) -> None:
        """The digest must be identical on a developer's machine and inside
        a container that checked the repo out somewhere else, or a baked
        wheel could never match. The root is derived from the source set,
        so only the repo-relative layout enters the digest."""
        crate = _crate_with_source(tmp_path, time.time())
        sources = crate_source_files(crate)
        root = digest_root(sources)
        assert all(root in s.parents for s in sources)
        assert root.is_dir()


# ---------------------------------------------------------------------------
# TestStampWriter -- the build side (scripts/write_extension_stamps.py)
# ---------------------------------------------------------------------------


class TestStampWriter:
    """A stamp is authoritative, so writing one next to an artifact that
    was not just built from those sources would permanently mask exactly
    the staleness this gate exists to catch. These tests pin that the
    writer can never do it.
    """

    def _repo_with_installed_crate(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        *,
        source_mtime: float,
        native_mtime: float,
    ) -> tuple[Path, Path]:
        _crate_with_source(tmp_path, source_mtime)
        init_py = _install_wrapper_layout(
            tmp_path / "site-packages", "fake_crate_ext", native_mtime=native_mtime
        )
        artifact = init_py.parent / "fake_crate_ext.cpython-312-darwin.so"
        fake_spec = importlib.util.spec_from_file_location("fake_crate_ext", init_py)
        monkeypatch.setattr(
            importlib.util,
            "find_spec",
            lambda name: fake_spec if name == "fake_crate_ext" else None,
        )
        return tmp_path, artifact

    def test_stamps_a_fresh_crate_and_the_gate_then_uses_it(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        now = time.time()
        repo, artifact = self._repo_with_installed_crate(
            tmp_path, monkeypatch, source_mtime=now - 86400, native_mtime=now
        )
        assert write_extension_stamps_main(["--repo-root", str(repo)]) == 0
        assert stamp_file_for(artifact).is_file()

        crate = discover_crates(repo)[0]
        status = check_module(crate)
        assert status.state == "fresh"
        assert status.method == "content"

    def test_refuses_to_stamp_a_stale_crate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The launder guard. If the writer stamped whatever happened to be
        installed, running it once on a tree with a stale .so would make
        that .so permanently 'fresh' -- a strictly worse outcome than
        having no stamp at all."""
        now = time.time()
        repo, artifact = self._repo_with_installed_crate(
            tmp_path, monkeypatch, source_mtime=now, native_mtime=now - 86400
        )
        crate = discover_crates(repo)[0]
        assert check_module(crate).state == "stale"

        # Exit 1: it stamped nothing, and "stamped 0" must never read as success.
        assert write_extension_stamps_main(["--repo-root", str(repo)]) == 1
        assert not stamp_file_for(artifact).is_file()
        assert check_module(crate).state == "stale"

    def test_not_installed_crate_is_skipped_not_stamped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _crate_with_source(tmp_path, time.time())
        monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
        assert write_extension_stamps_main(["--repo-root", str(tmp_path)]) == 1

    def test_zero_crates_discovered_is_a_failure(self, tmp_path: Path) -> None:
        """Same anti-vacuity rule as the gate: nothing to stamp is not a
        clean run."""
        assert write_extension_stamps_main(["--repo-root", str(tmp_path)]) == 1

    def test_rewriting_prunes_the_superseded_stamp(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """One crate carries one stamp; the content-keyed filename must not
        turn site-packages into a stamp midden."""
        now = time.time()
        repo, artifact = self._repo_with_installed_crate(
            tmp_path, monkeypatch, source_mtime=now - 86400, native_mtime=now
        )
        assert write_extension_stamps_main(["--repo-root", str(repo)]) == 0
        first = stamp_file_for(artifact)

        # A rebuild: new .so bytes, still newer than the sources.
        artifact.write_bytes(b"\x00rebuilt")
        os.utime(artifact, (now, now))
        assert write_extension_stamps_main(["--repo-root", str(repo)]) == 0

        stamps = sorted(artifact.parent.glob(f"{artifact.name}.*.source-digest"))
        assert stamps == [stamp_file_for(artifact)]
        assert not first.is_file()
