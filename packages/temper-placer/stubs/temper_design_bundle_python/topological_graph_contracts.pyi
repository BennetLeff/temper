"""Type stubs for `temper_design_bundle_python.topological_graph_contracts`.

Compiled from `packages/temper-design-bundle/src/topological_graph_contracts.rs`.
Keep in sync with that file.
"""
from __future__ import annotations
from typing import Any

class TopologicalGraphStore:
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...
    def nodes(self) -> list[Any]: ...
    def edges(self, *args: Any, **kwargs: Any) -> list[Any]: ...
