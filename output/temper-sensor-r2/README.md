# temper-sensor-r2: can firmware fix the passive pan sensor? (route 1)

2026-10-14. All numbers come from `estimator_study.py` → `results.json`, which
reruns in about 30 s on 10 cores. `plot_traces.py` draws `traces.png`.
`controller_sweep.py` reproduces the controller freeze. The
bar and the fixed inputs are in `DECISIONS.md` §1–3. They were written before
any run.

## Answer

**No, not as specified.** An estimator can't learn the pan contact (h_c) online
from coil power and the Pt100 reading. As a result, a passive cartridge meets
the bar only when the contact is both **good** and **known in advance**.

- **What the estimator would need to know is not observable.** The power →
  reading path has two lags in series:
  - the pan's own centre lag: the coil eye is unheated, so heat diffuses inward;
  - the cartridge's contact lag, C_cap/G_c.

  Series lags commute. In `commuting_lags_check`, swapping a 4 s and a 15 s
  lag changes the reading by 3×10⁻¹³ K and moves the contact-point
  temperature by 19.7 K. No filter can split the two, however well it is
  tuned. The route-1 EKF shows this directly: it puts the pan's lag into the
  contact, h_c falls to its clamp, and the estimate runs up to 242 K wrong.
- **The useful part of route 1 is a fixed contact model, and it works only if
  h_c is high and its spread is narrow.** The filter is given h_c × factor
  (worst over 4 pans, η 0.82, 0.2 K noise):

  | true h_c (W/m²K) | τ63 (s) | factors that pass A1 and A2 |
  |---|---|---|
  | 300 | 18.9 | none, not even ×1 (4.0 K / 4.9 K) |
  | 500 | 11.7 | none, not even ×1 (3.3 K) |
  | 1000 | 6.1 | ×1 and ×1.25 only |
  | 2000 | 3.2 | ×0.67 to ×2 |
  | 3000 | 2.3 | ×0.67 to ×2 |

  With the R16 alumina cap, this needs **every pan in use to give h_c ≳ 2000
  W/m²K (τ63 ≲ 3 s)**. A single assumed h_c of about 3000 then covers the
  measured spread. Below about 1000, the passive sensor fails even when h_c is
  known exactly: inverting a 12–19 s lag amplifies 0.2 K of noise past 3 K.

## Results matrix (A1/A2 gated at 0.2 K noise; 28 cases per feedback variant)

| feedback | A1 pass | A2 pass | worst \|T̂ − T_c\| | worst overshoot |
|---|---|---|---|---|
| perfect (true T_c) | n/a | 28 | 0 | 2.1 K |
| raw Pt100 | 2 | 10 | 38.3 K | 33.7 K |
| KF, nominal h_c 1000, no power | 8 | 15 | 20.7 K | 22.5 K |
| KF told the true h_c (oracle) | 22 | 25 | 4.5 K | 6.1 K |
| **route 1: EKF with power, h_c and η/C online** | **0** | 21 | 241.8 K | 34.7 K |

The 28 cases are:

- 4 pans: cast iron 26, 2 mm carbon steel 28, tri-ply clad 24, and a disc-base
  pot with 1.5 L of water;
- h_c 300 / 1000 / 3000, crossed with η 0.82 / 0.92;
- 4 mid-run contact steps (1000→300 and 300→3000).

Of the 7 oracle failures, 4 are at h_c 300: the worst error is 4.5 K and the
worst overshoot 6.1 K. The other 3 are within 0.5 K of the bar: the water pot
at h_c 1000, and two step cases.

## What else the run shows

- **Raw reading biases low under poor contact, not just lags.** At h_c 300
  the boot leak is 5.5 % of G_c. On clad (180/210 °C) the raw loop holds the
  pan 7–8 K hot, which is about that bias. On cast iron (200/230 °C) it
  averages 19 K hot: the Pt100 reads 12.5 K low, and the loop swings 8–25 K
  above setpoint. R15's "−0.7 K" was for h_c 1000 at 100 °C.
- **Overcompensating is unstable.** When the true contact is better than
  assumed (nominal 1000, true 3000), the KF over-leads and the loop goes into
  a ±7 K limit cycle (`traces.png`, bottom right).
- **The pan's centre is not the pan.** Even with perfect contact-point
  feedback, the heated annulus runs up to 29 K away from the centre during
  ramps (carbon steel; cast iron 23 K). A Pt100 at the coil eye can't see
  this, and neither can an active sensor at the coil eye (Impulse's).
- **The controller must be gain-scheduled by pan.** Feedback on the true
  centre temperature with one fixed PI(D) can't satisfy every pan: the plant
  gain η/C varies 14× (water pot to carbon steel). In exploratory fixed-gain sweeps
  (whose code was not kept), no single gain set both held every pan within 2 K
  and kept overshoot under 5 K. A rate-domain PID scheduled by η/C, with a 1 K/s setpoint ramp
  (`controller_sweep.py`), passes every pan at ≤ 2.1 K. Coil power *does* earn its keep here: it identifies
  η/C for the controller, even though it can't identify h_c.

## Limits of this study

- **The h_c values are assumptions.** 300–3000 is the R15 range, unmeasured.
  The pass/fail line above is in h_c, so the cookware survey on the bench
  decides which side temper is on.
- **The controller is given the true η/C.** Identifying η/C online from power
  (for example from the first seconds of heat-up) is plausible but untested
  here.
- **Simplified pan physics:**
  - pans start cold at equilibrium; a hot pan placed on the hob is untested;
  - radial 1-D base with the wall lumped on the rim;
  - water is the only load; boil-off and oil are not modelled;
  - h_c is constant except for the step cases.
- **Sink and NTC are assumed:** the sink rises 35–50 K over τ 300 s, and the
  rim NTC reads +3 K high.
- **The EKF tuning was not exhaustive.** The commuting-lag identity bounds
  every route-1 filter anyway: its contact-point accuracy is only as good as
  its prior on h_c, and the band table is that prior swept.

## What would change the answer

1. **Measure h_c on the bench before anything else.** This is the R16 sensor
   tests S1–S7, extended to a cookware survey. Fit τ63 per pan from a step
   (the pan heated off-hob, then set down). If every pan gives τ63 ≲ 3 s,
   route 1 with one fixed contact model is enough.
2. **Cheap levers on the cartridge side:**
   - Cut C_cap. The lag scales with it, so a thinner or smaller ceramic roof
     moves the whole table down.
   - Raise and narrow h_c: contact force, a cap face that self-aligns, and
     surface finish.

   R15 already chose 0.6 mm alumina for strength. Any change goes back through
   that screen.
3. **If the survey shows h_c below the line, temper needs an in-situ contact
   measurement.** That means injecting heat at the cartridge, for example by
   pulsing the Pt100's own current to self-heat it. That approach overlaps
   Impulse's US20240288175A1, which is allowed but whose allowed claims are
   unread. Read those claims first (teardown note §8).
