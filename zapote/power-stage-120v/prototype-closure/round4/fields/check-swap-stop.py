#!/usr/bin/env python3
"""Software negative control: inject swap-counter growth without causing paging.

This exercises controller termination, not an actual memory-pressure event.
"""

import importlib.util
import sys
from pathlib import Path

path = Path(__file__).with_name("watch.py")
spec = importlib.util.spec_from_file_location("watch_under_test", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
samples = iter((0, 300 * 1024**2))
module.swapout_bytes = lambda: next(samples)
receipt = sys.argv[1]
sys.argv = [str(path), "--receipt", receipt, "--rss-gib", "0.5", "--seconds", "15",
            "--", sys.executable, "-c", "import time; time.sleep(10)"]
module.main()
