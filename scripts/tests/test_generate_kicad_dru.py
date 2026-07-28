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
