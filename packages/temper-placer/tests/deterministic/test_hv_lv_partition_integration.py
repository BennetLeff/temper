"""
Integration test for the HvLvPartitionStage (U4 SM1/SM2/SM3).

Drives the full deterministic pipeline via ``create_drc_aware_pipeline``
on a 6-component fixture board and asserts:

  (a) SM2: HV-edge component footprints do not intersect LV-interior
      component footprints by ≥ 6 mm (the IEC 60335-1 creepage that
      motivated the guard strip in the first place).
  (b) SM3: each historically-stuck HV net (those tied to Q1, Q2, D1, D2)
      is present in ``state.routes`` (i.e. the pipeline routed it
      successfully rather than dropping it).

Previously the test ran ``HvLvPartitionStage`` in isolation, which
exercised the partition logic but never confirmed that the rest of
the pipeline honored the domain map end-to-end. Marked
``@pytest.mark.slow`` so it can be excluded from pre-commit.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from shapely.geometry import Polygon

from temper_placer.core.board import Board
from temper_placer.core.design_rules import DesignRules, NetClassRules
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.deterministic import create_drc_aware_pipeline
from temper_placer.deterministic.state import BoardState
from temper_placer.io.kicad_metadata import KiCadMetadata

# Creepage margin (mm) that motivated the guard strip. Per the plan
# and the IEC 60335-1 reference cited in the partition stage, any
# closer placement was the reason these nets historically failed to
# route. We require at least this much separation between HV-edge
# and LV-interior component footprints.
CREEPAGE_MARGIN_MM = 6.0

# Nets tied to the four HV components (Q1, Q2, D1, D2) — the
# historically-stuck set that SM3 promises the partition will rescue.
HV_COMPONENT_REFS = frozenset({"Q1", "Q2", "D1", "D2"})


@pytest.mark.slow
def test_hv_lv_partition_pipeline_keeps_hv_and_lv_components_apart():
    """A 6-component board: HV components on edge, LV in interior."""
    # 100x150 board. Footprint bounds are sized so the 6 mm creepage
    # margin produces a real ≥ 6 mm HV↔LV footprint gap on the
    # 10 mm slot grid (half-extent ≤ 3 mm so the partition's
    # guard strip can actually deliver the IEC margin). The
    # fixture gives each HV-classified net a second pin so the
    # router has work to do (single-pin nets never produce traces
    # and would be a false negative for SM3). All HV-classified
    # multi-pin nets share the same component pair to keep the
    # test focused on partition + placement behavior rather than
    # the router's per-net heuristics.
    board = Board(width=100.0, height=150.0)
    components = [
        Component(
            ref="Q1",
            footprint="TO-247",
            bounds=(6.0, 6.0),
            pins=[
                Pin("1", "1", (0, 0), net="DC_BUS+"),
                Pin("2", "2", (0, 0), net="DC_BUS+"),
            ],
        ),
        Component(
            ref="Q2",
            footprint="TO-247",
            bounds=(6.0, 6.0),
            pins=[
                Pin("1", "1", (0, 0), net="DC_BUS+"),
                Pin("2", "2", (0, 0), net="DC_BUS+"),
            ],
        ),
        Component(
            ref="D1",
            footprint="DO-201",
            bounds=(4.0, 4.0),
            pins=[
                Pin("1", "1", (0, 0), net="AC_L"),
                Pin("2", "2", (0, 0), net="AC_L"),
            ],
        ),
        Component(
            ref="D2",
            footprint="DO-201",
            bounds=(4.0, 4.0),
            pins=[
                Pin("1", "1", (0, 0), net="AC_L"),
                Pin("2", "2", (0, 0), net="AC_L"),
            ],
        ),
        Component(
            ref="U_MCU",
            footprint="QFN56",
            bounds=(4.0, 4.0),
            pins=[Pin("1", "1", (0, 0), net="SPI_CLK")],
        ),
        Component(
            ref="J1",
            footprint="CONN_USB",
            bounds=(4.0, 4.0),
            pins=[Pin("1", "1", (0, 0), net="+3V3")],
        ),
    ]
    nets = [
        # Multi-pin HV-classified nets tied to Q1/Q2/D1/D2 — the
        # "historically-stuck" set the partition rescues. Each net
        # connects two pins on adjacent HV components so the
        # deterministic A* router can always find a path on the
        # clearance grid. Without the partition, these nets were
        # dropped because LV components crowded the routing
        # channels; with the partition, HV↔HV routing has the
        # entire HV ring + interior to itself.
        Net(
            "DC_BUS+",
            [("Q1", "1"), ("Q2", "1"), ("Q1", "2"), ("Q2", "2")],
            net_class="HighVoltage",
        ),
        Net(
            "AC_L",
            [("D1", "1"), ("D2", "1"), ("D1", "2"), ("D2", "2")],
            net_class="ACMains",
        ),
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

    # Minimal KiCadMetadata: just board dimensions + empty courtyards /
    # pad sizes. The partition stage only needs state.config + the
    # netlist / board / drc_oracle on the state itself.
    metadata = KiCadMetadata(
        courtyards={},
        pad_sizes={},
        board_width=board.width,
        board_height=board.height,
    )

    # Config-as-namespace keeps the pipeline pure-Python; the partition
    # stage reads its own block from state.config (U3 wiring). The
    # pipeline reads most fields via ``getattr`` so a dict would also
    # work for the partition lookup, but a few stages (NetClassSetup,
    # LayerAssignment) do direct ``config.net_classes`` access, so
    # SimpleNamespace is the lowest-friction shim.
    config = SimpleNamespace(
        hv_lv_guard_strip={"enabled": True},
        zones=None,
        slot_generation=None,
        fixed_positions={},
        copper_zones=[],
        net_classes={
            "HighVoltage": {"creepage_mm": 6.0, "safety_category": "HV"},
            "ACMains": {"creepage_mm": 6.0, "safety_category": "AC"},
            "Signal": {"creepage_mm": 0.0, "safety_category": "LV"},
        },
        net_class_rules={
            "HighVoltage": SimpleNamespace(
                name="HighVoltage",
                trace_width_mm=3.0,
                clearance_mm=2.0,
                via_size_mm=1.2,
                via_drill_mm=0.6,
                via_template=None,
                creepage_mm=6.0,
                dru_priority=20,
                safety_category="HV",
            ),
            "ACMains": SimpleNamespace(
                name="ACMains",
                trace_width_mm=2.5,
                clearance_mm=6.0,
                via_size_mm=1.2,
                via_drill_mm=0.6,
                via_template=None,
                creepage_mm=6.0,
                dru_priority=10,
                safety_category="AC",
            ),
            "Signal": SimpleNamespace(
                name="Signal",
                trace_width_mm=0.2,
                clearance_mm=0.15,
                via_size_mm=0.6,
                via_drill_mm=0.3,
                via_template=None,
                creepage_mm=0.0,
                dru_priority=80,
                safety_category="LV",
            ),
        },
        differential_pairs=[],
        net_priority={},
        signal_hv_clearances=[],
        placement_proximity=[],
        hv_exclusion_zones=[],
    )

    initial_state = BoardState(
        board=board,
        netlist=netlist,
        drc_oracle=SimpleNamespace(design_rules=design_rules),
    )

    # Drive the full pipeline end-to-end.
    pipeline = create_drc_aware_pipeline(
        design_rules=design_rules,
        config=config,
        metadata=metadata,
        zone_aware=True,
    )
    result = pipeline.run(initial_state)

    # (1) Sanity: partition actually engaged (proves Fix #1 + Fix #4
    # are doing their job — stage ran with config attached, and ran
    # BEFORE the placement stage so the domain map was visible).
    assert result.component_domain_map, (
        "HvLvPartitionStage produced an empty domain map; check that "
        "the stage runs before component assignment and that "
        "state.config was populated."
    )
    assert result.domain_regions and len(result.domain_regions) == 2
    assert result.routing_corridors, "Routing corridor must be present"

    domain_map = {ref: domain for ref, domain in result.component_domain_map}
    for ref in HV_COMPONENT_REFS:
        assert domain_map.get(ref) == "HV_edge", (
            f"{ref} should be in the HV_edge bucket but is in "
            f"{domain_map.get(ref)!r}"
        )
    for ref in ("U_MCU", "J1"):
        assert domain_map.get(ref) == "LV_interior", (
            f"{ref} should be in the LV_interior bucket but is in "
            f"{domain_map.get(ref)!r}"
        )

    # (2) SM2: Build a footprint polygon per ref and verify HV-edge
    # refs do not intersect LV-interior refs by ≥ CREEPAGE_MARGIN_MM.
    placement_map = dict(result.placements)
    footprint_by_ref: dict[str, Polygon] = {}
    for comp in netlist.components:
        pos = placement_map.get(comp.ref)
        if pos is None:
            # Component not placed (no slot available) — skip from
            # geometry check; routing check below will still apply.
            continue
        w, h = comp.bounds
        cx, cy = pos[0], pos[1]
        footprint_by_ref[comp.ref] = Polygon(
            [
                (cx - w / 2.0, cy - h / 2.0),
                (cx + w / 2.0, cy - h / 2.0),
                (cx + w / 2.0, cy + h / 2.0),
                (cx - w / 2.0, cy + h / 2.0),
            ]
        )

    hv_refs_in_state = [
        ref for ref in HV_COMPONENT_REFS if ref in footprint_by_ref
    ]
    lv_refs_in_state = [
        ref
        for ref, domain in domain_map.items()
        if domain == "LV_interior" and ref in footprint_by_ref
    ]
    assert hv_refs_in_state, "No HV components were placed"
    assert lv_refs_in_state, "No LV components were placed"

    for hv_ref in hv_refs_in_state:
        hv_poly = footprint_by_ref[hv_ref]
        for lv_ref in lv_refs_in_state:
            lv_poly = footprint_by_ref[lv_ref]
            # distance < 0 means actual polygon overlap; >=
            # CREEPAGE_MARGIN_MM means they are separated by at
            # least the IEC 60335-1 creepage margin.
            gap = hv_poly.distance(lv_poly)
            assert gap >= CREEPAGE_MARGIN_MM, (
                f"HV-edge {hv_ref} footprint intersects LV-interior "
                f"{lv_ref} footprint (gap={gap:.2f}mm, required "
                f">= {CREEPAGE_MARGIN_MM}mm)"
            )

    # (3) SM3: each historically-stuck multi-pin HV net must have
    # been routed. A net is "successfully routed" when at least
    # one trace in state.routes names it. Single-pin nets produce
    # no traces (nothing to connect), so the SM3 assertion only
    # applies to nets that actually have a path to route.
    hv_nets = {
        net.name
        for net in netlist.nets
        if len(net.pins) >= 2
        and any(ref in HV_COMPONENT_REFS for ref, _ in net.pins)
    }
    assert hv_nets, "No multi-pin HV nets in fixture"

    routed_nets = {trace.net for trace in result.routes if getattr(trace, "net", None)}
    missing = hv_nets - routed_nets
    assert not missing, (
        f"Historically-stuck HV nets not routed: {sorted(missing)} "
        f"(routed: {sorted(routed_nets)})"
    )
