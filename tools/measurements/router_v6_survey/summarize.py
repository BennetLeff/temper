"""Router-v6 migration survey: bucket totals.

Joins ``classification.csv`` against ``measure.py``'s per-file numbers and
prints the bucket table the survey document cites. Fails loudly if the
classification and the measured file set disagree, so the two cannot drift.

Usage:
    python tools/measurements/router_v6_survey/measure.py \\
        packages/temper-placer/src/temper_placer/router_v6 . > rows.json
    python tools/measurements/router_v6_survey/summarize.py rows.json
"""

from __future__ import annotations

import csv
import json
import pathlib
import sys

PREFIX = "packages/temper-placer/src/temper_placer/router_v6/"
HERE = pathlib.Path(__file__).parent


def main() -> None:
    rows = json.load(open(sys.argv[1]))
    for r in rows:
        r["key"] = r["path"][len(PREFIX) :].removesuffix(".py")
    by_key = {r["key"]: r for r in rows}
    nondeleg = {k for k, r in by_key.items() if not r["delegates"]}

    with open(HERE / "classification.csv") as fh:
        cls = {row["module"]: row["bucket"] for row in csv.DictReader(fh)}

    missing = nondeleg - set(cls)
    extra = set(cls) - nondeleg
    if missing or extra:
        print(f"MISMATCH missing={sorted(missing)} extra={sorted(extra)}")
        raise SystemExit(1)

    totals: dict[str, list[int]] = {}
    for key, bucket in cls.items():
        r = by_key[key]
        t = totals.setdefault(bucket, [0, 0, 0, 0])
        t[0] += 1
        t[1] += r["stmts"]
        t[2] += r["stmts_nodoc"] - r["imports"]
        t[3] += r["loc"]

    grand = [sum(t[i] for t in totals.values()) for i in range(4)]
    print(f"{'bucket':10s} {'files':>6s} {'stmts':>7s} {'exec':>7s} {'loc':>7s} {'%stmts':>7s}")
    for bucket in sorted(totals, key=lambda b: -totals[b][1]):
        files, stmts, execs, loc = totals[bucket]
        pct = 100 * stmts / grand[1]
        print(f"{bucket:10s} {files:6d} {stmts:7d} {execs:7d} {loc:7d} {pct:6.1f}%")
    print(f"{'TOTAL':10s} {grand[0]:6d} {grand[1]:7d} {grand[2]:7d} {grand[3]:7d}")

    deleg = [r for r in rows if r["delegates"]]
    print(
        f"\n(already delegating: {len(deleg)} files, "
        f"{sum(r['stmts'] for r in deleg)} stmts, "
        f"{sum(r['loc'] for r in deleg)} loc)"
    )


if __name__ == "__main__":
    main()
