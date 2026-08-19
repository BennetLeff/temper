"""Where cargo builds land, and why the pyo3 extension builds land elsewhere.

THE INCIDENT THIS PARTITION CLOSES (measured 2026-08-18)
--------------------------------------------------------
A cargo target directory holds exactly ONE uplifted artifact per (crate,
profile): ``<target>/release/lib<crate>.so``. That path is NOT keyed on the
feature set the artifact was built with. For a pyo3 crate this is fatal,
because two feature sets produce two incompatible binaries at that one path:

  * ``--features python,pyo3/extension-module`` (what maturin builds) --
    exports ``PyInit_<module>``, links no libpython, importable by CPython.
  * no features (what a plain ``cargo build`` builds) -- exports no
    ``PyInit_``, and is not an importable extension module at all.

Measured on this repo's own ``temper-geometry``, one target dir, alternating:

    after maturin build          5,966,640 bytes   PyInit_temper_geometry x2
    after `cargo build`            527,152 bytes   PyInit_temper_geometry x0

and back again. In the steady state -- both feature variants already cached,
which is the normal condition of a build cache shared by ~90 worktrees --
each flip costs **~95 ms and prints no `Compiling` line at all**, only
``Finished `release` profile [optimized] target(s) in 0.05s``. Cargo is not
recompiling; it is re-hardlinking a cached artifact of the other feature set
over the shared uplift path. ``release/lib<crate>.so`` and
``release/deps/lib<crate>.so`` are the same inode.

That is the whole mechanism behind "maturin reported success while installing
a `.so` with no PyInit_": nothing is corrupt and no build failed. One agent's
``cargo build`` silently swapped the artifact another agent's maturin was
about to copy into site-packages.

A NOTE ON WHAT DOES *NOT* CAUSE IT
----------------------------------
AGENTS.md attributed this to ``cargo check``/clippy. Measured directly, those
are innocent: ``cargo check``, ``cargo clippy``, ``cargo clippy
--all-targets`` and ``cargo test`` all left the uplifted ``.so`` untouched
(they produce ``.rmeta``/test binaries, not a cdylib). Only ``cargo build``
without the extension-module features flips it. This matters operationally:
telling agents to avoid ``cargo check`` would cost them the cheap command and
leave the expensive one -- ``cargo build`` -- still poisoning the cache.

THE PARTITION
-------------
Extension-module builds get their own shared target directory, suffixed
``-pyext``. Both directories remain shared across every worktree, so the
cross-worktree cache -- the thing three disk-exhaustion incidents were paid
for -- is fully preserved; what is no longer shared is the *uplift path
between two incompatible feature sets*, which was never a cache benefit, only
a collision. The cost is that dependencies common to both configurations
compile twice, once per directory.

Three mechanisms must agree on this derivation, because each covers a path
the others do not:

  1. ``scripts/install_cargo_target_dir_guard.py``'s ``cargo`` PATH wrapper --
     covers direct ``cargo``/``maturin`` calls in any shell, which is how
     agents actually invoke things (a fresh shell per tool call, so nothing
     sourced survives).
  2. The ``Makefile``'s ``CARGO_TARGET_DIR`` / ``CARGO_TARGET_DIR_PYEXT`` --
     covers ``make`` recipes and CI, where the wrapper is not installed.
  3. This module -- covers the gates that must know where to look.

``scripts/tests/test_cargo_target_partition.py`` asserts all three agree, so
the duplication cannot drift silently.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

#: Suffix appended to the shared target dir for extension-module builds.
#: Changing this requires changing the Makefile and the wrapper in the same
#: commit; the partition test fails otherwise.
EXTENSION_TARGET_SUFFIX = "-pyext"

#: Basename of the shared target directory, matching `.cargo/config.toml`'s
#: `build.target-dir` so the two never disagree about the non-extension case.
SHARED_TARGET_BASENAME = "target-shared"

#: The cargo feature that discriminates an extension-module build. Every one
#: of this repo's 10 pyo3 crates declares it in `[tool.maturin] features`
#: (verified 2026-08-18), and maturin passes it through to cargo on the
#: command line -- captured live from maturin 1.9:
#:
#:   cargo rustc --profile release --features python \
#:        --features pyo3/extension-module --message-format json-... \
#:        --manifest-path .../Cargo.toml --lib --crate-type cdylib
#:
#: It is the right discriminator on the merits, not merely a convenient
#: string: `extension-module` is exactly the flag that makes the cdylib omit
#: libpython linkage and export `PyInit_`, i.e. the flag that makes the two
#: artifacts incompatible in the first place.
EXTENSION_MODULE_FEATURE = "pyo3/extension-module"


def canonical_repo_root(cwd: Path | None = None) -> Path:
    """The MAIN checkout's root, identical from every worktree.

    ``--git-common-dir`` resolves to the main checkout's ``.git`` regardless
    of which worktree asks, which is what makes one shared cache reachable
    from all ~90 of them. Deliberately not derived from ``__file__``: this
    module is read from whichever worktree is running, and using that
    worktree's path would hand each one a private cache -- the exact bug the
    shared cache exists to prevent.
    """
    out = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(cwd) if cwd else None,
    )
    return Path(out.stdout.strip()).parent


def shared_target_dir(repo_root: Path) -> Path:
    """Target dir for ordinary cargo work (build/check/clippy/test)."""
    return repo_root / SHARED_TARGET_BASENAME


def extension_target_dir(repo_root: Path) -> Path:
    """Target dir for maturin/pyo3 extension-module builds."""
    return repo_root / (SHARED_TARGET_BASENAME + EXTENSION_TARGET_SUFFIX)


def is_extension_module_build(argv: list[str]) -> bool:
    """Does this cargo argv enable the extension-module feature?

    Matches maturin's ``--features pyo3/extension-module`` in both spellings
    cargo accepts (separate argument or ``--features=...``) and inside a
    comma-separated feature list, since cargo treats all three identically
    and maturin's exact form is a detail of maturin's version.
    """
    for i, arg in enumerate(argv):
        value = None
        if arg == "--features" and i + 1 < len(argv):
            value = argv[i + 1]
        elif arg.startswith("--features="):
            value = arg.split("=", 1)[1]
        if value and EXTENSION_MODULE_FEATURE in value.replace(",", " ").split():
            return True
    return False


def target_dir_for(argv: list[str], repo_root: Path) -> Path:
    """The directory *argv* should build into, given the partition."""
    if is_extension_module_build(argv):
        return extension_target_dir(repo_root)
    return shared_target_dir(repo_root)


def with_extension_suffix(target_dir: Path) -> Path:
    """Apply the ``-pyext`` suffix to *target_dir*, idempotently.

    Idempotence is load-bearing rather than defensive tidiness: the Makefile
    exports an already-suffixed ``CARGO_TARGET_DIR`` for its maturin recipes
    AND the wrapper sees that same value on the cargo call maturin spawns.
    Without this, the two correct mechanisms would compose into
    ``target-shared-pyext-pyext``.
    """
    if target_dir.name.endswith(EXTENSION_TARGET_SUFFIX):
        return target_dir
    return target_dir.with_name(target_dir.name + EXTENSION_TARGET_SUFFIX)
