#!/usr/bin/env python3
"""Stale-compiled-Rust-extension CI gate.

Motivating incident (2026-07-27, commit ``02e907b9``): this repo had no
``.cargo/config.toml``, so on macOS *every* pyo3 crate failed to link
(``ld: symbol(s) not found for architecture arm64``) whenever anyone tried
to rebuild its extension module with ``maturin develop``, while
``cargo build``/``cargo test`` stayed green -- so installed ``.so`` files
sat frozen at their last successful build while ``lib.rs`` gained new
symbols. Two pytest modules silently failed to COLLECT as a result, and
``maturin develop`` printed "Installed ... as editable" while leaving the
stale ``.so`` in place -- a success message from the build tool is not
proof the artifact was replaced. Full narrative:
``docs/evidence/2026-07-27-stale-extension-gate.md``. Related
shared-venv staleness modes, including mode 4 (the same "Installed" lie):
``docs/evidence/2026-08-11-worktree-poisons-shared-venv.md``.

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

Design decision: content hashing, with mtime as the fallback
--------------------------------------------------------------------------
This section used to be titled "False-positive avoidance" and named a
limitation it declined to fix: ``git checkout``/clone resets every
tracked file's mtime to the checkout time, including ``.rs`` sources, so
a machine holding a perfectly valid build -- a restored ``.venv`` cache,
a wheel baked into a CI image, an artifact carried between jobs -- sees
every source as "newer" than the installed ``.so`` and is reported
STALE, which in this gate is *unconditionally fatal*. Fixing it "would
require content hashing or git-log timestamps, a materially heavier
check", so the gate instead assumed the build-after-checkout workflow.

That assumption is what blocks baking prebuilt Rust wheels into the CI
image (~77s of ``maturin develop`` per job, across 5-6 jobs), and it has
already cost this repo a gate: on 2026-07-28 an ``actions/cache`` restore
made ``check_domain_partition.py`` report a cached netlist STALE whose
sources had not changed at all (same sources, two CI runs, two verdicts;
see ``docs/evidence/2026-07-30-c27-net-annotation-stale-briefing.md``).

It is now fixed here too, with the shared mechanism that fixed the
netlist: ``scripts/_lib/freshness.py``. A successful build records a
SHA-256 digest of the exact source set described above beside the
installed artifact (``scripts/write_extension_stamps.py``); this gate
recomputes that digest over the sources as they are now and compares.
**When a stamp is present it is authoritative and mtimes are not
consulted at all.** When it is absent the mtime comparison runs exactly
as it did before -- a missing stamp means "installed by a path that
predates this mechanism", which is the normal state of every developer's
tree and of every artifact built before this landed. Failing closed
there would turn a latent improvement into an immediate outage for every
contributor, and the mtime check is exactly as good as it was yesterday.

Content hashing is *strictly stronger* than the mtime rule, not merely
more cache-tolerant. A source that is edited and then back-dated older
than the ``.so`` -- ``os.utime``, a restored backup, an rsync/tar that
preserves timestamps, a filesystem with coarse timestamp granularity --
passes the mtime comparison and fails the content comparison. That is a
case the old implementation got WRONG, not merely slowly, and there is a
test for exactly it (``TestContentStamp``).

Design decision: where the stamp lives (keyed on the .so's own bytes)
--------------------------------------------------------------------------
The netlist stamp sits beside its artifact so that whatever moves the
artifact -- ``actions/cache``, an image layer, an upload-artifact tarball
-- carries the stamp with it automatically. The same rule applies here,
and the only location that satisfies it is the install directory,
``.venv/lib/python3.12/site-packages/<module>/``, beside the very
``.so`` this gate already resolves and stats. Anywhere in the repo tree
is disqualified on its face: a checkout replaces the repo tree, and
surviving a checkout is the entire point.

That location survives the three transports that matter:

  - ``maturin develop`` -- the stamp is written immediately after the
    install it just performed, into the directory maturin wrote to.
  - an ``actions/cache`` restore of ``.venv`` -- tar carries the stamp
    out and back in beside the ``.so``, mtimes and all.
  - a container image layer with a prebuilt wheel baked into
    site-packages -- both files are copied in the same layer.

One transport does NOT preserve the pairing, and it is the reason the
stamp filename is not simply ``<artifact>.source-digest``: a wheel
reinstall (``uv sync``, ``uv pip install``) replaces the ``.so`` but,
because the stamp is not listed in the wheel's RECORD, leaves the old
stamp behind as an orphan describing a binary that is no longer there.
A stamp keyed only on the artifact's *filename* would then be believed
for a different binary. So the stamp is keyed on the artifact's own
content:

    <module>.cpython-312-darwin.so.<sha256-of-the-so[:16]>.source-digest

A replaced ``.so`` hashes differently, so no stamp is found for it and
the gate falls back to mtime -- which is the right answer for a
just-installed file. Writing a stamp prunes superseded siblings, so a
crate carries exactly one. Hashing the ``.so`` costs one pass over ~1 MB
per crate (temper_drc_rs.cpython-312-darwin.so is 1,118,544 bytes).

What a stamp still does not protect against: it records the inputs a
build *claimed*, so a build that produced a broken artifact and then
stamped it is believed, and a hand-edited stamp is believed. That is why
``write_extension_stamps.py`` refuses to stamp any crate this gate does
not already consider fresh -- running the writer can never launder a
stale artifact into a fresh one.

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

Design decision: symbols, because freshness is not the question anyone asks
--------------------------------------------------------------------------
Everything above answers "was this artifact rebuilt from these sources?".
That is not the question an agent asks before trusting a measurement, which
is "does this ``.so`` contain the function I am about to call?" -- and the
two answers came apart four separate times in one session, every time with
this gate green (AGENTS.md, "Measurement Instruments That Lie"):

  1. ``stale=0`` against a ``.so`` missing a function its own Rust source
     registers. Cost: ``is_hv_net("hb-gnd")`` read ``False`` where the
     rebuilt artifact reads ``True``, and an agent worked from that for
     hours.
  2. A plain ``cargo test`` on ``temper-orchestration`` compiles
     ``temper-geometry`` WITHOUT its ``python`` feature; the resulting
     artifact overwrites the shared ``target-shared`` copy every worktree
     links against, and maturin then reuses it and reports success.
  3. ``temper_geometry`` unimportable (no ``PyInit``) while the gate said
     fresh 10/10; ``make extensions`` did not fix it.
  4. Fresh 10/10 AND all ten modules importing cleanly, while
     ``temper_design_bundle_python`` lacked
     ``resolve_insulation_declaration``. Found only because someone
     happened to call the missing function.

(3) grew the ``PyInit`` byte scan below in #1132. (1), (2) and (4) need the
artifact's actual symbol table compared against what its Rust source
registers, which is what ``scripts/_lib/pyo3_symbols.py`` derives and
``check_symbols`` below enforces. The expected set is DERIVED from the
``#[pymodule]`` registration walk on every run -- a checked-in list would be
the same defect one level up and would go stale exactly the way the
timestamps did.

Two states come out of it:

  SYMBOLS   -- the module imports, and ``dir()`` is missing at least one
               name its own source registers. Always fatal: a
               present-but-incomplete module is precisely the shape that
               produced a wrong number nobody questioned.
  FEATURE-GATE -- the artifact has no module init function at all AND the
               crate builds its pyo3 surface behind a Cargo feature. This
               is case (2), named rather than folded into a generic
               "unloadable", because it is the failure that poisons every
               worktree on the host at once and its remedy is different
               from (and larger than) "rebuild".

What the symbol check CANNOT see, stated so nobody assumes otherwise
--------------------------------------------------------------------
  - **A changed function BODY.** Same name, same arity, different answer.
    Only the freshness half (stamp/mtime) can see that, which is exactly
    why the timestamp check is added to rather than replaced.
  - **A changed SIGNATURE.** ``dir()`` reports a name, not its arity or
    types; pyo3 does not reliably publish ``__text_signature__`` for these
    builds, so an argument added in Rust and absent from the artifact is
    invisible here. It surfaces as a ``TypeError`` at call time, loudly,
    which is the failure mode this gate is least worried about.
  - **Methods on a registered ``#[pyclass]``.** The class is checked for
    presence; its ``#[pymethods]`` are not. A class that gained a method
    in Rust and lost it in the artifact still passes.
  - **A poisoned SHARED target directory that has not been installed
    yet.** This gate only ever inspects what is installed in the current
    environment. ``target-shared`` can be holding a feature-less
    ``temper-geometry`` for every other worktree on the host, and until
    someone's ``maturin develop`` copies it into a ``.venv`` nothing here
    can know. That is a property of the machine, not of this environment.
  - **Whether the ``.so`` was built from THIS repo at all.** The content
    stamp answers that only when a stamp is present.
  - **Registrations whose name is computed at runtime** (``m.add(name,
    ...)`` with a non-literal). They are skipped, not guessed.

Anti-vacuous-truth backstop (always fatal, regardless of the flag above):
zero crates discovered, any crate whose own freshness could not be
determined (e.g. its ``src/`` directory vanished), or any crate whose
expected-symbol set comes out EMPTY (every crate here is a pyo3 cdylib; a
crate that registers nothing means the extractor broke, not that the crate
is trivially correct) is a TOOL ERROR, never folded into "0 violations".

Exit codes:
  0 - PASSED (or WARN on missing-but-not-required): every checked crate
      is fresh and exports every symbol it registers, or the only issues
      are MISSING crates and TEMPER_REQUIRE_FRESH_EXTENSIONS is not set.
  3 - VIOLATION: at least one crate's installed extension module is
      STALE, UNLOADABLE, FEATURE-GATE poisoned, missing registered
      SYMBOLS, or (when TEMPER_REQUIRE_FRESH_EXTENSIONS is set) MISSING.
  5 - GATE ERROR: zero crates discovered, a per-crate freshness
      computation failed, or a crate yielded no expected symbols -- never
      conflated with "0 violations".

Usage:
  uv run python scripts/check_stale_extensions.py
  TEMPER_REQUIRE_FRESH_EXTENSIONS=1 uv run python scripts/check_stale_extensions.py

Build side (writes the stamps this gate reads):
  uv run python scripts/write_extension_stamps.py
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.freshness import (  # noqa: E402
    STAMP_SUFFIX,
    compute_inputs_digest,
    read_stamp,
    stamp_path_for,
)
from _lib.github_summary import get_github_summary_path  # noqa: E402
from _lib.pyo3_symbols import (  # noqa: E402
    Extraction,
    extract_expected_symbols,
    load_crate_toml,
)
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


def crate_source_files(crate: Crate) -> list[Path]:
    """Every file that participates in building this crate's extension.

    The crate's own Cargo.toml/pyproject.toml/build.rs/src/**/*.rs, plus
    the same set (minus pyproject.toml) recursively for every local path
    dependency. This is the single definition of "this crate's source
    files": both the mtime comparison and the content digest are derived
    from it, so the two can never disagree about *what* they measured.
    Raises GateError if no source files are found at all (fail closed --
    see module docstring).
    """
    visited: set[Path] = set()
    found: list[Path] = []

    def visit(root: Path, *, include_pyproject: bool) -> None:
        root = root.resolve()
        if root in visited or not root.is_dir():
            return
        visited.add(root)

        cargo_toml = root / "Cargo.toml"
        if cargo_toml.is_file():
            found.append(cargo_toml)
        if include_pyproject:
            pyproject = root / "pyproject.toml"
            if pyproject.is_file():
                found.append(pyproject)
        build_rs = root / "build.rs"
        if build_rs.is_file():
            found.append(build_rs)
        src_dir = root / "src"
        if src_dir.is_dir():
            found.extend(f for f in src_dir.rglob("*.rs") if f.is_file())

        cdata = _load_toml(cargo_toml) if cargo_toml.is_file() else {}
        for dep_root in _local_path_deps(cdata, root):
            visit(dep_root, include_pyproject=False)

    visit(crate.root, include_pyproject=True)

    if not found:
        raise GateError(
            f"{crate.name}: no source files found under {crate.root} "
            "(Cargo.toml/pyproject.toml/build.rs/src/*.rs) -- cannot "
            "determine freshness; failing closed rather than skipping"
        )
    return sorted(found)


def newest_source_mtime(crate: Crate) -> tuple[float, Path]:
    """Return (mtime, path) of the newest of ``crate_source_files``.

    The mtime half of the freshness question -- used only when no build
    stamp is present (see module docstring "Design decision: content
    hashing, with mtime as the fallback").
    """
    newest_mtime = -1.0
    newest_path: Path | None = None

    for f in crate_source_files(crate):
        try:
            m = f.stat().st_mtime
        except OSError:
            continue
        if m > newest_mtime:
            newest_mtime = m
            newest_path = f

    if newest_path is None:
        raise GateError(
            f"{crate.name}: every source file under {crate.root} failed to "
            "stat -- cannot determine freshness; failing closed rather "
            "than skipping"
        )
    return newest_mtime, newest_path


def digest_root(source_files: list[Path]) -> Path:
    """Directory the digest's relative paths are taken from.

    ``compute_inputs_digest`` records each input's path relative to a root
    so that a digest computed in a container matches one computed on a
    developer's machine. The deepest common ancestor of the source set is
    that root: it is derived from the files themselves, so writer and gate
    always agree, it is identical on any machine with the same repo layout,
    and -- unlike hard-coding the repo root -- it cannot raise for a path
    dependency that resolves outside the repository.
    """
    return Path(os.path.commonpath([str(p.parent) for p in source_files]))


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


#: A CPython extension module is only importable if it exports an init
#: function named for the module. pyo3 emits ``PyInit_<name>`` (stable ABI
#: era) or ``PyModExport_<name>`` (newer multi-phase export); maturin's own
#: "Couldn't find the symbol" warning names both, so both are accepted here.
_INIT_SYMBOL_PREFIXES = ("PyInit_", "PyModExport_")

#: Cap on how much of an artifact is scanned for the init symbol. The symbol
#: lives in the dynamic symbol table, but reading the whole file and scanning
#: it is simpler and stays honest across ELF/Mach-O/PE without a parser. The
#: largest artifact in this repo is ~8 MB, so this reads everything in
#: practice; the cap only bounds the damage from a pathological file.
_SYMBOL_SCAN_MAX_BYTES = 128 << 20


def _exports_init_symbol(module_name: str, artifact: Path) -> bool | None:
    """Whether *artifact* exports an init function for *module_name*.

    Returns ``None`` when the question does not apply -- the artifact is not
    a native module (we fell back to the ``__init__.py`` wrapper because no
    ``.so``/``.pyd`` was found) or could not be read.

    Deliberately a byte scan, not an import: this gate must stay
    side-effect-free (see the module docstring's "resolving the actual
    compiled artifact" note -- ``find_spec`` is used precisely so that
    running the gate never executes module-level code). A byte scan answers
    "would this load?" without loading it, and inspects the same file the
    original incident's own ``strings`` check did.
    """
    if artifact.suffix not in {".so", ".pyd"}:
        return None
    try:
        blob = artifact.read_bytes()[:_SYMBOL_SCAN_MAX_BYTES]
    except OSError:
        return None
    return any(
        f"{prefix}{module_name}".encode() in blob for prefix in _INIT_SYMBOL_PREFIXES
    )


# ---------------------------------------------------------------------------
# Build stamps (content hashing) -- see module docstring for the two
# "Design decision" sections covering why these exist and where they live.
# ---------------------------------------------------------------------------

_ARTIFACT_KEY_CHARS = 16
_HASH_CHUNK = 1 << 20


def artifact_content_key(artifact: Path) -> str:
    """Short SHA-256 of the compiled artifact's own bytes.

    This is what binds a stamp to one specific binary rather than to a
    filename, so a wheel reinstall that swaps the ``.so`` underneath an
    orphaned stamp cannot inherit that stamp's claim.
    """
    digest = hashlib.sha256()
    with artifact.open("rb") as fh:
        while chunk := fh.read(_HASH_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()[:_ARTIFACT_KEY_CHARS]


def stamp_key_path(artifact: Path) -> Path:
    """The path ``_lib.freshness.stamp_path_for`` is keyed on for *artifact*.

    Not a file itself -- appending the artifact's content key here is what
    makes the resulting ``.source-digest`` filename artifact-specific.
    """
    return artifact.with_name(f"{artifact.name}.{artifact_content_key(artifact)}")


def stamp_file_for(artifact: Path) -> Path:
    """Full path of the stamp file that describes *artifact*."""
    return stamp_path_for(stamp_key_path(artifact))


def superseded_stamps(artifact: Path) -> list[Path]:
    """Stamps beside *artifact* that describe an earlier build of it.

    Pruned when a new stamp is written, so one crate carries one stamp.
    """
    current = stamp_file_for(artifact)
    pattern = f"{artifact.name}.*{STAMP_SUFFIX}"
    return sorted(p for p in artifact.parent.glob(pattern) if p != current and p.is_file())


def read_artifact_stamp(artifact: Path) -> str | None:
    """Digest recorded for exactly these artifact bytes, or None.

    None covers all of: no stamp (the normal pre-migration state), a
    stamp orphaned by a wheel reinstall, a corrupt or wrong-version
    stamp, and an unreadable artifact -- every one of which must fall
    back to the mtime comparison rather than fail.
    """
    try:
        key = stamp_key_path(artifact)
    except OSError:
        return None
    return read_stamp(key)


# ---------------------------------------------------------------------------
# Symbol verification -- see the module docstring's "Design decision: symbols"
# ---------------------------------------------------------------------------

#: Loads ONE built artifact in a child process and reports what it exposes.
#:
#: A child process, not an import here, for three reasons that are all real in
#: this repo: (a) this gate must stay side-effect-free in its own interpreter
#: -- ``find_spec`` is used everywhere above precisely so that running the gate
#: never executes module-level code; (b) a broken ``.so`` can abort or
#: segfault the process that dlopens it, and a gate that dies is worse than a
#: gate that reports; (c) loading ten unrelated Rust extensions into one
#: interpreter risks cross-module interference that has nothing to do with the
#: question being asked.
#:
#: The artifact is loaded BY PATH rather than by import name. Every crate here
#: ships maturin's mixed layout, whose ``__init__.py`` does ``from .<mod>
#: import *`` -- and ``import *`` silently drops any name starting with an
#: underscore. Loading the ``.so`` itself asks the artifact what it contains,
#: which is the question, instead of asking the wrapper what it chose to
#: re-export.
#:
#: Child modules attached with ``add_submodule`` are walked one level deep,
#: because that is where ``temper_design_bundle_python.board_contracts.Board``
#: and 19 other contract groups live.
_LOADER_SOURCE = r"""
import importlib.util, json, sys

name, path = sys.argv[1], sys.argv[2]
try:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"no loader for {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
except BaseException as exc:  # noqa: BLE001 -- reporting, not handling
    print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"}))
else:
    found = {}

    def walk(obj, prefix, depth):
        for attr in dir(obj):
            found[prefix + attr] = True
            if depth <= 0:
                continue
            child = getattr(obj, attr, None)
            if type(child).__name__ == "module":
                walk(child, prefix + attr + ".", depth - 1)

    walk(module, "", 1)
    print(json.dumps({"ok": True, "symbols": sorted(found)}))
"""

#: A child that has not answered in this long is not going to. Generous:
#: the slowest artifact here loads in well under a second.
_LOADER_TIMEOUT_S = 120


@dataclass(frozen=True)
class LoadResult:
    ok: bool
    symbols: frozenset[str] = frozenset()
    error: str = ""


def load_artifact_symbols(module_name: str, artifact: Path, cwd: Path) -> LoadResult:
    """Names the built *artifact* actually exposes, via a child process."""
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _LOADER_SOURCE, module_name, str(artifact)],
            capture_output=True,
            text=True,
            cwd=str(cwd),
            timeout=_LOADER_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return LoadResult(False, error=f"could not run the loader subprocess: {exc!r}")

    if proc.returncode < 0:
        return LoadResult(
            False,
            error=(
                f"loading the artifact killed the interpreter with signal "
                f"{-proc.returncode} -- the .so is not merely stale, it is corrupt"
            ),
        )
    try:
        payload = json.loads(proc.stdout)
    except (ValueError, TypeError):
        tail = (proc.stderr or proc.stdout or "").strip()[-400:]
        return LoadResult(False, error=f"loader produced no verdict (exit {proc.returncode}): {tail}")
    if not payload.get("ok"):
        return LoadResult(False, error=str(payload.get("error", "unknown import failure")))
    return LoadResult(True, symbols=frozenset(payload.get("symbols", ())))


def _gates_python_behind_a_feature(pyproject: dict) -> bool:
    """Does this crate's pyo3 surface sit behind a Cargo feature?

    True for every crate in this repo: ``[tool.maturin] features`` names a
    feature of the crate itself (``python``). That is exactly the
    precondition for failure mode (2) -- a build of the same crate WITHOUT
    that feature produces a cdylib with no module init at all, and cargo will
    happily leave it in the shared target directory for maturin to reuse.
    """
    features = pyproject.get("tool", {}).get("maturin", {}).get("features", [])
    return any("/" not in f for f in features)


def _feature_gate_remedy(crate: Crate) -> str:
    """The recovery that actually works, spelled out.

    ``cargo clean -p`` alone is NOT it, and an agent lost hours discovering
    that: cleaning the shared ``target-shared`` and rebuilding there races
    every other worktree on the host, any one of which re-poisons the entry
    with a plain ``cargo test``/``cargo check`` mid-rebuild. The rebuild has
    to happen somewhere nobody else writes.
    """
    return (
        f"REMEDY (both steps -- the first alone is not enough):\n"
        f"      1. cargo clean -p {crate.name}   # in the SHARED target dir, to\n"
        f"         evict the poisoned entry:\n"
        f"           CARGO_TARGET_DIR=\"$(dirname \"$(git rev-parse "
        f"--path-format=absolute --git-common-dir)\")/target-shared\" \\\n"
        f"             cargo clean -p {crate.name}\n"
        f"      2. rebuild under a PRIVATE target dir, so a concurrent "
        f"`cargo test`\n"
        f"         or `cargo check` from another worktree cannot re-poison the\n"
        f"         artifact between the clean and the install:\n"
        f"           CARGO_TARGET_DIR=\"$(mktemp -d)\" uv run --no-sync maturin "
        f"develop \\\n"
        f"             --release --manifest-path {crate.cargo_toml}\n"
        f"      Confirm a real `Compiling {crate.name}` line appears; a build that\n"
        f"      prints only `Finished ... in 0.0Xs` reused the poisoned artifact.\n"
        f"      Then stop re-creating it: run crate tests as `cargo test -p "
        f"{crate.name} --features python`\n"
        f"      (or under a private CARGO_TARGET_DIR). A plain `cargo test` on any\n"
        f"      crate that depends on {crate.name} compiles it WITHOUT `python` and\n"
        f"      overwrites the shared copy every worktree on this host links against."
    )


@dataclass
class SymbolVerdict:
    """Outcome of comparing a built artifact against its Rust source."""

    expected: int = 0
    inferred: int = 0
    unresolved_cfgs: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    origins: dict[str, str] = field(default_factory=dict)

    def summary(self) -> str:
        parts = [f"{self.expected} registered symbol(s) checked"]
        if self.inferred:
            parts.append(f"{self.inferred} name(s) inferred from macro-generated items")
        if self.unresolved_cfgs:
            parts.append(f"{len(self.unresolved_cfgs)} undecidable cfg(s) not demanded")
        return "; ".join(parts)


def check_symbols(crate: Crate, artifact: Path, sources: list[Path], repo_root: Path):
    """Compare *artifact*'s real symbol table against what its source registers.

    Returns ``(verdict, load_result, extraction)``. Raises :class:`GateError`
    when the expected set comes out empty -- see the anti-vacuity backstop in
    the module docstring.
    """
    extraction: Extraction = extract_expected_symbols(
        crate.root,
        sources,
        load_crate_toml(crate.pyproject),
        load_crate_toml(crate.cargo_toml),
        crate.module_name,
    )
    if not extraction.symbols:
        raise GateError(
            f"{crate.name}: derived ZERO expected symbols from "
            f"{extraction.files_scanned} Rust source file(s)"
            + (
                f" (entry point `{extraction.entry_point}`)"
                if extraction.entry_point
                else " -- no `#[pymodule]` function was found at all"
            )
            + ". Every crate this gate discovers is a pyo3 cdylib, so an empty "
            "expectation means scripts/_lib/pyo3_symbols.py stopped "
            "understanding this crate's source, not that the crate exports "
            "nothing. Failing closed: a symbol check with nothing in it is "
            "the vacuous pass this gate exists to prevent."
        )

    load = load_artifact_symbols(crate.module_name, artifact, repo_root)
    verdict = SymbolVerdict(
        expected=len(extraction.symbols),
        inferred=extraction.inferred_count,
        unresolved_cfgs=tuple(extraction.unresolved_cfgs),
    )
    if not load.ok:
        return verdict, load, extraction

    missing = sorted(n for n in extraction.symbols if n not in load.symbols)
    verdict.missing = tuple(missing)
    verdict.origins = {n: extraction.symbols[n].origin for n in missing}
    return verdict, load, extraction


@dataclass
class ModuleStatus:
    state: str  # "fresh" | "stale" | "symbols" | "feature-gate" | "unloadable" | "missing" | "error"
    detail: str
    artifact: Path | None = None
    artifact_mtime: float | None = None
    method: str = "mtime"  # "content" once a stamp decided it
    symbols: SymbolVerdict | None = None


def _fmt(ts: float) -> str:
    return datetime.fromtimestamp(ts).isoformat(timespec="seconds")


def check_module(crate: Crate, repo_root: Path | None = None) -> ModuleStatus:
    """Never trusts any build tool's stdout (see module docstring) --
    independently locates and stats the real installed artifact, then asks
    the artifact itself which symbols it contains.
    """
    repo_root = repo_root or find_repo_root()
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

    # Checked BEFORE freshness, because freshness is meaningless for an
    # artifact that cannot load: a `.so` rebuilt from a cargo cache that
    # holds a non-`python`-feature build carries a brand-new mtime and a
    # matching content hash, so every freshness path below reports it OK
    # while `import <module>` raises "dynamic module does not define module
    # export function". Measured 2026-08-13: this gate reported
    # "PASSED -- 10/10 extension module(s) fresh" against a temper_geometry
    # artifact that could not be imported at all, and 21 of 32 apparent test
    # failures were that one broken module. Freshness answers "was it
    # rebuilt?"; this answers "is what got installed loadable?".
    if _exports_init_symbol(crate.module_name, artifact) is False:
        gated = _gates_python_behind_a_feature(load_crate_toml(crate.pyproject))
        return ModuleStatus(
            "feature-gate" if gated else "unloadable",
            f"{crate.module_name}: installed artifact {artifact} exports no "
            f"PyInit_{crate.module_name} -- it cannot be imported, regardless "
            f"of how recently it was built."
            + (
                f"\n      DIAGNOSIS: FEATURE-GATE POISONED TARGET DIR. "
                f"{crate.name} builds its pyo3 surface behind a Cargo feature "
                f"(`[tool.maturin] features` in {crate.pyproject.name}), and this "
                f"artifact was compiled WITHOUT it -- so the `#[pymodule]` never "
                f"existed in this binary. Nothing about the build was reported as "
                f"failing: cargo left the feature-less cdylib in the shared target "
                f"directory and maturin reused it.\n      "
                + _feature_gate_remedy(crate)
                if gated
                else " The crate declares no Cargo feature for its pyo3 surface, so "
                "this is not the feature-gate case -- the artifact is malformed or "
                "was built for a different module name. Rebuild with `uv run "
                f"--no-sync maturin develop --release --manifest-path "
                f"{crate.cargo_toml}` and read the build output."
            ),
            artifact=artifact,
        )

    try:
        sources = crate_source_files(crate)
    except GateError as exc:
        return ModuleStatus("error", str(exc))

    artifact_mtime = artifact.stat().st_mtime
    freshness = _freshness_status(crate, artifact, sources, artifact_mtime)
    if freshness.state == "error":
        return freshness

    # The symbol comparison runs even when freshness is satisfied -- that is
    # the whole point. It is ADDITIVE to the timestamp/stamp check above, not
    # a replacement: source-newer-than-artifact is a real condition symbols
    # cannot see (a rebuild that changes only a function BODY leaves the
    # symbol set identical), and a missing symbol is a real condition
    # timestamps cannot see (cases 1 and 4 in the module docstring).
    try:
        verdict, load, _extraction = check_symbols(crate, artifact, sources, repo_root)
    except GateError as exc:
        return ModuleStatus(
            "error",
            str(exc),
            artifact=artifact,
            artifact_mtime=artifact_mtime,
            method=freshness.method,
        )

    if not load.ok:
        gated = _gates_python_behind_a_feature(load_crate_toml(crate.pyproject))
        looks_feature_gated = gated and "does not define module export function" in load.error
        return ModuleStatus(
            "feature-gate" if looks_feature_gated else "unloadable",
            f"{crate.module_name}: installed artifact {artifact} could not be "
            f"loaded -- {load.error}"
            + (
                f"\n      DIAGNOSIS: FEATURE-GATE POISONED TARGET DIR. The binary "
                f"has no module init function, which is what a build of "
                f"{crate.name} WITHOUT its `python` feature produces.\n      "
                + _feature_gate_remedy(crate)
                if looks_feature_gated
                else f"\n      Rebuild with `uv run --no-sync maturin develop "
                f"--release --manifest-path {crate.cargo_toml}` and read the build "
                f"output; freshness ({freshness.state}) is not the issue here."
            ),
            artifact=artifact,
            artifact_mtime=artifact_mtime,
            method=freshness.method,
            symbols=verdict,
        )

    freshness.symbols = verdict
    if verdict.missing:
        shown = ", ".join(
            f"{name} (registered at {verdict.origins.get(name, '?')})"
            for name in verdict.missing[:10]
        )
        overflow = "" if len(verdict.missing) <= 10 else f", and {len(verdict.missing) - 10} more"
        detail = (
            f"{crate.module_name}: installed artifact {artifact} is MISSING "
            f"{len(verdict.missing)} of the {verdict.expected} symbol(s) its own "
            f"Rust source registers -- {shown}{overflow}."
            f"\n      The freshness check said {freshness.state.upper()} for this "
            f"same artifact, which is exactly the disagreement this check exists "
            f"to surface: a timestamp says a file was written, not what is in it."
            f"\n      REMEDY: rebuild the crate and confirm a real `Compiling "
            f"{crate.name}` line appears --\n"
            f"        CARGO_TARGET_DIR=\"$(mktemp -d)\" uv run --no-sync maturin "
            f"develop --release --manifest-path {crate.cargo_toml}\n"
            f"      A private CARGO_TARGET_DIR is deliberate: rebuilding into the "
            f"shared target-shared can reuse (or re-acquire) the very artifact that "
            f"is wrong. If the symbols are still absent after a real recompile, the "
            f"registration is behind a Cargo feature this build does not enable."
        )
        if freshness.state == "stale":
            # Do not hide the staleness -- it is the same rebuild either way,
            # but the two findings are independent evidence and both are said.
            freshness.detail = f"{freshness.detail}\n      ALSO: {detail}"
            return freshness
        return ModuleStatus(
            "symbols",
            detail,
            artifact=artifact,
            artifact_mtime=artifact_mtime,
            method=freshness.method,
            symbols=verdict,
        )

    if freshness.state == "fresh":
        freshness.detail = f"{freshness.detail}; {verdict.summary()}, all present"
    return freshness


def _freshness_status(
    crate: Crate, artifact: Path, sources: list[Path], artifact_mtime: float
) -> ModuleStatus:
    """Was this artifact built from these sources? (stamp, else mtime)"""
    # Content comparison when a stamp is present: authoritative, mtimes
    # never consulted. That is what lets a cached/baked artifact whose
    # sources were merely re-checked-out be trusted.
    recorded = read_artifact_stamp(artifact)
    if recorded is not None:
        try:
            current = compute_inputs_digest(sources, digest_root(sources))
        except (OSError, ValueError) as exc:
            return ModuleStatus(
                "error",
                f"{crate.name}: a build stamp is present for {artifact} but its "
                f"source digest could not be recomputed ({exc!r}) -- refusing to "
                "guess; this is a tool error, not a clean pass",
                artifact=artifact,
                artifact_mtime=artifact_mtime,
                method="content",
            )
        if current == recorded:
            return ModuleStatus(
                "fresh",
                f"{crate.module_name}: {artifact} matches its build stamp "
                f"(digest {current[:12]}… over {len(sources)} source file(s); "
                "mtimes not consulted)",
                artifact=artifact,
                artifact_mtime=artifact_mtime,
                method="content",
            )
        return ModuleStatus(
            "stale",
            f"{crate.module_name}: installed artifact {artifact} "
            f"(built {_fmt(artifact_mtime)}) was built from different sources -- "
            f"current digest {current[:12]}… does not match its build stamp "
            f"{recorded[:12]}… over {len(sources)} source file(s) -- "
            f"rebuild with `uv run maturin develop --release --manifest-path "
            f"{crate.cargo_toml}`",
            artifact=artifact,
            artifact_mtime=artifact_mtime,
            method="content",
        )

    try:
        newest_mtime, newest_source = newest_source_mtime(crate)
    except GateError as exc:
        return ModuleStatus("error", str(exc))

    if artifact_mtime < newest_mtime:
        age_days = (newest_mtime - artifact_mtime) / 86400.0
        return ModuleStatus(
            "stale",
            f"{crate.module_name}: installed artifact {artifact} "
            f"(built {_fmt(artifact_mtime)}) predates {newest_source} "
            f"(modified {_fmt(newest_mtime)}, {age_days:.2f} day(s) newer) -- "
            "no build stamp was present, so the mtime comparison was used -- "
            f"rebuild with `uv run maturin develop --release --manifest-path "
            f"{crate.cargo_toml}`",
            artifact=artifact,
            artifact_mtime=artifact_mtime,
        )

    return ModuleStatus(
        "fresh",
        f"{crate.module_name}: {artifact} (built {_fmt(artifact_mtime)}) is fresh "
        "(no build stamp; mtime comparison)",
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
    results = [CrateResult(crate=c, status=check_module(c, repo_root)) for c in crates]
    return Report(crates_discovered=len(crates), results=results)


def _required() -> bool:
    return os.environ.get("TEMPER_REQUIRE_FRESH_EXTENSIONS", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


_MARKER = {
    "fresh": "OK",
    "stale": "STALE",
    "symbols": "MISSING-SYMBOLS",
    "feature-gate": "FEATURE-GATE",
    "unloadable": "UNLOADABLE",
    "missing": "MISSING",
    "error": "ERROR",
}

#: Every state that is a violation regardless of
#: TEMPER_REQUIRE_FRESH_EXTENSIONS. "built, but wrong" is never a legitimate
#: local state the way "not built here" is.
_ALWAYS_FATAL_STATES = ("stale", "symbols", "feature-gate", "unloadable")


def group_by_state(report: Report) -> dict[str, list[CrateResult]]:
    by_state: dict[str, list[CrateResult]] = {}
    for r in report.results:
        by_state.setdefault(r.status.state, []).append(r)
    return by_state


def decide_exit_code(report: Report, required: bool) -> int:
    """Pure decision function, isolated from I/O for unit testing.

    tool errors > "built, but wrong" (always fatal) > MISSING (fatal only
    if *required*) > PASSED. See module docstring "The 'is staleness fatal
    here' signal" for why STALE is never gated by *required*; the same
    reasoning covers MISSING-SYMBOLS, FEATURE-GATE and UNLOADABLE. An
    artifact that exports no init function cannot be imported by anyone, and
    one that is missing a registered symbol produces a wrong ANSWER rather
    than an error, so there is no environment in which tolerating either
    yields a meaningful test result -- they produce phantom failures instead
    (21 of 32, measured 2026-08-13). MISSING is gated by *required* because
    "not built here" is a legitimate local state; "built, but wrong" is not.
    """
    by_state = group_by_state(report)
    if by_state.get("error"):
        return EXIT_TOOL_ERROR
    if any(by_state.get(state) for state in _ALWAYS_FATAL_STATES):
        return EXIT_VIOLATION
    if by_state.get("missing") and required:
        return EXIT_VIOLATION
    return EXIT_OK


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root", type=Path, default=None, help="Override repo root (mainly for tests)."
    )
    parser.add_argument(
        "--list-crates",
        action="store_true",
        help=(
            "Print '<crate-name>\\t<Cargo.toml path>' for every discovered pyo3/maturin "
            "crate (one per line, tab-separated) and exit -- no freshness check is run. "
            "Machine-readable consumer of the same discover_crates() source of truth used "
            "by the gate itself, so a caller (e.g. `make extensions`) never hardcodes a "
            "crate list that can drift from this scan. Does not honor "
            "TEMPER_REQUIRE_FRESH_EXTENSIONS and never affects the gate's own exit codes."
        ),
    )
    args = parser.parse_args()
    repo_root = args.repo_root or find_repo_root()

    if args.list_crates:
        try:
            crates = discover_crates(repo_root)
        except OSError as exc:
            print(f"failed to discover crates under {repo_root}: {exc}", file=sys.stderr)
            return EXIT_TOOL_ERROR
        for crate in crates:
            print(f"{crate.name}\t{crate.cargo_toml}")
        return EXIT_OK

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
    symbol_gaps = by_state.get("symbols", [])
    feature_gated = by_state.get("feature-gate", [])
    missing = by_state.get("missing", [])
    unloadable = by_state.get("unloadable", [])
    errors = by_state.get("error", [])

    checked = [r for r in report.results if r.status.symbols is not None]
    symbols_checked = sum(r.status.symbols.expected for r in checked)
    inferred = sum(r.status.symbols.inferred for r in checked)
    undecidable = sum(len(r.status.symbols.unresolved_cfgs) for r in checked)

    print(
        f"Stale-extension gate -- {report.crates_discovered} pyo3/maturin "
        f"crate(s) discovered under packages/, {len(report.results)} checked "
        "(every discovered crate is checked; the denominator is never a subset)."
    )
    by_content = [r for r in report.results if r.status.method == "content"]
    print(
        f"  fresh={len(fresh)} stale={len(stale)} missing-symbols={len(symbol_gaps)} "
        f"feature-gate={len(feature_gated)} unloadable={len(unloadable)} "
        f"missing={len(missing)} tool-errors={len(errors)}  "
        f"TEMPER_REQUIRE_FRESH_EXTENSIONS={'1 (strict)' if required else '0 (lenient)'}"
    )
    print(
        f"  decided by content hash: {len(by_content)}; by mtime fallback "
        f"(no build stamp): "
        f"{len(report.results) - len(by_content) - len(missing) - len(unloadable) - len(feature_gated)}"
    )
    # Printed unconditionally, including on a clean run: a symbol check whose
    # denominator quietly went to zero would otherwise look exactly like a
    # symbol check that passed.
    print(
        f"  symbols compared against Rust source: {symbols_checked} registered "
        f"name(s) across {len(checked)} loadable artifact(s)"
        + (f"; {inferred} name(s) inferred from macro-generated items" if inferred else "")
        + (
            f"; {undecidable} cfg predicate(s) undecidable and therefore NOT demanded"
            if undecidable
            else ""
        )
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
                f"- Missing registered symbols: {len(symbol_gaps)}\n"
                f"- Feature-gate poisoned (no module init): {len(feature_gated)}\n"
                f"- Unloadable: {len(unloadable)}\n"
                f"- Missing: {len(missing)}\n"
                f"- Tool errors: {len(errors)}\n"
                f"- Decided by content hash: {len(by_content)}\n"
                f"- Registered symbols compared: {symbols_checked}\n"
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
        reasons = [
            f"{len(stale)} stale extension(s)",
            *([f"{len(symbol_gaps)} extension(s) missing registered symbols"] if symbol_gaps else []),
            *([f"{len(feature_gated)} feature-gate poisoned extension(s)"] if feature_gated else []),
            *([f"{len(unloadable)} unloadable extension(s)"] if unloadable else []),
            *(
                [f"{len(missing)} missing extension(s) (required)"]
                if required and missing
                else []
            ),
        ]
        print("\nFAILED -- " + ", ".join(reasons) + ".", file=sys.stderr)
    else:
        if missing:
            print(
                f"\nWARN -- {len(missing)} extension module(s) not installed; not "
                "failing because TEMPER_REQUIRE_FRESH_EXTENSIONS is unset (local "
                "dev: not every accelerator is assumed built). CI sets this."
            )
        print(
            f"\nPASSED -- {len(fresh)}/{report.crates_discovered} extension module(s) "
            f"fresh, and every one of {symbols_checked} registered symbol(s) is "
            f"present in the artifact that claims it."
        )

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
