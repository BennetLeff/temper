"""Sealed, offline I/O boundary for qualification replay.

Qualification runners are intentionally thin adapters.  This module is the
single owner of the security-sensitive mechanics they share: path resolution,
single-read hashing, identity rechecks, protected-set snapshots, and atomic
publication.  It does not know any qualification schema or verdict policy.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence


class ReplayError(RuntimeError):
    """A fail-closed repository replay error."""


@dataclass(frozen=True)
class ReadOnce:
    """Bytes and identity captured from one securely opened regular file."""

    path: Path
    data: bytes
    sha256: str
    identity: tuple[int, int, int, int, int]


@dataclass(frozen=True)
class SnapshotEntry:
    """Stable protected-set entry; ``absent`` is an intentional state."""

    kind: str
    sha256: str | None = None
    identity: tuple[int, int, int, int, int] | None = None


def _same_snapshot(
    before: Mapping[str, SnapshotEntry], after: Mapping[str, SnapshotEntry]
) -> bool:
    """Compare content/membership, excluding inode metadata such as link count."""

    return {
        path: (entry.kind, entry.sha256)
        for path, entry in before.items()
    } == {
        path: (entry.kind, entry.sha256)
        for path, entry in after.items()
    }


def _relative_path(path: str | Path, root: Path) -> tuple[Path, Path]:
    """Return a validated relative path and its resolved absolute spelling."""

    raw = Path(path)
    root = root.resolve(strict=True)
    if raw.is_absolute():
        try:
            # Keep the lexical spelling so the final lstat can reject a
            # symlink; resolve only for the containment check below.
            relative = raw.relative_to(root)
        except (OSError, RuntimeError, ValueError) as exc:
            raise ReplayError(f"path escapes replay root: {path}") from exc
    else:
        relative = raw
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise ReplayError(f"path must be a non-empty repo-relative path: {path!r}")
    absolute = root / relative
    try:
        resolved = absolute.resolve(strict=False)
        resolved.relative_to(root)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ReplayError(f"path escapes replay root: {path!r}") from exc
    # A symlink in a parent can redirect an otherwise safe final component.
    cursor = root
    for part in relative.parts[:-1]:
        cursor /= part
        try:
            if cursor.is_symlink():
                raise ReplayError(f"path contains symlink component: {path!r}")
        except OSError as exc:
            raise ReplayError(f"cannot inspect path component {cursor}: {exc}") from exc
    return relative, absolute


def _identity(info: os.stat_result) -> tuple[int, int, int, int, int]:
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def read_once(
    path: str | Path,
    *,
    root: Path,
    expected_sha256: str | None = None,
    reject_inodes: Iterable[tuple[int, int]] = (),
) -> ReadOnce:
    """Open, read, hash, and identity-recheck one regular file.

    The digest and any caller payload must be derived from ``result.data``.
    The final path and descriptor identities are checked after the read, so a
    replacement race cannot turn a preflight check into an approval.
    """

    relative, absolute = _relative_path(path, root)
    try:
        link_info = os.lstat(absolute)
    except OSError as exc:
        raise ReplayError(f"cannot inspect {relative}: {exc}") from exc
    if stat.S_ISLNK(link_info.st_mode):
        raise ReplayError(f"refusing symlink input: {relative}")
    if not stat.S_ISREG(link_info.st_mode):
        raise ReplayError(f"input is not a regular file: {relative}")
    link_identity = (link_info.st_dev, link_info.st_ino)
    if link_identity in set(reject_inodes):
        raise ReplayError(f"input aliases a protected inode: {relative}")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(absolute, flags)
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise ReplayError(f"input is not a regular file: {relative}")
        opened_identity = _identity(opened)
        if (opened.st_dev, opened.st_ino) != link_identity:
            raise ReplayError(f"input changed during secure open: {relative}")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1 << 20)
            if not chunk:
                break
            chunks.append(chunk)
        data = b"".join(chunks)
        after = os.fstat(descriptor)
        try:
            path_after = os.lstat(absolute)
        except OSError as exc:
            raise ReplayError(f"input changed during read: {relative}") from exc
        if _identity(after) != opened_identity or _identity(path_after) != opened_identity:
            raise ReplayError(f"input changed during read: {relative}")
    except ReplayError:
        raise
    except OSError as exc:
        raise ReplayError(f"cannot securely read {relative}: {exc}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
    digest = hashlib.sha256(data).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256.lower():
        raise ReplayError(
            f"digest mismatch for {relative}: expected {expected_sha256}, found {digest}"
        )
    return ReadOnce(absolute, data, digest, opened_identity)


def _snapshot_entry(relative: Path, absolute: Path, root: Path) -> dict[str, SnapshotEntry]:
    try:
        info = os.lstat(absolute)
    except FileNotFoundError:
        return {relative.as_posix(): SnapshotEntry("absent")}
    except OSError as exc:
        raise ReplayError(f"cannot inspect protected path {relative}: {exc}") from exc
    if stat.S_ISLNK(info.st_mode):
        raise ReplayError(f"protected path is a symlink: {relative}")
    if stat.S_ISREG(info.st_mode):
        result = read_once(absolute, root=root)
        return {
            relative.as_posix(): SnapshotEntry("file", result.sha256, result.identity)
        }
    if stat.S_ISDIR(info.st_mode):
        snapshot = {relative.as_posix(): SnapshotEntry("directory", None, _identity(info))}
        try:
            children = sorted(os.scandir(absolute), key=lambda item: item.name)
        except OSError as exc:
            raise ReplayError(f"cannot enumerate protected directory {relative}: {exc}") from exc
        for child in children:
            child_relative = relative / child.name
            snapshot.update(_snapshot_entry(child_relative, Path(child.path), root))
        return snapshot
    raise ReplayError(f"protected path is not regular: {relative}")


def snapshot_paths(root: Path, paths: Iterable[str | Path]) -> dict[str, SnapshotEntry]:
    """Capture bytes and membership for files/directories, including absence."""

    root = root.resolve(strict=True)
    result: dict[str, SnapshotEntry] = {}
    for path in paths:
        relative, absolute = _relative_path(path, root)
        entries = _snapshot_entry(relative, absolute, root)
        overlap = set(result).intersection(entries)
        if overlap:
            raise ReplayError("protected paths overlap: " + ", ".join(sorted(overlap)))
        result.update(entries)
    return result


def _open_parent(output: Path, root: Path) -> tuple[int, Path, os.stat_result]:
    _, absolute = _relative_path(output, root)
    parent = absolute.parent
    descriptor: int | None = None
    try:
        resolved = parent.resolve(strict=True)
        resolved.relative_to(root.resolve(strict=True))
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(resolved, flags)
        pinned = os.fstat(descriptor)
        current = os.stat(parent, follow_symlinks=False)
    except (OSError, RuntimeError, ValueError) as exc:
        if descriptor is not None:
            os.close(descriptor)
        raise ReplayError(f"cannot securely open output parent {parent}: {exc}") from exc
    if not stat.S_ISDIR(pinned.st_mode) or (pinned.st_dev, pinned.st_ino) != (
        current.st_dev,
        current.st_ino,
    ):
        os.close(descriptor)
        raise ReplayError(f"output parent changed during secure open: {parent}")
    return descriptor, parent, pinned


def publish_atomic(
    output: str | Path,
    content: str,
    *,
    root: Path,
    protected_paths: Iterable[str | Path] = (),
    protected_root: Path | None = None,
) -> None:
    """Atomically publish output after refusing protected aliases and links."""

    _, absolute = _relative_path(output, root)
    protected = snapshot_paths(protected_root or root, protected_paths)
    try:
        existing = os.lstat(absolute)
    except FileNotFoundError:
        existing = None
    except OSError as exc:
        raise ReplayError(f"cannot inspect output path {absolute}: {exc}") from exc
    if existing is not None:
        if stat.S_ISLNK(existing.st_mode):
            raise ReplayError(f"refusing symlink output: {absolute}")
        if not stat.S_ISREG(existing.st_mode):
            raise ReplayError(f"output is not a regular file: {absolute}")
        for entry in protected.values():
            if entry.identity and (existing.st_dev, existing.st_ino) == entry.identity[:2]:
                raise ReplayError(
                    f"refusing output sharing protected input inode (hardlink): {absolute}"
                )
    parent_fd: int | None = None
    temporary: str | None = None
    descriptor: int | None = None
    try:
        parent_fd, parent, parent_stat = _open_parent(absolute, root)
        current_parent = os.stat(parent, follow_symlinks=False)
        if (current_parent.st_dev, current_parent.st_ino) != (
            parent_stat.st_dev,
            parent_stat.st_ino,
        ):
            raise ReplayError(f"output parent changed during secure publication: {parent}")
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        for attempt in range(100):
            temporary = f".{absolute.name}.replay-{os.urandom(16).hex()}.tmp"
            try:
                descriptor = os.open(temporary, flags, 0o600, dir_fd=parent_fd)
                break
            except FileExistsError:
                temporary = None
        if descriptor is None or temporary is None:
            raise ReplayError("unable to allocate private replay output")
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            descriptor = None
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        current_parent = os.stat(parent, follow_symlinks=False)
        if (current_parent.st_dev, current_parent.st_ino) != (
            parent_stat.st_dev,
            parent_stat.st_ino,
        ):
            raise ReplayError(f"output parent changed during secure publication: {parent}")
        os.replace(temporary, absolute.name, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
        temporary = None
    except ReplayError:
        raise
    except (OSError, TypeError) as exc:
        raise ReplayError(f"cannot atomically publish {absolute}: {exc}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary is not None and parent_fd is not None:
            try:
                os.unlink(temporary, dir_fd=parent_fd)
            except OSError:
                pass
        if parent_fd is not None:
            os.close(parent_fd)


def normalized_text_exports(
    project_root: Path,
    exports: Mapping[str, str],
    *,
    root_token: str,
) -> dict[str, str]:
    """Read regular build outputs and normalize newline and checkout-root noise."""

    resolved_root = project_root.resolve(strict=True)
    marker = resolved_root.as_posix()
    result: dict[str, str] = {}
    for source_name, canonical_name in exports.items():
        source = resolved_root / "build" / source_name
        try:
            info = os.lstat(source)
            if not stat.S_ISREG(info.st_mode):
                raise ReplayError(f"build export is not regular: {source_name}")
            with source.open(encoding="utf-8", newline="") as handle:
                text = handle.read()
        except (OSError, UnicodeError) as exc:
            raise ReplayError(f"cannot read build export {source_name}: {exc}") from exc
        result[canonical_name] = text.replace("\r\n", "\n").replace(
            f"{marker}/src/", f"{root_token}/src/"
        )
    return result


def publish_text_exports(
    exports: Mapping[str, str],
    destination: Path,
    *,
    root: Path,
    protected_paths: Iterable[str | Path],
) -> None:
    """Publish a deterministic export set while proving protected bytes unchanged."""

    before = snapshot_paths(root, protected_paths)
    destination.mkdir(parents=True, exist_ok=True)
    for name, content in exports.items():
        publish_atomic(
            destination / name,
            content,
            root=root,
            protected_paths=protected_paths,
        )
    if not _same_snapshot(before, snapshot_paths(root, protected_paths)):
        raise ReplayError("protected artifacts changed during export publication")


def recheck_observations(
    observations: Mapping[str, ReadOnce], *, root: Path
) -> None:
    """Re-read every evidence file captured during a replay.

    A protected-set snapshot alone does not cover candidate evidence.  This
    shared primitive closes that window by requiring both bytes and secure-file
    identity to remain unchanged before and after a decision is published.
    """

    for relative, captured in sorted(observations.items()):
        current = read_once(
            root / relative,
            root=root,
            expected_sha256=captured.sha256,
        )
        if current.data != captured.data or current.identity != captured.identity:
            raise ReplayError(f"observed evidence changed during replay: {relative}")


def sealed_replay(
    manifest_path: str | Path,
    output_path: str | Path | None,
    *,
    root: Path,
    protected_paths: Sequence[str | Path],
    output_root: Path | None = None,
    parse_manifest: Callable[[bytes], Mapping[str, Any]],
    evaluate: Callable[[Mapping[str, Any]], str],
    validate_output: Callable[[Mapping[str, Any], Mapping[str, Any]], None],
    preflight: Callable[[Mapping[str, Any]], None] | None = None,
    observations: Mapping[str, ReadOnce] | None = None,
) -> str:
    """Run a schema-specific evaluator inside the common sealed boundary."""

    manifest_read = read_once(manifest_path, root=root)
    manifest = parse_manifest(manifest_read.data)
    if preflight is not None:
        preflight(manifest)
    before = snapshot_paths(root, protected_paths)
    package = evaluate(manifest)
    try:
        parsed = json.loads(package)
    except json.JSONDecodeError as exc:
        raise ReplayError(f"evaluator returned invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ReplayError("evaluator returned a non-object decision package")
    validate_output(manifest, parsed)
    after = snapshot_paths(root, protected_paths)
    if not _same_snapshot(before, after):
        raise ReplayError("protected set changed during replay")
    if observations is not None:
        recheck_observations(observations, root=root)
    canonical = package.rstrip() + "\n"
    if output_path is not None:
        publish_atomic(
            output_path,
            canonical,
            root=output_root or root,
            protected_paths=protected_paths,
            protected_root=root,
        )
        if observations is not None:
            recheck_observations(observations, root=root)
        if not _same_snapshot(before, snapshot_paths(root, protected_paths)):
            raise ReplayError("protected set changed during decision-package write")
    return canonical
