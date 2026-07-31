"""Deterministic evidence for bounded inherited-copper rip-up.

This module deliberately stops at selection.  It does not mutate a board or
authorize a rip-up.  A future bounded rip-up pass can consume this report
only after it has a corresponding reroute plan for every selected net.
"""

from __future__ import annotations

import math
from collections.abc import Collection, Iterable
from dataclasses import dataclass

from shapely.geometry import LineString, Point
from shapely.geometry.base import BaseGeometry

from temper_placer.io._kicad_types import TraceData, ViaData

__all__ = [
    "RipupCandidate",
    "RipupSelection",
    "select_ripup_candidates",
]


@dataclass(frozen=True, slots=True)
class RipupCandidate:
    """One named net whose inherited copper intersects a route corridor."""

    net_name: str
    track_count: int = 0
    via_count: int = 0
    layers: tuple[str, ...] = ()

    @property
    def copper_count(self) -> int:
        """Number of inherited copper primitives attributed to this net."""
        return self.track_count + self.via_count


@dataclass(frozen=True, slots=True)
class RipupSelection:
    """Auditable candidate set and ownership gaps for one corridor."""

    candidates: tuple[RipupCandidate, ...]
    unaddressed_track_count: int = 0
    unaddressed_via_count: int = 0

    @property
    def selected_net_names(self) -> tuple[str, ...]:
        """Return candidate names in deterministic lexical order."""
        return tuple(sorted(candidate.net_name for candidate in self.candidates))

    @property
    def unaddressed_copper_count(self) -> int:
        """Count intersecting primitives whose net identity is unavailable."""
        return self.unaddressed_track_count + self.unaddressed_via_count

    @property
    def is_addressable(self) -> bool:
        """Whether every intersecting inherited primitive has a named net."""
        return self.unaddressed_copper_count == 0


@dataclass
class _MutableCandidate:
    track_count: int = 0
    via_count: int = 0
    layers: set[str] | None = None

    def add_track(self, layer: str) -> None:
        self.track_count += 1
        if self.layers is None:
            self.layers = set()
        self.layers.add(layer)

    def add_via(self, layers: Iterable[str]) -> None:
        self.via_count += 1
        if self.layers is None:
            self.layers = set()
        self.layers.update(layers)


def select_ripup_candidates(
    tracks: Iterable[TraceData],
    vias: Iterable[ViaData],
    target_nets: Collection[str],
    corridor: BaseGeometry,
    *,
    clearance_mm: float = 0.0,
) -> RipupSelection:
    """Select named inherited-copper nets intersecting *corridor*.

    The target nets are always present, even when they have no committed
    copper.  Track and via footprints are expanded by ``clearance_mm`` before
    intersection, matching the conservative interpretation needed for a
    rip-up diagnostic.  Unnamed intersecting primitives are counted as an
    ownership gap instead of being silently ignored.

    The result is pure and deterministic: input order does not affect it, and
    candidates are ranked by descending copper count then lexical net name.
    It is evidence only; callers must not remove selected nets without a
    plan to reroute them and verify the resulting board.
    """
    normalized_targets = _normalize_target_nets(target_nets)
    if not corridor.is_empty and not corridor.is_valid:
        raise ValueError("corridor must be empty or a valid geometry")
    if not math.isfinite(clearance_mm) or clearance_mm < 0.0:
        raise ValueError("clearance_mm must be finite and non-negative")

    by_net: dict[str, _MutableCandidate] = {
        name: _MutableCandidate() for name in normalized_targets
    }
    unaddressed_tracks = 0
    unaddressed_vias = 0

    for track in tracks:
        footprint = _track_footprint(track, clearance_mm)
        if not footprint.intersects(corridor):
            continue
        net_name = _named_net(track.net)
        if net_name is None:
            unaddressed_tracks += 1
            continue
        by_net.setdefault(net_name, _MutableCandidate()).add_track(track.layer)

    for via in vias:
        footprint = _via_footprint(via, clearance_mm)
        if not footprint.intersects(corridor):
            continue
        net_name = _named_net(via.net)
        if net_name is None:
            unaddressed_vias += 1
            continue
        by_net.setdefault(net_name, _MutableCandidate()).add_via(via.layers)

    candidates = tuple(
        RipupCandidate(
            net_name=net_name,
            track_count=entry.track_count,
            via_count=entry.via_count,
            layers=tuple(sorted(entry.layers or ())),
        )
        for net_name, entry in sorted(
            by_net.items(),
            key=lambda item: (-item[1].track_count - item[1].via_count, item[0]),
        )
    )
    return RipupSelection(
        candidates=candidates,
        unaddressed_track_count=unaddressed_tracks,
        unaddressed_via_count=unaddressed_vias,
    )


def _normalize_target_nets(target_nets: Collection[str]) -> tuple[str, ...]:
    normalized = {name.strip() for name in target_nets}
    if not normalized or any(not name for name in normalized):
        raise ValueError("target_nets must contain non-empty names")
    return tuple(sorted(normalized))


def _named_net(net_name: str | None) -> str | None:
    if net_name is None:
        return None
    normalized = net_name.strip()
    return normalized or None


def _track_footprint(track: TraceData, clearance_mm: float) -> BaseGeometry:
    start = Point(track.start)
    geometry: BaseGeometry = (
        LineString([track.start, track.end])
        if track.start != track.end
        else start
    )
    return geometry.buffer(track.width / 2.0 + clearance_mm, cap_style=1)


def _via_footprint(via: ViaData, clearance_mm: float) -> BaseGeometry:
    return Point(via.position).buffer(via.diameter / 2.0 + clearance_mm)
