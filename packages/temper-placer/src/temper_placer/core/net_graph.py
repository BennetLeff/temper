"""
Net Graph and Sub-Net Edge definitions for topology-aware routing.

This module defines data structures for decomposing nets into directed graphs
of sub-net edges, each with its own routing constraints. This enables
star-point connections (Kelvin sensing) and mixed-signal routing rules
within a single electrical net.

Migrated to Rust pyclasses (Wave C, temper-design-bundle).
This module is now a pure-delegation shim re-exporting the pyclasses.
"""

import temper_design_bundle_python as _tdb

NetGraph = _tdb.net_graph_contracts.NetGraph
SubNetEdge = _tdb.net_graph_contracts.SubNetEdge

__all__ = ["NetGraph", "SubNetEdge"]
