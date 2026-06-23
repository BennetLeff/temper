"""
Smoke test for the coupled diff pair router import in
SequentialRoutingStage.

Background
----------
``SequentialRoutingStage`` (in
``temper_placer.deterministic.stages.sequential_routing``) imports the
``CoupledDiffPairRouter`` from ``experiments.diff_pair.coupled_router`` to
handle USB differential pairs. The import is wrapped in
``try/except ImportError`` because the coupled router lives in a
non-package ``experiments/`` directory at the package root, accessed
via a ``sys.path.insert`` hack. A failure of the import would set
``COUPLED_ROUTER_AVAILABLE = False`` and silently degrade USB diff
pair routing to separate single-ended routing.

This test guards against that silent failure mode: it asserts that the
coupled router module is present and importable, so the flag is True
and the production router uses the coupled path for USB pairs.
"""

import pytest

from temper_placer.deterministic.stages import sequential_routing


def test_coupled_router_imports_successfully() -> None:
    """The coupled diff pair router module is present and importable.

    Asserts the happy path: ``COUPLED_ROUTER_AVAILABLE`` is True after
    the production import resolves. This is the primary guard against
    silent degradation of USB diff pair routing.
    """
    assert sequential_routing.COUPLED_ROUTER_AVAILABLE is True, (
        "experiments.diff_pair.coupled_router did not import successfully. "
        "USB diff pairs will silently route as separate single-ended pairs."
    )
