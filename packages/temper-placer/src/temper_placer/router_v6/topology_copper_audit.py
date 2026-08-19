"""Topology-vs-copper divergence audit.

**Why this module exists.** ``net_batching.py``'s trace line --

    done: 11 batches, 11 solved at batch level, 0 batch-level crashes,
          0/110 nets fell back to Stage 4's existing no-topology path

-- measures whether Stage 3's per-batch SAT model produced a *channel-graph
topology* for each net (a ``NetTopology`` entry: which channel edges the net
may use). It says nothing about whether that topology ever became physical
copper. Two independent later stages can silently produce zero geometry for
a "solved" net:

1. Stage 4's clearance-aware A* (``run_astar_pathfinding``) can fail to find
   a legal, DRC-respecting path through the topology and fail closed (no
   forced segments, see ``_net_policy._allow_forced_segments``) -- a real,
   expected outcome, just one the batching trace never surfaces.
2. ``_should_route`` (``_net_policy.py``) excludes power/ground/HV nets from
   A* entirely on the stated assumption that "zone pours[will] handle them"
   -- but zone-pour eligibility (``_zone_layers_for_net``,
   ``_zone_pour_stitch.py``) is driven independently by each net's
   ``NetClassRules.routing_strategy`` (only ``"plane_required"``, which only
   ``ACMains``/``HighVoltage`` declare as of `d4047607`). A net excluded from
   A* by ``_should_route`` but not zone-eligible per the SSOT gets *no*
   copper-producing mechanism at all -- a policy gap between two
   independently-evolving classifiers, invisible to both Stage 3's trace and
   (previously) to any test.

MEASURED on a real net-batched production run (`pcb/temper.kicad_pcb`,
``--net-batching --batch-size 10``, this task's investigation): of 110
topology-solved nets, 36 emitted no explicit copper (segment/via). Of those
36: 9 were legitimately zone-pour-covered instead, 19 were attempted by
Stage 4's A* and genuinely failed to find a legal path
(forced-segment-disallowed), and 6 (``+15V``, ``+3V3``, ``PWR_RTN``,
``V_BUS_SENSE``, ``gnd``, ``vcc``) fell into the ``_should_route``/
``_zone_layers_for_net`` policy gap above -- excluded from A* *and* not
zone-eligible, orphaned by construction, regardless of net-batching.

**Correction, 2026-08-13.** The remaining 2 (``discharge.k_dis1-no``,
``discharge.k_dis2-no``) were originally counted here as "self-referential
(both 'pins' the same physical pad -- zero-length, no copper needed)."
That was wrong: ``pad_connectivity_audit`` (ground truth -- real pad
positions parsed off the board) shows both nets have 2 physical pads at 2
distinct coordinates, 7.5mm apart (K2/K3's manufacturer-duplicated
current-sharing contact pads -- see ``is_self_referential_net``'s
docstring for the full mechanism). They are a real, currently-unconnected
2-terminal net each, not a legitimate zero-copper case, and this module's
own ``is_self_referential_net`` helper no longer classifies them that way.
Root-caused and fixed in ``_pipeline_grid._net_pad_positions`` (the
router's own pad-position resolution had the identical name-identity
mistake, which is why Stage 4 printed "routed successfully" for both while
emitting zero connecting copper -- a false positive, not a policy gap).

This module gives that divergence a name and a shape so it can be reported
alongside the topology-level trace (instead of only discoverable by
independently re-parsing input and output boards, as this investigation had
to) and asserted against in tests.

REACHABILITY, MEASURED 2026-08-18 -- the audit itself no longer fires
---------------------------------------------------------------------
On the production recipe (``scripts/route_board.py`` defaults, this board,
4553 segments emitted), ``audit_topology_vs_copper``, ``nets_with_copper``,
``nets_carrying_copper`` and ``is_self_referential_net`` were each called
**zero** times; only ``net_number_to_name_map`` (5 calls, from
``_ground_plane``, ``_power_islands`` and ``pad_connectivity_audit``'s
``_parse_segments_and_vias``/``_parse_zones``) and the private
``_extract_top_level_blocks`` are live.

The mechanism is ``route_board.py``'s guard
``if content and result.topology_solved_nets:``. Since the 2026-08-16
SAT-vacuity fix the default, non-batched Stage 3 is a structural no-op that
claims no topology, so ``topology_solved_nets`` is ``[]`` and the audit is
skipped silently -- an anti-vacuity gate made vacuous by the very quantity
it was written to cross-check. It runs only under ``--net-batching``, a
non-default CLI branch. ``test_full_pipeline_run_surfaces_the_same_unexplained_gap``
does not catch this: it asserts ``topology_solved_nets == []`` and then
checks ``unexplained_gap == []`` over the resulting empty outcome set.

Fixing that is a ``route_board.py``/Stage-3 change, not a change here.
Measurement: ``docs/evidence/2026-08-18-no-rust-ledger-clearance-floor-and-topology-copper-audit.md``.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field

__all__ = [
    "NetCopperOutcome",
    "TopologyCopperAudit",
    "audit_topology_vs_copper",
    "is_self_referential_net",
    "net_number_to_name_map",
    "nets_carrying_copper",
    "nets_with_copper",
]

_NET_DECL_RE = re.compile(r'^\s*\(net\s+(\d+)\s+"((?:[^"\\]|\\.)*)"\)\s*$', re.MULTILINE)
_NET_ATTR_RE = re.compile(r"\(net\s+(\d+)\)")


def _extract_top_level_blocks(content: str, keywords: tuple[str, ...]) -> list[str]:
    """Paren-balanced extraction of every top-level ``(keyword ...)`` block.

    Same technique as ``_strip_copper.py``'s ``_strip_blocks`` (tracks paren
    depth line-by-line from each block's opening line), applied here
    independently -- this module does not import ``_strip_copper`` so it has
    no shared-bug risk with the code that *removes* these same blocks.
    """
    pattern = re.compile(r"^\s*\((" + "|".join(re.escape(k) for k in keywords) + r")\s")
    lines = content.split("\n")
    blocks: list[str] = []
    cur: list[str] = []
    depth = 0
    in_block = False
    for line in lines:
        if not in_block and pattern.match(line):
            in_block = True
            depth = 0
            cur = []
        if in_block:
            cur.append(line)
            depth += line.count("(") - line.count(")")
            if depth <= 0:
                in_block = False
                blocks.append("\n".join(cur))
            continue
    return blocks


def net_number_to_name_map(pcb_content: str) -> dict[int, str]:
    """Parse every top-level ``(net N "name")`` declaration into a dict."""
    return {int(m.group(1)): m.group(2) for m in _NET_DECL_RE.finditer(pcb_content)}


def nets_with_copper(pcb_content: str) -> tuple[set[str], set[str]]:
    """Return ``(explicit_copper_net_names, zone_copper_net_names)``.

    "Explicit copper" is ``(segment ...)``/``(via ...)`` -- an actual routed
    trace or via. "Zone copper" is a ``(zone ...)`` pour. Kept separate (not
    merged into one "has copper" set) because the distinction is exactly
    what determines whether a net's lack of an explicit trace is legitimate
    (covered by a pour instead) or not.
    """
    num_to_name = net_number_to_name_map(pcb_content)
    explicit: set[str] = set()
    for block in _extract_top_level_blocks(pcb_content, ("segment", "via")):
        m = _NET_ATTR_RE.search(block)
        if m:
            name = num_to_name.get(int(m.group(1)))
            if name:
                explicit.add(name)
    zoned: set[str] = set()
    for block in _extract_top_level_blocks(pcb_content, ("zone",)):
        m = _NET_ATTR_RE.search(block)
        if m:
            name = num_to_name.get(int(m.group(1)))
            if name:
                zoned.add(name)
    return explicit, zoned


def nets_carrying_copper(pcb_content: str) -> set[str]:
    """The single, unambiguous "does this net carry copper at all" set.

    **Why this exists.** ``nets_with_copper()`` deliberately returns two
    *separate* sets (explicit trace/via vs. zone pour) because that
    distinction matters for diagnosing *why* a net has no explicit trace.
    But it means every caller who just wants "how many nets carry copper"
    has to choose how to collapse the pair into one number, and two callers
    measuring the identical routed board content, independently, chose
    differently: one counted only the explicit set (a net routed by a
    literal trace/via), the other counted the union (explicit or zone) --
    treating a zone pour as "carrying copper" too. Both cited "using
    nets_with_copper()" and both were technically correct, since the
    accessor doesn't say which. That produced two different baseline
    counts for the same commit and the same routed board bytes (measured
    2026-08-08: explicit-only 52 vs. union 64 on an identical `pcb/
    temper.kicad_pcb --net-batching --batch-size 10` run -- the 12-net gap
    is exactly the zone-pour-covered HV/ACMains nets, e.g. `SW_NODE`,
    `DC_BUS_RTN`, `ac_l`, `ac_n`, that were never routed by A* on purpose).

    **The union is correct for "carries copper."** A zone pour is real,
    physical copper -- a net covered only by a pour is not missing copper,
    it has a different *kind* of copper than a trace. Excluding it
    undercounts completion and would make a zone-pour-covered net look
    identical to a genuinely orphaned one. This is also the convention
    ``NetCopperOutcome.has_copper`` (``has_explicit_copper or
    has_zone_copper``) already uses internally in this module -- this
    function just exposes that same definition as a single top-level call
    so future callers don't have to re-derive it (or re-diverge on it) from
    the raw tuple.

    Use ``nets_with_copper()`` directly only when the explicit-vs-zone
    distinction itself is what's being investigated (as
    ``audit_topology_vs_copper`` does); use this for a plain count/set of
    "nets with any copper."
    """
    explicit, zoned = nets_with_copper(pcb_content)
    return explicit | zoned


def is_self_referential_net(pins: Sequence[tuple[str, str]]) -> bool:
    """True only for a genuinely single-pin-instance net -- ``len(pins) == 1``.

    **Corrected 2026-08-13 (this was wrong).** This used to also return
    ``True`` whenever every ``(component_ref, pin_name)`` entry was
    identical for ``len(pins) >= 2`` -- e.g. ``pins == [('K2', '3'),
    ('K2', '3')]`` -- on the theory that "same (component, pad) name,
    listed twice" means "the same physical pad, so there is nothing to
    connect." **That is false on this exact board.** K2/K3 (the discharge
    relays, ``temper:Relay_SPDT_Schrack-RT314012``) have a
    manufacturer-duplicated pad "3"/"4"/"1" -- two GENUINELY DISTINCT
    physical solder holes, 7.5mm apart, sharing one pad number/name for
    16A current-sharing (see the footprint's own embedded datasheet
    comment in ``pcb/temper.kicad_pcb``). ``discharge.k_dis1-no`` /
    ``discharge.k_dis2-no`` (``pins == [('K2', '3'), ('K2', '3')]`` /
    ``[('K3', '3'), ('K3', '3')]``) were the real example this function's
    old docstring cited as *proof* of the (wrong) rule: MEASURED against
    ``pad_connectivity_audit`` (ground truth -- real physical pad
    positions parsed directly off the board, independent of this
    ``(ref, pin_name)`` tuple identity) both nets have ``pad_count == 2``
    at two distinct coordinates, ``has_any_copper == False`` -- a real,
    currently-unconnected 2-terminal net, not a trivial one. The false
    "self_referential_pad" classification let ``audit_topology_vs_copper``
    certify a genuine no-copper gap as "legitimately needs none," which is
    the mechanism that made these two nets look accounted-for while
    actually being silently unrouted (see ``_pipeline_grid._net_pad_positions``,
    whose ``comp.get_pin(name)`` first-match lookup made the same mistake
    on the router's own routing path, not just this diagnostic one).

    ``(component_ref, pin_name)`` identity is therefore not a safe proxy
    for physical-pad identity on this board and this function no longer
    trusts it for ``len(pins) >= 2``: a net component name/pin-name tuple
    matching another's tells you nothing about whether they're the same
    copper unless a footprint is known never to duplicate pad numbers,
    which K2/K3 disprove. Only the unambiguous, position-independent case
    -- a net with exactly one pin *instance* total, so there is only ever
    one thing to resolve regardless of what it turns out to be -- is
    trusted here.
    """
    return len(pins) == 1


@dataclass
class NetCopperOutcome:
    """Per-net topology-vs-copper outcome."""

    net_name: str
    has_explicit_copper: bool
    has_zone_copper: bool
    #: Non-None only when this net has NO copper at all and that absence is
    #: a recognized, legitimate case (self-referential net). A net excluded
    #: from A* by policy or zone-eligible-but-missing is deliberately left
    #: at None here -- see `note` -- because those are not (yet) proven
    #: legitimate, only explained/diagnosed.
    legitimate_reason: str | None
    #: Free-text diagnostic for the *unexplained* case -- distinguishes "A*
    #: attempted and failed" from "excluded from A* and not zone-eligible"
    #: without asserting either one is fine.
    note: str = ""

    @property
    def has_copper(self) -> bool:
        return self.has_explicit_copper or self.has_zone_copper

    @property
    def is_gap(self) -> bool:
        return not self.has_copper

    @property
    def is_unexplained(self) -> bool:
        return self.is_gap and self.legitimate_reason is None


@dataclass
class TopologyCopperAudit:
    """Full-run topology-vs-copper divergence report."""

    outcomes: dict[str, NetCopperOutcome] = field(default_factory=dict)

    @property
    def solved_count(self) -> int:
        return len(self.outcomes)

    @property
    def with_copper(self) -> list[str]:
        return sorted(n for n, o in self.outcomes.items() if o.has_copper)

    @property
    def legitimate_gap(self) -> list[str]:
        return sorted(n for n, o in self.outcomes.items() if o.is_gap and o.legitimate_reason)

    @property
    def unexplained_gap(self) -> list[str]:
        return sorted(n for n, o in self.outcomes.items() if o.is_unexplained)

    def format_report(self) -> str:
        unexplained = self.unexplained_gap
        msg = (
            f"[copper-audit] {self.solved_count} topology-solved nets: "
            f"{len(self.with_copper)} carry copper (explicit trace/via or zone), "
            f"{len(self.legitimate_gap)} legitimately need none, "
            f"{len(unexplained)} UNEXPLAINED (solved but emit no copper, no "
            "recorded legitimate reason)"
        )
        if unexplained:
            msg += ": " + ", ".join(unexplained)
        return msg


def audit_topology_vs_copper(
    topology_solved_nets: Iterable[str],
    pcb_content: str,
    net_pins: Mapping[str, Sequence[tuple[str, str]]],
    *,
    is_zone_pour_eligible: Callable[[str], bool] | None = None,
    is_excluded_from_astar: Callable[[str], bool] | None = None,
) -> TopologyCopperAudit:
    """Cross-check Stage 3's topology-solved net set against the final
    routed board's actual copper.

    Args:
        topology_solved_nets: net names Stage 3 (batched or monolithic)
            produced a ``NetTopology`` for -- what "solved" claims today.
        pcb_content: the final written ``.kicad_pcb`` text (post Stage 4,
            post zone regeneration) -- what actually shipped.
        net_pins: net name -> sequence of (component_ref, pad_name) pin
            tuples, for the self-referential-net check.
        is_zone_pour_eligible: predicate for "does this net's netclass
            declare `routing_strategy == plane_required`". Defaults to the
            real production predicate (``_zone_pour_stitch._zone_layers_for_net``).
            Overridable so tests can exercise the classification logic
            without needing the netclass SSOT loaded.
        is_excluded_from_astar: predicate for "does `_should_route` refuse
            to attempt A* for this net". Defaults to the real production
            predicate (``_net_policy._should_route``, inverted).
    """
    if is_zone_pour_eligible is None:
        from temper_placer.router_v6._zone_pour_stitch import _zone_layers_for_net

        is_zone_pour_eligible = lambda name: bool(_zone_layers_for_net(name))  # noqa: E731

    if is_excluded_from_astar is None:
        from temper_placer.router_v6._net_policy import _should_route

        is_excluded_from_astar = lambda name: not _should_route(name)  # noqa: E731

    explicit_copper, zone_copper = nets_with_copper(pcb_content)

    outcomes: dict[str, NetCopperOutcome] = {}
    for net_name in topology_solved_nets:
        has_explicit = net_name in explicit_copper
        has_zone = net_name in zone_copper
        reason: str | None = None
        note = ""
        if not has_explicit and not has_zone:
            pins = net_pins.get(net_name, ())
            if is_self_referential_net(pins):
                reason = "self_referential_pad"
            elif is_excluded_from_astar(net_name) and is_zone_pour_eligible(net_name):
                note = (
                    "zone-eligible per netclass SSOT (routing_strategy="
                    "plane_required) but no zone was emitted in the output "
                    "-- zone-generation gap, not a legitimate no-copper net"
                )
            elif is_excluded_from_astar(net_name) and not is_zone_pour_eligible(net_name):
                note = (
                    "excluded from A* by _should_route (power/ground/HV "
                    "heuristic) AND not zone-pour-eligible per the netclass "
                    "SSOT -- orphaned by a policy mismatch between the two "
                    "independent classifiers, regardless of net-batching"
                )
            else:
                note = (
                    "not excluded by policy -- Stage 4's A* was expected to "
                    "attempt this net but it produced no copper (e.g. a "
                    "forced-segment-disallowed failure after Stage 3 solved "
                    "its topology)"
                )
        outcomes[net_name] = NetCopperOutcome(
            net_name=net_name,
            has_explicit_copper=has_explicit,
            has_zone_copper=has_zone,
            legitimate_reason=reason,
            note=note,
        )
    return TopologyCopperAudit(outcomes)
