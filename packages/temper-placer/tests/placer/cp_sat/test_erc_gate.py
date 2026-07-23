"""Tests for ErcGate three-state measurement discipline.

Covers plan 2026-07-23-001 U2: ``ErcGate`` invokes ``kicad-cli pcb erc``,
parses the JSON output, and returns CLEAN / VIOLATIONS / UNMEASURED
mirroring DrcGate's shape.  kicad-cli is mocked so tests are fast and
deterministic; fail-closed ``UNMEASURED`` is the regression test for the
project's anti-false-zero discipline.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from temper_placer.placer.cp_sat.gates import (
    BoardState,
    ErcGate,
    GateStatus,
    _resolve_kicad_footprint_dir,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_pcb() -> Path:
    """Write a minimal stub PCB file for testing."""
    with tempfile.NamedTemporaryFile(suffix=".kicad_pcb", mode="w", delete=False) as tmp:
        tmp.write("(kicad_pcb)\n")
    return Path(tmp.name)


def _fake_run_factory(
    returncode: int,
    payload: dict | None,
    stderr: str = "",
    output_key: str = "violations",
):
    """Build a subprocess.run replacement that writes ERC JSON to -o path.

    *payload*, when not None, is serialized under *output_key* (``violations``
    or ``items`` to exercise both KiCad version formats).
    """

    def fake_run(cmd, **kwargs):
        if payload is not None:
            out_idx = cmd.index("-o") + 1
            Path(cmd[out_idx]).write_text(json.dumps({output_key: payload}))
        return subprocess.CompletedProcess(cmd, returncode, stdout="", stderr=stderr)

    return fake_run


# ---------------------------------------------------------------------------
# Unit: ErcGate.check() — three-state measurement
# ---------------------------------------------------------------------------


class TestErcGateCheck:
    """Direct unit tests for ``ErcGate.check()``."""

    def test_erc_clean(self, monkeypatch):
        """Zero ERC violations returns CLEAN."""
        pcb = _write_pcb()
        monkeypatch.setattr(subprocess, "run", _fake_run_factory(0, []))
        try:
            result = ErcGate().check(BoardState(routed_pcb_path=pcb))
        finally:
            pcb.unlink(missing_ok=True)

        assert result.status is GateStatus.CLEAN
        assert result.violations == ()
        assert result.error_message == ""

    def test_erc_violations(self, monkeypatch):
        """N ERC violations returns VIOLATIONS with the count."""
        pcb = _write_pcb()
        payload = [
            {"type": "unconnected_pin", "description": "Pin 1 of U1 is unconnected"},
            {"type": "conflicting_outputs", "description": "Outputs conflict on net DATA"},
        ]
        monkeypatch.setattr(subprocess, "run", _fake_run_factory(0, payload))
        try:
            result = ErcGate().check(BoardState(routed_pcb_path=pcb))
        finally:
            pcb.unlink(missing_ok=True)

        assert result.status is GateStatus.VIOLATIONS
        assert len(result.violations) == 2
        assert result.violations[0].description == "Pin 1 of U1 is unconnected"
        assert result.violations[1].description == "Outputs conflict on net DATA"

    def test_erc_items_key(self, monkeypatch):
        """ERC output using ``items`` key (KiCad version variation)."""
        pcb = _write_pcb()
        payload = [
            {"type": "missing_power", "message": "Power pin not driven"},
        ]
        monkeypatch.setattr(
            subprocess, "run", _fake_run_factory(0, payload, output_key="items")
        )
        try:
            result = ErcGate().check(BoardState(routed_pcb_path=pcb))
        finally:
            pcb.unlink(missing_ok=True)

        assert result.status is GateStatus.VIOLATIONS
        assert len(result.violations) == 1
        assert result.violations[0].description == "Power pin not driven"

    def test_erc_cli_unavailable(self, monkeypatch):
        """kicad-cli not on PATH returns UNMEASURED (fail-closed)."""
        pcb = _write_pcb()

        def raise_fnf(*_a, **_k):
            raise FileNotFoundError("kicad-cli")

        monkeypatch.setattr(subprocess, "run", raise_fnf)
        try:
            result = ErcGate().check(BoardState(routed_pcb_path=pcb))
        finally:
            pcb.unlink(missing_ok=True)

        assert result.status is GateStatus.UNMEASURED
        assert "unavailable" in result.error_message.lower()

    def test_erc_missing_pcb(self):
        """No PCB file returns UNMEASURED, not CLEAN."""
        result = ErcGate().check(BoardState(routed_pcb_path=None))
        assert result.status is GateStatus.UNMEASURED
        assert result.error_message

    def test_erc_nonexistent_pcb(self):
        """Non-existent PCB path returns UNMEASURED."""
        result = ErcGate().check(
            BoardState(routed_pcb_path=Path("/nonexistent/board.kicad_pcb"))
        )
        assert result.status is GateStatus.UNMEASURED
        assert result.error_message

    def test_erc_cli_exit_nonzero(self, monkeypatch):
        """kicad-cli exits with non-zero returns UNMEASURED."""
        pcb = _write_pcb()
        monkeypatch.setattr(
            subprocess, "run", _fake_run_factory(3, None, stderr="parse error")
        )
        try:
            result = ErcGate().check(BoardState(routed_pcb_path=pcb))
        finally:
            pcb.unlink(missing_ok=True)

        assert result.status is GateStatus.UNMEASURED
        assert "exit 3" in result.error_message

    def test_erc_no_output_file(self, monkeypatch):
        """kicad-cli returns 0 but produces no output file → UNMEASURED."""
        pcb = _write_pcb()

        def fake_run_no_output(cmd, **kwargs):
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", fake_run_no_output)
        try:
            result = ErcGate().check(BoardState(routed_pcb_path=pcb))
        finally:
            pcb.unlink(missing_ok=True)

        assert result.status is GateStatus.UNMEASURED
        assert "no" in result.error_message.lower() and "erc" in result.error_message.lower() and "output" in result.error_message.lower()

    def test_erc_footprint_dir_missing(self, monkeypatch):
        """When fp-lib-table is unresolvable, gate fails closed as UNMEASURED."""
        monkeypatch.setattr(
            "temper_placer.placer.cp_sat.gates._resolve_kicad_footprint_dir",
            lambda: None,
        )

        pcb = _write_pcb()
        try:
            result = ErcGate().check(BoardState(routed_pcb_path=pcb))
        finally:
            pcb.unlink(missing_ok=True)

        assert result.status is GateStatus.UNMEASURED, (
            "Gate must be UNMEASURED when footprint dir is missing — "
            "not CLEAN (false-zero regression)."
        )
        assert "footprint library directory not found" in result.error_message.lower()


# ---------------------------------------------------------------------------
# Integration: ErcGate invokes kicad-cli with correct args
# ---------------------------------------------------------------------------


class TestErcGateInvocation:
    """Verify subprocess.run is called with the right arguments."""

    def test_invokes_kicad_cli_pcb_erc(self, monkeypatch):
        """subprocess.run receives kicad-cli pcb erc ..."""
        pcb = _write_pcb()
        captured: list[list[str]] = []

        def capture_run(cmd, **kwargs):
            captured.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", capture_run)
        try:
            ErcGate().check(BoardState(routed_pcb_path=pcb))
        finally:
            pcb.unlink(missing_ok=True)

        assert len(captured) == 1
        cmd = captured[0]
        # args: kicad-cli pcb erc --format json -o <out> <board>
        assert "kicad-cli" in cmd[0] or cmd[0].endswith("kicad-cli")
        assert cmd[1:3] == ["pcb", "erc"]
        assert "--format" in cmd
        json_idx = cmd.index("--format")
        assert cmd[json_idx + 1] == "json"

    def test_uses_fp_lib_dir_env(self, monkeypatch):
        """ErcGate passes KICAD7_FOOTPRINT_DIR in the subprocess env."""
        monkeypatch.setenv("KICAD7_FOOTPRINT_DIR", "/custom/fp")

        pcb = _write_pcb()
        captured_env: dict[str, str] | None = None

        def capture_run(cmd, **kwargs):
            nonlocal captured_env
            captured_env = kwargs.get("env", {})
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        monkeypatch.setattr(subprocess, "run", capture_run)
        try:
            ErcGate().check(BoardState(routed_pcb_path=pcb))
        finally:
            pcb.unlink(missing_ok=True)

        assert captured_env is not None
        assert captured_env.get("KICAD7_FOOTPRINT_DIR") == "/custom/fp"


class TestErcGateMetadata:
    """Gate contract metadata checks."""

    def test_stage_and_name(self):
        gate = ErcGate()
        assert gate.stage.value == "routing"
        assert gate.name == "erc"

    def test_clean_and_unmeasured_are_distinct(self):
        """Empty violations means two different things depending on status."""
        from temper_placer.placer.cp_sat.gates import GateResult

        clean = GateResult(GateStatus.CLEAN)
        unmeasured = GateResult(GateStatus.UNMEASURED, error_message="tool crashed")
        assert clean.violations == unmeasured.violations == ()
        assert clean.status is not unmeasured.status


# ---------------------------------------------------------------------------
# Unit: _resolve_kicad_footprint_dir (same helper used by ErcGate)
# ---------------------------------------------------------------------------
# U1 regression — the portable path resolution must also work for ErcGate.


class TestResolveFootprintDirForErc:
    """ERC gate reuses _resolve_kicad_footprint_dir() from U1."""

    def test_returns_path_when_env_var_set(self, monkeypatch):
        monkeypatch.setenv("KICAD7_FOOTPRINT_DIR", "/my/fp")
        result = _resolve_kicad_footprint_dir()
        assert result == Path("/my/fp")

    def test_returns_none_when_nothing_found(self, monkeypatch):
        monkeypatch.delenv("KICAD7_FOOTPRINT_DIR", raising=False)
        monkeypatch.setattr(Path, "is_dir", lambda _s: False)
        result = _resolve_kicad_footprint_dir()
        assert result is None
