"""Type stubs for `temper_design_bundle_python.terminal_wire_contracts`.

Compiled from `packages/temper-design-bundle/src/terminal_wire_contracts.rs` —
the Orchestration plan Phase A unit U7 migration of
`temper_placer/router_v6/terminal_extraction.py`'s wire-format boundary. Keep
in sync with that file. The wire types are frozen dataclass-equivalents; the
`from_*` classmethods perform the attribute extraction the
`temper_rust_router.extract_net_terminals_py` kernel reads by name.
"""

from __future__ import annotations

class PinWire:
    name: str
    number: str
    position: tuple[float, float]
    is_pth: bool
    layer: str | None

    def __init__(
        self,
        name: str,
        number: str,
        position: tuple[float, float],
        is_pth: bool,
        layer: str | None = ...,
    ) -> None: ...

    @classmethod
    def from_pin(cls, pin: object) -> PinWire: ...


class ComponentWire:
    ref: str
    initial_position: tuple[float, float] | None
    initial_rotation_quadrant: int | None
    initial_side: int | None
    pins: list[PinWire]

    def __init__(
        self,
        ref: str,
        initial_position: tuple[float, float] | None = ...,
        initial_rotation_quadrant: int | None = ...,
        initial_side: int | None = ...,
        pins: list[PinWire] | None = ...,
    ) -> None: ...

    @classmethod
    def from_component(cls, component: object) -> ComponentWire: ...


class StackupLayerWire:
    name: str | None
    index: int | None
    layer_type: str | None

    def __init__(
        self,
        name: str | None = ...,
        index: int | None = ...,
        layer_type: str | None = ...,
    ) -> None: ...

    @classmethod
    def from_layer(cls, layer: object) -> StackupLayerWire: ...
