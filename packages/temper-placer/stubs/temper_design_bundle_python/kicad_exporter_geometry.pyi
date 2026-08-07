"""Type stubs for `temper_design_bundle_python.kicad_exporter_geometry`.

Compiled from `packages/temper-design-bundle/src/kicad_exporter_geometry.rs`
-- the Wave 4 Phase 3 (formats/IO) migration of the two GEOMETRY/matching
kernels ported out of `temper_placer/io/kicad_exporter.py`
(`snap_to_nearest_pad`, `_generate_connector_segments`). Keep in sync with
that file.

``generate_connector_segments_py``'s segment/pad_centers/return tuples are
``(net, start, end, width, layer)`` and ``(net, [(x, y), ...])`` respectively
-- see the Rust docstring on that function.
"""

from __future__ import annotations

def snap_to_nearest_pad_py(
    x: float,
    y: float,
    pad_centers: list[tuple[float, float]],
    tolerance: float = ...,
) -> tuple[float, float]: ...


def generate_connector_segments_py(
    segments: list[tuple[str, tuple[float, float], tuple[float, float], float, str]],
    pad_centers: list[tuple[str, list[tuple[float, float]]]],
    max_dist: float = ...,
) -> list[tuple[str, tuple[float, float], tuple[float, float], float, str]]: ...
