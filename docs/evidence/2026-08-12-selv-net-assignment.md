<!-- provenance: commit=06d21251174eca42d73ce12c4e8f4ca39250974c dirty=false (branch fix/unassigned-selv-nets, built on top of #1083 fix/unassigned-hv-domain-nets commit 6ca3172dd via a clean merge -- git log shows both parents). pcb/temper.kicad_pcb sha256=6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64, byte-identical to power_pcb_dataset/drc_ceiling.json's recorded provenance input and to docs/evidence/2026-08-12-unassigned-domain-nets.md's "before"/"after" board -- pcb/temper.kicad_pcb was never modified at any point in this session (confirmed: `git status` shows no changes to it throughout). Real net names and pad counts come from a hand-written S-expression tokenizer walking pcb/temper.kicad_pcb by paren-depth (scripts/check_hv_netclass_coverage.py's own `parse_board_net_names`, reused directly; a companion pad-counter built on the same tokenizer, not a grep -- see Sec 1.4). DRC measured with kicad-cli 10.0.5 (/home/bennet/.local/opt/kicad-10.0.5, wrapped by ~/.local/bin/kicad-cli) via temper_placer.validation._drc_api.run_drc (--all-track-errors, single-thread KICAD_CONFIG_HOME pin), pcb/temper.kicad_dru freshly regenerated from scripts/generate_kicad_dru.py before every measurement -- the repo's own ci_check_drc.py protocol. Every DRC number below is a fresh measurement taken in this session (20-30 samples per board variant, five variants); none is copied from a prior document. -->

# The 20 unassigned SELV nets are now correctly classed. One of them, `gnd`, accounts for the entire measured blast radius; the other 19 move nothing.

**Verdict up front.** `pcb/temper.kicad_pro`'s `net_settings.netclass_assignments` had no entry for 20 SELV-domain nets, including `gnd` — the board's own largest net (86 pads). All 20 are now assigned, using only the 9 classes `pcb/temper.kicad_pro` actually declares (`Default`, `Power`, `HighVoltage`, `GateDriveHV`, `GateDriveSELV`, `HighVoltageIsolated`, `ACMains`, `FinePitch`, `Differential`) — no netclass value was touched, no new class was added, and `pcb/temper.kicad_pcb` was never modified. **A single net, `gnd` (`Default` → `Power`), is measured to account for the entire clearance/aggregate-error delta the SELV fix produces; the other 19 nets move nothing** (isolated below in Sec 3.3 — assigning them all but `gnd` reproduces the pre-SELV-fix numbers exactly, and assigning `gnd` alone reproduces the full-fix numbers exactly). The fix breaches `power_pcb_dataset/drc_ceiling.json` further, as expected and as instructed: `clearance` 386→**418** (+32), `creepage` 186→**198** (+12), aggregate errors 1266→**1310** (+44). The ceiling is not raised. `scripts/check_hv_netclass_coverage.py`'s PROPERTY 4 (SELV coverage) is promoted from informational to **blocking**, shown failing (exit 3, naming all 20 nets) against the pre-fix state and passing (exit 0) after; the separate, permanently-informational PROPERTY 5 (37 deliberately-kept dead-alias assignments) is left alone, per the task's instruction.

**The corrected committed-board baseline, superseding 386 as the comparator for any future board**: once all 21 domain nets (the 1 HV net #1083 fixed, plus these 20 SELV nets) carry correct `kicad_pro` assignments, `pcb/temper.kicad_pcb` — unchanged since 2026-08-08 — measures **`clearance` 418 (deterministic), `creepage` 197–198, aggregate errors 1309–1310, warnings 624** (30/30 samples each, cross-checked by an independent 10-sample run and by `scripts/ci_check_drc.py`'s own live invocation against the committed worktree).

---

## 1. The 20 nets, their assigned classes, and the grounding for each

### 1.1 What was missing, confirmed independently

`docs/evidence/2026-08-12-unassigned-domain-nets.md` (PR #1083) found 21 domain-declared nets absent from `pcb/temper.kicad_pro`'s real `netclass_assignments`: 1 HV (`PWR_RTN`, fixed by that PR) and 20 SELV. Re-derived here from a fresh cross-reference of `elec/domain_manifest.yaml`'s `SELV` domain list against `pcb/temper.kicad_pro`'s real assignments (`scripts/check_hv_netclass_coverage.py`'s PROPERTY 4, run against the pre-fix state) — same 20, same names:

`gnd`, `usb_dn`, `usb_dp`, `i2c_scl_ui`, `i2c_sda_ui`, `rtd_force_p`, `rtd_force_n`, `rtd_sense_p`, `rtd_sense_n`, `WDT_RESET_N`, `SHUTDOWN`, `RELAY_CTRL`, `DISCHARGE_CTRL`, `discharge.k_dis1-coil1`, `discharge.k_dis1-coil2`, `discharge.k_dis2-coil1`, `power_in.bypass_relay-coil1`, `power_in.bypass_relay-coil2`, `safety.ovp.comp-inp`, `safety.uvlo_logic-line`.

### 1.2 A constraint that changes the answer for one of them: only 9 classes are real

`packages/temper-placer/src/temper_placer/core/design_rules.py`'s `TEMPER_NET_ASSIGNMENTS` names a class for exactly one of these 20 — `"gnd": "GND"` — and the task brief warns explicitly that this table is itself a source of drift, to be verified rather than copied. It doesn't hold up: **`pcb/temper.kicad_pro`'s `net_settings.classes` declares exactly 9 netclasses**, and `"GND"` is not one of them:

```
$ python3 -c "
import json
d = json.load(open('pcb/temper.kicad_pro'))
print([c['name'] for c in d['net_settings']['classes']])"
['Default', 'Power', 'HighVoltage', 'GateDriveHV', 'GateDriveSELV',
 'HighVoltageIsolated', 'ACMains', 'FinePitch', 'Differential']
```

`scripts/sync_kicad_netclass_assignments.py` — the script that mechanically syncs `kicad_pro` from `TEMPER_NET_ASSIGNMENTS` — already documents this exact gap in its own module docstring ("`PWR_RTN` [...] and its alias `CGND` [...] map, via `TEMPER_NET_ASSIGNMENTS`, to the `"GND"` class — and `pcb/temper.kicad_pro` has no `"Ground"` (or any other) declared netclass corresponding to it, so this script's own 'target class must be a class `kicad_pro` actually declares' rule already excludes them structurally") and its `compute_target_assignments` function enforces it in code (`if cls not in declared_classes: continue`).

Measured, not just read from the docstring: a scratch copy with `"gnd": "GND"` written into `kicad_pro` produces DRC output **byte-identical in every category, including `clearance` (386, exactly matching leaving `gnd` unassigned)**, to a scratch copy with no `gnd` entry at all — confirming `kicad-cli` silently treats an assignment naming an undeclared class as if it were absent, not as a 0.3mm rule:

| kicad_pro `gnd` assignment | clearance | creepage (1 sample) | track_width |
|---|---:|---:|---:|
| (absent) | 386 | 182 | 199 |
| `"GND"` (undeclared) | 386 | 184 | 199 |
| `"Power"` (declared) | 408 | 183 | 199 |

(The 182/184 creepage difference between the first two rows is a single-sample draw from the documented 182–184 nondeterministic band, not a real effect of the `"GND"` string — `clearance`, which is fully deterministic on this board, is unmoved, and `track_width` — which would move if `A.NetClass == 'GND'`'s custom `.kicad_dru` rule were actually firing — does not move either.)

Per this task's rule ("editing netclass values is not [in scope]") and PR #1061's settlement of netclass parameters, adding a tenth class to `kicad_pro` is out of scope here — mirroring #1083's own precedent of leaving `design_rules.py`'s `PWR_RTN → GND` mapping as a named, orthogonal, un-fixed finding rather than resolving it by touching the class list. `gnd`'s assignment below is therefore chosen from the 9 real classes, not from `design_rules.py`'s table.

### 1.3 The 20 nets

| Net | Assigned class | Grounding |
|---|---|---|
| `gnd` | `Power` | The board's largest net (86 pads, confirmed Sec 1.4). `design_rules.py`'s own `"GND"` class doesn't exist in `kicad_pro` (Sec 1.2) and can't be copied. The original, still-committed `docs/specs/NET_CLASS_SPECIFICATION.md` (REQ-ELEC-01) Sec 3.2 explicitly lists **"GND (control ground)"** as an assigned net of the **Power** class (0.5mm clearance) — the only textual source in this repo that ever formally classified `gnd`, and it names `Power`, not a dedicated ground class. `Power` is also the most protective of the 9 real classes plausible for a return net (vs. `Default`'s 0.2mm, the status quo this fix exists to correct). |
| `usb_dn`, `usb_dp` | `Differential` | `elec/src/main.ato:531-532,946-947` wires both directly to the MCU's own USB D-/D+ pins (`mcu.usb_dn`/`mcu.usb_dp`) — a real differential pair. `kicad_pro` already carries this exact function under its dead-alias spelling: `"USB_D+": "Differential"`, `"USB_D-": "Differential"`. |
| `i2c_scl_ui`, `i2c_sda_ui` | `Default` | `elec/src/main.ato:533-534,950-951`, "I2C expansion header for UI" — an MCU-side digital bus to an off-board connector. `kicad_pro` already classes the same function under its dead-alias spelling `"I2C_SCL": "Default"`, `"I2C_SDA": "Default"`; `NET_CLASS_SPECIFICATION.md` 3.1 explicitly buckets "I2C bus" under `Default`. |
| `rtd_force_p`, `rtd_force_n`, `rtd_sense_p`, `rtd_sense_n` | `FinePitch` | `elec/src/modules.ato:1994-1998` wires these directly to `adc.FORCE_P`/`FORCE_N`/`RTDIN_P`/`RTDIN_N`, where `adc` is U8 — `elec/src/components.ato:402-403` confirms U8's footprint is `SSOP-20_..._P0.635mm` (MAX31865AAP+), the exact part `design_rules.py`'s `FinePitch` class comment names ("U8 SSOP-20 (0.635mm)"). Same component, same package, as the already-`FinePitch` `bias`/`refin_n`/`vbias`/`sclk`/`sdi`/`sdo`/`cs_n` nets (all also U8/`adc` pins, confirmed by the same file). |
| `WDT_RESET_N` | `Default` | `elec/src/main.ato:895`, `safety.wdt_reset_n.line`, a 3.3V MCU-side logic fault line. Its sibling `WDT_KICK` is already `"Default"` in `kicad_pro`. |
| `SHUTDOWN` | `Default` | `elec/src/main.ato:899`, `safety.shutdown.line`. Its dead-alias sibling `"SHUTDOWN_N": "Default"` already exists. |
| `RELAY_CTRL` | `Default` | `elec/src/main.ato:927`, `mcu.relay_ctrl.line` — `elec/src/modules.ato:760`: "RELAY_CTRL (3.3V GPIO) cannot drive the 75mA/12V coil directly", i.e. this is the 3.3V MCU logic line upstream of a driver transistor, not the coil itself (see next row). `NET_CLASS_SPECIFICATION.md` 3.1's "Control signals" bucket is exactly this net shape. |
| `DISCHARGE_CTRL` | `Default` | `elec/src/main.ato:943`, `mcu.discharge_ctrl.line` — same 3.3V MCU-GPIO shape as `RELAY_CTRL`. |
| `discharge.k_dis1-coil1`, `discharge.k_dis1-coil2`, `discharge.k_dis2-coil1` | `Power` | `elec/domain_manifest.yaml:426-463`: the coil-drive pins of the TE/Schrack RT314012 discharge relays K2/K3, labeled "SELV coil drive" — the switched 12V/~75mA load side of the driver transistor `RELAY_CTRL`/`DISCHARGE_CTRL` feed (`elec/src/modules.ato:760`), not a logic signal. **Directly corroborated**: `configs/temper_production_config.yaml` (an orphaned config, not loaded by any code path today, but independent corroborating evidence per the same convention #1083 used for its own HV sweep) already classes these exact three net names `"Power"` (lines 159-161), with the file's own comment: "Power nets pull the 15V/3V3 conversion + relay coil drivers into Power." |
| `power_in.bypass_relay-coil1`, `power_in.bypass_relay-coil2` | `Power` | Same reasoning: `elec/domain_manifest.yaml:415-424`, the Omron G4A-1A-E DC12 bypass relay's coil pins, "SELV coil drive". Also directly corroborated in `configs/temper_production_config.yaml:157-158` as `"Power"`. |
| `safety.ovp.comp-inp` | `Default` | `elec/domain_manifest.yaml:334-352`'s own single-fault analysis places this node at ~1.4V normal / ~3.6V clamped-fault, fed from the SELV-referenced TLV3201 comparator (a standard SOT-23 part, not fine-pitch) — a low-current analog sense node, the same shape as the already-`Default` `V_SENSE`/`FAULT_STATUS`/`TEMP_FAULT`. |
| `safety.uvlo_logic-line` | `Default` | `elec/domain_manifest.yaml:292-299`: UVL-02's `LogicUVLOComparator` fault line, referenced to `power_3v3` via a TPS3700 (standard-pitch). Same "logic fault line" shape as `WDT_RESET_N`/`SHUTDOWN` above. |

No net in this list was left unassigned as ambiguous — every one had either a direct dead-alias precedent already in `kicad_pro`, a direct `configs/temper_production_config.yaml` corroboration, or an unambiguous component/pitch match traced in `elec/src`.

### 1.4 Verified against the real board, structurally

Every net above is confirmed a real, on-board net — not a manifest artifact — by a structural (non-grep) parse of `pcb/temper.kicad_pcb`, reusing `scripts/check_hv_netclass_coverage.py`'s own `parse_board_net_names` (paren-depth walk over a real token stream, matching only top-level `(net N "name")` forms — a grep or naive substring match would also match every pad's own nested `(net ...)` reference, the exact failure this task's own brief warns a prior agent already hit). A companion pad-counter built on the same tokenizer confirms `gnd` really is the board's largest net:

```
net                                      on_board  pads
gnd                                      True      86
DISCHARGE_CTRL                           True       2
RELAY_CTRL                               True       2
SHUTDOWN                                 True       6
WDT_RESET_N                              True       3
i2c_scl_ui                               True       2
i2c_sda_ui                               True       2
usb_dn                                   True       1
usb_dp                                   True       1
rtd_force_p                              True       1
rtd_force_n                              True       1
rtd_sense_p                              True       1
rtd_sense_n                              True       1
discharge.k_dis1-coil1                   True       3
discharge.k_dis1-coil2                   True       5
discharge.k_dis2-coil1                   True       3
power_in.bypass_relay-coil1              True       3
power_in.bypass_relay-coil2              True       3
safety.ovp.comp-inp                      True       4
safety.uvlo_logic-line                   True       4

top 5 nets by pad count: gnd(86), +3V3(51), PWR_RTN(18), vcc(13), DC_BUS_RTN(12)
```

162 top-level nets total on the real board; 522 pads total. `gnd` at 86 pads is confirmed the single largest net on the board, exactly matching `design_rules.py`'s own comment.

The fix (`pcb/temper.kicad_pro`, 20 lines appended to `net_settings.netclass_assignments`, following the same additive style as #1083's `PWR_RTN` line — no existing entry touched, no netclass value touched, `pcb/temper.kicad_pcb` never modified):

```diff
       "vcc": "Power",
       "V_BUS_SENSE": "Power",
+      "gnd": "Power",
+      "usb_dn": "Differential",
+      "usb_dp": "Differential",
+      "i2c_scl_ui": "Default",
+      "i2c_sda_ui": "Default",
+      "rtd_force_p": "FinePitch",
+      "rtd_force_n": "FinePitch",
+      "rtd_sense_p": "FinePitch",
+      "rtd_sense_n": "FinePitch",
+      "WDT_RESET_N": "Default",
+      "SHUTDOWN": "Default",
+      "RELAY_CTRL": "Default",
+      "DISCHARGE_CTRL": "Default",
+      "discharge.k_dis1-coil1": "Power",
+      "discharge.k_dis1-coil2": "Power",
+      "discharge.k_dis2-coil1": "Power",
+      "power_in.bypass_relay-coil1": "Power",
+      "power_in.bypass_relay-coil2": "Power",
+      "safety.ovp.comp-inp": "Default",
+      "safety.uvlo_logic-line": "Default"
     },
```

The 37 dead-alias `kicad_pro` assignments (nets absent from the real board, e.g. `AC_L`/`SWITCH_NODE`/`RTD_CS`) are confirmed unchanged and untouched — `scripts/check_hv_netclass_coverage.py`'s ghost-assignment count (Sec 2 below) still reads exactly 37, matching #1083's own count, and none of the 20 nets fixed here collides with any of the 37 (a live net getting a real assignment is a different net than a dead one keeping its inert one).

---

## 2. The gate: PROPERTY 4 promoted to blocking; PROPERTY 5 stays informational

`scripts/check_hv_netclass_coverage.py`'s PROPERTY 4 (the SELV mirror of PROPERTY 3, added by #1083 as informational) checks three things for every `SELV`-domain net: it exists on the real board, it has a real `kicad_pro` assignment, and that assignment's `safety_category` is `LV`. With all 20 nets now assigned, every one of those three checks is clean (0), so nothing excuses staying informational any longer — it is now **BLOCKING**, mirroring PROPERTY 3's HV treatment exactly (`run()`'s violation condition now includes `selv_domain_nets_off_board`, `selv_domain_nets_unassigned_in_kicad_pro`, and `selv_domain_class_safety_mismatches`).

The board-wide ghost-assignment check (37 dead-alias entries) is split out into its own **PROPERTY 5** and stays permanently informational — it is not a candidate for promotion, unlike PROPERTY 4 was. `scripts/sync_kicad_netclass_assignments.py`'s own docstring documents keeping these 37 entries as a deliberate, permanent policy ("It never removes an existing `kicad_pro` entry, even one that names a net no longer present on the board"). Gating on their presence would make PROPERTY 5 permanently red for a defect nobody introduced; promoting it would first require deciding to delete or rename those 37 entries — a separate, larger, explicitly out-of-scope decision this task does not make (per the brief: "confirm they are still deliberate, do not delete them").

Shown failing on the pre-fix state and passing after (`pcb/temper.kicad_pro` swapped for the pre-fix copy, the gate script itself — this branch's PROPERTY 4 promotion — left in place):

```
$ git show HEAD~2:pcb/temper.kicad_pro > pcb/temper.kicad_pro   # ONLY kicad_pro reverted
$ uv run python scripts/check_hv_netclass_coverage.py; echo "exit: $?"
...
=== PROPERTY 4 (BLOCKING): SELV-domain nets vs pcb/temper.kicad_pro's REAL netclass_assignments ===
  off-board SELV-domain nets: 0
  SELV-domain nets unassigned in kicad_pro: 20
    VIOLATION net 'DISCHARGE_CTRL' (SELV domain) has no kicad_pro netclass assignment -- falls to Default (0.2mm)
    VIOLATION net 'RELAY_CTRL' (SELV domain) has no kicad_pro netclass assignment -- falls to Default (0.2mm)
    ... (18 more, all 20 named)
  SELV wrong-safety-category assignments: 0
...
FAILED -- ... 0 off-board SELV-domain net(s), 20 SELV-domain net(s) unassigned in kicad_pro,
0 SELV-domain class safety-category mismatch(es) (PROPERTY 4)
exit: 3

$ git checkout -- pcb/temper.kicad_pro   # this branch's fix restored
$ uv run python scripts/check_hv_netclass_coverage.py; echo "exit: $?"
...
=== PROPERTY 4 (BLOCKING): SELV-domain nets vs pcb/temper.kicad_pro's REAL netclass_assignments ===
  off-board SELV-domain nets: 0
  SELV-domain nets unassigned in kicad_pro: 0
  SELV wrong-safety-category assignments: 0

=== PROPERTY 5 (INFORMATIONAL, non-blocking, permanently): board-wide ghost kicad_pro assignments ===
  ghost kicad_pro assignments (either domain): 37
...
HV netclass coverage gate passed
exit: 0
```

`scripts/tests/test_check_hv_netclass_coverage.py` gained 4 new tests mirroring PROPERTY 3's own falsifier set for SELV (`test_selv_net_unassigned_in_kicad_pro_now_blocks`, `..._is_not_flagged`, `test_selv_net_off_board_is_flagged`, `test_selv_net_wrong_safety_category_is_flagged`) plus one proving PROPERTY 5 remains non-blocking on its own (`test_ghost_findings_remain_informational_not_blocking`); the old test asserting PROPERTY 4 never blocks was replaced (it asserted the *pre-promotion* contract, which this fix deliberately changes). All 56 tests in the file pass. `ruff check` is clean.

Also confirmed clean, unaffected by this change: `scripts/check_netclass_class_param_correspondence.py` (0 field mismatches — no netclass value touched), `scripts/check_netclass_map_board_correspondence.py` (0 broken keys, 58 checked), `scripts/sync_kicad_netclass_assignments.py --check` ("already agrees... for all 51 covered net(s)" — no drift introduced against `TEMPER_NET_ASSIGNMENTS`, since 19 of the 20 nets fixed here are absent from that table entirely and `gnd`'s `"GND"` target remains excluded by the same undeclared-class rule as before). `scripts/check_domain_partition.py` still requires a locally-built `elec/build/default.net` (gitignored, not built in this session — pre-existing environment gap per #1083, unrelated). `scripts/check_pcl_config_board_correspondence.py` and `scripts/check_layer_plane_emission_coverage.py` both still fail on this branch for reasons entirely unrelated to netclasses (stale zone-bounds configs; a Rust parser dropping a layer-role token) — confirmed pre-existing by inspection, unchanged from #1083's own finding.

---

## 3. Blast radius — measured across five board variants, and it breaches the ceiling further

### 3.1 Method

Five `pcb/temper.kicad_pro` variants, all paired with the same, real, byte-identical, committed `pcb/temper.kicad_pcb` (sha256 `6928b7c8…`) and a freshly-regenerated `pcb/temper.kicad_dru`, measured from read-only scratch copies (the committed board file itself was never written):

- **A (`origin/main`)** — neither #1083's HV fix nor this branch's SELV fix. Reproduces the historical "386" baseline.
- **B (#1083 alone)** — `PWR_RTN` assigned, all 20 SELV nets still unassigned.
- **C (this branch, full fix)** — all 21 domain nets (1 HV + 20 SELV) correctly assigned. **The new corrected baseline.**
- **D (B + `gnd` only)** — isolates `gnd`'s individual contribution on top of B.
- **E (C − `gnd`)** — all 19 *other* SELV nets assigned, `gnd` deliberately left unassigned; isolates whether anything besides `gnd` moves the numbers.

20–30 samples per variant (A: 20, B: 20, C: 30, D: 10, E: 10 — matching #1083's own 20-sample convention, with extra samples on C since it is this document's new reported baseline).

### 3.2 Results

| Category | A (`origin/main`) | B (#1083 alone) | **C (full fix)** | Ceiling | Breach at C? |
|---|---:|---:|---:|---:|---|
| `clearance` | 386 (386–386, deterministic) | 396 (396–396, deterministic) | **418** (418–418, deterministic) | 386 | **YES, +32** |
| `creepage` | 183–184 | 196–198 | **197–198** | 186 | **YES, +12** |
| aggregate errors | 1263–1264 | 1286–1288 | **1309–1310** | 1266 | **YES, +44** |
| every other error category (18 categories: `annular_width`, `copper_edge_clearance`, `courtyards_overlap`, `drill_out_of_range`, `hole_clearance`, `hole_to_hole`, `lib_footprint_issues`, `missing_courtyard`, `pth_inside_courtyard`, `shorting_items`, `silk_edge_clearance`, `silk_over_copper`, `silk_overlap`, `solder_mask_bridge`, `track_dangling`, `track_width`, `tracks_crossing`, `via_dangling`, `via_diameter`) | unchanged | unchanged | **unchanged** | — | no |
| all warning categories | 624 total | 624 total | **624 total, unchanged** | 489 | pre-existing, not attributable (see below) |

`scripts/ci_check_drc.py --backend kicad-cli`, run directly against this branch's real, committed changes (not a scratch copy), confirms the same numbers and the exit code CI would produce:

```
FAIL: temper: DRC FAIL
  aggregate errors 1310 exceeds ceiling 1266 (+44)
  per-type errors (source: kicad-cli): 2 categories over ceiling (0 new, 2 regressed):
    [   ] clearance 418 > 386 (+32)
    [   ] creepage 198 > 186 (+12)
PASS: noise-headroom guard (single-sample DRC is safe for every recorded category)
```

**Nothing falls.** Every category besides `clearance`/`creepage`/(their roll-up into) aggregate errors is bit-for-bit identical across all five variants. `creepage`'s A→B (+13/+14) and B→C (+0/+1) shift as a whole band rather than overlapping partially — consistent with the known KiCad pointer-dedup nondeterminism (issue #20048, `docs/evidence/2026-08-04-drc-measurement-determinism.md`), not new noise from this change. `clearance` is fully deterministic at every one of the 90 samples taken across A/B/C.

**Warnings (624, vs. ceiling 489) are unrelated to this fix.** Identical across every one of A/B/C/D/E — this measurement environment's kicad-cli 10.0.5 prefix still lacks the `kicad-footprints` package, inflating `lib_footprint_issues` identically regardless of netclass assignments, exactly as #1083's own document already established. Not reported as this branch's blast radius.

### 3.3 Attribution: `gnd` alone accounts for the entire SELV-fix delta

Isolating `gnd` from the other 19 nets gives a clean, surprising, and fully attributable result:

| Variant | clearance | creepage | aggregate errors |
|---|---:|---:|---:|
| **B** (HV fix only, no SELV nets) | 396 | 196–198 | 1286–1288 |
| **D** (B + `gnd` **only**, 10 samples) | **418** | 197–198 | 1309–1310 |
| **E** (C − `gnd`, all 19 *other* SELV nets, 10 samples) | **396** | 197–198 | 1287–1288 |
| **C** (full fix, all 20 SELV nets, 30 samples) | **418** | 197–198 | 1309–1310 |

D (only `gnd` fixed) reproduces C (all 20 fixed) exactly. E (`gnd` deliberately left out, the other 19 fixed) reproduces B (none fixed) exactly, within the same creepage noise band. **The other 19 nets move nothing measurable in this board's current layout.** This is expected, not a sign the other 19 assignments are pointless: `gnd`'s 86 pads and board-wide extent mean it participates in far more copper-to-copper pairs than any of the other 19 nets (1–6 pads each, Sec 1.4) combined, and its class jump (`Default` 0.2mm → `Power` 0.5mm, a same-domain LV↔LV clearance increase, not a cross-domain HV↔SELV one — which is also why `creepage`, an HV↔LV-specific rule, barely moves B→C: the HV side of every crossing already carried its real class after #1083) is the only one of the 20 assignments that measurably tightens any already-close copper on this specific, real board layout. The other 19 remain correct and necessary for what `gnd`'s isolation doesn't cover: gate coverage (Sec 2), future layout changes that route copper closer to any of them, and the SELV-domain safety-category guarantee PROPERTY 4 now enforces.

### 3.4 Per the task's explicit instruction: not engineered around

The ceiling is not raised in this branch, and no class was swapped for a weaker one to stay under it. `power_pcb_dataset/drc_ceiling.json` is untouched. The +32/+12/+44 are real, newly-enforced clearance requirements against copper that was, until this fix, invisibly under-separated because `gnd` carried no netclass at all — surfacing that is this task's entire point, not a regression to be hidden.

---

## 4. Summary of what changed and what didn't

| File | Change |
|---|---|
| `pcb/temper.kicad_pro` | +20 lines in `net_settings.netclass_assignments`. No netclass *value* touched, no new class added. |
| `scripts/check_hv_netclass_coverage.py` | PROPERTY 4 (SELV coverage) promoted informational → BLOCKING. PROPERTY 5 (board-wide ghost assignments, split out from the old PROPERTY 4) stays informational, permanently. PROPERTIES 1/2/3 unchanged. |
| `scripts/tests/test_check_hv_netclass_coverage.py` | +4 tests mirroring PROPERTY 3's HV falsifiers for SELV; 1 test rewritten (ghost-only case) to match PROPERTY 5; 1 pre-existing PROPERTY 3 control test updated (its default SELV fixture nets needed real assignments now that PROPERTY 4 blocks). All 56 tests pass. |
| `pcb/temper.kicad_pcb` | **Not touched.** |
| `power_pcb_dataset/drc_ceiling.json` | **Not touched** — see Sec 3.4. |
| Netclass parameter *values* (`pcb/temper.kicad_pro`'s `net_settings.classes[]`, `netclass_rules.yaml`, `design_rules.py`'s `TEMPER_NET_CLASSES`) | **Not touched** — PR #1061 settled these, per the task's explicit instruction. |
| `design_rules.py`'s `TEMPER_NET_ASSIGNMENTS` (`"gnd": "GND"`) | **Not touched** — orthogonal, Python-placer-side finding, same shape and same disposition as #1083's own `PWR_RTN → GND` note (Sec 1.2 above); a legitimate follow-up, out of this task's scope (`pcb/temper.kicad_pro` assignments). |
