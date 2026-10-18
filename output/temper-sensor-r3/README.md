# temper-sensor-r3: a competitive, patent-aware pan sensor

2026-10-14. The bars were set first, in `DECISIONS.md` §1. Every number here
is reproduced by a committed script in this folder:

| Script | Output | Run time |
|---|---|---|
| `contact_model.py` | `contact-model.json` | seconds |
| `screen.py` | `screen-results.json` | about 20 s on 10 cores |
| `hnom_sweep.py` | stdout | — |
| `h_floor.py` | `h-floor.json` | — |
| `cartridge_budget.py` | `cartridge-budget.json` | — |

The thermal plant, filters and frozen controller come from
`../temper-sensor-r2/estimator_study.py`, imported read-only. The patent
reading is in `PATENTS.md`; it is not legal advice.

## Choice: C1, a low-mass passive contact disc

**What it is:**
- a lapped **Si3N4 disc, Ø8 × 0.32 mm**, which is the pan contact;
- the Pt100 chip bonded under it on a 0.10 mm bondline;
- the disc carried on a **thin-neck polymer post** that slides, and rocks
  slightly, in a short guide;
- a **sliding wiper lip** that seals the post, in place of a boot;
- a spring under the post;
- the rim NTC kept outside the cap.

**What firmware adds:**
- a Kalman filter with a **fixed contact model** (h_nom 1300 W/m²K);
- a controller gain-scheduled by the pan's η/C;
- **detector D1**, which checks contact thermally and with a short power step.

**Why it wins.** sensor-r2 showed that the whole problem is the contact lag
C_cap/(h_c·A), and that firmware cannot measure h_c. C1 attacks the
numerator:

- **heat capacity:** 40 mJ/K against R16's 376;
- **contact-lag spread:** across every modelled pan the lag lands in
  0.17–1.1 s, so a single fixed model is right to within about 0.5 s.

It does this with no heater, no position sensor and no diaphragm, which steers
clear of the Impulse dependents and Breville's mount claims (`PATENTS.md`).

## Results against the bars

The "design" cases are the 4 pans × η 0.82/0.92 × each design's own h_c
extremes from `contact_model.py`, 16 cases in all. The setpoints are 200/230
(cast iron, carbon steel), 180/210 (clad) and 90/100 (water). Noise is 0.2 K.

| Bar | C0: R16 as built, fixed model | **C1: chosen** | C2: R16 + self-heating pulses |
|---|---|---|---|
| B1 \|T̂ − T_c\| ≤ 3 K | 5/16 (worst 9.4 K) | **15/16 (worst 3.06 K)** | 0/16 (filter biased, 73 K) |
| B2 overshoot ≤ 5 K | 12/16 (9.2 K) | **16/16 (3.1 K)** | 16/16 (3.8 K) |
| B3 hold error | 12/16 | **16/16** | 6/16 |
| B4 dry t63 (worst / smooth pans) | 9.1 s / 3.8 s ✗ | **1.10 s / ≤ 0.38 s ✓** | 9.1 s ✗ |
| B5 contact loss | not detected; runaway | **suspected 1.7–2.6 s after loss, confirmed 19.8–20.6 s; T_c ≤ SP + 12.0 K** (timing clause ✗, temperature ✓) | not run |
| B5 false alarms | probes fire on nominal clad and water runs | **none in nominal runs; food drops probed but never latched** | — |
| B6 no conductive parts in the eye | ✓ | ✓ (ceramic, polymer, fibre; the open-helix spring as screened in R15) | ✓ |
| B8 T_mean overshoot vs perfect feedback (19.0 K) | 17.8 K | **18.3 K ✓** | 17.0 K |
| P1 patents | **R16 boot is close to US11378463B2 cl. 1/12** (counsel) | **clear of every independent claim found**; counsel items listed | **practises Impulse dependent 3 / spec** |

Notes on the table:

- **C1's one B1 miss** is the hardest smooth contact, enamelled cast iron at
  h_c ≈ 13,000. The fixed model over-leads there by 3.06 K, 0.06 K over the
  bar; the η 0.92 twin reads 2.83 K.
- **The nominal h_c is a trade.** A higher nominal (1722) passes all 16
  design cases but loses margin at the rough end (`hnom_sweep.py`). 1300 is
  the balanced choice.
- **Stress outside the design spread.** At sensor-r2's h_c = 300 floor, C1
  fails B1 on all 4 pans (8.6–10.3 K). At 1000 and 3000 it passes all 8.
- **C1's real floor** (`h_floor.py`) is h_c ≈ 700 W/m²K (τ63 ≈ 1.35 s),
  where 7 of 8 cases pass. At 600 only 1 of 8 passes.
- **The bench therefore has one number to check:** dry τ63 ≤ 1.2 s on every
  pan in the cookware survey. The contact model's worst is as-cast cast iron
  at h_c 888 (τ63 1.1 s), which assumes the post's rocking keeps relative
  tilt ≤ 2 mrad. With R16's rigid stack, tilt goes to 5 mrad, h_c to 653, and
  τ63 to 9.1 s.

## Contact model (`contact_model.py`)

At about 1–2 N on 45–64 mm², P/H is about 1e-5, so contact is gap conductance
through air: h_c ≈ k_air / (Y + M + tilt wedge), where Y ≈ 4.3σ is the
light-load mean-plane separation (Yovanovich). The modelled dry h_c:

| Pan base (assumed Ra) | R16 cap, tilt 0 → 5 mrad | C1 disc, tilt 0 → 2 mrad |
|---|---|---|
| Polished clad (0.2 µm) | 12,081 → 1,864 | 21,946 → 4,816 |
| Brushed disc base (0.6) | 7,896 → 1,663 | 9,535 → 3,542 |
| Carbon steel (1.2) | 4,680 → 1,397 | 5,085 → 2,596 |
| Machined cast iron (1.6) | 3,674 → 1,270 | 3,920 → 2,233 |
| As-cast cast iron (6.0) | 1,044 → 653 | 1,088 → 888 |
| Enamelled cast iron (0.4) | 9,540 → 1,755 | 12,991 → 4,022 |

**Reading:**
- Roughness and tilt dominate. Spring force barely matters, because Y
  depends on the logarithm of the pressure.
- This explains the Impulse engineer's remark (the Control Freak is "good
  only with paste"). It also says why a lapped face plus a mount that follows
  the pan's tilt does most of what paste does.
- **These Ra values and tilts are assumptions.** The bench survey replaces
  them.

## Contact-loss detector D1 (in `screen.py`)

1. **Trigger.** T̂ falls at more than 0.8 K/s over 2 s, held for 1 s, while
   mean power is ≥ 40 %. Power is then capped by the probe immediately; that
   moment is "suspect".
2. **Probe.** Run the coil off, on at 50 %, off: 5 s, 8 s, 5 s.
3. **Fit.** Regress the Pt100 reading on [1, t, t², E_lag], where E_lag is coil
   energy passed through a 3 s lag (the pan-centre diffusion).
4. **Test against a free decay.** Fit the reading to a free decay toward the
   rim-NTC temperature with τ_off = C_cap/G_leak (about 50 s).
5. **Decide.**
   - **Lost:** the energy coefficient is < 25 % of the pan's η/C, *and* the
     free-decay fit is ≤ 0.5 K rms.
   - **On lost:** power goes to 0 and the probe retries every 20 s.
   - **Otherwise:** control resumes, with a 30 s hold-off before the next
     trigger.

**Why it needs C1.** The free-decay signature and a power response within a
few seconds both need a sensor that is fast against the pan. With R16's cap
(τ_off 340 s, lag up to 9 s) the trigger fires falsely on clad and water and
the probe cannot decide.

**Why it is patent-relevant.** It replaces plunger position sensing, which is
Breville US12238844B2 when combined with pulse pan detection, and the Impulse
photosensor in the spec.

**B5 timing clause, as written.** Confirmation at 20 s misses the 15 s clause.
The protective action, a power cap from the probe, starts at about 2 s, and
the true pan stays ≤ SP + 12 K. `DECISIONS.md` §4 records this.

## Rejected candidates

- **C2 (Pt100 self-heating pulses) fails, as implemented.**
  - With R16's 376 mJ/K cap, a 40 mW pulse mainly heats through the 0.027 W/K
    bond, whose conductance is the same order as G_c. During ramps the filter
    then trades contact against pan velocity and drifts low.
  - A 60 mW, 4 s / 12 s retune still leaves 24–29 K errors at low contact.
  - More tuning might rescue it, but it needs a low-C cap to work, and once
    the cap is low-C the passive C1 already passes.
  - It also practises Impulse's "self-heated" dependent claim and spec, and
    pushes the Pt100 well past IST's typical 1 mA measuring current.
  - **Kept only as the documented fallback** if the bench floor is missed.
- **C3 (dual passive elements, heat-flux pair) is rejected analytically.**
  - A second element in the post measures heat leaving the cap downward, not
    the contact conductance. The cap balance still holds G_c as the unknown
    (sensor-r2's commuting-lag argument applies unchanged).
  - It adds a second under-cap sensor, which risks US10278238B2 if it is ever
    wired to a hardware trip.
  - It matches Impulse dependent claims 4–5 (auxiliary sensors between package
    and plunger).
- **Undrilled under-glass sensing** was rejected by study 08; nothing new
  here.
- **IR** was rejected by sensor-r1 and by Impulse; nothing new.

## Pan centre vs annulus

Even perfect contact-point feedback lets the heated annulus run 19 K past
setpoint during the approach (worst T_mean overshoot, all candidates). This is
pan physics at an unheated coil eye. C1 does not add to it (18.3 K vs 19.0 K).
It is now a controller and UX item: ramp limiting (1 K/s), the gain schedule,
and showing "pan centre" rather than "pan".

## Limits

- **h_c rests on modelled roughness and tilt.** The design depends on the
  bench confirming dry τ63 ≤ 1.2 s on every pan.
- **Sink and controller assumptions.** The truth sink is coil-eye air at
  60–75 °C, which is conservative for C1, whose wiper leaks to the glass bore
  that the rim NTC tracks. The controller is given the true η/C.
- **Food drop is a single severe case** (0.5 kg at 5 °C). Oil films, water
  under the pan and sugar crud in the wiper are not modelled.
- **Mechanical and thermal figures are hand calculations**
  (`cartridge_budget.py`): disc safety factor 2.4 at 20 N over the chip
  pocket, and cold leak 0.55 mW/K with the fibre plug. CAD must replace them
  with as-modelled geometry.
