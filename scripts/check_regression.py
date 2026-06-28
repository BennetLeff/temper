#!/usr/bin/env python3
# DEPRECATED: Use `python3 -m temper_placer.regression.cli run-corpus` instead.
#
# This script was removed from active CI in favour of the corpus regression
# runner (packages/temper-placer/src/temper_placer/regression/corpus_runner.py).
# The `make regression` target and `python-tests.yml` regression job now call
# the corpus runner directly.
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
