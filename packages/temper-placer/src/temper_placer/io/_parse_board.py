"""Internal: board geometry, stackup, and setup extraction from KiCad board objects.

Migrated to the Rust parse engine (``temper_design_bundle_python.parse_engine``,
Wave 4 Phase 3 candidate 3). What moved to Rust:

- board geometry / zones / mounting holes — run inside ``parse_kicad_pcb``;
- the raw stackup + zone/net data feeding the v6 stackup assembly
  (``parse_engine.extract_stackup_raw``).

What deliberately stays Python (R3-style boundary, argued in VERIFICATION.md):

- ``_is_plane_required_net`` — reads the netclass SSOT constants
  (``TEMPER_NET_ASSIGNMENTS``/``TEMPER_NET_CLASSES``) that the
  ``core/design_rules`` delegation shim still owns in Python.
- ``_extract_stackup`` — the v6-only assembly targeting the Python dataclasses
  ``StackupInfo``/``LayerInfo``/``DielectricInfo`` (``router_v6.stage0_data``);
  it consumes the Rust raw data.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import temper_design_bundle_python as _tdb

from temper_placer.core.board import STANDARD_LAYER_ORDER

_rs = _tdb.parse_engine

if TYPE_CHECKING:
    from temper_placer.router_v6.stage0_data import StackupInfo


def _is_plane_required_net(net_name: str) -> bool:
    """Whether a zone's net should mark its physical copper layer as a
    non-routable "plane" layer -- routing_space.py:85 excludes any layer
    whose ``layer_type`` is not ``"signal"``/``"mixed"`` from the router's
    grid entirely, so this decision controls whether an *entire physical
    layer* stays in the routing space.

    Reads the netclass SSOT first: a net whose class (``TEMPER_NET_ASSIGNMENTS``)
    declares ``routing_strategy == "plane_required"`` (``core/design_rules.py`` --
    today only ``ACMains``/``HighVoltage``) is plane-worthy. This is the
    same SSOT field ``_zone_layers_for_net()``
    (``router_v6/_adapter_convert.py``) drives zone-*generation* eligibility
    from, so the two decisions ("should this net get a pour" and "does a
    pour on this net make its layer non-routable") stay in step by
    construction instead of drifting independently.

    Falls back to a word-boundary-anchored keyword match (never a bare
    substring ``in`` test -- see
    ``docs/solutions/best-practices/substring-net-classification-drifts-from-ssot-2026-07-27.md``)
    for nets absent from the SSOT's per-net assignment table, so an
    unrecognized or renamed net isn't silently treated as never plane-worthy.

    FIXED 2026-07-28: the previous version tested bare
    ``"GND" in netName or "VCC" in netName or "+" in netName or "PWR" in
    netName``. A single ``"+"`` character matched *any* net containing
    one, including ``+3V3`` (Power class -- a handful of sub-mm2
    decoupling-cap zone islands, per
    ``docs/evidence/2026-07-28-pour-strategy-audit.md``), flipping an
    entire outer copper layer to "plane" and removing it from the
    router's routing space over a single small, non-plane-worthy zone.
    The old test was also case-sensitive (missed lowercase ``vcc``) and
    unanchored (``"GND" in "CGND"`` matched a distinct net, chassis
    ground, not literal GND).

    Kept in Python: reads the Python-side netclass SSOT (``core/design_rules``
    keeps its constant tables per the delegation precedent).

    FIXED 2026-08-13 (URGENT hyphen-boundary net-classification defect,
    "Family C" -- see PR #1145/#1162's "Family A"/"Family B" fixes
    elsewhere in this repo): the keyword fallback's word boundary was "_"
    or start/end of string ONLY -- "-" was never a boundary character,
    even though 85 of the 162 real net names on the production board
    contain a hyphen. "-" is now an equivalent boundary character to "_".
    Board-wide simulation of all 162 real net names found exactly one
    flip for this function's keyword set (GND/VCC/PWR): ``hb-gnd`` (now
    plane-eligible) -- correct/intended, matching PR #1145's own finding
    for this net. See
    docs/evidence/2026-08-13-hyphen-boundary-clearance-creepage-defect.md.
    """
    from temper_placer.core.design_rules import TEMPER_NET_ASSIGNMENTS, TEMPER_NET_CLASSES

    nc_name = TEMPER_NET_ASSIGNMENTS.get(net_name, "")
    nc = TEMPER_NET_CLASSES.get(nc_name)
    if nc is not None:
        return nc.routing_strategy == "plane_required"

    upper = net_name.upper()
    return any(
        re.search(rf"(?:^|[_-]){kw}(?:$|[\d_-])", upper) for kw in ("GND", "VCC", "PWR")
    )


def _extract_stackup(
    _ki_board: object | None,
    warnings: list[str],
    *,
    use_declared_layer_roles: bool = False,
    pcb_content: str | None = None,
) -> StackupInfo:
    """
    Extract PCB layer stackup from KiCad board content.

    Migrated (candidate 3): the raw stackup/zones come from the Rust engine
    (``parse_engine.extract_stackup_raw``); the assembly below targets the
    Python ``router_v6.stage0_data`` dataclasses and reads the netclass SSOT
    via ``_is_plane_required_net``, so it stays Python. ``_ki_board`` is
    accepted for call compatibility but unused (kiutils left the boundary);
    ``pcb_content`` is the raw board text (the v6 wrapper already reads it for
    design rules).

    Args:
        _ki_board: Accepted for call compatibility (unused).
        warnings: List to append warnings.
        use_declared_layer_roles: When ``True``, a layer's ``layer_type``
            (R8) comes purely from its structural position in the declared
            stackup (outer layers -- index 0 and the last copper index --
            are "signal"; inner layers are "mixed") and is never overridden
            by what happens to be poured on it. ``plane_net`` is still
            populated from the zone scan when a plane-required net's zone
            sits on that layer, so callers that want "does this layer carry
            a plane-required pour" keep that information -- only the
            *routability* classification stops reading zone content.

            Defaults to ``False``: today's behavior, unchanged. A zone on a
            plane-required net (``_is_plane_required_net``) still forces its
            whole physical layer to ``"plane"``, which
            ``routing_space.py``'s ``compute_routing_space`` then excludes
            from the router's routing space entirely (R8's bug).

            NOT SAFE TO ENABLE ALONE IN PRODUCTION: this only changes
            layer *role* classification. It does not stop the router's
            obstacle map (``obstacle_map.py``) from treating the board's
            existing, un-regenerated zones as opaque obstacles on every
            layer they sit on -- so flipping this on before pours become
            derived output (this plan's U3) reproduces the recorded 12x
            completion regression in
            ``docs/evidence/2026-07-28-stackup-partial-revert.md``. Land
            this flag's flip to ``True`` in the same change as U3.
        pcb_content: Raw ``.kicad_pcb`` text; when None the board is treated
            as having no declared stackup (fallback path).
    """
    from temper_placer.router_v6.stage0_data import (
        DielectricInfo,
        LayerInfo,
        StackupInfo,
    )

    layers = []
    parsed_dielectrics = []

    raw = _rs.extract_stackup_raw(pcb_content) if pcb_content else {}
    raw_zones = raw.get("zones", []) if raw else []
    raw_stackup = raw.get("stackup_layers", []) if raw else []
    board_layers = raw.get("layers", []) if raw else []
    general_thickness = raw.get("general_thickness") if raw else None

    plane_assignments = {}
    for zone in raw_zones:
        if zone["layers"] and zone["net_name"]:
            for layer in zone["layers"]:
                is_power = _is_plane_required_net(zone["net_name"])
                if is_power and layer.endswith(".Cu"):
                    plane_assignments[layer] = zone["net_name"]

    if raw_stackup:
        total_thickness = 0.0

        copper_layers = []
        raw_dielectrics = []

        for layer in raw_stackup:
            if layer["thickness"] is not None:
                total_thickness += layer["thickness"]

            if layer["type"] == "copper":
                copper_layers.append(layer)
            elif layer["type"] in ["core", "prepreg", "dielectric"] or "dielectric" in layer["type"]:
                raw_dielectrics.append(layer)

        layer_count = len(copper_layers)

        for i, layer in enumerate(copper_layers):
            name = layer["name"]

            if use_declared_layer_roles:
                # R8: role comes from the stackup declaration -- structural
                # position among this board's declared copper layers -- not
                # from zone content. plane_net is still surfaced when a
                # plane-required zone sits here, but it no longer decides
                # layer_type.
                layer_type = "signal" if i == 0 or i == layer_count - 1 else "mixed"
                plane_net = plane_assignments.get(name)
            elif name in plane_assignments:
                layer_type = "plane"
                plane_net = plane_assignments[name]
            elif i == 0 or i == layer_count - 1:
                layer_type = "signal"
                plane_net = None
            else:
                layer_type = "mixed"
                plane_net = None

            thickness_um = (layer["thickness"] * 1000.0) if layer["thickness"] else 35.0

            layers.append(
                LayerInfo(
                    index=i,
                    name=name,
                    layer_type=layer_type,
                    thickness_um=thickness_um,
                    plane_net=plane_net,
                )
            )

        for d in raw_dielectrics:
            epsilon_r = d.get("epsilon_r")
            if epsilon_r is None:
                epsilon_r = 4.5

            loss_tangent = d.get("loss_tangent")
            if loss_tangent is None:
                loss_tangent = 0.02

            parsed_dielectrics.append(
                DielectricInfo(
                    name=d["name"],
                    material=d.get("material") or "FR4",
                    thickness_mm=d["thickness"] if d.get("thickness") else 0.0,
                    epsilon_r=epsilon_r or 4.5,
                    loss_tangent=loss_tangent or 0.02,
                )
            )

    else:
        layer_count = 2
        if board_layers:
            # NOTE: must be a suffix match, not `in`. A substring check matches
            # "Edge.Cuts" (its tail ".Cuts" starts with ".Cu") as a spurious
            # 5th "copper" layer on a real 4-layer board, which pushes this
            # function into the "unusual layer count" branch below and
            # fabricates a phantom "In3.Cu" that does not exist on the board.
            # See docs/evidence/2026-07-27-phantom-layer-stackup.md.
            copper_layers = [ly for ly in board_layers if ly.endswith(".Cu")]
            layer_count = len(copper_layers)

        if layer_count == 2:
            layer_names = ["F.Cu", "B.Cu"]
        elif layer_count == 4:
            layer_names = [str(idx) for idx in STANDARD_LAYER_ORDER]
        elif layer_count == 6:
            layer_names = ["F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "B.Cu"]
        else:
            warnings.append(f"Unusual layer count: {layer_count}. Using generic naming.")
            layer_names = ["F.Cu"] + [f"In{i}.Cu" for i in range(1, layer_count - 1)] + ["B.Cu"]

        for i, name in enumerate(layer_names):
            # REVERTED 2026-07-28, deliberately. a1fe623e added a branch here
            # forcing F.Cu/B.Cu to "signal" on a 4-layer board before the
            # zone-netname heuristic ran, on the authority of
            # docs/hardware/POWER_PLANE_DESIGN.md and the 4-layer enforcement
            # plan (outer = signal, inner = GND/PWR planes).
            #
            # That is what the DESIGN DOCUMENTS say. It is not what the BOARD
            # is. pcb/temper.kicad_pcb pours per-net copper fill on F.Cu/B.Cu
            # for creepage and thermal reasons, so both outer layers are
            # effectively occupied. Measured, same harness, only this file
            # differing:
            #
            #     outer forced to signal : 3.12% completion, 93/96 unrouted
            #     zone heuristic honoured: 38.54% completion, 59/96 unrouted
            #
            # A 12x regression -- layer assignment spread nets onto two blocked
            # layers. test_astar_3d_production_scale_spike confirms the
            # mechanism: with F.Cu present it cannot construct ANY free
            # same-layer segment on it.
            #
            # The zone heuristic is therefore kept: it describes the artifact,
            # and the artifact is what gets routed. The phantom-In3.Cu half of
            # a1fe623e is RETAINED (see the .endswith(".Cu") fixes above) --
            # that layer genuinely does not exist.
            #
            # OPEN DESIGN QUESTION, not a code defect: the docs and the board
            # disagree about whether the outer layers should be poured at all.
            # Resolving that is a board decision. Until then this code follows
            # the board. See docs/evidence/2026-07-28-stackup-partial-revert.md.
            #
            # `use_declared_layer_roles=True` (U2, opt-in, default off) is the
            # supported way out of this tension: role is read from structural
            # position in the declared stackup, never from zone content, so
            # a handful of small plane-required pours (e.g. 4 of 48 zones on
            # F.Cu on the production board) no longer condemns the whole
            # physical layer. It must not be turned on before pours become
            # derived output (U3) -- see the docstring above.
            if use_declared_layer_roles:
                layer_type = "signal" if i == 0 or i == layer_count - 1 else "mixed"
                plane_net = plane_assignments.get(name)
            elif name in plane_assignments:
                layer_type = "plane"
                plane_net = plane_assignments[name]
            elif i == 0 or i == layer_count - 1:
                layer_type = "signal"
                plane_net = None
            else:
                layer_type = "mixed"
                plane_net = None

            thickness_um = 35.0

            layers.append(
                LayerInfo(
                    index=i,
                    name=name,
                    layer_type=layer_type,
                    thickness_um=thickness_um,
                    plane_net=plane_net,
                )
            )

        total_thickness = 1.6 if layer_count >= 4 else 0.8

        if general_thickness is not None:
            total_thickness = general_thickness

    return StackupInfo(
        layers=layers,
        total_thickness_mm=total_thickness,
        layer_count=layer_count,
        dielectrics=parsed_dielectrics,
    )
