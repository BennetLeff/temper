<!-- provenance: commit=b11a78a5b660cdfa5f2caa19bdeda3fbbc4aa9cd dirty=true -->

<!-- worktree agent-aa5a446f9f5edfc36, branch fix/board-shorting-items, based on b11a78a5b (main). dirty=true because this document is committed together with itself (no board or code change accompanies it). kicad-cli 10.0.5 (AppImage extraction, matches the CI pin recorded in power_pcb_dataset/drc_ceiling.json's provenance), pcb/temper.kicad_dru regenerated from scripts/generate_kicad_dru.py immediately before every measurement below. Every number in this document was measured live in this session against pcb/temper.kicad_pcb at its current committed content (unchanged by this document); none are carried over unverified from a prior report. -->

# `shorting_items` (200) and `track_width` (199): root causes, and why the obvious `track_width` fix is not safe to ship

**Date:** 2026-08-11
**Board:** `pcb/temper.kicad_pcb` (unchanged — this is a diagnosis, no board or pipeline
code change is applied by this document)
**Disposition: no code change lands.** A precise, mechanical fix for
`track_width` exists and is documented below, but measurement shows it is not
safe to ship standalone — see §3. `shorting_items` requires router-internals
work (same-run collision-avoidance in Stage 4) that a prior, independent
investigation already scoped out of a bounded PR
(`docs/evidence/2026-07-30-router-copper-shorts.md`); this document reproduces
that same conclusion on the current, larger board and adds the causal test
the task asked for (§4: are the two categories the same tracks — no).

## 0. Baseline measurement

`temper_placer.validation._drc_api.run_drc`'s own protocol
(`kicad-cli pcb drc --all-track-errors --format json`, project + regenerated
`.kicad_dru` resolvable, in place next to `pcb/temper.kicad_pcb`):

| category | count |
|---|---|
| errors (total) | 1249 |
| `clearance` | 367–368 |
| `shorting_items` | 199–200 |
| `track_width` | 199 |
| `tracks_crossing` | 1 |
| `creepage` | 186–187 |

Matches `drc_ceiling.json`'s recorded figures and the task brief's 1,250
errors / 199 / 199 / 1, within the file's own documented ±1
`clearance`/`shorting_items` noise band
(`docs/evidence/2026-08-04-drc-measurement-determinism.md`).

## 1. `track_width` (199): one root cause, nine nets

`assign_trace_widths` (`packages/temper-placer/src/temper_placer/router_v6/trace_width_assignment.py`,
Stage 4.4) picks a net's emitted trace width via
`temper_geometry::determine_trace_width` — a three-bucket **keyword**
classifier on the net's own *name* (`AC_`/`HV_`/`HIGH_VOLTAGE` → `hv_width`;
`GND`/`VCC`/`VDD`/`VSS`/`POWER`/leading `+` → `power_width`; `GATE`/`DRIVE` →
`power_width * 0.6`; else `default_width`). This is **completely independent**
of the project's actual, authoritative net-class table
(`design_rules.TEMPER_NET_CLASSES` / `TEMPER_NET_ASSIGNMENTS`, loaded at
router-run time from `packages/temper-placer/configs/netclass_rules.yaml` —
the same table `scripts/generate_kicad_dru.py` compiles into
`pcb/temper.kicad_dru`'s enforced `track_width` rules, and the same table
`via_placement.py` already consults correctly for per-netclass via sizing).

Cross-referencing every `(segment ...)` in `pcb/temper.kicad_pcb` against its
declared net's assigned class and that class's `trace_width` finds exactly
**9 nets, 509 undersized segments**:

| net | assigned class | required width | actual width | segments |
|---|---|---|---|---|
| `discharge.k_dis1-nc` | HighVoltage | 3.0mm | 0.25mm | 104 |
| `hb.gate_hs.driver-p2` | HighVoltageIsolated | 2.0mm | 0.25mm | 97 |
| `hb.power_loop.q_high-g` | HighVoltage | 3.0mm | 0.25mm | 68 |
| `zcd` | HighVoltage | 3.0mm | 0.25mm | 55 |
| `a` | HighVoltage | 3.0mm | 0.25mm | 42 |
| `w1_2` | HighVoltage | 3.0mm | 0.25mm | 41 |
| `GATE_LS` | GateDriveHV | 0.4mm | 0.3048mm | 39 |
| `hb.gate_hs.driver-p1-1` | HighVoltageIsolated | 2.0mm | 0.25mm | 32 |
| `power_in.ntc-no` | HighVoltage | 3.0mm | 0.25mm | 31 |

All 9 are HV-domain nets whose real spelling contains none of the keyword
classifier's substrings (`zcd`, `a`, `w1_2`, `power_in.ntc-no`,
`discharge.k_dis1-nc`, `hb.power_loop.q_high-g`, `hb.gate_hs.driver-p1-1`,
`hb.gate_hs.driver-p2`) or matches a bucket whose hardcoded width was never
kept in sync with the real per-class figure (`GATE_LS` matches
`"GATE"` and gets `power_width * 0.6` = 0.3048mm against a real
`GateDriveHV` requirement of 0.4mm). 509 segments is more than 199 because
KiCad's `track_width` DRC evidently reports at a coarser granularity than
"one violation per undersized segment" (the DRC engine itself is a black box
here — not investigated further, since it does not change the diagnosis:
same 9 nets, same direction of error).

**This is the same defect class already fixed twice elsewhere in this
codebase for the identical reason** (`clearance_check.py`,
`clearance_engine.py`, both cited in the code's own bug-history comments):
a net-name keyword heuristic drifting out of sync with this project's actual,
authoritative net-class table.

## 2. Candidate fix and its measured effect

The mechanical fix: thread `pcb.design_rules` (already available at the
Stage 4.4 call site, and already threaded to `place_vias` immediately above
it in the same function — the identical, established pattern) into
`assign_trace_widths`, and when a net has a real class assignment, use that
class's own `trace_width_mm` instead of the keyword heuristic. This was
implemented, unit-tested (existing `test_trace_width_assignment.py` suite
green, 8/8; new direct calls confirmed all 9 nets now resolve to their exact
DRU-required width), and then reverted — see §3.

## 3. Why the fix is not shipped: it trades `track_width` for a larger regression

`assign_trace_widths` runs in Stage 4.4, **after** Stage 4's A* pathfinding
has already committed to a centerline. Router V6 has no implementation of
per-netclass corridor reservation during pathfinding at all — grep confirms
`routing_strategy: "wide_trace"` is a documented enum value
(`_zone_pour_stitch.py`'s own comment: "four documented values ... but this
check only [handles two]") that no code path implements. Stage 2's obstacle
map (`obstacle_map.py`) buffers existing copper by its own literal geometry
only (`track.width / 2.0`, pad polygon as-is, via `diameter / 2.0`) — **zero
clearance margin, for any net, HV or not**. So trace width today is a purely
cosmetic post-process label with no relationship to how much corridor space
A* actually reserved.

That makes "just fix the label" testable directly, without re-running the
(memory-heavy, ~10+ minute, previously OOM-reported —
`docs/evidence/2026-08-05-r3-router-status.md` §3 — 108-net) router: patch
only the `width` field of the 9 nets' 509 segments on the real, current
`pcb/temper.kicad_pcb` to their correct DRU value, leaving every centerline
coordinate untouched, and re-measure. Two DRC runs through the identical
scratch-copy harness (isolating the width-patch effect from an unrelated
scratch-copy footprint-library artifact that inflates `lib_footprint_issues`
identically in both — confirmed by running the *unpatched* board through the
same harness and diffing against the in-place baseline):

| category | before (scratch copy) | after (widths patched) | delta | delta involving 1 of the 9 nets |
|---|---|---|---|---|
| `track_width` | 199 | **0** | **−199** | — |
| `shorting_items` | 199 | 199 | 0 | n/a (flat) |
| `tracks_crossing` | 1 | 0 | −1 | n/a |
| `track_dangling` | 45 | 39 | −6 | n/a |
| `clearance` | 368 | 500 | **+132** | +200 (96→296) |
| `creepage` | 186 | 218 | **+32** | +34 (136→170) |
| `hole_clearance` | 105 | 143 | **+38** | +36 (37→73) |
| `copper_edge_clearance` | 10 | 32 | **+22** | +22 (3→25) |
| `solder_mask_bridge` | 154 | 199 | **+45** | +45 (38→83) |

Every category that got worse is (at least) fully explained by violations
that now involve one of the same 9 nets — this is not noise or an unrelated
scratch-copy effect, it is the direct, causal, measured consequence of
drawing 2–3mm-wide copper on a centerline the router only ever cleared for a
0.25mm trace. Net effect: **−199 in the target category, +269 spread across
five others**, and `shorting_items` itself is unmoved (see §4 — the width
bug is not a shorting cause).

Per the task's own hard constraint, this cannot be shipped as-is:
`drc_ceiling.json`'s R27 monotone contract does not permit a per-category
raise without a `Ceiling-Approval:` trailer and an attributed cause, and this
raise is not one this task is positioned to grant — `creepage` in particular
is explicitly another concurrently-running agent's owned category
("do not touch those categories"), and this change would raise it by 32.
**The real fix is making Stage 2's obstacle map and Stage 4's A* corridor
sizing net-class-and-width aware** (implementing the `wide_trace`
`routing_strategy` value that is documented but has never been built) —
materially larger, router-internals-level work, out of a bounded PR's scope,
and itself something that would need to be coordinated with whoever owns the
concurrent `creepage`/clearance work rather than landed unilaterally here.

No code change from this investigation is left in the tree; `git status`
against `main` is clean other than this document.

## 4. `shorting_items` (200): falsifying the "same tracks" hypothesis, then clustering the real cause

The task flagged the `track_width == shorting_items == 199` coincidence as
worth checking directly. Measured, not assumed:

- Of the 200 `shorting_items` violations, only **57 (28.5%)** involve one of
  the 9 undersized-width nets on either side of the pair; only **1** has
  *both* sides from that set.
- §3's controlled width-patch experiment is the direct causal test: widening
  exactly those 9 nets to their correct DRU width, with every other net's
  copper held byte-identical, left `shorting_items` **completely flat (199 →
  199)**. If the width bug were a shorting cause, fixing it should have moved
  this number; it did not.

**The two categories are the same size by coincidence, not by shared cause.**
`shorting_items` needs its own diagnosis.

### Clustering

200 violations resolve to **108 distinct net pairs** and **257 distinct
offending items** — no single item appears in more than 8 violations, and no
single net pair accounts for more than 8 of 200 (`inb`↔`power_in.ntc-no` and
`discharge.k_dis1-nc`↔`ina`, both 8). This is diffuse, not concentrated in a
small number of net pairs. It clusters cleanly by **item kind**, though:

| item-kind pair | count | share |
|---|---|---|
| Pad ↔ Track | 149 | 74.5% |
| Track ↔ Via | 40 | 20.0% |
| Pad ↔ Via | 5 | 2.5% |
| Via ↔ Via | 4 | 2.0% |
| Track ↔ Track | 2 | 1.0% |

Both mechanisms — and their approximate proportions — reproduce
`docs/evidence/2026-07-30-router-copper-shorts.md`'s finding on this same
board's earlier, 82-short generation (`Track+Via` 40%, `Pad+Track`(+PTH)
~55%, residual `Pad+Via`/`Via+Via`/`Track+Track` single digits), after that
document's own fix (loading pre-existing vias as static obstacles) already
landed and is present in the current board. That document traced the
remainder to a **same-run** (not cross-run) collision-avoidance gap: dynamic
via-blocking during a single A* solve (`OccupancyGrid.mark_via_blocked`,
escape-via candidate selection, `_unmark_route_blocked` after rip-up/reroute)
has gaps that let a new via or track land within clearance — sometimes
exactly on top of — a different net's pad or via placed *in the same
routing run*, and explicitly identified this as needing direct A*
ripup/reroute-loop and via-candidate-selection instrumentation:
"router-internals work, explicitly out of scope."

A structural contributor visible in this session that the July 30 document
did not have to name (because it wasn't measuring width): **Stage 2's
obstacle map carries zero clearance margin for any net, of any class**
(§3) — new copper is only kept from *overlapping* existing copper, never
kept the DRC-required *distance* from it. That is consistent with both the
sheer size of `clearance` (368, independent of the width bug) and with some
fraction of `shorting_items` being clearance-zero cases that tip into
outright overlap through grid-quantization at the margin — but it is a
foundational router behavior affecting every net, not a narrow, safely
patchable bug, and changing it is the same class of out-of-scope work as
§3's `wide_trace` gap.

**Disposition: not fixed here.** This reproduces and extends an
already-thorough, independent prior investigation's own conclusion on a
larger version of the same board. A representative sample (top 9 net pairs,
full item descriptions and coordinates) is preserved in this session's
scratch analysis; the honest next step is the same one that document named
— instrumenting Stage 4's rip-up/reroute and via-candidate-selection loop
directly — not a bounded pipeline patch, and not a placement fix (the
diffuse, kind-clustered signature — mostly *new copper landing on existing
pads*, not systematic net-to-net proximity — points at the router's
same-run obstacle bookkeeping, not at component placement).

## 5. What was and wasn't verified

Verified live this session: baseline DRC (in place, matching
`drc_ceiling.json`'s protocol); the 9-net/509-segment `track_width` root
cause (cross-referenced against `pcb/temper.kicad_pcb` segments directly,
independent of kicad-cli); the candidate fix's unit-level correctness
(existing suite green, direct calls against the real net-class table);
the width-patch causal experiment (before/after DRC through an identical
scratch-copy harness, with the harness's own footprint-library artifact
isolated and confirmed inert for every category discussed); the
`shorting_items` clustering and the direct falsification of the
width-causes-shorts hypothesis.

Not verified / out of scope: a full router re-route with the fix applied
(attempted; killed after reaching ~44GB RSS with 300s+ elapsed and no
completion, consistent with `docs/evidence/2026-08-05-r3-router-status.md`'s
own "UNMEASURED (OOM on this machine)" — this sandbox is shared with several
other concurrently-running agents and was already near its memory ceiling,
so a repeat attempt was not safe to force); the exact internal reason
`track_width` reports 199 rather than 509 (KiCad-internal, does not change
the diagnosis); whether Stage 2/4 corridor-width-awareness is feasible
within this router's existing architecture (not designed here).
