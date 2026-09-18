#!/usr/bin/env python3
"""Extract the .meas values from a batch ngspice log into JSON.

Reads lines of the form `  <name>   =   <value>` (ngspice `meas` output).
Usage: extract_meas.py <log> [<log> ...]
Prints one JSON object per log line with its measurement dict.
"""
import json
import re
import sys

MEAS = re.compile(r"^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*([-+0-9.eE]+)\s*(?:from=.*)?$")


def main() -> int:
    for log in sys.argv[1:]:
        vals = {}
        for line in open(log, errors="replace"):
            m = MEAS.match(line)
            if m and not line.strip().startswith("Error"):
                try:
                    vals[m.group(1)] = float(m.group(2))
                except ValueError:
                    pass
        print(json.dumps({log: vals}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
