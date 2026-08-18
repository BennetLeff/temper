# ruff: noqa: ARG001  # _allow_forced_segments keeps its parameters for call-site
# stability after the gate became unconditional; see its docstring.
"""Router V6: per-net routing policy predicates.

Two total functions of their arguments, with no side effects and no
dependency on grid or search state: whether a net is routed by A* at all,
and whether forced segments may be emitted for it. Keeping them separate
from the search core makes both directly testable and keeps the
fail-closed forced-segment rule in one obvious place.

Split out of _astar_reconstruct.py, which had grown past its size cap.
"""

from __future__ import annotations

from temper_placer.router_v6.stage0_data import DesignRules

_SKIP_NET_PREFIXES = ("unconnected-", "NC-", "DNP-", "NC_", "TP_")


def _should_route(net_name: str) -> bool:
    """Return True if net should be routed by A*.

    As of 2026-08-18 the only exclusions are ``_CONTINUITY_EXEMPT_NETS``
    (one net, an unresolved router memory blowup -- see below) and the
    ``_SKIP_NET_PREFIXES`` no-connect/test-point families. Zone-pour
    eligibility no longer excludes anything: see the CHANGED 2026-08-18
    note in the body for the measurements that retired that rule.

    HISTORICAL (the two fixes this function accumulated, kept because each
    records a premise that turned out to be false and how it was
    measured):

    Power, ground, and HV nets used to be excluded from A* *only when a
    zone pour will actually cover them* -- checked against
    ``_zone_layers_for_net()``, the netclass SSOT's real pour-eligibility
    gate (``NetClassRules.routing_strategy == "plane_required"``).

    FIXED 2026-08-08 (topology_copper_audit.py / the investigation this
    closes): this used to exclude every net matching the Power/GND/HV name
    patterns unconditionally, on the assumption "zone pours handle them."
    That assumption stopped holding after `d4047607` (2026-07-28) narrowed
    ``_zone_layers_for_net()`` to only grant zone eligibility to
    ``ACMains``/``HighVoltage`` (the classes that actually declare
    ``routing_strategy == "plane_required"``) -- ``Power``/``GND`` no
    longer do. Six nets (``+15V``, ``+3V3``, ``PWR_RTN``, ``V_BUS_SENSE``,
    ``gnd``, ``vcc``) matched the Power/GND name patterns here but were
    never zone-eligible under the SSOT, so they got no copper from either
    mechanism -- excluded from A* by this function, uncovered by
    ``_zone_layers_for_net``. Per-net evidence
    (``docs/evidence/2026-07-28-pour-strategy-audit.md`` Task 1/Task 3):
    every one of those six is spec'd for a trace, not a pour --
    ``V_BUS_SENSE`` is a high-impedance ADC sense line where a pour is
    "pure liability" (capacitive pickup), ``+3V3``/``vcc``/``+15V`` are
    sub-amp rails with only local-decoupling pour history (17/12/4 clusters
    that were pad-sized remnants, not real floods), and ``PWR_RTN``/``gnd``
    (return conductors) are recommended for a *bespoke, shrunk, inner-layer*
    pour this codebase does not yet generate -- granting them the current
    all-or-nothing F.Cu/B.Cu netclass-level eligibility would reproduce the
    exact oversized-pour, layer-blocking regression Task 2 measured (a KEEP
    -verdict pour on F.Cu/B.Cu is what walls those layers off from all other
    routing). Routing them via A* instead is strictly better than the
    current zero-copper state and matches Task 3's own recommendation
    ("Power/GateDrive/GND should route as traces by default"). That fix
    left Power/GND/HV nets the SSOT *does* grant zone eligibility to (e.g.
    ``SW_NODE``, ``DC_BUS_RTN``, ``ac_l``, ``ac_n``) still excluded from
    A*, "since a pour genuinely covers it" -- the premise the 2026-08-18
    change below retired on measured evidence.
    """
    from temper_placer.router_v6._zone_pour_stitch import _CONTINUITY_EXEMPT_NETS

    # ADDED then REVISED 2026-08-14
    # (docs/evidence/2026-08-14-ntc-no-realization-and-delta-t-reconciliation.md):
    # this started as an attempt to let A* attempt a real backbone trace
    # for `_CONTINUITY_EXEMPT_NETS` members IN ADDITION to their pour (a
    # pad geometrically "inside" a zone outline is invisible to the
    # pad-connectivity audit's segment/via graph, so a pour-only
    # realization can never be scored `fully_connected` -- see that
    # module's docstring). That attempt was REVERTED same-day after direct
    # measurement: routing `power_in.ntc-no` through A* -- even in
    # isolation, filtered to just this one net against the real board's
    # real obstacle geometry, nowhere near the full ~139-net pipeline --
    # exhausted an 8GB hard cap and aborted ("memory allocation of 4 bytes
    # failed") rather than terminating with a clean route-or-fail verdict.
    # This is a router robustness gap (unbounded/inefficient search when a
    # wide net's clearance-respecting path is very hard or impossible to
    # find), not merely "this net is hard to route" -- and it reproduces
    # with or without this carve-out, since `_should_route`'s upstream
    # `is_hv_net('power_in.ntc-no')` already independently returns False
    # (a separate, unrelated name-classifier gap -- see the evidence doc
    # SS1.4), which ALSO falls through to "route via A*" today. Explicitly
    # EXCLUDING `_CONTINUITY_EXEMPT_NETS` from A* here is therefore not
    # optional caution, it is the one place in this function that can
    # override that other gap and actually prevent the crash. Real
    # pad-to-pad connectivity for these nets is instead provided by direct
    # stitch segments inside the pour's own convex hull
    # (`_zone_pour_stitch.py`'s pad-to-pad stitching), which needs no
    # obstacle search at all: any straight line between two pads that are
    # both inside the same convex hull stays entirely inside it.
    if net_name in _CONTINUITY_EXEMPT_NETS:
        return False

    # CHANGED 2026-08-18 (docs/evidence/2026-08-18-astar-for-zone-eligible-nets.md):
    # the zone-eligibility exclusion that used to live here is REMOVED. It
    # read:
    #
    #     if is_power_net(n) or is_ground_net(n) or is_hv_net(n):
    #         if _zone_layers_for_net(n):
    #             return False
    #
    # i.e. "a net the SSOT grants a pour to needs no trace, because the
    # pour is its conductive path." Three independent 2026-08-17/18
    # investigations measured that premise false for every net it applied
    # to on this board: the pours fragment into disjoint islands (19 for
    # `+170V_BUS`'s 11 pads, 26 for `PWR_RTN`'s 15) and stay fragmented
    # under `--refill-zones`, and a creepage-aware pad-to-pad MST stitcher
    # bridges none of them (48 of 51 candidate edges blocked by the
    # creepage gate, the 3 survivors redundant with the pour) --
    # docs/evidence/2026-08-18-zone-pour-fragmentation-rootcause.md. A net
    # excluded here therefore got no conductive path from EITHER mechanism.
    #
    # Removing the exclusion lets A* -- which detours around obstacles,
    # unlike a straight-line stitch edge -- attempt these nets in addition
    # to their pour. See the evidence doc for the measured outcome; this
    # gate deliberately does not decide whether any given net succeeds,
    # only that it is allowed to be tried.
    #
    # `is_power_net`/`is_ground_net`/`is_hv_net` are no longer consulted
    # here at all: with the zone branch gone they had no effect on the
    # return value. `_CONTINUITY_EXEMPT_NETS` above is the one remaining
    # net-scoped exclusion and is NOT relaxed -- routing
    # `power_in.ntc-no` through A* exhausts an 8GB cap and aborts rather
    # than returning a route-or-fail verdict (a router robustness gap
    # documented 2026-08-14), so it stays excluded and stays measured as
    # such.
    return not any(net_name.startswith(p) for p in _SKIP_NET_PREFIXES)


def _allow_forced_segments(
    net_name: str,
    design_rules: DesignRules | None,
    tree_route_active: bool,
) -> bool:
    """Determine whether forced segments are permitted for a net.

    Always ``False``. Forced segments draw a raw, unchecked line between
    waypoints with zero clearance checking -- fabricating copper that may
    violate netclass clearance for the net it's drawn for. Nothing on this
    board is worth an honest "unrouted" less than a silently unsafe
    "routed": a net that can't find a real, clearance-respecting path is
    reported as failed (see ``attempt_route``'s forced-segment interception,
    ``_astar_reconstruct.py:409-448``), never fabricated.

    This gate was originally class-conditional (only HV/AC-class nets, per
    R6 of docs/plans/2026-07-23-008-feat-property-test-hardening-plan.md)
    until docs/plans/2026-07-24-001-fix-forced-segment-fail-closed-plan.md
    generalized it: congested power/ground nets were still fabricating
    clearance-violating copper through this same fallback, which is why
    ``shorting_items`` didn't improve after the netclass-clearance wiring
    fix landed. ``net_name``, ``design_rules``, and ``tree_route_active``
    are accepted for call-site stability but no longer change the outcome.
    """
    return False
