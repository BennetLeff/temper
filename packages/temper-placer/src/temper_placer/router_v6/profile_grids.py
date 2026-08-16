"""One occupancy-grid family per clearance profile.

This is the occupancy-model half of the per-net-pair clearance fix; see
``pair_clearance.py`` for why a single grid cannot express a pair requirement
at all, and where the required figures come from.

THE SHAPE
---------
Instead of one ``{layer: OccupancyGrid}`` dict, keep one per clearance profile
(``pair_clearance.ClearanceProfiles``). All families start as copies of the
same base grids, so they agree on the board outline, keepouts and component
obstacles -- what differs is only how far each *routed* net's copper is dilated
in each family:

    family[P] gets net A stamped at  w_A/2 + stamp_clearance(class(A), P)

A net of class ``C`` then searches ``family[profile(C)]`` and nothing else.
Because the stamp already carries ``required(class_A, C) + w_C/2``, the
separation A* enforces between A and the searching net is pair-correct and
independent of which of the two routed first -- the two properties the
single-grid model could not have.

Deliberately NOT changed: the static obstacle layer. Pads and component
bodies are baked into ``RoutingSpace.available_area`` as an un-netted polygon
before any grid exists, so they carry no net identity and cannot be dilated
per pair without re-eroding the routing space once per profile. That is a
placement-side concern and is measured as such: stripping every segment and
via from this board leaves 48 violations under both rulesets (its placement
floor), while routing contributes 96-97% of the true count, and 1,053 of
1,291 distinct violating pairs are bare track<->track naming no component
(docs/evidence/2026-08-12-dru-rule-precedence.md). Track<->track and
track<->via are what this module governs. Pad<->track keeps today's behaviour
and is reported as a residual rather than silently claimed.

COST
----
Memory and stamp work are both linear in the profile count, which is the
number of distinct (requirement-vector, trace-width) signatures among the
board's LIVE net classes -- 7 on this board, not the 13 classes the rule file
names. Grids are ``int8``; see the evidence document for the measured figures.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from temper_placer.router_v6.astar_grid import _mark_route_blocked, _unmark_route_blocked
from temper_placer.router_v6.occupancy_grid import OccupancyGrid
from temper_placer.router_v6.pair_clearance import (
    UNASSIGNED_NETCLASS,
    ClearanceProfiles,
    load_pair_clearance_table,
    resolve_profiles,
)

if TYPE_CHECKING:
    from temper_placer.router_v6.astar_core import RoutePath, RoutePath3D
    from temper_placer.router_v6.stage0_data import DesignRules


class ProfileGrids:
    """The per-clearance-profile occupancy grid families for one route."""

    def __init__(
        self,
        base_grids: dict[str, OccupancyGrid],
        profiles: ClearanceProfiles,
        net_class_assignments: dict[str, str],
    ) -> None:
        self.profiles = profiles
        self._net_class = dict(net_class_assignments)
        self._families: dict[str, dict[str, OccupancyGrid]] = {}
        for index, profile in enumerate(profiles.profiles):
            if index == 0:
                # The first family reuses the caller's grids in place, so the
                # single-profile case costs nothing and every stage that still
                # holds a reference to the original objects keeps seeing a
                # live grid rather than a detached copy.
                self._families[profile] = base_grids
                continue
            self._families[profile] = {
                layer: replace(grid, grid=grid.grid.copy())
                for layer, grid in base_grids.items()
            }

    # -- lookup ---------------------------------------------------------

    def net_class(self, net_name: str) -> str:
        return self._net_class.get(net_name, UNASSIGNED_NETCLASS)

    def grids_for_net(self, net_name: str) -> dict[str, OccupancyGrid]:
        """The grid family a net of this name must search."""
        return self._families[self.profiles.profile_for_class(self.net_class(net_name))]

    def clearance_for(self, net_name: str, profile: str) -> float:
        return self.profiles.stamp_clearance_mm(self.net_class(net_name), profile)

    # -- mutation -------------------------------------------------------

    def mark_route(
        self,
        route_path: RoutePath | RoutePath3D,
        net_name: str,
        trace_width: float,
        net_id: int,
    ) -> None:
        """Stamp a completed route into EVERY family, at that family's radius."""
        for profile, grids in self._families.items():
            _mark_route_blocked(
                route_path,
                grids,
                trace_width=trace_width,
                clearance=self.clearance_for(net_name, profile),
                net_id=net_id,
            )

    def unmark_route(
        self,
        route_path: RoutePath | RoutePath3D,
        net_name: str,
        trace_width: float,
        net_id: int,
    ) -> None:
        """Undo :meth:`mark_route` -- same radii, so no stale halo survives."""
        for profile, grids in self._families.items():
            _unmark_route_blocked(
                route_path,
                grids,
                trace_width,
                self.clearance_for(net_name, profile),
                net_id,
            )

    def mark_path(
        self,
        layer: str,
        path: list[tuple[float, float]],
        net_name: str,
        trace_width: float,
        net_id: int,
    ) -> None:
        """Stamp one already-routed polyline (a terminal-tree branch)."""
        for profile, grids in self._families.items():
            grid = grids.get(layer)
            if grid is None:
                continue
            grid.mark_path_blocked(
                path, trace_width, self.clearance_for(net_name, profile), net_id
            )


def build_profile_grids(
    base_grids: dict[str, OccupancyGrid],
    design_rules: DesignRules,
    pair_table_path=None,
) -> ProfileGrids:
    """Build :class:`ProfileGrids` for the classes this board actually uses.

    Only classes that some net is assigned to become profiles; the rule file
    names 13, this board uses 9, and they collapse to 7 distinct profiles.
    """
    table = load_pair_clearance_table(pair_table_path)
    assignments = dict(getattr(design_rules, "net_class_assignments", {}) or {})
    net_classes = getattr(design_rules, "net_classes", {}) or {}

    live = sorted({name for name in assignments.values() if name in net_classes})
    widths = {name: net_classes[name].trace_width_mm for name in live}
    clearances = {name: net_classes[name].clearance_mm for name in live}

    profiles = resolve_profiles(
        table,
        widths,
        clearances,
        default_width_mm=design_rules.default_trace_width_mm,
        default_clearance_mm=design_rules.default_clearance_mm,
    )
    return ProfileGrids(base_grids, profiles, assignments)
