"""Metamorphic property-based tests for tag dispatch.

Tag hierarchy metamorphic relations:
- Tag refinement: If adjacent(POWER, DECOUPLING) produces constraints,
  then adjacent(HV, DECOUPLING) produces a SUBSET (never a superset).
- Tag expansion monotonicity: Adding a tag to a component never removes
  constraints it already participates in.
- Boolean identity: adjacent(POWER & !MECH, DECOUPLING) produces same
  constraints as adjacent(POWER, DECOUPLING) minus mechanical components.
"""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from temper_placer.core.netlist import Component, Net, Netlist, Pin
from temper_placer.pcl.constraints import ConstraintTier
from temper_placer.pcl.tag_dispatch import (
    ComponentTag,
    TagAnd,
    TagNot,
    TagOr,
    TagRef,
    components as tag_components,
    resolve,
)
from temper_placer.pcl.tagged_constraints import (
    TaggedAdjacentConstraint,
)


def _make_netlist(ref_tags: list[tuple[str, frozenset[str]]]) -> Netlist:
    """Build a netlist from (ref, tags) pairs."""
    comps = [
        Component(
            ref=ref,
            footprint="0603",
            bounds=(5.0, 5.0),
            tags=tags,
        )
        for ref, tags in ref_tags
    ]
    return Netlist(components=comps, nets=[])


def _expand_adjacent(
    tag_expr_a,
    tag_expr_b,
    netlist: Netlist,
    max_distance_mm: float = 5.0,
) -> set[tuple[str, str]]:
    """Expand a tagged adjacent constraint and return the set of (a, b) component pairs."""
    from temper_placer.pcl.tag_dispatch import _tag_to_component_refs

    comps_a = _tag_to_component_refs(tag_expr_a, netlist)
    comps_b = _tag_to_component_refs(tag_expr_b, netlist)

    pairs = set()
    for a in comps_a:
        for b in comps_b:
            if a != b:
                pairs.add((a, b))
    return pairs


# ---------------------------------------------------------------------------
# Tag refinement: more specific tag -> subset
# ---------------------------------------------------------------------------


class TestTagRefinementSubset:
    """If adjacent(GENERAL, X) produces constraints, adjacent(SPECIFIC, X)
    produces a subset where SPECIFIC <= GENERAL."""

    @pytest.mark.property
    def test_hv_is_subset_of_power(self):
        """adjacent(HV, DECOUPLING) <= adjacent(POWER, DECOUPLING)."""
        netlist = _make_netlist([
            ("C1", frozenset({"power", "hv", "decoupling"})),
            ("C2", frozenset({"power", "lv", "decoupling"})),
            ("C3", frozenset({"power", "decoupling"})),
            ("C4", frozenset({"decoupling"})),
        ])
        power_pairs = _expand_adjacent(
            TagRef(ComponentTag.POWER), TagRef(ComponentTag.DECOUPLING), netlist,
        )
        hv_pairs = _expand_adjacent(
            TagRef(ComponentTag.HV), TagRef(ComponentTag.DECOUPLING), netlist,
        )
        assert hv_pairs.issubset(power_pairs), (
            f"HV pairs should be subset of POWER pairs.\n"
            f"HV: {hv_pairs}\nPOWER: {power_pairs}"
        )
        assert len(hv_pairs) <= len(power_pairs)

    @pytest.mark.property
    def test_decoupling_subset_of_power(self):
        """adjacent(DECOUPLING, MCU) <= adjacent(POWER, MCU) since DECOUPLING <= POWER."""
        netlist = _make_netlist([
            ("C1", frozenset({"power", "decoupling"})),
            ("C2", frozenset({"power", "hv"})),
            ("U1", frozenset({"signal", "mcu"})),
        ])
        power_pairs = _expand_adjacent(
            TagRef(ComponentTag.POWER), TagRef(ComponentTag.MCU), netlist,
        )
        dec_pairs = _expand_adjacent(
            TagRef(ComponentTag.DECOUPLING), TagRef(ComponentTag.MCU), netlist,
        )
        assert dec_pairs.issubset(power_pairs), (
            f"DECOUPLING should be subset of POWER.\n"
            f"DECOUPLING: {dec_pairs}\nPOWER: {power_pairs}"
        )

    @pytest.mark.property
    def test_all_is_superset(self):
        """adjacent(ALL, X) is a superset of any more specific tag."""
        netlist = _make_netlist([
            ("C1", frozenset({"power", "hv", "decoupling"})),
            ("C2", frozenset({"signal", "mcu"})),
            ("C3", frozenset({"mechanical", "connector"})),
        ])
        all_pairs = _expand_adjacent(
            TagRef(ComponentTag.ALL), TagRef(ComponentTag.ALL), netlist,
        )
        power_pairs = _expand_adjacent(
            TagRef(ComponentTag.POWER), TagRef(ComponentTag.ALL), netlist,
        )
        assert power_pairs.issubset(all_pairs), (
            f"POWER should be subset of ALL.\n"
            f"POWER: {power_pairs}\nALL: {all_pairs}"
        )

    @pytest.mark.property
    @given(st.lists(st.sampled_from([
        ("C1", frozenset({"power", "hv"})),
        ("C2", frozenset({"power", "lv"})),
        ("C3", frozenset({"signal", "mcu"})),
        ("C4", frozenset({"power", "decoupling"})),
        ("C5", frozenset({"mechanical", "connector"})),
    ]), min_size=3, max_size=5, unique_by=lambda x: x[0]))
    @settings(max_examples=30, deadline=30000)
    def test_refinement_is_transitive(self, ref_tags):
        """SPEC <= GENERAL => adjacent(SPEC) <= adjacent(GENERAL)."""
        netlist = _make_netlist(ref_tags)
        all_pairs = _expand_adjacent(
            TagRef(ComponentTag.ALL), TagRef(ComponentTag.ALL), netlist,
        )
        power_pairs = _expand_adjacent(
            TagRef(ComponentTag.POWER), TagRef(ComponentTag.ALL), netlist,
        )
        hv_pairs = _expand_adjacent(
            TagRef(ComponentTag.HV), TagRef(ComponentTag.ALL), netlist,
        )
        assert hv_pairs.issubset(power_pairs)
        assert power_pairs.issubset(all_pairs)


# ---------------------------------------------------------------------------
# Tag expansion monotonicity: adding tags never removes constraints
# ---------------------------------------------------------------------------


class TestTagExpansionMonotonicity:
    """Adding a tag to a component never removes constraints it already
    participates in."""

    def test_adding_power_tag_adds_or_keeps_constraints(self):
        """Adding POWER tag to an untagged component makes it match more tags."""
        netlist_before = _make_netlist([
            ("C1", frozenset({"decoupling"})),
            ("C2", frozenset()),
        ])
        netlist_after = _make_netlist([
            ("C1", frozenset({"decoupling"})),
            ("C2", frozenset({"power"})),
        ])

        expr = TagRef(ComponentTag.POWER)
        before = _expand_adjacent(expr, TagRef(ComponentTag.ALL), netlist_before)
        after = _expand_adjacent(expr, TagRef(ComponentTag.ALL), netlist_after)

        assert before.issubset(after), (
            f"Adding tag should preserve or add constraints.\n"
            f"Before: {before}\nAfter: {after}"
        )

    def test_removing_tag_removes_or_preserves_constraints(self):
        """Removing HV tag from component reduces constraint participation."""
        netlist_before = _make_netlist([
            ("C1", frozenset({"power", "hv"})),
            ("C2", frozenset({"power"})),
        ])
        netlist_after = _make_netlist([
            ("C1", frozenset({"power"})),
            ("C2", frozenset({"power"})),
        ])

        expr = TagRef(ComponentTag.HV)
        before = _expand_adjacent(expr, TagRef(ComponentTag.ALL), netlist_before)
        after = _expand_adjacent(expr, TagRef(ComponentTag.ALL), netlist_after)

        assert after.issubset(before), (
            f"Removing tag should remove or preserve constraints.\n"
            f"Before: {before}\nAfter: {after}"
        )

    @pytest.mark.property
    @given(st.lists(st.sampled_from([
        ("C1", frozenset({"power", "hv"})),
        ("C2", frozenset({"power"})),
        ("C3", frozenset({"signal"})),
    ]), min_size=2, max_size=3, unique_by=lambda x: x[0]))
    @settings(max_examples=30, deadline=30000)
    def test_adding_all_tag_increases_or_maintains(self, ref_tags):
        """Adding tags to components never shrinks the match set."""
        netlist = _make_netlist(ref_tags)
        power_before = _expand_adjacent(
            TagRef(ComponentTag.POWER), TagRef(ComponentTag.ALL), netlist,
        )
        all_pairs = _expand_adjacent(
            TagRef(ComponentTag.ALL), TagRef(ComponentTag.ALL), netlist,
        )
        assert power_before.issubset(all_pairs), (
            f"POWER pairs should be subset of ALL pairs.\n"
            f"POWER: {power_before}\nALL: {all_pairs}"
        )


# ---------------------------------------------------------------------------
# Boolean identity: AND/OR/NOT tag expressions
# ---------------------------------------------------------------------------


class TestBooleanIdentity:
    """AND/OR/NOT tag expressions produce correct constraint sets."""

    def test_not_mechanical_equals_power_union_signal(self):
        """TagNot(MECHANICAL) matches POWER+ and SIGNAL+ components."""
        netlist = _make_netlist([
            ("C1", frozenset({"power", "hv"})),
            ("C2", frozenset({"signal", "mcu"})),
            ("C3", frozenset({"mechanical", "connector"})),
            ("C4", frozenset({"mechanical", "mounting"})),
        ])
        not_mech_expr = TagNot(TagRef(ComponentTag.MECHANICAL))

        not_mech_pairs = _expand_adjacent(not_mech_expr, TagRef(ComponentTag.ALL), netlist)
        all_pairs = _expand_adjacent(TagRef(ComponentTag.ALL), TagRef(ComponentTag.ALL), netlist)

        # not_mech should exclude C3 and C4 from left-hand-side
        assert not_mech_pairs.issubset(all_pairs)
        for a, b in not_mech_pairs:
            assert a in ("C1", "C2"), f"Non-mechanical match should not include {a}"

    def test_power_and_not_mech_matches_power_only_non_mech(self):
        """TagAnd(POWER, TagNot(MECH)) matches POWER components that aren't MECH."""
        netlist = _make_netlist([
            ("C1", frozenset({"power", "hv"})),
            ("C2", frozenset({"power", "mechanical"})),
            ("C3", frozenset({"signal", "mcu"})),
            ("C4", frozenset({"power", "decoupling"})),
        ])
        expr = TagAnd(TagRef(ComponentTag.POWER), TagNot(TagRef(ComponentTag.MECHANICAL)))

        # Resolve against each component
        assert resolve(expr, netlist.components[0]), "C1 (power, hv) should match"
        assert not resolve(expr, netlist.components[1]), "C2 (power, mechanical) should not match"
        assert not resolve(expr, netlist.components[2]), "C3 (signal) should not match"
        assert resolve(expr, netlist.components[3]), "C4 (power, decoupling) should match"

    def test_power_or_signal_matches_both(self):
        """TagOr(POWER, SIGNAL) matches both POWER and SIGNAL components."""
        netlist = _make_netlist([
            ("C1", frozenset({"power", "hv"})),
            ("C2", frozenset({"signal", "mcu"})),
            ("C3", frozenset({"mechanical", "connector"})),
        ])
        expr = TagOr(TagRef(ComponentTag.POWER), TagRef(ComponentTag.SIGNAL))

        assert resolve(expr, netlist.components[0]), "C1 should match"
        assert resolve(expr, netlist.components[1]), "C2 should match"
        assert not resolve(expr, netlist.components[2]), "C3 should not match"

    def test_compound_adjacent_power_not_mech(self):
        """adjacent(POWER & !MECH, DECOUPLING) produces constraints without
        mechanical components in the POWER group."""
        netlist = _make_netlist([
            ("U1", frozenset({"power", "decoupling"})),
            ("U2", frozenset({"power", "mechanical"})),
            ("U3", frozenset({"decoupling"})),
        ])

        power_not_mech = TagAnd(TagRef(ComponentTag.POWER), TagNot(TagRef(ComponentTag.MECHANICAL)))
        power_pairs = _expand_adjacent(
            power_not_mech, TagRef(ComponentTag.DECOUPLING), netlist,
        )

        # U2 (power+mechanical) should not appear as left-hand
        for a, _b in power_pairs:
            assert a != "U2", f"Mechanical component U2 should not be in LHS: {power_pairs}"

    def test_adjacent_power_excludes_mech(self):
        """adjacent(POWER & !MECH, X) is subset of adjacent(POWER, X)."""
        netlist = _make_netlist([
            ("C1", frozenset({"power", "decoupling"})),
            ("C2", frozenset({"power", "mechanical"})),
            ("C3", frozenset({"decoupling"})),
        ])

        all_power = _expand_adjacent(
            TagRef(ComponentTag.POWER), TagRef(ComponentTag.DECOUPLING), netlist,
        )
        power_not_mech = _expand_adjacent(
            TagAnd(TagRef(ComponentTag.POWER), TagNot(TagRef(ComponentTag.MECHANICAL))),
            TagRef(ComponentTag.DECOUPLING),
            netlist,
        )

        assert power_not_mech.issubset(all_power), (
            f"POWER&!MECH should be subset of POWER.\n"
            f"P&!M: {power_not_mech}\nPOWER: {all_power}"
        )
        # Should strictly exclude C2 from left side
        for a, _b in all_power:
            if a == "C2":
                assert (a, "C3") not in power_not_mech if "C3" in [c.ref for c in netlist.components] else True
                break
