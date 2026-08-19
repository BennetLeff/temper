"""In2.Cu power-island generation for the ``+3V3``/``vcc``/``+15V``/
``V_BUS_SENSE`` rails (feat/in2cu-power-islands).

**Why this module exists.** ``docs/evidence/2026-08-11-keepout-before-pour-spike.md``
(#1022/#1033) traced why ``pcb/temper.kicad_pcb`` declares ``In1.Cu``/
``In2.Cu`` as power-plane layers (commit ``c4956df66``) but both are
completely empty: (1) the Rust board parser
(``packages/temper-design-bundle/src/parse_engine.rs``) reads a layer's
*name* and discards its declared *role* token, so nothing downstream can
key off "this is a power-plane layer"; and (2)
``router_v6/_zone_pour_stitch.py::_zone_layers_for_net`` -- the only place
in the production ``route_pcb()`` path that emits ``(zone ...)``
geometry -- hardcoded its return value to ``["F.Cu", "B.Cu"]`` for every
zone-eligible net, so no code path in ``router_v6`` could ever emit a
zone on an inner layer at all. #1022/#1033 fixed cause (2) narrowly for
``In1.Cu``/``gnd`` by bypassing ``_zone_layers_for_net`` entirely (a
dedicated generator, ``_ground_plane.py``, calling the same zone-emission
primitives directly). This module is the ``In2.Cu`` counterpart, and
**does the same thing for the same reason, not the reason originally
proposed** -- see the course-correction below before reading further.

**Course correction on how this module reaches ``_zone_layers_for_net``.**
This task's own brief suggested driving inner-layer eligibility from
``NetClassRules.routing_strategy`` -- "the ``GND``/``Power`` classes carry
``routing_strategy: plane_preferred`` ... that is probably the right
signal" -- mirroring the paired fix ``design_rules.py``'s ``GND`` entry
and ``_zone_layers_for_net``'s ``nc_name == "GND"`` branch already got
(R3/R4, docs/plans/2026-07-29-001-fix-pour-derivation-rule-plan.md).
**Measured, not assumed: this premise is false for ``Power`` on this
board today.** ``TEMPER_NET_CLASSES["Power"].routing_strategy`` is
``None`` (the dataclass default), not ``"plane_preferred"`` -- and
setting it to match GND's fix was prototyped here and reverted, because
doing so does not close an accidental drift the way GND's fix did; it
**reverts an already-landed, evidence-corroborated, actively-tested
decision that Power stays trace-only.** That decision is R1/R7 of the
SAME plan document GND's own fix comes from:

- R1: "No net in ``Power`` or ``GateDrive`` gets a default pour: ``+3V3``,
  ``vcc``, ``+15V``, ``+15V_LS``, ``V_BUS_SENSE`` ... route as traces
  only," corroborated three independent ways --
  ``docs/hardware/TRACE_WIDTH_CALCULATIONS.md`` SS3.4/3.6-3.8 gives each of
  these nets a trace-width spec with local decoupling, never a pour spec;
  ``packages/temper-placer/configs/temper_constraints.yaml`` (a
  human-authored, independent net-class table) declares
  ``Power: routing_strategy: "wide_trace"``, not a plane tier at all; and
  ``docs/evidence/2026-07-28-pour-strategy-audit.md`` Task 1 independently
  reached DELETE (not pour) for all nine Power/GateDrive nets after
  checking real current budgets.
- R7: an explicit regression test,
  ``tests/router_v6/test_adapter.py::TestZoneLayersForNet.test_power_class_is_not_zone_eligible``,
  asserts ``_zone_layers_for_net("+3V3") == []`` (and the same for
  ``vcc``/``+15V``/``V_BUS_SENSE``) by name, specifically so a regression
  re-granting Power a pour would fail loudly instead of passing silently.
  Roughly a dozen other fixtures across the same test file were
  deliberately rewritten 2026-07-28 and again 2026-07-30 to stop using
  ``vcc``/``+3V3`` as "zone-eligible" test data, for the same reason.

Flipping ``Power.routing_strategy`` would not add an In2.Cu option
alongside the existing trace-only behavior -- it would silently revert
R1/R7 for every production ``route_pcb()`` call, re-granting these four
rails an *outer-layer* (F.Cu/B.Cu) pour too, which is exactly the
regression R7's test exists to catch. ``deterministic/stages/power_plane.py``'s
own docstring (this task's other cited source for "Power belongs on
In2.Cu") is not independent corroboration of the opposite conclusion --
it is a design note in a pipeline no production entry point invokes
(see ``_ground_plane.py``'s own module docstring, S:2e), naming nets
(``+5V``, ``VCC_BOOT``) that do not exist on the compiled board at all,
which is itself a sign of drift rather than a currently-validated
intent to weigh against R1's three live, cross-checked sources.

Given that, ``_zone_layers_for_net`` is **left completely unchanged** by
this task (see that function's own updated docstring for the pointer
back here). This module instead follows the precedent ``_ground_plane.py``
already set for ``In1.Cu``/``gnd``: a standalone generator that calls
the zone-emission primitives (``zone_emission.compute_zones_for_net``/
``emit_zone_s_expr``) directly, never going through ``_zone_layers_for_net``
at all -- so ``In2.Cu`` becomes expressible without touching R1/R7's
tested guarantee for a single production net. Cause (1) (``parse_engine.rs``'s
discarded layer-role token) is **also** not touched -- see "What this
does not do" below for why.

**Power islands are plural, not one plane.** Unlike ``gnd`` (a single
convex hull over all 86 pads), ``In2.Cu`` per this project's own
documented stackup intent carries *per-rail regions* -- ``+3V3``,
``+15V``, ``vcc``, ``V_BUS_SENSE`` each get their own copper, and those
regions must not touch each other (they are different nets sharing one
physical layer) on top of not touching the HV keepout ``_ground_plane.py``
already had to solve for. This module processes rails in priority order
(largest pad count first: ``+3V3`` (51), ``vcc`` (13), ``+15V`` (10),
``V_BUS_SENSE`` (4) -- measured directly against the production board,
2026-08-11) and accumulates each rail's own new copper (zone footprint,
drop vias, backbone segments) into the obstacle set every later rail's
geometry is kept clear of -- the single genuinely new geometry problem
this task has that the ground-plane spike did not: inter-rail clearance
on a shared layer, not just net-vs-HV-keepout.

**What this module reuses from ``_ground_plane.py`` (read-only import,
never modified -- out of this task's boundary).** The hard-won,
already-measured-safe primitives: ``compute_hv_selv_keepout`` (per-pad HV
buffer union, not a global band -- a global band was tried and measured
to fail on this board's real geometry), ``_collect_hv_copper_geometry``
(HV pad/via half-extent buffering, not just centres -- the fix for the
25-creepage-violation gap a centre-only buffer left), ``_collect_other_net_copper``,
``_existing_drilled_holes``, ``_find_via_drop_point``, ``mst_edges``,
``_emit_keepout_zone_s_expr``, ``_dedupe_positions``. None of that logic
is re-derived here; only the *multi-net accumulation* around it is new.

**What this module does NOT do (out of budget, reported honestly rather
than silently skipped):**

- **``parse_engine.rs`` is not touched.** The task names two independent
  root causes; this module addresses the second (the emitter path) the
  same way ``_ground_plane.py`` already did for ``In1.Cu`` -- a standalone
  generator bypassing ``_zone_layers_for_net`` entirely, not by making
  either function read the layer-role token. Fixing (1) requires
  rebuilding a shared pyo3/maturin extension (``temper-design-bundle``)
  that this sandbox's own tooling notes document as fragile under
  concurrent worktree builds (stale ``.so`` after a reported-successful
  ``maturin develop``, a shared venv multiple agents' worktrees point
  at). Given this module's bypass route is sufficient to make an
  inner-layer zone expressible and measurable end-to-end without it,
  rebuilding a shared native extension for a second, redundant path to
  the same capability was judged not worth the shared-environment risk
  this run.
- **UPDATED 2026-08-12**: the line above ("No MST backbone routing
  avoids OTHER rails'/nets' existing F.Cu copper") described the
  straight-line-MST-plus-one-bend-detour heuristic, which is genuinely
  incapable of this (measured: collapses connectivity). It is no longer
  the whole story -- ``_corridor_backbone.py``'s corridor-aware A* pass
  is now tried first for every MST edge (both the HV keepout and every
  other net's/rail's existing F.Cu copper), falling back to the
  keepout-only detour only for edges A* cannot solve (a measured,
  genuine fraction -- see that module's docstring). Residual
  ``tracks_crossing``/``clearance`` against pre-existing other-net
  copper is therefore reduced, not eliminated; still an honest,
  partial result, reported per-rail via
  ``PowerIslandResult.mst_edges_astar_routed_count`` /
  ``mst_edges_fallback_count``.
- **UPDATED 2026-08-19**: the MST backbone is no longer on ``F.Cu`` at
  all. It is on ``PLANE_LAYER`` (``In2.Cu``), the layer the pours are on,
  so "every other net's/rail's existing F.Cu copper" above now reads as
  "every other net's/rail's copper reaching ``In2.Cu``" -- which on this
  board is foreign THROUGH-VIA BARRELS, the gnd plane's own drop vias,
  and the other three rails. See ``BACKBONE_LAYER``'s comment for why the
  F.Cu choice was a workaround for a ``pad_connectivity_audit.py``
  limitation that no longer exists, and the MST-backbone emission site for
  the per-rail cost of leaving it. Consequences recorded here because
  they change this module's shape, not just a constant:

  * ``generate_power_islands_blocks`` is now a **two-pass** loop. Pass 1
    computes all four rails' zone footprints; pass 2 places their vias and
    routes their backbones. With the backbone on the shared plane, a rail
    must clear the pours of rails that come AFTER it in priority order,
    and in a single pass those pours do not exist yet. Priority ordering
    alone cannot fix that -- whichever rail routes first is blind to all
    the rest. Full rationale at the pass-1 loop head.
  * The backbone spans **barrel positions**, not pad positions. On F.Cu a
    pad position is the pad's own copper; on ``In2.Cu`` it is bare metal,
    reached only where a plated barrel passes through. ``_ground_plane.py``
    measured the difference on ``In1.Cu`` the day before: pad positions
    gave 204 plane segments and moved connectivity 5 -> 7 of 88 pads;
    barrel positions moved it to 16 and cut that net's copper from 54
    components to 8.
  * ``STUB_LAYER`` (``F.Cu``) is now separate from ``BACKBONE_LAYER``: the
    pad-to-offset-via stub must stay on the pad's own layer.
"""

from __future__ import annotations

import logging
from pathlib import Path

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from temper_placer.core.design_rules import TEMPER_NET_CLASSES
from temper_placer.router_v6._ground_plane import (
    _collect_hv_copper_geometry,
    _collect_other_net_copper,
    _dedupe_positions,
    _emit_keepout_zone_s_expr,
    _existing_drilled_holes,
    _find_via_drop_point,
    compute_hv_selv_keepout,
    mst_edges,
)

logger = logging.getLogger(__name__)

PLANE_LAYER = "In2.Cu"
# CHANGED 2026-08-19 (F.Cu -> PLANE_LAYER), mirroring the identical fix
# `_ground_plane.py` took the day before (a71765efe). The comment this
# replaced read:
#
#   "a via only unions pad_connectivity_audit's graph nodes for the layers
#    *literally present* in its own ``via.layers`` tuple ... so the
#    backbone must land on a layer the via's own ``(layers "F.Cu" "B.Cu")``
#    tuple already names, not on PLANE_LAYER itself."
#
# That was true when it was written (ce4c132d6, 2026-08-11) and stopped
# being true five days later: ``dabbeaf73`` (2026-08-16) taught
# ``pad_connectivity_audit._parse_segments_and_vias`` KiCad's real via
# typing, so an untyped ``(via ...)`` is now parsed as a THROUGH via
# (``layers=()``, the ``CopperVia`` convention for "spans every layer the
# checker knows about") and unions across the whole stack, In2.Cu
# included -- exactly as the physical board does. Nobody revisited this
# constant, so the workaround outlived its cause here just as it did in
# the sibling module. See the MST-backbone emission site below for the
# measured cost of leaving it (all four rails' backbones were competing
# for corridor space on F.Cu, the board's most congested layer, against
# 652 routed segments and a 27499 mm^2 HV keepout: 43/49 +3V3 edges and
# 100% of vcc's, +15V's and V_BUS_SENSE's were dropped fail-closed).
BACKBONE_LAYER = PLANE_LAYER
# The pad-to-offset-via stub is NOT on BACKBONE_LAYER: it exists to join a
# rail pad to the drop via that had to move off the pad centre, and the
# pad is on F.Cu. A stub on an inner layer would touch neither. The via
# itself (a through-via) carries the join down to BACKBONE_LAYER.
STUB_LAYER = "F.Cu"

# NOTE: the comment this replaced claimed this matched design_rules.py's
# Power netclass via convention "0.8/0.4mm exactly" -- that was already
# stale before this fix: Power's via_diameter/via_drill was corrected to
# 1.0/0.5mm on 2026-08-12 (docs/evidence/2026-08-12-netclass-param-
# reconciliation.md) and this literal constant was never updated alongside
# it, so it had already drifted from the class it claimed to mirror. This
# constant is, and always was, an independent hardcoded generator (one of
# the two literal generators of the board's 44 vias, along with
# _ground_plane.py's identical constant) -- not a derived mirror of any
# netclass table.
#
# RAISED size 0.8 -> 1.0mm 2026-08-13
# (docs/evidence/2026-08-13-jlcpcb-fab-capability-envelope.md sec.6.1,
# docs/hardware/FAB_CAPABILITY.md): the old 0.8mm pad / 0.4mm drill pair
# gave a 0.2mm annular ring, below JLCPCB's 2oz PTH annular-ring floor
# (0.254mm). Drill is unchanged (0.4mm) -- pure pad-geometry fix. New pad =
# drill + 2 x 0.3mm ring target, the board-wide 0.3mm-ring convention (see
# _ground_plane.py's identical constant and every TEMPER_NET_CLASSES
# via_diameter in core/design_rules.py).
VIA_SIZE_MM = 1.0
VIA_DRILL_MM = 0.4

# RAISED 0.3 -> Power netclass trace_width (1.0mm) 2026-08-17 (pour-stitch
# track_width root-cause fix,
# docs/evidence/2026-08-17-pour-stitch-defect-rootcause-and-m6c-reeval.md):
# every net in POWER_ISLAND_NETS ("+3V3", "vcc", "+15V", "V_BUS_SENSE") is
# classified "Power" in pcb/temper.kicad_pro, and the emitted DRU carries a
# "Power trace width" rule at min 1.0mm (design_rules.py
# TEMPER_NET_CLASSES["Power"].trace_width). This module's own comment
# above (VIA_SIZE_MM) claimed this constant was "identical" to
# _ground_plane.py's STITCH_TRACE_WIDTH_MM -- that was already false by
# the time it was written: _ground_plane.py's was raised 0.4 -> 1.0mm on
# 2026-08-16 for the exact same defect class on GND (216/747 track_width
# violations, that module's own STITCH_TRACE_WIDTH_MM comment), and this
# constant was never brought along. At 0.3mm every stitch/via-drop segment
# this generator emits for a Power-class net is, by construction, a real
# track_width DRC violation -- measured ~100 pre-existing on +3V3 alone at
# the committed board, worsening under router congestion as the MST
# generator falls back to more narrow-stub segments (see evidence doc
# above for the full before/after). Derived from TEMPER_NET_CLASSES rather
# than a second hardcoded literal, since a hardcoded copy silently
# drifting from its own netclass SSOT is exactly the failure being fixed.
# The corridor mask's erosion (compute_corridor_mask uses this same
# constant) and the inter-net blocked-check radius both widen
# correspondingly -- this is the same single-knob relationship
# _ground_plane.py's identical fix already established.
STITCH_TRACE_WIDTH_MM = TEMPER_NET_CLASSES["Power"].trace_width

BOARD_EDGE_MARGIN_MM = 1.0
OTHER_NET_CLEARANCE_MM = 0.05
# NOTE: this module deliberately does NOT redeclare
# KEEPOUT_EXTRA_MARGIN_MM/MIN_HOLE_EDGE_GAP_MM/VIA_OFFSET_RING_RADII_MM/
# VIA_OFFSET_RING_STEPS. _find_via_drop_point and compute_hv_selv_keepout
# are imported functions, not reimplemented here -- their free variables
# resolve against _ground_plane.py's own module globals regardless of
# what this module happens to name a same-named constant, so a local
# copy of those values would be inert and misleading (it would look
# like it configures the imported functions' behavior; it would not).

# Minimum edge-to-edge gap kept between one rail's own new zone footprint
# and every OTHER rail's already-emitted zone footprint this same run --
# the inter-rail-on-one-shared-layer problem _ground_plane.py never had
# (In1.Cu carries exactly one net). Not a safety-rated (creepage) figure
# -- these are all SELV/LV rails per elec/domain_manifest.yaml, so this
# is ordinary electrical clearance, sized to this board's own Power
# netclass clearance (design_rules.py: 0.25mm) with a small margin so a
# KiCad zone-fill pass (which itself adds clearance beyond a bare
# polygon-vs-polygon touch) has room to work with.
#
# DEMOTED TO A FLOOR, 2026-08-19. The "design_rules.py: 0.25mm" the
# sentence above cites is stale: ``TEMPER_NET_CLASSES["Power"].clearance``
# is 0.5mm today, and so is ``pcb/temper.kicad_pro``'s ``Power`` class --
# the value kicad-cli's own DRC enforces, and the one every rail here
# resolves to (all four are explicitly assigned ``Power`` in
# ``netclass_assignments``). 0.4mm was therefore BELOW the rule it claimed
# to implement.
#
# Rather than re-tune this literal (which would drift again the next time
# the netclass moves), every inter-rail separation in this module now
# takes ``max(this floor, _inter_rail_gap_mm(...))`` -- the pair clearance
# read from the .kicad_pro SSOT. This constant survives only as a lower
# bound, so a board whose netclass demanded LESS than 0.4mm would still
# get 0.4mm. It can no longer be the binding value on this board.
INTER_RAIL_CLEARANCE_MM = 0.4

DEFAULT_DOMAIN_MANIFEST_PATH = Path("elec/domain_manifest.yaml")

# Priority order: largest pad count first (measured against the
# production board, 2026-08-11: +3V3=51, vcc=13, +15V=10,
# V_BUS_SENSE=4 unique pad positions) -- see module docstring for why
# order matters (each later rail is clipped around every earlier rail's
# new copper).
POWER_ISLAND_NETS: tuple[str, ...] = ("+3V3", "vcc", "+15V", "V_BUS_SENSE")


__all__ = [
    "PLANE_LAYER",
    "POWER_ISLAND_NETS",
    "PowerIslandResult",
    "generate_power_islands_blocks",
    "generate_power_islands_content",
]


def _inter_rail_gap_mm(
    net_a: str,
    net_b: str,
    net_clearance: dict[str, float],
    default_clearance: float,
) -> float:
    """Edge-to-edge copper gap kicad-cli's DRC will require between
    *net_a*'s and *net_b*'s copper on a shared layer.

    KiCad resolves a pair's clearance as the MAX of the two nets' own
    netclass clearances (falling back to the ``Default`` class for a net
    with no assignment), which is the same convention
    ``_corridor_backbone.collect_other_net_copper_by_pairwise_clearance``
    already uses for foreign copper. Derived from
    ``resolve_netclass_clearances`` -- i.e. from ``pcb/temper.kicad_pro``,
    the file kicad-cli itself reads -- rather than from a module-local
    literal, precisely because the module-local literal
    (``INTER_RAIL_CLEARANCE_MM``) had already drifted below the class it
    claimed to mirror; that constant is now only a lower bound, and every
    caller here takes ``max(floor, this)``. See its own comment.

    Not a creepage figure and deliberately not compared against one: all
    four ``POWER_ISLAND_NETS`` are SELV/LV (``elec/domain_manifest.yaml``
    declares ``V_BUS_SENSE`` SELV explicitly, and ``design_rules.py``
    gives the ``Power`` class ``safety_category="LV"``), so rail-to-rail
    is ordinary electrical clearance. The reinforced 12.6mm barrier
    between any of these and the HV domain is enforced separately and
    unchanged, by the ``compute_hv_selv_keepout`` region every one of
    this module's obstacle sets already carries.
    """
    return max(
        net_clearance.get(net_a, default_clearance),
        net_clearance.get(net_b, default_clearance),
        default_clearance,
    )


class PowerIslandResult:
    """Per-rail report, mirroring ``_ground_plane.GroundPlaneResult`` so a
    caller can write the same kind of honest before/after evidence."""

    def __init__(
        self,
        *,
        net_name: str,
        pad_count: int,
        drop_via_count: int,
        mst_edge_count: int,
        zone_polygon_count: int,
        pour_area_mm2: float,
        via_skipped_through_hole_count: int = 0,
        via_offset_count: int = 0,
        via_unresolved_conflict_count: int = 0,
        mst_edges_dropped_count: int = 0,
        mst_edges_astar_routed_count: int = 0,
        mst_edges_fallback_count: int = 0,
    ) -> None:
        self.net_name = net_name
        self.pad_count = pad_count
        self.drop_via_count = drop_via_count
        self.mst_edge_count = mst_edge_count
        self.zone_polygon_count = zone_polygon_count
        self.pour_area_mm2 = pour_area_mm2
        self.via_skipped_through_hole_count = via_skipped_through_hole_count
        self.via_offset_count = via_offset_count
        self.via_unresolved_conflict_count = via_unresolved_conflict_count
        self.mst_edges_dropped_count = mst_edges_dropped_count
        self.mst_edges_astar_routed_count = mst_edges_astar_routed_count
        self.mst_edges_fallback_count = mst_edges_fallback_count

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return (
            f"PowerIslandResult(net={self.net_name!r}, pads={self.pad_count}, "
            f"drop_vias={self.drop_via_count}, mst_edges={self.mst_edge_count}, "
            f"zone_polygons={self.zone_polygon_count}, "
            f"pour_area_mm2={self.pour_area_mm2:.1f}, "
            f"via_skipped_through_hole={self.via_skipped_through_hole_count}, "
            f"via_offset={self.via_offset_count}, "
            f"via_unresolved_conflict={self.via_unresolved_conflict_count}, "
            f"mst_edges_dropped={self.mst_edges_dropped_count}, "
            f"mst_edges_astar_routed={self.mst_edges_astar_routed_count}, "
            f"mst_edges_fallback={self.mst_edges_fallback_count})"
        )


def generate_power_islands_blocks(
    pcb_path: Path,
    *,
    nets: tuple[str, ...] = POWER_ISLAND_NETS,
    domain_manifest_path: Path = DEFAULT_DOMAIN_MANIFEST_PATH,
    tstamp_counter: list[int] | None = None,
    segments: list[str] | None = None,
) -> tuple[list[str], dict[str, PowerIslandResult]]:
    """Compute per-rail ``In2.Cu`` power-island pours + via/MST stitching
    for every net in *nets* and return the NEW s-expression blocks plus
    the per-rail result reports.

    Does not write anything. This is the production wiring seam (the
    ``_ground_plane.generate_ground_plane_blocks`` counterpart): the
    caller appends the blocks to its own emitted copper after the pour
    pass. Rails are processed in the order given in *nets* (default:
    pad-count-descending); each rail's emitted zone footprint, drop vias,
    and backbone segments are folded into the obstacle set every later
    rail avoids, so the result never has two rails' new copper
    overlapping on ``In2.Cu`` (or a later rail's F.Cu/B.Cu vias landing
    on an earlier rail's). ``tstamp_counter`` is threaded from the caller
    (same convention as ``generate_ground_plane_blocks``) so the blocks'
    tstamps continue the caller's deterministic sequence; when ``None`` a
    fresh counter is used (the standalone script and the spike tests call
    it without one).

    UPDATED 2026-08-16: the pour outline for every rail is now computed
    by the Rust zone generator (``temper_geometry.pour_outline_py`` /
    ``emit_zone_outline_s_expr_py``, the #1257 machinery) carved at
    ``max(clearance, creepage)`` per foreign obstacle -- see the zone
    footprint section below for the measured rationale and the
    ``docs/evidence/2026-08-16-p3v3-in2cu-pour-feasibility.py`` data.
    """
    from temper_placer.io.kicad_parser import parse_kicad_pcb_v6
    from temper_placer.placer.cp_sat.isolation_barrier import (
        DEFAULT_CORRIDOR_WIDTH_MM,
        load_domain_manifest_nets,
    )
    from temper_placer.router_v6.pad_connectivity_audit import ALL_LAYERS, _pads_by_net
    from temper_placer.router_v6.routing_space import _get_board_polygon
    from temper_placer.router_v6.topology_copper_audit import net_number_to_name_map
    from temper_placer.router_v6.zone_emission import (
        compute_zones_for_net,
    )

    content = pcb_path.read_text()
    pcb = parse_kicad_pcb_v6(pcb_path)

    # The default manifest path is CWD-relative, and production callers
    # (route_pcb via _write_routes_to_content) run from arbitrary CWDs
    # (pytest from packages/temper-placer, route_board.py from the repo
    # root). Resolve a missing relative default against the repo root
    # (this module lives at packages/temper-placer/src/temper_placer/
    # router_v6/, so the repo root is five parents up) before handing it
    # to the loader -- the same fallback _ground_plane.py already has.
    if not domain_manifest_path.is_file() and not domain_manifest_path.is_absolute():
        alt = Path(__file__).resolve().parents[5] / domain_manifest_path
        if alt.is_file():
            domain_manifest_path = alt

    num_to_name = net_number_to_name_map(content)
    name_to_num = {v: k for k, v in num_to_name.items()}

    # Real, per-net-class-pair clearance table for the corridor-aware A*
    # obstacle grid, read once (not per rail) -- see
    # _corridor_backbone.resolve_netclass_clearances's docstring for why
    # this replaces a flat constant.
    from temper_placer.router_v6._corridor_backbone import resolve_netclass_clearances

    _net_clearance, _default_clearance = resolve_netclass_clearances(
        pcb_path.with_suffix(".kicad_pro")
    )

    pads_by_net = _pads_by_net(pcb)
    board_polygon = _get_board_polygon(pcb)
    hv_nets, _selv_nets = load_domain_manifest_nets(domain_manifest_path)

    hv_positions: list[tuple[float, float]] = []
    for net_name in sorted(hv_nets):
        for pad in pads_by_net.get(net_name, []):
            hv_positions.append(pad.position)

    keepout_pads = compute_hv_selv_keepout(
        hv_positions, [], board_polygon, DEFAULT_CORRIDOR_WIDTH_MM
    )
    hv_extra = _collect_hv_copper_geometry(pcb, hv_nets, DEFAULT_CORRIDOR_WIDTH_MM)
    keepout_parts = [g for g in (keepout_pads, hv_extra) if g is not None]
    keepout: Polygon | None = None
    if keepout_parts:
        merged = unary_union(keepout_parts).intersection(board_polygon)
        if not merged.is_empty:
            keepout = merged
    keepout_established = keepout is not None

    plane_region_base = board_polygon.buffer(-BOARD_EDGE_MARGIN_MM)
    if keepout_established:
        plane_region_base = plane_region_base.difference(keepout)

    if tstamp_counter is None:
        tstamp_counter = [0]

    def _next_tstamp() -> str:
        from temper_placer.router_v6._adapter_convert import _next_tstamp as _nt

        return _nt(tstamp_counter)

    new_blocks: list[str] = []

    # One fill-time keepout rule-area zone on PLANE_LAYER, shared by every
    # rail (the region is net-independent -- see _emit_keepout_zone_s_expr's
    # own docstring for why this is a hard, independent defense on top of
    # the pour-outline clip, not merely a duplicate of it).
    if keepout_established:
        keepout_pieces = list(keepout.geoms) if hasattr(keepout, "geoms") else [keepout]
        for piece in keepout_pieces:
            if piece.is_empty or not hasattr(piece, "exterior"):
                continue
            pts = [(float(x), float(y)) for x, y in piece.exterior.coords]
            if len(pts) > 1 and pts[0] == pts[-1]:
                pts.pop()
            if len(pts) < 3:
                continue
            new_blocks.append(_emit_keepout_zone_s_expr(pts, PLANE_LAYER, _next_tstamp()))

    # Cross-rail accumulators -- everything a LATER rail must stay clear
    # of that an EARLIER rail in this same run just added.
    other_rail_zone_region: Polygon | None = None  # In2.Cu, this run only
    run_new_holes: list[tuple[float, float, float]] = []  # any layer, this run
    run_new_fcu_copper: list[Polygon] = []  # via barrels + stubs, F.Cu, this run
    run_new_bcu_copper: list[Polygon] = []  # via barrels, B.Cu, this run
    # NEW 2026-08-19: via barrels + BACKBONE segments on PLANE_LAYER. The
    # backbone used to live on F.Cu and was accumulated into
    # ``run_new_fcu_copper``; it is now real In2.Cu copper and belongs in
    # the accumulator every later rail's In2.Cu geometry is kept clear of.
    run_new_plane_copper: list[Polygon] = []  # via barrels + backbone, In2.Cu

    results: dict[str, PowerIslandResult] = {}

    # ---------------------------------------------------------------
    # INTER-RAIL SEPARATION ON A SHARED PLANE -- the one geometry problem
    # `_ground_plane.py` never had to solve, and the reason this generator
    # is now a TWO-PASS loop rather than the single pass it was.
    #
    # In1.Cu carries exactly one net, so gnd's backbone could be routed
    # the moment gnd's own pour existed. In2.Cu carries four, and moving
    # this module's backbone onto it means +3V3's backbone is now copper
    # on the same layer as vcc's pour, +15V's pour and V_BUS_SENSE's pour.
    # A 1.0mm +3V3 trace crossing the vcc pour is not a clearance nibble;
    # it is a rail-to-rail short.
    #
    # The scheme is PRIORITY ORDERING (the option this module already
    # chose for its zones, extended to the plane's conductors) plus the
    # pass split that ordering alone cannot supply:
    #
    #   Pass 1 -- every rail's ZONE footprint, in POWER_ISLAND_NETS order
    #     (pad-count descending). Rail N's pour region excludes every
    #     EARLIER rail's pour, buffered by the real pair clearance (see
    #     the clip site: 0.5mm here, up from a flat 0.4mm that was below
    #     the Power netclass). The four footprints come out pairwise
    #     disjoint at the gap kicad-cli enforces. This pass emits no via
    #     and no track, so it depends on nothing a later pass produces.
    #
    #   Pass 2 -- every rail's DROP VIAS and BACKBONE, same order. Rail
    #     N's obstacle set now contains all THREE other rails' finished
    #     pours, not just the earlier ones, because pass 1 has already
    #     run to completion. Plus every EARLIER rail's In2.Cu vias and
    #     backbone (``run_new_plane_copper``), which is what keeps two
    #     rails' conductors apart in the gaps BETWEEN pours.
    #
    # Why the split is load-bearing and not cosmetic: in the old single
    # pass, when +3V3 (first) routed, vcc/+15V/V_BUS_SENSE had no pour
    # geometry yet -- they did not exist to avoid. That was harmless while
    # the backbone was on F.Cu and the pours were on In2.Cu. Move the
    # backbone to In2.Cu without splitting the pass and the highest-
    # priority rail, the one with the most edges, routes straight across
    # the three pours that have not been computed yet. Ordering cannot fix
    # that on its own: whichever rail goes first is blind to all the rest.
    #
    # Why priority ordering rather than a Voronoi/nearest-pour partition
    # of the free plane area: the guarantee needed here is mutual
    # separation, and sequential accumulation already gives it in full --
    # rail N avoids every other rail's pour AND every earlier rail's
    # conductors, and every later rail avoids N's, so no ordered pair is
    # unchecked. A territory partition would additionally guarantee
    # FAIRNESS (a high-priority rail cannot wall a low-priority one out of
    # a corridor), which is a routing-quality property, not a safety one,
    # and would introduce a second, independently-wrong-able notion of
    # where a rail is allowed to be. Not paid for here; if the per-rail
    # numbers show a starved low-priority rail it is visible directly in
    # ``mst_edges_dropped_count``.
    #
    # Determinism: pass 1 is a pure function of the board and the fixed
    # ``nets`` order; pass 2 consumes pass 1's completed output and the
    # same fixed order. No set iteration, no dict-order dependence, no
    # geometry keyed on anything but that order.
    # ---------------------------------------------------------------
    rail_state: list[dict] = []

    for net_name in nets:
        net_num = name_to_num.get(net_name)
        if net_num is None:
            logger.warning(
                "generate_power_islands_content: %r not found in this board's "
                "(net ...) declarations -- skipping.",
                net_name,
            )
            continue
        pads = pads_by_net.get(net_name, [])
        if not pads:
            logger.warning(
                "generate_power_islands_content: net %r has zero pads on this "
                "board -- skipping.",
                net_name,
            )
            continue
        positions = _dedupe_positions([p.position for p in pads])

        through_hole_positions: dict[tuple[float, float], bool] = {}
        for p in pads:
            key = (round(p.position[0], 3), round(p.position[1], 3))
            through_hole_positions[key] = through_hole_positions.get(key, False) or (
                p.layer == ALL_LAYERS
            )

        # --- Zone footprint: one hull per rail, carved by the Rust zone
        # generator (2026-08-16). ---
        # Previously: compute_zones_for_net(cluster=True) convex hulls
        # emitted via single-ring emit_zone_s_expr -- no carve, no holes,
        # clearance scalar only -- the same emission that fragmented the
        # historical +3V3 pours into pad-sized remnants (the measured
        # reason R1/R7 made Power trace-only). The Rust generator
        # (temper_geometry.pour_outline_py / emit_zone_outline_s_expr_py,
        # #1257) carves each foreign obstacle's halo at that pair's
        # max(clearance, creepage) -- 12.6mm HV-vs-Power creepage, not the
        # 2.0mm clearance table -- and emits one (polygon ...) element per
        # ring (exterior + holes). Measured 2026-08-16
        # (docs/evidence/2026-08-16-p3v3-in2cu-pour-feasibility.py): a
        # per-cluster carve covers 28/50 +3V3 pads in 12 zones, while a
        # SINGLE hull over all 50 pads (cluster=False, the gnd-plane
        # precedent) covers 34/50 pads in just 2 islands -- the same
        # fragmentation lesson gnd taught (see _ground_plane.py's region
        # comment): splitting the region before carving multiplies
        # islands without adding coverage. The remaining ~16 pads sit
        # inside the 12.6mm HV creepage halos and cannot be pour-covered
        # on ANY layer; they are trace-routing debt, reported honestly.
        # The pour is still PadsOnly -- padless islands are pure
        # isolated_copper liability -- and `_zone_layers_for_net` is
        # still NOT consulted (R1/R7's
        # `test_power_class_is_not_zone_eligible` stays intact: Power
        # remains outer-layer trace-only by policy; this is the
        # sanctioned `_ground_plane.py`-precedent inner-layer generator,
        # per this module's own docstring).
        import temper_geometry as _tg

        from temper_placer.router_v6.zone_pour_clearance import (
            collect_zone_obstacle_records,
        )
        from temper_placer.router_v6.zone_pour_clearance import (
            default_table as _zone_clearance_default_table,
        )
        from temper_placer.router_v6.zone_pour_creepage import default_creepage_table

        obstacle_records = [
            tuple(r)
            for r in collect_zone_obstacle_records(
                net_name,
                PLANE_LAYER,
                pcb=pcb,
                segments=[],
                net_number_to_name=num_to_name,
                clearance_table=_zone_clearance_default_table(),
                creepage_table=default_creepage_table(),
            )
        ]
        own_rust = [(float(x), float(y)) for x, y in positions]

        zones = compute_zones_for_net(
            net_name, net_num, positions, layer=PLANE_LAYER, margin=0.5, cluster=False,
            board_polygon=None,
        )
        plane_region = plane_region_base
        if other_rail_zone_region is not None:
            # RAISED 2026-08-19 from the bare INTER_RAIL_CLEARANCE_MM
            # (0.4mm) to the larger of that floor and the pair clearance
            # kicad-cli will actually enforce -- 0.5mm for any Power/Power
            # pair on this board, since all four rails are explicitly
            # assigned ``Power`` in ``pcb/temper.kicad_pro``. This is a
            # RAISE toward the SSOT, never a relaxation: the constant is
            # kept as a floor, so a board whose netclass demanded LESS
            # than 0.4mm would still get 0.4mm here.
            #
            # This clip DOES bind -- measured, in-process, by forcing the
            # gap to each value and comparing the emitted pours:
            #
            #   clip    +3V3<->vcc   +3V3<->+15V   vcc<->+15V   vcc area   +15V area
            #   0.4mm     0.3995mm      0.3993mm     0.3995mm   284.42     53.73
            #   0.5mm     0.4994mm      0.4991mm     0.4994mm   278.37     49.27
            #
            # (the ~0.0006mm shortfall is shapely's polygonal approximation
            # of the buffer arc, not a rule violation.) So at 0.4mm three
            # of the six rail pairs really did sit 0.1mm inside the 0.5mm
            # Power/Power clearance kicad-cli enforces. That is the defect
            # this fixes, and it is a fix to the POUR, independent of the
            # backbone work around it.
            #
            # Honest scope, because the first version of this comment
            # claimed more and the claim was falsified: this raise was
            # ALSO hypothesised to recover the drop vias the three small
            # rails lose once the plane carries conductors (vcc 2 -> 7
            # unresolved, +15V 4 -> 7, V_BUS_SENSE 1 -> 3; +15V down to
            # zero copper objects of its own). It does not. A full
            # `route_board.py` regeneration with the clip at 0.5mm
            # produced a BYTE-IDENTICAL board to the same run at 0.4mm
            # (sha256 697bad89...), so on this board the raise costs
            # nothing and recovers nothing in the production artefact.
            # Those vias are lost to a different new obstacle -- the
            # earlier rails' own In2.Cu conductors, +3V3's 227-segment
            # backbone chief among them -- which is the price of priority
            # ordering, not of this gap. See the pass-1 loop head for why
            # that price was accepted rather than partitioned away, and
            # `PowerIslandResult.via_unresolved_conflict_count` for where
            # it shows up per rail.
            _zone_clip_gap_mm = INTER_RAIL_CLEARANCE_MM
            for _prior in rail_state:
                _zone_clip_gap_mm = max(
                    _zone_clip_gap_mm,
                    _inter_rail_gap_mm(
                        net_name, _prior["net_name"], _net_clearance, _default_clearance
                    ),
                )
            plane_region = plane_region.difference(
                other_rail_zone_region.buffer(_zone_clip_gap_mm)
            )

        zone_polys: list[Polygon] = []
        pour_area_mm2 = 0.0
        this_rail_zone_geoms: list[Polygon] = []
        for zd in zones:
            hull_poly = Polygon(zd.points)
            clipped = hull_poly.intersection(plane_region)
            if clipped.is_empty:
                continue
            geoms = list(clipped.geoms) if hasattr(clipped, "geoms") else [clipped]
            for g in geoms:
                if not hasattr(g, "exterior") or g.is_empty or len(g.exterior.coords) < 4:
                    continue
                rpts = [(float(x), float(y)) for x, y in g.exterior.coords]
                if len(rpts) > 1 and rpts[0] == rpts[-1]:
                    rpts.pop()
                if len(rpts) < 3:
                    continue
                # The clip's piece may carry INTERIOR rings (an earlier
                # rail's buffered zone region, or a keepout island, sitting
                # inside this hull).  pour_outline_py takes a single region
                # ring, so passing only the exterior would silently pour
                # back over the other rail (measured 2026-08-16: vcc's
                # outline overlapped +3V3's by 75mm^2 exactly this way --
                # the region hole was dropped at the ring extraction).  The
                # region polygon (exterior + these interior rings) is
                # subtracted from the Rust carve result below so every
                # interior hole survives into the emitted outline.
                region_interiors = [
                    [(float(x), float(y)) for x, y in ring.coords]
                    for ring in g.interiors
                ]
                region_interiors = [r for r in region_interiors if len(r) >= 3]
                region_poly = Polygon(rpts, region_interiors)
                pour_zones = _tg.pour_outline_py(
                    rpts, own_rust, obstacle_records, 0.25 * 0.25, True
                )
                final_rings: list[tuple[list, list]] = []
                for zone_rings in pour_zones:
                    zp = Polygon(
                        zone_rings[0],
                        [list(h) for h in zone_rings[1:] if len(h) >= 3],
                    )
                    remaining = zp.intersection(region_poly)
                    if remaining.is_empty:
                        continue
                    pieces = (
                        list(remaining.geoms) if hasattr(remaining, "geoms") else [remaining]
                    )
                    for piece in pieces:
                        if piece.is_empty or not hasattr(piece, "exterior"):
                            continue
                        ext = [(float(x), float(y)) for x, y in piece.exterior.coords]
                        if ext and ext[0] == ext[-1]:
                            ext.pop()
                        pholes = [
                            [(float(x), float(y)) for x, y in h.coords]
                            for h in piece.interiors
                        ]
                        pholes = [h for h in pholes if len(h) >= 3]
                        if len(ext) >= 3:
                            final_rings.append((ext, pholes))
                for exterior, holes in final_rings:
                    new_blocks.append(
                        _tg.emit_zone_outline_s_expr_py(
                            net_num,
                            net_name,
                            PLANE_LAYER,
                            exterior,
                            holes,
                            0.25,
                            0,
                            0.25,
                        )
                    )
                    hole_polys = [list(h) for h in holes if len(h) >= 3]
                    carved = Polygon(exterior, hole_polys)
                    zone_polys.append(carved)
                    this_rail_zone_geoms.append(carved)
                    pour_area_mm2 += abs(carved.area)

        if this_rail_zone_geoms:
            merged_this_rail = unary_union(this_rail_zone_geoms)
            other_rail_zone_region = (
                merged_this_rail
                if other_rail_zone_region is None
                else unary_union([other_rail_zone_region, merged_this_rail])
            )
        # Union of THIS rail's carved pour outlines -- the fill's real
        # copper footprint on In2.Cu. Vias placed inside it touch the rail
        # after fill (see _find_via_drop_point's pour_region parameter); a
        # via outside it sits on the F.Cu backbone only (measured 2026-08-16:
        # keepout-only placement landed vias up to 12.6mm from HV copper,
        # outside the creepage-carved fill, touching no rail at all).
        pour_region: Polygon | None = None
        if this_rail_zone_geoms:
            merged_pour = unary_union(this_rail_zone_geoms)
            if not merged_pour.is_empty:
                pour_region = merged_pour

        rail_state.append(
            {
                "net_name": net_name,
                "net_num": net_num,
                "positions": positions,
                "through_hole_positions": through_hole_positions,
                "pour_region": pour_region,
                "zone_polys": zone_polys,
                "pour_area_mm2": pour_area_mm2,
            }
        )

    # =================== PASS 2: vias + backbone ===================
    # Every rail's pour footprint now exists, so a rail routing here can
    # be held clear of ALL the others', not just the ones that happened to
    # precede it. See the pass-split rationale above the pass-1 loop.
    for _rail_index, _rail in enumerate(rail_state):
        net_name = _rail["net_name"]
        net_num = _rail["net_num"]
        positions = _rail["positions"]
        through_hole_positions = _rail["through_hole_positions"]
        pour_region = _rail["pour_region"]

        # Every OTHER rail's finished In2.Cu pour, buffered by the gap
        # kicad-cli will actually demand between this rail and that one
        # (0.5mm for any Power/Power pair on this board -- see
        # `_inter_rail_gap_mm`; the same figure the pass-1 zone clip now
        # uses, so a via sitting inside its own pour is automatically
        # clear of the neighbour rather than caught between two
        # constraints that disagreed by 0.1mm). This is the obstacle that
        # did not and could not exist while this generator was a single pass, and it
        # is what stops +3V3's backbone -- 49 MST edges over the widest
        # span on the board -- from crossing the vcc/+15V/V_BUS_SENSE
        # pours it now shares a layer with.
        _other_rail_pours = [
            (_o["pour_region"], _o["net_name"])
            for _k, _o in enumerate(rail_state)
            if _k != _rail_index and _o["pour_region"] is not None
        ]
        other_rail_plane_zone_avoid: Polygon | None = None
        if _other_rail_pours:
            other_rail_plane_zone_avoid = unary_union(
                [
                    _poly.buffer(
                        _inter_rail_gap_mm(
                            net_name, _other_name, _net_clearance, _default_clearance
                        )
                    )
                    for _poly, _other_name in _other_rail_pours
                ]
            )

        # --- Drop vias + MST backbone. Vias: keepout + this run's own
        # prior new copper + OTHER nets' pre-existing F.Cu/B.Cu copper
        # are all hard obstacles for the per-point via-placement search
        # below. Backbone: as of 2026-08-12, a corridor-aware A* pass
        # (below, near `edges = mst_edges(positions)`) now ALSO attempts
        # to avoid OTHER nets' pre-existing F.Cu copper for the backbone
        # path itself, not just via placement -- see
        # _corridor_backbone.py's module docstring for why this had to
        # be a hybrid (A* first, keepout-only detour as fallback) rather
        # than a full per-path search replacing `_blocked` outright. ---
        other_copper_fcu = _collect_other_net_copper(
            pcb, net_name, "F.Cu", OTHER_NET_CLEARANCE_MM
        )
        other_copper_bcu = _collect_other_net_copper(
            pcb, net_name, "B.Cu", OTHER_NET_CLEARANCE_MM
        )
        # The route's own F.Cu/B.Cu copper (in-memory segment strings,
        # invisible to the stripped board file this generator re-parses)
        # must also be avoided -- see
        # _corridor_backbone.routed_segments_obstacle's docstring for the
        # measured 2026-08-16 failure mode (backbones blind to the routed
        # copper + the earlier gnd plane crossed them 81 times on one
        # route). The gnd plane's blocks are part of *segments* by the
        # time this generator runs (the caller extends the list first), so
        # gnd's vias/backbone are included here too.
        from temper_placer.router_v6._corridor_backbone import (
            routed_segments_obstacle,
        )

        routed_fcu_avoid = routed_segments_obstacle(
            segments, net_name, "F.Cu", num_to_name,
            _net_clearance, _net_clearance.get(net_name, _default_clearance), _default_clearance,
        )
        routed_bcu_avoid = routed_segments_obstacle(
            segments, net_name, "B.Cu", num_to_name,
            _net_clearance, _net_clearance.get(net_name, _default_clearance), _default_clearance,
        )
        # In1.Cu too (2026-08-19): this rail's drop vias are THROUGH vias,
        # so their barrels pass through the gnd plane's layer -- and as of
        # the _ground_plane.py backbone-layer fix that layer now carries
        # real 1.0mm gnd copper, emitted into *segments* by the caller
        # immediately before this generator runs. Without this term a
        # +3V3/vcc/+15V via could be dropped straight onto the gnd
        # backbone, which is a short, not a clearance nibble. (This
        # rail's own PLANE_LAYER, In2.Cu, is covered by the per-rail zone
        # separation below, not here.)
        # ...and the same for every OTHER copper layer this rail's THROUGH
        # vias pass through. A drop via's barrel is copper on all six; the
        # avoid set used to cover only F.Cu/B.Cu, so a via could be dropped
        # straight onto a routed In3.Cu/In4.Cu track (measured: "Track
        # [OCP2_VREF_2V5] on In4.Cu" vs "Via [+3V3]", and 5 more of that
        # exact shape). `_ground_plane.py` already gets this right for its
        # own drop vias -- its `emitted_geoms` spans every copper layer --
        # so this brings the sibling generator up to the same standard
        # rather than inventing a new rule. In1.Cu is in the list because
        # the gnd plane's backbone now lands there.
        #
        # In2.Cu joined the list 2026-08-19. The line this replaced read
        # "In2.Cu is this rail's own layer and is handled by the
        # inter-rail zone separation" -- true only while the zone was the
        # ONLY thing this generator put on In2.Cu. It now also puts a
        # backbone there, and anything the CALLER routed onto In2.Cu is
        # equally real copper a through-via barrel would pierce. This term
        # covers the caller-supplied case; sibling rails' own backbones
        # this same run are in `new_blocks`, not `segments`, and are
        # covered by `run_new_plane_copper` below.
        routed_inner_avoid = [
            routed_segments_obstacle(
                segments, net_name, other_layer, num_to_name,
                _net_clearance,
                _net_clearance.get(net_name, _default_clearance),
                _default_clearance,
            )
            for other_layer in ("In1.Cu", PLANE_LAYER, "In3.Cu", "In4.Cu")
        ]
        # Kept at the pre-2026-08-19 composition ON PURPOSE: this union is
        # ALSO the gate for the F.Cu pad-to-via stub below, and the two
        # new In2.Cu terms (other rails' pours, earlier rails' plane
        # conductors) are not obstacles for a track on F.Cu. Folding a
        # whole rail-sized In2.Cu pour into the stub's gate would block
        # nearly every stub on the board for a collision that does not
        # exist. The via search gets the wider set below.
        via_avoid_parts = [
            g
            for g in (
                other_copper_fcu,
                other_copper_bcu,
                routed_fcu_avoid,
                routed_bcu_avoid,
                *routed_inner_avoid,
                *run_new_fcu_copper,
                *run_new_bcu_copper,
            )
            if g is not None
        ]
        via_avoid_copper: Polygon | None = (
            unary_union(via_avoid_parts) if via_avoid_parts else None
        )
        # The drop via is a THROUGH via: its barrel is copper on In2.Cu
        # too, so it must clear every other rail's pour and every earlier
        # rail's plane conductors as well as everything above. Strictly a
        # superset of `via_avoid_copper` -- this can only move a via or
        # skip it fail-closed, never place one the narrower set refused.
        via_plane_avoid_parts = [
            g
            for g in (
                other_rail_plane_zone_avoid,
                *run_new_plane_copper,
            )
            if g is not None
        ]
        via_avoid_copper_all_layers: Polygon | None = via_avoid_copper
        if via_plane_avoid_parts:
            via_avoid_copper_all_layers = unary_union(
                ([via_avoid_copper] if via_avoid_copper is not None else [])
                + via_plane_avoid_parts
            )

        existing_holes = _existing_drilled_holes(pcb, net_name) + list(run_new_holes)

        via_skipped_through_hole = 0
        via_offset_count = 0
        via_unresolved_conflict = 0
        via_radius_mm = VIA_SIZE_MM / 2.0
        this_rail_vias: list[Polygon] = []
        this_rail_stubs: list[Polygon] = []
        # The nodes the MST backbone will actually span, in the order they
        # are established here. NOT ``positions``: the backbone now runs on
        # BACKBONE_LAYER (In2.Cu), and an In2.Cu point only reaches this
        # rail's copper where a PLATED BARREL passes through it. A rail pad
        # is F.Cu copper, not In2.Cu copper -- a backbone endpoint parked
        # on a bare pad position is floating metal on the plane layer,
        # joined to nothing.
        #
        # `_ground_plane.py` measured exactly this on In1.Cu the day
        # before: spanning PAD positions put 204 segments on the plane and
        # moved connectivity 5 -> 7 of 88 pads; spanning BARREL positions
        # moved it to 16 and cut gnd's copper from 54 components to 8. The
        # premise transfers because the cause does -- the drop-via search
        # here offsets a via off its pad for the same reasons (occupied
        # hole, foreign copper, keepout, and additionally this module's
        # `pour_region` constraint), and `via_offset_count` reports how
        # often per rail.
        #
        # Exactly two kinds of point are real nodes on this layer:
        #   * a through-hole rail pad -- its own plated hole spans every
        #     copper layer it lists, so the pad position IS an In2.Cu node
        #     (this is the ``via_skipped_through_hole`` branch);
        #   * the drop point of a via this loop emits (a through-via).
        # A pad whose via was skipped fail-closed (``via_unresolved_
        # conflict``) contributes NO node: no conductor joins it to this
        # layer, so spanning to it would emit copper that cannot carry its
        # current.
        backbone_positions: list[tuple[float, float]] = []

        for x, y in positions:
            key = (round(x, 3), round(y, 3))
            if through_hole_positions.get(key, False):
                via_skipped_through_hole += 1
                backbone_positions.append((x, y))
                continue

            drop_point, needs_stub = _find_via_drop_point(
                (x, y),
                existing_holes=existing_holes,
                via_radius_mm=via_radius_mm,
                keepout=keepout if keepout_established else None,
                other_copper=via_avoid_copper_all_layers,
                board_polygon=board_polygon,
                pour_region=pour_region,
            )
            if drop_point is None:
                via_unresolved_conflict += 1
                logger.warning(
                    "generate_power_islands_content(%s): no clear via drop "
                    "point found near pad at (%.4f, %.4f) -- skipping this "
                    "via rather than emitting a known-colliding one.",
                    net_name,
                    x,
                    y,
                )
                continue

            vx, vy = drop_point
            new_blocks.append(
                f'  (via (at {vx:.4f} {vy:.4f}) (size {VIA_SIZE_MM:.4f}) '
                f'(drill {VIA_DRILL_MM:.4f}) (layers "F.Cu" "B.Cu") '
                f"(net {net_num}) (tstamp \"{_next_tstamp()}\"))"
            )
            existing_holes.append((vx, vy, via_radius_mm))
            run_new_holes.append((vx, vy, via_radius_mm))
            this_rail_vias.append(Point(vx, vy).buffer(via_radius_mm + OTHER_NET_CLEARANCE_MM, quad_segs=8))
            backbone_positions.append((vx, vy))
            if needs_stub:
                via_offset_count += 1
                # RAISED 2026-08-17 (stitch-congestion root-cause fix, see
                # the MST-backbone `_blocked` comment below for the full
                # mechanism): this stub is real STITCH_TRACE_WIDTH_MM-wide
                # F.Cu copper from the pad straight to the offset via, and
                # was never checked against anything -- the via-drop search
                # only clears the via's OWN footprint, not the straight
                # line joining it back to the pad. `_ground_plane.py`'s
                # identical stub already gates on exactly this
                # (2026-08-16, "fix/route-to-100-percent"); this one,
                # cloned earlier, never did. Gate with the same
                # buffered-footprint check, reusing `via_avoid_copper`
                # (already comprehensive: pre-existing other-net copper,
                # this run's routed segments, and every earlier power rail's
                # own new copper). A blocked stub is skipped fail-closed --
                # the via stays; the pad just isn't stub-joined, a labelled
                # connectivity cost on this net, not a short.
                stub_footprint = LineString([(x, y), (vx, vy)]).buffer(
                    STITCH_TRACE_WIDTH_MM / 2.0
                )
                stub_blocked = (
                    keepout_established and stub_footprint.intersects(keepout)
                ) or (
                    via_avoid_copper is not None
                    and not via_avoid_copper.is_empty
                    and stub_footprint.intersects(via_avoid_copper)
                )
                if not stub_blocked:
                    # STUB_LAYER, not BACKBONE_LAYER (2026-08-19). These
                    # two constants were the same string until the
                    # backbone moved to In2.Cu; the stub must stay on the
                    # PAD's layer or it joins neither the pad nor the via.
                    new_blocks.append(
                        f"  (segment (start {x:.4f} {y:.4f}) (end {vx:.4f} {vy:.4f})"
                        f' (width {STITCH_TRACE_WIDTH_MM:.4f}) (layer "{STUB_LAYER}")'
                        f" (net {net_num}) (tstamp \"{_next_tstamp()}\"))"
                    )
                    # Accumulate the stub as this rail's F.Cu copper. It
                    # never was before -- only vias and (then-F.Cu)
                    # backbone segments went into `run_new_fcu_copper` --
                    # so a later rail's via could be dropped on an earlier
                    # rail's stub. That gap was masked while the F.Cu
                    # backbone dominated the accumulator; with the
                    # backbone gone from F.Cu the stubs are most of what
                    # this generator still puts there, so the omission
                    # would now be the whole of it.
                    this_rail_stubs.append(
                        LineString([(x, y), (vx, vy)]).buffer(
                            STITCH_TRACE_WIDTH_MM / 2.0 + OTHER_NET_CLEARANCE_MM,
                            quad_segs=8,
                        )
                    )

        edges = mst_edges(backbone_positions)

        # --- Corridor-aware A* pass (see _corridor_backbone.py's module
        # docstring): try a real, collision-avoiding path for every MST
        # edge first, over a grid that blocks the HV keepout and every
        # other net's copper ON BACKBONE_LAYER. The keepout-only
        # `_blocked`/one-bend-detour loop below is the fallback for edges
        # this cannot solve (a measured, genuine physical disconnection
        # for a real fraction of edges -- see that module's docstring), so
        # connectivity per rail can only improve edge-by-edge, never
        # regress below the prior behaviour.
        #
        # LAYER CHOICE, measured not assumed -- REVISED 2026-08-19 to
        # PLANE_LAYER (In2.Cu), for the reason recorded at BACKBONE_LAYER
        # (the `pad_connectivity_audit` limitation this module worked
        # around was fixed by dabbeaf73 five days after this module
        # landed). Keeping it on F.Cu was not free. F.Cu carries 652
        # routed segments and this module's own HV keepout covers
        # 27499 mm^2, so four separate 1.0mm rail backbones were competing
        # for whatever corridor was left, each also treating the previous
        # rails' F.Cu copper as an obstacle. Measured from this
        # generator's own per-run log output on the committed board:
        #
        #   net           pads  backbone edges dropped  pads attached
        #   +3V3           50   43 of 49                23/50
        #   vcc            13   12 of 12 (all)           6/13
        #   +15V           10    9 of 9  (all)           3/10
        #   V_BUS_SENSE     4    3 of 3  (all)           0/4
        #
        # -- 74 of the board's 304 remaining unconnected edges, and In2.Cu
        # carrying zero copper of any kind. On In2.Cu the same A* runs
        # against the HV keepout, the foreign VIA BARRELS, and the other
        # three rails, instead of against the whole front-side route.
        #
        # Those barrels are a prerequisite, not a follow-up: 80 foreign-net
        # vias sit inside the +3V3 In2.Cu outline, and until 2026-08-19
        # `_via_is_on_layer` short-circuited to False for In1.Cu/In2.Cu
        # (it indexed the ROUTER's signal-layer list, which excludes both
        # declared-power layers), so no via was ever an obstacle here.
        # Putting copper on this layer without that fix would have routed
        # 1.0mm rail traces straight through other nets' via barrels.
        # `a71765efe` fixed it; both `_collect_other_net_copper` and
        # `collect_other_net_copper_by_pairwise_clearance` now route their
        # via test through it, so the sets built below really do contain
        # those 80.
        #
        # The pad-to-via stubs stay on STUB_LAYER (F.Cu) -- a rail pad is
        # F.Cu copper, and the through-via carries the join down.
        from temper_placer.core.topology import UnionFind
        from temper_placer.router_v6._corridor_backbone import (
            build_obstacle_grid,
            collect_other_net_copper_by_pairwise_clearance,
            compute_corridor_mask,
            corridor_aware_spanning_edges,
        )

        # Real, per-net-pair clearance polygon for the A* obstacle grid --
        # NOT other_copper_fcu (built above at OTHER_NET_CLEARANCE_MM
        # =0.05mm for via placement); see
        # _corridor_backbone.resolve_netclass_clearances's docstring.
        #
        # Built for BACKBONE_LAYER, not F.Cu (2026-08-19). The copper this
        # backbone has to avoid is the copper on the layer it is on, which
        # on In2.Cu is the foreign via barrels passing through it plus
        # whatever this run put there -- no pre-existing track on this
        # board is on In2.Cu.
        this_net_own_clearance = _net_clearance.get(net_name, _default_clearance)
        other_copper_plane_backbone = collect_other_net_copper_by_pairwise_clearance(
            pcb, net_name, BACKBONE_LAYER, _net_clearance, this_net_own_clearance,
            _default_clearance,
        )
        # The route's own copper reaching BACKBONE_LAYER (the gnd plane's
        # blocks are part of *segments* by now, and its drop vias are
        # through-vias whose barrels pierce In2.Cu) -- see
        # routed_segments_obstacle's docstring.
        routed_plane_backbone = routed_segments_obstacle(
            segments, net_name, BACKBONE_LAYER, num_to_name,
            _net_clearance, this_net_own_clearance, _default_clearance,
        )
        # Every EARLIER rail's own In2.Cu conductors this same run (via
        # barrels + backbone), buffered up to the real Power/Power pair
        # clearance. Those polygons already carry OTHER_NET_CLEARANCE_MM
        # (0.05mm) from their own construction in `_emit_segment` /
        # `this_rail_vias`, so the extra buffer is the remainder needed to
        # reach the pair's required gap -- derived from the .kicad_pro
        # SSOT rather than from the module-local 0.4mm literal, which is
        # below it. Together with `other_rail_plane_zone_avoid` (all three
        # OTHER rails' pours, available because pass 1 finished) this is
        # the complete inter-rail obstacle set on the shared plane.
        _prior_rail_gap_mm = max(
            (
                _inter_rail_gap_mm(
                    net_name, _o["net_name"], _net_clearance, _default_clearance
                )
                for _k, _o in enumerate(rail_state)
                if _k != _rail_index
            ),
            default=this_net_own_clearance,
        )
        prior_rail_backbone_obstacles = [
            g.buffer(max(_prior_rail_gap_mm - OTHER_NET_CLEARANCE_MM, 0.0))
            for g in run_new_plane_copper
        ]
        # The grid's free space is the board inset by BOARD_EDGE_MARGIN_MM,
        # not the raw outline -- the same inset `plane_region_base` (the
        # pour) has always used. While the backbone lived on F.Cu this
        # never showed, because F.Cu's own routed copper kept it away from
        # the edge anyway; on a near-empty plane layer A* will happily hug
        # the board outline (`_ground_plane.py` measured 4 new
        # copper_edge_clearance violations, "Track [gnd] on In1.Cu", from
        # exactly this). Reusing this module's own edge constant rather
        # than the DRU's 0.5mm manufacturing floor keeps one knob for "how
        # far this plane's copper stays off the edge" and is the more
        # conservative of the two.
        backbone_region = board_polygon.buffer(-BOARD_EDGE_MARGIN_MM)
        if backbone_region.is_empty:
            backbone_region = board_polygon
        backbone_obstacles = [
            keepout,
            other_copper_plane_backbone,
            routed_plane_backbone,
            other_rail_plane_zone_avoid,
            *prior_rail_backbone_obstacles,
        ]
        backbone_grid = build_obstacle_grid(backbone_region, backbone_obstacles)
        backbone_corridor_mask = compute_corridor_mask(backbone_grid, STITCH_TRACE_WIDTH_MM)

        # Component-aware (see _corridor_backbone.py / _ground_plane.py's
        # own docstrings for the measured reason a blind per-Euclidean-
        # MST-edge attempt undersells this): a Euclidean MST WITHIN each
        # of the corridor mask's own connected components, not the
        # global MST's own (possibly corridor-infeasible) edge list.
        astar_routed_edges = corridor_aware_spanning_edges(
            backbone_positions, backbone_grid, backbone_corridor_mask, mst_edges
        )
        connectivity_uf = UnionFind()
        for i, j in astar_routed_edges:
            connectivity_uf.union(i, j)

        def _emit_segment(p1: tuple[float, float], p2: tuple[float, float], _net_num=net_num) -> Polygon:
            new_blocks.append(
                f"  (segment (start {p1[0]:.4f} {p1[1]:.4f}) (end {p2[0]:.4f} {p2[1]:.4f})"
                f' (width {STITCH_TRACE_WIDTH_MM:.4f}) (layer "{BACKBONE_LAYER}")'
                f" (net {_net_num}) (tstamp \"{_next_tstamp()}\"))"
            )
            return LineString([p1, p2]).buffer(
                STITCH_TRACE_WIDTH_MM / 2.0 + OTHER_NET_CLEARANCE_MM, quad_segs=8
            )

        run_this_rail_backbone: list[Polygon] = []

        # RAISED 2026-08-17 (stitch-congestion root-cause fix,
        # docs/evidence/2026-08-17-stitch-congestion-rootcause-and-fix.md):
        # this fallback used to test a ZERO-WIDTH line against obstacle
        # polygons that only carry the FOREIGN copper's own half-width +
        # OTHER_NET_CLEARANCE_MM -- correct for a point probe, wrong for a
        # STITCH_TRACE_WIDTH_MM-wide segment (under-buffers by exactly this
        # segment's own half-width, i.e. by 0.5mm at today's 1.0mm width,
        # vs. 0.15mm at the old 0.3mm width the check was never wrong
        # enough to catch). It ALSO never checked `other_copper_fcu_backbone`
        # (every OTHER net's pre-existing board copper, real per-net-class-
        # pair clearance) or `routed_fcu_backbone` (this run's own Stage
        # 3/4-routed copper + the gnd plane, same clearance convention) --
        # both already computed above for the primary corridor-aware A*
        # pass but never wired into this legacy fallback, so a straight-
        # line/one-bend-detour edge could be drawn directly through a
        # signal net's freshly-routed track with zero awareness it was
        # there. This is `_ground_plane.py`'s own `_blocked` fix
        # (2026-08-16, "fix/route-to-100-percent") applied here for the
        # first time -- that module's fallback got exactly this
        # combination (buffered test footprint + foreign-copper checks)
        # and this one, cloned from an earlier version, never did.
        # Measured (see evidence doc): 108/130 of the +77 shorting_items
        # regression from the 0.3->1.0mm stitch-width fix (PR #1329) is on
        # +3V3 alone -- the rail with by far the most MST edges, hence the
        # most fallback usage, hence the most exposure to exactly this gap.
        #
        # RETARGETED 2026-08-19 to BACKBONE_LAYER: every obstacle named
        # here is now the In2.Cu set the A* grid above was built from, so
        # the fallback and the primary pass agree on what "blocked" means
        # on the layer the segment is actually emitted on. That includes
        # the two new inter-rail terms -- the other three rails' pours and
        # every earlier rail's plane conductors -- which is what makes the
        # fallback safe on a shared plane. Without them a dropped-to-
        # fallback +3V3 edge would be drawn straight across the vcc pour.
        def _blocked(p1: tuple[float, float], p2: tuple[float, float]) -> bool:
            footprint = LineString([p1, p2]).buffer(STITCH_TRACE_WIDTH_MM / 2.0)
            # Same board-edge inset the A* grid uses -- this fallback
            # bypasses that grid entirely, so without this a fallback edge
            # can still run off the inset region and land a
            # copper_edge_clearance violation.
            if not backbone_region.covers(footprint):
                return True
            if keepout_established and footprint.intersects(keepout):
                return True
            if (
                other_copper_plane_backbone is not None
                and not other_copper_plane_backbone.is_empty
                and footprint.intersects(other_copper_plane_backbone)
            ):
                return True
            if (
                routed_plane_backbone is not None
                and not routed_plane_backbone.is_empty
                and footprint.intersects(routed_plane_backbone)
            ):
                return True
            if (
                other_rail_plane_zone_avoid is not None
                and not other_rail_plane_zone_avoid.is_empty
                and footprint.intersects(other_rail_plane_zone_avoid)
            ):
                return True
            for g in prior_rail_backbone_obstacles:
                if footprint.intersects(g):
                    return True
            return False

        # Emit every component-local A*-routed edge unconditionally --
        # additional real connectivity beyond (not necessarily a subset
        # of) the global Euclidean MST's own edge list.
        astar_routed_count = 0
        for (_i, _j), astar_path in astar_routed_edges.items():
            for a, b in zip(astar_path, astar_path[1:]):
                run_this_rail_backbone.append(_emit_segment(a, b))
            astar_routed_count += 1

        crossed_keepout = 0
        rerouted = 0
        for i, j in edges:
            if connectivity_uf.find(i) == connectivity_uf.find(j):
                # Already joined by a component-local A*-clean edge (or a
                # chain of them) -- drawing this global-MST edge too
                # would only add collision risk for zero connectivity
                # benefit.
                continue

            p1, p2 = backbone_positions[i], backbone_positions[j]
            if not _blocked(p1, p2):
                run_this_rail_backbone.append(_emit_segment(p1, p2))
                connectivity_uf.union(i, j)
                continue

            candidates = sorted(
                (k for k in range(len(backbone_positions)) if k != i and k != j),
                key=lambda k: (
                    (backbone_positions[k][0] - p1[0]) ** 2
                    + (backbone_positions[k][1] - p1[1]) ** 2
                    + (backbone_positions[k][0] - p2[0]) ** 2
                    + (backbone_positions[k][1] - p2[1]) ** 2
                ),
            )[:200]
            found = False
            for k in candidates:
                w = backbone_positions[k]
                if not _blocked(p1, w) and not _blocked(w, p2):
                    run_this_rail_backbone.append(_emit_segment(p1, w))
                    run_this_rail_backbone.append(_emit_segment(w, p2))
                    found = True
                    break
            if found:
                rerouted += 1
                connectivity_uf.union(i, j)
            else:
                crossed_keepout += 1

        if crossed_keepout:
            logger.warning(
                "generate_power_islands_content(%s): %d MST edge(s) crossed "
                "the HV keepout, another rail's %s pour or conductors, or a "
                "foreign net's copper on %s, and could not be rerouted "
                "(%d rerouted via one-bend detour). Dropped rather than "
                "routed through it -- the backbone may be a forest, not a "
                "single tree.",
                net_name,
                crossed_keepout,
                PLANE_LAYER,
                BACKBONE_LAYER,
                rerouted,
            )

        # Accumulate this rail's new copper per LAYER, so a later rail
        # avoids each piece on the layer it is actually on. Through-via
        # barrels are on every copper layer and so appear in all three;
        # the F.Cu pad stubs are F.Cu only; the backbone is In2.Cu only
        # (it used to be F.Cu, which is why `run_new_fcu_copper` used to
        # receive it).
        run_new_fcu_copper.extend(this_rail_vias)
        run_new_fcu_copper.extend(this_rail_stubs)
        run_new_bcu_copper.extend(this_rail_vias)
        run_new_plane_copper.extend(this_rail_vias)
        run_new_plane_copper.extend(run_this_rail_backbone)

        results[net_name] = PowerIslandResult(
            net_name=net_name,
            pad_count=len(positions),
            drop_via_count=len(positions) - via_skipped_through_hole - via_unresolved_conflict,
            mst_edge_count=len(edges) - crossed_keepout,
            zone_polygon_count=len(_rail["zone_polys"]),
            pour_area_mm2=_rail["pour_area_mm2"],
            via_skipped_through_hole_count=via_skipped_through_hole,
            via_offset_count=via_offset_count,
            via_unresolved_conflict_count=via_unresolved_conflict,
            mst_edges_dropped_count=crossed_keepout,
            mst_edges_astar_routed_count=astar_routed_count,
            mst_edges_fallback_count=len(edges) - astar_routed_count,
        )

    return new_blocks, results


def generate_power_islands_content(
    pcb_path: Path,
    *,
    nets: tuple[str, ...] = POWER_ISLAND_NETS,
    domain_manifest_path: Path = DEFAULT_DOMAIN_MANIFEST_PATH,
    segments: list[str] | None = None,
) -> tuple[str, dict[str, PowerIslandResult]]:
    """Standalone/CLI entry point: read *pcb_path*, compute the ``In2.Cu``
    power-island blocks (via ``generate_power_islands_blocks``), splice
    them into the file's own content, and return ``(new board content,
    {net_name: PowerIslandResult})``.

    This is the surface the standalone spike and the spike tests use.
    Production goes through ``generate_power_islands_blocks`` instead
    (from ``_write_routes_to_content``), because the routed board's
    content string is assembled in memory -- splicing back into the
    file's own text would drop the routing segments.
    """
    content = pcb_path.read_text()
    blocks, results = generate_power_islands_blocks(
        pcb_path, nets=nets, domain_manifest_path=domain_manifest_path, segments=segments
    )
    new_content = content.rstrip()
    if new_content.endswith(")"):
        new_content = new_content[:-1] + "\n" + "\n".join(blocks) + "\n)\n"

    return new_content, results
