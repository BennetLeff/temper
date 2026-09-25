# Reference revision 09: RevB protection integration map

Status: **source-only integration contract; review candidate**. This map does
not claim an assembled board, a physical F2, a local film reservoir, a
qualified auxiliary/logic producer, or hardware protection.

## Authority and candidate choice

The exact maintained protection authority is
`elec/src/power_entry_f2_shutdown_revb.ato:PowerEntryF2ShutdownRevB` together
with the compiled `f2-shutdown-04/source-07` export. The source hash is
`050818ac162a1aa93ecd63325588adb2102504c8148ecbcbf0898abce2377f68`; the
source-bound export has 79 components and its `resolved-components.json` hash
is `54d4842ac60e403a8963ab7d49ec2905ee66d176ce1974e77ac31652dd160543`.
`f2-shutdown-04/receipt.json` explicitly records simulation-only status and
`hardware_available: false`.

The 32-component `f2-shutdown-03` (`PowerEntryF2Shutdown`, source hash
`dcd9d65f77fad557b46a8bee92915782abec24cd5478c1a0583ade9927a40c69`) is an
earlier experiment, not an alternative current candidate. `source-build-06`
and `source-build-07` are the rejected 133-component passive-plus-supervisor
construction; their resolved export hashes are
`f8614dcde77610515c599116f391342b45126b38accc6acf4051f7039e03fe51` and
`0b29d45ccb966a0f4abf381860d388f3b552efab16fc4346debc237f3b6120d2`,
respectively. They must not be used as the integration source or as evidence
for this candidate.

The source-only count is **131 compiled component instances**:

```text
54 canonical passive RevA baseline
+79 standalone RevB protection graph
- 2 duplicated baseline gate parts (10 ohm gate resistor and 10 kohm gate pulldown)
=131
```

The off-board normally-closed F2, local VD film reservoir, and any new
connectors or headers are deliberately outside this count. They are named
interfaces in the contract below, not silently added components.

## Physical/net integration map

Uppercase functional labels below describe roles. The companion JSON now uses
the actual exported names: `local_vd`, `logic5`, `hot_arm`, `pwm`, `gate`,
`enable_good` and `PFC_BUS_MINUS`. Controller feedback is on `local_vd`;
the bank node feeds the separate VB protection detector.

The candidate is formed by copying the corrected 54-part passive source and
instantiating the exact RevB module. The retained root passive source hash is
`dd31c0addd5a5a5764955efca44d50d6fe89747f88c937e4c127398349b701d8`.
The corrected-clamp donor used by the review candidate is a separate source
identity, `4d63a25896e3bd3ed9cb242c2d074a225de71acdb3351bfcbae24b2f73c6fdbb`;
it does not rewrite the retained root source.

| RevB port or node | Candidate connection | Boundary and required behavior |
|---|---|---|
| `vd` | `d_boost.K` (diode cathode) -> named `LOCAL_VD`; `vd_div` sees LOCAL_VD | Diode-side node, before off-board F2. A local film capacitor is an external/uninstalled reservoir. |
| `vb` | `hv_plus` / bulk-bank positive, downstream of F2 | Bulk node remains separate from LOCAL_VD. Do not short the two in the source graph. |
| `aux` | passive `aux_15v` | HOT-referenced auxiliary rail; `aux_15v_return` remains tied to `control_gnd`/`hv_minus`. |
| `gnd` | passive `control_gnd` | HOT return only; never a SELV/MCU bond. |
| `logic5` | new external HOT-referenced 5 V logic producer port | Required for RevB detector, supervisors, buffers and latch. Its producer is not present in the 54-part source. |
| `permit` | external `hot_permit` | Sequencing authority input. It does not prove F2 continuity and is not a substitute for ARM. |
| `arm` | new external HOT-referenced fresh-arm edge port | Must be a deliberate rising edge after qualification; no direct SELV/interlock assumption. |
| `pwm` | `pfc.GATE` | Existing controller PWM is isolated into RevB through `pwm_iso`; no synthetic fixed-duty source. |
| `gate` | RevB `gate_r`/`gate_off_r` outputs joined at `q_boost.G` | Retain one RevB 10 kohm gate pulldown. The existing baseline gate resistor/pulldown are removed as duplicates. |
| `enable_good` | drive the retained standby `r_permit_gate` input (the `q_permit` gate path) | Keeps the existing two-AO3400 standby topology while making RevB's qualified RUN/clear state the producer. |
| `health_ok`, `rails_ok`, `clear_ok`, `run`, `fault_clear_n` | named observation/test nets | Preserve as diagnostic nets; they do not become unreviewed external producers. |

The passive controller feedback top must follow LOCAL_VD in this candidate:
`r_vtop.p1` is connected to LOCAL_VD, while the bulk output, bank bleeders and
load remain on `hv_plus`/VB. This keeps controller feedback and independent VD
observation on the diode-side reservoir. It is a source integration decision,
not a claim that the off-board reservoir or F2 has been installed.

The physical F2 boundary is a normally-closed, off-board series element from
LOCAL_VD to VB (candidate Mersen A70QS50-14F plus holder remains a selection,
not a qualification). The source candidate must expose the two sides as named
ports and must not instantiate an ideal switch, trip actuator, or resettable
fuse. Continuity diagnosis, arc/clearing, interconnect withstand and residual
energy are external requirements. A healthy-closed F2 may be used as a SPICE
fixture condition only.

## Existing parts, replacements, and non-additions

The only count overlap credited in the 131 arithmetic is the baseline
`r_gate` (10 ohm) and `r_gate_pd` (10 kohm). RevB supplies `gate_r` and
`gate_off_r` (two 10 ohm output resistors) plus `gate_pd` (10 kohm). Do not
retain both copies or count a baseline direct gate path in parallel with RevB.

The existing `q_inhibit`, `q_permit`, their gate resistors, and the rest of the
standby topology remain. `q_permit` is now driven by `enable_good`; external
`hot_permit` goes to RevB `permit`. The existing passive controller, shunt,
bulk bank, bleeders, relay/NTC stage, and corrected current-sense clamp remain
owned by the 54-part source. The accepted clamp topology is reused from that
donor; its worker export graph hash is
`8b7f452b8a92f410140dfb75476115455f894aba550ea5541976a325cfa6da55`.
No second clamp or alternate polarity is introduced.

## Where the current SPICE fixture diverges from the compiled graph

`operating-matrix-07/accepted-baseline-11` is the current modeled normal
baseline, not a second circuit authority. Its `protection.inc` and
`standby.inc` are authored SPICE equivalents. The following differences must
remain explicit when materializing the source candidate:

* `cold.cir` uses `Sf2 vd vb ... SWF2` as an ideal healthy/open simulation
  switch and models `Clocal=19.8 uF` at VD. Neither device exists in the 79
  compiled RevB graph or in the 54-part source; these are fixture boundary
  models. No source integration may copy the ideal actuator.
* `protection.inc` collapses RevB's split `OUTH`/`OUTL` paths to one authored
  `Xdriver ... gate_cmd` and one `Rgate`. The compiled graph has separate
  `gate_r`, `gate_off_r`, and `gate_pd` physical pins. SPICE gate timing is
  therefore a functional equivalent, not physical-pin parity.
* The graph's `clear_ok` is the HCS21 second output
  (`health_ok & rails_ok & permit_safe & aux_fast_good`) and `enable_good` is
  an LVC AND of `run & clear_ok`. The fixture derives `health`, `clear`, and
  `enable_src` with behavioral sources and adds explicit logic5 thresholds.
  Those names and thresholds are useful probes, but do not prove the source
  graph has been integrated until the compiled candidate check passes.
* `standby.inc` is a nominal two-AO3400 model fed by `enable_good`; it is not
  part of RevB's 79-component graph. It represents the retained standby
  circuit and remains conditional on its stated model limits.
* The accepted baseline drives `logic5`, `aux15`, `permit`, and `arm` with
  ideal PWL sources. Those are stimuli for the controller integration
  experiment, not installed supply/control producers. `controller-integration-06`
  has the same boundary and explicitly leaves physical ARM/PERMIT producers
  open.

The accepted fixture hashes are retained in `integration-map.json`; the
fixture's 5.36 GB trace is not copied or required for this map.

## Materialization and bounded check

The source candidate has now been materialized under
`reference-revision-09/source-candidate` and its export reports 131 compiled
component instances. The standalone Rust checker worker owns the one bounded
static contract check; no second fixture is needed. It should consume the
source-bound export and assert:

1. exactly 131 compiled component instances (79 RevB + 54 baseline - the two replaced
   gate parts), with no `Sf2`/F2 actuator, local film component, or new header
   counted;
2. exact external mappings in the table above, including `d_boost.K -> vd`,
   `r_vtop.p1 -> vd`, `hv_plus -> vb`, `pfc.GATE -> pwm`, `gate -> q_boost.G`,
   and `enable_good -> q_permit` gate drive;
3. no baseline `r_gate`/`r_gate_pd` remains alongside RevB's gate resistors;
4. standalone RevB's source hash and 79-component export hash still match the
   authorities above.

This worker-owned static graph check closes the integration evidence gap. It is
not a SPICE pass, DRC result, thermal result, or
hardware qualification. Reuse the existing accepted `protection.inc`,
`standby.inc`, and corrected `clamp.inc` only for separately labeled model
checks; do not promote their ideal F2/local-reservoir behavior into source
connectivity evidence.
