# Power-stage readiness — 2026-10-04

Execution follow-up: [D17 commutation evidence, exact capacitor limits and interlock ECO](closure-2026-10-04.md). This adds digital evidence; no physical measurement or operating-envelope release is claimed.

**Next deliverable: a characterized coil/bank and a bounded controller operating envelope for a few engineering prototypes to test. Production power and fault survival remain unqualified.** No assembled Temper hardware exists. Keep the current 120/127 V, 60 Hz, 15 A input target, approved exterior and hardware trip thresholds while collecting the missing evidence. The prototype cohort is the user's first milestone; it is not a production release.

## What is current

| Artifact | Identity and scope |
| --- | --- |
| Routed power board and decisions | `ps-oracle` remains commit `fda5ab9ece24ef1ee6f2317604c5ca73367d5201`; tracked files are clean (untracked `native-09/.history/` excluded). Native-18 has four single IPW65R018CFD7, 70 µH nominal coil assumption, 0.54 µF CDE bank, and 49.9 kΩ ±0.1% R9/R17 dead-time resistors. No later decision was found in this checkout. |
| HOT5 source candidate | This workstream starts at `dea4649ff466cf36b49a0523d8232c94c317b163`: 142 components / 88 nets. Native-18 has 135 / 83 and lacks the seven HOT5 parts. Its existing shunt and CT thresholds are unchanged. |
| Arithmetic screen | `docs/hardware/power-section-120v/coil_mc.rs`: first-harmonic, assumed cookware priors; corrected single-device loss and historical 45 A screen. Its percentages are not product yields or power guarantees. |
| Protection calculation | Task 02 round 3, authored 2026-09-27, source analysis last changed at `dae39a538bc057b7d8f78451343ac3e3e00e9a0a`. Recomputed here against both current source candidates; 24 BOM MPNs and 12 required net endpoint groups match in each. |
| Current protection follow-up | Current [D-17 brief](https://github.com/BennetLeff/temper/blob/fda5ab9ece24ef1ee6f2317604c5ca73367d5201/zapote/power-stage-120v/validation-results/01-switching-parasitics/round17/delegation/D17-protection-gate-off.md) carries the shunt finding forward, says native-18 dead time does not change the fault chain, and retains HOLD on threshold retuning. Its `out-D17/` result directory is absent. |

Full artifact hashes, corner results, assumptions and current-source checks are in [identity-and-threshold-check.json](identity-and-threshold-check.json). This identity check does not adopt every artifact from another worktree or merge it into this branch.

## The current numbers describe different things

| Quantity | Meaning | Consequence |
| --- | --- | --- |
| 15 A | Intended AC input-current limit; PF and waveform still need validation | Not a 15 A tank-current limit. At assumed PF 0.95, input real power is 1,710 W at 120 V and 1,809.75 W at 127 V before cooker losses; neither is delivered cooking power. |
| 37 A | Normal-current reference used by the CT design and sampled switching studies | Not an approved controller command, and sampled switching performance does not establish a continuous envelope. |
| 45 A | Historical comparative screen from the source comment | Overlaps the independent shunt band's low end. Retained to preserve model comparisons, explicitly unreleased. |
| 50.93–59.51 A | Older CT-only DC model | Its narrower assumptions cannot override the broader temperature/TCR result or the separate shunt detector. |
| 50.558–60.014 A | CT static band with temperature/TCR, rail, offset, bias and clamp terms | Conditional calculation with ideal 1:100 CT transfer. Frequency, phase, nonlinear behavior and gate-off overshoot still need evidence. |
| 38.438–85.551 A | Shunt static band at +85 °C board and **assumed +50 °C R5 self-heating** | Fails the existing 44 A minimum no-nuisance-trip criterion. Upper end is also a fault-energy concern. Neither endpoint is a measured threshold or complete bound on actual current. |
| 42 / 40.45 A | Actual-current ceilings explored by task 05 round 4 | Both leave 73/135 modeled cases above the static shunt minimum; neither was released as a controller command. |

The shunt is the hot-side DC return detector; the CT senses series tank current. Their waveforms differ during commutation, freewheel and faults. A static band overlap is a real coordination problem to investigate, **not proof that every 45 A tank peak causes a trip**. Resolve the actual R5 waveform, its filter and comparator timing; do not subtract the two scalar thresholds and claim a dynamic margin.

The shunt arithmetic was independently checked from KCL at both +85 °C extrema: `(Vref − Vnode)/R32 + (Vkelvin − Vnode)/R33 = 0`, with `Vnode = Vthreshold + offset + bias`, `I = −Vkelvin/R5`. It reproduces 38.438184 / 85.551033 A. The two full temperature-corner objects exactly match the stored task-02 result. The assumptions include R5 ±1%/250 ppm/°C, precision resistors ±0.1%/25 ppm/°C, comparator ±4 mV plus adverse bias, and reference 2.48–2.52 V. At +85 °C, the assumed shunt element is +135 °C; the separate D18 **local-ambient ≤100 °C** decision is not an element-temperature measurement or a replacement for this assumption. The −10 °C case remains outside the selected HOT5 regulator's specified range and is not qualified.

Live primary-source checks confirm that the [TLV3201 delay specification](https://www.ti.com/lit/ds/symlink/tlv3201.pdf) is conditioned on input overdrive and load (pp. 5–6), not an arbitrary slow-ramp guarantee. The [Vishay WSK2512 data](https://www.vishay.com/docs/30108/wsk2512.pdf) supplies the resistance/TCR and power-derating basis. These part documents do not establish Temper's total fault latency or survival.

## Operating-envelope choices to evaluate

These are proposed branches of the engineering work, not changes to product requirements.

| Choice | What to do next | Tradeoff / decision gate |
| --- | --- | --- |
| **A. Characterize the selected 70 µH / 0.54 µF construction first** | Build an unpowered coil/glass/ferrite fixture; measure selected cookware and request exact capacitor limits. Use results to solve controlled reduced-power points as well as requested full power. | Fastest path to finding whether the existing parts can serve the target. No guarantee of full power on intended cookware. Recommended immediate work; does not lower the target. |
| B. Optimize winding and resonant bank for the original target | Once A supplies real complex impedance, compare winding/bank variants in the same physical allocation, keeping current protection unchanged. Include 140 µH/22 kHz as one hypothesis, not a selection. | Can improve impedance matching but changes copper/ferrite loss, frequency, acoustic behavior, capacitor stress and physical fit. Re-measure each changed construction and rerun controller, thermal and fault analysis. |
| C. Accept a narrower cookware/power specification | Produce an explicit power-versus-cookware table from qualified measurements for owner review. | May retain current hardware but changes the product promise. No such change is authorized here. |
| D. Redesign protection/current sensing if proven necessary | Complete D-17 with the actual interlock and HOT5 chain; compare improved accuracy/gain or threshold network proposals against normal and fault requirements. | Board/controller redesign. Raising thresholds to recover model power is not an acceptable substitute for device-survival evidence. The existing hold remains. |

For each accepted operating point, enforce separately: AC input current, actual tank peak/RMS, actual R5 waveform/thermal stress, inductive commutation margin, measured switch stress, each capacitor's RMS/peak/temperature limits, and installed cooling. A controller command must reserve a documented allowance for measurement error, sampling/update delay, load steps and protection latency beneath the selected physical operating ceiling. **No defensible numeric command is available yet.**

The Monte Carlo percentages (14.8% at 114 V / 4.3% at 127 V for the selected point) remain comparative **45 A-screen** outputs, excluding the shunt dynamics above. Task 05's separate 1,710 W request is total modeled pan-plus-coil dissipation, not the same quantity as 1,710 W mains input or heat delivered into food. Keep `P_input`, `P_tank`, `P_pan` and calorimetric delivered power separate in every plot and requirement.

## Sequence and acceptance gates

1. **Cold characterization:** use [coil-characterization.md](coil-characterization.md) and its blank data tables. Freeze actual coil, ferrite, glass gap and cookware IDs. Produce raw calibrated impedance, uncertainty and repeatability evidence. Update priors from those samples; do not label a small sample as the cookware population.
2. **Parts and model reconciliation:** get written exact-part responses using [supplier-questions.md](supplier-questions.md). Re-solve waveform/current/power corners with selected bank limits and actual protection/control paths. Correlate small-signal measurements with later energized measurements before treating them as rated-power truth. A failure to meet the unchanged target triggers an explicit choice among A–D above.
3. **Prototype-design release:** PCB, controller/interlock and enclosure must share one revision manifest, include HOT5 supervision and the native-18 dead-time change, and supply an agreed protection/current limit and test access. Close D-17's missing fault timing, shorted-switch upstream interruption and returned-energy cases sufficiently for the qualified engineer's staged energization plan. The old numerical 1.0/1.3 µs shutdown sums are not guaranteed fault-to-current-extinction times. Cold-fabrication review is a separate gate from permission to energize.
4. **Powered engineering validation:** a qualified power-electronics engineer approves station, instrument isolation, energy/current limits and stage-specific abort thresholds before each stage. Measure current, VDS/VGS, tank voltage, every capacitor branch, fault-to-current-extinction, local temperatures and delivered fan flow. Cover startup, line phase/zero crossings, pan removal/offset, heat soak, low-power burst, no-pan, HOT5/V15/SELV loss, sensor faults and commanded shutdown. Hardware-fault procedures require their own controlled setup. No staged mains procedure is authorized by this document.
5. **Rated-power/production freeze:** every intended cookware/line/temperature point meets the approved product power definition, no normal nuisance trips, and all derated component and fault limits include uncertainty. Demonstrate D18 cooling in the integrated enclosure; retain 50 °C inlet, ≥20 CFM delivered, ≤0.15 °C/W sink and ≤1.0 °C/W per MOSFET interface allocations until changed through evidence. Then release matched source/BOM/PCB/control configuration, production test limits, calibration method, traceability, supplier process and the manufacturing qualification packet. Simulation and DRC alone cannot close this gate.

## Work completed here

- Replayed the existing static threshold calculation without writing to `ps-oracle`; independently checked shunt extrema and validated both frozen candidate input sets.
- Corrected the coil model's emitted qualification warning and its two design documents. Arithmetic, selected components and comparative rows remain unchanged; no new operating limit was invented.
- Prepared usable characterization tables and unsent supplier requests. No procurement, contact with suppliers, fabrication or physical measurement occurred.

Verification commands and outcomes are recorded in [verification.md](verification.md). Raw external PDFs are not added to this package.
