"""Tests for check_hv_netclass_coverage.py.

See docs/evidence/2026-07-29-hv-netclass-coverage-gate.md for the real
before/after proof against the actual historical defect: run against
``origin/main`` this gate fails naming ``+170V_BUS`` (unclassified) and
``HighVoltageIsolated`` (declared netclass, zero rules) specifically; run
against this branch (``fix/recover-stranded-netclass-safety``'s fixes
present) it passes clean.

These tests deliberately do NOT depend on a real installed
``temper_placer`` package or a real ``pcb/temper.kicad_pro`` on disk for
the mutation-style cases below -- ``run()`` accepts ``net_classes`` /
``net_assignments`` / ``dru_content`` / ``kicad_class_name_fn`` overrides
for exactly this reason (mirrors ``check_net_classification.py``'s
``ScanTarget`` injection and ``check_domain_partition.py``'s synthetic
netlist/manifest fixtures -- the pattern this repo uses so a gate test
never depends on the live repository state to prove a specific mutation
is caught).

Four groups:

1. ``TestMutations`` -- the two falsifiers this task requires: a manifest
   HV net absent from ``net_assignments`` (PROPERTY 1), and a declared
   netclass with zero positive rule references in the generated DRU
   content (PROPERTY 2). Also proves the positive/negative distinction
   (a class mentioned only via ``!=`` does not count) and that fixing
   either mutation independently clears only that property's violation.
2. ``TestAntiVacuity`` -- the gate fails CLOSED (state == "tool_error")
   on every degenerate input: missing/empty/malformed manifest, no HV
   domain, missing/malformed/empty kicad_pro classes list, empty DRU
   content, zero declared netclasses.
3. ``TestHelperUnits`` -- unit tests for the pure helper functions in
   isolation (``check_hv_net_coverage``, ``load_kicad_pro_classes``,
   ``declared_netclasses``, ``positively_referenced_classes``,
   ``check_netclass_rule_coverage``).
4. ``TestRealRepoIntegration`` -- the gate passes clean against the
   actual repo (live imports, live ``pcb/temper.kicad_pro``) as of this
   commit.
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_hv_netclass_coverage import (  # noqa: E402
    EXIT_GATE_ERROR,
    EXIT_OK,
    EXIT_VIOLATION,
    STRUCTURAL_KICAD_CLASSES,
    GateError,
    check_hv_net_coverage,
    check_netclass_rule_coverage,
    declared_netclasses,
    load_hv_nets,
    load_kicad_pro_classes,
    positively_referenced_classes,
    run,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))
    return path


def _manifest(tmp_path: Path, hv_nets: list[str], selv_nets: list[str] | None = None) -> Path:
    """A minimal, valid domain_manifest.yaml fixture: an 'HV' domain with
    the given nets and an 'SELV' domain (>=2 domains required by
    check_domain_partition.load_manifest)."""
    selv_nets = selv_nets or ["gnd", "+3V3"]
    hv_yaml = "\n".join(f'      - "{n}"' for n in hv_nets)
    selv_yaml = "\n".join(f'      - "{n}"' for n in selv_nets)
    # Built with plain concatenation, not textwrap.dedent: the net-list
    # lines are generated at a fixed indentation already, and dedent's
    # common-leading-whitespace computation across the whole (mixed)
    # string would otherwise silently collapse the template's own indent
    # relative to these lines -- confirmed to corrupt the YAML structure
    # when first written with an f-string inside a dedented block.
    text = (
        "schema_version: 1\n"
        "domains:\n"
        "  HV:\n"
        "    nets:\n"
        f"{hv_yaml}\n"
        "  SELV:\n"
        "    nets:\n"
        f"{selv_yaml}\n"
    )
    path = tmp_path / "domain_manifest.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def _kicad_pro(tmp_path: Path, classes: dict[str, str], name: str = "temper.kicad_pro") -> Path:
    """A minimal pcb/temper.kicad_pro fixture: net_settings.classes with
    the given {name: description} entries."""
    path = tmp_path / name
    path.write_text(
        json.dumps(
            {
                "net_settings": {
                    "classes": [
                        {"name": n, "description": d} for n, d in classes.items()
                    ]
                }
            }
        )
    )
    return path


# ---------------------------------------------------------------------------
# TestMutations
# ---------------------------------------------------------------------------


class TestMutations:
    """The two falsifiers this task requires, plus controls proving each
    property is independent of the other."""

    def test_unclassified_hv_net_is_flagged(self, tmp_path):
        """PROPERTY 1 falsifier: reconstructs the +170V_BUS defect --
        an HV-domain net entirely absent from TEMPER_NET_ASSIGNMENTS."""
        manifest = _manifest(tmp_path, hv_nets=["+170V_BUS", "ac_l", "SW_NODE"])
        kicad_pro = _kicad_pro(tmp_path, {"ACMains": "mains"})
        net_classes = {"ACMains": object(), "HighVoltage": object()}
        # "+170V_BUS" is MISSING here -- the exact historical defect shape.
        net_assignments = {"ac_l": "ACMains", "SW_NODE": "HighVoltage"}
        dru_content = "A.NetClass == 'ACMains'\nA.NetClass == 'HighVoltage'\n"

        state, report = run(
            manifest,
            kicad_pro,
            net_classes=net_classes,
            net_assignments=net_assignments,
            dru_content=dru_content,
            kicad_class_name_fn=lambda k: k,
        )
        assert state == "violation"
        assert report.unclassified_hv_nets == ["+170V_BUS"]
        assert report.classes_with_no_rules == []

    def test_classified_hv_net_is_not_flagged(self, tmp_path):
        """Control: the same fixture but with +170V_BUS classified must
        NOT be flagged -- proves the gate doesn't false-positive on a
        correctly-covered net."""
        manifest = _manifest(tmp_path, hv_nets=["+170V_BUS", "ac_l"])
        kicad_pro = _kicad_pro(tmp_path, {"ACMains": "mains"})
        net_classes = {"ACMains": object(), "HighVoltage": object()}
        net_assignments = {"ac_l": "ACMains", "+170V_BUS": "HighVoltage"}
        dru_content = "A.NetClass == 'ACMains'\nA.NetClass == 'HighVoltage'\n"

        state, report = run(
            manifest,
            kicad_pro,
            net_classes=net_classes,
            net_assignments=net_assignments,
            dru_content=dru_content,
            kicad_class_name_fn=lambda k: k,
        )
        assert state == "clean"
        assert report.unclassified_hv_nets == []

    def test_netclass_with_no_rules_is_flagged(self, tmp_path):
        """PROPERTY 2 falsifier: reconstructs the HighVoltageIsolated
        defect -- a declared netclass (present in TEMPER_NET_CLASSES)
        with zero positive rule references in the generated DRU
        content."""
        manifest = _manifest(tmp_path, hv_nets=["ac_l"])
        kicad_pro = _kicad_pro(tmp_path, {"ACMains": "mains"})
        net_classes = {
            "ACMains": object(),
            "HighVoltageIsolated": object(),  # declared, but never referenced below
        }
        net_assignments = {"ac_l": "ACMains"}
        dru_content = "A.NetClass == 'ACMains'\n"  # no HighVoltageIsolated rule at all

        state, report = run(
            manifest,
            kicad_pro,
            net_classes=net_classes,
            net_assignments=net_assignments,
            dru_content=dru_content,
            kicad_class_name_fn=lambda k: k,
        )
        assert state == "violation"
        assert report.classes_with_no_rules == ["HighVoltageIsolated"]
        assert report.unclassified_hv_nets == []

    def test_netclass_declared_only_in_kicad_pro_is_flagged(self, tmp_path):
        """Reconstructs the EXACT origin/main shape: HighVoltageIsolated
        is absent from TEMPER_NET_CLASSES entirely, but IS declared (with
        a real description) in pcb/temper.kicad_pro -- the gate must
        still catch it via the kicad_pro-sourced half of the declared-
        netclass union."""
        manifest = _manifest(tmp_path, hv_nets=["ac_l"])
        kicad_pro = _kicad_pro(
            tmp_path,
            {
                "ACMains": "mains",
                "HighVoltageIsolated": "Bootstrap supply, isolated gate power.",
            },
        )
        net_classes = {"ACMains": object()}  # HighVoltageIsolated NOT here
        net_assignments = {"ac_l": "ACMains"}
        dru_content = "A.NetClass == 'ACMains'\n"

        state, report = run(
            manifest,
            kicad_pro,
            net_classes=net_classes,
            net_assignments=net_assignments,
            dru_content=dru_content,
            kicad_class_name_fn=lambda k: k,
        )
        assert state == "violation"
        assert report.classes_with_no_rules == ["HighVoltageIsolated"]

    def test_netclass_with_only_negative_reference_is_still_flagged(self, tmp_path):
        """A class mentioned only through exclusion (`!= 'X'`) must not
        count as real coverage -- only a positive `== 'X'` match does."""
        manifest = _manifest(tmp_path, hv_nets=["ac_l"])
        kicad_pro = _kicad_pro(tmp_path, {"ACMains": "mains"})
        net_classes = {"ACMains": object(), "HighVoltageIsolated": object()}
        net_assignments = {"ac_l": "ACMains"}
        # "HighVoltageIsolated" appears, but only as an exclusion -- never
        # as a positive match for A or B.
        dru_content = (
            "A.NetClass == 'ACMains' && B.NetClass != 'HighVoltageIsolated'\n"
        )

        state, report = run(
            manifest,
            kicad_pro,
            net_classes=net_classes,
            net_assignments=net_assignments,
            dru_content=dru_content,
            kicad_class_name_fn=lambda k: k,
        )
        assert state == "violation"
        assert report.classes_with_no_rules == ["HighVoltageIsolated"]

    def test_both_mutations_fixed_together_passes(self, tmp_path):
        """Once both the unclassified net and the rule-less class are
        fixed, the gate passes clean -- proves the two properties are
        genuinely independent (fixing one alone leaves the other's
        violation intact, shown by the tests above; fixing both clears
        both)."""
        manifest = _manifest(tmp_path, hv_nets=["+170V_BUS", "ac_l"])
        kicad_pro = _kicad_pro(tmp_path, {"ACMains": "mains"})
        net_classes = {"ACMains": object(), "HighVoltage": object()}
        net_assignments = {"ac_l": "ACMains", "+170V_BUS": "HighVoltage"}
        dru_content = "A.NetClass == 'ACMains'\nA.NetClass == 'HighVoltage'\n"

        state, report = run(
            manifest,
            kicad_pro,
            net_classes=net_classes,
            net_assignments=net_assignments,
            dru_content=dru_content,
            kicad_class_name_fn=lambda k: k,
        )
        assert state == "clean"
        assert report.unclassified_hv_nets == []
        assert report.classes_with_no_rules == []

    def test_structural_kicad_classes_are_excluded(self, tmp_path):
        """'Default' and 'Differential' (KiCad-structural, non-safety
        classes, pre-existing and unrelated to this gate's defect) must
        never be flagged even with zero positive rule references."""
        manifest = _manifest(tmp_path, hv_nets=["ac_l"])
        kicad_pro = _kicad_pro(
            tmp_path,
            {
                "ACMains": "mains",
                "Default": "General signals fallback.",
                "Differential": "",
            },
        )
        net_classes = {"ACMains": object()}
        net_assignments = {"ac_l": "ACMains"}
        dru_content = "A.NetClass == 'ACMains'\n"  # no Default/Differential rule at all

        state, report = run(
            manifest,
            kicad_pro,
            net_classes=net_classes,
            net_assignments=net_assignments,
            dru_content=dru_content,
            kicad_class_name_fn=lambda k: k,
        )
        assert state == "clean"
        assert "Default" not in report.classes_with_no_rules
        assert "Differential" not in report.classes_with_no_rules
        assert STRUCTURAL_KICAD_CLASSES == frozenset({"Default", "Differential"})


# ---------------------------------------------------------------------------
# TestAntiVacuity
# ---------------------------------------------------------------------------


class TestAntiVacuity:
    def test_missing_manifest_is_gate_error(self, tmp_path):
        kicad_pro = _kicad_pro(tmp_path, {"ACMains": "mains"})
        state, report = run(
            tmp_path / "does-not-exist.yaml",
            kicad_pro,
            net_classes={"ACMains": object()},
            net_assignments={},
            dru_content="A.NetClass == 'ACMains'\n",
            kicad_class_name_fn=lambda k: k,
        )
        assert state == "tool_error"
        assert report.tool_errors

    def test_empty_manifest_is_gate_error(self, tmp_path):
        manifest = _write(tmp_path / "empty.yaml", "")
        kicad_pro = _kicad_pro(tmp_path, {"ACMains": "mains"})
        state, report = run(
            manifest,
            kicad_pro,
            net_classes={"ACMains": object()},
            net_assignments={},
            dru_content="A.NetClass == 'ACMains'\n",
            kicad_class_name_fn=lambda k: k,
        )
        assert state == "tool_error"

    def test_manifest_with_no_hv_domain_is_gate_error(self, tmp_path):
        manifest = _write(
            tmp_path / "no_hv.yaml",
            """\
            schema_version: 1
            domains:
              SELV:
                nets:
                  - gnd
              OTHER:
                nets:
                  - foo
            """,
        )
        kicad_pro = _kicad_pro(tmp_path, {"ACMains": "mains"})
        with pytest.raises(GateError):
            load_hv_nets(manifest)
        state, report = run(
            manifest,
            kicad_pro,
            net_classes={"ACMains": object()},
            net_assignments={},
            dru_content="A.NetClass == 'ACMains'\n",
            kicad_class_name_fn=lambda k: k,
        )
        assert state == "tool_error"

    def test_missing_kicad_pro_is_gate_error(self, tmp_path):
        manifest = _manifest(tmp_path, hv_nets=["ac_l"])
        state, report = run(
            manifest,
            tmp_path / "does-not-exist.kicad_pro",
            net_classes={"ACMains": object()},
            net_assignments={"ac_l": "ACMains"},
            dru_content="A.NetClass == 'ACMains'\n",
            kicad_class_name_fn=lambda k: k,
        )
        assert state == "tool_error"

    def test_malformed_kicad_pro_json_is_gate_error(self, tmp_path):
        manifest = _manifest(tmp_path, hv_nets=["ac_l"])
        bad = _write(tmp_path / "bad.kicad_pro", "{not valid json")
        state, report = run(
            manifest,
            bad,
            net_classes={"ACMains": object()},
            net_assignments={"ac_l": "ACMains"},
            dru_content="A.NetClass == 'ACMains'\n",
            kicad_class_name_fn=lambda k: k,
        )
        assert state == "tool_error"

    def test_empty_kicad_pro_classes_is_gate_error(self, tmp_path):
        manifest = _manifest(tmp_path, hv_nets=["ac_l"])
        kicad_pro = _kicad_pro(tmp_path, {})
        state, report = run(
            manifest,
            kicad_pro,
            net_classes={"ACMains": object()},
            net_assignments={"ac_l": "ACMains"},
            dru_content="A.NetClass == 'ACMains'\n",
            kicad_class_name_fn=lambda k: k,
        )
        assert state == "tool_error"

    def test_empty_dru_content_is_gate_error(self, tmp_path):
        manifest = _manifest(tmp_path, hv_nets=["ac_l"])
        kicad_pro = _kicad_pro(tmp_path, {"ACMains": "mains"})
        state, report = run(
            manifest,
            kicad_pro,
            net_classes={"ACMains": object()},
            net_assignments={"ac_l": "ACMains"},
            dru_content="   \n  ",
            kicad_class_name_fn=lambda k: k,
        )
        assert state == "tool_error"

    def test_zero_declared_netclasses_is_gate_error(self, tmp_path):
        """net_classes empty and kicad_pro's only class is structural
        (Default) -- zero declared netclasses to check at all."""
        manifest = _manifest(tmp_path, hv_nets=["ac_l"])
        kicad_pro = _kicad_pro(tmp_path, {"Default": "fallback"})
        state, report = run(
            manifest,
            kicad_pro,
            net_classes={},
            net_assignments={"ac_l": "ACMains"},
            dru_content="A.Type == 'Track'\n",
            kicad_class_name_fn=lambda k: k,
        )
        assert state == "tool_error"

    def test_unimportable_live_environment_is_gate_error(self, tmp_path):
        """If none of the override params are given and temper_placer
        cannot be imported, the gate must fail closed, not crash or
        silently pass. This exercises _default_live_inputs' own
        ImportError handling without needing to actually break the real
        environment."""
        import check_hv_netclass_coverage as mod

        original = mod._default_live_inputs

        def _boom():
            raise mod.GateError("simulated: temper_placer not importable")

        mod._default_live_inputs = _boom
        try:
            manifest = _manifest(tmp_path, hv_nets=["ac_l"])
            kicad_pro = _kicad_pro(tmp_path, {"ACMains": "mains"})
            state, report = run(manifest, kicad_pro)
            assert state == "tool_error"
            assert any("simulated" in e for e in report.tool_errors)
        finally:
            mod._default_live_inputs = original


# ---------------------------------------------------------------------------
# TestHelperUnits
# ---------------------------------------------------------------------------


class TestHelperUnits:
    def test_check_hv_net_coverage_sorted_and_exact(self):
        hv_nets = ["c", "a", "b"]
        assignments = {"a": "X"}
        assert check_hv_net_coverage(hv_nets, assignments) == ["b", "c"]

    def test_check_hv_net_coverage_all_covered(self):
        assert check_hv_net_coverage(["a", "b"], {"a": "X", "b": "Y"}) == []

    def test_load_kicad_pro_classes_reads_descriptions(self, tmp_path):
        path = _kicad_pro(tmp_path, {"ACMains": "mains desc", "Differential": ""})
        result = load_kicad_pro_classes(path)
        assert result == {"ACMains": "mains desc", "Differential": ""}

    def test_load_kicad_pro_classes_missing_name_is_gate_error(self, tmp_path):
        path = tmp_path / "bad.kicad_pro"
        path.write_text(json.dumps({"net_settings": {"classes": [{"description": "x"}]}}))
        with pytest.raises(GateError):
            load_kicad_pro_classes(path)

    def test_declared_netclasses_union_excludes_structural(self):
        net_classes = {"ACMains": object(), "HighVoltage": object()}
        kicad_pro_classes = {
            "ACMains": "mains",
            "HighVoltageIsolated": "bootstrap",
            "Default": "fallback",
            "Differential": "",
        }
        result = declared_netclasses(net_classes, kicad_pro_classes)
        assert result == {"ACMains", "HighVoltage", "HighVoltageIsolated"}

    def test_positively_referenced_classes_ignores_negation(self):
        content = "A.NetClass == 'Foo' && B.NetClass != 'Bar'\nB.NetClass == 'Baz'\n"
        assert positively_referenced_classes(content) == {"Foo", "Baz"}

    def test_positively_referenced_classes_empty_content(self):
        assert positively_referenced_classes("") == set()

    def test_check_netclass_rule_coverage_maps_through_kicad_name_fn(self):
        declared = {"GND", "ACMains"}
        referenced = {"Ground", "ACMains"}
        result = check_netclass_rule_coverage(
            declared, lambda k: {"GND": "Ground"}.get(k, k), referenced
        )
        assert result == []

    def test_check_netclass_rule_coverage_flags_missing(self):
        declared = {"GND", "HighVoltageIsolated"}
        referenced = {"Ground"}
        result = check_netclass_rule_coverage(
            declared, lambda k: {"GND": "Ground"}.get(k, k), referenced
        )
        assert result == ["HighVoltageIsolated"]


# ---------------------------------------------------------------------------
# TestRealRepoIntegration
# ---------------------------------------------------------------------------


class TestRealRepoIntegration:
    def test_gate_passes_clean_against_real_repo(self):
        """The gate, run with the real elec/domain_manifest.yaml,
        pcb/temper.kicad_pro, and live temper_placer/generate_kicad_dru
        imports, passes clean as of this commit (PR #440's fixes
        present). If temper_placer is not importable in this environment
        the test is skipped rather than xfailed -- a real environment gap
        is not this gate's own defect."""
        try:
            import temper_placer.core.design_rules  # noqa: F401
        except ImportError:
            pytest.skip("temper_placer not importable in this environment")

        manifest = REPO_ROOT / "elec" / "domain_manifest.yaml"
        kicad_pro = REPO_ROOT / "pcb" / "temper.kicad_pro"
        state, report = run(manifest, kicad_pro)
        assert state == "clean", (
            f"unclassified_hv_nets={report.unclassified_hv_nets} "
            f"classes_with_no_rules={report.classes_with_no_rules} "
            f"tool_errors={report.tool_errors}"
        )
        assert report.hv_nets_checked > 0
        assert report.declared_netclasses_checked > 0

    def test_exit_codes_match_module_constants(self):
        assert EXIT_OK == 0
        assert EXIT_VIOLATION == 3
        assert EXIT_GATE_ERROR == 5
