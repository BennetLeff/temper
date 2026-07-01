"""Integration test: auto_enrich generates constraints from Temper board data."""

import pytest

from temper_placer.core.board import Board, Zone
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.pcl.constraints import (
    AdjacentConstraint,
    ConstraintTier,
    KeepoutConstraint,
)
from temper_placer.pcl.parser import ConstraintCollection
from temper_placer.pcl.tagged_constraints import (
    TaggedAdjacentConstraint,
    TaggedAlignedConstraint,
    TaggedAnchoredConstraint,
    TaggedOnSideConstraint,
)
from temper_placer.pcl.tag_dispatch import ComponentTag, TagRef
from temper_placer.pcl.constraints import Axis, BoardSide, EdgeType


def test_keepout_auto_emission():
    """Zones with type='keepout' auto-emit KeepoutConstraint."""
    board = Board(
        120, 80,
        zones=[
            Zone(
                name="ISOLATION_BARRIER",
                bounds=(60, 0, 70, 80),
                zone_type="keepout",
            )
        ],
    )
    nl = Netlist(
        components=[
            Component(
                ref="U1",
                footprint="QFN32",
                bounds=(10, 10),
                pins=[
                    Pin("VCC", "1", (0, 0), net="VCC"),
                    Pin("GND", "2", (0, 0), net="GND"),
                ],
                net_class="Power",
            )
        ],
        nets=[],
    )

    collection = ConstraintCollection(constraints=[])
    collection.auto_enrich(nl, board)

    keepouts = [
        c for c in collection.constraints if isinstance(c, KeepoutConstraint)
    ]
    assert len(keepouts) == 1
    assert keepouts[0].zone_name == "ISOLATION_BARRIER"
    assert keepouts[0].tier == ConstraintTier.HARD
    assert "keepout" in keepouts[0].because.lower()


def test_no_keepout_for_placement_zones():
    """Placement zones should NOT auto-emit keepout constraints."""
    board = Board(
        120, 80,
        zones=[
            Zone(
                name="MCU_ZONE",
                bounds=(20, 20, 60, 60),
                zone_type="placement",
            )
        ],
    )
    nl = Netlist(components=[], nets=[])

    collection = ConstraintCollection(constraints=[])
    collection.auto_enrich(nl, board)

    keepouts = [
        c for c in collection.constraints if isinstance(c, KeepoutConstraint)
    ]
    assert len(keepouts) == 0


def test_decoupling_auto_detection():
    """Small cap on power net near IC is auto-detected."""
    # IC "U1" with 5 pins, one to VCC
    u1_pins = [
        Pin("VCC", "1", (0, 0), net="VCC"),
        Pin("GND", "2", (0, 0), net="GND"),
        Pin("IO1", "3", (0, 0), net="SIG1"),
        Pin("IO2", "4", (0, 0), net="SIG2"),
        Pin("RESET", "5", (0, 0), net="RST"),
    ]
    # Capacitor "C1" on VCC, known footprint "0402", 2 pins
    c1_pins = [
        Pin("1", "1", (0, 0), net="VCC"),
        Pin("2", "2", (0, 0), net="GND"),
    ]

    nl = Netlist(
        components=[
            Component(ref="U1", footprint="QFN32", bounds=(10, 10), pins=u1_pins),
            Component(ref="C1", footprint="0402", bounds=(2, 1), pins=c1_pins),
        ],
        nets=[
            Net(name="VCC", pins=[("U1", "VCC"), ("C1", "1")], net_class="Power"),
            Net(name="GND", pins=[("U1", "GND"), ("C1", "2")], net_class="Power"),
        ],
    )

    collection = ConstraintCollection(constraints=[])
    collection.auto_enrich(nl)

    adjacent = [
        c for c in collection.constraints if isinstance(c, AdjacentConstraint)
    ]
    assert len(adjacent) >= 1
    c1_u1 = [
        c for c in adjacent if c.a == "C1" and c.b == "U1"
    ]
    assert len(c1_u1) >= 1, f"Expected at least one C1->U1 constraint, got {adjacent}"


def test_decoupling_no_false_positives():
    """Non-decoupling components should not generate constraints."""
    c1_pins = [
        Pin("1", "1", (0, 0), net="SIG1"),
        Pin("2", "2", (0, 0), net="GND"),
    ]
    u1_pins = [
        Pin("A", "1", (0, 0), net="SIG1"),
    ]

    nl = Netlist(
        components=[
            Component(ref="U1", footprint="QFN32", bounds=(10, 10), pins=u1_pins),
            Component(ref="C1", footprint="0402", bounds=(2, 1), pins=c1_pins),
        ],
        nets=[
            Net(name="SIG1", pins=[("U1", "A"), ("C1", "1")], net_class="Signal"),
        ],
    )

    collection = ConstraintCollection(constraints=[])
    collection.auto_enrich(nl)

    adjacent = [
        c for c in collection.constraints if isinstance(c, AdjacentConstraint)
    ]
    # Signal nets (not power) should not produce decoupling constraints
    # because _is_power_net("SIG1") is False and _classify returns NOT_DECOUPLING
    # Actually _shared_vital_net may return "SIG1" since it's shared.
    # But _classify will check _is_power_net and return NOT_DECOUPLING
    # since SIG1 doesn't match power patterns and is non-V/non-BAT.
    # So no decoupling should be detected.
    assert len(adjacent) == 0


def test_decoupling_without_board():
    """auto_enrich with netlist only should still detect decoupling."""
    c1_pins = [
        Pin("1", "1", (0, 0), net="VCC"),
        Pin("2", "2", (0, 0), net="GND"),
    ]
    u1_pins = [
        Pin("VCC", "1", (0, 0), net="VCC"),
        Pin("GND", "2", (0, 0), net="GND"),
        Pin("IO1", "3", (0, 0), net="SIG1"),
        Pin("IO2", "4", (0, 0), net="SIG2"),
    ]

    nl = Netlist(
        components=[
            Component(ref="U1", footprint="QFN32", bounds=(10, 10), pins=u1_pins),
            Component(ref="C1", footprint="0402", bounds=(2, 1), pins=c1_pins),
        ],
        nets=[
            Net(name="VCC", pins=[("U1", "VCC"), ("C1", "1")], net_class="Power"),
            Net(name="GND", pins=[("U1", "GND"), ("C1", "2")], net_class="Power"),
        ],
    )

    collection = ConstraintCollection(constraints=[])
    collection.auto_enrich(nl, board=None)

    adjacent = [
        c for c in collection.constraints if isinstance(c, AdjacentConstraint)
    ]
    assert len(adjacent) >= 1


def test_tag_adjacent_expansion():
    """TaggedAdjacentConstraint expands into concrete AdjacentConstraint pairs."""
    r1_pins = [
        Pin("1", "1", (0, 0), net="SIG"),
        Pin("2", "2", (0, 0), net="GND"),
    ]
    r2_pins = [
        Pin("1", "1", (0, 0), net="SIG"),
        Pin("2", "2", (0, 0), net="GND"),
    ]
    r3_pins = [
        Pin("1", "1", (0, 0), net="SIG"),
        Pin("2", "2", (0, 0), net="GND"),
    ]

    nl = Netlist(
        components=[
            Component(
                ref="R1",
                footprint="0805",
                bounds=(2, 1),
                pins=r1_pins,
                tags=frozenset({"power"}),
            ),
            Component(
                ref="R2",
                footprint="0805",
                bounds=(2, 1),
                pins=r2_pins,
                tags=frozenset({"power"}),
            ),
            Component(
                ref="R3",
                footprint="0805",
                bounds=(2, 1),
                pins=r3_pins,
                tags=frozenset({"power"}),
            ),
        ],
        nets=[
            Net(name="SIG", pins=[("R1", "1"), ("R2", "1"), ("R3", "1")]),
        ],
    )

    tag_power = TagRef(ComponentTag.POWER)
    tagged = TaggedAdjacentConstraint(
        tag_expr_a=tag_power,
        tag_expr_b=tag_power,
        max_distance_mm=5.0,
        tier=ConstraintTier.STRONG,
        because="Keep power components close",
    )

    collection = ConstraintCollection(constraints=[tagged])
    collection.auto_enrich(nl)

    adjacent = [
        c for c in collection.constraints if isinstance(c, AdjacentConstraint)
    ]
    # 3 components matching "power" tag: R1, R2, R3
    # Cross product excluding self-pairs: 3 * 3 - 3 = 6
    assert len(adjacent) == 6, f"Expected 6 pairs, got {len(adjacent)}: {adjacent}"

    for c in adjacent:
        assert c.max_distance_mm == 5.0
        assert c.tier == ConstraintTier.STRONG
        assert "Keep power" in c.because


def test_tag_aligned_expansion():
    """TaggedAlignedConstraint expands into concrete AlignedConstraint."""
    c1_pins = [Pin("1", "1", (0, 0), net="VCC")]
    c2_pins = [Pin("1", "1", (0, 0), net="VCC")]

    nl = Netlist(
        components=[
            Component(
                ref="C1",
                footprint="0402",
                bounds=(2, 1),
                pins=c1_pins,
                tags=frozenset({"decoupling"}),
            ),
            Component(
                ref="C2",
                footprint="0402",
                bounds=(2, 1),
                pins=c2_pins,
                tags=frozenset({"decoupling"}),
            ),
        ],
        nets=[],
    )

    tagged = TaggedAlignedConstraint(
        tag_expr=TagRef(ComponentTag.DECOUPLING),
        axis=Axis.X,
        tier=ConstraintTier.SOFT,
        because="Align decoupling caps",
        tolerance_mm=0.3,
    )

    collection = ConstraintCollection(constraints=[tagged])
    collection.auto_enrich(nl)

    from temper_placer.pcl.constraints import AlignedConstraint

    aligned = [
        c for c in collection.constraints if isinstance(c, AlignedConstraint)
    ]
    assert len(aligned) == 1
    assert set(aligned[0].components) == {"C1", "C2"}
    assert aligned[0].axis == Axis.X
    assert aligned[0].tolerance_mm == 0.3


def test_tag_on_side_expansion():
    """TaggedOnSideConstraint expands into concrete OnSideConstraint."""
    c1_pins = [Pin("1", "1", (0, 0), net="VCC")]

    nl = Netlist(
        components=[
            Component(
                ref="C1",
                footprint="0402",
                bounds=(2, 1),
                pins=c1_pins,
                tags=frozenset({"connector"}),
            ),
        ],
        nets=[],
    )

    tagged = TaggedOnSideConstraint(
        tag_expr=TagRef(ComponentTag.CONNECTOR),
        side=BoardSide.LEFT,
        edge=EdgeType.FLUSH,
        tier=ConstraintTier.HARD,
        because="Connector on left edge",
    )

    collection = ConstraintCollection(constraints=[tagged])
    collection.auto_enrich(nl)

    from temper_placer.pcl.constraints import OnSideConstraint

    on_side = [
        c for c in collection.constraints if isinstance(c, OnSideConstraint)
    ]
    assert len(on_side) == 1
    assert on_side[0].components == ["C1"]
    assert on_side[0].side == BoardSide.LEFT


def test_tag_anchored_expansion():
    """TaggedAnchoredConstraint expands into concrete AnchoredConstraint."""
    c1_pins = [Pin("1", "1", (0, 0), net="VCC")]

    nl = Netlist(
        components=[
            Component(
                ref="C1",
                footprint="0402",
                bounds=(2, 1),
                pins=c1_pins,
                tags=frozenset({"mcu"}),
            ),
        ],
        nets=[],
    )

    tagged = TaggedAnchoredConstraint(
        tag_expr=TagRef(ComponentTag.MCU),
        region=(10.0, 10.0, 50.0, 50.0),
        tier=ConstraintTier.STRONG,
        because="MCU in center region",
    )

    collection = ConstraintCollection(constraints=[tagged])
    collection.auto_enrich(nl)

    from temper_placer.pcl.constraints import AnchoredConstraint

    anchored = [
        c for c in collection.constraints if isinstance(c, AnchoredConstraint)
    ]
    assert len(anchored) == 1
    assert anchored[0].component == "C1"
    assert anchored[0].region == (10.0, 10.0, 50.0, 50.0)


def test_enrich_preserves_existing_constraints():
    """auto_enrich should not remove existing manually-defined constraints."""
    board = Board(
        120, 80,
        zones=[
            Zone(
                name="KEEPOUT",
                bounds=(0, 0, 10, 80),
                zone_type="keepout",
            )
        ],
    )
    c1_pins = [
        Pin("1", "1", (0, 0), net="VCC"),
        Pin("2", "2", (0, 0), net="GND"),
    ]
    u1_pins = [
        Pin("VCC", "1", (0, 0), net="VCC"),
        Pin("GND", "2", (0, 0), net="GND"),
        Pin("IO1", "3", (0, 0), net="SIG"),
        Pin("IO2", "4", (0, 0), net="SIG"),
    ]
    nl = Netlist(
        components=[
            Component(ref="U1", footprint="QFN32", bounds=(10, 10), pins=u1_pins),
            Component(ref="C1", footprint="0402", bounds=(2, 1), pins=c1_pins),
        ],
        nets=[
            Net(name="VCC", pins=[("U1", "VCC"), ("C1", "1")], net_class="Power"),
            Net(name="GND", pins=[("U1", "GND"), ("C1", "2")], net_class="Power"),
        ],
    )

    existing = AdjacentConstraint(
        a="Q1",
        b="Q2",
        max_distance_mm=10.0,
        tier=ConstraintTier.HARD,
        because="Manual adjacent constraint",
    )
    collection = ConstraintCollection(constraints=[existing])
    collection.auto_enrich(nl, board)

    # Original constraint should still be present
    assert existing in collection.constraints
    # Keepout should be present
    keepouts = [
        c for c in collection.constraints if isinstance(c, KeepoutConstraint)
    ]
    assert len(keepouts) == 1
    # Decoupling should be present
    adjacent = [
        c for c in collection.constraints if isinstance(c, AdjacentConstraint)
    ]
    assert len(adjacent) >= 2  # original + at least 1 decoupling
