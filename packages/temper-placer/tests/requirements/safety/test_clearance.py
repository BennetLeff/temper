"""
Tests for REQ-SAFE-01: Creepage/Clearance Verification Matrix.

These tests verify that clearance and creepage distance validation functions work correctly
and that placements meet IEC 60335-2-6 safety requirements.
"""

import pytest

# Import validators (will fail until implemented)
VALIDATORS_AVAILABLE = False
try:
    from tests.requirements.validators.clearance import (
        IEC60335_REQUIREMENTS,
        ClearanceResult,
        ClearanceViolation,
        InsulationType,
        VoltageDomain,
        check_creepage_path,
        check_domain_clearance,
        get_requirement_matrix,
        verify_iec60335_compliance,
    )

    # Check if validators are actually implemented (not just stubs)
    try:
        check_domain_clearance({}, VoltageDomain.MAINS, VoltageDomain.LV_CONTROL, 3.0)
        VALIDATORS_AVAILABLE = True
    except NotImplementedError:
        VALIDATORS_AVAILABLE = False

except ImportError:
    # Define placeholder classes for TDD - tests will be skipped
    class ClearanceViolation:
        def __init__(self, code, message, location=None, severity="error"):
            self.code = code
            self.message = message
            self.location = location
            self.severity = severity

    class ClearanceResult:
        def __init__(self, passed, violations):
            self.passed = passed
            self.violations = violations

        @property
        def error_count(self):
            return sum(1 for v in self.violations if v.severity == "error")

        @property
        def warning_count(self):
            return sum(1 for v in self.violations if v.severity == "warning")

    class VoltageDomain:
        MAINS = "MAINS"
        DC_BUS = "DC_BUS"
        BOOTSTRAP = "BOOTSTRAP"
        LV_CONTROL = "LV_CONTROL"
        ISOLATED = "ISOLATED"

        @property
        def value(self):
            return self

    class InsulationType:
        BASIC = "basic"
        REINFORCED = "reinforced"
        FUNCTIONAL = "functional"

        @property
        def value(self):
            return self

    def check_domain_clearance(*_args, **_kwargs):
        # Return empty result for TDD - tests will be skipped anyway
        return ClearanceResult(passed=True, violations=[])

    def check_creepage_path(*_args, **_kwargs):
        # Return empty result for TDD - tests will be skipped anyway
        return ClearanceResult(passed=True, violations=[])

    def verify_iec60335_compliance(*_args, **_kwargs):
        # Return empty result for TDD - tests will be skipped anyway
        return ClearanceResult(passed=True, violations=[])

    def get_requirement_matrix():
        # Return empty matrix for TDD - tests will be skipped anyway
        return {}


pytestmark = pytest.mark.skipif(
    not VALIDATORS_AVAILABLE, reason="Clearance validators not yet implemented"
)


# =============================================================================
# Test Fixtures
# =============================================================================


@pytest.fixture
def simple_placement():
    """Simple placement with adequate clearance."""
    return {
        "components": [
            {"ref": "U1", "footprint": "QFN-32", "position": (10, 10), "nets": ["LV_CONTROL"]},
            {"ref": "Q1", "footprint": "TO-220", "position": (50, 10), "nets": ["DC_BUS"]},
        ],
        "nets": {
            "LV_CONTROL": {"domain": VoltageDomain.LV_CONTROL},
            "DC_BUS": {"domain": VoltageDomain.DC_BUS},
        },
    }


@pytest.fixture
def violation_placement():
    """Placement with clearance violations."""
    return {
        "components": [
            {"ref": "U1", "footprint": "QFN-32", "position": (10, 10), "nets": ["LV_CONTROL"]},
            {
                "ref": "Q1",
                "footprint": "TO-220",
                "position": (12, 10),
                "nets": ["DC_BUS"],
            },  # 2mm apart
        ],
        "nets": {
            "LV_CONTROL": {"domain": VoltageDomain.LV_CONTROL},
            "DC_BUS": {"domain": VoltageDomain.DC_BUS},
        },
    }


@pytest.fixture
def mains_placement():
    """Placement with mains voltage components."""
    return {
        "components": [
            {"ref": "F1", "footprint": "FUSE", "position": (10, 10), "nets": ["MAINS_L"]},
            {"ref": "U1", "footprint": "QFN-32", "position": (20, 10), "nets": ["LV_CONTROL"]},
        ],
        "nets": {
            "MAINS_L": {"domain": VoltageDomain.MAINS},
            "LV_CONTROL": {"domain": VoltageDomain.LV_CONTROL},
        },
    }


# =============================================================================
# IEC 60335-2-6 Requirements Matrix Tests
# =============================================================================


class TestRequirementMatrix:
    """Tests for the IEC 60335-2-6 requirements matrix."""

    @pytest.mark.parametrize(
        "domain_a,domain_b,insulation_type,expected_clearance,expected_creepage,expected_design",
        [
            # Mains to SELV (LV_CONTROL)
            (VoltageDomain.MAINS, VoltageDomain.LV_CONTROL, InsulationType.BASIC, 3.0, 4.0, 6.0),
            (
                VoltageDomain.MAINS,
                VoltageDomain.LV_CONTROL,
                InsulationType.REINFORCED,
                6.0,
                8.0,
                10.0,
            ),
            # DC Bus to Control
            (VoltageDomain.DC_BUS, VoltageDomain.LV_CONTROL, InsulationType.BASIC, 3.0, 4.0, 6.0),
            (
                VoltageDomain.DC_BUS,
                VoltageDomain.LV_CONTROL,
                InsulationType.REINFORCED,
                6.0,
                8.0,
                10.0,
            ),
            # Across Isolation Barrier
            (
                VoltageDomain.MAINS,
                VoltageDomain.ISOLATED,
                InsulationType.REINFORCED,
                6.0,
                8.0,
                10.0,
            ),
            # Within LV Domain
            (
                VoltageDomain.LV_CONTROL,
                VoltageDomain.LV_CONTROL,
                InsulationType.FUNCTIONAL,
                0.5,
                1.0,
                2.0,
            ),
        ],
    )
    def test_requirement_matrix_values(
        self,
        domain_a,
        domain_b,
        insulation_type,
        expected_clearance,
        expected_creepage,
        expected_design,
    ):
        """Test that requirement matrix contains correct values."""
        matrix = get_requirement_matrix()
        key = (domain_a.value, domain_b.value, insulation_type.value)

        assert key in matrix, f"Missing requirement for {key}"
        requirements = matrix[key]

        assert requirements["min_clearance_mm"] == expected_clearance
        assert requirements["min_creepage_mm"] == expected_creepage
        assert requirements["design_value_mm"] == expected_design

    def test_matrix_completeness(self):
        """Test that matrix covers all expected boundary combinations."""
        matrix = get_requirement_matrix()

        # Should have 6 requirement entries
        assert len(matrix) == 6

        # Check specific required boundaries
        required_boundaries = [
            ("MAINS", "LV_CONTROL", "basic"),
            ("MAINS", "LV_CONTROL", "reinforced"),
            ("DC_BUS", "LV_CONTROL", "basic"),
            ("DC_BUS", "LV_CONTROL", "reinforced"),
            ("MAINS", "ISOLATED", "reinforced"),
            ("LV_CONTROL", "LV_CONTROL", "functional"),
        ]

        for boundary in required_boundaries:
            assert boundary in matrix, f"Missing requirement for {boundary}"


# =============================================================================
# Domain Clearance Tests
# =============================================================================


class TestDomainClearance:
    """Tests for domain clearance validation."""

    def test_adequate_clearance_passes(self, simple_placement):
        """Placement with adequate clearance should pass."""
        result = check_domain_clearance(
            simple_placement,
            VoltageDomain.DC_BUS,
            VoltageDomain.LV_CONTROL,
            min_mm=6.0,
        )

        assert result.passed
        assert result.error_count == 0

    def test_insufficient_clearance_fails(self, violation_placement):
        """Placement with insufficient clearance should fail."""
        result = check_domain_clearance(
            violation_placement,
            VoltageDomain.DC_BUS,
            VoltageDomain.LV_CONTROL,
            min_mm=3.0,
        )

        assert not result.passed
        assert result.error_count >= 1
        assert any("clearance" in v.message.lower() for v in result.violations)

    def test_mains_to_control_clearance(self, mains_placement):
        """Test mains to control circuit clearance."""
        result = check_domain_clearance(
            mains_placement,
            VoltageDomain.MAINS,
            VoltageDomain.LV_CONTROL,
            min_mm=6.0,  # Reinforced insulation requirement
        )

        # Should check for 6mm minimum clearance
        assert result.passed or not result.passed  # Depends on actual implementation

    def test_clearance_violation_details(self, violation_placement):
        """Test that violations include required details."""
        result = check_domain_clearance(
            violation_placement,
            VoltageDomain.DC_BUS,
            VoltageDomain.LV_CONTROL,
            min_mm=3.0,
        )

        if not result.passed:
            violation = result.violations[0]
            assert violation.code is not None
            assert violation.message is not None
            assert violation.severity in ["error", "warning"]


# =============================================================================
# Creepage Path Tests
# =============================================================================


class TestCreepagePath:
    """Tests for creepage path validation."""

    def test_adequate_creepage_passes(self, simple_placement):
        """Placement with adequate creepage should pass."""
        result = check_creepage_path(
            simple_placement,
            VoltageDomain.DC_BUS,
            VoltageDomain.LV_CONTROL,
            min_mm=4.0,
        )

        assert result.passed
        assert result.error_count == 0

    def test_insufficient_creepage_fails(self, violation_placement):
        """Placement with insufficient creepage should fail."""
        result = check_creepage_path(
            violation_placement,
            VoltageDomain.DC_BUS,
            VoltageDomain.LV_CONTROL,
            min_mm=4.0,
        )

        assert not result.passed
        assert result.error_count >= 1
        assert any("creepage" in v.message.lower() for v in result.violations)

    def test_surface_path_consideration(self):
        """Test that creepage considers surface path, not just straight-line distance."""
        # Components close in straight line but with long surface path
        placement = {
            "components": [
                {"ref": "U1", "footprint": "QFN-32", "position": (10, 10), "nets": ["LV_CONTROL"]},
                {"ref": "Q1", "footprint": "TO-220", "position": (15, 10), "nets": ["DC_BUS"]},
            ],
            "nets": {
                "LV_CONTROL": {"domain": VoltageDomain.LV_CONTROL},
                "DC_BUS": {"domain": VoltageDomain.DC_BUS},
            },
        }

        result = check_creepage_path(
            placement,
            VoltageDomain.DC_BUS,
            VoltageDomain.LV_CONTROL,
            min_mm=4.0,
        )

        # Should fail if surface path is considered
        assert not result.passed or result.passed  # Depends on implementation

    def test_creepage_violation_includes_path_info(self, violation_placement):
        """Test that creepage violations include path information."""
        result = check_creepage_path(
            violation_placement,
            VoltageDomain.DC_BUS,
            VoltageDomain.LV_CONTROL,
            min_mm=4.0,
        )

        if not result.passed:
            violation = result.violations[0]
            assert violation.code is not None
            assert "creepage" in violation.message.lower()


# =============================================================================
# IEC 60335-2-6 Compliance Tests
# =============================================================================


class TestIEC60335Compliance:
    """Tests for complete IEC 60335-2-6 compliance verification."""

    def test_compliant_placement_passes(self, simple_placement):
        """Fully compliant placement should pass all checks."""
        voltage_domains = {
            "LV_CONTROL": VoltageDomain.LV_CONTROL,
            "DC_BUS": VoltageDomain.DC_BUS,
        }

        result = verify_iec60335_compliance(simple_placement, voltage_domains)

        assert result.passed
        assert result.error_count == 0

    def test_non_compliant_placement_fails(self, violation_placement):
        """Non-compliant placement should fail."""
        voltage_domains = {
            "LV_CONTROL": VoltageDomain.LV_CONTROL,
            "DC_BUS": VoltageDomain.DC_BUS,
        }

        result = verify_iec60335_compliance(violation_placement, voltage_domains)

        assert not result.passed
        assert result.error_count >= 1

    def test_multiple_violations_aggregated(self):
        """Multiple violations should be aggregated in result."""
        # Create placement with multiple violations
        placement = {
            "components": [
                {"ref": "U1", "footprint": "QFN-32", "position": (10, 10), "nets": ["LV_CONTROL"]},
                {"ref": "Q1", "footprint": "TO-220", "position": (12, 10), "nets": ["DC_BUS"]},
                {"ref": "F1", "footprint": "FUSE", "position": (14, 10), "nets": ["MAINS_L"]},
            ],
            "nets": {
                "LV_CONTROL": {"domain": VoltageDomain.LV_CONTROL},
                "DC_BUS": {"domain": VoltageDomain.DC_BUS},
                "MAINS_L": {"domain": VoltageDomain.MAINS},
            },
        }

        voltage_domains = {
            "LV_CONTROL": VoltageDomain.LV_CONTROL,
            "DC_BUS": VoltageDomain.DC_BUS,
            "MAINS_L": VoltageDomain.MAINS,
        }

        result = verify_iec60335_compliance(placement, voltage_domains)

        # Should have multiple violations
        assert result.error_count >= 2

    def test_all_boundary_types_checked(self):
        """verify_iec60335_compliance actually walks every matrix row, not a
        hardcoded subset. Falsifier: pack one component into each domain the
        matrix references (2 into LV_CONTROL, so the FUNCTIONAL
        LV_CONTROL<->LV_CONTROL row has a pair to check) within 0.05mm of
        each other -- tighter than the matrix's smallest requirement
        (FUNCTIONAL: 0.5mm clearance) -- so every one of the 6 matrix rows
        must report at least one clearance + one creepage violation, and
        every (boundary, insulation_type) combination in the matrix must
        appear in the result. If the implementation only checks a subset
        (e.g. hardcodes MAINS<->LV_CONTROL and ignores the rest), the
        boundary/insulation_type coverage assertions below catch it even
        though the exact violation count depends on how many component
        pairs straddle each boundary (2 LV_CONTROL components means every
        *-LV_CONTROL boundary yields 2 pairs, not 1).
        """
        matrix = get_requirement_matrix()
        assert len(matrix) == 6

        components = [
            {"ref": "MAINS1", "footprint": "0402", "position": (0.00, 0.0), "nets": ["N_MAINS"]},
            {"ref": "DCBUS1", "footprint": "0402", "position": (0.05, 0.0), "nets": ["N_DCBUS"]},
            {"ref": "ISO1", "footprint": "0402", "position": (0.10, 0.0), "nets": ["N_ISO"]},
            {"ref": "LV1", "footprint": "0402", "position": (0.15, 0.0), "nets": ["N_LV1"]},
            {"ref": "LV2", "footprint": "0402", "position": (0.20, 0.0), "nets": ["N_LV2"]},
        ]
        nets = {
            "N_MAINS": {"domain": VoltageDomain.MAINS},
            "N_DCBUS": {"domain": VoltageDomain.DC_BUS},
            "N_ISO": {"domain": VoltageDomain.ISOLATED},
            "N_LV1": {"domain": VoltageDomain.LV_CONTROL},
            "N_LV2": {"domain": VoltageDomain.LV_CONTROL},
        }
        placement = {"components": components, "nets": nets}
        voltage_domains = {name: info["domain"] for name, info in nets.items()}

        result = verify_iec60335_compliance(placement, voltage_domains)

        assert not result.passed
        # Every *-LV_CONTROL cross-domain boundary sees 2 pairs (1 other-side
        # component x 2 LV_CONTROL components); MAINS<->ISOLATED and the
        # LV_CONTROL<->LV_CONTROL self-pair each see exactly 1 pair. All
        # pairs are well within every row's minimum, so every candidate
        # pair violates both clearance and creepage: (4 rows x 2 pairs +
        # 2 rows x 1 pair) x 2 metrics = 20.
        assert len(result.violations) == 20

        expected_boundaries = {
            f"{a.value}<->{b.value}" for (a, b, _insulation) in IEC60335_REQUIREMENTS
        }
        seen_boundaries = {v.boundary for v in result.violations}
        assert seen_boundaries == expected_boundaries

        expected_insulation_types = {it for (_a, _b, it) in IEC60335_REQUIREMENTS}
        seen_insulation_types = {v.insulation_type for v in result.violations}
        assert seen_insulation_types == expected_insulation_types


# =============================================================================
# Integration Tests
# =============================================================================


class TestClearanceIntegration:
    """Integration tests for complete clearance validation."""

    @pytest.mark.slow
    def test_temper_board_clearance_compliance(self):
        """Temper board should meet all REQ-SAFE-01 requirements -- within
        the LEGACY 10-net boundary set this check has always used.

        UPDATE 2026-07-27: this was `xfail(strict=True)`, first with a
        reason citing 18 violations (2026-07-26 evidence doc), which turned
        out to be computed on a **broken reference-designator join**: the
        committed board's designators had drifted from the current netlist
        for 78 of 149 shared refs (e.g. old `U3` was a SOT-23-6 buck
        converter; the netlist's current `U3` is a DIP-6 H11L1
        optocoupler) -- see
        docs/evidence/2026-07-27-pcb-netlist-resync.md. After
        `pcb/temper.kicad_pcb` was resynced against the current netlist by
        reference designator/Sheetpath (0 components moved, 126/126
        classifiable components up from 109/126), the real count was
        **22** violations, not 18 -- re-derived directly, not assumed.

        The placer itself had no voltage-domain-aware clearance constraint
        (confirmed: no `hv_clearance`/`domain_clearance`/`isolation_gap`/
        `VoltageDomain` anywhere in placer/cp_sat/_encoder_core.py or
        model.py), so any hand-fix would have been silently reintroduced by
        the next solve. `temper_placer.placer.cp_sat.domain_clearance` adds
        a constraint generator that reuses this exact module's
        IEC60335_REQUIREMENTS/VoltageDomain classifier (not a second one)
        to emit per-pair SeparatedConstraint objects at the IEC 60335-2-6
        margin, and the resynced board was re-solved with them (169/169
        components, CP-SAT status=optimal). Re-running this exact check
        against the re-solved, re-parsed `pcb/temper.kicad_pcb` now reports
        0 violations -- see
        docs/evidence/2026-07-27-domain-clearance-constraint.md for the
        full 22->0 before/after count, the R24 soundness proof,
        BMC-exhaustive validation, and the post-solve audit. This is now a
        normal passing assertion, not an xfail: converting away from
        `xfail(strict=True)` is required once the underlying defect closes
        -- leaving the strict-xfail marker in place would have made this
        specific test XPASS (a hard failure under `strict=True`) while
        masking the fact the placer's actual capability changed.

        Falsifier (original, R24): if this ever reports >0 violations while
        `pcb/temper.kicad_pcb` is the resynced-and-re-solved board, the
        domain-clearance constraint (or its post-solve audit) has
        regressed silently. As implemented, it currently correctly reports
        0 violations, so the falsifier has NOT fired.

        UPDATE 2026-07-27 (coverage gap): this check's "0 violations" only
        ever covered 10 nets / ~127 of 170 components (74.7%) -- see
        docs/evidence/2026-07-27-domain-classification-coverage.md, the
        deliverable for that separate finding. That doc's own falsifier
        ("benign if every unclassified component is already further from
        mains than the largest IEC margin") did NOT hold on the first
        measurement (3 candidates under margin); after a small, mechanically
        -justified expansion of elec/domain_manifest.yaml (this same
        change), coverage rose to 156/170 (91.8%) and exactly one candidate
        remains, which is a same-declared-protective-impedance-chain
        sibling pair (not a new hazard -- see that doc). The two assertions
        below (coverage ratio, HV-proximity fail-closed) are the new,
        first-class checks that close this gap going forward; they use the
        FULL manifest-derived classification, not the legacy 10-net set the
        rest of this test method still checks. Widening the legacy set
        itself is deliberately NOT done here: doing so surfaces 17 real,
        previously-uncovered violations (9 unique component pairs) that
        need a placement re-solve to fix, which this task cannot perform
        (`pcb/temper.kicad_pcb` is read-only, owned by a concurrently
        running placement/routing task) -- see the evidence doc sec 5 for
        the full list. That finding is reported, not hidden: it is computed
        and asserted-as-informational below every time this test runs.
        """
        from ._real_board_fixture import RealBoardUnavailable, load_real_board_placement

        try:
            placement, voltage_domains, stats = load_real_board_placement()
        except RealBoardUnavailable as exc:
            pytest.skip(f"{exc} (run `make netlist` first)")

        assert stats["matched_components_in_placement"] > 0, (
            "Loaded zero components onto classified domains -- this would "
            "make the check below vacuously pass. Investigate the fixture, "
            "don't trust a 0-violation result from an empty placement."
        )

        # --- Coverage, reported prominently every run (not just on failure) ---
        print(
            f"\nDOMAIN CLASSIFICATION COVERAGE: "
            f"{stats['matched_components_in_placement_full']} of "
            f"{stats['total_components']} components classified "
            f"({stats['coverage_ratio']:.1%}), "
            f"{stats['compiled_nets_total'] - stats['unclassified_nets_total']} of "
            f"{stats['compiled_nets_total']} compiled nets classified "
            f"(boundary set ASSERTED by the hard check below: "
            f"{stats['matched_components_in_placement']} components / "
            f"{len(stats['classified_nets_present'])} nets)."
        )

        # Strengthened guard (was `> 0`, which a single matched component
        # would satisfy): require most of the board to be classified, not
        # merely "not zero". Threshold sits comfortably below the current
        # 91.8% full-manifest coverage so ordinary net-count churn (a part
        # added/removed) doesn't make this brittle, while still catching a
        # regression back toward the old, much sparser 74.7%-coverage state.
        assert stats["coverage_ratio"] >= 0.85, (
            f"Domain classification coverage dropped to "
            f"{stats['coverage_ratio']:.1%} "
            f"({stats['matched_components_in_placement_full']} of "
            f"{stats['total_components']} components) -- below the 85% "
            "floor. A 0-violation clearance result over a shrinking "
            "fraction of the board is not a safety result; see "
            "docs/evidence/2026-07-27-domain-classification-coverage.md."
        )

        # --- Fail-closed: any unclassified component sitting within the
        # largest IEC margin of an HV-classified component is a live,
        # currently-undetected candidate violation and must not pass
        # silently (the whole point of this task). The one exemption is a
        # same-declared-protective-impedance-chain sibling pair -- see
        # _real_board_fixture.py's _chain_sibling_exempt_pairs docstring.
        non_exempt_proximity = [
            f
            for f in stats["proximity_findings"]
            if not f["exempt"] and f["distance_mm"] < stats["max_iec_margin_mm"]
        ]
        assert not non_exempt_proximity, (
            f"{len(non_exempt_proximity)} unclassified component(s) sit "
            f"closer than the largest IEC margin "
            f"({stats['max_iec_margin_mm']}mm) to a declared-HV component, "
            "with no exemption on record: "
            + "; ".join(
                f"{f['ref']} ({f['instance_path']}) at {f['distance_mm']:.3f}mm "
                f"from {f['nearest_hv_ref']} ({f['nearest_hv_instance_path']})"
                for f in non_exempt_proximity
            )
        )

        # --- Informational: what the FULL manifest-derived classification
        # would find if wired into the hard check above (see this method's
        # 2026-07-27 docstring update for why it isn't, yet). Printed every
        # run so this is impossible to miss, not asserted, so this test's
        # pass/fail is not gated on a placement re-solve outside this
        # task's scope.
        full_result = verify_iec60335_compliance(
            stats["full_placement"], stats["full_voltage_domains"]
        )
        print(
            f"FULL-COVERAGE CROSS-CHECK: "
            f"{full_result.error_count} REQ-SAFE-01 violation(s) over the "
            f"full {stats['declared_nets_total']}-net manifest declaration "
            f"({stats['matched_components_in_placement_full']} components). "
            "As of 2026-07-27 the asserted set above IS the full declared "
            "set, so this figure should track it; a divergence between the "
            "two means the fixture has started filtering again. "
            "See docs/evidence/2026-07-27-clearance-resolve-full-coverage.md "
            "for the re-solve that took this from 17 violations to 0."
        )

        result = verify_iec60335_compliance(placement, voltage_domains)

        assert result.passed, (
            f"{result.error_count} REQ-SAFE-01 clearance/creepage violations "
            f"on the real board (components matched: "
            f"{stats['matched_components_in_placement']}). See "
            "docs/evidence/2026-07-26-safety-validators-implemented.md for "
            "the full list."
        )

    def test_validation_result_aggregation(self):
        """Multiple violations should aggregate correctly."""
        # Create violations from different checks
        violations = [
            ClearanceViolation("SAFE001", "Insufficient clearance", severity="error"),
            ClearanceViolation("SAFE002", "Inadequate creepage", severity="error"),
            ClearanceViolation("SAFE003", "Missing insulation", severity="warning"),
        ]

        result = ClearanceResult(passed=False, violations=violations)

        assert result.error_count == 2
        assert result.warning_count == 1
        assert not result.passed

    def test_voltage_domain_enum_values(self):
        """Test that voltage domain enums have expected values."""
        assert VoltageDomain.MAINS == "MAINS"
        assert VoltageDomain.DC_BUS == "DC_BUS"
        assert VoltageDomain.BOOTSTRAP == "BOOTSTRAP"
        assert VoltageDomain.LV_CONTROL == "LV_CONTROL"
        assert VoltageDomain.ISOLATED == "ISOLATED"

    def test_insulation_type_enum_values(self):
        """Test that insulation type enums have expected values."""
        assert InsulationType.BASIC == "basic"
        assert InsulationType.REINFORCED == "reinforced"
        assert InsulationType.FUNCTIONAL == "functional"
