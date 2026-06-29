"""Regression tests for strip_routing consolidation (Track A).

Validates that the canonical strip_routing() in kicad_writer.py:
1. Idempotence: produces outputs with empty traceItems (no segments, vias, arcs).
2. Content preservation: preserves footprints and nets.
3. Repo-state guard: no scripts/strip_routing*.py files remain tracked.

Runs the actual strip_routing via subprocess to avoid the temper_placer.io
__init__ import chain (JAX/flax incompatibility with Python >= 3.13).
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _run_strip_script(script: str, timeout: int = 60) -> subprocess.CompletedProcess:
    env = {
        "PYTHONPATH": str(REPO_ROOT / "packages" / "temper-placer" / "src"),
    }
    return subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=timeout,
        env=env,
    )


class TestStripRoutingIdempotence:
    """Test that strip_routing produces empty traceItems."""

    def test_minimal_board_strips_all_routing(self, tmp_path: Path):
        input_pcb = FIXTURES_DIR / "minimal_board.kicad_pcb"
        output_pcb = tmp_path / "minimal_unrouted.kicad_pcb"

        script = (
            "from temper_placer.io.kicad_writer import strip_routing\n"
            "from pathlib import Path\n"
            f"result = strip_routing(Path('{input_pcb}'), Path('{output_pcb}'),"
            " keep_zones=True, keep_fills=False)\n"
            "from kiutils.board import Board as KiBoard\n"
            f"board = KiBoard.from_file('{output_pcb}')\n"
            "ti = board.traceItems or []\n"
            "segs = sum(1 for t in ti if type(t).__name__ == 'Segment')\n"
            "vias = sum(1 for t in ti if type(t).__name__ == 'Via')\n"
            "arcs = sum(1 for t in ti if type(t).__name__ == 'Arc')\n"
            "assert segs == 0, f'segments={segs}'\n"
            "assert vias == 0, f'vias={vias}'\n"
            "assert arcs == 0, f'arcs={arcs}'\n"
            f"assert result.traces_removed >= 0\n"
            f"assert result.components_preserved > 0\n"
            "print('OK')\n"
        )
        result = _run_strip_script(script)
        assert result.returncode == 0, f"FAIL: {result.stderr}"

    def test_medium_board_strips_all_routing(self, tmp_path: Path):
        input_pcb = FIXTURES_DIR / "medium_board.kicad_pcb"
        output_pcb = tmp_path / "medium_unrouted.kicad_pcb"

        script = (
            "from temper_placer.io.kicad_writer import strip_routing\n"
            "from pathlib import Path\n"
            f"result = strip_routing(Path('{input_pcb}'), Path('{output_pcb}'),"
            " keep_zones=True, keep_fills=False)\n"
            "from kiutils.board import Board as KiBoard\n"
            f"board = KiBoard.from_file('{output_pcb}')\n"
            "ti = board.traceItems or []\n"
            "segs = sum(1 for t in ti if type(t).__name__ == 'Segment')\n"
            "vias = sum(1 for t in ti if type(t).__name__ == 'Via')\n"
            "arcs = sum(1 for t in ti if type(t).__name__ == 'Arc')\n"
            "assert segs == 0, f'segments={segs}'\n"
            "assert vias == 0, f'vias={vias}'\n"
            "assert arcs == 0, f'arcs={arcs}'\n"
            f"assert result.components_preserved > 0\n"
            "print('OK')\n"
        )
        result = _run_strip_script(script)
        assert result.returncode == 0, f"FAIL: {result.stderr}"


class TestStripRoutingContentPreservation:
    """Test that strip_routing preserves non-routing content."""

    def test_footprints_preserved(self, tmp_path: Path):
        input_pcb = FIXTURES_DIR / "minimal_board.kicad_pcb"
        output_pcb = tmp_path / "minimal_stripped.kicad_pcb"

        script = (
            "from kiutils.board import Board as KiBoard\n"
            f"original = KiBoard.from_file('{input_pcb}')\n"
            "orig_count = len(original.footprints)\n"
            "from temper_placer.io.kicad_writer import strip_routing\n"
            "from pathlib import Path\n"
            f"strip_routing(Path('{input_pcb}'), Path('{output_pcb}'),"
            " keep_zones=True, keep_fills=False)\n"
            f"stripped = KiBoard.from_file('{output_pcb}')\n"
            "strip_count = len(stripped.footprints)\n"
            "assert orig_count == strip_count, f'{orig_count} != {strip_count}'\n"
            "orig_refs = [fp.properties.get('Reference', fp.entryName) for fp in original.footprints]\n"
            "strip_refs = [fp.properties.get('Reference', fp.entryName) for fp in stripped.footprints]\n"
            "assert orig_refs == strip_refs, f'{orig_refs} != {strip_refs}'\n"
            "print('OK')\n"
        )
        result = _run_strip_script(script)
        assert result.returncode == 0, f"FAIL: {result.stderr}"

    def test_net_definitions_preserved(self, tmp_path: Path):
        input_pcb = FIXTURES_DIR / "medium_board.kicad_pcb"
        output_pcb = tmp_path / "medium_stripped.kicad_pcb"

        script = (
            "from kiutils.board import Board as KiBoard\n"
            f"original = KiBoard.from_file('{input_pcb}')\n"
            "orig_nets = [str(n) for n in (original.nets or [])]\n"
            "from temper_placer.io.kicad_writer import strip_routing\n"
            "from pathlib import Path\n"
            f"strip_routing(Path('{input_pcb}'), Path('{output_pcb}'),"
            " keep_zones=True, keep_fills=False)\n"
            f"stripped = KiBoard.from_file('{output_pcb}')\n"
            "strip_nets = [str(n) for n in (stripped.nets or [])]\n"
            "assert len(orig_nets) == len(strip_nets), f'{len(orig_nets)} != {len(strip_nets)}'\n"
            "for net in orig_nets:\n"
            "    assert net in strip_nets, f'Missing net: {net}'\n"
            "print('OK')\n"
        )
        result = _run_strip_script(script)
        assert result.returncode == 0, f"FAIL: {result.stderr}"


class TestRepoStateGuard:
    """Verify no scripts/strip_routing*.py files are tracked."""

    def test_no_strip_routing_scripts_tracked(self):
        result = subprocess.run(
            ["git", "ls-files", "scripts/strip_routing.py",
             "scripts/strip_routing_v2.py", "scripts/strip_routing_kiutils.py"],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
        assert result.stdout.strip() == "", (
            f"Tracked strip_routing scripts found:\n{result.stdout}"
        )
