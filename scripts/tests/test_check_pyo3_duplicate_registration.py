"""Tests for check_pyo3_duplicate_registration.py.

The incident this gate closes (2026-08-13): `temper-geometry` had two
independent `#[pyfunction] pub fn kw_boundary_match_py` definitions --
`via_clearance.rs` and `trace_width_assignment.rs` -- both wired into the
same `temper_geometry` pymodule. pyo3's `PyModule::add_function` silently
overwrites on a name collision; the earlier registration became unreachable
dead code with its own passing test suite. This class is invisible to
`cargo build`/`cargo test`/`check_stale_extensions.py`, and specifically
invisible to `check_unwired_kernels.py` (a different, complementary gate)
because that gate's `registered_symbols()` scan uses `dict.setdefault()` --
it keeps the first registration it sees and never notices a second one
exists at all.

Three groups:

1. `TestCleanTrees` -- a single-file and a multi-file (register() delegation
   chain) synthetic crate, each with distinct Python-visible names, report
   zero duplicates.
2. `TestCatchesDuplicate` -- the exact incident shape (two files, same
   `#[pyfunction] fn kw_boundary_match_py`, both `wrap_pyfunction!`'d into
   one pymodule) is caught and named with both call sites; a duplicate
   `add_class` is caught the same way; two DIFFERENT crates each declaring
   the same Python name is explicitly NOT a violation (they are different
   top-level Python modules and cannot collide at runtime).
3. `TestRenameResolution` -- the false-positive this gate's own development
   surfaced against the real repo (`temper-drc-rs`'s two, unrelated,
   same-named `struct ConstraintSet` in different files, only one of which
   carries `#[pyclass(name = "TypedConstraintSet")]`) must NOT be flagged;
   a genuine cross-file rename (declared in one file, registered from
   another, e.g. `lib.rs`) must still resolve correctly.
4. `TestAntiVacuity` -- zero crates, and a crate with zero registrations,
   both fail closed (GATE ERROR), never silently PASSED.
5. `TestRealRepo` -- the actual repo, post-consolidation, is clean.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_pyo3_duplicate_registration import (  # noqa: E402
    EXIT_GATE_ERROR,
    EXIT_OK,
    EXIT_VIOLATION,
    GateError,
    discover_crates,
    main,
    run,
)


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def _make_crate(root: Path, package_name: str, module_name: str) -> Path:
    """Minimal pyo3/maturin-shaped crate tree satisfying
    `check_stale_extensions.discover_crates`'s own filters (maturin
    build-backend, cdylib crate-type, pyo3 dependency)."""
    _write(
        root / "Cargo.toml",
        f"""\
[package]
name = "{package_name}"
version = "0.1.0"
edition = "2021"

[lib]
name = "{module_name}"
crate-type = ["cdylib"]

[dependencies]
pyo3 = {{ version = "0.29", features = ["extension-module"] }}
""",
    )
    _write(
        root / "pyproject.toml",
        f"""\
[build-system]
requires = ["maturin>=1.8"]
build-backend = "maturin"

[project]
name = "{package_name}"
version = "0.1.0"

[tool.maturin]
features = ["pyo3/extension-module"]
module-name = "{module_name}"
""",
    )
    return root


class TestCleanTrees:
    def test_single_file_no_duplicates(self, tmp_path: Path) -> None:
        root = _make_crate(tmp_path / "packages" / "one", "one", "one_ext")
        _write(
            root / "src" / "lib.rs",
            """\
use pyo3::prelude::*;

#[pyfunction]
pub fn foo_py() -> PyResult<bool> { Ok(true) }

#[pyfunction]
pub fn bar_py() -> PyResult<bool> { Ok(true) }

#[pymodule]
fn one_ext(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(foo_py, m)?)?;
    m.add_function(wrap_pyfunction!(bar_py, m)?)?;
    Ok(())
}
""",
        )
        report = run(tmp_path)
        assert report.duplicates == {}
        names = sorted(s.python_name for u in report.units for s in u.sites)
        assert names == ["bar_py", "foo_py"]

    def test_multi_file_register_delegation_chain(self, tmp_path: Path) -> None:
        """lib.rs's #[pymodule] calls a::register(m), which itself calls
        b::register(m) -- the transitive-BFS case, mirroring temper-
        geometry's real lib.rs -> via_clearance::register(m) shape."""
        root = _make_crate(tmp_path / "packages" / "chain", "chain", "chain_ext")
        _write(
            root / "src" / "lib.rs",
            """\
use pyo3::prelude::*;
mod a;
mod b;

#[pymodule]
fn chain_ext(m: &Bound<'_, PyModule>) -> PyResult<()> {
    crate::a::register(m)?;
    Ok(())
}
""",
        )
        _write(
            root / "src" / "a.rs",
            """\
use pyo3::prelude::*;

#[pyfunction]
pub fn a_py() -> PyResult<bool> { Ok(true) }

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(a_py, m)?)?;
    crate::b::register(m)?;
    Ok(())
}
""",
        )
        _write(
            root / "src" / "b.rs",
            """\
use pyo3::prelude::*;

#[pyfunction]
pub fn b_py() -> PyResult<bool> { Ok(true) }

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(b_py, m)?)?;
    Ok(())
}
""",
        )
        report = run(tmp_path)
        assert report.duplicates == {}
        names = sorted(s.python_name for u in report.units for s in u.sites)
        assert names == ["a_py", "b_py"]


class TestCatchesDuplicate:
    def test_the_kw_boundary_match_py_shape(self, tmp_path: Path) -> None:
        """Two files, each with their own `#[pyfunction] fn shared_py`, both
        wrap_pyfunction!'d into the same pymodule -- the exact incident."""
        root = _make_crate(tmp_path / "packages" / "geo", "geo", "geo_ext")
        _write(
            root / "src" / "lib.rs",
            """\
use pyo3::prelude::*;
mod via_clearance;
mod trace_width_assignment;

#[pymodule]
fn geo_ext(m: &Bound<'_, PyModule>) -> PyResult<()> {
    crate::trace_width_assignment::register(m)?;
    crate::via_clearance::register(m)?;
    Ok(())
}
""",
        )
        _write(
            root / "src" / "via_clearance.rs",
            """\
use pyo3::prelude::*;

#[pyfunction]
pub fn shared_py(x: bool) -> PyResult<bool> { Ok(x) }

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(shared_py, m)?)?;
    Ok(())
}
""",
        )
        _write(
            root / "src" / "trace_width_assignment.rs",
            """\
use pyo3::prelude::*;

#[pyfunction]
pub fn shared_py(x: bool) -> PyResult<bool> { Ok(!x) }

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(shared_py, m)?)?;
    Ok(())
}
""",
        )
        report = run(tmp_path)
        assert list(report.duplicates.keys()) == ["geo::geo_ext::shared_py"]
        sites = report.duplicates["geo::geo_ext::shared_py"]
        assert {Path(s.file).name for s in sites} == {"via_clearance.rs", "trace_width_assignment.rs"}
        assert len(sites) == 2

    def test_duplicate_add_class(self, tmp_path: Path) -> None:
        root = _make_crate(tmp_path / "packages" / "cls", "cls", "cls_ext")
        _write(
            root / "src" / "lib.rs",
            """\
use pyo3::prelude::*;
mod a;
mod b;

#[pymodule]
fn cls_ext(m: &Bound<'_, PyModule>) -> PyResult<()> {
    crate::a::register(m)?;
    crate::b::register(m)?;
    Ok(())
}
""",
        )
        _write(
            root / "src" / "a.rs",
            """\
use pyo3::prelude::*;

#[pyclass]
pub struct Thing { }

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<Thing>()?;
    Ok(())
}
""",
        )
        _write(
            root / "src" / "b.rs",
            """\
use pyo3::prelude::*;

#[pyclass]
pub struct Thing { }

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<Thing>()?;
    Ok(())
}
""",
        )
        report = run(tmp_path)
        assert list(report.duplicates.keys()) == ["cls::cls_ext::Thing"]

    def test_same_name_across_different_crates_is_not_a_violation(self, tmp_path: Path) -> None:
        for crate_name, mod_name in (("crate-one", "crate_one"), ("crate-two", "crate_two")):
            root = _make_crate(tmp_path / "packages" / crate_name, crate_name, mod_name)
            _write(
                root / "src" / "lib.rs",
                f"""\
use pyo3::prelude::*;

#[pyfunction]
pub fn foo_py() -> PyResult<bool> {{ Ok(true) }}

#[pymodule]
fn {mod_name}(m: &Bound<'_, PyModule>) -> PyResult<()> {{
    m.add_function(wrap_pyfunction!(foo_py, m)?)?;
    Ok(())
}}
""",
            )
        report = run(tmp_path)
        assert report.duplicates == {}
        assert len(report.units) == 2


class TestRenameResolution:
    def test_same_bare_name_different_files_one_renamed_is_not_a_false_positive(
        self, tmp_path: Path
    ) -> None:
        """Regression test for a false positive this gate's own development
        surfaced against the real repo: temper-drc-rs declares TWO distinct
        `struct ConstraintSet` in different files; only one carries
        `#[pyclass(name = "TypedConstraintSet")]`. Naively merging renames
        by bare Rust identifier across the whole crate (as
        check_unwired_kernels.py deliberately does, for an unrelated,
        complementary reason) makes the unrenamed one inherit the OTHER
        file's rename and reports a phantom duplicate. This must not
        happen."""
        root = _make_crate(tmp_path / "packages" / "drc", "drc", "drc_ext")
        _write(
            root / "src" / "lib.rs",
            """\
use pyo3::prelude::*;
mod marshal;
mod contracts;

#[pymodule]
fn drc_ext(m: &Bound<'_, PyModule>) -> PyResult<()> {
    crate::marshal::register(m)?;
    crate::contracts::register(m)?;
    Ok(())
}
""",
        )
        _write(
            root / "src" / "marshal.rs",
            """\
use pyo3::prelude::*;

#[pyclass(name = "TypedConstraintSet")]
pub struct ConstraintSet { }

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<ConstraintSet>()?;
    Ok(())
}
""",
        )
        _write(
            root / "src" / "contracts.rs",
            """\
use pyo3::prelude::*;

#[pyclass]
pub struct ConstraintSet { }

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<ConstraintSet>()?;
    Ok(())
}
""",
        )
        report = run(tmp_path)
        assert report.duplicates == {}, report.duplicates
        names = sorted(s.python_name for u in report.units for s in u.sites)
        assert names == ["ConstraintSet", "TypedConstraintSet"]

    def test_cross_file_rename_still_resolves(self, tmp_path: Path) -> None:
        """The legitimate cross-file case check_unwired_kernels.py's own doc
        cites: a #[pyclass(name=...)] declared in one file, registered from
        another (here, lib.rs itself)."""
        root = _make_crate(tmp_path / "packages" / "cross", "cross", "cross_ext")
        _write(
            root / "src" / "lib.rs",
            """\
use pyo3::prelude::*;
mod types;

#[pymodule]
fn cross_ext(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<crate::types::Circle>()?;
    Ok(())
}
""",
        )
        _write(
            root / "src" / "types.rs",
            """\
use pyo3::prelude::*;

#[pyclass(name = "DSNCircle")]
pub struct Circle { }
""",
        )
        report = run(tmp_path)
        assert report.duplicates == {}
        names = [s.python_name for u in report.units for s in u.sites]
        assert names == ["DSNCircle"]


class TestAntiVacuity:
    def test_zero_crates_fails_closed(self, tmp_path: Path) -> None:
        (tmp_path / "packages").mkdir()
        with pytest.raises(GateError, match="zero crates"):
            run(tmp_path)

    def test_crate_with_zero_registrations_fails_closed(self, tmp_path: Path) -> None:
        root = _make_crate(tmp_path / "packages" / "empty", "empty", "empty_ext")
        _write(
            root / "src" / "lib.rs",
            """\
use pyo3::prelude::*;

#[pymodule]
fn empty_ext(_m: &Bound<'_, PyModule>) -> PyResult<()> {
    Ok(())
}
""",
        )
        with pytest.raises(GateError, match="zero pyo3 registrations"):
            run(tmp_path)

    def test_discover_crates_finds_nothing_under_empty_packages_dir(self, tmp_path: Path) -> None:
        (tmp_path / "packages").mkdir()
        assert discover_crates(tmp_path) == []


class TestRealRepo:
    def test_real_repo_is_clean(self) -> None:
        """The actual repo, post-consolidation: exactly one implementation
        backs `kw_boundary_match_py` now, and no other crate has this
        defect either."""
        repo_root = Path(__file__).resolve().parents[2]
        report = run(repo_root)
        assert report.duplicates == {}, report.duplicates
        assert len(report.units) >= 10
        total_sites = sum(len(u.sites) for u in report.units)
        assert total_sites > 100

    def test_main_exits_zero_against_the_real_repo(self) -> None:
        assert main() == EXIT_OK


def test_exit_code_constants_match_repo_convention() -> None:
    # 0 pass / 3 violation / 5 gate-error mirrors check_domain_partition.py
    # and check_stale_extensions.py's own convention (same job, same reader).
    assert (EXIT_OK, EXIT_VIOLATION, EXIT_GATE_ERROR) == (0, 3, 5)
