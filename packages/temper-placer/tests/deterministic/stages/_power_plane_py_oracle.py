"""VERBATIM pre-migration oracle for ``deterministic/stages/power_plane.py``.

Wave 4, Phase 5, batch 2 (deterministic leaf stages). Pinned from
``packages/temper-placer/src/temper_placer/deterministic/stages/power_plane.py``
at the dispatch base (origin/main). Do NOT edit: this file is the Python arm
of the differential. If it drifts, the differential proves nothing.

The pure compute of ``PowerPlaneStage.run``'s reassignment loop is pinned as
a module-level function (the ``run`` orchestration — the ``state.netlist``
guard, the ``frozenset`` wraps — stays Python in the shim and is not part of
the oracle). The two module-level plane-net tables stay Python constants and
are not part of the oracle (they are data, not compute).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class LayerAssignment:
    """Assignment of a net to a preferred routing layer."""

    net_name: str
    layer: int
    allow_layer_change: bool = True  # Can router switch layers via vias?
    is_plane: bool = False  # Is this a power plane net (In1.Cu/In2.Cu)?


def recompute_plane_assignments(
    existing_assignments,
    plane_nets,
    plane_layers,
    all_nets,
):
    """Pin the body of ``PowerPlaneStage.run``'s reassignment loop.

    ``existing_assignments`` is a list of LayerAssignment-like objects;
    ``plane_nets`` an iterable of net names; ``plane_layers`` a mapping; and
    ``all_nets`` an iterable of netlist net names.
    """
    assignment_by_net = {a.net_name: a for a in existing_assignments}

    # Process plane nets
    new_assignments = []
    for net_name, assignment in assignment_by_net.items():
        if net_name in plane_nets:
            # Update to plane connection
            layer = plane_layers.get(net_name, 1)  # Default to In1.Cu
            new_assignments.append(
                LayerAssignment(
                    net_name=net_name,
                    layer=layer,
                    allow_layer_change=assignment.allow_layer_change,
                    is_plane=True,
                )
            )
        else:
            # Keep existing assignment
            new_assignments.append(assignment)

    # Add assignments for plane nets not in existing assignments
    assigned_nets = {a.net_name for a in new_assignments}
    for net_name in plane_nets:
        if net_name not in assigned_nets and net_name in all_nets:
            layer = plane_layers.get(net_name, 1)
            new_assignments.append(
                LayerAssignment(
                    net_name=net_name,
                    layer=layer,
                    allow_layer_change=True,
                    is_plane=True,
                )
            )

    # Add non-plane nets that weren't in existing assignments
    for net in all_nets:
        if net not in {a.net_name for a in new_assignments}:
            new_assignments.append(
                LayerAssignment(
                    net_name=net,
                    layer=0,  # Default to F.Cu
                    allow_layer_change=True,
                    is_plane=False,
                )
            )

    return new_assignments
