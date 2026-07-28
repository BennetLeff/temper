#!/usr/bin/env python3
"""Stale-compiled-Rust-extension CI gate.

Motivating incident (2026-07-27, see commit 02e907b9 and
docs/evidence/2026-07-27-stale-extension-gate.md): this repo had no
``.cargo/config.toml``, so on macOS *every* pyo3 crate failed to link
(``ld: symbol(s) not found for architecture arm64``, e.g.
``__Py_TrueStruct``) whenever anyone tried to rebuild its extension module
with ``maturin develop``. ``cargo build``/``cargo test`` were entirely
unaffected -- they build the rlib and link libpython normally -- so the
Rust test suites stayed green (temper-drc-rs 49/49, router-core 101/101)
while every ``.so`` already installed in ``.venv`` sat frozen at its last
successful build. The installed ``temper_io_types.cpython-312-darwin.so``
was dated Jul 23 and did not contain ``ConfigBoardMismatchError``, a
symbol registered at ``packages/temper-io-types/src/lib.rs:1178-1181`` --
confirmed with ``strings`` (2 occurrences in a fresh build, 0 in the
installed one). Two pytest modules silently failed to COLLECT as a
result -- reported as an error line easy to scroll past, not a loud
failure. A related trap: ``maturin develop`` printed "Installed ... as
editable" while leaving the stale ``.so`` in place -- a success message
from the build tool is not proof the artifact was replaced.

This gate closes that blind spot generically, for every pyo3/maturin
extension crate in the repo, not just the one that broke that day.

Design decision: crate discovery (source-tree scan, not environment scan)
--------------------------------------------------------------------------
``discover_crates`` walks ``packages/`` looking for directories that pair
a ``pyproject.toml`` (``build-backend = "maturin"``) with a sibling
``Cargo.toml`` whose ``[lib]`` table declares ``crate-type = [...,
"cdylib", ...]`` and whose ``[dependencies]`` include ``pyo3``. This is a
STATIC scan of source files -- it never depends on what happens to be
installed in the current environment. That is exactly what makes the
anti-vacuity backstop below meaningful: "how many pyo3 crates does this
repo contain" has one right answer regardless of build state, so finding
zero is always a bug in this scan (or a mangled checkout), never a
legitimate "nothing to check" outcome. An environment-driven discovery
(e.g. "whatever's importable") would silently shrink to whatever happened
to be installed and could report a vacuous "0 checked, PASSED" exactly
the way this repo's own history warns against.

Design decision: crate -> installed module mapping
-----------------------------------------------------
The Python import name is read from ``[tool.maturin] module-name`` in the
crate's own ``pyproject.toml`` -- NOT derived by replacing ``-`` with
``_`` in the crate name. ``temper-design-bundle`` proves why: its real
importable name is ``temper_design_bundle_python``, not
``temper_design_bundle``. Guessing would either silently check the wrong
(nonexistent) module -- always reporting MISSING, useless noise -- or
worse, resolve to an unrelated module of the guessed name and misreport.
Falls back to ``[project].name`` (hyphens replaced) only when
``module-name`` is absent, matching maturin's own default.

Design decision: "newest source file", including workspace dependencies
--------------------------------------------------------------------------
For a crate rooted at ``<root>``, the source set is:

  - ``<root>/Cargo.toml`` and ``<root>/pyproject.toml`` (build config --
    a features/module-name edit with no rebuild is itself a staleness bug)
  - ``<root>/build.rs`` if present (participates in codegen for at least
    one crate here, temper-constraints)
  - every ``*.rs`` under ``<root>/src/``
  - the same four categories, RECURSIVELY, for every local path
    dependency declared in ``[dependencies]``/``[build-dependencies]``
    (``path = "..."`` entries) -- a change to a shared core crate (e.g.
    ``temper-geometry-core``) must mark every pyo3 crate that depends on
    it as needing a rebuild too, exactly as ``cargo build`` itself would
    pick it up. Recursion is cycle-safe (visited-set on resolved paths).

Deliberately excluded: ``Cargo.lock`` (bumped by routine dependency
resolution unrelated to this crate's own code -- would false-positive on
every lockfile refresh) and anything under ``target/`` (build output, not
source; see the artifact-resolution note below for why build-artifact
timestamps specifically are not a source of false positives here).

Design decision: resolving the actual compiled artifact, not a wrapper
--------------------------------------------------------------------------
``importlib.util.find_spec(module_name)`` is used to locate the module
without importing it (no side effects from running a CI gate -- same
reasoning as ``check_undeclared_imports.py``). For every crate in this
repo, maturin's default "mixed" packaging makes ``find_spec`` resolve to
a thin, regenerated-on-every-build wrapper,
``<module>/__init__.py`` containing exactly ``from .<module> import *``
-- the real compiled artifact lives alongside it as
``<module>/<module>.cpython-*.so`` (confirmed empirically for all ten
pyo3 crates in this repo, both ``maturin develop`` editable installs and
plain ``uv sync`` wheel installs). This gate resolves past the wrapper to
stat the native ``.so``/``.pyd`` directly -- the same file the incident's
own ``strings`` check inspected -- falling back to the wrapper's own
mtime only if no matching native file is found by name (a future crate
with a nonstandard layout). Stopping at the wrapper would usually still
work (maturin rewrites it in the same install event as the ``.so`` copy),
but stating the actual binary is the more direct signal and the one this
gate's own docstring can point to when someone asks "how do you know."

Design decision: never trust a build tool's success message
--------------------------------------------------------------------------
Nothing here reads maturin's/uv's stdout. The 2026-07-27 incident's
sharpest lesson was that ``maturin develop`` printed "Installed ... as
editable" while the stale ``.so`` sat untouched. This gate only ever
looks at real filesystem mtimes of real files it independently locates.

False-positive avoidance
--------------------------
``git checkout``/clone resets every tracked file's mtime to the checkout
time, including ``.rs`` sources -- so a machine that already has a fresh
build installed *before* switching branches, then switches to a branch
whose sources are textually identical but newly checked out, could see
source mtimes "newer" than an install that is not actually stale. This
gate does not attempt to defeat that (would require content hashing or
git-log timestamps, a materially heavier check); it inherits the same
assumption every other freshness gate in this repo makes
(``check_copper_net_consistency.py``'s netlist-vs-``.ato`` check,
``check_rust_drc_presence.py``'s symbol check): the normal workflow
builds AFTER checkout, which is exactly what CI does and is the
environment ``TEMPER_REQUIRE_FRESH_EXTENSIONS=1`` (below) targets.

The "is staleness fatal here" signal
--------------------------------------
STALE (module present but built from an older revision of its own
source) is **always** a hard failure, unconditionally -- this is the
entire point of the gate: a present-but-wrong extension is silently
dangerous in a way "not installed at all" is not, which is the exact
shape of the incident this gate exists to catch. There is no
legitimate/intentional reason for an installed extension to predate its
own crate's source.

MISSING (module not importable at all) is softer, controlled by
``TEMPER_REQUIRE_FRESH_EXTENSIONS`` (mirrors
``TEMPER_REQUIRE_RUST_DRC`` in ``check_rust_drc_presence.py``):

  - Unset / "0" / "false" (default -- local dev): a contributor who
    hasn't run ``maturin develop`` for a given crate yet (or lacks a
    Rust toolchain) gets a WARNING, not a failure -- several of these
    extensions have documented pure-Python fallbacks.
  - "1" / "true" / "yes" (CI sets this): every crate must be present,
    because CI is the place a missing accelerator's absence should never
    be silent.

Anti-vacuous-truth backstop (always fatal, regardless of the flag above):
zero crates discovered, or any crate whose own freshness could not be
determined (e.g. its ``src/`` directory vanished), is a TOOL ERROR, never
folded into "0 violations".

Exit codes:
  0 - PASSED (or WARN on missing-but-not-required): every checked crate
      is fresh, or the only issues are MISSING crates and
      TEMPER_REQUIRE_FRESH_EXTENSIONS is not set.
  3 - VIOLATION: at least one crate's installed extension module is
      STALE, or (when TEMPER_REQUIRE_FRESH_EXTENSIONS is set) MISSING.
  5 - GATE ERROR: zero crates discovered, or a per-crate freshness
      computation failed -- never conflated with "0 violations".

Usage:
  uv run python scripts/check_stale_extensions.py
  TEMPER_REQUIRE_FRESH_EXTENSIONS=1 uv run python scripts/check_stale_extensions.py
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
import tomllib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.github_summary import get_github_summary_path  # noqa: E402
from _lib.repo import find_repo_root  # noqa: E402

EXIT_OK = 0
EXIT_VIOLATION = 3
EXIT_TOOL_ERROR = 5

_PRUNE_DIRS = {"target", ".git", "__pycache__", "node_modules", ".venv", ".mypy_cache"}


class GateError(Exception):
    """Raised for any condition that must fail closed (exit 5)."""


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Crate:
    name: str  # Cargo [package].name, e.g. "temper-io-types"
    root: Path  # crate directory (contains Cargo.toml + pyproject.toml)
    module_name: str  # Python import name, e.g. "temper_io_types"
    pyproject: Path
    cargo_toml: Path


def _load_toml(path: Path) -> dict:
    try:
        return tomllib.loads(path.read_text())
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return {}


def discover_crates(repo_root: Path) -> list[Crate]:
    """Scan ``packages/`` for pyo3/maturin extension crates. See module
    docstring "Design decision: crate discovery" for why this is a static
    source-tree scan rather than an environment probe.
    """
    packages_root = repo_root / "packages"
    if not packages_root.is_dir():
        return []

    crates: list[Crate] = []
    for dirpath, dirnames, filenames in os.walk(packages_root):
        dirnames[:] = sorted(d for d in dirnames if d not in _PRUNE_DIRS)
        if "pyproject.toml" not in filenames or "Cargo.toml" not in filenames:
            continue

        crate_dir = Path(dirpath)
        pyproject_path = crate_dir / "pyproject.toml"
        cargo_path = crate_dir / "Cargo.toml"

        pdata = _load_toml(pyproject_path)
        if pdata.get("build-system", {}).get("build-backend") != "maturin":
            continue

        cdata = _load_toml(cargo_path)
        lib = cdata.get("lib", {})
        if "cdylib" not in lib.get("crate-type", []):
            continue
        if "pyo3" not in cdata.get("dependencies", {}):
            continue

        maturin_cfg = pdata.get("tool", {}).get("maturin", {})
        module_name = maturin_cfg.get("module-name")
        if not module_name:
            project_name = pdata.get("project", {}).get("name", "")
            if not project_name:
                continue
            module_name = project_name.replace("-", "_")

        package_name = cdata.get("package", {}).get("name", crate_dir.name)
        crates.append(
            Crate(
                name=package_name,
                root=crate_dir,
                module_name=module_name,
                pyproject=pyproject_path,
                cargo_toml=cargo_path,
            )
        )

    return sorted(crates, key=lambda c: c.name)


# ---------------------------------------------------------------------------
# Source freshness (own files + recursive local path dependencies)
# ---------------------------------------------------------------------------


def _local_path_deps(cargo_data: dict, crate_root: Path) -> list[Path]:
    """Resolved crate-root paths for every `path = "..."` dependency in
    [dependencies]/[build-dependencies] -- the sections that affect the
    actual compiled artifact ([dev-dependencies] only affects `cargo
    test`, deliberately excluded).
    """
    out: list[Path] = []
    for section in ("dependencies", "build-dependencies"):
        for spec in cargo_data.get(section, {}).values():
            if isinstance(spec, dict) and "path" in spec:
                out.append((crate_root / spec["path"]).resolve())
    return out


def newest_source_mtime(crate: Crate) -> tuple[float, Path]:
    """Return (mtime, path) of the newest file among the crate's own
    Cargo.toml/pyproject.toml/build.rs/src/**/*.rs, and the same set,
    recursively, for every local path dependency. Raises GateError if no
    source files are found at all (fail closed -- see module docstring).
    """
    visited: set[Path] = set()
    newest_mtime = -1.0
    newest_path: Path | None = None

    def visit(root: Path, *, include_pyproject: bool) -> None:
        nonlocal newest_mtime, newest_path
        root = root.resolve()
        if root in visited or not root.is_dir():
            return
        visited.add(root)

        candidates: list[Path] = []
        cargo_toml = root / "Cargo.toml"
        if cargo_toml.is_file():
            candidates.append(cargo_toml)
        if include_pyproject:
            pyproject = root / "pyproject.toml"
            if pyproject.is_file():
                candidates.append(pyproject)
        build_rs = root / "build.rs"
        if build_rs.is_file():
            candidates.append(build_rs)
        src_dir = root / "src"
        if src_dir.is_dir():
            candidates.extend(src_dir.rglob("*.rs"))

        for f in candidates:
            try:
                m = f.stat().st_mtime
            except OSError:
                continue
            if m > newest_mtime:
                newest_mtime = m
                newest_path = f

        cdata = _load_toml(cargo_toml) if cargo_toml.is_file() else {}
        for dep_root in _local_path_deps(cdata, root):
            visit(dep_root, include_pyproject=False)

    visit(crate.root, include_pyproject=True)

    if newest_path is None:
        raise GateError(
            f"{crate.name}: no source files found under {crate.root} "
            "(Cargo.toml/pyproject.toml/build.rs/src/*.rs) -- cannot "
            "determine freshness; failing closed rather than skipping"
        )
    return newest_mtime, newest_path


# ---------------------------------------------------------------------------
# Installed-module resolution
# ---------------------------------------------------------------------------


def _resolve_native_artifact(module_name: str, origin: Path) -> Path:
    """See module docstring "Design decision: resolving the actual
    compiled artifact, not a wrapper". If *origin* is already a bare
    compiled file (no wrapper package), it is returned unchanged.
    """
    if origin.name != "__init__.py":
        return origin
    pkg_dir = origin.parent
    candidates = sorted(pkg_dir.glob(f"{module_name}*.so")) + sorted(
        pkg_dir.glob(f"{module_name}*.pyd")
    )
    return candidates[0] if candidates else origin


@dataclass
class ModuleStatus:
    state: str  # "fresh" | "stale" | "missing" | "error"
    detail: str
    artifact: Path | None = None
    artifact_mtime: float | None = None


def _fmt(ts: float) -> str:
    return datetime.fromtimestamp(ts).isoformat(timespec="seconds")


def check_module(crate: Crate) -> ModuleStatus:
    """Never trusts any build tool's stdout (see module docstring) --
    independently locates and stats the real installed artifact.
    """
    try:
        spec = importlib.util.find_spec(crate.module_name)
    except (ImportError, ModuleNotFoundError, ValueError, AttributeError, TypeError) as exc:
        return ModuleStatus("missing", f"{crate.module_name}: find_spec raised {exc!r}")

    if spec is None or not spec.origin:
        return ModuleStatus(
            "missing",
            f"{crate.module_name} is not importable in this environment -- "
            f"build it with `uv run maturin develop --release --manifest-path "
            f"{crate.cargo_toml}`",
        )

    origin = Path(spec.origin)
    if not origin.is_file():
        return ModuleStatus(
            "missing", f"{crate.module_name} resolved to a non-file origin: {origin}"
        )

    artifact = _resolve_native_artifact(crate.module_name, origin)

    try:
        newest_mtime, newest_source = newest_source_mtime(crate)
    except GateError as exc:
        return ModuleStatus("error", str(exc))

    artifact_mtime = artifact.stat().st_mtime
    if artifact_mtime < newest_mtime:
        age_days = (newest_mtime - artifact_mtime) / 86400.0
        return ModuleStatus(
            "stale",
            f"{crate.module_name}: installed artifact {artifact} "
            f"(built {_fmt(artifact_mtime)}) predates {newest_source} "
            f"(modified {_fmt(newest_mtime)}, {age_days:.2f} day(s) newer) -- "
            f"rebuild with `uv run maturin develop --release --manifest-path "
            f"{crate.cargo_toml}`",
            artifact=artifact,
            artifact_mtime=artifact_mtime,
        )

    return ModuleStatus(
        "fresh",
        f"{crate.module_name}: {artifact} (built {_fmt(artifact_mtime)}) is fresh",
        artifact=artifact,
        artifact_mtime=artifact_mtime,
    )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


@dataclass
class CrateResult:
    crate: Crate
    status: ModuleStatus


@dataclass
class Report:
    crates_discovered: int
    results: list[CrateResult] = field(default_factory=list)


def run(repo_root: Path) -> Report:
    crates = discover_crates(repo_root)
    if not crates:
        raise GateError(
            f"zero pyo3/maturin extension crates discovered under "
            f"{repo_root / 'packages'} -- vacuous run, not a clean pass. "
            "Either discover_crates() is broken or every Rust extension "
            "crate has been removed from the repo; either way this must "
            "not report success (see docs/METHODOLOGY.md Sec 4/5)."
        )
    results = [CrateResult(crate=c, status=check_module(c)) for c in crates]
    return Report(crates_discovered=len(crates), results=results)


def _required() -> bool:
    return os.environ.get("TEMPER_REQUIRE_FRESH_EXTENSIONS", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


_MARKER = {"fresh": "OK", "stale": "STALE", "missing": "MISSING", "error": "ERROR"}


def group_by_state(report: Report) -> dict[str, list[CrateResult]]:
    by_state: dict[str, list[CrateResult]] = {}
    for r in report.results:
        by_state.setdefault(r.status.state, []).append(r)
    return by_state


def decide_exit_code(report: Report, required: bool) -> int:
    """Pure decision function, isolated from I/O for unit testing.

    tool errors > STALE (always fatal) > MISSING (fatal only if
    *required*) > PASSED. See module docstring "The 'is staleness fatal
    here' signal" for why STALE is never gated by *required*.
    """
    by_state = group_by_state(report)
    if by_state.get("error"):
        return EXIT_TOOL_ERROR
    if by_state.get("stale"):
        return EXIT_VIOLATION
    if by_state.get("missing") and required:
        return EXIT_VIOLATION
    return EXIT_OK


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root", type=Path, default=None, help="Override repo root (mainly for tests)."
    )
    args = parser.parse_args()
    repo_root = args.repo_root or find_repo_root()
    required = _required()

    gh = get_github_summary_path()

    try:
        report = run(repo_root)
    except GateError as exc:
        print("=== STALE-EXTENSION GATE ERROR ===", file=sys.stderr)
        print(f"Reason: {exc}", file=sys.stderr)
        print(
            "GATE RESULT: ERROR -- not PASSED, not a violation. "
            "0 crate(s) checked.",
            file=sys.stderr,
        )
        if gh:
            with open(gh, "a") as f:
                f.write("### Stale-Extension Gate -- GATE ERROR\n")
                f.write(f"{exc}\n")
        return EXIT_TOOL_ERROR

    by_state = group_by_state(report)
    fresh = by_state.get("fresh", [])
    stale = by_state.get("stale", [])
    missing = by_state.get("missing", [])
    errors = by_state.get("error", [])

    print(
        f"Stale-extension gate -- {report.crates_discovered} pyo3/maturin "
        f"crate(s) discovered under packages/, {len(report.results)} checked "
        "(every discovered crate is checked; the denominator is never a subset)."
    )
    print(
        f"  fresh={len(fresh)} stale={len(stale)} missing={len(missing)} "
        f"tool-errors={len(errors)}  "
        f"TEMPER_REQUIRE_FRESH_EXTENSIONS={'1 (strict)' if required else '0 (lenient)'}"
    )
    for r in report.results:
        print(f"  [{_MARKER[r.status.state]}] {r.crate.name}: {r.status.detail}")

    if gh:
        with open(gh, "a") as f:
            f.write("### Stale-Extension Gate\n")
            f.write(
                f"- Crates discovered: {report.crates_discovered}\n"
                f"- Checked: {len(report.results)}\n"
                f"- Fresh: {len(fresh)}\n"
                f"- Stale: {len(stale)}\n"
                f"- Missing: {len(missing)}\n"
                f"- Tool errors: {len(errors)}\n"
                f"- TEMPER_REQUIRE_FRESH_EXTENSIONS: {required}\n"
            )

    exit_code = decide_exit_code(report, required)

    if errors:
        print(
            f"\nFAILED (tool error) -- {len(errors)} crate(s) could not be "
            "evaluated; never conflated with a clean pass.",
            file=sys.stderr,
        )
    elif exit_code == EXIT_VIOLATION:
        print(
            f"\nFAILED -- {len(stale)} stale extension(s)"
            + (f", {len(missing)} missing extension(s) (required)" if required and missing else "")
            + ".",
            file=sys.stderr,
        )
    else:
        if missing:
            print(
                f"\nWARN -- {len(missing)} extension module(s) not installed; not "
                "failing because TEMPER_REQUIRE_FRESH_EXTENSIONS is unset (local "
                "dev: not every accelerator is assumed built). CI sets this."
            )
        print(f"\nPASSED -- {len(fresh)}/{report.crates_discovered} extension module(s) fresh.")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
