"""Type stubs for `temper_design_bundle_python.hypergraph_contracts`.

Compiled from `packages/temper-design-bundle/src/hypergraph_contracts.rs` —
the Orchestration plan Phase A unit U7 migration of
`temper_placer/core/hypergraph.py`'s `Coo` container (the typed I/O boundary
of the `temper_geometry.hypergraph_coo_matvec` kernel). Keep in sync with
that file.

The numpy-visible surface is preserved: `row`/`col`/`data` getters return
`np.ndarray` (int64 / int64 / dtype-preserved), and `@` returns a float64
`np.ndarray`. Construction accepts any object pyo3 can extract to the typed
`Vec` fields (numpy arrays, lists).
"""

from __future__ import annotations

import numpy as np

class Coo:
    @property
    def row(self) -> np.ndarray: ...
    @property
    def col(self) -> np.ndarray: ...
    @property
    def data(self) -> np.ndarray: ...
    @property
    def shape(self) -> tuple[int, int]: ...
    @property
    def nnz(self) -> int: ...

    def __init__(
        self,
        row: object,
        col: object,
        data: object,
        shape: tuple[int, int],
    ) -> None: ...

    @property
    def T(self) -> Coo: ...

    def __matmul__(self, other: object) -> np.ndarray: ...
