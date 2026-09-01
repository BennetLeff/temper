<!-- provenance: commit=a434a9aa9f52b1b1407f4b934153ca1d740c7050 dirty=UNKNOWN -->

# Independent spike: the +113 `clearance` delta is essentially 100% real geometric regression, not newly-visible enforcement -- and PR #1051 could not have caused it either way

> **CORRECTION (2026-08-12), added by the void-board-baseline purge task.** §"Honest
> fidelity check" (segments target "4228", the "499/4228/66 headline figures") and the
> background reference to "94->44" both cite figures that are **VOID** -- PR #1050's
> 4,228/74 and `docs/evidence/2026-08-12-hvlv-candidate-board-measurement.md`'s 94->44,
> both measured on an unpinned `pumpkin_engine` build; see the correction notices on
> those documents. True segments/vias/zones baseline: **2,514 / 22 / 76** (168
> footprints); `SAF_HVL_001` **94 -> 74 (-21%)**. `scripts/board_shape_baseline.json` is
> the current source of truth. This document's own headline finding (the `clearance`
> delta is real geometric regression, not netclass-enforcement) was derived from this
> document's own independently-built candidate board -- also, necessarily, an
> unpinned-engine board, since this document predates #1060 -- and is reported as
> originally measured, not re-verified against the pinned-engine board by this
> correction.

**Verdict up front.** I built my own independent candidate board from scratch
(reconciliation -> Pumpkin placement -> `route_board.py --net-batching`,
methodology below) and ran the decisive 2x2 the task asked for, redefined
around the mechanism kicad-cli actually uses (see "Framing correction"
below, because the mechanism the task named, PR #1051, cannot be it).
**Result: on my candidate board, netclass-rule strictness changes the
`clearance` count by ~0, not by any material fraction of +113. Essentially
the entire delta is real, geometric, routing-caused congestion.** This
confirms the "regression is entirely real" branch of the task's own framing
-- the inconvenient, non-interesting answer -- and I am reporting it in
full, not softening it.

A second, structural finding, established by reading source before running
anything: **PR #1051 (`b94f8cc9d`) cannot mechanically affect kicad-cli's
`clearance` measurement at all**, in either direction. Its own commit
message says so ("kicad-cli DRC ceiling... unaffected... reads netclasses
from `pcb/temper.kicad_pro` directly, not from this Python path"), and I
verified it independently: the commit's diff touches only
`kicad_parser.py` + tests + docs, never `pcb/temper.kicad_pro`, and
`scripts/generate_kicad_dru.py`'s custom rules key exclusively on KiCad's
own `A.NetClass`/`B.NetClass` pad properties, which KiCad resolves from
`pcb/temper.kicad_pro`'s `net_settings` -- a completely different
resolution path from the Python `Component.net_class` field #1051 touched
(consumed only by the Rust safety-DRC kernels via
`run_drc(categories=["safety"]/["drc"])`, never by `kicad-cli pcb drc`).
If your own analysis attributes any of the +113 to #1051, that attribution
does not survive reading the diff.

---

## Framing correction: why the 2x2 cannot be run exactly as posed, and what I ran instead

The task's 2x2 axis is "old netclass rules (flat `Signal`, pre-#1051) vs.
new netclass rules (real per-class, post-#1051)." Per the structural
finding above, **this axis produces a hard, structural zero for
kicad-cli's `clearance` count** -- there is no experiment to run, because
`pcb/temper.kicad_pro` (the only place kicad-cli looks) never changed
across #1051 (`git diff <386-baseline-commit>..HEAD -- pcb/temper.kicad_pro`
is empty; the committed board's sha256 is identical before and after
#1051). Running the literal 2x2 as posed would just measure 386 in three
cells and undefined in the fourth (since #1051 doesn't touch the candidate
board's inputs either).

Rather than substitute reasoning for measurement, I ran the same
*conceptual* experiment against the lever that is actually real: I built a
synthetic `pcb/temper.kicad_pro` with `net_settings.netclass_assignments`
and `net_settings.netclass_patterns` both emptied, so every net on the
board resolves to the single loosest class (`Default`, 0.2mm clearance --
also the value `scripts/generate_kicad_dru.py`'s own netclass-independent
"Default routing" rule already enforces, Rule 10). This is a **strict
superset** of anything #1051 could have changed even hypothetically -- it
removes ALL netclass-granularity enforcement built by #1023/#1025/the
`generate_kicad_dru.py` safety-rule work, of which #1051 is not even a
member. If this maximal swing still doesn't move the candidate board's
count, no narrower, #1051-shaped swing could have either.

## The 2x2, filled

| | flat/no-netclass-granularity rules | current (real, as-committed) netclass rules |
|---|---:|---:|
| **committed board geometry** (`pcb/temper.kicad_pcb`) | **339** (339/339/339 across 3 runs -- deterministic) | **386** (386/386/386 across 3 runs -- exact match to `power_pcb_dataset/drc_ceiling.json`'s recorded ceiling) |
| **candidate board geometry** (independently reconstructed, see below) | **499-505** (505, 499, 501; mean 501.7, 3 runs) | **499-503** (500, 503, 499, 502, 502, 503, 500; mean 501.3, 7 runs) |

**Rules-only effect, holding geometry fixed:**
- Committed geometry: **+47** (386 − 339) — real, but this is the
  *entire* netclass-granularity build-out since before #1023, not
  anything #1051-specific, and it is already baked into both the
  historical 386 baseline and today's board identically (nothing changed
  here across #1051, confirmed by the empty diff above).
- Candidate geometry: **~0, not even consistently signed** (501.3 vs
  501.7 — the two means sit inside each other's own 3-7-run scatter band).

**Geometry-only effect, holding rules fixed:**
- At flat rules: **+160 to +167** (501.7 − 339).
- At today's real rules: **+113 to +117** (501.3 − 386) — matching the
  claimed +113 closely.

### Why the rules axis is ~0 specifically on the candidate board

I parsed every `clearance` violation's embedded rule name and required
value out of the raw kicad-cli JSON (`Clearance violation (rule '<name>'
clearance <req>mm; actual <actual>mm)`):

| | n | fires generic 0.2mm "Default routing" | fires an HV/ACMains/GateDrive-specific stricter rule (0.5mm-6.0mm) |
|---|---:|---:|---:|
| committed, current rules | 386 | 332 (86%) | 54 (14%) |
| candidate, current rules | 500 | **500 (100%)** | **0 (0%)** |

**All 500 of the candidate's clearance violations are generic
same-or-looser-than-Default-class copper packed inside the universal
0.2mm floor.** There is nothing for netclass-rule flattening to remove,
which is the direct, measured reason flat and current land in the same
place on this board. The 54 netclass-specific violations that DO
disappear under flat rules on the *committed* board (accounting for its
whole +47) simply have no candidate-board analogue at this placement.

## Priority-question verdict

**Of the ~113-117 net-new clearance violations, essentially all of them
(100%, within measurement noise) are real geometric regression, not
newly-visible enforcement.** Zero are attributable to PR #1051
specifically (mechanically impossible). At most ~0 are attributable to
*any* netclass-rule-granularity change of *any* kind, including changes
that predate #1051 entirely -- measured directly, not inferred: flattening
every netclass distinction on the board moves the candidate's count by an
amount smaller than its own run-to-run scatter. This is the plain,
uninteresting answer the task explicitly said was acceptable to report,
and it is what I found.

---

## Independent candidate-board reconstruction: methodology and honest fidelity assessment

I did not read or copy the exact placement/routing artifacts from the
`2026-08-12-place-and-reroute-connectivity.md` /
`2026-08-12-isolation-barrier-pumpkin-placement.md` lineage (they were
never committed; there is nothing to copy). I rebuilt a candidate from the
documented recipe, independently, in scratch space:

1. **Reconciliation**: `scripts/resync_pcb_netlist.py` against a fresh
   `elec/build/default.net` (already present, not regenerated by me), on a
   copper-stripped scratch copy of `pcb/temper.kicad_pcb` (2434 blocks
   stripped via `temper_placer.router_v6._strip_copper.strip_existing_copper`,
   same primitive `route_pcb`/`route_board.py` use). Required recovering
   `pcb/libs/Connector_JST.pretty/JST_XH_B4B-XH-A_1x04_P2.50mm_Vertical.kicad_mod`
   and its `fp-lib-table` entry from the unmerged `feat/board-sync-and-placement`
   branch (`git show d76bb27ed:...`), same prerequisite the prior docs
   name. Result: **kept 162, added 6 (`C37, J1, R65, T2, TP3, U19`), removed
   7 (`D2, R6-R10, U3`), moved 0 — exact match to every prior doc's
   reported delta.** Final board: 168/168 footprints matching the netlist
   exactly (re-running the script a second time confirms idempotence: 0
   changes).

2. **Placement**: Pumpkin (`docs/evidence/2026-08-07-pumpkin-engine`,
   built locally via `cargo build --release`), using the exact
   `_build_constraints` / wire-payload logic already checked in at
   `packages/temper-placer/tests/placer/cp_sat/test_golden_board_pumpkin_real_board.py`
   — netclass-aware `SEPARATED` constraints
   (`generate_netclass_separated_constraints`) backfilled with flat
   courtyard-tau pairs, **21,948 constraints total** (exact match to the
   isolation-barrier doc's own reported base-constraint count before its
   barrier is added), seed 42, solved `optimal` in 1.65s.
   **I deliberately did NOT add the PD2/8.0mm isolation barrier** the
   headline candidate board used — that requires a `"fixed_rotation"`
   Pumpkin-engine constraint type that exists only in an unmerged branch,
   not on `main`, and reproducing it was out of this spike's time budget.
   Round-trip oracle: PASS, 168 components / 521 pads verified.

3. **Routing**: `scripts/route_board.py --net-batching` (the documented
   flag), 4m42s wall clock.

### Honest fidelity check against the task's stated targets

| | target (documented) | my independent build | match? |
|---|---:|---:|---|
| footprints | 168 | **168** | exact |
| zones | 66 | **64** | close (97%) |
| segments | 4228 | **3017** | **not close (71%)** |
| vias | 74 | **32** | **not close (43%)** |
| containment violations | 2 / 527 pads | **137** (`check_board_containment.py`) | **not close** |

Per the task's own instruction, I am flagging this plainly rather than
papering over it: **this is not a faithful reproduction of the exact
candidate board the 499/4228/66 headline figures were measured on.** My
build differs in a real, identifiable way (no isolation barrier), and that
difference shows up clearly in containment and routed-copper density.

**Despite that, its `clearance` count landed at 499-503 (mean 501.3),
within 2-4 of the claimed 499.** I read this as a genuinely useful,
partial independent replication, not a full one: two materially different
placement/routing constructions on the same reconciled 168-component board
land in essentially the same place on this one metric, which is evidence
the regression is a property of this board's density at this component
count rather than an artifact of one specific pipeline's choices — but I
cannot claim to have reproduced *the same board*, only a board that agrees
on this number. `shorting_items` on my build (144, stable across all 7
runs) also does not match the documented 81, another sign of a genuinely
different construction, not measurement noise.

---

## Secondary questions

### Track/pad/via/zone breakdown (placement-caused vs. routing-caused)

Classified both items of every `clearance` violation by kind:

| | track-track | pad-track | pad-pad | track-via | pad-via | zone-involved |
|---|---:|---:|---:|---:|---:|---:|
| committed (n=386) | 254 (66%) | 59 (15%) | 38 (10%) | 19 (5%) | 16 (4%) | 0 |
| candidate (n=500) | **392 (78%)** | **107 (21%)** | **0 (0%)** | 1 (0.2%) | 0 | 0 |

Track-to-track dominance rises sharply (66%→78%) and pad-to-pad vanishes
entirely (10%→0%) on the candidate. **This is a routing-caused signature,
not a placement-caused one** — the regression is copper packed too close
to other copper, not components placed too close to other components.
This independently corroborates
`docs/evidence/2026-08-12-corridor-aware-plane-backbones.md`'s separate
finding that F.Cu congestion, not placement density, is the bottleneck.

Violations are concentrated, not diffuse: 45 distinct net-pairs behind the
candidate's 500 violations, with the top 6 pairs alone covering 400/500
(80%) — a `safety.ovp.r_div_top1-p2` / `discharge.r_snub1-p2` /
`power_in.bypass_relay-coil1` / `safety.coil_thermal-line` cluster
dominates, echoing the "concentrated in one congested region" shape the
prior doc reported for its own (different) net-pair list.

### Marginal vs. gross

Bucketed by `actual / required`:

| | marginal (actual ≥80% of required) | gross (actual <50% of required, nonzero) | exactly 0.00mm |
|---|---:|---:|---:|
| committed (n=386) | 98 (25%) | 97 (25%) | 1 (0.3%) |
| candidate (n=500) | **189 (38%)** | 137 (27%) | **0 (0%)** |

The candidate skews more marginal (38% vs 25%) and has zero dead-short-at-0.00mm
findings — consistent with "traces routed just barely too close together,"
not "components dropped on top of each other."

### Mains<->SELV net-new violations — flagged prominently, and NOT worse

By kicad-cli's own fired-rule name (the rules that specifically implement
reinforced HV<->LV separation — "HV to LV," "AC Mains to LV,"
"HighVoltageIsolated same side/to LV," "HV internal same footprint"):
committed has **30/386** such violations; candidate has **0/500**.

By a broader, independent check — classifying both violation-items' actual
net *names* against `pcb/temper.kicad_pro`'s own HV/ACMains/HighVoltageIsolated/GateDriveHV
assignments and glob patterns directly, not relying on which specific
kicad-cli rule happened to fire — committed has **96/386 (25%)**
violations touching one HV-domain net and one non-HV net; candidate has
**7/500 (1.4%)**.

**Under either measure, there is no net-new mains<->SELV clearance
violation on the candidate board — the count falls, it does not rise.**
This is scoped strictly to kicad-cli's own `clearance` category; it is a
different, narrower check than the custom Rust "HV/LV separation" kernel
metric the task's background cites (94→44 on the actual headline
candidate board, per `docs/evidence/2026-08-12-hvlv-candidate-board-measurement.md`)
and should not be read as agreeing or disagreeing with that number — I did
not re-measure that metric, and my differently-constructed board (no
isolation barrier) would not be a fair comparison against it regardless.

One residual finding worth flagging, not fixing: the candidate's 7
HV-domain-crossing pairs were all evaluated under the generic 0.2mm
"Default routing" bar, not a stricter HV-specific one -- meaning
`generate_kicad_dru.py`'s rule *conditions* did not fire for them even
though the underlying nets are HV-domain by `.kicad_pro`'s own
classification. This is the same class of rule-coverage gap
`docs/evidence/2026-07-28-drc-rule1-netclass-redo.md` already documents
(net-class is a necessary-but-not-sufficient proxy for safety domain), not
new, and present on the committed board too (25% of its HV-domain-crossing
pairs are also generic-rule-only) -- so it is a pre-existing gap, not a
candidate-specific regression.

---

## What could make this construction unfaithful, stated plainly

- **No isolation barrier**: the single largest known difference from the
  headline candidate board. It changes 8 components' positions/rotations
  and therefore every routed path near them — plausibly the reason my
  segment/via/containment counts diverge as much as they do, even though
  the aggregate `clearance` number happens to land close.
- **Single Pumpkin seed (42), single run**: I did not sweep seeds or
  re-solve; a different feasible placement at the same constraint set
  could route differently. I did not have budget to characterize this
  spread.
- **DRC run-to-run scatter**: I ran bare `kicad-cli` without the
  single-thread `KICAD_CONFIG_HOME` pin `_drc_api.py` applies in
  production; my committed-board runs were still byte-identical (386/386/386,
  339/339/339) but my candidate showed a small spread (499-505) that a
  pinned run might tighten. The rules-vs-geometry conclusion is unaffected
  either way — the flat/current means (501.3 vs 501.7) differ by less than
  this scatter band regardless of whether the band itself would shrink
  under pinning.
- **`.kicad_dru` regeneration**: I regenerated `pcb/temper.kicad_dru` via
  `scripts/generate_kicad_dru.py` fresh for each measurement (gitignored,
  never committed, same convention every cited prior doc uses) rather than
  reusing one fixed copy — if that script's output is non-deterministic in
  some way I didn't check, it could introduce noise I haven't accounted
  for. I did not find evidence of this (committed-board clearance was
  exactly reproducible across all runs).

## Sources measured directly

- `pcb/temper.kicad_pcb` (unmodified, sha256 6928b7c895...), `pcb/temper.kicad_pro`, `power_pcb_dataset/drc_ceiling.json`
- `scripts/resync_pcb_netlist.py`, `scripts/route_board.py`, `scripts/check_board_containment.py`, `scripts/generate_kicad_dru.py`
- `docs/evidence/2026-08-07-pumpkin-engine/` (built locally)
- `packages/temper-placer/tests/placer/cp_sat/test_golden_board_pumpkin_real_board.py` (constraint-building/wire-payload logic reused, not reimplemented)
- `packages/temper-placer/src/temper_placer/router_v6/_strip_copper.py`, `.../router_v6/adapter.py` (`_apply_placements_to_pcb`)
- commit `b94f8cc9d` (#1051) — full diff read, not just the message
- `git show d76bb27ed:pcb/libs/Connector_JST.pretty/...` (footprint recovery, `feat/board-sync-and-placement`, unmerged)
- All raw `kicad-cli pcb drc --all-track-errors --format json` output analyzed programmatically (rule-name/required-value regex parse, net-name domain classification against `pcb/temper.kicad_pro`'s own `net_settings`), not hand-sampled.
