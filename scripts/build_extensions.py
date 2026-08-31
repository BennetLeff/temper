#!/usr/bin/env python3
"""Build and verify every first-party PyO3 extension.

``cargo`` can leave a shared target directory containing a cdylib built with
the crate's non-Python feature set (for example after ``cargo check``).  A
later ``maturin develop`` can then reuse that output and install an artifact
without ``PyInit_<module>``.  The old Makefile loop also built alphabetically,
so a dependent build could replace an extension that had already been built.

This driver gives the build a deterministic order: dependents first, local
path dependencies last.  Every direct extension build therefore is the final
build of its package, explicitly enables ``python``, and starts by removing
that package's shared-target outputs.  The clean is intentionally scoped to
the package (never the whole shared cache); ``CARGO_TARGET_DIR`` is inherited
from Makefile's shared-cache export.  The final check additionally imports
all modules, because a symbol scan cannot catch a missing transitive loader
dependency.
"""

from __future__ import annotations

import argparse
import heapq
import importlib
import os
import subprocess
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_stale_extensions import (  # noqa: E402
    Crate,
    _local_path_deps,
    check_module,
    discover_crates,
)


def build_order(crates: list[Crate]) -> list[Crate]:
    """Return dependents-first, deterministic extension build order.

    A dependency's cdylib can be emitted while building a dependent package;
    placing dependencies last means their Python-feature artifact cannot be
    overwritten by another extension build after this function returns.
    Cycles are reported as a configuration error rather than silently using a
    partial order.
    """
    by_root = {crate.root.resolve(): crate for crate in crates}
    dependencies: dict[Path, list[Crate]] = {}
    for crate in crates:
        cargo_data = tomllib.loads(crate.cargo_toml.read_text())
        dependencies[crate.root.resolve()] = sorted(
            (
                by_root[dep]
                for dep in _local_path_deps(cargo_data, crate.root)
                if dep in by_root
            ),
            key=lambda item: item.name,
        )

    # Kahn's algorithm with the graph reversed: a crate is ready when no
    # unbuilt extension depends on it. This emits dependents first, while a
    # heap keeps independent choices deterministic and human-readable.
    dependents: dict[Path, list[Crate]] = {crate.root.resolve(): [] for crate in crates}
    remaining_dependents: dict[Path, int] = {}
    for crate in crates:
        root = crate.root.resolve()
        remaining_dependents[root] = len(dependents[root])
        for dependency in dependencies[root]:
            dependents[dependency.root.resolve()].append(crate)
    for root, users in dependents.items():
        remaining_dependents[root] = len(users)

    ready = [(crate.name, crate.root.resolve(), crate) for crate in crates if remaining_dependents[crate.root.resolve()] == 0]
    heapq.heapify(ready)
    result: list[Crate] = []
    while ready:
        _, root, crate = heapq.heappop(ready)
        result.append(crate)
        for dependency in dependencies[root]:
            dependency_root = dependency.root.resolve()
            remaining_dependents[dependency_root] -= 1
            if remaining_dependents[dependency_root] == 0:
                heapq.heappush(ready, (dependency.name, dependency_root, dependency))
    if len(result) != len(crates):
        raise ValueError("local extension dependency cycle")
    return result


def _run(command: list[str], *, env: dict[str, str] | None = None) -> None:
    """Run one build command, preserving its output and failing promptly."""
    subprocess.run(command, check=True, env=env)


def _force_recompile_trigger(crate: Crate) -> Path:
    """Touch a direct source after cleaning so Cargo cannot reuse a poison.

    ``cargo clean -p`` is scoped and normally sufficient, but it can report
    zero removals when the only bad output was produced while this package was
    a dependency.  Cargo then considers the direct package's cdylib complete
    even though it was built without ``python``.  Updating a source mtime is
    the proven recovery path from that incident (AGENTS.md); it changes no
    bytes and makes a real ``Compiling <crate>`` line unavoidable.
    """
    source = crate.root / "src" / "lib.rs"
    if not source.is_file():
        candidates = sorted((crate.root / "src").rglob("*.rs"))
        if not candidates:
            raise RuntimeError(f"{crate.name}: no Rust source exists to force a rebuild")
        source = candidates[0]
    os.utime(source, None)
    return source


def _clean_crate(crate: Crate) -> None:
    _run(
        [
            "cargo",
            "clean",
            "--manifest-path",
            str(crate.cargo_toml),
            "-p",
            crate.name,
        ]
    )


def _build_maturin(crate: Crate) -> None:
    env = os.environ.copy()
    # maturin refuses to run when both an active uv virtualenv and Conda are
    # advertised.  Agent shells commonly inherit CONDA_PREFIX, while CI's
    # job environment deliberately sets VIRTUAL_ENV; clear the unrelated
    # Conda marker so the extension build is reproducible in either context.
    env.pop("CONDA_PREFIX", None)
    if crate.name == "temper-constraints":
        env["PYO3_USE_ABI3_FORWARD_COMPATIBILITY"] = "1"
    _run(
        [
            "uv",
            "run",
            "--no-sync",
            "maturin",
            "develop",
            "--release",
            "--features",
            "python",
            "--manifest-path",
            str(crate.cargo_toml),
        ],
        env=env,
    )


def _remove_installed_artifact(crate: Crate) -> Path | None:
    """Remove an existing native file so editable install must copy anew.

    ``uv`` may hard-link an existing wheel into site-packages.  In that state
    maturin can report a successful editable install while the old inode (and
    its old mtime/bytes) remains.  Removing only the resolved native artifact
    is safe and narrow; maturin recreates it from the wheel it just built.
    """
    status = check_module(crate)
    artifact = status.artifact
    if artifact is None or artifact.suffix not in {".so", ".pyd"}:
        return None
    artifact.unlink(missing_ok=True)
    return artifact


def build_crate(crate: Crate, *, repo_root: Path, prepared: bool = False) -> None:
    """Remove stale outputs, trigger recompilation, and build the cdylib.

    ``prepared`` is used by :func:`main`: all crates are touched before any
    build starts.  That keeps transitive freshness timestamps coherent while
    still allowing the final dependency rebuild to repair a poisoned cdylib.
    """
    if not prepared:
        _clean_crate(crate)
        _force_recompile_trigger(crate)
    _remove_installed_artifact(crate)
    _build_maturin(crate)


def verify(crates: list[Crate], *, repo_root: Path) -> None:
    """Run the freshness gate and import every discovered module."""
    gate_env = os.environ.copy()
    gate_env["TEMPER_REQUIRE_FRESH_EXTENSIONS"] = "1"
    _run(
        [
            "uv",
            "run",
            "--no-sync",
            "python3",
            "scripts/check_stale_extensions.py",
            "--repo-root",
            str(repo_root),
        ],
        env=gate_env,
    )
    failures: list[str] = []
    for crate in crates:
        try:
            importlib.import_module(crate.module_name)
        except Exception as exc:  # pragma: no cover - exercised by real builds
            failures.append(f"{crate.name} ({crate.module_name}): {exc}")
    if failures:
        raise RuntimeError("extension import verification failed:\n" + "\n".join(failures))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=None)
    args = parser.parse_args(argv)
    repo_root = (args.repo_root or Path.cwd()).resolve()
    crates = discover_crates(repo_root)
    if not crates:
        parser.error(f"no pyo3/maturin crates discovered under {repo_root / 'packages'}")

    ordered = build_order(crates)
    print("Building extensions (dependents first; Python-feature builds last):")
    # Touch every direct source before starting any build. If only a
    # dependency were touched immediately before its final build, the
    # freshness gate would (correctly) mark dependents built earlier stale.
    # Preparing all timestamps up front avoids that while the dependents-first
    # order makes each dependency's own build the final cdylib producer.
    for crate in ordered:
        _clean_crate(crate)
    prepared_times: dict[Path, tuple[int, int]] = {}
    for crate in ordered:
        trigger = _force_recompile_trigger(crate)
        stat = trigger.stat()
        prepared_times[trigger] = (stat.st_atime_ns, stat.st_mtime_ns)
        print(f"  rebuild trigger: {trigger}", flush=True)
    for crate in ordered:
        print(f"--- {crate.name} ({crate.module_name}) ---", flush=True)
        # A dependent build can overwrite this crate's cdylib without the
        # Python feature after the up-front trigger. Retouch immediately so
        # Cargo must compile the direct pyo3 target, then restore the prepared
        # timestamp so dependents built earlier remain freshness-valid.
        trigger = _force_recompile_trigger(crate)
        try:
            build_crate(crate, repo_root=repo_root, prepared=True)
        finally:
            os.utime(trigger, ns=prepared_times[trigger])
    verify(crates, repo_root=repo_root)
    print(f"Verified {len(crates)} extension(s): fresh and importable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
