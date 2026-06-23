"""
Single source of truth for the DRC fence soft-launch flip.

The :data:`DRC_FENCE_FAIL_ENABLED` flag controls whether per-stage
fence invariants that are in their 2-week WARNING-only soft-launch
period should hard-fail the pipeline run. The flag is read at
invariant-check time, not at import time, so flipping the env var
(:envvar:`TEMPER_DRC_FENCE_FAIL`) takes effect on the next run.

The current invariant using this flip is
``no_component_center_in_critical_bottleneck`` on
:class:`PhasedComponentAssignmentStage`. Other invariants in soft-launch
can opt in by calling :func:`is_drc_fence_fail_enabled`.
"""

from __future__ import annotations

import logging
import os

_LOGGER = logging.getLogger(__name__)


_ENV_VAR: str = "TEMPER_DRC_FENCE_FAIL"


def is_drc_fence_fail_enabled() -> bool:
    """Return True when the DRC fence should hard-fail on violations.

    Reads the :envvar:`TEMPER_DRC_FENCE_FAIL` env var on every call so a
    test can flip the flag mid-process by setting the variable. Values
    ``"1"``, ``"true"``, ``"yes"`` (case-insensitive) are truthy; any
    other value is falsy. The default (env var unset) is False - soft
    launch.
    """
    raw = os.environ.get(_ENV_VAR, "").strip().lower()
    return raw in ("1", "true", "yes", "on")


# Module-level constant for callers that want to read the snapshot once
# at import time. Tests that need runtime re-evaluation should call
# :func:`is_drc_fence_fail_enabled` instead.
DRC_FENCE_FAIL_ENABLED: bool = is_drc_fence_fail_enabled()
