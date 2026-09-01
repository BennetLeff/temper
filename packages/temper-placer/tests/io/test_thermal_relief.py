"""Thermal-relief semantics of the power-plane zone writer.

The pre-migration ``zone_manager.create_zone`` built kiutils ``Zone``
objects with thermal relief parameters; the de-kiutils'd writer builds
the same content in Rust (``power_plane_zone_sexpr_py``) and serializes
through the parse engine's text path. Byte parity with the kiutils
construction is pinned differentially in
``test_zone_manager_rust_differential.py``; this module pins the
load-bearing fields directly on the shipped code path.
"""

from temper_io_types import kicad_write_geometry as _GEOM

from temper_placer.io.zone_manager import PlaneConfig, create_zone_sexpr


def test_create_zone_sexpr_has_thermal_relief():
    """Verify the zone s-expression sets thermal relief parameters."""
    config = PlaneConfig(
        layer="In1.Cu",
        net_name="GND",
        priority=1,
        clearance=0.4,
        min_thickness=0.25,
        thermal_gap=0.6,
        thermal_bridge_width=0.7,
    )

    outline = [(0, 0), (10, 0), (10, 10), (0, 10)]

    zone = create_zone_sexpr(1, config, outline)

    by_key = {item[0]: item for item in zone[1:]}
    assert by_key["net_name"][1] == "GND"
    assert by_key["layer"][1] == "In1.Cu"
    assert by_key["name"][1] == "GND_plane"
    assert by_key["priority"][1] == 1

    connect_pads = by_key["connect_pads"]
    assert "thermal_reliefs" in connect_pads
    clearance_item = next(c for c in connect_pads[1:] if isinstance(c, list) and c[0] == "clearance")
    assert clearance_item[1] == 0.4

    fill = by_key["fill"]
    assert fill[1] == "yes"
    gap_item = next(c for c in fill[2:] if isinstance(c, list) and c[0] == "thermal_gap")
    bridge_item = next(c for c in fill[2:] if isinstance(c, list) and c[0] == "thermal_bridge_width")
    assert gap_item[1] == 0.6
    assert bridge_item[1] == 0.7


def test_power_plane_kernel_matches_python_delegation():
    """create_zone_sexpr must delegate to the Rust kernel unchanged."""
    config = PlaneConfig(layer="In2.Cu", net_name="+5V", clearance=0.35)
    outline = [(0.0, 0.0), (5.0, 5.0)]
    expected = _GEOM.power_plane_zone_sexpr_py(
        "+5V", 4, "In2.Cu", 0, 0.35, 0.25, 0.5, 0.5, outline
    )
    assert create_zone_sexpr(4, config, outline) == expected
