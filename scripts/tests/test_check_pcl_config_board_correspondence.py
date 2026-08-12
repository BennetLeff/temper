"""Tests for check_pcl_config_board_correspondence.py.

These build small, synthetic board/config/reference-manifest fixtures on
disk (``tmp_path``) rather than depending on the real
``pcb/temper.kicad_pcb`` for every scenario -- matching
``test_check_domain_partition.py``'s and ``test_check_hv_netclass_coverage.py``'s
convention of a controlled minimal reproduction per behavior. The final
group, ``TestRealRepoIntegration``, does exercise the real repo files and
documents the CURRENT (still-broken, per PR #1026) state.

See docs/evidence/2026-08-11-correspondence-gates.md for the full
before/after proof against the real historical defect.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_pcl_config_board_correspondence import (  # noqa: E402
    EXIT_VIOLATION,
    check_zone_containment,
    parse_board,
    resolve_component_references,
    run,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))
    return path


def _board_text(
    refs: list[str], outline: tuple[float, float, float, float] = (20, 20, 172, 254)
) -> str:
    x_min, y_min, x_max, y_max = outline
    footprints = "\n".join(
        f'''
  (footprint "Lib:Foo" (layer "F.Cu")
    (at 50 50 0)
    (property "Reference" "{ref}")
    (property "Value" "?")
  )'''
        for ref in refs
    )
    return f"""
(kicad_pcb (version 20211014) (generator kiutils)
  (layers
    (0 "F.Cu" signal)
    (1 "In1.Cu" power)
    (31 "B.Cu" signal)
  )
{footprints}
  (gr_poly
    (pts
      (xy {x_min} {y_min})
      (xy {x_max} {y_min})
      (xy {x_max} {y_max})
      (xy {x_min} {y_max})
    ) (layer "Edge.Cuts") (width 0.1))
)
"""


def _references_text(
    aliases: dict[str, str] | None = None, unresolved: dict[str, str] | None = None
) -> str:
    aliases = aliases or {}
    unresolved = unresolved or {}
    alias_lines = "\n".join(f"  {k}: {v}" for k, v in aliases.items()) or "  {}"
    unresolved_lines = "\n".join(f'  {k}: "{v}"' for k, v in unresolved.items()) or "  {}"
    return f"""
component_aliases:
{alias_lines if aliases else "  {}"}
unresolved_components:
{unresolved_lines if unresolved else "  {}"}
loop_aliases: {{}}
unresolved_loops: {{}}
"""


def _config_text(zones: list[dict], constraints: list[dict]) -> str:
    import yaml

    return yaml.safe_dump({"zones": zones, "constraints": constraints})


# ---------------------------------------------------------------------------
# 1. Mutations -- the two falsifiers this gate exists for
# ---------------------------------------------------------------------------


class TestMutations:
    def test_component_reference_absent_from_board_and_manifest_is_broken(self, tmp_path):
        """A name that matches nothing -- not the board, not an alias,
        not an explicit unresolved entry -- is BROKEN (Property 1)."""
        board = _write(tmp_path / "board.kicad_pcb", _board_text(["R1", "R2"]))
        refs = _write(tmp_path / "refs.yaml", _references_text())
        config = _write(
            tmp_path / "config.yaml",
            _config_text(
                zones=[{"name": "Z", "bounds": [20, 20, 172, 254], "type": "lv"}],
                constraints=[{"type": "adjacent", "a": "R1", "b": "J_GHOST", "max_distance_mm": 5}],
            ),
        )
        state, report = run(config, board, refs)
        assert state == "violation"
        assert len(report.broken_references) == 1
        assert report.broken_references[0].name == "J_GHOST"

    def test_unresolved_components_flagged_even_when_name_matches_a_real_ref(self, tmp_path):
        """The adj_Q1_Q2 shape: 'Q1' IS a real board Reference, but the
        alias manifest explicitly documents it as the WRONG component --
        unresolved_components must win over a naive direct-match."""
        board = _write(tmp_path / "board.kicad_pcb", _board_text(["Q1", "Q2", "U5", "U6"]))
        refs = _write(
            tmp_path / "refs.yaml",
            _references_text(
                unresolved={
                    "Q1": "live designator is unrelated; legacy config means U5 (IGBT)",
                    "Q2": "live designator is unrelated; legacy config means U6 (IGBT)",
                }
            ),
        )
        config = _write(
            tmp_path / "config.yaml",
            _config_text(
                zones=[{"name": "Z", "bounds": [20, 20, 172, 254], "type": "lv"}],
                constraints=[{"type": "adjacent", "a": "Q1", "b": "Q2", "max_distance_mm": 10}],
            ),
        )
        state, report = run(config, board, refs)
        assert state == "violation"
        names = {b.name for b in report.broken_references}
        assert names == {"Q1", "Q2"}
        assert "unrelated" in [b.reason for b in report.broken_references if b.name == "Q1"][0]

    def test_alias_resolves_to_real_board_ref_is_clean(self, tmp_path):
        board = _write(tmp_path / "board.kicad_pcb", _board_text(["U7", "C2"]))
        refs = _write(
            tmp_path / "refs.yaml",
            _references_text(aliases={"U_GATE": "U7", "C_BUS1": "C2"}),
        )
        config = _write(
            tmp_path / "config.yaml",
            _config_text(
                zones=[{"name": "Z", "bounds": [20, 20, 172, 254], "type": "lv"}],
                constraints=[
                    {"type": "adjacent", "a": "U_GATE", "b": "C_BUS1", "max_distance_mm": 20}
                ],
            ),
        )
        state, report = run(config, board, refs)
        assert state == "clean"
        assert report.broken_references == []

    def test_zone_outside_board_outline_is_broken(self, tmp_path):
        """The real defect's second shape: zone bounds using origin
        (0,0) on a board whose outline starts at (20,20)."""
        board = _write(tmp_path / "board.kicad_pcb", _board_text(["R1"]))
        refs = _write(tmp_path / "refs.yaml", _references_text())
        config = _write(
            tmp_path / "config.yaml",
            _config_text(
                zones=[{"name": "MCU_ZONE", "bounds": [0, 0, 100, 70], "type": "lv"}],
                constraints=[{"type": "loop_area", "loop_name": "x", "max_area_mm2": 5}],
            ),
        )
        state, report = run(config, board, refs)
        assert state == "violation"
        assert len(report.broken_zones) == 1
        assert report.broken_zones[0].name == "MCU_ZONE"

    def test_zone_within_board_outline_is_clean(self, tmp_path):
        board = _write(tmp_path / "board.kicad_pcb", _board_text(["R1"]))
        refs = _write(tmp_path / "refs.yaml", _references_text())
        config = _write(
            tmp_path / "config.yaml",
            _config_text(
                zones=[{"name": "Z", "bounds": [30, 30, 100, 100], "type": "lv"}],
                constraints=[{"type": "loop_area", "loop_name": "x", "max_area_mm2": 5}],
            ),
        )
        state, report = run(config, board, refs)
        assert state == "clean"
        assert report.broken_zones == []

    def test_zone_name_referenced_by_a_component_field_is_not_a_broken_reference(self, tmp_path):
        """separated.a/.b may name a zone (HV_ZONE vs MCU_ZONE) -- that is
        not a component reference and must not be flagged."""
        board = _write(tmp_path / "board.kicad_pcb", _board_text(["R1"]))
        refs = _write(tmp_path / "refs.yaml", _references_text())
        config = _write(
            tmp_path / "config.yaml",
            _config_text(
                zones=[
                    {"name": "HV_ZONE", "bounds": [30, 30, 100, 100], "type": "hv"},
                    {"name": "MCU_ZONE", "bounds": [100, 100, 150, 200], "type": "lv"},
                ],
                constraints=[
                    {"type": "separated", "a": "HV_ZONE", "b": "MCU_ZONE", "min_distance_mm": 10}
                ],
            ),
        )
        state, report = run(config, board, refs)
        assert state == "clean"

    def test_fixing_only_one_property_leaves_the_other_violation(self, tmp_path):
        board = _write(tmp_path / "board.kicad_pcb", _board_text(["R1"]))
        refs = _write(tmp_path / "refs.yaml", _references_text())
        config = _write(
            tmp_path / "config.yaml",
            _config_text(
                zones=[{"name": "Z", "bounds": [0, 0, 100, 70], "type": "lv"}],  # broken
                constraints=[
                    {"type": "adjacent", "a": "R1", "b": "GHOST", "max_distance_mm": 5}
                ],  # broken
            ),
        )
        state, report = run(config, board, refs)
        assert state == "violation"
        assert len(report.broken_references) == 1
        assert len(report.broken_zones) == 1


# ---------------------------------------------------------------------------
# 2. Anti-vacuity -- fail closed on every degenerate input
# ---------------------------------------------------------------------------


class TestAntiVacuity:
    def test_missing_config(self, tmp_path):
        board = _write(tmp_path / "board.kicad_pcb", _board_text(["R1"]))
        refs = _write(tmp_path / "refs.yaml", _references_text())
        state, report = run(tmp_path / "nope.yaml", board, refs)
        assert state == "tool_error"

    def test_config_with_no_constraints(self, tmp_path):
        board = _write(tmp_path / "board.kicad_pcb", _board_text(["R1"]))
        refs = _write(tmp_path / "refs.yaml", _references_text())
        config = _write(
            tmp_path / "config.yaml",
            _config_text(zones=[{"name": "Z", "bounds": [30, 30, 100, 100]}], constraints=[]),
        )
        state, report = run(config, board, refs)
        assert state == "tool_error"

    def test_config_with_no_zones_is_not_vacuous(self, tmp_path):
        """A component-only PCL file (thermal_management.yaml's shape: real
        constraints, zero zones) is a legitimate config, not a tool error --
        Property 1 (reference resolution) still has real content to check.
        This used to raise a tool error before any reference was checked,
        which is why thermal_management.yaml was never actually run through
        this gate in CI (see docs/evidence/2026-08-12-thermal-emi-declaration-drift.md)."""
        board = _write(tmp_path / "board.kicad_pcb", _board_text(["R1"]))
        refs = _write(tmp_path / "refs.yaml", _references_text())
        config = _write(
            tmp_path / "config.yaml",
            _config_text(
                zones=[], constraints=[{"type": "adjacent", "a": "R1", "b": "GHOST", "max_distance_mm": 5}]
            ),
        )
        state, report = run(config, board, refs)
        assert state == "violation"
        assert report.zones_checked == 0
        assert len(report.broken_references) == 1
        assert report.broken_references[0].name == "GHOST"

    def test_config_with_no_zones_and_clean_references_passes(self, tmp_path):
        board = _write(tmp_path / "board.kicad_pcb", _board_text(["R1", "R2"]))
        refs = _write(tmp_path / "refs.yaml", _references_text())
        config = _write(
            tmp_path / "config.yaml",
            _config_text(
                zones=[], constraints=[{"type": "adjacent", "a": "R1", "b": "R2", "max_distance_mm": 5}]
            ),
        )
        state, report = run(config, board, refs)
        assert state == "clean"
        assert report.zones_checked == 0

    def test_config_with_zones_key_not_a_list_fails_closed(self, tmp_path):
        board = _write(tmp_path / "board.kicad_pcb", _board_text(["R1"]))
        refs = _write(tmp_path / "refs.yaml", _references_text())
        config = _write(
            tmp_path / "config.yaml",
            "zones: not-a-list\nconstraints:\n  - type: loop_area\n    loop_name: x\n",
        )
        state, report = run(config, board, refs)
        assert state == "tool_error"

    def test_missing_board(self, tmp_path):
        refs = _write(tmp_path / "refs.yaml", _references_text())
        config = _write(
            tmp_path / "config.yaml",
            _config_text(
                zones=[{"name": "Z", "bounds": [30, 30, 100, 100]}],
                constraints=[{"type": "loop_area", "loop_name": "x"}],
            ),
        )
        state, report = run(config, tmp_path / "nope.kicad_pcb", refs)
        assert state == "tool_error"

    def test_board_with_zero_footprints(self, tmp_path):
        board = _write(
            tmp_path / "board.kicad_pcb",
            '(kicad_pcb (layers (0 "F.Cu" signal)) '
            '(gr_poly (pts (xy 0 0) (xy 10 0) (xy 10 10) (xy 0 10)) (layer "Edge.Cuts")))',
        )
        refs = _write(tmp_path / "refs.yaml", _references_text())
        config = _write(
            tmp_path / "config.yaml",
            _config_text(
                zones=[{"name": "Z", "bounds": [1, 1, 5, 5]}],
                constraints=[{"type": "loop_area", "loop_name": "x"}],
            ),
        )
        state, report = run(config, board, refs)
        assert state == "tool_error"

    def test_board_with_no_edge_cuts(self, tmp_path):
        board = _write(
            tmp_path / "board.kicad_pcb",
            '(kicad_pcb (layers (0 "F.Cu" signal)) (footprint "X" (property "Reference" "R1")))',
        )
        refs = _write(tmp_path / "refs.yaml", _references_text())
        config = _write(
            tmp_path / "config.yaml",
            _config_text(
                zones=[{"name": "Z", "bounds": [1, 1, 5, 5]}],
                constraints=[{"type": "loop_area", "loop_name": "x"}],
            ),
        )
        state, report = run(config, board, refs)
        assert state == "tool_error"

    def test_missing_reference_manifest(self, tmp_path):
        board = _write(tmp_path / "board.kicad_pcb", _board_text(["R1"]))
        config = _write(
            tmp_path / "config.yaml",
            _config_text(
                zones=[{"name": "Z", "bounds": [30, 30, 100, 100]}],
                constraints=[{"type": "loop_area", "loop_name": "x"}],
            ),
        )
        state, report = run(config, board, tmp_path / "nope.yaml")
        assert state == "tool_error"

    def test_reference_manifest_missing_required_keys(self, tmp_path):
        board = _write(tmp_path / "board.kicad_pcb", _board_text(["R1"]))
        refs = _write(tmp_path / "refs.yaml", "loop_aliases: {}\n")
        config = _write(
            tmp_path / "config.yaml",
            _config_text(
                zones=[{"name": "Z", "bounds": [30, 30, 100, 100]}],
                constraints=[{"type": "loop_area", "loop_name": "x"}],
            ),
        )
        state, report = run(config, board, refs)
        assert state == "tool_error"

    def test_unknown_constraint_type_fails_closed(self, tmp_path):
        board = _write(tmp_path / "board.kicad_pcb", _board_text(["R1"]))
        refs = _write(tmp_path / "refs.yaml", _references_text())
        config = _write(
            tmp_path / "config.yaml",
            _config_text(
                zones=[{"name": "Z", "bounds": [30, 30, 100, 100]}],
                constraints=[{"type": "some_future_type", "a": "R1"}],
            ),
        )
        state, report = run(config, board, refs)
        assert state == "tool_error"
        assert any("some_future_type" in e for e in report.tool_errors)


# ---------------------------------------------------------------------------
# 3. Helper units
# ---------------------------------------------------------------------------


class TestHelperUnits:
    def test_parse_board_finds_refs_and_bbox(self, tmp_path):
        board = _write(
            tmp_path / "board.kicad_pcb", _board_text(["R1", "R2"], outline=(5, 5, 55, 105))
        )
        refs, bbox = parse_board(board)
        assert refs == {"R1", "R2"}
        assert bbox == (5.0, 5.0, 55.0, 105.0)

    def test_check_zone_containment_rejects_malformed_bounds(self):
        config = {"zones": [{"name": "Z", "bounds": [1, 2, 3]}]}
        broken = check_zone_containment(config, (0, 0, 100, 100))
        assert len(broken) == 1
        assert "4-element" in broken[0].reason

    def test_check_zone_containment_rejects_inverted_bounds(self):
        config = {"zones": [{"name": "Z", "bounds": [50, 0, 10, 100]}]}
        broken = check_zone_containment(config, (0, 0, 100, 100))
        assert len(broken) == 1
        assert "min >= max" in broken[0].reason

    def test_resolve_component_references_skips_zone_names(self):
        config = {"zones": [{"name": "HV_ZONE"}], "constraints": []}
        broken, unknown = resolve_component_references(
            {**config, "constraints": [{"type": "separated", "a": "HV_ZONE", "b": "HV_ZONE"}]},
            {"R1"},
            {},
            {},
        )
        assert broken == []
        assert unknown == []


# ---------------------------------------------------------------------------
# 4. Real-repo integration -- documents the CURRENT (broken) state
# ---------------------------------------------------------------------------


class TestRealRepoIntegration:
    def test_real_repo_config_currently_violates(self):
        """PR #1026 landed the loader fix, not the config -- the real
        temper_induction_cooker.yaml is still broken as of this gate's
        writing (5 unresolved component references, 3 zones outside the
        board outline). This test pins that fact so it fails loudly (not
        silently) the day the config is actually fixed -- at which point
        this test should be updated to assert 'clean' and the CI step's
        continue-on-error should be removed (see the gate's module
        docstring / docs/evidence/2026-08-11-correspondence-gates.md)."""
        config = (
            REPO_ROOT / "packages/temper-placer/configs/constraints/temper_induction_cooker.yaml"
        )
        board = REPO_ROOT / "pcb/temper.kicad_pcb"
        refs = REPO_ROOT / "packages/temper-placer/configs/temper_constraints.references.yaml"
        state, report = run(config, board, refs)
        assert state == "violation"
        broken_names = {b.name for b in report.broken_references}
        assert {"J_AC_IN", "J_COIL", "J_DEBUG", "Q1", "Q2"} <= broken_names
        assert {z.name for z in report.broken_zones} == {"MCU_ZONE", "ISOLATION_BARRIER", "HV_ZONE"}

    def test_real_repo_gate_exits_violation_not_error(self):
        import subprocess

        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts/check_pcl_config_board_correspondence.py")],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        assert result.returncode == EXIT_VIOLATION, result.stdout + result.stderr

    def test_real_repo_thermal_management_config_currently_violates(self):
        """thermal_management.yaml -- this board's IGBT-to-RTD/MCU thermal-
        clearance declarations -- was never checked by this gate at all
        before docs/evidence/2026-08-12-thermal-emi-declaration-drift.md
        (the gate required a non-empty ``zones:`` list to run at all, and
        this component-only config has none). Before that doc's manifest
        extension, running this gate against it found 21 broken references
        across all 13 constraints -- U_RTD/TH_HEATSINK/R_GATE_HIGH/
        R_GATE_LOW/C_VCC2 were simply unrecognized (no alias, no board ref,
        not even listed as a known-unresolved name), on top of the same
        Q1/Q2 wrong-component collision temper_induction_cooker.yaml has.
        After extending temper_constraints.references.yaml with this
        config's own spelling of those aliases, 14 remain broken -- all
        with a documented reason (Q1/Q2 wrong-component; R_SNUB/C_SNUB
        wrong-circuit; C_VCC1 no real counterpart). This test pins that
        reduced-but-still-broken state so it fails loudly the day any of
        it changes -- at which point update this test (and, if ALL 14
        clear, remove the CI step's continue-on-error)."""
        config = REPO_ROOT / "packages/temper-placer/configs/constraints/thermal_management.yaml"
        board = REPO_ROOT / "pcb/temper.kicad_pcb"
        refs = REPO_ROOT / "packages/temper-placer/configs/temper_constraints.references.yaml"
        state, report = run(config, board, refs)
        assert state == "violation"
        assert report.zones_checked == 0
        broken_names = {b.name for b in report.broken_references}
        assert broken_names == {"Q1", "Q2", "R_SNUB", "C_SNUB", "C_VCC1"}
        assert len(report.broken_references) == 14
        # These now resolve cleanly and must stay resolved:
        resolved_ok = {"U_RTD", "U_MCU", "TH_HEATSINK", "R_GATE_HIGH", "C_VCC2", "C_BUS1", "C_BUS2"}
        assert not (resolved_ok & broken_names)
