"""
Geometry types shared between the deterministic pipeline and router_v6.

These are pure dataclass types with no dependencies on router_v6 or deterministic.
They serve as the lowest-level geometry vocabulary for pads, tracks, vias, and points.

Migrated to Rust pyclasses (Wave C, temper-design-bundle, ``geometry_contracts`` submodule).
This module is now a pure-delegation shim re-exporting the pyclasses under their
original Python names.

Wave 4 (unit ``core_graph_cluster``): the scalar numeric methods were previously
migrated to ``packages/temper-geometry/src/core_graph_geometry.rs``.
"""

import temper_design_bundle_python as _tdb

Point = _tdb.geometry_contracts.GeometryPoint
Track = _tdb.geometry_contracts.GeometryTrack
Via = _tdb.geometry_contracts.GeometryVia
Pad = _tdb.geometry_contracts.GeometryPad

__all__ = ["Point", "Track", "Via", "Pad"]
