"""Property-based tests for source-reference reconciliation invariants.

Rework of PR #498's reference-reconciliation intent (commits bab2a75aa +
1162370f2). The invariants the reconciliation machinery must uphold:

1. **Idempotence** — reconciling an already-reconciled constraint set with
   the same alias map applies no further aliases.
2. **Canonical completeness** — after reconciliation, no constraint operand
   is an alias-map source (chains are fully collapsed to their target).
3. **Monotone improvement** — when every alias target is live in the
   validation namespace, reconciliation never enlarges the unresolved set
   reported by the fail-closed validator (a legacy source that resolves
   disappears; a legacy source that does not is replaced by its non-live
   target, never by a new name).
4. **Loop canonicalization** — loop names and member refs are both
   canonicalized, and a second pass is a no-op.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.pcl.constraints import (
    AdjacentConstraint,
    ConstraintTier,
)
from temper_placer.placer.cp_sat._encoder_core import (
    reconcile_constraint_refs,
    reconcile_loop_components,
    validate_constraint_refs,
)

MAX_EXAMPLES = 200

_names = st.sampled_from(["Q1", "Q2", "C1", "C2", "U1", "U2", "R1", "R2", "L1", "L2"])
_loop_names = st.sampled_from(["loop_a", "loop_b", "loop_c"])


@st.composite
def _acyclic_alias_map(draw: st.DrawFn) -> dict[str, str]:
    """Alias maps the manifest loader can actually admit.

    Edges only ever point to a name with a strictly higher rank in a random
    order, so the map is acyclic by construction (no self-loops either).
    Cyclic maps are rejected by the encoder's cycle guard -- a separate,
    explicitly-tested path, not a space these invariants hold over.
    """
    names = draw(st.lists(_names, min_size=1, max_size=6, unique=True))
    order = draw(st.permutations(names))
    rank = {name: i for i, name in enumerate(order)}
    mapping: dict[str, str] = {}
    for source in names:
        higher = [n for n in names if rank[n] > rank[source]]
        if higher:
            mapping[source] = draw(st.sampled_from(higher))
    return mapping


_aliases = _acyclic_alias_map()


def _adjacent_pairs(names: list[str]) -> list[AdjacentConstraint]:
    pairs: list[AdjacentConstraint] = []
    for i, a in enumerate(names):
        b = names[(i + 1) % len(names)]
        pairs.append(
            AdjacentConstraint(
                a,
                b,
                max_distance_mm=5.0,
                tier=ConstraintTier.HARD,
                because="property-based invariant check",
            )
        )
    return pairs


def _operand_names(constraints: list) -> set[str]:
    names: set[str] = set()
    for c in constraints:
        for attr in ("a", "b"):
            val = getattr(c, attr, None)
            if isinstance(val, str):
                names.add(val)
    return names


@given(st.lists(_names, min_size=1, max_size=6), _aliases)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_reconcile_is_idempotent(names: list[str], aliases: dict[str, str]) -> None:
    constraints = _adjacent_pairs(names)

    first = reconcile_constraint_refs(constraints, aliases)
    second = reconcile_constraint_refs(list(first.constraints), aliases)

    assert second.aliases_applied == ()


@given(st.lists(_names, min_size=1, max_size=6), _aliases)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_reconcile_collapses_all_alias_sources(names: list[str], aliases: dict[str, str]) -> None:
    constraints = _adjacent_pairs(names)

    result = reconcile_constraint_refs(constraints, aliases)

    sources = set(aliases.keys())
    assert not (_operand_names(list(result.constraints)) & sources)


@given(st.lists(_names, min_size=1, max_size=6), _aliases)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_reconcile_never_enlarges_unresolved_set_when_targets_live(
    names: list[str], aliases: dict[str, str]
) -> None:
    constraints = _adjacent_pairs(names)

    namespace = set(names) | set(aliases.values())
    before = validate_constraint_refs(
        constraints,
        component_refs=namespace,
        zone_names=set(),
        loop_names=set(),
        on_unresolved="ignore",
    )
    before_unresolved = set().union(*before.values()) if before else set()

    result = reconcile_constraint_refs(constraints, aliases)
    after = validate_constraint_refs(
        list(result.constraints),
        component_refs=namespace,
        zone_names=set(),
        loop_names=set(),
        on_unresolved="ignore",
    )
    after_unresolved = set().union(*after.values()) if after else set()

    # A live target never introduces a new unresolved name; the legacy
    # source either resolves to it or is replaced by a name already absent.
    assert after_unresolved <= before_unresolved


@given(
    st.lists(_loop_names, min_size=1, max_size=4),
    st.lists(_names, min_size=0, max_size=6),
    _aliases,
)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_loop_reconciliation_is_canonical_and_idempotent(
    loop_names: list[str], members: list[str], aliases: dict[str, str]
) -> None:
    loop_components = {name: list(members) for name in loop_names}

    first = reconcile_loop_components(loop_components, aliases, None)
    second = reconcile_loop_components(first.loop_components, aliases, None)

    assert second.aliases_applied == ()
    sources = set(aliases.keys())
    for refs in first.loop_components.values():
        assert not (set(refs) & sources)


@given(st.lists(_names, min_size=1, max_size=6), _aliases)
@settings(max_examples=MAX_EXAMPLES, deadline=None)
def test_reconcile_preserves_constraint_ids(names: list[str], aliases: dict[str, str]) -> None:
    """Reconciliation copies constraints; their identity-bearing ids survive."""
    constraints = _adjacent_pairs(names)

    result = reconcile_constraint_refs(constraints, aliases)

    for original, reconciled in zip(constraints, result.constraints):
        assert reconciled.id == original.id
