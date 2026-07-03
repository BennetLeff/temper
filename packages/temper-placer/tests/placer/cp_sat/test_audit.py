"""U4: Tests for the post-solve constraint audit.

Verifies that audit_placement() correctly detects violations for every
constraint type encoded in the CP-SAT model. Tests use deliberate
placements (not solver output) to isolate the audit logic.
"""

from __future__ import annotations

import pytest

from temper_placer.placer.cp_sat.audit import (
    AuditReport,
    Violation,
    audit_placement,
)


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def small_components() -> dict:
    """Three small components used across multiple tests."""
    return {
        "R1": {"w": 10.0, "h": 5.0},
        "R2": {"w": 8.0, "h": 4.0},
        "C1": {"w": 6.0, "h": 6.0},
    }


@pytest.fixture
def valid_positions() -> dict[str, tuple[float, float]]:
    """Non-overlapping placement for small_components."""
    return {
        "R1": (0.0, 0.0),    # (0,0)-(10,5)
        "R2": (15.0, 0.0),   # (15,0)-(23,4)
        "C1": (0.0, 10.0),   # (0,10)-(6,16)
    }


# ── Happy Path ────────────────────────────────────────────────────────


class TestHappyPath:
    """Placements with no violations."""

    def test_no_violations_on_valid_placement(
        self, valid_positions: dict, small_components: dict
    ) -> None:
        """A valid non-overlapping placement should pass the audit."""
        report = audit_placement(valid_positions, small_components)
        assert report.passed
        assert len(report.violations) == 0
        assert report.stats["failed"] == 0
        # 3 components => C(3,2) = 3 pairwise checks
        assert report.stats["checked"] == 3
        assert report.stats["passed"] == 3

    def test_no_violations_with_all_constraints(
        self, valid_positions: dict, small_components: dict
    ) -> None:
        """All constraint types satisfied should pass."""
        constraints = {
            "clearance_pairs": [("R1", "R2", 2.0)],
            "adjacent_pairs": [("R1", "C1", 20.0)],
            "edge_anchors": [("R1", "bottom", 5.0)],
            "region_members": [("R1", 0.0, 50.0, 0.0, 50.0)],
        }
        report = audit_placement(valid_positions, small_components, constraints)
        assert report.passed
        assert len(report.violations) == 0

    def test_empty_components(self) -> None:
        """Zero components should pass with stats.checked=0."""
        report = audit_placement({}, {})
        assert report.passed
        assert len(report.violations) == 0
        assert report.stats["checked"] == 0
        assert report.stats["passed"] == 0
        assert report.stats["failed"] == 0

    def test_single_component(self) -> None:
        """A single component has no pairs to check, passes trivially."""
        components = {"R1": {"w": 10.0, "h": 5.0}}
        positions = {"R1": (0.0, 0.0)}
        report = audit_placement(positions, components)
        assert report.passed
        assert report.stats["checked"] == 0  # no pairs
        assert report.stats["passed"] == 0

    def test_components_touching_edges_not_overlapping(self) -> None:
        """Components that share an edge (touch) do NOT overlap."""
        components = {
            "A": {"w": 10.0, "h": 5.0},
            "B": {"w": 8.0, "h": 4.0},
        }
        # A at (0,0)-(10,5), B starts exactly at A's right edge (10,0)-(18,4)
        positions = {"A": (0.0, 0.0), "B": (10.0, 0.0)}
        report = audit_placement(positions, components)
        assert report.passed


# ── Overlap Detection ─────────────────────────────────────────────────


class TestOverlap:
    """No-overlap (R1) violation detection."""

    def test_detects_overlap(self) -> None:
        """Two overlapping components should be caught."""
        components = {
            "R1": {"w": 10.0, "h": 5.0},
            "R2": {"w": 8.0, "h": 4.0},
        }
        # R1: (0,0)-(10,5), R2: (5,2)-(13,6) — overlaps in both axes
        positions = {"R1": (0.0, 0.0), "R2": (5.0, 2.0)}
        report = audit_placement(positions, components)
        assert not report.passed
        assert len(report.violations) == 1
        v = report.violations[0]
        assert v.constraint_type == "no_overlap"
        assert "R1" in v.components
        assert "R2" in v.components
        assert v.expected == 0.0
        assert v.actual > 0.0  # overlap amount

    def test_detects_overlap_x_only(self) -> None:
        """Overlap in X but not Y does NOT count as overlap (no full overlap)."""
        components = {
            "A": {"w": 10.0, "h": 5.0},
            "B": {"w": 5.0, "h": 5.0},
        }
        # A: (0,0)-(10,5), B: (5,10)-(10,15) — overlap in X only
        positions = {"A": (0.0, 0.0), "B": (5.0, 10.0)}
        report = audit_placement(positions, components)
        assert report.passed  # No AABB overlap (no Y overlap)

    def test_detects_overlap_y_only(self) -> None:
        """Overlap in Y but not X does NOT count as overlap."""
        components = {
            "A": {"w": 5.0, "h": 10.0},
            "B": {"w": 5.0, "h": 5.0},
        }
        # A: (0,0)-(5,10), B: (10,5)-(15,10) — overlap in Y only
        positions = {"A": (0.0, 0.0), "B": (10.0, 5.0)}
        report = audit_placement(positions, components)
        assert report.passed  # No AABB overlap (no X overlap)

    def test_multiple_overlaps(self) -> None:
        """Multiple overlapping pairs should all be reported."""
        components = {
            "A": {"w": 10.0, "h": 10.0},
            "B": {"w": 10.0, "h": 10.0},
            "C": {"w": 10.0, "h": 10.0},
        }
        # All at same position => A overlaps B, A overlaps C, B overlaps C
        positions = {"A": (0.0, 0.0), "B": (5.0, 5.0), "C": (2.0, 2.0)}
        report = audit_placement(positions, components)
        assert not report.passed
        assert len(report.violations) == 3  # 3 overlapping pairs
        assert all(v.constraint_type == "no_overlap" for v in report.violations)


# ── Clearance Detection ───────────────────────────────────────────────


class TestClearance:
    """Chebyshev clearance (R2) violation detection."""

    def test_detects_clearance_violation(self) -> None:
        """Components closer than min clearance should be caught."""
        components = {
            "R1": {"w": 10.0, "h": 5.0},
            "R2": {"w": 8.0, "h": 4.0},
        }
        # R1: (0,0)-(10,5), R2: (12,0)-(20,4)
        # Horizontal gap = 12 - 10 = 2mm, vertical gap = 0mm (aligned)
        # Chebyshev clearance = max(2, 0) = 2mm
        positions = {"R1": (0.0, 0.0), "R2": (12.0, 0.0)}
        constraints = {"clearance_pairs": [("R1", "R2", 5.0)]}
        report = audit_placement(positions, components, constraints)
        assert not report.passed
        assert len(report.violations) == 1
        v = report.violations[0]
        assert v.constraint_type == "clearance"
        assert "R1" in v.components
        assert "R2" in v.components
        assert v.actual == pytest.approx(2.0, abs=1e-9)
        assert v.expected == 5.0

    def test_clearance_satisfied_with_large_gap(self) -> None:
        """Components far enough apart pass clearance."""
        components = {
            "A": {"w": 10.0, "h": 5.0},
            "B": {"w": 8.0, "h": 4.0},
        }
        # A: (0,0)-(10,5), B: (20,0)-(28,4)
        # Horizontal gap = 20 - 10 = 10mm >= 5mm ✓
        positions = {"A": (0.0, 0.0), "B": (20.0, 0.0)}
        constraints = {"clearance_pairs": [("A", "B", 5.0)]}
        report = audit_placement(positions, components, constraints)
        assert report.passed

    def test_clearance_satisfied_vertical_separation(self) -> None:
        """Vertical separation alone satisfies Chebyshev clearance."""
        components = {
            "A": {"w": 30.0, "h": 5.0},
            "B": {"w": 30.0, "h": 4.0},
        }
        # A: (0,0)-(30,5), B: (0,20)-(30,24)
        # Horizontal gap = 0mm (directly above), Vertical gap = 20-5 = 15mm >= 5mm ✓
        positions = {"A": (0.0, 0.0), "B": (0.0, 20.0)}
        constraints = {"clearance_pairs": [("A", "B", 5.0)]}
        report = audit_placement(positions, components, constraints)
        assert report.passed

    def test_multiple_clearance_pairs(self) -> None:
        """Multiple clearance pairs: one fails, rest pass."""
        components = {
            "A": {"w": 5.0, "h": 5.0},
            "B": {"w": 5.0, "h": 5.0},
            "C": {"w": 5.0, "h": 5.0},
        }
        # A: (0,0)-(5,5), B: (6,0)-(11,5) — gap=1mm
        # C: (20,20)-(25,25) — far away
        positions = {"A": (0.0, 0.0), "B": (6.0, 0.0), "C": (20.0, 20.0)}
        constraints = {
            "clearance_pairs": [
                ("A", "B", 2.0),   # gap=1mm < 2mm => VIOLATION
                ("A", "C", 2.0),   # large gap => PASS
                ("B", "C", 2.0),   # large gap => PASS
            ]
        }
        report = audit_placement(positions, components, constraints)
        assert not report.passed
        assert len(report.violations) == 1
        assert report.violations[0].constraint_type == "clearance"
        # 3 no-overlap checks (C(3,2)) + 3 clearance checks = 6
        assert report.stats["checked"] == 6
        # 3 no-overlap pass + 2 clearance pass = 5
        assert report.stats["passed"] == 5
        assert report.stats["failed"] == 1


# ── Edge Anchoring ────────────────────────────────────────────────────


class TestEdgeAnchor:
    """Edge anchoring (R3) violation detection."""

    def test_detects_edge_violation(self) -> None:
        """Component too far from the specified edge should be caught."""
        components = {"R1": {"w": 10.0, "h": 5.0}}
        # R1 bottom edge at y=50, max allowed from bottom = 10mm => 50 > 10
        positions = {"R1": (0.0, 50.0)}
        constraints = {"edge_anchors": [("R1", "bottom", 10.0)]}
        report = audit_placement(positions, components, constraints)
        assert not report.passed
        assert len(report.violations) == 1
        v = report.violations[0]
        assert v.constraint_type == "edge_anchor"
        assert v.components == ["R1"]
        assert v.actual == pytest.approx(50.0)
        assert v.expected == 10.0

    def test_edge_anchor_satisfied(self) -> None:
        """Component within max distance of edge passes."""
        components = {"R1": {"w": 10.0, "h": 5.0}}
        positions = {"R1": (0.0, 3.0)}  # bottom edge at y=3 <= 10
        constraints = {"edge_anchors": [("R1", "bottom", 10.0)]}
        report = audit_placement(positions, components, constraints)
        assert report.passed

    def test_edge_anchor_left_edge(self) -> None:
        """Left edge anchoring works."""
        components = {"R1": {"w": 10.0, "h": 5.0}}
        positions = {"R1": (50.0, 0.0)}  # left edge at x=50 > 10
        constraints = {"edge_anchors": [("R1", "left", 10.0)]}
        report = audit_placement(positions, components, constraints)
        assert not report.passed
        assert report.violations[0].constraint_type == "edge_anchor"
        assert report.violations[0].actual == pytest.approx(50.0)

    def test_edge_anchor_right_edge_with_board_width(self) -> None:
        """Right edge anchoring with board_w_mm specified."""
        components = {"R1": {"w": 10.0, "h": 5.0}}
        # Board width=100, R1 right edge at 50+10=60, dist from right = 100-60=40
        positions = {"R1": (50.0, 0.0)}
        constraints = {"edge_anchors": [("R1", "right", 10.0)]}
        report = audit_placement(
            positions, components, constraints, board_w_mm=100.0
        )
        assert not report.passed
        assert report.violations[0].constraint_type == "edge_anchor"
        assert report.violations[0].actual == pytest.approx(40.0)

    def test_edge_anchor_top_edge_with_board_height(self) -> None:
        """Top edge anchoring with board_h_mm specified."""
        components = {"R1": {"w": 10.0, "h": 5.0}}
        # Board height=100, R1 top edge at 10+5=15, dist from top = 100-15=85
        positions = {"R1": (0.0, 10.0)}
        constraints = {"edge_anchors": [("R1", "top", 10.0)]}
        report = audit_placement(
            positions, components, constraints, board_h_mm=100.0
        )
        assert not report.passed
        assert report.violations[0].constraint_type == "edge_anchor"
        assert report.violations[0].actual == pytest.approx(85.0)


# ── Adjacency Detection ───────────────────────────────────────────────


class TestAdjacency:
    """Adjacency/proximity (R4) violation detection."""

    def test_detects_adjacency_violation(self) -> None:
        """Components too far apart should be caught."""
        components = {
            "R1": {"w": 10.0, "h": 5.0},
            "R2": {"w": 8.0, "h": 4.0},
        }
        # R1: (0,0)-(10,5), R2: (100,0)-(108,4)
        # x_start[b]=100 <= x_start[a]+w_a+max_d = 0+10+10 = 20? NO
        positions = {"R1": (0.0, 0.0), "R2": (100.0, 0.0)}
        constraints = {"adjacent_pairs": [("R1", "R2", 10.0)]}
        report = audit_placement(positions, components, constraints)
        assert not report.passed
        assert len(report.violations) == 1
        v = report.violations[0]
        assert v.constraint_type == "adjacency"
        assert "R1" in v.components
        assert "R2" in v.components
        assert v.expected == 10.0

    def test_adjacency_satisfied(self) -> None:
        """Components close enough pass adjacency."""
        components = {
            "A": {"w": 10.0, "h": 5.0},
            "B": {"w": 8.0, "h": 4.0},
        }
        # A: (0,0)-(10,5), B: (12,0)-(20,4)
        # x_b=12 <= x_a + w_a + max_d = 0+10+10=20 ✓
        # x_a=0 <= x_b + w_b + max_d = 12+8+10=30 ✓
        positions = {"A": (0.0, 0.0), "B": (12.0, 0.0)}
        constraints = {"adjacent_pairs": [("A", "B", 10.0)]}
        report = audit_placement(positions, components, constraints)
        assert report.passed


# ── Region Membership Detection ───────────────────────────────────────


class TestRegionMembership:
    """Region membership (R5) violation detection."""

    def test_detects_region_violation(self) -> None:
        """Component outside the designated region should be caught."""
        components = {"R1": {"w": 10.0, "h": 5.0}}
        # R1: (100,100)-(110,105), region: [0,50] x [0,50]
        # Right edge 110 > 50, top edge 105 > 50
        positions = {"R1": (100.0, 100.0)}
        constraints = {
            "region_members": [("R1", 0.0, 50.0, 0.0, 50.0)]
        }
        report = audit_placement(positions, components, constraints)
        assert not report.passed
        assert len(report.violations) == 1
        v = report.violations[0]
        assert v.constraint_type == "region_membership"
        assert v.components == ["R1"]
        assert v.actual > 0.0

    def test_region_membership_satisfied(self) -> None:
        """Component fully inside region passes."""
        components = {"R1": {"w": 10.0, "h": 5.0}}
        positions = {"R1": (5.0, 5.0)}  # (5,5)-(15,10), inside [0,50]x[0,50]
        constraints = {
            "region_members": [("R1", 0.0, 50.0, 0.0, 50.0)]
        }
        report = audit_placement(positions, components, constraints)
        assert report.passed

    def test_region_membership_violation_right_edge(self) -> None:
        """Component's right edge outside region."""
        components = {"R1": {"w": 10.0, "h": 5.0}}
        positions = {"R1": (45.0, 0.0)}  # right edge at 55 > 50
        constraints = {
            "region_members": [("R1", 0.0, 50.0, 0.0, 50.0)]
        }
        report = audit_placement(positions, components, constraints)
        assert not report.passed
        assert len(report.violations) == 1

    def test_region_membership_violation_left_edge(self) -> None:
        """Component's left edge outside region (negative x)."""
        components = {"R1": {"w": 10.0, "h": 5.0}}
        positions = {"R1": (-5.0, 0.0)}  # left edge at -5 < 0
        constraints = {
            "region_members": [("R1", 0.0, 50.0, 0.0, 50.0)]
        }
        report = audit_placement(positions, components, constraints)
        assert not report.passed


# ── Deliberate Corruption ─────────────────────────────────────────────


class TestDeliberateCorruption:
    """Valid placements that are then corrupted."""

    def test_deliberate_corruption(
        self, valid_positions: dict, small_components: dict
    ) -> None:
        """Shift one component 5mm should be caught with all constraints."""
        # Start from a clean valid placement
        components = small_components
        positions = dict(valid_positions)

        # Add constraints that the valid placement satisfies
        constraints = {
            "clearance_pairs": [("R1", "R2", 3.0)],  # gap=5mm >= 3 ✓
            "adjacent_pairs": [("R1", "C1", 12.0)],  # C1 at (0,10) => y difference
            "edge_anchors": [("R1", "bottom", 1.0)],  # R1 bottom at y=0 ✓
            "region_members": [("R1", 0.0, 50.0, 0.0, 50.0)],
        }

        # Verify valid placement passes
        report = audit_placement(positions, components, constraints)
        assert report.passed, "Valid placement should pass before corruption"

        # Corrupt: shift R1 5mm to the right
        positions["R1"] = (5.0, 0.0)  # was (0,0), now overlaps with R2 at (15,0)?

        # Actually: R1 now at (5,0)-(15,5), R2 at (15,0)-(23,4)
        # These just touch at x=15 — no overlap since touching doesn't count
        # But clearance: R1-R2 gap = 15-15=0mm < 3mm ✓ (caught)
        # And edge anchor: R1 bottom at y=0 <= 1 ✓

        report = audit_placement(positions, components, constraints)
        assert not report.passed, "Corrupted placement should fail"
        assert len(report.violations) >= 1

        # The clearance pair (R1, R2, 3.0) should be violated: gap is 0 < 3
        clearance_violations = [
            v
            for v in report.violations
            if v.constraint_type == "clearance"
        ]
        assert len(clearance_violations) >= 1

    def test_deliberate_corruption_overlap(
        self, valid_positions: dict, small_components: dict
    ) -> None:
        """Shifting component into another causes overlap violation."""
        positions = dict(valid_positions)  # R1: (0,0), R2: (15,0), C1: (0,10)

        # Shift R1 to overlap with R2
        positions["R1"] = (10.0, 0.0)  # (10,0)-(20,5) overlaps R2 at (15,0)-(23,4)

        report = audit_placement(positions, small_components)
        assert not report.passed
        overlap_violations = [
            v
            for v in report.violations
            if v.constraint_type == "no_overlap"
        ]
        assert len(overlap_violations) >= 1
        assert "R1" in overlap_violations[0].components
        assert "R2" in overlap_violations[0].components


# ── Error Paths ───────────────────────────────────────────────────────


class TestErrorPaths:
    """Error handling in edge cases."""

    def test_missing_component_in_clearance(self, small_components: dict) -> None:
        """Constraint referencing a component not in positions raises KeyError."""
        positions = {"R1": (0.0, 0.0)}
        constraints = {"clearance_pairs": [("R1", "MISSING", 5.0)]}
        with pytest.raises(KeyError, match="MISSING"):
            audit_placement(positions, small_components, constraints)

    def test_missing_component_in_adjacency(self, small_components: dict) -> None:
        positions = {"R1": (0.0, 0.0)}
        constraints = {"adjacent_pairs": [("MISSING", "R1", 10.0)]}
        with pytest.raises(KeyError, match="MISSING"):
            audit_placement(positions, small_components, constraints)

    def test_missing_component_in_edge_anchor(self, small_components: dict) -> None:
        positions = {"R1": (0.0, 0.0)}
        constraints = {"edge_anchors": [("MISSING", "bottom", 10.0)]}
        with pytest.raises(KeyError, match="MISSING"):
            audit_placement(positions, small_components, constraints)

    def test_missing_component_in_region(self, small_components: dict) -> None:
        positions = {"R1": (0.0, 0.0)}
        constraints = {"region_members": [("MISSING", 0.0, 50.0, 0.0, 50.0)]}
        with pytest.raises(KeyError, match="MISSING"):
            audit_placement(positions, small_components, constraints)

    def test_empty_constraints_dict(
        self, valid_positions: dict, small_components: dict
    ) -> None:
        """Empty constraints dict should not cause errors."""
        report = audit_placement(valid_positions, small_components, {})
        assert report.passed
        assert report.stats["checked"] == 3  # still checks no-overlap

    def test_none_constraints(
        self, valid_positions: dict, small_components: dict
    ) -> None:
        """None constraints should be treated as empty."""
        report = audit_placement(valid_positions, small_components, None)
        assert report.passed

    def test_components_with_different_key_formats(self) -> None:
        """Components using width_mm/height_mm keys work."""
        components = {
            "R1": {"width_mm": 10.0, "height_mm": 5.0},
            "R2": {"width_mm": 8.0, "height_mm": 4.0},
        }
        positions = {"R1": (0.0, 0.0), "R2": (15.0, 0.0)}
        report = audit_placement(positions, components)
        assert report.passed
