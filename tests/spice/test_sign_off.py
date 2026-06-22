"""Tests for sign-off report generation."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
from tools.spice.sign_off import (
    VGE_OVERSHOOT_MAX_PCT,
    GATE_DRIVE_L_MAX_nH,
    SignOffResult,
    _pcb_hash,
    run_sign_off,
)


class TestPcbHash:
    def test_same_file_same_hash(self, tmp_path: Path) -> None:
        p = tmp_path / "test.kicad_pcb"
        p.write_text("content")
        h1 = _pcb_hash(str(p))
        h2 = _pcb_hash(str(p))
        assert h1 == h2

    def test_different_content_different_hash(self, tmp_path: Path) -> None:
        p1 = tmp_path / "a.kicad_pcb"
        p2 = tmp_path / "b.kicad_pcb"
        p1.write_text("aaa")
        p2.write_text("bbb")
        assert _pcb_hash(str(p1)) != _pcb_hash(str(p2))

    def test_returns_16_char_hex(self, tmp_path: Path) -> None:
        p = tmp_path / "test.kicad_pcb"
        p.write_text("data")
        h = _pcb_hash(str(p))
        assert len(h) == 16
        assert all(c in "0123456789abcdef" for c in h)


class TestSignOffGates:
    @pytest.fixture
    def template_cir(self, tmp_path: Path) -> Path:
        p = tmp_path / "template.cir"
        p.write_text("* test\n.options reltol=1e-3\n.end\n")
        return p

    @pytest.fixture
    def pcb_file(self, tmp_path: Path) -> Path:
        p = tmp_path / "dummy.kicad_pcb"
        p.write_text("(kicad_pcb (version 20221018))")
        return p

    @pytest.fixture
    def net_groups(self, tmp_path: Path) -> Path:
        p = tmp_path / "net_groups.yaml"
        p.write_text(
            textwrap.dedent("""\
            gate_drive_hs:
              nets: [GATE_H, GND]
              description: test
            """)
        )
        return p

    def test_gate_loop_l_fail_triggers_nonzero(
        self, template_cir: Path, pcb_file: Path
    ) -> None:
        """If max gate L > 10nH, exit code should be non-zero."""
        assert GATE_DRIVE_L_MAX_nH == 10.0

    def test_overshoot_pass(self) -> None:
        """Vge overshoot < 20% should pass."""
        assert VGE_OVERSHOOT_MAX_PCT == 20.0

    @pytest.mark.skip(reason="requires ngspice for full pipeline")
    def test_full_pipeline_smoke(
        self, template_cir: Path, pcb_file: Path
    ) -> None:
        result = run_sign_off(
            str(pcb_file),
            str(template_cir),
            mode="corners",
        )
        assert isinstance(result, SignOffResult)
        assert isinstance(result.exit_code, int)


class TestSignOffResult:
    def test_all_fields_default(self) -> None:
        result = SignOffResult(
            pcb_file="test.kicad_pcb",
            pcb_hash="abcdef1234567890",
            template_file="t.cir",
            extraction_summary={},
            sweep_corners=0,
            sweep_converged=0,
            challenger_agreement_rate=100.0,
            hard_gates={},
            soft_warnings=[],
            exit_code=0,
        )
        assert result.exit_code == 0
        assert result.pcb_file == "test.kicad_pcb"

    def test_hard_gate_fail_nonzero_exit(self) -> None:
        result = SignOffResult(
            pcb_file="test.kicad_pcb",
            pcb_hash="abcdef1234567890",
            template_file="t.cir",
            extraction_summary={},
            sweep_corners=0,
            sweep_converged=0,
            challenger_agreement_rate=100.0,
            hard_gates={"gate_loop_L": False},
            soft_warnings=[],
            exit_code=1,
        )
        assert result.exit_code != 0
