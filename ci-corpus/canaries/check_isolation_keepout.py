"""Canary fixtures for check_isolation_keepout.py (R42).

Board construction is delegated to ``scripts/tests/test_check_isolation_keepout.py``'s
``build_board``/``write_board``/``write_manifest`` helpers (loaded here by
file path, not imported as a package) so the fixture geometry stays
byte-for-byte identical to the one this gate's own regression suite already
trusts -- a second, drifted copy of "what a minimal valid board looks like"
would itself be a blind spot.
"""

from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEST_MODULE_PATH = _REPO_ROOT / "scripts" / "tests" / "test_check_isolation_keepout.py"


def _load_test_helpers():
    spec = importlib.util.spec_from_file_location("_isolation_keepout_fixtures", _TEST_MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_helpers = _load_test_helpers()


def _state(gate_module, board_path: Path, manifest_path: Path) -> str:
    try:
        state, _report = gate_module.run(board_path, manifest_path)
        return state
    except gate_module.GateError:
        return "error"


def pristine_valid_barrier(gate_module) -> str:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        board_path = _helpers.write_board(root, _helpers.build_board())
        manifest_path = _helpers.write_manifest(root)
        return _state(gate_module, board_path, manifest_path)


def seed_narrow_barrier(gate_module) -> str:
    """Barrier only 2mm wide; MIN_BARRIER_WIDTH_MM requires 8.0mm -- the
    core physical-width safety check this gate exists for."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        board = _helpers.build_board(barrier_x=(49.0, 51.0))
        board_path = _helpers.write_board(root, board)
        manifest_path = _helpers.write_manifest(root)
        return _state(gate_module, board_path, manifest_path)


def seed_missing_barrier(gate_module) -> str:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        board = _helpers.build_board(include_barrier=False)
        board_path = _helpers.write_board(root, board)
        manifest_path = _helpers.write_manifest(root)
        return _state(gate_module, board_path, manifest_path)
