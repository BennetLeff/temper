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

import json
import sys
from hashlib import sha256
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_creepage_clearance_drift import (  # noqa: E402
    KNOWN_TIER_MISCLASSIFICATIONS,
    Declaration,
    FamilyResult,
    GateError,
    _resolve_reinforced_clearance_authority,
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
        families, flagged, unresolved, known_blind_spots, declared_not_enforced = build_families(decls)
        assert len(families) == 1
        assert families[0].is_consistent
        assert not flagged
        assert not unresolved
        assert not known_blind_spots

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
        families, _, _, _, _ = build_families(decls)
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
        families, flagged, _, _, _ = build_families(decls)
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
        families, _, _, _, _ = build_families(decls)
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
        families, _, _, _, _ = build_families(decls)
        metrics = {f.metric for f in families}
        assert metrics == {"clearance", "creepage"}
        for fam in families:
            assert fam.is_consistent  # each metric has exactly one member here


# ---------------------------------------------------------------------------
# Known tier misclassifications (Task 2, GateDriveHV/GateDriveSELV)
# ---------------------------------------------------------------------------


class TestKnownBlindSpots:
    def _gate_drive_yaml(self) -> str:
        return (
            "classes:\n"
            "  GateDriveHV:\n"
            "    clearance: 0.25\n"
            '    because: "secondary (HV) side of a reinforced barrier"\n'
            "  GateDriveSELV:\n"
            "    clearance: 0.25\n"
            '    because: "primary (SELV) side of a reinforced barrier"\n'
        )

    def test_registered_sites_are_excluded_from_family_comparison(self, tmp_path: Path) -> None:
        """The two registered GateDriveHV/GateDriveSELV sites must not be
        force-compared against a real reinforced-tier barrier figure (6.0mm)
        even though the keyword classifier alone would tier-tag both
        "reinforced"."""
        _mk(
            tmp_path,
            "packages/temper-placer/configs/netclass_rules.yaml",
            self._gate_drive_yaml(),
        )
        _mk(
            tmp_path,
            "elec/src/constraints.ato",
            "module Constraints:\n"
            "    # HighVoltage to Default: Reinforced insulation\n"
            "    module HV_to_LV:\n"
            "        min_clearance = 6.0mm\n",
        )
        decls = discover_ato(tmp_path) + discover_yaml(tmp_path)[0]
        families, flagged, unresolved, known_blind_spots, declared_not_enforced = build_families(decls)
        assert len(known_blind_spots) == 2
        assert {d.value_mm for d in known_blind_spots} == {0.25}
        clearance_reinforced = next(f for f in families if f.metric == "clearance" and f.tier == "reinforced")
        # Only the real barrier figure remains in the family -- it is
        # consistent because the two 0.25mm misclassified entries were
        # pulled out before comparison, not because they happened to agree.
        assert clearance_reinforced.is_consistent
        assert set(clearance_reinforced.distinct_values.keys()) == {6.0}

    def test_registry_entries_match_real_declaration_names(self) -> None:
        """Sanity: every (file, name) in the registry must be shaped like a
        real Declaration.site would render it -- catches a typo'd override
        that would silently never match anything."""
        for file, name in KNOWN_TIER_MISCLASSIFICATIONS:
            assert file.endswith(".yaml")
            assert name.startswith("classes.")

    def test_stale_override_whose_tier_no_longer_resolves_reinforced_is_gate_error(
        self, tmp_path: Path
    ) -> None:
        """If a registered site's own text no longer says "reinforced" (the
        because field was reworded, or the comment removed), the override
        would silently protect nothing -- this must fail loudly instead of
        going quiet."""
        _mk(
            tmp_path,
            "packages/temper-placer/configs/netclass_rules.yaml",
            "classes:\n"
            "  GateDriveHV:\n"
            "    clearance: 0.25\n"
            '    because: "ordinary intra-class spacing, no barrier mentioned"\n'
            "  GateDriveSELV:\n"
            "    clearance: 0.25\n"
            '    because: "primary (SELV) side of a reinforced barrier"\n',
        )
        decls = discover_yaml(tmp_path)[0]
        with pytest.raises(GateError):
            build_families(decls)

    def test_a_site_registered_but_absent_from_this_run_is_not_an_error(self, tmp_path: Path) -> None:
        """A tree that never mentions GateDriveHV/GateDriveSELV at all (a
        synthetic fixture, or a real tree like origin/main that predates the
        netclass split this override targets) must not fail just because
        the override never matched anything -- see build_families()'s own
        docstring for why this direction is safe."""
        _mk(
            tmp_path,
            "elec/src/constraints.ato",
            "module Constraints:\n"
            "    # HighVoltage to Default: Reinforced insulation\n"
            "    module HV_to_LV:\n"
            "        min_clearance = 6.0mm\n",
        )
        decls = discover_ato(tmp_path)
        families, flagged, unresolved, known_blind_spots, declared_not_enforced = build_families(decls)
        assert known_blind_spots == []


# ---------------------------------------------------------------------------
# Selection aliases (declared-candidates-vs-enforced-value, PR #443's
# generate_kicad_dru.py HV_CREEPAGE_PD2_MM/PD3_MM/ENFORCED_MM shape)
# ---------------------------------------------------------------------------


class TestSelectionAliases:
    def test_unselected_candidate_is_pulled_from_the_family_and_marked(self, tmp_path: Path) -> None:
        """Reproduces generate_kicad_dru.py's exact shape: two declared
        candidates plus a selection alias picking one. The unselected
        candidate must not land in the comparable family, and must carry
        the enforced value/site it lost to -- discovered and reported, not
        dropped."""
        _mk(
            tmp_path,
            "scripts/foo.py",
            "# Reinforced creepage at Pollution Degree 2: 8.0mm.\n"
            "HV_CREEPAGE_PD2_MM = 8.0\n"
            "HV_CREEPAGE_PD3_MM = 12.6  # flagged default; UNRESOLVED\n"
            "\n"
            "HV_CREEPAGE_ENFORCED_MM = HV_CREEPAGE_PD2_MM\n",
        )
        decls, errors = discover_python(tmp_path)
        assert not errors
        by_name = {d.name: d for d in decls}
        pd2 = by_name["HV_CREEPAGE_PD2_MM"]
        pd3 = by_name["HV_CREEPAGE_PD3_MM"]
        assert not pd2.declared_not_enforced
        assert pd3.declared_not_enforced
        assert pd3.enforced_value_mm == 8.0
        assert pd3.enforced_site == pd2.site
        assert pd3.enforcing_alias == "HV_CREEPAGE_ENFORCED_MM"

        families, flagged, unresolved, known_blind_spots, declared_not_enforced = build_families(decls)
        assert len(declared_not_enforced) == 1
        assert declared_not_enforced[0].name == "HV_CREEPAGE_PD3_MM"
        fam = next(f for f in families if f.metric == "creepage" and f.tier == "reinforced")
        assert fam.is_consistent
        assert set(fam.distinct_values.keys()) == {8.0}

    def test_detection_is_structural_not_name_based(self, tmp_path: Path) -> None:
        """A selector NOT named *ENFORCED* must be detected identically --
        proves this is an ast.Name-referring-to-a-declared-constant test,
        not a substring/naming-convention rule that would rot the day the
        selector is renamed. (Named ``ACTIVE_CREEPAGE_MM`` rather than
        something with no "creepage"/"clearance"/``_MM`` signal at all,
        since discovering it as a declaration in the first place is this
        gate's separate, orthogonal name/unit-marker requirement -- see
        ``_is_mm_named`` in the module docstring -- not part of what this
        test is checking.)"""
        _mk(
            tmp_path,
            "scripts/foo.py",
            "# Reinforced creepage at Pollution Degree 2: 8.0mm.\n"
            "HV_CREEPAGE_PD2_MM = 8.0\n"
            "HV_CREEPAGE_PD3_MM = 12.6  # flagged default; UNRESOLVED\n"
            "\n"
            "ACTIVE_CREEPAGE_MM = HV_CREEPAGE_PD2_MM\n",
        )
        decls, errors = discover_python(tmp_path)
        assert not errors
        by_name = {d.name: d for d in decls}
        assert by_name["HV_CREEPAGE_PD3_MM"].declared_not_enforced
        assert by_name["HV_CREEPAGE_PD3_MM"].enforcing_alias == "ACTIVE_CREEPAGE_MM"

    def test_enforced_value_still_compared_across_files(self, tmp_path: Path) -> None:
        """The selected candidate must still participate in cross-file
        family comparison -- reproduces the merge/main-into-ato-net-ssot
        case where the SSOT (.ato) disagrees with the alias-enforced value,
        and that must still surface as a real MISMATCH, not disappear."""
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
            "scripts/foo.py",
            "# Reinforced creepage at Pollution Degree 2: 8.0mm.\n"
            "HV_CREEPAGE_PD2_MM = 8.0\n"
            "HV_CREEPAGE_PD3_MM = 12.6  # flagged default; UNRESOLVED\n"
            "\n"
            "HV_CREEPAGE_ENFORCED_MM = HV_CREEPAGE_PD3_MM\n",
        )
        decls = discover_ato(tmp_path) + discover_python(tmp_path)[0]
        families, flagged, unresolved, known_blind_spots, declared_not_enforced = build_families(decls)
        fam = next(f for f in families if f.metric == "creepage" and f.tier == "reinforced")
        assert not fam.is_consistent
        assert set(fam.distinct_values.keys()) == {8.0, 12.6}
        # The unselected PD2 candidate (8.0, matching the .ato figure only
        # by coincidence of value) must NOT be sitting in this family --
        # only the genuinely enforced PD3 (12.6) participates.
        assert not any(d.name == "HV_CREEPAGE_PD2_MM" for d in fam.members)
        assert any(d.name == "HV_CREEPAGE_PD3_MM" for d in fam.members)
        assert "HV_CREEPAGE_PD2_MM" in {d.name for d in declared_not_enforced}

    def test_alias_to_unresolvable_name_is_left_unresolved_not_marked(self, tmp_path: Path) -> None:
        """An alias whose RHS name is not an in-file literal (e.g. an
        imported symbol) must fall through to the pre-existing UNRESOLVED
        handling (_resolve_python_aliases already leaves value_mm as None
        in that case) rather than being silently treated as a clean
        selection with nothing to mark."""
        _mk(
            tmp_path,
            "scripts/foo.py",
            "from other_module import SOME_IMPORTED_MM\nHV_CREEPAGE_ENFORCED_MM = SOME_IMPORTED_MM\n",
        )
        decls, errors = discover_python(tmp_path)
        assert not errors
        assert len(decls) == 1
        d = decls[0]
        assert d.value_mm is None
        assert not d.declared_not_enforced

    def test_stale_selection_alias_whose_target_loses_its_tier_is_gate_error(self, tmp_path: Path) -> None:
        """Self-verification: if a refactor strips the enforced target's own
        tier-giving comment (so the target itself now lands in `flagged`,
        not a comparable family), the mechanism must fail loudly. Left
        unchecked, this would silently stop comparing the enforced value
        against anything while still claiming (via the declared-not-
        enforced heading) that some other site enforces it -- the exact
        "comparing nothing" degradation requirement 5 rules out."""
        _mk(
            tmp_path,
            "scripts/foo.py",
            "HV_CREEPAGE_PD2_MM = 8.0\n"  # no tier-giving comment at all
            "HV_CREEPAGE_PD3_MM = 12.6  # flagged default; UNRESOLVED\n"
            "\n"
            "HV_CREEPAGE_ENFORCED_MM = HV_CREEPAGE_PD2_MM\n",
        )
        decls, errors = discover_python(tmp_path)
        assert not errors
        by_name = {d.name: d for d in decls}
        assert by_name["HV_CREEPAGE_PD2_MM"].tier == "unspecified"
        with pytest.raises(GateError):
            build_families(decls)


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


class TestRoleAwareAuthority:
    @staticmethod
    def _family() -> FamilyResult:
        return FamilyResult(
            metric="clearance",
            tier="reinforced",
            members=[
                Declaration(
                    file="packages/temper-placer/configs/netclass_rules.yaml",
                    line=1,
                    name="classes.HighVoltage.clearance",
                    metric="clearance",
                    metric_confidence="direct",
                    tier="reinforced",
                    value_mm=2.0,
                    raw="clearance: 2.0",
                    context="reinforced",
                ),
                Declaration(
                    file="elec/src/constraints.ato",
                    line=2,
                    name="HV_to_LV.min_clearance",
                    metric="clearance",
                    metric_confidence="direct",
                    tier="reinforced",
                    value_mm=6.0,
                    raw="min_clearance = 6.0mm",
                    context="reinforced",
                ),
                Declaration(
                    file="packages/temper-placer/configs/netclass_rules.yaml",
                    line=3,
                    name="classes.HighVoltageIsolated.clearance",
                    metric="clearance",
                    metric_confidence="direct",
                    tier="reinforced",
                    value_mm=6.0,
                    raw="clearance: 6.0",
                    context="reinforced",
                ),
            ],
        )

    def test_role_aware_verdict_is_digest_bound_and_review_visible(self) -> None:
        family = self._family()
        contract = {
            "schema_version": "temper-isolation-authority/v1",
            "contract_digest": "c" * 64,
            "topology_authority_digest": "t" * 64,
            "rows": [
                {
                    "key": f"authority.{index}",
                    "role": role,
                    "source": f"source-{index}",
                    "review_status": "current_edition_review_required",
                    "applicable_minimum_key": "minimum",
                }
                for index, role in enumerate(
                    ["fabrication_check", "conservative_design_target", "fabrication_check"]
                )
            ],
            "projections": [
                {
                    "file": row.file,
                    "name": row.name,
                    "authority_key": f"authority.{index}",
                    "value_mm": row.value_mm,
                }
                for index, row in enumerate(family.members)
            ],
        }

        def evaluate(request_json: str) -> str:
            request = json.loads(request_json)
            canonical = json.dumps(
                [request["schema_version"], sorted(request["rows"], key=lambda row: (row["file"], row["name"]))],
                separators=(",", ":"),
            )
            return json.dumps(
                {
                    "schema_version": "temper-isolation-verdict/v1",
                    "request_digest": sha256(canonical.encode()).hexdigest(),
                    "canonical_request_json": canonical,
                    "contract_schema_version": contract["schema_version"],
                    "contract_digest": contract["contract_digest"],
                    "topology_authority_digest": contract["topology_authority_digest"],
                    "role_resolved": True,
                    "results": [
                        {
                            "file": row.file,
                            "name": row.name,
                            "authority_key": f"authority.{index}",
                            "role": contract["rows"][index]["role"],
                            "value_mm": row.value_mm,
                            "relation": "at_or_above_applicable_minimum",
                            "source": contract["rows"][index]["source"],
                            "review_status": "current_edition_review_required",
                        }
                        for index, row in enumerate(family.members)
                    ],
                    "review_required": ["clearance.hv_lv.120v_ovc2.minimum"],
                }
            )

        verdict = _resolve_reinforced_clearance_authority(
            family,
            contract_json=json.dumps(contract),
            evaluator=evaluate,
        )

        assert verdict["role_resolved"] is True
        assert verdict["review_required"] == ["clearance.hv_lv.120v_ovc2.minimum"]

        malformed = json.loads(evaluate(json.dumps({"schema_version": "x", "rows": []})))
        malformed["results"][0].pop("role")
        with pytest.raises(GateError, match="changed role"):
            _resolve_reinforced_clearance_authority(
                family,
                contract_json=json.dumps(contract),
                evaluator=lambda _request: json.dumps(malformed),
            )

    @pytest.mark.parametrize(
        "mutation",
        ["contract_digest", "result_coverage", "canonical_request", "review_required"],
    )
    def test_digest_or_coverage_loss_fails_closed(self, mutation: str) -> None:
        family = self._family()
        contract = {
            "schema_version": "temper-isolation-authority/v1",
            "contract_digest": "c" * 64,
            "topology_authority_digest": "t" * 64,
            "rows": [
                {
                    "key": f"authority.{index}",
                    "role": "fabrication_check",
                    "source": f"source-{index}",
                    "review_status": "current_edition_review_required",
                    "applicable_minimum_key": "minimum",
                }
                for index, _row in enumerate(family.members)
            ],
            "projections": [
                {
                    "file": row.file,
                    "name": row.name,
                    "authority_key": f"authority.{index}",
                    "value_mm": row.value_mm,
                }
                for index, row in enumerate(family.members)
            ],
        }

        def bad_evaluator(request_json: str) -> str:
            request = json.loads(request_json)
            canonical = json.dumps(
                [
                    request["schema_version"],
                    sorted(request["rows"], key=lambda row: (row["file"], row["name"])),
                ],
                separators=(",", ":"),
            )
            verdict = {
                "schema_version": "temper-isolation-verdict/v1",
                "request_digest": sha256(canonical.encode()).hexdigest(),
                "canonical_request_json": canonical,
                "contract_schema_version": contract["schema_version"],
                "contract_digest": contract["contract_digest"],
                "topology_authority_digest": contract["topology_authority_digest"],
                "role_resolved": True,
                "results": [
                    {
                        "file": row.file,
                        "name": row.name,
                        "authority_key": f"authority.{index}",
                        "role": "fabrication_check",
                        "value_mm": row.value_mm,
                        "relation": "at_or_above_applicable_minimum",
                        "source": f"source-{index}",
                        "review_status": "current_edition_review_required",
                    }
                    for index, row in enumerate(family.members)
                ],
                "review_required": ["clearance.hv_lv.120v_ovc2.minimum"],
            }
            if mutation == "contract_digest":
                verdict["contract_digest"] = "wrong"
            elif mutation == "result_coverage":
                verdict["results"] = verdict["results"][:-1]
            elif mutation == "canonical_request":
                verdict["canonical_request_json"] = "[]"
            else:
                verdict["review_required"] = []
            return json.dumps(verdict)

        with pytest.raises(GateError):
            _resolve_reinforced_clearance_authority(
                family,
                contract_json=json.dumps(contract),
                evaluator=bad_evaluator,
            )

    def test_half_configured_authority_transport_fails_closed(self) -> None:
        family = self._family()
        with pytest.raises(GateError, match="must provide both"):
            _resolve_reinforced_clearance_authority(family, contract_json="{}")
        with pytest.raises(GateError, match="must provide both"):
            _resolve_reinforced_clearance_authority(
                family, evaluator=lambda _request: "{}"
            )

    def test_production_discovery_and_real_rust_authority_agree(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        pytest.importorskip("temper_design_bundle_python")

        state, report, families, *_ = run(repo_root)

        assert state == "clean"
        governed = next(
            family
            for family in families
            if (family.metric, family.tier) == ("clearance", "reinforced")
        )
        assert {(row.file, row.name) for row in governed.members} == {
            (
                "packages/temper-placer/configs/netclass_rules.yaml",
                "classes.HighVoltage.clearance",
            ),
            ("elec/src/constraints.ato", "HV_to_LV.min_clearance"),
            (
                "packages/temper-placer/configs/netclass_rules.yaml",
                "classes.HighVoltageIsolated.clearance",
            ),
        }
        assert report.role_resolutions[("clearance", "reinforced")]["role_resolved"] is True

# ---------------------------------------------------------------------------
# End-to-end
# ---------------------------------------------------------------------------


class TestFunctionalTier:
    def test_functional_tier_forms_its_own_family(self, tmp_path: Path) -> None:
        """IEC 60335-1 Table 18 functional-insulation figures are a real
        tier in their own right: two functional creepage declarations are
        compared against each other, and never against reinforced figures."""
        _mk_scan_roots(tmp_path)
        _mk(
            tmp_path,
            "packages/temper-placer/src/temper_placer/placer/cp_sat/tank_creepage.py",
            "#: IEC 60335-1 Table 18 (functional insulation, cl. 29.2.4), row vi\n"
            "HV_TANK_CREEPAGE_PD2_MM = 6.3\n"
            "#: Same row of Table 18 (functional insulation), PD3\n"
            "HV_TANK_CREEPAGE_PD3_MM = 10.0\n",
        )
        _mk(
            tmp_path,
            "packages/temper-placer/configs/netclass_rules.yaml",
            "classes:\n"
            "  HighVoltageTank:\n"
            '    because: "IEC 60335-1 Table 18 (functional insulation, cl. 29.2.4) PD2 = 6.3mm"\n'
            "    creepage_mm: 6.3\n"
            "  HighVoltage:\n"
            '    because: "IEC 60335-1 reinforced insulation (Table 17 row iv x2)"\n'
            "    creepage_mm: 12.6\n",
        )
        decls = discover_python(tmp_path)[0] + discover_yaml(tmp_path)[0]
        families, flagged, unresolved, known_blind_spots, declared_not_enforced = build_families(decls)
        func_fam = next(f for f in families if f.metric == "creepage" and f.tier == "functional")
        assert not func_fam.is_consistent
        assert set(func_fam.distinct_values.keys()) == {6.3, 10.0}
        # The reinforced figure stays in its own family, never merged with
        # the functional one.
        ref_fam = next(f for f in families if f.metric == "creepage" and f.tier == "reinforced")
        assert set(ref_fam.distinct_values.keys()) == {12.6}

    def test_functional_mentioned_as_context_keeps_more_specific_tier(self, tmp_path: Path) -> None:
        """The measured rejection case for a naive 'functional' keyword add:
        HighVoltageIsolated's `because` reads 'reinforced separation to
        LV/SELV, functional-only to its own HV/ACMains neighbours' -- the
        VALUE is reinforced, 'functional' is only context. Functional must
        be classified LAST so this stays in the reinforced family."""
        _mk_scan_roots(tmp_path)
        _mk(
            tmp_path,
            "packages/temper-placer/configs/netclass_rules.yaml",
            "classes:\n"
            "  HighVoltageIsolated:\n"
            '    because: "reinforced separation to LV/SELV, functional-only to its own HV/ACMains neighbours"\n'
            "    creepage_mm: 6.0\n",
        )
        decls = discover_yaml(tmp_path)[0]
        families, flagged, unresolved, known_blind_spots, declared_not_enforced = build_families(decls)
        ref_fam = next(f for f in families if f.metric == "creepage" and f.tier == "reinforced")
        assert [d.value_mm for d in ref_fam.members] == [6.0]
        assert not any(f.tier == "functional" for f in families)

    def test_pure_functional_tank_selection_alias_keeps_enforced_value_in_family(
        self, tmp_path: Path
    ) -> None:
        """The tank_creepage.py shape after 2026-08-15: a bare-name selection
        alias whose target is a Table 18 functional figure. The enforced
        value must participate in its (creepage, functional) family and the
        unselected PD2 sibling must be reported as declared-not-enforced --
        this is the alias self-verification contract applied to the
        functional tier."""
        _mk_scan_roots(tmp_path)
        _mk(
            tmp_path,
            "packages/temper-placer/src/temper_placer/placer/cp_sat/tank_creepage.py",
            "#: IEC 60335-1 Table 18 (functional insulation, cl. 29.2.4), row vi, PD2\n"
            "HV_TANK_CREEPAGE_PD2_MM = 6.3\n"
            "#: Same row of Table 18 (functional insulation), PD3\n"
            "HV_TANK_CREEPAGE_PD3_MM = 10.0\n"
            "DEFAULT_TANK_CREEPAGE_MM = HV_TANK_CREEPAGE_PD3_MM\n",
        )
        decls = discover_python(tmp_path)[0]
        families, flagged, unresolved, known_blind_spots, declared_not_enforced = build_families(decls)
        func_fam = next(f for f in families if f.metric == "creepage" and f.tier == "functional")
        # Both the enforced constant and its selection alias participate at
        # 10.0mm -- the alias is a selector, not a candidate, but it is a
        # live declaration and is compared like any other.
        assert [d.value_mm for d in func_fam.members] == [10.0, 10.0]
        assert any(d.name == "HV_TANK_CREEPAGE_PD3_MM" for d in func_fam.members)
        assert any(d.name == "DEFAULT_TANK_CREEPAGE_MM" for d in func_fam.members)
        assert len(declared_not_enforced) == 1
        assert declared_not_enforced[0].value_mm == 6.3
        assert declared_not_enforced[0].enforced_value_mm == 10.0


class TestAcceptedDrift:
    def test_registry_entries_are_reviewed_families(self) -> None:
        """Every ACCEPTED_DRIFT entry must name a real (metric, tier) pair
        with a non-empty reviewed value set and a non-empty justification --
        catches a typo'd key that would silently protect nothing."""
        from check_creepage_clearance_drift import ACCEPTED_DRIFT

        assert ACCEPTED_DRIFT
        for (metric, tier), entry in ACCEPTED_DRIFT.items():
            assert entry.metric == metric
            assert entry.tier == tier
            assert entry.accepted_values_mm
            assert entry.justification
            assert metric in {"creepage", "clearance"}
            assert tier in {"reinforced", "basic", "working", "functional"}

    def test_accepted_family_members_still_fully_discovered_and_reported(self, tmp_path: Path) -> None:
        """Acceptance must not hide the family: every member of an accepted
        mismatched family still appears in the report's family list with its
        value, and the report still shows the mismatch -- only the violation
        exit state is relaxed."""
        _mk_scan_roots(tmp_path)
        _mk(
            tmp_path,
            "elec/src/constraints.ato",
            "module Constraints:\n"
            "    # ACMains to Default: Basic insulation\n"
            "    module AC_to_LV:\n"
            "        min_clearance = 3.0mm\n",
        )
        _mk(
            tmp_path,
            "configs/temper_deterministic_config.yaml",
            "net_class_rules:\n"
            "  HighVoltage:\n"
            "    # basic insulation at the mains_240v voltage bucket\n"
            "    clearance_mm: 6.0\n",
        )
        state, report, families, flagged, unresolved, known_blind_spots, declared_not_enforced = run(tmp_path)
        assert state == "clean"
        basic_fam = next(f for f in families if f.metric == "clearance" and f.tier == "basic")
        assert not basic_fam.is_consistent
        assert set(basic_fam.distinct_values.keys()) == {3.0, 6.0}
        assert len(basic_fam.members) == 2


class TestEndToEnd:
    def _write_agreeing_tree(self, tmp_path: Path) -> None:
        _mk_scan_roots(tmp_path)
        _mk(
            tmp_path,
            "elec/src/constraints.ato",
            "module Constraints:\n"
            "    # HighVoltage to Default: Reinforced insulation\n"
            "    module HV_to_LV:\n"
            "        min_creepage = 12.6mm\n",
        )
        _mk(
            tmp_path,
            "scripts/check_isolation_keepout.py",
            "# REINFORCED creepage, pollution degree 3 (PD3 GOVERNS)\n"
            "MIN_BARRIER_WIDTH_MM = 12.6\n",
        )

    def test_agreeing_tree_is_clean(self, tmp_path: Path) -> None:
        self._write_agreeing_tree(tmp_path)
        state, report, families, flagged, unresolved, known_blind_spots, declared_not_enforced = run(tmp_path)
        assert state == "clean"
        assert not known_blind_spots
        assert report.declarations
        assert any(f.metric == "creepage" and f.tier == "reinforced" for f in families)
        for fam in families:
            assert fam.is_consistent

    def test_retargeted_tree_reproduces_the_task_defect(self, tmp_path: Path) -> None:
        """Reproduces the exact shape of the verified defect: the gate
        (check_isolation_keepout.py) was retargeted to PD3 (12.6mm) but the
        .ato source of truth was not -- the gate must fail, non-vacuously,
        naming both sites and both values.

        Since 2026-08-15 the (creepage, reinforced) family is registered in
        ACCEPTED_DRIFT with the reviewed value set {6.0, 12.6}mm (see that
        registry's justification -- the PD2 figure 8.0mm is explicitly NOT
        accepted). A synthetic tree in which the .ato still carries the
        pre-retarget 8.0mm PD2 figure therefore fails CLOSED (GateError:
        the family drifted beyond its reviewed values and must be
        re-reviewed), which is the correct, loud failure for exactly the
        defect shape this test reproduces -- a reappearing PD2 figure must
        never be silently absorbed by the acceptance."""
        self._write_agreeing_tree(tmp_path)
        _mk(
            tmp_path,
            "elec/src/constraints.ato",
            "module Constraints:\n"
            "    # HighVoltage to Default: Reinforced insulation\n"
            "    module HV_to_LV:\n"
            "        min_creepage = 8.0mm\n",
        )
        with pytest.raises(GateError):
            run(tmp_path)

    def test_accepted_mismatch_within_reviewed_values_is_not_a_violation(self, tmp_path: Path) -> None:
        """A mismatched family whose spread is inside its ACCEPTED_DRIFT
        reviewed value set is still discovered and still printed in full,
        but does not set the violation state -- that is the mechanism that
        lets the gate run green in CI despite investigated, accepted
        cross-source disagreements. 6.0mm is the UNSOURCED-legacy member of
        the (creepage, reinforced) acceptance; 12.6mm is the enforced PD3
        member."""
        _mk_scan_roots(tmp_path)
        _mk(
            tmp_path,
            "elec/src/constraints.ato",
            "module Constraints:\n"
            "    # HighVoltage to Default: Reinforced insulation\n"
            "    module HV_to_LV:\n"
            "        min_creepage = 12.6mm\n",
        )
        _mk(
            tmp_path,
            "scripts/check_isolation_keepout.py",
            "# REINFORCED creepage, PD3-pinned enforcement\n"
            "MIN_BARRIER_WIDTH_MM = 12.6\n",
        )
        _mk(
            tmp_path,
            "packages/temper-placer/configs/netclass_rules.yaml",
            "classes:\n"
            "  HighVoltage:\n"
            "    # UNSOURCED legacy reinforced figure, re-sourcing deferred (2026-08-15)\n"
            "    creepage_mm: 6.0\n",
        )
        state, report, families, flagged, unresolved, known_blind_spots, declared_not_enforced = run(tmp_path)
        assert state == "clean"
        reinforced_creepage = next(f for f in families if f.metric == "creepage" and f.tier == "reinforced")
        assert not reinforced_creepage.is_consistent
        assert set(reinforced_creepage.distinct_values.keys()) == {6.0, 12.6}
