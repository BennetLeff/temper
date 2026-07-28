"""Tests for _lib.measurement_provenance.

Covers the content-hash freshness oracle (sha256_file / check_inputs_fresh),
the provenance-record builder (build_provenance), and shape validation
(validate_provenance_shape) in isolation from the CI gate that consumes
them (scripts/tests/test_check_measurement_provenance.py).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _lib.measurement_provenance import (  # noqa: E402
    InputMismatch,
    build_provenance,
    check_inputs_fresh,
    sha256_file,
    validate_provenance_shape,
)

VALID_SHA = "a" * 64
VALID_COMMIT = "b" * 40


# ---------------------------------------------------------------------------
# sha256_file
# ---------------------------------------------------------------------------


def test_sha256_file_deterministic(tmp_path):
    f = tmp_path / "board.txt"
    f.write_text("hello world")
    assert sha256_file(f) == sha256_file(f)


def test_sha256_file_changes_with_content(tmp_path):
    f = tmp_path / "board.txt"
    f.write_text("version 1")
    h1 = sha256_file(f)
    f.write_text("version 2")
    h2 = sha256_file(f)
    assert h1 != h2


def test_sha256_file_missing_raises(tmp_path):
    import pytest

    with pytest.raises(OSError):
        sha256_file(tmp_path / "does-not-exist.txt")


# ---------------------------------------------------------------------------
# check_inputs_fresh
# ---------------------------------------------------------------------------


def test_check_inputs_fresh_matching_hash_is_fresh(tmp_path):
    board = tmp_path / "pcb" / "board.kicad_pcb"
    board.parent.mkdir()
    board.write_text("(kicad_pcb v1)")
    recorded = sha256_file(board)

    mismatches = check_inputs_fresh(tmp_path, [{"path": "pcb/board.kicad_pcb", "sha256": recorded}])
    assert mismatches == []


def test_check_inputs_fresh_changed_content_is_stale(tmp_path):
    board = tmp_path / "pcb" / "board.kicad_pcb"
    board.parent.mkdir()
    board.write_text("(kicad_pcb v1)")
    recorded = sha256_file(board)

    board.write_text("(kicad_pcb v2 -- routed)")  # content moved after measurement
    mismatches = check_inputs_fresh(tmp_path, [{"path": "pcb/board.kicad_pcb", "sha256": recorded}])

    assert len(mismatches) == 1
    m = mismatches[0]
    assert isinstance(m, InputMismatch)
    assert m.path == "pcb/board.kicad_pcb"
    assert m.recorded_sha256 == recorded
    assert m.current_sha256 != recorded
    assert "moved" in m.reason


def test_check_inputs_fresh_missing_file_is_a_mismatch(tmp_path):
    mismatches = check_inputs_fresh(
        tmp_path, [{"path": "pcb/gone.kicad_pcb", "sha256": VALID_SHA}]
    )
    assert len(mismatches) == 1
    assert mismatches[0].current_sha256 is None
    assert "no longer exists" in mismatches[0].reason


def test_check_inputs_fresh_one_bad_input_does_not_hide_the_rest(tmp_path):
    good = tmp_path / "good.txt"
    good.write_text("stable")
    recorded_good = sha256_file(good)

    mismatches = check_inputs_fresh(
        tmp_path,
        [
            {"path": "good.txt", "sha256": recorded_good},
            {"path": "missing.txt", "sha256": VALID_SHA},
        ],
    )
    assert len(mismatches) == 1
    assert mismatches[0].path == "missing.txt"


def test_check_inputs_fresh_malformed_entry_reported_not_raised(tmp_path):
    mismatches = check_inputs_fresh(tmp_path, [{"path": "x.txt"}])  # missing sha256
    assert len(mismatches) == 1
    assert "malformed" in mismatches[0].reason


# ---------------------------------------------------------------------------
# validate_provenance_shape
# ---------------------------------------------------------------------------


def _valid_prov(**overrides):
    base = {
        "measured_at_commit": VALID_COMMIT,
        "dirty": False,
        "inputs": [{"path": "a.txt", "sha256": VALID_SHA}],
        "tool_versions": {},
        "source": "measured-live",
    }
    base.update(overrides)
    return base


def test_validate_provenance_shape_accepts_valid_record():
    assert validate_provenance_shape(_valid_prov()) is None


def test_validate_provenance_shape_accepts_unknown_commit_and_dirty():
    assert validate_provenance_shape(_valid_prov(measured_at_commit="UNKNOWN", dirty="UNKNOWN")) is None


def test_validate_provenance_shape_rejects_bad_commit_shape():
    err = validate_provenance_shape(_valid_prov(measured_at_commit="not-a-sha"))
    assert err is not None and "measured_at_commit" in err


def test_validate_provenance_shape_rejects_bad_dirty_value():
    err = validate_provenance_shape(_valid_prov(dirty="maybe"))
    assert err is not None and "dirty" in err


def test_validate_provenance_shape_rejects_empty_inputs():
    err = validate_provenance_shape(_valid_prov(inputs=[]))
    assert err is not None and "inputs" in err


def test_validate_provenance_shape_rejects_missing_inputs_key():
    prov = _valid_prov()
    del prov["inputs"]
    err = validate_provenance_shape(prov)
    assert err is not None and "inputs" in err


def test_validate_provenance_shape_rejects_bad_source():
    err = validate_provenance_shape(_valid_prov(source="freshly-vibed"))
    assert err is not None and "source" in err


def test_validate_provenance_shape_rejects_non_dict_tool_versions():
    err = validate_provenance_shape(_valid_prov(tool_versions=["kicad-cli 10.0.5"]))
    assert err is not None and "tool_versions" in err


# ---------------------------------------------------------------------------
# build_provenance
# ---------------------------------------------------------------------------


def test_build_provenance_hashes_every_declared_input(tmp_path):
    (tmp_path / "a.txt").write_text("aaa")
    (tmp_path / "b.txt").write_text("bbb")

    prov = build_provenance(tmp_path, ["a.txt", "b.txt"], tool_versions={"kicad-cli": "10.0.5"})

    assert prov["source"] == "measured-live"
    assert prov["tool_versions"] == {"kicad-cli": "10.0.5"}
    paths = {entry["path"] for entry in prov["inputs"]}
    assert paths == {"a.txt", "b.txt"}
    for entry in prov["inputs"]:
        assert entry["sha256"] == sha256_file(tmp_path / entry["path"])
    # tmp_path is not a git repo -- commit/dirty/branch must degrade to
    # UNKNOWN rather than raising (see _lib.provenance's own contract).
    assert prov["measured_at_commit"] == "UNKNOWN"
    assert prov["dirty"] == "UNKNOWN"


def test_build_provenance_missing_input_raises(tmp_path):
    import pytest

    with pytest.raises(OSError):
        build_provenance(tmp_path, ["does-not-exist.txt"])
