# Stage19b criterion index

All 179 criteria have an explicit score, rationale and next evidence in their linked reports. Use the [synthesis](README.md) for priorities and interpretation. Counts are a coverage inventory; criteria are not weighted or averaged.

| Resource | 0 | 1 | 2 | 3 | U | NA | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| [bogatin-practical](bogatin-practical.md) | 0 | 9 | 15 | 0 | 4 | 0 | 28 |
| [ott-emc](ott-emc.md) | 0 | 8 | 9 | 0 | 18 | 0 | 35 |
| [bogatin-sipi](bogatin-sipi.md) | 0 | 13 | 3 | 0 | 11 | 2 | 29 |
| [art-of-electronics](art-of-electronics.md) | 0 | 26 | 8 | 0 | 2 | 1 | 37 |
| [trilogy-magnetics](trilogy-magnetics.md) | 0 | 3 | 9 | 0 | 16 | 1 | 29 |
| [an139](an139.md) | 0 | 3 | 14 | 0 | 4 | 0 | 21 |
| **Coverage total** | 0 | 62 | 58 | 0 | 55 | 4 | **179** |

Scores: 0 demonstrated applicable failure; 1 evidenced concern; 2 supported rationale with verification pending; 3 verified margin; U essential information missing; NA inapplicable with reason. No score 0 was demonstrated in this evidence; none has representative measured operating-margin qualification. This is not evidence that the design has no failures.

| Criterion | Score | Review topic | Assessment |
|---|---:|---|---|
| BP-01 | 2 | Define the function and risk before geometry | [Evidence and next check](bogatin-practical.md) |
| BP-02 | 2 | Classify nets by the harm their parasitics can cause | [Evidence and next check](bogatin-practical.md) |
| BP-03 | 1 | Qualify each exact MPN for its actual duty | [Evidence and next check](bogatin-practical.md) |
| BP-04 | 1 | Verify value under operating bias, heat and tolerance | [Evidence and next check](bogatin-practical.md) |
| BP-05 | 1 | Make alternatives genuinely interchangeable | [Evidence and next check](bogatin-practical.md) |
| BP-06 | 1 | Tie symbol, footprint and physical sample to one part | [Evidence and next check](bogatin-practical.md) |
| BP-07 | 1 | Match package to assembly, repair and force | [Evidence and next check](bogatin-practical.md) |
| BP-08 | 2 | Size every current path from worst-case heating and loss | [Evidence and next check](bogatin-practical.md) |
| BP-09 | 2 | Treat via and pad transitions as path bottlenecks | [Evidence and next check](bogatin-practical.md) |
| BP-10 | 2 | Calculate DC drop and sense error along the real return path | [Evidence and next check](bogatin-practical.md) |
| BP-11 | 2 | Trace each fast power loop and its return | [Evidence and next check](bogatin-practical.md) |
| BP-12 | 2 | Keep sensitive return currents out of shared narrow segments | [Evidence and next check](bogatin-practical.md) |
| BP-13 | 1 | Preserve a nearby uninterrupted return for fast signals | [Evidence and next check](bogatin-practical.md) |
| BP-14 | 2 | Review layer changes as two coupled transitions | [Evidence and next check](bogatin-practical.md) |
| BP-15 | 1 | Keep unrelated fast aggressors away from quiet victims | [Evidence and next check](bogatin-practical.md) |
| BP-16 | 1 | Place local bypass by total loop, not centroid distance | [Evidence and next check](bogatin-practical.md) |
| BP-17 | U | Select decoupling as an impedance network | [Evidence and next check](bogatin-practical.md) |
| BP-18 | 2 | Separate source filtering from local transient supply | [Evidence and next check](bogatin-practical.md) |
| BP-19 | 2 | Evaluate copper pours by function and boundary | [Evidence and next check](bogatin-practical.md) |
| BP-20 | U | Match stackup to routes, returns, voltage domains and fab | [Evidence and next check](bogatin-practical.md) |
| BP-21 | U | Protect solderability without sacrificing electrical purpose | [Evidence and next check](bogatin-practical.md) |
| BP-22 | 2 | Review board-edge placement and physical service access | [Evidence and next check](bogatin-practical.md) |
| BP-23 | 2 | Verify DRC, schematic intent and artwork independently | [Evidence and next check](bogatin-practical.md) |
| BP-24 | 2 | Provide intentional probe points and references | [Evidence and next check](bogatin-practical.md) |
| BP-25 | 2 | Make staged bring-up and fault isolation possible | [Evidence and next check](bogatin-practical.md) |
| BP-26 | 2 | Define what a pass means and retain the evidence | [Evidence and next check](bogatin-practical.md) |
| BP-27 | 1 | Keep release identity and fab process explicit | [Evidence and next check](bogatin-practical.md) |
| BP-28 | U | Review domain separation independently of return continuity | [Evidence and next check](bogatin-practical.md) |
| OTT-01 | 2 | Draw each fast-current loop, including the return | [Evidence and next check](ott-emc.md) |
| OTT-02 | 2 | Partition noisy and susceptible functions before routing | [Evidence and next check](ott-emc.md) |
| OTT-03 | 2 | Minimize differential-mode switching-loop area | [Evidence and next check](ott-emc.md) |
| OTT-04 | 1 | Keep fast signal references continuous | [Evidence and next check](ott-emc.md) |
| OTT-05 | U | Treat slots, cutouts, and antipad rows as return obstructions | [Evidence and next check](ott-emc.md) |
| OTT-06 | 1 | Supply a return when changing signal layers | [Evidence and next check](ott-emc.md) |
| OTT-07 | U | Choose stackup by field and return goals, not layer count alone | [Evidence and next check](ott-emc.md) |
| OTT-08 | 2 | Prefer continuous ground for mixed-signal areas, with disciplined routing | [Evidence and next check](ott-emc.md) |
| OTT-09 | U | Keep external connector returns intact | [Evidence and next check](ott-emc.md) |
| OTT-10 | U | Ground copper pours deliberately | [Evidence and next check](ott-emc.md) |
| OTT-11 | 2 | Control clock routes and high-edge-rate control signals | [Evidence and next check](ott-emc.md) |
| OTT-12 | 1 | Keep sensitive inputs and feedback loops compact | [Evidence and next check](ott-emc.md) |
| OTT-13 | U | Model decoupling as an installed L-C network | [Evidence and next check](ott-emc.md) |
| OTT-14 | U | Examine antiresonance and source interaction | [Evidence and next check](ott-emc.md) |
| OTT-15 | 1 | Put bulk energy where recharge current enters | [Evidence and next check](ott-emc.md) |
| OTT-16 | U | Separate common-mode from differential-mode conducted noise | [Evidence and next check](ott-emc.md) |
| OTT-17 | 1 | Locate the mains filter at the entry boundary and prevent bypass | [Evidence and next check](ott-emc.md) |
| OTT-18 | 1 | Match filter topology to measured mode and terminal impedances | [Evidence and next check](ott-emc.md) |
| OTT-19 | 2 | Treat X/Y capacitor roles and safety constraints explicitly | [Evidence and next check](ott-emc.md) |
| OTT-20 | 1 | Characterize chokes and ferrites at actual frequency and current | [Evidence and next check](ott-emc.md) |
| OTT-21 | 2 | Inventory parasitic common-mode paths from switch nodes | [Evidence and next check](ott-emc.md) |
| OTT-22 | 2 | Distinguish protective earth, chassis, circuit return, and isolation | [Evidence and next check](ott-emc.md) |
| OTT-23 | U | Make connector and cable paths part of the EMC model | [Evidence and next check](ott-emc.md) |
| OTT-24 | U | Terminate shields to a meaningful enclosure boundary | [Evidence and next check](ott-emc.md) |
| OTT-25 | 1 | Give each cable signal a nearby return | [Evidence and next check](ott-emc.md) |
| OTT-26 | 2 | Analyze enclosure seams, apertures, and nearby metal | [Evidence and next check](ott-emc.md) |
| OTT-27 | U | Filter susceptible inputs at the appropriate boundary | [Evidence and next check](ott-emc.md) |
| OTT-28 | U | Divert ESD current before it reaches sensitive ground | [Evidence and next check](ott-emc.md) |
| OTT-29 | U | Design surge/EFT protection as an energy and return-path network | [Evidence and next check](ott-emc.md) |
| OTT-30 | U | Suppress relay/contact and inductive-load transients locally where applicable | [Evidence and next check](ott-emc.md) |
| OTT-31 | U | Treat harmonic current and flicker as separate mains questions | [Evidence and next check](ott-emc.md) |
| OTT-32 | U | Measure cable common-mode current, then rescan all cables | [Evidence and next check](ott-emc.md) |
| OTT-33 | U | Use near-field scans for localization, not far-field certification | [Evidence and next check](ott-emc.md) |
| OTT-34 | U | Run conducted-emission tests with a valid setup and mode separation | [Evidence and next check](ott-emc.md) |
| OTT-35 | U | Verify immunity, functional behavior, and margin together | [Evidence and next check](ott-emc.md) |
| SI-01 | 1 | Edge and disturbance inventory | [Evidence and next check](bogatin-sipi.md) |
| SI-02 | U | Explicit noise and timing budgets | [Evidence and next check](bogatin-sipi.md) |
| SI-03 | 1 | Model fidelity and domain | [Evidence and next check](bogatin-sipi.md) |
| SI-04 | U | Prediction and measurement agreement | [Evidence and next check](bogatin-sipi.md) |
| SI-05 | 1 | Enumerate complete fast-current loops | [Evidence and next check](bogatin-sipi.md) |
| SI-06 | 1 | Bound loop inductance and voltage overshoot | [Evidence and next check](bogatin-sipi.md) |
| SI-07 | 1 | Shared-return contamination | [Evidence and next check](bogatin-sipi.md) |
| SI-08 | 1 | Reference continuity across transitions | [Evidence and next check](bogatin-sipi.md) |
| SI-09 | 2 | Current path proximity and parallel conductors | [Evidence and next check](bogatin-sipi.md) |
| SI-10 | U | Separate capacitor jobs | [Evidence and next check](bogatin-sipi.md) |
| SI-11 | 1 | Rail impedance versus load spectrum | [Evidence and next check](bogatin-sipi.md) |
| SI-12 | U | Mounted, not catalog, bypass inductance | [Evidence and next check](bogatin-sipi.md) |
| SI-13 | U | Antiresonance and damping | [Evidence and next check](bogatin-sipi.md) |
| SI-14 | 1 | Bulk versus fast local energy | [Evidence and next check](bogatin-sipi.md) |
| SI-15 | U | Placement sensitivity and stackup | [Evidence and next check](bogatin-sipi.md) |
| SI-16 | U | Decide when a net is electrically long | [Evidence and next check](bogatin-sipi.md) |
| SI-17 | U | Termination matched to topology | [Evidence and next check](bogatin-sipi.md) |
| SI-18 | U | Discontinuity inventory | [Evidence and next check](bogatin-sipi.md) |
| SI-19 | 2 | Delay and matching tied to a timing budget | [Evidence and next check](bogatin-sipi.md) |
| SI-20 | NA | Material and trace loss where it matters | [Evidence and next check](bogatin-sipi.md) |
| SI-21 | 1 | Rank aggressor/victim pairs | [Evidence and next check](bogatin-sipi.md) |
| SI-22 | NA | Guard trace claims | [Evidence and next check](bogatin-sipi.md) |
| SI-23 | 1 | Differential pair return and symmetry | [Evidence and next check](bogatin-sipi.md) |
| SI-24 | 1 | Common-mode conversion and cables | [Evidence and next check](bogatin-sipi.md) |
| SI-25 | U | Crosstalk evidence at the victim | [Evidence and next check](bogatin-sipi.md) |
| SI-26 | U | Instrument matches the question | [Evidence and next check](bogatin-sipi.md) |
| SI-27 | 1 | Verify uncertainty and worst case | [Evidence and next check](bogatin-sipi.md) |
| SI-28 | 2 | Copper resistance with the right current distribution | [Evidence and next check](bogatin-sipi.md) |
| SI-29 | 1 | Parasitic capacitance and displacement-current route | [Evidence and next check](bogatin-sipi.md) |
| AOE-01 | 1 | Define the real operating envelope before accepting a rating | [Evidence and next check](art-of-electronics.md) |
| AOE-02 | 1 | Size capacitors by effective function, not marked microfarads | [Evidence and next check](art-of-electronics.md) |
| AOE-03 | 1 | Treat inductors and transformers as lossy magnetic parts | [Evidence and next check](art-of-electronics.md) |
| AOE-04 | 1 | Select rectifiers and clamps for transients, not DC forward drop alone | [Evidence and next check](art-of-electronics.md) |
| AOE-05 | 1 | Audit connector systems as components with failure modes | [Evidence and next check](art-of-electronics.md) |
| AOE-06 | 2 | Keep calibration adjustments from becoming the accuracy strategy | [Evidence and next check](art-of-electronics.md) |
| AOE-07 | 1 | Account for resistor behavior beyond initial tolerance | [Evidence and next check](art-of-electronics.md) |
| AOE-08 | 2 | Select the switch topology and technology against actual voltage, loss, and frequency | [Evidence and next check](art-of-electronics.md) |
| AOE-09 | 1 | Verify fully enhanced gate drive at the hot and low-supply corners | [Evidence and next check](art-of-electronics.md) |
| AOE-10 | 1 | Make gate-drive current a transient calculation | [Evidence and next check](art-of-electronics.md) |
| AOE-11 | 1 | Include output capacitance and body-diode recovery in commutation | [Evidence and next check](art-of-electronics.md) |
| AOE-12 | 2 | Prove off-state and gate-oxide protection in abnormal states | [Evidence and next check](art-of-electronics.md) |
| AOE-13 | 1 | Separate repetitive switching SOA from fault and linear SOA | [Evidence and next check](art-of-electronics.md) |
| AOE-14 | 1 | Close the complete junction-to-ambient thermal path | [Evidence and next check](art-of-electronics.md) |
| AOE-15 | 1 | Design fault interruption as part of the power path | [Evidence and next check](art-of-electronics.md) |
| AOE-16 | 1 | Write an error budget for each protected or controlled quantity | [Evidence and next check](art-of-electronics.md) |
| AOE-17 | 1 | Verify precision resistor ratios and shunt temperature, not just absolute resistance | [Evidence and next check](art-of-electronics.md) |
| AOE-18 | 1 | Check analog front-end common-mode range, input return path, and recovery | [Evidence and next check](art-of-electronics.md) |
| AOE-19 | 2 | Preserve differential sensing in the presence of mismatch and switching fields | [Evidence and next check](art-of-electronics.md) |
| AOE-20 | 1 | Set bandwidth from control and protection timing, then budget noise | [Evidence and next check](art-of-electronics.md) |
| AOE-21 | 2 | Route return currents so power drops do not become measurements | [Evidence and next check](art-of-electronics.md) |
| AOE-22 | 1 | Test radiated, capacitive, and magnetic coupling as distinct paths | [Evidence and next check](art-of-electronics.md) |
| AOE-23 | 2 | Make decoupling and supply filtering stable and local | [Evidence and next check](art-of-electronics.md) |
| AOE-24 | 1 | Follow the complete mains protection and isolation path | [Evidence and next check](art-of-electronics.md) |
| AOE-25 | 1 | Size fuse and input parts from actual RMS, inrush, and fault waveforms | [Evidence and next check](art-of-electronics.md) |
| AOE-26 | 2 | Account for stored energy and discharge after power removal | [Evidence and next check](art-of-electronics.md) |
| AOE-27 | 1 | Check auxiliary supply behavior during startup, brownout, and power failure | [Evidence and next check](art-of-electronics.md) |
| AOE-28 | 1 | Use reference designs as empirical starting points and test their parasitic omissions | [Evidence and next check](art-of-electronics.md) |
| AOE-29 | 1 | Treat an isolator as a timed power-and-signal channel | [Evidence and next check](art-of-electronics.md) |
| AOE-30 | NA | Prove high-side supply hold-up for every commanded pattern | [Evidence and next check](art-of-electronics.md) |
| AOE-31 | 1 | Protect every off-board logic/sensor input at the physical boundary | [Evidence and next check](art-of-electronics.md) |
| AOE-32 | 2 | Route fast digital signals with a defined return and termination when needed | [Evidence and next check](art-of-electronics.md) |
| AOE-33 | U | Design ADC channel filtering and sampling together | [Evidence and next check](art-of-electronics.md) |
| AOE-34 | U | Select ADC/DAC architecture by the error that matters to the loop | [Evidence and next check](art-of-electronics.md) |
| AOE-35 | 1 | Make each BOM line a buildable, traceable choice | [Evidence and next check](art-of-electronics.md) |
| AOE-36 | 1 | Qualify supply and lifecycle without mistaking the book's directory for live inventory | [Evidence and next check](art-of-electronics.md) |
| AOE-37 | 1 | Make the measurement setup part of the evidence | [Evidence and next check](art-of-electronics.md) |
| MAG-01 | 2 | Identify the job of every magnetic element | [Evidence and next check](trilogy-magnetics.md) |
| MAG-02 | U | Derive an operating envelope before choosing catalog curves | [Evidence and next check](trilogy-magnetics.md) |
| MAG-03 | U | Distinguish the interference mode and frequency | [Evidence and next check](trilogy-magnetics.md) |
| MAG-04 | 2 | Define the useful signal band that filtering must preserve | [Evidence and next check](trilogy-magnetics.md) |
| MAG-05 | 2 | Separate thermal current rating from saturation current | [Evidence and next check](trilogy-magnetics.md) |
| MAG-06 | U | Check bias-dependent impedance and inductance | [Evidence and next check](trilogy-magnetics.md) |
| MAG-07 | U | Treat AC copper loss as distinct from DCR | [Evidence and next check](trilogy-magnetics.md) |
| MAG-08 | U | Account for core loss with the real flux waveform | [Evidence and next check](trilogy-magnetics.md) |
| MAG-09 | U | Confirm thermal aging and neighboring heat | [Evidence and next check](trilogy-magnetics.md) |
| MAG-10 | 2 | Check parasitic capacitance and self resonance | [Evidence and next check](trilogy-magnetics.md) |
| MAG-11 | U | Verify insulation, voltage, impulse, and mechanical clearances independently | [Evidence and next check](trilogy-magnetics.md) |
| MAG-12 | 2 | Maintain a current exact-part qualification record | [Evidence and next check](trilogy-magnetics.md) |
| MAG-13 | 2 | Model the installed filter with actual terminations | [Evidence and next check](trilogy-magnetics.md) |
| MAG-14 | 1 | Examine the whole filter's resonance and damping | [Evidence and next check](trilogy-magnetics.md) |
| MAG-15 | U | Keep common and differential behavior separate for L1 | [Evidence and next check](trilogy-magnetics.md) |
| MAG-16 | U | Place the filter at the boundary it protects | [Evidence and next check](trilogy-magnetics.md) |
| MAG-17 | U | Keep shunt-capacitor return paths short and intentional | [Evidence and next check](trilogy-magnetics.md) |
| MAG-18 | 2 | Measure parasitic input/output coupling around filter parts | [Evidence and next check](trilogy-magnetics.md) |
| MAG-19 | U | Validate X/Y capacitor and PE interaction as a system | [Evidence and next check](trilogy-magnetics.md) |
| MAG-20 | NA | Match ferrite suppression to the actual spectrum | [Evidence and next check](trilogy-magnetics.md) |
| MAG-21 | U | Do not use product-family claims as immunity evidence | [Evidence and next check](trilogy-magnetics.md) |
| MAG-22 | U | Characterize the external induction coil with representative pans | [Evidence and next check](trilogy-magnetics.md) |
| MAG-23 | 2 | Derive tank resonance, circulating current, and device stress from that characterization | [Evidence and next check](trilogy-magnetics.md) |
| MAG-24 | U | Optimize coil conductor for AC loss, not DCR alone | [Evidence and next check](trilogy-magnetics.md) |
| MAG-25 | 2 | Measure T1 burden, magnetizing error, and frequency response | [Evidence and next check](trilogy-magnetics.md) |
| MAG-26 | 1 | Confirm transformer reset and fault behavior | [Evidence and next check](trilogy-magnetics.md) |
| MAG-27 | U | Quantify transformer leakage versus interwinding capacitance | [Evidence and next check](trilogy-magnetics.md) |
| MAG-28 | U | Map stray field to sensitive functions and metalwork | [Evidence and next check](trilogy-magnetics.md) |
| MAG-29 | 1 | Preserve measurement observability in the physical design | [Evidence and next check](trilogy-magnetics.md) |
| AN139-01 | 1 | Map every bridge state before naming a “hot loop.” | [Evidence and next check](an139.md) |
| AN139-02 | 2 | Local DC-link closure at both bridge legs | [Evidence and next check](an139.md) |
| AN139-03 | 2 | Minimize effective loop area, not merely trace length | [Evidence and next check](an139.md) |
| AN139-04 | 2 | Control the switch-node copper deliberately | [Evidence and next check](an139.md) |
| AN139-05 | 2 | Preserve a close mirror-current path where permitted | [Evidence and next check](an139.md) |
| AN139-06 | U | Keep quiet ground attachments out of the hot-loop shield region | [Evidence and next check](an139.md) |
| AN139-07 | 2 | Keep high-current thermal paths compatible with RF geometry | [Evidence and next check](an139.md) |
| AN139-08 | 2 | Close each low-side gate-charge loop | [Evidence and next check](an139.md) |
| AN139-09 | 2 | Close each high-side floating-driver and bootstrap loop | [Evidence and next check](an139.md) |
| AN139-10 | 2 | Treat driver-supply decoupling as a separate AC loop | [Evidence and next check](an139.md) |
| AN139-11 | 2 | Route current-sense inputs as a small receiving loop | [Evidence and next check](an139.md) |
| AN139-12 | 2 | Keep control and measurement references out of fast-field paths | [Evidence and next check](an139.md) |
| AN139-13 | 1 | Establish a quiet filter boundary and return | [Evidence and next check](an139.md) |
| AN139-14 | 1 | Make the filter path pass through its capacitor pads | [Evidence and next check](an139.md) |
| AN139-15 | U | Check magnetic coupling around filter inductors | [Evidence and next check](an139.md) |
| AN139-16 | 2 | Evaluate conducted and common-mode routes separately | [Evidence and next check](an139.md) |
| AN139-17 | U | Verify filter/source impedance and stability | [Evidence and next check](an139.md) |
| AN139-18 | 2 | Do not trade insulation for a close image plane | [Evidence and next check](an139.md) |
| AN139-19 | 2 | Use field/impedance evidence for proposed layout improvements | [Evidence and next check](an139.md) |
| AN139-20 | 2 | Plan repeatable EMI precompliance and probing | [Evidence and next check](an139.md) |
| AN139-21 | U | Diagnose unexpected spectral lines before tuning copper | [Evidence and next check](an139.md) |
