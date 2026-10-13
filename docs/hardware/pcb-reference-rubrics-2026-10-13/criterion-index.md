# PCB reference criterion index

All criteria are unassessed. Use the [review guide](README.md) and [trade-off synthesis](tradeoffs.md) before scoring. Individual resource files contain the primary-source locators, advice, limitations and scoring anchors.

## Bogatin's Practical Guide: Temper PCB review rubric

[Detailed rubric](bogatin-practical.md) — 28 criteria.

| Criterion | Review topic |
|---|---|
| BP-01 | Define the function and risk before geometry |
| BP-02 | Classify nets by the harm their parasitics can cause |
| BP-03 | Qualify each exact MPN for its actual duty |
| BP-04 | Verify value under operating bias, heat and tolerance |
| BP-05 | Make alternatives genuinely interchangeable |
| BP-06 | Tie symbol, footprint and physical sample to one part |
| BP-07 | Match package to assembly, repair and force |
| BP-08 | Size every current path from worst-case heating and loss |
| BP-09 | Treat via and pad transitions as path bottlenecks |
| BP-10 | Calculate DC drop and sense error along the real return path |
| BP-11 | Trace each fast power loop and its return |
| BP-12 | Keep sensitive return currents out of shared narrow segments |
| BP-13 | Preserve a nearby uninterrupted return for fast signals |
| BP-14 | Review layer changes as two coupled transitions |
| BP-15 | Keep unrelated fast aggressors away from quiet victims |
| BP-16 | Place local bypass by total loop, not centroid distance |
| BP-17 | Select decoupling as an impedance network |
| BP-18 | Separate source filtering from local transient supply |
| BP-19 | Evaluate copper pours by function and boundary |
| BP-20 | Match stackup to routes, returns, voltage domains and fab |
| BP-21 | Protect solderability without sacrificing electrical purpose |
| BP-22 | Review board-edge placement and physical service access |
| BP-23 | Verify DRC, schematic intent and artwork independently |
| BP-24 | Provide intentional probe points and references |
| BP-25 | Make staged bring-up and fault isolation possible |
| BP-26 | Define what a pass means and retain the evidence |
| BP-27 | Keep release identity and fab process explicit |
| BP-28 | Review domain separation independently of return continuity |

## Henry Ott, *Electromagnetic Compatibility Engineering*: rubric for a future Temper native-21 review

[Detailed rubric](ott-emc.md) — 35 criteria.

| Criterion | Review topic |
|---|---|
| OTT-01 | Draw each fast-current loop, including the return |
| OTT-02 | Partition noisy and susceptible functions before routing |
| OTT-03 | Minimize differential-mode switching-loop area |
| OTT-04 | Keep fast signal references continuous |
| OTT-05 | Treat slots, cutouts, and antipad rows as return obstructions |
| OTT-06 | Supply a return when changing signal layers |
| OTT-07 | Choose stackup by field and return goals, not layer count alone |
| OTT-08 | Prefer continuous ground for mixed-signal areas, with disciplined routing |
| OTT-09 | Keep external connector returns intact |
| OTT-10 | Ground copper pours deliberately |
| OTT-11 | Control clock routes and high-edge-rate control signals |
| OTT-12 | Keep sensitive inputs and feedback loops compact |
| OTT-13 | Model decoupling as an installed L-C network |
| OTT-14 | Examine antiresonance and source interaction |
| OTT-15 | Put bulk energy where recharge current enters |
| OTT-16 | Separate common-mode from differential-mode conducted noise |
| OTT-17 | Locate the mains filter at the entry boundary and prevent bypass |
| OTT-18 | Match filter topology to measured mode and terminal impedances |
| OTT-19 | Treat X/Y capacitor roles and safety constraints explicitly |
| OTT-20 | Characterize chokes and ferrites at actual frequency and current |
| OTT-21 | Inventory parasitic common-mode paths from switch nodes |
| OTT-22 | Distinguish protective earth, chassis, circuit return, and isolation |
| OTT-23 | Make connector and cable paths part of the EMC model |
| OTT-24 | Terminate shields to a meaningful enclosure boundary |
| OTT-25 | Give each cable signal a nearby return |
| OTT-26 | Analyze enclosure seams, apertures, and nearby metal |
| OTT-27 | Filter susceptible inputs at the appropriate boundary |
| OTT-28 | Divert ESD current before it reaches sensitive ground |
| OTT-29 | Design surge/EFT protection as an energy and return-path network |
| OTT-30 | Suppress relay/contact and inductive-load transients locally where applicable |
| OTT-31 | Treat harmonic current and flicker as separate mains questions |
| OTT-32 | Measure cable common-mode current, then rescan all cables |
| OTT-33 | Use near-field scans for localization, not far-field certification |
| OTT-34 | Run conducted-emission tests with a valid setup and mode separation |
| OTT-35 | Verify immunity, functional behavior, and margin together |

## Signal and Power Integrity—Simplified: rubric for a later Temper review

[Detailed rubric](bogatin-sipi.md) — 29 criteria.

| Criterion | Review topic |
|---|---|
| SI-01 | Edge and disturbance inventory |
| SI-02 | Explicit noise and timing budgets |
| SI-03 | Model fidelity and domain |
| SI-04 | Prediction and measurement agreement |
| SI-05 | Enumerate complete fast-current loops |
| SI-06 | Bound loop inductance and voltage overshoot |
| SI-07 | Shared-return contamination |
| SI-08 | Reference continuity across transitions |
| SI-09 | Current path proximity and parallel conductors |
| SI-10 | Separate capacitor jobs |
| SI-11 | Rail impedance versus load spectrum |
| SI-12 | Mounted, not catalog, bypass inductance |
| SI-13 | Antiresonance and damping |
| SI-14 | Bulk versus fast local energy |
| SI-15 | Placement sensitivity and stackup |
| SI-16 | Decide when a net is electrically long |
| SI-17 | Termination matched to topology |
| SI-18 | Discontinuity inventory |
| SI-19 | Delay and matching tied to a timing budget |
| SI-20 | Material and trace loss where it matters |
| SI-21 | Rank aggressor/victim pairs |
| SI-22 | Guard trace claims |
| SI-23 | Differential pair return and symmetry |
| SI-24 | Common-mode conversion and cables |
| SI-25 | Crosstalk evidence at the victim |
| SI-26 | Instrument matches the question |
| SI-27 | Verify uncertainty and worst case |
| SI-28 | Copper resistance with the right current distribution |
| SI-29 | Parasitic capacitance and displacement-current route |

## The Art of Electronics (3rd ed.): a component-and-circuit rubric for a later Temper review

[Detailed rubric](art-of-electronics.md) — 37 criteria.

| Criterion | Review topic |
|---|---|
| AOE-01 | Define the real operating envelope before accepting a rating |
| AOE-02 | Size capacitors by effective function, not marked microfarads |
| AOE-03 | Treat inductors and transformers as lossy magnetic parts |
| AOE-04 | Select rectifiers and clamps for transients, not DC forward drop alone |
| AOE-05 | Audit connector systems as components with failure modes |
| AOE-06 | Keep calibration adjustments from becoming the accuracy strategy |
| AOE-07 | Account for resistor behavior beyond initial tolerance |
| AOE-08 | Select the switch topology and technology against actual voltage, loss, and frequency |
| AOE-09 | Verify fully enhanced gate drive at the hot and low-supply corners |
| AOE-10 | Make gate-drive current a transient calculation |
| AOE-11 | Include output capacitance and body-diode recovery in commutation |
| AOE-12 | Prove off-state and gate-oxide protection in abnormal states |
| AOE-13 | Separate repetitive switching SOA from fault and linear SOA |
| AOE-14 | Close the complete junction-to-ambient thermal path |
| AOE-15 | Design fault interruption as part of the power path |
| AOE-16 | Write an error budget for each protected or controlled quantity |
| AOE-17 | Verify precision resistor ratios and shunt temperature, not just absolute resistance |
| AOE-18 | Check analog front-end common-mode range, input return path, and recovery |
| AOE-19 | Preserve differential sensing in the presence of mismatch and switching fields |
| AOE-20 | Set bandwidth from control and protection timing, then budget noise |
| AOE-21 | Route return currents so power drops do not become measurements |
| AOE-22 | Test radiated, capacitive, and magnetic coupling as distinct paths |
| AOE-23 | Make decoupling and supply filtering stable and local |
| AOE-24 | Follow the complete mains protection and isolation path |
| AOE-25 | Size fuse and input parts from actual RMS, inrush, and fault waveforms |
| AOE-26 | Account for stored energy and discharge after power removal |
| AOE-27 | Check auxiliary supply behavior during startup, brownout, and power failure |
| AOE-28 | Use reference designs as empirical starting points and test their parasitic omissions |
| AOE-29 | Treat an isolator as a timed power-and-signal channel |
| AOE-30 | Prove high-side supply hold-up for every commanded pattern |
| AOE-31 | Protect every off-board logic/sensor input at the physical boundary |
| AOE-32 | Route fast digital signals with a defined return and termination when needed |
| AOE-33 | Design ADC channel filtering and sampling together |
| AOE-34 | Select ADC/DAC architecture by the error that matters to the loop |
| AOE-35 | Make each BOM line a buildable, traceable choice |
| AOE-36 | Qualify supply and lifecycle without mistaking the book's directory for live inventory |
| AOE-37 | Make the measurement setup part of the evidence |

## Magnetics and EMI-filter review rubric for a future Temper board review

[Detailed rubric](trilogy-magnetics.md) — 29 criteria.

| Criterion | Review topic |
|---|---|
| MAG-01 | Identify the job of every magnetic element |
| MAG-02 | Derive an operating envelope before choosing catalog curves |
| MAG-03 | Distinguish the interference mode and frequency |
| MAG-04 | Define the useful signal band that filtering must preserve |
| MAG-05 | Separate thermal current rating from saturation current |
| MAG-06 | Check bias-dependent impedance and inductance |
| MAG-07 | Treat AC copper loss as distinct from DCR |
| MAG-08 | Account for core loss with the real flux waveform |
| MAG-09 | Confirm thermal aging and neighboring heat |
| MAG-10 | Check parasitic capacitance and self resonance |
| MAG-11 | Verify insulation, voltage, impulse, and mechanical clearances independently |
| MAG-12 | Maintain a current exact-part qualification record |
| MAG-13 | Model the installed filter with actual terminations |
| MAG-14 | Examine the whole filter's resonance and damping |
| MAG-15 | Keep common and differential behavior separate for L1 |
| MAG-16 | Place the filter at the boundary it protects |
| MAG-17 | Keep shunt-capacitor return paths short and intentional |
| MAG-18 | Measure parasitic input/output coupling around filter parts |
| MAG-19 | Validate X/Y capacitor and PE interaction as a system |
| MAG-20 | Match ferrite suppression to the actual spectrum |
| MAG-21 | Do not use product-family claims as immunity evidence |
| MAG-22 | Characterize the external induction coil with representative pans |
| MAG-23 | Derive tank resonance, circulating current, and device stress from that characterization |
| MAG-24 | Optimize coil conductor for AC loss, not DCR alone |
| MAG-25 | Measure T1 burden, magnetizing error, and frequency response |
| MAG-26 | Confirm transformer reset and fault behavior |
| MAG-27 | Quantify transformer leakage versus interwinding capacitance |
| MAG-28 | Map stray field to sensitive functions and metalwork |
| MAG-29 | Preserve measurement observability in the physical design |

## AN-139 review: power layout and EMI criteria for a future Temper stage15b review

[Detailed rubric](an139.md) — 21 criteria.

| Criterion | Review topic |
|---|---|
| AN139-01 | Map every bridge state before naming a “hot loop.” |
| AN139-02 | Local DC-link closure at both bridge legs |
| AN139-03 | Minimize effective loop area, not merely trace length |
| AN139-04 | Control the switch-node copper deliberately |
| AN139-05 | Preserve a close mirror-current path where permitted |
| AN139-06 | Keep quiet ground attachments out of the hot-loop shield region |
| AN139-07 | Keep high-current thermal paths compatible with RF geometry |
| AN139-08 | Close each low-side gate-charge loop |
| AN139-09 | Close each high-side floating-driver and bootstrap loop |
| AN139-10 | Treat driver-supply decoupling as a separate AC loop |
| AN139-11 | Route current-sense inputs as a small receiving loop |
| AN139-12 | Keep control and measurement references out of fast-field paths |
| AN139-13 | Establish a quiet filter boundary and return |
| AN139-14 | Make the filter path pass through its capacitor pads |
| AN139-15 | Check magnetic coupling around filter inductors |
| AN139-16 | Evaluate conducted and common-mode routes separately |
| AN139-17 | Verify filter/source impedance and stability |
| AN139-18 | Do not trade insulation for a close image plane |
| AN139-19 | Use field/impedance evidence for proposed layout improvements |
| AN139-20 | Plan repeatable EMI precompliance and probing |
| AN139-21 | Diagnose unexpected spectral lines before tuning copper |
