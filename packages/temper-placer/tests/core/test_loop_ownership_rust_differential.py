"""
Differential oracle tests: LoopMembership, ComponentLoopInfo, LoopOwnershipMap.

This test pins the pre-migration Python dataclass implementations VERBATIM
as oracle blocks and compares the Rust pyclasses (imported via the delegation
shims) against them bit-identically.

G1 (TDD): This file is committed BEFORE any Rust pyclass code. Git history
must show the test predating the pyclass implementations. In identity mode
(before Rust), the shim imports ARE the Python dataclasses and the test
compares them against the oracles -- the test is trivially green when the
implementation still lives in Python.

Verification unit (per D5/G4 cluster rule): LoopMembership + ComponentLoopInfo
+ LoopOwnershipMap are one unit behind this shared oracle + corpus.

Module-to-property map:
  LoopMembership:      P1 (repr round-trip), MR1 (default identity)
  ComponentLoopInfo:   P2 (repr with memberships), P3 (critical-loop heuristic),
                       MR2 (empty memberships identity)
  LoopOwnershipMap:    P4 (shared-loop query), P5 (component info lookup),
                       MR3 (get_loop_components identity)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

# ---------------------------------------------------------------------------
# Oracle block -- verbatim copy of the three dataclasses from
# `temper_placer/core/loop_ownership.py` (origin/main, pre-migration).
# DO NOT EDIT -- these are the reference implementations, name-suffixed _Oracle
# to avoid clashing with the shim imports.
# ---------------------------------------------------------------------------


@dataclass
class _OracleLoopMembership:
    loop_name: str
    role: str
    pins_in_loop: list[str] = field(default_factory=list)


@dataclass
class _OracleComponentLoopInfo:
    component_ref: str
    memberships: list[_OracleLoopMembership] = field(default_factory=list)

    @property
    def loop_names(self) -> list[str]:
        return [m.loop_name for m in self.memberships]

    @property
    def is_in_critical_loop(self) -> bool:
        return any(
            m.loop_name.startswith("commutation")
            or m.loop_name.startswith("gate_drive")
            or "commutation" in m.loop_name.lower()
            or "gate_drive" in m.loop_name.lower()
            for m in self.memberships
        )

    def get_priority_weight(self, loop_collection) -> float:
        from temper_placer.core.loop import LoopPriority

        max_weight = 0.0
        for membership in self.memberships:
            loop = loop_collection.get_loop(membership.loop_name)
            if loop:
                weight = {
                    LoopPriority.CRITICAL: 1.0,
                    LoopPriority.HIGH: 0.7,
                    LoopPriority.MEDIUM: 0.4,
                    LoopPriority.LOW: 0.1,
                }.get(loop.priority, 0.0)
                max_weight = max(max_weight, weight)
        return max_weight


@dataclass
class _OracleLoopOwnershipMap:
    component_to_loops: dict[str, _OracleComponentLoopInfo] = field(default_factory=dict)
    loop_to_components: dict[str, list[str]] = field(default_factory=dict)

    def get_component_info(self, ref: str) -> _OracleComponentLoopInfo | None:
        return self.component_to_loops.get(ref)

    def get_loop_components(self, loop_name: str) -> list[str]:
        return self.loop_to_components.get(loop_name, [])

    def get_shared_loops(self, ref_a: str, ref_b: str) -> list[str]:
        info_a = self.component_to_loops.get(ref_a)
        info_b = self.component_to_loops.get(ref_b)
        if not info_a or not info_b:
            return []
        loops_a = set(info_a.loop_names)
        loops_b = set(info_b.loop_names)
        return list(loops_a & loops_b)

    def components_share_loop(
        self, ref_a: str, ref_b: str, _loop_collection=None
    ) -> bool:
        return len(self.get_shared_loops(ref_a, ref_b)) > 0

    def components_share_critical_loop(
        self, ref_a: str, ref_b: str, loop_collection
    ) -> bool:
        from temper_placer.core.loop import LoopPriority

        shared = self.get_shared_loops(ref_a, ref_b)
        for loop_name in shared:
            loop = loop_collection.get_loop(loop_name)
            if loop and loop.priority == LoopPriority.CRITICAL:
                return True
        return False


# ---------------------------------------------------------------------------
# Shim imports -- these ARE the Python dataclasses in identity mode (pre-Rust),
# and become the Rust pyclasses after migration. The test compares shim vs
# oracle; in identity mode the comparison is trivially green.
# ---------------------------------------------------------------------------

from temper_placer.core.loop_ownership import (
    ComponentLoopInfo,
    LoopMembership,
    LoopOwnershipMap,
)


# ============================================================================
# Canonicalization helpers
# ============================================================================


def _canon_membership(m: LoopMembership | _OracleLoopMembership):
    """Extract canonical fields from a LoopMembership (oracle or shim)."""
    return (m.loop_name, m.role, tuple(m.pins_in_loop))


def _canon_component_info(info: ComponentLoopInfo | _OracleComponentLoopInfo):
    """Extract canonical fields from a ComponentLoopInfo (oracle or shim)."""
    return (
        info.component_ref,
        tuple(_canon_membership(m) for m in info.memberships),
    )


def _canon_ownership_map(ownership: LoopOwnershipMap | _OracleLoopOwnershipMap):
    """Extract canonical fields from a LoopOwnershipMap (oracle or shim)."""
    comp_keys = sorted(ownership.component_to_loops.keys())
    comp_vals = tuple(
        (k, _canon_component_info(ownership.component_to_loops[k]))
        for k in comp_keys
    )
    loop_keys = sorted(ownership.loop_to_components.keys())
    loop_vals = tuple(
        (k, tuple(sorted(ownership.loop_to_components[k])))
        for k in loop_keys
    )
    return (comp_vals, loop_vals)


# ============================================================================
# LoopMembership tests
# ============================================================================


class TestLoopMembershipDifferential:
    """Compare Rust LoopMembership pyclass against the oracle dataclass."""

    def test_create_and_access_fields(self):
        oracle = _OracleLoopMembership(
            loop_name="commutation",
            role="switch",
            pins_in_loop=["COLLECTOR", "EMITTER"],
        )
        shim = LoopMembership(
            loop_name="commutation",
            role="switch",
            pins_in_loop=["COLLECTOR", "EMITTER"],
        )
        assert _canon_membership(shim) == _canon_membership(oracle)

    def test_default_pins_empty(self):
        oracle = _OracleLoopMembership(loop_name="test", role="switch")
        shim = LoopMembership(loop_name="test", role="switch")
        assert _canon_membership(shim) == _canon_membership(oracle)

    def test_repr_identical(self):
        oracle = _OracleLoopMembership(
            loop_name="commutation",
            role="switch",
            pins_in_loop=["COLLECTOR", "EMITTER"],
        )
        shim = LoopMembership(
            loop_name="commutation",
            role="switch",
            pins_in_loop=["COLLECTOR", "EMITTER"],
        )
        # Normalize class name: oracle uses _OracleLoopMembership, shim uses
        # LoopMembership (or the Rust pyclass class name after migration).
        expected = repr(oracle).replace(
            "_OracleLoopMembership", shim.__class__.__name__
        )
        assert repr(shim) == expected

    def test_repr_default_pins(self):
        oracle = _OracleLoopMembership(loop_name="test", role="switch")
        shim = LoopMembership(loop_name="test", role="switch")
        expected = repr(oracle).replace(
            "_OracleLoopMembership", shim.__class__.__name__
        )
        assert repr(shim) == expected

    def test_eq_same_values(self):
        m1 = LoopMembership(loop_name="loop1", role="switch")
        m2 = LoopMembership(loop_name="loop1", role="switch")
        assert m1 == m2

    def test_eq_different(self):
        m1 = LoopMembership(loop_name="loop1", role="switch")
        m2 = LoopMembership(loop_name="loop2", role="capacitor")
        assert m1 != m2

    def test_hash_raises_typeerror(self):
        """eq=True, frozen=False -> __hash__ is None."""
        m = LoopMembership(loop_name="test", role="switch")
        with pytest.raises(TypeError, match="unhashable"):
            hash(m)


# ============================================================================
# ComponentLoopInfo tests
# ============================================================================


class TestComponentLoopInfoDifferential:
    """Compare Rust ComponentLoopInfo pyclass against the oracle dataclass."""

    def test_create_and_access_fields(self):
        m = _OracleLoopMembership("commutation", "switch")
        oracle = _OracleComponentLoopInfo("Q1", [m])
        shim = ComponentLoopInfo("Q1", [LoopMembership("commutation", "switch")])
        assert _canon_component_info(shim) == _canon_component_info(oracle)

    def test_loop_names_property(self):
        shim = ComponentLoopInfo(
            component_ref="Q1",
            memberships=[
                LoopMembership("commutation", "switch"),
                LoopMembership("gate_drive_high", "switch"),
            ],
        )
        names = shim.loop_names
        assert len(names) == 2
        assert "commutation" in names
        assert "gate_drive_high" in names

    def test_is_in_critical_loop_heuristic(self):
        # Component in commutation loop
        info1 = ComponentLoopInfo(
            "Q1", [LoopMembership("commutation", "switch")]
        )
        assert info1.is_in_critical_loop

        # Component in gate_drive loop
        info2 = ComponentLoopInfo(
            "Q1", [LoopMembership("gate_drive_high", "switch")]
        )
        assert info2.is_in_critical_loop

        # Component not in critical loop
        info3 = ComponentLoopInfo(
            "C1", [LoopMembership("decoupling", "capacitor")]
        )
        assert not info3.is_in_critical_loop

    def test_get_priority_weight_critical(self):
        """Should return 1.0 for CRITICAL loop."""
        from temper_placer.core.loop import Loop, LoopCollection, LoopPriority, LoopType

        loop = Loop(
            name="commutation",
            loop_type=LoopType.COMMUTATION,
            description="Main commutation loop",
            components=["Q1", "Q2"],
            priority=LoopPriority.CRITICAL,
        )
        lc = LoopCollection(loops=[loop])

        info = ComponentLoopInfo(
            "Q1", [LoopMembership("commutation", "switch")]
        )
        assert info.get_priority_weight(lc) == 1.0

    def test_get_priority_weight_high(self):
        """Should return 0.7 for HIGH loop."""
        from temper_placer.core.loop import Loop, LoopCollection, LoopPriority, LoopType

        loop = Loop(
            name="bootstrap",
            loop_type=LoopType.BOOTSTRAP,
            description="Bootstrap",
            components=["D_BOOT", "C_BOOT"],
            priority=LoopPriority.HIGH,
        )
        lc = LoopCollection(loops=[loop])

        info = ComponentLoopInfo(
            "C_BOOT", [LoopMembership("bootstrap", "bootstrap_capacitor")]
        )
        assert info.get_priority_weight(lc) == 0.7

    def test_get_priority_weight_empty(self):
        """Should return 0.0 for component with no memberships."""
        from temper_placer.core.loop import LoopCollection

        info = ComponentLoopInfo("J1", [])
        lc = LoopCollection(loops=[])
        assert info.get_priority_weight(lc) == 0.0

    def test_repr_identical(self):
        m1 = LoopMembership("commutation", "switch", ["COLLECTOR", "EMITTER"])
        oracle = _OracleComponentLoopInfo("Q1", [
            _OracleLoopMembership("commutation", "switch", ["COLLECTOR", "EMITTER"])
        ])
        shim = ComponentLoopInfo("Q1", [m1])
        # Normalize nested class names: oracle uses _Oracle* prefixes.
        expected = repr(oracle).replace(
            "_OracleComponentLoopInfo", shim.__class__.__name__
        ).replace(
            "_OracleLoopMembership", LoopMembership.__name__
        )
        assert repr(shim) == expected

    def test_eq_same_values(self):
        info1 = ComponentLoopInfo("Q1", [LoopMembership("commutation", "switch")])
        info2 = ComponentLoopInfo("Q1", [LoopMembership("commutation", "switch")])
        assert info1 == info2

    def test_eq_different(self):
        info1 = ComponentLoopInfo("Q1", [LoopMembership("commutation", "switch")])
        info2 = ComponentLoopInfo("Q2", [LoopMembership("commutation", "switch")])
        assert info1 != info2

    def test_hash_raises_typeerror(self):
        info = ComponentLoopInfo("Q1", [LoopMembership("commutation", "switch")])
        with pytest.raises(TypeError, match="unhashable"):
            hash(info)


# ============================================================================
# LoopOwnershipMap tests
# ============================================================================


class TestLoopOwnershipMapDifferential:
    """Compare Rust LoopOwnershipMap pyclass against the oracle dataclass."""

    def test_create_empty_map(self):
        oracle = _OracleLoopOwnershipMap()
        shim = LoopOwnershipMap()
        assert _canon_ownership_map(shim) == _canon_ownership_map(oracle)

    def test_get_component_info_found(self):
        info = ComponentLoopInfo("Q1", [LoopMembership("loop1", "switch")])
        ownership = LoopOwnershipMap(component_to_loops={"Q1": info})
        result = ownership.get_component_info("Q1")
        assert result is not None
        assert result.component_ref == "Q1"

    def test_get_component_info_not_found(self):
        ownership = LoopOwnershipMap()
        result = ownership.get_component_info("UNKNOWN")
        assert result is None

    def test_get_loop_components_found(self):
        ownership = LoopOwnershipMap(
            loop_to_components={"commutation": ["Q1", "Q2", "C_BUS"]}
        )
        components = ownership.get_loop_components("commutation")
        assert len(components) == 3
        assert "Q1" in components
        assert "Q2" in components
        assert "C_BUS" in components

    def test_get_loop_components_not_found(self):
        ownership = LoopOwnershipMap()
        components = ownership.get_loop_components("UNKNOWN")
        assert components == []

    def test_get_shared_loops_with_overlap(self):
        ownership = LoopOwnershipMap(
            component_to_loops={
                "Q1": ComponentLoopInfo(
                    "Q1",
                    [
                        LoopMembership("commutation", "switch"),
                        LoopMembership("gate_drive_high", "switch"),
                    ],
                ),
                "Q2": ComponentLoopInfo(
                    "Q2",
                    [
                        LoopMembership("commutation", "switch"),
                        LoopMembership("gate_drive_low", "switch"),
                    ],
                ),
            }
        )
        shared = ownership.get_shared_loops("Q1", "Q2")
        assert len(shared) == 1
        assert "commutation" in shared

    def test_get_shared_loops_no_overlap(self):
        ownership = LoopOwnershipMap(
            component_to_loops={
                "Q1": ComponentLoopInfo("Q1", [LoopMembership("loop1", "switch")]),
                "C1": ComponentLoopInfo("C1", [LoopMembership("loop2", "capacitor")]),
            }
        )
        shared = ownership.get_shared_loops("Q1", "C1")
        assert shared == []

    def test_get_shared_loops_component_not_found(self):
        ownership = LoopOwnershipMap()
        shared = ownership.get_shared_loops("Q1", "Q2")
        assert shared == []

    def test_components_share_loop_true(self):
        ownership = LoopOwnershipMap(
            component_to_loops={
                "Q1": ComponentLoopInfo("Q1", [LoopMembership("commutation", "switch")]),
                "Q2": ComponentLoopInfo("Q2", [LoopMembership("commutation", "switch")]),
            }
        )
        assert ownership.components_share_loop("Q1", "Q2")
        assert not ownership.components_share_loop("Q1", "C1")

    def test_components_share_critical_loop(self):
        from temper_placer.core.loop import Loop, LoopCollection, LoopPriority, LoopType

        commutation = Loop(
            name="commutation",
            loop_type=LoopType.COMMUTATION,
            description="Main commutation",
            components=["Q1", "Q2"],
            priority=LoopPriority.CRITICAL,
        )
        bootstrap = Loop(
            name="bootstrap",
            loop_type=LoopType.BOOTSTRAP,
            description="Bootstrap",
            components=["C_BOOT"],
            priority=LoopPriority.HIGH,
        )
        lc = LoopCollection(loops=[commutation, bootstrap])

        ownership = LoopOwnershipMap(
            component_to_loops={
                "Q1": ComponentLoopInfo("Q1", [LoopMembership("commutation", "switch")]),
                "Q2": ComponentLoopInfo("Q2", [LoopMembership("commutation", "switch")]),
                "C_BOOT": ComponentLoopInfo("C_BOOT", [LoopMembership("bootstrap", "capacitor")]),
            }
        )

        # Q1 and Q2 share commutation (CRITICAL)
        assert ownership.components_share_critical_loop("Q1", "Q2", lc)
        # Q1 and C_BOOT don't share any loop
        assert not ownership.components_share_critical_loop("Q1", "C_BOOT", lc)

    def test_repr_identical(self):
        oracle = _OracleLoopOwnershipMap(
            component_to_loops={
                "Q1": _OracleComponentLoopInfo(
                    "Q1",
                    [_OracleLoopMembership("commutation", "switch", ["COLLECTOR", "EMITTER"])],
                ),
            },
            loop_to_components={"commutation": ["Q1"]},
        )
        shim = LoopOwnershipMap(
            component_to_loops={
                "Q1": ComponentLoopInfo(
                    "Q1",
                    [LoopMembership("commutation", "switch", ["COLLECTOR", "EMITTER"])],
                ),
            },
            loop_to_components={"commutation": ["Q1"]},
        )
        # Normalize nested class names: oracle uses _Oracle* prefixes.
        expected = repr(oracle).replace(
            "_OracleLoopOwnershipMap", shim.__class__.__name__
        ).replace(
            "_OracleComponentLoopInfo", ComponentLoopInfo.__name__
        ).replace(
            "_OracleLoopMembership", LoopMembership.__name__
        )
        assert repr(shim) == expected

    def test_eq_same_values(self):
        o1 = LoopOwnershipMap(
            component_to_loops={
                "Q1": ComponentLoopInfo("Q1", [LoopMembership("commutation", "switch")]),
            }
        )
        o2 = LoopOwnershipMap(
            component_to_loops={
                "Q1": ComponentLoopInfo("Q1", [LoopMembership("commutation", "switch")]),
            }
        )
        assert o1 == o2

    def test_eq_different(self):
        o1 = LoopOwnershipMap(
            component_to_loops={
                "Q1": ComponentLoopInfo("Q1", [LoopMembership("commutation", "switch")]),
            }
        )
        o2 = LoopOwnershipMap(
            component_to_loops={
                "Q1": ComponentLoopInfo("Q1", [LoopMembership("gate_drive", "switch")]),
            }
        )
        assert o1 != o2

    def test_hash_raises_typeerror(self):
        ownership = LoopOwnershipMap()
        with pytest.raises(TypeError, match="unhashable"):
            hash(ownership)

    def test_direct_dict_field_access(self):
        """Component_to_loops and loop_to_components should be accessible as dicts."""
        ownership = LoopOwnershipMap(
            component_to_loops={
                "Q1": ComponentLoopInfo("Q1", [LoopMembership("commutation", "switch")]),
            },
            loop_to_components={"commutation": ["Q1"]},
        )
        assert "Q1" in ownership.component_to_loops
        assert "commutation" in ownership.loop_to_components
        assert ownership.loop_to_components["commutation"] == ["Q1"]
