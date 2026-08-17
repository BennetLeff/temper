"""Auto-generate SEPARATED constraints for cross-class component-net pairs."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from temper_placer.pcl.constraints import ConstraintTier, SeparatedConstraint

if TYPE_CHECKING:
    from temper_placer.core.design_rules import DesignRules

logger = logging.getLogger(__name__)

# Severity ordering for when a component has pins on multiple net classes:
# pick the most restrictive one to represent the whole component. Ranked by
# ``NetClassRules.safety_category`` (AC > HV > LV > unclassified), the same
# three-tier field the safety SSOT already carries on every class (see
# ``core/design_rules.py``'s ``TEMPER_NET_CLASSES``/``netclass_rules.yaml``);
# ties within a category are broken by the class's own ``clearance`` value
# (both already-existing NetClassRules fields, not a new figure).
_SAFETY_CATEGORY_RANK: dict[str | None, int] = {"AC": 3, "HV": 2, "LV": 1, "iso": 1}


def _resolve_component_net_class(comp, _netlist, design_rules: DesignRules) -> str | None:
    """Determine the net class for a component from its connected nets.

    Iterates ALL pins, classifies each connected net via
    ``design_rules.get_rules_for_net()`` -- the same authoritative,
    manifest/kicad_pro-backed classifier (``TEMPER_NET_ASSIGNMENTS``, per-net
    override -> explicit class -> ground/power/gate-HV/gate-SELV/high-current
    pattern cascade -> Default) every other consumer of ``DesignRules``
    already uses (router_v6, DRU generation, ``scripts/check_hv_netclass_
    coverage.py``) -- and returns the highest-severity net class across all
    pins.  Returns None only when the component has no pins at all.

    FIXED (docs/evidence/2026-08-17-netclass-classifier-manifest-and-
    ieccreepagegate-liveness.md): previously classified via
    ``core.net_classification.classify_net_type()``, a plain net-NAME
    keyword heuristic covering 4 coarse buckets (ground/power/hv/signal).
    That heuristic misclassified K1's mains-connected relay-contact nets
    (``power_in.ntc-no``, ``w1_2``) as "signal" -- the exact same bucket
    J1's SELV RTD nets fall into -- because neither net name contains an
    HV-sounding keyword, even though ``elec/domain_manifest.yaml`` (and
    ``pcb/temper.kicad_pro``'s netclass_assignments, corrected in #1279)
    both correctly declare them HV. A same-bucket pair is skipped entirely
    by ``generate_netclass_separated_constraints`` (``ca == cb: continue``),
    so this generated ZERO separation constraint for the exact pair that
    proved unroutable (J1 sits 4.0-5.3mm from K1's HV contacts against the
    12.6mm PD3 requirement). ``design_rules.get_rules_for_net()`` resolves
    both nets from the same ``TEMPER_NET_ASSIGNMENTS`` table
    ``pcb/temper.kicad_pro``'s netclass_assignments already agrees with,
    not from spelling.

    A ``get_rules_for_net()`` name of "Default" (its own fallback tier for
    any net with no per-net override/assignment and no pattern-cascade
    match) is normalized to "Signal" here -- ``netclass_rules.yaml``'s
    ``class_pairs`` table (e.g. ``HighVoltage-Signal: 6.0mm``) and this
    module's own pre-fix behaviour both assume "Signal" is the generic-LV
    catch-all bucket; "Default" is a distinct class_pairs key that no entry
    lists. Leaving unclassified LV nets as "Default" would silently drop
    their cross-class separation from every applicable ``class_pairs``
    override (6.0mm for HV-adjacent cases) down to
    ``max(HighVoltage.clearance, Default.clearance)`` = 2.0mm -- a
    loosening this fix must not introduce.

    Uses ``component.pins[i].net`` (Pin objects on the Component) rather
    than ``netlist.nets[].pins[].component`` (tuples in the Net parser
    output) — the Net.pins path is tuple data and lacks a ``.component``
    attribute.
    """
    pins = getattr(comp, "pins", [])
    if not pins:
        return None

    best_class = None
    best_rank: tuple[int, float] = (-1, -1.0)

    for pin in pins:
        net_name = getattr(pin, "net", "")
        if not net_name:
            continue
        rules = design_rules.get_rules_for_net(net_name)
        net_class = "Signal" if rules.name == "Default" else rules.name
        rank = (
            _SAFETY_CATEGORY_RANK.get(getattr(rules, "safety_category", None), 0),
            float(getattr(rules, "clearance", 0.0) or 0.0),
        )
        if rank > best_rank:
            best_rank = rank
            best_class = net_class

    return best_class


def generate_netclass_separated_constraints(
    netlist,
    components: list,
    design_rules: DesignRules,
    existing_constraints: list | None = None,
    touch_refs: set[str] | None = None,
) -> list[SeparatedConstraint]:
    """Generate SEPARATED constraints for cross-class component-net pairs.

    Only cross-class pairs (different net classes) get explicit constraints.
    Same-class pairs are handled by the existing global NoOverlap2D.

    Args:
        touch_refs: if given, restricts generation to pairs where at least
            one ref is in this set -- same "touches" semantics and the same
            reason as ``_encoder_core._generate_courtyard_separated_constraints``'s
            own ``touch_refs`` (see that docstring): a caller pinning most
            of the board via ``fixed_positions`` must not have a pair of
            two frozen, unrelated components that already violates THIS
            (typically larger, e.g. 6mm) cross-class clearance turn every
            solve spuriously infeasible. ``None`` (default): unrestricted,
            identical to prior behaviour for every existing caller.
    """
    constraints: list[SeparatedConstraint] = []

    # Build component -> net_class map
    comp_classes: dict[str, str] = {}
    for comp in components:
        nc = _resolve_component_net_class(comp, netlist, design_rules)
        if nc:
            comp_classes[getattr(comp, "ref", str(comp))] = nc

    if len(comp_classes) < 2:
        return constraints

    # Collect existing constraint pairs to skip. Only SeparatedConstraint
    # entries suppress the auto-generated netclass clearance for a pair --
    # matching on `isinstance(c, SeparatedConstraint)` (the idiom already
    # used by `_encoder_core.py` / `_encoder_solve.py` to discriminate
    # constraint types) rather than duck-typing on `a`/`b` attribute
    # presence. The prior duck-type test also matched AdjacentConstraint
    # (which has its own `a`/`b` fields), so an adjacency relation on a
    # pair could silently suppress that pair's netclass clearance
    # constraint -- an ADJACENT constraint asserts nothing about minimum
    # separation, so it must not stand in for one.
    existing_pairs: set[tuple[str, str]] = set()
    if existing_constraints:
        for c in existing_constraints:
            if isinstance(c, SeparatedConstraint):
                key = tuple(sorted([str(c.a), str(c.b)]))
                existing_pairs.add(key)

    comp_refs = list(comp_classes.keys())
    for i in range(len(comp_refs)):
        for j in range(i + 1, len(comp_refs)):
            ra, rb = comp_refs[i], comp_refs[j]
            if touch_refs is not None and ra not in touch_refs and rb not in touch_refs:
                continue
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
            class_pairs = getattr(design_rules, "class_pairs", {})
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
