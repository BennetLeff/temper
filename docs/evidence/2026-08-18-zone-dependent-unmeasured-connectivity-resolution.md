<!-- provenance: commit=11a7e7c52d21ebca3ff8ff06e6e3b941441189fd dirty=false (worktree agent-a68418bfe13ef8302, branched from main at 11a7e7c52. pcb/temper.kicad_pcb sha256 26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b verified unchanged before AND after this task -- every fill/route/DRC run below executes against a scratch copy under /tmp, never against the tracked tree. .venv is isolated to this worktree: `temper_placer.__file__` resolves under `.claude/worktrees/agent-a68418bfe13ef8302/packages/...`, verified before trusting any number. kicad-cli 10.0.5.) -->
---
title: "Resolving the 9 zone_dependent_unmeasured nets: genuinely open, not connected"
date: 2026-08-18
module: temper-placer
tags: [router, routing, pad-connectivity, zone-fill, drc, connectivity]
problem_type: routing-completion
status: measured
---

# The 9 `zone_dependent_unmeasured` nets: measured, not assumed — the answer is negative

**Bottom line up front.** All 9 nets `pad_connectivity_audit.py` marks
`zone_dependent_unmeasured` were tested against KiCad's own connectivity
engine on an honestly zone-filled board (`--refill-zones`, the same fill
engine the GUI uses, per PR #1298). **All 9 remain unconnected.** The
headline figure does **not** move. It stays **60/139 connected**, and the
routing gap is **79 nets** (70 confirmed `broken` + 9 now confirmed
`broken`-by-measurement), not 70. This is the non-flattering answer and it
is the measured one — three independent `--refill-zones` DRC runs agree
exactly (815 violations, 265 unconnected items, byte-identical net sets,
every run).

## 1. The 9 nets, by name, on the current committed board

Re-ran `pad_connectivity_audit.audit_pcb_file` directly against
`pcb/temper.kicad_pcb` (sha256 `26981fea2dbc...`, main `11a7e7c52`) —
**not** trusted from the 2026-08-17 doc, which was measured against a
different, older board (`fa067a952`, sha `9c1f4a37...`, dozens of router/
placement commits behind). The category counts and the net identities are
unchanged despite the board content changing underneath:

```
Counter({'broken': 70, 'connected': 60, 'zone_dependent_unmeasured': 9})
total nets 139
```

| net | pads | zone layers declared |
|---|---|---|
| `+170V_BUS` | 11 | B.Cu, F.Cu, In3.Cu, In4.Cu |
| `DC_BUS_RTN` | 8 | B.Cu, F.Cu, In3.Cu, In4.Cu |
| `PWR_RTN` | 15 | B.Cu, F.Cu, In3.Cu, In4.Cu |
| `SW_NODE` | 7 | B.Cu, F.Cu, In3.Cu, In4.Cu |
| `ac_n` | 3 | B.Cu, In3.Cu, In4.Cu |
| `power_in.ntc-no` | 4 | B.Cu, F.Cu, In3.Cu, In4.Cu |
| `tank.c_tank1-p2` | 4 | B.Cu, F.Cu, In3.Cu, In4.Cu |
| `w1_1` | 4 | B.Cu, F.Cu, In3.Cu, In4.Cu |
| `w1_2` | 3 | B.Cu, F.Cu, In3.Cu, In4.Cu |

Every one of these has `pads_connected == 1`: the segment/via graph alone
does not join even two of the net's own pads — each pad is its own
singleton. This matches the M2/M2b "zone-fill missing" class named in
`docs/evidence/2026-08-17-unrouted-nets-rootcause-update.md` §4 exactly
(same 9 net names, unchanged identity across the intervening commits).

**The committed board's zone-fill state, re-verified**: 151 zone blocks
declared (`zone_layers_and_fill_stats`, not a naive grep), **0 with
`filled_polygon` data**. The handoff's "96 zones, zero fill" claim is
stale on the count (more zone generation has landed since) but its
qualitative finding — the committed artifact carries no fill geometry at
all — is still exactly true today.

## 2. Method: KiCad's own connectivity engine on an honestly-filled scratch board

`pad_connectivity_audit` is deliberately zone-blind (its own docstring:
"this audit does not attempt point-in-polygon zone-fill analysis"). To
answer the question it refuses to answer, I used **KiCad's own DRC
connectivity check** — the `unconnected_items` report, which is the
ratsnest/connectivity engine, not a DRC rule — run against a **scratch
copy** with `--refill-zones --save-board` (PR #1298's own honest-measurement
flag, the same fill engine the KiCad GUI uses):

```
cp pcb/temper.kicad_pcb  <scratch>/scratch.kicad_pcb
cp pcb/temper.kicad_pro  <scratch>/scratch.kicad_pro
kicad-cli pcb drc --refill-zones --save-board --format json \
    --severity-all -o drc_report.json scratch.kicad_pcb
```

Result: **815 violations, 265 `unconnected_items` entries.** Each
`unconnected_items` entry is one required-but-missing ratsnest edge
between two connectivity clusters (pad, via, track segment, or a filled
zone island) — computed by KiCad's real connectivity engine, which *does*
see filled-zone copper (unlike the audit). If a net's pads all end up in
one electrical cluster after the fill, that net contributes zero
`unconnected_items` entries. `pcb/temper.kicad_pcb` itself was **never
opened for writing** — sha256 verified unchanged before and after (§5).

### Validation against known-answer nets (both directions, full population — not a sample)

| Population | Expected in `unconnected_items` post-refill? | Measured |
|---|---|---|
| 60 `connected` nets | **No** (already fully joined by real copper) | **0/60** appear — 0 false positives |
| 70 `broken` nets | **Yes** (segment/via graph fails, and no zone rescues them either — this is the positive control, since a `--refill-zones` run *could* have silently rescued some) | **70/70** appear — every one still flagged, none rescued |

This is stronger than the "check a handful" bar in the task brief — it's
the **full 130-net known-answer population**, not a sample, and it checks
both directions (no false positives on the connected side, no silent
rescues on the broken side — the same null-result-with-positive-control
standard PR #1298 used for `via_dangling`, since a rescue *did* happen for
gnd/+3V3-adjacent `broken`→`partial` transitions historically, so the
method is capable of detecting one if it occurred here).

### Determinism (3 independent runs)

Re-ran the identical `--refill-zones` DRC three times from three separate
scratch copies. **Byte-identical**: 815 violations, 265 unconnected items,
and the exact same 79-net `unconnected_items` net-name set, every run. All
9 target nets present in every run.

## 3. Verdict per net: all 9 remain unconnected, even filled

```
+170V_BUS        -> still unconnected post-refill
DC_BUS_RTN       -> still unconnected post-refill
PWR_RTN          -> still unconnected post-refill
SW_NODE          -> still unconnected post-refill
ac_n             -> still unconnected post-refill
power_in.ntc-no  -> still unconnected post-refill
tank.c_tank1-p2  -> still unconnected post-refill
w1_1             -> still unconnected post-refill
w1_2             -> still unconnected post-refill
```

`unconnected_items` total distinct nets post-refill = **79**, exactly
`70 broken + 9 zone_dependent_unmeasured` from the zone-blind audit. Zone
fill rescues **zero** of the 9 — not a partial credit, a clean zero.

### Why: the zones fill, but fragment into disjoint islands that don't reach each other

This is not "the zone never fills." Direct inspection of the scratch
board's `filled_polygon` geometry shows real copper for all 9 nets —
e.g. `+170V_BUS` has **19 separate filled-polygon islands** across its 4
declared layers to serve 11 pads; `PWR_RTN` has **26** islands for 15
pads. `w1_1` is the cleanest illustration: its `unconnected_items` entries
are **exclusively zone-to-zone** (`Zone[w1_1] on B.Cu <-> Zone[w1_1] on
In3.Cu`, `F.Cu <-> B.Cu`, `F.Cu <-> In3.Cu` — 3 edges, i.e. a spanning
tree over 4 clusters), never a bare pad — consistent with each of w1_1's 4
THT pads locally uniting its own nearby zone fragment across all 4 layers
through its own barrel, while the 4 pads' *separate* local islands never
physically touch each other. The fill exists; it is fragmented into
per-location islands that don't bridge distinct pads. This is the same
mechanism as the handoff's §13 `isolated_copper` characterization
(109-114 fragments, 47% HV-domain) — not a coincidence, the same
carve/clearance-driven fragmentation is what starves these 9 nets of a
real connection even once "filled."

## 4. Corrected headline figure

**No correction — the flattering direction did not hold.** 60/139
connected stands. The 9 `zone_dependent_unmeasured` nets convert from
"cannot measure" to **confirmed `broken`**, so the honestly-measured
routing gap is **79 nets, not 70**, and the pre-existing "79 unrouted"
figure the project was already citing was the correct one all along — the
audit's own `zone_dependent_unmeasured` bucket was correctly refusing to
call these `broken` on the audit's own zone-blind evidence, but the
now-added zone-fill measurement resolves the "cannot measure" into a
definite, triple-confirmed "no."

**If `pad_connectivity_audit.category` is to report a live, always-current
number** rather than being read once and left stale, it needs a
`--refill-zones` connectivity input (this method, or equivalent) wired in
as a fourth data source alongside pads/segments/vias — today it has no way
to move a net out of `zone_dependent_unmeasured` on its own. That wiring is
out of this task's scope (measurement only, no code changes to the audit
or the router); flagged here for whoever picks up `category`'s stated
purpose ("the partition a report should actually act on").

## 5. Hard-rule compliance

- `pcb/temper.kicad_pcb` never opened for writing. sha256
  `26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b`
  verified identical before this task's first command and after its last.
  Every `--refill-zones`/`--save-board` run executed against a scratch
  copy under `/tmp`, outside the repo and outside the worktree's tracked
  tree.
- No clearance/creepage/copper-weight/DRU threshold read, touched, or
  reasoned about. `drc_ceiling.json` untouched.
- No oracle re-pinning; no `_*_py_oracle.py` files touched.
- `.venv` isolation verified: `temper_placer.__file__` resolves under
  `.claude/worktrees/agent-a68418bfe13ef8302/packages/temper-placer/...`
  before any number in this document was trusted.
- `git stash` never used.

## 6. Cleanup

Scratch board copies and DRC JSON reports (`/tmp/.../scratchpad/board_work/`,
~8MB) removed after this document was written; nothing under `/tmp` is
referenced by anything outside this task.
