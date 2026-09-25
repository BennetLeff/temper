"""Native serialization contract, using the committed shelf as a real fixture."""

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

UNIT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "planning_stackup", UNIT / "tools/planning_stackup.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def fixture(tmp_path):
    for name in ("section.kicad_pcb", "source-manifest.json"):
        shutil.copyfile(UNIT / "native-01" / name, tmp_path / name)
    return tmp_path / "section.kicad_pcb"


def test_stackup_projection_retains_source_identity_and_stable_pad_uuids(tmp_path):
    board = fixture(tmp_path)
    MODULE.apply_planning_stackup(tmp_path, UNIT / "stackup.json")
    first = board.read_bytes()
    manifest = json.loads((tmp_path / "source-manifest.json").read_text())
    assert b'"In1.Cu"' not in first
    assert first.count(b'(property "SourceInstance" ') == 91
    assert first.count(b'(property "MPN" ') == 91
    assert first.count(b'(uuid ') == first.count(b'(pad ')
    assert manifest['board_sha256'] == MODULE.sha256(board)
    assert manifest['input_hashes']['stackup.json'] == MODULE.sha256(UNIT / 'stackup.json')
    fixture(tmp_path)
    MODULE.apply_planning_stackup(tmp_path, UNIT / "stackup.json")
    assert board.read_bytes() == first


def test_unsupported_layer_order_leaves_board_and_manifest_untouched(tmp_path):
    board = fixture(tmp_path)
    before = [p.read_bytes() for p in (board, tmp_path / 'source-manifest.json')]
    config = json.loads((UNIT / 'stackup.json').read_text())
    config['layers'].reverse()
    invalid = tmp_path / 'invalid.json'
    invalid.write_text(json.dumps(config))
    with pytest.raises(ValueError, match='layer order'):
        MODULE.apply_planning_stackup(tmp_path, invalid)
    assert [p.read_bytes() for p in (board, tmp_path / 'source-manifest.json')] == before


def test_existing_copper_is_not_rewritten(tmp_path):
    board = fixture(tmp_path)
    board.write_text(board.read_text().replace('(setup', '(segment (start 1 1) (end 2 2))\n  (setup', 1))
    with pytest.raises(ValueError, match='unrouted'):
        MODULE.apply_planning_stackup(tmp_path, UNIT / 'stackup.json')
