<!-- provenance: commit=ea96b8b38aacfc4b732f5ade98b2756bbf38be0f dirty=UNKNOWN -->
     fast-forward of origin/fix/board-schematic-resync a3fbaff37 + origin/fix/t2-repair-entrypoint's
     one commit, PR #1144), dirty=false except this file. Own git worktree
     (.claude/worktrees/ocp02-subsystem-eval), never the main checkout. `make venv-isolate` run this
     session (unset CONDA_PREFIX first), all 10 pyo3/maturin crates rebuilt via `make extensions`
     after the merge (isolation_barrier.py changed), scripts/check_stale_extensions.py reports
     10/10 fresh, and every extension used below (temper_geometry, temper_placer.io.kicad_parser,
     temper_placer.placer.cp_sat._encoder_solve, temper_placer.cli.repair_commands) was confirmed to
     actually import and run before any measurement was trusted. kicad-cli 10.0.5. No
     pcb/temper.kicad_pcb or elec/src/** file was edited -- every solve below wrote only to scratch
     paths under /tmp/claude-*/scratchpad, never the tracked board, and every CP-SAT run used the
     committed board as read-only input. git status --porcelain clean; git grep -l "^<<<<<<< "
     empty, throughout. CORRECTED post-review, same session: §3 (Option 1) originally cited
     issue #871 as an open router OOM blocker; #871 is actually CLOSED/COMPLETED 2026-08-08.
     Re-verified firsthand (`scripts/route_board.py --net-batching`, real `/usr/bin/time -v`
     measurement against the committed board: 4.0GB peak RSS, exit 0, wall 452.3s) rather than
     trusting the issue tracker either way; §3 corrected in place with the real, current finding
     (router runs; this board's real primary-metric pad-connectivity is 38%, a congestion cost,
     not an OOM/crash blocker) and the ranking's reasoning downgraded accordingly (solver
     feasibility is "not attempted," not "proven infeasible"). Does not change §8's ranking or
     the headline recommendation, which rests on the independently-fatal creepage finding. -->

# OCP-02's three unplaced components (T2/C37/R65): options evaluation and recommendation

**Question asked:** PR #1144 (`fix/t2-repair-entrypoint`, merged into this worktree's baseline)
proved T2 (`safety.ocp2.ct`, Coilcraft CST3015 current transformer), C37 (`c_filter`) and R65
(`r_burden`) cannot be placed on the current board by incremental repair -- UNSAT on pure
courtyard geometry alone, independently re-verified below. This document evaluates the six
options the task specified and gives a ranked, costed recommendation.

**Headline finding, and why it reframes the whole question:** a parallel, not-yet-merged
investigation (`origin/investigate/cst3015-reinforced-isolation`, commit `ac5e62f8c`, opened as
**PR #1146**) found that
the CST3015 **cannot physically clear this board's own 12.6mm PD3 reinforced-creepage
requirement in this footprint, or in any drop-in replacement at the same ratio/current
class** -- its true intrinsic primary-to-secondary PCB separation is 9.100mm, 3.5mm short,
**independent of where on the board it sits**. This means Options 1 and 2 below (which only
attack the *placement* problem) cannot by themselves produce a compliant board: even a
perfectly legal placement for T2 as currently specified would still carry a 3.5mm reinforced-
creepage violation, because that gap is intra-footprint (primary pad to secondary pad), not a
function of neighbours. **The placement UNSAT and the creepage non-compliance are two
independent, both-fatal problems with the same part.** Every option below is evaluated against
both.

**Second finding, also load-bearing:** the CT is not the only part with this problem. Re-opening
`OCP02_DECISION_BRIEF.md`'s previously-rejected non-CT alternative (Option 3, an AMC1300 isolated
amplifier) as the task instructed surfaces a genuinely new result neither prior OCP-02 document
could have had: **AMC1300's own datasheet creepage (8.5mm) also falls short of the 12.6mm PD3
bar** (§5) once this repo's own 2026-08-12 pollution-degree determination is applied to it --
by 4.1mm, the same defect class as the CT. Switching sensing technology away from a CT does not,
by itself, sidestep the isolation problem on this board today.

**Recommendation, up front (reasoning in §8):** do not populate OCP-02 with the current CT-based
design now (Option 5); defer it until a mechanism change (Option 4, a bore/donut-primary CT) is
actually engineered for T1 *and* T2 jointly, since the parallel investigation shows T1 carries the
identical, currently-unresolved creepage defect already routed and shipped on the board today.
Options 0-3 are closed or do not clear the bar; ranked table in §8.

---

## 1. Re-verified baseline

Independently reproduced, this session, against the merged worktree (`temper-placer
repair-unplaced pcb/temper.kicad_pcb --refs T2,C37,R65 ...`, PR #1144's own tool, not a
reimplementation):

```
Phase 1 (fixed_copper + domain_clearance active, isolation-barrier auto-excluded --
pre-existing, unrelated UNSAT against the current board with everything frozen):
  status=infeasible (1678-1991ms across two runs)

Phase 2 (--displace T1 --max-displacement-mm 15.0):
  status=infeasible (1646ms) -- not a timeout (default budget 60000ms)
```

Matches PR #1144's own reported figures exactly (1.4s-class infeasibility proof, not a
solver timeout). T2/C37/R65 are confirmed off the board outline (x 20-172, y 20-254):
`T2 (100.0, 300.0)`, `C37 (0.0, 252.12)`, `R65 (24.0, 252.12)`, read directly from
`pcb/temper.kicad_pcb`. `power_pcb_dataset/drc_ceiling.json`'s own `_march` log (the
2026-08-13-board-schematic-resync entry) independently corroborates: the placement session that
produced the current board tried the prior feasibility study's candidate site and found it
"now occupied by PS1 (added after that study ran)," and the two other on-board sites tried
"either failed the 8mm SELV-isolation-adjacent courtyard check or landed pads directly on
existing, unrelated-net copper."

---

## 2. Option 0 -- is the courtyard over-drawn?

**Verdict: No. Closed, empirically re-verified beyond any legitimate correction.**

`pcb/libs/temper.pretty/CST3015.kicad_mod`'s own comment states the derivation directly:
*"Courtyard: body 23.0 x 30.0 and pads (x +/-12.18) plus 0.25mm margin. Body dominates in Y,
pads dominate in X."* This is drawn from "the official Recommended Land Pattern, Coilcraft
Document 1608-2" -- a standard IPC placement-courtyard margin (0.25mm) added to the part's own
real physical envelope (23.0x30.0mm body; pads that themselves extend past the body in X to
+-12.18mm), not a generously-padded safety keep-out. There is no slack to recover: in Y the
courtyard is set by the datasheet body max, in X by the pads' own copper extent -- both are
physically real, not drafting choices.

**Empirically re-verified this session, going further than documentation reasoning.** Using
this repo's own CP-SAT encoder (`temper_placer.placer.cp_sat._encoder_solve.solve_placement`),
courtyard-only (no `fixed_copper`, no `domain_clearance` -- matching PR #1144's own "pure
courtyard geometry alone" methodology), with T2/C37/R65 jointly free and the other 165
components frozen at committed positions:

| T2 courtyard tested | Basis | Result |
|---|---|---|
| 24.86 x 30.6mm | Committed (current) | infeasible, 855ms |
| 24.36 x 30.0mm | **Absolute physical floor** -- pad-extent x body-extent, the *entire* 0.25mm IPC margin removed on all four sides (physically impossible to build smaller without clipping actual copper or the datasheet body) | infeasible, 911ms |
| 90%, 75%, 50%, 35%, 25% of committed area (down to 6.09 x 7.50mm, 45.7mm² -- **16.6x smaller in area** than the real part) | Synthetic, not a real component | infeasible at every size, 828-930ms each |

Even a hypothetical component 94% smaller in area than the real CST3015 footprint does not
fit jointly with C37 and R65 among the current 165 frozen components, under courtyard geometry
alone. Correcting T2's courtyard cannot be the fix, at any size a real part could plausibly
take. **Not pursued further; do not shrink the courtyard.**

---

## 3. Option 1 -- full re-place

**Verdict: the solver question is genuinely "not attempted" rather than "proven infeasible" --
weaker grounds for ruling this out than originally stated. High cost either way; does not by
itself fix the creepage defect.**

> **CORRECTION (added after initial PR review, same session):** the first version of this
> document cited issue #871 as an open, unresolved router OOM blocker
> ("`docs/evidence/2026-08-07-router-silent-noop-diagnosis.md`, issue #871 ... the only path
> that builds a real model OOMs above 13GB RSS"). That was stale: **#871 is CLOSED,
> COMPLETED, 2026-08-08** -- fixed by the net-batching path (`scripts/route_board.py
> --net-batching`, `router_v6/net_batching.py`) one day after the diagnosis doc was written.
> Firsthand re-verification below replaces the stale claim; the router-related bullet is
> corrected, not deleted, per this repo's own `_march`-log convention of surfacing a checked
> correction rather than silently dropping it.

- Full-board entry point exists (`temper-placer optimize`, OR-Tools CP-SAT,
  `placer/cp_sat/loop.py:43-44`), but **the production engine does not complete even a bare
  feasibility solve on this board within its own 30s live budget** -- `status=unknown` at
  25.8-26.7s across 3 seeds (`docs/evidence/2026-08-11-pumpkin-real-budget-spike.md` §4.2). This
  claim is unaffected by the router correction below and still stands as cited.
- The experimental Pumpkin engine solves courtyard-+-bounds-only in 0.9-2.0s, but **has not
  been tested with `domain_clearance` (the 8mm reinforced tier) and `isolation_barrier` together
  in a full free-everything re-solve** -- the combination this task actually needs is unverified,
  not proven feasible or infeasible. Pumpkin is not integrated into `optimize` (spike only, "no
  line under `placer/cp_sat/**` touched"). **This is the correct verdict for the solver question
  on its own: "not attempted," not "proven infeasible."** Nothing in this document establishes
  that a full free-everything re-solve is actually UNSAT the way Option 0's courtyard question
  was established (§2) -- no brute-force or CP-SAT proof was run against the real constraint set
  at full-board scale.
- **Router status, re-verified firsthand this session** (not from the issue tracker either
  way): ran `scripts/route_board.py --pcb pcb/temper.kicad_pcb --net-batching --batch-size 10`
  (the exact flags issue #871's own fix added) against the current, unmodified, committed board,
  under `/usr/bin/time -v` for a real measurement, not an estimate:

  ```
  Result: 70/106 nets (66.0%)  segments=3331 vias=26 zones=80  wall=452.3s
  Result (pad connectivity, PRIMARY metric): 53/139 nets fully pad-connected
    fake-completion=46 honest-gap=40
  Maximum resident set size: 4,203,432 KB (~4.0 GB)
  Elapsed (wall clock) time: 7:32.95 (452.3s, matches the tool's own report)
  Exit status: 0
  ```

  **The OOM is genuinely fixed**: 4.0GB peak RSS, nowhere near the >13GB figure the original
  bug reported, and the run completes and writes a valid output board -- #871 was correctly
  closed. **But the router's output quality on this exact board, today, is real and poor,
  for a different, current reason, not a stale one**: by the tool's own labeled PRIMARY
  metric (pad connectivity, not the more permissive net-batching-stage completion number),
  only **53 of 139 nets (38%) are fully pad-connected**. 40 nets have a genuine "honest-gap"
  (`no legal path found`, zero copper), and 46 more are "fake-completion" (copper exists but
  does not join all of the net's own pads) -- this repo's own established distinction
  (`STRATEGY.md`: "The router is at roughly 79%, not 3.45%" is the same honest-vs-inflated
  metric question, resolved the same way there). A run also logged one
  `[LedgerReport IMBALANCED]` warning (`routing_complete` stage: `net_count: 112 -> 0`,
  `component_count: 168 -> 0`) whose cause was not investigated here -- noted, not
  characterized, since it did not stop the run from completing or writing a board.
  **Revised conclusion: the router runs and completes on this board today (#871 does not
  block it), but a full re-place's resulting board would still need to clear a real,
  currently-measured 38%-full-pad-connectivity baseline before being routable in practice --
  a routing-congestion cost, not an unrunnable-tool blocker.** This is weaker evidence against
  Option 1 than the original (incorrect) "unroutable by either code path" claim, but it is not
  zero evidence either: it is real, current, firsthand-measured congestion on the board as it
  stands, and a full re-place does not obviously make that better (more freedom to move
  components, but 168 of them instead of 3, all needing simultaneous legal positions).
- **Re-measurement burden**: `power_pcb_dataset/drc_ceiling.json`'s provenance is content-hash
  pinned to the board file; moving ~168 components (vs. 3) requires the same same-PR,
  ≥120-sample, per-category-attributed re-measurement discipline `AGENTS.md` already mandates,
  at a scale this repo has not exercised before.
- **Staleness surface**: 252 evidence files reference `kicad_pcb`; an unknown but nontrivial
  subset cite coordinates or measured distances tied to current positions and would need
  re-verification (not all -- many are methodology docs -- but the honest order of magnitude is
  in the hundreds, not itemized further here).
- **Does not fix T2's creepage defect.** Even a fully successful full re-place still places the
  same CST3015 footprint, whose primary-secondary creepage (9.100mm) is a fixed, intra-footprint
  property independent of where it lands.

**Cost: large, only partially bounded, and insufficient alone. The solver-feasibility question
is honestly "not attempted" rather than "proven infeasible" -- if that question mattered on its
own (it does not change the ranking here, since the creepage defect is independently fatal),
it would be worth actually running a full free-everything Pumpkin solve with the real
constraint set before concluding anything stronger than "unverified."**

---

## 4. Option 2 -- grow the board

**Verdict: not resolvable with current evidence; real risk of an enclosure violation; contrary
to the project's own stated direction; does not fix the creepage defect either.**

The current outline (152 x 234mm, `pcb/temper.kicad_pcb` `gr_poly (20,20)-(172,20)-(172,254)-
(20,254)`) was set 2026-07-25 as **"rung 1" of a deliberate tightening ladder**
(`docs/STRATEGY.md:279-284`): true pad extents (132.2 x 213.6mm) plus a flat 10mm margin,
explicitly *not* an enclosure decision, and explicitly meant to be **tightened further** toward
a "teardown enclosure envelope" at later rungs that were never reached. So the outline is loose
by construction -- but the project's own stated direction for it is to shrink, not grow.

The real mechanical constraint is a named physical enclosure, poorly characterized:
`docs/specs/REQUIREMENTS.md:431-434` requires the board fit inside a **vintage RCA 12A3
tube-amplifier chassis**, external dims "~230mm W x 180mm D x 120mm H (approximate, **needs
verification**)," with internal clearance and mounting holes both **TBD**. Separately,
`docs/evidence/2026-07-30-pcb-compartment-thermal-bound.md:74-79` flags that **the current
board's 234mm length already exceeds the chassis's own stated 230mm width figure** -- "one of
these two repo figures is wrong; this document does not resolve which."

No verified chassis interior dimension exists anywhere in the repo to check a larger board
against; the one real data point argues the board may already be at or past the enclosure's
own limit. Growing the outline would also trigger the same full DRC-ceiling re-measurement
obligation as Option 1 (`AGENTS.md`), and no PCB-fab cost-tier data exists in this repo to price
a size increase (an invented $ figure would violate the task's own rule against fabricated
figures). **And even if room existed, this does not address T2's independent 3.5mm creepage
shortfall.** Cannot be shown feasible or infeasible; cannot be recommended as-is.

---

## 5. Option 3 -- non-CT sensing (`OCP02_DECISION_BRIEF.md` Option B, `AMC1300DWVR`)

**Verdict: reopened per the task's instruction, and the reopening surfaces a new problem the
2026-08-07 documents could not have seen -- Option B no longer clears this board's *current*
reinforced-creepage bar either.**

`OCP02_DECISION_BRIEF.md` (2026-08-07) and `OCP02_QUANTIFIED_TRADEOFF.md` (2026-08-07)
evaluated Option B (AMC1300 isolated amplifier reading the existing shunt at `DC_BUS_RTN`,
replacing the CT) against the board's *then*-enforced PD2 figures: **6.4mm clearance / 8.0mm
creepage**. AMC1300 clears that (5000Vrms UL1577, "creepage >=8.5mm," decision brief §3.2,
verified against TI's own datasheet). But `docs/evidence/2026-08-12-pollution-degree-
resolution.md` (five days later, on this same baseline) determined **PD3 governs the as-built
board now** -- the PD2 compartment prerequisite (`docs/specs/pd2_compartment_evidence.yaml`)
does not exist and its own check script fails. Under PD3, the applicable reinforced-creepage
figure at this board's >250-<=400V working-voltage band is **12.6mm**
(`docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` Table 17, IS 302-1:2008). **AMC1300's own 8.5mm
creepage falls 4.1mm short of 12.6mm** -- the same defect class (part-intrinsic isolator
creepage below the governing PD3 bar) as CST3015, just discovered here for the first time
against the current governing pollution degree.

This is a genuinely new finding this document contributes, not a restatement: at the time
Option B was evaluated and ranked runner-up, it looked like it sidestepped the isolation
problem entirely (a certified isolator IC replacing a CT). It does not, once PD3 -- which the
repo had already separately determined governs -- is applied to it. Everything else the prior
documents found about Option B's cost stands unchanged and gets worse on top of this: the
tightest timing margin of any candidate (20.6% guaranteed-worst-case-over-temperature, intrinsic
to the part, not improvable), and a genuinely new isolated-bias-supply subsystem (the brief's
cited `UCC14140-Q1` is only basic-isolation; the correct reinforced part, `UCC14141-Q1`, was
out of stock at the time it was checked and still cannot produce AMC1300's required 4.5-5.5V
directly, needing an added LDO). **Not recommended: does not clear the current creepage bar,
and carries the largest standalone cost of any option even before that finding.**

---

## 6. Option 4 -- a physically smaller/different current transformer

**Verdict: the only technical path in this repo's evidence chain that plausibly resolves both
problems at once (creepage AND footprint) -- but unfinished, requires an `elec/`+mechanical
redesign this task cannot execute, and lacks a verified reinforced-insulation certificate on the
specific parts checked.**

`docs/evidence/2026-07-30-pd3-part-selection-k1-c6-t1.md` §3 (this repo's own prior, exhaustive
search) already ruled out every PCB-trace-primary 1:100-ratio, >=50A-sensed transformer
(Coilcraft CST1211/CS4xxx/SCS, TDK B78419A) as having equal-or-worse creepage than the incumbent
CST3015 -- **no drop-in swap exists**. Its §3.5 follow-up measured a real, different mechanism:
**donut/aperture-primary CTs** (Talema ASM, ICE Components CT07/08/10), where the primary is not
a PCB pad at all -- the mains conductor threads through the core's bore as a wire or bus bar. For
ICE CT07-1000 specifically (measured from the manufacturer's own dimensioned drawing, this
repo's session): secondary pins (1/2/3, all secondary) cluster at **7.62 x 7.62mm** on the PCB
around a **9.20mm bore** -- an order of magnitude smaller footprint than CST3015's 24.86 x
30.6mm courtyard. Because the primary is off-PCB, **primary-to-secondary creepage becomes a
board-layout choice, not a fixed component number**, and can plausibly be built to clear 12.6mm
by construction. Electrically, converting the burden resistor for a 1:1000-ratio part at the
same trip point is a single value change (worked out concretely for OCP-01's own 50A trip:
4.99Ω -> 49.85Ω, and it *reduces* burden dissipation).

**What is not established, and this document does not invent:** no third-party
reinforced-insulation certificate (VDE/ENEC/CB/UL-recognition specifically covering IEC
60335-1/60664-1 insulation coordination) was found for the ICE Components parts checked -- only
a manufacturer hipot test result, the same gap class CST3015 itself has. This is a real,
still-open gap, not a solved recommendation. Pursuing it requires: (a) finding or verifying a
certified aperture-primary CT (not done here -- would need a fresh datasheet/certificate search,
out of this determination-only task's scope), (b) an `elec/src` schematic change (new component,
new burden value, new primary-routing topology) -- **forbidden by this task's hard constraints**,
and (c) a mechanical assembly change (routing the AC line as a discrete conductor through a bore
rather than continuous PCB copper).

**Merges with Option 0/the creepage finding, per the task's own framing**: since CST3015 already
fails PD3 creepage independent of placement, and this is the only mechanism found that plausibly
clears both the safety bar and the footprint problem simultaneously, this is the recommended
*target end state* -- for T1 and T2 jointly, since T1 carries the identical creepage defect
already on the shipped board (PR #1146,
`docs/evidence/2026-08-13-cst3015-reinforced-isolation-capability.md`). This is corroborated by
a second, independent open PR: **#1140** (`investigate/t1-isolator-hv-lv-creepage`) separately
found T1 carries 8 live, *routing*-caused creepage/clearance violations today (worst 0.3715mm
against the 8.0mm PD2 bar the DRU currently enforces -- 21.5x short; 33.9x short against the
12.6mm PD3 figure that actually governs), on top of, not instead of, the intrinsic 9.1mm-vs-
12.6mm footprint shortfall PR #1146 measures. T1 is not a clean precedent to copy for T2; it is
itself broken two ways right now. Option 4 is not executable within this task's constraints;
it needs its own scoped engineering effort, for both CTs together.

---

## 7. Option 5 -- is OCP-02 required?

**Verdict: not IEC 60335-1 clause-mandated. A project-chosen defense-in-depth acceptance-test
item. De-scoping is a legitimate option with a stated, bounded safety cost.**

No IEC 60335-1 clause cited anywhere in this repo requires a second/redundant overcurrent-
sensing channel -- a repo-wide search of every IEC 60335-1 clause citation on record (clauses
3.4.2/3.4.4 SELV, 19 and 29.1/29.2/29.2.3/29.2.4 abnormal-operation/insulation-coordination/
creepage, 27.1/27.5 earthing) turns up nothing about overcurrent-sensing redundancy, and
`OCP02_DECISION_BRIEF.md` §6 -- the document that already asked this question -- never cites a
clause either; its case for building OCP-02 is "it's buildable" and "it's a numbered
acceptance-test line item," not "compliance requires it."

`docs/FUNCTIONAL_TEST_CRITERIA.md:48-49` (this project's own internal acceptance bar, no
external standard cited on the table):

```
| Primary OCP    | 50A Peak | 45 - 55 A | < 1 µs |
| Secondary OCP  | 60A Peak | 55 - 65 A | < 5 µs |
```

`docs/hardware/BOM.md` §5.4's accepted-residual-risk table frames OCP-01 and OCP-02 as
covering "most of the same fault space," with both jointly still missing shoot-through, gate-
drive degradation, device-local shorts, and response-speed-vs-fastest-possible-short -- i.e.
OCP-02 narrows a margin both channels already only partially cover; it does not close a gap
OCP-01 alone leaves uniquely open in a compliance sense.

**Precise, stated cost of not populating:** fails `FUNCTIONAL_TEST_CRITERIA.md`'s "Secondary
OCP" acceptance-test line item (internal, not a certification requirement), and removes the one
sensing path that specifically covers a shoot-through fault physically crossing `DC_BUS_RTN` --
a path OCP-01's tank-return CT does not sense by construction (`OCP02_DECISION_BRIEF.md`
§3.1). This is a real, bounded redundancy loss, not a new uncovered fault category beyond
what BOM.md §5.4 already accepts as residual risk for the combined OCP-01+OCP-02 design.

---

## 8. Ranked recommendation

| Rank | Option | Verdict | Fixes placement? | Fixes creepage? |
|---|---|---|---|---|
| **1 (do now)** | **5 -- do not populate OCP-02** | Legitimate, bounded, stated safety cost; not compliance-mandated | N/A (moot) | N/A (moot) |
| **2 (scope separately)** | **4 -- aperture/donut CT mechanism change, for T1+T2 jointly** | Only path found that plausibly fixes both problems; unfinished (no verified reinforced cert; needs `elec/`+mechanical redesign out of this task's scope) | Yes, plausibly (footprint ~16x smaller) | Yes, plausibly (creepage becomes routing-controlled) |
| 3 (closed) | 0 -- courtyard over-drawn | Empirically closed; not over-drawn, re-verified past the physical floor | No | No (not applicable) |
| 4 (closed, new finding) | 3 -- AMC1300 isolated amplifier | No longer clears the governing PD3 bar (8.5mm vs. 12.6mm); largest standalone cost of any option | N/A (smaller part, but moot) | **No** |
| 5 (insufficient alone) | 1 -- full re-place | Solver feasibility genuinely **not attempted** (production engine timeout, Pumpkin untested on full constraint set) -- not "proven infeasible." Router itself runs today (#871 fixed 2026-08-08, re-confirmed firsthand: 4.0GB RSS, exit 0), but this exact board's real, current pad-connectivity is only 38% (53/139) by the primary metric -- a congestion cost, not a tool blocker. Large re-measurement burden either way | Unproven | No |
| 6 (insufficient alone, least resolvable) | 2 -- grow the board | No verified enclosure dimension exists; board may already exceed the one cited enclosure figure; contrary to project's own shrink-direction | Unproven | No |

**Why 5 over 4 as the immediate action, not the reverse:** Option 4 is the technically correct
long-term fix but cannot be executed inside this task's hard constraints (no `elec/src` or
`pcb/` edits) and has an open certification gap that is itself a research task, not a quick
follow-up. Fielding OCP-02 today with a part that is independently proven to violate this
board's own 12.6mm reinforced-creepage requirement -- regardless of where it is placed -- is a
worse safety posture than not fielding it: a "redundant protection channel" that is itself a
codified creepage violation is a liability sitting on the board, not a safety net. De-scoping
now, and re-evaluating OCP-02 once T1/T2's shared CT-creepage defect is actually resolved (a
fix the parallel investigation already shows T1 needs regardless of this decision), is the
option that is both immediately actionable and does not ship a known violation.

**What would change this recommendation:** a verified, third-party-certified aperture-primary CT
(closing Option 4's open gap) would flip the ranking -- at that point Option 4 becomes directly
buildable and OCP-02 should be built with it rather than left de-scoped. A materially different
governing pollution-degree finding (e.g., a real, inspected PD2 compartment closing the gate
`scripts/check_pd2_compartment_evidence.py` currently fails) would also reopen Options 0/3 by
changing the 8.0mm-vs-12.6mm bar both are measured against -- neither has happened as of this
document.

---

## 9. What is NOT established here (explicit, per the task's evidentiary bar)

- No dollar cost is given for growing the board (Option 2): this repo carries no PCB-fab
  size/cost-tier data, and inventing one would violate the task's rule against fabricated
  figures.
- Option 1's Pumpkin engine has not been run against the real safety constraint set
  (`domain_clearance` + `isolation_barrier` together, full free-everything re-solve) on this
  board -- flagged as unverified, not assumed to transfer from the courtyard-only spike result.
- No specific aperture-primary CT part with a verified third-party reinforced-insulation
  certificate is named for Option 4 -- this document does not invent one; closing this is a
  distinct, scoped research task.
- The RCA 12A3 chassis's actual interior dimensions (Option 2) remain unverified anywhere in
  this repo ("TBD" in `docs/specs/REQUIREMENTS.md` itself).
