#!/usr/bin/env python3
"""Record which sources each installed pyo3 extension was built from.

Build-side half of content-hash freshness for the Rust extension crates;
``scripts/check_stale_extensions.py`` is the gate-side half and
``scripts/_lib/freshness.py`` is the shared mechanism. Read the gate's
docstring first -- it carries the two design decisions (why content
hashing at all, and why the stamp lives beside the installed ``.so``
keyed on that ``.so``'s own bytes).

Why a separate script rather than ``&& write_build_stamp.py``
------------------------------------------------------------
The netlist chains its stamp onto the build with ``&&`` because there is
one build command and one artifact at a known path. Here there are ten
crates, three of which CI builds with explicit ``maturin develop`` steps
and the rest of which arrive via ``uv sync --all-packages``; and the
artifact's path is not knowable from the command line -- it is whatever
``importlib.util.find_spec`` resolves to inside the venv, past maturin's
thin ``__init__.py`` wrapper. So the stamp writer reuses the gate's own
discovery, source-set, and artifact-resolution code rather than
re-deriving any of it. There is exactly one definition of "this crate's
source files" in this repo, and it lives in the gate.

Why this cannot launder a stale artifact
----------------------------------------
A stamp asserts "this binary was built from these sources". Writing one
next to an artifact that was *not* just built from them would be worse
than no stamp at all: it is authoritative, so it would permanently mask
the exact staleness the gate exists to catch.

So this script never asserts anything the gate does not already believe:
it runs ``check_module`` first and stamps a crate only when that returns
**fresh**. In CI that verdict comes from the mtime comparison
immediately after a build in a freshly checked-out tree -- the one
workflow mtimes are genuinely correct for -- which is exactly why the
stamp is trustworthy enough to outlive it. A crate the gate calls STALE
is refused, loudly, and left for the gate to fail on.

That also makes the ordering requirement mechanical rather than a
convention someone must remember: run this after the builds. A build
that failed leaves a stale-or-missing artifact, which is refused.

Exit codes:
  0 - at least one crate stamped (crates that are not installed in this
      environment are skipped; crates the gate calls STALE are refused
      and reported, but do not fail this script -- the gate itself is
      what must fail on those)
  1 - zero crates stamped, or discovery failed. Never report success for
      a run that recorded nothing; "stamped 0 of 10" is the vacuous-pass
      shape docs/METHODOLOGY.md Sec 4/5 warns about.

Usage:
  uv run --no-sync python scripts/write_extension_stamps.py
  uv run --no-sync python scripts/write_extension_stamps.py --repo-root .
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.freshness import write_stamp  # noqa: E402
from _lib.repo import find_repo_root  # noqa: E402
from check_stale_extensions import (  # noqa: E402
    Crate,
    GateError,
    check_module,
    crate_source_files,
    digest_root,
    discover_crates,
    stamp_file_for,
    stamp_key_path,
    superseded_stamps,
)

EXIT_OK = 0
EXIT_FAILED = 1


def stamp_crate(crate: Crate, artifact: Path) -> tuple[Path, str, int]:
    """Write *artifact*'s stamp and prune stamps of its earlier builds.

    Returns (stamp path, digest, number of superseded stamps removed).
    """
    pruned = 0
    for old in superseded_stamps(artifact):
        try:
            old.unlink()
            pruned += 1
        except OSError:
            pass  # litter, not a correctness problem -- the key still binds

    sources = crate_source_files(crate)
    digest = write_stamp(stamp_key_path(artifact), sources, digest_root(sources))
    return stamp_file_for(artifact), digest, pruned


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root", type=Path, default=None, help="Override repo root (mainly for tests)."
    )
    args = parser.parse_args(argv)
    repo_root = args.repo_root or find_repo_root()

    crates = discover_crates(repo_root)
    if not crates:
        print(
            f"[extension-stamps] ERROR: zero pyo3/maturin crates discovered under "
            f"{repo_root / 'packages'} -- nothing to stamp is not a success",
            file=sys.stderr,
        )
        return EXIT_FAILED

    stamped: list[str] = []
    skipped: list[str] = []
    refused: list[str] = []

    for crate in crates:
        status = check_module(crate)
        if status.state == "missing":
            skipped.append(crate.name)
            print(f"  [SKIP]    {crate.name}: not installed in this environment")
            continue
        if status.state != "fresh" or status.artifact is None:
            refused.append(crate.name)
            print(
                f"  [REFUSED] {crate.name}: {status.detail}",
                file=sys.stderr,
            )
            continue
        try:
            stamp, digest, pruned = stamp_crate(crate, status.artifact)
        except (GateError, OSError, ValueError) as exc:
            refused.append(crate.name)
            print(f"  [REFUSED] {crate.name}: could not write stamp: {exc!r}", file=sys.stderr)
            continue
        stamped.append(crate.name)
        print(
            f"  [STAMPED] {crate.name}: {stamp.name} = {digest[:12]}… "
            f"(verdict was '{status.method}'"
            + (f", pruned {pruned} superseded stamp(s)" if pruned else "")
            + ")"
        )

    print(
        f"[extension-stamps] {len(stamped)} stamped, {len(skipped)} not installed, "
        f"{len(refused)} refused, of {len(crates)} crate(s) discovered."
    )
    if refused:
        print(
            f"[extension-stamps] {len(refused)} crate(s) were NOT stamped because they "
            "are not fresh; check_stale_extensions.py is what fails on those.",
            file=sys.stderr,
        )
    if not stamped:
        print(
            "[extension-stamps] ERROR: stamped 0 crate(s) -- refusing to report "
            "success for a run that recorded nothing.",
            file=sys.stderr,
        )
        return EXIT_FAILED
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
