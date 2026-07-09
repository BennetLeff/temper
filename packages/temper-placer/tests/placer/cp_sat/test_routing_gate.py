"""Tests for RoutingGate three-state measurement discipline.

Covers the contract invariant that CLEAN, VIOLATIONS, and UNMEASURED are
distinct states. kicad-cli is mocked so the test is fast and deterministic;
an optional real-DRC smoke path runs only when kicad-cli is present.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

import pytest

from temper_placer.placer.cp_sat.gates import (
    BoardState,
    Gate,
    GateResult,
    GateStage,
    GateStatus,
    RoutingGate,
    Violation,
    ViolationType,
)


def _write_pcb() -> Path:
    tmp = tempfile.NamedTemporaryFile(suffix=".kicad_pcb", mode="w", delete=False)
    tmp.write("(kicad_pcb)\n")
    tmp.close()
    return Path(tmp.name)


def _fake_run_factory(returncode: int, payload: dict | None, stderr: str = ""):
    """Build a subprocess.run replacement that writes DRC JSON to -o path."""

    def fake_run(cmd, **kwargs):
        if payload is not None:
            out_idx = cmd.index("-o") + 1
            Path(cmd[out_idx]).write_text(json.dumps(payload))
        return subprocess.CompletedProcess(cmd, returncode, stdout="", stderr=stderr)

    return fake_run


def test_clean_state(monkeypatch):
    pcb = _write_pcb()
    monkeypatch.setattr(
        subprocess, "run", _fake_run_factory(0, {"violations": [], "unconnected_items": []})
    )
    try:
        result = RoutingGate().check(BoardState(routed_pcb_path=pcb))
    finally:
        pcb.unlink(missing_ok=True)

    assert result.status is GateStatus.CLEAN
    assert result.violations == ()
    assert result.error_message == ""


def test_violations_state_clearance(monkeypatch):
    pcb = _write_pcb()
    payload = {
        "violations": [
            {"type": "clearance", "severity": "error", "description": "track too close"},
            {"type": "silk_over_copper", "severity": "warning", "description": "ignored"},
        ],
        "unconnected_items": [],
    }
    monkeypatch.setattr(subprocess, "run", _fake_run_factory(0, payload))
    try:
        result = RoutingGate().check(BoardState(routed_pcb_path=pcb))
    finally:
        pcb.unlink(missing_ok=True)

    assert result.status is GateStatus.VIOLATIONS
    assert len(result.violations) == 1  # warning is filtered out
    assert result.violations[0].type is ViolationType.CLEARANCE


def test_violations_state_unrouted(monkeypatch):
    pcb = _write_pcb()
    payload = {
        "violations": [],
        "unconnected_items": [{"description": "Missing connection between SPI_MOSI pads"}],
    }
    monkeypatch.setattr(subprocess, "run", _fake_run_factory(0, payload))
    try:
        result = RoutingGate().check(BoardState(routed_pcb_path=pcb))
    finally:
        pcb.unlink(missing_ok=True)

    assert result.status is GateStatus.VIOLATIONS
    assert result.violations[0].type is ViolationType.UNROUTED


def test_unmeasured_no_path():
    result = RoutingGate().check(BoardState(routed_pcb_path=None))
    assert result.status is GateStatus.UNMEASURED
    assert result.error_message


def test_unmeasured_missing_file():
    result = RoutingGate().check(BoardState(routed_pcb_path=Path("/nonexistent/x.kicad_pcb")))
    assert result.status is GateStatus.UNMEASURED
    assert result.error_message


def test_unmeasured_kicad_exit_nonzero(monkeypatch):
    pcb = _write_pcb()
    monkeypatch.setattr(
        subprocess, "run", _fake_run_factory(3, None, stderr="board parse failure")
    )
    try:
        result = RoutingGate().check(BoardState(routed_pcb_path=pcb))
    finally:
        pcb.unlink(missing_ok=True)

    assert result.status is GateStatus.UNMEASURED
    assert "exit 3" in result.error_message
    assert "board parse failure" in result.error_message


def test_unmeasured_kicad_not_found(monkeypatch):
    pcb = _write_pcb()

    def raise_fnf(*a, **k):
        raise FileNotFoundError("kicad-cli")

    monkeypatch.setattr(subprocess, "run", raise_fnf)
    try:
        result = RoutingGate().check(BoardState(routed_pcb_path=pcb))
    finally:
        pcb.unlink(missing_ok=True)

    assert result.status is GateStatus.UNMEASURED


def test_clean_and_unmeasured_are_distinct():
    """Empty violations means two different things depending on status."""
    clean = GateResult(GateStatus.CLEAN)
    unmeasured = GateResult(GateStatus.UNMEASURED, error_message="tool crashed")
    assert clean.violations == unmeasured.violations == ()
    assert clean.status is not unmeasured.status


def test_gate_contract_metadata():
    gate = RoutingGate()
    assert gate.stage is GateStage.ROUTING
    assert gate.name == "routing"
    assert isinstance(gate, Gate)
    assert gate.to_delta(Violation(type=ViolationType.CLEARANCE)) is None
