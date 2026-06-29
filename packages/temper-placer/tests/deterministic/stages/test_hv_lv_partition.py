"""
Unit tests for HvLvPartitionStage.

Part of feat/hv-lv-guard-strip (plan 2026-06-23-001).

Covers the U1 surface (state, config, exception) and the U2 partition
stage (bucket assignment, width override, fallback, determinism).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from shapely.geometry import LineString

from temper_placer.core.board import Board
from temper_placer.core.design_rules import DesignRules, NetClassRules
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.deterministic.stages.hv_lv_partition import (
    HvLvGuardConfig,
    HvLvPartitionStage,
    PartitionError,
    load_guard_config,
)
from temper_placer.deterministic.state import BoardState

# ---------------------------------------------------------------------------
# BoardState defaults (NFR6)
# ---------------------------------------------------------------------------


def test_board_state_default_component_domain_map_empty():
    state = BoardState()
    assert state.component_domain_map == frozenset()


def test_board_state_default_routing_corridors_empty():
    state = BoardState()
    assert state.routing_corridors == ()


def test_board_state_default_domain_regions_empty():
    state = BoardState()
    assert state.domain_regions == ()


def test_board_state_default_config_none():
    state = BoardState()
    assert state.config is None


# ---------------------------------------------------------------------------
# HvLvGuardConfig pydantic round-trip (FR9)
# ---------------------------------------------------------------------------


def test_hv_lv_guard_config_round_trip_disabled():
    cfg = HvLvGuardConfig(enabled=False, width_mm=None, fallback_to_unconstrained=True)
    assert cfg.enabled is False
    assert cfg.width_mm is None
    assert cfg.fallback_to_unconstrained is True
    assert cfg.model_dump() == {
        "enabled": False,
        "width_mm": None,
        "fallback_to_unconstrained": True,
    }


def test_hv_lv_guard_config_defaults():
    cfg = HvLvGuardConfig()
    assert cfg.enabled is True
    assert cfg.width_mm is None
    assert cfg.fallback_to_unconstrained is True


# ---------------------------------------------------------------------------
# load_guard_config
# ---------------------------------------------------------------------------


def test_load_guard_config_with_block_present():
    cfg = load_guard_config(
        {
            "hv_lv_guard_strip": {
                "enabled": False,
                "width_mm": 8.0,
                "fallback_to_unconstrained": False,
            }
        }
    )
    assert cfg.enabled is False
    assert cfg.width_mm == 8.0
    assert cfg.fallback_to_unconstrained is False


def test_load_guard_config_missing_block_returns_defaults():
    cfg = load_guard_config({"some_other_block": {"foo": 1}})
    assert cfg.enabled is True
    assert cfg.width_mm is None
    assert cfg.fallback_to_unconstrained is True


def test_load_guard_config_none_returns_defaults():
    cfg = load_guard_config(None)
    assert cfg == HvLvGuardConfig()


def test_load_guard_config_empty_dict_returns_defaults():
    cfg = load_guard_config({})
    assert cfg == HvLvGuardConfig()


def test_load_guard_config_invalid_block_logs_and_returns_defaults(caplog):
    with caplog.at_level("WARNING"):
        cfg = load_guard_config({"hv_lv_guard_strip": "not-a-mapping"})
    assert cfg == HvLvGuardConfig()
    assert any("not a mapping" in rec.message for rec in caplog.records)


# ---------------------------------------------------------------------------
# PartitionError (FR7)
# ---------------------------------------------------------------------------


def test_partition_error_exposes_structured_fields():
    err = PartitionError("HV", "Q1", 25.0, 80.0)
    assert err.bucket == "HV"
    assert err.largest_ref == "Q1"
    assert err.region_area_mm2 == 25.0
    assert err.required_area_mm2 == 80.0


def test_partition_error_is_exception():
    assert issubclass(PartitionError, Exception)
    with pytest.raises(PartitionError):
        raise PartitionError("LV", "U1", 10.0, 50.0)


# ---------------------------------------------------------------------------
# HvLvPartitionStage fixtures and helpers
# ---------------------------------------------------------------------------


def _make_design_rules() -> DesignRules:
    """Synthetic DesignRules with HV/AC/LV net classes (creepage=6.0)."""
    return DesignRules(
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
            "iso": NetClassRules(
                name="iso",
                trace_width=0.2,
                clearance=0.15,
                via_diameter=0.6,
                via_drill=0.3,
                creepage_mm=0.0,
                dru_priority=90,
                safety_category="iso",
            ),
        },
        net_class_assignments={},
    )


def _make_state(
    netlist: Netlist,
    *,
    config: dict[str, Any] | None = None,
    board: Board | None = None,
    design_rules: DesignRules | None = None,
) -> BoardState:
    if board is None:
        board = Board(width=100.0, height=150.0)
    drc_oracle = SimpleNamespace(design_rules=design_rules or _make_design_rules())
    return BoardState(
        board=board,
        netlist=netlist,
        drc_oracle=drc_oracle,
        config=config,
    )


def _netlist_basic() -> Netlist:
    """Netlist with one HV, one AC, two LV components (Q1/D1 HV-edge, others LV)."""
    components = [
        Component(
            ref="Q1",
            footprint="TO-247",
            bounds=(12.0, 12.0),
            pins=[Pin("1", "1", (0, 0), net="DC_BUS+")],
        ),
        Component(
            ref="D1",
            footprint="DO-201",
            bounds=(6.0, 6.0),
            pins=[Pin("1", "1", (0, 0), net="AC_L")],
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
        Net("DC_BUS+", [("Q1", "1")], net_class="HighVoltage"),
        Net("AC_L", [("D1", "1")], net_class="ACMains"),
        Net("SPI_CLK", [("U_MCU", "1")], net_class="Signal"),
        Net("+3V3", [("J1", "1")], net_class="Signal"),
    ]
    return Netlist(components=components, nets=nets)


# ---------------------------------------------------------------------------
# HvLvPartitionStage behaviour (U2)
# ---------------------------------------------------------------------------


def test_stage_partitions_basic_hv_ac_lv():
    state = _make_state(_netlist_basic())
    result = HvLvPartitionStage().run(state)
    assert result.component_domain_map == frozenset(
        {
            ("Q1", "HV_edge"),
            ("D1", "HV_edge"),
            ("U_MCU", "LV_interior"),
            ("J1", "LV_interior"),
        }
    )


def test_stage_disabled_returns_state_unchanged():
    state = _make_state(_netlist_basic(), config={"hv_lv_guard_strip": {"enabled": False}})
    result = HvLvPartitionStage().run(state)
    assert result.component_domain_map == frozenset()
    assert result.routing_corridors == ()


def test_stage_dual_domain_assigned_to_lv_with_warning(caplog):
    components = [
        Component(
            ref="Q1",
            footprint="TO-247",
            bounds=(12.0, 12.0),
            pins=[Pin("1", "1", (0, 0), net="DC_BUS+")],
        ),
        Component(
            ref="U_BRIDGE",
            footprint="SOIC8",
            bounds=(5.0, 5.0),
            pins=[
                Pin("1", "1", (0, 0), net="DC_BUS+"),
                Pin("2", "2", (0, 0), net="SPI_CLK"),
            ],
        ),
    ]
    nets = [
        Net("DC_BUS+", [("Q1", "1"), ("U_BRIDGE", "1")], net_class="HighVoltage"),
        Net("SPI_CLK", [("U_BRIDGE", "2")], net_class="Signal"),
    ]
    netlist = Netlist(components=components, nets=nets)
    state = _make_state(netlist)
    with caplog.at_level("WARNING"):
        result = HvLvPartitionStage().run(state)
    assert ("Q1", "HV_edge") in result.component_domain_map
    assert ("U_BRIDGE", "LV_interior") in result.component_domain_map
    assert any("U_BRIDGE" in rec.message for rec in caplog.records)


def test_stage_empty_hv_bucket_returns_state_unchanged(caplog):
    components = [
        Component(
            ref="U_MCU",
            footprint="QFN56",
            bounds=(8.0, 8.0),
            pins=[Pin("1", "1", (0, 0), net="SPI_CLK")],
        ),
        Component(
            ref="R1",
            footprint="0603",
            bounds=(1.6, 0.8),
            pins=[Pin("1", "1", (0, 0), net="+3V3")],
        ),
    ]
    nets = [
        Net("SPI_CLK", [("U_MCU", "1")], net_class="Signal"),
        Net("+3V3", [("R1", "1")], net_class="Signal"),
    ]
    state = _make_state(Netlist(components=components, nets=nets))
    with caplog.at_level("INFO"):
        result = HvLvPartitionStage().run(state)
    assert result.component_domain_map == frozenset()
    assert any("empty HV/LV bucket" in rec.message for rec in caplog.records)


def test_stage_width_override_above_creepage_uses_override():
    state = _make_state(_netlist_basic(), config={"hv_lv_guard_strip": {"width_mm": 10.0}})
    result = HvLvPartitionStage().run(state)
    assert len(result.routing_corridors) == 1
    corridor = result.routing_corridors[0]
    # Corridor area is the ring of width 10 around a 100x150 rectangle
    expected = 2 * (100.0 + 150.0) * 10.0 - 4 * 10.0**2
    assert abs(corridor.area - expected) < 0.1


def test_stage_width_override_below_creepage_uses_creepage(caplog):
    state = _make_state(_netlist_basic(), config={"hv_lv_guard_strip": {"width_mm": 3.0}})
    with caplog.at_level("WARNING"):
        result = HvLvPartitionStage().run(state)
    assert len(result.routing_corridors) == 1
    corridor = result.routing_corridors[0]
    expected = 2 * (100.0 + 150.0) * 6.0 - 4 * 6.0**2
    assert abs(corridor.area - expected) < 0.1
    assert any("below creepage" in rec.message for rec in caplog.records)


def test_stage_width_zero_disables_guard_geometry():
    # width_mm=0 is a pass-through: no partition, no geometry, no corridors.
    state = _make_state(_netlist_basic(), config={"hv_lv_guard_strip": {"width_mm": 0}})
    result = HvLvPartitionStage().run(state)
    assert result.component_domain_map == frozenset()
    assert result.routing_corridors == ()


def test_stage_insufficient_area_falls_back_with_warning(caplog):
    # 10x10 board with a single huge HV component to shrink the LV region.
    components = [
        Component(
            ref="Q_BIG",
            footprint="HUGE",
            bounds=(12.0, 12.0),
            pins=[Pin("1", "1", (0, 0), net="DC_BUS+")],
        ),
        Component(
            ref="U1",
            footprint="QFN56",
            bounds=(8.0, 8.0),
            pins=[Pin("1", "1", (0, 0), net="SPI_CLK")],
        ),
    ]
    nets = [
        Net("DC_BUS+", [("Q_BIG", "1")], net_class="HighVoltage"),
        Net("SPI_CLK", [("U1", "1")], net_class="Signal"),
    ]
    state = _make_state(
        Netlist(components=components, nets=nets),
        board=Board(width=10.0, height=10.0),
        config={"hv_lv_guard_strip": {"fallback_to_unconstrained": True}},
    )
    with caplog.at_level("WARNING"):
        result = HvLvPartitionStage().run(state)
    # Pass-through: domain_map stays empty because the stage did not write
    # it after falling back.
    assert result.component_domain_map == frozenset()
    assert any("insufficient" in rec.message for rec in caplog.records)


def test_stage_insufficient_area_raises_when_fallback_disabled(caplog):
    components = [
        Component(
            ref="Q_BIG",
            footprint="HUGE",
            bounds=(12.0, 12.0),
            pins=[Pin("1", "1", (0, 0), net="DC_BUS+")],
        ),
        Component(
            ref="U1",
            footprint="QFN56",
            bounds=(8.0, 8.0),
            pins=[Pin("1", "1", (0, 0), net="SPI_CLK")],
        ),
    ]
    nets = [
        Net("DC_BUS+", [("Q_BIG", "1")], net_class="HighVoltage"),
        Net("SPI_CLK", [("U1", "1")], net_class="Signal"),
    ]
    state = _make_state(
        Netlist(components=components, nets=nets),
        board=Board(width=10.0, height=10.0),
        config={"hv_lv_guard_strip": {"fallback_to_unconstrained": False}},
    )
    with pytest.raises(PartitionError) as excinfo:
        HvLvPartitionStage().run(state)
    err = excinfo.value
    assert err.bucket in {"HV", "LV"}
    assert err.largest_ref in {"Q_BIG", "U1"}
    assert err.region_area_mm2 >= 0.0
    assert err.required_area_mm2 > 0.0


def test_stage_geometry_function_rejects_non_polygon():
    # Direct check on compute_guard_strip: a non-Polygon outline raises
    # ValueError, which the stage converts to PartitionError("geometry").
    from temper_placer.deterministic.geometry.guard_strip import compute_guard_strip

    with pytest.raises(ValueError):
        compute_guard_strip(LineString([(0, 0), (100, 0), (100, 150)]), 6.0)  # type: ignore[arg-type]


def test_stage_determinism_same_input_same_output():
    state_a = _make_state(_netlist_basic())
    state_b = _make_state(_netlist_basic())
    result_a = HvLvPartitionStage().run(state_a)
    result_b = HvLvPartitionStage().run(state_b)
    assert result_a.component_domain_map == result_b.component_domain_map
    assert len(result_a.routing_corridors) == len(result_b.routing_corridors) == 1
    a_area = result_a.routing_corridors[0].area
    b_area = result_b.routing_corridors[0].area
    assert abs(a_area - b_area) < 1e-9


def test_stage_unmapped_components_default_to_lv():
    # A component connected to a net with no safety_category mapping.
    components = [
        Component(
            ref="Q1",
            footprint="TO-247",
            bounds=(12.0, 12.0),
            pins=[Pin("1", "1", (0, 0), net="DC_BUS+")],
        ),
        Component(
            ref="R1",
            footprint="0603",
            bounds=(1.6, 0.8),
            pins=[Pin("1", "1", (0, 0), net="UNKNOWN_NET")],
        ),
    ]
    nets = [
        Net("DC_BUS+", [("Q1", "1")], net_class="HighVoltage"),
        Net("UNKNOWN_NET", [("R1", "1")], net_class="Signal"),
    ]
    state = _make_state(Netlist(components=components, nets=nets))
    result = HvLvPartitionStage().run(state)
    assert ("R1", "LV_interior") in result.component_domain_map
    assert ("Q1", "HV_edge") in result.component_domain_map


def test_stage_no_board_or_netlist_returns_state():
    empty = BoardState()
    result = HvLvPartitionStage().run(empty)
    assert result is empty

