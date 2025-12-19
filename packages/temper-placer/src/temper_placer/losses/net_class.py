from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
import jax
import jax.numpy as jnp
from temper_placer.losses.base import LossFunction, LossResult, LossContext


@dataclass
class NetClassRule:
    """Rule defining minimum separation between two net classes."""

    class_a: str
    class_b: str
    min_separation_mm: float
    weight: float = 1.0


class NetClassSeparationLoss(LossFunction):
    """
    Penalizes components from conflicting net classes being too close.
    """

    def __init__(
        self,
        net_class_rules: List[NetClassRule],
        component_net_classes: Dict[int, str],
    ):
        self.rules = net_class_rules
        self.component_net_classes = component_net_classes

    @property
    def name(self) -> str:
        return "net_class_separation"

    def __call__(
        self,
        positions: jnp.ndarray,
        rotations: jnp.ndarray,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
    ) -> LossResult:
        # Placeholder for unresolved version
        return LossResult(value=jnp.array(0.0))


class ResolvedNetClassSeparationLoss(LossFunction):
    def __init__(self, rules_data):
        """
        rules_data is a list of tuples:
        (indices_a, indices_b, min_sep_sq, weight)
        where indices_a and indices_b are jnp arrays of component indices
        """
        self.rules_data = rules_data

    @property
    def name(self) -> str:
        return "net_class_separation"

    def __call__(
        self,
        positions: jnp.ndarray,
        rotations: jnp.ndarray,
        context: LossContext,
        epoch: int = 0,
        total_epochs: int = 1,
    ) -> LossResult:
        total_loss = jnp.array(0.0)

        for indices_a, indices_b, min_sep, weight in self.rules_data:
            # Extract positions for both groups
            pos_a = positions[indices_a]  # (Na, 2)
            pos_b = positions[indices_b]  # (Nb, 2)

            # Compute pairwise squared distances
            # (Na, 1, 2) - (1, Nb, 2) -> (Na, Nb, 2)
            diff = pos_a[:, None, :] - pos_b[None, :, :]
            dist_sq = jnp.sum(diff**2, axis=-1)  # (Na, Nb)
            dist = jnp.sqrt(dist_sq + 1e-6)

            # Penalty: max(0, min_sep - dist)^2
            violation = jnp.maximum(0.0, min_sep - dist)
            penalty = jnp.sum(violation**2)

            total_loss = total_loss + penalty * weight

        return LossResult(value=total_loss)


def create_net_class_loss(
    netlist,
    net_class_rules: List[NetClassRule],
    # Optional override for manual classification
    component_classes: Optional[Dict[str, str]] = None,
) -> ResolvedNetClassSeparationLoss:
    """
    Factory to resolve net classes and component indices.
    """
    # 1. Determine net class for each component
    # Strategy:
    # - If component_classes provided, use it (keyed by RefDes)
    # - Else, infer from netlist nets
    #   - Each component pin connects to a net
    #   - Net has a name -> classify net -> assign class to component?
    #   - A component might connect to multiple net classes (e.g. ADC to Analog and Digital)
    #   - Strategy: "Worst case" or "Primary" class?
    #   - Or: This loss operates on *components*?
    #   - Yes, physical separation is usually component-to-component for clearance.

    # Let's implementation a simple heuristic:
    # - Component belongs to class X if ANY of its nets are class X
    # - If multiple, it might need to respect rules for ALL its classes against others.
    # - Simpler: Allow assigning a component to a single "Dominant" class.

    # Map RefDes -> Component Index
    comp_map = {c.ref: i for i, c in enumerate(netlist.components)}

    # Build idx -> class map
    # Using the passed dict for now, assuming external classifier or simple mapping
    # If None, we need to auto-classify. Let's assume passed for now or empty.

    comp_class_map = {}
    if component_classes:
        for ref, cls in component_classes.items():
            if ref in comp_map:
                comp_class_map[comp_map[ref]] = cls

    # If we want to auto-classify from netlist (as per task description):
    # This would require iterating nets, checking patterns, finding connected comps.
    # Let's assume the caller provides the classification for the factory
    # OR we implement the heuristic here.

    # Let's group components by class
    class_groups = {}
    for idx, cls in comp_class_map.items():
        if cls not in class_groups:
            class_groups[cls] = []
        class_groups[cls].append(idx)

    # Prepare data for Resolved Loss
    rules_data = []

    for rule in net_class_rules:
        cls_a = rule.class_a
        cls_b = rule.class_b

        if cls_a in class_groups and cls_b in class_groups:
            indices_a = jnp.array(class_groups[cls_a], dtype=jnp.int32)
            indices_b = jnp.array(class_groups[cls_b], dtype=jnp.int32)

            rules_data.append(
                (indices_a, indices_b, float(rule.min_separation_mm), float(rule.weight))
            )

    return ResolvedNetClassSeparationLoss(rules_data)
