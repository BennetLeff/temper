# Temper PCB design review rubric

Date: 2026-10-10. Scope: circuit design, placement, routing, thermal performance, electromagnetic compatibility, fabrication, assembly, reliability, and test beyond basic ERC and DRC.

Use this rubric to decide whether a PCB will perform its function across operating conditions and can be built repeatedly. Its 160 checks ask for evidence, not just an attractive layout or a zero violation count. The most consequential checks are conductor heating, switching and gate loops, protection latency, insulation across the assembled product, and sensing integrity.

This is a proposed engineering review method. It does not assign a passing score to any existing Temper board. Numerical project targets below require adoption against the actual requirements; manufacturer limits and applicable product requirements take precedence.

## Design identity and applicability

Primary scope is current Zapote at `ba575413f5a39401eed1c20417ab7565fa28b509`, refreshed from `origin/main` on 2026-10-10. The current repository describes a 120 V full bridge and five maintained standalone units; it removed the legacy board on 2026-10-08. Keep selected artifacts separate from candidate and historical snapshots:

| Family | Local evidence | Applicability |
| --- | --- | --- |
| Five maintained units | [Unit registry](../../zapote/validation/units.json), [check catalog](../../zapote/CHECKS.md) | RTD, current sensor, gate driver, thermal cutoff and safety interlock each have their own BOM, board and fabrication profile. Their checks do not qualify the complete appliance. |
| 120 V power stage | [Workspace](../../zapote/power-stage-120v/README.md), [power-section design](power-section-120v/POWER-SECTION.md), resolved BOMs and native candidates | Full bridge, IPW65R018CFD7, UCC21550 and isolated sensing/protection. Native candidate identity and exact fitted suffixes matter. The complete board is not registered in the five-unit check runner and has no hardware qualification claim. |
| Separate controller and prototype studies | [IC inventory](PCB_IC_DATASHEET_GUIDANCE.md), [source context](PCB_DESIGN_SOURCE_CONTEXT.md) | Inspected research snapshots provide useful device advice. Inclusion here does not select those circuits or parts for the current product. |
| Archived legacy board and retired Rev38 | [Legacy archive](https://github.com/BennetLeff/temper/tree/archive/temper-legacy-2026-10-08), [historical source context](PCB_DESIGN_SOURCE_CONTEXT.md) | Half-bridge/doubler and former PFC work are history. Do not carry their ratings, protection assumptions or populated parts into current acceptance checks. |

Apply topology-dependent rows to the identified design only. A CT measuring tank current does not necessarily detect a bus shoot-through fault. A bootstrap arrangement valid in a half bridge may fail under full-bridge phase shift or burst restart. An EMI or thermal result belongs to the revision, harness and enclosure that were tested.

Part-specific requirements and coverage are in [IC datasheet guidance](PCB_IC_DATASHEET_GUIDANCE.md). For the general rubric, **E** means an engineering criterion proposed here, **P** means a physics relationship, and **S** means a narrow principle supported by a cited primary source. E and P rows are not manufacturer prescriptions. An exact device's application circuit, package drawing and operating limits must be checked separately.

## Scoring and evidence

Use one record per rule per relevant circuit or component. Score the worst instance; retain the list of instances so a good capacitor cannot conceal a bad one.

| Score | Meaning |
| --- | --- |
| 0 | A demonstrated failure or contradicted requirement. |
| 1 | The intent is documented, but no adequate supporting evidence exists. |
| 2 | Layout inspection and calculations or supplier review support the requirement across stated corners. |
| 3 | Representative hardware or process tests support it across stated corners. |
| 4 | Representative verification includes margin, build variation and a controlled production check where relevant. |
| U | Unknown. Counts as zero in the score and stays visible as an open item. |
| N/A | Excluded only with a documented circuit or process reason. |

Priority **C** carries weight 5 and can prevent a safe or electrically credible release; **H** carries weight 3 for substantial performance or reliability consequences; **Q** carries weight 1 for build quality and maintainability. These priorities are proposed review defaults; raise them when the particular application warrants it.

`category score = 100 × sum(weight × score) / (4 × sum(applicable weights))`

Show each category, the overall score, the number of unknowns, and the minimum C score. A proposed readiness target is at least 80% in each applicable category, no demonstrated C failure, and no unknown C requirement. Before first controlled power testing, each applicable C rule needs at least score 2. Before production release, C rules concerning operating behavior need representative verification, normally score 3 or 4. Documentary requirements can close through authoritative drawings, certificates or supplier acceptance; do not invent a hardware test for them. A high average never overrides a failed critical requirement.

**Evidence codes:** D = exact datasheet or governing requirement; L = actual layout and stackup inspection; A = calculation; S = simulation with defined parasitics and boundaries; M = measurement on identified hardware; F = fabricator or assembler confirmation. The evidence column describes what would close the check, not work already completed.

## 1 Requirements and design margins

| ID | Priority | Rule and failure mechanism | Acceptance evidence |
| --- | --- | --- | --- |
| REQ01 | C | **E:** Pin the schematic, netlist, PCB, BOM, firmware assumptions and mechanical assembly to one build identity. Otherwise a good review can approve a circuit that is not fabricated. | L/D: revision manifest and resolved part list; compare safety nets and connector pins across artifacts. |
| REQ02 | C | **E:** Define operating and fault corners: line range, peak and RMS current, ambient, duty, cookware, startup, shutdown and fan conditions. Nominal values alone miss the limiting case. | D/A: corner matrix with a named requirement for each limit. |
| REQ03 | C | **E:** Identify every live, SELV, protective earth, floating driver and chassis domain by connectivity. Names such as GND or 15V do not establish accessibility or isolation. | L: colored domain map including connectors, sensor cables, heatsinks and mounting hardware. |
| REQ04 | H | **E:** Record recommended operating limits separately from absolute maximum ratings. Routine operation must not depend on surviving an absolute maximum excursion. | D/A: worst-case stress versus both limits, with uncertainties. |
| REQ05 | H | **E:** Allocate explicit margin for component tolerances, temperature, aging and measurement error. Apply derating to the actual stress mechanism rather than one universal percentage. | A/D: tolerance and margin budget; justify selected design margins. |
| REQ06 | C | **E:** Test supply sequencing, brownout, unplugging and back-powering combinations. An input protection diode can power a nominally disabled fault chain. | D/S/M: rail and input waveforms for all relevant powered/unpowered combinations. |
| REQ07 | H | **E:** Verify exact orderable part, package and suffix. Different UVLO grades, default outputs or package variants can change behavior despite a shared family name. | D/F: orderable-to-symbol-to-footprint reconciliation. |
| REQ08 | C | **E:** Assign every safety function a detection path, interrupt path and residual-energy path. Include the case where the switching device has already failed short. | A/L: fault tree and testable requirements for each path. |
| REQ09 | H | **E:** Trace proposed spacing, temperature and timing targets to their basis. A historical document labeled implemented is not an external oracle. | D/A: source, assumptions, units, derivation and responsible requirement owner. |
| REQ10 | Q | **E:** Make substitutions conditional on electrical, thermal, timing, package and isolation equivalence. A footprint match alone is insufficient. | D/F: approved substitution criteria and requalification triggers. |

## 2 Trace width and conductor heating

Conductor cross-section affects resistance and heat. The resulting temperature also depends on heat spreading and the environment. [TI's Analog Engineer's Pocket Reference, printed pp. 71–72](https://www.ti.com/seclit/eb/slyw038d/slyw038d.pdf#page=71) provides a trace-heating chart attributed to IPC-2152 and the resistance relationship; it does not establish a universal current rating for Temper.

| ID | Priority | Rule and failure mechanism | Acceptance evidence |
| --- | --- | --- | --- |
| CU01 | C | **P:** Size each power path for its actual RMS waveform and separately evaluate peak/fault pulses. Average current understates heating when current is pulsed. | A/M: waveform-derived RMS and fault energy for each segment. |
| CU02 | C | **P:** Calculate resistance using minimum manufactured width and copper thickness at operating temperature. Nominal artwork and copper weight can overstate the available cross-section. | A/F: resistance and voltage-drop budget using fabrication tolerances. |
| CU03 | C | **E:** Set both maximum temperature rise and absolute conductor/adjacent-part temperature. A permissible rise at room temperature may fail in a hot cooker. | D/A/M: local ambient, conductor hot spot and neighboring material limits. |
| CU04 | C | **E:** Inspect every neck at pads, fuse clips, connector exits, zone cutouts and thermal spokes. The narrowest section can dominate heating despite a large pour. | L/A/M: segment-by-segment bottleneck list and temperature checks. |
| CU05 | H | **E:** Model internal traces with their actual plane proximity and thermal boundaries. Do not apply an external-layer calculator to an internal route. | A/S: documented IPC-2152 method or thermal model matched to the stackup. |
| CU06 | C | **E:** Check via barrels and plated slots as current-carrying conductors. Finished hole, minimum plating and connection geometry matter more than via pad diameter. | A/F/M: barrel resistance, array entry geometry and hot-spot verification. |
| CU07 | H | **E:** Justify current sharing between parallel traces, layers and vias. Unequal entry resistance or inductance can overload one branch. | L/A/S/M: branch impedances and distributed connections. |
| CU08 | H | **P:** Include AC resistance where skin and proximity effects matter, including harmonics and coupled conductors. A low switching fundamental does not bound all edge-related losses. | A/S/M: frequency-dependent loss model or representative impedance measurement. |
| CU09 | C | **E:** Coordinate copper survival with protective-device clearing. A trace becoming the unintended fuse can arc or carbonize the laminate. | A/D/M: fault-current envelope, clearing time and conductor survival basis. |
| CU10 | H | **E:** Verify power paths with hot resistance and temperature measurements in the assembled enclosure. An isolated-board calculator cannot establish the final cooling boundary. | M: worst-duty soak, hot spots, local ambient and measured voltage drop. |

## 3 Placement and supply decoupling

Local ceramic bypassing needs a short connection to the supply and its reference return. A remote charge reservoir serves a different role. Capacitor ESR and ESL affect useful frequency range. These principles are supported by [ADI MT-101, pp. 1–4](https://www.analog.com/media/en/training-seminars/tutorials/MT-101.pdf#page=2). The detailed review procedure below is an engineering extension.

| ID | Priority | Rule and failure mechanism | Acceptance evidence |
| --- | --- | --- | --- |
| DEC01 | H | **E:** Enumerate every IC supply/reference pair and its required local bypass network. Include both sides of isolators and each floating driver channel. | D/L: supply-pin inventory linked to actual capacitors and return nets. |
| DEC02 | H | **S:** Keep bypass supply and return connections short. A capacitor near the package can still be ineffective through long interconnects. | L: inspect the complete pin-capacitor-return loop. |
| DEC03 | H | **E:** Evaluate placement from copper pad to IC pin, including vias and return path, rather than package-center distance. Optimize connection inductance. | L/A: actual path length, via count and loop geometry. |
| DEC04 | H | **E:** Place the network needed for the fastest transient first, then bulk capacitance. Nominally smaller capacitance does not automatically mean lower mounted inductance. | D/L: selected parts' impedance data and routed arrangement. |
| DEC05 | H | **E:** Avoid shared narrow return necks between noisy consumers and sensitive bypasses. Common impedance converts one load's transient into another IC's supply error. | L/M: return-current inspection and supply-pin ripple measurement. |
| DEC06 | H | **E:** Use effective capacitance at voltage, temperature, tolerance and age. A 10 µF marking is not a guarantee of 10 µF in operation. | D/A: exact-part characteristic curves and minimum effective capacitance. |
| DEC07 | H | **E:** Size charge storage to the load step and allowable droop, then check regulator replenishment. Large capacitance can also alter startup and current limit. | A/S/M: load-transient and startup waveforms at the IC pins. |
| DEC08 | H | **E:** Review antiresonance and damping in combinations of MLCCs, bulk capacitors, planes and ferrites. Adding more capacitors can create an impedance peak. | S/M: relevant-frequency PDN impedance or transient ringing. |
| DEC09 | H | **E:** Check ferrite impedance at actual DC current and temperature, and resulting rail drop and filter resonance. Catalog impedance at zero bias is insufficient. | D/A/M: biased characteristics, startup and load-step behavior. |
| DEC10 | C | **E:** Bypass a floating high-side supply to its own driver return. Connecting it to SELV or the wrong power return changes the circuit and domain isolation. | D/L: explicit pin-to-net review for every floating channel. |

## 4 Switching loops and gate drive

Use the selected driver's exact layout guidance in the companion datasheet review. Identify the loops whose current changes during a transition; the entire energy-delivery loop and the local commutation loop are not interchangeable.

| ID | Priority | Rule and failure mechanism | Acceptance evidence |
| --- | --- | --- | --- |
| SW01 | C | **E:** Draw conduction paths before and after each switch transition and mark their difference. This reveals the actual high-di/dt commutation loop. | A/L: annotated paths for every bridge leg and relevant operating mode. |
| SW02 | C | **E:** Place local bus decoupling to close that loop through switches with short outgoing and return paths. Remote bulk storage cannot remove local interconnect inductance. | L/S/M: extracted loop and device-terminal overshoot. |
| SW03 | H | **E:** Measure loop geometry using current paths, return separation and transitions between layers. Trace copper area is not enclosed current-loop area. | L/A: centerline/return map or field extraction; do not multiply length by trace width. |
| SW04 | C | **E:** Keep driver output, gate resistor, device gate and source/emitter return compact. The driver-return path matters as much as the forward trace. | D/L/M: loop inspection and gate waveform at device pins. |
| SW05 | C | **E:** Separate gate return from load current wherever package and topology permit. Shared source/emitter inductance alters the effective gate voltage. | L/S/M: Kelvin routing review and differential gate measurement. |
| SW06 | H | **E:** Place each damping resistor with its device branch; give parallel devices individual resistors when required. A common upstream resistor can leave local oscillation undamped. | D/L/M: branch layout and ringing comparison. |
| SW07 | C | **P:** Check Miller-induced gate current and turn-off impedance against unwanted turn-on margin. Driver sink rating alone does not bound the gate excursion. | A/M: gate-current model and off-device gate peaks at worst dv/dt. |
| SW08 | C | **E:** Bound actual dead time using propagation mismatch, logic/filter delays, temperature and device turn-off. Include minimum safe time and maximum acceptable diode conduction. | D/A/M: timing budget and both gate/device-terminal waveforms. |
| SW09 | C | **E:** Size and verify bootstrap recharge for maximum on-time, phase shift, startup and bursts. Include leakage, driver consumption, bias derating and diode drop. | A/S/M: minimum floating supply versus UVLO across operating modes. |
| SW10 | C | **E:** Check driver negative transients, output supply limits and CMTI using the real switching waveform. An isolation withstand rating does not imply immunity to every edge. | D/M: pin-referenced waveforms and false-output/glitch checks. |

## 5 Power-device stress and resonant operation

| ID | Priority | Rule and failure mechanism | Acceptance evidence |
| --- | --- | --- | --- |
| PWR01 | C | **E:** Check repetitive device voltage including parasitic overshoot, line tolerance and surge behavior. MOV clamp voltage is conditional on current and waveform. | D/A/S/M: worst stress at device terminals and specified surge conditions. |
| PWR02 | C | **E:** Calculate conduction losses at hot device parameters and switching losses at actual gate voltage, current and transition conditions. Cold headline ratings understate dissipation. | D/A/M: loss budget corroborated by waveforms and thermal evidence. |
| PWR03 | C | **E:** Evaluate safe operating area for startup, current limit, detuned load and faults. A rated steady current is not a short-circuit survival rating. | D/A/M: stress trajectory versus device SOA or qualified fault limits. |
| PWR04 | C | **E:** Verify the soft-switching envelope across pans, bus phase, temperature and control modes. Inductive steady operation does not prove safe startup or deep phase shift. | S/M: phase and switch-node waveforms over the operating matrix. |
| PWR05 | C | **E:** Review body-diode recovery and IGBT tail behavior for the selected device technology. A fast-diode marketing label does not authorize arbitrary hard commutation. | D/A/M: selected-device application limits and turn-on/turn-off evidence. |
| PWR06 | H | **P:** Put snubbers across the nodes they damp with minimal connection inductance. Check their pulse energy, RMS dissipation and the ringing they actually suppress. | A/L/M: waveform comparison and snubber temperature. |
| PWR07 | C | **E:** Check tank components and terminals against resonant voltage/current, not just bus voltage or wall power. Reactive circulating energy can produce much greater stress. | A/S/M: tank voltage, current and power-factor envelope. |
| PWR08 | H | **E:** Assess parasitic inductance and current sharing through coil wiring, capacitor banks and connector geometry. Include the assembled cable path. | L/A/M: physical harness model and individual-branch checks where necessary. |
| PWR09 | C | **E:** Test turn-off with residual tank energy and restart at adverse phases. Disable does not instantaneously remove stored inductive energy. | S/M: fault interruption, current decay and restart waveforms. |
| PWR10 | C | **E:** Rate bus, tank and discharge hardware for the selected architecture's energy. A low-energy film bus and a PFC electrolytic bank require different fault containment. | A/D: energy inventory and coordinated interrupt/discharge paths. |

## 6 Grounding stackup and return paths

Keep fast signals over a continuous reference within their electrical domain and provide a nearby return transition when changing layers. A gap can force return current into a larger loop; functional placement often avoids splitting a shared reference. [TI SCAA082A, pp. 10–16](https://www.ti.com/lit/an/scaa082a/scaa082a.pdf#page=10) illustrates these mechanisms. This does not authorize connecting separate isolation domains.

| ID | Priority | Rule and failure mechanism | Acceptance evidence |
| --- | --- | --- | --- |
| GND01 | H | **S:** Route sensitive/fast signals over a continuous appropriate reference. Plane slots, antipad chains and cutouts can interrupt the return. | L: view each signal together with its adjacent reference copper. |
| GND02 | H | **E:** Prefer functional separation over arbitrary analog/digital ground splits within one domain; follow device-specific ground instructions. | D/L/M: return map and noise at analog references. |
| GND03 | H | **E:** Pair signal layer changes with a credible local return path in the same domain. A remote stitch enlarges the transient loop. | L/A: via-pair geometry and reference-layer assignment. |
| GND04 | C | **E:** Preserve isolation boundaries on every copper layer, including plane fills, stitching, mounting pads and shields. Internal copper can defeat the intended barrier. | D/L: all-layer domain and dielectric/spacing review. |
| GND05 | H | **E:** Choose dielectric spacing and reference assignments before critical routing. Layer count alone says little about loop inductance or impedance. | F/L/A: fabricator-approved stackup and routed-layer rules. |
| GND06 | H | **E:** Check signal edges and source/load impedance before demanding length matching. Add termination where ringing needs it; avoid cosmetic serpentine routing. | D/A/M: edge time, flight time, ringing and timing margin. |
| GND07 | H | **E:** Keep noisy power-return currents out of comparator, divider and sensor reference connections. One net label does not mean equipotential copper. | L/A/M: shared-path impedance and reference movement. |
| GND08 | H | **E:** Eliminate accidental floating copper; connect intentional shields with a defined impedance and function. Uncontrolled islands can couple or resonate. | L: filled-zone connectivity review after final pour. |
| GND09 | H | **E:** Evaluate capacitance from switch nodes to planes, heatsinks and chassis. Larger copper can reduce resistance while increasing common-mode current. | A/S/M: overlap capacitance estimate and emissions/leakage evidence. |
| GND10 | Q | **E:** Document every intentional net tie, chassis connection and shield termination. Assembly and later routing must preserve the intended return topology. | L/F: controlled drawings and connector/shield instructions. |

## 7 Current voltage and temperature sensing

Kelvin sensing avoids including load-carrying copper resistance in the measured shunt value; reference-ground displacement can still introduce error. [TI's low-side sensing layout article](https://www.ti.com/document-viewer/lit/html/SSZT805/GUID-5F278960-BA94-4362-9099-87ABC753A4D6) demonstrates both effects. The shunt and CT checks below apply only where that sensor is present.

| ID | Priority | Rule and failure mechanism | Acceptance evidence |
| --- | --- | --- | --- |
| SEN01 | C | **S:** Take shunt sense connections from the intended sensing terminals rather than remote power copper. Shared load-path resistance changes trip current and measured gain. | D/L/A: Kelvin terminal map and parasitic-error budget. |
| SEN02 | H | **E:** Route differential sense pairs together and balance their filtering. Unequal parasitics convert common-mode switching noise to a differential error. | L/A/M: mismatch budget and in-circuit noise capture. |
| SEN03 | C | **E:** Check amplifier/comparator common-mode and differential ranges during switching, startup and faults. Nominal input voltage alone misses fast overrange. | D/A/M: pin extremes and recovery behavior. |
| SEN04 | C | **E:** Rate divider resistors for individual working voltage, pulse voltage and temperature. Total resistance and total wattage do not prove each resistor survives. | D/A: per-resistor stress at tolerance and fault corners. |
| SEN05 | H | **E:** Keep high-impedance nodes away from switch copper and contamination paths. Leakage and capacitive injection can exceed a precision error budget. | L/A/M: leakage/coupling estimate and humidity/noise verification. |
| SEN06 | C | **E:** Check CT saturation, burden power, polarity and open-secondary behavior. Verify bandwidth and phase error for both protection and phase detection. | D/A/M: CT/burden waveform over current and frequency corners. |
| SEN07 | C | **E:** Verify which fault currents actually traverse the sensor. A perfectly accurate tank CT can remain blind to bridge shoot-through. | L/A: current-path coverage map with explicit blind cases. |
| SEN08 | H | **E:** Lay out RTD excitation, sense and reference paths to preserve the chosen two-, three- or four-wire method. Check connector/contact resistance and self-heating. | D/L/A/M: terminal map and end-to-end temperature error. |
| SEN09 | C | **E:** Test sensor open, short, disconnected cable and supply loss independently of nominal readings. Include fault-chain operation during brownout. | S/M: injected faults and final hardware-disable result. |
| SEN10 | H | **E:** Place thermal sensors for the temperature they must detect, with quantified lag and heat-path error. A distant sensor can read safely while a junction overheats. | A/M: correlation to the critical hot spot during ramps and fan faults. |

## 8 Analog references ADCs and comparators

SAR sampling can disturb its driving circuit; excessive input RC slows recovery. Reference inputs can need local charge storage and a driver stable with that load. See [ADI's SAR-input treatment](https://www.analog.com/en/resources/technical-articles/ltspice-simulating-sar-adc-analog-inputs.html) and [reference design treatment](https://www.analog.com/en/resources/analog-dialogue/articles/precision-successive-approximation-adcs.html). Use MAX31865-specific guidance for its different converter architecture.

| ID | Priority | Rule and failure mechanism | Acceptance evidence |
| --- | --- | --- | --- |
| ANA01 | H | **E:** Allocate error across sensor, divider, reference, amplifier, converter, wiring and temperature. Nominal ADC bit depth is not system accuracy. | A/D/M: end-to-end error and noise budget. |
| ANA02 | H | **S:** Check acquisition settling for the converter's actual input architecture. Filtering must not leave the sampled input incompletely settled. | D/A/S/M: source impedance and settling at the selected sample rate. |
| ANA03 | H | **E:** Set analog anti-alias filtering from interference spectra and sampling behavior. A digital filter cannot undo noise that has already aliased. | A/M: frequency response and interference injection. |
| ANA04 | H | **S:** Place any required reference reservoir near the reference input and verify source stability with that capacitive load. | D/L/M: reference transient and oscillation checks. |
| ANA05 | H | **E:** Keep reference and divider returns away from pulsed power and logic currents. Their movement changes both measured values and protection thresholds. | L/A/M: reference-ground drop and threshold shift. |
| ANA06 | C | **E:** Bound comparator delay at minimum relevant overdrive and maximum load/temperature. A typical headline delay is not a worst-case fault-latency bound. | D/A/M: delay versus fault amplitude and operating corners. |
| ANA07 | C | **E:** Choose hysteresis above the credible noise while preserving required trip and reset thresholds. Include divider and reference tolerances. | A/S/M: chatter, trip and reset distributions. |
| ANA08 | C | **E:** Budget every RC filter and blanking interval into protection response time. Noise rejection can conceal a rapidly growing fault. | A/M: input fault to actual current extinction. |
| ANA09 | H | **E:** Check open-drain pulls, logic thresholds, output loading and analog-output stability. Slow or ringing edges can cause inconsistent decisions downstream. | D/A/M: receiving-pin waveforms and margins. |
| ANA10 | H | **E:** Test thermal gradients, supply ripple and switching noise as analog error sources. Room-temperature calibration does not remove operating-condition drift. | M: calibrated input checks during power and thermal sweeps. |

## 9 Hardware protection and sequencing

| ID | Priority | Rule and failure mechanism | Acceptance evidence |
| --- | --- | --- | --- |
| PRO01 | C | **E:** Keep fault detection and gate-disable routing independent of ordinary MCU software where required. Verify the complete path through latches and driver inputs. | L/M: fault injection with firmware stalled or outputs held active. |
| PRO02 | C | **E:** Establish safe outputs with each safety IC unpowered, brownout or disconnected. A family suffix can determine whether an isolator fails high or low. | D/S/M: rail-sequence and disconnect tests. |
| PRO03 | C | **E:** Bound the whole detection-to-current-extinction interval. Include sensor, filter, comparator, isolator, latch, driver, device and residual current paths. | A/M: worst-case latency and corresponding energy/stress. |
| PRO04 | C | **E:** Verify fault latching, reset permissions and restart inhibition at partial supply. A reset pulse must not briefly authorize switching during a continuing fault. | S/M: simultaneous fault/reset and brownout tests. |
| PRO05 | C | **E:** Keep safety inputs out of strongly coupled switching routes and give them defined bias states. An open connector must have a specified outcome. | L/D/M: bias/loading review and noise/disconnection tests. |
| PRO06 | C | **E:** Coordinate fuse voltage, breaking capacity, time-current behavior, ambient derating and surge endurance with available fault current. | D/A/F: selected fuse and holder assessment against the actual supply/fault envelope. |
| PRO07 | C | **E:** Check surge-protector aging, thermal disconnection and failure paths. Repeated surges can change leakage and end-of-life behavior. | D/A/M: surge coordination and credible end-of-life fault assessment. |
| PRO08 | C | **E:** Verify discharge time at maximum capacitance, maximum resistance and relevant failed branches. Label/prove residual voltage at accessible service points. | A/M: worst-case decay, resistor stress and loss-of-power behavior. |
| PRO09 | C | **E:** Check watchdog and supervisor action under slow ramps and noisy rails. The MCU, latch and gate driver can have different reset/UVLO boundaries. | D/S/M: ramp, dip and stalled-firmware tests. |
| PRO10 | C | **E:** Demonstrate independent overtemperature intervention with its real sensor or cutoff mounting. Verify response lag and what loses power when it operates. | L/M: mounted thermal-fault test and safe energy-decay result. |

## 10 Thermal placement and cooling

Junction-to-ambient thermal resistance describes a particular test-board environment. It should not be treated as a fixed property of an IC mounted anywhere. Junction-to-top characterization parameters also have conditions and are not ordinary series resistances. [TI SPRA953D, sections 1–3](https://www.ti.com/lit/an/spra953d/spra953d.pdf#page=2) explains these distinctions. [Nexperia AN90003, sections 3–4](https://assets.nexperia.com/documents/application-note/AN90003.pdf) illustrates PCB heat spreading; its LFPAK results are not TO-247 design limits.

| ID | Priority | Rule and failure mechanism | Acceptance evidence |
| --- | --- | --- | --- |
| THM01 | C | **E:** Map every significant heat source, including rectifiers, copper, shunts, snubbers, resistors, chokes and auxiliary supplies. Ignoring small distributed sources understates enclosure ambient. | A/M: loss inventory and total heat balance. |
| THM02 | C | **S:** Match thermal metrics to their test conditions. Do not turn datasheet RθJA into a production junction estimate without a matching thermal model. | D/A/M: stated heat paths and validated junction-estimation method. |
| THM03 | C | **E:** Model the complete junction-case-interface-sink-air path, including shared heatsink heating. Device dissipation alone does not set junction temperature. | A/S/M: thermal network and maximum temperatures. |
| THM04 | H | **E:** Keep electrolytics, references and low-temperature parts away from hot components and exhaust where practical. Quantify the local temperature when proximity is necessary. | L/A/M: placement review, local ambient and lifetime/error effects. |
| THM05 | H | **E:** Specify real thermal-interface area, thickness, compression and mounting load. An ideal CAD contact does not prove low interface resistance. | D/F/M: mounting specification and assembled thermal performance. |
| THM06 | C | **E:** Include fan stall, blocked intake, grease/dust buildup and reduced airflow where relevant. Free-air fan rating is not assembled airflow. | A/M: fan/system operating point and cooling-fault tests. |
| THM07 | H | **E:** Check transient thermal response for bursts, warm restart and short overloads. Peak power times steady thermal resistance can misrepresent short pulses. | D/A/M: transient thermal model and temperature/time records. |
| THM08 | H | **S:** Treat added copper and thermal vias as a system heat path with diminishing benefit. Check destination copper and nearby heat sources. | L/S/M: thermal-spreading comparison in the actual stackup. |
| THM09 | C | **E:** Set laminate, solder, connector and insulation temperatures from selected materials. Tg alone is not a continuous operating-temperature rating. | D/F/M: actual material limits and worst hot-spot temperatures. |
| THM10 | H | **E:** Corroborate thermal imaging using emissivity-controlled targets or contact measurements. Shiny copper and sinks can display reflected temperatures. | M: calibration, uncertainty and repeatable thermal-soak evidence. |

## 11 Capacitors resistors and magnetics

Film-capacitor allowable AC voltage/current depends on frequency and heating; a DC rating alone is insufficient. [TDK general technical information, sections on AC operation and thermal behavior](https://www.tdk-electronics.tdk.com/download/537974/480aeb04c789e45ef5bb9681513474ba/pdf-generaltechnicalinformation.pdf) provides the basis. Resistor pulse qualification needs peak power, duration, repetition and voltage as well as average power, as described in [Vishay technical note 28810](https://www.vishay.com/docs/28810/pulseloadhandling.pdf).

| ID | Priority | Rule and failure mechanism | Acceptance evidence |
| --- | --- | --- | --- |
| PAS01 | C | **S:** Select resonant/DC-link capacitors against frequency-dependent AC voltage and RMS current, plus pulse slope and temperature. | D/A/M: exact-series curves and measured in-circuit stress. |
| PAS02 | H | **E:** Verify sharing in parallel capacitors from impedance and routing. Summing individual current ratings does not prove equal current distribution. | L/A/M: branch-current or temperature corroboration. |
| PAS03 | H | **E:** Calculate electrolytic ripple heating and useful life from the selected series' model at local temperature. Do not apply an unqualified universal lifetime rule. | D/A/M: ripple spectrum, case/local temperature and life calculation. |
| PAS04 | H | **E:** Allow capacitor vents and required body clearances, and retain heavy parts against vibration. Glue or brackets must not obstruct vents. | D/L/F: mechanical and assembly drawings. |
| PAS05 | C | **E:** Use appropriate safety-certified capacitors across line or between live and accessible/earth domains. A high DC-voltage MLCC is not an X/Y replacement. | D/L: exact safety class and connection review. |
| PAS06 | H | **S:** Check resistor single-pulse, repetitive-pulse and working-voltage limits separately from steady wattage. | D/A: stress waveform versus exact resistor limits. |
| PAS07 | H | **E:** Account for magnetic saturation at current peaks, bias and hot operation, and winding/core losses over frequency. Inductance measured at small signal is insufficient. | D/A/M: inductance/current and thermal evidence. |
| PAS08 | H | **E:** Keep precision/sensor loops away from inductor fringe fields and coil leads. Orientation and return-loop area change induced error. | L/S/M: magnetic coupling inspection and powered noise test. |
| PAS09 | H | **E:** Check thermal gradients across precision resistor networks and the shunt. Temperature coefficients can change threshold ratios and gain. | D/A/M: hot-ratio or threshold drift. |
| PAS10 | Q | **E:** Validate solder and wave/reflow process suitability for every passive. Tall films, electrolytics and chokes may require a different assembly step. | D/F: process limits and approved build sequence. |

## 12 EMI RF and external interfaces

Common-mode and differential-mode noise require identifying different current paths. Switching edges and parasitic resonances, as well as the fundamental, shape the emissions spectrum. [Würth ANP044e, pp. 2–4](https://www.we-online.com/components/products/media/109026#page=2) supplies these principles. Its DC/DC examples inform the review method, not a cooker's compliance limits.

| ID | Priority | Rule and failure mechanism | Acceptance evidence |
| --- | --- | --- | --- |
| EMI01 | H | **S:** Draw differential and common-mode noise paths separately, including chassis and cables. A filter aimed at the wrong path may show little benefit. | L/A/M: path map and separated noise measurements. |
| EMI02 | H | **E:** Separate dirty and filtered wiring/copper at the mains entry. Capacitive or magnetic coupling around the filter can bypass it. | L/M: physical filter review and conducted-emissions comparison. |
| EMI03 | H | **E:** Locate interface filtering/protection at the actual cable boundary and provide a defined return. Long unprotected internal routes admit or radiate interference. | L/M: cable-entry geometry and immunity testing. |
| EMI04 | H | **E:** Evaluate filter damping and converter interaction across operating points. An undamped input resonance can cause oscillation or excess capacitor current. | A/S/M: impedance/stability and load-step evidence. |
| EMI05 | C | **E:** Check total leakage/coupling through Y capacitors, supply modules and isolation parasitics against the governing product requirement. | D/A/M: assembled leakage and insulation-system assessment. |
| EMI06 | H | **E:** Rate ESD/surge components for waveform and residual clamping at protected pins. Include interconnect inductance and the actual discharge return. | D/L/M: pin stress and interface immunity tests. |
| EMI07 | H | **E:** Preserve the selected ESP32 module's antenna keepout in copper, components, chassis and nearby cables. Bare-chip RF guidance is not a substitute for module guidance. | D/L/M: module-specific keepout and enclosed RF performance. |
| EMI08 | H | **E:** Check USB/SPI and other edges for impedance, return continuity, termination and connector loading as applicable. Protocol clock rate alone does not define signal bandwidth. | D/A/M: receiving-pin integrity and error-free transfers. |
| EMI09 | H | **E:** Test emissions and immunity with representative pan, coil, harness, sink, enclosure and control modes. A quiet bare board may become noisy after assembly. | M: documented precompliance test matrix and representative final tests. |
| EMI10 | H | **E:** Tune gate speed, snubbers and filtering using simultaneous loss, stress and noise evidence. Improving one waveform can worsen heat or another failure mode. | M/A: recorded tradeoff and operating-margin comparison. |

## 13 Insulation and assembled product boundaries

These rows assess whether the configured spacing rules cover the actual product. Determine numerical limits from the applicable standard edition and insulation system, selected components and material records; no generic PCB spacing table can establish all of them.

| ID | Priority | Rule and failure mechanism | Acceptance evidence |
| --- | --- | --- | --- |
| ISO01 | C | **E:** Establish working voltage, transient category, pollution conditions, material group, altitude and required insulation class for each barrier. | D/A: requirement matrix and governing clauses. |
| ISO02 | C | **E:** Inspect the full assembled clearance/creepage path: PCB, component body, solder, leads, connectors, wires, screws and sink. | D/L: three-dimensional path review including tolerances. |
| ISO03 | C | **E:** Verify slots with the actual milling geometry, tolerances and applicable creepage rules. A nominal slot is not automatically an effective barrier. | D/F/L: manufactured slot and minimum path measurement. |
| ISO04 | C | **E:** Do not credit solder mask or conformal coating as insulation without a qualified system and process basis. Include coverage, contamination and repair conditions. | D/F/M: insulation-system qualification and controlled application. |
| ISO05 | C | **E:** Check PCB material CTI, thickness, flammability and thermal suitability from order-specific evidence where required. A generic FR-4 label does not settle these properties. | D/F: laminate identification and certificates/requirements. |
| ISO06 | C | **E:** Check isolator working voltage, lifetime and surge/withstand ratings for the application separately. A short-duration kilovolt test rating is not continuous working voltage. | D/A: package-specific barrier assessment. |
| ISO07 | C | **E:** Treat thermal tabs and heatsinks as electrical conductors until their potential and insulation are established. Check pads, bushings, screws and mounting pressure. | D/L/M: insulation and mounted dielectric tests where required. |
| ISO08 | C | **E:** Provide protective-earth bonding or a justified alternative insulation architecture for accessible conductive parts. Keep the bond mechanically reliable where present. | D/L/M: bonding design, continuity and fault tests. |
| ISO09 | C | **E:** Prevent cable motion, connector errors and contamination from crossing the boundary. Consider sensor/probe accessibility and kitchen liquid ingress. | L/F/M: worst-position harness and ingress/fault assessment. |
| ISO10 | C | **E:** Define final dielectric, leakage and protective-bond test requirements for the assembled product. A supplier module certificate covers only its stated scope. | D/F/M: release and production test specification with limits. |

## 14 Fabrication and footprint integrity

Fabrication minima depend on the process and selected options. Reconfirm the actual supplier's current capability and order drawing; [JLCPCB's capability page](https://jlcpcb.com/capabilities/pcb-capabilities) is a current starting point for the repository's proposed supplier. Hole and registration tolerances also affect manufacturability, as illustrated by [Eurocircuits' tolerance guidance](https://www.eurocircuits.com/technical-guidelines/understanding-manufacturing-tolerances-on-a-pcb/tolerances-on-a-pcb/) and [solder-mask guidance](https://www.eurocircuits.com/technical-guidelines/pcb-design-guidelines/soldermask/). No Eurocircuits number is adopted as a JLCPCB requirement here.

| ID | Priority | Rule and failure mechanism | Acceptance evidence |
| --- | --- | --- | --- |
| FAB01 | C | **E:** Validate each footprint against the exact package drawing and pin numbering. Similar package names can hide skipped pins or different lead assignments. | D/L: pin-by-pin and dimensional review with drawing revision. |
| FAB02 | H | **E:** Specify finished copper thickness per layer and minimum via plating. Do not leave inner copper at a supplier default inconsistent with thermal calculations. | F/A: approved fabrication drawing and order options. |
| FAB03 | H | **E:** Use trace/space capability for the actual copper weight and stackup. Heavy copper changes etching limits and finished dimensions. | F/L: current supplier capability plus manufacturing margin. |
| FAB04 | H | **E:** Design holes around maximum lead dimensions, finished-hole tolerance, plating and solder process. Tool diameter and finished hole are different quantities. | D/F/A: fit tolerance stack and drill table. |
| FAB05 | H | **E:** Check annular-ring survival under drill registration, including inner layers. Pad diameter minus nominal drill alone overstates worst-case ring. | F/A/L: tolerance-adjusted rings and supplier acceptance. |
| FAB06 | H | **E:** Reconcile solder-mask expansion, dams and registration with fine-pitch footprints. Unmanufacturable dams can produce unexpected exposed copper. | F/L: final mask preview and assembler review. |
| FAB07 | H | **E:** Specify filled/capped vias where required, especially under soldered pads. Plain open vias can wick solder and change stand-off. | D/F/L: via treatment and fabrication notes. |
| FAB08 | H | **E:** Review stackup symmetry and copper distribution for bow, twist and plating uniformity. Preserve electrical keepouts when adding balancing copper. | F/L: copper distribution and panel review. |
| FAB09 | H | **E:** Check board profile, plated/unplated slots, edge tolerances and fabrication tabs against mounting and insulation geometry. | F/A/L: mechanical drawing and tolerance chain. |
| FAB10 | C | **E:** Inspect final Gerbers/drills/stackup and netlist from the exact release output. CAD setup does not prove the exported manufacturing data is correct. | L/F: output review, layer order and fabrication electrical-test basis. |

## 15 Assembly soldering and mechanical reliability

Soldered exposed pads need package-specific land, via and stencil decisions; they are part of the thermal path. [TI PowerPAD SLMA002H, sections 2.1–2.5](https://www.ti.com/lit/an/slma002h/slma002h.pdf) gives relevant process principles for those packages. Board bending can crack ceramic capacitors; location and orientation affect risk, as described by [Murata's MLCC layout guide](https://article.murata.com/en-eu/article/layout-helps-prevent-chip-mlcc-from-cracking).

| ID | Priority | Rule and failure mechanism | Acceptance evidence |
| --- | --- | --- | --- |
| ASM01 | H | **E:** Co-design paste apertures and stencil thickness with the assembler for each package. Generic full-pad paste can cause floating, bridging or inadequate joints. | D/F: stencil drawing and first-article solder evidence. |
| ASM02 | H | **S:** Solder exposed thermal pads where the selected package requires it and control via/paste interaction. | D/F/M: thermal-pad assembly and inspection criteria. |
| ASM03 | H | **E:** Balance solder heating on small passives while preserving electrical/thermal requirements. Unequal copper connections can encourage tombstoning. | L/F: land/copper review and first-article yield. |
| ASM04 | H | **E:** Decide thermal relief versus solid power-pad connection using both current and solder-process needs. Do not solve solderability by creating an unqualified hot neck. | A/F/M: joint formation and conductor temperature. |
| ASM05 | H | **S:** Keep stress-sensitive MLCCs away from high-strain locations and review orientation against the actual board flex. | L/F/M: depanel, connector insertion and mounting strain review. |
| ASM06 | H | **E:** Support heavy films, chokes, modules and terminals against vibration and connector forces. Electrical leads should not carry every mechanical load. | L/A/M: restraints, service loads and vibration evidence. |
| ASM07 | H | **E:** Include screw tightening, cable bend and thermal expansion in board strain. Check nearby ceramic parts, solder joints and isolation gaps. | A/L/M: assembly sequence and mechanical load tests. |
| ASM08 | Q | **E:** Provide polarity, pin-one and orientation markings visible during assembly and service. Avoid relying on silkscreen hidden beneath the fitted part. | L/F: top/bottom assembly drawing and operator review. |
| ASM09 | H | **E:** Qualify reflow/wave/selective solder profiles against every fitted part, including moisture-sensitive modules and hot/heavy copper areas. | D/F/M: measured board thermal profiles and handling instructions. |
| ASM10 | H | **E:** Make cleaning, flux residue, coating and rework compatible with high-impedance sensing and insulation. A repaired board must retain its qualified condition. | F/M: cleanliness, coating and controlled rework process. |

## 16 Test evidence and release control

| ID | Priority | Rule and failure mechanism | Acceptance evidence |
| --- | --- | --- | --- |
| TST01 | C | **E:** Provide usable probe access to gate-source/emitter, supplies, current and fault signals with the correct local references. Probe pads must preserve insulation and loop integrity. | L/M: probe method, bandwidth and connection review. |
| TST02 | C | **E:** Plan staged bring-up with defined current/energy limits and stop conditions. Verify low-voltage operation and fault inhibition before increasing bus energy. | D/M: executed bring-up record for the identified build. |
| TST03 | H | **E:** Measure where the requirement applies, such as at the IC supply pins or device terminals. Remote test points can conceal interconnect overshoot and droop. | M: measurement location and uncertainty for each result. |
| TST04 | H | **E:** Correlate simulations with independent measurements and plausible parameter bounds. A model fitted to one operating point does not prove all corners. | A/S/M: correlation and residual-error report. |
| TST05 | C | **E:** Test deterministic worst cases in addition to statistical cookware/load sampling. Rare startup or fault conditions can evade a large random sweep. | A/M: boundary matrix and fault-injection coverage. |
| TST06 | H | **E:** Verify models and geometry against an external oracle where possible. Two implementations agreeing can share the same sign, unit or coordinate error. | A/M: pcbnew/physical measurement or independent reference cases. |
| TST07 | H | **E:** Preserve test revision, instrument setup, calibration, environmental conditions and raw data. A bare number cannot support a repeatable release decision. | M: reproducible evidence record linked to the scored rule. |
| TST08 | C | **E:** Build production tests around consequential assembly faults: wrong values/polarity, open sense leads, unsafe thresholds and failed disable paths. | F/M: fault coverage, limits, test time and traceability. |
| TST09 | H | **E:** Reopen checks affected by any component, copper, stackup, firmware timing, cooling or harness change. A previous pass belongs to the previous configuration. | L: change-to-test impact record. |
| TST10 | C | **E:** Release matching BOM, placement, assembly, fabrication and test packages. Resolve C failures and unknowns through evidence before claiming readiness. | F/L: controlled release manifest and closed critical-check records. |

## Worked examples and quantitative checks

These are illustrative calculations with assumed inputs, not measured Temper results or newly adopted limits.

### Trace width resistance and temperature

For a uniform copper segment, use SI units:

```text
R20 = rho20 × length / (width × thickness)
R(T) ≈ R20 × [1 + alpha × (T − 20 °C)]
P_DC = I_RMS² × R(T)
V_drop = I × R(T)

Illustrative copper constants:
rho20 = 1.724 × 10⁻⁸ Ω·m
alpha ≈ 0.00393 / °C
```

With 20 mm length, 2 mm width, 35 µm copper and 20 A RMS, resistance is about 4.93 mΩ at 20 °C and loss is about 1.97 W. At an assumed conductor temperature of 80 °C, resistance is about 6.09 mΩ and loss about 2.43 W. Doubling width to 4 mm halves resistance and loss for the same uniform segment. It does **not** prove that temperature rise halves: cooling and current crowding also change.

For frequency-dependent resistance, heating is better represented by summing `I_RMS,n² × R_AC,n` over waveform components. For a short pulse where loss and boundary assumptions permit an adiabatic approximation, temperature rise follows deposited energy divided by the conductor's heat capacity. For longer pulses use a transient thermal model.

Trace temperature requires the power distribution and thermal boundary. Use an applicable IPC-2152 method or a validated thermal model, then verify in the assembled enclosure. Set `maximum conductor temperature` from the weakest nearby material or component and the life requirement; derive the allowable rise from local ambient. Neither 10 °C, 20 °C nor 40 °C is a universal acceptance limit.

The legacy [trace-width calculation](TRACE_WIDTH_CALCULATIONS.md) states `I = k × deltaT^0.44 × A^0.725`, but its displayed rearrangement for width omits the necessary exponent. Algebraically, within that model:

```text
A = [I / (k × deltaT^0.44)]^(1/0.725)
width = A / thickness
```

Use consistent units required by that empirical model. The old coefficients are not a substitute for a geometry-appropriate IPC-2152 assessment. Recheck derived widths and their assumptions before treating the historical table as a present requirement; this rubric does not silently replace its values.

### Decoupling charge and mounted inductance

The first-order charge estimate is `C_effective ≥ deltaI × duration / allowed_deltaV`. An assumed 100 mA pulse lasting 200 ns with a 20 mV capacitive-droop budget needs at least 1 µF **effective** local capacitance if it alone supplies that pulse. Include regulator contribution, ESR, mounted inductance and rail tolerance for a realistic budget.

`deltaV_L = L × di/dt` explains why placement matters. An assumed 1 nH loop with a 100 mA change in 1 ns creates a 100 mV inductive contribution. A capacitor's body touching the IC is not sufficient if its ground path takes a detour. Review pad-to-pin geometry, adjacent plane reference, vias and shared return impedance.

Use `Z_target ≈ allowed_deltaV / deltaI` as an initial PDN impedance budget, then evaluate the relevant frequency range and response. Avoid treating 100 nF per IC or a fixed 2 mm distance as universal requirements. A package-specific distance can be an automated screening target once its basis is recorded.

### Gate supply bootstrap and turn-off

For a bootstrap supply, use:

```text
charge_required = gate charge + driver consumption during on-time
                  + leakage during on-time + other floating-side loads
C_boot_effective ≥ charge_required / allowed_bootstrap_droop
```

Include initial voltage after charging losses, negative-bias arrangements where fitted, tolerance, recharge impedance, timing and UVLO margin. For an illustrative gate charge of 140 nC and a 0.5 V droop allocation, gate charge alone needs 0.28 µF effective capacitance; the other terms increase it. This does not establish the correct capacitor for either Temper architecture.

For protection, add all worst-case delays and verify when current actually extinguishes. A comparator's 40 ns typical value is only one term. Confirm device survival against the resulting current and energy, not just against the time at which a logic pin changes state.

### Switch-node coupling

`i_coupled = C_parasitic × dv/dt`. An assumed 20 pF path at 10 V/ns produces a 0.2 A transient displacement current. Trace-to-plane or switch-to-sink capacitance can therefore matter even though it carries no DC load. Reducing resistance by enlarging switch copper can increase this current; evaluate the tradeoff with actual stress and EMC evidence.

## Temper checks to apply first

These priorities follow the documented architecture and known review gaps. They are review actions, not findings from a new native-layout inspection.

1. Identify the selected full-bridge candidate and maintained units with their matching source, resolved BOM, native board and stackup. Exclude separate research snapshots and historical designs from current acceptance decisions.
2. Recalculate current and conductor heating for mains, bridge, bus, tank, shunt and connector paths. Include all necks, vias and solder connections; use actual current waveforms and manufactured copper.
3. Review each UCC21550 supply channel's bypassing and return, plus driver-to-device gate loops, gate-resistor placement, negative transients and bootstrap recharge in every control mode.
4. For a full bridge, verify local commutation loops and that a bus-fault detector covers shoot-through paths the tank CT cannot see.
5. Bound fault latency through filtering, comparator, isolation, latch and driver to current extinction. Verify default outputs and behavior with either side unpowered.
6. Validate resonant film-capacitor AC voltage/current versus frequency and temperature. Do not accept summed bank current ratings without current-sharing evidence.
7. Map switch tabs, rectifier mounting, sink insulation and common-mode capacitance, then check the full cooling path at line/pan/duty corners and cooling faults.
8. Review MAX31865/probe accuracy and RTD fault behavior separately. Place precision references and sensor return paths to avoid shared gate/power currents and thermal gradients.
9. Resolve exact logic and reference orderables in the companion datasheet guidance before approving footprints or sourcing substitutions.
10. Reconfirm the fabrication option set, inner copper and assembly process against the [current fabrication profiles and check catalog](../../zapote/CHECKS.md). Revalidate supplier limits for the actual order and record the assembly process.

## Review record template

Copy this record for each applicable rule instance. Link evidence to the build identity instead of accumulating unexplained pass marks.

| Field | Entry |
| --- | --- |
| Rule and instance | e.g. DEC01, driver U1 high-side supply |
| Artifact identity | Board/schematic/BOM revision and content hashes |
| Applicability | Circuit/process reason; architecture |
| Priority and score | C/H/Q; 0–4, U or justified N/A |
| Requirement | Exact limit, units, operating conditions and source |
| Observation | What the design actually does |
| Evidence class | D/L/A/S/M/F, with document or raw-data links |
| Margin | Worst result versus limit, including uncertainty |
| Closure | Required action or verification, owner, resulting evidence |

## Automation candidates

Turn inexpensive, well-defined checks into design tools after the rule inputs are authoritative. Implement new logic in the appropriate existing Rust crate with thin bindings, following this repository's migration policy. This rubric itself adds no checker or second constraint source.

| Candidate | Inputs and useful output | What it cannot establish alone |
| --- | --- | --- |
| Decoupling connectivity and geometry | Exact supply-pin/return metadata; required caps; routed pad-to-pin lengths, vias and shared necks | Effective capacitance, mounted inductance and rail-transient performance without valid models or measurements |
| Conductor bottleneck report | Current waveforms, actual copper geometry, tolerance and plating; segment/via resistance and loss | Final temperature without thermal boundaries |
| Critical return-path report | Stackup, route reference assignment and domain map; gaps, return transitions and shared segments | Full field behavior from geometric distance alone |
| Switching/gate-loop extraction | Explicit state/topology paths and component pin identity; loop paths and layer changes | Inductance from copper area or a bounding box |
| Domain and part reconciliation | Resolved netlist, fitted BOM and exact package pin map; mismatches and barrier crossings | Standard sufficiency or assembled creepage beyond supplied geometry |
| Threshold and timing budget | Exact references, tolerances, delays, RC and logic limits; bounded trip/reset and latency | Dynamic sensor/device behavior omitted from the model |
| Thermal evidence ledger | Loss sources, materials, cooling assumptions and validated temperatures | Correctness of an unvalidated heat model |
| Fabrication and assembly report | Supplier option set, drawings and manufacturing outputs; unsupported holes, masks, vias and package mappings | Production yield without process evidence |

For any new geometric checker, include asymmetric, non-orthogonal rotation cases and an external KiCad oracle. For board measurements, follow AGENTS.md instrument setup and provenance rules. A geometric screening pass and a physics-model pass remain separate evidence from representative hardware verification.

## Primary source register

The narrow sourced principles above are paraphrased. Device-specific numbers and package advice are in the companion inventory. Supplier examples support review topics; actual acceptance values must come from the chosen order/process.

| Source | Passage or section | Supported use |
| --- | --- | --- |
| [TI Analog Engineer's Pocket Reference SLYW038D](https://www.ti.com/seclit/eb/slyw038d/slyw038d.pdf) | Printed pp. 71–72, PCB and Wire | Trace-heating chart context and resistance; not appliance insulation approval |
| [ADI MT-101](https://www.analog.com/media/en/training-seminars/tutorials/MT-101.pdf) | pp. 1–4 | Local bypass, reservoir and capacitor-parasitic principles |
| [TI SCAA082A](https://www.ti.com/lit/an/scaa082a/scaa082a.pdf) | pp. 10–16 | Reference continuity, split-plane pitfalls and return-loop geometry |
| [TI SPRA953D](https://www.ti.com/lit/an/spra953d/spra953d.pdf) | Sections 1–3 | Thermal-metric conditions and misuse |
| [Nexperia AN90003 revision 5](https://assets.nexperia.com/documents/application-note/AN90003.pdf) | Sections 3–4 | Copper heat-spreading behavior; package-specific examples |
| [TI low-side current sensing layout](https://www.ti.com/document-viewer/lit/html/SSZT805/GUID-5F278960-BA94-4362-9099-87ABC753A4D6) | Kelvin and reference-ground discussion | Sense-path parasitic errors |
| [ADI SAR analog input simulation](https://www.analog.com/en/resources/technical-articles/ltspice-simulating-sar-adc-analog-inputs.html) | Input RC and switched-capacitor discussion | Noise-versus-settling tradeoff |
| [ADI precision SAR reference design](https://www.analog.com/en/resources/analog-dialogue/articles/precision-successive-approximation-adcs.html) | Reference drive and local reservoir discussion | Reference transient and stability checks |
| [TDK film capacitor technical information](https://www.tdk-electronics.tdk.com/download/537974/480aeb04c789e45ef5bb9681513474ba/pdf-generaltechnicalinformation.pdf) | AC operation and thermal behavior | Frequency-dependent capacitor stress |
| [Vishay pulse load handling 28810](https://www.vishay.com/docs/28810/pulseloadhandling.pdf) | Single and continuous pulse load sections | Resistor pulse and voltage constraints |
| [Würth ANP044e](https://www.we-online.com/components/products/media/109026) | pp. 2–4, principles | EMI modes and parasitic switching-noise paths |
| [JLCPCB capability page](https://jlcpcb.com/capabilities/pcb-capabilities) | Current process option tables, accessed 2026-10-10 | Verify the chosen fabrication option set |
| [Eurocircuits tolerances](https://www.eurocircuits.com/technical-guidelines/understanding-manufacturing-tolerances-on-a-pcb/tolerances-on-a-pcb/) | Manufacturing tolerance tables | Tolerance topics for supplier review |
| [Eurocircuits solder mask](https://www.eurocircuits.com/technical-guidelines/pcb-design-guidelines/soldermask/) | Mask registration and opening definitions | Mask design/process topics |
| [Eurocircuits bow and twist](https://www.eurocircuits.com/technical-guidelines/understanding-manufacturing-tolerances-on-a-pcb/bow-and-twist-on-a-pcb/) | Causes of bow and twist | Stackup/copper distribution review |
| [TI PowerPAD SLMA002H](https://www.ti.com/lit/an/slma002h/slma002h.pdf) | Sections 2.1–2.5 | Exposed-pad assembly and stencil/via process principles |
| [Murata MLCC layout guidance](https://article.murata.com/en-eu/article/layout-helps-prevent-chip-mlcc-from-cracking) | Board strain and board-break placement | Ceramic-capacitor mechanical risk |

The [current check catalog](../../zapote/CHECKS.md) identifies existing layout, current and fabrication checks and their limitations. Historical Temper documents provide context; recheck every inherited numerical target against the selected architecture and its derivation before carrying it forward.
