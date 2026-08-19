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

from temper_placer.router_v6.net_classification import (
    is_ground_net,
    is_power_net,
)
from temper_placer.router_v6.pipeline import RouterV6Pipeline


def test_r1_plane_nets_set_includes_ground_and_vcc():
    """Canonical net classification recognizes GND and VCC as plane nets.

    Confirms the canonical helpers (the source of truth for the
    completion_rate derivation in pipeline.py) classify the most common
    ground and power net names correctly. If these helpers regress,
    R1 cannot lift SM1 on the canonical temper board.
    """
    assert is_ground_net("GND"), (
        "is_ground_net('GND') must be True. R1 depends on GND being "
        "recognized as a ground net so it counts in completion_rate."
    )
    assert is_power_net("VCC"), (
        "is_power_net('VCC') must be True. R1 depends on VCC being recognized as a power net."
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


def test_r3_channel_skeleton_covers_all_routable_layers():
    """ChannelSkeletonStage builds skeletons for every routable layer.

    R3's original F.Cu/B.Cu hardcode was corrected by the plane-condemnation
    fix (2026-08-07 router-silent-noop-diagnosis "Bug B"): RoutingSpaceStage
    (routing_space.py:85) already restricts ``routing_spaces`` to routable
    layers, so filtering again here to two literal layer names silently
    dropped every other routable layer (e.g. a 4-layer stackup's inner
    layers) from ever getting a channel skeleton -- leaving
    ``state.channel_skeletons == {}`` even with a non-empty routing space.
    The corrected stage iterates the routing spaces it is given.
    """
    import inspect

    from temper_placer.router_v6.channel_skeleton import ChannelSkeletonStage

    source = inspect.getsource(ChannelSkeletonStage.run)
    # The stage must not re-filter to the two literal outer-layer names:
    # that hardcode is the bug the fix removed.
    assert '"F.Cu"' not in source and '"B.Cu"' not in source, (
        "ChannelSkeletonStage.run must not hardcode an F.Cu/B.Cu filter -- "
        "routing_spaces is already restricted to routable layers by "
        "RoutingSpaceStage; re-filtering here drops inner routable layers."
    )
    # Defensive: the loop must iterate the routing spaces, not a literal list.
    assert "routing_spaces.items()" in source, (
        "ChannelSkeletonStage.run must iterate routing_spaces (the routable-"
        "layer-restricted set), not a hardcoded layer-name list."
    )


# ---------------------------------------------------------------------------
# The any-angle divergence between entry points (measured 2026-08-18)
# ---------------------------------------------------------------------------


def test_entry_points_disagree_on_any_angle_search_and_that_is_pinned():
    """``route_pcb`` and ``RouterV6Pipeline()`` resolve DIFFERENT searches.

    This is a real, load-bearing divergence, pinned here rather than
    "reconciled" -- because it was reconciled in the wrong direction once
    already, on a stale note, before it was re-measured.

    Measured 2026-08-18 by routing ``pcb/temper.kicad_pcb`` through
    ``RouterV6Pipeline`` twice from identical stripped input, once per
    setting (deterministic -- the False arm reproduced bit-identically
    across two independent runs):

    ===========  =============  ===============  ========  ====
    flags        pad-connected  fake-completion  segments  vias
    ===========  =============  ===============  ========  ====
    both False       61/139            0           4500     52
    both True        94/139            4           3260     72
    ===========  =============  ===============  ========  ====

    Pad connectivity is the PRIMARY metric (see
    ``scripts/route_board.audit_pad_connectivity``: a net "carrying
    copper" is not a net whose copper reaches all of its own pads). The
    any-angle setting lands **+33 genuinely pad-connected nets on fewer
    segments**; even discounting all four fake-completions it is 90 vs 61.

    That REFUTES the ``NOTE 2026-06-23`` verdict in
    ``_adapter_convert.route_pcb`` ("plain theta star ... finds fewer nets
    than plain A* (Rust)"), whose two premises have both expired --
    Theta*/Lazy Theta* are Rust-backed since Wave 4, and
    ``_dispatch_search`` does pass ``max_iter``. It was also measured on a
    24-net smoke subset, not today's 139-net 6-layer board.

    So neither side is simply misconfigured, and neither is changed here:

    * Flipping ``route_pcb`` to True would change the committed routed
      board (sha256 ``6d4e1733...``) -- a board-level decision needing its
      own DRC/creepage review on a mains-voltage design.
    * Flipping the constructor to False would make every no-arg caller
      route the configuration that measures WORSE.

    What is fixed is that the divergence is no longer silent:
    ``_pipeline_route._resolve_any_angle_search`` names and logs the
    resolved search once per route. This test is the static half of that.
    Change either side deliberately, with a fresh measurement, and update
    the table above -- do not "make them agree" on the strength of prose.
    """
    import ast
    import inspect
    from pathlib import Path

    from temper_placer.adapters import router_v6_stage_adapter
    from temper_placer.router_v6 import _adapter_convert

    def _any_angle_kwargs(module) -> list[dict[str, object]]:
        tree = ast.parse(Path(inspect.getfile(module)).read_text(encoding="utf-8"))
        out = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name != "RouterV6Pipeline":
                continue
            out.append(
                {
                    kw.arg: kw.value.value
                    for kw in node.keywords
                    if kw.arg in ("enable_theta_star", "enable_lazy_theta_star")
                    and isinstance(kw.value, ast.Constant)
                }
            )
        return out

    # Side A -- the production entry point scripts/route_board.py drives.
    # Forced False since 2026-06-23; measures 61/139 pad-connected.
    convert_calls = _any_angle_kwargs(_adapter_convert)
    assert convert_calls, "no RouterV6Pipeline(...) call found in _adapter_convert"
    for kwargs in convert_calls:
        assert kwargs.get("enable_theta_star") is False, kwargs
        assert kwargs.get("enable_lazy_theta_star") is False, kwargs

    # Side B -- the no-arg constructor default, and the three
    # `router_v6_full` stage adapters that runner.run_with_fallback
    # prefers over the route_pcb-backed stage. Both True; measures 94/139.
    pipeline = RouterV6Pipeline()
    assert pipeline.enable_theta_star is True
    assert pipeline.enable_lazy_theta_star is True

    adapter_calls = _any_angle_kwargs(router_v6_stage_adapter)
    assert len(adapter_calls) == 3, adapter_calls
    for kwargs in adapter_calls:
        assert kwargs.get("enable_theta_star") is True, kwargs
        assert kwargs.get("enable_lazy_theta_star") is True, kwargs


def test_any_angle_search_decision_is_named_and_logged():
    """The resolved search is a named record, not an inferred branch.

    ``_dispatch_search`` tests ``use_lazy_theta_star`` FIRST, so with both
    flags True -- the ``RouterV6Pipeline()`` default -- ``enable_theta_star``
    is unobservable: Lazy Theta* always wins. A caller passing
    ``enable_theta_star=False`` alone (``scripts/bench_coarse_to_fine.py``
    does exactly this) therefore does NOT disable any-angle search. The
    resolver has to reproduce that precedence or the log would lie.
    """
    from temper_placer.router_v6._pipeline_route import _resolve_any_angle_search

    both_on = _resolve_any_angle_search(True, True, False, 0.0)
    assert both_on.mode == "lazy_theta_star"
    assert "preempts" in both_on.reason, (
        "with both flags True the resolver must say enable_theta_star was "
        "preempted -- that precedence is the whole reason the flag reads as "
        "a switch it is not."
    )

    theta_only = _resolve_any_angle_search(True, False, False, 0.0)
    assert theta_only.mode == "theta_star"

    off = _resolve_any_angle_search(False, False, True, 1.0)
    assert off.mode == "plain_2d_astar"
    assert off.dropped_inputs == (), "the plain arm drops nothing"

    # The any-angle arms silently drop cost inputs the plain arm receives.
    dropping = _resolve_any_angle_search(False, True, True, 1.0)
    assert "thermal_flat/thermal_weight" in dropping.dropped_inputs
    assert "congestion_tensor" in dropping.dropped_inputs
