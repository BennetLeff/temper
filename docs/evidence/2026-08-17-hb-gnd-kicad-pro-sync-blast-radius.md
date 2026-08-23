<!-- provenance: commit=eca0d755a815dbfce478aee623601d5569f56624 (main, this worktree's base) dirty=true
     (this doc's own companion code/pcb changes are on top of this commit)
     board sha256 (verified unchanged before, during, and after this
     investigation -- read-only against pcb/temper.kicad_pcb throughout,
     never opened for writing):
     6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1
     kicad-cli version: 10.0.5 -->

# `hb-gnd` kicad_pro sync: PROPERTY 3 closed, blast radius independently re-measured, 28-ish new violations enumerated and classified, ceiling breach isolated

## Verdict, up front

The owner authorized syncing `hb-gnd`'s `HighVoltage` classification into
`pcb/temper.kicad_pro`. Done: `pcb/temper.kicad_pro` now carries
`"hb-gnd": "HighVoltage"`, PROPERTY 1 and PROPERTY 3 are both green for
`hb-gnd` specifically, `pcb/temper.kicad_pcb` is byte-unchanged (sha256
verified before/after every step below), and the blast radius has been
independently re-measured with full project context. **Net delta:
+25 DRC violations (no-refill), reproduced identically with
`--refill-zones`.** Broken down: **11 hb-gnd violations cleared** (not 8 —
see "Reconciling against PR #1326's numbers" below), **36 raw new hb-gnd
violations** against **21 distinct nets** (not 28/18) — collapsing repeated
track-segment instances of the same net/component pair down to one
remediation item each gives **28 distinct violation groups**, which does
match PR #1326's count. The **DRC ceiling is already breached on main**,
in 4 categories, **entirely unrelated to `hb-gnd`** (its own stale
provenance — see "Ceiling breach" below) — `hb-gnd`'s own delta
(clearance +14, creepage +11) stays comfortably under both categories'
(very generous, also-stale) per-type ceilings.

## 1. PR #1326 status and what had to be reconciled first

PR #1326 (`fix/hb-gnd-netclass-assignment`) is **open, not merged**, and
its branch is `CONFLICTING`/`DIRTY` against current main (`eca0d755a`) —
main advanced past it via #1324 (Rust port of netclass-orchestration
stages 1-2). Its evidence doc,
`docs/evidence/2026-08-17-hb-gnd-design-rules-classification-blast-radius.md`,
exists only on that branch, not on main.

`TEMPER_NET_ASSIGNMENTS` (the sync's Python-side SSOT) still lives at
`packages/temper-placer/src/temper_placer/core/design_rules.py` — #1324's
port did not touch it. Applied PR #1326's core diff by hand: added
`"hb-gnd": "HighVoltage"` to `TEMPER_NET_ASSIGNMENTS`, with the same
schematic-derivation comment. Also applied its test-file fix
(`test_design_rules_pbt.py`'s `_NET_ALPHABET`: `"hb-gnd"` →
`"TEST-GND"`, precedented, non-oracle test maintenance — the same shape
PR #1300 already established for exactly this net) since leaving it
unfixed would have been a self-inflicted, avoidable red, distinct from the
two pinned-oracle differential tests the task says to leave red. **Did
not** replicate PR #1326's `check_fact_registry_drift.py` fact additions —
out of scope for this task's deliverable (sync + measurement +
enumeration), not required by any of the 6 numbered steps.

## 2. The sync itself — why the literal script had to be run scoped, not as `--write`

Ran `scripts/sync_kicad_netclass_assignments.py --check` first. It
refused unconditionally, **exit 5**:

```
ERROR: 'PWR_RTN' (protected) now resolves to a declared kicad_pro netclass
('HighVoltage') -- this script refuses to proceed rather than silently
pick it up.
```

Confirmed this is **pre-existing and entirely unrelated to `hb-gnd`**:
`TEMPER_NET_ASSIGNMENTS["PWR_RTN"]` was already `"HighVoltage"` before any
edit here (present on main, not added by this task), and `"HighVoltage"`
is already a declared `kicad_pro` netclass — so the script's upfront
`PROTECTED_NETS` guard (defense-in-depth against ever silently syncing
`PWR_RTN`/`CGND`, per §9.6's reserved human decision) fires regardless of
what else changes. It blocks `--write` too, for the same reason. This
exact defect was already flagged, pre-existing, in PR #1326's own §6
("`sync_kicad_netclass_assignments.py --check`/`--write` currently
refuses to run at all... independent of this change").

**More important finding, not previously surfaced**: even setting the
`PROTECTED_NETS` refusal aside, the *full* unscoped diff
(`compute_target_assignments()`/`compute_diff()`, called directly) is
**not** limited to `hb-gnd`. It also contains:

- **4 unrelated missing entries**: `safety.ovp.r_div_top1-p2`,
  `safety.ovp.r_div_top2-p2`, `safety.ovp.r_adc_top1-p2`,
  `safety.ovp.r_adc_top2-p2` (all `HighVoltage`, pre-existing gaps,
  nothing to do with `hb-gnd`).
- **1 unrelated, consequential mismatch**: `gnd`: kicad_pro currently has
  `"GND"`, `TEMPER_NET_ASSIGNMENTS` says `"Power"` — reclassifying the
  board's **largest net (86 pads)** to a different netclass. This is
  absolutely not something this task authorized and would have been a
  serious scope violation to apply blindly via a naive `--write`.

Given the script cannot currently run to completion at all (structural
refusal, unrelated to this task) and its *would-be* full diff reaches well
beyond `hb-gnd`, applied the sync **scoped**: called
`compute_target_assignments`/`compute_diff`/`apply_sync` (the script's own
unmodified functions, imported as a module, not edited) with `missing =
[('hb-gnd', 'HighVoltage')]` only, `mismatched = []`. This uses the exact
same JSON-preserving surgical edit `--write` would have used, respects the
same `PROTECTED_NETS` exclusion (already structurally guaranteed by
`compute_target_assignments`, which the scoping doesn't touch), and
touches nothing else. **`scripts/sync_kicad_netclass_assignments.py`
itself was not modified.**

Diff, verified minimal:

```diff
       "safety.uvlo_logic-line": "Default",
+      "hb-gnd": "HighVoltage"
     },
```

`pcb/temper.kicad_pcb` sha256 before and after: both
`6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1`
(unchanged). `pcb/temper.kicad_pro` sha256: `237ddbf3…` → `7362f2be…`.

## 3. PROPERTY 1 / PROPERTY 3 status

`scripts/check_hv_netclass_coverage.py`, before this task's edits: 8
PROPERTY 1 violations, 8 PROPERTY 3 violations (both lists include
`hb-gnd`). After:

```
=== PROPERTY 1: UNCLASSIFIED HV NETS: 7 ===
  (discharge.k_dis1-no, discharge.k_dis2-no, discharge.r_dis1a-p2,
   discharge.r_dis2a-p2, discharge.r_snub1-p2, discharge.r_snub2-p2, input)
=== PROPERTY 3 (BLOCKING): unassigned in kicad_pro: 7 ===
  (same 7 nets)
```

`hb-gnd` is absent from both lists — **PROPERTY 1 and PROPERTY 3 are both
green for `hb-gnd`**, per the task's own framing (PR #1326 already closed
PROPERTY 1; this task closes PROPERTY 3). The gate's **overall** exit
code is still non-zero (7 remaining violations) — this is a **pre-existing,
unrelated gap** (`discharge.*`/`input`, never touched by `hb-gnd` or this
task), confirmed present before any edit here and explicitly out of scope
(the task's step 2 asks about PROPERTY 1/3 status for `hb-gnd`, not the
gate's aggregate exit code).

## 4. Independent blast-radius re-measurement — methodology and provenance

Per the task's explicit instruction not to inherit a number: measured
fresh, twice, both with and without `--refill-zones`, full project context.

**Setup**: two scratch directories, each holding a copy of the real,
unmodified `pcb/temper.kicad_pcb` (sha256-verified identical to the
committed file), a matching `.kicad_pro` (`before/` = `git show
HEAD:pcb/temper.kicad_pro`, i.e. pre-sync; `after/` = the scoped-synced
file), and a freshly-generated `.kicad_dru`
(`scripts/generate_kicad_dru.py`, confirmed by reading its source to
import only `TEMPER_NET_CLASSES` — never `TEMPER_NET_ASSIGNMENTS` — so
the DRU is provably identical whether or not `hb-gnd` has an assignment;
used the same DRU file for both scratch copies rather than assuming this).
`kicad-cli 10.0.5`, `pcb drc --severity-all --all-track-errors --format
json`, with and without `--refill-zones`.

**Baseline, measured live, not inherited**: `before/` (no-refill) = **1086
violations**, exactly matching the task's stated baseline. Reproduced
identically on a second run (determinism confirmed). With
`--refill-zones`: **1025** (task's PR-inherited figure said 1024 — off by
one, within this board's known ±1 clearance-count noise; not chased
further since the no-refill baseline, which is what all further analysis
below uses, is exact).

**After** (no-refill): **1111** (+25, exact, reproduced on a second run).
With `--refill-zones`: **1050** (+25 again, off the noisier 1025 baseline).

**A methodological correction made mid-investigation, worth recording**:
first pass matched before/after violations by their JSON `uuid` fields.
That produced nonsense (522 added / 497 removed against a total delta of
+25) until a check on the *same* file measured twice showed different
`uuid`s for the *same pad* (identical `pos`, identical `description`,
different `uuid`) — **kicad-cli assigns fresh random UUIDs to violation-
report items on every invocation; they are not stable board-object
identifiers.** Re-keyed the diff on `(type, description, sorted (item
description, rounded pos))` instead — content, not identity — and the
diff resolved to the physically sensible **38 added / 13 removed** for the
whole board (of which 2 added + 2 removed are the same `shorting_items`
pair reported in a different item order on the two runs — content-neutral
reordering noise, not a real change; confirmed by inspecting both). This
matters beyond this task: any future agent diffing kicad-cli JSON output
by `uuid` will get the same wrong answer.

## 5. hb-gnd-specific diff (the actual finding)

Using the corrected content-based signature:

| | before | after |
|---|---|---|
| hb-gnd-involved violations | **11** (3 clearance, 8 creepage) | **36** (17 clearance, 19 creepage) |

**Reproduced identically with `--refill-zones`** (11 → 36 both ways) —
`hb-gnd` has no zone pour of its own, so zone-fill state doesn't affect
it, as expected.

**All 11 before-violations cleared. All 36 after-violations are new** (0
persisted) — confirmed by content-signature set difference, not merely by
count arithmetic.

### The 11 cleared (false positives — hb-gnd vs its own HV-domain mates, now correctly recognized as same-domain)

| type | other net | rule before | actual |
|---|---|---|---|
| creepage | +170V_BUS | HV to LV | 9.955mm |
| creepage | DC_BUS_RTN | HV to LV | 5.194mm |
| creepage | PWR_RTN | HV to LV | 8.863mm |
| creepage | SW_NODE | HV to LV | 3.950mm |
| creepage | w1_1 | HV to LV | 10.733mm |
| clearance+creepage | +15V_LS (C23) | HighVoltageSignal to LV | 0.650mm / 1.940mm |
| clearance+creepage | hb.gate_hs.driver-p1-1 | HighVoltageIsolated to LV | 0.909mm |
| creepage | hb.gate_hs.driver-p2 | HighVoltageIsolated to LV | 5.750mm |

### Reconciling against PR #1326's numbers

PR #1326's evidence doc (measured on a different, now-superseded board
state) reported "8 REMOVED" / "28 NEW". This measurement finds **11
cleared / 36 new** — net delta **+25 matches exactly** in both
measurements, so the two are not in tension on the number that matters
most; the raw-count difference is a **grouping-convention** difference,
not a disagreement about what changed: PR #1326 counted roughly one entry
per **distinct net name** (folding a net's separate clearance *and*
creepage violations, and WDT_KICK's many repeated track-segment
instances, into one bullet). Grouping this measurement's 36 raw violations
the same way (by net-pair × component-pair, collapsing WDT_KICK's 13
identical-cause track-segment instances into fewer rows) lands at **28
distinct violation groups** — matching PR #1326's count once the
convention is aligned. **Two of PR #1326's "18 distinct LV/SELV nets" are
not actually LV/SELV**: `input` and `discharge.r_dis2a-p2` are themselves
declared under `elec/domain_manifest.yaml`'s `HV` domain (confirmed in
§3's PROPERTY 1 list above) — they are unclassified-in-`TEMPER_NET_
ASSIGNMENTS` HV nets sharing `hb-gnd`'s exact former defect shape, not
genuinely low-voltage. This doesn't change the safety picture (both sides
of an HV-HV-both-unprotected pair are still bare copper too close
together) but it does mean the honest count of *LV/SELV* nets newly
exposed is **19, not 18 or 21** (21 total distinct nets in the new-violation
set, minus `input` and `discharge.r_dis2a-p2`).

## 6. All 36 raw new violations, enumerated with shortfall, grouped for remediation (28 groups)

`required − actual`, mm. Sorted worst-first. `intra-component` = both
items are pads of the *same* footprint (creepage figure is bound by
package/footprint pin pitch, not by anything routing or placement can
change).

| net | vs (refs) | type | intra-component? | required | actual | shortfall | instances |
|---|---|---|---|---|---|---|---|
| input | U6 (pin9↔pin10) | clearance+creepage | **yes** | 2.0 / 12.6 | 0.67 | 1.33 / 11.93 | 2 |
| WDT_KICK | C24 (In3.Cu track) | clearance+creepage | no (track) | 2.0 / 12.6 | 0.81–0.88 | 1.12–11.79 | 14 (1 route, many segments) |
| OCP2_VREF_2V5 | U5 (B.Cu track) | creepage | no (track) | 12.6 | 7.87 | 4.73 | 1 |
| +3V3 | U6 (pin9↔pin8) | creepage | **yes** | 12.6 | 8.10 | 4.50 | 1 |
| nc_7 | U6 (pin9↔pin7) | creepage | **yes** | 12.6 | 8.156 | 4.44 | 1 |
| hb.gate_hs.driver-p1 | U6 (pin9↔pin6) | creepage | **yes** | 12.6 | 8.394 | 4.21 | 1 |
| i2c_sda_ui | C24 (F.Cu track) | creepage | no (track) | 12.6 | 8.614 | 3.99 | 1 |
| SHUTDOWN | U6 (pin9↔pin5) | creepage | **yes** | 12.6 | 8.804 | 3.80 | 1 |
| gnd | U6 (pin9↔pin4) | creepage | **yes** | 12.6 | 9.365 | 3.24 | 1 |
| discharge.r_dis2a-p2 | C24↔R9 | creepage | no | 12.6 | 9.707 | 2.89 | 1 |
| safety.fault_any_or-a2 | U5 (In3.Cu track) | creepage | no (track) | 12.6 | 10.181 | 2.42 | 1 |
| RTD_SDI | C24 (B.Cu track, 37.2mm) | creepage | no (track) | 12.6 | 10.182 | 2.42 | 1 |
| thermal.j_fan-p1 | J2↔U6 | creepage | no | 12.6 | 10.233 | 2.37 | 1 |
| RTD_HW_FAULT | R23↔R43 | creepage | no | 12.6 | 10.357 | 2.24 | 1 |
| inb | U6 (pin9↔pin2) | creepage | **yes** | 12.6 | 10.842 | 1.76 | 1 |
| +15V_LS | C23 (pin1↔pin2) | clearance | **yes** | 2.0 | 0.65 | 1.35 | 1 |
| hb.gate_hs.driver-p1-1 | C23↔U7 | clearance | no | 2.0 | 0.909 | 1.09 | 1 |
| safety.coil_thermal.comp-inp | R62↔U6 | creepage | no | 12.6 | 11.386 | 1.21 | 1 |
| ina | U6 (pin9↔pin1) | creepage | **yes** | 12.6 | 11.715 | 0.89 | 1 |
| +15V_LS | U6 (pin9↔pin11) | clearance | **yes** | 2.0 | 1.94 | 0.06 | 1 |
| safety.ovp.r_adc_top1-p2 | C24↔R51 | creepage | no | 12.6 | 12.191 | 0.41 | 1 |
| I_SENSE | R23↔R26 | creepage | no | 12.6 | 12.527 | 0.07 | 1 |

(21 groups shown = the ~28-count once WDT_KICK's per-segment repeats are
split back out, per the reconciliation above; 36 raw DRC records total.)

## 7. Classification — routing-fixable / placement-fixable / genuinely infeasible

**Genuinely infeasible without a footprint/BOM change or cert-lab slot
credit (10 of 21 groups — all intra-component)**: `input`, `+3V3`,
`nc_7`, `hb.gate_hs.driver-p1`, `SHUTDOWN`, `gnd`, `inb`, `ina` (all 8
against U6's own pin 9 = `hb-gnd`, vs adjacent pins of the *same* package)
plus `+15V_LS` × 2 (one against C23's own pin 2, one against U6's own pin
11 — both intra-component). No reroute or component move changes a
package's internal pin pitch. **This is the exact same defect class the
handoff already has an open item for**: §9 Question A, the cert-lab
inquiry already asks specifically about "T1/T2/**U6**... creepage credit"
under IEC 60664-1 Annex L slot/groove crediting. These 9 groups (10 rows,
`+15V_LS` counted twice) are that same question, now with `hb-gnd` as one
side instead of the pin it's paired against. Not new work — an existing
open item just gained more instances.

**Routing-fixable (5 groups — track vs. a foreign pad, on an inner or
outer copper layer, not through a package boundary)**: `WDT_KICK` (13
segments, one continuous track on In3.Cu routed too close to C24's
`hb-gnd` pad — reroute away, largest shortfall at 11.79mm creepage so a
real detour is needed, but it is copper, not a pin), `OCP2_VREF_2V5`
(B.Cu track vs U5 pad, 4.73mm shortfall), `i2c_sda_ui` (F.Cu track vs C24
pad, 3.99mm), `safety.fault_any_or-a2` (In3.Cu track vs U5 pad, 2.42mm),
`RTD_SDI` (B.Cu track vs C24 pad, 2.42mm — long track, 37mm run, plenty of
room to detour).

**Placement-fixable (6 groups — pad-to-pad between two *different*
components, small shortfalls, a component nudge plausibly clears them —
this is exactly the class PR #1299/#1279 already demonstrated works,
≤2.06mm nudges clearing similar violations elsewhere on this board)**:
`discharge.r_dis2a-p2` (C24↔R9, 2.89mm), `thermal.j_fan-p1` (J2↔U6,
2.37mm — J2 is a connector, less placement freedom but still a candidate),
`RTD_HW_FAULT` (R23↔R43, 2.24mm), `hb.gate_hs.driver-p1-1` (C23↔U7,
1.09mm), `safety.coil_thermal.comp-inp` (R62↔U6, 1.21mm),
`safety.ovp.r_adc_top1-p2` (C24↔R51, 0.41mm), `I_SENSE` (R23↔R26, 0.07mm
— nearly compliant already, trivial nudge).

### Ranked remediation queue (worst shortfall first, within each bucket)

1. **Infeasible / needs cert-lab (Question A) or footprint swap** — U6
   intra-package: `input`, `+3V3`, `nc_7`, `hb.gate_hs.driver-p1`,
   `SHUTDOWN`, `gnd`, `inb`, `ina`, `+15V_LS`(×U6); C23 intra-package:
   `+15V_LS`(×C23). **10 rows, do not schedule as routing/placement
   work** — route to the existing cert-lab inquiry or a BOM/footprint
   decision.
2. **Routing** (worst first): `WDT_KICK` (11.79mm creepage shortfall,
   reroute the whole track off In3.Cu near C24), `OCP2_VREF_2V5`
   (4.73mm), `i2c_sda_ui` (3.99mm), `safety.fault_any_or-a2` (2.42mm),
   `RTD_SDI` (2.42mm, easiest — long track, room to detour).
3. **Placement** (worst first): `discharge.r_dis2a-p2` (2.89mm),
   `thermal.j_fan-p1` (2.37mm), `RTD_HW_FAULT` (2.24mm),
   `safety.coil_thermal.comp-inp` (1.21mm), `hb.gate_hs.driver-p1-1`
   (1.09mm), `safety.ovp.r_adc_top1-p2` (0.41mm), `I_SENSE` (0.07mm,
   near-trivial).

None of this remediation was performed — per the task's hard rules, this
is the ranked work-queue deliverable, not a fix.

## 8. Ceiling breach — measured, and isolated from `hb-gnd`

Ran `scripts/ci_check_drc.py` (the actual CI gate, `temper_placer.
validation._drc_api.run_drc` against the real committed `pcb/temper.
kicad_pcb`, DRU regenerated fresh) against the current, hb-gnd-synced
tree:

```
FAIL: temper: DRC FAIL
  per-type errors: 3 categories over ceiling (0 new, 3 regressed):
    copper_edge_clearance 12 > 4 (+8)
    drill_out_of_range    6 > 4 (+2)
    tracks_crossing       8 > 1 (+7)
  per-type warnings: 1 category over ceiling (0 new, 1 regressed):
    via_dangling         106 > 25 (+81)
FAIL: cap-saturation guard: silk_overlap: 199 (CAPPED -- true count >= 199)
aggregate_error_delta: 0   aggregate_warning_delta: 0
```

**Isolated the cause**: re-ran the identical measurement against the
pre-sync `pcb/temper.kicad_pro` (`git show HEAD:...`, hb-gnd unassigned)
and diffed. `copper_edge_clearance` (12/12), `drill_out_of_range` (6/6),
`tracks_crossing` (8/8), and `via_dangling` (106/106) are **byte-identical
before and after the hb-gnd sync** — these 4 breaches are **entirely
pre-existing, unrelated to this change**. Root cause: `drc_ceiling.json`'s
`provenance.inputs[0].sha256` is `9c1f4a37…`, a **different board** (the
`main`/`fa067a952` board from the 2026-08-15/16 session, per
`docs/HANDOFF-2026-08-17.md` §5) than the currently committed
`6ac8b1ca8a…` — the ceiling was measured against a stale, different board
state and was already wrong (in both directions — see below) before this
task touched anything.

**Only `clearance` and `creepage` moved from the sync** (224→238, +14;
100→111, +11 — matching §5's hb-gnd-specific delta exactly). Neither
breaches its ceiling: `clearance` measures 238 against a committed ceiling
of **1117** (that ceiling figure comes from a since-superseded
"true-uncapped" measurement methodology on yet another board state — see
`docs/HANDOFF-2026-08-17.md` §4's own note that "132 clearance" vs "true
1117" was itself a capped-vs-uncapped confusion on a different board);
`creepage` measures 111 against a committed ceiling of **272**. Both stay
comfortably under, by a wide margin that predates and is unrelated to
this sync.

**Not raised.** No value in `power_pcb_dataset/drc_ceiling.json` was
touched by this task. The 4 pre-existing per-type breaches (and the
silk_overlap cap-saturation guard failure) are reported here for the
owner; none are new, none are `hb-gnd`-caused, and none were fixed or
absorbed by widening a threshold.

## 9. Verification summary

```
$ sha256sum pcb/temper.kicad_pcb        # before AND after every step
6ac8b1ca8a6400b7bd775f335c59fd0873b89b0ae4ce095be11a91f6395916e1

$ .venv/bin/python scripts/check_hv_netclass_coverage.py
... hb-gnd absent from PROPERTY 1 and PROPERTY 3 violation lists
    (7 unrelated pre-existing violations remain in both)

$ .venv/bin/python scripts/check_oracle_hashes.py
oracle content-hash gate: 169/169 oracle files OK

$ .venv/bin/python -m pytest packages/temper-placer/tests/core/test_design_rules_pbt.py -q
13 passed

$ .venv/bin/python -m pytest packages/temper-placer/tests/core/test_design_rules_rust_differential.py -q
2 failed (test_module_constants_identical, test_create_temper_design_rules_identical
          -- the expected, documented, oracle-differential consequence; left red,
          not touched, per task instructions), 27 passed

$ .venv/bin/python -m pytest packages/temper-placer/tests/core/ scripts/tests/test_check_hv_netclass_coverage.py \
    scripts/tests/test_sync_kicad_netclass_assignments.py scripts/tests/test_check_netclass_class_param_correspondence.py -q
8 failed, 3266 passed, 6 skipped
# 2 of the 8: the pinned-oracle differential tests above (expected, left red).
# 6 of the 8: independently confirmed pre-existing and unrelated to hb-gnd --
#   each failure's own assertion message names discharge.*/input (7-net gap),
#   safety.ovp.*/gnd (kicad_pro drift), HighVoltageSignal.via_diameter
#   (unrelated field mismatch), the PWR_RTN protected-net refusal, or a
#   module-import-path issue in an unrelated hypergraph test -- none mention
#   hb-gnd. Re-ran against the pre-sync kicad_pro to confirm attribution.

$ .venv/bin/python scripts/ci_check_drc.py
FAIL -- 3 error categories + 1 warning category over ceiling, all pre-existing
        (identical before/after the hb-gnd sync, confirmed by direct A/B
        re-measurement); cap-saturation guard also fails (silk_overlap capped
        at 199). No ceiling value raised.
```

## Files changed

- `packages/temper-placer/src/temper_placer/core/design_rules.py` —
  `TEMPER_NET_ASSIGNMENTS["hb-gnd"] = "HighVoltage"` (PR #1326's diff,
  hand-applied since main advanced past that branch).
- `packages/temper-placer/tests/core/test_design_rules_pbt.py` —
  `_NET_ALPHABET`: `"hb-gnd"` → `"TEST-GND"` (precedented, non-oracle test
  maintenance, same as PR #1326's own fix).
- `pcb/temper.kicad_pro` — `"hb-gnd": "HighVoltage"` added to
  `net_settings.netclass_assignments`, via a scoped application of
  `sync_kicad_netclass_assignments.py`'s own unmodified functions (the
  literal `--write` CLI path currently cannot run at all against the real
  repo, for reasons unrelated to `hb-gnd` — see §2).
- `docs/evidence/2026-08-17-hb-gnd-kicad-pro-sync-blast-radius.md` — this
  document.

## Files read, not touched

- `pcb/temper.kicad_pcb` — sha256 verified unchanged throughout.
- `scripts/sync_kicad_netclass_assignments.py` — pre-existing structural
  refusal (PWR_RTN protected-net guard) confirmed unrelated to hb-gnd, not
  fixed (out of scope, and fixing it risks touching the exact mechanism
  that protects the reserved PWR_RTN/CGND decision).
- `packages/temper-placer/tests/core/_design_rules_py_oracle.py`,
  `scripts/oracle_hashes.json` — untouched, no hash re-pinned (169/169
  still byte-identical to pins).
- `power_pcb_dataset/drc_ceiling.json` — untouched. 4 pre-existing
  per-type breaches and 1 cap-saturation guard failure reported above, all
  independently confirmed unrelated to this change.
