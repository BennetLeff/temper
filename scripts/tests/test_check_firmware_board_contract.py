"""Tests for scripts/check_firmware_board_contract.py (plan 2026-08-02-027, U3).

Builds small synthetic repo fixtures under ``tmp_path`` (the repo
convention: the real files are exercised by running the oracle itself, not
by tests that would rot with board churn): a firmware header, a config
YAML, an elec/src/main.ato, a board-derivation registry and a synthetic
``.kicad_pcb``. The fixtures mirror the current board's structure --
outline (20,20)-(172,254), components keyed by Sheetpath, Value "?"
placeholders -- and the defect class is pinned as a test: ``tank.c_tank3``
at (20.0, 272.75) is OFF-OUTLINE and must fail the PLL entry, while a
plain refdes/value lookup would pass it.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "firmware" / "tools"))

from board_component_extractor import BoardParseError  # noqa: E402
from check_firmware_board_contract import (  # noqa: E402
    OracleGateError,
    load_registry,
    run,
)

TANK_CAP_FOOTPRINT = "temper:C_Axial_L34.0mm_D22.5mm_P40.00mm_Horizontal"
R_REF_FOOTPRINT = "Resistor_SMD:R_0805_2012Metric"
OUTLINE = [(20.0, 20.0), (172.0, 20.0), (172.0, 254.0), (20.0, 254.0)]


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text), encoding="utf-8")
    return path


def _pll_header(tmp_path: Path, *, min_hz: int = 44000) -> Path:
    return _write(
        tmp_path / "firmware" / "components" / "control" / "pll_control.h",
        f"""\
        #ifndef PLL_CONTROL_H
        #define PLL_CONTROL_H
        /* unrelated decoy */
        #define FREQ_HYSTERESIS_HZ 10.0f
        #define PLL_MIN_FREQ_HZ {min_hz}   /**< Minimum switching frequency */
        #endif
        """,
    )


def _config_yaml(
    tmp_path: Path,
    *,
    low_word: int = 1526,
    high_word: int = 45722,
    short_ohm: float = 10.0,
    open_ohm: float = 300.0,
) -> Path:
    return _write(
        tmp_path / "firmware" / "config.yaml",
        f"""\
        thresholds:
          - c_symbol: RTD_SHORT_FAULT_OHM
            field: rtd_short_fault_ohm
            value: {short_ohm}
            c_type: float
          - c_symbol: RTD_OPEN_FAULT_OHM
            field: rtd_open_fault_ohm
            value: {open_ohm}
            c_type: float
          - c_symbol: MAX31865_LOW_THRESHOLD_WORD
            field: max31865_low_threshold_word
            value: {low_word}
            c_type: uint16_t
          - c_symbol: MAX31865_HIGH_THRESHOLD_WORD
            field: max31865_high_threshold_word
            value: {high_word}
            c_type: uint16_t
        """,
    )


def _main_ato(
    tmp_path: Path,
    *,
    l_tank: str = "88uH",
    c_tank: str = "300nF",
    ratio: str = "0.68",
    l_tol: str = "0.10",
    c_tol: str = "0.10",
) -> Path:
    return _write(
        tmp_path / "elec" / "src" / "main.ato",
        f"""\
        module Top:
            l_tank_assumed: inductance = {l_tank}
            c_tank_total: capacitance = {c_tank}
            l_pan_loaded_ratio: dimensionless = {ratio}
            l_tank_tolerance: dimensionless = {l_tol}
            c_tank_tolerance: dimensionless = {c_tol}
        """,
    )


def _registry(
    tmp_path: Path,
    *,
    tank_footprint: str = TANK_CAP_FOOTPRINT,
    r_ref_footprint: str = R_REF_FOOTPRINT,
) -> Path:
    """The full 3-entry registry, mirroring firmware/tools/board_derivations.yaml."""
    return _write(
        tmp_path / "firmware" / "tools" / "board_derivations.yaml",
        f"""\
        version: 1
        derivations:
          - constant: PLL_MIN_FREQ_HZ
            firmware_file: firmware/components/control/pll_control.h
            formula: pll_min_freq_hz
            compare: ">="
            description: ZVS floor
            inputs:
              - name: c_tank_total
                provenance: board-derived
                combine: sum
                components:
                  - sheetpath: tank.c_tank1
                    footprint: {tank_footprint}
                    value: 100nF
                  - sheetpath: tank.c_tank2
                    footprint: {tank_footprint}
                    value: 100nF
                  - sheetpath: tank.c_tank3
                    footprint: {tank_footprint}
                    value: 100nF
              - name: l_tank_assumed
                provenance: declared-assumed
                source: elec/src/main.ato
              - name: l_pan_loaded_ratio
                provenance: declared-assumed
                source: elec/src/main.ato
              - name: l_tank_tolerance
                provenance: declared-assumed
                source: elec/src/main.ato
              - name: c_tank_tolerance
                provenance: declared-assumed
                source: elec/src/main.ato
              - name: zvs_margin_min
                provenance: declared-assumed
                source: gate-constant
                value: 1.05
          - constant: MAX31865_LOW_THRESHOLD_WORD
            firmware_file: firmware/config.yaml
            formula: max31865_low_threshold_word
            compare: "=="
            description: low threshold
            inputs:
              - name: rtd_resistance
                provenance: declared-assumed
                source: firmware/config.yaml
                symbol: RTD_SHORT_FAULT_OHM
              - name: r_ref
                provenance: board-derived
                components:
                  - sheetpath: rtd_pan.r_ref
                    footprint: {r_ref_footprint}
                    value: 430ohm
          - constant: MAX31865_HIGH_THRESHOLD_WORD
            firmware_file: firmware/config.yaml
            formula: max31865_high_threshold_word
            compare: "=="
            description: high threshold
            inputs:
              - name: rtd_resistance
                provenance: declared-assumed
                source: firmware/config.yaml
                symbol: RTD_OPEN_FAULT_OHM
              - name: r_ref
                provenance: board-derived
                components:
                  - sheetpath: rtd_pan.r_ref
                    footprint: {r_ref_footprint}
                    value: 430ohm
        """,
    )


def _board(
    tmp_path: Path,
    components: list[tuple[str, str, str, tuple[float, float]]],
    *,
    value_props: dict[str, str] | None = None,
) -> Path:
    value_props = value_props or {}
    pts = " ".join(f"(xy {x} {y})" for x, y in OUTLINE)
    lines = [
        "(kicad_pcb (version 20211014) (generator test)",
        "  (layers (44 \"Edge.Cuts\" user))",
        f"    (gr_poly (pts {pts}) (layer \"Edge.Cuts\") (width 0.1))",
    ]
    for sheetpath, refdes, footprint, (x, y) in components:
        value = value_props.get(sheetpath, "?")
        lines.append(
            f'  (footprint "{footprint}" (version 20231120) (layer "F.Cu")\n'
            f"    (at {x} {y} 0)\n"
            f'    (property "Reference" "{refdes}")\n'
            f'    (property "Value" "{value}")\n'
            f'    (property "Footprint" "{footprint}")\n'
            f'    (property "Sheetpath" "{sheetpath}")\n'
            "    (attr through_hole)\n"
            "  )"
        )
    lines.append(")")
    path = tmp_path / "pcb" / "board.kicad_pcb"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _repo(
    tmp_path: Path,
    *,
    min_hz: int = 44000,
    c_tank: str = "300nF",
    tank_caps: list[tuple[str, str, tuple[float, float]]] | None = None,
    r_ref: tuple[str, tuple[float, float]] | None = (R_REF_FOOTPRINT, (52.6, 250.51)),
    r_ref_value_prop: str | None = None,
) -> Path:
    """Full fixture repo. *tank_caps* defaults to all three placed inside
    the outline; pass a variant to stage one off the board. *r_ref* is
    (footprint, (x, y)); ``None`` omits the component entirely."""
    _pll_header(tmp_path, min_hz=min_hz)
    _config_yaml(tmp_path)
    _main_ato(tmp_path, c_tank=c_tank)
    _registry(tmp_path)

    if tank_caps is None:
        tank_caps = [
            ("tank.c_tank1", "C25", (73.42, 52.00)),
            ("tank.c_tank2", "C26", (59.38, 28.75)),
            ("tank.c_tank3", "C27", (20.0, 254.0)),
        ]
    components = [
        (sheetpath, refdes, TANK_CAP_FOOTPRINT, pos) for sheetpath, refdes, pos in tank_caps
    ]
    value_props: dict[str, str] = {}
    if r_ref is not None:
        footprint, pos = r_ref
        components.append(("rtd_pan.r_ref", "R34", footprint, pos))
        if r_ref_value_prop is not None:
            value_props["rtd_pan.r_ref"] = r_ref_value_prop
    _board(tmp_path, components, value_props=value_props)
    return tmp_path


def _verdicts(report) -> dict[str, str]:
    return {v.constant: v.status for v in report.entries}


class TestHappyPath:
    def test_all_entries_pass_when_board_matches_declarations(self, tmp_path: Path) -> None:
        """U3 test scenario 1: tank caps placed at the declared total and
        the 430 ohm reference on the board -> every registered entry
        re-derives equal to (or above) the firmware constant."""
        repo = _repo(tmp_path)
        report = run(repo, repo / "pcb" / "board.kicad_pcb")
        assert _verdicts(report) == {
            "PLL_MIN_FREQ_HZ": "PASS",
            "MAX31865_LOW_THRESHOLD_WORD": "PASS",
            "MAX31865_HIGH_THRESHOLD_WORD": "PASS",
        }
        assert report.failed == []

    def test_pll_entry_derives_the_floor_from_the_board(self, tmp_path: Path) -> None:
        """The PLL derived value is 43824Hz (1.05 x worst-case loaded
        resonance from the BOARD's placed caps) and firmware 44000 >= it."""
        repo = _repo(tmp_path)
        report = run(repo, repo / "pcb" / "board.kicad_pcb")
        pll = next(v for v in report.entries if v.constant == "PLL_MIN_FREQ_HZ")
        assert pll.derived_value == pytest.approx(43824.0, rel=1e-4)
        assert pll.firmware_value == 44000.0


class TestMissingComponent:
    def test_off_outline_tank_cap_fails_the_pll_entry(self, tmp_path: Path) -> None:
        """U3 test scenario 2 (and the plan's motivating incident): one
        tank cap staged OFF the board (tank.c_tank3 at (20, 272.75),
        outside the outline) -> the PLL entry is MISSING_COMPONENT with
        the constant and the component named. A declared-vs-declared
        check cannot see this; the board oracle can."""
        repo = _repo(
            tmp_path,
            tank_caps=[
                ("tank.c_tank1", "C25", (73.42, 52.00)),
                ("tank.c_tank2", "C26", (59.38, 28.75)),
                ("tank.c_tank3", "C27", (20.0, 272.75)),  # THE DEFECT
            ],
        )
        report = run(repo, repo / "pcb" / "board.kicad_pcb")
        verdicts = _verdicts(report)
        assert verdicts["PLL_MIN_FREQ_HZ"] == "MISSING_COMPONENT"
        assert verdicts["MAX31865_LOW_THRESHOLD_WORD"] == "PASS"
        assert verdicts["MAX31865_HIGH_THRESHOLD_WORD"] == "PASS"

        pll = next(v for v in report.entries if v.constant == "PLL_MIN_FREQ_HZ")
        assert "tank.c_tank3" in pll.detail
        assert "off-outline" in pll.detail.lower() or "OFF-OUTLINE" in pll.detail

    def test_component_absent_from_file_fails_the_pll_entry(self, tmp_path: Path) -> None:
        """A registered component missing from the board FILE entirely is
        the same failure class as off-outline."""
        repo = _repo(
            tmp_path,
            tank_caps=[
                ("tank.c_tank1", "C25", (73.42, 52.00)),
                ("tank.c_tank2", "C26", (59.38, 28.75)),
                # c_tank3 not on the board at all
            ],
        )
        report = run(repo, repo / "pcb" / "board.kicad_pcb")
        assert _verdicts(report)["PLL_MIN_FREQ_HZ"] == "MISSING_COMPONENT"

    def test_missing_r_ref_fails_both_threshold_entries(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path, r_ref=None)
        report = run(repo, repo / "pcb" / "board.kicad_pcb")
        verdicts = _verdicts(report)
        assert verdicts["MAX31865_LOW_THRESHOLD_WORD"] == "MISSING_COMPONENT"
        assert verdicts["MAX31865_HIGH_THRESHOLD_WORD"] == "MISSING_COMPONENT"


class TestValueMismatch:
    def test_wrong_reference_resistor_fails_with_recomputed_words(self, tmp_path: Path) -> None:
        """U3 test scenario 3: a board whose reference resistor differs
        from 430 ohm (here a self-describing Value of 500 ohm) fails both
        threshold-word entries with the recomputed words named."""
        repo = _repo(
            tmp_path,
            r_ref=(R_REF_FOOTPRINT, (52.6, 250.51)),
            r_ref_value_prop="500ohm",
        )
        report = run(repo, repo / "pcb" / "board.kicad_pcb")
        verdicts = _verdicts(report)
        assert verdicts["MAX31865_LOW_THRESHOLD_WORD"] == "FAIL"
        assert verdicts["MAX31865_HIGH_THRESHOLD_WORD"] == "FAIL"

        low = next(v for v in report.entries if v.constant == "MAX31865_LOW_THRESHOLD_WORD")
        assert low.firmware_value == 1526.0
        assert low.derived_value == 1312.0  # ceil(10/500*32768)=656 << 1

    def test_pll_firmware_below_derived_floor_fails(self, tmp_path: Path) -> None:
        """Firmware PLL_MIN_FREQ_HZ below the board-derived floor fails
        the '>=' comparison with both values named."""
        repo = _repo(tmp_path, min_hz=43000)
        report = run(repo, repo / "pcb" / "board.kicad_pcb")
        pll = next(v for v in report.entries if v.constant == "PLL_MIN_FREQ_HZ")
        assert pll.status == "FAIL"
        assert pll.firmware_value == 43000.0
        assert pll.derived_value == pytest.approx(43824.0, rel=1e-4)


class TestUnmeasured:
    def test_board_input_unmeasurable_reports_unmeasured(self, tmp_path: Path) -> None:
        """U3 test scenario 4: a registry board input that cannot be
        extracted (placed, Value '?', footprint not in the decode table)
        reports UNMEASURED -- it does not pass silently."""
        repo = _repo(tmp_path, r_ref=("Some:Unknown_Footprint", (52.6, 250.51)))
        report = run(repo, repo / "pcb" / "board.kicad_pcb")
        verdicts = _verdicts(report)
        assert verdicts["MAX31865_LOW_THRESHOLD_WORD"] == "UNMEASURED"
        assert verdicts["MAX31865_HIGH_THRESHOLD_WORD"] == "UNMEASURED"
        assert verdicts["PLL_MIN_FREQ_HZ"] == "PASS"
        assert report.failed  # UNMEASURED is a failure, never a pass


class TestRegistryValidation:
    def test_registry_entry_missing_formula_key_fails_naming_the_entry(self, tmp_path: Path) -> None:
        """U1 test scenario 4: a registry entry missing a required key
        (formula) fails registration with the entry named."""
        reg = _write(
            tmp_path / "registry.yaml",
            """\
            version: 1
            derivations:
              - constant: PLL_MIN_FREQ_HZ
                firmware_file: firmware/components/control/pll_control.h
                compare: ">="
                inputs: []
            """,
        )
        with pytest.raises(OracleGateError, match="PLL_MIN_FREQ_HZ.*formula"):
            load_registry(reg)

    def test_registry_unknown_compare_mode_fails(self, tmp_path: Path) -> None:
        reg = _write(
            tmp_path / "registry.yaml",
            """\
            version: 1
            derivations:
              - constant: X
                firmware_file: firmware/config.yaml
                formula: max31865_low_threshold_word
                compare: "<"
                inputs: []
            """,
        )
        with pytest.raises(OracleGateError, match="compare"):
            load_registry(reg)

    def test_empty_registry_fails_closed(self, tmp_path: Path) -> None:
        reg = _write(
            tmp_path / "registry.yaml",
            "version: 1\nderivations: []\n",
        )
        with pytest.raises(OracleGateError, match="zero derivations"):
            load_registry(reg)

    def test_gate_constant_zvs_margin_cannot_drift_from_the_library(self, tmp_path: Path) -> None:
        """A registry that restates zvs_margin_min differently from the
        shared library constant is a gate error -- the margin must never
        be relaxable from the registry side."""
        repo = _repo(tmp_path)
        reg_path = repo / "firmware" / "tools" / "board_derivations.yaml"
        text = reg_path.read_text(encoding="utf-8")
        reg_path.write_text(text.replace("value: 1.05", "value: 1.01"), encoding="utf-8")
        with pytest.raises(OracleGateError, match="zvs_margin_min"):
            run(repo, repo / "pcb" / "board.kicad_pcb", registry_path=reg_path)


class TestGateErrors:
    def test_missing_board_file_is_a_gate_error_not_a_pass(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        missing = repo / "pcb" / "nope.kicad_pcb"
        with pytest.raises(BoardParseError):
            run(repo, missing)

    def test_unparseable_board_is_a_gate_error(self, tmp_path: Path) -> None:
        repo = _repo(tmp_path)
        board = repo / "pcb" / "board.kicad_pcb"
        board.write_text("(kicad_pcb (version 20211014) (broken", encoding="utf-8")
        with pytest.raises(BoardParseError):
            run(repo, board)

    def test_missing_declared_input_is_a_gate_error(self, tmp_path: Path) -> None:
        """A declared-assumed input missing from its source file fails
        closed -- the derivation cannot be computed, so it must not run."""
        repo = _repo(tmp_path)
        (repo / "elec" / "src" / "main.ato").write_text(
            "module Top:\n    l_tank_assumed: inductance = 88uH\n", encoding="utf-8"
        )
        with pytest.raises(OracleGateError, match="l_pan_loaded_ratio"):
            run(repo, repo / "pcb" / "board.kicad_pcb")
