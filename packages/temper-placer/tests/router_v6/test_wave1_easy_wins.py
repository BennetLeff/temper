"""
Wave 1 PR — Easy Wins

Verifies the three "easy win" requirements from the closure-rate
rollout plan (``docs/plans/2026-06-23-009-feat-router-v6-closure-rate-90-percent-plan.md``).

R1: Plane nets (GND, VCC, etc.) are counted in ``completion_rate``
    (not filtered out by ``should_route``).
R2: ``RouterV6Pipeline`` defaults ``enable_theta_star=True`` (any-angle
    A*). Smoothing stays default ``False`` (broken path deferred).
R3: Channel skeleton extraction is restricted to F.Cu and B.Cu
    (the outer signal layers) for the production pipeline path.
"""
from __future__ import annotations

from temper_placer.router_v6.pipeline import RouterV6Pipeline
from temper_placer.router_v6.routing_space import PLANE_NETS


def test_r1_plane_nets_set_includes_ground_and_vcc():
    """PLANE_NETS contains the canonical ground and power net names.

    Confirms the source-of-truth set the completion_rate derivation
    reads from. If this set is empty or missing GND/VCC, R1 cannot
    lift SM1 on the canonical temper board.
    """
    assert "GND" in PLANE_NETS, (
        f"PLANE_NETS missing GND: {PLANE_NETS}. R1 depends on GND/VCC "
        f"being recognized as plane nets so they count in completion_rate."
    )
    assert "VCC" in PLANE_NETS, (
        f"PLANE_NETS missing VCC: {PLANE_NETS}. R1 depends on VCC being "
        f"recognized as a plane net."
    )


def test_r2_router_v6_pipeline_default_enables_theta_star():
    """RouterV6Pipeline() with no args has enable_theta_star=True.

    Confirms the Wave 1 PR flipped the constructor default. Callers
    that need the old behavior can still pass ``enable_theta_star=False``
    explicitly.
    """
    pipeline = RouterV6Pipeline()
    assert pipeline.enable_theta_star is True, (
        "RouterV6Pipeline() should default enable_theta_star=True "
        "(Wave 1 PR). Callers needing the old behavior pass False explicitly."
    )


def test_r2_smoothing_stays_default_false():
    """enable_smoothing stays default False; the path is broken.

    The smoothing path at ``router_v6/pipeline.py`` references
    ``SDFGrid.from_polygons`` which does not exist. Enabling it
    regresses SM1. Wave 1 leaves it off; a follow-up PR fixes the
    SDF implementation.
    """
    pipeline = RouterV6Pipeline()
    assert pipeline.enable_smoothing is False, (
        "enable_smoothing must stay default False until SDFGrid.from_polygons "
        "is implemented. Enabling it now exercises broken code on every "
        "closure test run."
    )


def test_r2_theta_star_can_still_be_disabled_explicitly():
    """Explicit False override still works; no regression for callers."""
    pipeline = RouterV6Pipeline(enable_theta_star=False)
    assert pipeline.enable_theta_star is False


def test_r3_channel_skeleton_filters_to_outer_layers():
    """ChannelSkeletonStage only extracts skeletons for F.Cu and B.Cu.

    Per R3: inner layers (In1.Cu, In2.Cu, etc.) are reserved for power
    ground planes; the channel skeleton graph is too sparse to be
    useful on those layers and adds SAT model bloat. Confirm the
    filter in ``ChannelSkeletonStage.run`` at
    ``router_v6/channel_skeleton.py:411`` still excludes inner layers.
    """
    import inspect
    from temper_placer.router_v6.channel_skeleton import ChannelSkeletonStage

    source = inspect.getsource(ChannelSkeletonStage.run)
    assert '"F.Cu"' in source and '"B.Cu"' in source, (
        "ChannelSkeletonStage.run must explicitly filter to F.Cu and "
        "B.Cu in its outer_layers dict comprehension. R3 depends on this."
    )
    # Defensive: ensure no inner layer names appear in the filter list
    for inner in ("In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu"):
        assert inner not in source.replace('"', "").replace("'", ""), (
            f"Inner layer {inner} should not appear in "
            f"ChannelSkeletonStage.run's outer-layer filter."
        )
