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
        # pads of one footprint: this keeps the fixture generic (it does not
        # rely on RULE 1's now-fixed A.Reference/A.NetClass same-footprint
        # guard to avoid a false pass) and mirrors the realistic case this
        # rule targets -- cross-component creepage, not same-footprint pin
        # pitch.
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


# ---------------------------------------------------------------------------
# TestHighVoltageIsolatedRules -- closing the netclass with no rules at all
# ---------------------------------------------------------------------------
#
# Background (docs/evidence/2026-07-28-hv-isolated-rules-and-creepage-triage.md):
# grep -c HighVoltageIsolated scripts/generate_kicad_dru.py used to return 0
# -- this netclass (the gate-drive floating bootstrap supply: +5V_ISO,
# VBOOT_H, VBOOT_L, and the UCC21550's own secondary bias nets
# hb.gate_hs.driver-p1-1/-p2) carried no custom clearance or creepage
# constraint anywhere in this generator, even though RULE 1's cross-domain
# guard fix (docs/evidence/2026-07-28-drc-rule1-netclass-redo.md sec 5)
# specifically re-homed U7's secondary bias nets INTO this class.
#
# elec/domain_manifest.yaml declares every net in this class a member of the
# same `HV` domain as ac_l/+170V_BUS/SW_NODE -- "isolated" names the gate
# driver's own internal primary/secondary barrier, not a barrier this
# class's nets sit on the far side of relative to the rest of HV. Two new
# rules therefore apply asymmetric treatment:
#   "HighVoltageIsolated same side"  -- functional-only clearance (2.0mm)
#                                       against its own HV/ACMains neighbours
#   "HighVoltageIsolated to LV"      -- reinforced clearance (2.0mm) AND
#                                       creepage (HV_CREEPAGE_ENFORCED_MM,
#                                       currently 8.0mm/PD2)
#                                       against every other (LV/SELV) class


def _build_two_class_fixture(
    tmp_path: Path,
    gap_mm: float,
    class_a: str,
    clearance_a: float,
    class_b: str | None,
    clearance_b: float | None,
) -> Path:
    """A single footprint 'Q1' with two SMD pads on nets 'A_SIDE'/'B_SIDE',
    gap_mm edge-to-edge apart. 'A_SIDE' is assigned to class_a; 'B_SIDE' is
    assigned to class_b if given, else left on the project's Default class
    (mirrors the LV/SELV fallthrough case). Per-netclass baseline clearance
    values are set explicitly on both classes so the fixture's own baseline
    clearance can be controlled independently of whatever custom .kicad_dru
    rule is under test -- same technique TestCreepageDrcFalsifier._fixture
    already established."""
    from kiutils.board import Board, LayerToken
    from kiutils.footprint import Footprint, Pad
    from kiutils.items.common import Net, Position
    from kiutils.items.fpitems import FpRect
    from kiutils.items.gritems import GrPoly

    board = Board()
    board.version = "20221018"
    board.generator = "pytest-hv-isolated-fixture"
    board.layers = [
        LayerToken(ordinal=0, name="F.Cu", type="signal"),
        LayerToken(ordinal=31, name="B.Cu", type="signal"),
        LayerToken(ordinal=44, name="Edge.Cuts", type="user"),
        LayerToken(ordinal=47, name="F.CrtYd", type="user", userName="F.Courtyard"),
    ]
    board.nets = [
        Net(number=0, name=""),
        Net(number=1, name="A_SIDE"),
        Net(number=2, name="B_SIDE"),
    ]
    board.graphicItems = [
        GrPoly(
            coordinates=[Position(0, 0), Position(60, 0), Position(60, 60), Position(0, 60)],
            layer="Edge.Cuts",
            width=0.1,
        )
    ]

    half_gap = gap_mm / 2
    pad_half_width = 1.0
    fp = Footprint()
    fp.entryName = "Test:HVIsolated_Pair"
    fp.layer = "F.Cu"
    fp.position = Position(30, 30)
    fp.properties = {"Reference": "Q1"}
    fp.pads = [
        Pad(
            number="1", type="smd", shape="rect",
            position=Position(-(half_gap + pad_half_width), 0), size=Position(2, 2),
            layers=["F.Cu"], net=Net(number=1, name="A_SIDE"),
        ),
        Pad(
            number="2", type="smd", shape="rect",
            position=Position(half_gap + pad_half_width, 0), size=Position(2, 2),
            layers=["F.Cu"], net=Net(number=2, name="B_SIDE"),
        ),
    ]
    fp.graphicItems = [FpRect(start=Position(-6, -4), end=Position(6, 4), layer="F.CrtYd", width=0.05)]
    board.footprints = [fp]

    pcb_path = tmp_path / "hv_isolated_fixture.kicad_pcb"
    board.to_file(str(pcb_path))

    proj = json.loads((REPO_ROOT / "pcb" / "temper_final_verified.kicad_pro").read_text())
    ns = proj["net_settings"]
    default_class = dict(ns["classes"][0])
    a_class = dict(default_class)
    a_class.update({"name": class_a, "clearance": clearance_a, "track_width": 2.0})
    classes = [default_class, a_class]
    assignments = {"A_SIDE": class_a}
    if class_b is not None:
        b_class = dict(default_class)
        b_class.update({"name": class_b, "clearance": clearance_b, "track_width": 3.0})
        classes.append(b_class)
        assignments["B_SIDE"] = class_b
    ns["classes"] = classes
    ns["netclass_assignments"] = assignments
    (tmp_path / "hv_isolated_fixture.kicad_pro").write_text(json.dumps(proj))

    return pcb_path


class TestHighVoltageIsolatedRulesEmitted:
    """Static checks on the generated text -- no kicad-cli required."""

    def test_high_voltage_isolated_netclass_no_longer_absent(self) -> None:
        content = gen.generate_dru()
        assert content.count("HighVoltageIsolated") >= 2, (
            "HighVoltageIsolated used to have zero occurrences in the "
            "generated output (grep -c HighVoltageIsolated returned 0) -- "
            "this asserts the gap is actually closed"
        )

    def test_same_side_rule_is_clearance_only_no_creepage(self) -> None:
        block = _rule_block(gen.generate_dru(), "HighVoltageIsolated same side")
        assert "A.NetClass == 'HighVoltageIsolated'" in block
        assert "B.NetClass == 'HighVoltage'" in block
        assert "B.NetClass == 'ACMains'" in block
        assert f"(constraint clearance (min {gen.fmt_mm(gen.HV_INTERNAL_CLEARANCE_MM)}))" in block
        assert "creepage" not in block, (
            "the same-side rule must NOT carry a creepage constraint -- "
            "both nets are on the same side of the reinforced barrier"
        )

    def test_to_lv_rule_has_reinforced_clearance_and_creepage(self) -> None:
        block = _rule_block(gen.generate_dru(), "HighVoltageIsolated to LV")
        assert "A.NetClass == 'HighVoltageIsolated'" in block
        assert "B.NetClass != 'HighVoltageIsolated'" in block
        assert "B.NetClass != 'HighVoltage'" in block
        assert "B.NetClass != 'ACMains'" in block
        assert f"(constraint clearance (min {gen.fmt_mm(gen.HV_INTERNAL_CLEARANCE_MM)}))" in block
        assert f"(constraint creepage (min {gen.fmt_mm(gen.HV_CREEPAGE_ENFORCED_MM)}))" in block


@pytest.mark.skipif(KICAD_CLI is None, reason="kicad-cli not on PATH")
class TestHighVoltageIsolatedDrcFalsifier:
    """Real kicad-cli DRC falsifier for both new rules -- each must actually
    bind (produce a measured violation, or correctly not produce one), not
    merely parse."""

    def test_to_lv_rule_flags_a_gap_below_reinforced_creepage(self, tmp_path: Path) -> None:
        """HighVoltageIsolated vs. Default (LV fallthrough) at a gap that
        clears the per-netclass baseline clearance but is well below
        HV_CREEPAGE_ENFORCED_MM -- must FAIL on creepage, isolating
        the effect to the new custom rule (baseline clearance set low so it
        cannot contribute a confounding violation)."""
        gap_mm = 7.0  # clears a 0.05mm artificial baseline
        assert gap_mm < gen.HV_CREEPAGE_ENFORCED_MM
        pcb_path = _build_two_class_fixture(
            tmp_path, gap_mm, "HighVoltageIsolated", 0.05, None, None
        )
        content = gen.generate_dru()
        violations = _run_drc(pcb_path, content)
        creepage = [v for v in violations if v["type"] == "creepage"]
        assert len(creepage) >= 1, (
            f"expected the {gap_mm}mm HighVoltageIsolated<->Default gap to "
            f"FAIL the {gen.HV_CREEPAGE_ENFORCED_MM}mm creepage constraint; "
            f"got no creepage violations -- 'HighVoltageIsolated to LV' may "
            f"not be binding"
        )
        expected = f"{gen.HV_CREEPAGE_ENFORCED_MM:.4f}"
        assert any(expected in v["description"] for v in creepage), (
            f"expected a creepage violation citing {expected}mm; got "
            f"{[v['description'] for v in creepage]!r}"
        )

    def test_to_lv_rule_passes_a_gap_past_reinforced_creepage(self, tmp_path: Path) -> None:
        """Control: a gap past HV_CREEPAGE_ENFORCED_MM must NOT flag
        creepage -- proves the rule discriminates on distance."""
        gap_mm = gen.HV_CREEPAGE_ENFORCED_MM + 5.0
        pcb_path = _build_two_class_fixture(
            tmp_path, gap_mm, "HighVoltageIsolated", 0.05, None, None
        )
        content = gen.generate_dru()
        violations = _run_drc(pcb_path, content)
        creepage = [v for v in violations if v["type"] == "creepage"]
        assert creepage == [], (
            f"expected a {gap_mm}mm gap (past {gen.HV_CREEPAGE_ENFORCED_MM}mm) "
            f"to PASS; got {creepage!r}"
        )

    def test_same_side_rule_relaxes_below_the_netclass_baseline(self, tmp_path: Path) -> None:
        """HighVoltageIsolated vs. HighVoltage, both carrying the REAL
        board's 6.0mm per-netclass baseline clearance, at a 3.0mm gap: WITHOUT
        the 'HighVoltageIsolated same side' rule this would fail the 6.0mm
        baseline; WITH it (the real generated file), the pair correctly
        relaxes to HV_INTERNAL_CLEARANCE_MM (2.0mm) and passes -- proving the
        same-side relaxation is real, not a no-op, and is justified only
        because both nets share the HV domain (elec/domain_manifest.yaml)."""
        gap_mm = 3.0
        assert gen.HV_INTERNAL_CLEARANCE_MM < gap_mm < 6.0
        pcb_path = _build_two_class_fixture(
            tmp_path, gap_mm, "HighVoltageIsolated", 6.0, "HighVoltage", 6.0
        )

        # Baseline-only control: a lone rule with no matching condition (so
        # only the per-netclass 6.0mm baseline applies) must FAIL at 3.0mm --
        # establishes the baseline this rule is relaxing is real.
        baseline_only = "(version 1)\n\n"
        baseline_violations = _run_drc(pcb_path, baseline_only)
        baseline_clearance = [v for v in baseline_violations if v["type"] == "clearance"]
        assert len(baseline_clearance) >= 1, (
            f"expected the {gap_mm}mm gap to FAIL the real board's 6.0mm "
            f"HighVoltageIsolated/HighVoltage per-netclass baseline with no "
            f"custom rule in force; got {baseline_clearance!r} -- the "
            f"fixture's baseline may not be set up as intended"
        )

        content = gen.generate_dru()
        violations = _run_drc(pcb_path, content)
        clearance = [v for v in violations if v["type"] == "clearance"]
        assert clearance == [], (
            f"expected the {gap_mm}mm HighVoltageIsolated<->HighVoltage gap "
            f"to PASS under the real generated file (the 'HighVoltageIsolated "
            f"same side' rule should relax this pair to "
            f"{gen.HV_INTERNAL_CLEARANCE_MM}mm); got {clearance!r}"
        )

    def test_same_side_rule_still_enforces_its_own_floor(self, tmp_path: Path) -> None:
        """The relaxation is not unbounded: a gap below
        HV_INTERNAL_CLEARANCE_MM (2.0mm) must still FAIL."""
        gap_mm = 1.0
        assert gap_mm < gen.HV_INTERNAL_CLEARANCE_MM
        pcb_path = _build_two_class_fixture(
            tmp_path, gap_mm, "HighVoltageIsolated", 6.0, "HighVoltage", 6.0
        )
        content = gen.generate_dru()
        violations = _run_drc(pcb_path, content)
        clearance = [v for v in violations if v["type"] == "clearance"]
        assert len(clearance) >= 1, (
            f"expected the {gap_mm}mm gap (below "
            f"{gen.HV_INTERNAL_CLEARANCE_MM}mm) to FAIL even under the "
            f"relaxed same-side rule; got no clearance violations"
        )
