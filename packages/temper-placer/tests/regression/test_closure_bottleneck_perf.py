"""
Performance gate tests for the closure test under U2's per-failed-net
min-cut work (SC4 / Open Question [Deferred: max node count]).

SC4: full closure test on the Temper PCB must complete within
``210s`` (180s baseline + 30s budget for U2's per-failed-net work).

Open Question [Deferred: max node count]: a 200x200mm board at
0.5mm cell size produces ~160K cells. The per-net ``BOTTLENECK_TIMEOUT_S``
must abort the analysis rather than raise, so the closure test
overall pass/fail result is not affected by very large boards.

These tests are slow and are marked with ``pytest.mark.slow`` so
they can be deselected with ``-m 'not slow'``. They are also
guarded with ``pytest.importorskip`` for any optional dependencies
so the rest of the suite can run on a minimal install.
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from temper_placer.router_v6.bottleneck_geometry import BOTTLENECK_TIMEOUT_S

pytestmark = pytest.mark.slow


# ---------------------------------------------------------------------------
# SC4: full closure test on the Temper PCB within 210s
# ---------------------------------------------------------------------------


def test_temper_pcb_within_budget() -> None:
    """Run the closure test on the Temper PCB and assert wall-clock ≤ 210s.

    SC4 budget math: 180s baseline + 30s for U2's per-failed-net work
    (60 nets × 0.5s = 30s, well under the 30s allocated). If a future
    corpus has more than 60 failed nets, this test should not assert
    SC4 wall-clock and should instead verify only the per-net timeout
    behavior via ``test_large_node_count_falls_back`` (see plan §
    "Performance risk (R6)").

    The test is conditional on the Temper PCB existing; if the file is
    not present (e.g. CI without the corpus), the test is skipped.
    """
    pytest.importorskip("temper_placer.io.kicad_parser", reason="kicad_parser not available")

    from pathlib import Path

    from temper_placer.regression.closure_test import ClosureTest

    pcb_candidates = [
        Path("pcb/temper.kicad_pcb"),
        Path("power_pcb_dataset/boards/temper.kicad_pcb"),
    ]
    pcb_path = next((p for p in pcb_candidates if p.is_file()), None)
    if pcb_path is None:
        pytest.skip("Temper PCB not available in this checkout")

    test = ClosureTest(pcb_path=pcb_path, seed={"benders_seed": 42, "router_seed": 42})
    start = time.perf_counter()
    result = test.run()
    elapsed = time.perf_counter() - start

    assert elapsed <= 210.0, f"closure test took {elapsed:.1f}s, budget 210s"
    # Closure result must still be returned (not crashed) — pass/fail is
    # independent of the timing assertion.
    assert result is not None


# ---------------------------------------------------------------------------
# Open Question [Deferred: max node count]: large boards abort cleanly
# ---------------------------------------------------------------------------


def test_large_node_count_falls_back() -> None:
    """A board > 200x200mm at 0.5mm must either complete within
    ``BOTTLENECK_TIMEOUT_S`` or set ``bottleneck_status='aborted_timeout'``,
    never raise.

    The test stubs the protocol runner to return a routing result whose
    net reports carry a BottleneckGeometry in the aborted state, then
    asserts the closure test does not crash.
    """
    from temper_placer.regression.closure_test import ClosureTest
    from temper_placer.router_v6.bottleneck_geometry import (
        BOTTLENECK_TIMEOUT_S as _BOTTLENECK_TIMEOUT_S,
    )
    from temper_placer.router_v6.bottleneck_geometry import (
        BottleneckGeometry,
    )
    from temper_placer.router_v6.diagnostics import (
        FailureReason,
        NetRoutingReport,
        RoutingStatus,
    )

    assert BOTTLENECK_TIMEOUT_S == 0.5  # SC4: 0.5s per failed net
    assert _BOTTLENECK_TIMEOUT_S == BOTTLENECK_TIMEOUT_S

    aborted = BottleneckGeometry(
        component_pair=("Q1", "D1"),
        pair_kind="component_component",
        positions_mm=((0.0, 0.0), (0.0, 0.0)),
        current_gap_mm=0.0,
        required_gap_mm=0.0,
        cut_size=0,
        cut_cells=(),
        message="aborted_timeout",
        bottleneck_status="aborted_timeout",
    )
    report = NetRoutingReport(
        net_name="GATE_H",
        status=RoutingStatus.FAILED,
        score=0.0,
        pins=2,
        routed_segments=0,
        total_segments=1,
        failure_reason=FailureReason.CHANNEL_CAPACITY,
        bottleneck=aborted,
    )
    from types import SimpleNamespace

    data = SimpleNamespace(completion_rate=0.5, net_reports=[report])
    routing_result = SimpleNamespace(data=data)

    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        from pathlib import Path

        pcb_path = Path(tmpdir) / "big.kicad_pcb"
        pcb_path.write_text("(kicad_pcb)")

        with patch(
            "temper_placer.io.kicad_parser.parse_kicad_pcb_v6",
            return_value={},
        ), patch(
            "temper_placer.runner.resolve_and_run",
            return_value=routing_result,
        ):
            test = ClosureTest(pcb_path=pcb_path)
            # Must not raise even when the bottleneck analysis aborted.
            result = test.run()

    assert result is not None
    assert result.routing_failure_messages == ["aborted_timeout"]
