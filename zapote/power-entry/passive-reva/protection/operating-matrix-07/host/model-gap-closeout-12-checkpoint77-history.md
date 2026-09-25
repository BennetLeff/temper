# Model-gap closeout audit (simulation-only)

> Historical checkpoint-12 audit. The nominal nine-point grid is now
> [complete](operating-envelope-checkpoint-53.md), the proposed clamp-law
> sensitivity fixtures were completed in
> [limiting-envelope-13](../clamp/limiting-envelope-13/parent-review.json), and
> [saved-pin diagnostic50](../faults/saved-pin-observability-50/full-F2-CREST38/parent-observability-review.md)
> adds model-only observations. Those results do not close the selected-part
> guarantees described below. Use the [current evidence register](campaign-evidence-register-28.md)
> for present campaign status; future-tense suggestions in this historical body
> are not authorization to repeat completed experiments.

Date: 2026-09-21 (UTC)  
Scope: the accepted modeled baseline, the forthcoming nominal line/load grid,
and the planned bounded fault cases. This note does not change a circuit,
accept a new part model, or add a hardware gate.

## Decision in one sentence

The accepted receipt establishes a versioned, event-aware result for one exact
cold-start model. A nominal grid and bounded fault runs can extend that result
to the declared **modeled** operating envelope, but they cannot turn the
selected Vishay BAV23C-E3-08, UCC28180D, STW65N65DM2AG, generic diodes, or
ideal F2 switch into manufacturer or hardware qualifications. The remaining
gaps are identified below rather than hidden behind nominal-model numbers.

## Evidence classes

| Evidence class | What it can support here | What it cannot support |
| --- | --- | --- |
| Manufacturer guaranteed limit | A published absolute/rated bound, under its stated test condition | A different current, temperature, pulse, assembly, or dynamic operating point |
| Typical curve/value | A plausibility or sensitivity point | Lot, temperature, tolerance, SOA, or worst-case bound |
| Assumed SPICE model | Behavior of the declared netlist/model | Silicon behavior, losses, thermal margin, protection clearing, or production tolerance |
| Accepted modeled metric | The exact source-hashed model and declared numerical policy passed its screens | Hardware survival, fuse interruption, or total-energy closure |

The last row is the scope of `accepted-baseline-11/acceptance.json`: it is
`ACCEPTED_MODELED_NORMAL_SCREEN_BASELINE`, while the legacy strictly increasing
checker remains `REJECTED_NONINCREASING_TIME`. Its 68.13 W residual is retained
as modeled loss/accounting, not measured heat or proof of energy closure.

## Current clamp (selected Vishay BAV23C-E3-08)

The retained primary Vishay document is
`clamp/datasheet-audit/bav23c.pdf` (BAV23C document 86374), SHA-256
`b05e055b9bddac73647119b108d61535c80f89b2ad12087d4cee28bb18106d96`, from
<https://www.vishay.com/docs/86374/bav23c.pdf>.
It guarantees, at the printed conditions, 250 V VRRM, 200 mA average forward
rectified current, 400 mA continuous forward current, 625 mA repetitive peak
forward current, 300 mW on the recommended FR-4 footprint, and maximum VF of
1.0 V at 100 mA / 25 °C and 1.25 V at 200 mA / 25 °C. The operating range is
-55 to +150 °C. Those facts do **not** provide a low-current VF(min)/VF(max)
envelope over the UCC28180's -40 to +125 °C electrical range.

The page-3 forward-current plot is typical, not a production limit. Near
0.438 V it reads only as a coarse order-of-magnitude indication: tens of µA at
25 °C, a few hundred µA to roughly 1 mA near 100 °C, and roughly 1 to several
mA near 150 °C. The existing assumed model's 25 °C current at that point is
70.2 nA, so the model is not vendor-anchored for PCL loading. The 1 µA diode
current and 2 mV ISENSE-shift checks are deliberately chosen screens; neither
is a TI or Vishay requirement.

TI's retained `clamp/datasheet-audit/UCC28180.pdf` (SLUSBQ5D, SHA-256
`e1e1588c6854b43742a667c76df26f06d9ac51231f0176c43b2a46b63c1b00be`) from
<https://www.ti.com/lit/ds/symlink/ucc28180.pdf> says ISENSE should be 0 to -1.1 V, the external
diode VF must be greater than the maximum PCL magnitude (0.438 V) and less
than 1.1 V over temperature/component variation, and the 220 ohm series path
with 1000 pF filter is the reference arrangement (section 8.3.14 and
9.2.2.9). The EVM uses 221 ohm/1000 pF and no populated clamp diode (the
retained report links the [EVM guide](https://www.ti.com/lit/ug/sluuat3b/sluuat3b.pdf)
and [TI E2E discussion](https://e2e.ti.com/support/power-management-group/power-management/f/power-management-forum/877587/ucc28180-isense-pin-diode-requirement)).
This is a useful standard placement, not evidence that BAV23C is qualified.
The E2E discussion also calls out the need for a VF-versus-temperature curve;
its “many customers use BAV23C” wording is application guidance, not a
guarantee.

The existing **dedicated clamp fixtures** (`clamp/clamp_pcl.cir`,
`clamp/clamp_temperature.cir`, and the Rust checker
`clamp/clamp_checks.rs`) establish polarity and quantify the assumed-model
loading. Their retained output `clamp/host-rerun/checks.txt` records the chosen
1 µA/2 mV screen passing at -20/25 °C but failing at 85/125 °C; that is a
screen result, not a Vishay limit. The normal baseline/grid trace does not
save a diode-current waveform or a clamp-specific error metric, so it cannot
be used to claim that the controller pin stayed within a clamp screen. The
fixtures and their outputs must be cited separately for any such model
statement. Neither fixture nor grid supports “the selected Vishay part does
not disturb PCL,” an ISENSE tolerance claim, or a pulse/SOA/thermal claim.

The useful next simulation is a small limiting-case fixture, not another full
plant run: retain 220 ohm and exercise (a) open clamp, (b) ideal hard clamp,
and (c) a swept unknown VF/I envelope at the PCL-max point (-0.438 V), the TI
-1.1 V pin limit, and the declared -5 V shunt excursion. Record controller
pin voltage, resistor current, clamp current, and pulse energy/duration. A
guaranteed pass/fail statement requires a selected-part low-current
VF-versus-temperature/tolerance curve or assembled characterization; absent
that evidence, the sweep is sensitivity information only.

The retained Diodes Inc BAV23C text model (`aa03e4db...`, alternative vendor)
is useful for sensitivity, but is not evidence for the selected Vishay die.
Its approximately +94% PCL-max current shift at 125 °C and approximately
19 mA at a -5 V shunt with 220 ohm are model results, not worst-case claims.

## Controller (selected UCC28180D)

The TI datasheet facts retained in
`clamp/datasheet-audit/report.md` (local PDF path and URL above) are
PCL min/typ/max -0.345/-0.400/-0.438 V, ISENSE absolute voltage -24 to +7 V,
and ISENSE input current -1 to +1 mA, with electrical characteristics over
-40 to +125 °C. The latter two are damage limits, not sensing-error budgets.

TI publishes a TINA-TI transient asset (`SLUM528.ZIP`) and a PSpice average
asset (`SLUM423.ZIP`), but the retained archives are encrypted/TINA- or
PSpice-managed and are not open ngspice transient netlists. The exact archive
hashes and inspection are recorded in
`host/ucc28180-vendor-model-availability.md`. `ucc28180-pwm-latch.inc` is
therefore a host-authored functional surrogate. Its nominal 0.72 V ICOMP
offset, clipping, amplifier current, reset, and timing assumptions are useful
fixture parameters but not silicon tolerance or propagation guarantees.

After the nominal grid/faults, the defensible statement is: **the authored
controller model produced the declared regulation, current, and modeled fault
logic responses under the tested source-hashed cases.** The normal grid does
not by itself establish a clamp-pin response, because its saved contract has
no diode-current/clamp-error channel; a dedicated controller/clamp fixture is
required for that statement. None of this is evidence of TI startup/restart
behavior, hot/cold propagation, PCL accuracy, or compensation stability in
silicon.

The next bounded controller-only test is a corner fixture around PCL/SOC,
UVLO/OVP, blanking, and latch reset, with each corner tied to a cited TI limit
or explicitly labelled an engineering sensitivity. Do not promote arbitrary
corner widths into requirements. Running the official model in its supported
TINA/PSpice environment and correlating named waveforms is an optional model
comparison; it does not retroactively make the ngspice surrogate a vendor
model.

## Power switch, boost diodes, and bridge

The selected MOSFET is STW65N65DM2AG, but the accepted `cold.cir` uses the
generic `STWMOS` model (`VTO=4`, `KP=4`, 1 mΩ source/drain) plus idealized
capacitances. The retained device audit records the manufacturer's rated
650 V VDS, 60 A at case 25 °C / 38 A at case 100 °C, and pulse/SOA examples;
its typical Ciss/Coss/Crss, Qg, and switching times are test-condition values,
not maxima. The exact ST PSpice ZIP is listed by ST but its bytes, encryption,
pin order, temperature coverage, and ngspice compatibility were not retained
or verified. The source URL and exact-model caveat are retained in
`protection/f2-shutdown-03/device-audit.md`; the listed primary links are the
[ST product page](https://www.st.com/en/power-transistors/stw65n65dm2ag.html)
and [exact PSpice ZIP](https://www.st.com/resource/en/spice_model/stw65n65dm2ag_spice.zip).
Consequently a grid/fault receipt can report modeled VDS, gate,
current, and switching screens only; it cannot report MOSFET loss, SOA,
avalanche, or thermal qualification.

Likewise `DBRIDGE`, `DBOOST`, and `DBODY` in `cold.cir` are generic diode models,
not exact GBJ2510-F or a retained exact boost-diode model. Their forward drop,
capacitance, reverse recovery, and pulse behavior are therefore model inputs.
The grid/faults establish modeled current/voltage paths only. A useful next
step, if the exact model/data is obtained, is a short temperature/parasitic/
reverse-recovery sensitivity replay; the current generic sweep must not be
labelled worst case.

## F2, driver, standby MOS, and passive energy storage

`SWF2` is an ideal controlled switch with scripted opening. It has no melting,
arc, DC-clearing, restrike, or I²t behavior, and the passive CAD still lacks
the physical VD/F2/VB split. A fault receipt can show topology energy and
gate-off timing in this model, but cannot claim fuse interruption or safe
post-open discharge.

The driver and standby paths are authored functional models; `AO3400_NOM` is a
nominal standby MOS model. The bridge, 19.8 µF local capacitor, 2240 µF bulk
capacitor, and 180 µH inductor are likewise nominal elements without measured
ESR/ESL/tolerance distributions. These are acceptable declared inputs for a
modeled envelope, not hardware margins.

## What the next receipts can and cannot close

1. **Nominal line/load grid:** extends regulation/current/voltage/frequency
   and event-aware numerical claims to the predeclared model points, provided
   every case has its own complete trace, source hashes, all-row extrema, and
   equal-time audit. It does not close component or fuse gaps.
2. **Bounded fault cases:** characterize shutdown ordering, modeled stress,
   and the ideal-switch topology under source-bound injection timing. They do
   not establish interruption, arc extinction, device survival, or thermal
   performance.
3. **Clamp limiting fixtures:** quantify sensitivity to the missing VF/I
   envelope. They become a qualification result only after selected-part
   bounds or measurements are supplied.
4. **Exact vendor models/data:** if retained and simulator-checked, permit a
   better model-correlation claim for that part. They still do not replace
   assembled parasitic, temperature, and protection measurements.

This closes the documentation gap without inventing a new acceptance gate:
the current work may proceed as explicitly scoped modeled evidence, while the
selected-part, controller-silicon, fuse, thermal, and hardware limits remain
named unknowns.

## Selected-inductor clarification — checkpoint73

The [manufacturer audit](inductor-manufacturer-audit-72/parent-disposition.md)
and [retrieved vendor-model review](inductor-manufacturer-audit-72/vendor-model-parent-review-73.md)
now bind exact Würth760800301 data and original files. The circuit's180µH
matches nominal inductance, and its20mΩ winding resistor matches the datasheet
maximum at20°C. Neither captures DC-bias inductance or thermal behavior. The
published43A saturation value is typical;24.5A is tied to40K temperature rise,
not an instantaneous peak screen. Whole-startup normal inductor peaks span
25.067–36.871A; these establish neither thermal failure nor guaranteed saturation
margin. The original vendor model is itself linear, with fixed loss/parasitic
elements, and does not close this gap. It has not been adopted or executed.
The [model inventory](inductor-model-inventory-72.json) binds each peak receipt.
