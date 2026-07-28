"""Re-export shim: geometry helpers moved into production code.

Now live at `temper_placer.requirements.validators._geometry`, alongside the
clearance validator, so the CP-SAT encoder can use them without production
importing from the test tree.
"""

from temper_placer.requirements.validators._geometry import *  # noqa: F401,F403
from temper_placer.requirements.validators._geometry import (  # noqa: F401
    _distance,
)
