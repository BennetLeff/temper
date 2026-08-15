"""Per-net-PAIR clearance for ZONE POURS, in the emitted geometry.

WHAT WAS WRONG
--------------
``_zone_pour_stitch._emit_zone_pours`` resolved one scalar ``effective_clearance``
per net CLASS and wrote it into every zone that class emits::

    for other_nc in zone_netclasses:            # <- zone-eligible classes ONLY
        eff = max(eff, class_pairs[pair].clearance)

Three defects, all measured on ``pcb/temper.kicad_pcb``:

1. **It is a per-net max, not a per-pair figure.** A single number cannot say
   "6.0mm from SELV, 3.0mm from HV, 0.5mm from the gate drive". Every zone on
   the committed board carries ``(clearance 6)`` -- including ``+3V3``,
   ``vcc``, ``PWM_HS/LS`` and ``V_BUS_SENSE``, which are SELV pours being held
   6.0mm off other SELV copper for no reason any rule states.
2. **The max ranges over the wrong set.** ``zone_netclasses`` is the set of
   *zone-eligible* classes, so the clearance a pour keeps from a net class is
   computed without that class being in the maximum unless it also pours. It
   lands on 6.0mm on this board only because every zone-eligible class here is
   HV or mains; the moment an LV class becomes pour-eligible the same code
   yields a figure derived from classes the pour may never be near.
3. **The numbers come from ``netclass_rules.yaml``'s ``class_pairs``**, whose
   every HV row cites "IEC 60335-1 Table 16 working isolation at 400V" -- a
   row that does not exist in that standard (established from recovered
   primary text, PR #1081) -- and whose own comments call the 6.0mm figures
   "a legacy, not primary-cited, number" with "the fab-authoritative
   enforcement point [being] scripts/generate_kicad_dru.py".

WHAT THIS MODULE DOES INSTEAD
-----------------------------
Reads ``configs/zone_pour_clearance.generated.yaml`` -- emitted by
``scripts/generate_kicad_dru.py`` by evaluating the rules it just wrote into
``pcb/temper.kicad_dru`` under KiCad's last-matching-rule-wins precedence,
with ``pcb/temper.kicad_pro``'s netclass clearances as the fallback for pairs
no rule matches. That two-step resolution is exactly what KiCad's own DRC
engine and zone filler perform, so a pour built against this table is decided
against the same figures kicad-cli will judge it by.

The table is keyed by the OTHER item's type as well as the two classes,
because ``Default routing``'s condition (``A.Type == 'Track' || B.Type ==
'Track'``) does not reach zone-to-pad, zone-to-via or zone-to-zone pairs: 64
class pairs resolve differently depending on what the pour is next to.

WHY THE GEOMETRY AND NOT THE ``(clearance ...)`` FIELD
------------------------------------------------------
A KiCad zone carries ONE scalar local clearance, so per-pair separation cannot
be expressed through it at all -- that field is the mechanism that produced
defect 1 above, not a mechanism that can fix it. Measured (see
docs/evidence/2026-08-13-zone-pour-safety-clearances.md sec 3): the field IS
honoured by the filler where no custom rule matches the pair, and IS overridden
by the custom rule where one does. So the correct division of labour is:

* the zone's local clearance carries the **minimum** requirement the pour has
  against anything on the board -- low enough never to over-clear a pair the
  rules relax, and it is only ever consulted where no rule speaks;
* the emitted **outline** is carved back from every other net's copper by that
  pair's own figure, so the per-pair requirement is in the geometry, where a
  single scalar cannot erase it.

KiCad's fill is a subset of the outline, so a carve is never undone by a
refill.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

#: The class KiCad reports for a net with no net-class assignment. Kept in
#: sync with ``generate_kicad_dru.UNASSIGNED_NETCLASS`` by
#: ``tests/router_v6/test_zone_pour_clearance.py``.
UNASSIGNED_NETCLASS = "Default"

#: ``scripts/generate_kicad_dru.KICAD_NAME_MAP``, in the direction this module
#: needs. A missing entry means the two names agree.
_ROUTER_TO_KICAD_CLASS = {"GND": "Ground"}

_DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[3] / "configs" / "zone_pour_clearance.generated.yaml"
)

#: The item kinds the generated table is keyed by.
OTHER_TYPES = ("Track", "Pad", "Via", "Zone")


def kicad_class_name(router_class: str) -> str:
    """Translate a router-side net-class name into the generated table's key."""
    return _ROUTER_TO_KICAD_CLASS.get(router_class or UNASSIGNED_NETCLASS, router_class)


@dataclass(frozen=True)
class ZonePourClearanceTable:
    """``{(zone_class, other_class, other_type): required_mm}``.

    ``required`` never raises. An unknown class resolves to
    :data:`UNASSIGNED_NETCLASS` -- the same treatment KiCad gives a net with no
    net-class assignment -- and an unknown item type resolves to the strictest
    figure the pair carries across the types the table does name. A safety
    table that raised mid-pour would turn a missing row into a failed board
    rather than a conservative one.
    """

    values: dict[tuple[str, str, str], float]
    classes: tuple[str, ...]
    default_clearance_mm: float = 0.2

    def _key_class(self, name: str | None) -> str:
        key = kicad_class_name(name or UNASSIGNED_NETCLASS)
        return key if key in self.classes else UNASSIGNED_NETCLASS

    def required(
        self,
        zone_class: str | None,
        other_class: str | None,
        other_type: str = "Track",
    ) -> float:
        """Required edge-to-edge clearance in mm between a pour and an item."""
        key_a = self._key_class(zone_class)
        key_b = self._key_class(other_class)
        value = self.values.get((key_a, key_b, other_type))
        if value is not None:
            return value
        across = [
            self.values[(key_a, key_b, t)] for t in OTHER_TYPES if (key_a, key_b, t) in self.values
        ]
        return max(across) if across else self.default_clearance_mm

    def min_required(self, zone_class: str | None, live_classes: tuple[str, ...]) -> float:
        """Smallest figure this pour must hold against any live class.

        This is what belongs in the zone's ``(clearance ...)`` field: KiCad
        consults it only where no custom rule matches the pair, so anything
        larger silently over-clears every relaxed pair, and anything smaller is
        never reached because the rule wins. The pair-specific remainder lives
        in the carved outline instead.
        """
        figures = [
            self.required(zone_class, other, item_type)
            for other in live_classes
            for item_type in OTHER_TYPES
        ]
        return min(figures) if figures else self.default_clearance_mm


def load_zone_pour_clearance_table(
    path: Path | str | None = None,
) -> ZonePourClearanceTable:
    """Load :data:`_DEFAULT_CONFIG_PATH` (or *path*) into a table."""
    config_path = Path(path) if path is not None else _DEFAULT_CONFIG_PATH
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    classes = tuple(raw["classes"])
    values: dict[tuple[str, str, str], float] = {}
    for key, per_type in raw["pairs"].items():
        zone_class, _, other_class = key.partition("|")
        for item_type, value in per_type.items():
            values[(zone_class, other_class, item_type)] = float(value)
    return ZonePourClearanceTable(values=values, classes=classes)


@lru_cache(maxsize=4)
def _cached_table(path: str | None) -> ZonePourClearanceTable:
    return load_zone_pour_clearance_table(path)


def default_table() -> ZonePourClearanceTable:
    """The generated table, parsed once per process."""
    return _cached_table(None)


# ---------------------------------------------------------------------------
# The carve
# ---------------------------------------------------------------------------

_SEGMENT_RE = re.compile(
    r"\(segment \(start ([-\d.]+) ([-\d.]+)\) \(end ([-\d.]+) ([-\d.]+)\)"
    r" \(width ([\d.]+)\) \(layer \"([^\"]+)\"\) \(net (\d+)\)"
)
_VIA_RE = re.compile(
    r"\(via \(at ([-\d.]+) ([-\d.]+)\) \(size ([\d.]+)\) \(drill [\d.]+\)"
    r" \(layers ([^)]*)\) \(net (\d+)\)"
)


def _net_class_of(net_name: str) -> str:
    from temper_placer.core.design_rules import TEMPER_NET_ASSIGNMENTS

    return TEMPER_NET_ASSIGNMENTS.get(net_name, "") or UNASSIGNED_NETCLASS


def pair_clearance_keepout(
    zone_net: str,
    layer: str,
    *,
    pcb: object | None = None,
    segments: list[str] | None = None,
    net_number_to_name: dict[int, str] | None = None,
    table: ZonePourClearanceTable | None = None,
):
    """Region a pour for *zone_net* on *layer* must not enter.

    Every other net's copper on this layer, each buffered by its own physical
    half-extent **plus the clearance that specific class pair requires** --
    6.0mm around SELV copper for a mains pour, 3.0mm around HV copper for the
    same pour, 0.5mm around gate-drive copper. That per-item figure is the
    whole point: the single ``(clearance ...)`` scalar a KiCad zone can carry
    cannot say three different things at once, so the requirement is put in
    the geometry instead.

    Sources, and what is deliberately NOT here:

    * ``pcb`` -- pads, pre-existing tracks and pre-existing vias, read through
      the same ``pin_world_position``/``pin_world_layer`` helpers
      ``_ground_plane._collect_other_net_copper`` already uses.
    * ``segments`` -- the tracks and vias THIS route just emitted, which are
      not on ``pcb`` yet. Parsed from the strings the emitter itself produced.
    * **Other zones are not carved against.** KiCad resolves zone-to-zone
      overlap by zone priority at fill time and the measurement in
      docs/evidence/2026-08-13-zone-pour-safety-clearances.md finds no
      zone-to-zone violation at any local clearance; carving here would
      instead make the result depend on which net's pour was emitted first,
      which is exactly the order-dependence PR #1112 removed from the A*.

    Returns ``None`` when nothing needs carving.
    """
    from shapely.geometry import LineString, Point
    from shapely.ops import unary_union

    from temper_placer.core.pin_geometry import pin_world_layer, pin_world_position

    table = table or default_table()
    zone_class = _net_class_of(zone_net)
    names = net_number_to_name or {}

    def clearance_for(other_net: str, item_type: str) -> float:
        return table.required(zone_class, _net_class_of(other_net), item_type)

    geoms: list = []

    for comp in getattr(pcb, "components", []) or []:
        for pin in getattr(comp, "pins", []) or []:
            if not pin.net or pin.net == zone_net:
                continue
            raw_layer = pin_world_layer(pin)
            on_layer = raw_layer in ("all", "*.Cu", layer) or (
                isinstance(raw_layer, str) and "Through" in raw_layer
            )
            if not on_layer:
                continue
            radius = max(pin.width, pin.height) / 2.0
            geoms.append(
                Point(pin_world_position(pin, comp)).buffer(
                    radius + clearance_for(pin.net, "Pad"), quad_segs=8
                )
            )

    for track in getattr(pcb, "tracks", []) or []:
        if track.net == zone_net or track.layer != layer:
            continue
        geoms.append(
            LineString([track.start, track.end]).buffer(
                track.width / 2.0 + clearance_for(track.net, "Track"), quad_segs=8
            )
        )

    for via in getattr(pcb, "vias", []) or []:
        if via.net == zone_net or layer not in getattr(via, "layers", ()):
            continue
        geoms.append(
            Point(via.position).buffer(
                via.diameter / 2.0 + clearance_for(via.net, "Via"), quad_segs=8
            )
        )

    for line in segments or []:
        match = _SEGMENT_RE.search(line)
        if match:
            x0, y0, x1, y1, width, seg_layer, net_num = match.groups()
            if seg_layer != layer:
                continue
            other = names.get(int(net_num), "")
            if not other or other == zone_net:
                continue
            geoms.append(
                LineString([(float(x0), float(y0)), (float(x1), float(y1))]).buffer(
                    float(width) / 2.0 + clearance_for(other, "Track"), quad_segs=8
                )
            )
            continue
        match = _VIA_RE.search(line)
        if match:
            x, y, size, via_layers, net_num = match.groups()
            if layer not in via_layers:
                continue
            other = names.get(int(net_num), "")
            if not other or other == zone_net:
                continue
            geoms.append(
                Point(float(x), float(y)).buffer(
                    float(size) / 2.0 + clearance_for(other, "Via"), quad_segs=8
                )
            )

    if not geoms:
        return None
    return unary_union(geoms)
