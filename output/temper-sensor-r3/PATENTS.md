# sensor-r3 patent chart

2026-10-14. These are an engineer's reading of primary claim text from Google
Patents HTML, fetched today and stripped of tags. They exist to steer the
design. **This is not legal advice and not a freedom-to-operate (FTO)
opinion.** Every row marked "counsel" needs a US patent attorney before
tooling.

- "Status" is Google Patents' legal-status field as of 2026-10-14.
- Raw texts are not kept in the repo. Re-fetch with
  `curl -sL https://patents.google.com/patent/<number>/en` and strip the tags.

## Candidates

| ID | Architecture |
|---|---|
| **C0** | R16 as built: alumina cap with a skirt, moulded silicone boot gripping the cap sleeve, PEEK plunger with up/down hard stops, S-23CS spring, passive Pt100. |
| **C1 (chosen)** | Lapped Si3N4 disc, Ø8 × 0.32 mm, bonded on a thin-neck polymer post. The post slides and rocks in a short guide and is sealed by a **sliding wiper lip**. No diaphragm and no boot. Coil spring; passive Pt100; rim NTC outside the cap. Contact loss is judged thermally (detector D1). |
| **C2** | C0 plus Pt100 self-heating pulses to measure contact. This is a heater in the sensor. |
| **C3** | Two passive Pt elements stacked in the post, as a heat-flux pair. |

## Claim chart (active and pending)

Each entry shows the patent's elements, then how each candidate maps to them.

**US11378463B2** (Breville, sensor mount assemblies). Active, adjusted expiry
2038-11-14.

- **Claim 1 elements:**
  - a resilient support attached to the chassis, including a mounting with
    a longitudinal axis;
  - the sensor secured in the mounting;
  - a resilient member urging the sensor to a set position;
  - the resilient support **includes a flexible diaphragm having a central
    opening receiving the sensor**;
  - axial movement;
  - **angular movement about two further axes** provided by the support and
    the member.
- **Claim 12 elements:** claim 1 without the angular movement, plus an
  **engaging member on the sensor remote from its end, with the spring between
  it and the chassis**.
- **Claim 13 elements:** no diaphragm, but **the sensor has a slot and the
  engaging member's flange sits in it**, and the engaging member engages the
  chassis so the axis is perpendicular at rest.
- **Mapping:**
  - **C0: close to cl. 1 and 12.** The boot is a flexible diaphragm with a
    central opening that grips the cap sleeve. The plunger shoulder carries
    the spring against the body. Counsel.
  - **C1:**
    - no diaphragm. The wiper is a sliding lip; motion happens by sliding,
      not by flexing a membrane.
    - The spring bears on the post, but cl. 1 and 12 both require the
      diaphragm.
    - No slot-and-flange retention (cl. 13). The post is retained by a
      shoulder and a bonded or threaded collar.
    - Rocking of the post comes from guide geometry, not from a resilient
      support.
    - Counsel to confirm that "flexible diaphragm" does not read on a lip
      seal.
  - **C2:** as C0.
  - **C3:** as C0 or C1, depending on the seal.

**US10278238B2** (Breville, cooktop). Active to 2036-02-13.

- **Claim 1 elements:** a hardware safety module with **≥ 2 circuits**, each
  having a temperature sensor, a comparator and a switch. The **sensors sit
  beneath a sensor cap biased raised above the surface**, and heating runs
  only if at least two of them are below threshold.
- **Mapping:**
  - **C0 and C1:** practised only if two hardware comparators both take
    sensors under the cap.
  - temper's open "runaway fault" decision (R31 CONTROLLER-ARCHITECTURE row
    51) may put one comparator on the Pt100. The rim NTC is in the body rib
    on the glass, **not beneath the cap**, so it must stay there.
  - **Rule:** at most one under-cap sensor feeds hardware.
  - **C3:** a second under-cap element would make two. Avoid.

**US12238844B2** (Breville, continuation). Active to 2035-11-02.

- **Claim 1 elements:** pan detection by a coil on-pulse with a current
  threshold, **plus a position sensor assembly with ≥ 2 position sensors**
  along the depressed assembly's path.
- **Mapping:** none of the candidates has a position sensor. C1's contact
  check is thermal and power-step based (D1). **Never add plunger position
  sensors.**

**US11743976B2** (Breville, continuation). Active to 2037-04-03.

- **Claim 1 elements:** a controller using a set temperature, a cooking-time
  input that sets stage duration, and a measured temperature to adjust power.
- **Mapping:** firmware and UI, not the sensor. Any temper "hold X °C for Y
  min" programme feature needs counsel.

**US10362639B2** (Breville). Active.

- **Claim 1 elements:** food probe vs vessel sensor; the controller switches
  between them on criteria.
- **Mapping:** firmware only, if temper's M12 food probe ever switches
  control source automatically. Counsel.

**US20240288175A1** (Impulse). **Allowed 2026-08-11 per the earlier session;
not issued. Allowed claims unread.** The family is pending: EP4670461A2,
CN120937497A, JP2026508848A, KR20250149710A, MX2025009916A.

- **As-filed claim 1:** a sensor package, a plunger assembly holding it, and
  a support base. This is generic: Control Freak (2016) and Morphy Richards
  GB2552531B (2016) are prior art to it. The examiner cited Haier
  US11976981B2 and Watlow US12135147B2.
- **Dependents and spec features**, with the risk to each candidate (C0 / C1
  / C2 / C3):

  | Feature | C0 | C1 | C2 | C3 |
  |---|---|---|---|---|
  | 3: self-heated flux sensor | none | none | **YES** | none |
  | 4–5: auxiliary sensors between package and plunger | none | none | none | **YES** |
  | 6: compliant bumper | none | none | none | none |
  | 8–9: plunger inner column + outer cap with spring between | partial (boot/cap stack): counsel | none (single post; the spring acts on a shoulder) | as C0 | — |
  | 10–12: protrusions running in side openings | **check the R15 stop design** | none (shoulder and circlip-type stop) | as C0 | — |
  | 13–15: sliding ramp | none | none | none | — |
  | 16: nonferrous thin-sheet cap | none | ceramic disc, not a sheet-metal cap; counsel | none | — |
  | 17–18: diaphragm assembly with collars, O-ring, elastic diaphragm | **C0's boot plus clamp is close** | none | as C0 | — |
  | spec: photosensor for plunger position | none | none | none | none |
  | spec: PID-held sensor heater with flux-direction trigger | none | none | **YES** | none |

**US11976981B2** (Haier). Active to 2042.

- **Claim 1 elements:** a probe recess (counterbore wider than the aperture)
  with a support flange, plus a **drive member that moves the sensor**
  between extended and retracted.
- **Mapping:** spring only, no actuator, in every candidate. Do not
  counterbore the glass to seat the probe.

**US12135147B2** (Watlow). Active.

- **Claim 1 elements:** an integrated heater-sensor for a heater system.
- **Mapping:** relevant to C2 only.

**GB2552531B** (Morphy Richards). Granted, **GB only**, no US family.

- **Claim 1 elements:** an NTC in an aluminium housing, sprung through the
  hob.
- **Mapping:** none. Pt RTD in ceramic, and temper is US-first.

## Prior art and expired art that C1 relies on

- Sprung contact sensors through a cooktop opening: Control Freak (on sale
  2016, Good Design 2016) and Morphy Richards GB2552531B (priority
  2016-07-28). Each predates the Impulse priority (2023-02-23).
- Model-based inversion of a contact sensor's lag (oversampling and a sensor
  model): textbook. Impulse's own spec describes it as background (WO ¶ on
  contacting sensors). sensor-r2 and sensor-r3 use a Kalman filter with a
  fixed contact model.
- Pan detection by coil pulse current: long-standing induction practice. The
  Breville claim needs position sensors in addition.
- Gap conductance at light load: Song and Yovanovich (1987); Yovanovich
  (1982).

## What counsel must do before tooling

1. **Impulse US 18/586,274:** pull the allowed claims from the Patent Center
   image file wrapper (the 2026-05-12 response and the notice of allowance)
   and chart C1 against them. Watch for issue, likely before the end of
   2026.
2. **US11378463B2:** opinion on whether a sliding lip seal around a moving
   post is "a flexible diaphragm having a central opening for receiving the
   sensor". Also check C0 (R16), which is in the field drawings today.
3. **US10278238B2:** confirm the safety architecture (one under-cap sensor in
   hardware, rim NTC outside the cap).
4. **US11743976B2 and US10362639B2:** firmware feature review.
5. **Wider search:** E.G.O., BSH, Whirlpool, LG and Samsung contact-sensor
   families were not searched systematically. Full-text Google Patents
   queries were noisy.
