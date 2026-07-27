"""Re-export shim: the clearance validator now lives in production code.

Moved to `temper_placer.requirements.validators.clearance` so the CP-SAT
encoder can import it without production depending on the test tree. This
shim keeps the existing `tests.requirements.validators.clearance` import
path working for the suite.
"""

from temper_placer.requirements.validators.clearance import *  # noqa: F401,F403
from temper_placer.requirements.validators.clearance import (  # noqa: F401
    IEC60335_REQUIREMENTS,
    VoltageDomain,
    _components_in_domain,
    _domain_boundary_pairs,
    _nets_domain_map,
    verify_iec60335_compliance,
)
