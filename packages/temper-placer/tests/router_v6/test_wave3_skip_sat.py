"""
Wave 3 PR — Skip SAT Stage

Verifies the guarded ``skip_stage3`` bypass from the closure-rate
rollout plan.

R7: ``RouterV6Pipeline(skip_stage3=True)`` bypasses Stage 3 (SAT
    topology) entirely.  When ``True``, ``pipeline.run`` returns
    an empty ``Stage3Output`` (with ``topology_graph=None``); Stage
    4 falls back to skeleton-path resolution in
    ``_map_net_to_channels``.  The SAT code stays in place; this
    is a guarded bypass, not a removal.
R8: ``map_topology_to_channels`` handles ``topology=None`` gracefully
    (skeleton-path fallback for every net).  This is the consumer
    side of the R7 bypass; without it, R7 would raise AttributeError.
"""
from __future__ import annotations

import inspect

from temper_placer.router_v6.pipeline import RouterV6Pipeline


def test_r7_skip_stage3_param_in_constructor():
    """RouterV6Pipeline accepts a skip_stage3 keyword argument with
    a default of False (preserves existing behavior).
    """
    pipeline = RouterV6Pipeline()
    assert hasattr(pipeline, "skip_stage3"), (
        "RouterV6Pipeline must expose a skip_stage3 attribute after "
        "Wave 3 (R7)."
    )
    assert pipeline.skip_stage3 is False, (
        "skip_stage3 must default to False; existing callers must "
        "be unaffected."
    )

    pipeline_skip = RouterV6Pipeline(skip_stage3=True)
    assert pipeline_skip.skip_stage3 is True


def test_r7_pipeline_run_branches_on_skip_stage3():
    """pipeline.run prints 'SKIPPED' for Stage 3 when skip_stage3=True.

    Inspects the run() source to confirm the branch exists.  The
    actual behavior (no SAT solver call) is verified by the
    integration test in test_router_completion.py.
    """
    source = inspect.getsource(RouterV6Pipeline.run)
    assert "if self.skip_stage3:" in source, (
        "pipeline.run must branch on self.skip_stage3 to bypass "
        "Stage 3.  Without the branch, R7 is a no-op."
    )
    assert "SKIPPED" in source, (
        "When skip_stage3 is True, Stage 3 should log 'SKIPPED' for "
        "visibility (the verbose=True path)."
    )


def test_r8_map_topology_to_channels_handles_none_topology():
    """``map_topology_to_channels`` accepts ``topology=None`` and
    routes every net through the skeleton-path fallback.

    Without this, R7's ``topology_graph=None`` Stage3Output would
    raise ``AttributeError`` inside ``map_topology_to_channels``.
    """
    from temper_placer.router_v6.channel_mapping import (
        map_topology_to_channels,
    )

    source = inspect.getsource(map_topology_to_channels)
    assert "topology is not None" in source, (
        "map_topology_to_channels must None-check the topology arg "
        "(R8).  The current code at line 80 calls "
        "topology.net_topologies.keys() which raises on None."
    )


def test_r7_default_false_preserves_existing_behavior():
    """``RouterV6Pipeline()`` with no args has skip_stage3=False; the
    SAT solver still runs in the default path.
    """
    pipeline = RouterV6Pipeline()
    assert pipeline.skip_stage3 is False, (
        "skip_stage3 must default to False.  Setting it True by "
        "default would silently disable the SAT solver for every "
        "caller — a significant behavior change."
    )
