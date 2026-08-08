"""Tests for check_plane_condemnation_quantifier.py.

Deliberately does NOT rely on the real ``pcb/temper.kicad_pcb`` -- matching
the convention in ``test_check_isolation_keepout.py`` (synthetic board built
via the kiutils Python API, round-tripped through ``Board.to_file``, so
every fixture exercises the exact same parser -- both kiutils itself for the
independent zone scan AND, via ``temper_placer.io.kicad_parser.parse_kicad_pcb_v6``,
the Rust ``extract_stackup_raw`` engine for the real classification -- the
gate script itself uses). The real board is exercised directly by running
the gate (see the module docstring's 2026-08-07 measurement: F.Cu/B.Cu each
6/48 = 0.125, both allowlisted in ``plane-condemnation-allowlist.yaml``).

Groups:
  TestMeasurement          -- the independent kiutils zone-fraction scan is
                               counted correctly and reuses the SSOT predicate
  TestQuantifierDetection  -- the core distinction this gate exists for:
                               a MINORITY-condemned layer is flagged, a
                               genuinely majority-plane layer is not, whether
                               or not either is allowlisted
  TestAllowlist            -- allowlisted vs unlisted condemned layers
  TestAntiVacuity          -- missing/empty inputs, zero zones, malformed
                               allowlist -> GateError, never "0 violations"
  TestFailBeforePassAfter  -- explicit before/after pair (no allowlist entry
                               -> gate fails; add the entry -> gate passes),
                               without git stash, per the plan's falsifier
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(
    0, str(Path(__file__).resolve().parents[2] / "packages" / "temper-placer" / "src")
)

from check_plane_condemnation_quantifier import (  # noqa: E402
    GateError,
    get_real_classification,
    measure_zone_fractions,
    run,
)
from kiutils.board import Board, LayerToken  # noqa: E402
from kiutils.items.common import Net, Position  # noqa: E402
from kiutils.items.zones import Hatch, Zone, ZonePolygon  # noqa: E402

_COPPER_LAYERS = [
    LayerToken(ordinal=0, name="F.Cu", type="signal"),
    LayerToken(ordinal=1, name="In1.Cu", type="signal"),
    LayerToken(ordinal=2, name="In2.Cu", type="signal"),
    LayerToken(ordinal=31, name="B.Cu", type="signal"),
]


def _zone(net_number: int, net_name: str, layer: str, tstamp: str) -> Zone:
    return Zone(
        net=net_number,
        netName=net_name,
        layers=[layer],
        hatch=Hatch(style="none", pitch=0.0),
        polygons=[
            ZonePolygon(
                coordinates=[Position(0, 0), Position(1, 0), Position(1, 1), Position(0, 1)]
            )
        ],
        tstamp=tstamp,
    )


def build_board(
    *,
    fcu_signal_zones: int = 0,
    fcu_plane_zones: int = 0,
    other_layer_zones: dict[str, int] | None = None,
    include_edge_cuts: bool = True,
) -> Board:
    """4-layer board (F.Cu/In1.Cu/In2.Cu/B.Cu). F.Cu gets
    ``fcu_signal_zones`` ordinary "SIG1"-net zones and ``fcu_plane_zones``
    "GND"-net zones (GND hits ``_is_plane_required_net``'s word-boundary
    keyword fallback, independent of the production netclass SSOT tables).
    ``other_layer_zones``: {layer_name: count of ordinary SIG1 zones}."""
    board = Board()
    board.version = "20211014"
    board.generator = "pytest"
    layers = list(_COPPER_LAYERS)
    if include_edge_cuts:
        layers.append(LayerToken(ordinal=44, name="Edge.Cuts", type="user"))
    board.layers = layers
    board.nets = [Net(number=0, name=""), Net(number=1, name="SIG1"), Net(number=2, name="GND")]

    zones: list[Zone] = []
    for i in range(fcu_signal_zones):
        zones.append(_zone(1, "SIG1", "F.Cu", f"fcu-sig-{i}"))
    for i in range(fcu_plane_zones):
        zones.append(_zone(2, "GND", "F.Cu", f"fcu-gnd-{i}"))
    for layer, count in (other_layer_zones or {}).items():
        for i in range(count):
            zones.append(_zone(1, "SIG1", layer, f"{layer}-sig-{i}"))
    board.zones = zones
    return board


def write_board(tmp_path: Path, board: Board, name: str = "board.kicad_pcb") -> Path:
    p = tmp_path / name
    board.to_file(str(p))
    return p


def write_allowlist(tmp_path: Path, entries: list[dict], name: str = "allowlist.yaml") -> Path:
    p = tmp_path / name
    p.write_text(yaml.safe_dump({"allowlist": entries}))
    return p


# ---------------------------------------------------------------------------
# TestMeasurement
# ---------------------------------------------------------------------------


class TestMeasurement:
    def test_counts_total_and_plane_required_zones_per_layer(self, tmp_path: Path) -> None:
        board_path = write_board(tmp_path, build_board(fcu_signal_zones=7, fcu_plane_zones=1))
        layers, stats = measure_zone_fractions(board_path)
        assert layers == ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"]
        assert stats["F.Cu"].total_zones == 8
        assert stats["F.Cu"].plane_required_zones == 1
        assert stats["F.Cu"].fraction == pytest.approx(0.125)
        assert stats["In1.Cu"].total_zones == 0

    def test_real_classification_agrees_with_kicad_fallback_rules(self, tmp_path: Path) -> None:
        """No declared (setup (stackup ...)) block -> fallback path: first/
        last copper index default 'signal', a plane-required zone anywhere
        on a layer overrides to 'plane', everything else 'mixed'."""
        board_path = write_board(tmp_path, build_board(fcu_signal_zones=7, fcu_plane_zones=1))
        real = get_real_classification(board_path)
        assert real["F.Cu"] == "plane"  # GND zone present -> overridden from the 'signal' default
        assert real["In1.Cu"] == "mixed"
        assert real["In2.Cu"] == "mixed"
        assert real["B.Cu"] == "signal"  # no zones at all -> untouched default


# ---------------------------------------------------------------------------
# TestQuantifierDetection -- the core distinction this gate exists for
# ---------------------------------------------------------------------------


class TestQuantifierDetection:
    def test_minority_condemned_layer_is_flagged(self, tmp_path: Path) -> None:
        """1 GND zone out of 8 (12.5%) condemns F.Cu entirely -- the exact
        documented bug shape."""
        board_path = write_board(tmp_path, build_board(fcu_signal_zones=7, fcu_plane_zones=1))
        allowlist_path = write_allowlist(tmp_path, [])
        state, report = run(board_path, allowlist_path)
        assert state == "violation"
        assert len(report.findings) == 1
        assert report.findings[0].layer == "F.Cu"
        assert report.findings[0].fraction == pytest.approx(0.125)
        assert any(f.layer == "F.Cu" for f in report.unlisted_condemned)

    def test_majority_plane_layer_is_not_flagged_even_unlisted(self, tmp_path: Path) -> None:
        """5 of 6 zones on F.Cu are plane-required (83%) -- a GENUINE plane,
        not a quantifier-bug instance. Must pass with an EMPTY allowlist:
        this is the check's core value, distinguishing real planes from
        minority-condemned ones."""
        board_path = write_board(tmp_path, build_board(fcu_signal_zones=1, fcu_plane_zones=5))
        allowlist_path = write_allowlist(tmp_path, [])
        state, report = run(board_path, allowlist_path)
        assert state == "clean"
        assert report.findings == []
        assert report.plane_layers_total == 1  # F.Cu is still classified 'plane'...
        # ...but not flagged, because its fraction is above the minority threshold.

    def test_no_plane_layers_at_all_is_clean(self, tmp_path: Path) -> None:
        board_path = write_board(tmp_path, build_board(fcu_signal_zones=5, fcu_plane_zones=0))
        allowlist_path = write_allowlist(tmp_path, [])
        state, report = run(board_path, allowlist_path)
        assert state == "clean"
        assert report.plane_layers_total == 0
        assert report.findings == []

    def test_exactly_at_threshold_is_not_flagged(self, tmp_path: Path) -> None:
        """fraction == MINORITY_THRESHOLD (0.5) is NOT < threshold -- boundary
        belongs to 'genuine plane', not 'condemned'."""
        board_path = write_board(tmp_path, build_board(fcu_signal_zones=1, fcu_plane_zones=1))
        allowlist_path = write_allowlist(tmp_path, [])
        state, report = run(board_path, allowlist_path)
        assert state == "clean"
        assert report.findings == []


# ---------------------------------------------------------------------------
# TestAllowlist
# ---------------------------------------------------------------------------


class TestAllowlist:
    def test_unlisted_condemned_layer_fails(self, tmp_path: Path) -> None:
        board_path = write_board(tmp_path, build_board(fcu_signal_zones=7, fcu_plane_zones=1))
        allowlist_path = write_allowlist(
            tmp_path,
            [
                {
                    "layer": "B.Cu",  # a DIFFERENT layer -- F.Cu remains unlisted
                    "date": "2026-08-07",
                    "reason": "unrelated",
                    "doc": "docs/solutions/x.md",
                }
            ],
        )
        state, report = run(board_path, allowlist_path)
        assert state == "violation"
        assert [f.layer for f in report.unlisted_condemned] == ["F.Cu"]

    def test_allowlisted_condemned_layer_passes(self, tmp_path: Path) -> None:
        board_path = write_board(tmp_path, build_board(fcu_signal_zones=7, fcu_plane_zones=1))
        allowlist_path = write_allowlist(
            tmp_path,
            [
                {
                    "layer": "F.Cu",
                    "date": "2026-08-07",
                    "reason": "known, tracked",
                    "doc": "docs/solutions/logic-errors/single-zone-condemns-whole-copper-layer-plane-2026-07-29.md",
                    "measured_fraction": 0.125,
                }
            ],
        )
        state, report = run(board_path, allowlist_path)
        assert state == "clean"
        assert report.unlisted_condemned == []
        assert report.findings[0].allowlisted is True

    def test_stale_allowlist_entry_noted_when_layer_no_longer_condemned(
        self, tmp_path: Path
    ) -> None:
        board_path = write_board(tmp_path, build_board(fcu_signal_zones=5, fcu_plane_zones=0))
        allowlist_path = write_allowlist(
            tmp_path,
            [
                {
                    "layer": "F.Cu",
                    "date": "2026-08-07",
                    "reason": "was condemned once",
                    "doc": "docs/solutions/x.md",
                }
            ],
        )
        state, report = run(board_path, allowlist_path)
        assert state == "clean"
        assert any("F.Cu" in note for note in report.stale_allowlist_entries)


# ---------------------------------------------------------------------------
# TestAntiVacuity
# ---------------------------------------------------------------------------


class TestAntiVacuity:
    def test_missing_board_file(self, tmp_path: Path) -> None:
        allowlist_path = write_allowlist(tmp_path, [])
        with pytest.raises(GateError):
            run(tmp_path / "does_not_exist.kicad_pcb", allowlist_path)

    def test_zero_zones_on_board(self, tmp_path: Path) -> None:
        board_path = write_board(tmp_path, build_board())  # no zones at all
        allowlist_path = write_allowlist(tmp_path, [])
        with pytest.raises(GateError, match="zero net-bearing copper zones"):
            run(board_path, allowlist_path)

    def test_zones_with_empty_net_name_do_not_count(self, tmp_path: Path) -> None:
        board = build_board()
        board.zones = [_zone(0, "", "F.Cu", "unnamed-net-zone")]
        board_path = write_board(tmp_path, board)
        allowlist_path = write_allowlist(tmp_path, [])
        with pytest.raises(GateError, match="zero net-bearing copper zones"):
            run(board_path, allowlist_path)

    def test_malformed_allowlist_not_a_mapping(self, tmp_path: Path) -> None:
        board_path = write_board(tmp_path, build_board(fcu_signal_zones=1, fcu_plane_zones=1))
        p = tmp_path / "bad_allowlist.yaml"
        p.write_text("- just\n- a\n- list\n")
        with pytest.raises(GateError, match="allowlist must be a mapping"):
            run(board_path, p)

    def test_malformed_allowlist_entry_missing_keys(self, tmp_path: Path) -> None:
        board_path = write_board(tmp_path, build_board(fcu_signal_zones=1, fcu_plane_zones=1))
        p = tmp_path / "bad_allowlist2.yaml"
        p.write_text(yaml.safe_dump({"allowlist": [{"layer": "F.Cu"}]}))  # missing date/reason/doc
        with pytest.raises(GateError, match="missing required keys"):
            run(board_path, p)

    def test_zero_copper_layers_declared(self, tmp_path: Path) -> None:
        board = Board()
        board.version = "20211014"
        board.generator = "pytest"
        board.layers = [LayerToken(ordinal=44, name="Edge.Cuts", type="user")]
        board.nets = [Net(number=0, name="")]
        board.zones = []
        board_path = write_board(tmp_path, board)
        allowlist_path = write_allowlist(tmp_path, [])
        with pytest.raises(GateError, match="zero copper"):
            run(board_path, allowlist_path)

    def test_missing_allowlist_file_treated_as_empty_not_an_error(self, tmp_path: Path) -> None:
        """A missing allowlist file is a valid (empty) allowlist -- the gate
        must still run and report real violations against it, not silently
        no-op. Distinguishes 'file absent' (fine, means nothing is
        allowlisted yet) from 'file present but malformed' (a GateError,
        asserted above)."""
        board_path = write_board(tmp_path, build_board(fcu_signal_zones=7, fcu_plane_zones=1))
        state, report = run(board_path, tmp_path / "does_not_exist_allowlist.yaml")
        assert state == "violation"


# ---------------------------------------------------------------------------
# TestFailBeforePassAfter
# ---------------------------------------------------------------------------


class TestFailBeforePassAfter:
    """Mirrors the real gate run against pcb/temper.kicad_pcb (2026-08-07):
    an empty/missing allowlist fails on F.Cu+B.Cu; the committed
    plane-condemnation-allowlist.yaml with both entries passes. Built here
    as two synthetic fixtures (never via ``git stash`` -- forbidden in this
    repo, the stash ref is shared across worktrees)."""

    def test_before_no_allowlist_entry_fails(self, tmp_path: Path) -> None:
        board_path = write_board(
            tmp_path, build_board(fcu_signal_zones=7, fcu_plane_zones=1), name="before.kicad_pcb"
        )
        allowlist_path = write_allowlist(tmp_path, [], name="before_allowlist.yaml")
        state, _report = run(board_path, allowlist_path)
        assert state == "violation"

    def test_after_allowlist_entry_added_passes(self, tmp_path: Path) -> None:
        board_path = write_board(
            tmp_path, build_board(fcu_signal_zones=7, fcu_plane_zones=1), name="after.kicad_pcb"
        )
        allowlist_path = write_allowlist(
            tmp_path,
            [
                {
                    "layer": "F.Cu",
                    "date": "2026-08-07",
                    "reason": "tracked",
                    "doc": "docs/solutions/logic-errors/single-zone-condemns-whole-copper-layer-plane-2026-07-29.md",
                }
            ],
            name="after_allowlist.yaml",
        )
        state, _report = run(board_path, allowlist_path)
        assert state == "clean"
