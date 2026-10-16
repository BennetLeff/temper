# Block validators re-run on the controller layout (DECISIONS C30, C34)

## C44 rerun (current results)

`results/`, `mappings/`, `summary.json` and the `*.sha256` files are from the **C1 board** (DECISIONS
C37-C44; `pcb/controller.kicad_pcb` sha256 `969936fbeedb9f313ee00c5eb2869b513591b93fa7b641dd5d702cbffeb04874`),
same binaries, exporters, filter and profiles as C34. One change to the binder: `--deviations
rtd-deviations-c37.json` declares the C37 RTD parts, MPNs and pad-net moves so that its census / MPN / pad gates
do not abort on them (any undeclared or stale difference still aborts); Rust still judges every one.

| Validator | C34 (pass / fail / indet) | C44 | New non-pass |
|---|---|---|---|
| Interlock | 70 / 5 / 5 | **69 / 6 / 5** | `aggregate` exact MPN (74HC30PW,118, C35/C36), WAIVERS W6 |
| Thermal-sense | 88 / 9 / 7 | **88 / 9 / 7** | none |
| RTD | 5 / 18 / 5 | **5 / 33 / 5** | 15 from the C37 sense filter and J3 protection, WAIVERS W7 |

Controls unchanged (standalone and pipeline). Negative controls still trip: interlock 67 / 8 and 68 / 8, thermal
86 / 11 and 87 / 11, RTD declared-absent `c_dvdd` 5 / 36; the undeclared `c_dvdd` drop and swap still abort the
binder. Not rerun on several boards (one routed board this round; see LAYOUT.md).

## C34 rerun (history)

`results/`, `mappings/`, `summary.json` and the `*.sha256` files were from the **C34 board**
(`pcb/controller.kicad_pcb`, sha256 `187cc5e5aaa8176047392705da45ecf8e58f9bb9055f9ace1e6eeb4f408b9228`, convergence run 3), with the same binaries, exporters,
filter, binder and profiles as the C30 run below. `summary-before-C34.json` keeps the C30 counts.

| Validator | C30 (pass / fail / indet) | C34 | Remaining non-pass |
|---|---|---|---|
| Interlock | 69 / 6 / 5 | **70 / 5 / 5** | host connectors absent (5); standalone indeterminates (5) |
| Thermal-sense | 86 / 14 / 7 | **88 / 9 / 7** | host connector absent (4), C32 trip resistors (5); standalone indeterminates (7) |
| RTD | 5 / 165 / 6 | **5 / 18 / 5** | `unit_io` absent (16 + 1 indet), DRDY on the expander (2); unit layer roles gnd In2 / +3V3 B.Cu (2 indet); standalone indeterminates (2) |

Every one of them is justified in **`WAIVERS.md`**. Gone: the stackup sum, the four thermal clearances
below 0.20 mm, the RTD filter locality, the 146 analog-return corridor failures and the RTD_AVDD-zone gap
(the layout changes are DECISIONS C34). The negative controls still trip (drop / swap cases add FAIL
findings over the new baseline), and the pipeline / standalone controls are unchanged.

The same counts came out on each of the three convergence boards (`run.sh` takes `BOARD=<file>`;
`layout/convergence.py` now keeps each run's board).

**Informative run** (not the verdict): `results/informative-controller-rtd-layer-roles.json`, the RTD
validator with `profile-controller-roles.json` (the controller's planes as the return-plane roles:
analog and clock return selv_gnd In1.Cu, upstream +3V3 In2.Cu). It shows what the two layer-role
indeterminates hide: the RTD SPI nets' clock return on B.Cu (WAIVERS W4, DECISIONS open item 14).

Rerun: as below, plus `KICAD_PY` for the exporters; about 45 s given the binaries.

---

## C30 run (history; the counts below are the C30 board's)

Re-run of the three Rust block validators of `zapote-harness` (interlock, thermal-sense, RTD) on
`zapote/controller/pcb/controller.kicad_pcb` (sha256 `45b962b1c61ab569d47c1450454225f8bea7015fc2c87bbf53b11623c92cfa06`),
base commit `0207a6974`, KiCad 10.0.4 exporters. Nothing in the controller board, schematic or the
standalone units was modified, and no validator check was weakened.

## Verdict

**None of the three validators passes on the controller layout. The result is FAIL for all three**, with the
failures falling into four classes (details below, counts in `summary.json`):

| Validator | Binary | Standalone control | Controller | Fails | Of which structural (absent host connector) | Genuine / contract mismatch |
|---|---|---|---|---|---|---|
| Interlock | `zapote-interlock` | exit 1, INDETERMINATE: 75 pass / 0 fail / 5 indet | **FAIL: 69 pass / 6 fail / 5 indet** | 6 | 5 (census, 2 x PARTS, TOPOLOGY, CONNECTIVITY) | 1 (stackup sum 1.6062 vs 1.600 mm) |
| Thermal-sense | `zapote-thermal` | exit 1, INDETERMINATE: 97 / 0 / 7 | **FAIL: 86 pass / 14 fail / 7 indet** | 14 | 4 (census, PARTS host, TOPOLOGY, CONNECTIVITY) | 10: stackup (1), C32 resistor MPNs (5), clearance < 0.20 mm (4) |
| RTD | `zapote-rtd --unit-input` | exit 1, INDETERMINATE: 5 / 0 / 2 | **FAIL: 5 pass / 165 fail / 6 indet** | 165 | 16 (`unit_io` absent) | 149: DRDY GPIO (2), decoupling locality (1), return-plane structure (146) |

Pass criterion fixed in advance: every validator exits 0 with no waived checks, or each waiver is justified
line by line. **Exit 0 is not reachable even for the standalone units**: all three standalone controls exit 1
with zero FAIL and only INDETERMINATE findings (physical tests NOT RUN, device-applicability and timing
conditions the validators deliberately leave open). So the achievable bar, applied here, is: zero FAIL, and
the INDETERMINATE set no larger than the standalone control's. The controller misses it on FAIL count; its
INDETERMINATE sets are the standalone's (RTD adds 3 "filled-zone evidence lacks ..." and 1 "unit_io pending",
which follow from the FAILs below).

## What was run (`run.sh`, ~35 s given the binaries)

1. **Build** `cd zapote && CARGO_TARGET_DIR=$PWD/../.target-validators cargo build --release -p zapote-harness`
   (30 s). Binaries used, exactly: `zapote-interlock`, `zapote-thermal`, `zapote-rtd` (hashes in
   `binaries.sha256`; also in the final report). The target dir is deleted after recording.
2. **Filter** (`filter_block.py`, plain Python text surgery on the saved board; the controller board is only
   read): keep the footprints with `SourceInstance` `interlock.*` / `thermal.*` / `rtd_pan.*`, strip the
   prefix for interlock and thermal (RTD keeps `rtd_pan.*`, which is the unit's own instance prefix),
   rename controller nets to the unit's net names, keep every segment/via/zone of the block's nets (the
   whole net, so connectivity is not cut), drop all other footprints, foreign-net copper and non-Edge
   graphics. Zone fills are kept verbatim. The net map comes from the unit's *compiled source manifest* by
   looking up the controller pad for each unit (instance, pad); conflicts (a unit net on two controller
   nets or vice versa) would be reported, not merged: there are none (`mappings/*.json`). The mapping
   report also checks pad-level equivalence with the unit netlist independently of Rust:
   interlock 94 pads, thermal 70, RTD 109, **0 pads on a different net, 0 extra connected pads**.
3. **Export** with the existing exporters, unchanged: `current-sense/tools/extract_current_sense_native.py`
   for interlock and thermal-sense, `rtd/native_measure.py` for the RTD. Both import
   `harness-lab/assembly_geometry.py`, which no longer exists in the tree (removed by d70fd1857); the file
   from `d70fd1857^` is vendored in `vendor/harness-lab/` (sha in `inputs.sha256`) and `run.sh` points the
   exporters at it. `rtd/native_measure.py` is run from a byte-identical copy so its relative path finds it.
4. **Bind / run.** Interlock and thermal take (unit source manifest, filtered export, unit contract).
   The RTD takes a `zapote.rtd.unit-input.v1` envelope from `bind_controller_rtd.py`, a three-change
   copy of `rtd/unit/bind_native.py` (header lists them): `--absent-instance` for the declared-absent
   `unit_io`, `--qualified-input` to carry the committed passive-network qualification receipt with only
   `source_hashes.board_sha256` rebound to the filtered board (Rust re-derives and decides qualification
   itself; it passed), and nothing else. `profile-controller.json` is `rtd/unit/profile.json` with
   `interface.connector_mpn = null` / `pending_qualified_source` (no host connector on the controller),
   `firmware.cs_gpio = 10` (controller.ato `mcu.IO10 ~ rtd_cs_n`) and `firmware.drdy_gpio = 65535`
   (DRDY is on TCA9555 P07, not a GPIO; DECISIONS C23). `controller_pins.h` carries those two facts for the
   binder. The Rust core pins `board.*` (4 layers, 35 um, 0.20 mm, 0.70/0.30 via) and the ten-net interface
   list, so those profile fields cannot differ per board and were left as the unit's.

## Census: subset handling (explicit, nothing synthesised)

The controller embeds a **strict subset** of each unit; the missing parts are exactly the host connectors,
which the controller replaces with copper (DECISIONS C1):

| Block | Unit census | Controller | Absent |
|---|---|---|---|
| interlock | 25 | 23 | `faults` (J1, B8B-XH), `host` (J2, B8B-XH) |
| thermal-sense | 27 | 26 | `host` (B6B-XH) |
| RTD | 36 | 35 | `unit_io` (FTSH-105-01-F-D) |

The validators check the exact census, so they report the absence and I did not hide it: the census,
connector PARTS, TOPOLOGY and CONNECTIVITY rules (which include the connector pads) FAIL. Given the
pad-level equivalence above (every remaining pad is on exactly its unit net), these five (interlock) and
four (thermal) rules are explained by the missing connector pads alone; that is an inference, not a Rust
output, because the Rust findings are boolean. No stand-in connector was fabricated.

## Results per validator (raw reports in `results/`, grouped counts in `summary.json`)

### Interlock (`results/controller-interlock.json`) - FAIL, 69 / 6 / 5
- Locality of all six bypass caps (<= 5 mm), 0.15 mm clearance, document binding, contract, all gate-logic
  findings: **pass**.
- FAIL (structural): `ERC.INTERLOCK.NATIVE_COMPONENTS`, `PARTS` (faults, host), `TOPOLOGY`, `CONNECTIVITY`.
- FAIL (genuine): `DRC.BOARD.STACKUP`: the controller board's stackup layers sum to 1.6062 mm against
  `general thickness 1.6`; the standalone units are exact. Same finding in thermal. A fixable board-file
  inconsistency (outside this task's remit: board not modified).
- INDETERMINATE x5: identical to the standalone control (physical tests NOT RUN, SENSOR_LIVE/AUX producers,
  watchdog timing, HC30 applicability).

### Thermal-sense (`results/controller-thermal.json`) - FAIL, 86 / 14 / 7
- Structural: census, `PARTS host`, `TOPOLOGY`, `CONNECTIVITY`.
- **C32 deviation (expected, documented in DECISIONS C32):** `PARTS` fails for `hs_top` (9.09 k -> 11.5 k),
  `hs_bottom` (11.5 k -> 8.06 k), `coil_top`, `coil_bottom`, `coil_hyst`. The validator's constants are
  the 85/120 C standalone trip values; the controller trips at 101.4/175.7 C. Resolving this is a change
  request to the thermal-sense unit, not something to waive here. The unit's 64-corner trip analysis is not
  re-checked by this validator for the controller values (the Python port in `controller_calcs.py` is).
- **Genuine layout findings against the unit's 0.20 mm floor:** `DRC.NATIVE.CLEARANCE` x4: pad/trace 0.1988 mm
  (`hs_or.3`) and 0.1826 mm (`hs_comp.5`), trace/via 0.1804 and 0.1999 mm (UUIDs in the report). The interlock
  unit uses 0.15 mm and passes; whether 0.20 mm is a requirement on the controller (JLC capability is lower)
  is a design call, not made here.
- Stackup: as above. INDETERMINATE x7: identical to the standalone control.

### RTD (`results/controller-rtd.json`) - FAIL, 5 / 165 / 6
- Passing: MODEL_QUALIFICATION (receipt rebound, Rust re-derived the 9-node network bound), UNIT_MODEL,
  FAULT_CORNERS (static), domain boundary, local escape.
- Structural (16): `unit_io` absent: `UNIT_INTERFACE` x11 (component + 10 pins), `SPI_SERIES_PLACEMENT` unit_io.4-8 (x5).
- **Controller pin map vs validator's source-defined GPIOs (2):** `FIRMWARE_GPIO_CORRESPONDENCE` and
  `SPI_SERIES_PLACEMENT` for RTD_DRDY: the controller has no direct DRDY GPIO (expander P07, C23), the
  validator hard-codes GPIO 9. Not waived. Limitation: the validator hard-codes SCK/SDI/SDO as GPIO 8/11/12
  (controller: 11/13/12), so it cannot check those three against the controller; the feed is only CS and DRDY.
- **Genuine layout (1):** `DRC.RTD.LOCAL_DECOUPLING`: the 1 nF differential filter `c_rtd_input` is outside the
  3 mm locality of `adc` (pad to ADC pin 10.0 mm and 14.0 mm).
- **Return-plane structure (146 + 3 indeterminate):** the validator expects the unit's layer roles: RTD_AVDD
  pour on F.Cu, ground on In2.Cu, +3V3 on B.Cu. The controller has no RTD_AVDD pour, ground on In1.Cu and
  v3v3 on In2.Cu, so the filled-corridor check fails 146 analog-return traces and reports the three planes
  as absent evidence. This is a structural mismatch between two layout contracts rather than evidence of a
  specific bad route; it still means the validator cannot vouch for the RTD analog return on this board.
- INDETERMINATE: device applicability and brownout timing (same as the standalone control), the 3 plane
  evidence gaps and "unit_io pending".

## Controls (all in `results/`)

- **Standalone controls** (`control-standalone-*`): each validator on its own committed unit input:
  interlock `interlock/evidence/native-final.json`, thermal `thermal-sense/evidence/native-final.json`, RTD
  `rtd/model-correctness/qualified-input/input.json`. All: zero FAIL, only the documented INDETERMINATE
  (75/0/5, 97/0/7, 5/0/2), exit 1 as by design.
- **Pipeline controls** (`control-pipeline-*`): the unit's own candidate board put through the same exporter
  (and, for RTD, `bind_controller_rtd.py` with the unit profile, no absent instances, receipt rebound):
  identical counts to the standalone controls. This shows the exporter/binder path itself does not
  introduce failures.
- **Negative controls on the filtered controller exports** (delta against the controller baseline):
  - interlock, delete `aggregate_bypass`: + `PARTS aggregate_bypass`, + `LOCALITY aggregate_bypass.1 to aggregate.14`
    (6+2 fails).
  - interlock, move `fault_inv_bypass` pad 1 to `gnd`: + 2 `NATIVE.CLEARANCE` at 0.000 mm (pad/trace, pad/via).
  - thermal, delete `hs_bypass`: + `PARTS hs_bypass`, + `LOCALITY hs_bypass.1 to hs_comp.5`.
  - thermal, move `hs_bypass` pad 1 to `COIL_REF`: + 2 `NATIVE.CLEARANCE` at 0.000 mm.
  - RTD, delete `c_dvdd` and declare it absent: + `LOCAL_DECOUPLING` x2, + `UNIT_PAD_GEOMETRY` (168 fails vs 165).
    Without the declaration, or with its pad moved to `gnd`, the binder aborts on census / pad-net mismatch
    (`results/negative-rtd-*-binder-abort.txt`, exit 1).
  The baseline already fails on census/topology, so the swap cases are caught by the clearance rule rather
  than TOPOLOGY; the drop cases are caught by exact-MPN and locality rules.

## Limitations

- The filtered export carries only the copper of the block's own nets. Foreign-net copper near the block is not
  in the validators' view, so their clearance checks cover block-net pairs only; the full-board KiCad DRC
  (`../drc.json`) covers the rest. Net sharing means shared nets (GND, v3v3, HS_FAULT ...) bring the whole
  net's copper, as intended.
- Blocks share the board and nets (HS_FAULT/COIL_FAULT in interlock and thermal; v3v3/selv_gnd everywhere).
  Each run sees only its block's pads; cross-block interactions are not validated.
- `harness-lab/assembly_geometry.py` is a vendored historical file (KiCad connectivity); its output is trusted
  as the exporters already trust it.
- The qualification receipt's `board_sha256` was rebound by script; its content (network bound, model) is the
  committed unit receipt. The receipt is board-independent in substance but this is a bookkeeping rebind.
- The thermal and interlock validators check unit constants; the controller's changed trip values (C32) are
  outside what the thermal validator can accept. The controller's own stackup, 0.5 oz inner copper and JLC rules
  differ from the unit contracts; Rust pins the unit values in the RTD profile.
- Physical tests remain NOT RUN; INDETERMINATE items are not evidence of pass.

## Rerun

```sh
cd zapote && CARGO_TARGET_DIR=$PWD/../.target-validators cargo build --release -p zapote-harness && cd ..
WORK=/private/tmp/blockval zapote/controller/evidence/block-validators/run.sh .target-validators/release
```
Intermediates (filtered boards, ~4 MB each; native exports up to 20 MB) are in `$WORK`, not committed;
their hashes are in `intermediates.sha256`. `run.sh` overwrites `results/`, `mappings/` and the `*.sha256` files.
