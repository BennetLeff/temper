"""Proof-first tests for the sealed qualification replay boundary."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest
from scripts._lib import qualification_replay


def test_read_once_rejects_symlink_and_hashes_the_same_bytes(tmp_path: Path) -> None:
    source = tmp_path / "source.json"
    source.write_bytes(b'{"stable":true}\n')
    link = tmp_path / "link.json"
    link.symlink_to(source)

    result = qualification_replay.read_once(source, root=tmp_path)
    assert result.data == source.read_bytes()
    assert result.sha256 == hashlib.sha256(result.data).hexdigest()
    with pytest.raises(qualification_replay.ReplayError, match="symlink"):
        qualification_replay.read_once(link, root=tmp_path)


def test_read_once_rechecks_replacement_before_returning(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "manifest.json"
    source.write_bytes(b"before")
    original = qualification_replay.os.read

    def replace_after_first_read(fd: int, size: int) -> bytes:
        data = original(fd, size)
        replacement = tmp_path / "replacement"
        replacement.write_bytes(b"after")
        os.replace(replacement, source)
        return data

    monkeypatch.setattr(qualification_replay.os, "read", replace_after_first_read)
    with pytest.raises(qualification_replay.ReplayError, match="changed during read"):
        qualification_replay.read_once(source, root=tmp_path)


def test_snapshot_records_initial_absence_and_directory_membership(tmp_path: Path) -> None:
    absent = "elec/build"
    snapshot = qualification_replay.snapshot_paths(tmp_path, [absent])
    assert snapshot[absent].kind == "absent"

    (tmp_path / absent / "nested").mkdir(parents=True)
    (tmp_path / absent / "nested" / "output.json").write_bytes(b"output")
    after = qualification_replay.snapshot_paths(tmp_path, [absent])
    assert after[absent].kind == "directory"
    assert f"{absent}/nested/output.json" in after


def test_publish_is_atomic_and_refuses_protected_hardlink(tmp_path: Path) -> None:
    protected = tmp_path / "protected.json"
    protected.write_bytes(b"do not replace")
    output = tmp_path / "decision.json"
    os.link(protected, output)

    with pytest.raises(qualification_replay.ReplayError, match="hardlink"):
        qualification_replay.publish_atomic(
            output,
            "{}\n",
            root=tmp_path,
            protected_paths=["protected.json"],
        )
    assert protected.read_bytes() == b"do not replace"


def test_publish_replaces_regular_output_atomically(tmp_path: Path) -> None:
    output = tmp_path / "decision.json"
    output.write_bytes(b"old")

    qualification_replay.publish_atomic(output, "new\n", root=tmp_path)

    assert output.read_bytes() == b"new\n"
    assert not list(tmp_path.glob(".decision.json.replay-*.tmp"))


def test_publish_refuses_symlink_output(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_bytes(b"protected")
    output = tmp_path / "decision.json"
    output.symlink_to(target)

    with pytest.raises(qualification_replay.ReplayError, match="symlink output"):
        qualification_replay.publish_atomic(output, "new\n", root=tmp_path)
    assert target.read_bytes() == b"protected"
