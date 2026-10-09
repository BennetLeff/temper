# Precharge and catch protection — round 5

**PC12.5 is now the selected digital candidate, with inspected primary pulse
curves and a revised mount. The catch gains explicit power copper and a rerouted
anode termination. Protection coordination is still incomplete; this packet
does not release a powered prototype.** Native19 and round4 evidence are unchanged.

The authoritative cross-team contract is [interface.json](interface.json),
version `PC125-CATCH-R5-2`. Calculations live in [coordination.rs](coordination.rs);
the Python file is a CadQuery adapter, not a second electrical calculation owner.

## Precharge selection and fault demands

Use two **Ohmite/ARCOL HS400 25R J** in parallel, each with its own series
**Sensience MICROTEMP G4A01128C** secondary thermal cutoff. The resulting branch
is 12.5 Ω nominal, 11.875–13.125 Ω at the resistance reference condition.
The older 11 Ω HS200 and rejected 88 Ω arrangement are not this revision.

The [Ohmite primary page](https://www.ohmite.com/hs/) specifies a heatsink-mounted
400 W part and a 4,000 W, five-second single-pulse overload. Its actual blue
HS400 energy graph was retrieved and visually inspected this round. Across
23.75–26.25 Ω it lies above **2,000 J**, used here as a deliberately coarse
screening floor rather than an invented precise digitization. The inspected
derating graph begins declining above 25°C and reaches zero at 250°C.
This does not establish a hot or repetitive overload rating.

At 140 V RMS into a hard downstream short, one minimum-value resistor sees
825.263 W cycle-average, 1,650.526 W peak and **412.632 J in 500 ms**. Each part
passes these conditional cold single-pulse screens. The other branch opening
does not increase the survivor's voltage-driven power; it changes admission and
must fail POST. A **shorted resistor or welded bypass shorts the entire parallel
network**: none of these energy screens protects that event. At a wrong-source
240 V, peak demand is 4,850.526 W, exceeding the published overload-power screen.
Source qualification and its failure cases remain essential.

[precharge-corners.csv](../../../../../output/temper-prototype-closure/round5/protection/precharge-corners.csv)
contains 24 demands with maximum closure-phase energy, including non-integral
line cycles. It is a demand calculation, not a substitute for the joined model's
reactive filter and actual per-branch voltage history.

The G4 family explicitly supports resistive and inductive applications at
10 A and 8 A respectively at 250 VAC. Its 128°C version has a −5/+0°C functioning
range and 113°C holding temperature. The 2022 full catalogue lists 205°C maximum
overshoot while the 2023 G4 product sheet lists 350°C: **use 205°C conservatively
pending exact suffix/lot confirmation**, and do not turn either figure into an
allowed enclosure temperature. This selection removes the Cantherm part's
unresolved direct-heater warning. It still requires the manufacturer's actual
application evaluation. No cutoff response within 500 ms is credited.
[Sensience G4 product sheet](https://www.sensience.com/wp-content/uploads/2023/10/G4-MicroTemp-Product-Information.pdf),
[full catalogue, pp14–18](https://www.sensience.com/wp-content/uploads/2022/12/Microtemp_Catalog.pdf).

The cold prototype contract is deliberately restrictive:

- Document winding/case equilibrium at true case temperature ≤25°C before an
  attempt. A measured NTC value ≤20°C only meets this if the complete ±5°C
  error/lag allocation is demonstrated. A rapidly cooled case does not prove a
  cold winding. No timed automatic restart is authorized.
- Isolate and measure **each** resistor using four wires, with the other branch
  and bypass disconnected. Its full measurement-uncertainty interval must lie
  inside 23.75–26.25 Ω. A parallel-pair scalar cannot replace these two results.
- Consume the attempt-scoped POST; a fault requires inspection, a new isolated
  POST and a separate eligible RESET/START. Thermal-cutoff continuity is included.
- The 446.458 ms hardware timeout plus an allocated 24 ms contact opening leaves
  29.542 ms for all other timing under a 500 ms source-present target. That
  remaining detection/driver/rail/contact-arc chain **has not been proven**.

## Mechanical implementation

[PC12.5 pod STEP](../../../../../output/temper-prototype-closure/round5/protection/pc125-pod-layout.step)
replaces the old HS200 envelopes with two vertically stacked HS400 bodies on the
existing 340 × 210 × 6 mm hot plate. Each drawing-derived flange is 182 mm long,
55.5 mm maximum height and 4.3 mm thick; body projection is 30 mm maximum. The
eight Ø5.4 mm mounting locations are recorded in
[hardware-geometry.json](../../../../../output/temper-prototype-closure/round5/protection/hardware-geometry.json).
The corrected plate pattern has 100 mm longitudinal and **45 mm transverse**
centre spacing. Its transverse datum is the centre of the authored 55.5 mm
maximum flange envelope; supplier edge tolerances remain unestablished. The
previous 44.7 mm pitch mistakenly used the 5.4 mm hole diameter as an edge
offset. The left flange pair now explicitly uses the supplier's 8 mm long,
5.4 mm wide longitudinal slots; the plate holes remain centred round drills.
Replay now rejects the former pitch independently of the CAD generator.
The 22-solid assembly reimports valid and has no nominal overlap of the new
parts with retained pod context. The hot plate remains a thermal mass/mount,
**not a characterized 800 W continuous heatsink**. Mount flatness, interface
material/thickness, screw preload and protective earth continuity still need
resolved specifications. Cutoff coupling blocks and initial flying-lead exits
are labeled reservations; the supplied 300 mm minimum leads are not fully
routed or arbitrarily declared trimmable.

[Catch power interposer STEP](../../../../../output/temper-prototype-closure/round5/protection/catch-power-interposer.step)
contains an unplated carrier, a 1 mm C110 anode conductor and a one-piece machined
cathode link. Actual diode lead holes and the separate anode M4 landing at world
[53.5,338.8] mm replace the old direct wire-to-lead endpoint. The cathode copper
is one connected solid, not two interpenetrating parts. The anode wire now ends
at that landing; its 22 mm circular bends and sampled route are regenerated.
The cathode case/spreader is hazardous **CATCH_P**, never PE. No common fastener
bridges anode and cathode; pin1 stays NC. These custom copper pieces require
machining, plating, solder-fill and insulation review. The local anode/cathode
gap remains below the general 8 mm design screen and needs an explicit,
appropriate working-voltage rule; it is not silently waived.

[Combined catch review STEP](../../../../../output/temper-prototype-closure/round5/protection/catch-with-power-interposer-review.step)
still carries the supervisor owner's old sensor envelope. The new native sensor's
three Ø2.7 mm mounting coordinates and JST mating direction are recorded in the
geometry receipt for the integration owner. The 664-solid export is a nominal
review model, not the final populated integration. A remaining insulated-wire
overlap at the anode termination is explicitly listed: the stripped conductor,
lug, boot and joint must replace that envelope before an assembly-fit pass.

Select **TE32994** uninsulated SOLISTRAND M4 rings for Alpha3080 12 AWG, replacing
the earlier insulated lug whose support window excluded the wire's minimum OD.
The terminal accepts 2.62–6.64 mm² copper and has a 4.34 mm stud hole; the wire's
3.29 mm² conductor is in range. TE's family guide identifies **49935**, position3
for 12–10 AWG. Provide independent wire restraint and a guarded joint; an
uninsulated terminal is not touch protection. Final strip length, crimp setup,
visual acceptance and pull test must follow the actual instruction sheet/tool.
[TE32994](https://www.te.com/en/product-32994.html),
[TE tooling guide](https://www.te.com/content/dam/te-com/documents/industrial-automation-and-control/global/1773464-2_QRG_SOLISTRAND_08-2013.pdf).

US141 remains the selected holder and is not a load-break switch. Its current
product page identifies the exact Z331153, 14×51 mm, 1000 VDC UL model. However,
primary documents disagree on terminal torque: 3.5 Nm maximum versus 35 lb-in
(3.95 Nm) suggested. Terminal locations, stripping, allowed ferrules, sideways
installation and hinge sweep remain supplier-drawing inputs. Do not invent a
torque or reuse the old rectangular service envelope as a hinge solution.
Retain the procedure requiring removal of the adjacent hood panel after verified
isolation/discharge. [Mersen product](https://www.mersen.com/en/products/ultrasafe-us14-modular-fuse-holders/z331153-us141),
[current holder catalogue p17](https://www.mersen.com/sites/default/files/medias/files/2025-05/FB-Fuse-Blocks-and-Holders-Mersen-EN.pdf).

## Fault-current and protection result

The closed-form RLC study is independent of the formerly unconverged 748 A
switching result. It sweeps **assumed** 0.1/1/3 µH and 0.02/0.05/0.08 Ω; these
are sensitivities, not extracted limits. See
[prospective-capacitor-faults.csv](../../../../../output/temper-prototype-closure/round5/protection/prospective-capacitor-faults.csv).

- A local short across maximum 51.7 µF at the 250 V guard allocation releases
  1.615625 J. The sensitivity grid produces approximately 0.86–4.16 kA. That
  loop can bypass FC1 and the diode; neither upstream fuse nor gate disable
  contains it. Physical capacitor failure/arc containment remains required.
- Native bulk/local capacitors alone, using an explicit +10% 6.38 µF allocation
  at 198 V, yield 264–1,403 A first peaks and 0.480–2.474 A²s in the first lobe.
  The latter is below the fuse's catalogue 4 A²s prearc figure, so do not assume
  the fuse interrupts that first impulse. Line/filter/tank contributions are
  additional and belong in the joined model.
- FWP-10A14F is actually rated 700 VDC and 50 kA DC interrupting capacity. Its
  published **22 A²s clearing value is at 700 VAC**, not an installed DC result.
  Actual prospective source current, L/R, prearc tolerance, minimum interrupting
  current and DC arc voltage/clearing integral remain required. The Eaton guide
  explicitly describes DC time-constant dependence and low-overcurrent limits.
  [Eaton product](https://www.eaton.com/ca/en-gb/skuPage.FWP-10A14F.html),
  [720025 pp2,5](https://www.eaton.com/content/dam/eaton/products/electrical-circuit-protection/bussmann-iec-high-speed-semi-conductors-fuses/bussmann-iec-ferrule-high-speed-fuses/eaton-bussmann-series-fwp-ferrule-high-speed-fuses-datasheet-720025-en-gb.pdf),
  [application guide p21](https://www.eaton.com/content/dam/eaton/products/electrical-circuit-protection/bussmann-iec-high-speed-semi-conductors-fuses/eaton-bussmann-series-high-speed-fuses-application-guide-br132015en-en-us.pdf).
- IDW40G65C5's 153 A / 118 A²s hot rating applies to its specified 10 ms
  half-sine at150°C. Its 1,432 A peak applies to 10 µs at25°C. Neither may be
  stretched into an arbitrary hot microsecond pulse. Its forward linearization
  is stated for currents **below80 A**; do not extrapolate it to the kA cases.
  The diode case mounting torque is 0.5 Nm typical,0.7 Nm maximum; RθJC is0.8 K/W
  maximum, but no installed case-to-spreader thermal resistance is established.
  [Infineon Rev2.2 pp4,8](https://www.infineon.com/assets/row/public/documents/24/49/infineon-idw40g65c5-datasheet-en.pdf).

[Conductor demands](../../../../../output/temper-prototype-closure/round5/protection/conductor-demands.csv)
calculate copper-only adiabatic heating from explicit resistivity, heat capacity
and temperature coefficient. They do not invent an insulation k-factor or prove
contact/crimp/solder survival. F0/K1/K2 remain uncoordinated for the installation's
prospective short circuit; no claim that a mains fuse saves the native bridge is made.

## Geometry for the coupled model and remaining closure

[closed-loop-topology.json](../../../../../output/temper-prototype-closure/round5/protection/closed-loop-topology.json)
has a machine-checked closed sequence from J8 through fuse, diode and capacitor
back to J10, with actual authored wire samples. **It is a geometry scaffold,
not a completed field solution.** Holder internals, die/bond connections,
distributed capacitor internals and native-bus closure have explicit surrogate
labels. Extracting that scaffold does not make their assumed shapes real.
The capacitor port closure is not a physical DC conductor.

Remaining digital/supplier work: resolve those internal paths or qualified
terminal parasitic models; installed diode thermal joint and conductor-gap rule;
exact fuse/holder DC envelope; source-fault/contact coordination; final lead,
cutoff and sensor-card mounting; analog timing/measurement uncertainty. These
are not all blocked by missing assembled hardware. Physical gates are then
crimp/solder coupons, pull/service fit, insulation, temperature/overshoot and
installed fault captures. No order, source energization or supplier message was made.

Run [replay.sh](replay.sh) to reproduce six calculation tests, all54 demand rows,
nominal CAD, link closure and fresh hashes. Raw primary images remain local in
`/private/tmp/temper-r5-protection`; [sources.json](sources.json) records their
identity without redistributing vendor artwork.
