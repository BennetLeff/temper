"""Content-hash freshness for built artifacts, with an mtime fallback.

Why this exists
---------------
Every freshness gate in this repo asks "was this artifact built from the
sources currently on disk?" and answers it by comparing mtimes: if any source
is newer than the artifact, the artifact is stale. That is cheap, and it is
correct for the workflow those gates were written for -- build after checkout,
compare, done.

It is wrong for any artifact that did not come from a build in this working
tree. ``git checkout`` stamps every tracked file with the checkout time, so a
restored cache, a prebuilt wheel baked into a container image, or an artifact
carried between jobs is *always* "older" than its own sources, whether or not
its content matches them. The gate then fails closed on a perfectly valid
artifact.

Measured on 2026-07-28: enabling the netlist ``actions/cache`` skip made
check_domain_partition.py error with "netlist is STALE ... 8 source file(s)
newer than the compiled netlist" on a netlist whose sources had not changed at
all. Same branch, same sources -- run 30383701486 rebuilt and passed the gate,
run 30384514627 restored from cache and failed it. The galvanic-isolation check
stopped running on a mains-connected design to save 27 seconds, so the change
was reverted.

check_stale_extensions.py names the same limitation in its own docstring and
declines to fix it ("would require content hashing or git-log timestamps, a
materially heavier check"). This module is that content hashing, made cheap
enough to adopt: one SHA-256 pass over the same files the gate already stats.

What a stamp is
---------------
A build writes a *stamp* next to its artifact recording the digest of the
inputs it was built from. A gate recomputes the digest of those inputs now and
compares. Equal digests mean the artifact matches current sources regardless of
mtimes, filesystem, or how the artifact got there.

Fallback, deliberately
----------------------
When no stamp is present the check falls back to the existing mtime comparison
rather than failing. A missing stamp means "built by a path that predates this
mechanism", which is the normal state for every artifact built before this
landed and for anyone's local tree mid-migration. Failing closed there would
turn a latent improvement into an immediate outage for every developer, and the
mtime check is exactly as good as it was yesterday -- no worse.

The reverse is not true: when a stamp IS present it is authoritative, and the
mtime comparison is not consulted. That is the entire point. A cached artifact
carrying a matching stamp is fresh even though every source file appears newer.

What a stamp does NOT protect against
-------------------------------------
A stamp records the inputs a build *claimed*. It cannot detect a build that
wrote a corrupt artifact and then stamped it, and it is not a signature -- a
hand-edited stamp will be believed. It answers "do the inputs still match?",
which is the question the mtime check was approximating, and nothing more.

Writing a stamp must therefore be conditional on the build succeeding. Callers
chain it after the build command (``build && write-stamp``), never alongside.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

# Bumped if the digest construction ever changes, so old stamps are ignored
# rather than silently compared against a differently-computed digest.
STAMP_VERSION = "1"
STAMP_SUFFIX = ".source-digest"

_CHUNK = 1 << 20


@dataclass(frozen=True)
class FreshnessResult:
    """Outcome of a freshness check.

    ``method`` is "content" when a stamp was present and authoritative, and
    "mtime" when the legacy comparison was used. Gates surface it so a reader
    can tell which question was actually answered.
    """

    fresh: bool
    method: str
    detail: str


def _hash_file(path: Path, digest: hashlib._Hash) -> None:
    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK):
            digest.update(chunk)


def compute_inputs_digest(source_files: Iterable[Path], root: Path) -> str:
    """SHA-256 over the sorted (relative path, content) pairs of the inputs.

    Paths are included, not just content, so that renaming a file changes the
    digest -- a rename with identical bytes genuinely changes the build inputs.
    Paths are relativised to ``root`` and POSIX-normalised so a digest computed
    in a container matches one computed on a developer's machine.

    Raises FileNotFoundError if any listed input is missing, rather than
    silently hashing a shorter list. A gate that skipped a deleted input would
    report fresh after a source file was removed.
    """
    digest = hashlib.sha256()
    digest.update(f"v{STAMP_VERSION}\n".encode())

    entries = sorted(Path(p) for p in source_files)
    if not entries:
        raise ValueError("refusing to compute a digest over zero input files")

    for path in entries:
        rel = path.resolve().relative_to(root.resolve()).as_posix()
        digest.update(f"{rel}\0".encode())
        _hash_file(path, digest)
        digest.update(b"\0")

    return digest.hexdigest()


def stamp_path_for(artifact: Path) -> Path:
    """Location of the stamp for ``artifact``.

    Kept beside the artifact so that whatever mechanism moves the artifact --
    actions/cache, a container layer, an upload-artifact tarball -- carries the
    stamp with it automatically. A stamp stored anywhere else would be lost by
    exactly the transports this mechanism exists to support.
    """
    return artifact.with_name(artifact.name + STAMP_SUFFIX)


def write_stamp(artifact: Path, source_files: Iterable[Path], root: Path) -> str:
    """Record the digest of ``source_files`` beside ``artifact``. Returns it.

    Call this only after the build that produced ``artifact`` succeeded.
    """
    digest = compute_inputs_digest(source_files, root)
    stamp_path_for(artifact).write_text(f"{STAMP_VERSION} {digest}\n", encoding="utf-8")
    return digest


def read_stamp(artifact: Path) -> str | None:
    """Digest recorded for ``artifact``, or None if absent/unreadable/stale-format."""
    path = stamp_path_for(artifact)
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None
    parts = raw.split()
    if len(parts) != 2 or parts[0] != STAMP_VERSION:
        return None
    return parts[1]


def check_freshness(
    artifact: Path,
    source_files: Iterable[Path],
    root: Path,
) -> FreshnessResult:
    """Is ``artifact`` built from the current ``source_files``?

    Content comparison when a stamp is present (authoritative); otherwise the
    legacy newer-than-artifact mtime comparison.
    """
    entries = sorted(Path(p) for p in source_files)
    if not entries:
        raise ValueError("refusing to check freshness against zero input files")

    recorded = read_stamp(artifact)
    if recorded is not None:
        current = compute_inputs_digest(entries, root)
        if current == recorded:
            return FreshnessResult(
                True, "content", f"inputs digest matches stamp ({current[:12]}…)"
            )
        return FreshnessResult(
            False,
            "content",
            f"inputs digest {current[:12]}… does not match stamp {recorded[:12]}… "
            f"-- {len(entries)} input file(s) hashed",
        )

    artifact_mtime = artifact.stat().st_mtime
    newer = [f for f in entries if f.stat().st_mtime > artifact_mtime]
    if not newer:
        return FreshnessResult(True, "mtime", "no input file is newer than the artifact")
    newest = max(newer, key=lambda f: f.stat().st_mtime)
    return FreshnessResult(
        False,
        "mtime",
        f"{newest} was modified after {artifact} was built "
        f"({len(newer)} source file(s) newer than the artifact); "
        "no build stamp was present, so the mtime comparison was used",
    )
