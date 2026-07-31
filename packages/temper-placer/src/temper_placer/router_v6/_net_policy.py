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
    """Return True if net should be routed by A* (signal nets only).

    Power, ground, and HV nets are handled by zone pours, not path routing.
    """
    from temper_placer.router_v6.net_classification import (
        is_ground_net,
        is_hv_net,
        is_power_net,
    )

    if is_power_net(net_name) or is_ground_net(net_name) or is_hv_net(net_name):
        return False
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
