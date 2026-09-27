"""Pinned Shapely oracle against a KiCad-exported, production-shaped board."""

import importlib.util
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

UNIT = Path(__file__).resolve().parents[1]
ORACLE = UNIT / "tests/_barrier_check_py_oracle.py"
ORACLE_SHA256 = "393fbfaac772f847f4e05177488ff69a0cda9ea6153e2860e6f2203207704a24"
KICAD_PY = Path(os.environ.get(
    "TEMPER_PCBNEW_PYTHON",
    "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3",
))


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_rust_does_not_underreport_pinned_oracle_on_real_filled_board(tmp_path):
    pytest.importorskip("shapely")
    assert hashlib.sha256(ORACLE.read_bytes()).hexdigest() == ORACLE_SHA256
    if not KICAD_PY.is_file():
        pytest.skip("KiCad pcbnew Python is not installed")
    board = UNIT / "native-09" / "section.kicad_pcb"
    evidence_path = tmp_path / "copper.json"
    result = subprocess.run(
        [str(KICAD_PY), str(UNIT / "tools/copper_dump.py"), str(board), str(evidence_path)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    evidence = json.loads(evidence_path.read_text())
    assert {item["kind"] for item in evidence["items"]} == {"pad", "track", "via", "zone"}
    current = load(UNIT / "tools/barrier_check.py", "rust_barrier_adapter")
    oracle = load(ORACLE, "legacy_barrier_oracle")
    for floor in (8.0, 10.0):
        observed = current.check(evidence, floor)
        reference = oracle.check(evidence, floor)
        # GEOS buffers polygonize circles/capsules inside their exact outer
        # boundary; exact Rust geometry may conservatively report more pairs.
        assert observed["violations"] >= reference["violations"]
        assert observed["cross_layer"] >= reference["cross_layer"]
    assert oracle.check(evidence, 10.0)["violations"] > 0
