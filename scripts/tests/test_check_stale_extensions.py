"""Tests for check_stale_extensions.py.

The live, mutation-based falsifier demonstration against the real
temper-io-types crate (the exact 2026-07-27 incident: stale
temper_io_types.cpython-312-darwin.so missing ConfigBoardMismatchError) is
done by hand against the real tree, not as a pytest fixture -- it requires
a real `maturin develop` rebuild, which is slow and environment-dependent.
See docs/evidence/2026-07-27-stale-extension-gate.md for that write-up
(mirrors the convention in test_check_undeclared_imports.py's own
docstring for the same reason).

Groups here, matching that same file's structure:

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
   decide_exit_code()'s pure exit-code matrix (tool-error > "built, but
   wrong" always fatal > MISSING fatal only when required > PASSED).
5. `TestContentStamp` / `TestStampWriter` -- the cases where content
   hashing and mtime disagree.
6. `TestUnloadableArtifact` -- a brand-new `.so` with no init symbol,
   including the FEATURE-GATE diagnosis and its negative control.
7. `TestSymbolExtraction` -- the DERIVATION of the expected symbol set
   from Rust source: renames, feature gates (both directions),
   `cfg_attr`, submodules, `macro_rules!`-generated items, masking of
   comments and string literals, and never starting the walk from a path
   dependency's own `#[pymodule]`. Each shape here was found by running
   the derivation against all ten real crates and reconciling it symbol
   by symbol with what the built artifacts actually export.
8. `TestSymbolFalsifiability` -- proof the symbol check can go red:
   same crate, same timestamps, one symbol removed from the installed
   artifact, verdict flips. Every red comes with the green control that
   shows the fixture was not simply broken. These load a REAL module in
   the gate's real subprocess loader; nothing is stubbed.
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

import check_stale_extensions as gate_module  # noqa: E402
from _lib.freshness import write_stamp  # noqa: E402
from _lib.pyo3_symbols import extract_expected_symbols, load_crate_toml  # noqa: E402
from check_stale_extensions import (  # noqa: E402
    EXIT_OK,
    EXIT_TOOL_ERROR,
    EXIT_VIOLATION,
    Crate,
    CrateResult,
    GateError,
    LoadResult,
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


@pytest.fixture
def loadable_artifact(monkeypatch: pytest.MonkeyPatch):
    """Stand in for loading a real compiled artifact.

    The synthetic ``.so`` files below are a handful of bytes, so nothing can
    dlopen them. Tests about FRESHNESS should not be blocked on that, and
    they were never loading anything before this change either -- they
    monkeypatch ``find_spec`` for the same reason. The symbol check's own
    end-to-end behaviour is proved separately, against artifacts that really
    are loaded, in ``TestSymbolFalsifiability``.
    """

    def _fake(module_name: str, artifact: Path, cwd: Path) -> LoadResult:
        return LoadResult(True, symbols=frozenset(_REGISTERED_SYMBOLS))

    monkeypatch.setattr(gate_module, "load_artifact_symbols", _fake)
    return _fake


def _write(path: Path, text: str = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))
    return path


#: What every synthetic crate's `#[pymodule]` registers, and therefore what
#: its installed artifact is required to expose. Two functions and a class,
#: because those are three different registration forms
#: (`wrap_pyfunction!`, `wrap_pyfunction!` with a rename, `add_class::<>`)
#: and the gate resolves each one differently.
_REGISTERED_SYMBOLS = ("alpha", "renamed_beta", "Gamma")


def _lib_rs(module_name: str) -> str:
    """A realistic pyo3 `lib.rs` registering :data:`_REGISTERED_SYMBOLS`.

    The synthetic crates used to carry ``// minimal``. That was fine while
    the gate only stat()ed files, but a gate that derives expected symbols
    from source needs source that actually registers some -- and a fixture
    with nothing to register would make every symbol assertion below
    vacuously true, which is the failure this whole change exists to stop.
    """
    return f"""\
use pyo3::prelude::*;

#[pyfunction]
fn alpha(x: f64) -> f64 {{
    x
}}

/// Renamed on the way out, so the gate must read the attribute rather than
/// assume the Rust identifier is the Python name.
#[pyfunction]
#[pyo3(name = "renamed_beta")]
fn beta_rs(x: f64) -> f64 {{
    x
}}

/// Declared but never registered: NOT a module attribute, and demanding it
/// would be a false positive.
#[pyfunction]
fn never_registered(x: f64) -> f64 {{
    x
}}

#[pyclass]
struct Gamma {{}}

#[pymodule]
fn {module_name}(m: &Bound<'_, PyModule>) -> PyResult<()> {{
    m.add_function(wrap_pyfunction!(alpha, m)?)?;
    m.add_function(wrap_pyfunction!(beta_rs, m)?)?;
    m.add_class::<Gamma>()?;
    Ok(())
}}
"""


def _make_pyo3_crate(
    root: Path,
    *,
    package_name: str,
    module_name: str | None = None,
    crate_type: str = '["cdylib", "rlib"]',
    with_pyo3_dep: bool = True,
    build_backend: str = "maturin",
    maturin_features: str = '["python", "pyo3/extension-module"]',
    lib_rs: str | None = None,
) -> Path:
    """Write a minimal pyo3-shaped crate tree at *root* and return it.

    *maturin_features* defaults to the shape every real crate in this repo
    uses -- an own-crate ``python`` feature plus the pyo3 passthrough --
    because that own-crate feature is the precondition for the FEATURE-GATE
    diagnosis, and a fixture that omitted it would never exercise it.
    """
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
        features = {maturin_features}
        {module_line}
        """,
    )
    _write(root / "src" / "lib.rs", lib_rs or _lib_rs((module_name or package_name).replace("-", "_")))
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
    native_bytes: bytes | None = None,
) -> Path:
    """Build maturin's real on-disk layout: <module>/__init__.py (thin
    re-export) + <module>/<module>.cpython-*.so (the real artifact) --
    confirmed empirically against every pyo3 crate in this repo (see
    module docstring). Returns the __init__.py path (what find_spec
    resolves to).

    *native_bytes* defaults to a payload carrying ``PyInit_<module_name>``,
    i.e. a LOADABLE artifact, because that is what a real successful build
    produces and it is the precondition every other test here means to
    assume. Pass explicit bytes without that symbol to exercise the
    UNLOADABLE state (see ``TestUnloadableArtifact``)."""
    if native_bytes is None:
        native_bytes = b"\x00" + f"PyInit_{module_name}".encode() + b"\x00"
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


@pytest.mark.usefixtures("loadable_artifact")
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


@pytest.mark.usefixtures("loadable_artifact")
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
        native_bytes: bytes | None = None,
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

        # A real source change that leaves the registered symbol set alone,
        # so this test measures the freshness verdict and nothing else.
        lib_rs = crate.root / "src" / "lib.rs"
        lib_rs.write_text(lib_rs.read_text() + "\n// an edit made after the build\n")

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

        lib_rs = crate.root / "src" / "lib.rs"
        lib_rs.write_text(lib_rs.read_text() + "\n// edited, then back-dated\n")
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


@pytest.mark.usefixtures("loadable_artifact")
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

        # A rebuild: new .so bytes, still newer than the sources. The payload
        # must still carry the init symbol -- this test models a SUCCESSFUL
        # rebuild, and the stamp writer now (correctly) refuses to stamp an
        # artifact that exports none. See TestUnloadableArtifact.
        artifact.write_bytes(b"\x00rebuilt\x00PyInit_fake_crate_ext\x00")
        os.utime(artifact, (now, now))
        assert write_extension_stamps_main(["--repo-root", str(repo)]) == 0

        stamps = sorted(artifact.parent.glob(f"{artifact.name}.*.source-digest"))
        assert stamps == [stamp_file_for(artifact)]
        assert not first.is_file()


# ---------------------------------------------------------------------------
# TestUnloadableArtifact
# ---------------------------------------------------------------------------


@pytest.mark.usefixtures("loadable_artifact")
class TestUnloadableArtifact:
    """A `.so` can be brand-new AND unimportable at the same time.

    `cargo check`/clippy compile these crates without their `python`
    feature. maturin will reuse such an artifact, report a successful build
    in ~0.03s with no `Compiling` line, and install a `.so` exporting no
    `PyInit_<module>`. Its mtime is new and its content hash matches, so
    every freshness path reports OK -- while `import <module>` raises
    "dynamic module does not define module export function".

    Measured 2026-08-13: this gate printed "PASSED -- 10/10 extension
    module(s) fresh" against exactly such a temper_geometry artifact, and 21
    of 32 apparent test failures in an unrelated suite were that one broken
    module. Freshness answers "was it rebuilt?"; these tests pin the
    separate question "is what got installed loadable?".
    """

    def _installed(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        *,
        native_bytes: bytes | None,
    ) -> Crate:
        now = time.time()
        crate = _crate_with_source(tmp_path, source_mtime=now - 100)
        init_py = _install_wrapper_layout(
            tmp_path / "site-packages",
            "fake_crate_ext",
            native_mtime=now,
            native_bytes=native_bytes,
        )
        fake_spec = importlib.util.spec_from_file_location("fake_crate_ext", init_py)
        monkeypatch.setattr(
            importlib.util,
            "find_spec",
            lambda name: fake_spec if name == "fake_crate_ext" else None,
        )
        return crate

    def test_artifact_without_init_symbol_is_named_as_the_feature_gate_case(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The regression itself: newer-than-sources, but no init symbol.

        The crate declares its pyo3 surface behind an own-crate Cargo
        feature (as all ten real ones do), which makes this the FEATURE-GATE
        case specifically -- the one that poisons every worktree on the host
        at once -- and not a generic "unloadable".
        """
        crate = self._installed(tmp_path, monkeypatch, native_bytes=b"\x00" * 4096)
        status = check_module(crate)
        assert status.state == "feature-gate", (
            f"an artifact exporting no PyInit_ from a feature-gated crate must "
            f"be named as the feature-gate case, not reported {status.state!r}: "
            f"{status.detail}"
        )
        assert "FEATURE-GATE POISONED TARGET DIR" in status.detail
        assert "cargo clean -p" in status.detail, (
            "the finding must name the fix; a bare 'unloadable' sends the "
            "reader back to the same dead end this gate exists to short-circuit"
        )
        assert "CARGO_TARGET_DIR=\"$(mktemp -d)\"" in status.detail, (
            "`cargo clean -p` ALONE is not the recovery -- rebuilding in the "
            "shared target dir races every other worktree and re-poisons it. "
            "The output must say to rebuild under a private target dir, "
            "because an agent already lost hours finding that out by hand."
        )
        assert "--features python" in status.detail, (
            "the output must also say how to stop re-creating the state, or "
            "the same worktree will re-poison the shared dir tomorrow"
        )

    def test_no_own_feature_means_it_is_not_diagnosed_as_the_feature_gate_case(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The named diagnosis must be earned, not printed on everything.

        A crate whose ``[tool.maturin] features`` names only a dependency's
        feature has no own-crate gate to have been dropped, so the same
        symptom gets the generic (and honestly weaker) verdict instead.
        """
        now = time.time()
        root = tmp_path / "packages" / "no-feature-crate"
        _make_pyo3_crate(
            root,
            package_name="no-feature-crate",
            module_name="no_feature_ext",
            maturin_features='["pyo3/extension-module"]',
        )
        crate = Crate(
            name="no-feature-crate",
            root=root,
            module_name="no_feature_ext",
            pyproject=root / "pyproject.toml",
            cargo_toml=root / "Cargo.toml",
        )
        init_py = _install_wrapper_layout(
            tmp_path / "site-packages",
            "no_feature_ext",
            native_mtime=now,
            native_bytes=b"\x00" * 4096,
        )
        fake_spec = importlib.util.spec_from_file_location("no_feature_ext", init_py)
        monkeypatch.setattr(
            importlib.util,
            "find_spec",
            lambda name: fake_spec if name == "no_feature_ext" else None,
        )
        status = check_module(crate)
        assert status.state == "unloadable"
        assert "FEATURE-GATE POISONED TARGET DIR" not in status.detail

    def test_unloadable_is_fatal_even_when_not_required(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Never gated by TEMPER_REQUIRE_FRESH_EXTENSIONS, unlike MISSING.

        "Not built here" is a legitimate local state. "Built, but cannot be
        imported" never is -- it yields phantom test failures in every
        environment, so tolerating it leniently would be tolerating noise.
        """
        crate = self._installed(tmp_path, monkeypatch, native_bytes=b"\x00" * 4096)
        report = Report(crates_discovered=1, results=[CrateResult(crate, check_module(crate))])
        assert decide_exit_code(report, required=False) == EXIT_VIOLATION
        assert decide_exit_code(report, required=True) == EXIT_VIOLATION

    def test_pymodexport_symbol_also_counts_as_loadable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """pyo3's newer multi-phase export must not be flagged unloadable.

        Anchors the gate against a false positive that would fire on every
        crate the moment pyo3 switches export style -- the failure mode that
        makes a gate get disabled rather than fixed.
        """
        crate = self._installed(
            tmp_path,
            monkeypatch,
            native_bytes=b"\x00" + b"PyModExport_fake_crate_ext" + b"\x00",
        )
        assert check_module(crate).state != "unloadable"

    def test_loadable_artifact_is_still_judged_on_freshness(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The symbol check must not short-circuit the freshness verdict."""
        crate = self._installed(tmp_path, monkeypatch, native_bytes=None)
        assert check_module(crate).state == "fresh"


# ---------------------------------------------------------------------------
# TestSymbolExtraction
# ---------------------------------------------------------------------------


def _extract(root: Path, module_name: str):
    """Run the derivation over a synthetic crate, the way the gate does."""
    crate = Crate(
        name=root.name,
        root=root,
        module_name=module_name,
        pyproject=root / "pyproject.toml",
        cargo_toml=root / "Cargo.toml",
    )
    return extract_expected_symbols(
        crate.root,
        crate_source_files(crate),
        load_crate_toml(crate.pyproject),
        load_crate_toml(crate.cargo_toml),
        crate.module_name,
    )


class TestSymbolExtraction:
    """The expected set is DERIVED, so its derivation is the thing to pin.

    A hand-maintained list of expected symbols would be the same defect one
    level up -- it goes stale exactly the way the timestamps did. These
    tests pin the source shapes that actually occur in `packages/`, each of
    which was found by running the derivation against all ten real crates
    and reconciling it, symbol by symbol, with what the built artifacts
    really export.
    """

    def _crate(self, tmp_path: Path, lib_rs: str, *, module_name: str = "ext", **kwargs) -> Path:
        root = tmp_path / "packages" / "c"
        return _make_pyo3_crate(
            root, package_name="c", module_name=module_name, lib_rs=lib_rs, **kwargs
        )

    def test_registered_functions_and_classes_are_expected(self, tmp_path: Path) -> None:
        root = self._crate(tmp_path, _lib_rs("ext"))
        result = _extract(root, "ext")
        assert set(result.symbols) == set(_REGISTERED_SYMBOLS)

    def test_pyo3_rename_is_honored(self, tmp_path: Path) -> None:
        """`#[pyo3(name = "...")]` is the exported name -- 54 items in this
        repo use it, and assuming the Rust identifier would flag every one."""
        root = self._crate(tmp_path, _lib_rs("ext"))
        result = _extract(root, "ext")
        assert "renamed_beta" in result.symbols
        assert "beta_rs" not in result.symbols

    def test_declared_but_unregistered_pyfunction_is_not_expected(
        self, tmp_path: Path
    ) -> None:
        """911 `#[pyfunction]` items exist in packages/, 774 are registered.
        Demanding the difference would be 137 false positives, which is how
        a gate gets switched off instead of fixed."""
        root = self._crate(tmp_path, _lib_rs("ext"))
        assert "never_registered" not in _extract(root, "ext").symbols

    def test_disabled_feature_gate_excludes_the_item(self, tmp_path: Path) -> None:
        """An item behind a feature this build does not enable is not in the
        artifact and must not be demanded of it."""
        lib_rs = """\
use pyo3::prelude::*;

#[pyfunction]
fn always_here() -> f64 { 1.0 }

#[cfg(feature = "extras")]
#[pyfunction]
fn only_with_extras() -> f64 { 2.0 }

#[pymodule]
fn ext(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(always_here, m)?)?;
    m.add_function(wrap_pyfunction!(only_with_extras, m)?)?;
    Ok(())
}
"""
        root = self._crate(tmp_path, lib_rs)
        assert set(_extract(root, "ext").symbols) == {"always_here"}

    def test_enabled_feature_gate_includes_the_item(self, tmp_path: Path) -> None:
        """Control for the test above: same shape, feature turned on.

        Without this pair, "excluded because the feature is off" is
        indistinguishable from "excluded because the parser gave up".
        """
        lib_rs = """\
use pyo3::prelude::*;

#[cfg(feature = "python")]
#[pyfunction]
fn gated_on_python() -> f64 { 2.0 }

#[pymodule]
fn ext(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(gated_on_python, m)?)?;
    Ok(())
}
"""
        root = self._crate(tmp_path, lib_rs)
        assert set(_extract(root, "ext").symbols) == {"gated_on_python"}

    def test_cfg_attr_pyfunction_is_recognised(self, tmp_path: Path) -> None:
        """`#[cfg_attr(feature = "python", pyfunction)]` -- 17 sites in this
        repo, all of them wasm-compatibility shims."""
        lib_rs = """\
use pyo3::prelude::*;

#[cfg_attr(feature = "python", pyfunction)]
pub fn compare_stage(a: f64) -> f64 { a }

#[cfg_attr(feature = "absent", pyfunction)]
pub fn not_built(a: f64) -> f64 { a }

#[pymodule]
fn ext(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(compare_stage, m)?)?;
    m.add_function(wrap_pyfunction!(not_built, m)?)?;
    Ok(())
}
"""
        root = self._crate(tmp_path, lib_rs)
        assert set(_extract(root, "ext").symbols) == {"compare_stage"}

    def test_submodule_symbols_carry_their_dotted_path(self, tmp_path: Path) -> None:
        """`add_submodule` puts the name one level down.

        temper-design-bundle does this 20 times; treating those as top-level
        names produced 122 phantom "missing" symbols against a known-good
        build while this was being written.
        """
        lib_rs = """\
use pyo3::prelude::*;

#[pyfunction]
fn nested_fn() -> f64 { 1.0 }

#[pyclass]
struct NestedClass {}

#[pymodule]
fn ext(module: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = module.py();
    let sub = PyModule::new(py, "contracts")?;
    sub.add_function(wrap_pyfunction!(nested_fn, &sub)?)?;
    sub.add_class::<NestedClass>()?;
    module.add_submodule(&sub)
}
"""
        root = self._crate(tmp_path, lib_rs)
        assert set(_extract(root, "ext").symbols) == {
            "contracts",
            "contracts.nested_fn",
            "contracts.NestedClass",
        }

    def test_string_literal_module_attributes_are_expected(self, tmp_path: Path) -> None:
        """`m.add("BUILD_PROFILE", ...)` is a module attribute like any other."""
        lib_rs = """\
use pyo3::prelude::*;

#[pymodule]
fn ext(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("BUILD_PROFILE", "release")?;
    Ok(())
}
"""
        root = self._crate(tmp_path, lib_rs)
        assert "BUILD_PROFILE" in _extract(root, "ext").symbols

    def test_registration_is_followed_through_helper_functions(
        self, tmp_path: Path
    ) -> None:
        """`crate::foo::register(m)` -- how nine of the ten real crates
        register nearly everything they export."""
        root = self._crate(
            tmp_path,
            """\
use pyo3::prelude::*;

mod kernels;

#[pymodule]
fn ext(m: &Bound<'_, PyModule>) -> PyResult<()> {
    crate::kernels::register(m)?;
    Ok(())
}
""",
        )
        _write(
            root / "src" / "kernels.rs",
            """\
use pyo3::prelude::*;

#[pyfunction]
pub fn from_a_helper() -> f64 { 1.0 }

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(from_a_helper, m)?)?;
    Ok(())
}
""",
        )
        assert set(_extract(root, "ext").symbols) == {"from_a_helper"}

    def test_macro_generated_pyfunction_is_expected_and_flagged_inferred(
        self, tmp_path: Path
    ) -> None:
        """`netclass_fn!(is_hv_net, ...)` expands to a `#[pyfunction]` that
        no source scan can see as an item.

        Dropping it would silently un-check `is_hv_net` -- the very symbol
        whose stale answer (`is_hv_net("hb-gnd") == False`) sent an agent
        down a wrong path for hours. So the default name is demanded, and
        the assumption is counted rather than hidden.
        """
        lib_rs = """\
use pyo3::prelude::*;

macro_rules! netclass_fn {
    ($py_name:ident) => {
        #[pyfunction]
        pub fn $py_name(name: &str) -> bool { name.is_empty() }
    };
}

netclass_fn!(is_hv_net);

#[pymodule]
fn ext(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(is_hv_net, m)?)?;
    Ok(())
}
"""
        root = self._crate(tmp_path, lib_rs)
        result = _extract(root, "ext")
        assert "is_hv_net" in result.symbols
        assert result.symbols["is_hv_net"].inferred
        assert result.inferred_count == 1

    def test_comments_and_strings_cannot_manufacture_symbols(
        self, tmp_path: Path
    ) -> None:
        """Registration-looking text inside a comment or a string literal is
        not registration. Without masking, a doc comment showing example
        usage would add a symbol nothing exports."""
        lib_rs = """\
use pyo3::prelude::*;

#[pyfunction]
fn real_one() -> f64 { 1.0 }

/// Example: m.add_function(wrap_pyfunction!(from_a_doc_comment, m)?)?;
#[pymodule]
fn ext(m: &Bound<'_, PyModule>) -> PyResult<()> {
    let _ = "m.add_function(wrap_pyfunction!(from_a_string, m)?)?;";
    m.add_function(wrap_pyfunction!(real_one, m)?)?;
    Ok(())
}
"""
        root = self._crate(tmp_path, lib_rs)
        assert set(_extract(root, "ext").symbols) == {"real_one"}

    def test_another_crates_pymodule_is_never_the_entry_point(
        self, tmp_path: Path
    ) -> None:
        """A crate's source set includes its local path dependencies, and
        several of those are pyo3 crates with their own `#[pymodule]`.

        Measured while writing this: temper-orchestration resolved to
        temper_geometry's entry point and reported two phantom missing
        classes.
        """
        root = self._crate(tmp_path, _lib_rs("ext"))
        dep = tmp_path / "packages" / "dep"
        _make_pyo3_crate(dep, package_name="dep", module_name="dep_ext")
        (root / "Cargo.toml").write_text(
            (root / "Cargo.toml").read_text() + '\ndep = { path = "../dep" }\n'
        )
        result = _extract(root, "ext")
        assert result.entry_point == "ext"
        assert set(result.symbols) == set(_REGISTERED_SYMBOLS)


# ---------------------------------------------------------------------------
# TestSymbolFalsifiability
# ---------------------------------------------------------------------------


def _install_loadable_module(
    site_packages: Path, module_name: str, provides, mtime: float
) -> Path:
    """Install a module the gate's loader really loads.

    No compiled `.so`: `_resolve_native_artifact` falls back to the package
    `__init__.py` when no native sibling exists, and that file is a real
    module the subprocess loader executes and introspects for real. So these
    tests exercise the ENTIRE path -- derive expectations from Rust source,
    load the installed artifact, diff -- with nothing stubbed. Breaking the
    symbol set here is a one-line change to *provides*, which is exactly the
    mutation a freshness gate has to be able to detect.
    """
    pkg_dir = site_packages / module_name
    pkg_dir.mkdir(parents=True, exist_ok=True)
    init_py = pkg_dir / "__init__.py"
    body = "\n".join(
        f"class {name}:\n    pass" if name[0].isupper() else f"def {name}():\n    return None"
        for name in provides
    )
    init_py.write_text(body + "\n")
    os.utime(init_py, (mtime, mtime))
    return init_py


class TestSymbolFalsifiability:
    """Can this gate go red? Proved, not asserted.

    A freshness gate that cannot detect staleness is the joke writing
    itself. This repo already carries a vacuity gate
    (`gate/ato-assertion-vacuity`) that exists because 74 of 86 electrical
    assertions could not fail, so every check below comes with the control
    that proves the red was caused by the mutation and not by the fixture.
    """

    def _setup(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, provides) -> Crate:
        now = time.time()
        crate = _crate_with_source(tmp_path, source_mtime=now - 3600)
        init_py = _install_loadable_module(
            tmp_path / "site-packages", "fake_crate_ext", provides, mtime=now
        )
        fake_spec = importlib.util.spec_from_file_location("fake_crate_ext", init_py)
        monkeypatch.setattr(
            importlib.util,
            "find_spec",
            lambda name: fake_spec if name == "fake_crate_ext" else None,
        )
        return crate

    def test_green_when_the_artifact_provides_every_registered_symbol(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The control. Without it, the red below proves nothing."""
        crate = self._setup(tmp_path, monkeypatch, _REGISTERED_SYMBOLS)
        status = check_module(crate)
        assert status.state == "fresh", status.detail
        assert status.symbols is not None
        assert status.symbols.expected == len(_REGISTERED_SYMBOLS)
        assert status.symbols.missing == ()

    def test_breaking_the_symbol_set_flips_the_verdict(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """THE falsifier: same crate, same timestamps, one symbol removed
        from the installed artifact -- and the verdict must flip."""
        crate = self._setup(tmp_path, monkeypatch, _REGISTERED_SYMBOLS)
        assert check_module(crate).state == "fresh"

        init_py = tmp_path / "site-packages" / "fake_crate_ext" / "__init__.py"
        mtime = init_py.stat().st_mtime
        _install_loadable_module(
            tmp_path / "site-packages",
            "fake_crate_ext",
            [s for s in _REGISTERED_SYMBOLS if s != "Gamma"],
            mtime=mtime,
        )

        status = check_module(crate)
        assert status.state == "symbols", (
            f"removing a registered symbol from the installed artifact left "
            f"the gate reporting {status.state!r} -- a freshness gate that "
            f"cannot detect this is the joke writing itself: {status.detail}"
        )
        assert status.symbols is not None
        assert status.symbols.missing == ("Gamma",)
        assert "Gamma" in status.detail
        assert "lib.rs" in status.detail, "the finding must say where the symbol is registered"

    def test_the_timestamp_check_alone_calls_the_broken_artifact_fresh(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Pins WHY the symbol check had to be added, not merely that it
        works: on this exact filesystem state the timestamp comparison --
        the entire pre-existing gate -- says the artifact is fine.
        """
        crate = self._setup(
            tmp_path, monkeypatch, [s for s in _REGISTERED_SYMBOLS if s != "Gamma"]
        )
        artifact = tmp_path / "site-packages" / "fake_crate_ext" / "__init__.py"
        newest_mtime, _newest = newest_source_mtime(crate)
        assert artifact.stat().st_mtime > newest_mtime, (
            "the fixture must be one the mtime rule passes, or this proves nothing"
        )
        assert check_module(crate).state == "symbols"

    def test_missing_symbols_are_fatal_even_when_not_required(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Never softened by TEMPER_REQUIRE_FRESH_EXTENSIONS.

        "Not built here" is a legitimate local state; "built, and quietly
        answering with a symbol table that does not match its source" is not
        -- it returns a wrong ANSWER rather than an error, which is the
        failure mode nobody notices.
        """
        crate = self._setup(
            tmp_path, monkeypatch, [s for s in _REGISTERED_SYMBOLS if s != "alpha"]
        )
        report = Report(crates_discovered=1, results=[CrateResult(crate, check_module(crate))])
        assert decide_exit_code(report, required=False) == EXIT_VIOLATION
        assert decide_exit_code(report, required=True) == EXIT_VIOLATION

    def test_stale_and_symbol_gap_report_both_findings(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Two independent pieces of evidence; neither hides the other."""
        now = time.time()
        crate = _crate_with_source(tmp_path, source_mtime=now)
        init_py = _install_loadable_module(
            tmp_path / "site-packages",
            "fake_crate_ext",
            [s for s in _REGISTERED_SYMBOLS if s != "Gamma"],
            mtime=now - 86400,
        )
        fake_spec = importlib.util.spec_from_file_location("fake_crate_ext", init_py)
        monkeypatch.setattr(
            importlib.util,
            "find_spec",
            lambda name: fake_spec if name == "fake_crate_ext" else None,
        )
        status = check_module(crate)
        assert status.state == "stale"
        assert "predates" in status.detail
        assert "Gamma" in status.detail

    def test_extra_symbols_in_the_artifact_are_not_a_violation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """One-directional on purpose.

        A real artifact carries `__doc__`, `__loader__`, pyo3 bookkeeping,
        and anything a newer source registers that this checkout predates.
        Failing on extras would make the gate fire on every legitimate
        artifact, which is how a gate gets disabled.
        """
        crate = self._setup(tmp_path, monkeypatch, [*_REGISTERED_SYMBOLS, "an_extra_symbol"])
        assert check_module(crate).state == "fresh"

    def test_zero_expected_symbols_is_a_tool_error_not_a_pass(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The anti-vacuity backstop for the symbol check itself.

        If the derivation ever stops understanding a crate's source, the
        expected set silently empties and every artifact trivially satisfies
        it -- a symbol check with nothing in it, reporting PASSED. That must
        be a tool error, exactly as zero-crates-discovered already is.
        """
        crate = self._setup(tmp_path, monkeypatch, _REGISTERED_SYMBOLS)
        (crate.root / "src" / "lib.rs").write_text("// no pymodule at all\n")
        status = check_module(crate)
        assert status.state == "error"
        assert "ZERO expected symbols" in status.detail
        report = Report(crates_discovered=1, results=[CrateResult(crate, status)])
        assert decide_exit_code(report, required=False) == EXIT_TOOL_ERROR

    def test_a_corrupt_artifact_is_reported_not_crashed_on(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Loading happens in a child process precisely so that a broken
        artifact produces a verdict instead of taking the gate down."""
        crate = self._setup(tmp_path, monkeypatch, _REGISTERED_SYMBOLS)
        init_py = tmp_path / "site-packages" / "fake_crate_ext" / "__init__.py"
        mtime = init_py.stat().st_mtime
        init_py.write_text("this is not valid python(\n")
        os.utime(init_py, (mtime, mtime))
        status = check_module(crate)
        assert status.state == "unloadable"
        assert "could not be loaded" in status.detail
