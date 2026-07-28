"""Tests for check_net_classification.py.

See docs/evidence/2026-07-27-net-classification-gate.md for the full
write-up, including the falsifier proof against the real historical
commits (pre-fix ``creepage_check.py``, pre-fix ``clearance_check.py``,
and the pre-fix ``clearance_engine.py``) -- that part is done by hand
against the live tree (``git checkout <commit> -- <path>``, run the gate,
restore), not as a pytest fixture, since it depends on this repo's actual
git history.

Four groups here:

1. `TestHistoricalDefectReconstruction` -- rebuilds the three confirmed
   historical instances (creepage false positives, clearance false
   negatives, and the bare-substring `_net_class_to_voltage_class` shape)
   as small, isolated fixture trees and asserts the gate fails, naming
   the exact call site. Also proves the anchored (fixed) equivalent, the
   manifest-membership pattern, and a non-vocabulary keyword list are NOT
   false-positived.
2. `TestAntiVacuity` -- asserts the gate fails CLOSED (state ==
   "tool_error", never "clean") on every degenerate input: a scan root
   that doesn't exist, zero files found, zero 'in' call sites discovered,
   a file that fails to parse, and an allowlist entry with no
   justification/scope.
3. `TestClassificationUnits` -- unit tests for the AST helpers in
   isolation (`_string_elements`, `_ConstantCollector`, allowlist
   matching).
4. `TestRealRepoIntegration` -- the gate passes clean against the actual
   repo as of this commit.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from check_net_classification import (  # noqa: E402
    GateError,
    ScanTarget,
    _ConstantCollector,
    _string_elements,
    load_allowlist,
    matches_allowlist,
    run,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))
    return path


def _single_target(root: Path, label: str = "fixture/**/*.py") -> list[ScanTarget]:
    return [ScanTarget(label, root, "**/*.py", False)]


# ---------------------------------------------------------------------------
# TestHistoricalDefectReconstruction
# ---------------------------------------------------------------------------


class TestHistoricalDefectReconstruction:
    """Fixture reconstructions of the three real confirmed instances, plus
    the anchored / manifest-membership / non-vocabulary controls that
    prove the gate does not fire on the shapes it is supposed to accept.
    """

    def test_creepage_false_positive_shape_is_flagged(self, tmp_path):
        """Reconstructs creepage_check.py's pre-fix ``broad_keywords``
        shape (merge 5076e715): a local list containing "L1"/"L2"/"LINE"
        checked via plain ``kw in name_upper``.
        """
        root = tmp_path / "fixture"
        _write(
            root / "creepage_check.py",
            """
            def _is_high_voltage_net(net_name: str) -> bool:
                name_upper = net_name.upper()
                broad_keywords = [
                    "HIGH_VOLTAGE", "MAINS", "LINE", "NEUTRAL", "PRIMARY",
                    "HOT", "L1", "L2", "L3", "PHASE", "VBUS",
                ]
                if any(kw in name_upper for kw in broad_keywords):
                    return True
                return False
            """,
        )
        state, report = run(tmp_path, tmp_path / "no-allowlist", _single_target(root))
        assert state == "violation"
        assert len(report.violations) == 1
        v = report.violations[0]
        assert v.qualname == "_is_high_voltage_net"
        assert "L1" in v.matched_vocab or "LINE" in v.matched_vocab

    def test_clearance_false_negative_shape_is_flagged(self, tmp_path):
        """Reconstructs clearance_check.py's pre-fix ``hv_keywords`` shape
        (merge 466c7724): ``["AC_", "HV_", "HIGH_VOLTAGE", "MAINS"]``
        checked via plain ``kw in net1_upper``.
        """
        root = tmp_path / "fixture"
        _write(
            root / "clearance_check.py",
            """
            def _get_required_clearance(net1, net2, default_clearance):
                hv_keywords = ["AC_", "HV_", "HIGH_VOLTAGE", "MAINS"]
                net1_upper = net1.upper()
                is_hv1 = any(kw in net1_upper for kw in hv_keywords)
                return default_clearance
            """,
        )
        state, report = run(tmp_path, tmp_path / "no-allowlist", _single_target(root))
        assert state == "violation"
        assert len(report.violations) == 1
        assert report.violations[0].qualname == "_get_required_clearance"

    def test_bare_substring_no_loop_shape_is_flagged(self, tmp_path):
        """Reconstructs clearance_engine.py's ``_net_class_to_voltage_class``
        shape: an inline tuple literal, not a named intermediate variable.
        """
        root = tmp_path / "fixture"
        _write(
            root / "clearance_engine.py",
            """
            def _net_class_to_voltage_class(net_class: str):
                upper = net_class.upper()
                if any(kw in upper for kw in ("HIGH_VOLTAGE", "HV", "MAINS_240V", "MAINS", "AC")):
                    return "HIGH_VOLTAGE"
                return "SELV"
            """,
        )
        state, report = run(tmp_path, tmp_path / "no-allowlist", _single_target(root))
        assert state == "violation"
        assert len(report.violations) == 1
        assert report.violations[0].qualname == "_net_class_to_voltage_class"

    def test_anchored_regex_fix_is_not_flagged(self, tmp_path):
        """The actual fix pattern (word-boundary regex via ``re.search``,
        no bare ``in`` test) must not be flagged -- this is what every
        historical instance was fixed to.
        """
        root = tmp_path / "fixture"
        _write(
            root / "creepage_check.py",
            """
            import re

            def _is_high_voltage_net(net_name: str) -> bool:
                name_upper = net_name.upper()
                broad_keywords = ["MAINS", "LINE", "L1", "L2"]
                for kw in broad_keywords:
                    if re.search(rf"(?:^|_){kw}(?:$|[\\d_])", name_upper):
                        return True
                return False
            """,
        )
        # A companion resolved, non-vocabulary call site so this isolated
        # single-purpose fixture doesn't trip the anti-vacuous-truth
        # backstop on its own (the fixed function above uses re.search,
        # not `in`, so it contributes zero call sites by itself -- that
        # backstop is repo-wide and is exercised on its own terms in
        # TestAntiVacuity.test_zero_call_sites_discovered_fails_closed).
        _write(
            root / "_control.py",
            """
            def is_debug_ref(ref: str) -> bool:
                return "DEBUG" in ref.upper()
            """,
        )
        state, report = run(tmp_path, tmp_path / "no-allowlist", _single_target(root))
        assert state == "clean"
        assert report.violations == []
        assert report.call_sites_discovered > 0

    def test_manifest_membership_pattern_is_not_flagged(self, tmp_path):
        """The other real fix pattern -- exact membership against a set
        of full net names loaded from elec/domain_manifest.yaml -- has no
        enclosing keyword loop and must not be flagged. This is the
        pattern this gate's own docstring explains it excludes by
        construction (no loop-bound keyword variable).
        """
        root = tmp_path / "fixture"
        _write(
            root / "clearance_check.py",
            """
            def _classify_net_class(net_name, hv_manifest_nets):
                if net_name in hv_manifest_nets:
                    return "HV"
                return "SIGNAL"
            """,
        )
        # Companion resolved call site -- see the identical note in
        # test_anchored_regex_fix_is_not_flagged. The manifest-membership
        # Compare above is excluded by construction (no loop-bound
        # keyword variable, so it is not even counted as "discovered"),
        # so this isolated fixture needs its own denominator.
        _write(
            root / "_control.py",
            """
            def is_debug_ref(ref: str) -> bool:
                return "DEBUG" in ref.upper()
            """,
        )
        state, report = run(tmp_path, tmp_path / "no-allowlist", _single_target(root))
        assert state == "clean"
        assert report.violations == []
        assert report.call_sites_discovered > 0

    def test_non_vocabulary_keyword_list_is_not_flagged(self, tmp_path):
        """A keyword-loop-substring-test shape whose vocabulary has
        nothing to do with the HV/SELV boundary (e.g. impedance-class
        keywords) must not be flagged -- this is
        ``net_class_manager.HIGH_SPEED_KEYWORDS``'s real shape.
        """
        root = tmp_path / "fixture"
        _write(
            root / "net_class_manager.py",
            """
            HIGH_SPEED_KEYWORDS = ["USB", "SPI", "I2C", "SDA", "SCL", "CLK"]

            def is_high_speed_net(net_name: str) -> bool:
                net_upper = net_name.upper()
                return any(keyword in net_upper for keyword in HIGH_SPEED_KEYWORDS)
            """,
        )
        state, report = run(tmp_path, tmp_path / "no-allowlist", _single_target(root))
        assert state == "clean"
        assert report.violations == []

    def test_allowlisted_call_site_does_not_fail(self, tmp_path):
        root = tmp_path / "fixture"
        _write(
            root / "reference_loader.py",
            """
            def infer_quality_config(design):
                for net in design.netlist.nets:
                    net_upper = net.name.upper()
                    if any(kw in net_upper for kw in ["GATE", "DRV", "DRIVE"]):
                        pass
            """,
        )
        allowlist = _write(
            tmp_path / ".net-classification-allowlist",
            """
            infer_quality_config::fixture/reference_loader.py  # test justification
            """,
        )
        state, report = run(tmp_path, allowlist, _single_target(root))
        assert state == "clean"
        assert len(report.allowlisted) == 1
        assert report.violations == []


# ---------------------------------------------------------------------------
# TestAntiVacuity
# ---------------------------------------------------------------------------


class TestAntiVacuity:
    def test_scan_root_missing_fails_closed(self, tmp_path):
        targets = [ScanTarget("missing", tmp_path / "does-not-exist", "**/*.py", False)]
        state, report = run(tmp_path, tmp_path / "no-allowlist", targets)
        assert state == "tool_error"
        assert any("does not exist" in e for e in report.tool_errors)

    def test_zero_files_found_fails_closed(self, tmp_path):
        root = tmp_path / "fixture"
        root.mkdir()
        state, report = run(tmp_path, tmp_path / "no-allowlist", _single_target(root))
        assert state == "tool_error"
        assert any("zero files" in e for e in report.tool_errors)

    def test_zero_call_sites_discovered_fails_closed(self, tmp_path):
        """A codebase with real .py files but zero 'in'-operator call
        sites at all is a vacuous run, not a clean pass -- see
        docs/solutions/best-practices/ on gates that silently checked an
        empty or partial set.
        """
        root = tmp_path / "fixture"
        _write(
            root / "harmless.py",
            """
            def add(a, b):
                return a + b
            """,
        )
        state, report = run(tmp_path, tmp_path / "no-allowlist", _single_target(root))
        assert state == "tool_error"
        assert any("vacuous run" in e for e in report.tool_errors)

    def test_unparseable_file_fails_closed(self, tmp_path):
        root = tmp_path / "fixture"
        _write(root / "broken.py", "def broken(:\n")
        state, report = run(tmp_path, tmp_path / "no-allowlist", _single_target(root))
        assert state == "tool_error"
        assert any("could not parse" in e for e in report.tool_errors)

    def test_zero_scan_targets_fails_closed(self, tmp_path):
        state, report = run(tmp_path, tmp_path / "no-allowlist", [])
        assert state == "tool_error"
        assert any("zero scan targets" in e for e in report.tool_errors)

    def test_allowlist_entry_without_justification_fails_closed(self, tmp_path):
        allowlist = _write(tmp_path / ".allowlist", "foo::bar.py\n")
        with pytest.raises(GateError, match="justification"):
            load_allowlist(allowlist)

    def test_allowlist_entry_with_empty_justification_fails_closed(self, tmp_path):
        allowlist = _write(tmp_path / ".allowlist", "foo::bar.py  #\n")
        with pytest.raises(GateError, match="empty justification"):
            load_allowlist(allowlist)

    def test_allowlist_entry_without_file_scope_fails_closed(self, tmp_path):
        allowlist = _write(tmp_path / ".allowlist", "foo  # some justification\n")
        with pytest.raises(GateError, match="separator"):
            load_allowlist(allowlist)

    def test_allowlist_missing_file_is_not_an_error(self, tmp_path):
        assert load_allowlist(tmp_path / "does-not-exist") == []

    def test_allowlist_entry_scoped_to_one_file_does_not_exempt_another(self, tmp_path):
        allowlist = _write(
            tmp_path / ".allowlist",
            "foo::exact_file.py  # justification\n",
        )
        entries = load_allowlist(allowlist)
        assert matches_allowlist("foo", "exact_file.py", entries)
        assert not matches_allowlist("foo", "other_file.py", entries)
        assert not matches_allowlist("bar", "exact_file.py", entries)


# ---------------------------------------------------------------------------
# TestClassificationUnits
# ---------------------------------------------------------------------------


class TestClassificationUnits:
    def test_string_elements_list_literal(self):
        import ast

        node = ast.parse('["A", "B"]', mode="eval").body
        assert _string_elements(node) == ["A", "B"]

    def test_string_elements_frozenset_call(self):
        import ast

        node = ast.parse('frozenset({"A", "B"})', mode="eval").body
        assert sorted(_string_elements(node)) == ["A", "B"]

    def test_string_elements_rejects_non_constant_element(self):
        import ast

        node = ast.parse('["A", some_var]', mode="eval").body
        assert _string_elements(node) is None

    def test_string_elements_none_for_non_collection(self):
        import ast

        node = ast.parse("some_name", mode="eval").body
        assert _string_elements(node) is None

    def test_constant_collector_tracks_module_level_assign(self):
        import ast

        tree = ast.parse('KEYWORDS = ["HV", "AC"]\n')
        collector = _ConstantCollector()
        collector.visit(tree)
        assert collector.bindings["KEYWORDS"] == ["HV", "AC"]

    def test_constant_collector_tracks_annassign(self):
        import ast

        tree = ast.parse('KEYWORDS: frozenset = frozenset({"HV", "AC"})\n')
        collector = _ConstantCollector()
        collector.visit(tree)
        assert sorted(collector.bindings["KEYWORDS"]) == ["AC", "HV"]

    def test_constant_collector_ignores_dynamic_assign(self):
        import ast

        tree = ast.parse("KEYWORDS = compute_keywords()\n")
        collector = _ConstantCollector()
        collector.visit(tree)
        assert "KEYWORDS" not in collector.bindings


# ---------------------------------------------------------------------------
# TestRealRepoIntegration
# ---------------------------------------------------------------------------


class TestRealRepoIntegration:
    def test_real_repo_is_clean(self):
        allowlist_path = REPO_ROOT / ".net-classification-allowlist"
        state, report = run(REPO_ROOT, allowlist_path)
        assert state == "clean", (
            f"expected clean, got {state}. Violations: "
            f"{[(v.file, v.lineno, v.qualname) for v in report.violations]}. "
            f"Tool errors: {report.tool_errors}"
        )
        assert report.call_sites_discovered > 0
        assert report.files_inspected > 0
