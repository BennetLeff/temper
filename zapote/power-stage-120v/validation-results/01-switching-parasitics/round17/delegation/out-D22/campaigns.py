#!/usr/bin/env python3
"""Declare the full operating envelope; never silently omit an aborted case."""

import itertools
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    for step in (0.5, 0.25, 0.125):
        cases = []
        for bus, freq, resistance, esl in itertools.product(
            (170, 198), (35000, 60000), (2, 100), (1.06, 10)
        ):
            cases.append(
                {
                    "label": f"envelope-v{bus}-f{freq}-r{resistance}-e{esl}-s{step}",
                    "config": {
                        "bus": bus,
                        "freq": freq,
                        "resistance": resistance,
                        "esl": esl,
                        "step": step,
                        "cycles": 24 if freq == 35000 else 48,
                        "timeout": 7200 if step < 0.25 else 2400,
                        "options": "",
                    },
                }
            )
        (HERE / f"envelope-{step}.json").write_text(json.dumps(cases, indent=2) + "\n")


if __name__ == "__main__":
    main()
