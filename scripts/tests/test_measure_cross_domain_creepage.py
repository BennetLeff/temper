"""Tests for measure_cross_domain_creepage.py.

Deliberately do NOT rely on the real ``pcb/temper.kicad_pcb`` or the real
``elec/domain_manifest.yaml`` -- matching the convention in
``test_check_isolation_keepout.py`` (synthetic board built via the kiutils
Python API, round-tripped through ``Board.to_file``/``Board.from_file`` so
every fixture exercises the exact same parser the tool itself uses). The
real board/manifest pair is exercised directly by running the tool (see
docs/evidence/2026-07-30-cross-domain-creepage-pd2-vs-pd3.md), including a
cross-check against previously-published exact ground-truth figures
(T1 = 9.100mm, K1 = 8.000mm, C17-R32 = ~0.905mm) that this synthetic suite
cannot reproduce on its own.

Board layout (200x200mm, five well-separated regions so no scenario
interferes with another):

  Region A (y=20,  x=20/30):  clean inter-footprint pair, no obstruction
                               -> body_free.
  Region B (y=20,  x~100):    single 2-pad footprint UB straddling both
                               domains, F.Fab body spans both pads
                               -> body_crossing (own body).
  Region C (y=20,  x=150/170): inter-footprint pair with a third,
                               domain-irrelevant footprint's F.Fab body
                               sitting on the straight-line path between
                               them -> body_crossing (bystander body).
  Region D (y=150, x=20/30):  clean inter-footprint pair, structurally
                               identical to Region A, except the HV pad's
                               own footprint carries neither F.Fab nor
                               F.CrtYd -> unknown (own-body cannot be ruled
                               out, not silently assumed body_free).
  Region E (y=100, x=20/190): far-apart control pair (~169mm gap) -- always
                               examined (counted in the denominator) but
                               never violates any threshold used here except
                               the wide one in the differential test.

Groups:
  TestManifestLoader     -- same discipline as check_isolation_keepout.py's
                             loader: exact literal net names, fail-closed.
  TestAntiVacuity         -- missing/empty inputs, zero HV/SELV pads -> ToolError.
  TestDenominator         -- pairs_examined = hv_pads * selv_pads, always.
  TestBodyClassification  -- body_free / body_crossing (own + bystander) / unknown.
  TestSortingAndAttribution -- worst-gap-first, component attribution.
  TestDifferential        -- --compare-to-mm delta, and the aliasing
                             regression: computing a second threshold must
                             never mutate an already-returned Report.
  TestRotationSensitivityPlumbing -- the mechanism runs and records a value
                             (or None when disabled); full real-board
                             behavior is validated separately (12 flips
                             found on pcb/temper.kicad_pcb at 8.0mm --
                             see the evidence doc).
  TestSSOTReuse           -- --min-creepage-mm default is imported from
                             check_isolation_keepout.MIN_BARRIER_WIDTH_MM,
                             never a duplicated literal.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_isolation_keepout  # noqa: E402
from kiutils.board import Board, LayerToken  # noqa: E402
from kiutils.footprint import Footprint, Pad  # noqa: E402
from kiutils.items.common import Net, Position  # noqa: E402
from kiutils.items.fpitems import FpPoly  # noqa: E402
from kiutils.items.gritems import GrPoly  # noqa: E402
from measure_cross_domain_creepage import (  # noqa: E402
    CURRENT_ENFORCED_MIN_CREEPAGE_MM,
    ToolError,
    load_board,
    load_manifest,
    measure,
    measure_all_pairs,
    measure_at_second_threshold,
)

MANIFEST_TEXT = """
schema_version: 1
domains:
  HV:
    nets: ["ac_l"]
  SELV:
    nets: ["gnd"]
"""


def write_manifest(tmp_path: Path, text: str = MANIFEST_TEXT) -> Path:
    p = tmp_path / "manifest.yaml"
    p.write_text(text)
    return p


COPPER_LAYERS = [
    LayerToken(ordinal=0, name="F.Cu", type="signal"),
    LayerToken(ordinal=31, name="B.Cu", type="signal"),
]


def _rect_pad(number: str, net: Net, x: float = 0.0, y: float = 0.0, w: float = 1.0, h: float = 1.0) -> Pad:
    return Pad(
        number=number, type="smd", shape="rect", position=Position(x, y), size=Position(w, h),
        layers=["F.Cu"], net=net,
    )


def _fab_box(cx: float, cy: float, half_w: float, half_h: float) -> FpPoly:
    """A local-frame F.Fab rectangle, centred at (cx, cy) in footprint-local
    coordinates, as a closed FpPoly -- the simplest body outline kiutils can
    round-trip through ``Board.to_file``/``from_file``."""
    return FpPoly(
        layer="F.Fab",
        coordinates=[
            Position(cx - half_w, cy - half_h),
            Position(cx + half_w, cy - half_h),
            Position(cx + half_w, cy + half_h),
            Position(cx - half_w, cy + half_h),
        ],
    )


def build_board() -> Board:
    board = Board()
    board.version = "20211014"
    board.generator = "pytest"
    board.layers = list(COPPER_LAYERS) + [LayerToken(ordinal=44, name="Edge.Cuts", type="user")]
    board.nets = [
        Net(number=0, name=""),
        Net(number=1, name="ac_l"),
        Net(number=2, name="gnd"),
        Net(number=3, name="misc"),
    ]
    board.graphicItems = [
        GrPoly(
            coordinates=[Position(0, 0), Position(200, 0), Position(200, 200), Position(0, 200)],
            layer="Edge.Cuts",
            width=0.1,
        )
    ]
    board.zones = []

    footprints: list[Footprint] = []

    def _fp(ref: str, x: float, y: float, pads: list[Pad], fab: list[FpPoly] | None = None) -> Footprint:
        fp = Footprint()
        fp.entryName = f"Test:{ref}"
        fp.layer = "F.Cu"
        fp.position = Position(x, y)
        fp.properties = {"Reference": ref}
        fp.pads = pads
        fp.graphicItems = list(fab or [])
        return fp

    net_ac_l = Net(number=1, name="ac_l")
    net_gnd = Net(number=2, name="gnd")
    net_misc = Net(number=3, name="misc")

    # --- Region A: clean pair, no obstruction -> body_free ---
    footprints.append(_fp("QA", 20, 20, [_rect_pad("1", net_ac_l)], [_fab_box(0, 0, 0.3, 0.3)]))
    footprints.append(_fp("UA", 30, 20, [_rect_pad("1", net_gnd)], [_fab_box(0, 0, 0.3, 0.3)]))

    # --- Region B: intra-footprint isolator, own F.Fab body spans both pads
    #     -> body_crossing ---
    footprints.append(
        _fp(
            "UB",
            100,
            20,
            [_rect_pad("1", net_ac_l, x=-2, y=0), _rect_pad("2", net_gnd, x=2, y=0)],
            [_fab_box(0, 0, 3.0, 2.0)],
        )
    )

    # --- Region C: inter-footprint pair with a bystander's F.Fab body on
    #     the path between them -> body_crossing (crosses the bystander) ---
    footprints.append(_fp("QC", 150, 20, [_rect_pad("1", net_ac_l)]))
    footprints.append(_fp("UC", 170, 20, [_rect_pad("1", net_gnd)]))
    footprints.append(
        _fp("RC", 160, 20, [_rect_pad("1", net_misc)], [_fab_box(0, 0, 5.0, 5.0)])
    )  # RC's own net ("misc") is neither HV nor SELV -- it never forms a
    # cross-domain pair itself, only its BODY matters here.

    # --- Region D: clean pair, structurally identical to A, except QD
    #     carries no F.Fab/F.CrtYd at all -> unknown ---
    footprints.append(_fp("QD", 20, 150, [_rect_pad("1", net_ac_l)]))  # no fab= -> empty graphicItems
    footprints.append(_fp("UD", 30, 150, [_rect_pad("1", net_gnd)], [_fab_box(0, 0, 0.3, 0.3)]))

    # --- Region E: far-apart control, always in the denominator ---
    footprints.append(_fp("QE", 20, 100, [_rect_pad("1", net_ac_l)]))
    footprints.append(_fp("UE", 190, 100, [_rect_pad("1", net_gnd)]))

    board.footprints = footprints
    board.traceItems = []
    return board


def write_board(tmp_path: Path, board: Board, name: str = "board.kicad_pcb") -> Path:
    p = tmp_path / name
    board.to_file(str(p))
    return p


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    return write_board(tmp_path, build_board()), write_manifest(tmp_path)


# ---------------------------------------------------------------------------
# TestManifestLoader
# ---------------------------------------------------------------------------


class TestManifestLoader:
    def test_rejects_overlapping_domains(self, tmp_path: Path) -> None:
        p = write_manifest(
            tmp_path,
            'schema_version: 1\ndomains:\n  HV:\n    nets: ["shared"]\n  SELV:\n    nets: ["shared"]\n',
        )
        with pytest.raises(ToolError, match="BOTH HV and SELV"):
            load_manifest(p)

    def test_rejects_empty_domains_mapping(self, tmp_path: Path) -> None:
        p = write_manifest(tmp_path, "schema_version: 1\ndomains: {}\n")
        with pytest.raises(ToolError):
            load_manifest(p)

    def test_rejects_missing_hv_domain(self, tmp_path: Path) -> None:
        p = write_manifest(tmp_path, 'schema_version: 1\ndomains:\n  SELV:\n    nets: ["gnd"]\n')
        with pytest.raises(ToolError, match="'HV'"):
            load_manifest(p)

    def test_exact_literal_net_matching_not_substring(self, tmp_path: Path) -> None:
        """The manifest's own ground rule: domain membership is exact
        literal net name, never a prefix/substring guess."""
        board_path = write_board(tmp_path, build_board())
        # A manifest that declares a net which is only a SUBSTRING of a real
        # net ("ac_l" contains "ac") must not match "ac_l" via "ac".
        manifest_path = write_manifest(tmp_path, 'schema_version: 1\ndomains:\n  HV:\n    nets: ["ac"]\n  SELV:\n    nets: ["gnd"]\n')
        with pytest.raises(ToolError, match="zero HV"):
            load_board(board_path, load_manifest(manifest_path))


# ---------------------------------------------------------------------------
# TestAntiVacuity
# ---------------------------------------------------------------------------


class TestAntiVacuity:
    def test_missing_board_file(self, tmp_path: Path) -> None:
        manifest_path = write_manifest(tmp_path)
        with pytest.raises(ToolError):
            load_board(tmp_path / "does_not_exist.kicad_pcb", load_manifest(manifest_path))

    def test_missing_manifest_file(self, tmp_path: Path) -> None:
        with pytest.raises(ToolError):
            load_manifest(tmp_path / "does_not_exist.yaml")

    def test_zero_hv_pads(self, tmp_path: Path) -> None:
        board_path = write_board(tmp_path, build_board())
        manifest_path = write_manifest(
            tmp_path, 'schema_version: 1\ndomains:\n  HV:\n    nets: ["nonexistent"]\n  SELV:\n    nets: ["gnd"]\n'
        )
        with pytest.raises(ToolError, match="zero HV-domain-classified pads"):
            load_board(board_path, load_manifest(manifest_path))

    def test_zero_selv_pads(self, tmp_path: Path) -> None:
        board_path = write_board(tmp_path, build_board())
        manifest_path = write_manifest(
            tmp_path, 'schema_version: 1\ndomains:\n  HV:\n    nets: ["ac_l"]\n  SELV:\n    nets: ["nonexistent"]\n'
        )
        with pytest.raises(ToolError, match="zero SELV-domain-classified pads"):
            load_board(board_path, load_manifest(manifest_path))

    def test_zero_footprints(self, tmp_path: Path) -> None:
        board = build_board()
        board.footprints = []
        board_path = write_board(tmp_path, board)
        manifest_path = write_manifest(tmp_path)
        with pytest.raises(ToolError, match="zero footprints"):
            load_board(board_path, load_manifest(manifest_path))

    def test_measure_never_reports_clean_zero_for_empty_domain(self, tmp_path: Path) -> None:
        """'0 violations' must never silently mean 'found nothing' -- an
        empty domain is a ToolError, not a vacuous clean report."""
        board_path = write_board(tmp_path, build_board())
        manifest_path = write_manifest(
            tmp_path, 'schema_version: 1\ndomains:\n  HV:\n    nets: ["nope"]\n  SELV:\n    nets: ["gnd"]\n'
        )
        with pytest.raises(ToolError):
            measure(board_path, manifest_path, 8.0)


# ---------------------------------------------------------------------------
# TestDenominator
# ---------------------------------------------------------------------------


class TestDenominator:
    def test_pairs_examined_is_full_cross_product(self, tmp_path: Path) -> None:
        board_path, manifest_path = _fixture(tmp_path)
        report, _all, _bodies = measure(board_path, manifest_path, 8.0)
        # 6 HV pads (QA, UB.1, QC, QD, QE, and none other) x 6 SELV pads
        # (UA, UB.2, UC, UD, UE) -- computed from the fixture, not assumed.
        assert report.pairs_examined == report.hv_pads_total * report.selv_pads_total
        assert report.pairs_examined > 0
        # Every violation is drawn from the full pair space, never more.
        assert len(report.violations) <= report.pairs_examined

    def test_denominator_reported_even_with_far_threshold(self, tmp_path: Path) -> None:
        """A threshold so small nothing violates must still report the real
        denominator, not silently look empty."""
        board_path, manifest_path = _fixture(tmp_path)
        report, _all, _bodies = measure(board_path, manifest_path, 0.001)
        assert report.violations == []
        assert report.pairs_examined > 0
        assert report.hv_pads_total > 0
        assert report.selv_pads_total > 0


# ---------------------------------------------------------------------------
# TestBodyClassification
# ---------------------------------------------------------------------------


class TestBodyClassification:
    def test_clean_pair_is_body_free(self, tmp_path: Path) -> None:
        board_path, manifest_path = _fixture(tmp_path)
        report, _all, _bodies = measure(board_path, manifest_path, 20.0)
        found = [f for f in report.violations if f.hv.ref == "QA" and f.selv.ref == "UA"]
        assert len(found) == 1
        assert found[0].body_class == "body_free"
        assert found[0].crossed_by == ()

    def test_intra_footprint_isolator_is_body_crossing(self, tmp_path: Path) -> None:
        board_path, manifest_path = _fixture(tmp_path)
        report, _all, _bodies = measure(board_path, manifest_path, 20.0)
        found = [f for f in report.violations if f.hv.ref == "UB" and f.selv.ref == "UB"]
        assert len(found) == 1
        assert found[0].body_class == "body_crossing"
        assert found[0].crossed_by == ("UB",)

    def test_bystander_body_is_body_crossing(self, tmp_path: Path) -> None:
        """A third component's body sitting on the straight-line path
        between two OTHER components' pads must be detected -- not just an
        endpoint's own footprint."""
        board_path, manifest_path = _fixture(tmp_path)
        report, _all, _bodies = measure(board_path, manifest_path, 30.0)
        found = [f for f in report.violations if f.hv.ref == "QC" and f.selv.ref == "UC"]
        assert len(found) == 1
        assert found[0].body_class == "body_crossing"
        assert "RC" in found[0].crossed_by

    def test_missing_own_body_outline_is_unknown_not_body_free(self, tmp_path: Path) -> None:
        """QD carries neither F.Fab nor F.CrtYd -- its own-body crossing
        cannot be ruled out, so this must be 'unknown', never silently
        'body_free'."""
        board_path, manifest_path = _fixture(tmp_path)
        report, _all, _bodies = measure(board_path, manifest_path, 20.0)
        found = [f for f in report.violations if f.hv.ref == "QD" and f.selv.ref == "UD"]
        assert len(found) == 1
        assert found[0].body_class == "unknown"


# ---------------------------------------------------------------------------
# TestSortingAndAttribution
# ---------------------------------------------------------------------------


class TestSortingAndAttribution:
    def test_violations_sorted_worst_first(self, tmp_path: Path) -> None:
        board_path, manifest_path = _fixture(tmp_path)
        report, _all, _bodies = measure(board_path, manifest_path, 200.0)
        distances = [f.distance_mm for f in report.violations]
        assert distances == sorted(distances)

    def test_component_attribution_lists_worst_gap(self, tmp_path: Path) -> None:
        from measure_cross_domain_creepage import _component_attribution

        board_path, manifest_path = _fixture(tmp_path)
        report, _all, _bodies = measure(board_path, manifest_path, 20.0)
        attribution = {ref: (worst, count) for ref, worst, count in _component_attribution(report.violations)}
        assert "QA" in attribution
        assert "UB" in attribution
        # UB appears once as hv-side and once as selv-side of the SAME pair
        # (its own intra-footprint pair) -- attribution counts pair
        # membership per component, so UB should show count >= 1.
        assert attribution["UB"][1] >= 1


# ---------------------------------------------------------------------------
# TestDifferential
# ---------------------------------------------------------------------------


class TestDifferential:
    def test_delta_only_contains_newly_violating_pairs(self, tmp_path: Path) -> None:
        board_path, manifest_path = _fixture(tmp_path)
        report_lo, all_findings, bodies = measure(board_path, manifest_path, 5.0)
        report_hi = measure_at_second_threshold(report_lo, all_findings, bodies, 200.0)

        lo_labels = {f.label for f in report_lo.violations}
        hi_labels = {f.label for f in report_hi.violations}
        assert lo_labels <= hi_labels  # every low-threshold violation still violates at the higher one
        assert len(hi_labels) > len(lo_labels)  # the wider threshold catches strictly more (Region E etc.)

    def test_second_threshold_does_not_mutate_first_report(self, tmp_path: Path) -> None:
        """Regression test for a real aliasing bug caught during development:
        classify_violations() used to mutate PairFinding objects shared
        between thresholds in place, so computing a second threshold from
        the same all_findings list silently corrupted an already-returned
        Report's body_class/convention_sensitive values. This must not
        happen -- report_lo.violations must be identical before and after
        computing report_hi."""
        board_path, manifest_path = _fixture(tmp_path)
        report_lo, all_findings, bodies = measure(board_path, manifest_path, 20.0)
        before = [(f.label, f.body_class, f.convention_sensitive, f.distance_mm) for f in report_lo.violations]

        _report_hi = measure_at_second_threshold(report_lo, all_findings, bodies, 200.0)

        after = [(f.label, f.body_class, f.convention_sensitive, f.distance_mm) for f in report_lo.violations]
        assert before == after
        assert len(before) > 0  # make sure this test actually exercised something


# ---------------------------------------------------------------------------
# TestRotationSensitivityPlumbing
# ---------------------------------------------------------------------------


class TestRotationSensitivityPlumbing:
    def test_disabled_leaves_fields_none(self, tmp_path: Path) -> None:
        board_path, manifest_path = _fixture(tmp_path)
        report, _all, _bodies = measure(board_path, manifest_path, 20.0, check_rotation_sensitivity=False)
        assert report.violations  # non-empty, or this test proves nothing
        assert all(f.convention_sensitive is None for f in report.violations)
        assert all(f.distance_mm_alt is None for f in report.violations)

    def test_enabled_populates_a_boolean(self, tmp_path: Path) -> None:
        board_path, manifest_path = _fixture(tmp_path)
        report, _all, _bodies = measure(board_path, manifest_path, 20.0, check_rotation_sensitivity=True)
        assert report.violations
        assert all(isinstance(f.convention_sensitive, bool) for f in report.violations)
        assert all(isinstance(f.distance_mm_alt, float) for f in report.violations)


# ---------------------------------------------------------------------------
# TestSSOTReuse
# ---------------------------------------------------------------------------


class TestSSOTReuse:
    def test_default_threshold_is_imported_not_duplicated(self) -> None:
        assert CURRENT_ENFORCED_MIN_CREEPAGE_MM == check_isolation_keepout.MIN_BARRIER_WIDTH_MM


# ---------------------------------------------------------------------------
# Sanity checks on measure_all_pairs directly
# ---------------------------------------------------------------------------


class TestMeasureAllPairs:
    def test_every_pair_is_measured_exactly_once(self, tmp_path: Path) -> None:
        board_path, manifest_path = _fixture(tmp_path)
        manifest = load_manifest(manifest_path)
        board = load_board(board_path, manifest)
        findings = measure_all_pairs(board.hv_pads, board.selv_pads)
        assert len(findings) == len(board.hv_pads) * len(board.selv_pads)
        labels = [f.label for f in findings]
        assert len(labels) == len(set(labels))  # no duplicate pair
