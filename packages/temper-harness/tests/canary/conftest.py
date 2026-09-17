"""The live canary is opt-in at collection, not skipped at run time.

A ``skipif`` would make "the instrument did not run" and "the instrument ran and
agreed" produce the same green line, which is precisely the confusion R12 exists to
prevent. So the module is not collected unless the operator asks for it -- and if it
*is* collected without a credential it fails with a typed blocked error rather than
quietly reporting success.

    TEMPER_HARNESS_CANARY=1 uv run pytest packages/temper-harness/tests/canary/test_canary_live.py

Add ``TEMPER_HARNESS_WRITE_CANARY_EVIDENCE=1`` to commit the run's evidence.
"""

from __future__ import annotations

import os

collect_ignore: list[str] = []
if not os.environ.get("TEMPER_HARNESS_CANARY"):
    collect_ignore.append("test_canary_live.py")
