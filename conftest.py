"""Repo-root pytest configuration.

Exists to install the protected-measurement-artifact guard for every test
collected with the repo root as ``rootdir``. See
``scripts/_lib/pytest_artifact_guard.py`` for the guard's design and the
2026-08-04 incident that motivated it, and
``scripts/_lib/protected_artifacts.py`` for the registry of protected paths.

``packages/temper-placer/tests/conftest.py`` imports the same fixture, because
CI runs most of the suite as ``cd packages/temper-placer && pytest ...`` --
which makes that package the ``rootdir`` and leaves this file unloaded.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent
_SCRIPTS_DIR = _REPO_ROOT / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from _lib.pytest_artifact_guard import (  # noqa: E402
    protected_artifact_guard,  # noqa: F401  (imported to register the fixture)
    pytest_sessionstart,  # noqa: F401  (imported to register the hook)
)
