"""Tests for MFEM corroboration gate (U4)."""

from __future__ import annotations

import pytest

from temper_placer.placer.cp_sat.gates import GateStatus
from temper_placer.validation.mfem_gate import MFEMCorroborationGate


class MockBoardState:
    board = None
    netlist = None


def test_gate_unmeasured_when_binary_absent():
    """The gate returns UNMEASURED when the MFEM binary is missing."""
    gate = MFEMCorroborationGate(
        fdm_config=_mock_fdm_config(),
        devices={"Q1": (5, 3)},
        binary_path="/nonexistent/path/ex1",
    )
    result = gate.check(MockBoardState())
    assert result.status is GateStatus.UNMEASURED
    assert "not available" in (result.error_message or "")


class MockFDMConfig:
    cell_size_mm = 1.0
    origin_mm = (0.0, 0.0)
    height_cells = 10
    width_cells = 10
    ambient_C = 40.0
    heatsink_edge = "BOTTOM"


def _mock_fdm_config():
    return MockFDMConfig()


class MockBoard:
    width = 100.0
    height = 150.0
    keepouts = []

    class _Stackup:
        thickness = 1.6
        layers = []

    layer_stackup = _Stackup()


# ---------------------------------------------------------------------------
# Integration — requires real MFEM binary
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    True,  # placeholder — gate test with real MFEM is a follow-up integration test
    reason="real MFEM gate integration deferred",
)
def test_gate_integration_real_mfem():
    """The gate produces CLEAN or VIOLATIONS when MFEM is available."""
    pass
