# Reconciling PCB design advice for Temper

This decision guide connects the six source rubrics. It is an original synthesis for a later review of the pinned native-21 stage15b full bridge; it does not prescribe a layout change or report a board failure. The IDs below point to the detailed questions, evidence requirements, scoring anchors and primary-source locators in each resource review.

## Decisions that require several sources together

| Decision | Useful starting advice | Conditions that can reverse the choice | Evidence to decide | Related criteria |
|---|---|---|---|---|
| Continuous return plane or separate copper regions | Preserve a nearby uninterrupted return for fast signals within their electrical domain; partition noisy and sensitive functions by placement and routing. | Actual hot-to-SELV isolation forbids conductive continuity. A shared power-current bottleneck can contaminate sensing despite a nominally continuous plane. | Domain map, current-return overlays, required isolation construction, shared-impedance model and victim measurements. | [BP-12–14, BP-28](bogatin-practical.md), [OTT-04–08, OTT-22](ott-emc.md), [SI-07–08](bogatin-sipi.md) |
| More switch-node copper or less | Minimize the capacitance of high-dv/dt copper to susceptible circuits, chassis and cables. | The switch terminal also needs a viable current and thermal path; removing copper can create heating or increase inductance. | Switching state map, thermal model, capacitance/displacement-current estimate and transient/EMC measurements on alternatives. | [SI-06, SI-28–29](bogatin-sipi.md), [OTT-03, OTT-21](ott-emc.md), [AN139-01–06](an139.md) |
| Shorter route or smaller loop | Optimize the complete outgoing-and-return geometry, including capacitor access and layer transitions. | A short visible trace over a reference gap can have a longer return and higher coupling than a slightly longer route over a continuous legal reference. | Actual copper and stackup; state-by-state loops; loop-inductance estimate; voltage at the affected device pins. | [BP-11–14](bogatin-practical.md), [SI-05–09](bogatin-sipi.md), [OTT-01, OTT-04–06](ott-emc.md) |
| Wider power conductors or additional vias | Reduce resistance and heating throughout the path, including narrow pad entries and transitions. | Via barrels, plating tolerances, unequal parallel paths, plane perforation and high-frequency inductance can dominate. Extra copper can also enlarge a switched field source. | RMS and transient currents, minimum cross sections, fabricated copper/plating tolerances, hot resistance and waveform/temperature tests. | [BP-08–11](bogatin-practical.md), [SI-06, SI-09, SI-28](bogatin-sipi.md) |
| Slower gate edges or faster switching | Damping and reduced slew can reduce overshoot and coupled interference. | Longer transition intervals can raise switching losses, alter dead-time behavior and change the operating stress distribution. | Gate and drain waveforms, driver supply behavior, switching-loss model, fault/timing requirements and hot-case operation. | [SI-01, SI-19](bogatin-sipi.md), [OTT-11–12](ott-emc.md), [power-device criteria](art-of-electronics.md) |
| More capacitance or lower connection inductance | Place pulse supply close to the active pins and minimize its installed current loop. | Nominal capacitance may shrink under bias or heat; adding unlike low-loss capacitors can create antiresonance; bulk, resonant and snubber capacitors have different duties. | Exact-part effective-C and impedance curves, mounted parasitics, load spectrum, rail/current waveforms and capacitor temperature. | [BP-04, BP-16–18](bogatin-practical.md), [SI-10–15](bogatin-sipi.md), [OTT-13–15](ott-emc.md) |
| Ferrite bead, common-mode choke or differential filter | Identify the disturbance mode and choose a component whose installed impedance addresses that mechanism. | A single impedance-at-frequency number or a 50-ohm insertion-loss curve may not predict attenuation with the actual source/load. Bias, temperature, parasitic bypass and resonance may reverse the benefit. | Mode-separated spectra, actual terminal impedance, bias/temperature curves, physical filter layout and before/after transients/emissions. | [MAG-03–06, MAG-13–21](trilogy-magnetics.md), [OTT-16–20](ott-emc.md), [BP-18](bogatin-practical.md) |
| Smaller filter or larger magnetic part | Use sufficient inductance/impedance and acceptable loss for the actual waveform. | Thermal current and saturation current measure different constraints. CMC cancellation does not remove winding heating, leakage-field effects or imbalance/fault behavior. | Exact winding currents, loss/bias curves, thermal limits, core flux and installed temperature, not merely an ampere number. | [MAG-05–12, MAG-15](trilogy-magnetics.md), [OTT-20](ott-emc.md) |
| Greater transformer coupling or less parasitic capacitance | Limit leakage when the intended transfer or switching circuit requires it. | Interleaving may increase interwinding capacitance and common-mode current across an isolation boundary. | Measured leakage, capacitance, waveform distortion, CM current and actual isolation construction. | [MAG-25–27](trilogy-magnetics.md), [OTT-21–23](ott-emc.md), [SI-24, SI-29](bogatin-sipi.md) |
| More sensor filtering or faster fault response | Reject interference at the correct input/boundary and keep signal plus reference compact. | Extra delay, phase shift, clamp distortion or reduced bandwidth can obscure a real fault or corrupt control. | Input error budget, threshold and latency requirements, aggressor/victim captures, fault pulses and complete interruption timing. | [OTT-12, OTT-27–29](ott-emc.md), [SI-21, SI-25](bogatin-sipi.md), [MAG-25–26](trilogy-magnetics.md), [analog/protection criteria](art-of-electronics.md) |
| Thermal relief or direct pad connection | Choose joint geometry that the assembly process can solder repeatably. | A relief may add unacceptable resistance/inductance; a direct connection may sink so much heat that the joint is unreliable or difficult to service. | Assembler process, copper geometry, reflow/repair trials, joint inspection and electrical/thermal performance. | [BP-07, BP-21](bogatin-practical.md), [assembly and thermal criteria](art-of-electronics.md) |
| Consolidated BOM or role-specific parts | Reduce unnecessary unique parts and qualify alternatives to simplify procurement and assembly. | Different voltage, pulse, safety, parasitic, thermal and mechanical duties can make nominally similar parts incompatible. | Role-by-role exact-MPN comparison, current datasheets, footprint/pinout, stress and operating tests, supplier/lifecycle records. | [BP-03–07](bogatin-practical.md), [MAG-11–12](trilogy-magnetics.md), [BOM criteria](art-of-electronics.md) |

These are conditional trade-offs, not equal-weight preferences. An applicable insulation or device-stress requirement constrains the set of acceptable choices; cost, compactness and appearance select among those choices. State the requirement and mechanism first so that an attractive compromise does not silently erase a constraint.

## Five shortcuts to reject during the eventual review

**The switching frequency is low, so the layout is slow.** Use actual voltage/current edge times and ringing spectra to judge interconnect and coupling risk. The fundamental tank frequency and the bandwidth of a switching transition answer different questions. [SI-01, SI-16](bogatin-sipi.md); [OTT-11](ott-emc.md).

**The net says ground or Kelvin, so its potential is fixed.** Trace the actual return currents and impedance. The pinned source specifically states that `OCP_KELVIN_P` carries defined auxiliary/protection current. Model those loads, the shared conductors and the sensitive node-to-node voltage before proposing a topology change. [BP-10–12](bogatin-practical.md); [SI-07](bogatin-sipi.md); [OTT-22](ott-emc.md). The source header is project context, not a book claim.

**The coil's inductance matches a reference example, so the tank is qualified.** Require the actual coil-plus-pan impedance over the operating range, including loss, position, temperature and drive conditions. Wireless-charging or generic converter examples may explain a mechanism without representing the cooker's scale, waveform or workpiece. [MAG-22–24](trilogy-magnetics.md).

**The model agrees with another model, so the mechanism is proven.** Agreement can preserve the same missing parasitic, wrong convention or operating assumption. Use an external instrument or independently established boundary where the claim requires it, and record measurement uncertainty. [BP-23, BP-26](bogatin-practical.md); [SI-03–04, SI-26–27](bogatin-sipi.md); [OTT-32–35](ott-emc.md).

**The rule checker is green, so the assembled product has margin.** Record what each rule actually checks. Copper spacing, connectivity, output consistency, solderability, thermal performance, switching behavior, EMC and insulation verification are distinct kinds of evidence. [BP-23, BP-27–28](bogatin-practical.md); [MAG-11, MAG-29](trilogy-magnetics.md).

## Convert advice into a falsifiable comparison

For each proposed change, keep the operating conditions fixed or explicitly account for their differences. Compare the original and modified exact identities, not vaguely named revisions. The decision should have this form:

> At the stated operating condition, the identified current/coupling/thermal mechanism consumes the defined margin. The proposed change is expected to improve this quantity by this mechanism, with these adverse effects. These calculations and measurements will determine whether the improvement and remaining margins are real.

The claim can then fail cleanly: perhaps an expected loop-inductance reduction does not occur, an EMI peak moves into a more sensitive band, or a cooler part introduces greater sensing error. Keep that result as evidence instead of changing the criterion to make the experiment pass.

## Record an eventual criterion result

Use this compact record for any criterion from the six reviews:

```text
Criterion ID:
Board manifest and full SHA-256:
Schematic, assembly, enclosure, coil/pan and control configuration:
Component/net mapping:
Applicability and acceptance requirement:
Operating and fault conditions:
Mechanism and prediction:
Evidence file, quantity, units and uncertainty:
Result: U / NA / 0 / 1 / 2 / 3
Measured or calculated margin:
Trade-offs and alternatives considered:
Required follow-up and owner:
Reviewer and date:
```

An unrun experiment remains a planned verification. An undefined requirement remains an input to resolve. Neither becomes a pass because the associated recommendation appears in several books.
