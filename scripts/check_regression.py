#!/usr/bin/env python3
# DEPRECATED: Use `python3 -m temper_placer.regression.cli run-corpus` instead.
#
# This script was removed from active CI in favour of the corpus regression
# runner (packages/temper-placer/src/temper_placer/regression/corpus_runner.py).
#
# RETIRED 2026-07-27: the corpus runner that replaced it is itself no longer
# reachable -- corpus_runner._run_board returns the retired-optimizer error
# for every valid board (the JAX optimizer and its stubs were removed in the
# cleanup C2 sweep). The `make regression` target and the `python-tests.yml`
# regression job that called it are both retired, so there is now no live
# caller of either script. Restoring this coverage needs a placement
# strategy that still exists.
#
# This stub is kept so that callers who haven't migrated get a clear message.
import sys

if __name__ == "__main__":
    print(
        "ERROR: check_regression.py has been retired. "
        "Use the corpus runner instead:\n"
        "  uv run python -m temper_placer.regression.cli run-corpus --json",
        file=sys.stderr,
    )
    sys.exit(1)
