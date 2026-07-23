"""Bootstrap ``temper-placer/src`` onto ``sys.path``."""

from __future__ import annotations

import sys
from pathlib import Path


def setup_temper_placer_path(repo_root: Path) -> None:
    """Insert ``packages/temper-placer/src`` into ``sys.path`` if not already present."""
    src_path = repo_root / "packages" / "temper-placer" / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
