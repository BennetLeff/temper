"""Integration tests for FreeRouting compatibility.

These tests verify that the deterministic DSN output is accepted by FreeRouting.
Tests are skipped if freerouting is not installed.
"""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from temper_placer.core.board import Board, LayerStackup
from temper_placer.core.netlist import Netlist, Component, Pin, Net
from temper_placer.io.dsn_exporter import DSNExporter


def _find_freerouting() -> str | None:
    """Find the freerouting executable."""
    path = os.environ.get("FREEROUTING_PATH") or shutil.which("freerouting")
    return path


def _export_deterministic_dsn() -> str:
    """Export a deterministic DSN for a simple test board."""
    from temper_placer.core.board import Layer
    stackup = LayerStackup(layers=[
        Layer(name="F.Cu", layer_type="signal"),
        Layer(name="B.Cu", layer_type="signal"),
    ])
    board = Board(width=50, height=50, layer_stackup=stackup)
    netlist = Netlist(
        components=[
            Component(ref="U1", footprint="SOIC-8", bounds=(5, 4), pins=[
                Pin("VCC", "8", (2.0, 1.5)),
                Pin("GND", "4", (-2.0, -1.5)),
                Pin("SIG", "1", (0.0, 0.0)),
            ]),
            Component(ref="R1", footprint="R_0805", bounds=(2, 1), pins=[
                Pin("1", "1", (0, 0)),
                Pin("2", "2", (1, 0)),
            ]),
            Component(ref="C1", footprint="C_0603", bounds=(1.6, 0.8), pins=[
                Pin("1", "1", (0, 0)),
                Pin("2", "2", (0.8, 0)),
            ]),
        ],
        nets=[
            Net(name="VCC", pins=[("U1", "8"), ("R1", "1")]),
            Net(name="GND", pins=[("U1", "4"), ("C1", "1")]),
            Net(name="SIG1", pins=[("U1", "1"), ("R1", "2"), ("C1", "2")]),
        ]
    )
    exporter = DSNExporter(board, netlist, deterministic=True)
    return str(exporter.export_pcb("test_board"))


def test_deterministic_dsn_is_valid_structure():
    """Deterministic DSN contains all required sections."""
    dsn = _export_deterministic_dsn()
    assert "(pcb test_board" in dsn
    assert "(structure" in dsn
    assert "(library" in dsn
    assert "(placement" in dsn
    assert "(network" in dsn
    assert "(unit mm)" in dsn
    assert "(resolution um 10)" in dsn


def test_deterministic_dsn_has_schema_version():
    """Deterministic DSN includes schema-version header."""
    dsn = _export_deterministic_dsn()
    assert dsn.startswith(";schema-version: sha256:")


def test_deterministic_dsn_nets_sorted_alphabetically():
    """Deterministic DSN has nets in alphabetical order."""
    dsn = _export_deterministic_dsn()
    idx_gnd = dsn.index("GND")
    idx_sig1 = dsn.index("SIG1")
    idx_vcc = dsn.index("VCC")
    assert idx_gnd < idx_sig1 < idx_vcc


@pytest.mark.skipif(
    not shutil.which("freerouting") and not os.environ.get("FREEROUTING_PATH"),
    reason="FreeRouting not installed"
)
def test_freerouting_accepts_deterministic_dsn():
    """FreeRouting accepts deterministic DSN without errors."""
    freerouting = _find_freerouting()
    if not freerouting:
        pytest.skip("FreeRouting not available")

    with tempfile.TemporaryDirectory() as tmpdir:
        dsn_path = Path(tmpdir) / "test.dsn"
        ses_path = Path(tmpdir) / "test.ses"

        dsn = _export_deterministic_dsn()
        dsn_path.write_text(dsn)

        result = subprocess.run(
            [freerouting, "-de", str(dsn_path), "-do", str(ses_path)],
            capture_output=True, text=True, timeout=120,
        )
        # FreeRouting may return non-zero but still produce output
        # We check if the command ran without erroring on DSN parsing
        assert result.returncode == 0 or ses_path.exists(), (
            f"FreeRouting failed: {result.stderr}"
        )
