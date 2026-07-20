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
            net_name=name, path=path, width_mm=0.25, vias=via_list or [],
        )
    # PCB with one net and two pads at the route endpoints.
    c1 = SimpleNamespace(ref="C1", initial_position=(0.0, 0.0))
    c1.get_pin = lambda _name: SimpleNamespace(position=(0.0, 0.0))
    c2 = SimpleNamespace(ref="C2", initial_position=(10.0, 0.0))
    c2.get_pin = lambda _name: SimpleNamespace(position=(0.0, 0.0))
    return SimpleNamespace(
        stage4=SimpleNamespace(routing_results=SimpleNamespace(
            compiled_routes=compiled, partial_routes={}, tree_routes={}, partial_tree_routes={},
        )),
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
            net_name="NET", coordinates=[(0,0),(5,0),(10,0)], layer_name="F.Cu",
            path_length=10.0,
        )
        via = _StubVia((2.5, 0.0), "F.Cu", "B.Cu", 0.6, 0.3, "NET")
        result = _make_result({"NET": path}, [via])
        content = _write_routes_to_content(
            '(kicad_pcb\n  (net 1 "NET")\n)\n', result
        )[0]
        assert '(via ' in content
        assert '(at 2.5000 0.0000)' in content
        assert '(size 0.6000)' in content
        assert '(layers "F.Cu" "B.Cu")' in content

    def test_two_vias_both_emitted(self):
        from temper_placer.router_v6.astar_core import RoutePath

        path = RoutePath(
            net_name="NET", coordinates=[(0,0),(5,0),(10,0)], layer_name="F.Cu",
            path_length=10.0,
        )
        vias = [
            _StubVia((3.0, 0.0), "F.Cu", "B.Cu", 0.6, 0.3, "NET"),
            _StubVia((7.0, 0.0), "B.Cu", "F.Cu", 0.6, 0.3, "NET"),
        ]
        result = _make_result({"NET": path}, vias)
        content = _write_routes_to_content(
            '(kicad_pcb\n  (net 1 "NET")\n)\n', result
        )[0]
        assert content.count('(via ') == 2

    def test_via_preserves_net_number(self):
        from temper_placer.router_v6.astar_core import RoutePath

        path = RoutePath(
            net_name="NET", coordinates=[(0,0),(5,0),(10,0)], layer_name="F.Cu",
            path_length=10.0,
        )
        via = _StubVia((2.5, 0.0), "F.Cu", "B.Cu", 0.6, 0.3, "NET")
        result = _make_result({"NET": path}, [via])
        content = _write_routes_to_content(
            '(kicad_pcb\n  (net 1 "NET")\n  (net 2 "OTHER")\n)\n', result
        )[0]
        assert '(net 1)' in content
