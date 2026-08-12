"""Tests for check_corpus_fixture_realboard_divergence.py.

Synthetic manifest/board fixtures on disk (``tmp_path``), matching the
sibling correspondence gates' convention (see
test_check_pcl_config_board_correspondence.py's own module docstring) of a
controlled minimal reproduction per behavior rather than depending on the
real corpus for every scenario. ``TestRealRepoIntegration`` exercises the
real repo manifest and documents the CURRENT (declared-independent,
2026-08-11) state.
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_corpus_fixture_realboard_divergence import (  # noqa: E402
    ROLE_INDEPENDENT,
    ROLE_SNAPSHOT,
    run,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text))
    return path


def _board_text(n_components: int, outline: tuple[float, float, float, float]) -> str:
    x_min, y_min, x_max, y_max = outline
    footprints = "\n".join(
        f'''
  (footprint "Lib:Foo" (layer "F.Cu")
    (at 50 50 0)
    (property "Reference" "R{i}")
    (property "Value" "?")
  )'''
        for i in range(n_components)
    )
    return f"""
(kicad_pcb (version 20211014) (generator kiutils)
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


def _manifest_text(boards: list[dict]) -> str:
    import yaml

    return yaml.safe_dump({"version": 1, "boards": boards})


class TestUndeclaredRole:
    def test_real_board_path_without_role_is_gate_error(self, tmp_path):
        """A board that names a real_board_path but never commits to a
        role is exactly the 2026-08-11 incident shape: fail closed rather
        than silently skip or silently assume either reading."""
        corpus = tmp_path / "power_pcb_dataset" / "corpus"
        fixture = _write(corpus / "foo" / "foo.kicad_pcb", _board_text(5, (0, 0, 50, 50)))
        real = _write(tmp_path / "pcb" / "real.kicad_pcb", _board_text(20, (0, 0, 100, 100)))
        manifest = _write(
            tmp_path / "manifest.yaml",
            _manifest_text(
                [{"id": "foo", "pcb": "foo/foo.kicad_pcb", "real_board_path": "pcb/real.kicad_pcb"}]
            ),
        )
        state, report = run(tmp_path, manifest)
        assert state == "tool_error"
        assert report.undeclared_role_boards
        assert fixture.exists() and real.exists()  # sanity: fixtures were used


class TestSnapshotRole:
    def test_snapshot_component_count_match_is_clean(self, tmp_path):
        _write(tmp_path / "power_pcb_dataset" / "corpus" / "foo" / "foo.kicad_pcb", _board_text(20, (0, 0, 100, 100)))
        _write(tmp_path / "pcb" / "real.kicad_pcb", _board_text(20, (0, 0, 100, 100)))
        manifest = _write(
            tmp_path / "manifest.yaml",
            _manifest_text(
                [
                    {
                        "id": "foo",
                        "pcb": "foo/foo.kicad_pcb",
                        "real_board_path": "pcb/real.kicad_pcb",
                        "role": ROLE_SNAPSHOT,
                    }
                ]
            ),
        )
        state, report = run(tmp_path, manifest)
        assert state == "clean"
        assert not report.violations

    def test_snapshot_component_count_mismatch_is_a_violation(self, tmp_path):
        """The exact 2026-07-15 shape: a real-board-snapshot fixture whose
        component count silently diverged from the board it claims to
        track (33 -> 169 in the real incident)."""
        _write(tmp_path / "power_pcb_dataset" / "corpus" / "foo" / "foo.kicad_pcb", _board_text(33, (0, 0, 100, 150)))
        _write(tmp_path / "pcb" / "real.kicad_pcb", _board_text(169, (20, 20, 172, 254)))
        manifest = _write(
            tmp_path / "manifest.yaml",
            _manifest_text(
                [
                    {
                        "id": "foo",
                        "pcb": "foo/foo.kicad_pcb",
                        "real_board_path": "pcb/real.kicad_pcb",
                        "role": ROLE_SNAPSHOT,
                    }
                ]
            ),
        )
        state, report = run(tmp_path, manifest)
        assert state == "violation"
        assert len(report.violations) == 1
        assert report.violations[0].fixture.n_components == 33
        assert report.violations[0].real.n_components == 169


class TestIndependentRole:
    def test_independent_component_count_mismatch_is_informational_not_a_violation(self, tmp_path):
        """The current, deliberate ``temper`` shape (2026-08-11 decision):
        divergence is reported but never fails the gate."""
        _write(tmp_path / "power_pcb_dataset" / "corpus" / "foo" / "foo.kicad_pcb", _board_text(33, (0, 0, 100, 150)))
        _write(tmp_path / "pcb" / "real.kicad_pcb", _board_text(169, (20, 20, 172, 254)))
        manifest = _write(
            tmp_path / "manifest.yaml",
            _manifest_text(
                [
                    {
                        "id": "foo",
                        "pcb": "foo/foo.kicad_pcb",
                        "real_board_path": "pcb/real.kicad_pcb",
                        "role": ROLE_INDEPENDENT,
                    }
                ]
            ),
        )
        state, report = run(tmp_path, manifest)
        assert state == "clean"
        assert not report.violations
        assert len(report.checked) == 1
        assert report.checked[0].component_count_mismatch is True


class TestNoRealBoardPath:
    def test_board_without_real_board_path_is_skipped_entirely(self, tmp_path):
        """A board making no claim about a real-board counterpart is not
        this gate's concern -- no path, no check, no error."""
        manifest = _write(
            tmp_path / "manifest.yaml",
            _manifest_text([{"id": "standalone", "pcb": "standalone/board.kicad_pcb"}]),
        )
        state, report = run(tmp_path, manifest)
        assert state == "clean"
        assert not report.checked
        assert not report.tool_errors


class TestGateErrors:
    def test_missing_manifest_is_gate_error(self, tmp_path):
        state, report = run(tmp_path, tmp_path / "does_not_exist.yaml")
        assert state == "tool_error"
        assert report.tool_errors

    def test_missing_board_file_is_gate_error(self, tmp_path):
        manifest = _write(
            tmp_path / "manifest.yaml",
            _manifest_text(
                [
                    {
                        "id": "foo",
                        "pcb": "foo/missing.kicad_pcb",
                        "real_board_path": "pcb/missing_real.kicad_pcb",
                        "role": ROLE_SNAPSHOT,
                    }
                ]
            ),
        )
        state, report = run(tmp_path, manifest)
        assert state == "tool_error"
        assert report.tool_errors


class TestRealRepoIntegration:
    """Exercises the real repo manifest -- documents the CURRENT
    (2026-08-11 decision: role=independent-fixture) state."""

    def test_real_manifest_temper_board_is_declared_independent(self):
        import yaml

        manifest_path = REPO_ROOT / "power_pcb_dataset" / "corpus" / "manifest.yaml"
        data = yaml.safe_load(manifest_path.read_text())
        boards = {b["id"]: b for b in data["boards"]}
        assert boards["temper"]["role"] == ROLE_INDEPENDENT
        assert boards["temper"]["real_board_path"] == "pcb/temper.kicad_pcb"

    def test_real_manifest_gate_passes_clean(self):
        manifest_path = REPO_ROOT / "power_pcb_dataset" / "corpus" / "manifest.yaml"
        state, report = run(REPO_ROOT, manifest_path)
        assert state == "clean"
        assert not report.tool_errors
        assert not report.undeclared_role_boards
