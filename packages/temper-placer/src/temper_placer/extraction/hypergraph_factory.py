"""
Factory for creating PhysicsHypergraph instances from Netlists.

This module handles the complexity of parsing netlists, filtering global nets,
and extracting physical attributes to populate the clean PhysicsHypergraph
data structure.

The hypergraph construction migrated to Rust (``temper_design_bundle_python``,
``hypergraph_factory.rs``) under the Wave 4 Phase 4 leftovers slice — the
home crate is ``temper-design-bundle`` because the factory consumes the
``Netlist`` contract pyclasses. This module keeps the pre-migration public
API unchanged: ``HypergraphFactory`` is a Python wrapper that owns the
KTD9 boundary assembly, and the Rust ``HypergraphFactory`` pyclass does the
filtering/classification/ordering compute underneath.

Boundaries kept Python-side (argued in ``hypergraph_factory.rs`` and
``packages/temper-design-bundle/VERIFICATION.md``):

- **COO triplet assembly**: ``rows``/``cols``/``data`` are collected into a
  ``Coo`` (``temper_placer.core.hypergraph.Coo``, a plain-array container --
  see its docstring). This used to be ``scipy.sparse.coo_matrix``; that
  changed 2026-08-07 (``docs/evidence/2026-08-07-scipy-keeps-re-triage.md``
  Sec 3) once triage found the "sparse construction semantics are not
  reimplementable" premise did not survive contact with the actual code: by
  the time ``coo_matrix``/``Coo`` is built, triplets are already
  deduplicated per net (the ``set(conn)`` below runs BEFORE construction),
  so there is no duplicate-entry summation-order ambiguity to reproduce, and
  the sole consumer (``PhysicsHypergraph.compute_node_degrees``/
  ``compute_edge_degrees``) is an order-invariant reduction. Retiring scipy
  here needed no new Rust: the Rust ``HypergraphFactory`` already returns
  the deduplicated ``connected_indices`` this module assembles into triplets.
- **numpy casts**: every ``np.array(..., dtype=np.float32)`` runs on the
  original Python objects (an int ``weight=7`` reaches numpy as the int,
  never through a Rust f64), so int-vs-float leaf conversion is numpy's.
- **CPython ``set`` iteration order**: the COO triplet ORDER per net comes
  from CPython's small-int set iteration. The Rust side returns each net's
  connected indices in pin order; ``set(connected_indices)`` below is the
  exact construction the pre-migration module performed, so iteration order
  (and therefore the triplet order) is CPython's on both sides.
- **value arithmetic**: ``width * height`` is computed by Python's
  ``__mul__`` on the original objects (int × int stays int).

Verification: bit-identical parity against the pinned pre-migration
implementation — including the COO triplets' (shape, nnz, data, row, col)
WITH triplet order, every array's ``(dtype, shape, tobytes())``, and the
physics classifications — is asserted by
``tests/core/test_hypergraph_factory_rust_differential.py`` (oracle:
``tests/core/_hypergraph_factory_py_oracle.py``, which still builds a real
``scipy.sparse.coo_matrix`` -- the pre-migration scipy path is retained
there, unused in production, as the differential's pinned oracle per R19)
and the closed-form properties in ``tests/core/test_hypergraph_factory_pbt.py``.
"""

from __future__ import annotations

import numpy as np
import temper_design_bundle_python as _tdb

from temper_placer.core.hypergraph import Coo, HypergraphIncidence, PhysicsHypergraph
from temper_placer.core.netlist import Netlist


class HypergraphFactory:
    """
    Builder for PhysicsHypergraph.

    The filtering, ref→index mapping, physics classification and connection
    extraction run in the Rust ``HypergraphFactory`` pyclass; this wrapper
    assembles the ``Coo`` triplet container and the PhysicsHypergraph (KTD9
    — see the module docstring).
    """

    def __init__(
        self, netlist: Netlist, ignore_global_nets: bool = False, global_net_threshold: int = 50
    ):
        self.netlist = netlist
        self.ignore_global_nets = ignore_global_nets
        self.global_net_threshold = global_net_threshold
        self._builder = _tdb.HypergraphFactory(
            netlist,
            ignore_global_nets=ignore_global_nets,
            global_net_threshold=global_net_threshold,
        )

    def build(self) -> PhysicsHypergraph:
        """
        Build and return the PhysicsHypergraph.
        """
        parts = self._builder.build()

        # COO triplets: per valid net, the connected component indices
        # collapsed through CPython's own set() — the exact construction the
        # pre-migration module performed (same members, same pin-order
        # insertion), so iteration order and the triplet order are CPython's
        # on both sides. data carries net.weight as the original object;
        # the float32 cast below is numpy's.
        rows = []
        cols = []
        data = []
        for net_idx, (weight, conn) in enumerate(
            zip(parts.hyperedge_weights, parts.connected_indices)
        ):
            for node_idx in set(conn):
                rows.append(node_idx)
                cols.append(net_idx)
                data.append(weight)

        # Assemble the plain-array COO container (triplets are already
        # deduplicated per net above -- see the module docstring's "COO
        # triplet assembly" boundary note for why no scipy sparse-matrix
        # construction semantics are needed here).
        if parts.n_edges > 0:
            values = np.array(data, dtype=np.float32)
        else:
            values = np.empty((0,), dtype=np.float32)

        shape = (parts.n_nodes, parts.n_edges)
        incidence_matrix = Coo(
            row=np.array(rows, dtype=np.int64),
            col=np.array(cols, dtype=np.int64),
            data=values,
            shape=shape,
        )

        return PhysicsHypergraph(
            incidence=HypergraphIncidence(
                matrix=incidence_matrix,
                node_weights=np.array(parts.node_weights, dtype=np.float32),
                hyperedge_weights=np.array(parts.hyperedge_weights, dtype=np.float32),
            ),
            node_refs=parts.node_refs,
            hyperedge_names=parts.hyperedge_names,
            edge_voltages=np.array(parts.edge_voltages, dtype=np.float32),
            edge_currents=np.array(parts.edge_currents, dtype=np.float32),
            edge_widths=np.array(parts.edge_widths, dtype=np.float32),
        )


def netlist_to_hypergraph(
    netlist: Netlist, ignore_global_nets: bool = False, global_net_threshold: int = 50
) -> PhysicsHypergraph:
    """Convenience wrapper for HypergraphFactory."""
    return HypergraphFactory(
        netlist, ignore_global_nets=ignore_global_nets, global_net_threshold=global_net_threshold
    ).build()
