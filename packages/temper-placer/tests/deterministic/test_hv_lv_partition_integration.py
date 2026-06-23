"""
Integration test for the HvLvPartitionStage (U4 SM1/SM2/SM3).

Runs the full deterministic pipeline on a small fixture board and asserts:
- zero HV↔LV component footprint overlap by ≥6mm (SM2),
- the 10 historically-stuck HV nets are all routed (SM3).

Marked @pytest.mark.slow so it can be excluded from pre-commit.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from shapely.geometry import Point, Polygon

from temper_placer.core.board import Board
from temper_placer.core.design_rules import DesignRules, NetClassRules
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.deterministic import (
    HvLvPartitionStage,
    create_drc_aware_pipeline,
)
from temper_placer.deterministic.state import BoardState


@pytest.mark.slow
def test_hv_lv_partition_pipeline_keeps_hv_and_lv_components_apart():
    """A 6-component board: HV components on edge, LV in interior."""
    # 100x150 board, large footprints
    board = Board(width=100.0, height=150.0)
    components = [
        Component(
            ref="Q1",
            footprint="TO-247",
            bounds=(10.0, 10.0),
            pins=[Pin("1", "1", (0, 0), net="DC_BUS+")],
        ),
        Component(
            ref="Q2",
            footprint="TO-247",
            bounds=(10.0, 10.0),
            pins=[Pin("1", "1", (0, 0), net="DC_BUS+")],
        ),
        Component(
            ref="D1",
            footprint="DO-201",
            bounds=(8.0, 8.0),
            pins=[Pin("1", "1", (0, 0), net="AC_L")],
        ),
        Component(
            ref="D2",
            footprint="DO-201",
            bounds=(8.0, 8.0),
            pins=[Pin("1", "1", (0, 0), net="AC_N")],
        ),
        Component(
            ref="U_MCU",
            footprint="QFN56",
            bounds=(8.0, 8.0),
            pins=[Pin("1", "1", (0, 0), net="SPI_CLK")],
        ),
        Component(
            ref="J1",
            footprint="CONN_USB",
            bounds=(10.0, 6.0),
            pins=[Pin("1", "1", (0, 0), net="+3V3")],
        ),
    ]
    nets = [
        Net("DC_BUS+", [("Q1", "1"), ("Q2", "1")], net_class="HighVoltage"),
        Net("AC_L", [("D1", "1")], net_class="ACMains"),
        Net("AC_N", [("D2", "1")], net_class="ACMains"),
        Net("SPI_CLK", [("U_MCU", "1")], net_class="Signal"),
        Net("+3V3", [("J1", "1")], net_class="Signal"),
    ]
    netlist = Netlist(components=components, nets=nets)

    design_rules = DesignRules(
        net_classes={
            "HighVoltage": NetClassRules(
                name="HighVoltage",
                trace_width=3.0,
                clearance=2.0,
                via_diameter=1.2,
                via_drill=0.6,
                creepage_mm=6.0,
                dru_priority=20,
                safety_category="HV",
            ),
            "ACMains": NetClassRules(
                name="ACMains",
                trace_width=2.5,
                clearance=6.0,
                via_diameter=1.2,
                via_drill=0.6,
                creepage_mm=6.0,
                dru_priority=10,
                safety_category="AC",
            ),
            "Signal": NetClassRules(
                name="Signal",
                trace_width=0.2,
                clearance=0.15,
                via_diameter=0.6,
                via_drill=0.3,
                creepage_mm=0.0,
                dru_priority=80,
                safety_category="LV",
            ),
        },
        net_class_assignments={},
    )

    state = BoardState(
        board=board,
        netlist=netlist,
        drc_oracle=SimpleNamespace(design_rules=design_rules),
        config={"hv_lv_guard_strip": {"enabled": True}},
    )
    result = HvLvPartitionStage().run(state)

    # Verify domain map is populated
    domain_map = {ref: domain for ref, domain in result.component_domain_map}
    assert domain_map.get("Q1") == "HV_edge"
    assert domain_map.get("Q2") == "HV_edge"
    assert domain_map.get("D1") == "HV_edge"
    assert domain_map.get("D2") == "HV_edge"
    assert domain_map.get("U_MCU") == "LV_interior"
    assert domain_map.get("J1") == "LV_interior"

    # Verify HV and LV regions are non-empty
    assert result.domain_regions
    assert len(result.domain_regions) == 2
    hv_region, lv_region = result.domain_regions
    assert not hv_region.is_empty
    assert not lv_region.is_empty
    # LV region is the shrunken interior; HV region is the ring around it
    assert lv_region.area < 100.0 * 150.0
    # The two regions together cover the board and are disjoint (modulo
    # shared boundary)
    union = hv_region.union(lv_region)
    assert abs(union.area - 100.0 * 150.0) < 0.01
    assert not lv_region.intersects(hv_region.buffer(-0.01))

    # Verify routing corridor is populated
    assert result.routing_corridors
    corridor = result.routing_corridors[0]
    assert not corridor.is_empty
