#!/usr/bin/env python3
"""Render the inventory's numeric tables for the readable summary."""

import collections
import json
import os
from pathlib import Path

D = Path(os.environ.get("DECOMP_WORKDIR", "/tmp/decomp-map"))
inv = json.load(open(D / "inventory.json"))
rows = inv["units"]

print("### probes\n")
for k, v in inv["probes"].items():
    print(f"- `{k}` ran={v['ran']} -- {v['command']}")

print("\n### disposition x evidence class\n")
c = collections.Counter()
l = collections.Counter()
for r in rows:
    c[(r["disposition"], r["evidence_class"])] += 1
    l[(r["disposition"], r["evidence_class"])] += r["loc"]
print("| disposition | evidence class | files | LOC |")
print("|---|---|---:|---:|")
for k in sorted(c, key=lambda x: (-l[x], x)):
    print(f"| `{k[0]}` | `{k[1]}` | {c[k]} | {l[k]:,} |")

print("\n### by kind\n")
c2 = collections.Counter()
l2 = collections.Counter()
for r in rows:
    c2[r["kind"]] += 1
    l2[r["kind"]] += r["loc"]
for k in c2:
    print(f"- {k}: {c2[k]} files, {l2[k]:,} LOC")

print("\n### E2 (execution-absent) units, largest first\n")
e2 = sorted(
    (r for r in rows if r["evidence_class"] == "E2-execution-absent"), key=lambda r: -r["loc"]
)
print(f"total {len(e2)} files, {sum(r['loc'] for r in e2):,} LOC")
print("\n| LOC | path |")
print("|---:|---|")
for r in e2[:60]:
    print(f"| {r['loc']} | `{r['path']}` |")

print("\n### live on a production-path probe, with a same-stem Rust file (port candidates)\n")
pt = sorted((r for r in rows if r["disposition"] == "port-to-rust"), key=lambda r: -r["loc"])
print(f"total {len(pt)} files, {sum(r['loc'] for r in pt):,} LOC")
print("\n| LOC | path | probes that entered it |")
print("|---:|---|---|")
for r in pt[:30]:
    print(f"| {r['loc']} | `{r['path']}` | {', '.join(r['executed_in'])} |")

print("\n### imported but never entered on ANY probe (strong smell, not proof)\n")
io_ = [r for r in rows if not r["executed_in"] and r["imported_only_in"]]
io_.sort(key=lambda r: -r["loc"])
print(f"total {len(io_)} files, {sum(r['loc'] for r in io_):,} LOC")
print("\n| LOC | path | imported in |")
print("|---:|---|---|")
for r in io_[:40]:
    print(f"| {r['loc']} | `{r['path']}` | {', '.join(r['imported_only_in'])} |")

print(
    "\n### `delete-with-its-tests-candidate` -- cold on every production probe, only test importers\n"
)
dw = sorted(
    (r for r in rows if r["disposition"] == "delete-with-its-tests-candidate"),
    key=lambda r: -r["loc"],
)
print(f"total {len(dw)} files, {sum(r['loc'] for r in dw):,} LOC. NONE of these is `delete-now`:")
print("each one's deletion also removes test coverage, so each needs a reviewer's")
print("explicit nod, and several are pinned by an oracle.\n")
print("| LOC | path | test importers |")
print("|---:|---|---:|")
for r in dw:
    print(
        f"| {r['loc']} | `{r['path'].replace('packages/temper-placer/src/temper_placer/', 'TP/')}` | {r['static']['n_python_importers']} |"
    )
