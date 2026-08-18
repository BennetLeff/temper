"""
Pinned Python oracle for ``temper_placer/core/hypergraph.py``'s
``Coo.__matmul__`` (Rust orchestration plan, Phase A unit U7).

This file is a VERBATIM copy of the pre-migration ``Coo.__matmul__``
scatter-add semantics (``np.bincount`` with ``minlength`` extension and
negative-column fancy-index wrapping) as of commit ``edc19ffa`` of
``packages/temper-placer/src/temper_placer/core/hypergraph.py``.

Provenance of THIS file (2026-08-18)
------------------------------------
The accepted pin used to live inline in
``tests/core/test_core_graph_cluster_rust_differential.py``, and
``test_hypergraph_coo_rust_differential.py::test_oracle_verbatim`` compared
its own inline copy against it with ``inspect.getsource``. That host file was
deleted on 2026-08-17 by the surface-area sweep (``35e3f914a``, merged as
``caec25d6`` / #1314) as collateral to removing ``core/graph.py`` and
``core/power_topology.py`` -- it was a shared oracle host for seven modules
but was retired on the basis of two of them being dead. See
``docs/evidence/2026-08-17-surface-area-sweep-and-gate.md``.

The sweep explicitly checked ``scripts/oracle_hashes.json`` and correctly
found no entry for these clusters. That check could not protect this oracle,
because this oracle was never a registered ``_*_py_oracle.py`` file -- it was
an inline block guarded only by a cross-module ``inspect.getsource``
assertion. Extracting it here restores ``test_oracle_verbatim``'s
counterparty AND moves it onto the registry-backed mechanism, so the next
sweep sees it. The text below is byte-identical to the deleted copy at
``35e3f914a^``; no semantics changed in the move.

DO NOT EDIT THE SEMANTICS. This is the oracle the Rust pyo3 pyclass
(``temper_design_bundle_python.hypergraph_contracts.Coo``) must reproduce
bit-identically; any edit here silently weakens the differential proof. If
the module's contract changes, the oracle must be re-pinned from the new
base first.
"""

from __future__ import annotations

import numpy as np


def _oracle_coo_matmul(row, col, data, shape, other):
    n_rows = shape[0]
    if int(data.shape[0]) == 0:
        return np.zeros(n_rows, dtype=np.float64)
    contributions = data.astype(np.float64) * other[col]
    return np.bincount(row, weights=contributions, minlength=n_rows)
