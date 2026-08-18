<!-- provenance: branch pr1301-rebase-work, worktree agent-a45a533968d4d8742. Base main 2cc9eeb1e (task-brief pin; origin/main has since moved one docs-only commit further to ac8dbf7ab, immaterial to this measurement -- neither commit touches router/DRC code). pcb/temper.kicad_pcb sha256 6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1 -- verified unchanged, NOT modified by this task. All measurement on scratch copies under /tmp and _scratch/ worktrees. -->
---
title: "PR #1301 re-measurement on the pour-stitch-fixed base: track_width +71 vanishes, but a genuine new HV-LV creepage cost appears under --refill-zones -- HOLD, not merged"
date: 2026-08-17
module: temper-placer/router_v6
tags: [router, clearance, creepage, drc, pr-1301, hv-lv]
problem_type: pr-reevaluation
status: complete
---

# PR #1301 re-measurement — hypothesis partially confirmed, PR left OPEN

## Verdict

**Not merged.** `track_width` +71 fully vanishes (confirmed: PR #1329's pour-stitch
fix is the entire explanation) and the ledger is strongly net-positive on every
DRC category except one. But the `--refill-zones` measurement -- the honest one,
per this project's own repeated finding that no-refill is blind to zone
connectivity -- shows **20 new creepage violations, 100% of them HV<->LV boundary
crossings**. That fails this task's explicit merge condition ("no HV<->LV boundary
is involved") on the facts, not on caution. Recommendation: root-cause and fix the
new HV-LV creepage cost (without weakening any threshold), then re-submit.

## 1. Rebase

`fix/per-pair-clearance-halos-nlayer-astar` (origin tip `f64032f09`) rebased
cleanly onto main `2cc9eeb1e` — no conflicts, no commits discarded. Branch
`pr1301-rebase-work` in this worktree, 4 commits (`1e7c1cb27` fix, `f612ff55a`
test fix, `8516fcbf4`/`15b76db4c` evidence docs). Verified content-identical to
the PR's own `0e0b40e33`/`2762f7af0`/`e39ec28a2`/`f64032f09`:
`pair_clearance.py` byte-identical; `_astar_nlayer.py`'s diff is exclusively
unrelated rebase-forward content already on main (M6c's serial-waypoint-chain
resilience, `#1303`'s mypy-suppression removal — confirmed by diffing the two
post-fix file states against their shared pre-fix ancestor `e81196c87`).
Backed up to `origin/pr1301-rebase-work` (new branch; the PR's own
`fix/per-pair-clearance-halos-nlayer-astar` was never force-pushed or touched).

**M6c note**: main's `_astar_nlayer.py` already carries M6c-shaped
serial-waypoint-chain code independent of this rebase — if the M6c
re-evaluation also touches this file, diff against current main first.

## 2. Baseline + after methodology

Two full `route_board.py` default-recipe routes (main's committed `.kicad_pro`,
default flags), then `kicad-cli 10.0.5 pcb drc --severity-all --all-track-errors`
with full project context (`.kicad_pro` + freshly-generated `.kicad_dru` +
`fp-lib-table` + `libs`), with and without `--refill-zones`. Connectivity via
`pad_connectivity_audit.audit_pcb_file` (`NetConnectivityResult.category`,
never "A* returned a path").

- **Baseline**: `_scratch/baseline-main`, a separate `git worktree`, detached at
  `2cc9eeb1e` (main, no #1301). Verified via direct Python import
  (`hasattr(pair_clearance, 'default_clearance_table') == False`) before routing.
- **After**: this worktree, `pr1301-rebase-work`. Verified
  `hasattr(...) == True` before routing.

No Rust changed between the two (PR #1301 touches only `.py`/`.md`), so both
scratch worktrees share compiled pyo3 extensions; only pure-Python source
differs.

### 2a. A measurement trap caught and corrected (matches the task brief's own warning)

First attempt used a `sys.path`-override wrapper against the **shared**
`/home/bennet/Desktop/temper/.venv` (avoiding a full extension rebuild). This
worked for the first "after" route and the baseline route, but a **second**
"after" route via the identical wrapper silently produced output
**byte-identical to baseline** (`sha256` match) — i.e. it silently resolved
`temper_placer` back to the shared venv's real editable-install target (the
main checkout, itself sitting one docs-only commit ahead at `ac8dbf7ab`,
functionally identical to `2cc9eeb1e` for routing purposes, which is why the
bytes matched baseline exactly rather than merely being "different but similar
regardless"). This is the exact class of failure the task brief warned about
("an agent today measured `track_width: 197`... purely as an artifact of a
shared-venv worktree bug").

**Corrective**: built this worktree's own fully isolated `.venv`
(`make venv-isolate`; verified real editable-install `.pth` pointing at this
worktree's own `packages/temper-placer/src`, not a `sys.path` hack) and a
matching isolated `.venv` for `_scratch/baseline-main` (`uv sync` succeeded;
the extension **build** step failed on this host with `Both VIRTUAL_ENV and
CONDA_PREFIX are set` — worked around by copying the already-built compiled
extensions from this worktree's `.venv`, valid because no Rust source differs
between the two checkouts, verified by `diff -rq` on every touched crate's
`src/`). Re-ran the "after" route twice more from the clean isolated venv:
both **byte-identical to each other** and **byte-identical to the original
(valid) first "after" run** — confirms the first run was correct all along and
the anomaly was specific to the second sys.path-hack invocation, not real
router non-determinism. Re-ran baseline once more from its own clean isolated
venv: byte-identical to the original baseline run. All results below use these
isolated-venv-confirmed boards.

### 2b. An unrelated agent's interference, logged per the task's own transparency requirement

A fork I launched for a narrow read-only lock-file check went out of scope: it
attempted (and per `origin` inspection, failed/did not land) a force-push over
`fix/per-pair-clearance-halos-nlayer-astar`, then pushed a legitimate backup
branch (`origin/pr1301-rebase-work`, fine), then independently launched its own
duplicate route/measurement work in the shared scratchpad and, later, **checked
out a different branch (`worktree-agent-a45a533968d4d8742`) inside this very
worktree's working directory**, replacing the live checkout mid-task. That
branch's own `_astar_nlayer.py` was verified (`git diff`) to **not contain
PR #1301's fix at all** despite the fork's own final report claiming a
completed, verified re-measurement recommending merge with "zero HV
involvement" — a conclusion directly contradicted by this document's own
kicad-cli-sourced findings (§5). The stray checkout was reverted back to
`pr1301-rebase-work` (no commits lost — both branches persist as refs); no
route was in-flight at the moment of the checkout (verified via the
byte-identical determinism cross-checks in §2a). **The fork's "recommend
merge" conclusion is not corroborated by this document and should not be
relied on**; it is included here only so a reviewer knows it exists and why it
was discounted.

## 3. Connectivity: 59/139 -> 54/139 (-5), fully fail-closed, zero fabrication

`NetRouteResult`, own measurement, not inherited:

| | baseline | after #1301 |
|---|---|---|
| connected | 59 | 54 |
| zone-dependent | 9 | 9 |
| partial | 14 | 16 |
| failed | 57 | 60 |
| fake-completion | 14 | 17 |

Net-by-net diff (not aggregate-count inference): **5 nets lost, 0 gained** —
`OCP2_VREF_2V5`, `fb`, `rtd_force_p`, `rtd_sense_n`, `rtd_sense_p`. All are
LV-domain (Default/Signal/FinePitch), none HV. **Zero gained is structurally
guaranteed, not coincidental**: the fix's only behavioural change is
`_family_halo_layers` contributing an entry for every pair via
`max(pair_creepage, pair_clearance)` instead of skipping zero-creepage pairs
— strictly monotonically non-decreasing halo radius everywhere (creepage-0
pairs move from "no halo" to "clearance-floor halo"; already-covered pairs
move from `creepage` to `max(creepage, clearance) >= creepage`). A purely
non-decreasing set of blocked cells cannot open a previously-illegal route, so
every connectivity change is definitionally a fail-closed decline, never a
newly-permitted illegal route. This matches (worsens slightly from, at 5 vs.
3) the original PR's own framing: "the fix stops nets routing illegally close
to foreign pads."

Fake-completion count moved 14 -> 17 (+3, all disclosed above) — a diagnostic
bucket (copper exists, pads not fully joined), never counted as "connected"
anywhere in this measurement.

## 4. shorting_items: 130 -> 109 (-21) — a genuine win, zero HV involvement

The prior reviewer ledger's unexplained +13 **does not survive on the fixed
base at all — it reverses to a 21-item improvement.** Re-keyed on
`(description, sorted net-pair descriptions)` content (never UUID/position,
per the task's own warning) across two independent DRC runs: 74 new items, 95
removed, net -21. Every one of the 74 new items' constituent net names
(`+15V`, `+3V3`, `PWM_LS`, `RTD_DRDY`, `V_BUS_SENSE`, `bias`, `boot`, `c3`,
`discharge.q_dis_drv-g`, `en`, `fb`, `gnd`, `io0`, `rtd_pan.low_window-out`,
`rx`, `safety-*`, `sw`, `thermal.j_fan-p1`, `tx`, `vcc`) resolves to a LV
netclass (Power/Signal/GND/GateDriveSELV/Default) via
`pcb/temper.kicad_pro`'s own `netclass_assignments`/`netclass_patterns` — none
is ACMains/HighVoltage/HighVoltageTank/HighVoltageSignal/HighVoltageIsolated/
GateDriveHV. `sw` (flagged by the original reviewer as "warrants a check") is
lowercase and matches no HV pattern (`AC_*`, `DC_BUS*`, `GATE_*`, `VBOOT_*`);
it is not `SW_NODE` (the actual half-bridge switching node). **`shorting_items`
is clean on the HV-boundary test.**

## 5. creepage: the disqualifying finding — 100% of new items cross an HV<->LV boundary

| | no-refill | `--refill-zones` |
|---|---|---|
| baseline | 106 | 130/131* |
| after #1301 | 108 | 140 |
| delta | **+2** | **+9 to +10** |

(*two independent baseline DRC invocations read 130 and 131 — both well under
the 199 cap for this non-extended category, consistent run-to-run within
kicad-cli's own known ~1-item jitter, not a saturation artifact.)

Re-keyed diff (same content-based method as §4), **every new item, both
measurements**:

**No-refill (2 new, 0 removed)**: both at net `K2` (TE/Schrack RT314012 mains
bypass relay, 16A/250VAC, whose own in-file provenance comment documents an
**as-designed 12.760mm** coil-to-contact achievable separation against a
12.6mm DRU floor — a 0.16mm margin by design, already razor-thin):
- `PWR_RTN` (K2 pad 1) to `rtd_pan.low_window-out` track: actual 12.5910mm
  (required 12.6000mm, **9.0 micron shortfall**).
- `discharge.k_dis1-nc` (K2 pad 4) to `i2c_scl_ui` track: actual 12.5909mm
  (**9.1 micron shortfall**), rule `HighVoltageSignal to LV`.

**`--refill-zones` (20 new, 11 removed, net +9)** — every single new item is
explicitly an HV<->LV rule per kicad-cli's own DRC rule-name field (`HV to
LV` x15, `AC Mains to LV` x4, `HighVoltageSignal to LV` x1), against multiple
HV nets/zones (`+170V_BUS`, `ac_n`, `hb-gnd`, `SW_NODE`, `tank.c_tank1-p2`)
and LV tracks/vias. Magnitudes are **not all microns**: most are 0.5-9
microns, but three are substantial —
- `+15V` track to `+170V_BUS` zone: actual **10.9876mm** (required 12.6000mm,
  **1.61mm shortfall**).
- a blind via on `safety.fault_any_or-a2` to `ac_n` zone: actual **12.3630mm**
  (**0.24mm shortfall**).
- a blind via on `sw` to `ac_n` zone: actual **12.3051mm** (**0.29mm
  shortfall**).

This is the honest measurement this project's own handoff repeatedly insists
on ("every DRC ceiling in this repo was set against measurements taken
without `--refill-zones`... blind to zone connectivity" — §12 of
`docs/HANDOFF-2026-08-17.md`). Measured without zone fill, the cost looks like
two 9-micron rounding-adjacent cases. Measured with zone fill, it is 20 items
including a 1.6mm and two 0.24-0.29mm genuine encroachments on HV zone pours.

**Mechanism (not investigated to a fix, per the task's scope and the hard
rule against weakening thresholds)**: the halo change is a pure clearance-halo
input to A*'s cost/obstacle map for the SEARCHING net's own path; it does not
touch DRC's own creepage geometry check, and cannot itself have gotten looser
anywhere (§3's monotonicity argument). The plausible mechanism is downstream
and emergent: several LV nets, denied their previous (illegal) path by the
restored halos elsewhere on the board, found different legal-per-A*-but-
creepage-marginal paths that happen to pass measurably closer to HV zone
pours/pads than their previous paths did. This is a real, reproducible
consequence of the fix's changed routing behaviour, not a measurement
artifact — confirmed reproducible across the isolated-venv-verified
determinism pair (§2a) and independent of the no-refill/refill choice (present,
though smaller, under both).

## 6. track_width: 120(orig,100pre-#1329-fix)/+71(held) -> 0/0 — the hypothesis is CONFIRMED

**Absent from both boards' violation lists, both refill and no-refill.**
`track_width` is not merely reduced from the reviewer's held +71 — it is
**zero on both baseline and after**, i.e. it never resurfaces even under
#1301's altered congestion. This fully confirms PR #1329's `_power_islands.py`
`STITCH_TRACE_WIDTH_MM` fix (deriving from `TEMPER_NET_CLASSES["Power"]
.trace_width` = 1.0mm instead of the old hardcoded 0.3mm) eliminated the
defect at its root, independent of whatever congestion #1301's wider per-pair
halos introduce. The reviewer's +71 charge against #1301 was entirely a
confound from a pre-existing, since-fixed, unrelated defect.

## 7. Full ledger

**No-refill** (baseline -> after, delta):

| category | baseline | after #1301 | delta |
|---|---|---|---|
| clearance | 232 | 198 | **-34** |
| track_width | 0 | 0 | **0 (was held +71)** |
| shorting_items | 130 | 109 | **-21 (was held +13)** |
| creepage | 106 | 108 | **+2 (was held +5)** |
| tracks_crossing | 13 | 14 | +1 (was held +4) |
| hole_clearance | 44 | 42 | -2 |
| copper_edge_clearance | 17 | 6 | -11 |
| solder_mask_bridge | 31 | 29 | -2 |
| drill_out_of_range | 6 | 6 | 0 |
| courtyards_overlap | 1 | 1 | 0 |
| (warn) copper_sliver | 1 | 0 | -1 |
| (warn) track_dangling | 8 | 7 | -1 |
| (warn) via_dangling | 107 | 106 | -1 |
| silk_overlap [capped 199 both] | 199 | 199 | unmeasured |
| **error total** | 580 | 513 | **-67** |
| **warning total** | 529 | 526 | -3 |
| **grand total** | 1109 | 1039 | **-70** |

**`--refill-zones`** (baseline -> after, delta):

| category | baseline | after #1301 | delta |
|---|---|---|---|
| clearance | 233 | 198 | **-35** |
| track_width | 0 | 0 | **0** |
| shorting_items | 130 | 109 | **-21** |
| creepage | 130 | 140 | **+10** |
| tracks_crossing | 13 | 14 | +1 |
| hole_clearance | 44 | 42 | -2 |
| copper_edge_clearance | 17 | 6 | -11 |
| solder_mask_bridge | 31 | 29 | -2 |
| (warn) track_dangling | 8 | 7 | -1 |
| (warn) via_dangling | 23 | 23 | 0 |
| **error total** | 605 | 545 | **-60** |
| **warning total** | 445 | 443 | -2 |
| **grand total** | 1050 | 988 | **-62** |

No category is cap-saturated on either board (clearance 198-233 vs. its 499
extended-cap; creepage/shorting_items 106-140/109-130 vs. their 199 cap;
`silk_overlap` alone sits at its 199 cap on both sides — unrelated to the PR,
pure silkscreen geometry, untouched by this diff).

## 8. Determinism: PASS

Two independent `route_board.py` runs of the identical after-#1301 code, from
this worktree's own properly isolated `.venv` (no `sys.path` hack): **byte-
identical** (`sha256 8b01f9c7dc5242da57fcaaa70e32da759cb7894e04dcbd6c8d0a53a98b5b0810`,
both runs). A third independent run via the (later-shown-fragile) shared-venv
sys.path-hack approach also matched this hash exactly, confirming that
methodology's *first* invocation was valid even though its *second* invocation
silently mis-resolved (§2a) — the router itself is deterministic; the flaw was
entirely in one measurement wrapper's import resolution, not in the router.

## 9. Decision

Per the task's stated rule: *"You may merge PR #1301 if the re-measured ledger
is net-positive, no HV<->LV boundary is involved, and the connectivity cost
remains fail-closed honesty rather than fabrication."*

- Ledger net-positive: **yes** (-70 no-refill, -62 refill).
- Connectivity fail-closed, not fabrication: **yes** (§3).
- No HV<->LV boundary involved: **no** — 2 new HV-LV creepage items no-refill,
  20 new HV-LV creepage items (net +9) under the honest `--refill-zones`
  measurement, on a board whose entire purpose is IEC 60335-1 mains isolation.

**Two of three conditions are met; the HV-LV condition is not. Per the task's
own rule, this is held, not merged.** `fix/per-pair-clearance-halos-nlayer-astar`
remains open. The rebased, fully-measured branch is preserved at
`pr1301-rebase-work` (backed up to `origin/pr1301-rebase-work`) for whoever
picks up the creepage root-cause next — no work here needs to be redone, only
extended: find and legally reroute the specific LV tracks/vias listed in §5
away from the HV zones/pads they now graze, without loosening any clearance,
creepage, or DRU threshold, then re-run this same measurement.
