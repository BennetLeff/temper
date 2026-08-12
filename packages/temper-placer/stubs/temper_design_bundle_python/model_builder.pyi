"""Type stubs for `temper_design_bundle_python.model_builder`.

Compiled from `packages/temper-design-bundle/src/model_builder.rs`. Keep in
sync with that file.
"""
from __future__ import annotations
from typing import Any

class Variable:
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

class NetChannelVar:
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

class NetLayerVar:
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

class ViaVar:
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

class OrderVar:
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

class Constraint:
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

class CapacityConstraint:
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

class DiffPairConstraint:
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

class LayerConstraint:
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

class ChannelSeparationConstraint:
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

class ConstraintModel:
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

class ModelBuilder:
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

class ConstraintModelEmptyError(Exception): ...
