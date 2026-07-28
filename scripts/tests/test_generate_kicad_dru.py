"""Tests for the coating-based fail-open fix in generate_kicad_dru.py.

Background (docs/evidence/2026-07-28-conformal-coating-pd1.md,
docs/evidence/2026-07-28-creepage-determination-brainstorm.md,
docs/evidence/2026-07-28-drc-coating-failopen-fix.md): the generated KiCad
design rules used to relax the "HV internal same footprint" clearance rule
to 1.5mm and justify it with "REQUIRES: Conformal coating to achieve PD1
(needs 0.8mm for 400V)". No coating exists on this board, and even a
qualified one could not have delivered that credit here (IEC 60664-3
cl. 4.3's full-path coverage requirement fails on every declared isolator's
own component body). The 0.8mm figure also matched no cell of Table 17.

Groups:
  TestNoCoatingRelaxation        -- generated text/constants no longer carry
                                     the fictitious coating justification or
                                     value; the fail-closed 2.0mm figure is
                                     the one actually emitted.
  TestCoatingQualifiedGateFailsLoudly -- flipping COATING_QUALIFIED without
                                     also fixing the code raises instead of
                                     silently relaxing.
  TestDrcFalsifier                -- fail-before/pass-after against a real
                                     kicad-cli DRC run on a minimal, isolated
                                     fixture reproducing the exact TO-247
                                     1.95mm edge-to-edge gap this rule used
                                     to reason about. Skipped if kicad-cli
                                     isn't on PATH.

TestDrcFalsifier's two cases record an honest, two-part finding rather than
a single "violations went up" number:

* ``test_number_change_is_load_bearing_with_working_courtyard_match`` uses a
  literal footprint reference in the courtyard test (``A.insideCourtyard
  ('Q1')``) and shows the value change alone flips PASS->FAIL for a 1.95mm
  gap, exactly as intended.
* ``test_real_rule_as_committed_now_binds_after_condition_fix`` used to
  document that the EXACT condition string ``generate_dru()`` emitted
  (``A.insideCourtyard(B.Reference)``) did not match at all in kicad-cli
  10.0.4 -- a second, independent defect in RULE 5 beyond the coating value,
  fixed separately (see docs/evidence/2026-07-28-drc-courtyard-condition-fix.md):
  ``A.insideCourtyard(B.Reference)`` is not a valid dynamic same-footprint
  test in KiCad's rule language (``intersectsCourtyard()``'s argument
  resolves against a literal footprint reference/wildcard string, not
  another matched item's property value); the condition is now
  ``A.Reference == B.Reference``, confirmed to bind on both an isolated
  fixture and the real board. This test now asserts the FIXED condition
  fires correctly and that the broken form is not reintroduced.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import generate_kicad_dru as gen  # noqa: E402

KICAD_CLI = shutil.which("kicad-cli")
REPO_ROOT = Path(__file__).resolve().parents[2]

# Historical fail-open value this fix removes. Not imported from the module
# (it no longer exists there) -- hardcoded here as a regression tripwire so
# a future edit can't silently bring it back.
_HISTORICAL_RELAXED_CLEARANCE_MM = 1.5

# The exact edge-to-edge gap scripts/generate_kicad_dru.py's own RULE 5
# comment cites for TO-247 IGBT packages (5.45mm pin pitch, 1.95mm
# edge-to-edge) -- see docs/evidence/2026-07-28-conformal-coating-pd1.md
# sec 4. 1.95mm sits strictly between the historical 1.5mm and the
# corrected 2.0mm, so it is the exact value that flips pass<->fail.
_TO247_GAP_MM = 1.95


def _hv_internal_rule_block(content: str) -> str:
    m = re.search(r'\(rule "HV internal same footprint".*?\n\)\n', content, re.DOTALL)
    assert m, "HV internal same footprint rule not found in generated output"
    return m.group(0)


def _hv_internal_rule_section(content: str) -> str:
    """Like _hv_internal_rule_block, but starting at the '# RULE 5:' comment
    marker rather than the '(rule ...)' statement -- the coating language
    this fix removes lived in the COMMENT lines above the rule statement
    (both before and after this fix), not inside the s-expr itself, so a
    check for coating language must include them or it tests nothing."""
    m = re.search(r"# RULE 5:.*?\n\)\n", content, re.DOTALL)
    assert m, "RULE 5 section not found in generated output"
    return m.group(0)


# ---------------------------------------------------------------------------
# TestNoCoatingRelaxation
# ---------------------------------------------------------------------------


class TestNoCoatingRelaxation:
    def test_no_false_coating_safety_claim_in_header(self) -> None:
        content = gen.generate_dru()
        assert "REQUIRES conformal coating for safety" not in content
        assert "carries NO qualified conformal coating" in content

    def test_hv_internal_rule_has_no_coating_language(self) -> None:
        section = _hv_internal_rule_section(gen.generate_dru())
        assert "Conformal coating" not in section
        assert "0.8mm" not in section

    def test_hv_internal_clearance_is_2mm_not_the_historical_value(self) -> None:
        block = _hv_internal_rule_block(gen.generate_dru())
        assert "(constraint clearance (min 2.0mm))" in block
        assert f"(constraint clearance (min {_HISTORICAL_RELAXED_CLEARANCE_MM}mm))" not in block

    def test_hv_internal_clearance_constant_is_2mm(self) -> None:
        assert gen.HV_INTERNAL_CLEARANCE_MM == 2.0

    def test_coating_qualified_flag_is_false(self) -> None:
        assert gen.COATING_QUALIFIED is False

    def test_creepage_figures_recorded_but_flagged_unresolved(self) -> None:
        # Not emitted as an enforced KiCad rule (the generator has no
        # creepage constraint type) -- recorded so the gap is visible.
        assert gen.HV_CREEPAGE_PD2_MM == 8.0
        assert gen.HV_CREEPAGE_PD3_MM == 12.6


# ---------------------------------------------------------------------------
# TestCoatingQualifiedGateFailsLoudly
# ---------------------------------------------------------------------------


class TestCoatingQualifiedGateFailsLoudly:
    """COATING_QUALIFIED=True must fail loudly, not silently relax, until a
    human has recorded a real IEC 60664-3 Annex J qualification. The check
    runs at import time, so this re-executes the module source with the
    flag flipped rather than monkeypatching after the fact."""

    def test_flipping_the_flag_raises(self) -> None:
        source = Path(gen.__file__).read_text()
        assert "COATING_QUALIFIED = False" in source
        patched = source.replace(
            "COATING_QUALIFIED = False", "COATING_QUALIFIED = True", 1
        )
        namespace = {"__name__": "generate_kicad_dru_patched_test", "__file__": gen.__file__}
        with pytest.raises(NotImplementedError):
            exec(compile(patched, gen.__file__, "exec"), namespace)


# ---------------------------------------------------------------------------
# TestDrcFalsifier -- real kicad-cli DRC on a minimal, isolated fixture
# ---------------------------------------------------------------------------


def _build_fixture(tmp_path: Path, gap_mm: float) -> Path:
    """A single footprint 'Q1' with two SMD rect pads on nets 'DC_BUS+' /
    'DC_BUS-' (both mapped to netclass 'HighVoltage'), gap_mm edge-to-edge
    apart, inside an F.CrtYd courtyard. Returns the .kicad_pcb path; a
    matching .kicad_pro with the netclass assignment is written alongside
    it (kicad-cli resolves A.NetClass from the project's
    net_settings.netclass_assignments, not from a legacy same-file
    add_net list)."""
    from kiutils.board import Board, LayerToken
    from kiutils.footprint import Footprint, Pad
    from kiutils.items.common import Net, Position
    from kiutils.items.fpitems import FpRect
    from kiutils.items.gritems import GrPoly

    board = Board()
    board.version = "20221018"
    board.generator = "pytest-rule5-fixture"
    board.layers = [
        LayerToken(ordinal=0, name="F.Cu", type="signal"),
        LayerToken(ordinal=31, name="B.Cu", type="signal"),
        LayerToken(ordinal=44, name="Edge.Cuts", type="user"),
        LayerToken(ordinal=47, name="F.CrtYd", type="user", userName="F.Courtyard"),
    ]
    board.nets = [
        Net(number=0, name=""),
        Net(number=1, name="DC_BUS+"),
        Net(number=2, name="DC_BUS-"),
    ]
    board.graphicItems = [
        GrPoly(
            coordinates=[Position(0, 0), Position(50, 0), Position(50, 50), Position(0, 50)],
            layer="Edge.Cuts",
            width=0.1,
        )
    ]

    half_gap = gap_mm / 2
    pad_half_width = 1.0  # 2mm-wide pads
    fp = Footprint()
    fp.entryName = "Test:TO247_HV_internal"
    fp.layer = "F.Cu"
    fp.position = Position(25, 25)
    fp.properties = {"Reference": "Q1"}
    fp.pads = [
        Pad(
            number="1", type="smd", shape="rect",
            position=Position(-(half_gap + pad_half_width), 0), size=Position(2, 2),
            layers=["F.Cu"], net=Net(number=1, name="DC_BUS+"),
        ),
        Pad(
            number="2", type="smd", shape="rect",
            position=Position(half_gap + pad_half_width, 0), size=Position(2, 2),
            layers=["F.Cu"], net=Net(number=2, name="DC_BUS-"),
        ),
    ]
    fp.graphicItems = [FpRect(start=Position(-4, -3), end=Position(4, 3), layer="F.CrtYd", width=0.05)]
    board.footprints = [fp]

    pcb_path = tmp_path / "rule5_fixture.kicad_pcb"
    board.to_file(str(pcb_path))

    proj = json.loads((REPO_ROOT / "pcb" / "temper_final_verified.kicad_pro").read_text())
    ns = proj["net_settings"]
    default_class = dict(ns["classes"][0])
    hv_class = dict(default_class)
    hv_class.update({"name": "HighVoltage", "clearance": 6.0, "track_width": 3.0})
    ns["classes"] = [default_class, hv_class]
    ns["netclass_assignments"] = {"DC_BUS+": "HighVoltage", "DC_BUS-": "HighVoltage"}
    (tmp_path / "rule5_fixture.kicad_pro").write_text(json.dumps(proj))

    return pcb_path


def _run_drc(pcb_path: Path, dru_text: str) -> list[dict]:
    dru_path = pcb_path.with_suffix(".kicad_dru")
    dru_path.write_text(dru_text)
    report_path = pcb_path.parent / "drc_report.json"
    subprocess.run(
        [
            KICAD_CLI, "pcb", "drc", "--format", "json",
            "-o", str(report_path), str(pcb_path),
        ],
        capture_output=True, text=True, timeout=120, check=False,
    )
    report = json.loads(report_path.read_text())
    return report.get("violations", [])


def _rule(condition: str, min_mm: float, name: str = "HV internal same footprint") -> str:
    return (
        "(version 1)\n\n"
        f'(rule "{name}"\n'
        f'   (condition "{condition}")\n'
        f"   (constraint clearance (min {min_mm}mm))\n"
        ")\n"
    )


@pytest.mark.skipif(KICAD_CLI is None, reason="kicad-cli not on PATH")
class TestDrcFalsifier:
    def test_number_change_is_load_bearing_with_working_courtyard_match(self, tmp_path: Path) -> None:
        """With a courtyard reference kicad-cli actually matches, the
        1.5mm -> 2.0mm correction flips a real DRC pass to a real fail for
        the 1.95mm TO-247 gap -- proving the corrected NUMBER is sound."""
        pcb_path = _build_fixture(tmp_path, _TO247_GAP_MM)
        condition = (
            "A.NetClass == 'HighVoltage' && B.NetClass == 'HighVoltage'"
            " && A.insideCourtyard('Q1')"
        )

        old_violations = _run_drc(pcb_path, _rule(condition, _HISTORICAL_RELAXED_CLEARANCE_MM))
        old_clearance = [v for v in old_violations if v["type"] == "clearance"]
        assert old_clearance == [], (
            f"expected the {_TO247_GAP_MM}mm gap to PASS the historical "
            f"{_HISTORICAL_RELAXED_CLEARANCE_MM}mm rule; got {old_clearance!r}"
        )

        new_violations = _run_drc(pcb_path, _rule(condition, gen.HV_INTERNAL_CLEARANCE_MM))
        new_clearance = [v for v in new_violations if v["type"] == "clearance"]
        assert len(new_clearance) == 1, (
            f"expected the {_TO247_GAP_MM}mm gap to FAIL the corrected "
            f"{gen.HV_INTERNAL_CLEARANCE_MM}mm rule (1 violation); got {new_clearance!r}"
        )
        assert f"actual {_TO247_GAP_MM:.4f}" in new_clearance[0]["description"]

    def test_real_rule_as_committed_now_binds_after_condition_fix(self, tmp_path: Path) -> None:
        """The EXACT rule generate_dru() emits today uses
        ``A.Reference == B.Reference`` for the same-footprint test (fixed
        from the historical ``A.insideCourtyard(B.Reference)``, which does
        not match anything in kicad-cli 10.0.4/10.0.5 -- see
        docs/evidence/2026-07-28-drc-courtyard-condition-fix.md). This test
        asserts both that the broken dynamic-courtyard form is gone AND that
        the corrected condition, taken verbatim from generate_dru()'s real
        output (not a hand-written substitute), actually fires: the
        1.5mm->2.0mm value correction flips PASS->FAIL for the 1.95mm
        TO-247 gap, exactly as intended, using the real emitted condition."""
        pcb_path = _build_fixture(tmp_path, _TO247_GAP_MM)
        real_block = _hv_internal_rule_block(gen.generate_dru())
        condition_match = re.search(r'\(condition "([^"]+)"\)', real_block)
        assert condition_match
        real_condition = condition_match.group(1)
        assert "insideCourtyard(B.Reference)" not in real_condition, (
            "the broken A.insideCourtyard(B.Reference) form was reintroduced -- "
            "see docs/evidence/2026-07-28-drc-courtyard-condition-fix.md"
        )
        assert "A.Reference == B.Reference" in real_condition

        old_violations = _run_drc(
            pcb_path, _rule(real_condition, _HISTORICAL_RELAXED_CLEARANCE_MM)
        )
        old_clearance = [v for v in old_violations if v["type"] == "clearance"]
        assert old_clearance == [], (
            f"expected the {_TO247_GAP_MM}mm gap to PASS the historical "
            f"{_HISTORICAL_RELAXED_CLEARANCE_MM}mm rule under the real, "
            f"as-emitted condition; got {old_clearance!r}"
        )

        new_violations = _run_drc(pcb_path, _rule(real_condition, gen.HV_INTERNAL_CLEARANCE_MM))
        new_clearance = [v for v in new_violations if v["type"] == "clearance"]
        assert len(new_clearance) == 1, (
            f"expected the {_TO247_GAP_MM}mm gap to FAIL the corrected "
            f"{gen.HV_INTERNAL_CLEARANCE_MM}mm rule (1 violation) under the "
            f"real, as-emitted condition; got {new_clearance!r} -- if this "
            f"fails, the condition fix stopped binding and RULE 5 is silently "
            f"matching nothing again"
        )
        assert f"actual {_TO247_GAP_MM:.4f}" in new_clearance[0]["description"]


# ---------------------------------------------------------------------------
# TestPowerInternalConditionFix -- RULE 7 shares RULE 5's exact defect
# ---------------------------------------------------------------------------


class TestPowerInternalConditionFix:
    """RULE 7 ("Power internal same footprint") used the identical
    A.insideCourtyard(B.Reference) same-footprint test as RULE 5, and so
    shares the identical defect (see
    docs/evidence/2026-07-28-drc-courtyard-condition-fix.md). Not owned by
    any other in-flight fix, so corrected alongside RULE 5 rather than only
    reported. A full kicad-cli DRC re-verification isn't repeated here since
    the underlying mechanism (A.Reference == B.Reference vs.
    A.insideCourtyard(B.Reference)) is already proven by TestDrcFalsifier
    above -- this is a static regression guard against the broken form
    coming back."""

    def test_power_internal_condition_uses_reference_equality_not_dynamic_courtyard(
        self,
    ) -> None:
        content = gen.generate_dru()
        m = re.search(r'\(rule "Power internal same footprint".*?\n\)\n', content, re.DOTALL)
        assert m, "Power internal same footprint rule not found in generated output"
        block = m.group(0)
        condition_match = re.search(r'\(condition "([^"]+)"\)', block)
        assert condition_match
        condition = condition_match.group(1)
        assert "insideCourtyard(B.Reference)" not in condition, (
            "the broken A.insideCourtyard(B.Reference) form was reintroduced in RULE 7 -- "
            "see docs/evidence/2026-07-28-drc-courtyard-condition-fix.md"
        )
        assert "A.Reference == B.Reference" in condition


# ---------------------------------------------------------------------------
# TestRule1NetclassDiscrimination -- RULE 1/1a redo
# ---------------------------------------------------------------------------
#
# Background (docs/evidence/2026-07-28-drc-rule1-netclass-redo.md,
# docs/evidence/2026-07-28-drc-rule1-netclass-discrimination.md): RULE 1
# ("Same footprint pads") and RULE 1a ("Fine pitch IC pads") used
# A.Footprint == B.Footprint as their same-footprint-instance test.
# "Footprint" is not a property KiCad's PROPERTY_MANAGER registers on Pad
# or Footprint (confirmed against pcbnew/pad.cpp and pcbnew/footprint.cpp
# at kicad-cli 10.0.4/10.0.5), so this never bound -- on the isolated
# fixture below AND on the real board (0 matches at a 999mm threshold,
# same methodology as the sibling courtyard-condition fix).
#
# Two independent defects are fixed here, not one:
#   1. The dead same-footprint test: A.Footprint == B.Footprint ->
#      A.Reference == B.Reference (measured to bind: 215 lone-condition
#      matches at 999mm against an unclassified-baseline copy of the real
#      board, closely reproducing the 214 the task's own measurement
#      reported).
#   2. RULE 1a's A.Attribute == 'SMD' clause is ALSO not a registered
#      property (pad.cpp registers this field as "Pad Type", not
#      "Attribute") -> A.Pad_Type == 'SMD' (measured to bind: 483 lone-
#      condition matches at 999mm vs. 0 for A.Attribute).
#
# A same-footprint-instance test alone is too broad: several isolators in
# elec/domain_manifest.yaml (the gate driver, aux supply, Y-cap, relays)
# put HV-side and SELV-side pins on the SAME footprint reference, and a
# same-footprint rule must never grant THOSE pairs the 0.1mm
# manufacturability allowance meant for a single package's own pin pitch.
# KiCad's rule language cannot reference elec/domain_manifest.yaml
# directly, so A.NetClass == B.NetClass (confirmed to bind: 499 lone-
# condition matches) is used as the finest dynamically-expressible proxy
# for "same domain" -- a NECESSARY but not SUFFICIENT proxy (see the
# evidence doc's U7/UCC21550 discussion for a measured real-board
# counterexample and how far the accompanying pcb/temper.kicad_pro fix
# closes it), and a strict improvement over both the previous always-dead
# condition and a hardcoded literal-net-name exclusion (which reproduces
# the exact failure mode -- an unnoticed net rename orphaning the rule --
# that produced the +340V_BUS defect this task is named after).


def _build_cross_domain_fixture(tmp_path: Path, gap_mm: float) -> Path:
    """A single footprint 'Q1' with two SMD pads on the SAME reference but
    DIFFERENT net classes ('HighVoltage' vs 'Default'), gap_mm edge-to-edge
    apart -- modeling an isolator's primary/secondary pins sharing one
    physical package, the case RULE 1's cross-domain guard exists for."""
    from kiutils.board import Board, LayerToken
    from kiutils.footprint import Footprint, Pad
    from kiutils.items.common import Net, Position
    from kiutils.items.fpitems import FpRect
    from kiutils.items.gritems import GrPoly

    board = Board()
    board.version = "20221018"
    board.generator = "pytest-rule1-fixture"
    board.layers = [
        LayerToken(ordinal=0, name="F.Cu", type="signal"),
        LayerToken(ordinal=31, name="B.Cu", type="signal"),
        LayerToken(ordinal=44, name="Edge.Cuts", type="user"),
        LayerToken(ordinal=47, name="F.CrtYd", type="user", userName="F.Courtyard"),
    ]
    board.nets = [
        Net(number=0, name=""),
        Net(number=1, name="HV_SIDE"),
        Net(number=2, name="LV_SIDE"),
    ]
    board.graphicItems = [
        GrPoly(
            coordinates=[Position(0, 0), Position(50, 0), Position(50, 50), Position(0, 50)],
            layer="Edge.Cuts",
            width=0.1,
        )
    ]

    half_gap = gap_mm / 2
    pad_half_width = 1.0
    fp = Footprint()
    fp.entryName = "Test:Isolator_CrossDomain"
    fp.layer = "F.Cu"
    fp.position = Position(25, 25)
    fp.properties = {"Reference": "Q1"}
    fp.pads = [
        Pad(
            number="1", type="smd", shape="rect",
            position=Position(-(half_gap + pad_half_width), 0), size=Position(2, 2),
            layers=["F.Cu"], net=Net(number=1, name="HV_SIDE"),
        ),
        Pad(
            number="2", type="smd", shape="rect",
            position=Position(half_gap + pad_half_width, 0), size=Position(2, 2),
            layers=["F.Cu"], net=Net(number=2, name="LV_SIDE"),
        ),
    ]
    fp.graphicItems = [FpRect(start=Position(-4, -3), end=Position(4, 3), layer="F.CrtYd", width=0.05)]
    board.footprints = [fp]

    pcb_path = tmp_path / "rule1_fixture.kicad_pcb"
    board.to_file(str(pcb_path))

    proj = json.loads((REPO_ROOT / "pcb" / "temper_final_verified.kicad_pro").read_text())
    ns = proj["net_settings"]
    default_class = dict(ns["classes"][0])
    hv_class = dict(default_class)
    hv_class.update({"name": "HighVoltage", "clearance": 2.0, "track_width": 3.0})
    ns["classes"] = [default_class, hv_class]
    ns["netclass_assignments"] = {"HV_SIDE": "HighVoltage"}  # LV_SIDE stays Default
    (tmp_path / "rule1_fixture.kicad_pro").write_text(json.dumps(proj))

    return pcb_path


# Edge-to-edge gap for the cross-domain fixture: bigger than RULE 1's 0.1mm
# relaxed minimum (so an over-broad same-footprint-only rule would silently
# PASS it) but smaller than the HighVoltage netclass's own 2.0mm baseline
# clearance (so the CORRECT, netclass-discriminating rule -- which should
# not match this cross-domain pair at all -- leaves the stricter baseline
# in force and the pair correctly FAILS).
_CROSS_DOMAIN_GAP_MM = 0.5


@pytest.mark.skipif(KICAD_CLI is None, reason="kicad-cli not on PATH")
class TestRule1CrossDomainGuard:
    def test_bare_same_footprint_test_would_wrongly_pass_a_cross_domain_pair(
        self, tmp_path: Path
    ) -> None:
        """Without the NetClass guard, a same-Reference-only test grants the
        0.1mm relaxation to ANY same-footprint pair, including one that
        spans an isolator's HV/SELV barrier -- demonstrating why the guard
        is necessary, not merely a style choice."""
        pcb_path = _build_cross_domain_fixture(tmp_path, _CROSS_DOMAIN_GAP_MM)
        bare_condition = "A.Reference == B.Reference"  # no NetClass guard

        violations = _run_drc(pcb_path, _rule(bare_condition, 0.1, name="Same footprint pads"))
        clearance = [v for v in violations if v["type"] == "clearance"]
        assert clearance == [], (
            f"expected the bare same-Reference test to (wrongly) PASS a "
            f"{_CROSS_DOMAIN_GAP_MM}mm cross-domain gap; got {clearance!r} -- "
            f"if this fails, the danger this guard exists for is no longer "
            f"reproducible and the fixture needs review"
        )

    def test_real_rule1_condition_correctly_rejects_the_cross_domain_pair(
        self, tmp_path: Path
    ) -> None:
        """The EXACT condition generate_dru() emits for RULE 1 today must
        NOT match the cross-domain pair (different NetClass), so RULE 1
        contributes no constraint and the pair falls through to the
        HighVoltage netclass's own stricter baseline clearance (2.0mm),
        correctly failing at a 0.5mm gap."""
        pcb_path = _build_cross_domain_fixture(tmp_path, _CROSS_DOMAIN_GAP_MM)
        content = gen.generate_dru()
        m = re.search(r'\(rule "Same footprint pads".*?\n\)\n', content, re.DOTALL)
        assert m, "Same footprint pads rule not found in generated output"
        condition_match = re.search(r'\(condition "([^"]+)"\)', m.group(0))
        assert condition_match
        real_condition = condition_match.group(1)
        assert "A.Footprint" not in real_condition, (
            "the broken A.Footprint == B.Footprint form was reintroduced -- "
            "see docs/evidence/2026-07-28-drc-rule1-netclass-redo.md"
        )
        assert "A.Reference == B.Reference" in real_condition
        assert "A.NetClass == B.NetClass" in real_condition

        # Run the real generated DRU wholesale (RULE 1 plus the HighVoltage
        # trace-width/clearance baseline already present in the file) so
        # the fallthrough to the netclass baseline is the file's real
        # behavior, not a hand-picked substitute rule.
        violations = _run_drc(pcb_path, content)
        clearance = [v for v in violations if v["type"] == "clearance"]
        assert len(clearance) >= 1, (
            f"expected the {_CROSS_DOMAIN_GAP_MM}mm cross-domain gap to FAIL "
            f"now that RULE 1 correctly declines to match it; got no "
            f"clearance violations -- RULE 1 may be over-matching again"
        )

    def test_genuine_same_domain_pair_still_gets_the_relaxation(self, tmp_path: Path) -> None:
        """The guard must not make RULE 1 useless: two same-footprint,
        same-netclass pads at a tight manufacturability pitch should still
        pass at the relaxed 0.1mm minimum."""
        from kiutils.board import Board, LayerToken
        from kiutils.footprint import Footprint, Pad
        from kiutils.items.common import Net, Position
        from kiutils.items.fpitems import FpRect
        from kiutils.items.gritems import GrPoly

        gap_mm = 0.15  # fails Default's 0.2mm baseline, passes RULE 1's 0.1mm
        board = Board()
        board.version = "20221018"
        board.generator = "pytest-rule1-samedomain-fixture"
        board.layers = [
            LayerToken(ordinal=0, name="F.Cu", type="signal"),
            LayerToken(ordinal=31, name="B.Cu", type="signal"),
            LayerToken(ordinal=44, name="Edge.Cuts", type="user"),
            LayerToken(ordinal=47, name="F.CrtYd", type="user", userName="F.Courtyard"),
        ]
        board.nets = [
            Net(number=0, name=""),
            Net(number=1, name="SIG_A"),
            Net(number=2, name="SIG_B"),
        ]
        board.graphicItems = [
            GrPoly(
                coordinates=[Position(0, 0), Position(50, 0), Position(50, 50), Position(0, 50)],
                layer="Edge.Cuts",
                width=0.1,
            )
        ]
        half_gap = gap_mm / 2
        pad_half_width = 1.0
        fp = Footprint()
        fp.entryName = "Test:SameDomain_TightPitch"
        fp.layer = "F.Cu"
        fp.position = Position(25, 25)
        fp.properties = {"Reference": "U1"}
        fp.pads = [
            Pad(
                number="1", type="smd", shape="rect",
                position=Position(-(half_gap + pad_half_width), 0), size=Position(2, 2),
                layers=["F.Cu"], net=Net(number=1, name="SIG_A"),
            ),
            Pad(
                number="2", type="smd", shape="rect",
                position=Position(half_gap + pad_half_width, 0), size=Position(2, 2),
                layers=["F.Cu"], net=Net(number=2, name="SIG_B"),
            ),
        ]
        fp.graphicItems = [FpRect(start=Position(-4, -3), end=Position(4, 3), layer="F.CrtYd", width=0.05)]
        board.footprints = [fp]
        pcb_path = tmp_path / "rule1_samedomain_fixture.kicad_pcb"
        board.to_file(str(pcb_path))

        proj = json.loads((REPO_ROOT / "pcb" / "temper_final_verified.kicad_pro").read_text())
        (tmp_path / "rule1_samedomain_fixture.kicad_pro").write_text(json.dumps(proj))
        # SIG_A/SIG_B both resolve to the project's Default netclass -- same
        # domain by construction, no netclass_assignments override needed.

        content = gen.generate_dru()
        violations = _run_drc(pcb_path, content)
        clearance = [v for v in violations if v["type"] == "clearance"]
        assert clearance == [], (
            f"expected a genuine same-footprint, same-netclass pair at "
            f"{gap_mm}mm to PASS under RULE 1's relaxed 0.1mm minimum; got "
            f"{clearance!r} -- the cross-domain guard may have made RULE 1 "
            f"unusable for its original manufacturability-allowance purpose"
        )


class TestRule1aPadTypeConditionFix:
    """RULE 1a's A.Attribute == 'SMD' clause is a second, independent
    undefined-property defect (pad.cpp registers this field as "Pad Type",
    not "Attribute") -- see docs/evidence/2026-07-28-drc-rule1-netclass-redo.md.
    Static regression guard against both the A.Footprint and A.Attribute
    forms coming back."""

    def test_fine_pitch_condition_uses_pad_type_not_attribute(self) -> None:
        content = gen.generate_dru()
        m = re.search(r'\(rule "Fine pitch IC pads".*?\n\)\n', content, re.DOTALL)
        assert m, "Fine pitch IC pads rule not found in generated output"
        condition_match = re.search(r'\(condition "([^"]+)"\)', m.group(0))
        assert condition_match
        condition = condition_match.group(1)
        assert "A.Attribute" not in condition and "B.Attribute" not in condition, (
            "the undefined A.Attribute property was reintroduced -- see "
            "docs/evidence/2026-07-28-drc-rule1-netclass-redo.md"
        )
        assert "A.Pad_Type == 'SMD'" in condition
        assert "B.Pad_Type == 'SMD'" in condition
        assert "A.Footprint" not in condition
        assert "A.Reference == B.Reference" in condition
        assert "A.NetClass == B.NetClass" in condition
