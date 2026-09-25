# Revision 16 protected-AUX capacitance census

Read-only census for `/Users/bennet/Desktop/temper/worktrees/power-entry` at
`5dde29ab3e2f1223c2d33c129ced2cf647238307`. No exact passive was selected and
no source or schematic was changed.

## Rail interpretation

The revision-15/16 LT4363 fixture calls the existing regulated 15 V input
`AUX_RAW` and its pass-device output `AUX_PROTECTED` (the protected AUX15
consumer rail). The supply candidate independently calls the upstream LDO
output `AUX15`/`aux15`; it specifies a 47 uF nominal LDO output on that rail
with an effective floor of 10 uF. That capacitor is upstream of the proposed
pass device and cannot satisfy the LT4363 source/output-capacitance condition.
The fixture itself states this explicitly in `interface-capture-16/README.md`
lines 26-38 and `interface-active-15/clamp/design.md` lines 47-52.

## Capacitances that are actually on the protected consumer rail

The following are the nominal values in the existing candidate that would be
downstream if the LT4363 output supplies the retained AUX consumers:

| item | nominal | evidence and interpretation |
|---|---:|---|
| LT4363 C4, protected output bulk | 220 uF / 50 V target | `interface-capture-16/capture.rs` lines 503-508; `clamp.kicad_sch` C4. This is a target, not an exact part or effective-value guarantee. |
| TPS54202 buck VIN decoupler | 10 uF | `controller-integration-06/supply/source/hot15_logic5_supply.ato` lines 145-148 and `source/required_caps.txt` line 5. It is connected to `aux15`; if this buck is downstream of the clamp, it is part of the protected-rail load. |
| PFC controller VCC bypass | 1 uF | `interface-defaults-11/source-candidate/elec/src/power_entry_pfc_control_candidate.ato` lines 341-342 and 444, 465-466 (`pfc.VCC ~ aux_15v`). This is a direct AUX input bypass. |
| UCC27511A driver HF bypass | 100 nF | `interface-defaults-11/source-candidate/elec/src/power_entry_f2_shutdown_revb.ato` lines 571-574 (`drv_bypass_hf.p1 ~ aux`). |
| UCC27511A driver local bulk bypass | 1 uF | same file lines 575-579 (`drv_bypass_bulk.p1 ~ aux`). |

These known direct-rail nominal values total **232.1 uF** (220 + 10 + 1 +
1 + 0.1). The older TPS7A4701 LDO output **47 uF** is upstream and excluded.
The LT4363 fixture's C1 100 nF is on `AUX_RAW` (pin-5 VCC bypass), while C2
100 nF is the timer and C3 1.5 uF is the gate-control capacitor; neither is a
protected-output load. Their locations and nets are in
`interface-capture-16/clamp-expected.tsv` lines 30-37 and
`capture.rs` lines 491-506.

The 22 uF TPS54202 output capacitor is on `LOGIC5`, and the 100 nF bootstrap
capacitor is between `BOOT` and `SW`, so neither is direct protected AUX15.
The reset fixture's eight 100 nF bypasses are on `SELV3V3` or `HOT_LOGIC5`
(`interface-capture-16/capture.rs` lines 847-860); they are not AUX15
capacitance. PFC compensation/filter capacitors (4.7 uF VCOMP, 220 nF,
2.7 nF, 1 nF, 680 pF, 47 pF) are connected to controller signal nodes, not
directly from AUX15 to ground (`power_entry_pfc_control_candidate.ato` lines
343-353 and 450-468), and therefore are not part of the direct rail sum.

## What can and cannot be bounded for the LT4363 10:1 rule

The LT4363 Rev C application text requires low-ESR bulk close to the MOSFET
source, at least 22 uF and at least ten times the downstream converter's
ceramic input-bypass capacitance. The captured requirement is recorded in
`interface-capture-16/README.md` lines 26-38 and `capture.rs` line 536.

From the retained source, the **nominal** direct-rail ceramic candidate is
10 uF (buck VIN) + 1 uF (PFC VCC) + 1 uF (driver bulk) + 0.1 uF (driver HF) =
**12.1 uF nominal**. This is the origin of the fixture's rounded “12 uF
hypothetical maximum” example. It is not a qualified maximum effective
capacitance: the source uses generic capacitors for the buck and does not
provide a common tolerance, DC-bias, temperature, aging, or frequency model.
The 1 uF PFC and driver values also need confirmation that their fitted
dielectrics are ceramic; the source gives values but not a complete assembly
specification for every item.

Therefore the only defensible current bound is conditional:

`Cbulk,effective,min >= max(22 uF, 10 * Cceramic,effective,max)`.

If later exact parts prove `Cceramic,effective,max <= 12 uF`, the bulk floor is
120 uF effective. A 220 uF nominal target could satisfy that floor, but this
cannot be asserted until each part's effective capacitance, ESR, temperature,
bias and aging are documented. Nominal ±20% must not be silently treated as a
temperature/DC-bias/end-of-life guarantee. The 300 uF total downstream limit
in the fixture is likewise a conditional startup allocation, not a measured
or vendor-qualified bound.

## TPS54202 startup interaction

The source EN divider is 820 kOhm over 100 kOhm (`hot15_logic5_supply.ato`
lines 131-148). Its arithmetic gives about 1.589 V at the 14.625 V low static
rail before the documented 1 uA bias allowance, and the source uses the TI
1.28 V maximum rising threshold in `rail_contract.txt` line 12. TI's current
TPS54202 Rev C datasheet reports EN rising 1.21 V min / 1.28 V max, EN falling
1.19 V typical, 0.7 uA EN input current and 1.55 uA hysteresis current
(§5.5, PDF lines 228-232). TI also specifies VIN UVLO rising 3.9–4.4 V and
falling 3.4–3.9 V (lines 223-227), internal soft-start **5 ms typical**
(lines 252-258 and 595-596), and recommends a ceramic input decoupler over
10 uF plus an optional 0.1 uF, rated above maximum input voltage (§7.2.3.1,
lines 743-748). EN begins operation once above threshold; it is not an
independent guarantee that the LT4363 has exited its low-voltage/current
foldback state.

Consequently the retained 820 kOhm/100 kOhm network can let the buck begin its
5 ms soft-start while the protected rail is still charging. The revision-16
screen already computes 129.700 mA for the conditional operating load plus
capacitive ramp against a 67.507 mA minimum foldback screen
(`interface-capture-16/capture-screen.csv` rows 6-10). That comparison is a
warning, not a pass/fail dynamic result: startup must hold the buck/load below
the foldback envelope or add a qualified sequencing gate. The 5 ms vendor
soft-start does not prove compatibility with the LT4363 current loop, 220 uF
bulk, source impedance, or load release.

## Open evidence needed before choosing parts

1. Freeze the list of every consumer physically downstream of C4 and confirm
   whether PFC VCC, driver bypasses and TPS54202 VIN are all fed through it.
2. Select exact capacitors and record voltage rating, tolerance, DC-bias,
   temperature/aging effective minimum and ESR; recompute both the 10:1 floor
   and 300 uF startup allocation.
3. Measure the actual EN/VIN/startup sequence with the LT4363 current limit,
   source impedance and all intended loads. Do not infer startup safety from
   the TPS54202's 5 ms typical soft-start.
