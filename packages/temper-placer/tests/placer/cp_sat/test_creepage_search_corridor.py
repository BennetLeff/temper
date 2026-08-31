"""Tests for the experiment-only designer-declared search corridor."""

from __future__ import annotations

import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest

from temper_placer.core.netlist import Component, Netlist, Pin
from temper_placer.placer.cp_sat.creepage_search_corridor import (
    add_creepage_search_corridor_to_model,
    resolve_creepage_search_corridor_report,
)
from temper_placer.placer.cp_sat.encoder import solve_placement
from temper_placer.placer.cp_sat.model import CpSatModel


def _component(ref: str, *nets: str, width: float = 4.0, height: float = 4.0) -> Component:
    return Component(
        ref=ref,
        footprint="Synthetic",
        bounds=(width, height),
        pins=[
            Pin(str(index), str(index), (0.0, 0.0), net=net) for index, net in enumerate(nets, 1)
        ],
    )


def _manifest(tmp_path: Path) -> Path:
    path = tmp_path / "domain_manifest.yaml"
    path.write_text(
        textwrap.dedent(
            """
            domains:
              HV:
                nets: [AC_L]
              SELV:
                nets: [GND]
            """
        ),
        encoding="utf-8",
    )
    return path


def _model(
    components: list[Component], *, width_mm: float = 100.0, height_mm: float = 80.0
) -> CpSatModel:
    model = CpSatModel(units_per_mm=100)
    for component in components:
        model.add_component(
            component.ref,
            0,
            0,
            model.mm_to_units(component.width),
            model.mm_to_units(component.height),
        )
        model.add_rotation(component.ref, is_polarized=True)
    model.set_bounds(0, 0, model.mm_to_units(width_mm), model.mm_to_units(height_mm))
    model.add_no_overlap_2d([component.ref for component in components])
    return model


def _partitioned_components() -> list[Component]:
    return [
        _component("H1", "AC_L"),
        _component("H2", "AC_L"),
        _component("S1", "GND"),
        _component("S2", "GND"),
        _component("ISO", "AC_L", "GND"),
        _component("FREE", "FLOATING"),
    ]


@pytest.mark.parametrize("axis", ["x", "y"])
def test_hard_corridor_orders_declared_boxes_and_reports_separator(
    tmp_path: Path, axis: str
) -> None:
    components = _partitioned_components()
    model = _model(components)
    manifest = _manifest(tmp_path)
    encoding = add_creepage_search_corridor_to_model(
        model,
        Netlist(components=components),
        manifest,
        hv_only_refs=["H2", "H1"],
        selv_only_refs=["S2", "S1"],
        axis=axis,
        gap_mm=12.6,
        board_w_mm=100.0,
        board_h_mm=80.0,
    )

    solution = model.solve(time_limit_s=2.0)
    assert solution.feasible, solution.unsat_assumptions
    report = resolve_creepage_search_corridor_report(encoding, solution)
    assert report.axis == axis
    assert report.polarity == "hv-low-selv-high"
    assert report.gap_mm == 12.6
    assert report.hv_only_refs == ("H1", "H2")
    assert report.selv_only_refs == ("S1", "S2")
    assert report.isolator_refs == ("ISO",)
    assert report.unclassified_refs == ("FREE",)
    assert report.separator_mm is not None

    axis_index = 0 if axis == "x" else 1
    separator_units = model.mm_to_units(report.separator_mm)
    gap_units = model.mm_to_units(report.gap_mm)
    for ref in report.hv_only_refs:
        center = solution.positions[ref][axis_index]
        size = solution.sizes[ref][axis_index]
        assert center + size // 2 <= separator_units
    for ref in report.selv_only_refs:
        center = solution.positions[ref][axis_index]
        size = solution.sizes[ref][axis_index]
        assert center - size // 2 >= separator_units + gap_units


@pytest.mark.parametrize(("hv_center_mm", "expected_separator_mm"), [(5.0, 7.0), (28.0, 30.0)])
def test_separator_is_movable_not_fixed_at_board_center(
    tmp_path: Path, hv_center_mm: float, expected_separator_mm: float
) -> None:
    components = [_component("H1", "AC_L"), _component("S1", "GND")]
    model = _model(components)
    # Pin the two boxes so their free-space gap is exactly 12.6 mm.  Both
    # corridor inequalities therefore force the separator to the HV edge.
    hv_center = model.mm_to_units(hv_center_mm)
    selv_center = model.mm_to_units(hv_center_mm + 4.0 + 12.6)
    model.model_ref.Add(model.get_component("H1").x_center == hv_center)
    model.model_ref.Add(model.get_component("S1").x_center == selv_center)
    encoding = add_creepage_search_corridor_to_model(
        model,
        Netlist(components=components),
        _manifest(tmp_path),
        hv_only_refs=["H1"],
        selv_only_refs=["S1"],
        axis="x",
        gap_mm=12.6,
        board_w_mm=100.0,
        board_h_mm=80.0,
    )

    solution = model.solve(time_limit_s=2.0)
    assert solution.feasible
    report = resolve_creepage_search_corridor_report(encoding, solution)
    assert report.separator_mm == expected_separator_mm
    assert report.separator_mm != 50.0


def test_isolator_and_unclassified_boxes_are_free_to_occupy_gap(tmp_path: Path) -> None:
    components = _partitioned_components()
    model = _model(components)
    # Force a unique separator at x=12mm, then place excluded buckets inside
    # different parts of the 12.6mm gap. Ordinary no-overlap still applies.
    model.model_ref.Add(model.get_component("H1").x_center == model.mm_to_units(10.0))
    model.model_ref.Add(model.get_component("H2").x_center == model.mm_to_units(5.0))
    model.model_ref.Add(model.get_component("S1").x_center == model.mm_to_units(26.6))
    model.model_ref.Add(model.get_component("S2").x_center == model.mm_to_units(32.0))
    model.model_ref.Add(model.get_component("ISO").x_center == model.mm_to_units(15.0))
    model.model_ref.Add(model.get_component("FREE").x_center == model.mm_to_units(21.0))
    encoding = add_creepage_search_corridor_to_model(
        model,
        Netlist(components=components),
        _manifest(tmp_path),
        hv_only_refs=["H1", "H2"],
        selv_only_refs=["S1", "S2"],
        axis="x",
        gap_mm=12.6,
        board_w_mm=100.0,
        board_h_mm=80.0,
    )

    solution = model.solve(time_limit_s=2.0)
    assert solution.feasible, solution.unsat_assumptions
    report = resolve_creepage_search_corridor_report(encoding, solution)
    assert report.separator_mm == 12.0
    assert 12.0 < solution.positions["ISO"][0] / 100 < 24.6
    assert 12.0 < solution.positions["FREE"][0] / 100 < 24.6


def test_encoding_adds_one_separator_without_pairwise_literals_or_envelopes(
    tmp_path: Path,
) -> None:
    components = _partitioned_components()
    model = _model(components)
    variables_before = len(model.model_ref.Proto().variables)
    constraints_before = len(model.model_ref.Proto().constraints)

    add_creepage_search_corridor_to_model(
        model,
        Netlist(components=components),
        _manifest(tmp_path),
        hv_only_refs=["H1", "H2"],
        selv_only_refs=["S1", "S2"],
        axis="x",
        gap_mm=12.6,
        board_w_mm=100.0,
        board_h_mm=80.0,
    )

    # One movable integer separator; one inequality per declared box plus
    # one max-equality canonicalizer. No pairwise direction Boolean, cluster
    # envelope, isolator, or unclassified variable/constraint is introduced.
    assert len(model.model_ref.Proto().variables) - variables_before == 1
    assert len(model.model_ref.Proto().constraints) - constraints_before == 5


def test_infeasible_result_disproves_only_the_declared_axis_topology(
    tmp_path: Path,
) -> None:
    components = [_component("H1", "AC_L"), _component("S1", "GND")]
    model = _model(components)
    # Ordinary placement is feasible, but these fixed positions put SELV on
    # the low side and HV on the high side, contradicting only this x-axis
    # declaration.
    model.model_ref.Add(model.get_component("H1").x_center == model.mm_to_units(40.0))
    model.model_ref.Add(model.get_component("S1").x_center == model.mm_to_units(10.0))
    encoding = add_creepage_search_corridor_to_model(
        model,
        Netlist(components=components),
        _manifest(tmp_path),
        hv_only_refs=["H1"],
        selv_only_refs=["S1"],
        axis="x",
        gap_mm=12.6,
        board_w_mm=100.0,
        board_h_mm=80.0,
    )

    solution = model.solve(time_limit_s=2.0)
    assert not solution.feasible
    report = resolve_creepage_search_corridor_report(encoding, solution)
    assert report.axis == "x"
    assert report.separator_mm is None


@pytest.mark.parametrize(
    ("hv_refs", "selv_refs", "match"),
    [
        ([], ["S1", "S2"], "HV-only declaration must be nonempty"),
        (["H1", "H2"], [], "SELV-only declaration must be nonempty"),
        (["H1", "H2", "MISSING"], ["S1", "S2"], "unknown component"),
        (["H1", "H1", "H2"], ["S1", "S2"], "duplicate"),
        (["H1", "H2"], ["S1", "S1", "S2"], "duplicate"),
        (["H1", "H2"], ["H2", "S1", "S2"], "overlap"),
        (["H1"], ["S1", "S2"], "does not exactly match"),
        (["H1", "H2", "ISO"], ["S1", "S2"], "does not exactly match"),
    ],
)
def test_invalid_designer_declarations_fail_before_solve(
    tmp_path: Path, hv_refs: list[str], selv_refs: list[str], match: str
) -> None:
    components = _partitioned_components()
    model = _model(components)
    constraint_count = len(model.model_ref.Proto().constraints)
    with pytest.raises(ValueError, match=match):
        add_creepage_search_corridor_to_model(
            model,
            Netlist(components=components),
            _manifest(tmp_path),
            hv_only_refs=hv_refs,
            selv_only_refs=selv_refs,
            axis="x",
            gap_mm=12.6,
            board_w_mm=100.0,
            board_h_mm=80.0,
        )
    assert len(model.model_ref.Proto().constraints) == constraint_count


def test_gap_wider_than_axis_and_invalid_axis_fail_before_solve(tmp_path: Path) -> None:
    components = _partitioned_components()
    common = {
        "netlist": Netlist(components=components),
        "manifest_path": _manifest(tmp_path),
        "hv_only_refs": ["H1", "H2"],
        "selv_only_refs": ["S1", "S2"],
        "board_w_mm": 100.0,
        "board_h_mm": 80.0,
    }
    with pytest.raises(ValueError, match="axis must be 'x' or 'y'"):
        add_creepage_search_corridor_to_model(
            _model(components), axis="vertical", gap_mm=12.6, **common
        )
    with pytest.raises(ValueError, match="does not fit"):
        add_creepage_search_corridor_to_model(_model(components), axis="y", gap_mm=80.2, **common)


def test_authoritative_manifest_membership_beats_misleading_ref_names(tmp_path: Path) -> None:
    components = [
        _component("LOOKS_SELV", "AC_L"),
        _component("LOOKS_HV", "GND"),
    ]
    model = _model(components)
    encoding = add_creepage_search_corridor_to_model(
        model,
        Netlist(components=components),
        _manifest(tmp_path),
        hv_only_refs=["LOOKS_SELV"],
        selv_only_refs=["LOOKS_HV"],
        axis="x",
        gap_mm=12.6,
        board_w_mm=100.0,
        board_h_mm=80.0,
    )
    assert encoding.report.hv_only_refs == ("LOOKS_SELV",)
    assert encoding.report.selv_only_refs == ("LOOKS_HV",)


def test_production_solver_corridor_is_opt_in_and_resolves_report(tmp_path: Path) -> None:
    components = [_component("H1", "AC_L"), _component("S1", "GND")]
    netlist = Netlist(components=components)
    board = SimpleNamespace(width=60.0, height=60.0, zones=[], constraints=[])

    ordinary = solve_placement(netlist, board, extra_constraints=[], timeout_ms=1_000)
    assert ordinary.status in ("optimal", "feasible")
    assert ordinary.creepage_search_corridor_report is None

    restricted = solve_placement(
        netlist,
        board,
        extra_constraints=[],
        timeout_ms=1_000,
        creepage_search_corridor={
            "manifest_path": _manifest(tmp_path),
            "hv_only_refs": ["H1"],
            "selv_only_refs": ["S1"],
            "axis": "x",
            "gap_mm": 12.6,
        },
    )
    assert restricted.status in ("optimal", "feasible"), restricted.status
    report = restricted.creepage_search_corridor_report
    assert report is not None
    assert report.separator_mm is not None
    assert restricted.positions["H1"][0] + 2.0 <= report.separator_mm
    assert restricted.positions["S1"][0] - 2.0 >= report.separator_mm + 12.6
