"""
Pytest configuration and shared fixtures for temper-placer tests.
"""

import pytest
import jax
import jax.numpy as jnp
from pathlib import Path

from temper_placer.core.state import PlacementState
from temper_placer.core.netlist import Component, Pin, Net, Netlist
from temper_placer.core.board import Board, Zone, LayerStackup
from temper_placer.io.footprint_library import load_footprint_library, FootprintLibrary


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
