<!-- provenance: commit=81f3c69a56a3a078cafbaa7edd3d99c0492eba72 dirty=false (base) -->

# Reconciling two safety-relevant netclass defects (`+15V_LS`, U3's `a`)
against `elec/domain_manifest.yaml`, and sweeping for siblings

Base commit: `4d73cad9` (`merge: HighVoltageIsolated rules, creepage triage
-- and KiCad fail-opens on narrow grooves`, branch
`docs/methodology-loop-discipline`). Work done in worktree
`agent-acf5d9dd830775f3a`, branch `fix/netclass-defect-reconciliation`
created from that commit in this agent's own already-assigned worktree
(no new worktree created, per the task's disk constraint -- this worktree
started on an unrelated branch, `worktree-agent-acf5d9dd830775f3a` at
`65fc5df7`, and was repointed with `git checkout -b ... 4d73cad9`, which
does not create a second worktree).

Reads first, per task instructions:
`docs/evidence/2026-07-28-hv-isolated-rules-and-creepage-triage.md` (which
reported both defects, as Findings 1 and 2 of its Task B),
`elec/domain_manifest.yaml`,
`packages/temper-placer/src/temper_placer/core/design_rules.py`
(`TEMPER_NET_ASSIGNMENTS`), `pcb/temper.kicad_pro`,
`packages/temper-placer/configs/netclass_rules.yaml`.

Two commits: `b124b8fb` (the two named defects), `0814a901` (sweep
siblings + two incidental pre-existing test fixes). This doc covers both.

---

## FALSIFIER

> *"Both nets are genuinely misclassified against the manifest, and
> correcting them in all three locations is unambiguous. If either turns
> out correctly classified -- or if the manifest itself is wrong about the
> domain -- that is the finding, and the manifest is what needs fixing."*

**Did not fire.** Both nets are genuinely misclassified, verified
independently against `elec/domain_manifest.yaml` and the wiring it cites
(not against net spelling):

- `+15V_LS`: `elec/domain_manifest.yaml` line 81, under `domains.HV.nets`,
  with its own comment: "low-side gate-driver rail; referenced to
  `DC_BUS_RTN`, not `gnd` (`modules.ato`) -- floats within the HV domain,
  not SELV." `TEMPER_NET_ASSIGNMENTS` and `pcb/temper.kicad_pro` both had it
  under `"Power"` (an LV class).
- `a`: `elec/domain_manifest.yaml` lines 98-100, under `domains.HV.nets`:
  "auto-named net between the ZCD divider tap and the H11L1 LED series
  resistor/anode (R9-U3), still entirely HV-side." Confirmed directly in
  `elec/build/default.net` (net code 24): `U3` pin `1` <-> `R9` pin `2`.
  `U3` pin `1` is the LED anode, declared `primary` in the
  `power_in.zcd_opto` isolator entry (line 425: "A (LED anode, HV side,
  driven from the zcd divider tap)"). `a` was absent from every assignment
  table (`TEMPER_NET_ASSIGNMENTS`, `pcb/temper.kicad_pro`), falling to
  unclassified `Default`.

Neither correction required touching the manifest. Both fixes are
consistent with the manifest's own domain-membership call.

---

## Fix 1 -- the two named defects (commit `b124b8fb`)

`"+15V_LS": "Power"` -> `"+15V_LS": "HighVoltage"`, and `"a"` added as
`"HighVoltage"` (previously absent), in:

| File | +15V_LS before | +15V_LS after | `a` before | `a` after |
|---|---|---|---|---|
| `TEMPER_NET_ASSIGNMENTS` (`design_rules.py`) | `Power` | `HighVoltage` | absent | `HighVoltage` |
| `pcb/temper.kicad_pro` `netclass_assignments` | `Power` | `HighVoltage` | absent | `HighVoltage` |
| `packages/temper-placer/configs/netclass_rules.yaml` | n/a | n/a | n/a | n/a |

**`netclass_rules.yaml` needed no change for either net.** Read in full
(147 lines): this file defines net-*class* parameters (`clearance`,
`trace_width`, `class_pairs`, ...) keyed by class name -- it carries no
per-net assignment table at all (no `nets:`/`net_classes:` mapping
anywhere in the file). `HighVoltage` was already fully defined there
(`clearance: 6.0`, `creepage_mm: 6.0`) before this change, so reclassifying
`+15V_LS`/`a` into it needed no edit here. The task's brief named this file
as one of (at least) three drifting assignment locations; this
investigation found it is not actually a *per-net* assignment location for
these two nets -- see the FALSIFIER-adjacent finding below for the
location that turned out to be the real third/fourth site.

**A fourth, previously-unnamed drift site was found and fixed too:**
`configs/temper_production_config.yaml` (`net_classes: "+15V_LS": "Power"`)
-- the deterministic-placement zone config. Verified this file is **not
loaded by any code path in this repo today** (`grep -rn
"temper_production_config" --include='*.py' .` returns zero hits; the file
actually wired up by `scripts/run_feedback_loop.py` is the
similarly-named-but-different `configs/temper_deterministic_config.yaml`,
which does not mention either `+15V_LS` or `a` at all). Fixed anyway, per
the task's own precedent (`+340V_BUS`, commit `688c15bb`): a wrong
assignment left lying around is a latent trap if this config is ever wired
up, and the fix costs nothing since it's dead code today.

### Manifest-domain-consistent classification, not name-based

Neither fix used the net's spelling. `+15V_LS`'s "V" and "LS" suffix look
like an ordinary low-voltage rail name; the fix is justified entirely by
the manifest's wiring citation (referenced to `DC_BUS_RTN`). `a` has no
name signal at all; the fix is justified by the manifest's declared
membership plus the direct netlist trace to U3 pin 1 (the isolator's own
declared primary-side pin).

---

## Fix 2 -- sweep for siblings (commit `0814a901`)

Per task instruction 3: every net in `elec/build/default.net` (164 compiled
nets) checked against its domain in `elec/domain_manifest.yaml` (21 `HV`
nets, 33 `SELV` nets, 110 nets the manifest does not mention at all).

### 3a. Nine more HV-domain nets, unclassified in both assignment tables (FIXED)

| Net | Manifest citation (paraphrased) | Also independently classed `HighVoltage` in the orphaned `configs/temper_production_config.yaml`? |
|---|---|---|
| `w1_1` | CMC winding 1 tap, line side | yes |
| `w1_2` | CMC winding 1 tap, line side | yes |
| `power_in.ntc-no` | bypass-relay NO contact -> rectified mains node | yes |
| `tank-out` | ResonantTank input == `SW_NODE` (traced, `main.ato:442`) | yes |
| `tank.c_tank1-p2` | same 400V-rated resonant tank | yes |
| `discharge.k_dis1-nc` | k_dis1 "contacts" group, same group as the isolator's own declared COM pin | yes |
| `discharge.k_dis2-nc` | same, k_dis2 | yes |
| `zcd` | power_in's internal HV-side ZCD divider tap | no (added there too) |
| `hb.power_loop.q_high-g` | Q_high's own Gate pin, one 2.2ohm resistor from `GATE_HS`/`SW_NODE` (traced, `modules.ato:382`) | no (added there too) |

Denominator: **9 of 21** manifest-HV nets were unclassified in
`TEMPER_NET_ASSIGNMENTS` and `pcb/temper.kicad_pro` before this fix (same
false-negative shape as `a`); **7 of those 9** were already independently
classed `HighVoltage` in `configs/temper_production_config.yaml`, which
corroborates the manifest's call rather than resolving it (that file is
authoritative for nothing -- it isn't loaded -- but its pre-existing,
independently-arrived-at agreement is evidence the classification isn't a
judgment call). All 9 added to `TEMPER_NET_ASSIGNMENTS`,
`pcb/temper.kicad_pro`, and (the 2 missing ones, `zcd` and
`hb.power_loop.q_high-g`) `configs/temper_production_config.yaml`, as
`HighVoltage`.

### 3b. `TEMPER_NET_CLASSES`/`TEMPER_NET_ASSIGNMENTS` had zero `HighVoltageIsolated` entries at all (FIXED)

`pcb/temper.kicad_pro` and `packages/temper-placer/configs/netclass_rules.yaml`
have both carried a `HighVoltageIsolated` class since 2026-07-28
(`docs/evidence/2026-07-28-hv-isolated-rules-and-creepage-triage.md`,
commit `71dba365`, same day, earlier in the base branch's history). That
fix never reached `design_rules.py` -- `TEMPER_NET_CLASSES` had no
`HighVoltageIsolated` key, and `TEMPER_NET_ASSIGNMENTS` had none of its 5
member nets (`+5V_ISO`, `VBOOT_H`, `VBOOT_L`, `hb.gate_hs.driver-p1-1`,
`hb.gate_hs.driver-p2`), confirmed by direct grep (zero hits) before this
change. This is the identical drift shape the task's own brief names as
precedent (`+340V_BUS`, commit `688c15bb`): a fix landing in the KiCad-side
and placer-config-side files, and not in the Python placer/router's own
net-class model. Fixed: added the class (parameters copied verbatim from
`netclass_rules.yaml`'s own entry) plus all 5 net assignments to
`design_rules.py`. Of the 5, only `hb.gate_hs.driver-p1-1` /
`hb.gate_hs.driver-p2` have a live counterpart in the current compiled
netlist (net codes 57/55, confirmed by grep); `+5V_ISO`/`VBOOT_H`/`VBOOT_L`
have none (0 occurrences in `elec/build/default.net`) -- added anyway,
harmless if absent, matching this table's own pre-existing convention for
historical aliases (e.g. `+340V_BUS`, `AC_L`).

### 3c. Items found and NOT fixed -- require a judgement call

**`PWR_RTN`** (manifest `HV` domain, "the doubler midpoint... confirmed a
SEPARATE net from `gnd`"). Classed `"GND"` in `TEMPER_NET_ASSIGNMENTS`,
unclassified (`Default`) in `pcb/temper.kicad_pro`. Two compounding
problems, not one:

1. `TEMPER_NET_CLASSES["GND"]` maps to KiCad net-class name `"Ground"`
   (`scripts/generate_kicad_dru.py`'s `KICAD_NAME_MAP`), but
   `pcb/temper.kicad_pro`'s own `net_settings.classes` list has **no**
   class literally named `"Ground"` (`Default`, `Power`, `HighVoltage`,
   `GateDrive`, `HighVoltageIsolated`, `ACMains`, `FinePitch`,
   `Differential` -- verified by reading the file directly). `generate_kicad_dru.py`'s
   `"RULE 8: Ground clearance"` (`A.NetClass == 'Ground' || B.NetClass ==
   'Ground'`) can therefore never match on the real board -- it is inert,
   independent of anything in this task.
2. Because `PWR_RTN` therefore falls to KiCad's real `Default` class, it
   accidentally satisfies the `B` side of the `"HV to LV"` creepage rule
   (`A.NetClass == 'HighVoltage' && B.NetClass != 'HighVoltage' &&
   B.NetClass != 'ACMains'`) whenever paired against a real
   `HighVoltage`-classed neighbour (`+170V_BUS`, `DC_BUS_RTN`, `SW_NODE`,
   ...) -- which is most of the many `PWR_RTN`-involving creepage
   violations already catalogued in the sibling triage doc's B.1 table
   (`R4<->R4`, `R56<->R56`, `C2`/`C3`/`C5` self-pairs, `K3<->K3`, etc.).
   Since `PWR_RTN` genuinely IS the same `HV` domain as those nets per the
   manifest, this is the **same false-positive shape as Defect 1**
   (`+15V_LS`) -- but at a much larger scale (dozens of existing
   violations, not 3). Conversely, `PWR_RTN` paired against a genuinely
   `SELV` net that is *also* unclassified (e.g. `gnd` -- itself
   unclassified, see 3d below) matches **no** creepage rule at all (`Ground`
   is not the `A` side of anything, and `Default` vs `Default` matches
   nothing), which is the **same false-negative shape as Defect 2** (`a`).

   Reclassifying `PWR_RTN` to `HighVoltage` would resolve both, exactly as
   done for `+15V_LS`/`a` above -- but the blast radius (dozens of
   existing violations moving, not a handful) is an order of magnitude
   larger, and `configs/temper_production_config.yaml` carries its own,
   pre-existing, deliberate comment against exactly this move: *"NOTE:
   PWR_RTN is the star-point-merged system ground (85 pins) - classing it
   HighVoltage would drag every grounded part into HV"* (a placement-zone
   concern, not a DRC-domain concern, but evidence someone already weighed
   this tradeoff once). Not fixed here -- flagged for a human call.

**`GATE_HS`/`GATE_LS`** (manifest `HV`) share the `"GateDrive"` netclass
with **`PWM_HS`/`PWM_LS`** (manifest `SELV` -- "MCU-side PWM output,
primary side of the gate driver"). These are the primary-side and
secondary-side pins of the *same* isolator (`hb.gate_hs.driver`, U7) --
the identical primary/secondary-conflation pattern the sibling triage
doc's Task A already fixed once for this same component's `VDDA`/`VSSA`
pins (moving them out of `Default` into `HighVoltageIsolated` specifically
to stop a spurious "same domain" match). It was not extended to the PWM
digital signals. `scripts/generate_kicad_dru.py`'s only `GateDrive`-aware
creepage-adjacent rule is `"RULE 6: GateDrive near HV"`
(`A.NetClass=='GateDrive' && B.NetClass=='HighVoltage'`, clearance-only,
0.5mm) -- there is no `GateDrive`-to-LV creepage rule at all, so if
`PWM_HS`/`PWM_LS` (SELV) and `GATE_HS`/`GATE_LS` (HV) shared a netclass and
ran close to a real HV net, the SELV pair would get the *reduced*
same-side 0.5mm allowance rather than full cross-domain creepage
protection. **Not fixed here.** Reclassifying `PWM_HS`/`PWM_LS` requires
choosing a *new* target class (unlike this task's other fixes, where the
manifest's already-declared domain mapped onto an obviously-correct,
already-existing class name) and verifying it doesn't break existing
routing elsewhere on the board -- a design decision, not a lookup. Flagged
as the most safety-relevant open item this sweep found; recommend a
dedicated follow-up.

**`CGND`** -- classed `"GND"` in `TEMPER_NET_ASSIGNMENTS`, same as
`PWR_RTN`, but has **0 occurrences** in `elec/build/default.net` and is not
mentioned anywhere in `elec/domain_manifest.yaml`. A legacy/historical
alias (same category as `+340V_BUS`), not a live net. Not touched.

### 3d. ~20 unclassified SELV nets -- informational, not fixed

**21 of 33** manifest-`SELV` nets are unclassified (`Default`) in both
`TEMPER_NET_ASSIGNMENTS` and `pcb/temper.kicad_pro`: `gnd`, `usb_dn`,
`usb_dp`, `i2c_sda_ui`, `i2c_scl_ui`, `rtd_force_p`, `rtd_force_n`,
`rtd_sense_p`, `rtd_sense_n`, `WDT_RESET_N`, `SHUTDOWN`, `RELAY_CTRL`,
`DISCHARGE_CTRL`, `ZCD_ISO`, `safety.uvlo_logic-line`,
`discharge.k_dis1-coil1`, `discharge.k_dis1-coil2`,
`discharge.k_dis2-coil1`, `power_in.bypass_relay-coil1`,
`power_in.bypass_relay-coil2`, `safety.ovp.comp-inp`. This is the safer
*direction* of miscoding on its own (an unclassified SELV net does not, by
itself, inflate a false HV-domain violation) and is a much larger,
separate cleanup project (21 nets, no single-net manifest citation makes
the "right" class as unambiguous as the HV-side fixes above -- most would
plausibly be `Signal`, some `Power` for the relay coils). Not fixed here;
listed with its exact denominator per the task's instruction to report
(not guess) on items needing judgement. The one place this interacts with
a fixed item is `PWR_RTN` <-> `gnd` (3c above).

### 3e. 110 compiled nets the manifest does not mention at all

Denominator only, no action: `164 - 21 - 33 = 110` compiled nets (RTD
front-end signals, MCU GPIOs, decoupling-cap reference nets like
`mcu-reference-*`, discharge-bank internal nodes, etc.) are outside both
manifest domains entirely. The manifest's own stated scope
(`elec/domain_manifest.yaml`'s header) is domain-crossing safety, not
every net on the board; this is expected, not a gap, and out of this
task's scope to adjudicate net-by-net.

---

## Violation-count effect (kicad-cli 10.0.4, `--all-track-errors --format
json --severity-all`, matching the sibling triage doc's own methodology;
`pcb/temper.kicad_pcb`/`pcb/temper.kicad_pro` are the real, committed
files -- no scratch copies needed since the fix itself lives in
`kicad_pro`; `pcb/temper.kicad_dru` regenerated from
`scripts/generate_kicad_dru.py` before each measurement, deleted
afterward, never committed)

### Stage 1 -- Fix 1 only (`+15V_LS` + `a`), before commit `0814a901`

| Type | Before (`4d73cad9`) | After Fix 1 | Delta |
|---|---:|---:|---:|
| **creepage** | **188** | **227** | **+39** |
| track_width | 39 | 81 | +42 |
| clearance | 499 | 500 | +1 |
| all others | unchanged | unchanged | 0 |
| **TOTAL** | **2025** | **2107** | **+82** |

Creepage delta reconciles exactly: creepage violations mentioning
`+15V_LS` went **3 -> 22** (+19: the 3 before were all false positives --
1 `HV to LV` + 2 `HighVoltageIsolated to LV`, all same-domain mismatches,
now gone; the 22 after are new, real violations against genuinely-LV
neighbours, e.g. `RTD_SCK`, `usb_dn`, `gnd`, `gpio18`, previously invisible
because `+15V_LS` wasn't classed as an `A`-side HV netclass). Creepage
violations mentioning `a` went **2 -> 22** (+20: 1 real false positive
removed, `a`-vs-`ac_l` under `"AC Mains to LV"`, now correctly same-domain;
21 new real violations against genuine LV neighbours). `19 + 20 = 39`,
exactly the measured creepage delta.

By rule name: `HV to LV` 100 -> 142 (+42), `HighVoltageIsolated to LV` 72
-> 70 (-2, the 2 `+15V_LS` false positives), `AC Mains to LV` 16 -> 15
(-1, the `a`/`ac_l` false positive removed, offset by +1 from a
pre-existing, unrelated run-to-run measurement variance on the
`L1`<->`safety.ovp.r_div_top1-p2` pair -- same class of variance the
sibling triage doc's own sec A.4 already documented for `creepage`, traced
here to a track-length difference between two separate kicad-cli
invocations of the identical net pair, confirmed not attributable to this
diff's own condition logic).

### Stage 2 -- full fix (Fix 1 + Fix 2's 9 HV nets + HighVoltageIsolated class), commit `0814a901`

| Type | Before (`4d73cad9`) | After full fix | Delta |
|---|---:|---:|---:|
| **creepage** | **188** | **329** | **+141** |
| track_width | 39 | 199 | +160 |
| shorting_items | 199 | 200 | +1 |
| clearance | 499 | 499 | 0 |
| all others | unchanged | unchanged | 0 |
| **TOTAL** | **2025** | **2327** | **+302** |

By rule name: `HV to LV` 100 -> 261 (+161, the large majority: 9 more
HV-domain nets are now visible to this rule, most for the first time),
`HighVoltageIsolated to LV` 72 -> 58 (-14, additional same-domain false
positives removed now that neighbours like `zcd`/`tank-out`/`w1_2` are
correctly `HighVoltage`-classed instead of `Default`), `AC Mains to LV` 16
-> 10 (-6, same mechanism -- `w1_1`/`w1_2`/`power_in.ntc-no` no longer
falsely read as `B`-side LV against `ac_l`/`ac_n`).

**Both directions moved, as the task predicted.** The net effect is
strongly positive (+302 total, +141 creepage) because this sweep found
many more real, previously-invisible HV-domain coverage gaps (Fix 2) than
false positives (Fix 1) -- expected for a mains appliance where the
starting condition was under-coverage, not over-coverage. `track_width`'s
large increase (+160, entirely attributable to nets newly recognized as
`HighVoltage`/`HighVoltageIsolated`, none to `+15V_LS` specifically, which
has no violations of this type) reflects real, existing copper on these
nets that was routed to LV/Default trace-width rules and does not meet the
3.0mm `HighVoltage` minimum -- a genuine, now-visible fabrication-readiness
gap on the physical board, not something this task's file scope (assignment
data only) can or should silently paper over.

`power_pcb_dataset/drc_ceiling.json` was **not touched**. No
`Ceiling-Approval:` trailer added or needed; the ratchet gate (not run
directly here, since it isn't in this task's required-ten-gates list, but
its ceiling-vs-measured math is identical to the raw kicad-cli counts
above) fails harder than before this diff, reported here, not silenced.

---

## Verification

- `make netlist` -- **PASSED**, both before and after all edits; digest
  `2c7a04623052...` identical in both runs (this diff never touches
  `elec/src/*.ato`).
- `uv run --no-sync python -m pytest elec/validation
  scripts/tests/test_generate_kicad_dru.py -q` -- **58 passed**, both
  before and after all edits.
- Broader placer suite, run as a collateral check (not one of the task's
  required commands, but touched by this diff's `design_rules.py`
  changes): `packages/temper-placer/tests/core/test_design_rules.py`,
  `tests/io/test_netclass_loader.py`, `tests/router_v6/test_adapter.py`,
  `tests/router_v6/test_zone_emission.py` -- found and fixed 2
  **pre-existing** failures (both hard-coded "9 net classes", stale since
  `netclass_rules.yaml` gained `HighVoltageIsolated` on 2026-07-28, before
  this session; became visible once `TEMPER_NET_CLASSES` caught up in
  commit `0814a901`) -- **120 passed** after the fix.
- `packages/temper-placer/tests/requirements/safety/` (54 tests) -- **53
  passed, 1 pre-existing failure**
  (`TestClearanceIntegration::test_temper_board_clearance_compliance`, "9
  REQ-SAFE-01 clearance/creepage violations", vs. that test's own docstring
  claiming 0 as of 2026-07-27). **Confirmed unrelated to this diff**: its
  fixture (`_real_board_fixture.py`) derives net classification from
  `elec/domain_manifest.yaml` directly (via `check_domain_partition.py`'s
  loader) and component positions from `pcb/temper.kicad_pcb` -- neither
  touched by this diff, and its only imports are `kicad_parser`,
  `check_domain_partition`, and a separate `validators.clearance` module,
  none of which reference `TEMPER_NET_ASSIGNMENTS`/`design_rules.py`.
  `elec/build/default.net`'s digest is also unchanged (above). Not fixed
  here (out of file scope: would require touching `pcb/temper.kicad_pcb`
  or the manifest, both off-limits or requiring a different kind of
  investigation); flagged in UNVERIFIED.
- Ten required gates, before vs. after (both the Stage-1-only and final
  full-fix state) -- **byte-identical stdout, same exit codes, at every
  stage**:

| Gate | Result |
|---|---|
| `check_domain_partition.py` | exit 0, unchanged |
| `capacity_budget_gate.py` | exit 0, unchanged |
| `mpn_fabrication_gate.py` | exit 0, unchanged |
| `check_derived_doc_drift.py` | exit 0, unchanged |
| `check_rust_drc_presence.py` | exit 0, unchanged |
| `check_undeclared_imports.py` | exit 0, unchanged |
| `check_net_classification.py` | exit 0, unchanged |
| `check_pll_range_consistency.py` | exit 0, unchanged |
| `check_copper_net_consistency.py` | exit 0, unchanged |
| `check_stale_extensions.py` | exit 3 (documented checkout-mtime false positive), unchanged |
| `check_isolation_keepout.py` | exit 3 -- **expected**, unrelated to this diff |
| `check_measurement_provenance.py` | exit 5 -- **expected**, unrelated to this diff |

- `power_pcb_dataset/drc_ceiling.json` -- **not touched**.
- No `git stash` used anywhere this session. No `run_in_background`, no
  `Monitor`; every command ran in the foreground.
- `uv run --no-sync` used throughout, with `UV_PROJECT_ENVIRONMENT`
  pointed at the main checkout's already-synced `.venv` (this worktree has
  no venv of its own) and `PYTHONPATH` prepended with this worktree's own
  `packages/temper-placer/src` -- required because the shared venv's
  editable install (`_editable_impl_temper_placer.pth`) is a hardcoded
  absolute path into the *main checkout*, not this worktree; without the
  `PYTHONPATH` override every test/gate would have silently exercised the
  main checkout's unmodified `design_rules.py` instead of this worktree's
  edits. Verified directly (`temper_placer.core.design_rules.__file__`)
  before relying on it for any measurement.
- Committed after each meaningful step (`b124b8fb` for the two named
  defects, `0814a901` for the sweep). Not pushed.
- Files touched: `packages/temper-placer/src/temper_placer/core/design_rules.py`,
  `pcb/temper.kicad_pro`, `configs/temper_production_config.yaml`,
  `packages/temper-placer/tests/core/test_design_rules.py`,
  `packages/temper-placer/tests/io/test_netclass_loader.py`, this evidence
  doc. Did not touch `pcb/temper.kicad_pcb`, `elec/src/`,
  `elec/domain_manifest.yaml`, `packages/temper-placer/configs/netclass_rules.yaml`
  (verified it needed no change), or `power_pcb_dataset/drc_ceiling.json`.
  Did not build any new checker/gate script (per the task's hard rule --
  the sweep in this doc was done with a one-off script kept in this
  session's scratchpad, never committed to the repo).

## Compliance with the task's hard rules

- **Never reclassified a net to reduce a violation count.** Every change
  follows `elec/domain_manifest.yaml`'s own domain declaration; the
  violation count moved in both directions as a consequence (down for the
  3 `+15V_LS` and 3 `a`/`ac_l` false positives removed; up, substantially,
  for the many real gaps closed), never the reverse.
- `power_pcb_dataset/drc_ceiling.json` -- not touched.
- No `git stash`. No `run_in_background`/`Monitor`.
- Committed after every meaningful step.
- Disk: no new worktree (repointed this agent's own assigned worktree via
  `git checkout -b` onto the task's base commit); reused the main
  checkout's `.venv` via `UV_PROJECT_ENVIRONMENT` + `PYTHONPATH`, no fresh
  `uv sync`.
- `uv run --no-sync` used throughout.
- Did not build a checker (the sibling gate-design work mentioned in the
  task brief is untouched by this diff).

## UNVERIFIED

- **`PWR_RTN`'s classification** (3c) -- genuinely ambiguous between "fix
  it like `+15V_LS`" and "leave it, per the existing placement-zone
  tradeoff comment"; flagged for a human call, not guessed.
- **`GATE_HS`/`GATE_LS` sharing `"GateDrive"` with `PWM_HS`/`PWM_LS`**
  (3c) -- the most safety-relevant open item this sweep found (an
  isolator's primary/secondary pins sharing a netclass, the same pattern
  already fixed once for this component's `VDDA`/`VSSA` pins), but fixing
  it means choosing a new target class and re-verifying existing routing,
  not a manifest lookup. Not fixed; recommend a dedicated follow-up task.
- **21 unclassified SELV nets** (3d) -- denominator reported, not
  individually adjudicated; the "right" class for each is a judgment call
  this task's scope (assignment-data corrections against an
  already-explicit manifest domain) does not cover.
- **The pre-existing `TestClearanceIntegration::test_temper_board_clearance_compliance`
  failure** (9 REQ-SAFE-01 violations vs. its own docstring's claimed 0) --
  confirmed unrelated to this diff by dependency analysis (no shared
  inputs: manifest, `kicad_pcb`, and `default.net` are all byte-identical
  before/after), but not root-caused or fixed (out of this task's file
  scope, and predates this session).
- **The `+15V_LS`/`a` creepage-count reconciliation's own `AC Mains to LV`
  +1** (Stage 1 table) -- traced to a specific pair
  (`L1`<->`safety.ovp.r_div_top1-p2`) reporting a different track-segment
  length between two separate kicad-cli invocations of the byte-identical
  board, the same small run-to-run variance class the sibling triage doc's
  sec A.4 already documented for `creepage`. Confirmed not attributable to
  this diff's own condition logic (neither net's classification changed in
  Stage 1); not otherwise characterized.
- **Whether the 7-of-9 pre-existing `configs/temper_production_config.yaml`
  agreements (3a) reflect an actual prior human review of these nets, or
  just a different AI session's earlier, equally-unverified judgment call**
  -- treated here as corroborating evidence (a second, independent source
  reaching the same conclusion) but not as independent proof; the primary
  justification for every net in 3a is its own citation inside
  `elec/domain_manifest.yaml`, not this file.
