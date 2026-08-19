"""Auto-generate SEPARATED constraints for cross-class component-net pairs.

CLASSIFIER FIXED (main, PR #1323, commit 22876b7b7 -- see
docs/evidence/2026-08-17-netclass-classifier-manifest-and-ieccreepagegate-
liveness.md): classification now runs through ``design_rules.
get_rules_for_net()`` -- the same manifest/kicad_pro-backed
``TEMPER_NET_ASSIGNMENTS`` classifier every other ``DesignRules`` consumer
already uses -- instead of ``core.net_classification.classify_net_type()``'s
plain net-NAME keyword heuristic, which misclassified K1's HV relay-contact
nets as "signal" (the same bucket J1's SELV RTD nets fall into), generating
ZERO separation constraint for the one pair that later proved unroutable.

ORCHESTRATION PORTED 2026-08-17 (placer constraint/clearance Rust-port
stage 2; see docs/evidence/2026-08-17-domain-clearance-netclass-rust-port-
stages-1-2.md, spec docs/evidence/2026-08-17-placer-constraint-rust-port-
spike.md, rebased onto #1323 -- see that same evidence doc's rebase
addendum). The O(n^2) cross-class pairing loop, per-component
severity-rank reduction, and class-pair-override lookup run in
``temper-orchestration``'s ``netclass.rs``
(``netclass_separated_constraints_py`` / ``netclass_resolve_component_class_py``).
This module keeps: the opaque-object marshalling (``comp.pins``/``pin.net``
getattr access), the live ``design_rules.get_rules_for_net()`` calls
(memoized per net name -- a real pyclass method call, not portable to Rust
without threading a live ``DesignRules`` reference across the FFI boundary,
which this stage does not scope), the ``SeparatedConstraint`` construction,
and ``_resolve_component_net_class``'s public name/signature (kept for
``tests/pcl/test_netclass_constraints.py``'s direct unit tests -- now a
thin wrapper over the same Rust reduction kernel the batch orchestration
calls, so the two paths cannot silently diverge).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import temper_orchestration as _to

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
# (both already-existing NetClassRules fields, not a new figure). Mirrored
# in netclass.rs's `safety_category_rank` -- differential-tested, see
# tests/pcl/test_netclass_constraints_rust_differential.py.
_SAFETY_CATEGORY_RANK: dict[str | None, int] = {"AC": 3, "HV": 2, "LV": 1, "iso": 1}


def _pin_class_infos(
    pins: list, design_rules: DesignRules, cache: dict[str, tuple[str, str | None, float]]
) -> list[tuple[str, str | None, float]]:
    """Resolve each pin's connected net through ``design_rules.
    get_rules_for_net()``, in pin order, skipping pins with no net name.

    ``cache`` memoizes by net name across an entire
    ``generate_netclass_separated_constraints`` call (``get_rules_for_net``
    is a pure function of net name, and a heavily-shared net like ``gnd``
    would otherwise be resolved once per pin -- 86+ times on the real
    board). Returns ``(net_class, safety_category, clearance)`` tuples --
    the Rust-side severity-rank reduction's exact input shape.

    A ``get_rules_for_net()`` name of "Default" (its own fallback tier for
    any net with no per-net override/assignment and no pattern-cascade
    match) is normalized to "Signal" here -- ``netclass_rules.yaml``'s
    ``class_pairs`` table (e.g. ``HighVoltage-Signal: 6.0mm``) assumes
    "Signal" is the generic-LV catch-all bucket; "Default" is a distinct
    class_pairs key that no entry lists. Leaving unclassified LV nets as
    "Default" would silently drop their cross-class separation from every
    applicable ``class_pairs`` override down to
    ``max(HighVoltage.clearance, Default.clearance)`` -- a loosening this
    must not introduce (see PR #1323's commit message).
    """
    infos: list[tuple[str, str | None, float]] = []
    for pin in pins:
        net_name = getattr(pin, "net", "")
        if not net_name:
            continue
        cached = cache.get(net_name)
        if cached is None:
            rules = design_rules.get_rules_for_net(net_name)
            net_class = "Signal" if rules.name == "Default" else rules.name
            category = getattr(rules, "safety_category", None)
            clearance = float(getattr(rules, "clearance", 0.0) or 0.0)
            cached = (net_class, category, clearance)
            cache[net_name] = cached
        infos.append(cached)
    return infos


def _resolve_component_net_class(comp, _netlist, design_rules: DesignRules) -> str | None:
    """Determine the net class for a component from its connected nets.

    Iterates ALL pins, classifies each connected net via
    ``design_rules.get_rules_for_net()`` -- the same authoritative,
    manifest/kicad_pro-backed classifier (``TEMPER_NET_ASSIGNMENTS``, per-net
    override -> explicit class -> ground/power/gate-HV/gate-SELV/high-current
    pattern cascade -> Default) every other consumer of ``DesignRules``
    already uses -- and returns the highest-severity net class across all
    pins (``_SAFETY_CATEGORY_RANK``, ties broken by clearance). Returns None
    only when the component has no pins at all (or none carry a net name).

    Uses ``component.pins[i].net`` (Pin objects on the Component) rather
    than ``netlist.nets[].pins[].component`` (tuples in the Net parser
    output) — the Net.pins path is tuple data and lacks a ``.component``
    attribute.

    Thin wrapper (2026-08-17 stage 2 port, rebased onto #1323's classifier
    fix): ``_pin_class_infos`` resolves each pin through the live
    ``design_rules`` (unavoidably Python -- a pyclass method call);
    the highest-severity reduction itself runs in ``netclass.rs``'s
    ``resolve_component_net_class`` — the identical kernel
    ``generate_netclass_separated_constraints`` below calls for every
    component, so a direct caller of this function and the batch
    orchestration cannot disagree.
    """
    pins = getattr(comp, "pins", [])
    if not pins:
        return None

    pin_infos = _pin_class_infos(pins, design_rules, {})
    if not pin_infos:
        return None

    return _to.netclass_resolve_component_class_py(pin_infos)


def _dru_resolved_pair_overrides(
    legacy_overrides: list[tuple[str, str, float | None, str]],
    class_clearance: dict[str, float],
) -> list[tuple[str, str, float | None, str]]:
    """Raise every cross-class pair figure onto the DRU-resolved requirement.

    **What was wrong.** The only separation family live on every production
    solve was this module's, and its figures came from
    ``netclass_rules.yaml``'s ``class_pairs`` table, whose own ``because``
    strings read *"UNSOURCED legacy 6.0mm (debunked 'Table 16 working
    isolation at 400V' citation; 6.0mm is in no recovered table)"*. That
    table caps at **6.0mm** for every HV-domain-to-LV pair, while
    ``pcb/temper.kicad_dru`` -- the surface kicad-cli actually grades the
    board against -- requires **12.6mm** creepage for the same pairs (PD3
    reinforced, IEC 60335-1 cl. 29.2.3 x Table 17 row iv, doubled; see
    ``scripts/generate_kicad_dru.py``'s ``HV_CREEPAGE_ENFORCED_MM`` and
    ``docs/evidence/2026-08-15-pd2-pd3-data-driven-decision.md``). The
    placer was therefore under-constrained by 6.6mm on every HV<->SELV
    pair it was asked to place, and no amount of routing effort can rescue
    a placement that was never required to be compliant.

    **Where the numbers come from.** ``configs/pair_clearance.generated.yaml``
    and ``configs/pair_creepage.generated.yaml``, both emitted by
    ``scripts/generate_kicad_dru.py`` by evaluating the rules it just wrote
    into ``pcb/temper.kicad_dru`` under KiCad's own last-matching-rule-wins
    precedence. They are what ``kicad-cli pcb drc`` enforces, not a
    hand-copied restatement of it -- the same reason
    ``router_v6.pair_clearance`` (this repo's only prior consumer of them,
    for the A* obstacle halos) chose them over ``class_pairs``, in that
    module's own words: *"not netclass_rules.yaml's class_pairs, whose own
    comments record that its 6.0mm HV figures are legacy, not
    primary-cited"*. Wiring the placer to the same two files makes the
    solver decide against the table it will be judged by, and closes the
    "one fact, two homes" gap between placement and DRC by construction
    rather than by anyone remembering to sync them.

    **Why the pair figure is ``max(clearance, creepage)``.** They are two
    different physical quantities graded by two separate kicad-cli
    constraints on the same pair, and a placement must satisfy both, so the
    binding requirement is the larger. This is the identical combination
    ``router_v6.pair_creepage``'s own module docstring prescribes for the
    obstacle map (*"the caller takes max(clearance, creepage)"*), reused
    rather than re-derived.

    **Why this RAISES rather than substitutes -- load-bearing.** For
    HV<->SELV pairs the DRU is far stricter (12.6mm vs 6.0mm) and it wins.
    But for a few SAME-DOMAIN pairs the DRU is deliberately *looser* than
    the legacy table: ``ACMains|HighVoltage`` resolves to 3.0mm clearance
    with no creepage rule at all, against ``class_pairs``' 6.0mm.
    ``netclass_rules.yaml``'s own comment explains that asymmetry -- its
    table "stays conservative for same-domain neighbours" while "the
    fab-authoritative KiCad DRC rule ... applies the reduced, cited 2.0mm
    same-side figure". Substituting the DRU figure wholesale would
    therefore *weaken* the placement model on those pairs, which is not a
    thing this change is entitled to do: lowering a separation figure is a
    separately-attributed safety decision, not a side effect of re-sourcing
    a different one. So the returned figure is
    ``max(legacy, dru_clearance, dru_creepage, per-class fallback)`` -- the
    result is >= today's on EVERY pair, and strictly greater on exactly the
    pairs the DRU grades harder.

    ``class_clearance`` is folded into the max for the same
    never-weaken reason: the kernel uses an override verbatim when one
    matches, so an override below ``max(class_a.clearance,
    class_b.clearance)`` would silently drop that pair *below* the figure
    it gets today with no override at all.

    Class-name translation: the generated tables are keyed by KiCad net-class
    names, this module's classes by ``netclass_rules.yaml`` names; the two
    differ only by ``GND`` -> ``Ground``, mapped through
    ``kicad_class_name`` rather than restated here.

    Returns the override list in the same ``(key_a, key_b, clearance,
    because)`` shape the kernel already consumes -- no Rust change is
    needed, because this only changes what the existing lookup table
    *contains*.
    """
    # Both tables live in router_v6 because the A* obstacle map was their
    # first consumer; neither is router-specific (they are DRU projections).
    # Direct submodule imports, permitted: neither module is listed in
    # .importlinter's `router-v6-public-interface-only` forbidden set.
    from temper_placer.router_v6.pair_clearance import (
        kicad_class_name,
        load_pair_clearance_table,
    )
    from temper_placer.router_v6.pair_creepage import load_pair_creepage_table

    clearance_table = load_pair_clearance_table()
    creepage_table = load_pair_creepage_table()

    # Index the legacy overrides by their unordered class pair so a DRU
    # figure can be merged onto an existing row instead of shadowing it.
    # The kernel scans this list in order and breaks on the FIRST key match,
    # so a duplicate key would make the later row dead.
    merged: dict[tuple[str, str], tuple[float | None, str]] = {}
    order: list[tuple[str, str]] = []
    for key_a, key_b, clearance, because in legacy_overrides:
        pair_key = (key_a, key_b) if key_a <= key_b else (key_b, key_a)
        if pair_key not in merged:
            order.append(pair_key)
        merged[pair_key] = (clearance, because)

    # Every unordered pair of declared classes, not just the ones the legacy
    # table happened to name. `class_pairs` names only a handful of this
    # board's live classes, so an HV<->LV pair it simply omits would keep
    # falling through to `max(class_a.clearance, class_b.clearance)` -- 2.0mm
    # for HighVoltage<->Signal -- while the DRU grades it at 12.6mm. The
    # omissions are exactly where the model was weakest.
    declared = sorted(class_clearance)
    for i, class_a in enumerate(declared):
        for class_b in declared[i + 1 :]:
            pair_key = (class_a, class_b)
            if pair_key not in merged:
                order.append(pair_key)
                merged[pair_key] = (None, "")

    out: list[tuple[str, str, float | None, str]] = []
    for pair_key in order:
        class_a, class_b = pair_key
        legacy_clearance, legacy_because = merged[pair_key]

        kicad_a = kicad_class_name(class_a)
        kicad_b = kicad_class_name(class_b)
        dru_clearance = clearance_table.required(kicad_a, kicad_b)
        dru_creepage = creepage_table.required(kicad_a, kicad_b)
        dru = max(dru_clearance, dru_creepage)

        # The figure the kernel would have used with NO override at all.
        # Folding it in is what makes this function incapable of lowering
        # any pair below today's behaviour.
        fallback = max(class_clearance.get(class_a, 0.0), class_clearance.get(class_b, 0.0))
        floor = max(legacy_clearance or 0.0, fallback)
        resolved = max(floor, dru)

        if resolved <= 0.0:
            continue

        if dru > floor:
            binding = "creepage" if dru_creepage >= dru_clearance else "clearance"
            because = (
                f"DRU-resolved {binding} {class_a}<->{class_b} at {resolved}mm "
                f"(pcb/temper.kicad_dru via scripts/generate_kicad_dru.py: "
                f"clearance {dru_clearance}mm, creepage {dru_creepage}mm; the "
                f"figure kicad-cli grades this pair by). Raised from the "
                f"placer-side {floor}mm"
                + (f" -- previously: {legacy_because}" if legacy_because else "")
            )
        elif legacy_because:
            because = legacy_because
        else:
            because = f"Netclass clearance {class_a}<->{class_b} at {resolved}mm"

        out.append((class_a, class_b, resolved, because))

    return out


def generate_netclass_separated_constraints(
    _netlist,
    components: list,
    design_rules: DesignRules,
    existing_constraints: list | None = None,
    touch_refs: set[str] | None = None,
    dru_resolved_pairs: bool = False,
) -> list[SeparatedConstraint]:
    """Generate SEPARATED constraints for cross-class component-net pairs.

    Only cross-class pairs (different net classes) get explicit constraints.
    Same-class pairs are handled by the existing global NoOverlap2D.

    Args:
        _netlist: unused (kept for public-API/call-site compatibility --
            every net class this function needs is read directly off each
            component's own pins via ``design_rules``).
        touch_refs: if given, restricts generation to pairs where at least
            one ref is in this set -- same "touches" semantics and the same
            reason as ``_encoder_core._generate_courtyard_separated_constraints``'s
            own ``touch_refs`` (see that docstring): a caller pinning most
            of the board via ``fixed_positions`` must not have a pair of
            two frozen, unrelated components that already violates THIS
            (typically larger, e.g. 6mm) cross-class clearance turn every
            solve spuriously infeasible. ``None`` (default): unrestricted,
            identical to prior behaviour for every existing caller.
        dru_resolved_pairs: when True, every cross-class pair figure is
            RAISED to the fab-authoritative ``pcb/temper.kicad_dru``
            requirement before encoding -- see
            :func:`_dru_resolved_pair_overrides` for the derivation, the
            source files, and the proof that it can only raise. Set by the
            production encoder (``_encoder_core.encode_constraints``).
            ``False`` (the default) preserves this function's pinned
            pre-Rust-port behaviour byte-for-byte, which is what the
            oracle differential asserts against; see the call site's own
            comment for why that default is load-bearing rather than
            timid.

    Marshalling (2026-08-17 stage 2 port, rebased onto #1323): this function
    resolves every component's pins through the live ``design_rules``
    (memoized per net name in ``pin_cache``, shared across the whole call --
    a heavily-shared net like ``gnd`` is otherwise re-resolved per pin), then
    walks the opaque ``existing_constraints``/``class_pairs`` objects into
    plain tuples/dicts and calls
    ``temper_orchestration.netclass_separated_constraints_py`` for the
    per-component severity-rank reduction, the O(n^2) pairing walk, and the
    class-pair lookup. Component iteration order is preserved exactly
    (load-bearing: both the emitted ``.id``'s ca/cb/ra/rb ordering and the
    pair-enumeration order depend on it, exactly like the pre-port Python
    ``dict`` insertion order it replaces).
    """
    pin_cache: dict[str, tuple[str, str | None, float]] = {}
    components_pin_infos: list[tuple[str, list[tuple[str, str | None, float]]]] = []
    for comp in components:
        pins = getattr(comp, "pins", [])
        if not pins:
            continue
        pin_infos = _pin_class_infos(pins, design_rules, pin_cache)
        if not pin_infos:
            continue
        components_pin_infos.append((getattr(comp, "ref", str(comp)), pin_infos))

    if len(components_pin_infos) < 2:
        return []

    # Existing SEPARATED-constraint pairs to skip. Only SeparatedConstraint
    # entries suppress the auto-generated netclass clearance for a pair --
    # matching on `isinstance(c, SeparatedConstraint)` (the idiom already
    # used by `_encoder_core.py` / `_encoder_solve.py` to discriminate
    # constraint types) rather than duck-typing on `a`/`b` attribute
    # presence. The prior duck-type test also matched AdjacentConstraint
    # (which has its own `a`/`b` fields), so an adjacency relation on a
    # pair could silently suppress that pair's netclass clearance
    # constraint -- an ADJACENT constraint asserts nothing about minimum
    # separation, so it must not stand in for one.
    existing_pairs: list[tuple[str, str]] = []
    if existing_constraints:
        for c in existing_constraints:
            if isinstance(c, SeparatedConstraint):
                existing_pairs.append((str(c.a), str(c.b)))

    # Flatten design_rules.class_pairs (an arbitrary Python dict from
    # netclass_loader) into (key_0, key_1, clearance_or_none, because)
    # tuples in RAW key order -- not re-sorted, matching the pre-port
    # `cp_key in class_pairs` exact-key lookup (see netclass.rs's own doc
    # comment on why re-sorting here would change behaviour).
    class_pairs = getattr(design_rules, "class_pairs", {}) or {}
    class_pair_overrides: list[tuple[str, str, float | None, str]] = []
    for key, value in class_pairs.items():
        if not (isinstance(key, tuple) and len(key) == 2):
            continue
        key_a, key_b = key
        if not (isinstance(key_a, str) and isinstance(key_b, str)):
            continue
        if not isinstance(value, dict):
            continue
        class_pair_overrides.append(
            (key_a, key_b, value.get("clearance"), str(value.get("because", "")))
        )

    # Per-class clearance via DesignRules: a pure function of class name
    # (net_name="" never matches a per-net override in practice), computed
    # once per class actually declared on this DesignRules -- covers every
    # class `_pin_class_infos` can ever resolve to, since every non-Default
    # resolution is itself sourced from `net_classes` and "Default" is
    # normalized to "Signal", always present in `net_classes` (see
    # `_pin_class_infos`'s docstring). Bounded (~13 entries on the real
    # board's netclass_rules.yaml), not per-pair as the pre-#1322 O(n^2)
    # loop computed it.
    class_clearance = {
        cls: design_rules.get_rules_for_net("", net_class=cls).clearance
        for cls in design_rules.net_classes
    }

    # DRU-RESOLVED PAIR FIGURES (2026-08-19), opt-in per call. Every override
    # built above is RAISED to the fab-authoritative figure before it reaches
    # the kernel; see `_dru_resolved_pair_overrides` for the full argument and
    # for why this is a strict raise (max) rather than a substitution.
    #
    # OPT-IN, and deliberately so. This function is pinned by a
    # Rust-vs-Python differential against `tests/pcl/
    # _netclass_constraints_py_oracle.py`, a VERBATIM pre-port snapshot that
    # has no such step and must not be re-pinned to acquire one (AGENTS.md:
    # re-pinning an existing oracle is a separate, evidence-first act). With
    # the default `dru_resolved_pairs=False` this function's behaviour is
    # byte-identical to that oracle, so the differential keeps asserting
    # exactly what it was written to assert -- that the Rust kernel did not
    # change the port's semantics. The production caller
    # (`_encoder_core.encode_constraints`) passes True, and
    # `TestDruResolvedPairs` pins THAT path's figures directly.
    if dru_resolved_pairs:
        class_pair_overrides = _dru_resolved_pair_overrides(
            class_pair_overrides,
            class_clearance,
        )

    # Deterministic iteration (the hash-order gate): sorted so
    # PYTHONHASHSEED cannot leak into the marshalled list. The Rust side
    # only tests set membership.
    touch_list = sorted(touch_refs) if touch_refs is not None else None

    out = _to.netclass_separated_constraints_py(
        components_pin_infos,
        class_clearance,
        class_pair_overrides,
        existing_pairs,
        touch_list,
    )

    constraints = [
        SeparatedConstraint(
            a=a,
            b=b,
            min_distance_mm=min_distance_mm,
            tier=ConstraintTier.HARD,
            because=because,
            id=id_,
        )
        for (a, b, min_distance_mm, because, id_) in out
    ]

    logger.info("Auto-generated %d netclass SEPARATED constraints", len(constraints))
    return constraints
