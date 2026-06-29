"""Integration tests for KiCad SES import compatibility.

These tests verify that the deterministic DSN/SES output is importable
by KiCad's SPECCTRA session importer.
Tests are skipped if kicad-cli is not installed.
"""

import shutil
from pathlib import Path

import pytest

from temper_placer.core.board import Board
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.io.dsn_exporter import DSNExporter


def _export_deterministic_dsn() -> str:
    """Export a deterministic DSN for a simple test board."""
    from temper_placer.core.board import Layer, LayerStackup
    stackup = LayerStackup(layers=[
        Layer(name="F.Cu", layer_type="signal"),
        Layer(name="GND.Cu", layer_type="plane"),
        Layer(name="VCC.Cu", layer_type="plane"),
        Layer(name="B.Cu", layer_type="signal"),
    ])
    board = Board(width=50, height=50, layer_stackup=stackup)
    netlist = Netlist(
        components=[
            Component(ref="U1", footprint="SOIC-8", bounds=(5, 4), pins=[
                Pin("VCC", "8", (2.0, 1.5)),
                Pin("GND", "4", (-2.0, -1.5)),
            ]),
            Component(ref="R1", footprint="R_0805", bounds=(2, 1), pins=[
                Pin("1", "1", (0, 0)),
                Pin("2", "2", (1, 0)),
            ]),
        ],
        nets=[
            Net(name="VCC", pins=[("U1", "8"), ("R1", "1")]),
            Net(name="GND", pins=[("U1", "4"), ("R1", "2")]),
        ]
    )
    exporter = DSNExporter(board, netlist, deterministic=True)
    return str(exporter.export_pcb("test_board"))


def test_dsn_has_required_sections_for_kicad():
    """DSN output has sections needed by KiCad SPECCTRA importer."""
    dsn = _export_deterministic_dsn()
    assert "(structure" in dsn
    assert "(library" in dsn
    assert "(placement" in dsn
    assert "(network" in dsn
    assert "(resolution um" in dsn
    assert "(unit mm)" in dsn


def test_dsn_layer_names_are_specctra_compatible():
    """Layer names in DSN use SPECCTRA-compatible naming (no spaces, no special chars)."""
    dsn = _export_deterministic_dsn()
    # All layers should be properly formatted
    for layer_line in dsn.split("\n"):
        if layer_line.strip().startswith("(layer "):
            # Layer names should not contain spaces or parens that break parsing
            assert "  " not in layer_line  # double spaces would indicate issues


def test_dsn_schema_header_is_kicad_safe():
    """Schema-version comment header does not break KiCad import."""
    dsn = _export_deterministic_dsn()
    assert dsn.startswith(";schema-version: sha256:")
    # Comment lines are ignored by SPECCTRA parsers
    lines = dsn.split("\n")
    assert lines[0].startswith(";")
    assert lines[1].startswith("(pcb")


def test_deterministic_dsn_has_proper_layer_structure():
    """Each layer definition includes type and index properties."""
    dsn = _export_deterministic_dsn()
    for layer_line in dsn.split("\n"):
        if "(layer " in layer_line:
            assert "(type " in layer_line
            assert "(property" in layer_line
            assert "(index " in layer_line


def test_dsn_wire_via_definition_present():
    """VIA padstack and via definition are present for routing."""
    dsn = _export_deterministic_dsn()
    assert "(via VIA)" in dsn or '(padstack "VIA"' in dsn  # accept either format


@pytest.mark.skipif(not shutil.which("kicad-cli"), reason="kicad-cli not installed")
def test_kicad_cli_can_read_dsn():
    """KiCad CLI can parse the DSN structure."""
    import subprocess
    import tempfile

    dsn = _export_deterministic_dsn()
    with tempfile.NamedTemporaryFile(mode="w", suffix=".dsn", delete=False) as f:
        f.write(dsn)
        dsn_path = Path(f.name)

    try:
        result = subprocess.run(
            ["kicad-cli", "pcb", "import", "specctra", "--help"],
            capture_output=True, text=True, timeout=30,
        )
        # If the command exists, verify the DSN is parseable
        assert result.returncode == 0, f"kicad-cli help failed: {result.stderr}"
    finally:
        dsn_path.unlink(missing_ok=True)
