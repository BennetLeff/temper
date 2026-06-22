"""Tests for parasitic netlist injection engine."""

from __future__ import annotations

from pathlib import Path

import pytest
from tools.spice.extract import ExtractionResult, ParasiticValues
from tools.spice.inject_parasitics import inject_parasitics

MINIMAL_TEMPLATE = """\
* Test template
* @PEEC_MODE: G3_hand_calculated
.options reltol=1e-3
.options abstol=1e-9

.param VDC=320
.param F_SW=40k
.param VGE_ON=15

* INCLUDE MODELS
.include ../models/test.lib

V_dcbus vbus 0 DC {VDC}

V_pwm_hi gate_hi_in gnd_hi PWL(0 0 1u {VGE_ON})

R_gate_hi gate_hi_in gate_hi 5

X_Q1 vbus gate_hi midpoint TEST_IGBT

.control
run
quit
.endc

.end
"""


@pytest.fixture
def template_file(tmp_path: Path) -> Path:
    p = tmp_path / "template.cir"
    p.write_text(MINIMAL_TEMPLATE)
    return p


@pytest.fixture
def extraction_result() -> ExtractionResult:
    return ExtractionResult(
        pcb_file="test.kicad_pcb",
        nets={
            "GATE_H": ParasiticValues(
                net_name="GATE_H",
                R_mOhm=15.3,
                L_nH=7.2,
                C_pF=2.1,
                loop_group="gate_drive_hs",
            ),
            "DC_BUS+": ParasiticValues(
                net_name="DC_BUS+",
                R_mOhm=8.2,
                L_nH=12.5,
                C_pF=5.3,
                loop_group="dc_bus",
            ),
        },
        loop_groups={
            "gate_drive_hs": ["GATE_H", "GND"],
            "dc_bus": ["DC_BUS+", "DC_BUS-"],
        },
    )


class TestInjectParasitics:
    def test_produces_output(
        self, template_file: Path, extraction_result: ExtractionResult, tmp_path: Path
    ) -> None:
        output = tmp_path / "output.cir"
        inject_parasitics(
            str(template_file), extraction_result, str(output)
        )
        assert output.exists()
        content = output.read_text()
        assert len(content) > 0

    def test_injects_parasitic_params(
        self, template_file: Path, extraction_result: ExtractionResult, tmp_path: Path
    ) -> None:
        output = tmp_path / "output.cir"
        inject_parasitics(str(template_file), extraction_result, str(output))
        content = output.read_text()

        assert "L_GATE_H=7.2n" in content
        assert "R_GATE_H=15.3m" in content

    def test_injects_parasitic_elements(
        self, template_file: Path, extraction_result: ExtractionResult, tmp_path: Path
    ) -> None:
        output = tmp_path / "output.cir"
        inject_parasitics(str(template_file), extraction_result, str(output))
        content = output.read_text()

        assert "R_peec_GATE_H" in content
        assert "L_peec_GATE_H" in content
        assert "LAYOUT PARASITICS" in content

    def test_template_unchanged(
        self, template_file: Path, extraction_result: ExtractionResult, tmp_path: Path
    ) -> None:
        original = template_file.read_text()
        output = tmp_path / "output.cir"
        inject_parasitics(str(template_file), extraction_result, str(output))

        assert template_file.read_text() == original

    def test_includes_original_content(
        self, template_file: Path, extraction_result: ExtractionResult, tmp_path: Path
    ) -> None:
        output = tmp_path / "output.cir"
        inject_parasitics(str(template_file), extraction_result, str(output))
        content = output.read_text()

        assert "X_Q1" in content
        assert "V_dcbus" in content
        assert ".end" in content

    def test_reproducible_output(
        self, template_file: Path, extraction_result: ExtractionResult, tmp_path: Path
    ) -> None:
        output1 = tmp_path / "output1.cir"
        output2 = tmp_path / "output2.cir"

        r1 = inject_parasitics(str(template_file), extraction_result, str(output1))
        r2 = inject_parasitics(str(template_file), extraction_result, str(output2))

        assert r1 == r2

    def test_temp_directive(
        self, template_file: Path, extraction_result: ExtractionResult, tmp_path: Path
    ) -> None:
        output = tmp_path / "output.cir"
        inject_parasitics(
            str(template_file), extraction_result, str(output), temp=125.0
        )
        content = output.read_text()
        assert ".temp 125.0" in content
