<!-- provenance: commit=a94ea10b36fe42c3e31d06d70b54d3ac49d760f8 (merge of fix/router-power-gnd-copper-gap + investigate/stage4-astar-19nets onto 888331ba) dirty=true -- this doc + the accessor fix are the dirty diff in this same task -->

# Combining the power/GND policy fix and the Stage 4 clearance fix: resolving the baseline contradiction and measuring the real combined effect

**Date:** 2026-08-08

**Task:** Merge `fix/router-power-gnd-copper-gap` (`51ade730`) and
`investigate/stage4-astar-19nets` (`6020b6be`), resolve a baseline-measurement
contradiction between their two authoring agents, and produce one
trustworthy set of before/after/combined numbers for
`pcb/temper.kicad_pcb`.

**Headline:** The contradiction was not a measurement error, not stale
board input, and not run-to-run nondeterminism — it was a genuine
ambiguity in `topology_copper_audit.nets_with_copper()`'s return shape,
which two callers collapsed to a single number two different (and
internally inconsistent, in one case) ways over the *same, deterministic,
byte-identical* routed board. Fixed by adding a single unambiguous
accessor, `nets_carrying_copper()`. The two fixes merge with **zero
conflicts** (disjoint files) and combine to a **net-neutral copper-count
result on this board**: 64/110 nets carry copper both before and after —
Fix A's gain and Fix B's cost land on the same number by coincidence, not
because either fix did nothing. Total copper volume (segments) drops
15.7% from baseline, and vias return to the baseline count. A per-net
spot-check of the 52 remaining Stage 4 failures (Problem 3) confirms Fix
B's conclusion: the gap is dominated by genuine multi-net placement
congestion, not by the newly-correct HV clearance envelopes.

---

## 1. Resolving the baseline contradiction

### 1.1 The two claims

- Fix A's agent (`51ade730` commit message): baseline **52** nets carrying
  copper, 3058 segments, 50 vias → after Fix A: **73** nets, 3468
  segments, 54 vias.
- Fix B's agent (`docs/evidence/2026-08-08-stage4-astar-clearance-mismatch.md`,
  on `investigate/stage4-astar-19nets`): baseline **64/110** nets carrying
  copper (explicit+zone), 3058 segments, 50 vias, "three independent
  reproducible runs, byte-identical" → after Fix B: **61/110**, 2535
  segments, 54 vias.

Both cite `nets_with_copper()`. Note the segments/vias figures already
agree exactly between the two agents (3058/50 baseline) — the divergence
is entirely in the "nets carrying copper" scalar, not in the underlying
routed board.

### 1.2 Candidates tested and ruled out

Built a fresh worktree at `888331ba` (`.claude/worktrees/router-combined-measurement`,
never checked out in the primary checkout), rebuilt all 13 pyo3 extensions,
and ran `scripts/route_board.py --pcb pcb/temper.kicad_pcb --net-batching
--batch-size 10` with `TEMPER_BATCH_TRACE=1` from scratch, using the same
script both agents used (which always strips existing copper/zones before
routing — ruling out stripped-vs-unstripped input as a factor) and the
same `--net-batching --batch-size 10` flags (ruling out batching settings).
`nets_with_copper()` skips net 0 by construction (`net_number_to_name_map`
only records name-bearing `(net N "name")` declarations, and net 0's name
is always `""`, which every call site's `if name:` guard drops) —
identical in both agents' code, ruling out net-0 handling as a factor.

**Result: segments=3058, vias=50** — an exact match to what *both* agents
independently reported as the baseline. This is a third independent
process launch (mine), on top of the two each agent already ran (Fix B
explicitly ran 3), all agreeing exactly on segments and vias. **Spread
across all known independent runs at this commit: 0.** This is not
run-to-run nondeterminism.

### 1.3 The actual cause

`nets_with_copper(pcb_content)` returns `tuple[set[str], set[str]]` —
`(explicit_copper_nets, zone_copper_nets)` — deliberately kept separate so
callers can distinguish *why* a net has no trace. It has no built-in way
to collapse that pair into the one number both agents wanted ("how many
nets carry copper, period"), so each call site had to invent one:

| Quantity (my fresh measurement, same commit, same run) | Value |
|---|---:|
| `len(explicit)` at baseline | **52** |
| `len(explicit \| zoned)` (union) at baseline | **64** |
| `len(explicit)` after Fix A alone | 60 |
| `len(explicit \| zoned)` after Fix A alone | **73** |

Fix A's agent's baseline number (52) is exactly `len(explicit)` —
explicit-trace-or-via nets only, excluding the 12 nets that are covered
*only* by a zone pour (real copper, just not a discrete trace: `SW_NODE`,
`DC_BUS_RTN`, `ac_l`, `ac_n`, and 8 others). Fix A's agent's after-fix
number (73) is exactly `len(explicit | zoned)` — the union. **The same
agent's own before/after comparison used two different conventions**,
which is why the reported delta (52→73, +21) doesn't match either a
consistent explicit-only delta (52→60, +8) or a consistent union delta
(64→73, +9). Fix B's agent used the union consistently in both directions
(64→61) and its number matches the audit module's own printed report line
verbatim (`[copper-audit] ... 64 carry copper (explicit trace/via or
zone)`), which is the tool's own internal definition of `has_copper`
(`NetCopperOutcome.has_copper = has_explicit_copper or has_zone_copper`).

**Verdict: Fix B's baseline (64) is correct; Fix A's baseline (52) is a
real undercount**, not a different run. A zone pour is physical copper; a
net covered only by a pour is not "missing copper," and excluding it from
"nets carrying copper" makes a legitimately-covered net indistinguishable
from a genuinely orphaned one — precisely the confusion
`topology_copper_audit.py` exists to prevent.

### 1.4 Fix: disambiguate the accessor

Added `nets_carrying_copper(pcb_content) -> set[str]` to
`topology_copper_audit.py` — the union, exposed as a single top-level call
so no future caller has to re-derive (or re-diverge on) the reduction from
the raw tuple. `nets_with_copper()` itself is unchanged (still returns the
pair, for callers like `audit_topology_vs_copper` that need the
explicit-vs-zone distinction). Added
`test_nets_carrying_copper_is_the_union_not_explicit_only` pinning the
convention. This is the **only** source change in this task beyond the
merge itself — no router behavior changed, so it cannot have affected any
routing measurement below (verified: the four production routes in
Problem 2 were run from worktrees where this function either doesn't
exist yet (baseline/Fix-A-only/Fix-B-only) or exists as a pure read-only
addition never consulted by the router (combined) — same routing code
path either way).

All existing `topology_copper_audit` tests plus the new one pass (11
tests, `packages/temper-placer/tests/router_v6/test_topology_copper_audit.py`).

---

## 2. Merge

New worktree `.claude/worktrees/router-combined` branched from `888331ba`,
never checked out in the primary checkout:

```
git worktree add .claude/worktrees/router-combined 888331ba -b agent/router-combined
git merge --no-edit fix/router-power-gnd-copper-gap investigate/stage4-astar-19nets
```

**Zero conflicts** — octopus merge succeeded cleanly (`51ade730` touches
only `_net_policy.py` + its test file; `6020b6be` touches only
`_astar_reconstruct.py` + a new evidence doc; no file overlap). Merge
commit: `a94ea10b`. All directly-relevant tests pass post-merge (32 tests:
`test_topology_copper_audit.py`, `test_astar_pathfinding.py`,
`test_forced_segment_fail_closed_pbt.py`, `test_decline_reason_contract.py`).

---

## 3. Four-configuration measurement, one methodology

Built 4 independent worktrees from `888331ba` (baseline unmodified, Fix A
alone, Fix B alone, both merged), each with its own freshly-built `.venv`
and pyo3 extensions (`uv sync --all-packages --inexact` + `make
extensions` — the workspace's `temper-placer` package itself is **not** a
default `uv sync` target, only `uv sync --all-packages` installs it; a
bare `uv sync` both fails to install it and evicts already-built maturin
`.so` files, a real trap hit and fixed during this task's setup). Ran, in
parallel, on all four:

```
TEMPER_BATCH_TRACE=1 uv run --no-sync python3 scripts/route_board.py \
    --pcb pcb/temper.kicad_pcb --net-batching --batch-size 10 \
    --output <config>_routed.kicad_pcb
```

Measured with `nets_carrying_copper()` (the now-unambiguous accessor)
directly on each output board's content — not copied from any prior
report:

| Config | Nets carrying copper | explicit-only | zone-only | Segments | Vias | Zones | should_route-excluded | Wall |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline (`888331ba`) | **64/110** | 52 | 12 | 3058 | 50 | 32 | 12 | 851.7s |
| Fix A alone | **73/110** | 60 | 13 | 3468 | 54 | 32 | 6 | 852.1s |
| Fix B alone | **61/110** | 47 | 14 | 2535 | 54 | 32 | 12 | 856.1s |
| **combined (A+B)** | **64/110** | 50 | 14 | 2579 | 50 | 32 | 6 | 862.4s |

("should_route-excluded" = nets `_should_route()` never hands to A* at
all — the denominator Fix A's fix shrinks from 12 to 6 by construction.)

Every baseline and Fix-A-alone figure above exactly reproduces what both
original agents independently reported (segments/vias/union-count all
match, see §1.2–1.3). Every Fix-B-alone figure exactly reproduces Fix B's
own evidence doc table (`64/110→61/110`, `3058→2535` segments,
`50→54` vias). The combined row is the only genuinely new measurement.

### 3.1 The combined effect, stated plainly

**Nets carrying copper: net-neutral (64 = 64).** Fix A's gain and Fix B's
cost are not both zero — they are opposite-signed changes that land on
the same total by coincidence, confirmed by diffing the actual net sets
(not just the counts):

- **6 nets gain copper** in combined vs. baseline: `+15V`, `PWR_RTN`,
  `V_BUS_SENSE`, `vcc` (4 of Fix A's 6 named orphans — `+3V3` and `gnd`
  remain unrouted even with Fix A, now genuinely attempted and fail
  closed, exactly as Fix A's own commit message predicted), plus
  `RTD_SCK` and `power_in.bypass_relay-coil2` as downstream
  routing-order effects.
- **6 nets lose copper** in combined vs. baseline: `PWM_LS`, `ZCD_ISO`,
  `ina`, `inb`, `safety.ovp.r_adc_top1-p2`, `y`. 5 of these 6 are also on
  Fix B's own evidence doc's "7 nets newly fail" list (Fix-B-alone vs.
  baseline); `y` is an additional downstream casualty unique to the
  combined run. The remaining 2 nets on Fix B's list — `a` and `zcd`,
  both `HighVoltage` — fail under Fix B alone but **do carry copper in
  the combined board** (verified directly:
  `nets_carrying_copper()` includes both `a` and `zcd` in both the
  baseline and combined sets). Fix B's stricter clearance is equally
  active in both configurations, so this is a genuine interaction effect,
  not simple additivity: Fix A routing the 6 previously-orphaned
  power/ground nets by A* changes downstream routing order/occupancy
  enough to free a legal path for `a`/`zcd` that Fix B alone, without
  Fix A's reordering, does not find. The two fixes are not independent
  on this board.

**Total copper volume drops.** Segments: 3058 (baseline) → 2579
(combined), **−15.7%**. Vias: 50 → 50 (unchanged; Fix A alone pushed vias
to 54, but Fix B's stricter clearance brings the combined figure back to
the baseline count). This is consistent with Fix B doing what it is
supposed to do — the routes that do complete under correct HV clearance
are not artificially inflated by borrowed SELV space.

**This is not "Fix A cancels out, so skip it."** Fix A closes a real,
distinct correctness gap (6 named nets with *no* copper-producing
mechanism at all, previously silently orphaned regardless of net-batching
or clearance correctness) — 4 of those 6 nets are routed in the combined
board that would not be routed at all otherwise. Fix B closes a
real, distinct safety gap (HV/HighVoltageIsolated copper's own occupancy
footprint being under-computed by up to 8.6mm during Stage 4's legality
check). That their aggregate net-count effects happen to cancel on this
particular board, at this placement, is a property of this board, not a
reason either fix is unnecessary.

**Per this task's instructions: a combined result no better than baseline
is an acceptable, reported-as-is finding.** No tuning, no cherry-picking
of which run to report — all four rows above are single, first-attempt,
production runs at commonly-used settings.

---

## 4. Problem 3: is the remaining 52-net gap placement-bound or clearance-envelope-crowding?

Instrumented one additional combined-config run
(`scripts/rcm_blocking_diag.py`, monkeypatching
`astar_pathfinding.run_astar_pathfinding` to capture the real
`RoutingFailureReport.blocking_nets` per failing net — never touching
production code, same technique Fix B's own evidence doc used).
**52 failures**, each cross-referenced against `design_rules.get_rules_for_net()`
for every one of its blockers, classifying a blocker as "large-clearance"
if its netclass is `HighVoltage`/`HighVoltageIsolated`/`ACMains` or its
clearance ≥ 1.0mm (the newly-correct-and-large envelopes Fix B introduced).

| | Count |
|---|---:|
| Failing nets total | 52 |
| ...with **zero** large-clearance blockers (pure ordinary-clearance congestion) | 14 (27%) |
| ...of those, with **zero blockers at all** (genuine A* search exhaustion, no straight-line obstruction found) | 3 (`discharge.r_snub1-p2`, `tank-out`, `w1_2`) |
| ...with **≥1** large-clearance blocker present | 38 (73%) |
| ...where large-clearance blockers are a **majority** of that net's blocker list | **0 (0%)** |
| Median blocker count | 7 (mean 7.4) — matches Fix B's own 5–20-blocker, median-7-9 finding |

**Finding: genuinely placement-bound, not an HV-clearance-envelope
artifact — confirmed by spot-check, with a nuance.** Zero of the 52
failing nets are blocked *primarily* by the new large-clearance
envelopes; every net with a large-clearance blocker in its list also has
at least as many ordinary-clearance (Default/FinePitch/Power/GND, ≤0.3mm)
blockers. Concretely:

- `RELAY_CTRL` (13 blockers, 4 large): blocked by 4 HV/HVIsolated-class
  nets (`discharge.k_dis1-nc`, `discharge.k_dis2-nc`,
  `hb.gate_hs.driver-p1-1`, `hb.gate_hs.driver-p2`, each 6.0mm) **and** 9
  ordinary nets at 0.1–0.3mm (`sclk`, `en`, `vcc`, `input`, ...).
  Removing only the HV blockers would still leave 9 real obstructions.
- `power_in.q_relay_drv-g` (18 blockers, only 1 large) and
  `rtd_pan.rail_monitor-outa` (17 blockers, only 1 large): dense
  ordinary-clearance congestion in the safety-comparator/RTD cluster,
  essentially unrelated to HV clearance.
- Even the nets Fix B's own doc flags as newly failing *because of* the
  clearance correction — `PWM_LS` (6 blockers, 2 large),
  `ZCD_ISO` (12 blockers, 1 large), `safety.ovp.r_adc_top1-p2`
  (11 blockers, 4 large) — still have a majority of ordinary-clearance
  blockers each. Reverting Fix B would not have freed these corridors on
  its own.
- `discharge.r_snub1-p2`, `tank-out`, `w1_2`: **zero** blockers of any
  kind — a genuine search/topology exhaustion, not a clearance question
  at all.

**Which remedy applies:** predominantly the first — placement density /
net-ordering, matching Fix B's own conclusion and the prior
`2026-07-27-forced-segment-analysis.md` finding on a similarly-shaped
failure set. For the 38 nets with *some* HV involvement (never dominant),
routing-order or layer-assignment changes in the HV-adjacent corridor
(SPI/RTD-bus and safety-comparator clusters, per Fix B's doc) could
plausibly recover a handful at the margin, but would not be sufficient
alone — the ordinary-clearance congestion in the same corridors is the
larger constraint in every single sampled case. Not a case of "the router
mechanism is wrong"; a placement/routing-order lever, not a clearance-rule
lever.

---

## 5. Sources / reproduction

- Baseline commit: `888331ba` (`fix(router): add topology-vs-copper
  divergence audit for net-batching's vacuous trace`).
- `fix/router-power-gnd-copper-gap` @ `51ade730`.
- `investigate/stage4-astar-19nets` @ `6020b6be`
  (`docs/evidence/2026-08-08-stage4-astar-clearance-mismatch.md`).
- Merge worktree: `.claude/worktrees/router-combined`, branch
  `agent/router-combined`, merge commit `a94ea10b`.
- Measurement worktrees (throwaway, not merged anywhere):
  `.claude/worktrees/router-combined-measurement` (baseline),
  `router-fixA-only`, `router-fixB-only`.
- All 4 production routes: `scripts/route_board.py --pcb
  pcb/temper.kicad_pcb --net-batching --batch-size 10`,
  `TEMPER_BATCH_TRACE=1`, run in parallel, one process per worktree, on
  the same machine.
- Problem 3 diagnostic: `scripts/rcm_blocking_diag.py` (committed
  alongside this doc), one additional combined-config run.
- Report script used for every "nets carrying copper" figure in §3:
  calls `topology_copper_audit.nets_carrying_copper()` directly on each
  routed board's written content — no ad hoc regex, no copied numbers.
