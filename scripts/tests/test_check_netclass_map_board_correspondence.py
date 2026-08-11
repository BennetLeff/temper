"""Tests for check_netclass_map_board_correspondence.py.

Builds small, synthetic board/config-directory fixtures on disk
(``tmp_path``) rather than depending on the real config files for every
scenario. ``TestRealRepoIntegration`` exercises the real repo and
documents the CURRENT (broken, as surveyed 2026-08-11) state of all four
discovered files. See docs/evidence/2026-08-11-correspondence-gates.md.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_netclass_map_board_correspondence import (  # noqa: E402
    EXIT_VIOLATION,
    discover_netclass_map_files,
    load_real_net_names,
    run,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))
    return path


def _board_text(net_names: list[str]) -> str:
    nets = "\n".join(f'  (net {i + 1} "{name}")' for i, name in enumerate(net_names))
    return f'(kicad_pcb (version 1)\n  (net 0 "")\n{nets}\n)\n'


# ---------------------------------------------------------------------------
# 1. Mutations
# ---------------------------------------------------------------------------


class TestMutations:
    def test_stale_key_is_broken(self, tmp_path):
        """The +340V_BUS shape: a name elec/domain_manifest.yaml itself
        documents as renamed, still used as a net_classes key."""
        board = _write(tmp_path / "board.kicad_pcb", _board_text(["+170V_BUS", "DC_BUS_RTN"]))
        cfg_dir = tmp_path / "configs"
        _write(
            cfg_dir / "prod.yaml",
            """
            net_classes:
              "+340V_BUS": "HighVoltage"
              DC_BUS_RTN: "HighVoltage"
            """,
        )
        state, report = run(board, (cfg_dir,))
        assert state == "violation"
        assert len(report.broken_keys) == 1
        assert report.broken_keys[0].net_name == "+340V_BUS"

    def test_case_mismatch_key_is_broken(self, tmp_path):
        """The AC_L/ac_l shape: uppercase key, real net is lowercase."""
        board = _write(tmp_path / "board.kicad_pcb", _board_text(["ac_l", "ac_n"]))
        cfg_dir = tmp_path / "configs"
        _write(cfg_dir / "det.yaml", 'net_classes:\n  AC_L: "HighVoltage"\n  AC_N: "HighVoltage"\n')
        state, report = run(board, (cfg_dir,))
        assert state == "violation"
        assert {b.net_name for b in report.broken_keys} == {"AC_L", "AC_N"}

    def test_matching_keys_are_clean(self, tmp_path):
        board = _write(tmp_path / "board.kicad_pcb", _board_text(["ac_l", "ac_n", "GATE_HS"]))
        cfg_dir = tmp_path / "configs"
        _write(
            cfg_dir / "ok.yaml",
            'net_classes:\n  ac_l: "HighVoltage"\n  ac_n: "HighVoltage"\n  GATE_HS: "GateDrive"\n',
        )
        state, report = run(board, (cfg_dir,))
        assert state == "clean"
        assert report.broken_keys == []

    def test_multiple_files_are_all_scanned_and_broken_keys_attributed_correctly(self, tmp_path):
        board = _write(tmp_path / "board.kicad_pcb", _board_text(["ac_l"]))
        cfg_dir = tmp_path / "configs"
        _write(cfg_dir / "a.yaml", 'net_classes:\n  ac_l: "HighVoltage"\n  GHOST_A: "Signal"\n')
        _write(cfg_dir / "b.yaml", 'net_classes:\n  GHOST_B: "Signal"\n')
        state, report = run(board, (cfg_dir,))
        assert state == "violation"
        names = {b.net_name for b in report.broken_keys}
        assert names == {"GHOST_A", "GHOST_B"}
        assert report.keys_checked == 3

    def test_nested_list_shaped_net_classes_key_is_not_a_false_positive(self, tmp_path):
        """Some files also have a per-rule 'net_classes: [\"ACMains\"]'
        list field nested under a different top-level key -- that must
        never be confused with the top-level {str: str} mapping this
        gate checks."""
        cfg_dir = tmp_path / "configs"
        _write(
            cfg_dir / "nested.yaml",
            """
            escape_rules:
              - net_classes: ["ACMains"]
                clearance_mm: 0.4
            """,
        )
        candidates = discover_netclass_map_files((cfg_dir,))
        assert candidates == []


# ---------------------------------------------------------------------------
# 2. Anti-vacuity
# ---------------------------------------------------------------------------


class TestAntiVacuity:
    def test_missing_board(self, tmp_path):
        cfg_dir = tmp_path / "configs"
        _write(cfg_dir / "a.yaml", 'net_classes:\n  ac_l: "HighVoltage"\n')
        state, report = run(tmp_path / "nope.kicad_pcb", (cfg_dir,))
        assert state == "tool_error"

    def test_board_with_no_nets(self, tmp_path):
        board = _write(tmp_path / "board.kicad_pcb", "(kicad_pcb (version 1))\n")
        cfg_dir = tmp_path / "configs"
        _write(cfg_dir / "a.yaml", 'net_classes:\n  ac_l: "HighVoltage"\n')
        state, report = run(board, (cfg_dir,))
        assert state == "tool_error"

    def test_zero_candidate_files_is_tool_error(self, tmp_path):
        board = _write(tmp_path / "board.kicad_pcb", _board_text(["ac_l"]))
        cfg_dir = tmp_path / "configs"
        _write(cfg_dir / "irrelevant.yaml", "board_width_mm: 100\n")
        state, report = run(board, (cfg_dir,))
        assert state == "tool_error"

    def test_malformed_yaml_candidate_fails_closed(self, tmp_path):
        board = _write(tmp_path / "board.kicad_pcb", _board_text(["ac_l"]))
        cfg_dir = tmp_path / "configs"
        _write(cfg_dir / "broken.yaml", "net_classes: [unterminated\n")
        state, report = run(board, (cfg_dir,))
        assert state == "tool_error"

    def test_missing_config_dir_is_skipped_not_errored(self, tmp_path):
        """A config dir that doesn't exist at all (e.g. optional second
        dir) is tolerated -- only a TOTAL absence of candidates across
        all given dirs is a tool error."""
        board = _write(tmp_path / "board.kicad_pcb", _board_text(["ac_l"]))
        cfg_dir = tmp_path / "configs"
        _write(cfg_dir / "a.yaml", 'net_classes:\n  ac_l: "HighVoltage"\n')
        state, report = run(board, (cfg_dir, tmp_path / "does_not_exist"))
        assert state == "clean"


# ---------------------------------------------------------------------------
# 3. Helper units
# ---------------------------------------------------------------------------


class TestHelperUnits:
    def test_load_real_net_names(self, tmp_path):
        board = _write(tmp_path / "board.kicad_pcb", _board_text(["ac_l", "ac_n"]))
        names = load_real_net_names(board)
        assert names == {"ac_l", "ac_n"}

    def test_discover_finds_only_dict_shaped_top_level_net_classes(self, tmp_path):
        cfg_dir = tmp_path / "configs"
        _write(cfg_dir / "good.yaml", 'net_classes:\n  ac_l: "HighVoltage"\n')
        _write(cfg_dir / "list_shaped.yaml", "net_classes:\n  - ACMains\n")
        _write(cfg_dir / "no_key.yaml", "board_width_mm: 100\n")
        found = discover_netclass_map_files((cfg_dir,))
        assert [p.name for p in found] == ["good.yaml"]


# ---------------------------------------------------------------------------
# 4. Real-repo integration -- documents the CURRENT (broken) state
# ---------------------------------------------------------------------------


class TestRealRepoIntegration:
    def test_real_repo_currently_violates(self):
        """As surveyed 2026-08-11: four files (configs/temper_deterministic_config.yaml,
        configs/temper_production_config.yaml, packages/temper-placer/configs/
        temper_constraints.yaml, packages/temper-placer/configs/gate_driver_constraints.yaml)
        each have at least one net_classes key that matches no real board
        net. Update this test (and consider un-advisory-ing the CI step)
        once they're fixed -- see docs/evidence/2026-08-11-correspondence-gates.md."""
        state, report = run(REPO_ROOT / "pcb" / "temper.kicad_pcb")
        assert state == "violation"
        broken_files = {Path(b.config_path).name for b in report.broken_keys}
        assert broken_files == {
            "temper_deterministic_config.yaml",
            "temper_production_config.yaml",
            "temper_constraints.yaml",
            "gate_driver_constraints.yaml",
        }
        assert len(report.files_checked) == 4

    def test_real_repo_gate_exits_violation_not_error(self):
        import subprocess

        result = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts/check_netclass_map_board_correspondence.py")],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        assert result.returncode == EXIT_VIOLATION, result.stdout + result.stderr
