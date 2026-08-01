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
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

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
            f"tool_errors={report.tool_errors}"
        )
        assert report.hv_nets_checked > 0
        assert report.declared_netclasses_checked > 0

    def test_exit_codes_match_module_constants(self):
        assert EXIT_OK == 0
        assert EXIT_VIOLATION == 3
        assert EXIT_GATE_ERROR == 5
