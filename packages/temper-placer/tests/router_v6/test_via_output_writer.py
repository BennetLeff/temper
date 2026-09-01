"""U5: _write_routes_to_content must emit real (via ...) s-expressions."""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from temper_placer.router_v6.adapter import _write_routes_to_content
from tests.router_v6._via_annular_floor import floor_compliant_via

# The pad every fixture below carries is DERIVED from the crate that owns
# the board's annular-ring fabrication floor, never written out.
#
# `_write_routes_to_content` marshals each via through
# `temper_orchestration`'s `Via::new`, which since 968d1a33d (PR #1316)
# enlarges any pad leaving a ring below the 0.254mm fab floor. The pre-#1316
# fixture pad here was 0.6mm on a 0.3mm drill -- a 0.15mm ring, which KiCad
# DRC rejects outright (`pcb/temper.kicad_pro`:
# `board.design_settings.rules.min_via_annular_width` = 0.254 at severity
# `error`). `test_single_via_is_emitted_correctly` asserted `(size 0.6000)`
# came back, so it failed for anyone whose extension was current and passed
# for anyone whose extension predated #1316 -- a verdict that tracked build
# state, not code state. The emitted size must equal the pad handed in, and
# both are now read from the same place.
_VIA_DIAMETER, _VIA_DRILL = floor_compliant_via()


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
        via = _StubVia((2.5, 0.0), "F.Cu", "B.Cu", _VIA_DIAMETER, _VIA_DRILL, "NET")
        result = _make_result({"NET": path}, [via])
        content = _write_routes_to_content('(kicad_pcb\n  (net 1 "NET")\n)\n', result)[0]
        assert "(via " in content
        assert "(at 2.5000 0.0000)" in content
        assert f"(size {_VIA_DIAMETER:.4f})" in content, (
            "the emitted pad must be the pad handed in -- a compliant via is a "
            "fixed point of `Via::new`'s annular-floor clamp"
        )
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
            _StubVia((3.0, 0.0), "F.Cu", "B.Cu", _VIA_DIAMETER, _VIA_DRILL, "NET"),
            _StubVia((7.0, 0.0), "B.Cu", "F.Cu", _VIA_DIAMETER, _VIA_DRILL, "NET"),
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
        via = _StubVia((2.5, 0.0), "F.Cu", "B.Cu", _VIA_DIAMETER, _VIA_DRILL, "NET")
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
        via = _StubVia((2.5, 0.0), "F.Cu", "In3.Cu", _VIA_DIAMETER, _VIA_DRILL, "NET")
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
        via = _StubVia((2.5, 0.0), "In1.Cu", "In3.Cu", _VIA_DIAMETER, _VIA_DRILL, "NET")
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
        via = _StubVia((2.5, 0.0), "F.Cu", "B.Cu", _VIA_DIAMETER, _VIA_DRILL, "NET")
        result = _make_result({"NET": path}, [via])
        content = _write_routes_to_content('(kicad_pcb\n  (net 1 "NET")\n)\n', result)[0]
        assert "(via (at 2.5000 0.0000)" in content
        assert "via blind" not in content
        assert "via buried" not in content
