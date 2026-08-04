"""Type stubs for `temper_design_bundle_python.netlist_contracts`.

Compiled from `packages/temper-design-bundle/src/netlist_contracts.rs` --
the Wave 4 Phase 3 candidate-1 migration of
`temper_placer/core/netlist.py`. Keep in sync with that file.

Every field is declared with the *annotation the original dataclass
carried*, not the storage type. The pyclass actually stores each field as an
opaque Python object and performs no coercion -- exactly as the dataclass
did -- so e.g. `Component(..., bounds=(1, 2))` really does keep `int`s and
`.width` really does return `int`. The annotations describe intended usage;
they are deliberately not tightened beyond what the runtime enforces
(which is nothing).
"""

from __future__ import annotations

from dataclasses import Field
from typing import Any, ClassVar

import numpy as np

class Pin:
    # Installed at import time by `temper_placer.core._contract_dataclass_compat`
    # so `dataclasses.replace()` / `fields()` / `is_dataclass()` keep working on
    # the migrated contracts. Declaring it here is what makes the pyclass satisfy
    # typeshed's `DataclassInstance` protocol at the call sites.
    __dataclass_fields__: ClassVar[dict[str, Field[Any]]]
    name: str
    number: str
    position: tuple[float, float]
    net: str | None
    width: float
    height: float
    shape: str
    layer: str
    drill: float
    is_pth: bool
    roundrect_ratio: float
    pad_rotation_deg: float

    def __init__(
        self,
        name: str,
        number: str,
        position: tuple[float, float],
        net: str | None = ...,
        width: float = ...,
        height: float = ...,
        shape: str = ...,
        layer: str = ...,
        drill: float = ...,
        is_pth: bool = ...,
        roundrect_ratio: float = ...,
        pad_rotation_deg: float = ...,
    ) -> None: ...
    @property
    def mask_expansion(self) -> float: ...

class Component:
    # Installed at import time by `temper_placer.core._contract_dataclass_compat`
    # so `dataclasses.replace()` / `fields()` / `is_dataclass()` keep working on
    # the migrated contracts. Declaring it here is what makes the pyclass satisfy
    # typeshed's `DataclassInstance` protocol at the call sites.
    __dataclass_fields__: ClassVar[dict[str, Field[Any]]]
    ref: str
    footprint: str
    bounds: tuple[float, float]
    pins: list[Pin]
    net_class: str
    zone: str | None
    fixed: bool
    initial_position: tuple[float, float] | None
    initial_rotation: int | None
    initial_side: int | None
    attributes: dict[str, str]
    tags: frozenset[Any]
    sheetpath: str | None

    def __init__(
        self,
        ref: str,
        footprint: str,
        bounds: tuple[float, float],
        pins: list[Pin] | None = ...,
        net_class: str = ...,
        zone: str | None = ...,
        fixed: bool = ...,
        initial_position: tuple[float, float] | None = ...,
        initial_rotation: int | None = ...,
        initial_side: int | None = ...,
        attributes: dict[str, str] | None = ...,
        tags: frozenset[Any] | None = ...,
        sheetpath: str | None = ...,
    ) -> None: ...
    @property
    def width(self) -> float: ...
    @property
    def height(self) -> float: ...
    def get_pin(self, name_or_number: str) -> Pin | None: ...
    def get_pins_for_net(self, net_name: str) -> list[Pin]: ...

class Net:
    # Installed at import time by `temper_placer.core._contract_dataclass_compat`
    # so `dataclasses.replace()` / `fields()` / `is_dataclass()` keep working on
    # the migrated contracts. Declaring it here is what makes the pyclass satisfy
    # typeshed's `DataclassInstance` protocol at the call sites.
    __dataclass_fields__: ClassVar[dict[str, Field[Any]]]
    name: str
    pins: list[tuple[str, str]]
    net_class: str
    weight: float
    max_current: float
    voltage_class: str

    def __init__(
        self,
        name: str,
        pins: list[tuple[str, str]],
        net_class: str = ...,
        weight: float = ...,
        max_current: float = ...,
        voltage_class: str = ...,
    ) -> None: ...
    @property
    def pin_count(self) -> int: ...
    def get_component_refs(self) -> set[str]: ...

class Netlist:
    # Installed at import time by `temper_placer.core._contract_dataclass_compat`
    # so `dataclasses.replace()` / `fields()` / `is_dataclass()` keep working on
    # the migrated contracts. Declaring it here is what makes the pyclass satisfy
    # typeshed's `DataclassInstance` protocol at the call sites.
    __dataclass_fields__: ClassVar[dict[str, Field[Any]]]
    components: list[Component]
    nets: list[Net]
    # Real `init=True, repr=False, compare=True` dataclass fields; rebuilt
    # unconditionally by `__init__` and by `build_indices()`.
    _component_index: dict[str, int]
    _net_index: dict[str, int]
    _component_nets: dict[str, list[str]]

    def __init__(
        self,
        components: list[Component] | None = ...,
        nets: list[Net] | None = ...,
        _component_index: dict[str, int] | None = ...,
        _net_index: dict[str, int] | None = ...,
        _component_nets: dict[str, list[str]] | None = ...,
    ) -> None: ...
    def build_indices(self) -> None: ...
    def get_component_index(self, ref: str) -> int: ...
    def get_component(self, ref: str) -> Component: ...
    def get_net(self, name: str) -> Net: ...
    def get_component_nets(self, ref: str) -> list[str]: ...
    def get_net_pins(self, net_name: str) -> list[tuple[str, str]]: ...
    @property
    def n_components(self) -> int: ...
    @property
    def n_nets(self) -> int: ...
    def get_bounds_array(self) -> np.ndarray: ...
    def get_fixed_mask(self) -> np.ndarray: ...
    def apply_net_class_mapping(self, mapping: dict[str, str]) -> int: ...
    def find_isomorphic_groups(self, iterations: int = ...) -> list[list[int]]: ...
    def validate(self) -> list[str]: ...

def build_adjacency_matrix(netlist: Any) -> np.ndarray: ...
