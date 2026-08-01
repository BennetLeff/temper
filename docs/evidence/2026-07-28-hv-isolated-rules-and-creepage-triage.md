<!-- provenance: commit=0cf203afbc887420e1836dcbf456e3f43158d39c dirty=false (base) -->

> **Recovery note (added when this document was recovered from the
> stranded `feat/provable-safety-place-and-route` branch onto `main`):**
> the branch this document was written on had already pinned
> `HV_CREEPAGE_ENFORCED_MM` to the PD3 figure (12.6mm) via a separate
> `check_isolation_keepout.py` retarget (`1c1b6d32`) that is entangled with
> a since-reverted relay swap and was **not** recovered alongside this
> document. The recovered `scripts/generate_kicad_dru.py` on `main` pins
> `HV_CREEPAGE_ENFORCED_MM` to the PD2 figure (8.0mm) instead, to match
> `check_isolation_keepout.py` as it actually stands on `main` today. Every
> violation count, 999mm-probe number, and creepage figure cited below
> reflects the PD3-pinned branch this was written on, **not** the PD2-pinned
> state it was recovered into -- the qualitative findings (what
> `HighVoltageIsolated` is, the `+15V_LS`/U3 `a` misclassifications, the
> groove-width-bridging gap) still hold; the specific numbers do not
> transfer 1:1 and should not be quoted as current.

# Closing `HighVoltageIsolated`, triaging the 117 creepage violations, and
# validating KiCad's creepage solver against IEC 60664-1 cl. 4.2

Base commit: `0cf203af` (`merge: KiCad DOES have a real creepage constraint
-- and it is now enforced`, branch `docs/methodology-loop-discipline`).
Work done in worktree `agent-a7a53319d2420d7ee`, branch
`fix/hv-isolated-netclass-and-creepage-triage` created from that commit
(this worktree already existed and was reused rather than creating a new
one, per the task's disk constraint).

Reads first, per task instructions:
`docs/evidence/2026-07-28-drc-creepage-constraint.md`,
`docs/evidence/2026-07-28-drc-rule1-netclass-redo.md`,
`docs/evidence/2026-07-28-creepage-determination-brainstorm.md`,
`scripts/generate_kicad_dru.py`,
`packages/temper-placer/configs/netclass_rules.yaml`,
`elec/domain_manifest.yaml`.

Three independent tasks, one commit (`71dba365`) for Task A's code, this
doc for all three.

---

## Task A -- `HighVoltageIsolated` had no rules at all

**Confirmed the premise**: `grep -c HighVoltageIsolated scripts/generate_kicad_dru.py`
returned 0 before this change (verified directly, not assumed).

### A.1 What the class is, and who is in it

Traced across every source that mentions it:

- `pcb/temper.kicad_pro` (`net_settings.classes`): `HighVoltageIsolated`
  exists as a real, already-in-use KiCad netclass with its own baseline
  `clearance: 6.0`, `track_width: 2.0`. Five nets are assigned to it:
  `+5V_ISO`, `VBOOT_H`, `VBOOT_L`, `hb.gate_hs.driver-p1-1` (U7 pin 16,
  VDDA), `hb.gate_hs.driver-p2` (U7 pin 14, VSSA). The last two were
  added by `docs/evidence/2026-07-28-drc-rule1-netclass-redo.md` sec 5 --
  moved out of the unclassified `Default` bucket specifically to close a
  spurious "same domain" match RULE 1 was making for U7's own
  primary/secondary pin pairs.
- `elec/domain_manifest.yaml`: every one of those five nets is declared
  under `domains.HV.nets`, the SAME domain as `ac_l`, `+170V_BUS`,
  `SW_NODE`, `GATE_HS`, `GATE_LS`. The manifest's own comments trace why:
  VDDA/VSSA "float with the switch node, one gate-drive-current resistor
  downstream of GATE_HS/SW_NODE" (see the manifest's own lines documenting
  `hb.gate_hs.driver-p1-1`/`-p2`).
- `elec/src/constraints.ato`: declares a `HighVoltageIsolated` module
  (`clearance = 6.0mm`, `v_max = 20V`, `isolation_barrier = True`) and an
  `HV_to_ISO` inter-domain block (`min_clearance = 6.0mm`, `min_creepage =
  8.0mm`, `requires_slot = True`) -- this file's own model already
  anticipated a barrier-crossing requirement for this class, just never
  wired into the KiCad DRC generator.
- `docs/specs/NET_CLASS_SPECIFICATION.md` sec 3.5/5: describes it as
  "Floating power domains with reinforced isolation requirements," and its
  own inter-class matrix gives HV-Isolated-to-HV = 2.0mm (functional) but
  HV-Isolated-to-Default/Power/FinePitch = 6.0mm (reinforced) --
  **inconsistent with itself** on ACMains (6.0mm there, vs. this
  generator's own RULE 3 "AC Mains to HV" treating ACMains-HighVoltage as
  same-side/reduced at 3.0mm). Per `elec/domain_manifest.yaml`
  (authoritative for domain membership, not this spec doc), `ac_l`/`ac_n`
  are themselves HV-domain nets, so ACMains is same-side, not a third
  domain -- this doc's own ACMains-HVIso figure looks like another
  uncorrected legacy number in the same family the brainstorm doc's sec 1
  already catalogued elsewhere in this repo. Not fixed here (out of this
  task's file scope; flagged as UNVERIFIED below).
- `packages/temper-placer/configs/netclass_rules.yaml`: had **no**
  `HighVoltageIsolated` entry at all before this change (confirmed by
  reading the file directly) -- the placer's own feasibility model
  treated this netclass as `default_clearance_mm: 0.2` for any pair
  lacking a class_pairs entry, i.e. no protection whatsoever on that side
  either.

**Conclusion: "isolated" names the UCC21550 gate driver's own internal
galvanic primary/secondary barrier, not a barrier this netclass's own nets
sit on the far side of relative to the rest of HV.** They are floating,
low-voltage-differential (20V max) nets that live entirely on the HV side
of the real mains<->SELV barrier. That distinguishes exactly two
relationships, per the task's own framing:

1. **To its own HV/ACMains neighbours** (same side of the real barrier):
   only functional separation is needed -- the same category of relaxation
   RULE 3 ("AC Mains to HV") already applies for ACMains vs. HighVoltage.
2. **To every other (LV/SELV) netclass** (the real barrier): reinforced
   clearance AND creepage are needed, at the same figures RULE 2/RULE 4
   already enforce for ACMains/HighVoltage.

### A.2 What was added

`scripts/generate_kicad_dru.py` -- two new rules, inserted after RULE 4:

```
(rule "HighVoltageIsolated same side"
   (condition "A.NetClass == 'HighVoltageIsolated' && (B.NetClass == 'HighVoltage' || B.NetClass == 'ACMains')")
   (constraint clearance (min 2.0mm))
)

(rule "HighVoltageIsolated to LV"
   (condition "A.NetClass == 'HighVoltageIsolated' && B.NetClass != 'HighVoltageIsolated' && B.NetClass != 'HighVoltage' && B.NetClass != 'ACMains'")
   (constraint clearance (min 2.0mm))
   (constraint creepage (min 12.6mm))
)
```

Both reuse existing, already-derived constants
(`HV_INTERNAL_CLEARANCE_MM = 2.0`, `HV_CREEPAGE_ENFORCED_MM = 12.6`,
currently pinned to PD3) -- no new figure was invented, and the PD2/PD3
pin is **not** touched or re-decided here.

`packages/temper-placer/configs/netclass_rules.yaml` -- a matching
`HighVoltageIsolated` class entry (`clearance: 6.0`, `creepage_mm: 6.0`,
`voltage_v: 20.0`, mirroring the sibling `ACMains`/`HighVoltage` entries'
existing convention exactly) plus four `class_pairs` entries
(`HighVoltageIsolated-Signal/GND/Power/FinePitch`, all 6.0mm, matching the
existing `HighVoltage-*` pairs). Deliberately **no**
`HighVoltageIsolated-HighVoltage`/`-ACMains` pair was added, mirroring this
file's own pre-existing choice not to reduce `ACMains-HighVoltage` below
6.0mm either -- this file's placer-feasibility model stays conservative
for same-domain neighbours; the reduced, cited 2.0mm same-side figure is
applied only at the fab-authoritative KiCad DRC layer
(`generate_kicad_dru.py`).

### A.3 Verified to bind -- 999mm probe (real board, denominators)

Ran each new condition as a lone rule at `(min 999mm)` against a scratch
copy of `pcb/temper.kicad_pcb`/`pcb/temper.kicad_pro` (never the live
files):

| Condition | Real-board matches (999mm/500mm-clamped probe) |
|---|---:|
| `A.NetClass == 'HighVoltageIsolated' && (B.NetClass == 'HighVoltage' \|\| B.NetClass == 'ACMains')` | **137** |
| `A.NetClass == 'HighVoltageIsolated' && B.NetClass != 'HighVoltageIsolated' && B.NetClass != 'HighVoltage' && B.NetClass != 'ACMains'` | **496** (near the ~500 truncation floor documented in the redo doc sec 2a -- a lower bound, not exact) |

Also re-ran the task's own four reference-point probes against this
session's kicad-cli 10.0.4, on a `netclass_assignments`-emptied copy (the
redo doc's own methodology for isolating a condition's true match count):
`A.Reference == B.Reference` -> **211** (task's figure: 214-215, same
run-to-run band), `A.NetClass == B.NetClass` -> **500** (task's figure:
499, at the same truncation cap), `A.Footprint == B.Footprint` -> **0**,
`A.Attribute == 'SMD'` -> **0**. Environment behaves as documented.

**One methodology note found while doing this**: combining all four probe
rules in a single `.kicad_dru` file caused kicad-cli to report zero
matches for every one of them (all clearance violations fell back to the
bare netclass baseline) -- each rule had to be run as the *sole* rule in
its own file to get a clean per-condition count. Not chased further (not
this task's own new rules, which were each verified singly and match the
combined real-file run in sec A.4 below); flagged in UNVERIFIED.

### A.4 Real-board impact -- counts with denominators

Raw kicad-cli, full generated `.dru`, before vs. after this diff (scratch
copies of `pcb/temper.kicad_pcb`/`.kicad_pro`, `--all-track-errors
--format json --severity-all`, matching the project's own ratchet
harness's invocation):

| Generator | Total violations | `creepage` |
|---|---:|---:|
| `0cf203af` (no `HighVoltageIsolated` rules) | 1955 | **117** (101 "HV to LV" + 16 "AC Mains to LV" -- exact match to sec B.1) |
| This diff | 2025 | **188** (100 "HV to LV" + 72 "HighVoltageIsolated to LV" [new] + 16 "AC Mains to LV") |

Delta: **+70 total, +71 creepage** (188-117; the 1-fewer "HV to LV" count
after this diff, 101->100, traces to `C4`/`C5` self-pairs on `PWR_RTN`
reporting slightly different `actual` values -- or, for `C5`, not
appearing at all -- between the two separate kicad-cli invocations,
diffed pair-by-pair to confirm this is not attributable to this diff's
own rule conditions, which do not touch RULE 4's condition at all. This
is the same class of run-to-run DRC measurement variance
`power_pcb_dataset/drc_ceiling.json`'s own `nondeterministic_error_types`
note already documents for `clearance`, now also observed for `creepage`
at this small a magnitude -- not chased further; flagged in UNVERIFIED).
Of the 188 post-diff creepage violations, 72 are the new
**"HighVoltageIsolated to LV"** rule -- rule attribution taken directly
from each violation's own description string, not inferred.

`--severity-all` alone (no `--all-track-errors`, matches the project's
`_drc_api.run_drc` wrapper minus the determinism flag) gave a second,
independent measurement: before 1702 total (`creepage`=116, `clearance`=361,
`shorting_items`=176), after 1741 total (`creepage`=187 [+71],
`clearance`=335 [**-26**], `shorting_items`=170 [**-6**]). Net delta: +39,
reconciling exactly (71-26-6=39).

**The `clearance`/`shorting_items` decreases are deliberate, not a
weakening** -- same category of effect
`docs/evidence/2026-07-28-drc-rule1-netclass-redo.md` sec 4b already
documented and defended for its own net decrease. "HighVoltageIsolated
same side" matches 137 real pad pairs (sec A.3) but produces **zero**
violations at its own 2.0mm floor -- every real HighVoltageIsolated-vs-
HighVoltage/ACMains pad pair on this board already clears 2.0mm, so the
rule's only live effect today is removing the false-positive 6.0mm
per-netclass-baseline clearance requirement those legitimate same-domain
pairs used to trip (this is exactly what shows up as the `clearance`/
`shorting_items` decrease). **No safety-relevant figure was lowered
anywhere**; the new floor (2.0mm) is still enforced and verified to bind
(sec A.5, `test_same_side_rule_still_enforces_its_own_floor`).

Ratchet harness (`scripts/ci_check_drc.py --backend kicad-cli`), same
before/after generator swap, `pcb/temper.kicad_dru` regenerated between
runs then removed afterward (untracked build artifact, never committed;
`pcb/temper.kicad_pcb` never touched):

| Generator | Aggregate errors | vs. ceiling (1017) | `creepage` | `track_width` |
|---|---:|---:|---:|---:|
| `0cf203af` | 1193 | **+176 over** (matches the task's own cited figure exactly) | 116 (NEW) | 39 (NEW) |
| This diff | 1264 | **+247 over** | 188 (NEW) | 39 (unchanged) |

Net attributable to this diff via the harness: +71 aggregate errors.
`creepage` itself rose 116 -> 188 (+72, matching sec A.4's raw
`--all-track-errors` count exactly); the aggregate delta (+71) is 1 lower
than the pure creepage delta (+72) because the ratchet's "errors" tally
excludes a small number of `warning`-severity items that raw `--severity-
all` includes -- a 1-count methodology difference, not a discrepancy in
the creepage finding itself. `power_pcb_dataset/drc_ceiling.json` was
**not touched**; the ratchet gate fails harder than before, reported, not
silenced.

### A.5 Tests -- 7 new, all passing; full suite 28/28

`scripts/tests/test_generate_kicad_dru.py`:

- `TestHighVoltageIsolatedRulesEmitted` (3 static tests): the netclass is
  no longer absent from the generated text; "same side" carries clearance
  only, no creepage; "to LV" carries both, at the right figures.
- `TestHighVoltageIsolatedDrcFalsifier` (4 real kicad-cli tests): "to LV"
  flags a 7.0mm HighVoltageIsolated<->Default gap on creepage (baseline
  clearance set artificially low to isolate the effect) and passes a
  17.6mm control gap; "same side" relaxes a 3.0mm
  HighVoltageIsolated<->HighVoltage gap below the real board's 6.0mm
  per-netclass baseline (proven via an explicit baseline-only control run
  that fails first) and still enforces its own 2.0mm floor at a 1.0mm gap.

`uv run --no-sync python -m pytest scripts/tests/test_generate_kicad_dru.py -q`
-- **28 passed** (21 pre-existing + 7 new). `ruff check` -- all checks
passed.

---

## Task B -- triage of the creepage violations

### B.1 The original 117 (pre-Task-A), reproduced exactly

Regenerated `0cf203af`'s own `generate_kicad_dru.py` (no
`HighVoltageIsolated` rules) against a scratch copy of the real board,
`kicad-cli pcb drc --all-track-errors --format json --severity-all`:

**117 creepage violations -- 101 "HV to LV", 16 "AC Mains to LV" -- an
exact match to the task's own cited figures.** Denominator: 117 total,
100% attributed by rule name from each violation's own description
string.

**Split: 56 placement-derived (pad<->pad, both items are `Pad`/`PTH pad`
-- durable under any routing), 61 routing-derived (at least one item is a
`Track`/`Via`/`Segment` -- a routing artifact, could shrink or vanish
under different routing).** Item-kind pairing, all 117:

| Item-kind pair | Count |
|---|---:|
| `Pad`+`Pad` | (part of 56) |
| `PTH pad`+`PTH pad` | (part of 56) |
| `PTH pad`+`Pad` | (part of 56) |
| `Track`+`PTH pad` | (part of 61) |
| `Track`+`Pad` | (part of 61) |

#### B.1.a Placement-derived, ranked (33 unique component pairs, worst first)

| Actual (mm) | Required | Component pair | # instances | Rule(s) | Nets involved |
|---:|---:|---|---:|---|---|
| **0.0000** | 12.6 | **U7 <-> U7** | 4 | HV to LV | `+15V_LS`-`DC_BUS_RTN`, `DC_BUS_RTN`-`GATE_HS`, `DC_BUS_RTN`-`hb.gate_hs.driver-p2`, `DC_BUS_RTN`-`input` |
| 0.7000 | 12.6 | R24<->R24 | 1 | HV to LV | `SW_NODE`-`hb.power_loop.q_high-g` |
| 1.0111 | 12.6 | R24<->R6 | 2 | AC Mains to LV, HV to LV | `SW_NODE`-`power_in.r_zcd_top1-p2`, `ac_l`-`hb.power_loop.q_high-g` |
| 1.8000 | 12.6 | R56<->R56 | 1 | HV to LV | `+170V_BUS`-`safety.ovp.r_adc_top1-p2` |
| 1.8000 | 12.6 | R6<->R6 | 1 | AC Mains to LV | `ac_l`-`power_in.r_zcd_top1-p2` |
| 2.4000 | 12.6 | D5<->D5 | 1 | HV to LV | `SW_NODE`-`hb.gate_hs.driver-p2` |
| 2.5750 | 12.6 | R4<->R4 | 1 | HV to LV | `+170V_BUS`-`PWR_RTN` |
| 3.2000 | 12.6 | C1<->C1 | 1 | AC Mains to LV | `ac_n`-`w1_1` |
| 3.4500 | 12.6 | U5<->U5 | 2 | HV to LV | `+170V_BUS`/`SW_NODE`-`hb.power_loop.q_high-g` |
| 3.9500 | 12.6 | U6<->U6 | 2 | HV to LV | `DC_BUS_RTN`/`SW_NODE`-`GATE_LS` |
| 3.9800 | 12.6 | U1<->U1 | 1 | HV to LV | `+170V_BUS`-`power_in.ntc-no` |
| 3.9800 | 12.6 | U2<->U2 | 1 | HV to LV | `DC_BUS_RTN`-`power_in.ntc-no` |
| 4.6175 | 12.6 | R18<->U6 | 4 | HV to LV | `DC_BUS_RTN`/`SW_NODE`-`discharge.q_dis_drv-g`/`gnd` |
| 4.7000 | 12.6 | R5<->R5 | 1 | HV to LV | `DC_BUS_RTN`-`PWR_RTN` |
| 5.0246 | 12.6 | K3<->K3 | 2 | HV to LV | `DC_BUS_RTN`-`discharge.k_dis1-coil2`/`k_dis2-coil1` |
| 6.4840 | 12.6 | R14<->R5 | 1 | HV to LV | `DC_BUS_RTN`-`discharge.k_dis2-nc` |
| 7.0000 | 12.6 | C4<->C4 | 1 | HV to LV | `+170V_BUS`-`PWR_RTN` |
| 7.1312 | 12.6 | RT1<->RV1 | 1 | AC Mains to LV | `ac_n`-`power_in.ntc-no` |
| 8.0000 | 12.6 | C2/C3/C5 self-pairs | 3 | HV to LV | `+170V_BUS`/`DC_BUS_RTN`-`PWR_RTN` |
| 8.0252 | 12.6 | **C23<->U27 (the MCU)** | 7 | HV to LV | `DC_BUS_RTN`-`RTD_DRDY`/`RTD_SCK`/`gpio18`/`io46`/`safety-line`/`usb_dn`/`usb_dp` |
| 8.4396-11.0361 | 12.6 | 9 more pairs | 1-2 each | HV/AC to LV | (K3/R12, R42/R5, C1/R7, C1/U5, R40/R5, R67/U7, C23/U17, R12/R4, C17/R1, R34/R5) |
| 12.3308 | 12.6 | C21<->U1 | 1 | HV to LV | `+170V_BUS`-`gnd` |
| 12.4050 | 12.6 | C29<->D5 | 1 | HV to LV | `+3V3`-`SW_NODE` |

Full per-pair data (all 33 rows, every instance) saved in this session's
scratchpad (`creepage_rows.json`/`before_creepage_rows.json`) -- not
committed (not one of this task's files), reproducible from the method in
sec B.4.

**Note on `C23<->U27`**: this is the task's own named caveat ("a 1.27mm
figure attributed to U27, which is the MCU"). KiCad's real DRC engine
measures this pair at **8.0252mm** edge-to-edge, not 1.27mm -- the prior
figure was a different (likely centre-to-centre or unrelated) measurement
of the same pair; this session's number comes directly from the DRC
engine's own `actual` field, not a hand computation.

#### B.1.b Routing-derived, net-pair summary (61 violations -- individual track
segments are many; the underlying barrier crossing is the durable unit)

Worst 15 by actual distance (full list of ~55 distinct net-pairs in the
scratchpad JSON):

| Actual (mm) | Net pair | Instances |
|---:|---|---:|
| 0.0000 | `DC_BUS_RTN`-`SHUTDOWN` | 1 |
| 0.0376 | `ac_n`-`hb.gate_hs.driver-p2` | 1 |
| 0.0750 | `+170V_BUS`-`RTD_SDI` | 1 |
| 0.2460 | `+170V_BUS`-`power_in.bypass_relay-coil2` | 1 |
| 0.3150 | `DC_BUS_RTN`-`discharge.r_snub1-p2` | 1 |
| 0.5566 | `+170V_BUS`-`power_in.ntc-no` | 1 |
| 0.5743 | `DC_BUS_RTN`-`RELAY_CTRL` | 1 |
| 0.6450 | `RELAY_CTRL`-`SW_NODE` | 1 |
| 0.7250 | `ac_l`-`inb` | 1 |
| 0.9400 | `DC_BUS_RTN`-`rtd_pan.rail_monitor-outa` | 1 |
| 0.9889 | `SW_NODE`-`i2c_scl_ui` | 1 |
| 1.0650 | `DC_BUS_RTN`-`RTD_SDI` | 1 |
| 1.3968 | `DC_BUS_RTN`-`discharge.k_dis1-coil2` | 1 |
| 1.4140/1.4266 | `+170V_BUS`-`WDT_RESET_N`/`WDT_KICK` | 1 each |
| 1.7083 | `+170V_BUS`-`hb.gate_hs.driver-p2` | 1 |

These are all track-to-pad or track-to-track gaps -- a reroute (or a
groove, per Task C's finding below, for the ones whose binding path is the
PCB surface rather than a component package) can change every one of
these without a BOM or footprint change.

### B.2 Task A's own new violations (72, from "HighVoltageIsolated to LV")

Same methodology, same board, generator with this task's Task A change:
72 creepage violations from the new rule. **Split: 28 placement-derived
(9 unique component pairs), 44 routing-derived.**

Placement-derived, ranked:

| Actual (mm) | Component pair | # instances | Nets |
|---:|---|---:|---|
| **0.0000** | **U7<->U7** | **9** | `+15V_LS`-`hb.gate_hs.driver-p2`, `GATE_HS`-`hb.gate_hs.driver-p1-1`/`-p2`, `hb.gate_hs.driver-p1-1`-`ina`/`inb`/`input`, `hb.gate_hs.driver-p2`-`ina`/`inb`/`input` |
| 0.6510 | C17<->R30 | 3 | (tank/bootstrap nets) |
| 0.9050 | C17<->R32 | 2 | `+3V3`/`I_SENSE`-`hb.gate_hs.driver-p2` |
| 1.5000 | U8<->U8 | 1 | `+15V_LS`-`hb.gate_hs.driver-p1-1` |
| 2.3875 | C22<->L2 | 2 | `sw`-`hb.gate_hs.driver-p1-1`/`-p2` |
| 2.9090 | C22<->U15 | 6 | `RTD_HW_FAULT`/`gnd`/`vcc`/`y`-`hb.gate_hs.driver-p1-1`/`-p2` |
| 4.8650 | C17<->R73 | 1 | `hb.gate_hs.driver-p2`-`safety.uvlo_logic.mon-outa` |
| 10.2410 | C22<->Q2 | 2 | `discharge.q_dis_drv-g`-`hb.gate_hs.driver-p1-1`/`-p2` |
| 11.0044 | C17<->R1 | 2 | `+15V`/`power_in.bypass_relay-coil1`-`hb.gate_hs.driver-p2` |

Routing-derived: 44 violations, all involving `hb.gate_hs.driver-p1-1`/
`-p2` on one side (the only two `HighVoltageIsolated`-classed nets with
routed copper today; `+5V_ISO`/`VBOOT_H`/`VBOOT_L` appear to have none
yet). Worst 5: `+3V3`-`hb.gate_hs.driver-p1-1` (0.0000mm),
`hb.gate_hs.driver-p1-1`-`safety.ovp.r_div_top1-p2` (0.0000mm),
`hb.gate_hs.driver-p2`-`tank-out` (0.0376mm),
`hb.gate_hs.driver-p2`-`safety.uvlo_logic.mon-outa` (0.0397mm),
`hb.gate_hs.driver-p1-1`-`rtd_pan.rail_monitor-outa` (0.0550mm).

### B.3 Two findings that change how these counts should be read

**Finding 1 -- `+15V_LS` net-classification false positive (pre-existing,
inherited by both RULE 4 and this task's new rule).** `+15V_LS` is
classified into the `Power` netclass (`TEMPER_NET_ASSIGNMENTS`), which
both RULE 4 and "HighVoltageIsolated to LV" treat as "LV". But
`elec/domain_manifest.yaml` declares `+15V_LS` an **HV-domain** net ("low-
side gate-driver rail; referenced to `DC_BUS_RTN`, not `gnd`... floats
within the HV domain, not SELV"). The `U7<->U7`/`0.0000mm` cluster's
`+15V_LS`-vs-`DC_BUS_RTN`/`hb.gate_hs.driver-p2` entries are therefore
**same-domain pairs misclassified as cross-domain** -- a real violation of
the *rule's own condition logic* (the same "netclass is necessary but not
sufficient for domain" gap the redo doc's own sec 5/UNVERIFIED already
named), not evidence of a real barrier breach. This is not something this
task introduced; it is inherited from the pre-existing `TEMPER_NET_
ASSIGNMENTS` table (`design_rules.py`, not in this task's file scope) and
now shows up identically under the new rule.

**Finding 2 -- U3 (H11L1 opto) has a genuine barrier crossing with ZERO
creepage protection, a coverage gap in the opposite direction.**
`elec/domain_manifest.yaml` declares U3's primary-side net `a` (LED anode,
HV side) and its secondary side (`ZCD_ISO`, `gnd`, `+3V3`) as a real,
declared isolator crossing. But `a` is **not** in `TEMPER_NET_ASSIGNMENTS`
at all -- it falls to the unclassified `Default` netclass, so neither
RULE 4 nor "HighVoltageIsolated to LV" (both keyed on `A.NetClass ==
'HighVoltage'`/`'HighVoltageIsolated'`) ever match a pad on this net.
**Confirmed by direct search: zero creepage-type violations, in either the
before or after report, mention `U3` anywhere.** U3's own primary/
secondary pad gap (6.02mm edge-to-edge, per
`docs/evidence/2026-07-28-creepage-determination-brainstorm.md` sec 6) is
below even the PD2 8.0mm figure, let alone 12.6mm -- **a real hazard this
whole rule family is currently blind to**, because a net-classification
gap, not a rule-syntax defect, hides it. Reported, not fixed (fixing this
needs a `design_rules.py`/`TEMPER_NET_ASSIGNMENTS` change, outside this
task's declared file scope of `generate_kicad_dru.py`/its test file/
`netclass_rules.yaml`/this doc).

Both findings point the same direction the redo doc already flagged in its
own UNVERIFIED section (sec 7): "whether other same-footprint pairs beyond
U7 hide a similar cross-domain-via-shared-classification miscategorization"
-- yes, at least two more, one false-positive (`+15V_LS`) and one
false-negative (`a`/U3). A full net-by-net classification audit against
`elec/domain_manifest.yaml` is the natural follow-up and is explicitly out
of this task's scope.

### B.4 Method (reproducible)

`temper_placer.validation._drc_api._parse_drc_json`'s own
`_extract_ref_from_item_description`/`_extract_net_from_item_description`
regexes were reused to parse each violation's `items[].description`
strings (`"Pad 2 [net] of REF on LAYER"`, `"Track [net] on LAYER, length
N"`, etc.) into `(kind, ref, net)` tuples. `placement_derived = True` iff
both items' kind is `Pad`/`PTH pad`. Full script and raw JSON in this
session's scratchpad (not committed).

### B.5 Truncation caveat (per task instructions)

`docs/evidence/2026-07-28-drc-rule1-netclass-redo.md` sec 2a's ~500-total-
`clearance`-violation truncation cap was re-confirmed this session
(sec A.3's `NetClassEq` probe hit exactly 500). **The creepage counts in
this section (117, 72, 188) are all comfortably below that floor and were
not observed to be truncated in any run this session** -- they are exact
counts, not lower bounds, by the same reasoning the redo doc already
established (truncation can only reduce a true count, never fabricate a
nonzero one, and none of these runs showed signs of hitting the cap for
the `creepage` type specifically).

---

## Task C -- does KiCad's creepage solver implement IEC 60664-1 cl. 4.2's
## groove-width minimum?

**Verdict: NO. KiCad's `CREEPAGE_GRAPH` credits a detour around a groove
of ANY width, including one far narrower than any real groove-width
standard would recognize. This is a fail-open on KiCad's part -- it
over-estimates creepage whenever a "fix" is a groove/slot too narrow to
legitimately count. `check_isolation_keepout.py` (or an equivalent
groove-width-aware check) must remain an independent, authoritative
cross-check on this specific point; KiCad's native `creepage` constraint
cannot be retired in its favour.**

### C.1 Fixture

Built three variants of a single-footprint, two-pad fixture (`HV_SIDE`/
`LV_SIDE`, netclasses `HighVoltage`/`Default`, 5.0mm straight-line
edge-to-edge gap -- same base geometry
`docs/evidence/2026-07-28-drc-creepage-constraint.md` sec 2a already
established), each with a rectangular Edge.Cuts slot polygon cut directly
between the pads (40mm long -- well past the pads' own 2mm extent, so any
surface path must detour around one end), varying only the slot's WIDTH:

- `noslot`: no slot at all (control).
- `hairline`: slot width **0.05mm** (an order of magnitude below either
  reference threshold -- 1.0mm at PD2, 1.5mm at PD3 -- and well below any
  manufacturable groove).
- `narrow`: slot width **0.3mm** (below both thresholds, but a width a fab
  could plausibly cut).
- `wide`: slot width **3.0mm** (above both thresholds -- a legitimate
  groove by any reading).

A single lone rule, `(condition "A.NetClass == 'HighVoltage' && B.NetClass
!= 'HighVoltage'") (constraint creepage (min 999mm))`, run against each
via `kicad-cli pcb drc --format json --severity-all`.

### C.2 Result

| Fixture | Slot width | Reported "actual" creepage |
|---|---:|---:|
| `noslot` | -- | **5.0000 mm** |
| `hairline` | 0.05mm | **38.3710 mm** |
| `narrow` | 0.3mm | **38.5896 mm** |
| `wide` | 3.0mm | **41.0526 mm** |

**A slot 30x narrower than the PD2 minimum groove width (0.05mm vs.
1.0mm), and 20x narrower than a manufacturable slot most fabs could even
cut reliably, gets credited with essentially the SAME large detour
distance (38.37mm) as a slot well above the PD3 threshold (41.05mm,
3.0mm-wide) -- both roughly 8x the straight-line 5.0mm gap.** If KiCad
implemented cl. 4.2's groove-bridging rule, the `hairline`/`narrow` cases
should have reported something close to the `noslot` baseline (5.0mm) --
the standard's own rule is that a groove narrower than X is *bridged*
(ignored) for creepage-measurement purposes, i.e. the surface path should
be measured as if the slot were not there. Instead, KiCad's `CREEPAGE_
GRAPH` appears to treat **any** closed Edge.Cuts polygon between two pads
purely as a geometric obstacle to route a shortest-path graph around,
with no width-dependent bridging logic at all -- consistent with the
constraint doc's own characterization, "it knows geometry, not
standards."

### C.3 Consequence for `check_isolation_keepout.py`

This confirms the task's stated risk directly: a board that "fixes" a
creepage shortfall with an unmanufacturably-narrow slot (whether by design
error or by an automated tool naively trying to satisfy KiCad's `creepage`
constraint) would **pass** KiCad's own DRC even though the real,
standards-governed creepage path is shorter (the groove should have been
bridged). **`check_isolation_keepout.py`'s straight-line corridor check
does not have this failure mode** -- it measures a zero-copper corridor
width directly and cannot be fooled by a narrow slot claiming a long
detour, because it never credits any detour at all (it is a stricter,
sufficient-but-not-necessary condition, per that script's own docstring
and `docs/evidence/2026-07-28-creepage-determination-brainstorm.md` sec 7).
**Answer to the task's stated question: `check_isolation_keepout` cannot
be retired in favour of KiCad's native rule -- it must remain the
independent cross-check specifically for groove/slot legitimacy**, even
though Task A/B's work above establishes KiCad's `creepage` constraint as
a real, additional, useful, and more geometry-aware check for the
*non-groove* case (flat, ungrooved gaps, where the two checks agree, per
the constraint doc's own K1/8.000mm corroboration).

Not independently re-verified: whether a groove that is *legitimately*
wide (>=X) but very close to the threshold shows any different treatment,
or whether kicad-cli's behavior changes with a groove that only partially
blocks the pads' extent (rather than fully, as tested here). Both are
UNVERIFIED, flagged below.

---

## Verification

- `make netlist` -- **PASSED** (rebuilt `elec/build/default.net`, full
  assertions-report green, this session).
- `uv run --no-sync python -m pytest elec/validation
  scripts/tests/test_generate_kicad_dru.py -q` -- **58 passed** (30 in
  `elec/validation` + 28 in `test_generate_kicad_dru.py`, 21 pre-existing +
  7 new).
- `uv run --no-sync ruff check scripts/generate_kicad_dru.py
  scripts/tests/test_generate_kicad_dru.py` -- all checks passed.
- 999mm probe reference points, this session's kicad-cli 10.0.4, real
  board: `A.Reference == B.Reference` -> 211 (task: 214-215),
  `A.NetClass == B.NetClass` -> 500 (task: 499, truncation-consistent),
  `A.Footprint == B.Footprint` -> 0, `A.Attribute == 'SMD'` -> 0. This
  task's own two new conditions: "same side" -> 137, "to LV" -> 496.
- Ten required gates, this session:

| Gate | Result |
|---|---|
| `check_domain_partition` | PASSED (exit 0) -- 0 domain crossings, 0 isolator-barrier breaches, 0 protective-impedance chain defects (54 declared nets, 2 domains, 10 isolators, over 164 compiled nets/168 components) |
| `capacity_budget_gate` | PASSED (exit 0) -- 0 defects |
| `mpn_fabrication_gate` | PASSED (exit 0) -- 0 new violations |
| `check_derived_doc_drift` | PASSED (exit 0) -- 3 docs, 47 tables, 136 fields checked |
| `check_rust_drc_presence` | PASSED (exit 0) -- `temper_drc_rs` symbols present and fresh |
| `check_undeclared_imports` | PASSED (exit 0) -- 3236 imports checked |
| `check_net_classification` | PASSED (exit 0) |
| `check_pll_range_consistency` | PASSED (exit 0) -- 4/4 checks agree |
| `check_copper_net_consistency` | PASSED (exit 0) -- 0 violations across 2482 copper items, 510 pads |
| `check_stale_extensions` | exit 3, 10 crates flagged "stale" -- confirmed the documented checkout-mtime false positive (none of the 10 crates' `.rs` files are touched by this diff) |

- Expected failures, confirmed:

| Gate | Result |
|---|---|
| `check_isolation_keepout` | exit 3 -- barrier keepout zone `MAINS_SELV_ISOLATION_BARRIER` still not placed; unrelated to this diff, `MIN_BARRIER_WIDTH_MM` unchanged at 12.6mm |
| `check_measurement_provenance` | exit 5 -- `power_pcb_dataset/drc_ceiling.json`'s `source: "measured-live-5-samples"` still not an allowed enum value; pre-existing, not touched |

- `power_pcb_dataset/drc_ceiling.json` -- **not touched**. Ceiling gate
  fails harder (ratchet harness: +176 over before this diff, matching the
  task's own cited figure exactly; +247 over after) -- reported, not
  silenced, no `Ceiling-Approval:` trailer added or needed.
- `pcb/temper.kicad_pcb`, `elec/src/`, `check_isolation_keepout.py` --
  **not touched**. All real-board measurement used scratch copies or a
  temporary, untracked `pcb/temper.kicad_dru` (generated, measured,
  deleted -- confirmed `git status` clean and `git ls-files
  pcb/temper.kicad_dru` empty both before and after).

## Compliance with the task's hard rules

- **Never tuned a figure to reduce a violation count.** Every new rule
  either adds real protection (creepage where none existed) or applies
  the same category of same-side reduction (`RULE 3`) this codebase
  already established and defended, verified to still enforce its own
  floor (sec A.5). Violation counts rose (+72 creepage, raw; +71,
  ratchet), as expected for a mains appliance closing a real gap.
- `power_pcb_dataset/drc_ceiling.json` -- not touched; breaches reported
  above.
- No `git stash` used anywhere this session.
- No `run_in_background`, no `Monitor`; every `kicad-cli`/`pytest`/gate
  invocation ran in the foreground.
- Committed after the code+test+config change (`71dba365`); this evidence
  doc is a second, final commit.
- Disk: no new worktree created (reused this agent's already-assigned
  worktree, rebased its branch onto `0cf203af`); `UV_PROJECT_ENVIRONMENT`
  pointed at the main checkout's already-synced `.venv`. No large
  downloads.
- `uv run --no-sync` used throughout.
- Files touched: `scripts/generate_kicad_dru.py`,
  `scripts/tests/test_generate_kicad_dru.py`,
  `packages/temper-placer/configs/netclass_rules.yaml`, this evidence doc.
  Did not touch `pcb/temper.kicad_pcb`, `elec/src/`,
  `scripts/check_isolation_keepout.py`, or
  `power_pcb_dataset/drc_ceiling.json`.
- Not pushed.

## UNVERIFIED

- **The `+15V_LS` and `a`/U3 net-classification findings (sec B.3) are
  not fixed here** -- both point to `design_rules.py`'s
  `TEMPER_NET_ASSIGNMENTS`, which is not in this task's declared file
  scope. Flagged as a concrete, scoped follow-up: `+15V_LS` needs
  reclassifying out of `Power` (or the rule conditions need a domain-aware
  exclusion), and U3's `a` net (and its LED cathode net) need a
  `HighVoltage`/`ACMains` classification to make the existing rule family
  see this isolator's real barrier at all. Whether other nets share either
  failure mode was not systematically audited (same scope limit the redo
  doc's own sec 5/7 already flagged).
- **`docs/specs/NET_CLASS_SPECIFICATION.md`'s own inter-class matrix
  (sec 5) is internally inconsistent** with this task's domain-membership
  finding for ACMains (treats `HighVoltageIsolated`-`ACMains` as 6.0mm/
  reinforced, while `HighVoltageIsolated`-`HighVoltage` is 2.0mm/
  functional, even though `elec/domain_manifest.yaml` puts ACMains nets in
  the same HV domain). Not corrected here (that file is not in this
  task's scope); flagged rather than silently perpetuated.
- **Why combining all four of the task's reference-point probe rules in
  one `.kicad_dru` file produced zero matches for every rule** (sec A.3),
  when each rule run alone reproduces the documented figures cleanly --
  not root-caused. Does not affect any conclusion in this document (this
  task's own two new rules were verified singly, matching the combined
  real-generated-file falsifier tests in sec A.5, and the reference-point
  probes were re-run singly to get clean numbers).
- **Task C's groove-width finding was tested at one slot length (40mm)
  and one pad gap (5.0mm), with the slot always fully blocking the
  straight-line path** -- not tested at a partially-blocking slot, a
  slot right at the boundary widths (1.0mm/1.5mm exactly), or a curved/
  non-rectangular groove shape. The qualitative finding (no width-
  dependent bridging at all, from 0.05mm to 3.0mm) is unlikely to be
  contradicted by those variations but they were not run.
- **Whether kicad-cli 10.0.5 (a CI-container version difference already
  flagged as unverified by the sibling creepage-constraint doc) behaves
  identically for the groove-width question** -- not independently
  re-checked here (no Docker pull, per disk constraints); relies on the
  same source-tag-diff precedent prior sessions used elsewhere in this
  project, not re-diffed here for `drc_test_provider_creepage.cpp`'s
  `CREEPAGE_GRAPH`/`CollectBoardEdges` implementation specifically.
- **`creepage`-type violations may share the small run-to-run measurement
  variance already documented for `clearance`** (sec A.4's `C4`/`C5`
  1-count difference between two separate kicad-cli invocations of the
  identical rule against the identical board). Only this one instance was
  found (via an explicit before/after pair-by-pair diff, not by assumption)
  and it is small (1 pair out of 117/188); not systematically
  characterized across repeated runs the way `clearance`'s variance was in
  `power_pcb_dataset/drc_ceiling.json`'s own march notes.
- Per sec B.5, all creepage counts in this document are read as exact
  (below the ~500 truncation floor); other violation types incidentally
  reported alongside them (e.g. `clearance`, close to that floor in some
  runs) should still be read as lower bounds per the redo doc's own
  caveat, not re-verified here since this task's own conclusions never
  depend on those other types' exact counts.
