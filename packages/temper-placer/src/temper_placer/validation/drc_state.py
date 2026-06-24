"""Crash-only fence state for the DRC fence.

The fence is either ``FENCED`` (the artifact is fresh and the schema
is valid) or ``NOT_FENCED`` (everything else).  There is no
``stale``, no ``skipped``, no mid-state — the property holds or it
does not, and the SM2 promotion gate fails on ``NOT_FENCED``.

The check is a single mtime comparison plus a schema-version lookup:

    fenced iff mtime(drc_artifact) > mtime(router_output) AND
                schema_version == "drcc.v1"

The router output is the .kicad_pcb produced by Router V6; the DRC
artifact is the ``drcc.v1.json`` schema file written by
:mod:`temper_placer.validation.drc_schema`.  A fresh artifact means
"we measured DRC on this exact board version"; a stale artifact
means "the board moved and we did not re-measure".
"""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path

# The wrapper schema version this fence validates against.  Must
# match :data:`temper_placer.validation.drc_schema.DRCC_V1_SCHEMA_VERSION`.
DRCC_V1 = "drcc.v1"


class FenceState(Enum):
    """Crash-only state of the DRC fence.

    The two values are exhaustive: the fence is either ``FENCED`` or
    ``NOT_FENCED``.  There is no third state.  A missing artifact, a
    stale artifact, a corrupt artifact, or a wrong-schema-version
    artifact are all ``NOT_FENCED`` — the gate fails loudly rather
    than silently passing on partial information.
    """

    FENCED = "fenced"
    NOT_FENCED = "not_fenced"

    @classmethod
    def check(
        cls,
        drc_artifact: Path,
        router_output: Path,
    ) -> "FenceState":
        """Return ``FENCED`` iff the artifact is fresh AND schema-valid.

        Args:
            drc_artifact: Path to the ``drcc.v1.json`` artifact written
                by the DRC runner.  Missing or unreadable → NOT_FENCED.
            router_output: Path to the board file the router produced.
                Missing or older than the artifact → NOT_FENCED.

        Returns:
            ``FenceState.FENCED`` when ``mtime(drc_artifact) > mtime(
            router_output)`` AND the artifact's
            ``schema_version == "drcc.v1"``; otherwise
            ``FenceState.NOT_FENCED``.

        The check is deliberately permissive on filesystem errors:
        a transient read failure on the artifact is treated as
        ``NOT_FENCED`` (fail the gate) rather than raising, so the
        gate fails loudly with a clear signal.
        """
        if not drc_artifact.exists():
            return cls.NOT_FENCED
        if not router_output.exists():
            return cls.NOT_FENCED
        try:
            artifact_mtime = drc_artifact.stat().st_mtime
            router_mtime = router_output.stat().st_mtime
        except OSError:
            return cls.NOT_FENCED
        if artifact_mtime <= router_mtime:
            return cls.NOT_FENCED
        try:
            data = json.loads(drc_artifact.read_text())
        except (json.JSONDecodeError, OSError, UnicodeDecodeError):
            return cls.NOT_FENCED
        if not isinstance(data, dict):
            return cls.NOT_FENCED
        if data.get("schema_version") != DRCC_V1:
            return cls.NOT_FENCED
        return cls.FENCED
