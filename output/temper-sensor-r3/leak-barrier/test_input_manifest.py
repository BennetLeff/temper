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


ALL_STUDIES = ("T2_INPUTS", "T3_INPUTS", "F1_INPUTS", "T1_INPUTS")
# Firmware sources that no F1 or T1 input compiles or reads (the broad control/sensor globs hit them).
UNUSED_BY_F1_T1 = (
    "firmware/components/control/pll_control.c",
    "firmware/components/control/pan_detect.c",
    "firmware/components/control/low_temp_control.c",
)


def test_listed_inputs_exist():
    for name in ALL_STUDIES:
        for rel in getattr(IM, name):
            assert (REPO / rel).is_file(), (name, rel)


def test_f1_and_t1_lists_exclude_unused_control_sources():
    for name in ("F1_INPUTS", "T1_INPUTS"):
        for rel in UNUSED_BY_F1_T1:
            assert rel not in getattr(IM, name), (name, rel)
    assert "output/temper-sensor-r3/firmware/cosim_shim.c" in IM.F1_INPUTS
    assert "output/temper-sensor-r3/firmware/cosim_shim.c" in IM.C_LIBRARY


def test_touching_pll_control_leaves_f1_and_t1_manifests_unchanged(tmp_path):
    for name in ("F1_INPUTS", "T1_INPUTS"):
        inputs = getattr(IM, name)
        _copy_inputs(tmp_path, inputs)
        before = IM.sha256_manifest(tmp_path, inputs)
        unlisted = tmp_path / "firmware/components/control/pll_control.c"
        unlisted.parent.mkdir(parents=True, exist_ok=True)
        unlisted.write_bytes(b"/* unrelated edit */\n")
        assert IM.sha256_manifest(tmp_path, inputs) == before, name
        assert IM.unchanged(before, tmp_path), name
        unlisted.unlink()


def test_flipped_byte_in_f1_library_source_changes_f1_manifest(tmp_path):
    rel = "firmware/components/control/contact_check.c"   # in C_LIBRARY, so in F1_INPUTS
    assert rel in IM.F1_INPUTS
    _copy_inputs(tmp_path, IM.F1_INPUTS)
    before = IM.sha256_manifest(tmp_path, IM.F1_INPUTS)
    target = tmp_path / rel
    data = bytearray(target.read_bytes())
    data[0] ^= 0x01
    target.write_bytes(bytes(data))
    assert IM.sha256_manifest(tmp_path, IM.F1_INPUTS)[rel] != before[rel]
    assert not IM.unchanged(before, tmp_path)


def test_flipped_byte_in_t1_rtd_source_changes_t1_manifest(tmp_path):
    rel = "firmware/components/sensors/rtd_convert.c"
    assert rel in IM.T1_INPUTS
    _copy_inputs(tmp_path, IM.T1_INPUTS)
    before = IM.sha256_manifest(tmp_path, IM.T1_INPUTS)
    target = tmp_path / rel
    data = bytearray(target.read_bytes())
    data[0] ^= 0x01
    target.write_bytes(bytes(data))
    assert IM.sha256_manifest(tmp_path, IM.T1_INPUTS)[rel] != before[rel]
    assert not IM.unchanged(before, tmp_path)


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
