"""VERBATIM pre-migration oracle for ``deterministic/stages/layer_assignment.py``.

Wave 4, Phase 5, batch 2 (deterministic leaf stages). Pinned from
``packages/temper-placer/src/temper_placer/deterministic/stages/layer_assignment.py``
at the dispatch base (origin/main). Do NOT edit: this file is the Python arm
of the differential. If it drifts, the differential proves nothing.

The pure compute of ``LayerAssignmentStage`` is pinned as module-level
functions (the ``run`` orchestration — the ``state.netlist`` guard and the
``frozenset`` wrap — stays Python in the shim and is not part of the oracle).
``LayerAssignment`` is pinned as its dataclass, which the pyclass replicates.
"""

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class LayerAssignment:
    """Assignment of a net to a preferred routing layer."""

    net_name: str
    layer: int
    allow_layer_change: bool = True  # Can router switch layers via vias?
    is_plane: bool = False  # Is this a power plane net (In1.Cu/In2.Cu)?


def assign_layer_by_net_class(net_class: str) -> tuple[int, bool]:
    """Determine preferred layer and plane status based on net class.

    Layer mapping (4-layer board):
    - L0 (F.Cu/Top): HV, Signal, PowerTrace
    - L1 (In1.Cu): Ground plane
    - L2 (In2.Cu): Power plane
    - L3 (B.Cu/Bottom): Signal overflow

    Returns:
        (layer_index, is_plane)
    """
    mapping = {
        "HighVoltage": (0, False),
        "Power": (2, True),
        "PowerTrace": (0, False),
        "Ground": (1, True),
        "Signal": (0, False),
        "Differential": (0, False),
        "FinePitch": (0, False),
        "FinePitchPower": (2, True),
    }
    return mapping.get(net_class, (0, False))


def run_assign_layers(nets, manual_assignments, net_classes):
    """Pin the body of ``LayerAssignmentStage.run``'s per-net loop.

    ``nets`` is a list of objects exposing ``name`` and ``net_class``.
    """
    assignments = []

    for net in nets:
        # Check if there's a manual assignment
        if net.name in manual_assignments:
            layer = manual_assignments[net.name]
            # Infer plane status from layer index (1=In1, 2=In2)
            is_plane = layer in (1, 2)
            assignments.append(
                LayerAssignment(
                    net_name=net.name, layer=layer, allow_layer_change=True, is_plane=is_plane
                )
            )
            continue

        # Get net_class from config if available, otherwise use the one from parser
        net_class = net_classes.get(net.name, net.net_class) or "Signal"

        # Use net class rules to assign layer
        layer, is_plane = assign_layer_by_net_class(net_class)
        assignments.append(
            LayerAssignment(
                net_name=net.name, layer=layer, allow_layer_change=True, is_plane=is_plane
            )
        )

    return assignments
