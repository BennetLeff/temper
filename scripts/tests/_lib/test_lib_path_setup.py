"""Tests for _lib.path_setup."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from _lib.path_setup import setup_temper_placer_path


def test_inserts_when_not_present(tmp_path):
    src = tmp_path / "packages" / "temper-placer" / "src"
    src.mkdir(parents=True)
    path_str = str(src)
    if path_str in sys.path:
        sys.path.remove(path_str)
    setup_temper_placer_path(tmp_path)
    assert path_str in sys.path


def test_noop_when_already_present(tmp_path):
    src = tmp_path / "packages" / "temper-placer" / "src"
    src.mkdir(parents=True)
    path_str = str(src)
    if path_str in sys.path:
        sys.path.remove(path_str)
    sys.path.insert(0, path_str)
    before = list(sys.path)
    setup_temper_placer_path(tmp_path)
    assert sys.path == before


def test_handles_nonexistent_directory(tmp_path):
    src = tmp_path / "packages" / "temper-placer" / "src"
    path_str = str(src)
    if path_str in sys.path:
        sys.path.remove(path_str)
    assert not src.exists()
    setup_temper_placer_path(tmp_path)
    assert path_str in sys.path


def test_inserts_absolute_path_when_relative_exists(tmp_path):
    src = tmp_path / "packages" / "temper-placer" / "src"
    src.mkdir(parents=True)
    abs_path = str(src)
    if abs_path in sys.path:
        sys.path.remove(abs_path)
    rel = os.path.relpath(abs_path)
    if rel in sys.path:
        sys.path.remove(rel)
    sys.path.insert(0, rel)
    setup_temper_placer_path(tmp_path)
    assert abs_path in sys.path
    assert Path(rel).resolve() == Path(abs_path).resolve()
