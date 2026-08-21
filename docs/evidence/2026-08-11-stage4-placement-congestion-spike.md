<!-- provenance: commit=c4956df6646b98355f12f00527370b20325e8a70 (HEAD at spike start), branch spike/stage4-placement-congestion, dirty=false for pcb/temper.kicad_pcb (never modified by this task) -->

# Stage 4 placement-congestion spike: what would actually route the remaining nets, costed

**Date:** 2026-08-11

**Task:** a spike (not an implementation) to determine what would actually
route the ~46 nets that fail Stage 4, and produce a costed,
evidence-backed recommendation, per this repo's 2026-08-08 conclusion that
the gap is "genuine multi-net placement congestion, not... HV clearance
envelopes."

**Budget note, stated up front per this task's own instructions.** This
spike spent real time attempting a fresh full production route
(`--net-batching`) before discovering it cannot currently succeed at all
on this HEAD without a workaround (§1). After building that workaround, the
coordinator redirected this spike away from waiting on that run and toward
answering the brief from artifacts that already exist, which is what §§2-6
below are built from — cheap (seconds) static analysis of the committed
board plus prior evidence documents, not a fresh full route. The
backgrounded in-process run (§1.3) was not waited on further, but it
finished on its own shortly after: it completed Stage 3 and a full Stage 4
A* pass, then crashed on its very last step (§1.4 — a second, independent,
previously-undocumented regression). Its per-net Stage 4 results survived
in the run's log despite that crash and are used below (§3-4) as a live,
current cross-check alongside the static analysis — not as a replacement
for it, since the crash means its own structured JSON/board output was
never written.

**Headline, stated plainly up front, in priority order:**

1. **The full production route path is currently broken twice over, in
   two independent, unrelated ways, both found by this spike and neither
   previously documented.** (a) `--net-batching` — the flag every prior
   evidence doc used — crashes before Stage 3 solves a single batch, a
   pickling regression from a Rust migration. (b) Even routed past that
   (this spike built a workaround), the pipeline crashes again at the
   very last step, on *every* successful route: `scripts/route_board.py`
   still unconditionally calls `audit_pad_connectivity()` — the project's
   own declared **PRIMARY completion metric**, introduced 2026-08-08 —
   but the module it imports, `pad_connectivity_audit.py`, was deleted
   that same day, a few hours later, by a "dead code" retirement pass
   whose import-graph scan covered `src/` and tests but not `scripts/`,
   so it never saw this real, active, production-critical caller. Both
   are out of this spike's scope to fix (`router_v6/**` is off-limits;
   another agent is mid-migration there; the retirement/scripts boundary
   is a different owner entirely) but together they are the single most
   urgent, actionable finding in this document — more urgent than
   anything about placement, and very likely why no routing-evidence
   document has been produced since 2026-08-08 despite 73 subsequent
   commits touching `router_v6/**`.
2. **The 2-signal-layer question is answered, and needs no SAT run.**
   In1.Cu/In2.Cu are **not** the binding constraint, and the 2026-08-08
   "declare them as power-plane layers" commit is **not** why signal
   routing is capped at 2 layers — that cap is structural, predates that
   commit, and was already tested directly: a working N-layer A* prototype
   exists (2026-08-08, unmerged) and was measured to recover **zero** real
   nets on this board, because Stage 2 never builds a routing grid for
   In1.Cu/In2.Cu in the first place (they are classified as planes by zone
   content/structural position, not by the layer-type token). More layers
   is not a lever here without a stackup redesign.
3. **The congestion hypothesis still holds — confirmed with fresh, live,
   current data, not just artifacts.** A static check against today's
   committed board (§3) and a live Stage-4 A* pass recovered from the
   crashed §1.4 run (§4) agree closely: raw Stage 4 completion today is
   **60/103 (58.3%)**, almost identical to the 2026-08-08 post-fix figure
   (61/104, 58.7%). In the live run's own 43-net failure list, `U27` (the
   MCU) is the single most-implicated component by a wide margin — 11
   failures touch it, more than double the runner-up — with `U9` (the RTD
   front-end ADC) close behind at 8, reproducing the same long, forced
   MCU↔RTD-ADC bus a prior investigation already named. Netclass breakdown
   of the live failures is 65% `Default`/19% `FinePitch` vs. only 4 (9%)
   `HighVoltage`, confirming — with fresh, live numbers — that this is
   ordinary placement/routing-order congestion, not HV-clearance crowding.
4. **The costed options, ranked, are unchanged in substance from what a
   2026-08-07 feasibility study already found**: the placer that produced
   this board's layout has **no wirelength/HPWL/clustering objective
   anywhere in its live solve path** — only a minimum-displacement repair
   term. The board's scatter is not incidental; nothing has ever asked the
   solver to avoid it. That is the highest-ceiling, highest-cost lever.
   Manual, targeted component nudges are the highest near-term
   (nets routed)/(effort) lever. More layers and net-reordering are cheap
   but low- or zero-payoff, per direct measurement.

---

## 1. Reproduction: blocked, then partially unblocked, then de-prioritized per the coordinator

### 1.1 The board itself, statically

`pcb/temper.kicad_pcb` is unchanged since 2026-08-08 except for one
one-line-per-layer, provably inert edit (`c4956df66`, §3). Its current
committed state, measured directly (no route, no SAT):

```
sha256 = 6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64
169 footprints, 2290 segments, 48 vias, 96 zones
```

This matches this task's own brief exactly, and is the same board every
document cited below was written against.

### 1.2 The net-batching path is currently broken — a regression found by this spike

`docs/evidence/2026-08-08-router-power-gnd-and-stage4-clearance-combined.md`
(and every other cited evidence doc) got its numbers by calling
`route_pcb(..., enable_net_batching=True, net_batch_size=10)` — the same
call `scripts/route_board.py --net-batching` and
`scripts/rcm_blocking_diag.py` make today. Attempting to reproduce that
exact call on current HEAD, **both scripts crash identically, before
Stage 3 solves a single batch**:

```
File ".../net_batching.py", line 947, in run_net_batched_stage3
    ctx_path = _write_shared_context(pcb, skeletons)
File ".../net_batching.py", line 550, in _write_shared_context
    pickle.dump(...)
_pickle.PicklingError: Can't pickle <class
'temper_design_bundle_python.channel_skeleton_contracts.SkeletonGraph'>:
import of module 'temper_design_bundle_python.channel_skeleton_contracts'
failed
```

**Root cause, traced.** `_write_shared_context` unconditionally pickles
Stage 2's `skeletons` dict so each batch's subprocess can reconstruct it
(subprocess isolation was added 2026-08-08 specifically to stop
cross-batch RSS creep, per `docs/evidence/2026-08-08-net-batching-subprocess-isolation.md`).
Since `feat(wave4): migrate channel_skeleton.py nx.Graph to Rust
SkeletonGraph` (commit `281aa747b`, one of 73 `router_v6/**` commits
landed since the last routing-evidence run), `skeletons` values are now
`temper_design_bundle_python.channel_skeleton_contracts.SkeletonGraph`
pyo3 objects, which do not implement `__reduce__`/pickling. **This call
site has never been unconditional-tested against a real Rust
`SkeletonGraph`** — `test_net_batching_subprocess.py` covers
`channel_widths`/`_DesignRulesStub` pickling round-trips but not
`skeletons`, so nothing caught this when the migration landed.

**Severity: total, not partial.** `_write_shared_context` runs once,
unconditionally, before the batch loop starts (`net_batching.py:947`) — it
is not batch-size- or flag-dependent. Every `--net-batching` call fails
the same way, 100% of the time, on this HEAD. `router_v6/**` is explicitly
off-limits to this spike (another agent is mid-migration there), so this
is reported, not fixed, here — but it should be treated as a P0 blocker
for any further routing work, independent of everything else in this
document.

### 1.3 A measurement-only workaround, and why it was de-prioritized

To get any current number at all, this task wrote
`scripts/spike_2026_08_11_inprocess_netbatch.py` (outside `router_v6/**`,
committed alongside this doc) — a read-only monkeypatch (the same pattern
`rcm_blocking_diag.py` already uses) that runs each batch's build+solve
**in-process** instead of via the broken subprocess/pickle boundary,
verbatim-copying `_batch_worker_entry`'s logic. This is a measurement
workaround only, not a proposed fix (subprocess isolation exists for a
real reason — RSS creep on memory-constrained CI — that this workaround
deliberately re-exposes on this 62 GB workstation, acceptable for one
measurement run, not for production).

It got past the crash and into real Stage 3 SAT solving (all 11 batches
observed SAT in the trace log) and into real Stage 4 A*. **This is the
"expensive setup" the task brief warned about**: Stage 0-2 setup + 11
sequential SAT batches + full Stage 4 A* costs on the order of **10-15
minutes of wall time** on this machine (consistent with every prior
evidence doc's own reported wall times: 712-862s), and this spike had
already spent a large fraction of its own budget getting to a working
in-process route by the time the coordinator redirected it away from
waiting on that run. Per instruction, this run was **not** used as the
basis for anything below; §§2-6 are built entirely from (a) existing
evidence documents and (b) cheap (seconds, not minutes) static analysis
against the committed board file. If the backgrounded run happened to
finish, its numbers are reported as an unweighted cross-check in the
Appendix, not as this document's primary evidence.

**Cost of a full, trustworthy reproduction, stated explicitly as the task
asked:** ~10-15 minutes of wall-clock SAT+A* solving per run, **plus**
first fixing the pickling regression in §1.2 (an unscoped
`router_v6/**` fix, effort unknown but almost certainly small — one
`SkeletonGraph`-shaped object needs either a `__reduce__` implementation
in the Rust crate or the same "reconstruct from a cheap source, don't
pickle the pyclass" pattern `_write_shared_context`'s own docstring
already uses for `ParsedPCB`/`DesignRules`) **and** the §1.4 regression
below.

### 1.4 A second, independent regression: the PRIMARY completion metric was deleted the same day it was introduced

The in-process workaround (§1.3) got all the way through Stage 3 SAT and a
full Stage 4 A* pass (every one of the ~104 attempted nets printed a
`✓ routed successfully` / `✗ ... FAILED` line) — then crashed on the very
last step, before it could report or save anything:

```
File ".../scripts/route_board.py", line 269, in route_once
    pad_connectivity = audit_pad_connectivity(content) if content else None
File ".../scripts/route_board.py", line 124, in audit_pad_connectivity
    from temper_placer.router_v6.pad_connectivity_audit import audit_pcb_file
ModuleNotFoundError: No module named 'temper_placer.router_v6.pad_connectivity_audit'
```

**Traced:** `pad_connectivity_audit.py` — the module
`docs/evidence/2026-08-08-terminal-defect-and-pad-connectivity-fix.md`
introduced earlier on 2026-08-08 and explicitly labelled the project's
**PRIMARY completion metric** (`route_board.py`'s own output literally
prints that label) — was deleted a few hours later the same day by
commit `47349a50d` ("retire(python): delete 14 dead/dormant modules +
6 dead test files"). That commit's own message states its method: "AST
import-graph scan (**src + tests**) found zero production importers."
`scripts/route_board.py` is neither under `src/` nor a test file, so the
scan never saw it — and it is exactly, and unconditionally
(`route_once()` line 269, called whenever `content` is non-empty, i.e.
on every route that produces any output at all), the real caller this
module exists for. `pad_connectivity_audit.py` is still absent on current
HEAD; `route_board.py` still imports it unconditionally. **Every full
production `route_board.py` run that reaches Stage 4 completion crashes
before it can report a result**, independent of and in addition to §1.2's
regression. This is very likely why no routing-evidence document exists
between 2026-08-08 and today despite 73 intervening `router_v6/**`
commits — nobody has been able to run the production entry point to
completion since that day.

Also out of this spike's scope to fix (ownership of the retirement
pass/`scripts/` boundary is unclear and not this task's to resolve), but
it should be reported with the same urgency as §1.2: **two independent,
unrelated regressions, landed the same day, each independently blocking
the production route path**, neither previously documented.

---

## 2. Is 2-signal-layers the binding constraint? Answered without a route.

**No — measured and already prototyped. Not the 2026-08-08 declaration,
and not fixable by lifting it.**

**2a. The commit is inert, by its own admission and independently
verified today.** `c4956df66` ("declare In1.Cu/In2.Cu as power-plane
layers, not signal") changed exactly two tokens
(`(1 "In1.Cu" signal)` → `(1 "In1.Cu" power)`, same for In2.Cu) and
nothing else. Its own commit message states
`temper_placer.io._parse_board._extract_stackup` "never reads this raw
layer-table token at all — it derives layer_type from zone content +
structural position." Verified independently today: grepping the current
committed board shows `In1.Cu`/`In2.Cu` appear **only** in that one
layer-declaration line each (`grep -c "In1.Cu\|In2.Cu" pcb/temper.kicad_pcb`
→ 2) — zero zones, segments, or vias reference either layer, on the
committed board both before and after that commit. The router's own
layer-role classification does not consult the token this commit changed.

**2b. The real 2-layer cap is structural and predates the commit.**
`_pipeline_route.select_routing_grids()` hardcodes selection of exactly
one primary + one alternate grid (`occupancy_grids.get("F.Cu")` /
`.get("B.Cu")`, falling back to name-preference order), and
`astar_pathfinding.run_astar_pathfinding()`'s signature takes one
`alternate_grid: OccupancyGrid | None` — singular, confirmed by `git log
-p -S"alternate_grids"` returning zero commits across this repo's entire
history. This is unrelated to the layer-type token; it is a plumbing cap
on how many grids Stage 4 is ever handed.

**2c. This has already been tested directly, and the result is decisive:
opening it buys nothing on this board.** `docs/evidence/2026-08-08-nlayer-via-astar-spike.md`
built and measured a real N-layer generalization (`spike/nlayer-via-astar`,
unmerged, opt-in via `--nlayer-astar-spike`): the underlying via-aware 3D
search primitive was *already* N-layer-capable and via-cost/clearance-aware
— only three call sites hardcoded "2." Generalizing them and re-routing
the same board looked like a huge win at first (`nets_carrying_copper()`
64/110 → 96/110) — until the spike's own pad-connectivity audit proved
**every one of those 32 additional "carrying copper" nets is fake
completion**: the set of nets whose copper actually reaches *all* of their
own pads is the **identical 31 nets**, verified by exact set equality, in
both the baseline and the N-layer run. Zero real nets recovered. Root
cause: `In1.Cu`/`In2.Cu` never get an occupancy grid *at all*, regardless
of the layer-type token or how many grids Stage 4 is willing to accept,
because `routing_space.py` classifies them as plane layers from zone
content/structural position (REQ-ELEC-05's design intent: In1=GND
reference plane, In2=power-domain planes) — the same classification path
§2a already showed is untouched by `c4956df66`. `select_routing_grids_nlayer`
collapses to `{F.Cu, B.Cu}`, the same two grids production already uses,
because that is every signal-routable layer this board has today.

**Conclusion:** lifting the 2-layer cap in software (cheap — the
prototype is ~500 LOC and already exists) does not recover any of the
remaining nets on *this* board's stackup. Making In1/In2 real signal
layers would require redesigning the stackup itself (dropping or relocating
the GND/power-plane role REQ-ELEC-05 specifies, with real EMC/impedance
consequences), not a router change — and this repo has a directly
analogous, already-measured cautionary precedent for casually changing a
layer's role: `docs/evidence/2026-07-28-stackup-partial-revert.md` records
a **12× routing-completion regression** from an earlier, different
attempt to force outer layers into an unconditional signal role. This is
not the lever to pull.

---

## 3. Current failure count: live data (recovered from §1.4's crashed run) plus a static cross-check

### 3.1 Live: 60/103 raw Stage 4 completion, today, on current HEAD

The §1.3/§1.4 in-process run got all the way through a real Stage 4 A*
pass before crashing on its reporting step. Its console log (not the
structured JSON, which was never written) is a complete, real,
per-net record of every net Stage 4 attempted today:

```
✓ routed successfully: 60
✗ FAILED ("no legal path found (forced segment disallowed)"): 43
Raw completion: 60/103 = 58.3%
```

**This is almost exactly the 2026-08-08 post-terminal-fix figure (61/104,
58.7%)** — strong evidence that, modulo the two regressions in §1, today's
actual Stage 4 behavior is essentially unchanged from 2026-08-08, despite
73 intervening `router_v6/**` commits. Stage 3 also fully succeeded in
this run: `[batch-trace] done: 11 batches, 11 solved at batch level, 0
batch-level crashes, 0/110 nets fell back` — exactly reproducing the
2026-08-08 net-batching-subprocess-isolation doc's "all 11 batches SAT"
result.

The 43 failing net names, extracted directly from the log:

```
+3V3, a, bias, cs_n, discharge.k_dis2-coil1, discharge.r_dis1a-p2,
discharge.r_dis2a-p2, discharge.r_snub2-p2, fb, gnd,
hb.power_loop.q_high-g, i2c_sda_ui, ina, inb, power_in.q_relay_drv-g,
refin_n, RELAY_CTRL, RTD_DRDY, rtd_pan.rail_monitor-ina_p,
rtd_pan.rail_monitor-outa, RTD_SCK, safety.coil_thermal-line,
safety.fault_any_or-a2, safety.fault_any_or-y2, safety.fault_or-b2,
safety.fault_or-y2, safety-line-1, safety-line-2, safety-line-3,
safety.ovp.r_adc_top1-p2, safety.ovp.r_div_top2-p2, safety.thermal-line,
sdi, sdo, tank.c_tank1-p2, thermal.j_fan-p1, vbias, vcc, w1_1, WDT_KICK,
WDT_RESET_N, y, ZCD_ISO
```

**Caveat, stated plainly:** this is one run, from a measurement workaround
(§1.3) that bypasses subprocess isolation, with no independent
byte-identical confirmation (this spike had budget for exactly one such
run before the coordinator's redirect). This repo's own prior work
established byte-identical determinism for the equivalent subprocess-based
path across many runs (§1.2's cited doc: 3 independent runs, 0 spread), so
there is no specific reason to expect this workaround to be
non-deterministic, but it has not been proven so today. Treat this as a
strong single data point, not a certified reproducible baseline.

### 3.2 Static cross-check: 64/110 nets carry copper on the committed file

Independently, parsing `pcb/temper.kicad_pcb` and calling
`topology_copper_audit.nets_carrying_copper()` directly against its
content (no route, no SAT — seconds, not minutes; exactly the entry point
the 2026-08-08 combined-fix doc used, run here against the file as it
exists today):

```
Total nets in netlist:                          110
Nets carrying copper (explicit trace/via ∪ zone): 64   (58.2%)
Routing-eligible nets with ZERO copper:            45
should_route()-excluded (zone-pour-only class)…    7   (6 of which DO carry zone copper)
  …of those, the one genuine policy-gap orphan:     1  (+170V_BUS — a separate,
                                                          already-known bug class,
                                                          not placement congestion)
Check: 64 + 45 + 1 = 110 ✓.
```

**64/110 matches this task's own brief exactly** and matches the
2026-08-08 combined-fix doc's "combined (A+B)" row. This is the
*committed* board's own copper, which is a different (and, per §4 of the
2026-08-08 nlayer spike doc, a strictly weaker) bar than "Stage 4 actually
attempted and succeeded this net" — some of the 64 are zone-pour-only, and
raw "carrying copper" over-counts real completion (§1.4's cited doc: only
31/139 nets were genuinely fully pad-connected on 2026-08-08, before that
day's terminal-defect fix raised it to 48/139). The static 45-net
"zero-copper" list and the live 43-net "A*-failed" list (§3.1) are
close but not identical, for the same reason the two differ in general: a
net can fail Stage 4 A* and still gain copper via a separate zone-pour
fallback (the 2026-08-08 doc documents exactly this mechanism for
`rtd_pan.rail_monitor-outa` — which is, consistently, in §3.1's live
*failure* list but not in this section's static *no-copper* list).

**The honest reading: today's real Stage-4 gap is 43-45 nets, tightly
bounded by two independent measurements**, both taken this task, one live
and one static — materially the same shape and size as every
2026-08-08 document found, not a regression and not an improvement.

---

## 4. Characterizing the failures — live data, cross-checked against the existing record

### 4.1 Which components are implicated — live data

Cross-referencing each of the 43 live-failing nets' (§3.1) own component
pins against the committed board:

| Component | Live failures touched (of 43) |
|---|---:|
| **U27 (ESP32-S3 MCU)** | **11** |
| **U9 (RTD front-end ADC)** | **8** |
| U24 (safety fault-OR) | 7 |
| U23 (safety comparator) | 6 |
| U26 | 5 |
| U20, U3, U14, U7, U19, U15 | 4 each |

**U27 alone touches over a quarter of today's live Stage-4 failures** —
by a wide margin the single most-implicated component on the board today,
exactly matching (and, with live rather than static data, sharpening) the
2026-08-08 placement-remediation-analysis's structural finding of a forced
~211mm MCU↔RTD-ADC bus (`U27` at (34.1, 48.0) TOP-LEFT ↔ `U9` at
(95.4, 249.9) BOTTOM-MID, on a 279mm-diagonal board): **18 of the 43 live
failures (42%)** touch `U27`, `U9`, or the RTD divider network
(`R36`-`R42`/`U10`) between them. A further 10 of 43 touch the other
named congestion cluster (`PS1`/`U7`/`U6`/the safety-comparator
small-parts field, all physically piled up at the board's center per that
same document).

### 4.2 Netclass breakdown — confirms placement congestion, not HV crowding, with live data

| Netclass | Live failures (of 43) |
|---|---:|
| Default | 28 (65%) |
| FinePitch | 8 (19%) |
| HighVoltage | 4 (9%) |
| Power | 2 (5%) |
| GND | 1 (2%) |

Only 4/43 live-failing nets today are even in the `HighVoltage` class; 84%
are ordinary `Default`/`FinePitch` signal nets. This is the same shape the
2026-08-08 blocker-classification run found by a much more expensive
method (live capture of every failing net's `blocking_nets` list,
classified by clearance size): "0/52 failing nets blocked *primarily* by
the new large-clearance envelopes... genuinely placement-bound." Today's
live netclass count corroborates that conclusion independently, with
fresh data, five days later.

### 4.3 The existing spatial record (2026-08-08, not re-derived, still structurally valid)

`docs/evidence/2026-08-08-placement-remediation-analysis.md` bucketed each
failing net's own-pin centroid into a 3×3 grid over the 152×234mm board
and found the congestion **concentrated, not diffuse**: the physical-center
cell (MID-MID, 11.1% of board area) held 22/52 (42%) of failing nets by
centroid and 30.5% of all recorded blocker occurrences — the largest share
by a wide margin. That cell contains five *unrelated* subsystems physically
stacked on each other: `PS1` (a 46.2×25.9mm AC/DC converter module, the
single largest footprint in the region), `U7` (isolated gate driver, a
6.0mm `GateDriveHV`/`HighVoltageIsolated` clearance envelope sitting
directly in the busiest through-traffic path), `U6` (TO-247 half-bridge
switch), and a dense field of small safety-comparator parts
(`R58/R67/R71/TP1/TP2/U20/U25`). `K2`/`K3` (discharge relays, 6.0mm
clearance) sit at the MID-MID/MID-RIGHT and TOP-LEFT seams. Median blocker
count per failing net was 7 (mean 7.4), from 46 distinct blocker net names
— dense multi-net congestion, not one removable obstruction.

**This spike could not re-run that exact spatial analysis** (it needs the
live per-net `blocking_nets` capture that §1's regression currently
blocks), but §4.1's independent, cheap, current component-touch count
reproduces its two named hotspots (the MCU↔RTD bus and the MID-MID pileup)
on today's actual board, which is the strongest available corroboration
without a working route.

### 4.4 A live update to the 2026-08-08 "zero-blocker" cases — and why it cannot be fully trusted

The 2026-08-08 placement-remediation-analysis named three nets with
genuinely different failure mechanisms from the dense-congestion majority:
`discharge.r_snub1-p2`, `tank-out` (zero-blocker A* search exhaustion),
and `w1_1`/`w1_2` (targeting `K1`'s Faston spade-lug pads, declared on
`F.Fab` — a fabrication layer, not copper — by the footprint's own
deliberate design; an external wire-to-spade connection, not a PCB trace).

**Today's live run (§3.1) only partly agrees, and the disagreement itself
is informative.** `w1_1` and `tank.c_tank1-p2` still fail today. But
`w1_2` and `tank-out` are both logged **`✓ routed successfully`** in
today's live run — a change from 2026-08-08's characterization. This spike
cannot fully trust that "success," for exactly the reason §1.4's
regression matters: "routed successfully" only means Stage 4 A* found
*some* path to whatever terminal it was given, not that the terminal is
the net's real pad or that the copper is genuinely connected end-to-end
(the documented `b39b382d`/fake-completion shape,
`docs/evidence/2026-08-08-nlayer-via-astar-spike.md`) — and the one tool
that would tell the difference, `pad_connectivity_audit`, is exactly the
module §1.4 found deleted. `w1_2` in particular targets a pad the
footprint declares has **no copper layer entry at all**; a reported
"success" there is a strong candidate for exactly this fake-completion
shape, not a genuine improvement, but this spike cannot currently prove
that classification either way. Flagged, not resolved: fixing §1.4 first
would let this be checked directly rather than guessed at.

**`+170V_BUS`** (§3.2) is a `should_route()`-excluded net with zero
copper — a known, separate policy-gap bug class (the same shape as the six
named orphans Fix A closed on 2026-08-08 for `+15V`/`PWR_RTN`/
`V_BUS_SENSE`/`vcc`/etc.), not a Stage 4 A* failure and not congestion.

---

## 5. Testing the placement-congestion hypothesis — what's decisive, cheaply

Three independent, already-existing tests all point the same direction,
none of which required this spike to re-run a route:

1. **Iteration-budget is not the constraint.** `docs/evidence/2026-07-27-forced-segment-analysis.md`
   swept the A* iteration cap 8× (500k→4M) on a full production route and
   found the total failure count **never moved** — only which specific
   nets succeed churns (tie-break sensitivity). At 4M, 56/59 of that day's
   failures provably exhausted their entire reachable search space. This
   rules out "the router gave up too early" outright.
2. **More routing capacity (N-layer) is not the constraint.** §2c: a real,
   working N-layer generalization was built and measured to recover zero
   real (pad-connected) nets on this board.
3. **The netclass/component evidence is congestion-shaped, not
   clearance-shaped.** §4.2's fresh netclass breakdown (69% `Default`) and
   §4.1's fresh component-touch count (dominated by a long forced MCU↔ADC
   bus and a five-subsystem pileup at board center) match the 2026-08-08
   live-capture finding exactly, using a completely independent, much
   cheaper method.

**What this spike could not test cheaply:** whether a specific net fails
*in isolation* (i.e., against an otherwise-empty board) as well as *in
situ* — the most direct possible falsifier of "it's congestion, not a
router defect." That test needs a live route (single-net or full-board),
which needs the regression in §1 fixed first. Flagged as the most valuable
next measurement, not attempted here.

---

## 6. Costed options, ranked by (nets routed) / (effort)

| # | Option | Effort | Measured/estimated payoff | Verdict |
|---|---|---|---|---|
| 0a | **Fix the net-batching pickling regression (§1.2)** | Small, unscoped (one Rust pyclass needs `__reduce__`, or its `skeletons` payload needs the same "reconstruct, don't pickle" treatment `_write_shared_context` already uses for `ParsedPCB`/`DesignRules`) | N/A — this is a prerequisite, not a routing improvement | **Do first.** Nothing else in this table is measurable in production until this lands. Not this spike's task (`router_v6/**` off-limits) but should be flagged to whoever owns that migration immediately. |
| 0b | **Restore `pad_connectivity_audit.py` (§1.4)**, and widen the retirement gate's import scan to cover `scripts/` | Small — the module's own git history has the file; restoring is a revert, not a rewrite. The scan-scope gap should also be fixed so this class of miss can't recur silently | N/A — prerequisite for trusting *any* completion number, including §3-4's own live data (§4.4's `w1_2`/`tank-out` ambiguity exists precisely because this tool is gone) | **Do first, alongside 0a.** Without it, "routed successfully" cannot be distinguished from fake completion. |
| 1 | **Fix `w1_1`/`w1_2`'s footprint modeling** (real copper pads for `K1`'s spade lugs, or mark the nets no-route) — and re-verify `w1_2`'s live "success" (§4.4) is real once 0b lands | Tiny — one footprint edit or one net-exclusion entry | +1-2 nets, mechanically, not a placement win | Do regardless; it's free and currently ambiguous/misreported. |
| 2 | **Manual, targeted placement nudges** — relocate `PS1` out of MID-MID, widen the `U7`/`U6` corridor, shorten the `U27`↔`U9` bus (per §4.1/4.3, together implicating 18-28 of today's 43 live failures) | Medium — hours to days: a human/agent repositions a handful of free (non-pinned; ~89% of components carry no hard position constraint, per `docs/evidence/2026-08-07-placement-clustering-feasibility.md`) components and re-solves | Unquantified (no candidate has been re-placed and re-routed end-to-end yet) but directionally the strongest near-term lever — it directly targets the two largest, most independent, already-identified obstructions | **Highest (nets routed)/(effort) of any option that isn't already ruled out.** Recommended first real routing work, after #0a/0b. |
| 3 | **Net-reordering experiment** (`order_nets_for_batching`'s existing hub-block/priority knobs) | Cheap — no new code, just different flag values and a re-route | Existing evidence (the iteration-cap sweep, §5.1) shows reordering changes *which* nets fail, not the *total* — expected payoff low | Worth a cheap A/B once #0 is fixed, but not the primary lever. |
| 4 | **Add a real CP-SAT wirelength/clustering objective** | Large — genuine engineering: the placer's live `Minimize()` path has exactly one term today (a minimum-displacement repair term for local patches, `model.py:290`); the config surface that looks like it should provide clustering (`component_groups`, `loss_weights`) is either dead code or wired into an unrelated non-CP-SAT heuristic. A real term needs a materially larger variable/constraint budget than the existing ~33-component displacement objective (already flagged as timeout-marginal) for ~150 free components, and must be paired with the isolation barrier's HV/SELV split (also unapplied today) plus a thermal-aware term to avoid trading a placement win for a new safety regression | Large, ESTIMATED-only chain (per the cited feasibility doc: ~11× edge-density reduction for the largest SAT block, if paired with an also-unbuilt isolation-barrier split) — this is the actual root cause of why the board is scattered (8/9 resolvable atopile-module blocks measure radius-of-gyration 90-105% of the whole board's own — statistically indistinguishable from uniform scatter) but is a multi-quarter research direction, not a near-term fix | Highest ceiling, highest cost. Correct long-term lever; not a spike-sized deliverable. |
| 5 | **Open In1.Cu/In2.Cu to real signal routing** | Low to enable in software (prototype exists, ~500 LOC) but requires a stackup/EMC redesign to be real | **Measured zero** on this board as designed (§2c) | Not recommended. Already tried; already shown not to work without contradicting REQ-ELEC-05's plane design intent, with a directly-analogous 12× regression precedent for casual layer-role changes. |
| 6 | **Wire up rip-up-and-reroute for single-blocker forced-segment failures** | Small-to-medium, real regression risk | Historically ~2-3 of ~50-60 failing nets have a clean single-blocker signature | Low ceiling; not worth the regression risk ahead of options 2 and 4. |
| 7 | **SAT model / block decomposition** (`docs/plans/2026-08-07-003-...-plan.md`) | Large | Targets a *different* problem (Stage 3 SAT model size/OOM), already substantially mitigated by subprocess isolation (though see §1.2 — that same mechanism is what's currently broken) | Not a Stage 4 geometric-congestion lever; useful corroboration only (its own placement-dispersion measurement independently confirms the "board isn't clustered" finding behind option 4). |

---

## 7. Recommendation

1. **Immediately:** report both §1 regressions — the net-batching pickling
   crash (§1.2) to whoever owns the `channel_skeleton.py` Rust migration,
   and the deleted `pad_connectivity_audit.py` (§1.4) to whoever owns the
   dead-code retirement pass, flagging that its import scan needs to cover
   `scripts/`, not just `src/`+tests. Together they block all further
   trustworthy routing measurement on this board.
2. **Free, do anyway:** fix `w1_1`/`w1_2`'s footprint modeling and re-verify
   `w1_2`'s live "success" once pad-connectivity is restored (§4.4), and
   close the `+170V_BUS` orphan (§3.2) — none of these are placement
   problems.
3. **First real routing work:** a manually-guided placement pass targeting
   `PS1`, the `U7`/`U6` corridor, and the `U27`↔`U9` distance (option 2)
   — re-solve and re-measure with the tooling this repo already has
   (`rcm_blocking_diag.py`/`rcm_pin_positions.py`/`rcm_spatial_analysis.py`,
   once §1's regressions are fixed) rather than continuing to estimate.
4. **Do not** pursue more layers or net-reordering as the primary lever —
   both are cheap to try but are already measured/predicted to have low or
   zero payoff.
5. **Track separately, not for this spike:** a real CP-SAT clustering
   objective (option 4) is the durable fix, but it is a multi-quarter
   research investment, not something to fold into near-term routing work.

---

## Appendix: what the crashed in-process run's log could and couldn't provide

The backgrounded in-process run (§1.3) was not waited on further per the
coordinator's redirect, but it finished on its own: full Stage 3 (11/11
batches SAT) and a full Stage 4 A* pass, then crashed at the reporting
step on §1.4's regression. Its console log — not its structured JSON or
routed-board output, neither of which was ever written — is what §3.1 and
§4.1-4.2 above are built from: real, live, per-net Stage 4 results for
today's committed board, recovered by grepping the log for `✓`/`✗` lines
rather than by waiting for the run's own (broken) reporting path. What it
could **not** provide, because the crash happened before this step: the
pad-connectivity primary metric, the routed board content itself (for a
`nets_carrying_copper()`/segment/via/zone recount against a fresh route),
and any spatial (`blocking_nets`) capture — all of which would need
`pad_connectivity_audit.py` restored (§1.4) and, for the spatial capture
specifically, a separate `rcm_blocking_diag.py`-style monkeypatch run
(which crashes on the same §1.2 regression today, and would need the same
in-process workaround applied).

---

## Sources

- `docs/evidence/2026-08-08-router-power-gnd-and-stage4-clearance-combined.md`
  — the 3-day-old doc this spike was asked to test; source of "64/110",
  "52 failures", and the "genuine placement congestion, not HV clearance"
  conclusion (§4 Problem 3).
- `docs/evidence/2026-08-08-stage4-astar-clearance-mismatch.md` — the
  Stage3/Stage4 clearance-model fix; §5's "genuinely infeasible... not
  software-fixable" verdict.
- `docs/evidence/2026-08-08-placement-remediation-analysis.md` — spatial
  clustering (MID-MID), named components (`PS1`/`U7`/`U6`/`K2`/`K3`), the
  ~211mm `U27`↔`U9` bus, and the corrected §4 verdict that the 2-layer cap
  is software (`select_routing_grids`), not hardware.
- `docs/evidence/2026-08-08-nlayer-via-astar-spike.md` — the N-layer A*
  prototype; decisive "zero real nets recovered, fake-completion-only"
  result this document's §2c relies on.
- `docs/evidence/2026-08-08-terminal-defect-and-pad-connectivity-fix.md` —
  pad-connectivity as the primary completion metric; root cause of why
  raw "carrying copper" over-counts.
- `docs/evidence/2026-08-08-net-batching-subprocess-isolation.md` —
  subprocess-per-batch design rationale this spike's §1.2 finding shows is
  currently broken.
- `docs/evidence/2026-07-27-forced-segment-analysis.md` — the iteration-cap
  8× sweep; "net-ordering or placement-density... is the correct lever."
- `docs/evidence/2026-08-07-placement-clustering-feasibility.md` — root
  cause of the scatter: no wirelength/clustering objective in the CP-SAT
  placer's live solve path; dispersion measurement (radius of gyration);
  cost estimate for adding one.
- `docs/evidence/2026-07-28-stackup-partial-revert.md` — the 12× regression
  precedent cited in §2c/§6 against casual layer-role changes.
- `docs/plans/2026-08-07-003-feat-routing-block-decomposition-plan.md` —
  corroborating placement-dispersion measurement (bounding-box/edge-density),
  cited for context, not a Stage 4 lever.
- This task's own commits: `scripts/spike_2026_08_11_inprocess_netbatch.py`
  (measurement workaround, not a fix); static measurements in this document
  reproduced directly against `pcb/temper.kicad_pcb` via
  `temper_placer.router_v6.topology_copper_audit.nets_carrying_copper()`,
  `temper_placer.router_v6._net_policy._should_route()`, and
  `temper_placer.io.kicad_parser.parse_kicad_pcb()` — all read-only, no
  board or `router_v6/**` file modified.
