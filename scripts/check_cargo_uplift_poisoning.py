#!/usr/bin/env python3
"""Is the shared cargo cache currently holding a PyInit-less cdylib?

WHAT THIS CATCHES, AND WHY IT IS NOT check_stale_extensions.py
--------------------------------------------------------------
``check_stale_extensions.py`` answers "is what got INSTALLED loadable?" -- it
inspects ``.venv/.../site-packages``, after the fact. By the time it fires, a
build has already reported success, an agent has already run a test suite,
and (2026-08-13) 21 of 32 apparent failures were one broken module.

This gate answers the prior question: **is the cargo cache the next build
will draw from already poisoned?** It inspects the shared target directory,
before maturin copies anything anywhere. Same symbol, opposite end of the
pipeline -- and this end is where the fix (``cargo clean -p``) applies.

Both are needed. The installed artifact can be broken while the cache is
clean (someone rebuilt the cache afterwards), and the cache can be poisoned
while the installed artifact is fine (nobody has run maturin since). Neither
gate implies the other.

THE INVARIANT
-------------
In the **extension-module** target directory -- ``target-shared-pyext``, the
one only ``--features pyo3/extension-module`` builds write to -- every pyo3
crate's uplifted cdylib must export its own ``PyInit_<module>``. There is no
legitimate state in which it does not: that directory exists precisely so
that nothing but extension-module builds land in it. A cdylib there without
the symbol means either a non-extension build reached it (the partition
leaked) or a build produced a broken artifact.

The invariant deliberately does NOT apply to the plain ``target-shared``
directory. A ``PyInit_``-less ``libtemper_geometry.so`` is the *correct*
output of ``cargo build`` there, and flagging it would be a false positive on
every ordinary Rust workflow in the repo -- the fastest way to get a gate
switched off. See ``scripts/_lib/cargo_target.py`` for the partition itself
and the measurements behind it.

WHY THE SYMBOL AND NOT THE FILE SIZE
------------------------------------
The two variants differ enormously in size (5,966,640 vs 527,152 bytes for
temper-geometry, measured) and a size threshold would be a cheaper check. It
would also be wrong the first time a crate's pure-Rust half grows, and it
encodes no reason. The symbol is the actual load-bearing property: CPython
refuses to import a module whose init function it cannot find, with exactly
the error this repo has hit -- "dynamic module does not define module export
function".

Module-name resolution reuses ``check_stale_extensions.discover_crates``
rather than deriving names locally, so both gates agree on what the crates
are. That matters here for a concrete reason: ``temper-design-bundle``'s
cdylib is ``libtemper_design_bundle.so`` but its init symbol is
``PyInit_temper_design_bundle_python`` -- deriving the symbol from the
FILENAME would look right and check the wrong thing.

REPORT MODE vs REMEDIATION MODE, AND WHY THE EXIT CODES DIFFER
---------------------------------------------------------------
Without ``--clean`` this is a gate: a poisoned cdylib is exit 3.

With ``--clean`` it is a repair step, and "found poison, evicted it, the
cache is now clean" is a SUCCESS -- exit 0. Only a clean that actually
failed leaves the cache poisoned, and that is exit 3.

This is deliberate, and it is what lets ``make extensions`` call the
pre-flight without ``|| true`` masking its result. Suppressing an exit code
with ``|| true`` would also suppress the eviction *failing*, which is the one
outcome the build must not proceed past -- the difference between "the cache
was poisoned and is now fixed" and "the cache is poisoned and I could not fix
it" is exactly what the caller needs, and a mask erases it.

Exit codes:
  0 - OK: every uplifted extension cdylib found exports its init symbol; or
      --clean successfully evicted every poisoned one; or the target
      directory does not exist yet (nothing built is not a violation, and is
      reported as such rather than as a pass).
  3 - VIOLATION: at least one poisoned cdylib remains. Without --clean that
      means "found, not fixed" (reported with the exact `cargo clean -p`
      needed, per crate); with --clean it means the eviction itself failed.
  5 - GATE ERROR: zero pyo3 crates discovered -- a vacuous run, never
      folded into "0 violations" (docs/METHODOLOGY.md Sec 4/5).

Usage:
  uv run --no-sync python scripts/check_cargo_uplift_poisoning.py
  uv run --no-sync python scripts/check_cargo_uplift_poisoning.py --clean
  uv run --no-sync python scripts/check_cargo_uplift_poisoning.py \
      --target-dir /path/to/target-shared-pyext
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.cargo_target import (  # noqa: E402
    canonical_repo_root,
    extension_target_dir,
)
from _lib.repo import find_repo_root  # noqa: E402
from check_stale_extensions import (  # noqa: E402
    Crate,
    _exports_init_symbol,
    _load_toml,
    discover_crates,
)

EXIT_OK = 0
EXIT_VIOLATION = 3
EXIT_TOOL_ERROR = 5

#: Cargo's cdylib filenames per platform. Checked in this order; a crate is
#: expected to have at most one built at a time.
_CDYLIB_PATTERNS = ("lib{name}.so", "lib{name}.dylib", "{name}.dll")

#: Profiles whose uplift directory is checked. Both are real: `make
#: extensions` builds --release, but a developer debugging a pyo3 crate
#: builds debug, and a poisoned debug artifact misleads exactly as much.
_PROFILE_DIRS = ("release", "debug")


def cdylib_stem(crate: Crate) -> str:
    """The `[lib] name` cargo uses for this crate's cdylib file.

    Falls back to the package name with hyphens replaced, which is cargo's
    own default when `[lib] name` is absent.
    """
    data = _load_toml(crate.cargo_toml)
    lib_name = data.get("lib", {}).get("name")
    if lib_name:
        return str(lib_name)
    return crate.name.replace("-", "_")


@dataclass
class Finding:
    crate: Crate
    artifact: Path
    exports_init: bool | None  # None = unreadable / not a native file


def scan(crates: list[Crate], target_dir: Path) -> list[Finding]:
    """Every uplifted extension cdylib present under *target_dir*."""
    findings: list[Finding] = []
    for crate in crates:
        stem = cdylib_stem(crate)
        for profile in _PROFILE_DIRS:
            for pattern in _CDYLIB_PATTERNS:
                artifact = target_dir / profile / pattern.format(name=stem)
                if not artifact.is_file():
                    continue
                findings.append(
                    Finding(
                        crate=crate,
                        artifact=artifact,
                        # The module name, NOT the filename stem -- see the
                        # module docstring's temper-design-bundle note.
                        exports_init=_exports_init_symbol(crate.module_name, artifact),
                    )
                )
    return findings


def poisoned(findings: list[Finding]) -> list[Finding]:
    """Findings that are definitively broken.

    ``exports_init is None`` (unreadable, or not a native file) is NOT
    counted: it means the question could not be answered, and inventing a
    verdict there would make the gate fire on a permissions problem. It is
    reported separately instead.
    """
    return [f for f in findings if f.exports_init is False]


def clean_command(finding: Finding, target_dir: Path) -> list[str]:
    """The `cargo clean` that evicts exactly this crate's poisoned artifact.

    Scoped with `-p` so it never discards the whole shared cache: this
    directory is shared by every worktree on the host, and a blanket `cargo
    clean` here would cold-rebuild the fleet.
    """
    return [
        "cargo",
        "clean",
        "-p",
        finding.crate.name,
        "--target-dir",
        str(target_dir),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--repo-root", type=Path, default=None)
    parser.add_argument(
        "--target-dir",
        type=Path,
        default=None,
        help="Extension-module target directory to scan (default: the shared "
        "target-shared-pyext derived from --git-common-dir).",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Run the per-crate `cargo clean -p` for each poisoned artifact "
        "instead of only reporting it. Scoped per crate; never wipes the "
        "shared cache.",
    )
    args = parser.parse_args(argv)

    repo_root = args.repo_root or find_repo_root()
    crates = discover_crates(repo_root)
    if not crates:
        print(
            f"=== CARGO UPLIFT POISONING GATE ERROR ===\n"
            f"zero pyo3/maturin crates discovered under {repo_root / 'packages'} -- "
            "a vacuous run, not a clean pass. Either discover_crates() is broken "
            "or every extension crate is gone; both must fail loudly.",
            file=sys.stderr,
        )
        return EXIT_TOOL_ERROR

    if args.target_dir is not None:
        target_dir = args.target_dir
    else:
        try:
            target_dir = extension_target_dir(canonical_repo_root(repo_root))
        except (subprocess.CalledProcessError, OSError) as exc:
            print(
                f"could not derive the shared extension target dir ({exc!r}); "
                "pass --target-dir explicitly",
                file=sys.stderr,
            )
            return EXIT_TOOL_ERROR

    print(f"Cargo uplift-poisoning gate -- scanning {target_dir}")
    print(f"  {len(crates)} pyo3/maturin crate(s) discovered under packages/.")

    if not target_dir.is_dir():
        # Not a violation and not a pass: state it, so nobody reads a clean
        # exit here as "the cache was checked and was fine".
        print(
            "  target directory does not exist yet -- nothing has been built "
            "into it. 0 artifact(s) checked; this is not evidence the cache "
            "is clean."
        )
        return EXIT_OK

    findings = scan(crates, target_dir)
    bad = poisoned(findings)
    unreadable = [f for f in findings if f.exports_init is None]

    print(
        f"  {len(findings)} uplifted cdylib(s) present, {len(bad)} poisoned, "
        f"{len(unreadable)} unreadable."
    )
    for f in findings:
        mark = "OK" if f.exports_init else ("UNREADABLE" if f.exports_init is None else "POISONED")
        print(f"  [{mark}] {f.crate.name}: {f.artifact}")

    if not bad:
        if not findings:
            print(
                "\nNo extension cdylib has been built into this directory yet. "
                "0 checked -- not a certification that the cache is clean."
            )
        else:
            print(f"\nPASSED -- {len(findings)} uplifted cdylib(s) export their init symbol.")
        return EXIT_OK

    print(
        f"\nFAILED -- {len(bad)} cdylib(s) in the extension-module target dir export no "
        f"PyInit_<module>.",
        file=sys.stderr,
    )
    print(
        "\nThis is the shared cargo cache holding an artifact built WITHOUT "
        "`pyo3/extension-module`. maturin will reuse it, print `Finished ... in "
        "0.0Xs` with no `Compiling` line, and install a `.so` that cannot be "
        "imported -- while every mtime and content hash on it looks perfectly "
        "fresh. Nothing downstream will tell you; the import just fails with "
        '"dynamic module does not define module export function".',
        file=sys.stderr,
    )
    evict_failures = 0
    for f in bad:
        cmd = clean_command(f, target_dir)
        print(f"\n  {f.crate.name}: {f.artifact}", file=sys.stderr)
        print(f"    expected symbol: PyInit_{f.crate.module_name}", file=sys.stderr)
        print(f"    fix: {' '.join(cmd)}", file=sys.stderr)
        if args.clean:
            print(f"    running: {' '.join(cmd)}", file=sys.stderr)
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                evict_failures += 1
                print(
                    f"    cargo clean FAILED (exit {result.returncode}): {result.stderr.strip()}",
                    file=sys.stderr,
                )
                continue
            print("    evicted.", file=sys.stderr)

    if not args.clean:
        return EXIT_VIOLATION

    if evict_failures:
        print(
            f"\nFAILED -- {evict_failures} of {len(bad)} poisoned artifact(s) could "
            "not be evicted; the cache is still poisoned and the next build will "
            "reuse it.",
            file=sys.stderr,
        )
        return EXIT_VIOLATION

    # Found poison and removed it: the cache is clean, which is what the
    # caller asked for. See "REPORT MODE vs REMEDIATION MODE" above for why
    # this is exit 0 and not a masked failure.
    print(
        f"\nREPAIRED -- evicted {len(bad)} poisoned artifact(s). Rebuild and confirm "
        "a real `Compiling <crate>` line appears; a rebuild that prints only "
        "`Finished ... in 0.0Xs` reused something.",
        file=sys.stderr,
    )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
