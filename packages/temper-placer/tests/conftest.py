"""
Pytest configuration and shared fixtures for temper-placer tests.
"""

from pathlib import Path

import jax
import pytest

from temper_placer.core.board import Board, Zone
from temper_placer.core.design_rules import DesignRules, NetClassRules
from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.core.state import PlacementState
from temper_placer.deterministic.state import BoardState
from temper_placer.io.footprint_library import load_footprint_library


def _make_temper_design_rules() -> DesignRules:
    """Subset of core/design_rules.py:337-444 net classes for fixture use."""
    return DesignRules(
        net_classes={
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
            "HighVoltage": NetClassRules(
                name="HighVoltage",
                trace_width=3.0,
                clearance=2.0,
                via_diameter=1.2,
                via_drill=0.6,
                creepage_mm=2.0,
                dru_priority=20,
                safety_category="HV",
            ),
            "Power": NetClassRules(
                name="Power",
                trace_width=0.5,
                clearance=0.25,
                via_diameter=0.8,
                via_drill=0.4,
                dru_priority=40,
                safety_category="LV",
            ),
            "Signal": NetClassRules(
                name="Signal",
                trace_width=0.2,
                clearance=0.15,
                via_diameter=0.6,
                via_drill=0.3,
                dru_priority=80,
                safety_category="LV",
            ),
        },
        net_class_assignments={},
    )


@pytest.fixture
def rng_key():
    """Provide a consistent JAX random key for reproducible tests."""
    return jax.random.PRNGKey(42)


@pytest.fixture
def simple_board():
    """Create a simple 100x100mm board for testing."""
    return Board(
        width=100.0,
        height=100.0,
        origin=(0.0, 0.0),
        zones=[
            Zone("ZONE_A", (0, 0, 50, 100)),
            Zone("ZONE_B", (50, 0, 100, 100)),
        ],
    )


@pytest.fixture
def temper_board():
    """Create the default Temper board for testing."""
    return Board.temper_default()


@pytest.fixture
def simple_components():
    """Create a list of simple test components."""
    return [
        Component(
            ref="U1",
            footprint="SOIC-8",
            bounds=(5.0, 4.0),
            pins=[
                Pin("VCC", "8", (2.0, 1.5), net="VCC"),
                Pin("GND", "4", (-2.0, -1.5), net="GND"),
                Pin("IN", "1", (-2.0, 1.5), net="SIG_IN"),
                Pin("OUT", "5", (2.0, -1.5), net="SIG_OUT"),
            ],
            net_class="Signal",
        ),
        Component(
            ref="R1",
            footprint="0603",
            bounds=(1.6, 0.8),
            pins=[
                Pin("1", "1", (-0.75, 0.0), net="SIG_IN"),
                Pin("2", "2", (0.75, 0.0), net="NET1"),
            ],
            net_class="Signal",
        ),
        Component(
            ref="C1",
            footprint="0805",
            bounds=(2.0, 1.25),
            pins=[
                Pin("1", "1", (-0.9, 0.0), net="VCC"),
                Pin("2", "2", (0.9, 0.0), net="GND"),
            ],
            net_class="Signal",
        ),
    ]


@pytest.fixture
def simple_nets():
    """Create simple test nets."""
    return [
        Net("VCC", [("U1", "VCC"), ("C1", "1")], net_class="Power", weight=1.0),
        Net("GND", [("U1", "GND"), ("C1", "2")], net_class="Power", weight=1.0),
        Net("SIG_IN", [("U1", "IN"), ("R1", "1")], net_class="Signal", weight=1.5),
        Net("SIG_OUT", [("U1", "OUT")], net_class="Signal", weight=1.0),
        Net("NET1", [("R1", "2")], net_class="Signal", weight=1.0),
    ]


@pytest.fixture
def simple_netlist(simple_components, simple_nets):
    """Create a complete simple netlist for testing."""
    return Netlist(components=simple_components, nets=simple_nets)


@pytest.fixture
def simple_placement_state(simple_netlist, rng_key):
    """Create a random placement state for the simple netlist."""
    return PlacementState.random_init(
        n_components=simple_netlist.n_components,
        board_width=100.0,
        board_height=100.0,
        key=rng_key,
        margin=10.0,
    )


# =============================================================================
# Footprint Library Fixtures (temper-1my.1.3)
# =============================================================================


@pytest.fixture(scope="session")
def footprint_library():
    """
    Load the footprint library once per test session.

    Returns cached library for all tests that need accurate component bounds.
    """
    library_path = Path("configs/footprint_library.yaml")
    if not library_path.exists():
        # Fallback to creating minimal library for tests
        pytest.skip(f"Footprint library not found: {library_path}")

    return load_footprint_library(library_path)


@pytest.fixture
def component_factory(footprint_library):
    """
    Factory function for creating components with library-accurate bounds.

    Usage:
        comp = component_factory("R1", "0805", pins=[...])

    The factory looks up bounds from the footprint library, ensuring
    all test components use accurate dimensions.
    """
    def make_component(ref: str, footprint: str, **kwargs):
        """Create a component with bounds from library."""
        if footprint not in footprint_library:
            raise ValueError(
                f"Unknown footprint: {footprint}. "
                f"Add to configs/footprint_library.yaml"
            )

        spec = footprint_library[footprint]

        # Override bounds with library value
        if "bounds" in kwargs:
            # Warn if bounds differ
            if kwargs["bounds"] != spec.bounds:
                import warnings
                warnings.warn(
                    f"Component {ref} has hardcoded bounds {kwargs['bounds']} "
                    f"but library specifies {spec.bounds}. Using library value."
                )

        kwargs["bounds"] = spec.bounds
        kwargs["footprint"] = footprint

        return Component(ref=ref, **kwargs)

    return make_component


# =============================================================================
# feat/hv-lv-guard-strip fixtures (plan 2026-06-23-001)
# =============================================================================


@pytest.fixture
def fixture_design_rules_temper():
    """Subset of core/design_rules.py:337-444 net classes (creepage + safety)."""
    return _make_temper_design_rules()


@pytest.fixture
def fixture_minimal_pcb(fixture_design_rules_temper):
    """10-component mixed HV/LV PCB on a 100x150 board."""
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
            ref="C_DC_BUS",
            footprint="CAP_BIG",
            bounds=(6.0, 6.0),
            pins=[Pin("1", "1", (0, 0), net="DC_BUS+")],
        ),
        Component(
            ref="U_15V",
            footprint="SOIC8",
            bounds=(5.0, 5.0),
            pins=[Pin("1", "1", (0, 0), net="+15V")],
        ),
        Component(
            ref="U_3V3",
            footprint="SOIC8",
            bounds=(5.0, 5.0),
            pins=[Pin("1", "1", (0, 0), net="+3V3")],
        ),
        Component(
            ref="U_TEMP",
            footprint="SOT23",
            bounds=(2.0, 1.5),
            pins=[Pin("1", "1", (0, 0), net="TEMP_SENSE")],
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
        Net("DC_BUS+", [("Q1", "1"), ("Q2", "1"), ("C_DC_BUS", "1")], net_class="HighVoltage"),
        Net("AC_L", [("D1", "1")], net_class="ACMains"),
        Net("AC_N", [("D2", "1")], net_class="ACMains"),
        Net("+15V", [("U_15V", "1")], net_class="Power"),
        Net("+3V3", [("U_3V3", "1"), ("J1", "1")], net_class="Power"),
        Net("TEMP_SENSE", [("U_TEMP", "1")], net_class="Signal"),
        Net("SPI_CLK", [("U_MCU", "1")], net_class="Signal"),
    ]
    return BoardState(
        board=Board(width=100.0, height=150.0),
        netlist=Netlist(components=components, nets=nets),
        drc_oracle=__import__("types").SimpleNamespace(design_rules=fixture_design_rules_temper),
    )


@pytest.fixture
def fixture_hv_lv_config_yaml():
    """The YAML block from U3, as a raw string."""
    return (
        "hv_lv_guard_strip:\n"
        "  enabled: true\n"
        "  width_mm: null\n"
        "  fallback_to_unconstrained: true\n"
    )
