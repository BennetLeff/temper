"""Tests for check_creepage_clearance_drift.py.

These build small synthetic ``elec/``, ``scripts/``, ``packages/``,
``configs/`` trees under ``tmp_path`` rather than depending on the real
repository -- the real tree's exact findings drift as the source changes,
and this gate's own delivery report already records what it finds on
``origin/main`` and on ``merge/main-into-ato-net-ssot`` as point-in-time
evidence, not as an assertion this suite should re-derive on every run.

Groups:
  TestAtoDiscovery        -- .ato module/attribute parsing, same-line and
                              module-doc-comment tier inheritance
  TestPythonDiscovery     -- direct name match, _MM comment-fallback,
                              function-body exclusion, alias resolution,
                              sibling-tier propagation
  TestYamlDiscovery       -- direct key match, indirect distance-shaped-key
                              matching, the block-boundary fix (a sibling
                              field must not bleed its tier into an
                              unrelated neighbour)
  TestFamilyComparison    -- consistent vs. mismatched families, and that
                              unspecified-tier / low-confidence entries are
                              excluded from automatic comparison
  TestAntiVacuity         -- missing scan root / zero declarations -> GateError
  TestEndToEnd            -- a full synthetic tree reproducing the exact
                              defect shape from the task (PD3 retarget in
                              two files, not the other two) -> VIOLATION,
                              and a fully-agreeing tree -> clean
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_creepage_clearance_drift import (  # noqa: E402
    GateError,
    build_families,
    discover_ato,
    discover_python,
    discover_yaml,
    run,
)


def _mk(repo_root: Path, rel: str, content: str) -> Path:
    p = repo_root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _mk_scan_roots(repo_root: Path) -> None:
    for name in ("elec", "scripts", "packages", "configs"):
        (repo_root / name).mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# .ato discovery
# ---------------------------------------------------------------------------


class TestAtoDiscovery:
    def test_same_line_comment_gives_reinforced_tier(self, tmp_path: Path) -> None:
        _mk(
            tmp_path,
            "elec/src/constraints.ato",
            "module Constraints:\n"
            "    module HighVoltage:\n"
            "        creepage = 8.0mm   # IEC 60335-1 reinforced insulation\n",
        )
        decls = discover_ato(tmp_path)
        assert len(decls) == 1
        d = decls[0]
        assert d.metric == "creepage"
        assert d.tier == "reinforced"
        assert d.value_mm == 8.0
        assert d.name == "HighVoltage.creepage"

    def test_module_doc_comment_gives_tier_to_attribute_with_no_own_comment(self, tmp_path: Path) -> None:
        _mk(
            tmp_path,
            "elec/src/constraints.ato",
            "module Constraints:\n"
            "    # ACMains to Default: Basic insulation\n"
            "    module AC_to_LV:\n"
            "        min_clearance = 3.0mm\n"
            "        min_creepage = 5.0mm\n",
        )
        decls = {d.name: d for d in discover_ato(tmp_path)}
        assert decls["AC_to_LV.min_clearance"].tier == "basic"
        assert decls["AC_to_LV.min_creepage"].tier == "basic"

    def test_bare_clearance_with_no_nearby_tier_keyword_is_unspecified(self, tmp_path: Path) -> None:
        _mk(
            tmp_path,
            "elec/src/constraints.ato",
            "module Constraints:\n"
            "    # High Voltage Domain (DC Bus, Switch Node)\n"
            "    module HighVoltage:\n"
            "        clearance = 2.0mm\n",
        )
        decls = discover_ato(tmp_path)
        assert decls[0].tier == "unspecified"

    def test_comment_block_does_not_cross_a_blank_line(self, tmp_path: Path) -> None:
        """A banner comment separated from the module by a blank line must
        not leak its keywords into the module's tier -- this is what keeps
        an unrelated section header from being mistaken for the module's
        own doc-comment."""
        _mk(
            tmp_path,
            "elec/src/constraints.ato",
            "module Constraints:\n"
            "    # REINFORCED SECTION BANNER\n"
            "\n"
            "    module HighVoltage:\n"
            "        clearance = 2.0mm\n",
        )
        decls = discover_ato(tmp_path)
        assert decls[0].tier == "unspecified"

    def test_sibling_modules_do_not_share_a_doc_comment(self, tmp_path: Path) -> None:
        _mk(
            tmp_path,
            "elec/src/constraints.ato",
            "module Constraints:\n"
            "    # HighVoltage to Default: Reinforced insulation\n"
            "    module HV_to_LV:\n"
            "        min_creepage = 8.0mm\n"
            "\n"
            "    module AC_to_LV:\n"
            "        min_creepage = 5.0mm\n",
        )
        decls = {d.name: d for d in discover_ato(tmp_path)}
        assert decls["HV_to_LV.min_creepage"].tier == "reinforced"
        assert decls["AC_to_LV.min_creepage"].tier == "unspecified"


# ---------------------------------------------------------------------------
# Python discovery
# ---------------------------------------------------------------------------


class TestPythonDiscovery:
    def test_direct_name_match(self, tmp_path: Path) -> None:
        _mk(tmp_path, "scripts/foo.py", "HV_CREEPAGE_PD2_MM = 8.0\n")
        decls, errors = discover_python(tmp_path)
        assert not errors
        assert len(decls) == 1
        assert decls[0].metric == "creepage"
        assert decls[0].metric_confidence == "direct"
        assert decls[0].value_mm == 8.0

    def test_mm_suffix_without_metric_in_name_uses_comment_fallback(self, tmp_path: Path) -> None:
        _mk(
            tmp_path,
            "scripts/foo.py",
            "# REINFORCED creepage, pollution degree 2 -- top of the stated\n"
            "# 3.0-8.0mm range.\n"
            "MIN_BARRIER_WIDTH_MM = 8.0\n",
        )
        decls, errors = discover_python(tmp_path)
        assert not errors
        assert len(decls) == 1
        d = decls[0]
        assert d.metric == "creepage"
        assert d.tier == "reinforced"
        assert d.value_mm == 8.0

    def test_ratio_without_mm_suffix_is_excluded(self, tmp_path: Path) -> None:
        """A dimensionless factor whose name contains 'creepage' but has no
        _MM unit marker must not be treated as a millimetre value."""
        _mk(tmp_path, "scripts/foo.py", "INTERNAL_LAYER_CREEPAGE_FACTOR = 0.30\n")
        decls, errors = discover_python(tmp_path)
        assert not errors
        assert decls == []

    def test_threshold_without_metric_or_mm_is_excluded(self, tmp_path: Path) -> None:
        _mk(tmp_path, "scripts/foo.py", "_CLEARANCE_PASS_THRESHOLD = 0.95\n")
        decls, errors = discover_python(tmp_path)
        assert not errors
        assert decls == []

    def test_function_body_local_variable_is_excluded(self, tmp_path: Path) -> None:
        _mk(
            tmp_path,
            "scripts/foo.py",
            "def compute():\n"
            "    clearance_mm = 0.4\n"
            "    return clearance_mm\n",
        )
        decls, errors = discover_python(tmp_path)
        assert not errors
        assert decls == []

    def test_alias_resolves_to_referenced_constant_value(self, tmp_path: Path) -> None:
        _mk(
            tmp_path,
            "scripts/foo.py",
            "HV_CREEPAGE_PD3_MM = 12.6\n"
            "HV_CREEPAGE_ENFORCED_MM = HV_CREEPAGE_PD3_MM\n",
        )
        decls, errors = discover_python(tmp_path)
        assert not errors
        by_name = {d.name: d for d in decls}
        assert by_name["HV_CREEPAGE_ENFORCED_MM"].value_mm == 12.6

    def test_sibling_tier_propagates_across_adjacent_declarations_only(self, tmp_path: Path) -> None:
        _mk(
            tmp_path,
            "scripts/foo.py",
            "# the reinforced creepage requirement is 2 x 6.3mm = 12.6mm\n"
            "HV_CREEPAGE_PD2_MM = 8.0\n"
            "HV_CREEPAGE_PD3_MM = 12.6  # flagged default; UNRESOLVED\n"
            "\n"
            "OTHER_UNRELATED_CLEARANCE_MM = 1.0\n",
        )
        decls, errors = discover_python(tmp_path)
        assert not errors
        by_name = {d.name: d for d in decls}
        assert by_name["HV_CREEPAGE_PD2_MM"].tier == "reinforced"
        assert by_name["HV_CREEPAGE_PD3_MM"].tier == "reinforced"
        # A blank line separates OTHER_UNRELATED_CLEARANCE_MM from the run
        # above -- it must NOT inherit the tier of an unrelated constant
        # merely for being declared later in the same file.
        assert by_name["OTHER_UNRELATED_CLEARANCE_MM"].tier == "unspecified"

    def test_dataclass_construction_keyword_is_discovered_regardless_of_outer_name(
        self, tmp_path: Path
    ) -> None:
        """TEMPER_NET_CLASSES's own name contains neither 'creepage' nor
        'clearance' -- discovery must not depend on it."""
        _mk(
            tmp_path,
            "packages/temper-placer/src/temper_placer/core/design_rules.py",
            "TEMPER_NET_CLASSES = {\n"
            '    "ACMains": NetClassRules(name="ACMains", clearance=6.0, creepage_mm=6.0),\n'
            "}\n",
        )
        decls, errors = discover_python(tmp_path)
        assert not errors
        names = {d.name for d in decls}
        assert "TEMPER_NET_CLASSES.ACMains.clearance" in names
        assert "TEMPER_NET_CLASSES.ACMains.creepage_mm" in names

    def test_non_literal_value_is_reported_unresolved_not_dropped(self, tmp_path: Path) -> None:
        _mk(
            tmp_path,
            "packages/temper-placer/src/temper_placer/core/foo.py",
            "class C:\n"
            "    clearance_mm: float = Field(default=6.0, description='x')\n",
        )
        decls, errors = discover_python(tmp_path)
        assert not errors
        assert len(decls) == 1
        assert decls[0].value_mm is None

    def test_syntax_error_is_a_reported_error_not_a_silent_skip(self, tmp_path: Path) -> None:
        _mk(tmp_path, "scripts/broken.py", "def f(:\n    pass\n")
        decls, errors = discover_python(tmp_path)
        assert decls == []
        assert len(errors) == 1
        assert "broken.py" in errors[0][0]


# ---------------------------------------------------------------------------
# YAML discovery
# ---------------------------------------------------------------------------


class TestYamlDiscovery:
    def test_direct_key_match(self, tmp_path: Path) -> None:
        _mk(
            tmp_path,
            "packages/foo/configs/netclass_rules.yaml",
            "classes:\n  HighVoltage:\n    clearance: 6.0\n",
        )
        decls, errors = discover_yaml(tmp_path)
        assert not errors
        assert len(decls) == 1
        assert decls[0].metric == "clearance"
        assert decls[0].metric_confidence == "direct"
        assert decls[0].value_mm == 6.0

    def test_indirect_match_via_because_field_with_matching_number(self, tmp_path: Path) -> None:
        _mk(
            tmp_path,
            "packages/foo/configs/pcl/temper_production.yaml",
            "constraints:\n"
            "  - type: separated\n"
            '    id: "tank-cap1-mcu-creepage"\n'
            "    min_distance_mm: 8.0\n"
            "    tier: 1\n"
            '    because: "IEC 60335-1 reinforced-insulation creepage, HV tank cap to MCU"\n',
        )
        decls, errors = discover_yaml(tmp_path)
        assert not errors
        assert len(decls) == 1
        d = decls[0]
        assert d.metric == "creepage"
        assert d.tier == "reinforced"
        assert d.value_mm == 8.0
        assert "tank-cap1-mcu-creepage" in d.name

    def test_indirect_match_requires_a_distance_shaped_key(self, tmp_path: Path) -> None:
        """A numeric field near a creepage/clearance-mentioning comment is
        only a candidate if its own key looks like a distance/gap field --
        this is the fix for the false 'voltage_v: 400 is a 400mm clearance'
        finding an earlier version of this gate produced."""
        _mk(
            tmp_path,
            "packages/foo/configs/netclass_rules.yaml",
            "classes:\n"
            "  HighVoltage:\n"
            "    clearance: 6.0\n"
            "    voltage_v: 400.0\n"
            '    because: "IEC 60335-1 Table 16 working isolation at 400V"\n',
        )
        decls, errors = discover_yaml(tmp_path)
        assert not errors
        names = {d.name for d in decls}
        assert not any("voltage_v" in n for n in names)

    def test_block_window_does_not_bleed_into_sibling_mapping(self, tmp_path: Path) -> None:
        """FinePitch.clearance sits five lines below HighVoltage's 'working
        isolation' because-field in the real file this reproduces
        (netclass_rules.yaml) -- a fixed-size window previously leaked that
        tier across the class boundary."""
        _mk(
            tmp_path,
            "packages/foo/configs/netclass_rules.yaml",
            "classes:\n"
            "  HighVoltage:\n"
            "    clearance: 6.0\n"
            "    creepage_mm: 6.0\n"
            '    because: "IEC 60335-1 Table 16 working isolation at 400V"\n'
            "\n"
            "  FinePitch:\n"
            "    clearance: 0.1\n",
        )
        decls = {d.name: d for d in discover_yaml(tmp_path)[0]}
        assert decls["classes.HighVoltage.clearance"].tier == "working"
        assert decls["classes.FinePitch.clearance"].tier == "unspecified"

    def test_invalid_yaml_is_a_reported_error(self, tmp_path: Path) -> None:
        _mk(tmp_path, "configs/broken.yaml", "clearance: [1, 2\n")
        decls, errors = discover_yaml(tmp_path)
        assert decls == []
        assert len(errors) == 1


# ---------------------------------------------------------------------------
# Family comparison
# ---------------------------------------------------------------------------


class TestFamilyComparison:
    def test_consistent_family_reports_ok(self, tmp_path: Path) -> None:
        _mk(
            tmp_path,
            "elec/src/constraints.ato",
            "module Constraints:\n"
            "    # HighVoltage to Default: Reinforced insulation\n"
            "    module HV_to_LV:\n"
            "        min_creepage = 8.0mm\n"
            "\n"
            "    module HighVoltage:\n"
            "        creepage = 8.0mm  # IEC 60335-1 reinforced insulation\n",
        )
        decls = discover_ato(tmp_path)
        families, flagged, unresolved = build_families(decls)
        assert len(families) == 1
        assert families[0].is_consistent
        assert not flagged
        assert not unresolved

    def test_mismatched_family_reports_all_distinct_values(self, tmp_path: Path) -> None:
        _mk(
            tmp_path,
            "elec/src/constraints.ato",
            "module Constraints:\n"
            "    # HighVoltage to Default: Reinforced insulation\n"
            "    module HV_to_LV:\n"
            "        min_creepage = 8.0mm\n",
        )
        _mk(
            tmp_path,
            "scripts/check_isolation_keepout.py",
            "# REINFORCED creepage figure for the barrier\n"
            "MIN_BARRIER_WIDTH_MM = 12.6\n",
        )
        decls = discover_ato(tmp_path) + discover_python(tmp_path)[0]
        families, _, _ = build_families(decls)
        assert len(families) == 1
        fam = families[0]
        assert not fam.is_consistent
        assert set(fam.distinct_values.keys()) == {8.0, 12.6}

    def test_unspecified_tier_is_flagged_not_compared(self, tmp_path: Path) -> None:
        _mk(
            tmp_path,
            "elec/src/constraints.ato",
            "module Constraints:\n    module HighVoltage:\n        clearance = 2.0mm\n",
        )
        decls = discover_ato(tmp_path)
        families, flagged, _ = build_families(decls)
        assert families == []
        assert len(flagged) == 1

    def test_different_tiers_never_compared_against_each_other(self, tmp_path: Path) -> None:
        """5.0mm basic creepage and 8.0mm reinforced creepage must land in
        separate families -- this is the core "do not conflate distinct
        insulation classes" requirement."""
        _mk(
            tmp_path,
            "elec/src/constraints.ato",
            "module Constraints:\n"
            "    # ACMains to Default: Basic insulation\n"
            "    module AC_to_LV:\n"
            "        min_creepage = 5.0mm\n"
            "\n"
            "    # HighVoltage to Default: Reinforced insulation\n"
            "    module HV_to_LV:\n"
            "        min_creepage = 8.0mm\n",
        )
        decls = discover_ato(tmp_path)
        families, _, _ = build_families(decls)
        assert len(families) == 2
        assert all(f.is_consistent for f in families)
        tiers = {f.tier for f in families}
        assert tiers == {"basic", "reinforced"}

    def test_creepage_and_clearance_never_compared_against_each_other(self, tmp_path: Path) -> None:
        _mk(
            tmp_path,
            "elec/src/constraints.ato",
            "module Constraints:\n"
            "    # HighVoltage to Default: Reinforced insulation\n"
            "    module HV_to_LV:\n"
            "        min_clearance = 6.0mm\n"
            "        min_creepage = 8.0mm\n",
        )
        decls = discover_ato(tmp_path)
        families, _, _ = build_families(decls)
        metrics = {f.metric for f in families}
        assert metrics == {"clearance", "creepage"}
        for fam in families:
            assert fam.is_consistent  # each metric has exactly one member here


# ---------------------------------------------------------------------------
# Anti-vacuity / fail-closed
# ---------------------------------------------------------------------------


class TestAntiVacuity:
    def test_missing_scan_root_is_gate_error(self, tmp_path: Path) -> None:
        (tmp_path / "elec").mkdir()
        (tmp_path / "scripts").mkdir()
        (tmp_path / "packages").mkdir()
        # configs/ deliberately absent
        with pytest.raises(GateError):
            run(tmp_path)

    def test_zero_declarations_anywhere_is_gate_error(self, tmp_path: Path) -> None:
        _mk_scan_roots(tmp_path)
        _mk(tmp_path, "scripts/unrelated.py", "TRACE_WIDTH_MM = 2.0\n")
        with pytest.raises(GateError):
            run(tmp_path)


# ---------------------------------------------------------------------------
# End-to-end
# ---------------------------------------------------------------------------


class TestEndToEnd:
    def _write_agreeing_tree(self, tmp_path: Path) -> None:
        _mk_scan_roots(tmp_path)
        _mk(
            tmp_path,
            "elec/src/constraints.ato",
            "module Constraints:\n"
            "    # HighVoltage to Default: Reinforced insulation\n"
            "    module HV_to_LV:\n"
            "        min_creepage = 8.0mm\n",
        )
        _mk(
            tmp_path,
            "scripts/check_isolation_keepout.py",
            "# REINFORCED creepage, pollution degree 2\n"
            "MIN_BARRIER_WIDTH_MM = 8.0\n",
        )

    def test_agreeing_tree_is_clean(self, tmp_path: Path) -> None:
        self._write_agreeing_tree(tmp_path)
        state, report, families, flagged, unresolved = run(tmp_path)
        assert state == "clean"
        assert report.declarations
        assert any(f.metric == "creepage" and f.tier == "reinforced" for f in families)
        for fam in families:
            assert fam.is_consistent

    def test_retargeted_tree_reproduces_the_task_defect(self, tmp_path: Path) -> None:
        """Reproduces the exact shape of the verified defect: the gate
        (check_isolation_keepout.py) was retargeted to PD3 (12.6mm) but the
        .ato source of truth was not -- the gate must fail, non-vacuously,
        naming both sites and both values."""
        self._write_agreeing_tree(tmp_path)
        _mk(
            tmp_path,
            "scripts/check_isolation_keepout.py",
            "# REINFORCED creepage, pollution degree 3 (PD3 GOVERNS)\n"
            "MIN_BARRIER_WIDTH_MM = 12.6\n",
        )
        state, report, families, flagged, unresolved = run(tmp_path)
        assert state == "violation"
        reinforced_creepage = next(f for f in families if f.metric == "creepage" and f.tier == "reinforced")
        assert not reinforced_creepage.is_consistent
        assert set(reinforced_creepage.distinct_values.keys()) == {8.0, 12.6}
        sites = {d.file for d in reinforced_creepage.members}
        assert "elec/src/constraints.ato" in sites
        assert "scripts/check_isolation_keepout.py" in sites
