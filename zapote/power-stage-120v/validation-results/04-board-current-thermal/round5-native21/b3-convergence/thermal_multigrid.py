"""Multigrid preconditioning for the layered board (python3 -m pip install pyamg==5.3.0)."""
import numpy as np
from pyamg import ruge_stuben_solver
from scipy.sparse.linalg import LinearOperator


def preconditioner(matrix):
    """Approximate inverse; the outer CG operator and residual remain float64."""
    hierarchy = ruge_stuben_solver(matrix.astype(np.float32), strength=("classical", {"theta": 0.1}),
                                  max_coarse=100, coarse_solver="splu",
                                  presmoother=("gauss_seidel", {"sweep": "forward"}),
                                  postsmoother=("gauss_seidel", {"sweep": "backward"}))
    cycle = hierarchy.aspreconditioner()
    return LinearOperator(matrix.shape, matvec=lambda v: (cycle @ v.astype(np.float32)).astype(np.float64),
                          dtype=np.float64)
