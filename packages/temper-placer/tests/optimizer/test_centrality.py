"""
Unit tests for eigenvector centrality (temper-7qr).

Tests cover:
- Eigenvector centrality computation from adjacency matrix.
- Verification of hub centrality in star and complex topologies.
"""

import jax.numpy as jnp
import pytest

from temper_placer.core.netlist import (
    Component,
    Net,
    Netlist,
    build_adjacency_matrix,
    compute_eigenvector_centrality,
)


@pytest.fixture
def mcu_star_netlist():
    """
    Create a star topology with an MCU hub and several passives.
    
    Topology:
        R1 -- [N1] -- MCU
        R2 -- [N2] -- MCU
        R3 -- [N3] -- MCU
        R4 -- [N4] -- MCU
    """
    components = [
        Component(ref="MCU", footprint="QFP", bounds=(10.0, 10.0)),
        Component(ref="R1", footprint="0603", bounds=(1.6, 0.8)),
        Component(ref="R2", footprint="0603", bounds=(1.6, 0.8)),
        Component(ref="R3", footprint="0603", bounds=(1.6, 0.8)),
        Component(ref="R4", footprint="0603", bounds=(1.6, 0.8)),
    ]

    nets = [
        Net(name="N1", pins=[("MCU", "1"), ("R1", "1")]),
        Net(name="N2", pins=[("MCU", "2"), ("R2", "1")]),
        Net(name="N3", pins=[("MCU", "3"), ("R3", "1")]),
        Net(name="N4", pins=[("MCU", "4"), ("R4", "1")]),
    ]

    return Netlist(components=components, nets=nets)


@pytest.fixture
def complex_netlist():
    """
    Create a more complex topology.
    MCU (Hub)
    /  |  \
    U1  U2  U3 (Secondary Hubs)
    |   |   |
    R1  R2  R3 (Leaves)
    """
    components = [
        Component(ref="MCU", footprint="QFP", bounds=(10.0, 10.0)),
        Component(ref="U1", footprint="SOIC", bounds=(5.0, 4.0)),
        Component(ref="U2", footprint="SOIC", bounds=(5.0, 4.0)),
        Component(ref="U3", footprint="SOIC", bounds=(5.0, 4.0)),
        Component(ref="R1", footprint="0603", bounds=(1.6, 0.8)),
        Component(ref="R2", footprint="0603", bounds=(1.6, 0.8)),
        Component(ref="R3", footprint="0603", bounds=(1.6, 0.8)),
    ]

    nets = [
        Net(name="M1", pins=[("MCU", "1"), ("U1", "1")]),
        Net(name="M2", pins=[("MCU", "2"), ("U2", "1")]),
        Net(name="M3", pins=[("MCU", "3"), ("U3", "1")]),
        Net(name="L1", pins=[("U1", "2"), ("R1", "1")]),
        Net(name="L2", pins=[("U2", "2"), ("R2", "1")]),
        Net(name="L3", pins=[("U3", "2"), ("R3", "1")]),
    ]

    return Netlist(components=components, nets=nets)


def test_compute_eigenvector_centrality_star(mcu_star_netlist):
    """Verify MCU has highest centrality in a star topology."""
    adj = build_adjacency_matrix(mcu_star_netlist)
    centrality = compute_eigenvector_centrality(adj)

    assert centrality.shape == (5,)

    # MCU is index 0
    mcu_centrality = centrality[0]
    passive_centralities = centrality[1:]

    assert mcu_centrality > jnp.max(passive_centralities)
    # In a perfect star, all passives should have same centrality
    assert jnp.allclose(passive_centralities, passive_centralities[0])


def test_compute_eigenvector_centrality_complex(complex_netlist):
    """Verify centrality hierarchy: MCU > Us > Rs."""
    adj = build_adjacency_matrix(complex_netlist)
    centrality = compute_eigenvector_centrality(adj)

    # Indices: MCU=0, U1=1, U2=2, U3=3, R1=4, R2=5, R3=6
    mcu_c = centrality[0]
    u_c = centrality[1:4]
    r_c = centrality[4:7]

    assert mcu_c > jnp.max(u_c)
    assert jnp.min(u_c) > jnp.max(r_c)


def test_empty_adjacency():
    """Empty adjacency should return empty centrality."""
    adj = jnp.zeros((0, 0))
    centrality = compute_eigenvector_centrality(adj)
    assert centrality.shape == (0,)


def test_single_node():
    """Single node should have centrality 1.0."""
    adj = jnp.zeros((1, 1))
    centrality = compute_eigenvector_centrality(adj)
    assert centrality.shape == (1,)
    assert centrality[0] == 1.0
