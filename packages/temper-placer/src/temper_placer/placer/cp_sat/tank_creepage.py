"""Tank-node functional creepage as a HARD placement constraint.

Why this module exists
-----------------------
``tank.c_tank1-p2`` — the resonant tank's cap<->coil junction — measures
**570.5 Vrms** against the DC bus, the only pair on this board above the
500V cliff in IEC 60335-1 Table 18 (functional insulation, cl. 29.2.4).
That crosses from Table 18's >400-500V row (4.0/6.3mm) into its >500-800V
row: **6.3mm at PD2, 10.0mm at PD3**
(``docs/evidence/2026-08-12-hv-hv-creepage-determination.md``, PR #1081,
branch ``docs/recover-standards-primary-text`` — not on ``main``). PD2 is
conditional on a sealed compartment that does not exist on this board
today, so **PD3 (10.0mm) governs as-built**
(``docs/evidence/2026-08-11-pd2-decision-record.md``).

``docs/evidence/2026-08-12-hv-hv-creepage-enforcement.md`` (PR #1084,
branch ``feat/hv-hv-creepage-enforcement`` — also not on ``main``) turned
that figure into a ``.kicad_dru`` rule and measured it rejecting the
committed board: **C25 pad 2 <-> a track of ``discharge.k_dis1-nc``, actual
2.2656mm against 6.3mm required — 2.8x short**, plus a second real pair
(R30's own two pads, 5.0mm) and two more that only cross the bar at the
PD3 figure. That work reaches exactly one enforcement path — kicad-cli's
DRC, run *after* placement and routing are both already fixed. **Nothing
upstream of DRC currently keeps a re-solved board from reproducing the
same shortfall.** This module is the placement-time half: it gives the
CP-SAT/Pumpkin solver a HARD constraint that pushes the tank node's own
components away from every other high-voltage component *before* a board
is placed, rather than discovering the shortfall only after routing.

**What this constraint actually guarantees, stated precisely, because it
is easy to overstate.** Creepage is a distance measured *along a surface*
between the nearest copper of two different nets — in the DRC report
above, a *pad* of ``tank.c_tank1-p2`` against a *routed track* of
``discharge.k_dis1-nc``. This module (like ``domain_clearance.py``, whose
soundness proof it reuses without re-deriving) can only constrain
**component bounding boxes** at placement time — nothing about a trace or
via, which the router places in a *later* pipeline stage this constraint
has no visibility into.

*What IS guaranteed, and why.* ``domain_clearance.py``'s module docstring
proves that a HARD ``SeparatedConstraint`` at margin M, SAT under the
Chebyshev box-disjunction encoding, implies every point of component A's
bounding box is >= M (Euclidean) from every point of component B's
bounding box — and because ``comp.bounds`` is constructed to *contain*
every pad each component places (``_calculate_footprint_bounds``, proven
by ``test_bounds_computed_in_placement_frame_not_raw_anchor``), that
Euclidean bound extends to **every pad-copper point on A vs every
pad-copper point on B**. So: SAT of this constraint at 10.0mm guarantees
straight-line pad-to-pad distance >= 10.0mm between every tank-node
component's own pads and every other classified-HV component's own pads —
which, on a flat board surface with no intervening slot, is the same
quantity kicad-cli's creepage check measures for a *pad-to-pad* pair (a
straight line on a flat plane already is the shortest surface path).

*What is NOT guaranteed, quantified against the real board.* The pair
that actually fails DRC — C25 pad 2 vs a ``discharge.k_dis1-nc`` **track**
— is not a pad-to-pad pair. Measured directly from the committed board
(``pcb/temper.kicad_pcb``, read-only; see the evidence doc's Sec 5 for the
harness): the box-to-box gap between C25 and K2 (the nearest
``discharge.k_dis1-nc``-owning component, a relay) is **already 10.8mm** —
it clears this module's own 10.0mm bound with no solver intervention at
all — while the real copper-to-copper creepage kicad-cli measures for
that net pair is **2.2656mm**. That 4.8x gap is not an encoding bug; it is
the routed trace swinging close to C25 on its way somewhere else on the
board, a degree of freedom this constraint (or any placement-time,
component-box constraint) cannot see or bound. **This module is therefore
a conservative proxy for pad-to-pad creepage between the tank node's own
components and other HV components' own components, and it is silent —
correctly, not by omission — on pad-to-routed-copper creepage, which is a
routing-stage property.** Fixing THAT class of violation needs a
routing-aware keepout, not a placement constraint; this module does not
claim to be one.

What it DOES reject on the committed board, measured directly: 14 of the
168 (tank-ref x other-HV-ref) component pairs have a box-to-box Chebyshev
gap under 10.0mm today (10 are under even the looser 6.3mm PD2 figure),
headlined by ``C25<->RV1`` and ``C27<->U5`` at **0.4mm** — components
whose bodies are nearly touching. Those are real placement-level
proximity problems this constraint newly forbids, independent of whether
they happen to be the specific pair kicad-cli's DRU rule named.

The pair the box constraint structurally cannot see: tank <-> DC-bus rails
-----------------------------------------------------------------------------
The one pair this module's own evidence doc measures as the board's
highest-voltage shortfall — ``tank.c_tank1-p2`` vs the **DC-bus rails**
(``+170V_BUS``, ``DC_BUS_RTN``), 2.0mm provided against 6.3mm PD2 /
10.0mm PD3 required (``docs/evidence/2026-08-12-hv-hv-creepage-
determination.md`` Sec 4.3, a 3.2x-5.0x shortfall) — is **not a
component-pair at all**. The bus rails are *nets*: a net with no refdes
can never appear in :func:`tank_creepage_pairs`, so the box constraint
(and the old test that asserted on it) is structurally blind to exactly
the pair that matters. The 2026-08-15 safety-assertion audit
(``docs/evidence/2026-08-15-safety-assertion-audit-resumed.md`` Part 0)
classified this as a real structural mask, not a documentation gap:
``len(pairs) == 4 * 42`` would pass unchanged with the tank<->bus gap at
2.0mm.

This module therefore also exposes a **net-level** enumeration
(:func:`tank_bus_net_pairs`) and a **copper-level** checker
(:func:`check_tank_bus_creepage`) for exactly those pairs. The copper
metric has two honest quantities:

- **Exact pad-to-pad copper distance** (:func:`tank_bus_pad_gap_mm`, the
  same ``pad_pair_distance`` kernel the REQ-SAFE-01 validator uses) — the
  quantity kicad-cli measures for a pad-to-pad pair, with no box proxy.
- **Pour containment** (:func:`tank_bus_pour_contained_pads`): when a
  tank-node pad lies *inside* a bus-rail zone outline on a layer the pad
  occupies, the pad-pad distance is NOT the copper gap — the pour
  approaches the foreign pad to exactly the design's enforced netclass
  clearance, so the design itself bounds the gap. Measured on the
  committed board: C26's and R30's tank pads sit inside the ``DC_BUS_RTN``
  pours on both F.Cu and B.Cu (both are THT, layer=all) — the "2.0mm
  provided" of the evidence doc is physically real on the committed
  board, not a hypothetical routing outcome.

The checker reports both kinds against the PD3 margin, and the test pins
the *enforced* figures (netclass clearance, DRU-emitted creepage, SSOT
declared creepage) against the 6.3/10.0 requirement so the shortfall is a
hard, labelled failure rather than a prose caveat.

Scope: which components, and why
---------------------------------
**Group A ("tank refs")**: every component with a pad on
``tank.c_tank1-p2`` — measured from the board: ``C25``, ``C26``, ``C27``
(the tank capacitor bank, sharing ``SW_NODE`` on their other pad) and
``R30`` (the litz coil pad, sharing ``tank-out`` on its other pad).

**Group B ("other HV refs")**: every OTHER component (Group A excluded)
with a pad on any net classified ``"HighVoltage"`` in
``design_rules.TEMPER_NET_ASSIGNMENTS`` — the same 16-net classification
``docs/evidence/2026-08-12-hv-hv-creepage-enforcement.md`` Sec 1.1 uses to
scope its own DRU rule's B-side (``B.NetClass == 'HighVoltage'``), so the
pairs this module protects are the same population that rule protects,
just at component-box granularity instead of copper granularity. Measured
from the board: 42 refs.

**Group A components excluded from Group B, deliberately.** C25/C26/C27
also carry ``SW_NODE`` (also ``HighVoltage``-classified) and R30 also
carries ``tank-out`` (same). Without the exclusion, a tank-net component
would appear on BOTH sides of its own pair (e.g. C25 in Group A vs C25 in
Group B, and separately C25 in Group A vs C26 in Group B even though both
are tank capacitors meant to sit close together for a low-inductance
connection) — silently forcing >=10mm between the three tank capacitors
themselves, which is not the requirement anything measured and would
actively fight the electrical design. Only genuinely different-net,
non-tank-node HV components are constrained against the tank node.

**What this cannot fix even in principle: R30's own two pads.** R30's pad
1 (``tank.c_tank1-p2``) and pad 2 (``tank-out``) are 5.0mm apart on the
committed board against the same 6.3/10.0mm requirement
(``2026-08-12-hv-hv-creepage-enforcement.md`` Sec 5.1) — a real violation,
but an INTRA-footprint one. Every one of a component's own pads moves as
one rigid unit under placement; no ``SeparatedConstraint``, and no other
placement-time constraint, can ever separate a two-pin part's own pads
from each other (``domain_clearance.py``'s own documented limitation,
carried over unchanged here — not re-derived, because the argument does
not depend on which two nets or which two components). Fixing this needs
a different part or a milled slot, not placement. ``other_hv_refs``
excludes R30 from its own Group-A membership as a matter of course, so no
constraint is ever generated for this pair, and ``find_tank_self_pairs``
below names it explicitly rather than leaving it silently uncovered.

Why no new constraint type
---------------------------
``separated`` already exists, is registered in both backends
(Pumpkin ``docs/evidence/2026-08-07-pumpkin-engine/src/main.rs:308``;
OR-Tools ``handlers/separated.py::encode_separated``, dispatched via
``ConstraintType.SEPARATED``), and already carries exactly the
``min_distance_mm`` primitive this requirement needs. Pumpkin ``exit(2)``s
on an unregistered constraint type while OR-Tools warns and continues
(``_encoder_core.py``), so reusing an already-dual-registered type is
materially safer than inventing one — and it means the pinned engine
binary (``scripts/verify_pumpkin_engine.py``) needs no rebuild, so no
other worktree's identity gate is put at risk.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.core.netlist import Component, Netlist, Pin
    from temper_placer.placer.cp_sat.model import CpSatModel

logger = logging.getLogger(__name__)

__all__ = [
    "HV_TANK_CREEPAGE_PD2_MM",
    "HV_TANK_CREEPAGE_PD3_MM",
    "DEFAULT_TANK_CREEPAGE_MM",
    "TANK_NODE_NET",
    "TANK_BUS_RAIL_NETS",
    "TankCreepagePair",
    "TankBusNetPair",
    "TankCreepageReport",
    "tank_node_refs",
    "other_hv_refs",
    "tank_creepage_pairs",
    "tank_bus_net_pairs",
    "tank_bus_pad_gap_mm",
    "tank_bus_pour_contained_pads",
    "enforced_tank_bus_clearance_mm",
    "check_tank_bus_creepage",
    "find_tank_self_pairs",
    "tank_creepage_wire_constraints",
    "add_tank_creepage_to_model",
    "check_tank_creepage_separation",
]

#: The one net this module protects. See module docstring for why it is
#: the only tank-domain net measured above the Table 18 500V cliff.
TANK_NODE_NET: str = "tank.c_tank1-p2"

#: IEC 60335-1 Table 18 (functional insulation, cl. 29.2.4), >500-800V row,
#: material group IIIa/IIIb: PD2 = 6.3mm.
#: ``docs/evidence/2026-08-12-hv-hv-creepage-determination.md`` Sec 3.1.
HV_TANK_CREEPAGE_PD2_MM: float = 6.3

#: Same row of Table 18 (functional insulation, cl. 29.2.4), PD3 = 10.0mm.
#: PD2 is conditional on a sealed compartment that does not exist on this
#: board (``docs/evidence/2026-08-11-pd2-decision-record.md``), so PD3 is
#: the figure this module designs against by default.
HV_TANK_CREEPAGE_PD3_MM: float = 10.0

#: Design against PD3, not PD2 (task instruction, carried into code so a
#: caller who does not pass ``margin_mm`` gets the as-built-correct figure
#: rather than the conditional one).
#:
#: Written as the bare ``NAME2 = NAME1`` selection-alias form on purpose.
#: ``scripts/check_creepage_clearance_drift.py`` models exactly this shape
#: as a *selection* between same-(metric, tier) candidates: it marks the
#: unselected sibling ``HV_TANK_CREEPAGE_PD2_MM`` (6.3mm) as "declared but
#: not enforced" -- reported, never compared as live -- and keeps the
#: enforced ``HV_TANK_CREEPAGE_PD3_MM`` (10.0mm) participating in its
#: ``[creepage/functional]`` family, satisfying that gate's own "the
#: enforced value must still participate in its family" contract.
#:
#: This only works because that gate's tier vocabulary now includes
#: ``functional`` (IEC 60335-1 Table 18; added 2026-08-15, see
#: ``docs/evidence/2026-08-15-pending-decisions.md`` item A). The earlier
#: dict-lookup form here (``{"PD2": ..., "PD3": ...}[key]``) was a
#: workaround for a gate that could not model this tier at all: its
#: selection-alias self-verification failed closed (exit 5, GATE ERROR)
#: because the selected constant had no comparable family. The workaround
#: is now obsolete -- with ``functional`` a real tier the alias form works
#: and models the enforced-vs-fallback relationship correctly instead of
#: hiding both values in the gate's UNRESOLVED bucket.
DEFAULT_TANK_CREEPAGE_MM: float = HV_TANK_CREEPAGE_PD3_MM

#: The DC-bus rail family the tank node's 570.5 Vrms sits against. Named
#: explicitly rather than derived: the evidence doc's finding is
#: specifically "tank.c_tank1-p2 <-> bus rails" and names ``+170V_BUS`` and
#: ``DC_BUS_RTN`` (``docs/evidence/2026-08-12-hv-hv-creepage-determination.md``
#: Sec 4.3); ``DC_BUS+``/``DC_BUS-`` are the same family in
#: ``TEMPER_NET_ASSIGNMENTS`` (``core/design_rules.py``) and are included so
#: a board that renames or expands the rail set is caught rather than
#: silently dropping coverage. These are NETS, not components: the box-level
#: :func:`tank_creepage_pairs` can never name them, which is the structural
#: gap :func:`tank_bus_net_pairs` closes.
TANK_BUS_RAIL_NETS: frozenset[str] = frozenset(
    {"+170V_BUS", "DC_BUS_RTN", "DC_BUS+", "DC_BUS-"}
)


#: Classes this module treats as equivalent to "HighVoltage" for Group B
#: membership (module docstring: "the SAME 16-net classification ... uses
#: to scope its own DRU rule's B-side"). UPDATED 2026-08-13 (docs/evidence/
#: 2026-08-13-netclass-current-scoping.md): HighVoltageSignal was carved out
#: of HighVoltage that day (current-band re-scope, not a domain change --
#: same clearance/creepage/voltage_v/safety_category) and generate_kicad_dru.py's
#: own "HighVoltageTank functional creepage" rule (the DRU rule this module
#: mirrors) was extended to include it on the same day. Without this update,
#: every component whose only HV-classifying pin moved to HighVoltageSignal
#: (measured: K2, R7, R12, R19, R23, U8 on the real board) would silently
#: drop out of Group B here while remaining fully protected at the DRU/DRC
#: level -- a placement-time-only coverage gap this module's own docstring
#: says should not exist. HighVoltageTank is deliberately NOT included here:
#: that is a separate, PRE-EXISTING gap (this literal-string check already
#: excluded HighVoltageTank before this task), not one this task introduced,
#: and fixing it is a larger, independent decision outside this task's scope.
_HV_EQUIVALENT_CLASSES: frozenset[str] = frozenset({"HighVoltage", "HighVoltageSignal"})


def _hv_net_names(net_class_map: dict[str, str] | None = None) -> frozenset[str]:
    """Every net classified ``"HighVoltage"`` (or an equivalent current-band
    carve-out, see :data:`_HV_EQUIVALENT_CLASSES`) in
    ``TEMPER_NET_ASSIGNMENTS`` (or a caller-supplied override map, for
    tests)."""
    if net_class_map is None:
        from temper_placer.core.design_rules import (
            TEMPER_NET_ASSIGNMENTS as net_class_map,  # noqa: N806
        )

    return frozenset(net for net, cls in net_class_map.items() if cls in _HV_EQUIVALENT_CLASSES)


def tank_node_refs(netlist: Netlist) -> frozenset[str]:
    """Every component with >=1 pad on :data:`TANK_NODE_NET`."""
    return frozenset(
        c.ref for c in netlist.components if any(p.net == TANK_NODE_NET for p in c.pins)
    )


def other_hv_refs(
    netlist: Netlist,
    tank_refs: frozenset[str],
    net_class_map: dict[str, str] | None = None,
) -> frozenset[str]:
    """Every component (excluding ``tank_refs``) with >=1 pad on a net
    classified ``"HighVoltage"``.

    See module docstring ("Group A components excluded from Group B") for
    why the exclusion matters: tank-node components (C25/C26/C27/R30) also
    carry a second ``HighVoltage``-classified net (``SW_NODE`` /
    ``tank-out``), and without the exclusion they would be constrained
    against each other and against themselves.
    """
    hv_nets = _hv_net_names(net_class_map)
    return frozenset(
        c.ref
        for c in netlist.components
        if c.ref not in tank_refs and any(p.net in hv_nets for p in c.pins)
    )


@dataclass(frozen=True)
class TankCreepagePair:
    """One (tank ref, other-HV ref) pair this module constrains."""

    tank_ref: str
    other_ref: str
    other_hv_nets: tuple[str, ...]  # which of the other ref's nets triggered inclusion


def tank_creepage_pairs(
    netlist: Netlist,
    net_class_map: dict[str, str] | None = None,
) -> list[TankCreepagePair]:
    """Every (tank ref, other-HV ref) pair, sorted for deterministic order."""
    tank_refs = tank_node_refs(netlist)
    other_refs = other_hv_refs(netlist, tank_refs, net_class_map)
    hv_nets = _hv_net_names(net_class_map)
    nets_by_ref = {
        c.ref: tuple(sorted({p.net for p in c.pins if p.net} & hv_nets))
        for c in netlist.components
        if c.ref in other_refs
    }
    return [
        TankCreepagePair(tank_ref=a, other_ref=b, other_hv_nets=nets_by_ref[b])
        for a in sorted(tank_refs)
        for b in sorted(other_refs)
    ]


def find_tank_self_pairs(netlist: Netlist, net_class_map: dict[str, str] | None = None) -> list[str]:
    """Tank-node refs whose OWN pads straddle a second ``HighVoltage`` net.

    These are the intra-footprint pairs no placement constraint can ever
    protect (module docstring, "What this cannot fix even in principle").
    Returned so a caller logs them loudly instead of the coverage gap
    being silent (the same discipline ``domain_clearance.py``'s
    ``find_intra_footprint_domain_conflicts`` established).
    """
    hv_nets = _hv_net_names(net_class_map)
    tank_refs = tank_node_refs(netlist)
    out = []
    for c in netlist.components:
        if c.ref not in tank_refs:
            continue
        other_nets = {p.net for p in c.pins if p.net} & hv_nets
        other_nets.discard(TANK_NODE_NET)
        if other_nets:
            out.append(c.ref)
    return sorted(out)


# ---------------------------------------------------------------------------
# Tank <-> DC-bus rail pairs: the net-level pair the box constraint cannot
# see, plus the copper-level checker that measures it. See the module
# docstring's "The pair the box constraint structurally cannot see" section
# for why this exists and what the two quantities mean.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TankBusNetPair:
    """One (tank ref, DC-bus rail net) pair.

    The bus rail is a NET, not a component: this pair can never appear in
    :func:`tank_creepage_pairs` (a net has no refdes), which is exactly why
    the box-level constraint was blind to the board's highest-voltage
    shortfall. ``bus_net`` is a net NAME; asserting it against the board's
    component refdes set is a falsifier that catches a future regression
    where the pair silently collides with (or is absorbed by) the
    component enumeration.
    """

    tank_ref: str
    bus_net: str


def tank_bus_net_pairs(
    netlist: Netlist,
    net_class_map: dict[str, str] | None = None,
) -> list[TankBusNetPair]:
    """Every (tank ref, DC-bus rail net) pair whose rail is both
    HV-classified and present on the board, sorted for deterministic order.

    A rail that is declared in :data:`TANK_BUS_RAIL_NETS` but absent from
    the board's netlist (``DC_BUS+``/``DC_BUS-`` today) yields no pairs --
    there is nothing on the board to measure. A rail present but
    re-classified out of HV drops out too, which is a real coverage
    regression and is caught by the test's pair-count pin.
    """
    # Annotated list[str] (not inferred) so the salted-hash gate can prove
    # these are sorted lists, not sets: `tank_refs` is set-typed earlier in
    # this module (tank_creepage_pairs), and `sorted(<set>)` alone does not
    # clear that typing in the gate's conservative analysis.
    tank_refs: list[str] = sorted(tank_node_refs(netlist))
    hv_nets = _hv_net_names(net_class_map)
    present = frozenset(n.name for n in netlist.nets)
    bus: list[str] = sorted(TANK_BUS_RAIL_NETS & hv_nets & present)
    return [TankBusNetPair(a, b) for a in tank_refs for b in bus]


def _pad_world_spec(
    comp: Component, pin: Pin
) -> tuple[float, float, str, float, float, float, float]:
    """One pin as ``pad_pair_distance``'s pad tuple in BOARD coordinates.

    ``(width, height, shape, cx, cy, rotation_rad, roundrect_ratio)``.
    World center = local pin position rotated by the component's quadrant
    rotation, added to the component center; rotation is the quadrant plus
    the pad's own intrinsic rotation. Bit-identical to the production
    REQ-SAFE-01 pad parser (verified against
    ``temper_drc_rs.req_safe_01_component_pads`` on the real board -- both
    use ``temper_geometry.rotate_local_to_world_py``, see
    ``requirements/validators/_copper.py::_rotate``).
    """
    import math

    import temper_geometry as _tg

    q = int(comp.initial_rotation_quadrant or 0)
    dx, dy = _tg.rotate_local_to_world_py(
        pin.position[0], pin.position[1], math.radians(q * 90)
    )
    cx, cy = comp.initial_position
    rotation_rad = math.radians(q * 90) + math.radians(float(pin.pad_rotation_deg or 0.0))
    return (pin.width, pin.height, pin.shape, cx + dx, cy + dy, rotation_rad, pin.roundrect_ratio)


def _bus_net_pad_specs(netlist: Netlist, bus_net: str) -> list[tuple]:
    """Every pad on ``bus_net`` as a board-coordinate pad tuple."""
    return [
        _pad_world_spec(c, p)
        for c in netlist.components
        for p in c.pins
        if p.net == bus_net
    ]


def tank_bus_pad_gap_mm(netlist: Netlist, pair: TankBusNetPair) -> float:
    """Exact copper-to-copper distance between ``pair.tank_ref``'s pads on
    the tank node and every pad on ``pair.bus_net``.

    Uses ``pad_geometry.pad_pair_distance`` -- the exact shape-correct
    edge-to-edge kernel (no box proxy, no center-to-center optimism): the
    same quantity kicad-cli measures for a pad-to-pad pair. ``inf`` when
    either side has no pads (the bus net is present in the netlist by
    construction of :func:`tank_bus_net_pairs`, so only a tank ref with no
    tank-net pad can produce it).
    """
    from temper_placer.core.pad_geometry import pad_pair_distance

    tank_ref = next(c for c in netlist.components if c.ref == pair.tank_ref)
    tank_pads = [_pad_world_spec(tank_ref, p) for p in tank_ref.pins if p.net == TANK_NODE_NET]
    bus_pads = _bus_net_pad_specs(netlist, pair.bus_net)
    if not tank_pads or not bus_pads:
        return float("inf")
    return min(pad_pair_distance(a, b) for a in tank_pads for b in bus_pads)


def tank_bus_pour_contained_pads(
    netlist: Netlist,
    pair: TankBusNetPair,
    zones: list,
) -> list[tuple[str, tuple[str, ...]]]:
    """Tank-node pads of ``pair.tank_ref`` lying INSIDE a zone outline whose
    net is ``pair.bus_net``, on a layer the pad occupies.

    Returns ``[(pad_label, layers), ...]``. ``pad_label`` is
    ``"<ref>.<number>"``; ``layers`` is the sorted tuple of zone layers
    containing the pad (e.g. ``("B.Cu", "F.Cu")`` for a THT pad inside a
    two-layer pour).

    Why this is a copper-level quantity, not a placement artifact: the zone
    *fill* approaches a foreign pad to exactly the design's enforced
    netclass clearance, so for a contained pad the pad-pad distance is NOT
    the copper gap -- the pour is between them and the design itself bounds
    the gap to its clearance value. Measured on the committed board: C26's
    and R30's tank pads are inside the ``DC_BUS_RTN`` pours on both layers
    (both are THT, layer=all) -- the evidence doc's "2.0mm provided" is
    physical copper geometry, not a routing hypothetical.

    ``zones`` are ``temper_placer.core.board.Zone`` objects (from
    ``parse_kicad_pcb_v6(...).zones``), each with ``net_classes``,
    ``layers`` and ``polygon``. A pad occupies layer ``L`` when its pin
    layer is ``"all"`` (THT) or ``L`` itself.
    """
    from shapely.geometry import Point, Polygon

    tank_ref = next(c for c in netlist.components if c.ref == pair.tank_ref)
    per_pad: dict[str, set[str]] = {}
    for p in tank_ref.pins:
        if p.net != TANK_NODE_NET:
            continue
        pt = Point(_pad_world_spec(tank_ref, p)[3:5])
        for z in zones:
            if pair.bus_net not in (z.net_classes or []):
                continue
            layers = set(z.layers) & _pin_layers(p)
            if not layers:
                continue
            if Polygon(z.polygon).covers(pt):
                per_pad.setdefault(f"{pair.tank_ref}.{p.number}", set()).update(layers)
    return sorted((label, tuple(sorted(layers))) for label, layers in per_pad.items())


def _pin_layers(pin: Pin) -> frozenset[str]:
    """Layers a pin's copper occupies: both faces for a THT pad, else its
    declared layer."""
    if pin.is_pth or pin.layer == "all":
        return frozenset({"F.Cu", "B.Cu"})
    return frozenset({pin.layer})


def enforced_tank_bus_clearance_mm() -> float:
    """The same-domain HV clearance the design enforces for a
    tank<->bus-rail pair, in mm.

    KiCad's pairwise clearance between two nets is the max of their two
    netclasses' clearances; both classes involved here (``HighVoltageTank``
    and ``HighVoltage``) currently declare 2.0, so this returns 2.0. The
    governing requirement for the pair is Table 18 functional creepage at
    the pair's >500-800V band: 6.3mm PD2 / 10.0mm PD3 -- see
    ``HV_TANK_CREEPAGE_PD2_MM``'s comment. The 2.0 figure is the
    reinforced mains<->PELV barrier value re-applied as same-domain HV<->HV
    clearance (``scripts/generate_kicad_dru.py:63-67``, N1 in
    ``docs/evidence/2026-08-15-safety-assertion-audit-resumed.md``); this
    function exists so the test can assert the enforced figure against the
    requirement and FAIL until the value is corrected.
    """
    from temper_placer.core.design_rules import TEMPER_NET_CLASSES

    tank_cls = TEMPER_NET_CLASSES["HighVoltageTank"].clearance
    bus_cls = TEMPER_NET_CLASSES["HighVoltage"].clearance
    return float(max(tank_cls, bus_cls))


def check_tank_bus_creepage(
    netlist: Netlist,
    pairs: list[TankBusNetPair],
    margin_mm: float = DEFAULT_TANK_CREEPAGE_MM,
    zones: list | None = None,
) -> list[tuple[TankBusNetPair, float, str]]:
    """Recompute the tank<->bus copper gap for every net pair and return
    every pair whose gap is under ``margin_mm``.

    Returns ``(pair, gap_mm, kind)`` with ``kind`` one of:

    - ``"pad-pad"``: exact pad-to-pad copper distance (:func:`tank_bus_pad_gap_mm`).
    - ``"pour-bounded"``: a tank pad is inside a bus-net pour outline on a
      layer it occupies; the reported ``gap_mm`` is the design's enforced
      netclass clearance (:func:`enforced_tank_bus_clearance_mm`) -- the
      pour approaches the pad to exactly that clearance, so the design
      itself bounds the copper gap to a value under the requirement.

    ``zones`` must be supplied for pour-bounded detection (``None`` keeps
    the check pad-pad only, which is the honest limit of netlist-only
    data). Independent of the solver: recomputes from coordinates, same
    discipline as :func:`check_tank_creepage_separation`.
    """
    violations: list[tuple[TankBusNetPair, float, str]] = []
    for pair in pairs:
        if zones is not None:
            contained = tank_bus_pour_contained_pads(netlist, pair, zones)
            if contained:
                bound = enforced_tank_bus_clearance_mm()
                if bound < margin_mm:
                    violations.append((pair, bound, "pour-bounded"))
                continue  # pad-pad distance is not the gap when a pour bounds it
        gap = tank_bus_pad_gap_mm(netlist, pair)
        if gap < margin_mm:
            violations.append((pair, gap, "pad-pad"))
    return violations


# ---------------------------------------------------------------------------
# Pumpkin wire-format emission
# ---------------------------------------------------------------------------


def tank_creepage_wire_constraints(
    netlist: Netlist,
    margin_mm: float = DEFAULT_TANK_CREEPAGE_MM,
    net_class_map: dict[str, str] | None = None,
    present_refs: frozenset[str] | None = None,
) -> list[dict]:
    """``ModelSpec.constraints`` entries (Pumpkin JSON wire format) for
    every tank-creepage pair, using the existing ``separated`` type.

    *present_refs*, when given, filters to refs the payload actually
    declares (same convention as ``heatsink_colocation_wire_constraints``).
    """
    pairs = tank_creepage_pairs(netlist, net_class_map)
    out: list[dict] = []
    for p in pairs:
        if present_refs is not None and (
            p.tank_ref not in present_refs or p.other_ref not in present_refs
        ):
            continue
        out.append(
            {
                "type": "separated",
                "a": p.tank_ref,
                "b": p.other_ref,
                "min_distance_mm": margin_mm,
            }
        )
    return out


# ---------------------------------------------------------------------------
# OR-Tools CpSatModel emission
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TankCreepageReport:
    """What :func:`add_tank_creepage_to_model` actually encoded."""

    tank_refs: tuple[str, ...]
    other_refs: tuple[str, ...]
    margin_mm: float
    pairs_encoded: int
    pairs_skipped_absent: int
    self_pairs: tuple[str, ...]  # intra-footprint refs this could not protect


def add_tank_creepage_to_model(
    model: CpSatModel,
    netlist: Netlist,
    margin_mm: float = DEFAULT_TANK_CREEPAGE_MM,
    net_class_map: dict[str, str] | None = None,
) -> TankCreepageReport:
    """Post the tank-creepage HARD constraint onto an OR-Tools
    :class:`CpSatModel`.

    Reuses the registered ``separated`` handler
    (``handlers/separated.py::encode_separated``) directly rather than
    re-implementing its Chebyshev-disjunction encoding -- one
    ``SeparatedConstraint`` per (tank ref, other-HV ref) pair, exactly the
    shape ``domain_clearance.py`` already establishes for cross-domain
    pairs. ``ctx`` is passed as ``None``: every ``a``/``b`` here is a
    literal component ref already present in ``components``, and
    ``handlers/_shared.py::resolve_refs`` returns immediately on that
    branch without touching ``ctx`` -- the zone-lookup branch, the only
    one that reads it, is unreachable for a literal ref.
    """
    from temper_placer.pcl.constraints import ConstraintTier, SeparatedConstraint
    from temper_placer.placer.cp_sat.handlers.separated import encode_separated

    pairs = tank_creepage_pairs(netlist, net_class_map)
    components = model.component_map
    self_pairs = find_tank_self_pairs(netlist, net_class_map)

    if self_pairs:
        logger.warning(
            "add_tank_creepage_to_model: %d tank-node component(s) straddle "
            "a second HighVoltage net WITHIN their own footprint and "
            "therefore have NO SeparatedConstraint protecting that pad "
            "pair -- no placement constraint can fix this (see module "
            "docstring): %s",
            len(self_pairs),
            ", ".join(self_pairs),
        )

    encoded = 0
    skipped = 0
    tank_refs: set[str] = set()
    other_refs: set[str] = set()
    for p in pairs:
        if p.tank_ref not in components or p.other_ref not in components:
            skipped += 1
            continue
        tank_refs.add(p.tank_ref)
        other_refs.add(p.other_ref)
        constraint = SeparatedConstraint(
            a=p.tank_ref,
            b=p.other_ref,
            min_distance_mm=margin_mm,
            tier=ConstraintTier.HARD,
            because=(
                f"IEC 60335-1 Table 18 functional creepage ({margin_mm}mm): "
                f"{p.tank_ref} (tank.c_tank1-p2, 570.5Vrms) vs {p.other_ref} "
                f"({', '.join(p.other_hv_nets)})"
            ),
            id=f"tank_creepage_{p.tank_ref}_{p.other_ref}",
        )
        encode_separated(constraint, components, model, None)  # type: ignore[arg-type]
        encoded += 1

    logger.info(
        "add_tank_creepage_to_model: encoded %d/%d tank-creepage SEPARATED "
        "constraints at %.2fmm (%d skipped, ref absent from model)",
        encoded,
        len(pairs),
        margin_mm,
        skipped,
    )

    return TankCreepageReport(
        tank_refs=tuple(sorted(tank_refs)),
        other_refs=tuple(sorted(other_refs)),
        margin_mm=margin_mm,
        pairs_encoded=encoded,
        pairs_skipped_absent=skipped,
        self_pairs=tuple(self_pairs),
    )


# ---------------------------------------------------------------------------
# Pure-Python post-solve / pre-solve checker (no CP-SAT dependency) --
# mirrors heatsink_colocation.check_heatsink_colocation's shape: usable
# against ANY resolved placement (solved or read straight off the board),
# not only inside a solve.
# ---------------------------------------------------------------------------


def _box(
    ref: str,
    positions_mm: dict[str, tuple[float, float]],
    rotations: dict[str, int],
    sizes_mm: dict[str, tuple[float, float]],
) -> tuple[float, float, float, float]:
    cx, cy = positions_mm[ref]
    w0, h0 = sizes_mm[ref]
    if rotations.get(ref, 0) % 2 == 1:
        w0, h0 = h0, w0
    return (cx - w0 / 2, cx + w0 / 2, cy - h0 / 2, cy + h0 / 2)


def _chebyshev_gap_mm(box_a: tuple[float, float, float, float], box_b: tuple[float, float, float, float]) -> float:
    ax0, ax1, ay0, ay1 = box_a
    bx0, bx1, by0, by1 = box_b
    return max(bx0 - ax1, ax0 - bx1, by0 - ay1, ay0 - by1)


def check_tank_creepage_separation(
    positions_mm: dict[str, tuple[float, float]],
    rotations: dict[str, int],
    sizes_mm: dict[str, tuple[float, float]],
    pairs: list[TankCreepagePair],
    margin_mm: float = DEFAULT_TANK_CREEPAGE_MM,
) -> list[tuple[TankCreepagePair, float]]:
    """Recompute the box-to-box Chebyshev gap for every pair against a
    resolved placement (solved OR read straight off a board) and return
    every pair whose gap is under ``margin_mm``.

    Independent of whatever the solver claims: same discipline as
    ``domain_clearance.py``'s ``audit_domain_clearance`` -- this
    recomputes from coordinates rather than trusting SAT/solve status.
    """
    violations: list[tuple[TankCreepagePair, float]] = []
    for p in pairs:
        if p.tank_ref not in positions_mm or p.other_ref not in positions_mm:
            continue
        box_a = _box(p.tank_ref, positions_mm, rotations, sizes_mm)
        box_b = _box(p.other_ref, positions_mm, rotations, sizes_mm)
        gap = _chebyshev_gap_mm(box_a, box_b)
        if gap < margin_mm:
            violations.append((p, gap))
    return violations
