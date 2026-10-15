# Findings: Impulse mining, round 2

**Scope.** Everything outside the drive board, coil, EMI shield and sensing
chain. Those are covered by `output/temper-coil-driver-r1/` and
`docs/evidence/2026-10-14-impulse-labs-teardown.md`.

**Tags:**
- **seen**: a Munro frame under `~/temper-media/Sue70X7ZeS0/frames/`.
- **said**: the Munro transcript, at mm:ss.
- **yt:id mm:ss**: YouTube captions, under `~/temper-media/<id>/captions.txt`.
- **doc**: Impulse PDFs, under `~/temper-media/impulse-docs/`.
- **inferred**: our reading.
- **model**: computed by a script in this folder.

No frames are in the repo.

## A. Boards

- **A1. Main computer** (seen `t01351.0`, 22:31):
  - u-blox **SARA-R5** cellular module (seen; exact variant illegible), plus
    a second, smaller u-blox module (model illegible; Wi-Fi/BT inferred).
  - **NXP PCA9450C** power-management chip (seen). That points to an
    i.MX 8M-family processor under the heatsink (inferred).
  - Two BGA memory packages with a "Y" logo; vendor unidentified.
  - Connectors and controls: 2× USB-C, RJ45 Ethernet, "J3 PWR IN", a display
    ribbon connector, a header by a "CAN" silkscreen, a DIP switch and a
    tactile button.
  - "Speakers, Bluetooth, Matter" are already fitted but not yet used
    (yt:jgJ89Jr_0a8 14:38).
- **A2. Coil-centre board:**
  - an MCU of about 100 pins (LQFP), marking illegible (seen);
  - a glossy surface, possibly conformal coat (inferred);
  - several 2×3 and 2×4 shrouded headers;
  - "UL 6730" certified, probably UL 60730 (said 14:48).
- **A3. U-shaped boards:** an STM32-class LQFP (faint ST logo, low
  confidence), an RTC coin cell, hazard triangles in silkscreen, and a ribbon
  connector.
- **A4. Knob board:**
  - Hand-labelled "SP Hall-?/131", so a Hall-effect angle sensor (seen).
  - Magnetic viewing film at 25:05–25:16 shows hold-down magnets around a
    two-pole N/S centre magnet.
- **A5. Inverter-charger, DVT build** (`t01451`, `t01475`):
  - 4× Jianghai **CD297** 820 µF capacitors; the voltage digit is hidden.
  - Magnetics marked "**MT 7102**" ×2 and "**LR 5502**", dated YZ 03/24.
    A resonant inductor next to two transformers suggests an LLC or CLLC
    converter (inferred).
  - Input filter: two U-core common-mode chokes with an X-capacitor between
    them; blue Y-capacitors staked with RTV; a board screw to the steel case
    beside the Y-capacitors (an earth bond point, inferred).
  - A Hongfa 3 A auxiliary relay, TO-247 parts on heatsinks, and a taped
    toroid inductor.
- **A6. Low-voltage supply** (TONLY, board "400204-06…"):
  - two isolated stages on one board;
  - two MOVs, toroid common-mode chokes, and a fuse with UL warning text in
    the silkscreen;
  - RTV staking on all tall parts, and 105 °C "RA"-series capacitors with
    date code 2348.
- **A7. Battery management** (low relevance to temper):
  - cell-monitor board "NLCF001", with 51 Ω balance resistors and a
    64-pin-class monitoring chip;
  - an **IP_IN/IM_IN/IP_OUT/IM_OUT** connector, so ADI isoSPI daisy chaining
    (seen, and said "ADI BMS chips").

## B. Munro transcript: items not in earlier notes

| Time | Statement |
|---|---|
| 00:08, 32:23 | They throttle how fast the temperature ramps. |
| 20:36 | Set temperature means the **top surface of the pan**, estimated from trained models. |
| 20:51 | No pan classification is rolled out yet; there is one default profile. |
| 21:11 | Contact roughness and pan warp dominate the variability. |
| 23:39 | Pan detection has been improved over the air several times. |
| 24:18 | Early hardware was over-provisioned, then cut down. |
| 28:35 | An "aluminium-capable" commercial burner turned out to hide a resistive element, so Impulse dropped the idea. |
| 29:16 | Thermocouples are welded into pans and logged over USB through the stove. |
| 30:13 | Power mode runs 50–10,000 W in 1 W steps. Temperature mode runs 68–482 °F. |
| 33:24 | Simmer is 600 W, down to 200 W. |
| 33:35 | Pulling the knob cuts the power. |
| 34:04 | The boiling plateau needs separate handling in the control loop. |
| 37:30–38:30 (captions) | The inside of the sensor recess is the hardest thing to clean; wipe it with the edge of a sponge. |

## C. Other sources

- **C1. Reliability Update** (yt:DTRs4Ld5Qwg):
  - **Service calls:** 6.7 % → 1.21 % → 0.79 % → about 0.5 %, against an
    industry average they put at about 5 %. Zero remorse returns.
  - **Reset button:** under shipping vibration the display ribbon cable
    pressed it, so stoves wouldn't boot. They deleted the button.
  - **Bad pans (02:39–05:24):** a multi-ply aluminium pan with a thin
    stainless base changes its magnetic properties as it heats. At high
    power that destabilised the control loop, caused overvoltage, and
    killed transistors. They fixed it over the air by moving the overvoltage
    check from 50 Hz to every few microseconds.
  - **Sensor:** thousands were built before launch. At the factory every unit
    gets an end-of-line check: a pan is placed on it and the reading checked.
    Some test escapes still happened.
- **C2. Demo videos** (yt:QHgv1FINRCs, yt:39qXNscf9ts):
  - The burners are raised about ¼".
  - The LED ring fades from yellow to red; orange means residual heat.
  - Knob: lifting it turns the burner off, no knob means no start, and the
    knob has no electronics. The display is not a touchscreen.
  - The sensor "depresses, sealed top and bottom".
  - Tri-ply is recommended (39q 29:01).
  - An egg pan at 315 °F takes about 1 kW to preheat, then 150–200 W to
    hold.
- **C3. "Everything you need to know"** (yt:jgJ89Jr_0a8):
  - Cast iron and carbon steel read less accurately in temperature mode
    (08:10).
  - Don't put 10 kW into a dry pan; stay at 0–2.5 kW (09:47).
  - Hold power: four burners at 482 °F take about 1.73 kW in total.
    Medium is 150–300 W per burner. Preheat is 2 kW for 45–90 s.
  - 10 over-the-air updates by April 2026; certified "Impulse Core" modules.
- **C4. Interviews:**
  - **Latent Space** (yt:obEWFoLfWD4): pots with thermocouples are the
    regression test before each release. Over 200 units were built before
    launch. Lifting the pan pauses cooking; replacing it resumes.
  - **ARK** (yt:9C3G9yAHP3Y): tested to 12–13 kW; the practical limit is
    film boiling at about 15 kW. The sensor took four years, with custom
    ceramics.
- **C5. Install manual and UI guide** (doc):
  - Listed to UL 858. The cabinet needs ≥ 20 mm rear clearance.
  - Electrical: 120 V draws 12.5 A, giving 1.5 kW, on a 20 A breaker.
    240 V draws 8.3 A, giving 2 kW, on a 30 A breaker.
  - With no pan, the burner turns off within 30 s.
  - Power is throttled for unusual heating, for pans that don't respond as
    expected (small, or layered/bonded bases), for low battery, and to
    balance burners.
  - A system pause shows a blue animation. Holding the power control for
    10 s turns the unit fully off.
- **C6. Control Freak:**
  - The two fans are marketed for reliability (yt:Tq1qx3RMBfs).
  - Heat-up speed is user-selectable, 1–3 "flames" (yt:BcSqJ7sZiAQ).
  - Reviewers used a flour-scorch test for the heating pattern; 2 L boils in
    10:55.
- **C7. Commodity induction teardowns:**
  - **Kaizer 8 kW:** a half bridge per coil, GT60J323 IGBTs, D25XB60
    rectifier, 0.68 µF 800 V resonant capacitors, a 4 µF bus, and white foam
    between coil and pan.
  - **IKEA Tilla 2 kW:** a single-switch quasi-resonant stage, 1200 V 20 A
    IGBT, 10 µF bus and 8 µF resonant capacitor.
  - **Duxtop 8100CM:** ETL-listed with an ungrounded 2-prong cord, VIPer12A
    supply, LM339 comparator, 8 µF bus, 2× 0.3 µF 1200 V resonant
    capacitors, an S3F94C4 MCU, and a sprung sensor with thermal paste.

## D. Hold power (model: `hold_power_check.py` → `hold-power-check.json`)

Steady power to hold an empty pan:

| Pan | 177 °C | 250 °C |
|---|---|---|
| Tri-ply | 220–247 W | 342–383 W |
| Carbon steel | 295–331 W | 481–539 W |
| Cast iron | 367–411 W | 567–637 W |

These are consistent with Impulse's figure of 150–430 W per burner. What
limits temper is ramp rate, not hold power.

## E. Not found

- **FCC filings:** lookups returned 403. Induction cooktops come under
  Part 18 with SDoC, so no FCC ID or internal photos are expected.
- **Illegible markings:** the main processor, the coil-board MCU, the
  inverter-charger's switches, and the capacitor voltage digit.
- **Captions blocked (HTTP 429):** 7TZb8I5rVZ8 (Cars & Capitalists),
  G-GHxlLsCy8 (SMEG 10 kW) and ctVXMv_4Glw (Tech Dregs).
