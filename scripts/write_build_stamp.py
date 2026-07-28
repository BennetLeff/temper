#!/usr/bin/env python3
"""Record which sources a built artifact came from, for content-hash freshness.

Freshness gates in this repo ask "was this artifact built from the sources
currently on disk?". They answered it by mtime, which is wrong for any artifact
that did not come from a build in this working tree -- `git checkout` stamps
every source with the checkout time, so a restored cache always looks stale
even when its content matches exactly. See scripts/_lib/freshness.py.

This is the build-side half: run it immediately after a successful build to
record the digest of that build's inputs beside its output. The gate-side half
reads the stamp and compares against the inputs as they are now.

Chain it after the build, never alongside -- a stamp written next to a failed
build would assert freshness for a broken artifact:

    ato build ... && write_build_stamp.py --artifact ... --sources ...

Usage:
    write_build_stamp.py --artifact elec/build/default.net \\
                         --source-root elec/src --glob '*.ato'

Exit codes:
    0  stamp written
    1  no inputs matched, artifact missing, or the stamp could not be written
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib.freshness import write_stamp  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True, help="Built file to stamp")
    parser.add_argument(
        "--source-root", type=Path, required=True, help="Directory the inputs live under"
    )
    parser.add_argument(
        "--glob", default="*", help="Recursive glob selecting inputs (default: all files)"
    )
    args = parser.parse_args(argv)

    if not args.artifact.is_file():
        print(
            f"[write-build-stamp] ERROR: artifact not found: {args.artifact} "
            "-- refusing to stamp a build that did not produce its output",
            file=sys.stderr,
        )
        return 1
    if not args.source_root.is_dir():
        print(
            f"[write-build-stamp] ERROR: source root not found: {args.source_root}",
            file=sys.stderr,
        )
        return 1

    sources = sorted(p for p in args.source_root.rglob(args.glob) if p.is_file())
    if not sources:
        print(
            f"[write-build-stamp] ERROR: no files matched {args.glob!r} under "
            f"{args.source_root} -- a stamp over zero inputs would assert "
            "freshness against nothing",
            file=sys.stderr,
        )
        return 1

    digest = write_stamp(args.artifact, sources, args.source_root)
    print(
        f"[write-build-stamp] {args.artifact}: {len(sources)} input(s), "
        f"digest {digest[:12]}…"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
