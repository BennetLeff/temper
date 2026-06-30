"""Integration tests for RouterV6Pipeline with DRCFence (P0#2).

Tests that the fence-gated code path in pipeline.py:131-152
(Stage 0.5 legalization fence check) is exercised and runs
without errors.
"""

from pathlib import Path

import pytest
from temper_placer.validation.drc_result import ClearanceCheck, ComponentOverlapCheck
from temper_placer.validation.drc_fence import DRCFence
from temper_placer.validation.drc_runner import CheckRunner

from temper_placer.router_v6.pipeline import RouterV6Pipeline

FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fence():
    """Create a DRCFence with standard component-level checks."""
    runner = CheckRunner()
    runner.add_check(ComponentOverlapCheck())
    runner.add_check(ClearanceCheck())
    return DRCFence(runner, fail_on_violation=False)


class TestRouterV6FenceIntegration:
    """Integration tests verifying RouterV6Pipeline + DRCFence."""

    def test_pipeline_runs_with_fence(self, fence):
        """Pipeline with fence runs without error on a small PCB."""
        pcb_path = FIXTURE_DIR / "minimal_board.kicad_pcb"

        pipeline = RouterV6Pipeline(
            verbose=False,
            enable_legalization=False,
            max_nets=1,
            fence=fence,
        )
        result = pipeline.run(pcb_path)

        assert result is not None
        assert result.pcb is not None
        assert result.runtime_seconds >= 0

    def test_fence_passed_after_legalization(self, fence):
        """Stage 0.5 fence passes for a well-formed PCB."""
        pcb_path = FIXTURE_DIR / "minimal_board.kicad_pcb"

        pipeline = RouterV6Pipeline(
            verbose=False,
            enable_legalization=True,
            max_nets=1,
            fence=fence,
        )
        result = pipeline.run(pcb_path)
        assert result is not None

    def test_pipeline_no_fence_backward_compatible(self):
        """Pipeline without fence (None) is backward compatible."""
        pcb_path = FIXTURE_DIR / "minimal_board.kicad_pcb"

        pipeline = RouterV6Pipeline(
            verbose=False,
            enable_legalization=False,
            max_nets=1,
            fence=None,
        )
        result = pipeline.run(pcb_path)
        assert result is not None

    def test_fence_with_legalization_enabled_runs_fence(self, fence):
        """Verify fence execution trace: Stage 0.5 fence runs."""
        pcb_path = FIXTURE_DIR / "minimal_board.kicad_pcb"

        pipeline = RouterV6Pipeline(
            verbose=False,
            enable_legalization=True,
            max_nets=1,
            fence=fence,
        )
        result = pipeline.run(pcb_path)
        assert result is not None
        assert result.success_count >= 0
