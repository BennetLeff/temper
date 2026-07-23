"""CP-SAT constraint handler package.

Each constraint type is encoded in its own module, registered via
the ``register_handler`` decorator. The dispatch orchestrator in
``encoder.py`` uses ``HANDLER_REGISTRY`` with ``assert_never``
exhaustiveness checking.
"""

from __future__ import annotations

from temper_placer.placer.cp_sat.handlers._protocol import (
    AssumptionLiteral,
    ConstraintHandler,
)
from temper_placer.placer.cp_sat.handlers._registry import (
    HANDLER_REGISTRY,
    register_handler,
)

__all__ = [
    "AssumptionLiteral",
    "ConstraintHandler",
    "HANDLER_REGISTRY",
    "register_handler",
]
