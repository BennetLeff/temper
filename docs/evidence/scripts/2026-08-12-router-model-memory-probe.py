"""VENDORED VERBATIM from `spike/router-orchestration-rust` (PR #1064), where
this probe was written and first measured. Copied onto
`feat/constraint-model-rust-repr` unchanged so plan 2026-08-12-002 U1's
before/after bytes-per-variable numbers are reproducible from that branch
alone. See `2026-08-12-constraint-model-rust-representation.md` for the
measurements, and `2026-08-12-router-model-memory-probe-distinct-keys.py`
for why this probe's `net_channel_vars` is degenerate.

provenance: commit=6b669db2a6ff3943954cc95e7f467429431fbf2e dirty=false
"""
import os, sys, gc
import temper_design_bundle_python as t
mb = t.model_builder

def rss_kb():
    for line in open('/proc/self/status'):
        if line.startswith('VmRSS:'):
            return int(line.split()[1])

N = int(sys.argv[1]) if len(sys.argv) > 1 else 2_000_000

# Realistic edge_id: "{layer}_E{i}_({x:.6}, {y:.6})_({x:.6}, {y:.6})"
def edge_id(i):
    return "F.Cu_E%d_(%.6f, %.6f)_(%.6f, %.6f)" % (i, 123.456789, 98.765432, 124.567891, 99.876543)

sample = edge_id(1234567)
print("edge_id len:", len(sample), "->", sample)
print("var name len:", len("uses_N%d_%s" % (57, sample)))

gc.collect(); base = rss_kb()
cm = mb.ConstraintModel()
for i in range(N):
    cm.add_variable(mb.NetChannelVar(
        name="uses_N%d_%s" % (i % 110, edge_id(i % 204490)),
        net_idx=i % 110,
        channel_id=edge_id(i % 204490)))
gc.collect(); after = rss_kb()
d = after - base
print("N=%d  RSS delta=%.3f GB  bytes/var=%.1f" % (N, d/1048576, d*1024/N))

# Now the .variables materialization cost (a FRESH PyList per access)
gc.collect(); b2 = rss_kb()
lst = cm.variables
gc.collect(); a2 = rss_kb()
print(".variables PyList delta=%.3f GB  bytes/entry=%.1f  len=%d" % ((a2-b2)/1048576, (a2-b2)*1024/N, len(lst)))
print("TOTAL model+one-list RSS = %.3f GB for N=%d" % ((a2-base)/1048576, N))
# extrapolate
FULL = 22_493_900
print("EXTRAPOLATED to %d NetChannelVars: model=%.2f GB, +1 PyList=%.2f GB, total=%.2f GB" % (
    FULL, d*1024*FULL/N/1e9, (a2-b2)*1024*FULL/N/1e9, (a2-base)*1024*FULL/N/1e9))
