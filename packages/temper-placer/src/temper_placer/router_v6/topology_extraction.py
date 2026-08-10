"""
Router V6 Stage 3.9: Topology graph types.

The topology graph is built directly from the Rust solver result in
``_pipeline_route`` (see ``rust_result["topology_graph"]``); this module owns
only the dataclasses that result is marshalled into.
Part of temper-8qm8 (Stage 3 - Topological Routing)

Migrated to Rust pyclasses (Wave 4 fanout, temper-design-bundle,
``topology_extraction_contracts`` submodule). This module is now a
pure-delegation shim re-exporting the pyclasses under their original names.

``PathGraph`` replaces ``networkx.DiGraph`` for the ``path_graph`` field.
"""

from __future__ import annotations

import temper_design_bundle_python as _tdb

from temper_placer.core._contract_dataclass_compat import (
    field as _contract_field,
)
from temper_placer.core._contract_dataclass_compat import (
    install_dataclass_fields as _install_dataclass_fields,
)

PathGraph = _tdb.topology_extraction_contracts.PathGraph
NetTopology = _tdb.topology_extraction_contracts.NetTopology
TopologyGraph = _tdb.topology_extraction_contracts.TopologyGraph

__all__ = ["NetTopology", "PathGraph", "TopologyGraph"]

# A pyclass is not a dataclass, and ``dataclasses.replace()`` / ``dataclasses.fields()``
# are used across router_v6; pickling also needs a resolvable ``__module__``.
# See ``_contract_dataclass_compat`` for the mechanism and ``core/geometry_types.py``
# for the established precedent.
_install_dataclass_fields(
    NetTopology,
    (
        _contract_field("net_name", "str"),
        _contract_field("path_graph", "PathGraph | None"),
        _contract_field("uses_channels", "list[str]"),
        _contract_field("total_length_estimate", "float"),
    ),
    module=__name__,
)
_install_dataclass_fields(
    TopologyGraph,
    (
        _contract_field("net_topologies", "dict[str, NetTopology]"),
    ),
    module=__name__,
)
