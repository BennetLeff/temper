# Temper IC datasheet guidance for PCB design and assembly

Reviewed 2026-10-10. This companion to [the PCB design rubric](PCB_DESIGN_RUBRIC.md) translates manufacturer guidance into reviewable layout and assembly checks. It records applicability and evidence; it does not certify any physical assembly.

## Current design inventory and evidence basis

The authoritative maintained scope on main is **RTD, current-sense, thermal-sense, interlock and gate-drive, plus power-stage-120v**. Main's [Zapote scope](../../zapote/README.md) archives Rev38 PFC and voltage-sense. The [shared source](../../zapote/elec-base/README.md) was restored under zapote/elec-base/src after removing the legacy root tree. A controller exists in a separately accessible worktree snapshot; it is recorded below as a candidate, not a maintained released main-board assembly. Older source declarations and qualification candidates are historical references only. Architecture chronology and separate-worktree context are in [source context](PCB_DESIGN_SOURCE_CONTEXT.md).

Current inventory was read from Git object **ba575413f** (origin/main at review), using each maintained unit's resolved BOM, not merely a component declaration:

| Assembly | Resolved inventory file | Meaning |
|---|---|---|
| RTD | [PCB BOM](../../zapote/rtd/unit/bom/pcb-bom.csv) and [source manifest](../../zapote/rtd/unit/candidate/source-manifest.json) | Current maintained unit candidate |
| Current-sense | [source-build-04 BOM](../../zapote/current-sense/source-build-04/build/default.csv) | Latest retained source-build candidate |
| Gate-drive | [source-build-09 BOM](../../zapote/gate-drive/source-build-09/build/default.csv) | Latest retained source-build candidate |
| Interlock | [source-build-02 BOM](../../zapote/interlock/source-build-02/build/default.csv) | Latest retained source-build candidate |
| Thermal-sense | [source-build-02 BOM](../../zapote/thermal-sense/source-build-02/build/default.csv) | Latest retained source-build candidate |
| 120 V power-stage | [frozen BOM](../../zapote/power-stage-120v/frozen/default.csv) and [source](../../zapote/power-stage-120v/elec/src/power_stage_120v.ato) | Source includes later bias changes; individual native-N BOMs require their own release comparison |

These records establish source/BOM applicability, not fitted hardware, procurement approval, physical qualification or a fab release. Before checking a particular native board, compare that board's own frozen BOM/netlist and hash with this inventory. Historical MCU/buck declarations still in shared source do not mean those parts appear in every unit.

| Current device/orderable | Assembly / references | Exact package or behavior | Datasheet |
|---|---|---|---|
| UCC21550BDWKR | Gate-drive U1; power-stage U1/U2 | DWK has 14 physical leads numbered 1–11,14–16; DW16 is different | D01 |
| MAX31865AAP+ | RTD U1 | SSOP20; no TQFN exposed-pad instruction | D03 |
| TLV3201AIDBVR | RTD U3/U4; current U1/U2; thermal U1/U2; power-stage U6/U7/U10–U12 | DBV SOT23-5 push-pull comparator | D04 |
| REF2025AIDDCR | RTD U2 | DDC SOT23-5, two reference outputs | D05 |
| TPS3700DDCR | Power-stage U14 | DDC SOT23-6 open-drain window supervisor | D06 |
| TPS389001DSER | RTD U6 | DSE WSON6; custom footprint/pin map must match datasheet | D33 |
| SN74LVC1G08DBVR | RTD U5; interlock U6 | DBV SOT23-5 AND | D07 |
| SN74LVC1G38DBVR | RTD U7 | Open-drain NAND, requires pullup | D08 |
| TPS3823-33DBVR | Interlock U5 | -33 threshold/watchdog variant | D09 |
| CD74HC4075M96 | Current U3 | M SOIC14; resolves older SN74HC4075DR identity problem for this current unit | D10 |
| SN74LVC14ADR | Interlock U1/U2 | D SOIC14 hex Schmitt inverter | D36 |
| CD74HC30PWR | Interlock U3 | PW TSSOP14 8-input NAND | D37 |
| SN74LVC1G74DCUR | Interlock U4 | DCU VSSOP8 flip-flop; asynchronous clear/preset and clock are separate constraints | D38 |
| TLV9031DBVR | Thermal U3/U4 | DBV SOT23-5 comparator | D34 |
| SN74LVC1G32DBVR | Thermal U5/U6; power-stage U22/U23 | DBV SOT23-5 OR | D35 |
| AMC1311BDWVR | Power-stage U4 | DWV wide SOIC8 isolated amplifier | D16 |
| ISO7710DWR | Power-stage U9/U32–U34 | DW16; **non-F defaults high**, unlike old ISO7710FDWR default-low documentation | D17 |
| LM4040A25IDBZR | Power-stage U5 | DBZ SOT23-3, 2.5 V shunt reference | D18 |
| TPS70950DBVR | Power-stage U3/U37–U39 | DBV SOT23-5 5 V LDO | D39 |
| SN74LVC1G10DBVR | Power-stage U8 | DBV SOT23-6 3-input NAND | D46 |
| SN74LVC1G332DBVR | Power-stage U13/U25 | DBV SOT23-6 3-input OR | D47 |
| SN74LVC1G17DBVR | Power-stage U15/U24/U40 | DBV SOT23-5 Schmitt buffer | D48 |
| TPS7A4700RGWR | Power-stage U26–U28 | RGW VQFN20 exposed pad; programmable ANY-OUT | D40 |
| TLVH431BQDBZR | Power-stage U16/U18/U20 | DBZ shunt, 1.24 V reference; different from TL431 | D42 |
| TL431AIDBZR | Power-stage U17/U19/U21 | DBZ shunt, 2.495 V reference; TL432 example has different pinout | D41 |
| LM339BIDR | Power-stage U29–U31 | D SOIC14 quad open-collector comparator | D43 |
| SN6507DGQR | Power-stage U35 | DGQ HVSSOP10 exposed pad transformer driver | D44 |
| VOL628A-3X001T | Power-stage U36 | LSOP4 AC-input optocoupler; selected CTR bin and review-only footprint | D45 |
| IRM-20-15 / IRM-20-24 | Power-stage PS1/PS2 | Different output voltages in same THT module family | D20 |
| IPW65R018CFD7 | Power-stage Q2/Q3/Q5/Q6 | PG-TO247-3; live drain tab | D31 |
| AO3400A | Gate-drive and power-stage MOSFET positions | SOT23, thermal data tied to test copper | D32 |

## Applying the checks

For every applicable row record **pass, fail, unverified or not applicable**, exact OPN/reference, board hash/revision, evidence and owner. Recommendations are design defaults; deviations need reasoned electrical/thermal justification and measurements. Absolute maxima, pin maps, capacitor stability bounds and assembly limits are hard bounds. Example layouts indicate topology, not universal safety dimensions. Nominal capacitance is subject to tolerance, DC bias, temperature and aging. “Close” means short outgoing and return current paths unless a device states an explicit distance.

## Rules applicable to the maintained unit inventory

The IC identifiers are stable across this research expansion; gaps in numbering belong to explicitly historical or separate candidate guidance later in this file.

| ID | Rule | Evidence for a pass | Manufacturer locator |
|---|---|---|---|
| IC-01 | UCC21550: place low-ESR/ESL bypass directly across each VDD/VSS pair; default to approximately 10 uF plus at most 100 nF per output side. | Per-channel capacitor values, bias retention, and annotated supply loops | D01, section 9, p38 |
| IC-02 | UCC21550: provide at least 100 nF at VCCI/GND and keep gate-charge/discharge loops compact. | Supply-pad route and gate/return loop overlay | D01, sections 9/10.1, pp38-39 |
| IC-03 | UCC21550: minimize the bootstrap recharge loop as well as the gate loop; place DT and remote-DIS filtering beside their pins. | Both loops traced; filter delay budget | D01, section 10.1, p39 |
| IC-04 | UCC21550: preserve the isolation corridor; do not add copper under the isolation region to improve cooling. | All-layer corridor and channel-separation inspection | D01, section 10, pp39-41 |
| IC-05 | UCC21550: enlarge same-domain VSS/VDD copper for cooling while retaining high-voltage separation; verify DWK pin numbering. | Package drawing comparison and thermal/clearance review | D01, sections 4, 10, 13 |
| IC-06 | UCC21550 input RC changes need timing review. Recommended INA/INB filtering is 10-100 ohm with 10-100 pF; DT bypass above 1 nF is discouraged. | Measured input pulse and dead-time response | D01, table 4-1, p3 |
| IC-15 | IPW65R018CFD7: derive losses at hot junction temperature, not from 25 C resistance alone; case-rated current is not PCB ampacity. | Hot resistance/loss model and measured case temperature | D31, tables 2-4, pp3-5 |
| IC-16 | IPW65R018CFD7: constrain mounting torque to 60 Ncm; wave solder only leads within the stated 260 C/10 s geometry limit. | Torque/process plan and package comparison | D31, tables 2/3, pp3-4 |
| IC-17 | IPW65R018CFD7: if devices are paralleled, consider the stated separate gate drive/ferrite recommendation and verify dynamic sharing. | Each gate path and sharing/ringing capture | D31, p1 |
| IC-18 | AO3400A: use resistance specified at the actual gate drive; do not select by threshold voltage. | Minimum gate voltage and hot conduction-loss calculation | D32, electrical characteristics, p2 |
| IC-19 | AO3400A: its headline dissipation/thermal rating assumes a specific 1 square inch, 2 oz copper board; recalculate for Temper copper. | Real copper area and temperature rise | D32, thermal notes A/B/F, pp1-2 |
| IC-25 | REF2025: bypass VIN, VREF and VBIAS locally; manufacturer example uses 0.1 uF low-ESR capacitors. | All three capacitor/return loops | D05, section 9.4.1, p24 |
| IC-26 | REF2025: keep reference paths short and away from digital routes; reduce thermal gradients and parasitic thermoelectric errors. | Precision-route and heat-source overlay | D05, section 9.4.1 |
| IC-27 | REF2025: account for solder heat shift when setting final accuracy/calibration acceptance. | Post-assembly reference measurement and error budget | D05, section 7.1 |
| IC-28 | LM4040: current-limit the shunt at supply/load extremes and place a local cathode bypass as recommended. | Bias-current corners and cathode/return layout | D18, sections 8.3/8.4, pp28-29 |
| IC-29 | LM4040: isolate precision-reference routing from digital signals and local thermal gradients. | Reference-route overlay and accuracy budget | D18, section 8.4.1 |
| IC-36 | MAX31865: provide separate local 100 nF paths from DVDD to DGND and VDD to GND1. | Both pin-local supply loops; not a single distant shared capacitor | D03, Pin Description, p8; Power-Supply Decoupling, p21 |
| IC-37 | MAX31865: use the correct 2/3/4-wire force/sense connections; retain independent Kelvin sense routing where applicable. | Connector-to-device force/sense net and routing audit | D03, Pin Description and typical circuits |
| IC-38 | MAX31865: any differential input filter must be included in acquisition/fault settling timing. | Actual RC, bias-start and fault-cycle timing | D03, Applications Information, p19; electrical notes, p4 |
| IC-39 | MAX31865: explicitly address broken RTDIN+ in 3/4-wire use; a floating ADC input can evade simple threshold checks. | Cable-open test; decision on manufacturer's 10 Mohm BIAS pullup | D03, Detecting RTDIN+ Cable Faults, p21 |
| IC-40 | MAX31865: apply exposed-pad grounding only to the TQFN orderable; AAP+ is SSOP. | Exact part-to-footprint/pin-map comparison | D03, Pin Description and package information |
| IC-41 | TLV3201: place 100 nF at VCC with an unbroken low-inductance local-domain ground reference. | Supply loop and return-plane continuity | D04, sections 8.3/8.4.1, p18 |
| IC-42 | TLV3201: separate input from output routing and keep both short to avoid feedback-induced chatter. | Comparator route overlay and threshold-noise test | D04, section 8.4.1 |
| IC-43 | TLV3201: input filtering for slow crossings must include propagation-delay cost in the fault budget. | Worst-case input ramp and trip latency | D04, section 8.4.1 |
| IC-44 | TPS3700: bypass locally with 100 nF; choose divider current with input-bias error explicitly accounted for. | Input leakage/bias versus divider error budget | D06, sections 8/10.1, pp18-19 |
| IC-45 | TPS3700: verify open-drain pullups for low-level current and fail-safe startup, including any wired output combination. | Pullup-current and unpowered-rail state table | D06, sections 8/10 |
| IC-48 | AMC1311: bypass each isolated side with 100 nF plus 1 uF, using effective capacitance under actual bias. | Four local bypass components and bias curves | D16, section 10, p27 |
| IC-49 | AMC1311: place the sense resistor near IN and keep the isolation corridor free of conductive material. | Input loop and all-layer isolation overlay | D16, section 11, p28 |
| IC-52 | SN74LVC1G08: give each IC local 100 nF with a short, wide return. | Per-device supply-loop overlay | D07, power supply/layout sections |
| IC-53 | SN74LVC1G08: preserve continuous reference under signal routes and evaluate long traces/branches using edge rate and termination. | Route/edge analysis; documented departure from example dimensions | D07, section 8.4.1, p14 |
| IC-54 | SN74LVC1G38: bypass at VCC and define every input; open-drain output needs a real pullup and loaded timing check. | Startup state and output rise-time calculation | D08, sections 7/8.3/8.4, pp13-14 |
| IC-55 | CD74HC4075M96: bypass each VCC and tie unused inputs to defined levels. | Unused-pin inventory and local bypass | D10, power supply/layout sections |
| IC-57 | TPS3823: place 100 nF locally on noisy rails; keep supply route short to avoid supply-LC ringing. | VDD waveform and reset/watchdog behavior | D09, sections 8.3/8.4, p18 |
| IC-58 | ISO7710 (non-F): decouple each supply side with local 100 nF referenced to that side's ground. | Independent side-1/side-2 loops | D17, section 8.3 |
| IC-59 | ISO7710 (non-F): implement a documented low-EMI stackup; their examples specify four layers and continuous same-domain references. | Stackup and return-path review; justified deviation if fewer layers | D17, section 8.4.1 |
| IC-60 | ISO7710 (non-F): keep the barrier corridor free of planes, traces, pads and vias on every layer. | All-layer view and assembly contamination allowance | D17, layout examples |
| IC-67 | IRM-20: use each module's own bottom-view mechanical drawing; input orientation/body dimensions are not transferable between families. | Part-specific footprint/pin-map signoff | D20, Mechanical Specification |
| IC-68 | IRM-20: apply temperature/input-voltage derating at actual enclosure temperature and local airflow. | Operating-point mark on both derating curves | D20, Derating Curve/Static Characteristics |
| IC-69 | IRM-20: respect wave solder 265 C maximum for 5 s and manual solder 390 C maximum for 3 s. | Through-hole assembly process traveler | D20, Environment specification |
| IC-70 | IRM-20: internal Class II/no-FG construction and module EMC ratings do not establish the complete appliance's leakage/EMI/isolation performance. | System-domain, barrier and end-product EMC review | D20, Description and notes |
| IC-71 | Every TI orderable: compare footprint to that package's appended mechanical/land-pattern drawing; review stencil/mask notes and packaging MSL/reflow table. | Exact OPN-to-package drawing and supplier assembly agreement | D01/D02/D04-D11/D15-D18/D22-D29, Mechanical/Packaging/Orderable Information |
| IC-72 | Every isolated device/module: preserve safety geometry through copper pours, fabrication tolerances and solder/process residues. | All-layer fabricated geometry and cleanliness plan | D01/D16/D17 layout corridors; D20 mechanical drawings; system-specific safety assessment |
| IC-73 | TPS3890: place 0.1 uF VDD/GND bypass on noisy rails with a short, low-impedance path; keep SENSE away from switching nets. | Local supply loop and supervisor threshold/noise captures | D33, sections 10/11, pp16–17 |
| IC-74 | TPS3890: keep CT routing short; when intentionally using no CT capacitor, include pin/trace parasitic capacitance in reset-delay uncertainty. | CT geometry, delay calculation and measured reset release | D33, sections 8/11 |
| IC-75 | TLV9031: use local 0.1 uF low-ESR bypass; separate input and output paths or shield them with local supply/ground. | Input/output coupling overlay and chatter test | D34, sections 7.3/7.4, p34 |
| IC-76 | TLV9031: treat output edges as fast even with slow thermal input; locate series input filtering at the pin and consider less-than-100-ohm output damping for a long route. | Loaded edge/overshoot and complete trip-delay measurement | D34, section 7.4 |
| IC-77 | SN74LVC14A, CD74HC30 and SN74LVC1G74: give each IC local 0.1 uF supply bypass and define every unused input, including disabled/asynchronous inputs. | Pin inventory, startup state table and per-IC loops | D36 sections 10/11; D37 sections 10/11; D38 sections 10/11 |
| IC-78 | SN74LVC1G74: verify clear/preset legality, minimum pulse width and recovery/removal timing; a noise pulse on CLK can create a state change that DRC cannot detect. | Loaded waveforms at pins, timing corners and reset tests | D38, function table and switching requirements |
| IC-79 | SN74LVC1G32, SN74LVC1G10, SN74LVC1G332 and SN74LVC1G17: give each device local 0.1 uF bypass with short return, define all inputs, and check operating voltage/logic thresholds across powered and unpowered states. | Per-IC bypass, voltage-domain and unused-pin review | D35/D46/D47/D48, power supply/layout sections |
| IC-80 | TPS70950: retain 1.5–47 uF effective output capacitance with 0–0.2 ohm ESR; 0.1–2.2 uF local input bypass is recommended and is necessary for anticipated line transients above 10 V. | Biased capacitor/ESR corners and input-transient envelope | D39, section 8.1.1 |
| IC-81 | TPS709: place input/output capacitors on the IC side with short supply/ground traces; compute junction temperature from linear loss and actual copper, including simultaneous bias-channel loads. | Capacitor-loop overlay and thermal corner calculation | D39, section 10.1, p16; thermal information |
| IC-82 | TPS7A4700: retain at least 1 uF input, 10 uF output and 10 nF NR capacitance; manufacturer performance defaults are 10 uF input, 47 uF output, 1 uF NR. | Effective capacitance and startup/noise measurements | D40, pin functions pp3–4; capacitor recommendations |
| IC-83 | TPS7A4700: place capacitors on the same side with a shared low-impedance ground and solder the exposed pad to ground/cooling copper; preserve isolation boundaries. | RGW package/pad audit, solder process and junction estimate | D40, section 9.1, p20; RGW appendices |
| IC-84 | TPS7A4700: unused ANY-OUT voltage-setting pins stay floating; selected pins connect only to GND. Include NR-dependent startup in bias sequencing. | Exact pin/net audit and loaded startup sequence | D40, pin functions and ANY-OUT/startup sections |
| IC-85 | TL431 and TLVH431: determine cathode-capacitance stability at actual voltage/current; generic “add 100 nF” can enter an unstable region. Current-limit cathode and REF. | Device-specific stability plot and supply/load corners | D41 figures 6-16/6-18 and section 9.4; D42 figures 5-15–5-17 and section 8.3 |
| IC-86 | TL431/TLVH431: place permitted capacitors locally, size cathode/anode paths for drop, and check the actual pinout rather than copying a TL432 package example. | Exact OPN/pin map and shunt-current routing | D41 section 9.5 p31; D42 section 8.4 pp20–21 |
| IC-87 | LM339B: bypass locally and keep output routes away from sensitive inputs; provide open-collector pullups and test slow crossings for chatter. | Pullup/edge budget, input/output overlay and trip test | D43, application/power/layout sections |
| IC-88 | ISO7710: verify the intended default-high fault contract through all power-loss corners; **current ISO7710DWR defaults high**. F/non-F suffix changes that behavior. | Loss-of-input-power and startup state table through shutdown logic | D17, description/function tables; current frozen BOM |
| IC-89 | SN6507: place 100 nF within 2 mm of VCC; place 1–10 uF low-ESR bulk, preferably 10 uF, at the transformer primary center tap. | Dimensioned capacitor/return loops and biased values | D44, section 9.2.2.4 p24 |
| IC-90 | SN6507: keep SW1/SW2-to-primary and VCC-to-center-tap paths short; use parallel ground vias as shown and maintain the primary/secondary isolation corridor. | Primary switching-loop and all-layer domain overlay | D44, section 9.4 p30; transformer pin/insulation drawing |
| IC-91 | SN6507: keep output capacitance below ten times CSS as recommended; verify transformer volt-seconds at worst input/minimum switching frequency and loaded startup OCP. | CSS/COUT review, saturation calculation and startup capture | D44, sections 9.2.2.4/9.2.2.5 pp24–25 |
| IC-92 | SN6507: choose actual capacitor voltage ratings for the live supply, not generic example minimums; characterize low-parasitic transformer, rectifier capacitance, slew setting and secondary snubber for EMI. | Voltage derating and measured EMI/efficiency tradeoff | D44, sections 9.2.2.6/9.4 pp27/30 |
| IC-93 | VOL628A: check exact CTR bin over temperature and at actual LED current; include saturation/load-dependent turn-off in shutdown timing. | LED-current, pullup, temperature and latency corners | D45, electrical/typical characteristics pp2–7 |
| IC-94 | VOL628A: validate the LSOP4 review-only footprint against the package/possible land pattern; apply the full Pb-free reflow profile and specified handling conditions. | Pin map, mask/paste/clearance audit and assembly traveler | D45, package p8; solder profile/handling p9 |

| IC-122 | TPS709: do not tie EN to VIN on the 15/24 V rail; keep EN within its 0–6.5 V recommended range and 7 V absolute maximum, or leave it floating for the specified enabled behavior. | EN net/voltage audit including rail transients and startup | D39, pin functions and section 7.4 |

## Separate controller snapshot and prototype proposals

The read-only controller inventory was accessible at /Users/bennet/Desktop/temper/worktrees/ps-integrate/zapote/controller/frozen/default.csv, checkout HEAD **5191b3263**, CSV SHA-256 **c9a675a6ecb0b4ffb042fae90ee3e873d0808059fa871e529ef88eaa3d24dd70**. The file's content hash identifies the actual inspected snapshot; its HEAD alone does not prove a clean tree. This controller path is absent from the inspected main tree. It contributes device guidance for that candidate, not an assertion that main selects those ICs.

An additional readable snapshot at /Users/bennet/.codex/worktrees/ps-r17-d35/temper had HEAD **69144e87e**. Source-only prototype supervisor declarations were checked there and in ps-integrate, then against the retained main file [prototype supervisor](../../zapote/power-stage-120v/prototype-closure/round4/supervisor/generated/supervisor.ato). Its header explicitly says no physical release. Source-only imported/declared devices must be resolved against the actual compiled assembly before applying them as fitted requirements.

| Additional device/orderable | Snapshot applicability | Package/variant caution | Source |
|---|---|---|---|
| TPS62933FDRLR / TPS62933DRLR | Separate controller U1/U2 | DRL SOT583-8; F and non-F variants have different operating mode | D49 |
| TPS3703A4330DSERQ1 | Controller U3 | DSE WSON6; exact threshold, reset-delay variant | D50 |
| SN74LVC244APWR | Controller U9 | PW TSSOP20; output-enable doesn't eliminate input bias requirement | D59 |
| OPA2388IDR | Controller U5 | D SOIC8 precision dual amplifier | D51 |
| TLV9062IDR | Controller U6/U7 | D SOIC8 dual; prototype TLV9061IDBVR is single SOT23-5 | D52 |
| AD8436BRQZ | Controller U14 | RQ QSOP20 B-grade, not LFCSP | D53 |
| MCP3202-CI/SN | Controller U15 | SN SOIC8; shared VDD/reference supply | D54 |
| TCA9555PWR | Controller U8 | PW TSSOP24 I2C expander | D55 |
| TLV76050DBZR | Controller U16 | DBZ SOT23-3 5 V LDO | D56 |
| SN74LVC2G17DBVR | Controller U17 | DBV SOT23-6 dual Schmitt buffer | D57 |
| SN74LVC1G14DBVR | Controller U12 | DBV SOT23-5 Schmitt inverter | D58 |
| ESP32-S3-WROOM-1-N8 | Controller U4 | N8 module lacks the N8R8 PSRAM option; antenna/assembly guidance remains module-specific | D12/D13 |
| ADS131M08IPBSR | Retained prototype supervisor source only | PBS TQFP32 ADC; analog/digital decoupling, clocking | D60 |
| AMC3330DWE | Prototype supervisor source only | DWE wide SOIC16 with integrated isolated power | D61 |
| SN74AHCT125PWR | Prototype supervisor source only | 4.5–5.5 V AHCT buffer; cannot infer LVC supply/thresholds | D62 |
| TPS1H100AQPWPRQ1 | Prototype supervisor source only | PWP HTSSOP14 exposed pad, A variant high-side switch | D63 |
| LTC6993HS6-1#TRMPBF | Prototype supervisor source only | S6 TSOT23-6; -1 edge/retrigger behavior | D64 |
| STM32G071RBT6 | Prototype supervisor source only | R LQFP64; not another MCU/package's supply map | D65 |
| LD1117S33TR | Prototype supervisor source only | SOT223 fixed 3.3 V; thermal tab/pin map matters | D66 |
| VO617A-3X017T | f6 source variant / prototype, not current frozen VOL628A | Option7 SMDIP4; not option8 >8 mm package | D67 |
| R-78HB5.0-0.5/W | Prototype external/wired module source only | Non-isolated wired suffix differs from ordinary SIP land pattern | D68 |
| R24C2T25/R-R | Prototype bias-module source only | Reinforced /R family, 36-pin SSOP; distinguish non-/R family | D69 |
| HDR-60-24 | Prototype external supply source only | DIN rail supply, offboard wiring/mounting; no IC footprint | D70 |
| ISO7710DR / ISO7710FDR | Prototype variants | D SOIC8 differs from DW16; F/non-F fail-safe differs | D17 |
| TPS3820-33DBVR / TPS3825-50DBVR | Prototype variants | Supervisor reset polarity/manual-reset/watchdog/threshold differ | D09 |
| SN74LVC1G04DBVR | Prototype catalog inverter variant | Separate from historical Q1 orderable | D71 |

The controller also reuses current MAX31865, REF2025, LM4040, TLV3201, TLV9031, TPS3890, TPS3823 and LVC logic families above. Prototype source reuses INA240, IRM modules and other families covered elsewhere. A declaration is not evidence of instantiation. Unresolved discrete manufacturer identities, including generic 2N7002, remain a BOM-completion task.

| ID | Rule for separate candidate/prototype device | Evidence for a pass | Manufacturer locator |
|---|---|---|---|
| IC-95 | TPS62933: compact the input pulse-current loop; put IC, CIN, inductor and COUT on the same side, including local 0.1 uF VIN bypass. | Input/current-loop overlay and pin-level voltage capture | D49, section 12.1 p40 |
| IC-96 | TPS62933: keep SW short, place BST parts at pins, place feedback divider at FB, and route separate output sense away from SW with shielding. | SW/FB/SS/RT route audit and load-step stability | D49, section 12.1 |
| IC-97 | TPS3703: use local 0.1–1 uF bypass; keep VDD/SENSE short and separate sensitive sense from digital paths. | Supervisor VDD/SENSE waveform and reset sequence | D50, sections 10/11 p26 |
| IC-98 | OPA2388: place local 0.1 uF bypass and short feedback/input loops; give both input paths similar thermal conditions and avoid heat sources/airflow gradients. | Route and temperature-gradient overlay; offset drift measurement | D51, sections 9/10 pp25–26 |
| IC-99 | TLV9061/2: give each supply local 0.1 uF, keep input/feedback routes short and isolated from output/supply paths; use guarding when leakage error warrants it. | Input leakage/impedance budget and routing overlay | D52, section 8.4 p27 |
| IC-100 | TLV9061/2: control flux/moisture leakage; manufacturer's cleaning/post-aqueous bake guidance must be checked against the complete assembly's material and component limits. | Qualified cleaning/bake process and leakage verification | D52, section 8.4; whole-assembly compatibility |
| IC-101 | AD8436: select CAVG for low-frequency accuracy and leakage, and CLPF separately for ripple/settling; avoid electrolytic or X7R-or-lower ceramics for CAVG as instructed. | Exact capacitor dielectric/leakage and frequency/settling error budget | D53, Averaging Capacitor Considerations and CAVG Capacitor Styles pp12–13 |
| IC-102 | AD8436: account for the RMS input's 8 kohm loading or use its buffer; follow the actual single-supply/reference circuit and capacitor polarity. | Source impedance/scale, supply and grounding review | D53, Basic Core Connections p13; Single Supply p15 |
| IC-103 | MCP3202: put 0.1 uF bypass at VDD; separate clock/digital routing from analog inputs, avoid signal traces below IC/bypass and preserve a low-impedance analog reference. | Analog/clock overlay and supply-noise conversion result | D54, section 6.4 Layout Considerations |
| IC-104 | MCP3202: include source resistance and sampling-capacitor acquisition settling, minimum effective conversion clock and VDD/reference noise in error budget. | Acquisition and clock timing corners under actual drive | D54, Analog Input Model/Driving Analog Inputs; Maintaining Minimum Clock Speed |
| IC-105 | TCA9555: decouple locally; size I2C pullups from capacitance/speed, check output loads and startup direction/default states. I2C generally needs no differential-pair matching. | Bus rise-time and power-up state test, supply loops | D55, sections 11/12 p31 and functional description |
| IC-106 | TLV760: place input/output capacitors on the same side, near pins, with a short/wide shared ground; compute linear loss and actual thermal copper. | Capacitor/return layout, stability values and junction estimate | D56, sections 9/10 p14 |
| IC-107 | SN74LVC244A: use local 0.1 uF and wide/short return; maintain signal reference continuity and assess branching/termination from edge rate. Its example trace dimensions are not universal impedance constraints. | Signal/return overlay and loaded edge measurement | D59, sections 8.3/8.4 |
| IC-108 | SN74LVC1G14/2G17 and AHCT125: use local 0.1 uF, define unused input/OE states and verify exact logic-voltage compatibility. | Supply/input state and edge review | D57 sections 11/12; D58 sections 7.3/7.4; D62 sections 8.3/8.4 |
| IC-109 | ADS131M08: use pin-local 1 uF AVDD and DVDD bypass; use stable C0G input filters, protect clock integrity and avoid routing clock near analog input. | Supply/filter BOM and clock/analog route overlays | D60, sections 10/11 pp103–104 |
| IC-110 | ADS131M08: keep AGND/DGND references at the ADC controlled; if using separated ground regions, join near ADC without multiple-loop joins and keep digital return out of analog input paths. | Actual return-current topology; conversion-noise test | D60, section 11 |
| IC-111 | AMC3330: implement its complete named bypass network, including VDD, DCDC_IN/OUT and high-side LDO nodes; a generic pair of 100 nF caps is insufficient. | Every named capacitor against exact application diagram | D61, sections 7.4/7.5 p27 onward |
| IC-112 | AMC3330: separate Kelvin high-side sense ground from power return, join DCDC_HGND/HGND at pins, route inputs symmetrically, and keep the barrier free of conductive material. | Sense/return/isolation overlay and dynamic-noise test | D61, section 7.5 |
| IC-113 | TPS1H100: solder exposed pad to thermal ground with adequate copper/vias; manufacturer requires at least 85% solder coverage and plugged/capped or plated-shut vias to prevent voiding. | Assembly inspection/X-ray specification and hot-load thermal test | D63, section 10 p37 |
| IC-114 | LTC6993: place 0.1 uF directly V+/GND, keep RSET/SET connection short and ground-shielded, and put DIV divider close. Noise injection at SET directly changes pulse width. | SET/return overlay and pulse-width noise test | D64, Supply Bypassing and PCB Layout Guidelines p20 |
| IC-115 | STM32G071RBT6: follow LQFP64-specific supply/ground and VREF+ bypass connections and placement; check reset, boot and debug accessibility using its actual pin map. | Package-specific schematic/layout review and startup/programming test | D65, figure 13 p54; pins and application supply notes |
| IC-116 | LD1117: retain at least 10 uF output capacitance for stability, confirm real dropout at load, and design SOT223 cooling for linear dissipation. | Capacitor/range review and junction-temperature evidence | D66, description p1; electrical, thermal/package sections |
| IC-117 | VO617A: check selected option7 land pattern and insulation distances; its ≥7 mm package limits must not inherit option6/8 ≥8 mm ratings. Evaluate CTR/loading and full reflow profile. | OPN/package comparison, barrier and timing review | D67, insulation table, ordering/package and solder sections |
| IC-118 | R-78HB/W: for input above 50 V add specified 3.3 uF/100 V input capacitor; check capacitive-load/startup and wired-body mounting using the /W drawing. | Voltage/load corners and mounting/lead restraint | D68, characteristics/application and mechanical sections |
| IC-119 | R24C2T25/R: use full input/output/feedback capacitor network and exact 36-pin land pattern; check output split, isolation spacing and board-specific thermal derating. | Exact /R application/land-pattern review and bias load/temperature test | D69, Typical Application, Layout Guidelines p13, Package Dimensions, Derating Graph |
| IC-120 | HDR-60-24: apply ambient/input derating and specified mounting clearances; verify external terminal wiring, protective measures and ventilation at system level. | Supply operating point and enclosure/wiring review | D70, derating/mechanical and installation-manual reference |
| IC-121 | Catalog SN74LVC1G04: provide local 0.1 uF bypass and defined input state; do not assume automotive-grade limits from the Q1 datasheet. | Exact catalog OPN and supply/input audit | D71, sections 8.4/8.5 |

## Historical declarations and qualification candidates

The following were identifiable in the older electrical tree, removed hardware generations or qualification source. They are retained to make the research traceable and to avoid applying the wrong variant if old files reappear. **They are not current design requirements.** Rev38 PFC was archived at the owner's request; UCC28180 rules below apply only when explicitly reviewing that archived design. Current source-only declarations likewise do not establish fitted hardware. Archive pointers and older source context are recorded in [source context](PCB_DESIGN_SOURCE_CONTEXT.md).

| Historical/candidate part | Original source use (historical only) | Identity issue | Source |
|---|---|---|---|
| LMR51430XDDCR | Historical: 15 V to 3.3 V buck | DDC six-lead SOT-23; suffix selects switching/mode variant | D02 |
| SN74HC4075DR | Historical: three-input OR logic | Exact TI OPN unresolved: reviewed official family is CD74HC4075, not an authorization to substitute | D10; gap G01 |
| SN74HC00DR | Historical: NAND fault latch | D SOIC-14; unused gates still require defined input levels | D11 |
| ESP32-S3-WROOM-1-N8R8 | Historical: MCU/RF module | PCB antenna, octal PSRAM variant; -1U antenna guidance differs | D12/D13 |
| IRM-10-15 | Historical: isolated auxiliary supply module | THT potted module; supply and assembly instructions differ from SMT ICs | D14 |
| INA240A1QPWRQ1 | Historical: proposed current sensing | PW TSSOP-8 and gain A1; not instantiated in elec/src/modules.ato | D15 |
| ISO7710FDWR | Historical: isolated fault signal | F suffix gives fail-safe low; DW package, do not use D dimensions | D17 |
| MC78L05ACHT1G | Historical: hot-domain 5 V linear regulator | Onsemi SOT-89; this ordering variant's operating junction range is 0 to 125 C | D19 |
| IRM-05-15 | Historical: hot gate supply | Output is HOT by its system connection; internal isolation alone does not make it SELV | D21 |
| UCC28180 | Historical: boost PFC controller | Exact packaging/orderable and reviewed Rev38 connectivity need BOM closure | D22 |
| ISO7741FQDWWRQ1 | Historical: digital isolator gate-drive candidate | DWW-16 package, channel directions and default-low F behavior require exact check | D23 |
| UCC27517AQDBVRQ1 | Historical: local gate-driver candidate | DBV five-lead; local ground reference must be the intended hot/source node | D24 |
| TPS7B6933QDBVRQ1 | Historical: local 3.3 V LDO candidate | DBV five-lead; voltage loss times current governs dissipation | D25 |
| TLV1701QDBVRQ1 | Historical: comparator candidate | Open-collector output differs from TLV3201 push-pull | D26 |
| TLV431BQDBZRQ1 | Historical: adjustable shunt reference | DBZ three-lead; 1.24 V reference, load-capacitance stability restrictions | D27 |
| SN74LVC1G08QDBVRQ1 | Historical: automotive AND | Check Q1 package and limits separately from catalog part | D28 |
| SN74LVC1G04QDBVRQ1 | Historical: automotive inverter | DBV five-lead; unused/floating input is unacceptable | D29 |
| REF2025AIDBZR | Historical: CT07 candidate reference declaration | Reviewed REF20 datasheet identifies DDC-5, not this DBZ-3 suffix | D05; gap G02 |
| TLV3201BIDBVR | Historical: CT07 comparator declaration | Reviewed TLV3201 orderable information did not establish this B-grade OPN | D04; gap G03 |
| IKW40N120H3 | Historical: IGBT power switch | TO-247-3, collector tab; current ratings depend on case temperature | D30 |

| ID | Historical or candidate-only rule | Evidence if separately applicable | Manufacturer locator |
|---|---|---|---|
| IC-07 | UCC28180: return sense/compensation capacitors to quiet signal ground outside high-current return paths. | Annotated separation and deliberate ground joining | D22, section 11.1, pp36-37 |
| IC-08 | UCC28180: place ICOMP/VCOMP compensation and FREQ resistor at the controller; keep VCC bypass close without injecting its pulses into signal return. | Component placement and return-path overlay | D22, section 11.1 |
| IC-09 | UCC28180: keep the switch-node path short and appropriately wide; shield sensitive traces from it, including remote shunt sensing. | Noise-coupling review and current-sense waveform | D22, section 11.1, p37 |
| IC-10 | UCC27517A-Q1 candidate: place driver, power transistor and VDD bypass together; route outgoing/return gate paths close together. | Gate-loop overlay and ringing measurement | D24, sections 11/12.1, pp19-20 |
| IC-11 | UCC27517A-Q1 candidate: follow its defined ground joining and input biasing; do not copy its local star-ground recommendation across unrelated domains. | Same-domain return topology and unused-input state | D24, section 12.1 |
| IC-12 | UCC27517A-Q1 candidate: estimate junction temperature using actual lead/PCB cooling; use appropriate characterization parameters for measurements. | Driver-loss calculation and thermal measurement method | D24, section 12.3, p21 |
| IC-13 | IKW40N120H3: calculate IGBT and antiparallel-diode temperatures separately; their junction-to-case resistances differ. | Device/diode loss models and case-temperature envelope | D30, table 1, p3 |
| IC-14 | IKW40N120H3: respect the stated 0.6 Nm M3 mounting limit and limited mounting repetitions; implement the specified lead-only solder process. | Assembly torque and solder-process instructions | D30, table 1, p3 |
| IC-20 | LMR51430: place CIN directly at VIN/GND and close COUT to the inductor output with a local ground return. | Input pulse-current loop and output loop overlay | D02, section 9.4.1, p21 |
| IC-21 | LMR51430: keep SW short and only as wide/large as required; balance cooling against switch-node EMI area. | SW area, current/thermal calculation, EMI result | D02, sections 9.4.1/9.4.1.1 |
| IC-22 | LMR51430: place the feedback divider at FB, and route load sensing away from SW/inductor with ground shielding where possible. | Feedback-node and load-sense route | D02, section 9.4.1.2, p22 |
| IC-23 | LMR51430: size cooling copper/vias to keep operating junction below the stated 125 C layout target. | Dissipation and actual-board thermal estimate/measurement | D02, section 9.4.1, p21 |
| IC-24 | LMR51430: include supply lead impedance and remote-source bulk capacitance in startup/load-step review. | VIN minimum/maximum waveform at chip pins | D02, section 9.3, p21 |
| IC-30 | TPS7B69 candidate: place input/output capacitors on the regulator side of the PCB with short traces; provide thermal vias/copper. | Capacitor placement, stability bounds and thermal model | D25, section 11.1, p14 |
| IC-31 | TPS7B69 candidate: validate output capacitor capacitance/ESR against the recommended operating conditions before using a generic MLCC. | Exact biased capacitor/ESR versus allowed range | D25, recommended operating conditions and section 9 |
| IC-32 | MC78L05: use local input bypass and output bypass; short leads and minimal ground-loop resistance matter. | Input/output bypass paths and transient response | D19, Design Considerations, p11 |
| IC-33 | MC78L05: calculate the 15 V to 5 V linear loss with all hot-domain loads and the exact SOT-89 thermal installation. | Load sum, junction estimate and package identity | D19, ratings/thermal data and ordering table |
| IC-34 | TLV431 candidate: select cathode/load capacitance from its stability region; adding arbitrary bypass can destabilize it. | Bias-current/capacitance stability plot evaluation | D27, figure 5-18 and section 8.3 |
| IC-35 | TLV431 candidate: current-limit cathode and REF; size anode/cathode routing for actual shunt current. | Supply corners, resistor power and voltage drop | D27, sections 8.3/8.4, p22 |
| IC-46 | INA240 candidate: Kelvin-connect directly to shunt sense points; never sense through shared load-carrying copper. | Four-terminal shunt geometry and sense path overlay | D15, figure 9-7 and section 11.1, pp24-25 |
| IC-47 | INA240 candidate: bypass locally with 100 nF and retain input common-mode/output-swing margins. | Chip-pin supply and analog-range budget | D15, section 10, p24 |
| IC-50 | TLV1701 candidate: use a local 100 nF bypass, continuous local ground and separated input/output routing. | Return plane and noise/chatter test | D26, sections 10/11, pp13-14 |
| IC-51 | TLV1701 candidate: include open-collector pullup and input-filter delays in the shutdown path. | Loaded output edge and end-to-end trip timing | D26, application circuits and section 11 |
| IC-56 | SN74LVC1G04-Q1 candidate: define input during startup/unpowered states and bypass VCC locally. | State table and supply-pad layout | D29, sections 8.3/8.4, p12 |
| IC-61 | ESP32-S3-WROOM-1: locate the PCB antenna beyond/near the baseboard edge using the manufacturer's clearance geometry. | Module/antenna footprint overlay | D12 section 11; D13 General Principles of PCB Layout for Modules |
| IC-62 | ESP32-S3-WROOM-1: keep housing, cookware/chassis metal, cables and components out of antenna clearance; guideline recommends at least 15 mm in all directions inside housing. | Complete enclosure/assembly RF view and final-product range test | D13, module placement guidance, p30 |
| IC-63 | ESP32-S3-WROOM-1: use the exact module land pattern; decide EPAD grounding/thermal connection from module guidance. | Land-pattern comparison and assembly drawing | D12, sections 9/11, figures 11-1/11-2 |
| IC-64 | ESP32-S3-WROOM-1: follow MSL3 storage/floor-life handling and the single-reflow requirement. | Moisture handling and assembly traveler | D12, section 12, p47 |
| IC-65 | ESP32-S3-WROOM-1: use its specified reflow profile; the 235-250 C peak differs from IC packages rated to 260 C. | Qualified board profile at module body | D12, figure 12-1, p47 |
| IC-66 | ESP32-S3: where USB is routed, use 90 ohm differential impedance within 10%, continuous reference and paired return vias at transitions. | Fabricator stackup/impedance report and route audit | D13, USB layout guidance, p30 |

## Coverage and open work

This pass covers the **28 IC/optocoupler orderables in the six maintained resolved inventories**, the two IRM-20 output variants and two materially relevant MOSFET types, plus additional controller/prototype/historical devices explicitly distinguished above. It reviewed full relevant manufacturer sections rather than relying on search snippets. It does not establish complete appliance safety or review every passive, connector, discrete semiconductor or every dirty worktree.

| Gap | Finding | Closure needed |
|---|---|---|
| G01 | Old SN74HC4075DR identity remains unresolved in legacy declarations. Current maintained current-sense BOM uses valid CD74HC4075M96. | Resolve old OPN only if reusing that source; current unit uses D10 |
| G02 | Historical qualification REF2025AIDBZR conflicts with reviewed DDC5 orderable/package. | Correct exact OPN/package before reviving candidate |
| G03 | Historical TLV3201BIDBVR declaration is not established by reviewed orderable information. | Manufacturer OPN evidence before procurement or reuse |
| G04 | Current six-unit source/BOM families are covered; individual native-N releases and separate controller/prototype sources can differ. | Compare exact release BOM/netlist/PCB hashes, including latest native variant and source-to-board parity |
| G05 | Controller snapshot is absent from inspected main and prototype source says no physical release. A resolved full cooker/control assembly is not established by declarations. | Resolve and pin the actual intended full assembly before closing an “all fitted ICs” review |
| G06 | Datasheets do not fully define supplier paste apertures, via filling/capping, solder void acceptance, washing/coating compatibility or module mounting restraint. | Package-specific fabricator/assembler agreement and process qualification |
| G07 | Complete manufacturer extraction remains open for rectifier/bridge, CT/transformer, bus/resonant capacitors, fuse/holder, relay, MOV, connectors, choke, TIM, cutoffs and generic discrete identities. | Review exact live-BOM datasheets and assembly/derating; IC coverage is not component coverage |

Part-specific numbers above are paraphrased manufacturer guidance. Where a package appendix or profile is graphical, compare the actual drawing/profile before releasing mask/paste/holes; the prose is not a substitute for the drawing. Firmware startup and physical fault/EMI/thermal tests remain separate evidence.

## Manufacturer source register

The relevant full datasheet sections were reviewed, including their surrounding notes. Page numbers are printed PDF page numbers; named sections are the stable locator where appendices or live revisions change pagination. Documents are paraphrased. Official URLs can serve newer revisions later; pin the reviewed document and its hash in a fabrication-release evidence bundle.

| ID | Official document and reviewed version | Principal sections |
|---|---|---|
| D01 | [TI UCC21550, SLUSE89C](https://www.ti.com/lit/ds/symlink/ucc21550.pdf), Aug 2024 | Pins p3; power p38; layout pp39-41; package appendices |
| D02 | [TI LMR51430, SLUSEF4A](https://www.ti.com/lit/ds/symlink/lmr51430.pdf), Nov 2022 | Sections 9.3/9.4, pp21-23 |
| D03 | [ADI/Maxim MAX31865](https://www.analog.com/media/en/technical-documentation/data-sheets/MAX31865.pdf) | Pin Description p8; Applications Information p19; fault/decoupling p21; package information |
| D04 | [TI TLV3201, SBOS561C](https://www.ti.com/lit/ds/symlink/tlv3201.pdf), May 2024 | Sections 8.3/8.4, pp18-19; orderables |
| D05 | [TI REF20 family, SBOS600F](https://www.ti.com/lit/ds/symlink/ref20.pdf), Jul 2026 | Solder Heat Shift; sections 9.3/9.4, p24; orderables |
| D06 | [TI TPS3700, SBVS187G](https://www.ti.com/lit/ds/symlink/tps3700.pdf), Feb 2019 | Applications p18; layout p19 |
| D07 | [TI SN74LVC1G08, SCES217AA](https://www.ti.com/lit/ds/symlink/sn74lvc1g08.pdf), Aug 2026 | Sections 8.3/8.4, p14 |
| D08 | [TI SN74LVC1G38, SCES538H](https://www.ti.com/lit/ds/symlink/sn74lvc1g38.pdf), Aug 2026 | Sections 8.3/8.4, pp13-14 |
| D09 | [TI TPS382x, SLVS165O](https://www.ti.com/lit/ds/symlink/tps3823.pdf), Mar 2025 | Sections 8.3/8.4, p18 |
| D10 | [TI CD74HC4075, SCHS210H](https://www.ti.com/lit/ds/symlink/cd74hc4075.pdf), Jun 2021 | Sections 10/11, pp12-13; family-only applicability |
| D11 | [TI SN74HC00, SCLS181H](https://www.ti.com/lit/ds/symlink/sn74hc00.pdf), Aug 2021 | Sections 10/11, p14 |
| D12 | [Espressif ESP32-S3-WROOM-1/-1U datasheet v1.8](https://www.espressif.com/sites/default/files/documentation/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf) | Sections 9-12; land pattern; Product Handling p47 |
| D13 | [Espressif ESP32-S3 Hardware Design Guidelines](https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/esp-hardware-design-guidelines-en-master-esp32s3.pdf), live master retrieved 2026-10-10 | General Principles of PCB Layout for Modules; USB, pp30-31 |
| D14 | [MEAN WELL IRM-10 specification](https://www.meanwell.com/Upload/PDF/IRM-10/IRM-10-SPEC.PDF) | Environment; derating/static characteristics; mechanical drawing |
| D15 | [TI INA240-Q1, SBOS808E](https://www.ti.com/lit/ds/symlink/ina240-q1.pdf), Dec 2021 | Sections 10/11, pp24-25 |
| D16 | [TI AMC1311, SBAS786C](https://www.ti.com/lit/ds/symlink/amc1311.pdf), Jun 2022 | Sections 10/11, pp27-28 |
| D17 | [TI ISO7710, SLLSER9E](https://www.ti.com/lit/ds/symlink/iso7710.pdf), Dec 2024 | Sections 8.3/8.4, pp24-25 |
| D18 | [TI LM4040, SLOS456Q](https://www.ti.com/lit/ds/symlink/lm4040.pdf), Apr 2026 | Sections 8.3/8.4, pp28-29 |
| D19 | [Onsemi MC78L00A](https://www.onsemi.com/pdf/datasheet/mc78l00a-d.pdf) | Design Considerations p11; ratings, orderables, case drawings |
| D20 | [MEAN WELL IRM-20 specification](https://www.meanwell.com/Upload/PDF/IRM-20/IRM-20-SPEC.PDF), Nov 2025 | Environment; derating/static characteristics; mechanical drawing |
| D21 | [MEAN WELL IRM-05 specification](https://www.meanwell.com/Upload/PDF/IRM-05/IRM-05-SPEC.PDF), Aug 2025 | Environment; derating/static characteristics; mechanical drawing |
| D22 | [TI UCC28180, SLUSBQ5D](https://www.ti.com/lit/ds/symlink/ucc28180.pdf), Jul 2016 | Section 11, pp36-38 |
| D23 | [TI ISO774x-Q1, SLLSEU0G](https://www.ti.com/lit/ds/symlink/iso7741-q1.pdf), Oct 2024 | Sections 8.3/8.4, pp33-34; DWW package |
| D24 | [TI UCC27517A-Q1, SLVSC88B](https://www.ti.com/lit/ds/symlink/ucc27517a-q1.pdf), Aug 2015 | Sections 11/12, pp19-21 |
| D25 | [TI TPS7B69xx-Q1, SLVSCJ8B](https://www.ti.com/lit/ds/symlink/tps7b69-q1.pdf), Jan 2015 | Operating conditions; sections 10/11, pp14-15 |
| D26 | [TI TLV170x-Q1, SLOS890C](https://www.ti.com/lit/ds/symlink/tlv1701-q1.pdf), Dec 2019 | Sections 10/11, pp13-14 |
| D27 | [TI TLV431x-Q1, SLVS905B](https://www.ti.com/lit/ds/symlink/tlv431b-q1.pdf), Jul 2024 | Figure 5-18; sections 8.3/8.4, pp22-23 |
| D28 | [TI SN74LVC1G08-Q1, SCES556H](https://www.ti.com/lit/ds/symlink/sn74lvc1g08-q1.pdf), Aug 2026 | Sections 8.3/8.4, p12 |
| D29 | [TI SN74LVC1G04-Q1, SCES482F](https://www.ti.com/lit/ds/symlink/sn74lvc1g04-q1.pdf), Oct 2025 | Sections 8.3/8.4, p12 |
| D30 | [Infineon IKW40N120H3 Rev1.20](https://www.infineon.com/assets/row/public/documents/60/49/infineon-ikw40n120h3-datasheet-en.pdf), Jun 2025 | Package/ratings p3; thermal, electrical and package outlines |
| D31 | [Infineon IPW65R018CFD7 Rev2.0](https://www.infineon.com/assets/row/public/documents/24/49/infineon-ipw65r018cfd7-datasheet-en.pdf), Apr 2021 | Maximum ratings p3; thermal p4; resistance p5; package outlines |
| D32 | [AOS AO3400A Rev3.1](https://www.aosmd.com/res/data_sheets/AO3400A.pdf), Jul 2023 | Ratings pp1-2; thermal test-board notes p2 |
| D33 | [TI TPS3890, SLVSD65A](https://www.ti.com/lit/ds/symlink/tps3890.pdf), May 2016 | CT/reset timing; sections 10/11 pp16–17; DSE package |
| D34 | [TI TLV903x, SNOSDA3H](https://www.ti.com/lit/ds/symlink/tlv9031.pdf), Nov 2025 | Sections 7.3/7.4 p34; DBV package |
| D35 | [TI SN74LVC1G32, SCES219W](https://www.ti.com/lit/ds/symlink/sn74lvc1g32.pdf), Aug 2026 | Sections 8.3/8.4; DBV package |
| D36 | [TI SN74LVC14A, SCAS285AC](https://www.ti.com/lit/ds/symlink/sn74lvc14a.pdf), Apr 2022 | Sections 10/11 pp14–15; D package |
| D37 | [TI CD74HC30, SCHS121E](https://www.ti.com/lit/ds/symlink/cd74hc30.pdf), Apr 2021 | Sections 10/11 p12; PW package |
| D38 | [TI SN74LVC1G74, SCES794G](https://www.ti.com/lit/ds/symlink/sn74lvc1g74.pdf), Sep 2021 | Function/timing requirements; sections 10/11 pp12–13; DCU package |
| D39 | [TI TPS709, SBVS186H](https://www.ti.com/lit/ds/symlink/tps709.pdf), Jul 2021 | Section 8.1.1; sections 9/10 pp15–16; DBV package |
| D40 | [TI TPS7A4700/4701, SBVS204G](https://www.ti.com/lit/ds/symlink/tps7a47.pdf), May 2026 | Pin functions pp3–4; ANY-OUT/capacitors; section 9 p20; RGW package |
| D41 | [TI TL431/TL432, SLVS543S](https://www.ti.com/lit/ds/symlink/tl431.pdf), May 2024 | Stability plots; sections 9.4/9.5 p31; pin maps |
| D42 | [TI TLVH431/432, SLVS555N](https://www.ti.com/lit/ds/symlink/tlvh431.pdf), Jun 2024 | Stability plots; sections 8.3/8.4 pp20–21 |
| D43 | [TI LM339B family](https://www.ti.com/lit/ds/symlink/lm339b.pdf), retrieved 2026-10-10 | Application, power and layout sections; D package |
| D44 | [TI SN6507, SLLSFM0A](https://www.ti.com/lit/ds/symlink/sn6507.pdf), Jun 2022 | Sections 9.2.2.4/5 pp24–25; emissions p27; layout p30; DGQ package |
| D45 | [Vishay VOL628A, document82401 Rev1.9](https://www.vishay.com/docs/82401/vol628a.pdf), Feb 2023 | Electrical/typical pp2–7; package p8; solder/handling p9 |
| D46 | [TI SN74LVC1G10](https://www.ti.com/lit/ds/symlink/sn74lvc1g10.pdf), retrieved 2026-10-10 | Power supply and layout sections; DBV package |
| D47 | [TI SN74LVC1G332](https://www.ti.com/lit/ds/symlink/sn74lvc1g332.pdf), retrieved 2026-10-10 | Power supply and layout sections; DBV package |
| D48 | [TI SN74LVC1G17](https://www.ti.com/lit/ds/symlink/sn74lvc1g17.pdf), retrieved 2026-10-10 | Sections 8.3/8.4; DBV package |
| D49 | [TI TPS62933, SLUSEA4D](https://www.ti.com/lit/ds/symlink/tps62933.pdf), Aug 2022 | Variants; section 12.1 p40; DRL package |
| D50 | [TI TPS3703-Q1, SBVS344D](https://www.ti.com/lit/ds/symlink/tps3703-q1.pdf), Mar 2021 | Sections 10/11 p26; DSE package |
| D51 | [TI OPAx388, SBOS777D](https://www.ti.com/lit/ds/symlink/opa2388.pdf), Jul 2020 | Sections 9/10 pp25–26; thermoelectric layout |
| D52 | [TI TLV906x, SBOS839N](https://www.ti.com/lit/ds/symlink/tlv9062.pdf), Jul 2026 | Section 8.4 p27; cleaning/leakage; DBV/D packages |
| D53 | [ADI AD8436 RevE](https://www.analog.com/media/en/technical-documentation/data-sheets/AD8436.pdf), Mar 2017 | Applications pp12–15; CAVG dielectric/leakage; package p20 |
| D54 | [Microchip MCP3202, DS21034F](https://ww1.microchip.com/downloads/en/DeviceDoc/21034F.pdf) | Analog input/acquisition; minimum clock; section 6.4 Layout Considerations; SN package |
| D55 | [TI TCA9555, SCPS200E](https://www.ti.com/lit/ds/symlink/tca9555.pdf), Apr 2019 | Functional defaults; sections 11/12 p31 |
| D56 | [TI TLV760, SNVSAV1A](https://www.ti.com/lit/ds/symlink/tlv760.pdf), Oct 2017 | Stability/thermal; sections 9/10 p14 |
| D57 | [TI SN74LVC2G17](https://www.ti.com/lit/ds/symlink/sn74lvc2g17.pdf), retrieved 2026-10-10 | Sections 11/12; DBV package |
| D58 | [TI SN74LVC1G14](https://www.ti.com/lit/ds/symlink/sn74lvc1g14.pdf), retrieved 2026-10-10 | Sections 7.3/7.4; DBV package (DPW example is different) |
| D59 | [TI SN74LVC244A](https://www.ti.com/lit/ds/symlink/sn74lvc244a.pdf), retrieved 2026-10-10 | Sections 8.3/8.4; PW package |
| D60 | [TI ADS131M08, SBAS950B](https://www.ti.com/lit/ds/symlink/ads131m08.pdf), Feb 2021 | Sections 10/11 pp103–104; PBS package |
| D61 | [TI AMC3330, SBASA34B](https://www.ti.com/lit/ds/symlink/amc3330.pdf), Aug 2024 | Sections 7.4/7.5 p27 onward; isolated supply bypass network |
| D62 | [TI SN74AHCT125, SCLS264R](https://www.ti.com/lit/ds/symlink/sn74ahct125.pdf), Feb 2024 | Operating voltage; sections 8.3/8.4 pp11–12; PW package |
| D63 | [TI TPS1H100-Q1, SLVSCM2D](https://www.ti.com/lit/ds/symlink/tps1h100-q1.pdf), Dec 2019 | Section 10 p37; exposed-pad solder/via treatment |
| D64 | [ADI LTC6993-1/-2/-3/-4 RevF](https://www.analog.com/media/en/technical-documentation/data-sheets/LTC6993-6993-1-6993-2-6993-3-6993-4.pdf) | Supply Bypassing and PCB Layout Guidelines p20; orderables |
| D65 | [ST STM32G071x8/xB, DS12232 Rev5](https://www.st.com/resource/en/datasheet/stm32g071rb.pdf) | Pin assignments; figure13 and notes p54; LQFP64 package |
| D66 | [ST LD1117, DocID2572 Rev38](https://www.st.com/resource/en/datasheet/ld1117.pdf) | Description p1; fixed3.3V electrical data; thermal/package information |
| D67 | [Vishay VO617A, document83430](https://www.vishay.com/docs/83430/vo617a.pdf), retrieved 2026-10-10 | Ordering option7; insulation table; package and solder profile |
| D68 | [RECOM R-78HB/W Rev4/2021](https://recom-power.com/pdf/Innoline/R-78HB-0.5_W.pdf) | Characteristics/application capacitor notes; /W mechanical drawing |
| D69 | [RECOM R24C2T25/R Rev1-2024](https://g.recomcdn.com/media/Datasheet/pdf/.fnTvgaLZ/.tb6b85aa8e0611678e078/Datasheet-746/R24C2T25_R.pdf) | Typical Application, Recommended Layout, Package Dimensions, Derating Graph; [official product/download page](https://recom-power.com/en/rec-s-R24C2T25%21sR.html) |
| D70 | [MEAN WELL HDR-60 specification](https://www.meanwell.com/Upload/PDF/HDR-60/HDR-60-SPEC.PDF), retrieved 2026-10-10 | Mechanical/mounting, derating, installation-manual reference |
| D71 | [TI SN74LVC1G04 catalog](https://www.ti.com/lit/ds/symlink/sn74lvc1g04.pdf), retrieved 2026-10-10 | Sections 8.4/8.5; DBV package |
