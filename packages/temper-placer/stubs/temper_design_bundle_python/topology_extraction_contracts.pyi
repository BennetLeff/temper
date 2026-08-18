"""Type stubs for `temper_design_bundle_python.topology_extraction_contracts`.

Compiled from `packages/temper-design-bundle/src/topology_extraction_contracts.rs`.
Keep in sync with that file.
"""
from __future__ import annotations
from typing import Any

class PathGraph:
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

class NetTopology:
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

class TopologyGraph:
    net_topologies: dict[str, NetTopology]
    def __init__(self, net_topologies: dict[str, NetTopology]) -> None: ...
    @property
    def routed_net_count(self) -> int: ...
    def get_topology(self, net_name: str) -> NetTopology | None: ...
