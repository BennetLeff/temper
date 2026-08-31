"""Crash-safe persistence for collision-campaign checkpoints.

Rust owns checkpoint meaning and serialization.  This module is deliberately
boring: it validates the destination, reads/writes the opaque bytes exposed by
``temper_orchestration``, and never decodes or reconstructs campaign state in
Python.
"""

from __future__ import annotations

import os
import stat
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import Any

import temper_orchestration as _rust


def _validate_path(path: Path) -> None:
    if not isinstance(path, Path):
        raise TypeError("checkpoint_path must be a pathlib.Path")
    try:
        info = path.lstat()
    except FileNotFoundError:
        info = None
    if info is not None:
        if stat.S_ISLNK(info.st_mode):
            raise ValueError("checkpoint_path must not be a symlink")
        if not stat.S_ISREG(info.st_mode):
            raise ValueError("checkpoint_path must name a regular file")
    try:
        parent = path.parent.stat()
    except OSError as exc:
        raise ValueError("checkpoint_path parent is not accessible") from exc
    if not stat.S_ISDIR(parent.st_mode):
        raise ValueError("checkpoint_path parent must be a directory")


def write_collision_campaign_checkpoint(path: str | Path, checkpoint: Any) -> None:
    """Atomically write bytes produced by a Rust checkpoint object."""

    destination = Path(path)
    _validate_path(destination)
    try:
        payload = checkpoint.to_bytes()
    except AttributeError as exc:
        raise TypeError("checkpoint must be a Rust collision campaign checkpoint") from exc
    if not isinstance(payload, (bytes, bytearray)):
        raise TypeError("Rust checkpoint to_bytes() must return bytes")

    descriptor = -1
    temporary_name: str | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".tmp",
        )
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(bytes(payload))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, destination)
        temporary_name = None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary_name is not None:
            with suppress(FileNotFoundError):
                os.unlink(temporary_name)


def read_collision_campaign_checkpoint(path: str | Path) -> Any:
    """Read and validate opaque Rust checkpoint bytes without Python decoding."""

    source = Path(path)
    _validate_path(source)
    descriptor = -1
    try:
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(source, flags)
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError("checkpoint_path must name a regular file")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            payload = stream.read()
    except OSError as exc:
        raise ValueError("unable to read collision campaign checkpoint") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    try:
        return _rust.CollisionCampaignCheckpoint.from_bytes(payload)
    except Exception as exc:
        raise ValueError(f"invalid collision campaign checkpoint: {exc}") from exc


def restore_collision_campaign_checkpoint(
    path: str | Path,
    *,
    board: str,
    rules: str,
    solver: str,
    axis: str,
) -> Any:
    """Restore a checkpoint after Rust validates its complete identity."""

    checkpoint = read_collision_campaign_checkpoint(path)
    try:
        return checkpoint.restore_for(board, rules, solver, axis)
    except Exception as exc:
        raise ValueError(f"collision campaign checkpoint identity mismatch: {exc}") from exc


# Short aliases mirror the older creepage replay persistence module while
# keeping the collision-specific names discoverable to callers.
write_checkpoint = write_collision_campaign_checkpoint
read_checkpoint = read_collision_campaign_checkpoint
restore_checkpoint = restore_collision_campaign_checkpoint


__all__ = [
    "read_checkpoint",
    "read_collision_campaign_checkpoint",
    "restore_checkpoint",
    "restore_collision_campaign_checkpoint",
    "write_checkpoint",
    "write_collision_campaign_checkpoint",
]
