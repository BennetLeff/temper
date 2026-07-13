"""Tests for MFEM mesh converter (U2)."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from temper_placer.validation.mfem_mesh import build_temper_mesh


class _MockBoard:
    width = 100.0
    height = 150.0
    keepouts = []

    class _Stackup:
        thickness = 1.6
        layers = []

    layer_stackup = _Stackup()


class _MockConfig:
    cell_size_mm = 1.0
    origin_mm = (0.0, 0.0)
    height_cells = 50
    width_cells = 50
    ambient_C = 40.0
    heatsink_edge = "BOTTOM"


def test_build_mesh_creates_msh():
    """build_temper_mesh produces a non-empty .msh file."""
    board = _MockBoard()
    config = _MockConfig()
    path = build_temper_mesh(board, config, {}, {"Q1": 15.0})
    assert os.path.isfile(path)
    content = Path(path).read_text()
    assert len(content) > 0
    assert "$MeshFormat" in content
    assert "$Nodes" in content


def test_mesh_without_power_map():
    """build_temper_mesh works with an empty power_map."""
    board = _MockBoard()
    config = _MockConfig()
    path = build_temper_mesh(board, config, {})
    assert os.path.isfile(path)


def test_mesh_output_dir_custom():
    """build_temper_mesh respects a custom output_dir."""
    board = _MockBoard()
    config = _MockConfig()
    with tempfile.TemporaryDirectory() as tmp:
        path = build_temper_mesh(board, config, {}, output_dir=tmp)
        assert tmp in path
        assert os.path.isfile(path)
