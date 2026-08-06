"""Pinned Python oracle for router_v6 cluster F — quality metrics (Wave 4).

**DO NOT EDIT — THESE ARE THE REFERENCE.**  Every executable statement below
is a VERBATIM ``git show`` extraction from commit
``15110feccc6ec9389f0777d3cff1ce9f81b11068`` (``origin/main``, 2026-08-04) of:

* ``temper_placer/router_v6/metrics/slop_linter.py``
* ``temper_placer/router_v6/quality/corridor.py``
* ``temper_placer/router_v6/quality/via_count.py``

Nothing here is cleaned up, refactored, or fixed — **including the things that
look like bugs** (see "Known defects, deliberately preserved" below).  The
value of this module is that it is byte-faithful.  If a kernel's contract
genuinely changes, re-pin the oracle from the new base commit first; do not
edit it in place.  ``test_quality_metrics_oracle_pin.py`` re-runs the
``git show`` and asserts byte-identity of every symbol below, so an edit here
fails CI rather than silently weakening the differential proof.

What was omitted, and why
-------------------------
Six top-level functions from the pinned sources are **not** copied here.  Every
one of them is pure I/O delegation containing zero arithmetic — a two-line
``_parse_pcb`` call followed by a call to a ``*_from_parse`` entry point that
*is* pinned below:

===================================  =========================================
Omitted                              Pinned kernel it delegates to
===================================  =========================================
``corridor._parse_pcb``              (I/O only)
``corridor.corridor_consolidation_score``   ``_compute_consolidation``
``corridor.track_spread_score``      ``_compute_spread``
``via_count._parse_pcb``             (I/O only)
``via_count.count_signal_vias``      ``_classify_vias``
``via_count.count_thermal_vias``     ``_classify_vias``
``via_count.count_stitching_vias``   ``_classify_vias``
``via_count.classify_vias``          ``_classify_vias``
===================================  =========================================

``slop_linter._parse_pcb`` **is** pinned, because ``slop_linter`` has no
parse-free entry point — ``lint_all`` (the live gate at
``placer/cp_sat/gates.py:960``) reaches the parser through it.  Keeping exactly
one of the three ``_parse_pcb`` copies is also what makes a single-file oracle
possible; see "Correction to the survey" below for why the three copies are not
interchangeable.

Correction to the survey
------------------------
``docs/evidence/2026-08-04-router-v6-migration-survey.md`` §4 cluster F states
the three modules share "a duplicated 3-line ``_parse_pcb``".  They do not
share it — there are **three near-copies with two different behaviours**:

* ``slop_linter._parse_pcb`` forwards its argument unchanged::

      return parse_kicad_pcb(pcb_path)

* ``corridor._parse_pcb`` and ``via_count._parse_pcb`` coerce first::

      return parse_kicad_pcb(Path(pcb_path))

The coercion is observable: the two ``quality`` modules accept a ``str`` path
wherever ``parse_kicad_pcb`` is stricter than ``Path``; ``slop_linter`` does
not.  The cluster still holds (one parsed-board fixture serves all three), but
a Rust port must not assume one shared helper.

Which language's operator is at each call site (catalog §2)
-----------------------------------------------------------
Recorded here because the Rust side needs it per call site, not per module.
Catalog classes are from ``docs/wave4-discipline-contract.md`` §2.

**B4 — CPython 2-arg ``math.hypot`` is Dekker double-double, not libm.**
Both distance call sites in ``slop_linter`` are CPython ``math.hypot``:

* ``_distance_mm``  -> ``math.hypot(a[0] - b[0], a[1] - b[1])``
* ``_angle_between`` -> ``math.hypot(v1[0], v1[1])`` and ``math.hypot(v2[0], v2[1])``

The Rust side must use a ``py_hypot`` (``vector_norm``) replica at all three,
**not** ``f64::hypot`` and **not** ``sqrt(dx*dx + dy*dy)``.  No GEOS/shapely
distance appears anywhere in cluster F, so B6 does not apply.

**B5 — Python ``max``/``min`` keep the FIRST argument on NaN.**
One call site, in ``_angle_between``::

    cos_angle = max(-1.0, min(1.0, dot / (m1 * m2)))

These are CPython **builtins**, not ``np.minimum``/``np.maximum`` (B12 does not
apply — cluster F imports no numpy at all).  The nesting is min-then-max and
must be preserved as such: for ``dot / (m1 * m2) == NaN``, CPython's ``min``
keeps its first argument ``1.0``, and the outer ``max(-1.0, 1.0)`` yields
``1.0``, so ``_angle_between`` returns ``degrees(acos(1.0)) == 0.0`` rather
than NaN.  A Rust ``t.max(-1.0).min(1.0)`` or ``f64::clamp`` diverges here.

A second, subtler ``min`` call site is in ``via_count._is_via_near_board_edge``::

    min_edge_dist = min(left_dist, right_dist, bottom_dist, top_dist)

This is the **variadic** builtin ``min``, whose NaN rule is "keep the first
argument that no later argument compares less than" — with a NaN in any
position all comparisons are false, so it returns the *first* element.  A Rust
fold over ``f64::min`` returns a non-NaN neighbour instead.

**B7 — f64 operation order.**  No ``**`` appears in cluster F, so the
``x**2``-is-``pow`` arm of B7 is inert.  The order-sensitive expressions that
must be copied with their exact grouping are:

* ``_angle_between``: ``dot = v1[0] * v2[0] + v1[1] * v2[1]`` (mul, mul, add —
  no ``mul_add`` fusion), and the divisor ``(m1 * m2)`` grouped before the
  division.
* ``_compute_consolidation`` / ``_compute_spread``:
  ``_CHANNEL_WIDTH_MULTIPLIER * (track_width_mm + min_clearance_mm)`` — the
  add is grouped first; ``3.0 * a + 3.0 * b`` is a different f64.
* ``corridor.TrackSegment.left_edge`` etc.: ``self.x - self.width_mm / 2.0``
  (divide, then subtract — not ``(2.0 * self.x - self.width_mm) / 2.0``).
* ``_get_component_bboxes`` / ``_compute_courtyards``: ``comp.width / 2.0``
  then add/subtract; ``_compute_courtyards`` additionally adds
  ``clearance_mm`` to the half-extent *before* offsetting the centre
  (``half_w = comp.width / 2.0 + clearance_mm``), which is not the same f64 as
  offsetting and then expanding.
* ``lint_single_net_detours``: ``path_length`` is a **left-to-right ``sum()``
  over the ordered segment list** with an implicit ``0`` (int) seed.  Both the
  order and the int seed are part of the contract: a Rust ``iter().sum()`` in a
  different order, or a reassociating/SIMD reduction, diverges.
* ``lint_single_net_detours`` midpoint: ``(start_pos[0] + end_pos[0]) / 2``
  divides by the **int** ``2``, not ``2.0`` (they agree bit-for-bit for f64 but
  the int literal is what the source says).

**B3 — banker's rounding.**  ``round()`` is never called in cluster F.  B3 is
nonetheless live through the **f-strings**: ``f"{angle:.1f}"``,
``f"{x:.2f}"`` and ``f"{ratio:.2f}"`` in every ``description`` field use
CPython's ``format`` -> ``float_repr_style`` shortest-correct rounding, which
is round-half-**even** on ties.  These strings are part of the differential
contract (they are compared, not ignored), so a Rust ``format!("{:.1}")``
— which rounds half-away-from-zero — diverges on exact ties such as
``0.125 -> "0.12"`` (Python) vs ``"0.13"`` (Rust).

**Non-arithmetic determinism hazards the Rust side must also replicate:**

* ``_order_traces`` is a greedy nearest-endpoint chain builder whose result
  depends on **input order** (it pops index 0 first) and on strict ``<``
  comparisons, so ties keep the earliest index.  Insertion order is a real
  input, not an incidental one.
* ``_load_traces_by_net`` returns a ``dict`` whose **insertion order** is the
  parser's trace order; ``lint_*`` iterate it directly, so finding order is
  parser-order-dependent.
* ``_assign_tracks_to_channels`` keys its result by ``id(ch)`` — a **CPython
  object address**.  It is stable within one call (the channel list is alive
  for the duration) but is not a value-level key at all; a Rust port must key
  by channel index instead, and must reproduce the fact that two equal-valued
  channels are *distinct* keys.
* ``list.sort`` in ``_compute_consolidation`` / ``_compute_spread`` is
  **timsort, stable**, on ``t.x`` / ``t.y``.  Ties preserve channel-assignment
  order.  Rust's ``sort_by`` is also stable, but ``sort_unstable_by`` is not
  and must not be used.  Note the key is a bare float, so a NaN coordinate
  makes the comparison non-transitive and the resulting order is an
  implementation detail of timsort — pinned, not designed.
* ``via_count._classify_vias`` reads ``is_ground_net``/``is_signal_net`` from
  ``router_v6.net_classification``, which branch on the **module-global**
  ``_SINGLE_LAYER_MODE`` flag (default ``False``, flipped by
  ``set_single_layer_mode``).  That flag is a hidden input to this kernel; the
  differential pins it at its default and asserts the default.

Known defects, deliberately preserved
-------------------------------------
Reported, **not** fixed — a fix would break the verbatim pin.

1. ``_classify_vias``: the entire ``if is_signal_net(via_net): signal += 1 /
   else: pass`` block is **dead**.  Two lines later ``signal`` is unconditionally
   overwritten by ``signal = total - thermal - stitching``.  The accumulator, the
   ``is_signal_net`` call, and the explanatory comment about "vias on non-signal
   nets" have no effect on the return value.
2. ``corridor``: component courtyards are built from
   ``comp.initial_position``, which is **board-relative**, while tracks are
   assigned from ``trace.start``/``trace.end``, which are **page-absolute**
   KiCad coordinates.  The two frames do not coincide, so on real boards no
   track is ever assigned to a channel and both scores collapse to their
   empty-input constants (``1.0`` and ``0.0``).  Measured over the five
   ``power_pcb_dataset`` corpus boards: 4 of 5 assign zero tracks to any of
   their 92-739 identified channels; only ``piantor_right`` assigns any, and
   only because its two coordinate ranges happen to overlap by accident
   (courtyards 0.8-139.3 mm, traces 69.6-195.2 mm).  See
   ``_quality_metrics_cases.CORPUS_BOARDS`` for the pinned numbers.
3. ``_compute_consolidation``'s inner pair loop is quadratic *and* recomputes
   ``intervening_nets`` per pair, so it is O(n^3) in a channel's track count.
   Behaviour-preserving, but the Rust port should not "obviously" reassociate it.

Original module docstrings
--------------------------
``metrics/slop_linter.py``::

    AI-Slop Pattern Linter - Post-route detection of machine-routing artifacts.

    Detects four artifact classes on routed PCB files:
    - Hairpin turns: track segments reversing direction within a close distance.
    - Zigzag patterns: 3+ consecutive alternating direction changes.
    - Isolated vias: vias with only one connected track segment (stubs).
    - Single-net detours: nets where path_length / direct_distance exceeds a
      threshold.

``quality/corridor.py``::

    Router V6 Quality: Corridor Consolidation + Track-Spread (U3)

``quality/via_count.py``::

    Router V6 Quality: Via Counting (U2)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from temper_placer.router_v6.net_classification import is_ground_net, is_signal_net

if TYPE_CHECKING:
    from temper_placer.io._kicad_types import ParseResult, ViaData
    from temper_placer.router_v6.routing_results import CompiledRoute

# Verbatim from quality/corridor.py — module-level constants, unchanged.
_DEFAULT_COURTYARD_CLEARANCE_MM = 0.25
_DEFAULT_TRACK_WIDTH_MM = 0.2
_DEFAULT_MIN_CLEARANCE_MM = 0.15
_CHANNEL_WIDTH_MULTIPLIER = 3.0


# ==========================================================================
# packages/temper-placer/src/temper_placer/router_v6/metrics/slop_linter.py
# ==========================================================================


def lint_hairpin_turns(routed_pcb_path: Path) -> list[dict]:
    """Find track segments that reverse direction by >=160deg.

    Parses the routed PCB, groups traces by net, orders them into
    connected paths, and checks the turn angle at each junction.
    """
    traces_by_net = _load_traces_by_net(routed_pcb_path)
    findings: list[dict] = []

    for net_name, traces in traces_by_net.items():
        ordered = _order_traces(traces)
        for i in range(1, len(ordered)):
            prev = ordered[i - 1]
            curr = ordered[i]
            angle = _angle_between(
                (prev["end"], prev["start"]),  # reverse incoming
                (curr["start"], curr["end"]),  # outgoing
            )
            if angle >= 160.0:
                findings.append(
                    {
                        "type": "hairpin",
                        "net_name": net_name,
                        "position": prev["end"],
                        "severity": angle,
                        "description": (
                            f"Hairpin turn ({angle:.1f} deg) at "
                            f"({prev['end'][0]:.2f}, {prev['end'][1]:.2f}) mm"
                        ),
                    }
                )
    return findings


def lint_zigzag_patterns(routed_pcb_path: Path) -> list[dict]:
    """Find 3+ consecutive alternating direction changes.

    Excludes hairpin reversals (>=160 deg) from the alternation count.
    """
    traces_by_net = _load_traces_by_net(routed_pcb_path)
    findings: list[dict] = []

    for net_name, traces in traces_by_net.items():
        ordered = _order_traces(traces)
        if len(ordered) < 4:
            continue

        # Determine turn direction at each junction.
        # "left" = +delta_angle, "right" = -delta_angle.
        turns: list[tuple[int, float, str]] = []  # (idx, angle, dir)
        for i in range(1, len(ordered)):
            prev = ordered[i - 1]
            curr = ordered[i]
            angle = _angle_between(
                (prev["end"], prev["start"]),
                (curr["start"], curr["end"]),
            )
            if angle >= 160.0:
                continue  # exclude hairpins
            if angle < 5.0:
                continue  # almost-straight, not a meaningful turn
            # Determine left vs right via cross-product sign.
            v_in = _vector(prev["end"], prev["start"])
            v_out = _vector(curr["start"], curr["end"])
            cross = v_in[0] * v_out[1] - v_in[1] * v_out[0]
            direction = "left" if cross > 0 else "right" if cross < 0 else "straight"
            if direction == "straight":
                continue
            turns.append((i, angle, direction))

        # Scan for 3+ alternating turns.
        for start in range(len(turns) - 3 + 1):
            window = turns[start : start + 3]
            dirs = [t[2] for t in window]
            if len(set(dirs)) == 1:
                continue  # all same direction — not alternating
            alternating = all(dirs[j] != dirs[j + 1] for j in range(len(dirs) - 1))
            if alternating:
                mid_turn = turns[start + 1]
                junction = ordered[mid_turn[0] - 1]
                findings.append(
                    {
                        "type": "zigzag",
                        "net_name": net_name,
                        "position": junction["end"],
                        "severity": float(len(window)),
                        "description": (
                            f"Zigzag pattern ({len(window)} alternating turns) near "
                            f"({junction['end'][0]:.2f}, {junction['end'][1]:.2f}) mm"
                        ),
                    }
                )
    return findings


def lint_isolated_vias(routed_pcb_path: Path) -> list[dict]:
    """Find vias with only one connected track segment (stubs)."""
    parse_result = _parse_pcb(routed_pcb_path)
    vias = [
        {
            "position": v.position,
            "net": v.net,
            "layers": v.layers,
        }
        for v in parse_result.vias
    ]
    traces = [
        {
            "start": t.start,
            "end": t.end,
            "net": t.net,
        }
        for t in parse_result.traces
    ]

    findings: list[dict] = []
    for via in vias:
        via_pos = via["position"]
        via_net = via["net"]
        segment_count = 0
        for trace in traces:
            if trace["net"] != via_net:
                continue
            if (
                _distance_mm(trace["start"], via_pos) < 0.2
                or _distance_mm(trace["end"], via_pos) < 0.2
            ):
                segment_count += 1
        if segment_count == 1:
            findings.append(
                {
                    "type": "isolated_via",
                    "net_name": via_net or "?",
                    "position": via_pos,
                    "severity": 1.0,
                    "description": (
                        f"Isolated via (stub) on net {via_net or '?'} at "
                        f"({via_pos[0]:.2f}, {via_pos[1]:.2f}) mm"
                    ),
                }
            )
    return findings


def lint_single_net_detours(routed_pcb_path: Path, max_ratio: float = 1.5) -> list[dict]:
    """Find nets where path_length / direct_distance > max_ratio."""
    traces_by_net = _load_traces_by_net(routed_pcb_path)
    findings: list[dict] = []

    for net_name, traces in traces_by_net.items():
        if len(traces) < 2:
            continue

        ordered = _order_traces(traces)
        if len(ordered) < 2:
            continue

        start_pos = ordered[0]["start"]
        end_pos = ordered[-1]["end"]
        direct_dist = _distance_mm(start_pos, end_pos)
        if direct_dist < 0.001:
            continue  # avoid division by zero

        path_length = sum(_distance_mm(s["start"], s["end"]) for s in ordered)
        ratio = path_length / direct_dist
        if ratio > max_ratio:
            midpoint = (
                (start_pos[0] + end_pos[0]) / 2,
                (start_pos[1] + end_pos[1]) / 2,
            )
            findings.append(
                {
                    "type": "single_net_detour",
                    "net_name": net_name,
                    "position": midpoint,
                    "severity": ratio,
                    "description": (
                        f"Net {net_name} detour ratio {ratio:.2f} "
                        f"(path {path_length:.2f} mm / direct {direct_dist:.2f} mm) > {max_ratio}"
                    ),
                }
            )
    return findings


def lint_all(routed_pcb_path: Path) -> list[dict]:
    """Run all slop linters, return combined list of artifacts."""
    findings: list[dict] = []
    findings.extend(lint_hairpin_turns(routed_pcb_path))
    findings.extend(lint_zigzag_patterns(routed_pcb_path))
    findings.extend(lint_isolated_vias(routed_pcb_path))
    findings.extend(lint_single_net_detours(routed_pcb_path))
    return findings


def _parse_pcb(pcb_path: Path):
    """Parse a KiCad PCB file and return the ParseResult."""
    from temper_placer.io.kicad_parser import parse_kicad_pcb

    return parse_kicad_pcb(pcb_path)


def _load_traces_by_net(pcb_path: Path) -> dict[str, list[dict]]:
    """Load traces grouped by net name.

    Returns ``{net_name: [{"start": (x,y), "end": (x,y), "width": ..., "layer": ...}, ...]}``.
    """
    parse_result = _parse_pcb(pcb_path)
    by_net: dict[str, list[dict]] = {}
    for trace in parse_result.traces:
        net_name = trace.net or "_unnamed"
        by_net.setdefault(net_name, []).append(
            {
                "start": trace.start,
                "end": trace.end,
                "width": trace.width,
                "layer": trace.layer,
            }
        )
    return by_net


def _order_traces(traces: list[dict]) -> list[dict]:
    """Order a set of trace segments into a connected path by endpoint matching.

    Uses a greedy chain-building approach: start with the first segment, then
    repeatedly find the next segment whose start or end matches the current
    chain end.
    """
    if len(traces) <= 1:
        return traces

    remaining = list(traces)
    ordered: list[dict] = [remaining.pop(0)]
    eps = 0.1  # mm tolerance for endpoint matching

    while remaining:
        tail = ordered[-1]["end"]
        best_idx = -1
        best_dist = float("inf")
        best_reversed = False

        for idx, seg in enumerate(remaining):
            d_start = _distance_mm(tail, seg["start"])
            d_end = _distance_mm(tail, seg["end"])
            if d_start < best_dist and d_start < eps:
                best_idx = idx
                best_dist = d_start
                best_reversed = False
            if d_end < best_dist and d_end < eps:
                best_idx = idx
                best_dist = d_end
                best_reversed = True

        if best_idx < 0:
            # No adjacent segment found; append the nearest remaining segment
            # as a disconnected sub-path.
            nearest_idx = 0
            nearest_dist = _distance_mm(tail, remaining[0]["start"])
            for idx, seg in enumerate(remaining):
                d = _distance_mm(tail, seg["start"])
                if d < nearest_dist:
                    nearest_dist = d
                    nearest_idx = idx
            ordered.append(remaining.pop(nearest_idx))
            continue

        seg = remaining.pop(best_idx)
        if best_reversed:
            seg = {**seg, "start": seg["end"], "end": seg["start"]}
        ordered.append(seg)

    return ordered


def _vector(start: tuple[float, float], end: tuple[float, float]) -> tuple[float, float]:
    """Compute direction vector from start to end."""
    return (end[0] - start[0], end[1] - start[1])


def _angle_between(
    incoming: tuple[tuple[float, float], tuple[float, float]],
    outgoing: tuple[tuple[float, float], tuple[float, float]],
) -> float:
    """Compute the signed turn angle (0--180 deg) between two directed segments.

    Incoming: earlier segment end -> start (reversed direction for junction
    computation).  Outgoing: current segment start -> end.
    """
    v1 = _vector(incoming[0], incoming[1])
    v2 = _vector(outgoing[0], outgoing[1])
    m1 = math.hypot(v1[0], v1[1])
    m2 = math.hypot(v2[0], v2[1])
    if m1 < 1e-9 or m2 < 1e-9:
        return 0.0
    dot = v1[0] * v2[0] + v1[1] * v2[1]
    cos_angle = max(-1.0, min(1.0, dot / (m1 * m2)))
    return math.degrees(math.acos(cos_angle))


def _distance_mm(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Euclidean distance between two points in mm."""
    return math.hypot(a[0] - b[0], a[1] - b[1])


# ==========================================================================
# packages/temper-placer/src/temper_placer/router_v6/quality/corridor.py
# ==========================================================================


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


# ==========================================================================
# packages/temper-placer/src/temper_placer/router_v6/quality/via_count.py
# ==========================================================================


@dataclass(frozen=True)
class ViaCounts:
    """Classified via counts from a routed PCB."""

    signal: int
    thermal: int
    stitching: int
    total: int


def classify_vias_from_parse(parse_result: ParseResult) -> ViaCounts:
    """Classify all vias in a ParseResult (for reuse by human_reference_extractor).

    Args:
        parse_result: Parsed PCB data.

    Returns:
        ViaCounts with breakdown of signal, thermal, and stitching vias.
    """
    return _classify_vias(parse_result)


def _classify_vias(result: ParseResult) -> ViaCounts:
    """Classify all vias in a ParseResult.

    - Thermal: vias under Q1/Q2 footprint on DC_BUS+.
    - Stitching: vias around board edges on GND.
    - Signal: all other vias.
    """
    _THERMAL_COMPONENTS = frozenset({"Q1", "Q2"})
    _THERMAL_NET = "DC_BUS+"
    _STITCHING_EDGE_MARGIN_MM = 5.0  # Board-edge margin for stitching detection

    if not result.vias:
        return ViaCounts(signal=0, thermal=0, stitching=0, total=0)

    # Get Q1/Q2 component bboxes for thermal via detection
    thermal_bboxes = _get_component_bboxes(result, _THERMAL_COMPONENTS)

    # Get board edges for stitching via detection
    board_bbox = _get_board_bbox(result)

    signal = 0
    thermal = 0
    stitching = 0

    for via in result.vias:
        via_net = via.net or ""

        # Thermal via: under Q1/Q2 footprint on DC_BUS+
        if via_net.upper() == _THERMAL_NET.upper():
            # Check if via is within any Q1/Q2 bbox
            is_thermal = _is_via_in_bbox(via, thermal_bboxes) if thermal_bboxes else False
            if is_thermal:
                thermal += 1
                continue

        # Stitching via: around board edges on GND
        if is_ground_net(via_net):
            if board_bbox and _is_via_near_board_edge(via, board_bbox, _STITCHING_EDGE_MARGIN_MM):
                stitching += 1
                continue

        # Signal via: everything else (including valid signal nets)
        if is_signal_net(via_net):
            signal += 1
        else:
            # Via on non-signal net (ground/power/HV) that isn't thermal/stitching
            # — still count these outside the signal group
            pass

    total = len(result.vias)
    # Ensure signal count covers all remaining vias not classified as thermal/stitching
    signal = total - thermal - stitching

    return ViaCounts(signal=signal, thermal=thermal, stitching=stitching, total=total)


def _get_component_bboxes(
    result: ParseResult,
    refs: frozenset[str],
) -> list[tuple[float, float, float, float]]:
    """Get bounding boxes for components with given refs (x_min, y_min, x_max, y_max).

    Uses the component's initial_position and bounds to compute the bbox in
    board-absolute coordinates.
    """
    bboxes: list[tuple[float, float, float, float]] = []
    for comp in result.netlist.components:
        if comp.ref in refs and comp.initial_position is not None:
            cx, cy = comp.initial_position
            half_w = comp.width / 2.0
            half_h = comp.height / 2.0
            x_min = cx - half_w
            y_min = cy - half_h
            x_max = cx + half_w
            y_max = cy + half_h
            bboxes.append((x_min, y_min, x_max, y_max))
    return bboxes


def _get_board_bbox(
    result: ParseResult,
) -> tuple[float, float, float, float] | None:
    """Get the board bounding box (x_min, y_min, x_max, y_max)."""
    board = result.board
    if board is None:
        return None
    return (0.0, 0.0, float(board.width), float(board.height))


def _is_via_in_bbox(
    via: ViaData,
    bboxes: list[tuple[float, float, float, float]],
) -> bool:
    """Check if a via's position is within any of the given bboxes."""
    x, y = via.position
    return any(x_min <= x <= x_max and y_min <= y <= y_max for x_min, y_min, x_max, y_max in bboxes)


def _is_via_near_board_edge(
    via: ViaData,
    board_bbox: tuple[float, float, float, float],
    margin_mm: float,
) -> bool:
    """Check if a via is within ``margin_mm`` of any board edge."""
    x, y = via.position
    x_min, y_min, x_max, y_max = board_bbox
    left_dist = x - x_min
    right_dist = x_max - x
    bottom_dist = y - y_min
    top_dist = y_max - y
    min_edge_dist = min(left_dist, right_dist, bottom_dist, top_dist)
    return min_edge_dist <= margin_mm


def count_signal_vias_from_routing(
    compiled_routes: dict[str, CompiledRoute],
) -> tuple[int, list, list, list]:
    """Count signal vias from compiled routes (for QualityGate integration).

    Classifies vias by net name alone (no position/board context available).

    Args:
        compiled_routes: dict of net_name -> CompiledRoute.

    Returns:
        (signal_count, signal_vias, thermal_stitching_vias, all_vias)
    """
    from temper_placer.router_v6.via_placement import Via

    signal_vias: list[Via] = []
    non_signal_vias: list[Via] = []
    all_vias: list[Via] = []

    for route in compiled_routes.values():
        for via in route.vias:
            all_vias.append(via)
            if is_signal_net(via.net_name):
                signal_vias.append(via)
            else:
                non_signal_vias.append(via)

    return len(signal_vias), signal_vias, non_signal_vias, all_vias
