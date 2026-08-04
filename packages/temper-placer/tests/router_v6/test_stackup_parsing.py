"""Stackup extraction: declared-stackup and fallback paths.

Wave 4 Phase 3 candidate 3: the stackup assembly
(``temper_placer.io._parse_board._extract_stackup``) now consumes the Rust
engine's raw stackup data via ``pcb_content`` (kiutils left the boundary), so
these tests drive it with synthetic board text instead of in-memory kiutils
objects. The asserted invariants are unchanged from the pre-migration tests.
"""

from temper_placer.io._parse_board import _extract_stackup


def _board_text(zones: list[tuple[str, str]] | None = None, layers_decl: list[str] | None = None) -> str:
    """A minimal board with an optional declared stackup and zones.

    ``zones``: list of (net_name, layer) pairs. ``layers_decl``: optional list
    of board layer names (fallback path uses the .Cu suffix count).
    """
    zone_sexprs = ""
    for net_name, layer in zones or []:
        zone_sexprs += (
            f'  (zone (net 1) (net_name "{net_name}") (layer "{layer}")\n'
            "    (polygon (pts (xy 0 0) (xy 10 0) (xy 10 10) (xy 0 10)))\n"
            "  )\n"
        )
    layers = ""
    if layers_decl:
        layers = "  (layers\n"
        for i, name in enumerate(layers_decl):
            layers += f'    ({i} "{name}" signal)\n'
        layers += "  )\n"
    return (
        "(kicad_pcb (version 20211014) (generator test)\n"
        "  (general (thickness 1.6))\n"
        f"{layers}"
        '  (net 0 "")\n'
        '  (net 1 "GND")\n'
        "  (setup\n"
        "    (stackup\n"
        '      (layer "F.SilkS" (type "Top Silk Screen"))\n'
        '      (layer "F.Mask" (type "Top Solder Mask") (thickness 0.01))\n'
        '      (layer "F.Cu" (type "copper") (thickness 0.035))\n'
        '      (layer "dielectric 1" (type "core") (thickness 1.51) (material "FR4") (epsilon_r 4.5) (loss_tangent 0.02))\n'
        '      (layer "B.Cu" (type "copper") (thickness 0.035))\n'
        '      (layer "B.Mask" (type "Bottom Solder Mask") (thickness 0.01))\n'
        "    )\n"
        "  )\n"
        f"{zone_sexprs}"
        ")\n"
    )


def _board_fallback_text(
    layers_decl: list[str],
    thickness: float = 1.6,
    zones: list[tuple[str, str]] | None = None,
) -> str:
    """Fallback-path board text (no declared stackup): the layer declaration
    drives the .Cu count; optional zones drive the plane assignments."""
    layers = "  (layers\n"
    for i, name in enumerate(layers_decl):
        layers += f'    ({i} "{name}" signal)\n'
    layers += "  )\n"
    zone_sexprs = ""
    for net_name, layer in zones or []:
        zone_sexprs += (
            f'  (zone (net 1) (net_name "{net_name}") (layer "{layer}")\n'
            "    (polygon (pts (xy 0 0) (xy 10 0) (xy 10 10) (xy 0 10)))\n"
            "  )\n"
        )
    return (
        "(kicad_pcb (version 20211014) (generator test)\n"
        f"  (general (thickness {thickness}))\n"
        f"{layers}"
        '  (net 0 "")\n'
        '  (net 1 "GND")\n'
        f"{zone_sexprs}"
        ")\n"
    )


def test_parse_stackup_from_setup():
    """Test parsing stackup from KiCad board setup (Method 1)."""
    text = _board_text(zones=[("GND", "F.Cu")])
    stackup = _extract_stackup(None, [], pcb_content=text)

    assert stackup.layer_count == 2
    assert abs(stackup.total_thickness_mm - 1.6) < 0.0001  # 0.01*2 + 0.035*2 + 1.51 = 1.6
    assert len(stackup.layers) == 2

    # Check Copper Layers
    assert stackup.layers[0].name == "F.Cu"
    assert stackup.layers[0].layer_type == "plane"  # GND zone -> plane
    assert stackup.layers[0].plane_net == "GND"
    assert stackup.layers[1].name == "B.Cu"
    assert stackup.layers[1].layer_type == "signal"

    assert abs(stackup.layers[0].thickness_um - 35.0) < 0.001
    assert len(stackup.dielectrics) == 1
    assert stackup.dielectrics[0].name == "dielectric 1"
    assert abs(stackup.dielectrics[0].thickness_mm - 1.51) < 0.001
    assert abs(stackup.dielectrics[0].epsilon_r - 4.5) < 0.001
    assert abs(stackup.dielectrics[0].loss_tangent - 0.02) < 0.001


def test_parse_stackup_fallback():
    """Boards without a declared stackup fall back to the layer-count
    heuristic. Per-layer plane/mixed/signal classification is pinned (the
    GND zone on In1.Cu must turn that layer into a plane and surface the
    plane_net -- the plane-assignment assertions the migration temporarily
    lost are restored here)."""
    text = _board_fallback_text(
        ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu", "F.SilkS", "B.SilkS", "Edge.Cuts"],
        zones=[("GND", "In1.Cu")],
    )
    stackup = _extract_stackup(None, [], pcb_content=text)

    assert stackup.layer_count == 4
    assert len(stackup.layers) == 4

    # F.Cu: signal default
    assert stackup.layers[0].name == "F.Cu"
    assert stackup.layers[0].layer_type == "signal"
    assert stackup.layers[0].plane_net is None

    # In1.Cu: plane due to the GND zone
    assert stackup.layers[1].name == "In1.Cu"
    assert stackup.layers[1].layer_type == "plane"
    assert stackup.layers[1].plane_net == "GND"

    # In2.Cu: mixed default
    assert stackup.layers[2].name == "In2.Cu"
    assert stackup.layers[2].layer_type == "mixed"
    assert stackup.layers[2].plane_net is None

    # B.Cu: signal default
    assert stackup.layers[3].name == "B.Cu"
    assert stackup.layers[3].layer_type == "signal"
    assert stackup.layers[3].plane_net is None

    # Fallback assumes default thickness logic and no dielectrics.
    assert abs(stackup.total_thickness_mm - 1.6) < 0.0001
    assert len(stackup.dielectrics) == 0


def test_parse_stackup_fallback_declared_role_ignores_zone_content():
    """use_declared_layer_roles=True: outer layers are signal even when a
    plane-required zone sits on them (fallback path)."""
    text = _board_fallback_text(
        ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu", "F.SilkS", "B.SilkS", "Edge.Cuts"]
    )
    stackup = _extract_stackup(None, [], pcb_content=text, use_declared_layer_roles=True)

    assert stackup.layer_count == 4
    assert stackup.layers[0].layer_type == "signal"
    assert stackup.layers[-1].layer_type == "signal"
    assert stackup.layers[1].layer_type == "mixed"
    assert stackup.layers[2].layer_type == "mixed"


def test_parse_stackup_from_setup_declared_role_ignores_zone_content():
    """use_declared_layer_roles=True: role from structural position, not zone
    content; plane_net is still surfaced (declared-stackup path)."""
    text = _board_text(zones=[("GND", "F.Cu")])
    stackup = _extract_stackup(None, [], pcb_content=text, use_declared_layer_roles=True)

    assert stackup.layers[0].layer_type == "signal"  # outer despite GND zone
    assert stackup.layers[0].plane_net == "GND"  # zone info still surfaced
    assert stackup.layers[1].layer_type == "signal"
