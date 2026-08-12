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

Six groups:

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
   commit -- including PROPERTY 3, which really did evaluate (not
   silently skip) and really is clean (``PWR_RTN`` fixed).
5. ``TestPropertyThreeAndFour`` -- the falsifier this task actually
   exists for: an HV-domain net with a real ``pcb/temper.kicad_pro``
   (the ``netclass_assignments`` key present) but no entry for it -- the
   exact ``PWR_RTN`` shape, reconstructed as a synthetic fixture. Also:
   off-board HV nets, wrong-safety-category HV assignments, and proof
   that the SELV/ghost-assignment findings (PROPERTY 4) are reported but
   never flip the gate to "violation".
6. ``TestBoardNetParsing`` -- ``parse_board_net_names`` is structural, not
   a grep: a pad's own nested ``(net ...)`` reference (which contains the
   exact substring a grep-based scan would match) must never be counted,
   only genuine top-level ``(net N "name")`` declarations.
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_hv_netclass_coverage import (  # noqa: E402
    EXIT_GATE_ERROR,
    EXIT_OK,
    EXIT_VIOLATION,
    STRUCTURAL_KICAD_CLASSES,
    GateError,
    check_domain_class_safety_mismatch,
    check_domain_net_kicad_pro_coverage,
    check_domain_nets_on_board,
    check_ghost_kicad_pro_assignments,
    check_hv_net_coverage,
    check_netclass_rule_coverage,
    declared_netclasses,
    load_hv_nets,
    load_kicad_pro_classes,
    load_kicad_pro_netclass_assignments,
    load_netclass_safety_categories,
    load_selv_nets,
    parse_board_net_names,
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


def _kicad_pro(
    tmp_path: Path,
    classes: dict[str, str],
    name: str = "temper.kicad_pro",
    assignments: dict[str, str] | None = None,
) -> Path:
    """A minimal pcb/temper.kicad_pro fixture: net_settings.classes with
    the given {name: description} entries. ``assignments`` is OMITTED by
    default (matching every PROPERTY 1/2-only test above -- PROPERTY 3/4
    are then simply not evaluated, per their own contract); pass a dict
    (even {}) to opt a test into PROPERTY 3/4."""
    path = tmp_path / name
    net_settings: dict[str, object] = {
        "classes": [{"name": n, "description": d} for n, d in classes.items()]
    }
    if assignments is not None:
        net_settings["netclass_assignments"] = assignments
    path.write_text(json.dumps({"net_settings": net_settings}))
    return path


def _kicad_pcb(tmp_path: Path, net_names: list[str], name: str = "temper.kicad_pcb") -> Path:
    """A minimal but structurally-real .kicad_pcb fixture: top-level
    ``(net N "name")`` declarations for every name in *net_names*, PLUS a
    footprint pad carrying its own nested ``(net ...)`` reference to the
    first net (if any) -- reproducing the exact shape
    ``parse_board_net_names`` must not be confused by (a grep for ``(net``
    would match both; the structural parser must match only the former).
    """
    lines = ["(kicad_pcb", "  (version 20240108)", "  (generator test)"]
    for i, n in enumerate(net_names, start=1):
        lines.append(f'  (net {i} "{n}")')
    if net_names:
        lines.append(
            "  (footprint \"test:pad\" (layer \"F.Cu\")\n"
            "    (fp_text reference \"REF1\")\n"
            "    (pad \"1\" smd rect (at 0 0) (size 1 1) (layers \"F.Cu\")\n"
            f'      (net 1 "{net_names[0]}"))\n'
            "  )"
        )
    lines.append(")")
    path = tmp_path / name
    path.write_text("\n".join(lines))
    return path


def _netclass_rules(
    tmp_path: Path, categories: dict[str, str], name: str = "netclass_rules.yaml"
) -> Path:
    """A minimal packages/temper-placer/configs/netclass_rules.yaml
    fixture: classes: {name: {safety_category: ...}}."""
    lines = ["classes:"]
    for cls, category in categories.items():
        lines.append(f"  {cls}:")
        lines.append(f'    safety_category: "{category}"')
    path = tmp_path / name
    path.write_text("\n".join(lines) + "\n")
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
# TestMetamorphic -- property-based relations between the gate and the
# safety-category SSOT, and between the gate's two independent input
# parsers. See the module docstring of check_hv_netclass_coverage.py for
# what each property means; these tests assert the gate's *boundaries* over
# arbitrary generated inputs, not just the hand-picked fixtures above.
#
# The repo's actual safety-classification SSOT is
# `NetClassRules.safety_category` in
# `packages/temper-placer/src/temper_placer/core/design_rules.py` (the
# `resolve_safety_category` helper referenced in AGENTS.md's NetClassRules
# section does not exist in this tree -- the field it describes is the
# real authority). The gate's PROPERTY 1 is deliberately a *presence* check
# (see the evidence doc's scope note); the metamorphic relation asserted
# here is that the gate and the SSOT never contradict each other in either
# direction that matters:
#
#   - an HV-correct assignment (net -> class whose safety_category is HV/AC)
#     is NEVER flagged by PROPERTY 1 (the gate accepts everything the SSOT
#     certifies as HV-safe), and
#   - a net with NO assignment is ALWAYS flagged (the gate is exactly
#     sensitive to the table it claims to check -- no masking).
#
# Plus: parser agreement (check_domain_partition's manifest parser vs an
# independent naive PyYAML traversal on the same text), end-to-end mutation
# sensitivity (removing exactly one assignment / one rule reference flips
# the verdict and names exactly the mutation), and idempotence.
# ---------------------------------------------------------------------------


class _FakeNetClass:
    """Minimal stand-in for NetClassRules: the gate reads only the class
    *name* (dict key); the SSOT oracle in these tests reads
    ``safety_category``. Keeping the stub local means the property tests
    never depend on a live temper_placer install."""

    def __init__(self, safety_category: str | None):
        self.safety_category = safety_category


# Net-name alphabet mirrors what the real manifest uses (exact literal net
# names: letters, digits, + - _ . /). Double quotes, backslashes (YAML
# escape char), single quotes (the DRU condition grammar `A.NetClass == 'X'`
# captures names as [^']+ -- a quoted name is structurally unrepresentable
# and never occurs in real KiCad netclass names) and newlines are excluded
# by construction.
_NET_NAME = st.text(
    alphabet=st.characters(
        blacklist_categories=("C",), blacklist_characters='"\n\\\''
    ),
    min_size=1,
    max_size=12,
).filter(lambda n: n not in STRUCTURAL_KICAD_CLASSES)

_HV_NETS = st.lists(_NET_NAME, min_size=1, max_size=6, unique=True)

_CATEGORIES = st.sampled_from(["HV", "AC", "LV", None, "iso"])

_CLASS_NAMES = st.lists(
    _NET_NAME, min_size=1, max_size=5, unique=True
).filter(lambda names: len(names) >= 1)


@st.composite
def _ssot_safe_fixture(draw, class_names_strategy=_CLASS_NAMES):
    """(hv_nets, class_names, classes, assignments) where every HV net is
    assigned a class whose safety_category is HV or AC -- the SSOT-safe
    configuration PROPERTY 1 must always accept."""
    hv_nets = draw(_HV_NETS)
    class_names = draw(class_names_strategy)
    classes = {n: _FakeNetClass(draw(_CATEGORIES)) for n in class_names}
    # force at least one HV/AC class so the fixture can be SSOT-safe
    hv_ac = [n for n, c in classes.items() if c.safety_category in ("HV", "AC")]
    if not hv_ac:
        classes[class_names[0]] = _FakeNetClass("HV")
        hv_ac = [class_names[0]]
    assignments = {net: draw(st.sampled_from(hv_ac)) for net in hv_nets}
    return hv_nets, class_names, classes, assignments


# The end-to-end mutation tests need >= 2 classes: with exactly one class,
# removing its only rule reference leaves EMPTY DRU content, which the gate
# correctly fail-closes as tool_error (anti-vacuity), not a violation.
_CLASS_NAMES_2PLUS = st.lists(
    _NET_NAME, min_size=2, max_size=5, unique=True
).filter(lambda names: len(names) >= 2)


@st.composite
def _fixture_with_partial_assignments(draw):
    """(hv_nets, assignments) where each HV net is independently either
    assigned a random class or deliberately left unassigned."""
    hv_nets = draw(_HV_NETS)
    class_names = draw(_CLASS_NAMES)
    assignments = {}
    for net in hv_nets:
        if draw(st.booleans()):
            assignments[net] = draw(st.sampled_from(class_names))
    return hv_nets, assignments


# tmp_path is function-scoped (created once per test call, reused across
# @given examples); every example below writes its own manifest/kicad_pro
# files before reading them back, so no example depends on a previous
# example's files -- the fixture reuse is benign and suppression is sound.
_FIXTURE_SUPPRESS = {"suppress_health_check": [HealthCheck.function_scoped_fixture]}


class TestMetamorphic:
    @settings(max_examples=50, deadline=None, **_FIXTURE_SUPPRESS)
    @given(hv_nets=_HV_NETS, selv_nets=_HV_NETS)
    def test_load_hv_nets_agrees_with_independent_yaml_parser(
        self, tmp_path, hv_nets, selv_nets
    ):
        """Metamorphic relation between two independent code paths that
        both read the manifest: check_domain_partition's own parser (which
        the gate trusts, via load_hv_nets) and a naive PyYAML traversal
        written independently in this test. If they ever disagree on
        arbitrary generated manifests, the gate is reading a different net
        set than the file literally declares."""
        import yaml

        # ensure the two domains are disjoint (load_manifest rejects a net
        # claimed by two domains -- that is its contract, not a fixture bug)
        selv = [n for n in selv_nets if n not in hv_nets] or ["gnd"]
        manifest = _manifest(tmp_path, hv_nets, selv)
        text = manifest.read_text()

        via_gate = load_hv_nets(manifest)
        via_naive = yaml.safe_load(text)["domains"]["HV"]["nets"]

        assert via_gate == via_naive

    @settings(max_examples=50, deadline=None)
    @given(_ssot_safe_fixture())
    def test_property1_never_flags_ssot_safe_assignments(self, fixture):
        """The gate's PROPERTY 1 (presence in TEMPER_NET_ASSIGNMENTS) must
        agree with the safety-category SSOT in the direction that matters:
        every manifest-HV net assigned a class whose safety_category is HV
        or AC -- the configuration the SSOT certifies as HV-safe -- is
        never flagged as unclassified."""
        hv_nets, _, _, assignments = fixture
        assert check_hv_net_coverage(hv_nets, assignments) == []

    @settings(max_examples=50, deadline=None, **_FIXTURE_SUPPRESS)
    @given(_fixture_with_partial_assignments())
    def test_property1_flags_exactly_the_absent_nets(self, fixture):
        """Metamorphic counterpart: PROPERTY 1 flags a net IFF it has no
        assignment -- never more (no net that the SSOT could certify is
        rejected once present), never fewer (an absent assignment is never
        masked by a neighbouring entry)."""
        hv_nets, assignments = fixture
        expected = sorted(set(hv_nets) - set(assignments))
        assert check_hv_net_coverage(hv_nets, assignments) == expected

    @settings(max_examples=40, deadline=None, **_FIXTURE_SUPPRESS)
    @given(_ssot_safe_fixture(_CLASS_NAMES_2PLUS))
    def test_run_is_exactly_sensitive_to_single_mutations(self, tmp_path, fixture):
        """End-to-end: build a fully-covered fixture (all HV nets assigned,
        every declared class positively referenced in the DRU), assert the
        gate runs clean, then remove EXACTLY ONE input and assert the gate
        flips to 'violation' naming exactly that mutation -- for both
        properties, independently. A gate that masked either mutation would
        fail this test."""
        hv_nets, class_names, classes, assignments = fixture
        manifest = _manifest(tmp_path, hv_nets)
        kicad_pro = _kicad_pro(tmp_path, dict.fromkeys(class_names, ""))
        dru_content = "".join(f"A.NetClass == '{n}'\n" for n in class_names)

        state, report = run(
            manifest,
            kicad_pro,
            net_classes=classes,
            net_assignments=assignments,
            dru_content=dru_content,
            kicad_class_name_fn=lambda k: k,
        )
        assert state == "clean", (report.unclassified_hv_nets, report.classes_with_no_rules)

        # Mutation 1: drop exactly one HV net's assignment.
        dropped_net = hv_nets[0]
        mutated_assignments = dict(assignments)
        del mutated_assignments[dropped_net]
        state, report = run(
            manifest,
            kicad_pro,
            net_classes=classes,
            net_assignments=mutated_assignments,
            dru_content=dru_content,
            kicad_class_name_fn=lambda k: k,
        )
        assert state == "violation"
        assert report.unclassified_hv_nets == [dropped_net]
        assert report.classes_with_no_rules == []

        # Mutation 2: drop exactly one class's positive rule reference.
        dropped_class = class_names[0]
        mutated_dru = "".join(
            f"A.NetClass == '{n}'\n" for n in class_names if n != dropped_class
        )
        state, report = run(
            manifest,
            kicad_pro,
            net_classes=classes,
            net_assignments=assignments,
            dru_content=mutated_dru,
            kicad_class_name_fn=lambda k: k,
        )
        assert state == "violation"
        assert report.classes_with_no_rules == [dropped_class]
        assert report.unclassified_hv_nets == []

    @settings(max_examples=40, deadline=None, **_FIXTURE_SUPPRESS)
    @given(_ssot_safe_fixture())
    def test_run_is_idempotent(self, tmp_path, fixture):
        """Metamorphic idempotence: running the gate twice over identical
        inputs yields the identical state and report -- the gate has no
        hidden state or ordering dependence."""
        hv_nets, class_names, classes, assignments = fixture
        manifest = _manifest(tmp_path, hv_nets)
        kicad_pro = _kicad_pro(tmp_path, dict.fromkeys(class_names, ""))
        dru_content = "".join(f"A.NetClass == '{n}'\n" for n in class_names)

        state1, report1 = run(
            manifest,
            kicad_pro,
            net_classes=classes,
            net_assignments=assignments,
            dru_content=dru_content,
            kicad_class_name_fn=lambda k: k,
        )
        state2, report2 = run(
            manifest,
            kicad_pro,
            net_classes=classes,
            net_assignments=assignments,
            dru_content=dru_content,
            kicad_class_name_fn=lambda k: k,
        )
        assert state1 == state2
        assert report1.unclassified_hv_nets == report2.unclassified_hv_nets
        assert report1.classes_with_no_rules == report2.classes_with_no_rules


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
            f"hv_domain_nets_off_board={report.hv_domain_nets_off_board} "
            f"hv_domain_nets_unassigned_in_kicad_pro="
            f"{report.hv_domain_nets_unassigned_in_kicad_pro} "
            f"hv_domain_class_safety_mismatches="
            f"{report.hv_domain_class_safety_mismatches} "
            f"tool_errors={report.tool_errors}"
        )
        assert report.hv_nets_checked > 0
        assert report.declared_netclasses_checked > 0
        # PROPERTY 3 anti-vacuity: the real pcb/temper.kicad_pro always has
        # a netclass_assignments key, so this must genuinely evaluate --
        # not silently report "clean" by skipping. This is the check that
        # would have caught PWR_RTN: docs/evidence/
        # 2026-08-12-unassigned-domain-nets.md.
        assert report.property3_evaluated is True
        assert report.kicad_pro_assignments_checked > 0
        assert report.hv_domain_nets_off_board == []
        assert report.hv_domain_nets_unassigned_in_kicad_pro == []
        assert report.hv_domain_class_safety_mismatches == []
        # PWR_RTN specifically must be a real, on-board, HighVoltage-class
        # net now -- the exact defect this gate exists to catch, fixed.
        assert "PWR_RTN" not in report.hv_domain_nets_unassigned_in_kicad_pro

    def test_exit_codes_match_module_constants(self):
        assert EXIT_OK == 0
        assert EXIT_VIOLATION == 3
        assert EXIT_GATE_ERROR == 5


# ---------------------------------------------------------------------------
# TestPropertyThreeAndFour
# ---------------------------------------------------------------------------


class TestPropertyThreeAndFour:
    """PROPERTY 3 (BLOCKING, HV domain) and PROPERTY 4 (INFORMATIONAL,
    SELV domain + board-wide ghosts) against pcb/temper.kicad_pro's REAL
    netclass_assignments -- the file kicad-cli's DRC actually reads, which
    PROPERTIES 1/2 never look at. See module docstring."""

    def test_property3_not_evaluated_without_assignments_key(self, tmp_path):
        """The exact fixture every PROPERTY 1/2 test above uses (no
        netclass_assignments key at all) must leave PROPERTY 3/4
        unevaluated, not silently pass or silently fail -- this is what
        keeps every pre-existing test in this file behaving identically
        after PROPERTY 3/4 were added."""
        manifest = _manifest(tmp_path, hv_nets=["ac_l"])
        kicad_pro = _kicad_pro(tmp_path, {"ACMains": "mains"})  # no assignments=

        state, report = run(
            manifest,
            kicad_pro,
            net_classes={"ACMains": object()},
            net_assignments={"ac_l": "ACMains"},
            dru_content="A.NetClass == 'ACMains'\n",
            kicad_class_name_fn=lambda k: k,
        )
        assert state == "clean"
        assert report.property3_evaluated is False
        assert report.hv_domain_nets_unassigned_in_kicad_pro == []

    def test_hv_net_unassigned_in_kicad_pro_is_flagged(self, tmp_path):
        """The PWR_RTN falsifier: an HV-domain net that IS on the real
        board, IS present in TEMPER_NET_ASSIGNMENTS (so PROPERTY 1 is
        clean), but has NO entry in pcb/temper.kicad_pro's REAL
        netclass_assignments -- must be caught and must block the gate."""
        manifest = _manifest(tmp_path, hv_nets=["ac_l", "PWR_RTN"])
        kicad_pro = _kicad_pro(
            tmp_path,
            {"ACMains": "mains", "HighVoltage": "hv"},
            assignments={"ac_l": "ACMains"},  # PWR_RTN missing -- the defect
        )
        board = _kicad_pcb(tmp_path, ["ac_l", "PWR_RTN", "gnd", "+3V3"])
        rules = _netclass_rules(tmp_path, {"ACMains": "AC", "HighVoltage": "HV"})

        state, report = run(
            manifest,
            kicad_pro,
            net_classes={"ACMains": object(), "HighVoltage": object()},
            net_assignments={"ac_l": "ACMains", "PWR_RTN": "GND"},  # P1 clean
            dru_content="A.NetClass == 'ACMains'\nA.NetClass == 'HighVoltage'\n",
            kicad_class_name_fn=lambda k: k,
            kicad_pcb_path=board,
            netclass_rules_path=rules,
        )
        assert state == "violation"
        assert report.property3_evaluated is True
        assert report.unclassified_hv_nets == []  # PROPERTY 1 does NOT catch this
        assert report.hv_domain_nets_unassigned_in_kicad_pro == ["PWR_RTN"]
        assert report.hv_domain_nets_off_board == []
        assert report.hv_domain_class_safety_mismatches == []

    def test_hv_net_assigned_in_kicad_pro_is_not_flagged(self, tmp_path):
        """Control: the same fixture with PWR_RTN assigned in kicad_pro
        (the fix) must pass -- proves the property clears once the real
        file, not just TEMPER_NET_ASSIGNMENTS, is fixed."""
        manifest = _manifest(tmp_path, hv_nets=["ac_l", "PWR_RTN"])
        kicad_pro = _kicad_pro(
            tmp_path,
            {"ACMains": "mains", "HighVoltage": "hv"},
            assignments={"ac_l": "ACMains", "PWR_RTN": "HighVoltage"},
        )
        board = _kicad_pcb(tmp_path, ["ac_l", "PWR_RTN", "gnd", "+3V3"])
        rules = _netclass_rules(tmp_path, {"ACMains": "AC", "HighVoltage": "HV"})

        state, report = run(
            manifest,
            kicad_pro,
            net_classes={"ACMains": object(), "HighVoltage": object()},
            net_assignments={"ac_l": "ACMains", "PWR_RTN": "HighVoltage"},
            dru_content="A.NetClass == 'ACMains'\nA.NetClass == 'HighVoltage'\n",
            kicad_class_name_fn=lambda k: k,
            kicad_pcb_path=board,
            netclass_rules_path=rules,
        )
        assert state == "clean"
        assert report.hv_domain_nets_unassigned_in_kicad_pro == []

    def test_hv_net_off_board_is_flagged(self, tmp_path):
        """An HV-domain net the manifest declares but which is not a real
        net on the board (a manifest/board spelling drift, the historical
        +340V_BUS -> +170V_BUS shape) must be flagged, distinctly from
        'unassigned'."""
        manifest = _manifest(tmp_path, hv_nets=["ac_l", "+340V_BUS"])
        kicad_pro = _kicad_pro(
            tmp_path,
            {"ACMains": "mains", "HighVoltage": "hv"},
            assignments={"ac_l": "ACMains", "+340V_BUS": "HighVoltage"},
        )
        # The real board only has "+170V_BUS" -- "+340V_BUS" does not exist.
        board = _kicad_pcb(tmp_path, ["ac_l", "+170V_BUS", "gnd"])
        rules = _netclass_rules(tmp_path, {"ACMains": "AC", "HighVoltage": "HV"})

        state, report = run(
            manifest,
            kicad_pro,
            net_classes={"ACMains": object(), "HighVoltage": object()},
            net_assignments={"ac_l": "ACMains", "+340V_BUS": "HighVoltage"},
            dru_content="A.NetClass == 'ACMains'\nA.NetClass == 'HighVoltage'\n",
            kicad_class_name_fn=lambda k: k,
            kicad_pcb_path=board,
            netclass_rules_path=rules,
        )
        assert state == "violation"
        assert report.hv_domain_nets_off_board == ["+340V_BUS"]
        assert report.hv_domain_nets_unassigned_in_kicad_pro == []

    def test_hv_net_wrong_safety_category_is_flagged(self, tmp_path):
        """An HV-domain net assigned a REAL kicad_pro class whose
        safety_category is LV (not HV/AC) must be flagged -- the
        historical '+15V_LS -> Power' defect shape, but checked against
        the actual kicad_pro file instead of TEMPER_NET_ASSIGNMENTS."""
        manifest = _manifest(tmp_path, hv_nets=["+15V_LS"])
        kicad_pro = _kicad_pro(
            tmp_path,
            {"Power": "lv rail", "HighVoltage": "hv"},
            assignments={"+15V_LS": "Power"},  # LV-safe class on an HV net
        )
        board = _kicad_pcb(tmp_path, ["+15V_LS", "gnd"])
        rules = _netclass_rules(tmp_path, {"Power": "LV", "HighVoltage": "HV"})

        state, report = run(
            manifest,
            kicad_pro,
            net_classes={"Power": object(), "HighVoltage": object()},
            net_assignments={"+15V_LS": "HighVoltage"},  # PROPERTY 1 clean
            dru_content="A.NetClass == 'Power'\nA.NetClass == 'HighVoltage'\n",
            kicad_class_name_fn=lambda k: k,
            kicad_pcb_path=board,
            netclass_rules_path=rules,
        )
        assert state == "violation"
        assert report.hv_domain_nets_unassigned_in_kicad_pro == []
        assert len(report.hv_domain_class_safety_mismatches) == 1
        assert "+15V_LS" in report.hv_domain_class_safety_mismatches[0]

    def test_selv_and_ghost_findings_are_informational_not_blocking(self, tmp_path):
        """PROPERTY 4: an unassigned SELV-domain net and a kicad_pro
        assignment naming an off-board net must both be REPORTED but must
        NOT flip the gate to 'violation' when every PROPERTY 1/2/3 check
        is otherwise clean."""
        manifest = _manifest(tmp_path, hv_nets=["ac_l"], selv_nets=["gnd", "usb_dn"])
        kicad_pro = _kicad_pro(
            tmp_path,
            {"ACMains": "mains", "Power": "lv"},
            assignments={
                "ac_l": "ACMains",
                "gnd": "Power",
                # "usb_dn" deliberately absent -- PROPERTY 4, not blocking.
                "GHOST_NET": "Power",  # names no real board net
            },
        )
        board = _kicad_pcb(tmp_path, ["ac_l", "gnd", "usb_dn"])
        rules = _netclass_rules(tmp_path, {"ACMains": "AC", "Power": "LV"})

        state, report = run(
            manifest,
            kicad_pro,
            net_classes={"ACMains": object(), "Power": object()},
            net_assignments={"ac_l": "ACMains"},
            dru_content="A.NetClass == 'ACMains'\nA.NetClass == 'Power'\n",
            kicad_class_name_fn=lambda k: k,
            kicad_pcb_path=board,
            netclass_rules_path=rules,
        )
        assert state == "clean", (
            report.selv_domain_nets_unassigned_in_kicad_pro,
            report.ghost_kicad_pro_assignments,
        )
        assert report.selv_domain_nets_unassigned_in_kicad_pro == ["usb_dn"]
        assert report.ghost_kicad_pro_assignments == ["GHOST_NET"]

    def test_default_and_differential_resolve_to_lv_safety_category(self, tmp_path):
        """Structural KiCad classes not modeled in netclass_rules.yaml
        (via load_netclass_safety_categories's own structural fallback)
        must resolve to 'LV', not 'UNKNOWN' -- an HV net assigned one of
        these should be flagged for being LV (the correct reason), not for
        an unrecognized category. check_domain_class_safety_mismatch
        itself is a pure lookup with no fallback of its own; the fallback
        is load_netclass_safety_categories's contract, exercised here
        end-to-end."""
        rules = _netclass_rules(tmp_path, {"ACMains": "AC"})  # no Default/Differential entry
        categories = load_netclass_safety_categories(rules)
        assert (
            check_domain_class_safety_mismatch(
                ["ac_l"],
                {"ac_l": "Default"},
                categories,
                frozenset({"HV", "AC"}),
            )
            == ["'ac_l' -> kicad_pro class 'Default' (safety_category='LV')"]
        )

    def test_check_domain_class_safety_mismatch_unknown_class_reports_unknown(self):
        """A class absent from the safety-category table entirely (not
        even the Default/Differential fallback) reports 'UNKNOWN', not a
        silent pass -- an unrecognized class must never be assumed safe."""
        assert check_domain_class_safety_mismatch(
            ["ac_l"], {"ac_l": "SomeUnmappedClass"}, {}, frozenset({"HV", "AC"})
        ) == ["'ac_l' -> kicad_pro class 'SomeUnmappedClass' (safety_category='UNKNOWN')"]


# ---------------------------------------------------------------------------
# TestBoardNetParsing
# ---------------------------------------------------------------------------


class TestBoardNetParsing:
    """``parse_board_net_names`` must walk the S-expression structurally
    (paren depth over a real token stream), not grep for the substring
    ``(net`` -- a prior agent's grep-based pad count was wrong for exactly
    this reason (docs/evidence/2026-08-12-unassigned-domain-nets.md)."""

    def test_ignores_nested_pad_net_reference(self, tmp_path):
        """A pad's own (net N "name") reference, nested many levels below
        the top-level form, must not be double-counted or misread as a
        second top-level net -- the fixture below has exactly ONE
        top-level (net ...) declaration and one nested pad reference to
        the SAME net name; the result must contain that name exactly
        once, and must not contain any name only the pad reference would
        produce if the parser were depth-blind."""
        board = _kicad_pcb(tmp_path, ["ac_l", "gnd"])
        names = parse_board_net_names(board)
        assert names == {"ac_l", "gnd"}

    def test_grep_would_overcount_vs_structural_parse(self, tmp_path):
        """Direct falsifier: a naive substring count of '(net ' on the
        fixture disagrees with the structural parser's result, because the
        fixture's pad carries its own nested (net ...) reference -- proving
        the structural walk is doing real work, not agreeing with a grep
        by coincidence."""
        board = _kicad_pcb(tmp_path, ["ac_l", "gnd"])
        text = board.read_text()
        naive_count = text.count("(net ")
        names = parse_board_net_names(board)
        assert naive_count != len(names)  # 3 occurrences ((net 1..), (net 2..), pad's) vs 2 real nets
        assert len(names) == 2

    def test_missing_file_is_gate_error(self, tmp_path):
        with pytest.raises(GateError):
            parse_board_net_names(tmp_path / "does-not-exist.kicad_pcb")

    def test_zero_top_level_nets_is_gate_error(self, tmp_path):
        path = tmp_path / "empty.kicad_pcb"
        path.write_text("(kicad_pcb (version 1) (generator test))")
        with pytest.raises(GateError):
            parse_board_net_names(path)

    def test_load_kicad_pro_netclass_assignments_absent_key_is_none(self, tmp_path):
        kicad_pro = _kicad_pro(tmp_path, {"ACMains": "mains"})  # no assignments=
        assert load_kicad_pro_netclass_assignments(kicad_pro) is None

    def test_load_kicad_pro_netclass_assignments_reads_present_key(self, tmp_path):
        kicad_pro = _kicad_pro(tmp_path, {"ACMains": "mains"}, assignments={"ac_l": "ACMains"})
        assert load_kicad_pro_netclass_assignments(kicad_pro) == {"ac_l": "ACMains"}

    def test_load_netclass_safety_categories_reads_and_adds_structural(self, tmp_path):
        rules = _netclass_rules(tmp_path, {"ACMains": "AC", "HighVoltage": "HV"})
        result = load_netclass_safety_categories(rules)
        assert result["ACMains"] == "AC"
        assert result["HighVoltage"] == "HV"
        assert result["Default"] == "LV"
        assert result["Differential"] == "LV"

    def test_load_netclass_safety_categories_missing_file_is_gate_error(self, tmp_path):
        with pytest.raises(GateError):
            load_netclass_safety_categories(tmp_path / "does-not-exist.yaml")

    def test_check_ghost_kicad_pro_assignments_helper(self):
        assert check_ghost_kicad_pro_assignments(
            {"ac_l": "ACMains", "GHOST": "Power"}, {"ac_l", "gnd"}
        ) == ["GHOST"]

    def test_check_domain_nets_on_board_helper(self):
        assert check_domain_nets_on_board(["ac_l", "GHOST"], {"ac_l", "gnd"}) == ["GHOST"]

    def test_check_domain_net_kicad_pro_coverage_helper(self):
        assert check_domain_net_kicad_pro_coverage(
            ["ac_l", "PWR_RTN"], {"ac_l": "ACMains"}
        ) == ["PWR_RTN"]

    def test_load_selv_nets_reads_selv_domain(self, tmp_path):
        manifest = _manifest(tmp_path, hv_nets=["ac_l"], selv_nets=["gnd", "usb_dn"])
        assert load_selv_nets(manifest) == ["gnd", "usb_dn"]
