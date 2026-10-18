# Impulse Labs induction stove — teardown evidence and comparison — 2026-10-14

<!-- provenance: commit=84c5e5b61000d45eec09834cb23e6bba8fa51169 dirty=true -->

Mined from the Munro Live teardown *"Impulse Labs: Engineering a Better
Induction Stove"* (YouTube `Sue70X7ZeS0`, published 2026-02-06, 39:59, 4K).
The video is narrated by an Impulse engineer and shows hardware from several
build stages. Impulse's own patents fill in what the video only shows. No
code, `.ato`, board file or gate was modified.

Every claim is tagged:

- **[said mm:ss]**: stated on camera. From a local Whisper transcript,
  cross-checked against YouTube's auto-captions.
- **[seen mm:ss]**: visible in a frame at that timestamp. Read from 4K
  stills.
- **[patent X]**: read from the patent's full text (Google Patents HTML,
  fetched 2026-10-14). Not from a summary.
- **[inferred]**: our reading. Not stated and not measured.
- **[press, unverified]**: a secondary source we did not re-check.

Footage, frames and patent texts are **not committed**: the repo is public and
the footage is copyrighted. Re-create them with `scripts/video_mining/`, which
documents the pipeline and run order in its `README.md`. Frames are cited by
timestamp so anyone with the video can check them.

## Headline findings

| # | Finding | Basis | Consequence for temper |
|---|---|---|---|
| 1 | Impulse drives each coil with a **full bridge on a ~115 V DC bus**. Their patent says half-bridge designs "often do not deliver sufficient power from a lower DC voltage source (e.g., 115 V)". | [patent US12712433B1], [said 22:42] | Independent support for temper's half→full-bridge change (native-21; bus ~170 V peak). Their bus is a stiff battery; ours is unfiltered and follows the rectified line. |
| 2 | Their gate driver is the **TI UCC21540**, the same family as temper's UCC21550. They add **spread-spectrum switching** so the EMI filter can stay small. | [patent US12712433B1] | Spread spectrum is a cheap EMI lever we have not evaluated. Temper's EMI front end is not yet verified. |
| 3 | Their coil is a **9-inch coil "all the way out to the edge"**, with litz windings over radial ferrite bars. | [said 32:48, 14:37], [seen 14:33–16:32] | Same size class as temper (OD ≈ 228 mm), same construction. |
| 4 | **A microcontroller on each coil** handles sensors, the LED ring and safety. The burners are **daisy-chained over CAN**, and this layer is "UL 6730 certified". All other software runs on a tablet-class main computer and can be updated over the air without recertification. | [said 14:48–15:33, 22:04–22:17], [seen 16:25] | Temper's safety is hardware-only (TCO loop, latches, fail-safe PERMIT). There is no second safety MCU. Theirs is a different, deliberate trade-off. |
| 5 | **The pan sensor is the hardest part of the program**, per the engineer [said 17:01]. IR was rejected: it can't see a pan below ~250 °F through glass-ceramic. A passive contact sensor (Breville Control Freak style) only worked well *with thermal paste*. Contact quality — roughness, warp — dominated their error [said 21:11–21:36]. | [said 17:01–21:53], [patent WO2024178387A2] | **Direct risk flag for temper's R15 passive Pt100 cartridge.** R15's 6.1 s / −0.7 K figures are modelled with contact conductance as a free parameter. Impulse says that parameter is the problem. |
| 6 | Their answer is an **active, self-heated heat-flux sensor**: thermocouple plus an internal heater on a spring plunger through the glass. It targets zero heat flux. The patent claims >4 °C/s ramps, sub-second lag and ~2 Hz sampling at steady state. | [patent WO2024178387A2 / US20240288175A1], [said 19:37–20:28] | Patent-pending (see §8). Temper should not copy it. |
| 7 | **Pan detection pulses the coil before committing power.** An aluminium pan "looks like a short circuit" and would overcurrent the transistors. They have iterated the detection over the air. | [said 23:21–23:54, 27:42–28:22] | Same family as temper's "pulse and listen" (`firmware/components/control/pan_detect.c`: a 20 µs pulse and a ring-down edge count). Ours was written for the legacy half-bridge (2026-01-10) and has not been re-checked against native-21's full bridge and unfiltered bus. Their point that aluminium reads as a short belongs in its test set. |

## 1. System architecture

- **Battery:** LFP, 3 kWh, "6C discharge… can technically push like 18 kW,
  currently rated for about 15" **[said 11:52, 26:15]**. The patent says LFP and
  "up to 3 kilowatt hours" **[patent US12640662B1]**.
- **Bus:** "all of the electronics inside the stove are essentially hanging off
  the DC bus of the battery… DC native" **[said 03:10–03:34]**. The patent's
  example bus is 115 V **[patent US12712433B1]**.
- **Five inverters:** "one per coil… then there's the inverter charger… the
  bi-directional inverter" **[said 23:56–24:10]**.
- **Grid connection:** a 120 V plug or a 240 V hardwire cable. It can backfeed
  on 240 V but not on 120 V, "for compliance reasons, not technical"
  **[said 07:46–09:32]**.
- **Power:** "50 all the way up to 10,000 [W]… in single digit watt increments",
  sustained 10 kW into a medium pan **[said 30:13–30:22, 31:36–32:08]**.
  Temperature mode runs from room temperature to 482 °F **[said 30:29–30:33]**.
- **Cooling:** "air cooled with a blower fan" **[said 24:45]**. The battery is
  also air cooled **[said 26:13]**.
- **Build stage:** "we're in mass production now" **[said 03:24]**. The drive
  boards shown are DVT-era units, marked "DVT" in marker on the heatsink
  **[seen 03:28]**.

## 2. Induction drive board

**Seen** (best views 03:28.75 and 22:38.75; overview 22:41–22:45):

- Two long PCBs, each under a full-length finned aluminium heatsink in two
  sections.
- **3-lead through-hole power devices** (TO-247 class), in groups of four
  along the heatsink sides. Each is held by an **individual screwed spring
  clip**, not a screw through the tab, with a white insulating sheet behind
  it.
- At one end of each board: three grey rectangular box capacitors (probably
  film; the moulded markings are illegible at 4K) and a cluster of small
  polymer capacitors under the heatsink overhang. A large black block sits at
  the other end.
- **Not visible:** device markings (the clips cover the faces) and any board
  surface under the heatsinks. No heatsink-off frame exists in the video.

**Said:**

- "A half bridge or H bridge type design driving a resonant tank, with
  resonance between a capacitor and the inductor, the inductor being the coil"
  **[said 22:42]**.
- Coil inductance "changes depending on how much core material is around the
  coil. The core material ends up partially being the pan" **[said 23:00]**.
- The older build had "a bigger heat sink… you over-provision, then you
  start cutting" **[said 24:19–24:35]**. That remark refers to the
  inverter-charger chassis shown at 24:11–24:35.

**Patent US12712433B1**, "Appliance with modular full-bridge driver and DC
source". Impulse Labs Inc, filed 2026-01-27, granted 2026-08-18. FIG. 3 is
described as an example implementation:

| Function | Part / value as written in the patent |
|---|---|
| Topology | Full bridge (H bridge), two legs; "MOSFETs or IGBTs"; FIG. 3: "a set of four n-channel… FETs" |
| DC source | "e.g., 115 V from a battery pack" |
| Frequency | "between about 20 kHz and about 100 kHz"; optional spread-spectrum modulation of the PWM carrier |
| Power | "up to 10 KW" |
| Gate driver | TI **UCC21540** isolated half-bridge driver, "isolation up to 5 kVrms" |
| DC bus current | Allegro **ACS773** (Hall, isolated) |
| Coil current | Allegro **ACS37612** (isolated, high-frequency AC) |
| Bus voltage | TI **AMC1350** across a divider |
| LV rails | **LNK3207D** HV buck (15 / 5 / 3.3 V) |
| Other | MOSFET NTCs, high-voltage-present LEDs, resonant capacitor bank, an EMI shield between coil and target, and a frame acting as heatsink and second EMI shield |

**[inferred]** There are two boards, said to be "one on each side", and four
burners, so each board most likely carries two bridges. Two heatsink sections
per board fits that reading.

## 3. Coil assembly and coil-centre board

- "We designed all the magnetics for this from scratch… ferrite core and then
  litz wire windings" **[said 14:32–14:39]**. It is a 9-inch coil "all the way
  out to the edge" **[said 32:48]**.
- **Seen** (14:33–14:54 hand-held, 16:11–16:32 underside, 03:40 top-down):
  - Copper litz windings and dark radial ferrite bars in a black moulded
    carrier.
  - A **C-shaped PCB around a central bore**, carrying a QFP microcontroller,
    pin headers and a ribbon cable.
  - White insulated coil leads ending in ring lugs.
  - Successive generations shown side by side: "2024-ish… late 2024, early
    2025… mass production" **[said 16:15]**.
- **Coil-centre MCU:** "that LED ring… is actually controlled by a
  microcontroller here, which is also doing all of the sensor aggregation. So
  that way we only run CAN bus off of this… you can daisy chain as many
  burners as you want" **[said 14:48–15:06]**. Analog sense and control lines
  run to the induction driver board **[said 15:10]**.
- **Certification split:** "this ended up being like UL 6730 certified for all
  the control system. So that way… we can run arbitrary software on the main
  computer… whereas this is ensuring that… the system doesn't melt itself"
  **[said 15:19–15:33]**. Both the Whisper and YouTube transcripts read
  "UL 6730"; it is probably UL 60730-1 **[inferred]**.
- **Auxiliary sensing:** "auxiliary temperature sensing, which gets you…
  from the UL side of stuff", separate from the pan-contact sensor
  **[said 15:37–15:45]**.
- **Leads:** a production-process note on the coil leads: "started with
  solder, go to a hot bar… or hot crimping" **[said 16:37–16:43]**.
- **Not established:** turns, litz strand count, ferrite count and
  dimensions, coil inductance, resonant capacitor value.

## 4. Pan temperature sensor

**Why they built their own** **[said 17:01–19:37]**:

- **IR was rejected.** Glass-ceramic passes only certain wavelengths, so IR
  "can't see a pan that is below like 250 degrees", and shiny stainless makes
  it worse.
- **Breville Control Freak contact sensor:** "way better if I put thermal
  paste on the sensor… otherwise it doesn't actually have good ability to…
  work across varied contact scenarios", and customers will not apply paste.
- **So they made an active sensor:** "It has thermocouples in it… but it also
  has a heater", a "heat flux sensor that targets zero heat flux"
  **[said 19:37–20:28]**. They train models to report the *top* surface of
  the pan **[said 20:36]**.
- **Dominant error source:** "there's a huge variability in how good the pan
  contacts the sensor… how rough the bottom of the pan is… a warped pan…
  we had to basically build in compliance" **[said 21:11–21:36]**.

**Patent WO2024178387A2**, "Temperature sensing device". Impulse Labs Inc,
priority 2023-02-23, filed 2024-02-23; US national phase is
**US20240288175A1** (pending).

- **Mechanism:**
  - spring-loaded plunger
  - sensor cap that is a non-ferrous thin sheet ("such as a stainless steel
    316")
  - silicone diaphragm or gasket
  - sliding ramp and compliant bumper
  - "packaged reflective" photosensor that determines plunger position, i.e.
    pan presence and seating
- **Sensing:** a "self-heated flux sensor that generates the heat using an
  internal heater"; "type T thermocouple, nonferrous RTD".
- **Performance as claimed by the patent:**
  - ramp rate "greater than 4 degrees C per second" with "sub-second" lag
  - sampled "on the order of 2 Hz" during steady cooking under a PID loop
  - preheat of the sensor itself under PID
- **Not used:** IR appears zero times in the text.

**Validation method:** thermocouples welded into pans, logged over USB
through the stove, and used to tune the temperature estimate per pan type
**[said 29:16–29:36]**.

## 5. Main controller

- **Processor:** "a tablet class processor… to control the screen… we're
  able to write a lot of our algorithms on this because we've done the safety
  stuff there [on the per-coil MCU]… without having to recertify"
  **[said 22:04–22:17]**.
- **Connectivity:** OTA updates, Wi-Fi, "a bunch of antennas"
  **[said 22:26–22:31, 34:43]**.
- **Seen** (22:28, 22:31): a long board with two BGA devices, one under a
  small heatsink; a wireless module; USB-C; a display flex connector; a pin
  header. One arc-shaped board, a knob encoder, and small sensor/UI boards.
  No part numbers are legible.
- **[press, unverified]** Impulse's open-source licence list
  (resources.impulselabs.com) shows ~700 Rust crates, including Wayland, DRM,
  GStreamer and socketcan. That points to a Linux-class UI computer with CAN
  **[inferred]**.
- **Knobs:** magnetic and removable; "you can pull the knob off and it kills
  power on the system" **[said 33:32–33:35]**.

## 6. Pan detection and control behaviour

- **Pulsing before power:** "If you naively just put power in, you will
  overcurrent… the transistors in the drive… What you need to do is detect
  that in a way that is not disruptive… you end up pulsing ahead of time
  before you… fully commit" **[said 27:44–28:08]**.
- **Aluminium:** an aluminium pan "effectively looks like a short circuit on
  this side" **[said 28:15–28:22]**. Pan detection classifies metal type and
  coverage **[said 23:27–23:39]**, and was improved over the air
  **[said 23:40]**.
- **Ramp limiting:** "we do some kind of dynamic throttling… we do constrain
  you in terms of ramp rate in some cases" **[said 32:23]**.
- **Near boiling:** "the temperature control algorithm has to behave a
  little differently around [boiling]" **[said 34:04–34:20]**.

## 7. Comparison with temper (native-21 stage15b)

Temper values come from the current design sources: `hardware/README.md` and
`CURRENT.tsv`, `hardware/native21-stage15b/source/elec/src/power_stage_120v.ato`
and `parts.ato`, `output/temper-manufacturing-r42/design/rNN/DECISIONS.md`,
`docs/hardware/TANK_COIL_SPECIFICATION.md` (reissued 2026-10-10) and
`docs/hardware/power-section-120v/POWER-SECTION.md`. **All temper performance
figures are modelled; native-21 has no physical measurements.**

| Area | Impulse | Temper | Reading |
|---|---|---|---|
| Topology | Full bridge, one per coil | Full bridge, single zone (`power_stage_120v.ato:5`) | Same choice, reached independently |
| DC bus | ~115 V battery, stiff | Unfiltered rectified 120 V, ~170 V peak, 18.4 µF film (`parts.ato:126`) | Ours sags to zero each half-cycle, theirs never does. Line-synchronous control is a temper-only problem. |
| Switches | "MOSFETs or IGBTs"; FIG. 3 four n-FETs; TO-247-class, clip-mounted [seen] | 4 × IPW65R018CFD7 650 V SJ MOSFET, TO-247-3 | Same class |
| Device mounting | Individual spring clip per device, insulating sheet [seen 03:28] | Clamped through a 2 mm insulator onto a spreader bar with a pressure strip and comb spring; insulator part **open** (R27) | Data point for R27: a shipping product uses per-device clips |
| Gate driver | UCC21540, 5 kVrms | 2 × UCC21550BDWKR, isolated bias (stage 14) | Same family |
| Coil current sensing | ACS37612, Hall, isolated | CST3015-100ED CT, 1:100, burden + LM339 | Different. CT has no DC path; Hall is self-powered and isolated. No change suggested. |
| Bus voltage sensing | AMC1350 | AMC1311 | Same family |
| EMI | Spread-spectrum switching; Al/Cu shield between coil and pan; frame as second shield | X2 / CM-choke / Y1 front end; no metal shield (ferrite acts as shield, R33–R35); not EMI-verified | **Evaluate spread spectrum** before growing the filter |
| Coil | 9" (≈229 mm), litz, radial ferrite | OD ≈ 228 mm, 21.9 turns, 270 × 0.10 litz, 10 × PC95 radial bars (R36/R37) | Same size and construction |
| Coil-eye board | C-shaped PCB with MCU, CAN, LED ring, aux temperature sensing | Sensor cartridge plus NTC/TCOs wired back; no coil-eye MCU | Theirs scales to four burners. With one zone we don't need it. |
| Safety architecture | Per-coil MCU certified as the safety layer ("UL 6730" said); free software on the main computer, OTA | Hardware-independent: TCO loop removes gate supply, BUS_FAULT latch, fail-safe PERMIT; ESP32-S3; no safety MCU | Both valid. Ours avoids a software safety class entirely. Theirs buys OTA freedom. Certification target still **open** (UL 858 vs UL 1026). |
| Pan sensor | Active self-heated heat-flux sensor, plunger through the glass | R15 cartridge: 4-wire Pt100 under a 96 % alumina cap, spring, silicone collar through the glass; modelled τ63 = 6.1 s, −0.7 K (R15 G1) | See below |
| Pan detection | Pulse before full power; classifies metal type and coverage | Firmware "pulse and listen" ring-down count (`pan_detect.c`, legacy half-bridge era, 2026-01-10); hardware backstop is the shunt OCP (~93 A, `power_stage_120v.ato:553`) and tank CT OCP (~70 A, `:735`) | Re-validate on native-21; add aluminium/copper and small-pan cases |
| Power | 50 W–10 kW per burner (battery-assisted) | 1.8 kW target; commissioning ceiling 1,239 W modelled hold | Not comparable (battery) |
| Cooling | Blower, air | Delta 97 mm blower + coil jet plenum; 134 °C FET row modelled | Same approach |

**The pan sensor is the comparison that matters.** R15's thermal screen
(`output/temper-manufacturing-r42/design/r15/DECISIONS.md`) already sweeps pan
contact conductance from 300 to 3000 W/m²K. Impulse's field experience is
that this term is the *dominant* error, and that a passive contact sensor
works well only with paste [said 19:07–19:31, 21:11–21:36]. Before any bench
work (per "vet in the box"):

1. Report R15's response and error at the *low* end of the conductance sweep
   (dry, rough or warped pan), not the 1000 W/m²K midpoint.
2. Write the acceptance criterion as a ramp-tracking error at a stated
   heating rate. Impulse targets >4 °C/s. Temper's power level gives slower
   ramps, which is a relief worth quantifying.
3. Treat sensor *seating*, i.e. whether the cartridge is actually touching
   the pan, as a measured state. Impulse uses a photosensor (patent-pending:
   see §8). A cheaper prior-art route is the Control Freak's "must be pressed
   to run" interlock.

**Stale doc found:** `docs/SENSOR_MOUNT_DESIGN.md` (2025-12-21) still
describes a PT100 *under* 4 mm of glass with grease. R15 superseded it with a
through-glass cartridge. The doc should carry a supersession note.

## 8. Patent landscape (Impulse filings only)

This is a claim-level reading, not a legal opinion. A freedom-to-operate
opinion from a patent attorney is needed before shipping. It would also need
to cover other assignees (Breville, BSH, Whirlpool, Midea, Copper).

| Filing | Status | Independent claims require | Temper |
|---|---|---|---|
| **US12712433B1**, modular full-bridge driver | Granted 2026-08-18 | Claims 1 and 11: one DC source supplying *different* DC outputs to a *first and a second appliance*, a sensor, a processor, and a full bridge producing different AC outputs for each appliance | No shared DC source powering multiple appliances. **Low risk; avoid a shared power module serving different appliance types.** |
| **US12640662B1**, modular power manager | Granted 2026-05-26 | Claims 1, 8, 15: a housing that docks to appliances, with a battery and a multi-mode inverter, identifying the appliance type | No battery. Not applicable. |
| **US20240288175A1** (appl. 18/586,274; also WO2024178387A2, EP4670461A2, CN120937497A, JP2026508848A, KR20250149710A, MX2025009916A), temperature sensing device | **Allowed 2026-08-11, not yet issued as of 2026-10-14.** Prosecution: non-final rejection mailed 2026-02-13; response 2026-05-12; allowance 2026-08-11. The **allowed claims are probably narrower than those filed** and have not been read. Get them from USPTO Patent Center (image file wrapper: 2026-05-12 claims and the notice of allowance). The examiner cited Watlow **US12135147B2** (integrated heater-sensor, priority 2017). | Claim 1 *as filed*: a sensor package, a plunger assembly holding it, and a support base. Dependents add spring, self-heated flux sensor, compliant bumper, sliding ramp, etc. | Read literally, the R15 cartridge resembles *filed* claim 1. But filed claim 1 had strong prior art (below), and the claims were amended before allowance. R15 also has none of the dependent features: it is passive, with no heater, no photosensor, no ramp and no bumper. **Read the allowed claims before adding any heater or position sensing to the cartridge.** It becomes enforceable on issue, likely within weeks. |
| US20240195199A1, appliance with integrated energy storage | Pending | Battery + bidirectional converter in an appliance | Not applicable without a battery |

**Prior art predating Impulse's 2023-02-23 priority date** (for the plunger
sensor):

- **Morphy Richards GB2552531B**, "Temperature sensor in induction cooker".
  Priority 2016-07-28, granted 2019-10-23, active, **GB only; no US family
  found**. Claim 1: a sensor in an aperture in the cover plate, resiliently
  biased to protrude, with a silicone seal, using an *NTC in an aluminium
  housing*. R15 cites this design as its basis. R15 uses a Pt100 under
  alumina, so it does not meet GB claim 1's NTC/aluminium elements
  **[inferred, not legal advice]**.
- **Breville | PolyScience Control Freak** (Good Design Award 2016): "a
  sensor raised above the cook top surface… contacts the pan directly". This
  is product prior art and weaker than a patent. Breville's own
  **US10362639B2** (priority 2014) covers control and fan logic, not the
  sensor hardware.

Patent texts used here are saved locally under
`~/temper-media/Sue70X7ZeS0/patents/` (not committed).

## 9. Not established

- Drive switch technology and part number (patent: "MOSFETs or IGBTs"); the
  resonant capacitor type and value; the per-zone sustained power limit at
  120 V input.
- Coil turns, litz specification, ferrite count and dimensions.
- The coil-centre MCU part, the main SoC, and the "UL 6730" standard number.
- FCC filings: none found. fccid.io and fcc.report refused automated access.
  Part 18 consumer equipment need not publish a grant, so absence carries no
  information.
- Impulse's install and user-guide PDFs (resources.impulselabs.com) were not
  opened. They may list electrical ratings.

## Appendix — key frames

| Time | Subject | Why |
|---|---|---|
| 03:28.75 | Drive boards, side oblique | Clip-mounted TO-247 rows, film-capacitor end cap |
| 22:38.75 | Drive boards ("DVT") | Second angle on the same |
| 03:40.75 | Coil, top-down | Centre PCB, ferrite ring |
| 14:33–14:54 | Coil hand-held | Centre PCB, litz, ferrite bars |
| 16:25.25 | Two coils underside + main controller | C-shaped centre board around the sensor bore |
| 17:56.25 | Coil plate with thermal-paste patch | Sensor-contact discussion |
| 22:28.25 | Main controller board, arc board | SoC, wireless module, display FFC |
| 24:11–24:35 | Inverter-charger (older build), lid off | EMI filter, bulk capacitors, magnetics |
| 25:50 | BMS in pack enclosure | Stacked ADI-based boards [said 25:50–26:06] |
