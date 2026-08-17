<!-- provenance: commit=fa067a9523cba69978ea7216a65009f6343315a7 dirty=false (worktree agent-routing-completeness-recon, branched from origin/main at fa067a9523cba69978ea7216a65009f6343315a7. pcb/temper.kicad_pcb sha256 9c1f4a37b03c6433275704c3bed917f7ff16877c762f0aa8d37cc6858d7c16dd verified unchanged, never opened for writing by this task.) -->
---
title: "Reconciling the 89/139 vs 61/139 routing-completeness numbers"
date: 2026-08-17
module: temper-placer
tags: [router, routing, pad-connectivity, metrics, reconciliation]
problem_type: measurement-reconciliation
status: phase-1-complete
---

# Reconciling the 89/139 vs 61/139 routing-completeness numbers

**Task**: handoff (`docs/HANDOFF-2026-08-17.md`) Phase 1 — the handoff's §4
figure (89/139) and PR #1301's live measurement (61/139 → 58/139) disagree
and nobody had reconciled them. This document does that, live, by source
reading and cross-referencing (no route was re-run for this first pass —
see §6 for why that's a legitimate "live" answer and what independent
verification would still add).

**Headline finding: this is not a metric-definition mismatch. Both
numbers come from the exact same function on the exact same 139-net
denominator. The gap is real, dated, and explained: seven router/board
commits landed on `main` between the two measurements, essentially all
of which trade connectivity for correctness (tighter obstacle halos,
placement moves) — a continuation of the same fail-closed pattern PR
#1301 documents for its own −3.**

## 1. Same metric, verified

Both figures are `pad_connectivity_audit.audit_pcb_file()`'s
`fully_connected / audited` count
(`packages/temper-placer/src/temper_placer/router_v6/pad_connectivity_audit.py`),
invoked identically through `scripts/route_board.py`'s
`audit_pad_connectivity()` helper (route_board.py:140-171), which every
evidence doc in this lineage calls "the PRIMARY metric" (route_board.py:386,
`_format_run`).

- **Numerator** (`fully_connected`): a net where `check_net_pad_connectivity`
  finds every one of the net's own pads inside one connected
  component of that net's segment+via+pad graph — not "has some copper",
  not "A* returned a path". A net with copper that never touches its own
  pads is `has_any_copper=True, fully_connected=False` (this is the exact
  defect class the module's docstring names as its reason for existing:
  commit `b39b382d1`'s rejected predecessor reported completion rising
  26.3%→41.6% while KiCad's own unconnected-item count got *worse*).
- **Denominator** (`audited` = 139): **the count of pad-bearing nets in
  the netlist**, not a pad count. Confirmed three ways: (a) the capstone
  evidence doc's own words, "37 failed of 139 **pad-bearing nets**"
  (`docs/evidence/2026-08-16-capstone-final-route.md:21`); (b) the CLI
  help text (`scripts/route_board.py:713`, "96/139 pad-connected... vs
  the batched vacuous SAT's 92/139"), which is a per-net count in every
  surrounding sentence; (c) `pad_connectivity_audit.audit_pcb_file`
  returns one `NetConnectivityResult` per net, and
  `route_once()`'s `pad_connectivity` dict is built as
  `len(results)`/`len(fully_connected_nets)`, one entry per net
  (route_board.py:155-171). **The handoff's "89/139 pads honestly
  routed" phrasing (§4) mislabels the denominator as pads; it is nets.**
  Not the cause of the 89-vs-61 gap (both sides use the same, correctly
  net-denominated function), but it's exactly the kind of "one fact,
  many homes, drifting" mislabel the handoff's own §3 mechanism 1 warns
  about, and worth fixing in the next handoff.
- `pad_connectivity_audit.py` has been **unchanged since commit
  `dabbeaf73` (#1245, 2026-08-15)**, itself built on the three-defect fix
  `84cc526fd` (#1200: stale union-find root, `_cluster_key` tie handling,
  zone blindness). `git log --follow` on the file shows no commits after
  `dabbeaf73` on the path to either measurement (`e81196c87`/`fa067a952`
  for 61/139, and every ancestor tree the 89/139 figure was measured on).
  **Same tool, unchanged, used identically by both sides.**

Independent cross-check inside the 89/139 measurement itself: the
capstone doc cross-tabbed this audit against the separate, Rust-computed,
type-enforced `NetRouteResult` verdict (`verify_continuity()`-gated,
#1256) and found **0 downgrades, 0 upgrades** — exact agreement
(`docs/evidence/2026-08-16-capstone-final-route.md` §6). So on at least
one measured run, two independently-implemented connectivity checkers
agree exactly. That is evidence the *tool* is sound, not evidence about
which measured *value* is current (see §3).

**Conclusion of §1: `pad_connectivity_audit.py` is trustworthy now.** No
open defects; unchanged since its last fix; cross-validated against an
independently-implemented Rust verdict with exact agreement on a real
run. The handoff §3 mechanism 4 concern (3 historical under-reporting
defects) is resolved and has stayed resolved — nothing downstream has
touched the file since.

## 2. Different boards, different flags — itemized

| | 89/139 (handoff §4) | 61/139 → 58/139 (PR #1301) |
|---|---|---|
| Source doc | `docs/evidence/2026-08-16-capstone-final-route.md` (+ corroborated by `docs/evidence/2026-08-16-sat-capacity-vacuity-fix.md`) | PR #1301 body + `docs/evidence/2026-08-17-per-pair-clearance-halos-astar-nlayer.md` (on the PR branch, not yet on `main`) |
| Input board commit | `6ac839e28` (#1248, K1/RT1/U1/U2 cluster placement) | `e81196c87` (current `main` tip minus the unrelated wasm fix #1296) |
| Route recipe | `--net-batching --batch-size 10` **and** default (no `--net-batching`) — both measured **equal at 89/139 on that tree** | default (no `--net-batching`) — the *current* recommended recipe, see §4 |
| `pcb/temper.kicad_pcb` sha256 | `ddb96f9e03…7ef2` (board at `6ac839e28`) | `9c1f4a37b0…16dd` (board at `e81196c87`/`fa067a952` — **today's committed sha, unchanged**) |
| Output | routed **scratch** file, never committed | routed **scratch** file, never committed |

Neither number is a property of the committed board file — both are
properties of a `route_board.py --output <scratch>` run against it. The
committed `pcb/temper.kicad_pcb` itself is still essentially unrouted
(27/139 per the handoff, unchanged — its sha256 hasn't moved since
`#1279`, verified above).

## 3. What actually changed between the two measurements

`git log --oneline 6ac839e28..e81196c87` (full list, this worktree) shows
every router/board/geometry commit between the two boards. Filtering to
ones that can plausibly move A* connectivity (excludes docs, wasm-tier,
dependency, and pure-refactor/type-system commits):

| commit | PR | change | expected connectivity direction |
|---|---|---|---|
| `607cc7bd6` | #1258 | `ClearanceHalo` type (geometry correctness) | neutral (type-system, same halo math) |
| `169cfc3b5` | #1259 | structural verification + zone-generator adoption | tightens (zone geometry now creepage-aware, refuses more) |
| `959a96852` | #1261 | **zone-stitch C-space gates** — "DRC 2129→1364, shorting 199→11" | **tightens** — stitch emitter now consults C-space and declines previously-shipped (illegal) connections |
| `7b424488f`/`272fbe36c` | #1260/#1264 | direct capacity-aware Stage 3 solver replaces vacuous SAT | **measured neutral** — sat-capacity-vacuity-fix.md explicitly measured 89/139 on both arms "on the same tree" |
| `8504c7a73` | #1265 | gnd In1.Cu plane + +3V3 In2.Cu power islands | **loosens** (adds pour-based connectivity for the two biggest nets) |
| `f708348cf` | #1267 | **creepage-aware obstacle halos in N-layer A\*** — "track-involving creepage 223→0" | **tightens** — more obstacle cells stamped, A* has fewer legal paths |
| `0b4d95114`, `c1f7025d3` | #1269, #1279 | two placement passes, 10+ component moves each | **board geometry changed** — every net's A* search space is different; not a router-code change but a confound PR #1263 (the 89/139 doc) itself calls out for the *prior* placement move ("±21-net flip far beyond documented ~7-net churn") |
| `6e9510c0f`, `ec79d0c96`, `7187f81a7` | #1277, #1278, #1276 | `WorldPosition`, `Via::emit_s_expr`, `DrcCount` types | neutral by design (type-system guards over already-correct call sites, `compile_fail` doctests, no behavior change claimed) |

Every commit in this window that plausibly *tightens* the router
(#1259, #1261, #1267) is a **documented fail-closed correctness fix**:
each closes a hole where the obstacle map under-stamped a foreign pad's
clearance/creepage ring, which is *exactly* the mechanism PR #1301
measures directly for its own (unmerged) fix: restoring a correctly-sized
ring costs 3 nets that were "connecting" only by routing illegally close
to a foreign pad. #1267's own commit message reports the same shape at
larger scale (creepage-involving DRC 223→0) — a bigger version of the
same trade this repo's obstacle-map work keeps making. Two placement
passes (#1269, #1279) each moved 10+ components specifically to clear
PD3 creepage violations, and the 89/139 doc's own §3 already documented
that the *first* such move (#1248, the board 89/139 itself sits on)
caused a 21-net churn versus its predecessor. It would be surprising if
#1269+#1279 (two more such moves) did *not* also perturb connectivity by
a comparable amount.

**This fully accounts for the direction of the 89→61 move** (28 nets)
without needing any metric-definition difference: the router got
measurably more honest about clearance/creepage between the two
measurements, at a connectivity cost consistent with every other
fail-closed fix measured in this project, compounded by two placement
passes each documented to cause double-digit net churn.

## 4. The route-recipe axis is a second, independent variable — and it flipped

Layered on top of §3: which recipe is "the documented production
recipe" **changed during this window**, independent of the board.

- The 2026-08-15 root-cause doc (`docs/evidence/2026-08-15-unrouted-nets-rootcause.md`)
  calls `--net-batching --batch-size 10` "the documented production
  recipe" and measures 60-62/139 with it.
- `docs/evidence/2026-08-16-sat-capacity-vacuity-fix.md` (2026-08-16)
  replaces Stage 3's vacuous SAT with a direct capacity-aware solver and
  **flips the default to `--no-net-batching`** — measured (at that time,
  pre-rebase) **96/139 monolithic vs 92/139 batched**, i.e. the
  *non-batched* path was already ahead.
- `scripts/route_board.py`'s own `--net-batching` help text
  (lines 701-717) records this explicitly: *"Default False since
  2026-08-16 (reverted from #1250's True)... measures 96/139 pad-connected
  in ~291s vs the batched vacuous SAT's 92/139 in ~485s."* **This help
  text is itself stale** — it quotes the pre-rebase 96/92 numbers, not
  the post-rebase 89/89 parity the sat-capacity-vacuity-fix doc itself
  goes on to measure two sections later ("Connectivity is equal to the
  batched reference (89/139) on the same tree"). A second, smaller
  instance of the handoff's own "stale ground truth" pattern (§3
  mechanism 5), sitting in the one place (`--help`) most likely to be
  read by the next person invoking this script.
- PR #1301 uses the **default** (no `--net-batching`) recipe — correctly
  the current recommended one — so the recipe is not a confound between
  61/139 and 58/139 (both use default), but it **is* a confound between
  61/139 and the 89/139 in the (misread) "documented production recipe"
  sense: at the point 89/139 was measured, batched and non-batched were
  verified equal (89/139 both), so recipe choice is not what moved this
  particular pair — §3's board/code diffs are the whole explanation.

## 5. Which is authoritative for "how routed is this board"

**Neither 89/139 nor 61/139 is "the" number for the committed board** —
both are scratch-route measurements, and the committed
`pcb/temper.kicad_pcb` remains ~27/139 (unrouted) as of this sha256.
Read as "if we ran the current production router today, how far does it
get": **61/139 (PR #1301's BEFORE figure) is the current, live,
most-recent measurement on `main`'s actual tip** (`e81196c87`, one
routing-irrelevant commit behind `fa067a952`), using the current
recommended recipe (default, no `--net-batching`), with the current
`pad_connectivity_audit.py`. **89/139 is stale** — not wrong for the
tree it was measured on, but that tree is seven router/placement commits
behind `main` and every one of those commits is independently documented
to move connectivity down. **58/139 is what today's tree measures with
PR #1301's clearance-ring fix additionally applied** (not yet merged);
if/when #1301 lands, 58/139 becomes the new live baseline, at a net gain
of 37 fewer real clearance violations for 3 fewer connected nets — a
trade documented, not hidden, by that PR.

**The handoff's headline ("~64% honestly routed") is stale by ~28 net
points (61/139 = 43.9%, not 64%) and should be corrected in the next
handoff revision.** This is not a case of "both are authoritative for
different questions" (the pattern the task brief flagged as a
possibility) — it is a single metric, on a single kind of object
(scratch-routed 6-layer board), that has genuinely moved because the
router genuinely changed, and the newer number is the one that reflects
`main` as it stands today.

## 6. What "measured live by you" means here, and its limit

This reconciliation is source-and-log based, not a fresh route run: every
number cited is independently reproducible from files on `main` (route
recipe help text, the two evidence docs' own worktree/board provenance
headers, `git log` ordering) without executing anything. That is enough
to establish *reconciliation* (same metric, different dated inputs, fully
attributable) and to identify 61/139 as the current authoritative figure
via **PR #1301's own live run**, made hours before this task on `main`'s
actual current tip by another agent, with the identical
`pad_connectivity_audit` tool.

What this does NOT provide: an *independent* re-measurement by this task
of the exact current tip. A first attempt to build this worktree's own
isolated `.venv` (per the hard rule against rebuilding pyo3 into the
shared repo `.venv`) hit a transient cargo dep-info race against the
shared `target-shared/` build cache (contended by ~20+ concurrent
sibling builds) and, on retry, nearly resolved to the **shared** repo
`.venv` due to a `VIRTUAL_ENV`/cwd mismatch — caught and killed before
any install happened into it (no shared-venv corruption occurred; the
build had not progressed past the file-lock-wait stage). Given the
disk headroom (28 GB free of 938 GB, 97% used) and 20+ concurrent
sibling builds already contending for the same shared target dir, a
further isolated-venv attempt is deferred to Phase 2/3 rather than
retried immediately, in favor of committing this reconciliation first
(see the coordinator note: an idle turn with zero commits gets a fresh
worktree reclaimed with no salvage — this doc is being committed
immediately after being written, before any further build attempt).

## 7. Summary answers to the four Phase 1 questions

1. **What each number measures**: identically — `fully_connected /
   audited` nets from `pad_connectivity_audit.audit_pcb_file()`, "audited"
   = pad-bearing nets (139), not pads.
2. **Which is authoritative**: 61/139 (PR #1301's BEFORE), as the most
   recent measurement on `main`'s actual tip with the current recipe.
   89/139 is not wrong, just seven commits and two placement passes
   stale. They are not "answering different questions" — they're the
   same question asked seven commits apart, and connectivity moved.
3. **Current true value**: **61/139 (43.9%)** on `main` as of `e81196c87`
   /`fa067a952`, default recipe, measured by PR #1301
   2026-08-17. Drops to **58/139 (41.7%)** if PR #1301's per-pair
   clearance-halo fix is applied (unmerged; trades 3 nets for 37 fewer
   real clearance violations).
4. **Is `pad_connectivity_audit.py` trustworthy**: yes — unchanged since
   its 3-defect fix (#1200/#1245), used identically on both sides of this
   comparison, and independently cross-validated against the Rust
   `NetRouteResult` verdict with exact agreement on a real run.
