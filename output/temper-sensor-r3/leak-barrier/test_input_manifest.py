"""Cheap tests of the T2/T3 input manifest: only listed bytes move the manifest."""
from __future__ import annotations

import shutil
from pathlib import Path

import input_manifest as IM

REPO = Path(__file__).resolve().parents[3]


def _copy_inputs(dst: Path, rels) -> None:
    for rel in rels:
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / rel, target)


def test_listed_inputs_exist():
    for rel in IM.T2_INPUTS + IM.T3_INPUTS:
        assert (REPO / rel).is_file(), rel


def test_unlisted_file_does_not_change_manifest(tmp_path):
    _copy_inputs(tmp_path, IM.T2_INPUTS)
    before = IM.sha256_manifest(tmp_path, IM.T2_INPUTS)
    # A file the old broad glob would have hashed (sensors include/*.h), but the study never reads.
    unlisted = tmp_path / "firmware/components/sensors/include/max31865.h"
    unlisted.parent.mkdir(parents=True, exist_ok=True)
    unlisted.write_bytes(b"/* unrelated edit */\n")
    assert IM.sha256_manifest(tmp_path, IM.T2_INPUTS) == before
    assert IM.unchanged(before, tmp_path)


def test_changed_byte_in_listed_file_changes_manifest(tmp_path):
    _copy_inputs(tmp_path, IM.T2_INPUTS)
    before = IM.sha256_manifest(tmp_path, IM.T2_INPUTS)
    listed = tmp_path / IM.T2_INPUTS[0]
    data = bytearray(listed.read_bytes())
    data[0] ^= 0x01
    listed.write_bytes(bytes(data))
    after = IM.sha256_manifest(tmp_path, IM.T2_INPUTS)
    assert after != before
    assert after[IM.T2_INPUTS[0]] != before[IM.T2_INPUTS[0]]
    assert not IM.unchanged(before, tmp_path)


def test_missing_listed_file_counts_as_changed(tmp_path):
    _copy_inputs(tmp_path, IM.T3_INPUTS)
    recorded = IM.sha256_manifest(tmp_path, IM.T3_INPUTS)
    (tmp_path / IM.T3_INPUTS[-1]).unlink()
    assert not IM.unchanged(recorded, tmp_path)
    assert not IM.unchanged({}, tmp_path)
