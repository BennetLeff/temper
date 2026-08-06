"""Connectivity validation stage — delegation shim.

Wave 4, Phase 5: the per-net connectivity compute (UnionFind over
pads/tracks/vias, the touch predicates, component classification, the
dangling-track scan) moved to ``temper-drc-rs``'s
``connectivity_validate_net_py``; this module keeps the ``run()``
orchestration: drc-oracle geometry extraction, per-net grouping,
plane-net/empty-net skipping, violation-object construction, summary
logging and the ``fail_on_violations`` raise. The pre-migration
implementation is pinned VERBATIM in
``tests/deterministic/stages/_connectivity_validation_py_oracle.py``.
"""

import logging
from dataclasses import dataclass, replace
from typing import Any

import temper_drc_rs as _drc

from temper_placer.router_v6.constraints_geometry import Point

from ..state import BoardState
from .base import Stage

logger = logging.getLogger(__name__)


@dataclass
class ConnectivityViolation:
    """Represents a connectivity error on the PCB."""

    type: str  # "orphan_island", "dangling_track", "unconnected_pad"
    net: str
    location: Point
    description: str


class ConnectivityValidationError(Exception):
    """Raised when connectivity violations exceed configured thresholds."""

    pass


class ConnectivityValidationStage(Stage):
    """
    Validates net connectivity, detecting unconnected pads,
    dangling tracks, and isolated copper islands.
    """

    def __init__(self, fail_on_violations: bool = False):
        self.fail_on_violations = fail_on_violations

    @property
    def name(self) -> str:
        return "connectivity_validation"

    def run(self, state: BoardState) -> BoardState:
        if not state.drc_oracle:
            logger.warning("No DRCOracle in state, skipping connectivity validation")
            return state

        geom = state.drc_oracle.geometry
        violations = []

        # Group all geometry by net
        nets: dict[str, dict[str, list[Any]]] = {}

        for pad in geom.pads:
            if pad.net not in nets:
                nets[pad.net] = {"pads": [], "tracks": [], "vias": []}
            nets[pad.net]["pads"].append(pad)

        for track in geom.tracks:
            if track.net not in nets:
                nets[track.net] = {"pads": [], "tracks": [], "vias": []}
            nets[track.net]["tracks"].append(track)

        for via in geom.vias:
            if via.net not in nets:
                nets[via.net] = {"pads": [], "tracks": [], "vias": []}
            nets[via.net]["vias"].append(via)

        # Get plane nets from assignments
        plane_nets = set()
        if state.layer_assignments:
            for assignment in state.layer_assignments:
                if assignment.is_plane:
                    plane_nets.add(assignment.net_name)

        # Validate each net
        for net_name, net_items in nets.items():
            if not net_name or net_name == "NoNet":
                continue

            # Skip plane nets - they are assumed connected via inner layer pours
            if net_name in plane_nets:
                continue

            net_violations = self._validate_net_connectivity(net_name, net_items)
            violations.extend(net_violations)

        # Log summary
        self._log_summary(violations)

        if self.fail_on_violations and violations:
            raise ConnectivityValidationError(f"{len(violations)} connectivity violations found")

        return replace(state, connectivity_violations=tuple(violations))

    def _validate_net_connectivity(
        self, net_name: str, items: dict[str, list[Any]]
    ) -> list[ConnectivityViolation]:
        pads = items["pads"]
        tracks = items["tracks"]
        vias = items["vias"]

        flat_pads = [
            (p.center.x, p.center.y, p.layer, p.id, p.size[0], p.size[1], p.rotation)
            for p in pads
        ]
        flat_tracks = [
            (t.start.x, t.start.y, t.end.x, t.end.y, t.layer) for t in tracks
        ]
        flat_vias = [(v.center.x, v.center.y) for v in vias]

        rows = _drc.connectivity_validate_net_py(net_name, flat_pads, flat_tracks, flat_vias)
        return [
            ConnectivityViolation(
                type=row[0], net=net_name, location=Point(row[1], row[2]), description=row[3]
            )
            for row in rows
        ]

    def _log_summary(self, violations: list[ConnectivityViolation]):
        if not violations:
            logger.info("Connectivity validation passed: 0 violations")
            return

        by_type: dict[str, int] = {}
        for v in violations:
            by_type[v.type] = by_type.get(v.type, 0) + 1

        logger.warning(f"Connectivity validation: {len(violations)} violations")
        for vtype, count in sorted(by_type.items(), key=lambda x: -x[1]):
            logger.warning(f"  {vtype}: {count}")
