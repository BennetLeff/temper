"""Shared loader for ``power_pcb_dataset/drc_ceiling.json``.

Three CI gates each read and parse this one file:

* ``scripts/check_drc_ceiling_approval.py`` -- the R27 raise-approval gate
  (compares the file at HEAD against the merge-base snapshot);
* ``scripts/check_measurement_provenance.py`` -- the input-freshness gate
  (walks the file's records and their ``provenance`` blocks);
* ``scripts/ci_check_drc.py`` -- the ratchet entry point (feeds the parsed
  dict to ``DrcRatchet.load_data`` for entry construction).

Before this module existed each gate carried its own ``json.loads`` of the
same file -- three copies of one loader, free to drift apart. This module is
the single read+parse entry point. The gates deliberately KEEP their own
fail-closed error *formatting* (each has a distinct message contract pinned
by its tests -- e.g. ``check_drc_ceiling_approval.py`` must say "malformed
ceiling JSON at HEAD" vs "at merge-base <sha>"), so the loader raises
``json.JSONDecodeError`` uncaught on malformed JSON, exactly as a bare
``json.loads`` did -- every caller already wraps this exception type.

Boundary note: the loader lives in ``scripts/_lib`` (repo-internal tooling)
on purpose. ``DrcRatchet`` in
``packages/temper-placer/src/temper_placer/regression/drc_ratchet.py`` does
NOT import it -- that package deliberately never depends on repo-internal
``scripts/`` (see its own ``_sha256_file`` comment for the boundary
argument) -- so ``DrcRatchet.load()`` keeps its own ``json.load`` and
delegates the entry construction to ``DrcRatchet.load_data``. The shared
loader is for the scripts that sit next to it.
"""

from __future__ import annotations

import json
from pathlib import Path

# The one repo-relative path all three gates read. check_drc_ceiling_approval
# defaulted this exact literal before; ci_check_drc and
# check_measurement_provenance hardcoded it inline.
CEILING_RELPATH = "power_pcb_dataset/drc_ceiling.json"


def load_ceiling(path: str | Path) -> dict:
    """Read and parse the DRC ceiling file at *path*.

    Returns the raw parsed JSON object -- the exact structure each gate
    already constructed with its own ``json.loads`` call (a ``dict`` with
    ``"boards"``, ``"_goal"``, ``"_march"`` keys for the real file), so no
    consumer's comparison logic changes.

    Raises:
        json.JSONDecodeError: the file's content is not valid JSON
            (propagated uncaught -- every caller already formats its own
            fail-closed message around this exact exception type).
        OSError: the file cannot be read (callers already guard existence
            before calling).
    """
    return json.loads(Path(path).read_text(encoding="utf-8"))


def parse_ceiling_text(text: str) -> dict:
    """Parse ``drc_ceiling.json`` content from a string.

    Used by ``check_drc_ceiling_approval.py`` for the merge-base snapshot,
    which arrives as ``git show <ref>:<path>`` output rather than a file on
    disk. Same contract as ``load_ceiling``: returns the raw dict, raises
    ``json.JSONDecodeError`` on malformed content.
    """
    return json.loads(text)
