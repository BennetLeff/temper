"""Type stubs for `temper_design_bundle_python.geometry_contracts`.

Compiled from `packages/temper-design-bundle/src/geometry_types_contracts.rs`
(submodule registered under the shorter name `geometry_contracts`). Keep in
sync with that file.
"""
from __future__ import annotations
from typing import Any

class Point:
    x: Any
    y: Any
    def __init__(self, x: Any, y: Any) -> None: ...

class Track:
    start: Any
    end: Any
    width: Any
    net: Any
    layer: Any
    id: Any
    diff_pair_companion: Any
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

class Via:
    center: Any
    diameter: Any
    drill: Any
    net: Any
    id: Any
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

class Pad:
    center: Any
    shape: Any
    size: Any
    net: Any
    layer: Any
    id: Any
    rotation: Any
    mask_expansion: Any
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...
