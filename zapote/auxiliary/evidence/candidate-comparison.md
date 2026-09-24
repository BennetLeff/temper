# Auxiliary U2 candidate comparison — static feasibility only

2026-09-23. **Decision:** carry two HOT paths into a controlled bench comparison. Neither is selected for Rev38 construction. Keep a separate line-fed SELV study and a separately accepted inverter-bias output. No source, load waveform, cutoff, PCB or powered response is accepted by this record.

## Fixed source snapshot

The active Rev38 checkout was read only. Its HEAD at the snapshot was `7c2bc6d4748731918d7bfb7f4754e6c20ced266c`; the following saved files were uncommitted and must be treated as provisional:

| File in `zapote/power-entry/passive-reva/protection/interface-integration-38/` | SHA-256 of saved bytes |
| --- | --- |
| `AUX-WINDOW.md` | `d81eadc8f92dbaeabe84d6d1a7a3b43abf55aa784c87687ada087ecedaddb353` |
| `AUX-OVP-WINDOW.md` | `cb990b20d9f7baeb20c233b23534f592db15ad4890b587346b74e3d7cb762176` |
| `AUX-SOURCE-CANDIDATE.md` | `de918fea40fb5ba1d864d752ec3e00257fa26492eeb82a7237c9d78cf799c417` |
| `elec/src/power_entry_integrated_38.ato` | `f9041f342516f6f7a2a1c6a869463841eceb6b33ee1baf6d91846bad85c765b1` |

That source proposal itself says the HOT producer is not joined. The worktree may have changed since these hashes; remeasure the saved files and revise this comparison rather than importing a later claim silently. The isolated branch's committed `AUX-WINDOW.md` also gives the ~41.50 mA incomplete relay/passive screen. `rail-ledger.md` traces its six branches. Manufacturer values below are cited directly; vendor typical and specified fixture values retain those qualifiers.

## HOT source comparison

Both paths take AC **after F1/CMC, before the main NTC/bypass**, so their input can exist before PFC RUN. Neither has a constructed AUX branch fuse, conductor, module footprint or inrush coordination. Both propose an LTC4368-2 disconnect with external back-to-back MOSFETs and shunt, followed by TPS54202 producing `HOT_LOGIC5` from `AUX_PROTECTED`. The cutoff must have no alternate path. The LTC4368 controller supplies threshold detection, not an output-peak clamp: its UV/OV gate turn-off data use a 2.2 nF gate fixture, and its recovery includes a 32 ms delay; downstream capacitance, real FETs and load determine the actual rail waveform ([ADI datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/ltc4368.pdf)). TPS54202 is a 4.5–28 V, 2 A buck with 5 ms internal soft start, but its 2 A output rating does not specify Rev38 input current or startup charge ([TI datasheet](https://www.ti.com/lit/ds/symlink/tps54202.pdf)).

| Path | Manufacturer facts / static result | Advantage | Main rejection risks and unbounded inputs |
| --- | --- | --- | --- |
| **H1 direct:** IRM-20-15 → LTC4368-2 → protected AUX → HOT logic5 buck | [Mean Well IRM-20](https://www.meanwell.com/Upload/PDF/IRM-20/IRM-20-SPEC.PDF): 15 V, 1.4 A/21 W rated at stated conditions, ±2.5% voltage tolerance, 200 mVpp ripple in its 20 MHz/0.1 µF+47 µF fixture; 85–305 Vac, 115–160% overload with automatic hiccup, 17.25–20.25 V **internal OVP trigger**, not an output peak. Treating the *entire* 200 mVpp as adverse on either end, plus ±0.03%/°C over 25→50 °C, yields conditional `14.3125–15.6875 V` raw at 50 °C. Only **62.5 mV** remains to the protected lower limit of 14.25 V before FET/shunt/cable drop. | One conversion before cutoff; no 24→15 V buck loss/startup mode. | Unknown actual local temperature and thermal derating, raw output transient, path drop at complete load, output peak after failure, source hiccup interaction, capacitor recharge. A larger nameplate current cannot widen the 62.5 mV voltage margin. |
| **H2 regulated:** IRM-20-24 → LMR36015FBRNXT buck nominal 15 V → LTC4368-2 → protected AUX → HOT logic5 buck | [Mean Well IRM-20](https://www.meanwell.com/Upload/PDF/IRM-20/IRM-20-SPEC.PDF): 24 V, 0.9 A/21.6 W at stated conditions. [TI LMR36015](https://www.ti.com/lit/ds/symlink/lmr36015.pdf): 4.2–60 V, 1.5 A; exact FBRNXT is adjustable 1 MHz forced PWM. `VFB=0.985–1.015 V` at its stated electrical fixture. An **ideal feedback-only** 14:1 ratio with independent ±0.1% resistors gives `14.74745–15.25345 V`, about **497 mV** either side of the normal AUX window before all other errors. | More static headroom for cutoff/cable drop, conditional on complete buck design. | Regulator output line/load/ripple/startup/feedback-fault waveform, inductor/capacitor/thermal selection, EMI, PG pin's 18 V recommended ceiling, raw 24 V surge and extra conversion failure mode. The ideal feedback result is not a protected rail guarantee. |

The current Rev38 [AUX OVP screen](../../power-entry/passive-reva/protection/interface-integration-38/AUX-OVP-WINDOW.md) mathematically rejects the ±1% TPS26601 divider for the stated 15.75 V normal high / 18.0 V provisional ceiling. Its LTC4368 example gives a larger *static input-threshold* interval but does not bound the protected output after a source/buck failure. The **18.0 V figure remains provisional**; choose the actual allowable driver VDD from all relevant device/system limits before calling a cutoff threshold sufficient.

No current acceptance follows from the source nameplates. The Rev38 41.50 mA relay/passive screen leaves out the UCC28180, UCC27624 quiescent and `Qg × fSW`, HOT logic5 load and efficiency, all startup/capacitor currents and real board temperatures. The 8 mA UCC28180 figure has a 15 V/4.7 nF test fixture. No guaranteed maximum for the actual STW gate charge at 15 V was found in the cited Rev38 evidence. Current-limit shunt selection and branch ampacity require the complete pulse and steady envelope.

## SELV and inverter-bias comparison

The 390 V Rev38 topology has no accepted ~170 V half-bus supply input. The full-board `AuxSupply` from `elec/src/modules.ato` must therefore not be copied with its old DC input. Its output joins SELV `+15V`/`GND`, then the LMR51430 3V3 converter and historical loads. The accepted standalone interlock instead explicitly accepts 3.135–3.465 V and still lacks `SENSOR_LIVE` and AUX-fault producers. These are separate source requirements.

| Output candidate | Manufacturer source and fit | Decision gate |
| --- | --- | --- |
| **S1 SELV:** separate line-fed IRM-10-15 → SELV `+15V`, then reviewed 3V3 converter | [Mean Well IRM-10](https://www.meanwell.com/Upload/PDF/IRM-10/IRM-10-SPEC.PDF): 15 V, 0.67 A/10.05 W, ±2.5% tolerance, 200 mVpp ripple in specified fixture, 4.2 kVac input/output withstand rating. Separate AC branch before precharge removes the historical half-bus dependency. | Need complete SELV 15 V and 3V3 steady/start/stall coil/fan tally, module local thermal derating, new AC branch and PE/leakage/creepage review. A 4.2 kVac module rating alone does not qualify appliance insulation or the SELV-to-HOT signal crossings. Keep no conductive HOT0–SELV join. |
| **G1 inverter bias:** line-fed IRM-10-15 whose isolated output return is bonded to `HV_RETURN` | Same manufacturer rating, but a third separate source/AC branch. No J2 load envelope exists. The primary J5 3V3/`CTRL_GND` stays a distinct crossing. | Prove input-to-HV_RETURN insulation, installed spacing, output/gate charge and bootstrap-startup current, source brownout, and safe default-off at J1 PERMIT. Extra AC branches/inrush may make this impractical. Do not infer it can serve SELV simultaneously after its return is bonded to HV_RETURN. |
| **G2 inverter bias:** RECOM `R15P215S/P/X2` from a separately accepted SELV 15 V rail to `+15V_LS`/`HV_RETURN` | [RECOM RxxP2xx datasheet](https://recom-power.com/pdf/Econoline/RxxP2xx.pdf): 2 W, 15 V/133 mA class, ±10% input range, 6.4 kVdc isolation, `/X2` clearance >9 mm, `/P` continuous short protection option. It is **unregulated**: ±5% output accuracy at the specified fixture and 15 V-version load regulation is 10% **typical** from 10–100% load. | Reject as an **unregulated direct J2 source** until a guaranteed J2 voltage envelope is derived or a post-regulator is selected. Gate pulse/startup current could exceed 133 mA average or startup limits; 2 W is no substitute for charge/current waveform. Its DC withstand number must not be silently equated to an appliance AC insulation requirement. |

Cooling fan power is deliberately not added to S1 or G1. Current cooker cooling candidates use different 12 V fans and no selected rail or stall current. The historical 15 V/39 Ω fan path is a third, older assembly; selecting a fan changes the SELV load and potentially adds a 12 V regulator.

## Executable screen and interpretation

`hot_source_screen.rs` is a standalone Rust check with no new Python owner or repo-wide crate changes. Run:

```bash
rustc --edition=2021 --test zapote/auxiliary/evidence/hot_source_screen.rs -o /tmp/temper-hot-source-screen
/tmp/temper-hot-source-screen
rustc --edition=2021 zapote/auxiliary/evidence/hot_source_screen.rs -o /tmp/temper-hot-source-screen-cli
/tmp/temper-hot-source-screen-cli
```

Its adverse cases reject a source fed after RUN, a series drop consuming all 62.5 mV margin, an out-of-range temperature extrapolation, and missing complete load/startup/fault-peak inputs. It reproduces both conditional static H1 and feedback-only H2 arithmetic. It does **not** model LTC4368 output dynamics, HOT logic5 startup, hysteretic restart, FET SOA or insulation. Passing its tests proves the screen enforces its own declared inputs; it cannot turn an unknown waveform into a PASS.

**Next evidence needed to choose:** complete 15 V and 5 V worst steady/pulse/startup loads at one Rev38 revision; local module temperature and installed input/fuse design; orderable FET/shunt/dividers/caps; H1 and H2 source-to-UCC27624 VDD, HOT logic5, ENA, gate and switch-current captures during slow/fast OV, dropout, hiccup, cutoff recovery, repeated mains dip and output short; the SELV and J2 consumer/current envelopes; insulation, leakage and installed grounding. The Rev38 deliberate restart protocol, not a recovered supply, must authorize any re-arm.
