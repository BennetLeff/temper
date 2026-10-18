# Findings: mining round 3 (2026-10-15)

This round covers market, regulatory and sensing evidence. Rounds 1 and 2
(`docs/evidence/2026-10-14-impulse-labs-teardown.md`,
`output/temper-coil-driver-r1/`, `output/temper-impulse-mining-r2/`) are not
repeated.

**Tags:**
- **said** / **yt:id mm:ss**: transcripts in `~/temper-media/<id>/captions.txt`.
  The three videos that were rate-limited in round 2 were transcribed locally
  with Whisper (`scripts/video_mining/audio_transcript.sh`).
- **doc**: a manufacturer document.
- **reg**: primary regulatory text (`~/temper-media/regulatory/`).
- **patent**: Google Patents full text.
- **web**: a secondary web source.
- **model**: a script in this folder.
- **inferred**: our reading.

## 1. Power and boil speed

- **Control Freak** (Eater test, yt:BcSqJ7sZiAQ 04:37–04:45): 2 L in a wide,
  uncovered pan boiled in **10:55**. The reviewers expected about 5 min. The
  unit is rated 1800 W at 120 V.
- **Amazon Basics 1800 W portable** (yt:ctVXMv_4Glw):
  - UL listed, about $50.
  - A single quasi-resonant IGBT (H30PR5, 1350 V), 2 × 0.24 µF resonant
    capacitors, a 10 µF bus, and a CHK S011 controller.
- **Temper in the same test** (model, `boil_time.py`, η 0.80–0.90):

  | Input current | Time to boil | vs the Control Freak |
  |---|---|---|
  | 11.09 A (today's hold) | 16:36–17:45 | 1.52–1.63× slower |
  | 12.05 A (current measured) | 14:43–15:23 | slower |
  | 15 A | — | equal |

- **Impulse:** about 40 s to boil 1 L. 10 kW per zone, 15 kW peak (said
  7TZb8I5rVZ8 20:52, 24:49).

## 2. Regulatory (primary text)

- **UL 858 SUN** (2018-03-29, effective 2020-09-01):
  - **47.7:** the vessel must be on the zone.
  - **47.8:** power must go off within 30 s of the vessel being removed, and
    need a manual reset. Temper's `NO_PAN_TIMEOUT_MS` of 3000 complies.
  - **59.6:** an iron bar, 2 × 100 × 20 mm, at the highest setting may rise
    by no more than 35 °C.
  - **72.1.7.1:** abnormal operation.
  - **87.3(h):** the instructions must say "do not place metallic objects".
  - **25.3.1, exception:** requirements don't apply if the appliance complies
    with the solid-state control totally or partially inoperable.
  - **SA (smart-enabled supplement):**
    - controls that respond to communication must meet UL 60730-1;
    - Class B protective functions are evaluated per SB;
    - SA3: a control must not defeat or alter protective functions;
    - there is a ≤ 15 W low-voltage exemption;
    - 87.16 requires a remote-operation warning.
- **UL 1026:** portable induction units are certified under it (Kenyon,
  TÜV). The Control Freak Home carries a "UL household" certification. The
  scope text is paywalled and was not read.
- **NEC 210.23(A)(1):** cord-and-plug equipment is limited to 80 % of the
  branch circuit, so 12 A on a 15 A circuit.
  - NRTLs list portables at 100 %, and the code is effectively unenforceable
    against a listing (ECM).
  - Market practice: the Control Freak is 15 A; Impulse is 12.5 A on a 20 A
    breaker.
- **47 CFR 18.307(a)**, conducted limits for induction:
  - 9–50 kHz: 110 dBµV QP;
  - 50–150 kHz: 90 → 80 dBµV QP;
  - no average limit below 150 kHz.
- **47 CFR 18.305**, radiated limits for induction cooking:
  - below 90 kHz: 1,500 µV/m at 30 m;
  - at or above 90 kHz: 300 µV/m at 30 m.
  - Authorization is SDoC or certification.
- **10 CFR 430.32(j)(1)(iii):** from 2028-01-31, cooking tops other than
  portable indoor ones must meet IAEC ≤ 207 kWh/yr (electric, smooth).
  Under 430.2 induction is included, and "portable indoor" means designed for
  indoor use and to be moved from place to place.

## 3. Sensorless and impedance-based estimation

- **Literature:**
  - KIEE 71(9):1230 (2022): impedance regression on a 2 kW series-resonant
    prototype.
  - Energies 15:1294 (2022): R and L estimated within 7.1 % and 2.9 %.
  - Sensors 14:5278 (2014): IR through glass, ≤ 5 °C error at 60–250 °C for
    a known emissivity.
- **Products:**
  - **Miele TempControl:** 2 temperature sensors plus a reflectivity sensor.
  - **Bosch PerfectFry:** no accuracy published.
  - **Hestan Cue:** a Bluetooth sensor in the pan handle, $299–650. Impulse's
    CEO dismisses the approach (said 26:12–26:32).
- **Patents:**
  - **E.G.O. US10085303B2**, active to 2035-02-07: resonant frequency
    measured with a held bus voltage.
  - **Whirlpool US8530805B2**, active to 2032-01-09: a model tuned via
    R_s = R0(1 + α(T − T0)).
- **Model** (`impedance_sensitivity.py`, an upper bound):
  - carbon steel: 0.09–0.24 %/K, so 4–11 K at 1 % repeatability;
  - cast iron and 430-clad: 0.03–0.09 %/K, so 11–30 K;
  - the reading is weighted over the annulus, not the contact point.
- **Inference:** usable as a plausibility channel only.

## 4. Burst mode vs "continuous control"

- **Impulse:** most induction stoves "click on and off at like one time a
  second … scorch the pan … We're true continuous control" (said 7TZb8I5rVZ8
  75:04–75:27).
- **Control Freak:** owners say it "basically has three output levels" and
  pulses gently (Hungry Onion, 2022).
- **Temper:** bursts at the ~160 W floor with a 20 s default period
  (power-stage F9).
- **Model** (`burst_ripple.py`): ripple is ≤ 0.91 K at the contact point and
  ≤ 2.90 K at the hottest ring, against ≤ 0.33 K with continuous power. That
  is not a scorch problem.

## 5. Market

- **Breville Control Freak:**
  - Price: CMC850 $1,473–1,500; Home BMC800 $1,299–1,499.95.
  - Specs: 25–250 °C, sampled at 20 Hz through the glass, "dual NTC", ±1.8 °F
    claimed, pans 14–26 cm.
  - The Home model has a polymer frame and no IPX3 rating.
  - Its error list includes "Sensor rubber broken / Sensor stuck down".
  - The sensor must be kept oil-free.
  - Owners report a problem with Demeyere Proline pans, and a slow UI.
- **Impulse:**
  - $5,999–6,999; "a couple thousand units" and backlogged as of 2026-10-08.
  - UL took 18+ months, with the firmware certified.
  - Licenses Impulse Core to Zephyr (HyperCore, 300+ showrooms), THOR and
    BS Service (Eximius).
  - Knob: 6 hold-down magnets plus a centre magnet over a 3-axis
    magnetometer; pulling the knob turns the burner off.
  - Sous-vide-style "pan to 140 °F".
- **Copper Charlie:** $5,999, 120 V 15 A, with a 5 kWh battery.
- **Demeyere ControlInduc:** the pan self-limits at 250 °C.
- **SMEG 10 kW** (yt:G-GHxlLsCy8):
  - Field failure: melted wire insulation, causing intermittent operation and
    a costly repair.
  - Build: a half bridge per zone, 0.68 µF 630 V capacitors,
    IXGR40N60 ISOPLUS IGBTs, an MC56F8322 DSC per inverter on CAN, and a CT
    per tank.

## 6. Not found

- The UL 858 and UL 1026 full texts, and their touch-current limits.
- Control Freak failure rates.
- The KIEE paper's error figures.
