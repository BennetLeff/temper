"""U5: _write_routes_to_content must emit real (via ...) s-expressions."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from temper_placer.router_v6.adapter import _write_routes_to_content


@dataclass
class _StubVia:
    position: tuple[float, float]
    from_layer: str
    to_layer: str
    diameter: float
    drill: float
    net_name: str


def _make_result(routed_by_name: dict, via_list: list | None = None) -> object:
    compiled = {}
    for name, path in routed_by_name.items():
        compiled[name] = SimpleNamespace(
            net_name=name,
            path=path,
            width_mm=0.25,
            vias=via_list or [],
        )
    # PCB with one net and two pads at the route endpoints.
    c1 = SimpleNamespace(ref="C1", initial_position=(0.0, 0.0))
    c1.get_pin = lambda _name: SimpleNamespace(position=(0.0, 0.0))
    c2 = SimpleNamespace(ref="C2", initial_position=(10.0, 0.0))
    c2.get_pin = lambda _name: SimpleNamespace(position=(0.0, 0.0))
    return SimpleNamespace(
        stage4=SimpleNamespace(
            routing_results=SimpleNamespace(
                compiled_routes=compiled,
                partial_routes={},
                tree_routes={},
                partial_tree_routes={},
            )
        ),
        pcb=SimpleNamespace(
            components=[c1, c2],
            nets=[SimpleNamespace(name="NET", pins=[("C1", "1"), ("C2", "1")])],
        ),
    )


class TestViaEmission:
    """U5: vias emitted as (via ...) s-expressions."""

    def test_single_via_is_emitted_correctly(self):
        from temper_placer.router_v6.astar_core import RoutePath

        path = RoutePath(
            net_name="NET",
            coordinates=[(0, 0), (5, 0), (10, 0)],
            layer_name="F.Cu",
            path_length=10.0,
        )
        via = _StubVia((2.5, 0.0), "F.Cu", "B.Cu", 0.6, 0.3, "NET")
        result = _make_result({"NET": path}, [via])
        content = _write_routes_to_content('(kicad_pcb\n  (net 1 "NET")\n)\n', result)[0]
        assert "(via " in content
        assert "(at 2.5000 0.0000)" in content
        assert "(size 0.6000)" in content
        assert '(layers "F.Cu" "B.Cu")' in content

    def test_two_vias_both_emitted(self):
        from temper_placer.router_v6.astar_core import RoutePath

        path = RoutePath(
            net_name="NET",
            coordinates=[(0, 0), (5, 0), (10, 0)],
            layer_name="F.Cu",
            path_length=10.0,
        )
        vias = [
            _StubVia((3.0, 0.0), "F.Cu", "B.Cu", 0.6, 0.3, "NET"),
            _StubVia((7.0, 0.0), "B.Cu", "F.Cu", 0.6, 0.3, "NET"),
        ]
        result = _make_result({"NET": path}, vias)
        content = _write_routes_to_content('(kicad_pcb\n  (net 1 "NET")\n)\n', result)[0]
        assert content.count("(via ") == 2

    def test_via_preserves_net_number(self):
        from temper_placer.router_v6.astar_core import RoutePath

        path = RoutePath(
            net_name="NET",
            coordinates=[(0, 0), (5, 0), (10, 0)],
            layer_name="F.Cu",
            path_length=10.0,
        )
        via = _StubVia((2.5, 0.0), "F.Cu", "B.Cu", 0.6, 0.3, "NET")
        result = _make_result({"NET": path}, [via])
        content = _write_routes_to_content(
            '(kicad_pcb\n  (net 1 "NET")\n  (net 2 "OTHER")\n)\n', result
        )[0]
        assert "(net 1)" in content

    def test_partial_stack_via_emits_blind_type_token(self):
        """A via whose pair is NOT the full stack must carry a `blind` token.

        KiCad's file format default is THROUGH: a via with no type token
        pierces every copper layer regardless of its declared layer pair.
        This was the router's emission bug -- every layer-pair via was
        silently widened to a through via (16 phantom DRC shorts on layers
        outside the declared pair). See
        docs/evidence/2026-08-15-via-type-emission-fix.md.
        """
        from temper_placer.router_v6.astar_core import RoutePath

        path = RoutePath(
            net_name="NET",
            coordinates=[(0, 0), (5, 0), (10, 0)],
            layer_name="F.Cu",
            path_length=10.0,
        )
        via = _StubVia((2.5, 0.0), "F.Cu", "In3.Cu", 0.6, 0.3, "NET")
        result = _make_result({"NET": path}, [via])
        content = _write_routes_to_content('(kicad_pcb\n  (net 1 "NET")\n)\n', result)[0]
        assert "(via blind (at 2.5000 0.0000)" in content
        assert '(layers "F.Cu" "In3.Cu")' in content

    def test_inner_pair_via_emits_buried_type_token(self):
        """An inner-inner via pair must carry a `buried` token."""
        from temper_placer.router_v6.astar_core import RoutePath

        path = RoutePath(
            net_name="NET",
            coordinates=[(0, 0), (5, 0), (10, 0)],
            layer_name="In1.Cu",
            path_length=10.0,
        )
        via = _StubVia((2.5, 0.0), "In1.Cu", "In3.Cu", 0.6, 0.3, "NET")
        result = _make_result({"NET": path}, [via])
        content = _write_routes_to_content('(kicad_pcb\n  (net 1 "NET")\n)\n', result)[0]
        assert "(via buried (at 2.5000 0.0000)" in content

    def test_full_stack_via_keeps_no_type_token(self):
        """F.Cu <-> B.Cu is the full stack: through, so NO token is emitted.

        The KiCad default (no token) is exactly right for this pair, and
        the pre-fix byte format for it must be preserved."""
        from temper_placer.router_v6.astar_core import RoutePath

        path = RoutePath(
            net_name="NET",
            coordinates=[(0, 0), (5, 0), (10, 0)],
            layer_name="F.Cu",
            path_length=10.0,
        )
        via = _StubVia((2.5, 0.0), "F.Cu", "B.Cu", 0.6, 0.3, "NET")
        result = _make_result({"NET": path}, [via])
        content = _write_routes_to_content('(kicad_pcb\n  (net 1 "NET")\n)\n', result)[0]
        assert "(via (at 2.5000 0.0000)" in content
        assert "via blind" not in content
        assert "via buried" not in content


# ---------------------------------------------------------------------------
# Tree-routed nets: the writer's OTHER emission branch.
#
# ``_write_routes_to_content`` handles a tree route separately from a serial
# path, because a tree's branches must never be bridged by synthetic copper.
# That branch drops every layer-CHANGING point pair (a KiCad ``(segment ...)``
# is single-layer and cannot express one) -- so until 2026-08-19 a tree route
# lost its connection at every layer transition, because nothing emitted the
# via that carries it.  These tests pin that the vias are emitted, that they
# are electrically correct (layer pair, net number, KiCad type token), and
# that the via-only emission cannot leak a ``(segment ...)`` of its own.
#
# The production 6-layer route of ``pcb/temper.kicad_pcb`` does NOT reach this
# branch (``_astar_nlayer.run_astar_pathfinding_nlayer`` never populates
# ``PathfindingResult.tree_routes``); the live producers are
# ``_astar_reconstruct.run_astar_pathfinding`` -- ``route_stage.py``'s
# deterministic pipeline and ``_pipeline_route``'s <=2-routable-layer branch.
# ---------------------------------------------------------------------------


def _tree_result(geometry, vias, *, width_mm=0.25, partial=False):
    from temper_placer.router_v6.routing_results import CompiledTreeRoute

    ctr = CompiledTreeRoute(
        net_name=geometry.net_name,
        geometry=geometry,
        width_mm=width_mm,
        vias=list(vias),
    )
    trees = {geometry.net_name: ctr}
    c1 = SimpleNamespace(ref="C1", initial_position=(0.0, 0.0))
    c1.get_pin = lambda _name: SimpleNamespace(position=(0.0, 0.0))
    c2 = SimpleNamespace(ref="C2", initial_position=(10.0, 0.0))
    c2.get_pin = lambda _name: SimpleNamespace(position=(0.0, 0.0))
    return SimpleNamespace(
        stage4=SimpleNamespace(
            routing_results=SimpleNamespace(
                compiled_routes={},
                partial_routes={},
                tree_routes={} if partial else trees,
                partial_tree_routes=trees if partial else {},
            )
        ),
        pcb=SimpleNamespace(
            components=[c1, c2],
            nets=[SimpleNamespace(name="NET", pins=[("C1", "1"), ("C2", "1")])],
        ),
    )


def _one_branch_tree(segments, via_positions):
    """A single-branch ``TreeRouteGeometry`` over a ``RoutePath3D``."""
    from temper_placer.router_v6.astar_core import RoutePath3D
    from temper_placer.router_v6.connectivity import PadIdentity
    from temper_placer.router_v6.terminal_tree import TerminalTreeEdge
    from temper_placer.router_v6.tree_route_geometry import (
        TreeRouteBranch,
        TreeRouteGeometry,
    )

    def _pad(ref):
        return PadIdentity(component_ref=ref, pad="1", net="NET", x=0.0, y=0.0, layers=(0,))

    branch = TreeRouteBranch(
        edge=TerminalTreeEdge(source=_pad("C1"), target=_pad("C2")),
        path=RoutePath3D(
            net_name="NET",
            segments=list(segments),
            via_positions=list(via_positions),
            path_length=10.0,
            via_count=len(via_positions),
        ),
    )
    return TreeRouteGeometry(net_name="NET", branches=(branch,))


class TestTreeRouteViaEmission:
    """A tree route's layer transitions must be carried by real vias."""

    # An F.Cu run, a transition at (5, 0), then an In3.Cu run.  The middle
    # point pair is the layer change the segment loop cannot express.
    SEGMENTS = (
        (0.0, 0.0, "F.Cu"),
        (5.0, 0.0, "F.Cu"),
        (5.0, 0.0, "In3.Cu"),
        (10.0, 0.0, "In3.Cu"),
    )

    def _geometry(self):
        return _one_branch_tree(self.SEGMENTS, [(5.0, 0.0)])

    def test_tree_route_layer_transition_emits_a_via(self):
        via = _StubVia((5.0, 0.0), "F.Cu", "In3.Cu", 0.6, 0.3, "NET")
        content = _write_routes_to_content(
            '(kicad_pcb\n  (net 1 "NET")\n)\n', _tree_result(self._geometry(), [via])
        )[0]
        assert content.count("(via ") == 1
        assert "(at 5.0000 0.0000)" in content

    def test_tree_route_via_carries_the_derived_layer_pair_and_net(self):
        via = _StubVia((5.0, 0.0), "F.Cu", "In3.Cu", 0.6, 0.3, "NET")
        content = _write_routes_to_content(
            '(kicad_pcb\n  (net 1 "NET")\n  (net 2 "OTHER")\n)\n',
            _tree_result(self._geometry(), [via]),
        )[0]
        # The pair is the one the route actually transitions across, and an
        # outer<->inner pair MUST carry the `blind` token -- without it KiCad
        # parses the via as THROUGH and it pierces every copper layer.
        assert "(via blind (at 5.0000 0.0000)" in content
        assert '(layers "F.Cu" "In3.Cu")' in content
        assert "(net 1)" in content

    def test_tree_route_via_bridges_the_two_track_fragments(self):
        """The via lands exactly where the two same-layer runs meet.

        This is the connectivity property: without it the F.Cu run and the
        In3.Cu run are two disconnected components of the same net.
        """
        via = _StubVia((5.0, 0.0), "F.Cu", "In3.Cu", 0.6, 0.3, "NET")
        content = _write_routes_to_content(
            '(kicad_pcb\n  (net 1 "NET")\n)\n', _tree_result(self._geometry(), [via])
        )[0]
        assert (
            "(segment (start 0.0000 0.0000) (end 5.0000 0.0000)"
            ' (width 0.2500) (layer "F.Cu") (net 1)' in content
        )
        assert (
            "(segment (start 5.0000 0.0000) (end 10.0000 0.0000)"
            ' (width 0.2500) (layer "In3.Cu") (net 1)' in content
        )
        assert "(at 5.0000 0.0000)" in content

    def test_tree_route_via_emission_adds_no_extra_segment(self):
        """The via-only payload must not smuggle in track copper.

        The branch geometry is the sole source of a tree net's tracks; the
        payload carrying the vias is built with a zero-length path and a zero
        pad count precisely so the emission core's
        ``path_length > 0 and pad_count >= 2`` guard cannot fire.
        """
        vias = [
            _StubVia((5.0, 0.0), "F.Cu", "In3.Cu", 0.6, 0.3, "NET"),
            _StubVia((7.0, 0.0), "In3.Cu", "In4.Cu", 0.6, 0.3, "NET"),
        ]
        content = _write_routes_to_content(
            '(kicad_pcb\n  (net 1 "NET")\n)\n', _tree_result(self._geometry(), vias)
        )[0]
        assert content.count("(segment ") == 2  # the two same-layer runs only
        assert content.count("(via ") == 2
        assert "(via buried (at 7.0000 0.0000)" in content

    def test_tree_route_with_no_vias_emits_none(self):
        geometry = _one_branch_tree([(0.0, 0.0, "F.Cu"), (5.0, 0.0, "F.Cu")], [])
        content = _write_routes_to_content(
            '(kicad_pcb\n  (net 1 "NET")\n)\n', _tree_result(geometry, [])
        )[0]
        assert "(via " not in content

    def test_partial_tree_route_vias_are_emitted_too(self):
        via = _StubVia((5.0, 0.0), "F.Cu", "In3.Cu", 0.6, 0.3, "NET")
        content = _write_routes_to_content(
            '(kicad_pcb\n  (net 1 "NET")\n)\n',
            _tree_result(self._geometry(), [via], partial=True),
        )[0]
        assert content.count("(via ") == 1

    def test_sub_floor_annular_ring_is_corrected_at_emission(self):
        """``Via::new``'s 0.254mm annular floor applies to tree-route vias too.

        Reusing the shared Rust emission core rather than formatting a
        ``(via ...)`` string here is what makes that automatic.
        """
        via = _StubVia((5.0, 0.0), "F.Cu", "In3.Cu", 0.4, 0.3, "NET")
        content = _write_routes_to_content(
            '(kicad_pcb\n  (net 1 "NET")\n)\n', _tree_result(self._geometry(), [via])
        )[0]
        # (0.4 - 0.3) / 2 = 0.05mm ring -> enlarged to drill + 2 x 0.3mm.
        assert "(size 0.9000)" in content
        assert "(drill 0.3000)" in content
