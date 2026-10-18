# temper-sensor-r3 decisions

**sensor-r3** is the sensing line's design round: architecture, patent
position, and the handoff for CAD, PCB and firmware. Numbering follows
`output/temper-sensor-r2/DECISIONS.md` §0.

- **Started:** 2026-10-14.
- **Not legal advice.** Patent notes below are an engineer's reading of
  primary text, to steer design. A US freedom-to-operate (FTO) opinion from
  counsel is required before tooling.

## 0. Inputs carried in

- **sensor-r2 (route 1).**
  - Coil power cannot identify contact conductance h_c, because the pan-centre
    lag and the contact lag commute.
  - A passive sensor with a fixed contact model meets A1/A2 only if the
    contact lag τ63 is ≲ 3 s and known to about ±1.5 s.
  - The R16 alumina cap (376 mJ/K) therefore needs h_c ≳ 2000 W/m²K on every
    pan.
  - The cap's heat capacity is the lever: the lag scales with it.
- **R16 cartridge as built:**
  - alumina cap Ø10, 0.6 mm wall
  - IST Pt100 on EPO-TEK 930-4
  - PEEK plunger and bayonet body
  - moulded silicone boot that grips the cap sleeve
  - S-23CS spring, 0.79–0.96 N, 0.6 mm proud, 1.2 mm stroke
  - glass bore Ø18
  - rim NTC in the body rib (R36), 6-conductor cable
- **Impulse teardown** (`docs/evidence/2026-10-14-impulse-labs-teardown.md`
  §4, §8): Impulse moved to an active, self-heated flux sensor because dry
  contact variability dominated. The Control Freak was "good only with thermal
  paste" (said 19:37–20:28).
- **Control Freak** (`output/temper-reference/control-freak-teardown/`,
  `output/temper-r33-studies/08-undrilled-glass-sensor/sources/`):
  - sprung, booted contact sensor through a bored glass;
  - manual errors "Sensor rubber broken or sensor stuck down";
  - "cookware must touch the sensor";
  - marketing says "multiple sensors" in the tip, sampled 20 times a second;
  - a reviewer measured about ±1 °C (±1.8 °F) holds;
  - range 25–250 °C.

## 1. Competitive targets and acceptance bars (set before screening)

The targets are pegged to the Control Freak, temper's direct 1.8 kW
competitor. They beat it on the things the Impulse engineer said it gets wrong
(contact without paste) and on boot durability. Impulse's ">4 °C/s,
sub-second" is a 10 kW product. temper's coil ramps a pan at 0.3–3.5 °C/s, and
the controller limits the approach to 1 K/s. So "sub-second" matters only
inside that envelope.

| ID | Bar | Basis |
|---|---|---|
| B1 | Estimate tracks the pan contact-point temperature to \|T̂ − T_c\| ≤ 3 K from 10 s on. 4 pans × both η × the design's own h_c spread from the contact model (§3), 0.2 K Pt100 noise. | sensor-r2 A1 |
| B2 | Closed-loop overshoot of true T_c ≤ 5 K, controller frozen as in sensor-r2 §5. | sensor-r2 A2 |
| B3 | Hold error \|T_c − SP\| ≤ 1.5 K at ≤ 100 °C, ≤ 3 K at 200–230 °C (mean over the last 60 s of each hold). | R16 bench T3 |
| B4 | Dry contact t63 ≤ 3 s on the worst pan in the set, ≤ 1.5 s on smooth bases. The Control Freak needs paste; R16 bench T3 allowed 7 s. | competitive |
| B5 | Contact loss with the coil on, plunger stuck or pan lifted off the tip, is detected within 15 s. True T_c then stays ≤ SP + 15 K. | Control Freak "sensor stuck down"; study 08 |
| B6 | No field self-heating: no electrically conductive part inside Ø20 of the coil eye above the coil plane, except the open-helix spring already screened. | R15 G1 |
| B7 | Sample and estimator rate ≥ 10 Hz; raw sampling ≥ 16 Hz. | CF claims 20 Hz |
| B8 | Pan centre vs annulus: the annulus mean temperature T_mean overshoots no more than 2 K beyond what perfect T_c feedback gives. This is reported, not a gate on the sensor alone. | sensor-r2 |
| P1 | **Patent bar.** No candidate may knowingly practise every element of an independent claim of an active US patent found in §2. Features of pending families (Impulse) that match dependent claims or the spec are avoided too, because the allowed claims are unread. | owner goal |

## 2. Patent landscape (primary text, fetched 2026-10-14)

Full chart: `PATENTS.md`. Summary:

| Patent | Status (Google Patents, 2026-10-14) | Gist of independent claims | Design consequence |
|---|---|---|---|
| **US11378463B2** Breville, "Sensor mount assemblies" (prio 2016-08-10) | Active, adjusted expiry 2038-11-14 | Cl. 1 and 12: a resilient support including a **flexible diaphragm having a central opening receiving the sensor**, plus a resilient member urging the sensor along its axis. Cl. 1 adds two-axis angular movement. Cl. 12 adds an engaging member on the sensor with the spring between it and the chassis. Cl. 13: no diaphragm, but the sensor has a slot with a flange of the engaging member in it, which sets the axis perpendicular. | This is the Control Freak mount. **R16's silicone boot gripping the cap sleeve is close to cl. 1/12** and needs counsel. sensor-r3 drops the diaphragm boot and any designed tilt freedom, and uses no slot-and-flange retention. |
| **US10278238B2** Breville, "Cooktop" (prio 2014-11-07) | Active to 2036-02-13 | Two or more hardware safety circuits (sensor, comparator, switch) whose **sensors sit beneath a sensor cap biased above the cooking surface**. Heating is enabled only when at least two read below threshold. | At most one hardware over-temperature comparator may have its sensor under the cap. The rim NTC stays outside the cap, in the body rib against the glass. |
| **US12238844B2** Breville (continuation) | Active to 2035-11-02 | Pan detection by a coil current pulse **plus a position-sensor assembly with ≥ 2 position sensors** along the plunger stroke | No plunger position sensors. Contact is judged thermally (B5). |
| **US11743976B2** Breville (continuation) | Active to 2037-04-03 | Set temperature plus cooking-time stage inputs driving power | Firmware/UI scope, not the sensor. Flagged for FTO. |
| **US10362639B2** Breville | Active (in session folder) | Food probe vs vessel sensor switching on criteria | Firmware scope. Flagged. |
| **US20240288175A1** Impulse (family WO2024178387A2, EP4670461A2, CN, JP, KR, MX) | US allowed 2026-08-11 per the earlier session, **not issued; allowed claims unread** (Patent Center needs a browser session or API key; not obtained). Others pending. | As filed, cl. 1 is a sensor package + plunger assembly + support base, which is generic and has much prior art. Dependents: self-heated flux sensor (3); auxiliary sensors between package and plunger (4–5); compliant bumper (6); plunger inner column and outer cap with the spring between (8–9); protrusions in side openings (10–12); sliding ramp (13–15); nonferrous thin-sheet cap (16); diaphragm assembly with collars, O-ring and elastic diaphragm (17–18). The spec adds a photosensor for plunger position and a PID-held sensor heater. | Avoid every dependent feature and the spec features: no heater or self-heating, no second sensor in the plunger, no compliant bumper, no column/cap spring nest, no pin-in-slot stops, no ramp clamp, no metal-sheet cap, no diaphragm/collar/O-ring assembly, no photosensor. |
| **US11976981B2** Haier (prio 2021-09-10) | Active to 2042 | A **drive member that moves** the sensor between extended and retracted positions, plus a probe recess in the panel | Spring only, no actuator. No counterbored glass seat. |
| **GB2552531B** Morphy Richards | GB only, no US family | NTC in an aluminium housing | Not applicable (US market, Pt RTD, ceramic). |
| **US12135147B2** Watlow | Active | Integrated heater-sensor | Relevant only to heater candidates. |

**Residual risk:** Impulse as-filed claim 1 is generic and would read on any
sprung plunger contact sensor, including the Control Freak (2016) and Morphy
Richards (2016) prior art. Counsel must read the allowed claims (Patent
Center image file wrapper: 2026-05-12 response and the notice of allowance)
before release. This search was not exhaustive: E.G.O., BSH and Whirlpool
families were not searched systematically.

## 3. Decision: C1, a low-mass passive disc with a sliding wiper (2026-10-14)

`README.md` has the screen. Each design choice and its reason:

| Choice | Reason |
|---|---|
| Lapped Si3N4 disc, Ø8 × 0.32 mm, contact Ø7.6 | 40 mJ/K vs R16's 376. Si3N4 is the toughest common thin ceramic (k 85–90), non-conductive (B6), and stocked as 0.32 mm power-module substrate. 0.25 mm bought only 0.3 K in the screen, so the stronger 0.32 mm stays. |
| Pt100 (IST P0K1.202) on a 0.10 mm EPO-TEK 930-4-class bond | G_bond 0.061 W/K, element τ 0.13 s. The bond's *continuous* rating at 250 °C is unpublished (930-4 lists < 325 °C intermittent only). PCB/CAD must get a vendor rating or switch to a bond with one. |
| Thin-neck polymer post (polyimide preferred; PEEK only if its UL RTI holds at the post-top temperature). Neck wall 0.25 mm, ≥ 6 mm to the first cold sink, fibre plug in the cavity. | Cold-side leak 0.55 mW/K, under the 0.8 budget (`cartridge_budget.py`). |
| Post rocks about the face centre in a short guide, giving ≤ 2 mrad relative tilt | Raises worst-case h_c from 710 to 888 (as-cast cast iron). Tilt comes from guide geometry, not a resilient diaphragm (US11378463B2 cl. 1). |
| **Sliding wiper lip** (PTFE/FDA, or FFKM if it runs above 250 °C), no boot | Clears US11378463B2's "flexible diaphragm having a central opening receiving the sensor" (counsel to confirm). Removes the Control Freak's "sensor rubber broken" failure. |
| Spring under the post, 1.2–1.8 N | Force barely moves h_c. Keeps small pans from rocking. |
| No position sensor, no heater, no second under-cap sensor | US12238844B2, Impulse dependents 3–5 and spec, US10278238B2 |
| Firmware: KF with fixed h_nom 1300 W/m²K, sink taken from the rim NTC | `hnom_sweep.py` |
| Firmware: detector D1 (thermal plus power-step contact check) | B5 |
| Controller: sensor-r2's frozen gain-scheduled PID, with η/C identified online | sensor-r2 §5. Online η/C is new firmware scope; the screen used the true value. |

**C0 (R16 as built) is retired** on B1, B4 and B5, and on P1 risk. The R16
CAD and quote package stay frozen in their rounds.

**C2 and C3 are rejected** (README §Rejected). C2 is the fallback only if the
bench survey misses the floor, and only after counsel reads the Impulse
allowed claims.

## 4. Deviation recorded: B5 timing clause

C1's D1 confirms loss 19.8–20.6 s after it happens, against the 15 s clause.
Protection starts at 1.7–2.6 s (the probe caps power), and the true pan stays
≤ SP + 12.0 K, which meets the temperature clause.

**Decision.** Accept for sensor-r3 and keep B5 unchanged as a firmware target.
The firmware agent may shorten the probe (for example a 3/6/3 s probe with
the lagged-energy regressor) if the in-the-box tests still show no false
latch on food drops. The bar is not loosened.

## 5. Bench acceptance carried forward

**Dry τ63 ≤ 1.2 s on every pan** in a cookware survey of at least 12 pans
across the six classes in `contact_model.py`. Method: a pan preheated
off-hob, set on a cold sensor, coil off.

**If any pan exceeds 1.35 s** (`h_floor.py`: the floor is h_c ≈ 700), stop.
The next steps are, in order:

1. contact face finish and tilt compliance;
2. C_cap (0.25 mm disc);
3. C2-class active contact measurement, after FTO.
