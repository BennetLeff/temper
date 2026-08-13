"""Tests for check_netclass_class_param_correspondence.py.

Companion to test_check_hv_netclass_coverage.py and
test_check_netclass_map_board_correspondence.py -- same family, same
idiom. See docs/evidence/2026-08-12-gate-vacuity-structural-prevention.md
for the real defect this gate closes: PR #1023 and PR #1025 both claimed
to sync pcb/temper.kicad_pro against design_rules.py's TEMPER_NET_CLASSES
but only ever touched netclass_assignments (which net maps to which
class); neither PR, and no gate before this one, ever compared a class's
own parameter values (clearance, trace width, via diameter, via drill)
between the two tables. ``HighVoltage.clearance`` disagrees on
``origin/main`` right now: 6.0 (design_rules.py) vs. 2.0 (kicad_pro).

``run()`` accepts ``net_classes`` / ``kicad_pro_classes`` overrides for
exactly the reason ``check_hv_netclass_coverage.py``'s own tests use the
same pattern: a gate test should never depend on live repo state to prove
a specific mutation is caught.

Four groups:

1. ``TestMutations`` -- inject a single-field mismatch (mirroring the real
   HighVoltage.clearance defect) and confirm the gate flags exactly it;
   confirm a fully-agreeing fixture is clean; confirm the gate is exactly
   sensitive to a single-field mutation (fixing it clears the violation,
   nothing else is affected).
2. ``TestAntiVacuity`` -- the gate fails CLOSED on every degenerate input:
   missing/malformed/empty kicad_pro, unimportable design_rules.py, zero
   classes shared by name.
3. ``TestHelperUnits`` -- unit tests for the pure helper functions.
4. ``TestRealRepoIntegration`` -- the gate's verdict against the actual
   repo as of this commit is a VIOLATION (not a tool error, not a false
   clean) -- pins the exact 5 mismatches this task discovered, so a future
   fix to any one of them must touch this test too, not silently go
   green.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_netclass_class_param_correspondence import (  # noqa: E402
    _KNOWN_UNRESOLVED_ASSIGNMENTS,
    EXIT_GATE_ERROR,
    EXIT_OK,
    EXIT_VIOLATION,
    FIELD_MAP,
    GateError,
    check_referenced_classes_exist,
    compare_class_params,
    load_kicad_pro_class_params,
    run,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


class _FakeNetClassRules:
    """Minimal stand-in for NetClassRules: the gate reads only the four
    scalar routing field attributes named in FIELD_MAP."""

    def __init__(self, clearance, trace_width, via_diameter, via_drill):
        self.clearance = clearance
        self.trace_width = trace_width
        self.via_diameter = via_diameter
        self.via_drill = via_drill


def _kicad_pro(
    tmp_path: Path,
    classes: dict[str, dict[str, float]],
    name: str = "temper.kicad_pro",
) -> Path:
    """A minimal pcb/temper.kicad_pro fixture: net_settings.classes with
    the given {name: {json_field: value}} entries. Any field omitted from
    a class's dict is simply absent from that class's JSON entry (proving
    the gate's None-on-missing handling, not a KeyError)."""
    path = tmp_path / name
    entries = []
    for cls_name, fields in classes.items():
        entry = {"name": cls_name}
        entry.update(fields)
        entries.append(entry)
    path.write_text(json.dumps({"net_settings": {"classes": entries}}))
    return path


def _agreeing_fields(clearance=1.0, trace_width=0.5, via_diameter=0.6, via_drill=0.3):
    """Return (fake_net_class_rules, matching_kicad_pro_field_dict) that
    agree on all four scalar routing fields."""
    dr = _FakeNetClassRules(clearance, trace_width, via_diameter, via_drill)
    kc = {
        "clearance": clearance,
        "track_width": trace_width,
        "via_diameter": via_diameter,
        "via_drill": via_drill,
    }
    return dr, kc


# ---------------------------------------------------------------------------
# TestMutations
# ---------------------------------------------------------------------------


class TestMutations:
    def test_single_field_mismatch_is_flagged(self, tmp_path):
        """Falsifier: reconstructs the real HighVoltage.clearance defect
        shape -- one field disagrees, everything else matches."""
        dr_hv, kc_hv = _agreeing_fields(clearance=6.0)
        kc_hv["clearance"] = 2.0  # the real origin/main mismatch, in miniature

        kicad_pro = _kicad_pro(tmp_path, {"HighVoltage": kc_hv})
        # kicad_pro_classes not injected -> exercises the real JSON-load path
        state, report = run(
            kicad_pro,
            net_classes={"HighVoltage": dr_hv},
            net_assignments={"SOME_NET": "HighVoltage"},
        )
        assert state == "violation"
        assert len(report.mismatches) == 1
        m = report.mismatches[0]
        assert m.class_name == "HighVoltage"
        assert m.field_name == "clearance"
        assert m.design_rules_value == 6.0
        assert m.kicad_pro_value == 2.0

    def test_agreeing_class_is_not_flagged(self, tmp_path):
        """Control: a class that agrees on all four fields must not be
        flagged -- proves the gate doesn't false-positive."""
        dr, kc = _agreeing_fields()
        kicad_pro = _kicad_pro(tmp_path, {"Power": kc})
        state, report = run(
            kicad_pro, net_classes={"Power": dr}, net_assignments={"SOME_NET": "Power"}
        )
        assert state == "clean"
        assert report.mismatches == []
        assert report.classes_checked == ["Power"]

    def test_multiple_field_mismatches_on_one_class_all_reported(self, tmp_path):
        """Reconstructs the real Power-class defect shape: several fields
        on the SAME class disagree simultaneously -- all must be reported,
        not just the first."""
        dr = _FakeNetClassRules(clearance=0.25, trace_width=0.5, via_diameter=0.8, via_drill=0.4)
        kc = {
            "clearance": 0.5,
            "track_width": 1.0,
            "via_diameter": 1.0,
            "via_drill": 0.5,
        }
        kicad_pro = _kicad_pro(tmp_path, {"Power": kc})
        state, report = run(
            kicad_pro, net_classes={"Power": dr}, net_assignments={"SOME_NET": "Power"}
        )
        assert state == "violation"
        assert len(report.mismatches) == 4
        fields_flagged = {m.field_name for m in report.mismatches}
        assert fields_flagged == {"clearance", "trace_width", "via_diameter", "via_drill"}

    def test_class_only_in_design_rules_is_not_compared(self, tmp_path):
        """A class with no kicad_pro counterpart (e.g. Signal) has nothing
        to disagree with -- out of PROPERTY 1's scope, not a PROPERTY 1
        violation (unreferenced, so not a PROPERTY 2 violation either)."""
        dr, kc = _agreeing_fields()
        kicad_pro = _kicad_pro(tmp_path, {"Power": kc})
        state, report = run(
            kicad_pro,
            net_classes={"Power": dr, "Signal": _FakeNetClassRules(0.15, 0.2, 0.6, 0.3)},
            net_assignments={"SOME_NET": "Power"},
        )
        assert state == "clean"
        assert report.classes_checked == ["Power"]

    def test_class_only_in_kicad_pro_is_not_compared(self, tmp_path):
        """A class with no design_rules.py counterpart (e.g. Default) has
        nothing to disagree with -- out of this gate's scope."""
        dr, kc = _agreeing_fields()
        kicad_pro = _kicad_pro(tmp_path, {"Power": kc, "Default": kc})
        state, report = run(
            kicad_pro, net_classes={"Power": dr}, net_assignments={"SOME_NET": "Power"}
        )
        assert state == "clean"
        assert report.classes_checked == ["Power"]

    def test_missing_kicad_pro_field_is_flagged_against_none(self, tmp_path):
        """A field present on the design_rules.py side but entirely absent
        from the kicad_pro entry must be flagged, not silently skipped."""
        dr = _FakeNetClassRules(6.0, 3.0, 1.2, 0.6)
        kc = {"clearance": 6.0, "track_width": 3.0, "via_diameter": 1.2}  # via_drill omitted
        kicad_pro = _kicad_pro(tmp_path, {"HighVoltage": kc})
        state, report = run(
            kicad_pro, net_classes={"HighVoltage": dr}, net_assignments={"SOME_NET": "HighVoltage"}
        )
        assert state == "violation"
        assert len(report.mismatches) == 1
        assert report.mismatches[0].field_name == "via_drill"
        assert report.mismatches[0].kicad_pro_value is None

    def test_fixing_the_mismatch_clears_the_violation(self, tmp_path):
        """End-to-end mutation sensitivity: the exact same fixture, before
        and after correcting the one disagreeing field, flips the verdict
        and nothing else."""
        dr = _FakeNetClassRules(6.0, 3.0, 1.2, 0.6)
        kc_broken = {"clearance": 2.0, "track_width": 3.0, "via_diameter": 1.2, "via_drill": 0.6}
        kicad_pro_broken = _kicad_pro(tmp_path, {"HighVoltage": kc_broken}, name="broken.kicad_pro")
        state, report = run(
            kicad_pro_broken,
            net_classes={"HighVoltage": dr},
            net_assignments={"SOME_NET": "HighVoltage"},
        )
        assert state == "violation"

        kc_fixed = dict(kc_broken, clearance=6.0)
        kicad_pro_fixed = _kicad_pro(tmp_path, {"HighVoltage": kc_fixed}, name="fixed.kicad_pro")
        state, report = run(
            kicad_pro_fixed,
            net_classes={"HighVoltage": dr},
            net_assignments={"SOME_NET": "HighVoltage"},
        )
        assert state == "clean"
        assert report.mismatches == []


# ---------------------------------------------------------------------------
# TestReferencedClassExistence (PROPERTY 2)
# ---------------------------------------------------------------------------


class TestReferencedClassExistence:
    """Falsifiers for PROPERTY 2: reconstructs the real
    ``"gnd": "GND"`` / ``"PWR_RTN": "GND"`` shape -- a net assignment
    naming a class that is real Python-side data (a genuine, non-empty
    entry in ``net_classes``) but was never declared in
    ``pcb/temper.kicad_pro``. PROPERTY 1 alone cannot see this defect --
    it only ever compares classes both tables already agree are declared."""

    def test_assignment_naming_undeclared_kicad_pro_class_is_flagged(self, tmp_path):
        """Reconstructs the real defect exactly: "gnd" -> "GND", where
        "GND" is a genuine design_rules.py class absent from kicad_pro."""
        dr, kc = _agreeing_fields()
        kicad_pro = _kicad_pro(tmp_path, {"Power": kc})
        state, report = run(
            kicad_pro,
            net_classes={"Power": dr, "GND": _FakeNetClassRules(0.3, 1.0, 1.0, 0.5)},
            net_assignments={"gnd": "GND", "PWR_RTN": "GND"},
        )
        assert state == "violation"
        assert report.mismatches == []  # PROPERTY 1 has nothing to compare -- GND isn't shared
        assert len(report.unresolved_references) == 2
        by_net = {u.net_name: u for u in report.unresolved_references}
        assert by_net["gnd"].class_name == "GND"
        assert by_net["gnd"].missing_from_kicad_pro is True
        assert by_net["gnd"].missing_from_design_rules is False  # real Python-side data
        assert by_net["PWR_RTN"].class_name == "GND"

    def test_assignment_naming_declared_class_is_not_flagged(self, tmp_path):
        """Control: an assignment naming a class declared in both tables
        must not be flagged."""
        dr, kc = _agreeing_fields()
        kicad_pro = _kicad_pro(tmp_path, {"Power": kc})
        state, report = run(
            kicad_pro, net_classes={"Power": dr}, net_assignments={"vcc": "Power"}
        )
        assert state == "clean"
        assert report.unresolved_references == []
        assert report.assignments_checked == ["vcc"]

    def test_assignment_naming_class_missing_from_design_rules_is_flagged(self, tmp_path):
        """The reverse gap: a class declared in kicad_pro but absent from
        TEMPER_NET_CLASSES is reported with equal weight, not just the
        "GND" direction seen in practice."""
        dr, kc = _agreeing_fields()
        kicad_pro = _kicad_pro(tmp_path, {"Power": kc, "Differential": kc})
        state, report = run(
            kicad_pro,
            net_classes={"Power": dr},
            net_assignments={"usb_dn": "Differential"},
        )
        assert state == "violation"
        assert len(report.unresolved_references) == 1
        u = report.unresolved_references[0]
        assert u.net_name == "usb_dn"
        assert u.missing_from_design_rules is True
        assert u.missing_from_kicad_pro is False

    def test_fixing_the_assignment_clears_the_violation(self, tmp_path):
        """End-to-end: the exact same fixture, before and after retargeting
        the assignment to a class both tables declare, flips the verdict."""
        dr, kc = _agreeing_fields()
        kicad_pro = _kicad_pro(tmp_path, {"Power": kc})
        net_classes = {"Power": dr, "GND": _FakeNetClassRules(0.3, 1.0, 1.0, 0.5)}

        state, report = run(kicad_pro, net_classes=net_classes, net_assignments={"gnd": "GND"})
        assert state == "violation"

        state, report = run(kicad_pro, net_classes=net_classes, net_assignments={"gnd": "Power"})
        assert state == "clean"
        assert report.unresolved_references == []

    def test_known_unresolved_assignment_is_reported_but_not_blocking(self, tmp_path):
        """CGND (the one remaining "-> GND" entry left out of this task's
        two-mapping fix, see design_rules.py's own comment at that line) is
        reported every run -- never silently dropped -- but does not fail
        the gate on its own."""
        assert "CGND" in _KNOWN_UNRESOLVED_ASSIGNMENTS
        dr, kc = _agreeing_fields()
        kicad_pro = _kicad_pro(tmp_path, {"Power": kc})
        state, report = run(
            kicad_pro,
            net_classes={"Power": dr, "GND": _FakeNetClassRules(0.3, 1.0, 1.0, 0.5)},
            net_assignments={"vcc": "Power", "CGND": "GND"},
        )
        assert state == "clean"  # the ONLY unresolved reference is the known one
        assert report.unresolved_references == []
        assert len(report.known_unresolved_references) == 1
        assert report.known_unresolved_references[0].net_name == "CGND"

    def test_known_carveout_does_not_mask_a_second_real_violation(self, tmp_path):
        """CGND's carve-out must not swallow an unrelated, non-exempt
        unresolved reference reported in the same run."""
        dr, kc = _agreeing_fields()
        kicad_pro = _kicad_pro(tmp_path, {"Power": kc})
        state, report = run(
            kicad_pro,
            net_classes={"Power": dr, "GND": _FakeNetClassRules(0.3, 1.0, 1.0, 0.5)},
            net_assignments={"gnd": "GND", "CGND": "GND"},
        )
        assert state == "violation"
        assert [u.net_name for u in report.unresolved_references] == ["gnd"]
        assert [u.net_name for u in report.known_unresolved_references] == ["CGND"]

    def test_empty_net_assignments_is_gate_error(self, tmp_path):
        """An empty TEMPER_NET_ASSIGNMENTS would make PROPERTY 2 vacuously
        pass -- fail closed instead."""
        dr, kc = _agreeing_fields()
        kicad_pro = _kicad_pro(tmp_path, {"Power": kc})
        state, report = run(kicad_pro, net_classes={"Power": dr}, net_assignments={})
        assert state == "tool_error"
        assert any("PROPERTY 2" in e for e in report.tool_errors)


# ---------------------------------------------------------------------------
# TestAntiVacuity
# ---------------------------------------------------------------------------


class TestAntiVacuity:
    def test_missing_kicad_pro_is_gate_error(self, tmp_path):
        dr, _ = _agreeing_fields()
        state, report = run(tmp_path / "does-not-exist.kicad_pro", net_classes={"Power": dr})
        assert state == "tool_error"
        assert report.tool_errors

    def test_malformed_kicad_pro_json_is_gate_error(self, tmp_path):
        bad = tmp_path / "bad.kicad_pro"
        bad.write_text("{not valid json")
        dr, _ = _agreeing_fields()
        state, report = run(bad, net_classes={"Power": dr})
        assert state == "tool_error"

    def test_empty_kicad_pro_classes_is_gate_error(self, tmp_path):
        kicad_pro = _kicad_pro(tmp_path, {})
        dr, _ = _agreeing_fields()
        state, report = run(kicad_pro, net_classes={"Power": dr})
        assert state == "tool_error"

    def test_kicad_pro_entry_missing_name_is_gate_error(self, tmp_path):
        path = tmp_path / "bad.kicad_pro"
        path.write_text(json.dumps({"net_settings": {"classes": [{"clearance": 1.0}]}}))
        with pytest.raises(GateError):
            load_kicad_pro_class_params(path)

    def test_zero_shared_classes_is_gate_error(self, tmp_path):
        """kicad_pro declares classes, design_rules.py declares classes,
        but their name sets don't intersect at all -- nothing to compare,
        must fail closed rather than report a vacuous clean pass."""
        _, kc = _agreeing_fields()
        kicad_pro = _kicad_pro(tmp_path, {"Default": kc})
        dr, _ = _agreeing_fields()
        state, report = run(
            kicad_pro, net_classes={"Signal": dr}, net_assignments={"SOME_NET": "Signal"}
        )
        assert state == "tool_error"
        assert any("vacuous" in e for e in report.tool_errors)

    def test_unimportable_live_environment_is_gate_error(self, tmp_path):
        """If net_classes is not injected and temper_placer cannot be
        imported, the gate must fail closed, not crash or silently pass."""
        import check_netclass_class_param_correspondence as mod

        original = mod._default_live_net_classes

        def _boom():
            raise mod.GateError("simulated: temper_placer not importable")

        mod._default_live_net_classes = _boom
        try:
            _, kc = _agreeing_fields()
            kicad_pro = _kicad_pro(tmp_path, {"Power": kc})
            state, report = run(kicad_pro)
            assert state == "tool_error"
            assert any("simulated" in e for e in report.tool_errors)
        finally:
            mod._default_live_net_classes = original


# ---------------------------------------------------------------------------
# TestHelperUnits
# ---------------------------------------------------------------------------


class TestHelperUnits:
    def test_field_map_covers_four_scalar_routing_fields(self):
        assert dict(FIELD_MAP) == {
            "clearance": "clearance",
            "trace_width": "track_width",
            "via_diameter": "via_diameter",
            "via_drill": "via_drill",
        }

    def test_compare_class_params_shared_only(self):
        dr = {"A": _FakeNetClassRules(1, 1, 1, 1), "B": _FakeNetClassRules(2, 2, 2, 2)}
        kc = {"A": {"clearance": 1, "track_width": 1, "via_diameter": 1, "via_drill": 1}}
        shared, mismatches = compare_class_params(dr, kc)
        assert shared == ["A"]
        assert mismatches == []

    def test_compare_class_params_reports_every_mismatched_field(self):
        dr = {"A": _FakeNetClassRules(1, 2, 3, 4)}
        kc = {"A": {"clearance": 9, "track_width": 2, "via_diameter": 9, "via_drill": 4}}
        shared, mismatches = compare_class_params(dr, kc)
        assert shared == ["A"]
        flagged = {(m.field_name, m.design_rules_value, m.kicad_pro_value) for m in mismatches}
        assert flagged == {("clearance", 1, 9), ("via_diameter", 3, 9)}

    def test_load_kicad_pro_class_params_reads_full_entry(self, tmp_path):
        kicad_pro = _kicad_pro(tmp_path, {"ACMains": {"clearance": 6.0, "track_width": 2.5}})
        result = load_kicad_pro_class_params(kicad_pro)
        assert result["ACMains"]["clearance"] == 6.0
        assert result["ACMains"]["track_width"] == 2.5

    def test_check_referenced_classes_exist_flags_missing_from_kicad_pro(self):
        net_classes = {"Power": _FakeNetClassRules(1, 1, 1, 1), "GND": _FakeNetClassRules(1, 1, 1, 1)}
        kicad_pro_classes = {"Power": {}}
        blocking, known = check_referenced_classes_exist(
            {"gnd": "GND", "vcc": "Power"}, net_classes, kicad_pro_classes
        )
        assert [u.net_name for u in blocking] == ["gnd"]
        assert blocking[0].missing_from_kicad_pro is True
        assert blocking[0].missing_from_design_rules is False
        assert known == []

    def test_check_referenced_classes_exist_flags_missing_from_design_rules(self):
        net_classes = {"Power": _FakeNetClassRules(1, 1, 1, 1)}
        kicad_pro_classes = {"Power": {}, "Differential": {}}
        blocking, known = check_referenced_classes_exist(
            {"usb_dn": "Differential"}, net_classes, kicad_pro_classes
        )
        assert [u.net_name for u in blocking] == ["usb_dn"]
        assert blocking[0].missing_from_design_rules is True
        assert blocking[0].missing_from_kicad_pro is False

    def test_check_referenced_classes_exist_clean_when_declared_both_sides(self):
        net_classes = {"Power": _FakeNetClassRules(1, 1, 1, 1)}
        kicad_pro_classes = {"Power": {}}
        blocking, known = check_referenced_classes_exist(
            {"vcc": "Power"}, net_classes, kicad_pro_classes
        )
        assert blocking == []
        assert known == []

    def test_check_referenced_classes_exist_splits_known_from_blocking(self):
        net_classes = {"GND": _FakeNetClassRules(1, 1, 1, 1)}
        kicad_pro_classes = {}
        blocking, known = check_referenced_classes_exist(
            {"CGND": "GND"}, net_classes, kicad_pro_classes
        )
        assert blocking == []
        assert [u.net_name for u in known] == ["CGND"]


# ---------------------------------------------------------------------------
# TestRealRepoIntegration
# ---------------------------------------------------------------------------


class TestRealRepoIntegration:
    def test_gate_passes_clean_on_real_repo(self):
        """The gate, run with the real TEMPER_NET_CLASSES,
        TEMPER_NET_ASSIGNMENTS and pcb/temper.kicad_pro, is CLEAN as of
        this commit on BOTH properties:

        PROPERTY 1 -- all 5 field mismatches (HighVoltage.clearance: 6.0
        vs 2.0, plus four Power-class field mismatches) were reconciled
        2026-08-12 (docs/evidence/2026-08-12-netclass-param-reconciliation.md).

        PROPERTY 2 -- "gnd"/"PWR_RTN" no longer map to the undeclared
        "GND" class (docs/evidence/2026-08-12-nonexistent-gnd-class-mapping.md,
        this commit); "CGND" still does, but it is the one carve-out
        _KNOWN_UNRESOLVED_ASSIGNMENTS names and is reported informationally,
        not blocking.

        If temper_placer is not importable in this environment the test is
        skipped rather than xfailed -- a real environment gap is not this
        gate's own defect.
        """
        try:
            import temper_placer.core.design_rules  # noqa: F401
        except ImportError:
            pytest.skip("temper_placer not importable in this environment")

        kicad_pro = REPO_ROOT / "pcb" / "temper.kicad_pro"
        state, report = run(kicad_pro)
        assert state == "clean", (
            "expected the real repo to be reconciled as of this commit; "
            f"got state={state!r} mismatches={report.mismatches!r} "
            f"unresolved_references={report.unresolved_references!r} "
            f"tool_errors={report.tool_errors!r}"
        )
        assert report.classes_checked  # non-empty: a real comparison ran
        assert report.assignments_checked  # non-empty: PROPERTY 2 actually ran
        assert report.unresolved_references == []
        # CGND is still there, still reported -- just not blocking.
        assert [u.net_name for u in report.known_unresolved_references] == ["CGND"]

    def test_exit_codes_match_module_constants(self):
        assert EXIT_OK == 0
        assert EXIT_VIOLATION == 3
        assert EXIT_GATE_ERROR == 5
