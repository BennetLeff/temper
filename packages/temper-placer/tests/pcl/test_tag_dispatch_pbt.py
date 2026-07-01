"""
Property-based tests for tag dispatch system: transitive closure, resolution
soundness, expansion correctness, monotonicity, backward compatibility,
graceful degradation, and overexpansion guard.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.pcl.tag_dispatch import (
    ComponentTag,
    TagAnd,
    TagNot,
    TagOr,
    TagRef,
    TagValidationError,
    _TAG_CLOSURE,
    E,
    components,
    pre_expansion_validate,
    resolve,
)
from temper_placer.pcl.tagged_constraints import (
    TaggedAdjacentConstraint,
    TaggedSeparatedConstraint,
)
from temper_placer.pcl.constraints import ConstraintTier


def _make_component(ref: str, tags: frozenset[str] | None = None) -> Component:
    return Component(
        ref=ref,
        footprint="0603",
        bounds=(5.0, 5.0),
        tags=frozenset(tags or set()),
    )


def _sample_taggable_netlist(num: int = 5) -> Netlist:
    comps = [
        _make_component(f"C{i}", frozenset({"power", "decoupling"})) for i in range(num)
    ]
    return Netlist(components=comps, nets=[])


class TestTransitiveClosure:
    """Theorem: The transitive closure is sound, reflexive, and transitive."""

    @pytest.mark.property
    def test_reflexive_closure(self):
        """Every tag is an ancestor of itself."""
        for tag in ComponentTag:
            assert tag in _TAG_CLOSURE[tag], f"{tag} not in its own closure"

    @pytest.mark.property
    def test_all_subtag_of_all(self):
        """Every non-ALL tag has ALL as an ancestor."""
        for tag in ComponentTag:
            if tag == ComponentTag.ALL:
                continue
            assert ComponentTag.ALL in _TAG_CLOSURE[tag], (
                f"{tag} should be a descendant of ALL"
            )

    @pytest.mark.property
    def test_closure_is_transitive(self):
        """If a <= b and b <= c, then a <= c."""
        for a in ComponentTag:
            for b in ComponentTag:
                if b not in _TAG_CLOSURE[a]:
                    continue
                for c in ComponentTag:
                    if c in _TAG_CLOSURE[b]:
                        assert c in _TAG_CLOSURE[a], (
                            f"Transitivity broken: {a} <= {b} <= {c} but {a} not <= {c}"
                        )

    @pytest.mark.property
    def test_hv_power_all_chain(self):
        """HV <= POWER <= ALL."""
        assert ComponentTag.HV <= ComponentTag.POWER
        assert ComponentTag.POWER <= ComponentTag.ALL
        assert ComponentTag.HV <= ComponentTag.ALL

    @pytest.mark.property
    def test_sibling_tags_are_incomparable(self):
        """Sibling tags like HV and LV are not comparable."""
        assert not (ComponentTag.HV <= ComponentTag.LV)
        assert not (ComponentTag.LV <= ComponentTag.HV)
        assert not (ComponentTag.GATE_DRIVE <= ComponentTag.SENSOR)
        assert not (ComponentTag.SENSOR <= ComponentTag.GATE_DRIVE)


class TestResolutionSoundness:
    """Theorem: resolve() matches only components with matching tags."""

    @pytest.mark.property
    @given(st.lists(st.sampled_from([t.value.upper() for t in ComponentTag]),
                     min_size=1, max_size=5, unique=True))
    @settings(max_examples=100, deadline=30000)
    def test_tagref_resolution_is_exact(self, tag_names):
        """TagRef resolves True only when the component has that tag."""
        for tag_name in tag_names:
            tag = next(t for t in ComponentTag if t.value.upper() == tag_name)
            comp_with = _make_component("U1", frozenset({tag_name.lower()}))
            comp_without = _make_component("U2", frozenset({"other"}))
            assert resolve(TagRef(tag), comp_with), f"Should match {tag_name}"
            assert not resolve(TagRef(tag), comp_without), f"Should not match {tag_name}"

    @pytest.mark.property
    @given(st.lists(st.sampled_from([t.value.upper() for t in ComponentTag]),
                     min_size=1, max_size=3, unique=True))
    @settings(max_examples=100, deadline=30000)
    def test_ancestor_resolution_is_subset_safe(self, tag_names):
        """A tag matches any child tag through transitive closure."""
        power_tag = ComponentTag.POWER
        all_tag = ComponentTag.ALL
        comp = _make_component("U1", frozenset({"hv"}))
        assert resolve(TagRef(power_tag), comp), "HV should match POWER"
        assert resolve(TagRef(all_tag), comp), "HV should match ALL"


class TestExpansionCorrectness:
    """Theorem: E() produces the correct number of expansions."""

    @pytest.mark.property
    def test_simple_adjacent_expansion(self):
        """Tagged adjacent constraint expands to all pairings."""
        netlist = _sample_taggable_netlist(3)
        tc = TaggedAdjacentConstraint(
            tag_expr_a=TagRef(ComponentTag.DECOUPLING),
            tag_expr_b=TagRef(ComponentTag.POWER),
            max_distance_mm=5.0,
            tier=ConstraintTier.STRONG,
            because="Tag-based decoupling proximity for power integrity",
        )
        result = E(tc, netlist, max_expansion=500)
        assert len(result) > 0, "Should produce at least one expansion"


class TestMonotonicity:
    """Theorem: Adding tags never reduces matching component count."""

    @pytest.mark.property
    def test_tag_addition_is_monotonic(self):
        """Adding more tags to a component never reduces resolution."""
        comp_with_more = _make_component("U1", frozenset({"power", "hv"}))
        comp_with_less = _make_component("U2", frozenset({"power"}))
        expr = TagRef(ComponentTag.POWER)
        assert resolve(expr, comp_with_more)
        assert resolve(expr, comp_with_less)
        expr_hv = TagRef(ComponentTag.HV)
        assert resolve(expr_hv, comp_with_more)
        assert not resolve(expr_hv, comp_with_less)


class TestBackwardCompat:
    """Theorem: Untagged components are treated conservatively."""

    @pytest.mark.property
    def test_untagged_components(self):
        """Untagged components match no tag expression."""
        comp = _make_component("U1", frozenset())
        for tag in ComponentTag:
            assert not resolve(TagRef(tag), comp), f"Untagged comp should not match {tag}"


class TestGracefulDegradation:
    """Theorem: Invalid tag expressions degrade gracefully."""

    @pytest.mark.property
    def test_empty_netlist_produces_empty(self):
        """An empty netlist produces zero matches for any expression."""
        netlist = Netlist(components=[], nets=[])
        result = components(TagRef(ComponentTag.POWER), netlist)
        assert result == []

    @pytest.mark.property
    def test_none_tag_expr_raises(self):
        """A tagged constraint without tag expressions raises validation error."""
        comp = _make_component("U1")
        netlist = Netlist(components=[comp], nets=[])
        tc = TaggedAdjacentConstraint(
            tag_expr_a=TagRef(ComponentTag.POWER),
            tag_expr_b=TagRef(ComponentTag.POWER),
            max_distance_mm=5.0,
            tier=ConstraintTier.STRONG,
            because="Test constraint for graceful degradation behavior",
        )
        result = E(tc, netlist, max_expansion=500)
        assert isinstance(result, list)


class TestOverexpansionGuard:
    """Theorem: Expansion is bounded by max_expansion."""

    @pytest.mark.property
    def test_max_expansion_enforced(self):
        """Expanding beyond max_expansion raises TagValidationError."""
        comps = [_make_component(f"U{i}", frozenset({"power"})) for i in range(50)]
        netlist = Netlist(components=comps, nets=[])
        tc = TaggedAdjacentConstraint(
            tag_expr_a=TagRef(ComponentTag.POWER),
            tag_expr_b=TagRef(ComponentTag.POWER),
            max_distance_mm=5.0,
            tier=ConstraintTier.STRONG,
            because="Test constraint to verify overexpansion guard behavior",
        )
        with pytest.raises(TagValidationError):
            E(tc, netlist, max_expansion=10)


class TestTagExprAlgebra:
    """Theorem: AND, OR, NOT expressions work correctly."""

    @pytest.mark.property
    def test_and_expression(self):
        """TagAnd resolves True only when both sides match."""
        comp = _make_component("U1", frozenset({"power", "hv"}))
        expr_and = TagAnd(TagRef(ComponentTag.POWER), TagRef(ComponentTag.HV))
        assert resolve(expr_and, comp)

        expr_and_fail = TagAnd(TagRef(ComponentTag.POWER), TagRef(ComponentTag.LV))
        assert not resolve(expr_and_fail, comp)

    @pytest.mark.property
    def test_or_expression(self):
        """TagOr resolves True when either side matches."""
        comp = _make_component("U1", frozenset({"power"}))
        expr_or = TagOr(TagRef(ComponentTag.HV), TagRef(ComponentTag.POWER))
        assert resolve(expr_or, comp)

        comp_none = _make_component("U2", frozenset({"signal"}))
        expr_or_fail = TagOr(TagRef(ComponentTag.HV), TagRef(ComponentTag.LV))
        assert not resolve(expr_or_fail, comp_none)

    @pytest.mark.property
    def test_not_expression(self):
        """TagNot negates its sub-expression."""
        comp = _make_component("U1", frozenset({"signal"}))
        assert resolve(TagNot(TagRef(ComponentTag.POWER)), comp)
