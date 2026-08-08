"""
Regression falsifier for the bug fixed in commit 8abcec24 ("fix(router):
open F.Cu/B.Cu to real routing instead of the plane-condemnation
fallback").

The bug: ``_extract_stackup()`` (``io/_parse_board.py``) classifies an
entire *physical* copper layer as ``layer_type="plane"`` whenever ANY zone
on it sits on a plane-required net (``_is_plane_required_net``) -- an
existential quantifier over zones, not an area/role predicate. On
``pcb/temper.kicad_pcb``, 4 of 48 zones per outer layer are enough to
condemn all of F.Cu/B.Cu, which ``routing_space.py``'s
``compute_routing_space`` then drops from the router's routing space
entirely. That collapses ``state.channel_skeletons`` to ``{}`` and makes
``route_pcb()`` build a 0-variable/0-constraint model that silently
degrades to a per-net fallback (~37.75% completion) -- certified as
"passing" by every routing DRC baseline since 556ccf4f.

The fix for this existed since commit 20dd3533: ``_extract_stackup`` /
``parse_kicad_pcb_v6`` accept an opt-in ``use_declared_layer_roles=True``
flag under which a layer's role comes from its structural position in the
declared stackup (outer = signal, inner = mixed), never from zone content.
``packages/temper-placer/tests/router_v6/test_u2_stackup_role_ssot.py``
already covers that flag's own correctness in isolation (both "off"
today's-bug-baseline and "on" fixed behavior), on the real production
board's ``_extract_stackup``/``compute_routing_space`` call chain.

What was missing, and what actually shipped the bug end-to-end: the flag
was never threaded into ``RouterV6Pipeline.run()`` -- "the one path that
matters for routing" (route_pcb()'s real, production/CI call site). This
module is that missing falsifier: it exercises ``RouterV6Pipeline.run()``
itself (not a source-inspection assertion, and not a call to
``_extract_stackup``/``parse_kicad_pcb_v6`` directly with the flag
supplied by the test) and checks what value the flag actually carries at
the real call site.

MEASURED, both directions, as part of the branch that added this test
(see the branch's own commit history for the exact SHAs and full
transcripts):

- On ``main`` (pre-fix, commit b31fe017): route_pcb() on the *unstripped*
  ``pcb/temper.kicad_pcb`` (the board exactly as committed, real zones
  and all -- this is the scenario that actually triggers the bug, since
  the existential-zone-quantifier defect only fires when real zones are
  present in the parsed input) measures **0** total channel-skeleton
  edges, ``state.channel_skeletons == {}``. This test's
  ``test_pipeline_run_wires_declared_layer_roles_into_stage0`` FAILS on
  that commit: it captures ``use_declared_layer_roles=False`` at the real
  call site.
- On the fix branch (commit e1c06970, cherry-picking 8abcec24 onto
  ``main``): the same test PASSES, capturing
  ``use_declared_layer_roles=True``.

The wiring test below intercepts the exact call site inside
``RouterV6Pipeline.run()`` and aborts immediately after capturing the
flag value -- deliberately not exercising Stage 0.5 onward (placement
legalization, escape vias, Stage 2 channel analysis, ...), so it is fast
and deterministic regardless of which board path a future caller passes.
It is not a proxy for "does the flag work" (that is
``test_u2_stackup_role_ssot.py``'s job, already covered) -- it is a proxy
for "does the one caller that matters for production routing actually use
it", which is precisely the gap that let the bug ship for 100+ commits
before compressed 8abcec24 fixed the wiring specifically.
"""

from __future__ import annotations

from pathlib import Path

import pytest


class _StoppedAfterParseCapture(Exception):
    """Raised by the parse_kicad_pcb_v6 spy the instant it is called, so
    RouterV6Pipeline.run() never proceeds past Stage 0 -- no real file I/O,
    no placement legalization, no Stage 2 channel analysis. This keeps the
    test's runtime independent of board size and avoids the island-bridging
    performance cliff on the real, unstripped production board (documented
    in 8abcec24's own commit message: opening F.Cu/B.Cu with their real
    zone-pour geometry fragments the medial-axis skeleton into ~150
    disconnected islands, and _ensure_skeleton_connectivity's O(n^2)
    bridging does not complete in practical time on that input)."""


def test_pipeline_run_wires_declared_layer_roles_into_stage0(monkeypatch):
    """RouterV6Pipeline.run() must call parse_kicad_pcb_v6 with
    use_declared_layer_roles=True.

    This is the actual falsifier for 8abcec24. Before that fix, ``run()``
    called ``parse_kicad_pcb_v6(pcb_path)`` with the flag left at its
    default ``False`` -- so on the real, committed production board
    (zones present, exactly as CI parses it), the existential-zone-
    quantifier bug in ``_extract_stackup()`` fires, F.Cu/B.Cu are
    classified ``layer_type="plane"``, ``routing_space.py`` drops them
    from the routing space, and ``state.channel_skeletons`` collapses to
    ``{}`` -- MEASURED as 0 total skeleton edges on ``main`` (commit
    b31fe017) via this exact call path.
    """
    import temper_placer.io.kicad_parser as kicad_parser_module
    from temper_placer.router_v6.pipeline import RouterV6Pipeline

    captured: dict[str, object] = {}

    def _spy_parse_kicad_pcb_v6(pcb_path, *, use_declared_layer_roles=False):
        captured["pcb_path"] = pcb_path
        captured["use_declared_layer_roles"] = use_declared_layer_roles
        raise _StoppedAfterParseCapture()

    monkeypatch.setattr(
        kicad_parser_module, "parse_kicad_pcb_v6", _spy_parse_kicad_pcb_v6
    )

    pipeline = RouterV6Pipeline()
    # The path is never actually opened -- run() calls parse_kicad_pcb_v6
    # (patched above) as its very first Stage-0 action, with no file I/O
    # before that call, so a placeholder path is sufficient and keeps this
    # test independent of any real board fixture.
    placeholder_path = Path("/nonexistent/placeholder-not-read.kicad_pcb")

    with pytest.raises(_StoppedAfterParseCapture):
        pipeline.run(placeholder_path)

    assert captured.get("pcb_path") == placeholder_path, (
        "sanity check: the spy must have actually been called by "
        "RouterV6Pipeline.run() with the path we passed in"
    )
    assert captured.get("use_declared_layer_roles") is True, (
        "RouterV6Pipeline.run() must parse with use_declared_layer_roles="
        "True (the wiring fixed by commit 8abcec24). Leaving this at its "
        "default False reproduces the plane-condemnation bug: any zone "
        "on a plane-required net anywhere on F.Cu/B.Cu condemns the "
        "WHOLE physical layer to layer_type='plane', which "
        "routing_space.py's compute_routing_space then drops entirely -- "
        "collapsing state.channel_skeletons to {} and making route_pcb() "
        "build a silent 0-variable/0-constraint model that every routing "
        "DRC baseline nonetheless certified as 'passing'."
    )
