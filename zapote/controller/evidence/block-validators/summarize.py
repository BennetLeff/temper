#!/usr/bin/env python3
"""Summarise results/*.json (raw validator reports) into summary.json.

Per run: process exit code, overall status, pass/fail/indeterminate counts,
and the failing / indeterminate findings grouped by rule (message patterns
with UUIDs collapsed).  No verdict logic: it only counts what the Rust
validators emitted.
"""
import collections
import json
import re
import sys
from pathlib import Path

out = Path(sys.argv[1])
summary = {}
for path in sorted((out / "results").glob("*.json")):
    report = json.loads(path.read_text())
    exit_code = (out / "results" / (path.stem + ".exit")).read_text().strip()
    counts = collections.Counter(f["status"] for f in report["findings"])
    groups = collections.defaultdict(lambda: collections.Counter())
    for f in report["findings"]:
        if f["status"] != "pass":
            msg = re.sub(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "<uuid>", f["message"])
            groups[f"{f['status']} {f['rule']}"][msg] += 1
    summary[path.stem] = {
        "exit_code": int(exit_code),
        "status": report["status"],
        "pass": counts["pass"], "fail": counts["fail"], "indeterminate": counts["indeterminate"],
        "non_pass_by_rule": {k: dict(v) for k, v in sorted(groups.items())},
    }
(out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
for name, s in summary.items():
    print(f"{name:60s} exit={s['exit_code']} {s['status']:13s} pass={s['pass']:3d} fail={s['fail']:3d} indet={s['indeterminate']:2d}")
