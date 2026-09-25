#!/usr/bin/env python3
"""Run a disposable ngspice interrupt probe; never targets another PID."""
from pathlib import Path
import os
import signal
import subprocess
import time

HERE = Path(__file__).resolve().parent
LOG = HERE / "probe.log"
PARTIAL = HERE / "probe-partial.tsv"
for path in (LOG, PARTIAL):
    path.unlink(missing_ok=True)

cmd = ["ngspice", "-b", "-o", str(LOG), str(HERE / "probe.cir")]
started = time.monotonic()
proc = subprocess.Popen(cmd, cwd=HERE, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
pid = proc.pid
time.sleep(1.0)
if proc.poll() is not None:
    raise SystemExit(f"probe ended before interrupt: pid={pid} rc={proc.returncode}")
os.kill(pid, signal.SIGINT)
try:
    stdout, stderr = proc.communicate(timeout=8.0)
except subprocess.TimeoutExpired:
    proc.kill()
    stdout, stderr = proc.communicate()
    raise SystemExit(f"probe did not exit after SIGINT: pid={pid}")
elapsed = time.monotonic() - started
(HERE / "transport.stdout").write_bytes(stdout)
(HERE / "transport.stderr").write_bytes(stderr)
(HERE / "result.txt").write_text(
    f"pid={pid}\nreturncode={proc.returncode}\nelapsed_s={elapsed:.3f}\n"
    f"partial_export_exists={PARTIAL.exists()}\n"
    f"partial_export_bytes={PARTIAL.stat().st_size if PARTIAL.exists() else 0}\n"
)
print((HERE / "result.txt").read_text(), end="")
