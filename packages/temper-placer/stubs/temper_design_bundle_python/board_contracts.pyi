"""Type stubs for `temper_design_bundle_python.board_contracts`.

Compiled from `packages/temper-design-bundle/src/board_contracts.rs` -- the
Wave 4 Phase 3 candidate-1 migration of `temper_placer/core/board.py`. Keep
in sync with that file.

`LayerIndex` and its derived tables are deliberately NOT here: they remain a
Python `IntEnum` in `temper_placer/core/board.py` under a recorded R3
verdict (pyo3 cannot subclass `int`). See
`packages/temper-design-bundle/VERIFICATION.md`.

As in the netlist stubs, annotations describe intended usage; the pyclasses
coerce nothing, mirroring the dataclasses they replace.
"""

from __future__ import annotations

from dataclasses import Field
from typing import Any, ClassVar

import numpy as np

class MountingHole:
    # Installed at import time by `temper_placer.core._contract_dataclass_compat`
    # so `dataclasses.replace()` / `fields()` / `is_dataclass()` keep working on
    # the migrated contracts. Declaring it here is what makes the pyclass satisfy
    # typeshed's `DataclassInstance` protocol at the call sites.
    __dataclass_fields__: ClassVar[dict[str, Field[Any]]]
    position: tuple[float, float]
    diameter: float
    keepout_radius: float

    def __init__(
        self,
        position: tuple[float, float],
        diameter: float,
        keepout_radius: float = ...,
    ) -> None: ...

class Pad:
    # Installed at import time by `temper_placer.core._contract_dataclass_compat`
    # so `dataclasses.replace()` / `fields()` / `is_dataclass()` keep working on
    # the migrated contracts. Declaring it here is what makes the pyclass satisfy
    # typeshed's `DataclassInstance` protocol at the call sites.
    __dataclass_fields__: ClassVar[dict[str, Field[Any]]]
    position: tuple[float, float]
    size: tuple[float, float]
    shape: str
    layer: str
    number: str
    net_name: str | None

    def __init__(
        self,
        position: tuple[float, float],
        size: tuple[float, float],
        shape: str = ...,
        layer: str = ...,
        number: str = ...,
        net_name: str | None = ...,
    ) -> None: ...

class Component:
    # Installed at import time by `temper_placer.core._contract_dataclass_compat`
    # so `dataclasses.replace()` / `fields()` / `is_dataclass()` keep working on
    # the migrated contracts. Declaring it here is what makes the pyclass satisfy
    # typeshed's `DataclassInstance` protocol at the call sites.
    __dataclass_fields__: ClassVar[dict[str, Field[Any]]]
    ref: str
    position: tuple[float, float]
    rotation: float
    width: float
    height: float
    footprint: str | None
    pads: list[Pad]
    layer: str
    fixed: bool

    def __init__(
        self,
        ref: str,
        position: tuple[float, float],
        rotation: float,
        width: float,
        height: float,
        footprint: str | None = ...,
        pads: list[Pad] | None = ...,
        layer: str = ...,
        fixed: bool = ...,
    ) -> None: ...

class Trace:
    """`frozen=True`: assignment raises `dataclasses.FrozenInstanceError`."""

    # Installed at import time by `temper_placer.core._contract_dataclass_compat`
    # so `dataclasses.replace()` / `fields()` / `is_dataclass()` keep working on
    # the migrated contracts. Declaring it here is what makes the pyclass satisfy
    # typeshed's `DataclassInstance` protocol at the call sites.
    __dataclass_fields__: ClassVar[dict[str, Field[Any]]]
    @property
    def start(self) -> tuple[float, float]: ...
    @property
    def end(self) -> tuple[float, float]: ...
    @property
    def width(self) -> float: ...
    @property
    def layer(self) -> str: ...
    @property
    def net(self) -> str | None: ...
    def __init__(
        self,
        start: tuple[float, float],
        end: tuple[float, float],
        width: float,
        layer: str,
        net: str | None = ...,
    ) -> None: ...

class Via:
    """`frozen=True`: assignment raises `dataclasses.FrozenInstanceError`."""

    # Installed at import time by `temper_placer.core._contract_dataclass_compat`
    # so `dataclasses.replace()` / `fields()` / `is_dataclass()` keep working on
    # the migrated contracts. Declaring it here is what makes the pyclass satisfy
    # typeshed's `DataclassInstance` protocol at the call sites.
    __dataclass_fields__: ClassVar[dict[str, Field[Any]]]
    @property
    def position(self) -> tuple[float, float]: ...
    @property
    def drill(self) -> float: ...
    @property
    def width(self) -> float: ...
    @property
    def layers(self) -> tuple[str, ...]: ...
    @property
    def net(self) -> str | None: ...
    @property
    def is_diff_pair(self) -> bool: ...
    def __init__(
        self,
        position: tuple[float, float],
        drill: float,
        width: float,
        layers: tuple[str, ...] = ...,
        net: str | None = ...,
        is_diff_pair: bool = ...,
    ) -> None: ...

class Layer:
    # Installed at import time by `temper_placer.core._contract_dataclass_compat`
    # so `dataclasses.replace()` / `fields()` / `is_dataclass()` keep working on
    # the migrated contracts. Declaring it here is what makes the pyclass satisfy
    # typeshed's `DataclassInstance` protocol at the call sites.
    __dataclass_fields__: ClassVar[dict[str, Field[Any]]]
    name: str
    layer_type: str
    copper_weight: float
    is_routable: bool

    def __init__(
        self,
        name: str,
        layer_type: str,
        copper_weight: float = ...,
        is_routable: bool = ...,
    ) -> None: ...

class LayerStackup:
    """`frozen=True`. Hashable only while empty -- `Layer` is unhashable."""

    # Installed at import time by `temper_placer.core._contract_dataclass_compat`
    # so `dataclasses.replace()` / `fields()` / `is_dataclass()` keep working on
    # the migrated contracts. Declaring it here is what makes the pyclass satisfy
    # typeshed's `DataclassInstance` protocol at the call sites.
    __dataclass_fields__: ClassVar[dict[str, Field[Any]]]
    @property
    def layers(self) -> tuple[Layer, ...]: ...
    @property
    def thickness(self) -> float: ...
    def __init__(
        self, layers: tuple[Layer, ...] = ..., thickness: float = ...
    ) -> None: ...
    def is_plane_layer(self, layer_idx: int) -> bool: ...
    @classmethod
    def default_4layer(cls) -> LayerStackup: ...
    @classmethod
    def _test_only_2layer(cls) -> LayerStackup: ...
    def routable_layers(self, net_class: str = ...) -> list[int]: ...
    def tracks_per_cell(self, grid_size: float, net_class: str = ...) -> float: ...

class Rect:
    """`frozen=True, eq=False`. Compares equal to a bare 4-tuple/list.

    `__init__` does NOT coerce; `from_xyxy`/`from_xywh`/`coerce` call
    `float()`.
    """

    # Installed at import time by `temper_placer.core._contract_dataclass_compat`
    # so `dataclasses.replace()` / `fields()` / `is_dataclass()` keep working on
    # the migrated contracts. Declaring it here is what makes the pyclass satisfy
    # typeshed's `DataclassInstance` protocol at the call sites.
    __dataclass_fields__: ClassVar[dict[str, Field[Any]]]
    @property
    def x_min(self) -> float: ...
    @property
    def y_min(self) -> float: ...
    @property
    def x_max(self) -> float: ...
    @property
    def y_max(self) -> float: ...
    def __init__(
        self, x_min: float, y_min: float, x_max: float, y_max: float
    ) -> None: ...
    @classmethod
    def from_xyxy(cls, x_min: float, y_min: float, x_max: float, y_max: float) -> Rect: ...
    @classmethod
    def from_xywh(cls, x: float, y: float, width: float, height: float) -> Rect: ...
    @classmethod
    def coerce(cls, value: Rect | tuple[float, float, float, float]) -> Rect: ...
    @property
    def width(self) -> float: ...
    @property
    def height(self) -> float: ...
    def __iter__(self) -> Any: ...
    def __getitem__(self, index: Any) -> Any: ...
    def __len__(self) -> int: ...

class Zone:
    # Installed at import time by `temper_placer.core._contract_dataclass_compat`
    # so `dataclasses.replace()` / `fields()` / `is_dataclass()` keep working on
    # the migrated contracts. Declaring it here is what makes the pyclass satisfy
    # typeshed's `DataclassInstance` protocol at the call sites.
    __dataclass_fields__: ClassVar[dict[str, Field[Any]]]
    name: str
    # Coerced to `Rect` at construction only; a later assignment stores the
    # raw object, as the dataclass did.
    bounds: Any
    net_classes: list[str]
    components: list[str]
    weight: float
    polygon: list[tuple[float, float]] | None
    layers: list[str]
    max_size: tuple[float, float] | None
    can_expand: list[str]
    zone_type: str

    def __init__(
        self,
        name: str,
        bounds: Rect | tuple[float, float, float, float],
        net_classes: list[str] | None = ...,
        components: list[str] | None = ...,
        weight: float = ...,
        polygon: list[tuple[float, float]] | None = ...,
        layers: list[str] | None = ...,
        max_size: tuple[float, float] | None = ...,
        can_expand: list[str] | None = ...,
        zone_type: str = ...,
    ) -> None: ...
    @property
    def width(self) -> float: ...
    @property
    def height(self) -> float: ...
    @property
    def center(self) -> tuple[float, float]: ...
    @property
    def area(self) -> float: ...
    def contains_point(self, x: float, y: float) -> bool: ...

class GroundDomain:
    # Installed at import time by `temper_placer.core._contract_dataclass_compat`
    # so `dataclasses.replace()` / `fields()` / `is_dataclass()` keep working on
    # the migrated contracts. Declaring it here is what makes the pyclass satisfy
    # typeshed's `DataclassInstance` protocol at the call sites.
    __dataclass_fields__: ClassVar[dict[str, Field[Any]]]
    name: str
    bounds: tuple[float, float, float, float]
    star_point: tuple[float, float] | None

    def __init__(
        self,
        name: str,
        bounds: tuple[float, float, float, float],
        star_point: tuple[float, float] | None = ...,
    ) -> None: ...
    def contains_point(self, x: float, y: float) -> bool: ...

class Board:
    # Installed at import time by `temper_placer.core._contract_dataclass_compat`
    # so `dataclasses.replace()` / `fields()` / `is_dataclass()` keep working on
    # the migrated contracts. Declaring it here is what makes the pyclass satisfy
    # typeshed's `DataclassInstance` protocol at the call sites.
    __dataclass_fields__: ClassVar[dict[str, Field[Any]]]
    width: float
    height: float
    origin: tuple[float, float]
    # Untyped on purpose: `cli/__init__.py` assigns duck-typed zone objects.
    zones: list[Any]
    mounting_holes: list[MountingHole]
    keepouts: list[tuple[float, float, float, float]]
    ground_domains: list[GroundDomain]
    layer_stackup: LayerStackup
    outline_polygon: list[tuple[float, float]] | None
    # `init=False` but present in both `__repr__` and `__eq__`.
    _zone_map: dict[str, Any]

    def __init__(
        self,
        width: float,
        height: float,
        origin: tuple[float, float] = ...,
        zones: list[Any] | None = ...,
        mounting_holes: list[MountingHole] | None = ...,
        keepouts: list[tuple[float, float, float, float]] | None = ...,
        ground_domains: list[GroundDomain] | None = ...,
        layer_stackup: LayerStackup | None = ...,
        outline_polygon: list[tuple[float, float]] | None = ...,
    ) -> None: ...
    def build_indices(self) -> None: ...
    @property
    def keepout_regions(self) -> list[tuple[float, float, float, float]]: ...
    @property
    def has_polygon_outline(self) -> bool: ...
    def polygon_array(self) -> np.ndarray | None: ...
    @classmethod
    def from_polygon(
        cls,
        polygon: list[tuple[float, float]],
        origin: tuple[float, float] = ...,
    ) -> Board: ...
    @classmethod
    def temper_default(cls) -> Board: ...
    def get_zone(self, name: str) -> Any: ...
    def get_zone_for_point(self, x: float, y: float) -> Any | None: ...
    def get_ground_domain(self, x: float, y: float) -> GroundDomain | None: ...
    def contains_point(self, x: float, y: float) -> bool: ...
    def point_in_keepout(self, x: float, y: float) -> bool: ...
    def get_bounds_array(self) -> np.ndarray: ...
    def get_relative_bounds_array(self) -> np.ndarray: ...
    @property
    def area(self) -> float: ...
    def rotated_90(self) -> Board: ...

def side_to_layer_name(side: int) -> str: ...
