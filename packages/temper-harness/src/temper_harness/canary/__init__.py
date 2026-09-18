"""The live canary and the bounded concurrency probe.

Both are instruments rather than gates, and the distinction is the point:

* :mod:`temper_harness.canary.runner` needs a production credential, so it runs on
  demand and commits hashed evidence (KTD8). Until it has run, the recorded oracle is
  a reproducibility instrument and S0 makes no fidelity claim (R12).
* :mod:`temper_harness.canary.fanout` needs no model at all -- it is driven by
  whatever transport it is handed -- so its attribution assertions run in CI.

Keeping them together because they answer the same question from two directions: does
the client still say what it used to (shapes), and does it still account for every
call it made (lineage).
"""

from temper_harness.canary.fanout import CallOutcome, FanoutResult, probe_fanout
from temper_harness.canary.runner import (
    CanaryReport,
    ProbeComparison,
    recorded_shapes,
    run_canary,
    write_evidence,
)
from temper_harness.canary.shapes import compare_shapes, shape_digest, shape_of_exchange

__all__ = [
    "CanaryReport",
    "CallOutcome",
    "FanoutResult",
    "ProbeComparison",
    "compare_shapes",
    "probe_fanout",
    "recorded_shapes",
    "run_canary",
    "shape_digest",
    "shape_of_exchange",
    "write_evidence",
]
