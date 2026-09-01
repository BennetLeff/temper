"""Tests for scripts/_lib/drc_ceiling.py -- the shared drc_ceiling.json loader.

The three CI gates (``check_drc_ceiling_approval.py``,
``check_measurement_provenance.py``, ``ci_check_drc.py``) used to each
carry their own ``json.loads`` of the same file. This pins the shared
loader's contract so the "same parsed structure, no behavior change" claim
of the consolidation is verified directly rather than trusted:
``load_ceiling`` returns the raw dict ``json.loads`` returns, raises
``json.JSONDecodeError`` on malformed JSON (each caller formats its own
fail-closed message around that exception), and ``parse_ceiling_text``
parses the ``git show`` merge-base content the approval gate reads from
git history rather than disk.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _lib.drc_ceiling import (  # noqa: E402
    CEILING_RELPATH,
    load_ceiling,
    parse_ceiling_text,
)


def test_ceiling_relpath_is_the_one_file_all_gates_read():
    assert CEILING_RELPATH == "power_pcb_dataset/drc_ceiling.json"


def test_load_ceiling_returns_the_raw_parsed_dict(tmp_path):
    payload = {
        "_goal": "error_ceiling: 0",
        "_march": {"2026-07-27": "entry"},
        "boards": [{"board_id": "b", "error_ceiling": 7}],
    }
    path = tmp_path / "drc_ceiling.json"
    path.write_text(json.dumps(payload))
    assert load_ceiling(path) == payload


def test_load_ceiling_matches_bare_json_loads(tmp_path):
    """The consolidation's core claim: the shared loader returns exactly
    what each gate's historic inline ``json.loads`` returned."""
    path = tmp_path / "drc_ceiling.json"
    path.write_text(json.dumps({"boards": [{"board_id": "b"}]}))
    assert load_ceiling(path) == json.loads(path.read_text())


def test_load_ceiling_raises_json_decode_error_on_malformed(tmp_path):
    path = tmp_path / "drc_ceiling.json"
    path.write_text("{ not: valid json ]")
    with pytest.raises(json.JSONDecodeError):
        load_ceiling(path)


def test_parse_ceiling_text_parses_git_show_content():
    # The approval gate reads the merge-base snapshot as `git show`
    # output (a string), not a file.
    assert parse_ceiling_text('{"boards": [{"board_id": "x"}]}') == {
        "boards": [{"board_id": "x"}]
    }


def test_parse_ceiling_text_raises_json_decode_error_on_malformed():
    with pytest.raises(json.JSONDecodeError):
        parse_ceiling_text("{ nope")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
