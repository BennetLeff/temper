# Coil winding to SELV/PE working voltage at the 28 A ceiling (COIL-SPEC row 12b, DECISIONS item 7)

> **ASSUMED / bounded calculation, pre-measurement.** Fundamental-harmonic tank current, ideal 0/Vbus switch nodes, no ringing, no bench data. Table values are the repo's transcription (`packages/temper-design-bundle/src/safety_value.rs` TABLE_17); the IEC text and IEC 60664-4 were not read. Study only: no board, DECISIONS or coil-spec file was edited.

**Rerun:** `python3 zapote/power-stage-120v/validation-results/08-manufacturing-package/native-21/owner-items/m6m10/coil-selv-28a/coil_selv_28a.py` (stdlib only, about 15 s, deterministic, writes `results.json` beside it, asserts the controls).

## Question

DECISIONS item 7 and row 12b of `05-resonant-tank-envelope/round5-coil-od210/COIL-SPEC-ELECTRICAL.md` record "RES_A / coil to SELV is **242 V rms / 640 V pk** working (ORACLE Q2)". They size the reinforced tank-to-SELV/PE insulation: creepage 8.0 mm (PD3, IIIa), clearance 3.0 mm, hipot 3000 V rms 1 min, PD < 10 pC at 1.5 x U_rp (960 V pk), production 3000 V 1 s. That number comes from the 22 A era. The design is now a 28 A ceiling (no-pan clamp 22 A, RMS trip 29.4 A). Do the 8 mm board rule and row 12b still hold?

## Where 242 V / 640 V came from

`ORACLE-ANSWER.md` Q2 (row "RES_A / coil_ret (T1 primary before relocation)") quotes the output of `tools/bus_voltage_sim.py::node_rms`; there is no other script. The method:

- **Reference.** Voltage of the resonant junction **RES_A to earth**. N at earth, SELV return bonded to PE (single point), so SELV = earth. The bridge gives HV_RET = min(v_line, 0), BUS_P = HV_RET + |v_line|, SW_A/SW_B toggle between them, and RES_A = SW_B + v_Cr. The result is symmetric in L and N.
- **Statistic.** Rms over a whole 60 Hz cycle (the repo's "line-cycle time RMS", which equals carrier-crest rms / sqrt 2), and the peak over the cycle.
- **Hand-entered inputs** (not computed anywhere): line 127 V +10 % = 139.7 V; bank-capacitor crest **442 V** (the 48 uH loaded coil at 127 V; 277 V for the 70 uH coil); tank current **in phase with the drive** (v_Cr = -Vcr cos(carrier phase)).
- **Meaning of the label.** It is the voltage of the old T1 primary node against its SELV secondary. Row 12b reuses it as the coil winding against SELV and PE parts. The winding spans SW_A (99 V rms, 198 V pk to earth) and RES_A, so RES_A bounds the winding at every instant (a point on the winding is a convex mix of the two end potentials, so its rms and peak cannot exceed the larger end's).

## Controls (asserted by the script)

| # | Control | Result |
|---|---|---|
| C1 | Oracle Q2 reproduced from its own inputs (this script's line-cycle integration) | 165 / 457, 220 / 582 and **242.1 V rms / 639.6 V pk** (the last at 139.7 V, 442 V; the first two at 127 V with 277 V and 402 V). Matches `tools/bus_voltage_sim.py` exactly (C1c). |
| C1b | Crest shortcut (rms = crest rms / sqrt 2, pk = crest pk) equals the explicit 60 Hz integral | within 0.3 V rms / 0.6 V pk |
| C2 | 442 V is the 22 A ceiling | 2 x 22 A crest x Xc(35 kHz, 0.45 uF) = 444.6 V, within 0.6 % of 442 V. "Consistent with", not "derived from": the oracle typed it in. |
| C3 | Earlier study's RES_A rows (`../coil-voltage-28a/results.json`, design-worst, rho 2.0) | 295.3 / 642.5 (22 A), 353.3 / 762.4 (28 A), 361.7 / 791.1 (29.4 A) reproduced exactly. RES_A to HV_RET at the line crest equals RES_A to earth. |

## Pass criterion (fixed before the results)

Working voltage is **RES_A to earth**, repo convention (line-cycle rms; U_rp = peak over the cycle). Normal use = a pan at up to 28 A, or no pan at the 22 A clamp. Faults (clamp failed at 28 A, RMS trip 29.4 A) are reported separately: per ORACLE Q3, transients and faults govern clearance and component ratings, not creepage.

- **(a) Board 8 mm HOT to SELV/PE rule** (D5, reinforced, provisional floor): holds iff the reinforced creepage for the normal-use rms working voltage is at most 8.0 mm. The repo's basis is IEC 60335-1 **Table 17** basic x 2 (cl. 29.2.3), PD3, group IIIa (not Table 18, which is functional insulation). Table 17 PD3 IIIa basic by band: 4.0 mm (>125-250 V), 6.3 (>250-400), 8.0 (>400-500), 10.0 (>500-800); reinforced 8.0 / 12.6 / 16.0 / 20.0. So the 8 mm rule holds only up to **250 V rms**. PD2 IIIa basic: 2.5 / 4.0 / 5.0 / 6.3, reinforced 5.0 / 8.0 / 10.0 / 12.6.
- **(b) Row 12b**: creepage 8.0 mm passes iff the same test passes; clearance 3.0 mm passes iff the recurring peak stays below the 2.5 kV step that sets it (ORACLE Q3, marked "verify"); the PD test level (960 V pk) passes iff it is at least 1.5 x U_rp.
- **(c) Hipot 3000 V rms 1 min**: passes iff it is at least the reinforced 3000 V rms level and its peak (4243 V) is at least the 4.0 kV reinforced impulse step. Neither depends on the working voltage in the repo's basis; the ratio to U_rp is reported.

## Method

Same tank model as `../coil-voltage-28a/coil_voltage_28a.py` (FHA, ZVS ratio 1.05, 35 kHz floor, 60 kHz top, bank 0.45 / 0.50 / 0.55 uF, lines 108 / 120 / 132 / 140 V, I_crest = 2 x I_rms), with the node potentials referenced to earth as above and the phase from the tank (`phi = atan2(wL - 1/wC, R)`), not zero.

- **No pan.** Unloaded coil, L 59.9 / 66.5 / 73.2 uH, R 0.168 / 0.25 ohm, frequency solved for the ceiling current.
- **With a pan (normal use).** Round-6 grid rows at 28 A (`round6-full-power/outputs/grid6-*-I28-*-cases.csv`, 135 cases for the L70 coil, 108 / 120 / 140 V lines, R_eq about 2 ohm and phase about 65 deg in the worst cases), with their own f, L_eq, R_eq, C and I_pk. The analytic loaded-L sweep (R_eq down to 0.5 ohm) is nearly unloaded and is used only in the fault envelope.
- **Fault envelope.** Worst of the unloaded and loaded equivalent-circuit sweeps at 28 A and 29.4 A, as the earlier study's design-worst row (C3).

## Results (RES_A to earth, bounds the coil winding; SW_A end is 99 V rms / 198 V pk)

| State | rms (line cycle) | peak = U_rp | crest rms | Reinforced creepage PD3 IIIa (line rms) | PD2 IIIa | PD3, crest-rms reading |
|---|---:|---:|---:|---:|---:|---:|
| **Control: 22 A as recorded (242 / 640)** | 242.1 | 639.6 | 452.3 | 8.0 mm | 5.0 | 16.0 |
| 22 A, no pan (clamp, normal use), phase modelled | 286.2 | 623.7 | 441.0 | **12.6 mm** | 8.0 | 16.0 |
| 22 A, pan, L70 / C050 grid (reference) | 253.8 | 566.3 | | 12.6 mm (knife-edge) | | |
| **28 A, pan, L70 coil (normal use)** | **297.0** | **655.5** | 463.5 | **12.6 mm** | 8.0 | 16.0 |
| 28 A, pan, any of L 70 / 80 / 90 uH | 314.1 | 690.4 | | 12.6 mm | 8.0 | 16.0 |
| **Normal-use envelope** | **297.0** | **655.5** | 463.5 | **12.6 mm** | 8.0 | 16.0 |
| 28 A, no pan, unloaded only (clamp failed, fault) | 353.0 | 761.3 | 538 | 12.6 mm | 8.0 | 20.0 |
| 28 A, envelope of all tank states (fault) | 353.3 | 762.4 | | 12.6 mm | 8.0 | |
| 29.4 A (RMS trip), envelope of all tank states (fault) | 361.7 | 791.1 | | 12.6 mm | 8.0 | |

Worst corners: no pan is the 140 V line, bank -10 % (0.45 uF), 35 kHz floor, coil 66.5-73 uH, R 0.168 ohm, phase 88 deg. The 28 A pan worst case is `d228_gap84-L70-C050-I28-pan180|aluminium_clad_multiply-high-140v` (INPUT_LIMITED, 27.0 A rms, 38.0 kHz, L_eq 52.8 uH, R_eq 1.98 ohm, 140 V). The 29.4 A envelope peak is a loaded corner (L 63 uH, R 2.0 ohm, 35.06 kHz).

**Why 242 V understated even the 22 A case.** The oracle assumed the tank current in phase with the drive (loaded, near resonance). With the phase the round-6 and unloaded models give (65 deg with a pan, 88 deg unloaded, above resonance), v_Cr is more nearly in phase with the SW_B step and the two add. That raises the rms (242 to 254-300 V at 22 A) much more than the peak (640 V stays close: 566-663 V at 22 A). Going from 22 A to 28 A then adds 5-17 % rms with a pan (299.6 to 314.1 V for any L, 253.8 to 297.0 V for the L70 grid) and 23 % unloaded (286.2 to 353.0 V).

## Verdicts

| Item | Verdict | Why |
|---|---|---|
| **(a) Board 8 mm HOT to SELV/PE rule** | **FAIL for RES_A at PD3 IIIa.** 8.0 mm holds only to 250 V rms; RES_A is 297 V rms (up to 314 V with any coil L) with a pan at 28 A and 286 V rms with no pan at the 22 A clamp. Needs **12.6 mm** (>250-400 V band), or 8.0 mm if the lab accepts PD2 for the RES_A copper. Every other HOT net is at most 140 V rms (switch nodes and rails 99 V rms / 198 V pk, 4.8 mm; mains inputs 140 V rms, 8.0 mm), so the 8.0 mm rule is fine for them. | Reading it as a rule on the whole board, 8.0 mm is right for all nets except RES_A. The committed evidence has one board-wide minimum (8.047 mm, `REVIEW-2026-10-08.md`), not a per-net RES_A-to-SELV/PE gap, so whether the board's RES_A copper already clears 12.6 mm is **open** (run the barrier gate for RES_A alone). |
| **(b1) Row 12b creepage 8.0 mm** | **FAIL at PD3** (needs 12.6 mm); passes only as PD2 (8.0 mm). | Same test as (a), applied to the coil assembly (winding to ferrite, carrier screws, NTC leads, PE brackets). |
| **(b2) Row 12b clearance 3.0 mm** | **PASS, unchanged.** | Set by the 4.0 kV reinforced impulse step (unverified, "verify" in ORACLE Q3), not by working voltage. U_rp 0.66-0.79 kV is far below the 2.5 kV step. IEC 60664-4 distances above 30 kHz remain unverified. |
| **(b3) PD < 10 pC at 1.5 x U_rp** | **FAIL as written.** 1.5 x 655.5 = **983 V pk** exceeds the 960 V in the row (and 1.5 x 791 = 1187 V pk at the 29.4 A trip envelope). The "raised" 1200 V pk becomes 1.83 x the normal-use U_rp, 1.52 x the trip-envelope U_rp. | U_rp is a peak, so it moved less than rms (+2.4 % at 28 A with a pan vs 640 V), but it crosses the recorded level. |
| **(c) Hipot 3000 V rms 1 min / 3000 V 1 s production** | **PASS, unchanged.** | 3000 V rms is 4243 V pk: 6.5 x U_rp at 28 A with a pan, 5.4 x the 791 V trip envelope, and above the 4.0 kV step. It tests 50/60 Hz only, not the 35-60 kHz stress. |
| Crest-rms reading (lab question) | Worse: 463 V (normal use) falls in the >400-500 V band, **16.0 mm** PD3 reinforced; 20.0 mm for the fault envelope. | The certifier question on the Table 18/17 voltage convention (DECISIONS 2026-10-08) now also covers row 12b. |

## Recommendation

Row 12b and DECISIONS item 7 should change. The 28 A design is not the cause alone: the oracle's phase assumption was already optimistic at 22 A. New numbers (pending the certifier):

1. **Row 12b working voltage:** "**297 V rms / 656 V peak** against SELV and PE parts in normal use (28 A with a pan, 22 A without; line-cycle rms, 33-60 kHz); up to **362 V rms / 791 V peak** with the clamp failed, up to the 29.4 A RMS trip". Round the headline to 300 V rms / 660 V pk if a round number is wanted (314 V / 690 V pk if any L of 70-90 uH variant is accepted).
2. **Row 12b creepage:** "reinforced creepage >= **12.6 mm** (PD3, material group IIIa, >250-400 V band); 8.0 mm only if the certifier accepts PD2 for the winding insulation system (potted or sealed)". Clearance **3.0 mm** unchanged (verify). Keep "IEC 60664-4 distances above 30 kHz where larger".
3. **Row 12b PD test:** "< 10 pC at 1.5 x U_rp; with U_rp = 790 V pk (trip envelope) this is **1.2 kV pk** (1187 V rounded up), raised first to 1.875 x U_rp = **1.5 kV pk**". If the lab insists on normal-use U_rp only, the floor is 1.5 x 656 = 983 V pk, so 960 V cannot stand either way. Test at 50/60 Hz and, if a source exists, about 40 kHz at the same peak.
4. **Row 12b hipot:** unchanged, 3000 V rms 1 min; production 3000 V 1 s.
5. **DECISIONS item 7, first bullet:** replace with "RES_A / coil to SELV and PE is **297 V rms / 656 V pk** in normal use at 28 A (up to 362 V rms / 791 V pk at the 29.4 A trip) (`coil-selv-28a/`, phase modelled); ORACLE Q2's 242 V rms / 640 V pk assumed in-phase tank current and is superseded for the coil. The 8.0 mm HOT/SELV/PE floor holds for nets at or below 250 V rms; RES_A and the coil winding need 12.6 mm at PD3 (8.0 mm at PD2)". Also fix the second-order text in the coil-spec sources table (line 293).
6. **Board follow-up (open):** run the barrier gate with a RES_A-specific floor of 12.6 mm (and 8.0 mm for the other nets); if RES_A copper or the J5 stud lies within 12.6 mm of SELV or PE, either move it, add a barrier, or take the PD2/coating route to the lab. Add to the certifier questions: PD2 for the coil winding insulation, and the voltage convention (line-cycle rms vs carrier-crest rms).
7. **Bench:** measure V(RES_A to PE) at 28 A with and without a pan before the coil RFQ is released; the unloaded phase is the sensitive input.

## Limits

- FHA current, ideal switch nodes; ngspice tank peaks run up to 5.8 % above FHA, switch-node ringing is not modelled, so peaks and PD levels are lower bounds on that count.
- The earth reference follows ORACLE Q2 (N at earth, bus = |v_line|). It is not valid for a bus elevated by returned tank energy, and the PE-open case roughly halves every difference (not governing for insulation).
- 60 Hz envelope: current amplitude proportional to the bus (fixed frequency), as in the repo.
- Table 17 PD2/PD3 values are the repo's transcription of an IS 302-1:2008 copy (see `safety_value.rs`), applied by band without interpolation. The standard text and IEC 60664-4 Table 2 were not read.
- The pan cases are the round-6 INPUT_LIMITED/TANK_LIMITED grid; a pan the grid does not contain could do worse. The unloaded point is bounded by the sweep, not measured.

## Files

- `coil_selv_28a.py`: script (controls, node model, sweeps, assessment).
- `results.json`: `controls`, `headline`, `pan_grid`, `sweep`, `assessment`, `recommended_row_12b`, `constants`.
