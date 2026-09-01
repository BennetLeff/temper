#!/usr/bin/env python3
"""Replay the repository-owned Net-41 corridor campaign driver."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from run_net41_corridor_campaign import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
