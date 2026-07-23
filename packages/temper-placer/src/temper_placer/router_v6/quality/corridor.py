"""
Router V6 Quality: Corridor Consolidation + Track-Spread (U3)

Defines and computes:
- corridor_consolidation_score: ratio of co-routed track pairs to total pairs
  sharing a channel. Range 0.0-1.0. Higher is better.
- track_spread_score: ratio of max gap between adjacent tracks to target
  spacing. Range >= 1.0. 1.0 = optimal spacing.

Gate: corridor >= 0.7, track-spread <= 1.5 (provisional).

Part of temper-7rqf (Stage 6 - Quality Gate)
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from temper_placer.io._kicad_types import ParseResult


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class Channel:
    """A rectangular gap region between two component courtyards.

    A channel is a space between components where tracks can run,
    wider than ``3 * (track_width + min_clearance)``.
    """

    x_min: float
    y_min: float
    x_max: float
    y_max: float
    gap_width_mm: float  # Width of the gap in mm
    axis: str  # "horizontal" or "vertical"
    component_a: str
    component_b: str

    @property
    def center(self) -> tuple[float, float]:
        return ((self.x_min + self.x_max) / 2, (self.y_min + self.y_max) / 2)

    @property
    def region(self) -> tuple[float, float, float, float]:
        return (self.x_min, self.y_min, self.x_max, self.y_max)


@dataclass
class TrackSegment:
    """A track segment passing through a channel."""

    net: str
    x: float
    y: float
    width_mm: float
    layer: str

    @property
    def left_edge(self) -> float:
        return self.x - self.width_mm / 2.0

    @property
    def right_edge(self) -> float:
        return self.x + self.width_mm / 2.0

    @property
    def bottom_edge(self) -> float:
        return self.y - self.width_mm / 2.0

    @property
    def top_edge(self) -> float:
        return self.y + self.width_mm / 2.0


# ---------------------------------------------------------------------------
# Default parameters
# ---------------------------------------------------------------------------

_DEFAULT_COURTYARD_CLEARANCE_MM = 0.25
_DEFAULT_TRACK_WIDTH_MM = 0.2
_DEFAULT_MIN_CLEARANCE_MM = 0.15
_CHANNEL_WIDTH_MULTIPLIER = 3.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def corridor_consolidation_score(
    routed_pcb_path: Path,
    courtyard_clearance_mm: float | None = None,
    track_width_mm: float | None = None,
    min_clearance_mm: float | None = None,
) -> float:
    """Ratio of co-routed track pairs to total pairs sharing a channel.

    A channel is the gap between two component courtyards wider than
    3 track widths. 'Co-routed' means two tracks adjacent with no
    foreign track interleaved.

    Range 0.0-1.0. Higher is better. Gate: >= 0.7.

    Args:
        routed_pcb_path: Path to the routed .kicad_pcb file.
        courtyard_clearance_mm: Clearance margin for courtyard expansion.
        track_width_mm: Typical track width in mm.
        min_clearance_mm: Minimum clearance from netclass SSOT.

    Returns:
        Consolidation score in [0.0, 1.0]. 1.0 if no channels have >= 2 tracks.
    """
    result = _parse_pcb(routed_pcb_path)
    return _compute_consolidation(result, courtyard_clearance_mm, track_width_mm, min_clearance_mm)


def track_spread_score(
    routed_pcb_path: Path,
    courtyard_clearance_mm: float | None = None,
    track_width_mm: float | None = None,
    min_clearance_mm: float | None = None,
) -> float:
    """Ratio of max gap between adjacent track edges to target spacing.

    Range >= 1.0. 1.0 = tracks at exactly target spacing.
    > 1.5 = too sparse. Gate: <= 1.5.

    Target spacing = min_clearance + track_width from netclass SSOT.

    Args:
        routed_pcb_path: Path to the routed .kicad_pcb file.
        courtyard_clearance_mm: Clearance margin for courtyard expansion.
        track_width_mm: Typical track width in mm.
        min_clearance_mm: Minimum clearance from netclass SSOT.

    Returns:
        Track-spread score >= 0.0. 0.0 if no tracks to spread.
    """
    result = _parse_pcb(routed_pcb_path)
    return _compute_spread(result, courtyard_clearance_mm, track_width_mm, min_clearance_mm)


# ---------------------------------------------------------------------------
# Internal: PCB parsing and geometry
# ---------------------------------------------------------------------------


def corridor_consolidation_from_parse(
    result: ParseResult,
    courtyard_clearance_mm: float | None = None,
    track_width_mm: float | None = None,
    min_clearance_mm: float | None = None,
) -> float:
    """Corridor consolidation score from a ParseResult (for reuse)."""
    return _compute_consolidation(result, courtyard_clearance_mm, track_width_mm, min_clearance_mm)


def track_spread_from_parse(
    result: ParseResult,
    courtyard_clearance_mm: float | None = None,
    track_width_mm: float | None = None,
    min_clearance_mm: float | None = None,
) -> float:
    """Track-spread score from a ParseResult (for reuse)."""
    return _compute_spread(result, courtyard_clearance_mm, track_width_mm, min_clearance_mm)


def _parse_pcb(pcb_path: Path) -> ParseResult:
    """Parse a KiCad PCB file."""
    from temper_placer.io.kicad_parser import parse_kicad_pcb

    return parse_kicad_pcb(Path(pcb_path))


def _compute_consolidation(
    result: ParseResult,
    courtyard_clearance_mm: float | None,
    track_width_mm: float | None,
    min_clearance_mm: float | None,
) -> float:
    """Compute corridor consolidation score from a ParseResult."""
    if courtyard_clearance_mm is None:
        courtyard_clearance_mm = _DEFAULT_COURTYARD_CLEARANCE_MM
    if track_width_mm is None:
        track_width_mm = _DEFAULT_TRACK_WIDTH_MM
    if min_clearance_mm is None:
        min_clearance_mm = _DEFAULT_MIN_CLEARANCE_MM

    channel_min_gap = _CHANNEL_WIDTH_MULTIPLIER * (track_width_mm + min_clearance_mm)
    courtyards = _compute_courtyards(result, courtyard_clearance_mm)
    channels = _identify_channels(courtyards, channel_min_gap)

    if not channels:
        return 1.0

    tracks_by_channel = _assign_tracks_to_channels(result, channels)
    total_pairs = 0
    co_routed_pairs = 0

    for ch in channels:
        channel_tracks = tracks_by_channel.get(id(ch), [])
        if len(channel_tracks) < 2:
            continue

        if ch.axis == "vertical":
            channel_tracks.sort(key=lambda t: t.x)
        else:
            channel_tracks.sort(key=lambda t: t.y)

        n = len(channel_tracks)
        total_pairs += n * (n - 1) // 2

        for i in range(n - 1):
            for j in range(i + 1, n):
                if j == i + 1:
                    co_routed_pairs += 1
                else:
                    intervening_nets = {track.net for track in channel_tracks[i + 1 : j]}
                    if len(intervening_nets) <= 1 and (
                        not intervening_nets or intervening_nets == {channel_tracks[i].net}
                    ):
                        co_routed_pairs += 1

    if total_pairs == 0:
        return 1.0

    return co_routed_pairs / total_pairs


def _compute_spread(
    result: ParseResult,
    courtyard_clearance_mm: float | None,
    track_width_mm: float | None,
    min_clearance_mm: float | None,
) -> float:
    """Compute track-spread score from a ParseResult."""
    if courtyard_clearance_mm is None:
        courtyard_clearance_mm = _DEFAULT_COURTYARD_CLEARANCE_MM
    if track_width_mm is None:
        track_width_mm = _DEFAULT_TRACK_WIDTH_MM
    if min_clearance_mm is None:
        min_clearance_mm = _DEFAULT_MIN_CLEARANCE_MM

    target_spacing_mm = track_width_mm + min_clearance_mm
    channel_min_gap = _CHANNEL_WIDTH_MULTIPLIER * (track_width_mm + min_clearance_mm)
    courtyards = _compute_courtyards(result, courtyard_clearance_mm)
    channels = _identify_channels(courtyards, channel_min_gap)

    if not channels:
        return 0.0

    tracks_by_channel = _assign_tracks_to_channels(result, channels)
    overall_max_gap_mm = 0.0
    any_tracks_found = False

    for ch in channels:
        channel_tracks = tracks_by_channel.get(id(ch), [])
        if len(channel_tracks) < 2:
            continue

        any_tracks_found = True

        if ch.axis == "vertical":
            channel_tracks.sort(key=lambda t: t.x)
        else:
            channel_tracks.sort(key=lambda t: t.y)

        for i in range(len(channel_tracks) - 1):
            if ch.axis == "vertical":
                gap = channel_tracks[i + 1].left_edge - channel_tracks[i].right_edge
            else:
                gap = channel_tracks[i + 1].bottom_edge - channel_tracks[i].top_edge
            if gap > overall_max_gap_mm:
                overall_max_gap_mm = gap

    if not any_tracks_found:
        return 0.0

    if target_spacing_mm <= 0.0:
        return 0.0

    return overall_max_gap_mm / target_spacing_mm


@dataclass
class _Courtyard:
    """Component courtyard (bbox + clearance margin)."""

    ref: str
    x_min: float
    y_min: float
    x_max: float
    y_max: float


def _compute_courtyards(
    result: ParseResult,
    clearance_mm: float,
) -> list[_Courtyard]:
    """Compute component courtyards from the parsed PCB.

    Each courtyard is the component bbox expanded by ``clearance_mm`` on all sides.
    """
    courtyards: list[_Courtyard] = []
    for comp in result.netlist.components:
        if comp.initial_position is None:
            continue
        cx, cy = comp.initial_position
        half_w = comp.width / 2.0 + clearance_mm
        half_h = comp.height / 2.0 + clearance_mm
        courtyards.append(
            _Courtyard(
                ref=comp.ref,
                x_min=cx - half_w,
                y_min=cy - half_h,
                x_max=cx + half_w,
                y_max=cy + half_h,
            )
        )
    return courtyards


def _identify_channels(
    courtyards: list[_Courtyard],
    min_gap_width_mm: float,
) -> list[Channel]:
    """Identify channels (gaps between courtyards wider than ``min_gap_width_mm``).

    A channel is formed where the projections of two courtyards overlap
    in one axis and the gap between them in the orthogonal axis is
    wider than ``min_gap_width_mm``.
    """
    if len(courtyards) < 2:
        return []

    channels: list[Channel] = []

    for i, ca in enumerate(courtyards):
        for j, cb in enumerate(courtyards):
            if j <= i:
                continue

            # Vertical channel: x-projections overlap, y-gap is wide enough
            x_overlap = _overlap(ca.x_min, ca.x_max, cb.x_min, cb.x_max)
            if x_overlap is not None:
                gap = _gap(ca.y_max, cb.y_min)
                if gap > min_gap_width_mm:
                    x0, x1 = x_overlap
                    if ca.y_max < cb.y_min:
                        channels.append(
                            Channel(
                                x_min=x0,
                                y_min=ca.y_max,
                                x_max=x1,
                                y_max=cb.y_min,
                                gap_width_mm=gap,
                                axis="vertical",
                                component_a=ca.ref,
                                component_b=cb.ref,
                            )
                        )
                    else:
                        channels.append(
                            Channel(
                                x_min=x0,
                                y_min=cb.y_max,
                                x_max=x1,
                                y_max=ca.y_min,
                                gap_width_mm=gap,
                                axis="vertical",
                                component_a=ca.ref,
                                component_b=cb.ref,
                            )
                        )

            # Horizontal channel: y-projections overlap, x-gap is wide enough
            y_overlap = _overlap(ca.y_min, ca.y_max, cb.y_min, cb.y_max)
            if y_overlap is not None:
                gap = _gap(ca.x_max, cb.x_min)
                if gap > min_gap_width_mm:
                    y0, y1 = y_overlap
                    if ca.x_max < cb.x_min:
                        channels.append(
                            Channel(
                                x_min=ca.x_max,
                                y_min=y0,
                                x_max=cb.x_min,
                                y_max=y1,
                                gap_width_mm=gap,
                                axis="horizontal",
                                component_a=ca.ref,
                                component_b=cb.ref,
                            )
                        )
                    else:
                        channels.append(
                            Channel(
                                x_min=cb.x_max,
                                y_min=y0,
                                x_max=ca.x_min,
                                y_max=y1,
                                gap_width_mm=gap,
                                axis="horizontal",
                                component_a=ca.ref,
                                component_b=cb.ref,
                            )
                        )

    return channels


def _assign_tracks_to_channels(
    result: ParseResult,
    channels: list[Channel],
) -> dict[int, list[TrackSegment]]:
    """Assign trace segments to the channels they pass through.

    Each track segment midpoint that falls within a channel's region
    is assigned to that channel.

    Returns:
        dict mapping ``id(channel)`` to list of ``TrackSegment``.
    """
    tracks: dict[int, list[TrackSegment]] = {id(ch): [] for ch in channels}

    for trace in result.traces:
        mid_x = (trace.start[0] + trace.end[0]) / 2.0
        mid_y = (trace.start[1] + trace.end[1]) / 2.0
        seg = TrackSegment(
            net=trace.net or "",
            x=mid_x,
            y=mid_y,
            width_mm=trace.width,
            layer=trace.layer,
        )
        for ch in channels:
            if _point_in_rect(mid_x, mid_y, ch.x_min, ch.y_min, ch.x_max, ch.y_max):
                tracks[id(ch)].append(seg)

    return tracks


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def _overlap(a_min: float, a_max: float, b_min: float, b_max: float) -> tuple[float, float] | None:
    """Return the overlapping interval of two ranges, or None."""
    o_min = max(a_min, b_min)
    o_max = min(a_max, b_max)
    if o_min < o_max:
        return (o_min, o_max)
    return None


def _gap(a_max: float, b_min: float) -> float:
    """Return the gap between two ranges (positive = separated, negative = overlapping)."""
    return b_min - a_max


def _point_in_rect(
    x: float, y: float, x_min: float, y_min: float, x_max: float, y_max: float
) -> bool:
    """Check if a point is inside a rectangle."""
    return x_min <= x <= x_max and y_min <= y <= y_max
