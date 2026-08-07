"""SAT channel-edge identity must come from GEOMETRY, not construction order.

This is the contract that blocked `channel_skeleton.py` from ever being
reimplemented. Edge identity used to be built from
`enumerate(graph.edges)` — networkx INSERTION order — plus the raw float
`repr()` of both endpoints, because skeleton nodes *are* coordinate tuples
(`G.add_node(p1, pos=p1)`).

So a reimplementation that produced identical geometry by a different route
produced different SAT variable NAMES. A 2026-08-04 spike measured an
independent Voronoi reproducing the skeleton to <1e-9 mm on 12/12 boards — the
geometry was never the obstacle; this naming contract was.
"""

from __future__ import annotations

import networkx as nx
import pytest
from temper_placer.router_v6.constraint_model import canonical_channel_edges

A = (1.0, 2.0)
B = (3.0, 4.0)
C = (5.0, 6.0)


def _ids(graph):
    return [eid for eid, _u, _v in canonical_channel_edges(graph, "F.Cu")]


def test_insertion_order_does_not_change_identity():
    """The same geometry built in two orders must yield the same names."""
    g1 = nx.Graph()
    for u, v in [(A, B), (B, C), (A, C)]:
        g1.add_edge(u, v)

    g2 = nx.Graph()
    for u, v in [(A, C), (B, C), (A, B)]:  # reversed insertion
        g2.add_edge(u, v)

    assert _ids(g1) == _ids(g2), "identity still depends on insertion order"


def test_endpoint_order_within_an_edge_does_not_matter():
    g1 = nx.Graph()
    g1.add_edge(A, B)
    g2 = nx.Graph()
    g2.add_edge(B, A)
    assert _ids(g1) == _ids(g2)


def test_coordinates_are_quantised_not_raw_repr():
    """Two endpoints differing below the quantum are the same edge.

    1e-6 mm is a nanometre — orders of magnitude below any manufacturing
    tolerance — so a reimplementation agreeing to <1e-9 mm must land on the
    same name rather than a different one.
    """
    g1 = nx.Graph()
    g1.add_edge((1.0, 2.0), (3.0, 4.0))
    g2 = nx.Graph()
    g2.add_edge((1.0 + 1e-12, 2.0), (3.0, 4.0 - 1e-12))
    assert _ids(g1) == _ids(g2), "sub-nanometre noise still changes identity"


def test_names_carry_no_raw_float_repr():
    """A raw tuple repr would leak `(1.0, 2.0)`-style unrounded text."""
    g = nx.Graph()
    g.add_edge((1.0, 2.0), (3.0, 4.0))
    (eid,) = _ids(g)
    assert "1.000000" in eid and "2.000000" in eid
    assert eid.startswith("F.Cu_E0_")


def test_distinct_edges_stay_distinct():
    """The index tie-break must keep names unique."""
    g = nx.Graph()
    for u, v in [(A, B), (B, C), (A, C)]:
        g.add_edge(u, v)
    ids = _ids(g)
    assert len(ids) == len(set(ids)) == 3


def test_geometry_changes_do_change_identity():
    """Anti-vacuity: normalisation must not flatten genuinely different edges."""
    g1 = nx.Graph()
    g1.add_edge(A, B)
    g2 = nx.Graph()
    g2.add_edge(A, C)
    assert _ids(g1) != _ids(g2)
