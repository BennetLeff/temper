"""Compatibility entry point for the root, provenance-pinned v2 launcher."""

import sys
from pathlib import Path

LAB = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(LAB))
import buck_v2

if __name__ == "__main__":
    raise SystemExit(buck_v2.main(["qualify", *sys.argv[1:]]))
