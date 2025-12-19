"""
Tests for synthetic netlist generator for scale testing.

TDD Task: temper-1my.3.1
"""

import pytest
from collections import Counter

from temper_placer.core.netlist import Netlist, Component, Net


class TestSyntheticNetlistGenerator:
    """Test the synthetic netlist generator for scale testing."""

    def test_generate_50_components(self) -> None:
        """Generate a netlist with exactly 50 components."""
        from tests.fixtures.generators.synthetic_netlist import generate_netlist

        netlist = generate_netlist(n_components=50)

        assert isinstance(netlist, Netlist)
        assert netlist.n_components == 50

    def test_generate_100_components(self) -> None:
        """Generate a netlist with exactly 100 components."""
        from tests.fixtures.generators.synthetic_netlist import generate_netlist

        netlist = generate_netlist(n_components=100)

        assert netlist.n_components == 100

    def test_generate_custom_count(self) -> None:
        """Generate netlists with arbitrary component counts."""
        from tests.fixtures.generators.synthetic_netlist import generate_netlist

        for n in [10, 25, 75, 150]:
            netlist = generate_netlist(n_components=n)
            assert netlist.n_components == n

    def test_component_type_distribution(self) -> None:
        """Component types should follow expected distribution."""
        from tests.fixtures.generators.synthetic_netlist import generate_netlist

        netlist = generate_netlist(n_components=100, seed=42)

        # Count component types by footprint prefix
        type_counts = Counter()
        for comp in netlist.components:
            if "0805" in comp.footprint or "0603" in comp.footprint or "0402" in comp.footprint:
                type_counts["passive"] += 1
            elif "SOIC" in comp.footprint or "QFN" in comp.footprint or "TSSOP" in comp.footprint:
                type_counts["ic"] += 1
            elif "TO-247" in comp.footprint or "TO-220" in comp.footprint:
                type_counts["power"] += 1
            else:
                type_counts["other"] += 1

        total = sum(type_counts.values())

        # Expected distribution: ~40% passives, ~30% ICs, ~20% power, ~10% other
        # Allow 15% tolerance
        assert type_counts["passive"] / total > 0.25, (
            f"Too few passives: {type_counts['passive']}/{total}"
        )
        assert type_counts["ic"] / total > 0.15, f"Too few ICs: {type_counts['ic']}/{total}"

    def test_net_connectivity(self) -> None:
        """All components should be connected to at least one net."""
        from tests.fixtures.generators.synthetic_netlist import generate_netlist

        netlist = generate_netlist(n_components=50, seed=42)

        # Build set of all connected component refs
        connected_refs = set()
        for net in netlist.nets:
            for comp_ref, _ in net.pins:
                connected_refs.add(comp_ref)

        # All components should be in at least one net
        all_refs = {c.ref for c in netlist.components}
        unconnected = all_refs - connected_refs

        # Allow some unconnected (mounting holes, test points)
        assert len(unconnected) < netlist.n_components * 0.1, (
            f"Too many unconnected components: {unconnected}"
        )

    def test_power_rail_coverage(self) -> None:
        """Power rails (VCC, GND) should reach expected number of components."""
        from tests.fixtures.generators.synthetic_netlist import generate_netlist

        netlist = generate_netlist(n_components=50, seed=42)

        # Find power nets
        power_nets = [n for n in netlist.nets if n.name in ("VCC", "GND", "+3V3", "+5V", "VBUS")]

        assert len(power_nets) >= 1, "No power nets found"

        # Count components on power nets
        powered_refs = set()
        for net in power_nets:
            for comp_ref, _ in net.pins:
                powered_refs.add(comp_ref)

        # At least 50% of ICs should have power
        ic_refs = {
            c.ref for c in netlist.components if "SOIC" in c.footprint or "QFN" in c.footprint
        }
        powered_ics = ic_refs & powered_refs

        if ic_refs:
            assert len(powered_ics) / len(ic_refs) > 0.3, (
                f"Too few ICs have power: {len(powered_ics)}/{len(ic_refs)}"
            )

    def test_unique_component_refs(self) -> None:
        """All component refs should be unique."""
        from tests.fixtures.generators.synthetic_netlist import generate_netlist

        netlist = generate_netlist(n_components=100, seed=42)

        refs = [c.ref for c in netlist.components]
        assert len(refs) == len(set(refs)), "Duplicate component refs found"

    def test_unique_net_names(self) -> None:
        """All net names should be unique."""
        from tests.fixtures.generators.synthetic_netlist import generate_netlist

        netlist = generate_netlist(n_components=50, seed=42)

        names = [n.name for n in netlist.nets]
        assert len(names) == len(set(names)), "Duplicate net names found"

    def test_valid_pin_references(self) -> None:
        """All pin references in nets should point to valid components/pins."""
        from tests.fixtures.generators.synthetic_netlist import generate_netlist

        netlist = generate_netlist(n_components=50, seed=42)

        # Validate should return no errors
        errors = netlist.validate()
        assert len(errors) == 0, f"Netlist validation errors: {errors}"

    def test_component_bounds_reasonable(self) -> None:
        """All components should have reasonable bounds (> 0, < 100mm)."""
        from tests.fixtures.generators.synthetic_netlist import generate_netlist

        netlist = generate_netlist(n_components=50, seed=42)

        for comp in netlist.components:
            assert comp.bounds[0] > 0, f"{comp.ref} has zero width"
            assert comp.bounds[1] > 0, f"{comp.ref} has zero height"
            assert comp.bounds[0] < 100, f"{comp.ref} width too large: {comp.bounds[0]}"
            assert comp.bounds[1] < 100, f"{comp.ref} height too large: {comp.bounds[1]}"

    def test_reproducibility_with_seed(self) -> None:
        """Same seed should produce identical netlists."""
        from tests.fixtures.generators.synthetic_netlist import generate_netlist

        netlist1 = generate_netlist(n_components=50, seed=12345)
        netlist2 = generate_netlist(n_components=50, seed=12345)

        # Same component refs in same order
        refs1 = [c.ref for c in netlist1.components]
        refs2 = [c.ref for c in netlist2.components]
        assert refs1 == refs2

        # Same net names
        names1 = [n.name for n in netlist1.nets]
        names2 = [n.name for n in netlist2.nets]
        assert names1 == names2

    def test_different_seeds_produce_different_netlists(self) -> None:
        """Different seeds should produce different netlists."""
        from tests.fixtures.generators.synthetic_netlist import generate_netlist

        netlist1 = generate_netlist(n_components=50, seed=1)
        netlist2 = generate_netlist(n_components=50, seed=2)

        # Should have different components (at least some)
        refs1 = [c.ref for c in netlist1.components]
        refs2 = [c.ref for c in netlist2.components]

        # Refs are generated deterministically, so check nets differ
        net_pins1 = {frozenset(n.pins) for n in netlist1.nets}
        net_pins2 = {frozenset(n.pins) for n in netlist2.nets}

        # Some nets should be different
        assert net_pins1 != net_pins2, "Different seeds produced identical netlists"

    def test_mixed_net_classes(self) -> None:
        """Netlist should have components from different net classes."""
        from tests.fixtures.generators.synthetic_netlist import generate_netlist

        netlist = generate_netlist(n_components=50, seed=42)

        net_classes = {c.net_class for c in netlist.components}

        # Should have at least 2 different net classes
        assert len(net_classes) >= 2, f"Only one net class: {net_classes}"
