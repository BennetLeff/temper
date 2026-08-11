"""Coverage paydown tests v10: constraints reporter, validation metrics,
validation preflight, io provenance, testing quarantine/golden-diff,
heuristics organizational/style/structural pure functions, pipeline helpers.

Exercises public functions in:
- constraints/reporter.py: ConstraintResult, ConstraintReport (pure dataclass)
- validation/metrics.py: PlacementMetrics (summary, to_dict, is_valid)
- validation/preflight.py: PreflightResult (error_count, warning_count, info_count, merge)
- io/provenance.py: Provenance.as_comment
- testing/quarantine.py: QuarantineEntry.to_dict/to_json, classify_error
- testing/golden_diff.py: DiffReport.to_json
- heuristics/organizational.py: classify_signal_domains, classify_power_topology
- heuristics/style.py: identify_ground_domains
- heuristics/structural.py: identify_connectors, identify_thermal_components
- heuristics/pipeline.py: HeuristicPipeline.register, clear, register_all
- constraints/builder.py: ConstraintBuilder (add_spacing, build)
"""

from __future__ import annotations

import pytest

# ===========================================================================
# constraints/reporter.py — ConstraintResult and ConstraintReport
# ===========================================================================


class TestConstraintResult:
    """Covers ConstraintResult.is_violation, ConstraintResult.is_warning."""

    def test_is_violation_true(self):
        from temper_placer.constraints.reporter import ConstraintResult, ConstraintStatus

        cr = ConstraintResult(
            constraint_type="ComponentSpacing",
            status=ConstraintStatus.VIOLATED,
            tier="hard",
            components=["U1", "Q1"],
            message="Too close",
        )
        assert cr.is_violation() is True

    def test_is_violation_false_soft(self):
        from temper_placer.constraints.reporter import ConstraintResult, ConstraintStatus

        cr = ConstraintResult(
            constraint_type="Proximity",
            status=ConstraintStatus.VIOLATED,
            tier="soft",
            components=["U1"],
            message="Suboptimal proximity",
        )
        assert cr.is_violation() is False

    def test_is_violation_false_satisfied(self):
        from temper_placer.constraints.reporter import ConstraintResult, ConstraintStatus

        cr = ConstraintResult(
            constraint_type="Spacing",
            status=ConstraintStatus.SATISFIED,
            tier="hard",
            components=["U1", "Q1"],
            message="OK",
        )
        assert cr.is_violation() is False

    def test_is_warning_true(self):
        from temper_placer.constraints.reporter import ConstraintResult, ConstraintStatus

        cr = ConstraintResult(
            constraint_type="Proximity",
            status=ConstraintStatus.VIOLATED,
            tier="soft",
            components=["U1"],
            message="Warning",
        )
        assert cr.is_warning() is True

    def test_is_warning_false_hard(self):
        from temper_placer.constraints.reporter import ConstraintResult, ConstraintStatus

        cr = ConstraintResult(
            constraint_type="Spacing",
            status=ConstraintStatus.VIOLATED,
            tier="hard",
            components=["U1", "Q1"],
            message="Hard fail",
        )
        assert cr.is_warning() is False


class TestConstraintReport:
    """Covers ConstraintReport.violations, warnings, satisfied,
    hard_results, soft_results, has_violations."""

    def _make_result(self, constraint_type, status_value, tier):
        from temper_placer.constraints.reporter import ConstraintResult, ConstraintStatus

        status = ConstraintStatus(status_value)
        return ConstraintResult(
            constraint_type=constraint_type,
            status=status,
            tier=tier,
            components=[],
            message="test",
        )

    def test_violations(self):
        from temper_placer.constraints.reporter import ConstraintReport

        report = ConstraintReport(
            results=[
                self._make_result("Spacing", "violated", "hard"),
                self._make_result("Proximity", "satisfied", "soft"),
                self._make_result("Clearance", "violated", "hard"),
                self._make_result("Thermal", "violated", "soft"),
            ]
        )
        assert len(report.violations) == 2

    def test_warnings(self):
        from temper_placer.constraints.reporter import ConstraintReport

        report = ConstraintReport(
            results=[
                self._make_result("Spacing", "violated", "hard"),
                self._make_result("Proximity", "violated", "soft"),
                self._make_result("Thermal", "violated", "soft"),
            ]
        )
        assert len(report.warnings) == 2

    def test_satisfied(self):
        from temper_placer.constraints.reporter import ConstraintReport

        report = ConstraintReport(
            results=[
                self._make_result("Spacing", "satisfied", "hard"),
                self._make_result("Proximity", "violated", "soft"),
                self._make_result("Clearance", "satisfied", "hard"),
            ]
        )
        assert len(report.satisfied) == 2

    def test_hard_results(self):
        from temper_placer.constraints.reporter import ConstraintReport

        report = ConstraintReport(
            results=[
                self._make_result("A", "satisfied", "hard"),
                self._make_result("B", "violated", "soft"),
                self._make_result("C", "violated", "hard"),
            ]
        )
        assert len(report.hard_results) == 2

    def test_soft_results(self):
        from temper_placer.constraints.reporter import ConstraintReport

        report = ConstraintReport(
            results=[
                self._make_result("A", "satisfied", "hard"),
                self._make_result("B", "violated", "soft"),
                self._make_result("C", "satisfied", "soft"),
            ]
        )
        assert len(report.soft_results) == 2

    def test_has_violations_true(self):
        from temper_placer.constraints.reporter import ConstraintReport

        report = ConstraintReport(
            results=[self._make_result("Spacing", "violated", "hard")]
        )
        assert report.has_violations() is True

    def test_has_violations_false(self):
        from temper_placer.constraints.reporter import ConstraintReport

        report = ConstraintReport(
            results=[
                self._make_result("Spacing", "satisfied", "hard"),
                self._make_result("Proximity", "violated", "soft"),
            ]
        )
        assert report.has_violations() is False


# ===========================================================================
# validation/metrics.py — PlacementMetrics summary, to_dict, is_valid
# ===========================================================================


class TestPlacementMetrics:
    """Covers PlacementMetrics.summary, PlacementMetrics.to_dict,
    PlacementMetrics.is_valid."""

    def test_is_valid_clean(self):
        from temper_placer.validation.metrics import PlacementMetrics

        m = PlacementMetrics(
            overlap_count=0,
            boundary_violations=0,
            hv_lv_violations=0,
            keepout_violations=0,
        )
        assert m.is_valid is True

    def test_is_valid_with_overlap(self):
        from temper_placer.validation.metrics import PlacementMetrics

        m = PlacementMetrics(overlap_count=1)
        assert m.is_valid is False

    def test_is_valid_with_boundary(self):
        from temper_placer.validation.metrics import PlacementMetrics

        m = PlacementMetrics(boundary_violations=3)
        assert m.is_valid is False

    def test_is_valid_with_hv_lv(self):
        from temper_placer.validation.metrics import PlacementMetrics

        m = PlacementMetrics(hv_lv_violations=5)
        assert m.is_valid is False

    def test_is_valid_with_keepout(self):
        from temper_placer.validation.metrics import PlacementMetrics

        m = PlacementMetrics(keepout_violations=2)
        assert m.is_valid is False

    def test_summary(self):
        from temper_placer.validation.metrics import PlacementMetrics

        m = PlacementMetrics(
            overlap_count=1,
            total_overlap_area=25.0,
            boundary_violations=2,
            clearance_violations=3,
            hv_lv_violations=1,
            zone_violations=0,
            keepout_violations=0,
            total_wirelength=150.0,
            avg_net_length=15.0,
            utilization=0.45,
        )
        s = m.summary()
        assert "Placement Metrics" in s
        assert "Overlaps" in s
        assert "Boundary violations" in s
        assert "Wirelength" in s
        assert "Utilization" in s

    def test_to_dict(self):
        from temper_placer.validation.metrics import PlacementMetrics

        m = PlacementMetrics(
            overlap_count=0,
            total_overlap_area=0.0,
            worst_overlap=0.0,
            boundary_violations=0,
            total_boundary_violation=0.0,
            clearance_violations=2,
            hv_lv_violations=1,
            min_hv_lv_clearance=15.0,
            zone_violations=0,
            keepout_violations=0,
            total_wirelength=42.0,
            max_net_length=10.0,
            avg_net_length=5.0,
            max_congestion=0.1,
            avg_congestion=0.05,
            utilization=0.3,
            spread_score=0.7,
            center_of_mass=(50.0, 50.0),
            computation_time_ms=123.4,
        )
        d = m.to_dict()
        assert d["overlap_count"] == 0
        assert d["clearance_violations"] == 2
        assert d["total_wirelength"] == 42.0
        assert d["center_of_mass"] == (50.0, 50.0)
        assert d["computation_time_ms"] == 123.4

    def test_to_dict_inf_clearance(self):
        from temper_placer.validation.metrics import PlacementMetrics

        m = PlacementMetrics(min_hv_lv_clearance=float("inf"))
        d = m.to_dict()
        assert d["min_hv_lv_clearance"] is None


# ===========================================================================
# validation/preflight.py — PreflightResult properties
# ===========================================================================


class TestPreflightResult:
    """Covers PreflightResult.error_count, warning_count, info_count, merge."""

    def test_error_count(self):
        from temper_placer.validation.preflight import (
            PreflightIssue,
            PreflightResult,
            PreflightSeverity,
        )

        pr = PreflightResult(
            passed=False,
            issues=[
                PreflightIssue(severity=PreflightSeverity.ERROR, code="E1", message="err"),
                PreflightIssue(severity=PreflightSeverity.WARNING, code="W1", message="warn"),
                PreflightIssue(severity=PreflightSeverity.ERROR, code="E2", message="err2"),
            ],
        )
        assert pr.error_count == 2

    def test_warning_count(self):
        from temper_placer.validation.preflight import (
            PreflightIssue,
            PreflightResult,
            PreflightSeverity,
        )

        pr = PreflightResult(
            passed=False,
            issues=[
                PreflightIssue(severity=PreflightSeverity.WARNING, code="W1", message="warn"),
                PreflightIssue(severity=PreflightSeverity.WARNING, code="W2", message="warn2"),
                PreflightIssue(severity=PreflightSeverity.ERROR, code="E1", message="err"),
            ],
        )
        assert pr.warning_count == 2

    def test_info_count(self):
        from temper_placer.validation.preflight import (
            PreflightIssue,
            PreflightResult,
            PreflightSeverity,
        )

        pr = PreflightResult(
            passed=True,
            issues=[
                PreflightIssue(severity=PreflightSeverity.INFO, code="I1", message="info"),
                PreflightIssue(severity=PreflightSeverity.INFO, code="I2", message="info2"),
                PreflightIssue(severity=PreflightSeverity.ERROR, code="E1", message="err"),
            ],
        )
        assert pr.info_count == 2

    def test_merge_combines_issues(self):
        from temper_placer.validation.preflight import (
            PreflightIssue,
            PreflightResult,
            PreflightSeverity,
        )

        a = PreflightResult(
            passed=True,
            issues=[
                PreflightIssue(severity=PreflightSeverity.WARNING, code="W1", message="w1"),
            ],
        )
        b = PreflightResult(
            passed=False,  # ERROR-level issues mean passed=False
            issues=[
                PreflightIssue(severity=PreflightSeverity.ERROR, code="E1", message="e1"),
            ],
        )
        merged = a.merge(b)
        assert len(merged.issues) == 2
        # merge sets passed = self.passed AND other.passed
        assert merged.passed is False

    def test_merge_passes_both_pass(self):
        from temper_placer.validation.preflight import (
            PreflightIssue,
            PreflightResult,
            PreflightSeverity,
        )

        a = PreflightResult(
            passed=True,
            issues=[
                PreflightIssue(severity=PreflightSeverity.INFO, code="I1", message="info"),
            ],
        )
        b = PreflightResult(
            passed=True,
            issues=[
                PreflightIssue(severity=PreflightSeverity.WARNING, code="W1", message="warn"),
            ],
        )
        merged = a.merge(b)
        assert merged.passed is True


# ===========================================================================
# io/provenance.py — Provenance.as_comment
# ===========================================================================


class TestProvenance:
    """Covers Provenance.as_comment."""

    def test_as_comment_full(self):
        from temper_placer.io.provenance import Provenance

        p = Provenance(
            board_sha256="abc123",
            netlist_sha256="def456",
            config_sha256="ghi789",
            generated_at="2024-01-01T00:00:00+00:00",
        )
        comment = p.as_comment()
        assert "board=abc123" in comment
        assert "netlist=def456" in comment
        assert "config=ghi789" in comment
        assert "at=2024-01-01" in comment

    def test_as_comment_no_config(self):
        from temper_placer.io.provenance import Provenance

        p = Provenance(
            board_sha256="abc123",
            netlist_sha256="def456",
            config_sha256=None,
            generated_at="2024-01-01T00:00:00+00:00",
        )
        comment = p.as_comment()
        assert "config=" not in comment
        assert "board=abc123" in comment
        assert "netlist=def456" in comment


# ===========================================================================
# testing/quarantine.py — QuarantineEntry.to_dict/to_json, classify_error
# ===========================================================================


class TestQuarantineEntry:
    """Covers QuarantineEntry.to_dict, QuarantineEntry.to_json."""

    def test_to_dict(self):
        from temper_placer.testing.quarantine import QuarantineEntry

        entry = QuarantineEntry(
            board_id="BOARD_01",
            board_path="/tmp/test.kicad_pcb",
            stage="parse",
            error_class="ValueError",
            error_message="something broke",
            stack_hash="abc123",
            taxonomy="PARSE_DECODE_ERROR",
            git_commit="def456",
        )
        d = entry.to_dict()
        assert d["board_id"] == "BOARD_01"
        assert d["stage"] == "parse"
        assert d["error_class"] == "ValueError"
        assert d["taxonomy"] == "PARSE_DECODE_ERROR"
        # taxonomy_label should be populated from TAXONOMY_CLASSES
        assert "taxonomy_label" in d
        assert len(d["taxonomy_label"]) > 0

    def test_to_json(self):
        from temper_placer.testing.quarantine import QuarantineEntry

        entry = QuarantineEntry(
            board_id="BOARD_01",
            board_path="/tmp/test.kicad_pcb",
            stage="parse",
            error_class="ValueError",
            error_message="something broke",
            stack_hash="abc123",
        )
        j = entry.to_json()
        assert "BOARD_01" in j
        assert "ValueError" in j


class TestClassifyError:
    """Covers classify_error for various taxonomy branches."""

    def test_parse_version_mismatch(self):
        from temper_placer.testing.quarantine import classify_error

        class MockErr(Exception):
            pass

        err = MockErr("KiCad version 5.99 is not supported")
        result = classify_error("parse", err)
        assert result == "PARSE_KICAD_VERSION_MISMATCH"

    def test_parse_decode_error(self):
        from temper_placer.testing.quarantine import classify_error

        class MockErr(Exception):
            pass

        err = MockErr("utf-8 decode error in file")
        result = classify_error("parse", err)
        assert result == "PARSE_DECODE_ERROR"

    def test_parse_empty_board(self):
        from temper_placer.testing.quarantine import classify_error

        class MockErr(Exception):
            pass

        err = MockErr("zero components found in board")
        result = classify_error("parse", err)
        assert result == "PARSE_EMPTY_BOARD"

    def test_parse_unknown(self):
        from temper_placer.testing.quarantine import classify_error

        class MockErr(Exception):
            pass

        err = MockErr("some random parse error")
        result = classify_error("parse", err)
        assert result == "PARSE_UNKNOWN"

    def test_stage_preflight_failed(self):
        from temper_placer.testing.quarantine import classify_error

        class MockErr(Exception):
            pass

        err = MockErr("preflight check failed")
        result = classify_error("preflight", err)
        assert result == "STAGE_PREFLIGHT_FAILED"

    def test_stage_routing_failed(self):
        from temper_placer.testing.quarantine import classify_error

        class MockErr(Exception):
            pass

        err = MockErr("routing failed for board")
        result = classify_error("routing", err)
        assert result == "STAGE_ROUTING_FAILED"

    def test_invariant_broken(self):
        from temper_placer.testing.quarantine import classify_error

        class MockErr(Exception):
            pass

        # Any non-recognised stage falls through to UNKNOWN
        err = MockErr("invariant violated: overlap detected")
        result = classify_error("invariant_check", err)
        assert result == "UNKNOWN"

    def test_stage_unknown(self):
        from temper_placer.testing.quarantine import classify_error

        class MockErr(Exception):
            pass

        err = MockErr("some random placement error")
        result = classify_error("placement", err)
        assert result == "UNKNOWN"


# ===========================================================================
# testing/golden_diff.py — DiffReport.to_json
# ===========================================================================


class TestDiffReport:
    """Covers DiffReport.to_json."""

    def test_to_json_empty(self):
        from temper_placer.testing.golden_diff import DiffReport

        report = DiffReport(board="test_board", stage="drc", passed=True)
        result = report.to_json()
        assert result == []

    def test_to_json_with_entries(self):
        from temper_placer.testing.golden_diff import DiffEntry, DiffReport

        entry = DiffEntry(
            board="test_board",
            stage="drc",
            category="BINARY",
            entity="net 'HV_IN'",
            field="presence",
            golden_value="present",
            candidate_value="missing",
        )
        report = DiffReport(
            board="test_board", stage="drc", passed=False, entries=[entry]
        )
        result = report.to_json()
        assert len(result) == 1
        assert result[0]["entity"] == "net 'HV_IN'"
        assert result[0]["category"] == "BINARY"


# ===========================================================================
# heuristics/organizational.py — classify_signal_domains, classify_power_topology
# ===========================================================================


class TestClassifySignalDomains:
    """Covers classify_signal_domains."""

    def test_digital_default(self):
        from temper_placer.core.netlist import Component, Netlist
        from temper_placer.heuristics.organizational import classify_signal_domains
        from temper_placer.io.config_loader import PlacementConstraints

        comps = [Component(ref="U_UNKNOWN", footprint="QFP-100", bounds=(10, 10))]
        netlist = Netlist(components=comps, nets=[])
        constraints = PlacementConstraints()
        domains = classify_signal_domains(netlist, constraints)
        assert domains["U_UNKNOWN"] == "digital"

    def test_power_patterns(self):
        from temper_placer.core.netlist import Component, Netlist
        from temper_placer.heuristics.organizational import classify_signal_domains
        from temper_placer.io.config_loader import PlacementConstraints

        comps = [
            Component(ref="Q1", footprint="TO-220", bounds=(10, 5)),
            Component(ref="U_BUCK_1", footprint="QFN-16", bounds=(4, 4)),
            Component(ref="U_GATE_DRV", footprint="SOIC-8", bounds=(5, 4)),
            Component(ref="L1", footprint="IND_10MM", bounds=(10, 10)),
        ]
        netlist = Netlist(components=comps, nets=[])
        constraints = PlacementConstraints()
        domains = classify_signal_domains(netlist, constraints)
        # All should be "power"
        for comp in comps:
            assert domains[comp.ref] == "power", f"{comp.ref} should be power"

    def test_analog_patterns(self):
        from temper_placer.core.netlist import Component, Netlist
        from temper_placer.heuristics.organizational import classify_signal_domains
        from temper_placer.io.config_loader import PlacementConstraints

        comps = [
            Component(ref="U_OPAMP_1", footprint="SOIC-8", bounds=(5, 4)),
            Component(ref="U_ADC_1", footprint="QFN-24", bounds=(4, 4)),
            Component(ref="U_SENS_1", footprint="SOT23", bounds=(3, 3)),
        ]
        netlist = Netlist(components=comps, nets=[])
        constraints = PlacementConstraints()
        domains = classify_signal_domains(netlist, constraints)
        for comp in comps:
            assert domains[comp.ref] == "analog", f"{comp.ref} should be analog"

    def test_digital_patterns(self):
        from temper_placer.core.netlist import Component, Netlist
        from temper_placer.heuristics.organizational import classify_signal_domains
        from temper_placer.io.config_loader import PlacementConstraints

        comps = [
            Component(ref="U_MCU_MAIN", footprint="QFP-100", bounds=(10, 10)),
            Component(ref="U_FLASH_1", footprint="SOIC-8", bounds=(5, 4)),
        ]
        netlist = Netlist(components=comps, nets=[])
        constraints = PlacementConstraints()
        domains = classify_signal_domains(netlist, constraints)
        for comp in comps:
            assert domains[comp.ref] == "digital", f"{comp.ref} should be digital"

    def test_net_name_classification(self):
        from temper_placer.core.netlist import Component, Net, Netlist
        from temper_placer.heuristics.organizational import classify_signal_domains
        from temper_placer.io.config_loader import PlacementConstraints

        # A regular component with an analog net name
        comps = [
            Component(ref="R1", footprint="0603", bounds=(2, 1)),
            Component(ref="U_X", footprint="QFN-16", bounds=(4, 4)),
        ]
        nets = [
            Net("ANALOG_IN", [("R1", "1"), ("U_X", "1")]),
        ]
        netlist = Netlist(components=comps, nets=nets)
        constraints = PlacementConstraints()
        domains = classify_signal_domains(netlist, constraints)
        # R1 should be reclassified to analog via net name
        assert domains["R1"] == "analog"


class TestClassifyPowerTopology:
    """Covers classify_power_topology."""

    def test_input_components(self):
        from temper_placer.core.netlist import Component, Netlist
        from temper_placer.heuristics.organizational import classify_power_topology
        from temper_placer.io.config_loader import PlacementConstraints

        comps = [
            Component(ref="J_DC_IN", footprint="CONN_2P", bounds=(10, 5)),
            Component(ref="F1", footprint="FUSE_5x20", bounds=(20, 5)),
            Component(ref="C_BULK_1", footprint="CAP_10MM", bounds=(10, 10)),
        ]
        netlist = Netlist(components=comps, nets=[])
        constraints = PlacementConstraints()
        nodes = classify_power_topology(netlist, constraints)
        assert len(nodes) >= 2  # J_DC_IN and F1 should be input
        for node in nodes:
            if node.ref in ("J_DC_IN", "F1", "C_BULK_1"):
                assert node.role == "input", f"{node.ref} should be input"
                assert node.stage == 0

    def test_distribution(self):
        from temper_placer.core.netlist import Component, Netlist
        from temper_placer.heuristics.organizational import classify_power_topology
        from temper_placer.io.config_loader import PlacementConstraints

        comps = [
            Component(ref="U_BUCK_1", footprint="QFN-16", bounds=(4, 4)),
            Component(ref="U_LDO_1", footprint="SOT223", bounds=(6, 3)),
            Component(ref="L1", footprint="IND_10MM", bounds=(10, 10)),
        ]
        netlist = Netlist(components=comps, nets=[])
        constraints = PlacementConstraints()
        nodes = classify_power_topology(netlist, constraints)
        for node in nodes:
            if node.ref in ("U_BUCK_1", "U_LDO_1", "L1"):
                assert node.role == "distribution", f"{node.ref} should be distribution"
                assert node.stage == 1

    def test_load_components(self):
        from temper_placer.core.netlist import Component, Netlist
        from temper_placer.heuristics.organizational import classify_power_topology
        from temper_placer.io.config_loader import PlacementConstraints

        comps = [
            Component(ref="U_MCU_1", footprint="QFP-100", bounds=(10, 10)),
            Component(ref="U_GATE_A", footprint="SOIC-8", bounds=(5, 4)),
        ]
        netlist = Netlist(components=comps, nets=[])
        constraints = PlacementConstraints()
        nodes = classify_power_topology(netlist, constraints)
        for node in nodes:
            if node.ref in ("U_MCU_1", "U_GATE_A"):
                assert node.role == "load", f"{node.ref} should be load"
                assert node.stage == 2

    def test_skips_fixed_components(self):
        from temper_placer.core.netlist import Component, Netlist
        from temper_placer.heuristics.organizational import classify_power_topology
        from temper_placer.io.config_loader import PlacementConstraints

        comps = [
            Component(ref="Q1", footprint="TO-220", bounds=(10, 5), fixed=True),
            Component(ref="U_BUCK", footprint="QFN-16", bounds=(4, 4), fixed=True),
        ]
        netlist = Netlist(components=comps, nets=[])
        constraints = PlacementConstraints()
        nodes = classify_power_topology(netlist, constraints)
        # Fixed components should be skipped
        assert len(nodes) == 0

    def test_skips_passives_without_role(self):
        from temper_placer.core.netlist import Component, Netlist
        from temper_placer.heuristics.organizational import classify_power_topology
        from temper_placer.io.config_loader import PlacementConstraints

        # Passives (R*, C* without special patterns) default to load stage 2
        # but are excluded from nodes unless they start with "U"
        comps = [
            Component(ref="R42", footprint="0603", bounds=(2, 1)),
            Component(ref="C17", footprint="0603", bounds=(2, 1)),
        ]
        netlist = Netlist(components=comps, nets=[])
        constraints = PlacementConstraints()
        nodes = classify_power_topology(netlist, constraints)
        # These passives default to load role but don't start with U, so excluded
        assert len(nodes) == 0


# ===========================================================================
# heuristics/style.py — identify_ground_domains
# ===========================================================================


class TestIdentifyGroundDomains:
    """Covers identify_ground_domains."""

    def test_power_ground_patterns(self):
        from temper_placer.core.netlist import Component, Netlist
        from temper_placer.heuristics.style import identify_ground_domains
        from temper_placer.io.config_loader import PlacementConstraints

        comps = [
            Component(ref="Q1", footprint="TO-220", bounds=(10, 5)),
            Component(ref="U_GATEA", footprint="SOIC-8", bounds=(5, 4)),
            Component(ref="L1", footprint="IND_10MM", bounds=(10, 10)),
        ]
        netlist = Netlist(components=comps, nets=[])
        constraints = PlacementConstraints()
        domains = identify_ground_domains(netlist, constraints)
        for comp in comps:
            assert domains[comp.ref] == "PGND", f"{comp.ref} should be PGND"

    def test_analog_ground_patterns(self):
        from temper_placer.core.netlist import Component, Netlist
        from temper_placer.heuristics.style import identify_ground_domains
        from temper_placer.io.config_loader import PlacementConstraints

        comps = [
            Component(ref="U_OPAMP1", footprint="SOIC-8", bounds=(5, 4)),
            Component(ref="U_TEMP1", footprint="SOT23", bounds=(3, 3)),
        ]
        netlist = Netlist(components=comps, nets=[])
        constraints = PlacementConstraints()
        domains = identify_ground_domains(netlist, constraints)
        for comp in comps:
            assert domains[comp.ref] == "AGND", f"{comp.ref} should be AGND"

    def test_digital_ground_patterns(self):
        from temper_placer.core.netlist import Component, Netlist
        from temper_placer.heuristics.style import identify_ground_domains
        from temper_placer.io.config_loader import PlacementConstraints

        comps = [
            Component(ref="U_MCU1", footprint="QFP-100", bounds=(10, 10)),
            Component(ref="U_FLASH", footprint="SOIC-8", bounds=(5, 4)),
            Component(ref="Y1", footprint="XTAL", bounds=(3, 1)),
        ]
        netlist = Netlist(components=comps, nets=[])
        constraints = PlacementConstraints()
        domains = identify_ground_domains(netlist, constraints)
        for comp in comps:
            assert domains[comp.ref] == "DGND", f"{comp.ref} should be DGND"

    def test_default_digital(self):
        from temper_placer.core.netlist import Component, Netlist
        from temper_placer.heuristics.style import identify_ground_domains
        from temper_placer.io.config_loader import PlacementConstraints

        comps = [Component(ref="R42", footprint="0603", bounds=(2, 1))]
        netlist = Netlist(components=comps, nets=[])
        constraints = PlacementConstraints()
        domains = identify_ground_domains(netlist, constraints)
        assert domains["R42"] == "DGND"

    def test_net_name_overrides(self):
        from temper_placer.core.netlist import Component, Net, Netlist
        from temper_placer.heuristics.style import identify_ground_domains
        from temper_placer.io.config_loader import PlacementConstraints

        comps = [Component(ref="R1", footprint="0603", bounds=(2, 1))]
        nets = [Net("PGND", [("R1", "1")])]
        netlist = Netlist(components=comps, nets=nets)
        constraints = PlacementConstraints()
        domains = identify_ground_domains(netlist, constraints)
        assert domains["R1"] == "PGND"


# ===========================================================================
# heuristics/structural.py — identify_connectors, identify_thermal_components
# ===========================================================================


class TestIdentifyConnectors:
    """Covers identify_connectors."""

    def test_by_reference_pattern(self):
        from temper_placer.core.netlist import Component, Netlist
        from temper_placer.heuristics.structural import identify_connectors
        from temper_placer.io.config_loader import PlacementConstraints

        comps = [
            Component(ref="J1", footprint="CONN_2", bounds=(10, 5)),
            Component(ref="P1", footprint="CONN_3", bounds=(10, 5)),
            Component(ref="CON1", footprint="HEADER_10", bounds=(20, 5)),
        ]
        netlist = Netlist(components=comps, nets=[])
        constraints = PlacementConstraints()
        connectors = identify_connectors(netlist, constraints)
        assert len(connectors) == 3

    def test_by_footprint(self):
        from temper_placer.core.netlist import Component, Netlist
        from temper_placer.heuristics.structural import identify_connectors
        from temper_placer.io.config_loader import PlacementConstraints

        comps = [
            Component(ref="U_ADAPTER", footprint="USB_C_CONN", bounds=(8, 3)),
        ]
        netlist = Netlist(components=comps, nets=[])
        constraints = PlacementConstraints()
        connectors = identify_connectors(netlist, constraints)
        assert len(connectors) == 1

    def test_classify_power_input(self):
        from temper_placer.core.netlist import Component, Netlist
        from temper_placer.heuristics.structural import identify_connectors
        from temper_placer.io.config_loader import PlacementConstraints

        comps = [Component(ref="J_DC_IN", footprint="BARREL_JACK", bounds=(10, 8))]
        netlist = Netlist(components=comps, nets=[])
        constraints = PlacementConstraints()
        connectors = identify_connectors(netlist, constraints)
        assert len(connectors) == 1
        _, purpose = connectors[0]
        assert purpose == "power_input"

    def test_classify_debug(self):
        from temper_placer.core.netlist import Component, Netlist
        from temper_placer.heuristics.structural import identify_connectors
        from temper_placer.io.config_loader import PlacementConstraints

        comps = [Component(ref="J_DEBUG", footprint="HEADER_6", bounds=(15, 5))]
        netlist = Netlist(components=comps, nets=[])
        constraints = PlacementConstraints()
        connectors = identify_connectors(netlist, constraints)
        assert len(connectors) == 1
        _, purpose = connectors[0]
        assert purpose == "debug"


class TestIdentifyThermalComponents:
    """Covers identify_thermal_components."""

    def test_by_reference_pattern(self):
        from temper_placer.core.netlist import Component, Netlist
        from temper_placer.heuristics.structural import identify_thermal_components
        from temper_placer.io.config_loader import PlacementConstraints

        comps = [
            Component(ref="Q1", footprint="TO-220", bounds=(10, 5)),
            Component(ref="Q2", footprint="TO-220", bounds=(10, 5)),
        ]
        netlist = Netlist(components=comps, nets=[])
        constraints = PlacementConstraints()
        thermal = identify_thermal_components(netlist, constraints)
        assert len(thermal) == 2

    def test_by_footprint(self):
        from temper_placer.core.netlist import Component, Netlist
        from temper_placer.heuristics.structural import identify_thermal_components
        from temper_placer.io.config_loader import PlacementConstraints

        comps = [
            Component(ref="U_REG_1", footprint="D2PAK", bounds=(10, 10)),
        ]
        netlist = Netlist(components=comps, nets=[])
        constraints = PlacementConstraints()
        thermal = identify_thermal_components(netlist, constraints)
        assert len(thermal) == 1

    def test_from_config_thermal_properties(self):
        from temper_placer.core.netlist import Component, Netlist
        from temper_placer.heuristics.structural import identify_thermal_components
        from temper_placer.io.config_loader import PlacementConstraints

        comps = [Component(ref="R_HEAT", footprint="0603", bounds=(2, 1))]
        netlist = Netlist(components=comps, nets=[])

        from temper_placer._constraint_types import ThermalProperties
        constraints = PlacementConstraints(
            thermal_properties=ThermalProperties(
                high_power_components=["R_HEAT"],
                thermal_pad_components=["R_HEAT"],
            )
        )
        thermal = identify_thermal_components(netlist, constraints)
        assert len(thermal) == 1

    def test_excludes_fixed(self):
        from temper_placer.core.netlist import Component, Netlist
        from temper_placer.heuristics.structural import identify_thermal_components
        from temper_placer.io.config_loader import PlacementConstraints

        comps = [
            Component(ref="Q1", footprint="TO-220", bounds=(10, 5), fixed=True),
        ]
        netlist = Netlist(components=comps, nets=[])
        constraints = PlacementConstraints()
        thermal = identify_thermal_components(netlist, constraints)
        assert len(thermal) == 0


# ===========================================================================
# heuristics/pipeline.py — HeuristicPipeline basic operations
# ===========================================================================


class TestHeuristicPipeline:
    """Covers HeuristicPipeline.register, clear, register_all."""

    def test_register_and_clear(self):
        from temper_placer.core.board import Board
        from temper_placer.core.netlist import Component, Netlist
        from temper_placer.heuristics.base import (
            Heuristic,
            HeuristicPriority,
            HeuristicResult,
            PlacementContext,
        )
        from temper_placer.heuristics.pipeline import HeuristicPipeline
        from temper_placer.io.config_loader import PlacementConstraints

        class DummyHeuristic(Heuristic):
            @property
            def name(self) -> str:
                return "dummy"

            @property
            def priority(self) -> HeuristicPriority:
                return HeuristicPriority.FILL

            def apply(self, context):
                return HeuristicResult(success=True)

        pipeline = HeuristicPipeline()
        h = DummyHeuristic()
        pipeline.register(h)
        # get_registered_heuristics returns list[tuple[str, HeuristicPriority]]
        registered = pipeline.get_registered_heuristics()
        assert ("dummy", HeuristicPriority.FILL) in registered

        pipeline.clear()
        registered = pipeline.get_registered_heuristics()
        assert len(registered) == 0

    def test_register_all(self):
        from temper_placer.heuristics.pipeline import HeuristicPipeline
        from temper_placer.heuristics.organizational import (
            DecouplingCapHeuristic,
            DomainSeparationHeuristic,
            FunctionalModuleClusteringHeuristic,
        )
        from temper_placer.heuristics.structural import (
            ConnectorEdgeSnappingHeuristic,
            CriticalLoopHeuristic,
            KeepoutAwarenessHeuristic,
            ThermalEdgePlacementHeuristic,
        )
        from temper_placer.heuristics.style import (
            SignalFlowPreservationHeuristic,
            StarGroundTopologyHeuristic,
        )

        pipeline = HeuristicPipeline()
        # Register a set of heuristics
        heuristics = [
            KeepoutAwarenessHeuristic(),
            ConnectorEdgeSnappingHeuristic(),
            ThermalEdgePlacementHeuristic(),
            CriticalLoopHeuristic(),
            FunctionalModuleClusteringHeuristic(),
            DecouplingCapHeuristic(),
            DomainSeparationHeuristic(),
            StarGroundTopologyHeuristic(),
            SignalFlowPreservationHeuristic(),
        ]
        pipeline.register_all(heuristics)
        registered = pipeline.get_registered_heuristics()
        # All should be registered
        assert len(registered) == len(heuristics)


# ===========================================================================
# constraints/builder.py — ConstraintBuilder add_spacing, build
# ===========================================================================


class TestConstraintBuilder:
    """Covers ConstraintBuilder.add_spacing, ConstraintBuilder.build."""

    def test_add_spacing_and_build(self):
        from temper_placer.constraints.builder import ConstraintBuilder

        builder = ConstraintBuilder()
        result = builder.add_spacing("U1", "Q1", 15.0, tier="hard")
        # Returns self for chaining
        assert result is builder
        constraints = builder.build()
        assert constraints is not None
        assert len(constraints.component_spacing_rules) == 1
        assert constraints.component_spacing_rules[0].component_a == "U1"
        assert constraints.component_spacing_rules[0].component_b == "Q1"
        assert constraints.component_spacing_rules[0].min_separation_mm == 15.0

    def test_empty_build(self):
        from temper_placer.constraints.builder import ConstraintBuilder

        builder = ConstraintBuilder()
        constraints = builder.build()
        assert constraints is not None
        assert len(constraints.component_spacing_rules) == 0
