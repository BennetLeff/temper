"""Focused fail-closed tests for the standalone current-sense adapters."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import shutil
import sys
from pathlib import Path

import pytest

TOOLS = Path(__file__).parents[1] / "tools"
REPO = Path(__file__).parents[3]
sys.path.insert(0, str(TOOLS))
sys.path.insert(0, str(REPO / "scripts"))

import gen_pcb_skeleton as skeleton  # noqa: E402
import gen_schematics as schematics  # noqa: E402
from native_report import load_kicad_report, require_success  # noqa: E402


def _load_tool(name: str):
    path = TOOLS / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build_native = _load_tool("build_current_sense_native.py")
native_checks = _load_tool("run_current_sense_native_checks.py")


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_erc_report_requires_kicad_schema_and_sheet_violations(tmp_path: Path) -> None:
    report = tmp_path / "erc.json"
    _write_json(report, {"sheets": []})
    with pytest.raises(ValueError, match="unexpected \\$schema"):
        load_kicad_report(report, "erc")

    _write_json(
        report,
        {
            "$schema": "https://schemas.kicad.org/erc.v1.json",
            "sheets": [{"path": "/root", "violations": {}}],
        },
    )
    with pytest.raises(ValueError, match="violations list"):
        load_kicad_report(report, "erc")


def test_drc_report_requires_all_finding_lists(tmp_path: Path) -> None:
    report = tmp_path / "drc.json"
    _write_json(
        report,
        {
            "$schema": "https://schemas.kicad.org/drc.v1.json",
            "violations": [],
            "unconnected_items": [],
        },
    )
    with pytest.raises(ValueError, match="schematic_parity list"):
        load_kicad_report(report, "drc")


def test_missing_report_and_nonzero_command_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="produced no erc report"):
        load_kicad_report(tmp_path / "missing.json", "erc")
    with pytest.raises(RuntimeError, match="returncode=7"):
        require_success("ERC", 7, "stdout", "stderr")


def test_native_check_runner_records_then_rejects_nonzero_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class FailedProcess:
        returncode = 9
        stdout = "tool output"
        stderr = "tool failure"

    monkeypatch.setattr(native_checks.subprocess, "run", lambda *args, **kwargs: FailedProcess())
    output = tmp_path / "reports"
    output.mkdir()
    with pytest.raises(RuntimeError, match="returncode=9"):
        native_checks._run(["kicad-cli", "sch", "erc"], output / "erc.json", output, {})
    command_receipt = json.loads((output / "erc-command.json").read_text(encoding="utf-8"))
    assert command_receipt["returncode"] == 9


def test_source_hash_map_is_required_and_contained(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    source = repo / "source-build"
    source.mkdir(parents=True)
    source_file = source / "elec" / "src" / "current_sense_unit.ato"
    source_file.parent.mkdir(parents=True)
    source_file.write_text("component CurrentSenseUnit:\n", encoding="utf-8")
    digest = hashlib.sha256(source_file.read_bytes()).hexdigest()
    export = {"source_sha256": {"elec/src/current_sense_unit.ato": digest}}
    assert build_native._require_source_hashes(repo, source, export)

    with pytest.raises(ValueError, match="nonempty source_sha256"):
        build_native._require_source_hashes(repo, source, {})
    with pytest.raises(ValueError, match="escapes source build"):
        build_native._require_source_hashes(
            repo, source, {"source_sha256": {"../outside": digest}}
        )
    with pytest.raises(ValueError, match="contained under repo"):
        build_native._require_source_hashes(
            repo, tmp_path / "outside", export
        )


def _aliased_symbol_netlist() -> schematics.Netlist:
    """Two selected parts share the compiler's footprint-aliased libpart."""
    alias = "SN74LV221AQPWRQ1"
    return schematics.Netlist(
        components={
            ref: schematics.Component(
                ref=ref,
                value="?",
                footprint="Package_SO:TSSOP-16_4.4x5mm_P0.65mm",
                part_name=alias,
                description="compiled alias",
                sheet_module="source_mcu",
                tstamp=ref,
            )
            for ref in ("U1", "U2")
        },
        nets={
            "1": schematics.Net("1", "SOURCE_SIGNAL", [("U1", "1"), ("U2", "2")]),
            "2": schematics.Net("2", "RETURN", [("U1", "2"), ("U2", "1")]),
        },
        libparts={
            alias: schematics.LibPart(
                alias, "compiled alias", [("1", "ALIAS_A"), ("2", "ALIAS_B")]
            )
        },
    )


def test_selected_mpn_rekeys_aliased_symbols_without_changing_numeric_pins() -> None:
    netlist = _aliased_symbol_netlist()
    selected = {"U1": "SN74LV221AQPWRQ1", "U2": "TCA6408AQPWRQ1"}
    before = {code: list(net.nodes) for code, net in netlist.nets.items()}
    schematics.apply_bom_values(netlist, selected)

    build_native._apply_selected_symbol_identity(
        netlist, selected, selected, schematics
    )

    assert {code: net.nodes for code, net in netlist.nets.items()} == before
    assert netlist.components["U2"].part_name == "TCA6408AQPWRQ1"
    assert netlist.libparts["TCA6408AQPWRQ1"].pins == [("1", "1"), ("2", "2")]
    layout = schematics.SchematicLayout(
        root_sheet="section.kicad_sch",
        sheets=("CurrentSense",),
        sheet_files={"CurrentSense": "section.kicad_sch"},
        module_to_sheet={"source_mcu": "CurrentSense"},
        title="Identity test",
        sheet_description="Identity test",
        flat=True,
    )
    generated = schematics._generate_all_sheets(netlist, Path("."), layout)[
        "section.kicad_sch"
    ]
    assert '(lib_id "TCA6408AQPWRQ1")' in generated
    assert '(property "Value" "TCA6408AQPWRQ1"' in generated
    assert '(name "1"' in generated and '(name "2"' in generated
    assert "ALIAS_A" not in generated and "ALIAS_B" not in generated
    assert '(global_label "SOURCE_SIGNAL"' in generated
    assert '(global_label "RETURN"' in generated


@pytest.mark.parametrize(
    ("selected", "bom", "message"),
    [
        (
            {"U1": "SN74LV221AQPWRQ1"},
            {"U1": "SN74LV221AQPWRQ1", "U2": "TCA6408AQPWRQ1"},
            "missing selected MPN",
        ),
        (
            {"U1": "SN74LV221AQPWRQ1", "U2": "TCA6408AQPWRQ1"},
            {"U1": "SN74LV221AQPWRQ1", "U2": "WRONG"},
            "MPN mismatch",
        ),
    ],
)
def test_selected_symbol_identity_fails_on_missing_or_mismatched_mpn(
    selected: dict[str, str], bom: dict[str, str], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        build_native._apply_selected_symbol_identity(
            _aliased_symbol_netlist(), selected, bom, schematics
        )


def test_board_value_uses_selected_mpn_over_nominal_value() -> None:
    netlist = skeleton.Netlist(
        components={
            "U224": skeleton.Component(
                ref="U224",
                value="180uH",
                footprint="Inductor_THT_Wurth:L_Wurth_WE-TORPFC-T75",
                tstamp="u224",
                sheetpath="pfc_power.l_boost",
            )
        },
        nets={},
    )
    build_native._apply_selected_board_values(netlist, {"U224": "760800301"})
    assert netlist.components["U224"].value == "760800301"
    with pytest.raises(ValueError, match="cover exactly"):
        build_native._apply_selected_board_values(netlist, {})


def test_candidate_board_rekeys_legacy_footprint_text_without_changing_pads(
    tmp_path: Path,
) -> None:
    library = tmp_path / "Inductor_THT_Wurth.pretty"
    library.mkdir()
    footprint_name = "L_Wurth_WE-TORPFC-T75.kicad_mod"
    source_footprint = (
        REPO / "zapote" / "power-entry" / "passive-reva" / "libraries"
        / "Inductor_THT_Wurth.pretty" / footprint_name
    )
    assert '(fp_text reference "REF**"' in source_footprint.read_text(encoding="utf-8")
    shutil.copy2(source_footprint, library / footprint_name)
    table = tmp_path / "fp-lib-table"
    table.write_text(
        f'(fp_lib_table (lib (name "Inductor_THT_Wurth") (type "KiCad") '
        f'(uri "{library}") (options "") (descr "")))\n',
        encoding="utf-8",
    )
    netlist = skeleton.Netlist(
        components={
            "U224": skeleton.Component(
                ref="U224", value="?",
                footprint="Inductor_THT_Wurth:L_Wurth_WE-TORPFC-T75",
                tstamp="u224", sheetpath="pfc_power.l_boost",
            )
        },
        nets={
            "1": skeleton.Net("1", "VD", [("U224", "1")]),
            "2": skeleton.Net("2", "SW", [("U224", "2")]),
        },
    )
    pin_map = {("U224", "1"): "1", ("U224", "2"): "2"}
    selected_mpn = "760800301"
    build_native._apply_selected_board_values(netlist, {"U224": selected_mpn})
    board_path = tmp_path / "section.kicad_pcb"
    skeleton.generate_candidate_board(
        netlist, pin_map, set(), table, (0, 0, 360, 250),
        {"U224": (150, 120, 0)}, board_path,
        values={"U224": selected_mpn},
    )
    from kiutils.board import Board
    from kiutils.items.fpitems import FpText

    footprint = Board.from_file(str(board_path)).footprints[0]
    assert footprint.properties["Reference"] == "U224"
    assert footprint.properties["Value"] == selected_mpn
    assert {
        item.type: item.text
        for item in footprint.graphicItems
        if isinstance(item, FpText) and item.type in {"reference", "value"}
    } == {"reference": "U224", "value": selected_mpn}
    assert {pad.number: pad.net.name for pad in footprint.pads if pad.number} == {
        "1": "VD", "2": "SW",
    }
    assert skeleton.candidate_oracle_verify(
        board_path, netlist, pin_map, (0, 0, 360, 250)
    )


def test_flat_candidate_pin_endpoints_stay_on_kicad_connection_grid() -> None:
    part = schematics.LibPart("TwoPin", "grid probe", [("1", "A"), ("2", "B")])
    components = {
        f"U{index}": schematics.Component(
            ref=f"U{index}", value="probe", footprint="Test:TwoPin",
            part_name="TwoPin", description="grid probe", sheet_module="test",
            tstamp=f"grid-{index}", display_value="Probe MPN",
        )
        for index in range(1, 8)
    }
    netlist = schematics.Netlist(
        components=components,
        nets={"1": schematics.Net("1", "GRID_NET", [("U1", "1"), ("U7", "2")])},
        libparts={"TwoPin": part},
    )
    text = schematics.generate_flat_root_sheet(netlist, schematics.mcu_candidate_layout())
    # Seven refs span a second row and five columns. Read the generated
    # connection points, including global labels and no-connect markers.
    endpoints = re.findall(
        r'\((?:no_connect|global_label)\b.*?\(at ([\d.]+) ([\d.]+)',
        text,
        flags=re.S,
    )
    assert len(endpoints) == 14
    for x_text, y_text in endpoints:
        for coordinate in (float(x_text), float(y_text)):
            assert abs(coordinate / 1.27 - round(coordinate / 1.27)) < 1e-8


def test_flat_candidate_rows_clear_large_synthesized_symbols() -> None:
    part = schematics.LibPart(
        "Tall", "32-pin row probe", [(str(pin), str(pin)) for pin in range(1, 33)]
    )
    components = {
        f"U{index}": schematics.Component(
            ref=f"U{index}", value="probe", footprint="Test:Tall",
            part_name="Tall", description="row probe", sheet_module="test",
            tstamp=f"tall-{index}", display_value="Tall MPN",
        )
        for index in range(1, 7)
    }
    text = schematics.generate_flat_root_sheet(
        schematics.Netlist(components, {}, {"Tall": part}),
        schematics.mcu_candidate_layout(),
    )
    origins = [
        (float(x), float(y)) for x, y in re.findall(
            r'\(symbol\s+\(lib_id "Tall"\)\s+\(at ([\d.]+) ([\d.]+) 0\)',
            text,
        )
    ]
    assert len(origins) == 6
    first_row_y = {y for _, y in origins[:5]}
    assert len(first_row_y) == 1
    # KiCad's generated body extends pin_count * 5.08 mm above and below
    # each origin. Distinct rows need a gap beyond both body extents.
    assert origins[5][1] - origins[0][1] > 2 * 32 * 5.08
