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
_install_dataclass_fields(
    Pin,
    (
        "name",
        "number",
        "position",
        "net",
        "width",
        "height",
        "shape",
        "layer",
        "drill",
        "is_pth",
        "roundrect_ratio",
        "pad_rotation_deg",
    ),
)
_install_dataclass_fields(
    Component,
    (
        "ref",
        "footprint",
        "bounds",
        "pins",
        "net_class",
        "zone",
        "fixed",
        "initial_position",
        "initial_rotation",
        "initial_side",
        "attributes",
        "tags",
        "sheetpath",
    ),
)
_install_dataclass_fields(
    Net,
    ("name", "pins", "net_class", "weight", "max_current", "voltage_class"),
)
_install_dataclass_fields(
    Netlist,
    ("components", "nets", "_component_index", "_net_index", "_component_nets"),
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
