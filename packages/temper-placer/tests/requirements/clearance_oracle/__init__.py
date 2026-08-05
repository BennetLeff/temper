"""Oracle package for the REQ-SAFE-01 clearance validator differential.

The differential test uses ``clearance_oracle.clearance`` and
``clearance_oracle._copper`` as module attributes — importing the
submodules here so ``_oracle_pkg.clearance.check_domain_clearance``
resolves. The modules themselves are VERBATIM pre-migration copies.
"""

from tests.requirements.clearance_oracle import _copper  # noqa: F401
from tests.requirements.clearance_oracle import clearance  # noqa: F401
