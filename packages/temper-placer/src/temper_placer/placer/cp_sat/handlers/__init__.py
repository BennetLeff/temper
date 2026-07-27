"""CP-SAT constraint handler package.

Each constraint type is encoded in its own module, registered via
the ``register_handler`` decorator. The dispatch orchestrator in
``encoder.py`` uses ``HANDLER_REGISTRY`` with ``assert_never``
exhaustiveness checking.

Registration is a side effect of importing each concrete handler
module (the ``@register_handler`` decorator runs at module import
time and populates ``HANDLER_REGISTRY``). That import must not be
left to chance: relying on some other module to import the handlers
first makes ``HANDLER_REGISTRY`` completeness depend on import
order, which is invisible until a constraint type silently has no
handler. So every concrete handler module is imported here,
unconditionally, as the single source of truth for registration.
"""

from __future__ import annotations

# Import every concrete handler module so its @register_handler
# decorator runs and populates HANDLER_REGISTRY. These imports are
# for their side effect only (registration), not for the names they
# bind, hence the `noqa: F401` on each -- see module docstring above.
from temper_placer.placer.cp_sat.handlers import adjacent as _adjacent  # noqa: F401
from temper_placer.placer.cp_sat.handlers import aligned as _aligned  # noqa: F401
from temper_placer.placer.cp_sat.handlers import anchored as _anchored  # noqa: F401
from temper_placer.placer.cp_sat.handlers import enclosing as _enclosing  # noqa: F401
from temper_placer.placer.cp_sat.handlers import keepout as _keepout  # noqa: F401
from temper_placer.placer.cp_sat.handlers import loop_area as _loop_area  # noqa: F401
from temper_placer.placer.cp_sat.handlers import onside as _onside  # noqa: F401
from temper_placer.placer.cp_sat.handlers import separated as _separated  # noqa: F401
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
