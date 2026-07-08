"""Auto-generate SEPARATED constraints for cross-class component-net pairs."""

from __future__ import annotations
import logging
from typing import TYPE_CHECKING

from temper_placer.pcl.constraints import ConstraintTier, SeparatedConstraint

if TYPE_CHECKING:
    from temper_placer.core.design_rules import DesignRules

logger = logging.getLogger(__name__)

# Map classify_net_type() return values to DesignRules net class names
_NET_TYPE_TO_CLASS = {
    "ground": "GND",
    "power": "Power",
    "hv": "HighVoltage",
    "signal": "Signal",
}

# Severity ordering for when a component has pins on multiple net classes.
# Highest rank wins: HighVoltage > Power > GND > Signal.
_SEVERITY_RANK = {"HighVoltage": 4, "Power": 3, "GND": 2, "Signal": 1}


def _resolve_component_net_class(comp, netlist) -> str | None:
    """Determine the net class for a component from its connected nets.

    Iterates ALL pins, classifies each connected net, and returns the
    highest-severity net class across all pins.  Returns None only when
    the component has no pins at all.

    Uses ``component.pins[i].net`` (Pin objects on the Component) rather
    than ``netlist.nets[].pins[].component`` (tuples in the Net parser
    output) — the Net.pins path is tuple data and lacks a ``.component``
    attribute.
    """
    from temper_placer.core.net_classification import classify_net_type

    pins = getattr(comp, 'pins', [])
    if not pins:
        return None

    best_class = None
    best_rank = -1

    for pin in pins:
        net_name = getattr(pin, 'net', '')
        if not net_name:
            continue
        net_type = classify_net_type(net_name)
        net_class = _NET_TYPE_TO_CLASS.get(net_type, "Signal")
        rank = _SEVERITY_RANK.get(net_class, 0)
        if rank > best_rank:
            best_rank = rank
            best_class = net_class

    return best_class


def generate_netclass_separated_constraints(
    netlist,
    components: list,
    design_rules: DesignRules,
    existing_constraints: list | None = None,
) -> list[SeparatedConstraint]:
    """Generate SEPARATED constraints for cross-class component-net pairs.
    
    Only cross-class pairs (different net classes) get explicit constraints.
    Same-class pairs are handled by the existing global NoOverlap2D.
    """
    constraints: list[SeparatedConstraint] = []

    # Build component -> net_class map
    comp_classes: dict[str, str] = {}
    for comp in components:
        nc = _resolve_component_net_class(comp, netlist)
        if nc:
            comp_classes[getattr(comp, 'ref', str(comp))] = nc

    if len(comp_classes) < 2:
        return constraints

    # Collect existing constraint pairs to skip
    existing_pairs: set[tuple[str, str]] = set()
    if existing_constraints:
        for c in existing_constraints:
            if hasattr(c, 'a') and hasattr(c, 'b'):
                key = tuple(sorted([str(c.a), str(c.b)]))
                existing_pairs.add(key)

    comp_refs = list(comp_classes.keys())
    for i in range(len(comp_refs)):
        for j in range(i + 1, len(comp_refs)):
            ra, rb = comp_refs[i], comp_refs[j]
            ca, cb = comp_classes[ra], comp_classes[rb]
            if ca == cb:
                continue

            pair_key = tuple(sorted([ra, rb]))
            if pair_key in existing_pairs:
                continue

            # Get per-class clearance via DesignRules
            rules_a = design_rules.get_rules_for_net("", net_class=ca)
            rules_b = design_rules.get_rules_for_net("", net_class=cb)
            max_self = max(rules_a.clearance, rules_b.clearance)

            # Check for class_pair override (from netclass_loader's class_pairs)
            cp_key = tuple(sorted([ca, cb]))
            class_pairs = getattr(design_rules, 'class_pairs', {})
            if cp_key in class_pairs:
                clearance = class_pairs[cp_key].get("clearance", max_self)
                because = class_pairs[cp_key].get("because", "")
            else:
                clearance = max_self
                because = ""

            c = SeparatedConstraint(
                a=ra,
                b=rb,
                min_distance_mm=clearance,
                tier=ConstraintTier.HARD,
                because=because or f"Netclass clearance {ca}↔{cb} at {clearance}mm",
                id=f"netclass_autogen_{ca}_{cb}_{ra}_{rb}",
            )
            constraints.append(c)

    logger.info("Auto-generated %d netclass SEPARATED constraints", len(constraints))
    return constraints
