"""Tests for the real KiCad `creepage` DRC constraint in generate_kicad_dru.py.

Background (docs/evidence/2026-07-28-drc-creepage-constraint.md, recovered
alongside this test from the stranded feat/provable-safety-place-and-route
branch): this generator's own header used to state plainly "this generator
has no creepage constraint type today (only clearance and track_width)".
That made every creepage figure established for this board enforced only by
check_isolation_keepout.py's straight-line-corridor approximation -- a
documented sufficient-but-not-necessary bound, not the fab-authoritative
KiCad DRC check.

kicad-cli 10.0.4 DOES implement a real `creepage` constraint
(CREEPAGE_CONSTRAINT / DRCE_CREEPAGE) -- confirmed against
kicad-source-mirror @ the 10.0.4 tag and empirically. RULE 2 ("AC Mains to
LV") and RULE 4 ("HV to LV") now each carry a second `(constraint
creepage ...)` clause pinned to HV_CREEPAGE_ENFORCED_MM, which reuses --
rather than re-deciding -- scripts/check_isolation_keepout.py's
MIN_BARRIER_WIDTH_MM (currently the PD2/8.0mm figure) for the same barrier.

Groups:
  TestCreepageConstantsDeclared    -- both PD2/PD3 candidate figures are
                                     declared, and the enforced constant is
                                     one of the two -- never silently
                                     invented or collapsed.
  TestCreepageConstraintEmitted    -- static checks that RULE 2/RULE 4 emit
                                     a `(constraint creepage ...)` clause
                                     pinned to HV_CREEPAGE_ENFORCED_MM.
  TestCreepageDrcFalsifier         -- real kicad-cli DRC run on a minimal,
                                     isolated fixture proving the emitted
                                     constraint actually binds (produces a
                                     real "creepage" violation), not just
                                     parses. Skipped if kicad-cli isn't on
                                     PATH.
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


def _rule_block(content: str, rule_name: str) -> str:
    m = re.search(rf'\(rule "{re.escape(rule_name)}".*?\n\)\n', content, re.DOTALL)
    assert m, f"{rule_name!r} rule not found in generated output"
    return m.group(0)


# ---------------------------------------------------------------------------
# TestCreepageConstantsDeclared
# ---------------------------------------------------------------------------


class TestCreepageConstantsDeclared:
    def test_both_pd2_and_pd3_candidates_declared(self) -> None:
        assert gen.HV_CREEPAGE_PD2_MM == 8.0
        assert gen.HV_CREEPAGE_PD3_MM == 12.6

    def test_enforced_constant_is_one_of_the_two_declared_candidates(self) -> None:
        assert gen.HV_CREEPAGE_ENFORCED_MM in (gen.HV_CREEPAGE_PD2_MM, gen.HV_CREEPAGE_PD3_MM)

    def test_enforced_constant_matches_check_isolation_keepout(self) -> None:
        """The two independent creepage enforcement points on this board
        (this generator's KiCad DRC rules and check_isolation_keepout.py's
        board-construction check) must not silently diverge."""
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        import check_isolation_keepout as keepout  # noqa: E402

        assert gen.HV_CREEPAGE_ENFORCED_MM == keepout.MIN_BARRIER_WIDTH_MM


# ---------------------------------------------------------------------------
# TestCreepageConstraintEmitted
# ---------------------------------------------------------------------------


class TestCreepageConstraintEmitted:
    def test_ac_mains_to_lv_rule_emits_creepage_constraint(self) -> None:
        block = _rule_block(gen.generate_dru(), "AC Mains to LV")
        assert "(constraint clearance (min 6.0mm))" in block
        assert f"(constraint creepage (min {gen.fmt_mm(gen.HV_CREEPAGE_ENFORCED_MM)}))" in block

    def test_hv_to_lv_rule_emits_creepage_constraint(self) -> None:
        block = _rule_block(gen.generate_dru(), "HV to LV")
        assert "(constraint clearance (min 2.0mm))" in block
        assert f"(constraint creepage (min {gen.fmt_mm(gen.HV_CREEPAGE_ENFORCED_MM)}))" in block

    def test_header_documents_creepage_is_now_enforced(self) -> None:
        content = gen.generate_dru()
        assert "CREEPAGE IS ENFORCED HERE" in content
        assert "check_isolation_keepout.py" in content

    def test_no_other_rule_gained_a_creepage_constraint(self) -> None:
        """Only the AC-Mains/HighVoltage <-> everything-else boundary rules
        should carry the new constraint -- e.g. "HV internal same
        footprint" and "GateDrive near HV" must not."""
        content = gen.generate_dru()
        for name in ("HV internal same footprint", "GateDrive near HV", "Ground clearance"):
            block = _rule_block(content, name)
            assert "constraint creepage" not in block


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


@pytest.mark.skipif(KICAD_CLI is None, reason="kicad-cli not on PATH")
class TestCreepageDrcFalsifier:
    """Real kicad-cli DRC falsifier: the emitted `creepage` constraint must
    actually bind (produce a real, measured violation), not just parse."""

    def _fixture(self, tmp_path: Path, gap_mm: float) -> Path:
        from kiutils.board import Board, LayerToken
        from kiutils.footprint import Footprint, Pad
        from kiutils.items.common import Net, Position
        from kiutils.items.fpitems import FpRect
        from kiutils.items.gritems import GrPoly

        board = Board()
        board.version = "20221018"
        board.generator = "pytest-creepage-fixture"
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
                coordinates=[
                    Position(0, 0), Position(60, 0), Position(60, 60), Position(0, 60),
                ],
                layer="Edge.Cuts",
                width=0.1,
            )
        ]
        half_gap = gap_mm / 2
        pad_half_width = 1.0
        # Two SEPARATE footprints (Q1 on HV_SIDE, Q2 on LV_SIDE), not two
        # pads of one footprint: RULE 1 ("Same footprint pads") matches any
        # same-footprint pad pair regardless of net class today (that
        # cross-domain gap is a separate, already-identified defect --
        # fix(drc): RULE 1/1a discriminate by domain via netclass, not
        # literal net names, not part of this recovery) and would override
        # this rule's clearance/creepage constraint for a same-footprint
        # fixture, silently masking the very thing this test verifies.
        fp1 = Footprint()
        fp1.entryName = "Test:Creepage_HvSide"
        fp1.layer = "F.Cu"
        fp1.position = Position(30 - (half_gap + pad_half_width), 30)
        fp1.properties = {"Reference": "Q1"}
        fp1.pads = [
            Pad(
                number="1", type="smd", shape="rect",
                position=Position(0, 0), size=Position(2, 2),
                layers=["F.Cu"], net=Net(number=1, name="HV_SIDE"),
            ),
        ]
        fp1.graphicItems = [FpRect(start=Position(-3, -4), end=Position(3, 4), layer="F.CrtYd", width=0.05)]

        fp2 = Footprint()
        fp2.entryName = "Test:Creepage_LvSide"
        fp2.layer = "F.Cu"
        fp2.position = Position(30 + (half_gap + pad_half_width), 30)
        fp2.properties = {"Reference": "Q2"}
        fp2.pads = [
            Pad(
                number="1", type="smd", shape="rect",
                position=Position(0, 0), size=Position(2, 2),
                layers=["F.Cu"], net=Net(number=2, name="LV_SIDE"),
            ),
        ]
        fp2.graphicItems = [FpRect(start=Position(-3, -4), end=Position(3, 4), layer="F.CrtYd", width=0.05)]

        board.footprints = [fp1, fp2]

        pcb_path = tmp_path / "creepage_fixture.kicad_pcb"
        board.to_file(str(pcb_path))

        proj = json.loads((REPO_ROOT / "pcb" / "temper_final_verified.kicad_pro").read_text())
        ns = proj["net_settings"]
        default_class = dict(ns["classes"][0])
        hv_class = dict(default_class)
        hv_class.update({"name": "HighVoltage", "clearance": 0.05, "track_width": 3.0})
        ns["classes"] = [default_class, hv_class]
        ns["netclass_assignments"] = {"HV_SIDE": "HighVoltage"}  # LV_SIDE -> Default
        (tmp_path / "creepage_fixture.kicad_pro").write_text(json.dumps(proj))

        return pcb_path

    def test_real_hv_to_lv_rule_flags_a_gap_below_the_enforced_creepage_figure(
        self, tmp_path: Path
    ) -> None:
        """The exact 'HV to LV' rule block generate_dru() emits today,
        applied wholesale (not a hand-picked substitute), must produce a
        real creepage violation for a HighVoltage<->Default pad pair whose
        straight-line gap is well below HV_CREEPAGE_ENFORCED_MM."""
        gap_mm = 5.0
        assert gap_mm < gen.HV_CREEPAGE_ENFORCED_MM
        pcb_path = self._fixture(tmp_path, gap_mm)
        content = gen.generate_dru()
        violations = _run_drc(pcb_path, content)
        creepage = [v for v in violations if v["type"] == "creepage"]
        assert len(creepage) >= 1, (
            f"expected the {gap_mm}mm cross-domain gap to FAIL the emitted "
            f"{gen.HV_CREEPAGE_ENFORCED_MM}mm creepage constraint; got no "
            f"creepage violations -- the emitted rule may not be binding"
        )

    def test_gap_above_the_enforced_creepage_figure_does_not_flag(
        self, tmp_path: Path
    ) -> None:
        """Control case: a gap comfortably above HV_CREEPAGE_ENFORCED_MM
        must not produce a creepage violation -- proves the constraint is a
        real bound, not an always-fire tripwire."""
        gap_mm = gen.HV_CREEPAGE_ENFORCED_MM + 10.0
        pcb_path = self._fixture(tmp_path, gap_mm)
        content = gen.generate_dru()
        violations = _run_drc(pcb_path, content)
        creepage = [v for v in violations if v["type"] == "creepage"]
        assert len(creepage) == 0, (
            f"expected the {gap_mm}mm gap (well above "
            f"{gen.HV_CREEPAGE_ENFORCED_MM}mm) to PASS; got {len(creepage)} "
            f"creepage violations"
        )
