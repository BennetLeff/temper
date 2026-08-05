"""
Component, Pin, Net, and Netlist data structures.

This module defines the netlist representation used throughout temper-placer.
Components represent physical parts, Pins are connection points, Nets define
electrical connectivity, and Netlist aggregates everything.

The data model is implemented in Rust as pyo3 pyclasses in the
``temper-design-bundle`` crate (the ``temper_design_bundle_python``
extension) — Wave 4 **Phase 3, candidate 1**
(``docs/plans/2026-08-02-001-feat-wave4-phase3-formats-io-plan.md``). This
module keeps the pre-migration public API unchanged and re-exports the Rust
pyclasses directly (the pure-delegation pattern established by
``core/loop.py`` and ``core/priority.py``).

Verification: bit-identical parity against the pinned pre-migration
implementation — including the concrete Python type of every field and the
``float32`` dtype of every returned array — is asserted by
``tests/core/test_netlist_rust_differential.py`` (oracle:
``tests/core/_netlist_py_oracle.py``) and
``tests/core/test_netlist_pbt.py``; the structural proof lives in
``packages/temper-design-bundle/VERIFICATION.md``.

Deliberately NOT migrated (R3 verdict, named blocker)
-----------------------------------------------------
``compute_eigenvector_centrality`` stays Python. It is a thin wrapper over
``numpy.linalg.eigh`` — LAPACK ``?syevd``. No independent implementation
reproduces LAPACK's output bit-for-bit (the eigenvector basis is only
defined up to sign and, in degenerate subspaces, up to an arbitrary
rotation), so an honest R1 bit-parity differential is unreachable for it;
and a Rust wrapper that merely re-called ``numpy.linalg.eigh`` would add a
boundary crossing while proving nothing. This mirrors PR #688's judgment to
keep ``yaml.safe_load`` on the Python side rather than re-tokenize. See
``packages/temper-design-bundle/VERIFICATION.md``.
"""

from __future__ import annotations

from typing import TypeAlias

import numpy as np
import temper_design_bundle_python as _tdb

from temper_placer.core._contract_dataclass_compat import (
    field as _contract_field,
)
from temper_placer.core._contract_dataclass_compat import (
    install_dataclass_fields as _install_dataclass_fields,
)

Array: TypeAlias = np.ndarray  # numpy alias replacing JAX Array post-JAX retirement

_rs = _tdb.netlist_contracts

Pin = _rs.Pin
Component = _rs.Component
Net = _rs.Net
Netlist = _rs.Netlist
build_adjacency_matrix = _rs.build_adjacency_matrix

# A pyclass is not a dataclass, and `dataclasses.replace()` is load-bearing
# here -- `deterministic/stages/apply_placements.py` rebuilds both `Component`
# and `Netlist` with it. See `_contract_dataclass_compat` for the mechanism.
# Each field spec mirrors the pinned pre-migration oracle
# (`tests/core/_netlist_py_oracle.py`) field-for-field: annotation, literal
# default or default_factory, and the init/repr flags.
_install_dataclass_fields(
    Pin,
    (
        _contract_field("name", "str"),
        _contract_field("number", "str"),
        _contract_field("position", "tuple[float, float]"),
        _contract_field("net", "str | None", None),
        _contract_field("width", "float", 1.0),
        _contract_field("height", "float", 1.0),
        _contract_field("shape", "str", "rect"),
        _contract_field("layer", "str", "F.Cu"),
        _contract_field("drill", "float", 0.0),
        _contract_field("is_pth", "bool", False),
        _contract_field("roundrect_ratio", "float", 0.25),
        _contract_field("pad_rotation_deg", "float", 0.0),
    ),
    module=__name__,
)
_install_dataclass_fields(
    Component,
    (
        _contract_field("ref", "str"),
        _contract_field("footprint", "str"),
        _contract_field("bounds", "tuple[float, float]"),
        _contract_field("pins", "list[Pin]", default_factory=list),
        _contract_field("net_class", "str", "Signal"),
        _contract_field("zone", "str | None", None),
        _contract_field("fixed", "bool", False),
        _contract_field("initial_position", "tuple[float, float] | None", None),
        _contract_field("initial_rotation", "int | None", None),
        _contract_field("initial_side", "int | None", None),
        _contract_field("attributes", "dict[str, str]", default_factory=dict),
        _contract_field("tags", "frozenset", default_factory=frozenset),
        _contract_field("sheetpath", "str | None", None),
    ),
    module=__name__,
)
_install_dataclass_fields(
    Net,
    (
        _contract_field("name", "str"),
        _contract_field("pins", "list[tuple[str, str]]"),
        _contract_field("net_class", "str", "Signal"),
        _contract_field("weight", "float", 1.0),
        _contract_field("max_current", "float", 0.0),
        _contract_field("voltage_class", "str", "LV"),
    ),
    module=__name__,
)
# The computed indices are `repr=False` on the original dataclass; the
# init/repr flags mirror the oracle exactly.
_install_dataclass_fields(
    Netlist,
    (
        _contract_field("components", "list[Component]", default_factory=list),
        _contract_field("nets", "list[Net]", default_factory=list),
        _contract_field("_component_index", "dict[str, int]", default_factory=dict, repr=False),
        _contract_field("_net_index", "dict[str, int]", default_factory=dict, repr=False),
        _contract_field(
            "_component_nets", "dict[str, list[str]]", default_factory=dict, repr=False
        ),
    ),
    module=__name__,
)


def compute_eigenvector_centrality(adjacency: Array) -> Array:
    """
    Compute eigenvector centrality for each node in the graph.

    Eigenvector centrality measures a node's importance based on the
    importance of its neighbors. It corresponds to the eigenvector
    associated with the largest eigenvalue of the adjacency matrix.

    Args:
        adjacency: (N, N) weighted adjacency matrix.

    Returns:
        (N,) array of centrality scores, normalized to sum to 1.0.

    Not migrated to Rust — see the module docstring's R3 note. The three
    return paths have deliberately different dtypes (``n == 0`` is float64,
    ``n == 1`` is float32, ``n >= 2`` follows the input); that is preserved
    here by leaving the code untouched.
    """
    n = adjacency.shape[0]
    if n == 0:
        return np.array([])
    if n == 1:
        return np.array([1.0], dtype=np.float32)

    # For symmetric matrices, eigh returns eigenvalues in ascending order
    eigenvalues, eigenvectors = np.linalg.eigh(adjacency)

    # The leading eigenvector is the last one (largest eigenvalue)
    centrality = eigenvectors[:, -1]

    # Eigenvector centrality should be non-negative (Perron-Frobenius theorem)
    centrality = np.abs(centrality)

    # Normalize so they sum to 1.0
    total = np.sum(centrality)
    if total > 0:
        centrality = centrality / total

    return centrality


__all__ = [
    "Array",
    "Component",
    "Net",
    "Netlist",
    "Pin",
    "build_adjacency_matrix",
    "compute_eigenvector_centrality",
]
