# sensor-r3 robustness study: contact changes and contaminated contact

Firmware open item 9 (`../firmware/DECISIONS.md`): a mid-cook drop of the
contact conductance h_c made C1 overheat the pan by up to 13.09 K (B2 bar
5 K). This study (a) fixes that in firmware and (b) runs oil, water and crud
under the pan through the Python screen and the C co-sim.

Every number below comes from a script in this folder that writes JSON:

| Script | Writes | What |
|---|---|---|
| `cases.py` | – | The case lists (gated h-step set HS, reported sets, contaminant cases). |
| `pyloop.py`, `shift_kf.py` | – | Python closed loop with the candidates; the Python reference of the window. |
| `hc_candidates.py` | `hc-candidates.json` | Problem A candidates V0–V3L in the Python screen. |
| `vpin_variants.py` | `vpin-variants.json` | Window design alternatives (rate pin, acceptance bias). |
| `contaminants.py` | `contaminants.json` | Oil / water / crud contact values, squeeze film, boiling curve, friction margin. |
| `contaminant_screen.py` | `contaminant-screen.json` | Problem B cases in the Python screen, V0 / V3 / V3Lc / V3L. |
| `hc_cosim.py` | `hc-cosim.json` | HS + reported + contaminant cases through the C firmware, before / after, three gain modes. Gated in `../firmware/run.sh`. |

Constraints held throughout: sensor-r2 non-identifiability (coil power cannot
identify absolute h_c), no heater or self-heating, no second under-cap
sensor, no plunger position sensor (US12238844B2), no actuator (US11976981B2;
`../DECISIONS.md` section 2, `../PATENTS.md`).

## R-A. Problem A: mid-cook h_c drops

### R-A1. Mechanism

The C1 estimator is a KF with a fixed contact model (h_nom 1300 W/m²K). In a
steady state it reads the pan low by the static offset q_leak / G_c, where
q_leak = g_leak (T_cap − T_sink) ≈ 0.1 W at 200 °C. When the true contact
drops mid-cook (pan nudged or tilted, post sticking), the true offset grows,
the model's does not, and the loop heats the pan by the difference: 1000 →
300 W/m²K at 200 °C is about +3.5 K of static error, plus the transient while
the cartridge re-settles. The co-sim measured up to 13.09 K overshoot
(`../firmware/cosim-results.json` before this change).

sensor-r2 showed that coil power cannot identify absolute h_c over a run: the
contact lag and the pan-centre lag commute. A **step** is different. The
cartridge re-settles in 0.2–3.5 s; the pan cannot change its rate in that time
unless the coil power changes. With the pan pinned to its trajectory just
before the step, the only explanation for the reading's fall is a lower G. The
window measures G relative to the model before the step; the absolute h_c stays
unknown (`shift_kf.py` docstring). In the static limit the estimate obeys
1/G_est = 1/G_model + 1/G_new − 1/G_old, so a pan that was already below the
model's 1300 (h0 = 1000) keeps that prior error after the step (accepted
ln(G_est/G_true) +0.12 … +0.5 for h0 1000, −0.02 … −0.28 for h0 above 1300;
`hc-cosim.json` cs_events).

### R-A2. Candidates (Python screen, `hc-candidates.json`, true a)

All share the residual trigger (reading slope over the last 1.5 s minus slope
over the 3 s before < −0.6 K/s, and no 1 s power block in the last 8 s more
than 10 % P_max below the 8 s before). HS = the 64-case gated set (R-A3).

| Variant | What it does on a trigger | HS B1 / B2 / B3 (of 64) | HS worst overshoot | Loss: worst suspect / T_c − SP | Food false latches |
|---|---|---|---|---|---|
| V0 | nothing (the firmware before) | 11 / 36 / 26 | 12.83 K | 2.6 s / 12.04 K | 0 |
| V1 | cap power at the pre-event mean for 30 s | 11 / 33 / 14 | 17.71 K | **32.2 s** / 16.07 K | **1** |
| V2 | request a D1 probe at once ("use D1 more") | 12 / 35 / 24 | 11.93 K | 2.2 s / 5.8 K | 0 |
| V3f | contact-shift window, power frozen during it | 49 / 64 / 48 | 4.95 K | 2.7 s / 6.22 K | 0 |
| **V3 / V3L** | **contact-shift window** (V3L adds the R-B plateau guard) | **49 / 64 / 47** | **4.95 K** | 2.7 s / 6.65 K | 0 |

Design cases: B1 15/16, B2 16/16, B3 16/16 in every variant. Nominal: 0
probes, 0 latches in every variant.

- **V1 rejected.** A power cap holds the wrong (over-heating) model in place
  and only delays it; it also hides real cooling from D1 (loss suspect 32 s,
  breaks B5) and latched a food run.
- **V2 rejected.** A D1 probe answers "contact or no contact". It cannot
  measure a partial contact (`../firmware/DECISIONS.md` D-D1: d/d_exp overlaps
  between intact contact, food and deep drops), so after the probe passes the
  model is still wrong: B2 35/64. It also probes 48 times in 64 runs.
- **V3f rejected.** Freezing power during the window gave no gain over V3
  (B3 48 vs 47, same worst case) and makes the coil ignore the loop for up to
  12 s.
- **V3 chosen.** It is the only candidate that fixes the static error, and the
  only one that passes B2 on all 64.

### R-A3. Window design choices (`vpin-variants.json`)

| Alternative | HS worst overshoot | HS worst \|T̂ − T_c\| | HS B1 | Stress B1 (of 12) |
|---|---|---|---|---|
| **v = reading slope over 5 s before the snapshot, accept ln G − 1 sd (chosen)** | 4.95 K | 4.41 K | 49 | 7 |
| v = the KF's own v | 5.25 K | 5.74 K | 37 | 7 |
| v = end slope of a quadratic fit | 14.44 K | 9.36 K | 41 | 7 |
| v = slope over the last 2 s | 4.95 K | 5.12 K | 41 | 7 |
| accept ln G (no bias) | 4.95 K | 4.52 K | 49 | 7 |
| accept ln G − 0.5 sd | 4.95 K | 4.25 K | 50 | 7 |
| v = 0 when the loop is steady | 4.95 K | 4.41 K | 47 | 8 |

- The quadratic and short-slope pins are noisier than the pan's real
  acceleration and lose B1.
- The 1-sd acceptance bias takes the safe side of the estimate: a contact
  assumed too good reads low and over-heats. It lowers the worst hold error
  from 3.43 to 3.13 K at no cost. It can only lower the accepted contact of a
  DOWN window, and never takes an UP window below where it started.
- v = 0 when steady fixes one stress case and costs two HS B1 cases and up to
  +2 K overshoot elsewhere: rejected.

### R-A4. Bars for h_c steps (gated, `hc_cosim.py`, in `../firmware/run.sh`)

The HS set: 4 pans × h0 ∈ {1000, the pan's design-mid h_c} × h1 ∈ {600, 300}
× t_step ∈ {100 s (first ramp), 250 s (first hold), 365 s (second ramp,
5 s after the setpoint step), 500 s (second hold)} = 64 cases, each in the
three gain modes (true / id_measured / id_estimated), with D1 and the runaway
supervisor in the loop.

| ID | Bar | Why this bar |
|---|---|---|
| R-HS1 | Overshoot of true T_c ≤ 5 K on every case | B2, unchanged |
| R-HS2 | \|T̂ − T_c\| ≤ 5 K from 10 s on, outside the 20 s after the step | B1 is 3 K inside the C1 design h_c spread (floor ~700). A step to 300 or 600 leaves it: the window measures G only relative to the old model (R-A1), so the absolute error of the old model stays. 3 K is reported. |
| R-HS3 | \|hold error\| ≤ 5 K on every case D1 did not latch | B3 (1.5 / 3 K) is reported for the same reason |
| R-HS4 | No runaway-supervisor latch or R1 trip; no D1 latch except the water pot 5811 → 300 at 250 s | That case is a 19× drop that leaves the probe response below D1's threshold. It latches before this change and in the Python screen. Power off, safe side. |
| R-HS5 | C vs Python shadow rms ≤ 0.05 K | Parity, as `cosim.py` |

### R-A5. Result in the C firmware (`hc-cosim.json`, 64 HS cases per mode)

| Gain mode | Version | B1 3 K | B2 5 K | B3 | Worst overshoot | Worst \|T̂ − T_c\| | Worst hold (unlatched) | D1 probes | Windows accepted |
|---|---|---|---|---|---|---|---|---|---|
| true | before | 11 | 36 | 26 | 12.83 K | 10.50 K | 7.42 K | 31 | – |
| true | **after** | **49** | **64** | **47** | **4.95 K** | **4.41 K** | **3.13 K** | 1 | 45 |
| id_measured | before | 11 | 36 | 28 | 13.14 K | 10.65 K | 7.45 K | 32 | – |
| id_measured | **after** | **49** | **64** | **50** | **5.00 K** | **4.49 K** | **3.18 K** | 2 | 44 |
| id_estimated | before | 10 | 39 | 28 | 13.14 K | 10.53 K | 7.47 K | 30 | – |
| id_estimated | **after** | **45** | **64** | **49** | **4.72 K** | **4.52 K** | **3.16 K** | 1 | 43 |

All R-HS bars pass in all three modes. Shadow parity worst 2.2e-4 K rms.

**Margin.** The cases closest to R-HS1 are the water pot stepping to
300 W/m²K (4.72–5.00 K). They are identical before and after: a 1.5 l pot
changes its reading slope by only ~0.2 K/s at the step, below the trigger,
and 300 is 10× under the pot's design h_c. Their overshoot is the pre-existing
static offset at an out-of-design contact. Among the cases a window handles,
the worst is triply clad 1000 → 300 at 365 s in id_measured: 4.89 K (6.92 K
before). The original open-item case (clad 1000 → 300 at 250 s, 13.09 K) is
now 4.21 K.

Reported, not gated (`hc-cosim.json`, after, worst over the three modes):

| Set | Result | Why |
|---|---|---|
| HS_DEEP 1000 → 150 (below the 150 floor) | overshoot up to 24.74 K (24.83 K before), D1 latches 1–2 of 8 | A drop past the floor escalates to a D1 probe, which passes (the post still touches). The real cause of such a drop is a post that no longer follows the pan: R-B4. |
| HS_BACK 1000 → 300 → 1000 (re-seated) | overshoot ≤ 4.78 K (12.95 K before); clad holds −4.17 K cool; the water pot latches D1 in the identified modes (hold −8.86 K) | The UP window returns the model toward nominal only as far as the estimate supports; the 1-sd bias keeps it on the low side, so the pan runs cool (safe side). |
| HS_GRAD warp 1000 → 300 over 60–120 s | overshoot up to 11.98 K, same as before | A gradual change is not an event; the window cannot see it (R-A1). Open item. |

Side effects on the existing gated co-sim (`../firmware/cosim-results.json`,
all bars pass):
- Contact loss: the window opens at once, escalates in ~2 s and keeps T̂ off
  the falling reading, so the PID does not chase it: T_c − SP after loss drops
  from 11.65–12.04 K to 6.72–6.94 K. D1's suspect time moves from 2.5–2.6 s to
  2.7–2.9 s (bar ≤ 3 s: 0.1 s margin in id_measured); the Monte Carlo (20
  seeds × 4 pans, `b5-montecarlo.json`) shows worst suspect 2.7 s, worst
  T_c − SP 6.43 K (was 11.88 K), 0 false latches in 300 runs.
- Food: the window opens and escalates within 0.6–1.1 s; T̂ is pinned high
  for that time (worst error 15.1 K vs 7.5 K before, under-heating side).
  D1 handles the food as before; 0 false latches.
- Stress (constant h outside the design spread, reported): B1 6–7/12 vs 8/12.
  Carbon steel at 3000 opens a window at the end of the second ramp without a
  contact change (the pan decelerates as the loop settles). In true and
  id_estimated it reverts; in id_measured it accepts 585 W/m²K and the hold
  runs 3.66 K cool. A false DOWN acceptance always errs cool (R-A3).

## R-B. Problem B: contaminated contact

### R-B1. Physics and property values (`contaminants.py`, `contaminants.json`)

The contact model is `../contact_model.py` (Yovanovich light-load gap
conductance, the r3 disc and face) with a fluid in the gap, a solid film in
series, a stuck post, or a boiling pocket. Property values, each an
assumption with its source (the bench replaces them):

| Quantity | Value | Source |
|---|---|---|
| Edible oil k | 0.15–0.17 W/m K (0.155 at 150 °C) | Turgut, Tavman & Tavman, Int. J. Food Prop. 12 (2009) 741; Coupland & McClements, JAOCS 74 (1997) 1559 |
| Oil viscosity | 0.060 Pa s at 25 °C, 0.0055 at 150 °C, 0.004 at 180 °C (canola) | Fasina & Colley, Int. J. Food Prop. 11 (2008) 738 |
| Polymerised oil ("varnish") k | 0.15–0.25 W/m K; thickness 0–100 µm swept | Mark (ed.), Physical Properties of Polymers Handbook (2007) ch. 10 |
| Water at 100 °C | k_l 0.680, k_v 0.0248 W/m K, c_p 4217 J/kg K, h_fg 2.257 MJ/kg | Incropera & DeWitt 6th ed., Table A.6 |
| Boiling curve | nucleate q'' = q''_max (ΔT_e/30)³ to 1.26 MW/m² at 30 K, Leidenfrost 1.8e4 W/m² at 120 K; ×0.3 run as a confined-pocket sensitivity | Incropera 6th ed. §10.4, Fig. 10.4, Ex. 10.1 |
| Pocket geometry | 204 mm² of pan over the bore, 0.05–0.35 ml held | `../cad/cartridge_r3.py` |
| Wiper friction / spring | 0.056–0.185 N / 1.21–1.79 N | `../cad/tilt-follow.json` |
| Pan bow when hot | 0–0.3 mm at 230 °C, linear in pan mean T | **assumption, no source found**; bench item |

Contact values (W/m²K, `contaminants.json`):
- **Oil wets the gap: h rises 4.5–5×** (carbon steel 2596 → 13225). A film
  squeezes from 100 to 5 µm in 0.09 s at 150 °C, so a thick wet film does not
  persist under the spring.
- **Varnish lowers h** in series: 60 µm on as-cast cast iron 888 → 655,
  100 µm → 558.
- **Water:** liquid in the gap ×20 (carbon steel 52874), a vapour gap ×0.72.
  Boiling pins the wet pan centre, and the reading, near 100 °C.
- **Crud:** a partly sticking post (1 N friction, 5 mrad tilt) gives 670 on
  as-cast cast iron. A **stuck** post opens a gap as the pan bows: 10 µm
  → 498, 100 µm → 273, 200 µm → 158 (as-cast). The post sticks only if
  friction rises ≥ 6.5× over the dry worst case (0.185 N vs the 1.21 N
  spring).

### R-B2. Plateau guard (firmware, D-LPG)

V0 and V3 run 5 and 4 water cases above the SP + 15 K line (`contaminant-
screen.json`, Python): water trapped in the bore boils under the pan centre and
pins the reading near 100 °C, so the PID holds full power while the annulus
runs away (T_c up to SP + 27 K, pan mean up to SP + 67 K). In the C firmware
before this change the runaway supervisor latched in 5 water cases per mode,
mostly after T_c had already passed SP + 15 K (`hc-cosim.json` before: T_c up
to SP + 29.14 K, 49–51 of 54 SAFE).

The guard: when T̂ sits in 95–118 °C, its 10 s least-squares slope is within
±0.15 K/s and the setpoint is > 5 K above it, the PID is capped at
0.2 K/s / a. Two versions were run:

| Variant (Python, 54 water cases) | SAFE (T_c ≤ SP + 15) | Worst T_c − SP | Worst pan mean − SP | Worst under-temperature hold |
|---|---|---|---|---|
| V0 | 49 | 27.0 K | 66.9 K | −6.63 K |
| V3 (window only) | 50 | 28.64 K | 68.5 K | −6.64 K |
| V3Lc (window + plain cap) | 54 | 6.05 K | 24.0 K | **−105 K** |
| **V3L (window + cap after an energy budget)** | **54** | **6.05 K** | **22.0 K** | **−6.64 K** |

The plain cap is safe but stalls a cook: on triply clad with 350 mg at
100 s, it holds the pan at ~100 °C for the rest of the run, because a pan
held at 100 °C never boils the pocket off. The chosen guard first lets the
PID deliver the energy that would take the whole pan from T̂ to the setpoint
(a·E ≥ SP − T̂, counted from entering the band from below; losses make the
true rise smaller). That heats the pan around the pocket so it boils off, and
keeps the pan mean near the setpoint. Entering the band from above (the
reading fell into it, so the pan was hotter than T̂) gives no budget.

### R-B3. Results per bar

Python screen (`contaminant-screen.json`, V3L, true a) and C co-sim
(`hc-cosim.json`, after, three gain modes; "C worst" is over the three):

| Group | Cases | B1 3 K (Py) | B2 5 K (Py / C) | SAFE (Py / C) | Worst T_c − SP (Py / C) | D1 false latches | Verdict |
|---|---|---|---|---|---|---|---|
| Oil (wet, drip, varnish 30–100 µm) | 28 | 24 | 27 / 27 per mode | 28 / 28 per mode | 5.51 / 5.51 K | 0 | **Pass safety.** Oil raises h: under-temperature side. The one B2 miss is 100 µm varnish on as-cast cast iron (h 558, below the C1 floor, 5.24–5.51 K); 60 µm gives 4.57 K. |
| Water (50–350 mg, at 0 / 100 / 250 s, boil ×1 / ×0.3) | 54 | 30 | 49 / 49 per mode | **54 / 54 per mode** | 6.05 / 6.05 K | 0 | **Pass safety** with the plateau guard (V0: 49 / 49–51). B2 misses are cast iron and clad water arriving mid-hold (5.05–6.05 K). |
| Crud: partial stick | 3 | – | 3 / 3 | 3 / 3 | 4.36 K | 0 | Pass. |
| Crud: stuck post + pan bow 0.1–0.3 mm, ± a nudge | 15 | – | 0 / 0 | **7 / 7** | 36.6 / 42.58 K | 0 | **Safety fails (8 of 15)**: R-B4. |

Gated in `hc_cosim.py` (R-CT1): oil and water SAFE on every case with no D1
latch, in every mode. Supervisor latches are reported (a latch is the safe
state): 0 in oil and water after, 5 per mode before.

### R-B4. Stuck post + pan bow: not fixable in firmware

If crud glues the post in its bore and the pan bows away as it heats, the
contact falls smoothly with pan temperature (h 1431 → 160 W/m²K on carbon
steel by 200 µm). That is a gradual change like HS_GRAD: no event, no
slope change, and coil power cannot identify absolute h_c (sensor-r2). The
estimator reads low and the loop over-heats the pan by up to 36.6 K (Python)
/ 42.58 K (C). The window helps only when the stuck post is nudged abruptly
(carbon steel, clad), not with the slow bow. The D1 probe passes (the post
still touches at the start), and the rim cross-check (D-XCHK, the sibling
rim-NTC work) is the only independent signal; the co-sim's NTC reads the
coil-eye sink, so it was not credited here.

Proposed (not firmware-local, so not implemented):
1. **Mechanical margin is the control.** Stick needs a 6.5× friction rise.
   Keep the wiper lip dry-running and the spring ≥ 1.2 N; the bench crud test
   below sets the real margin.
2. **Rim cross-check sizing.** The sibling rim-NTC agent should run these 15
   cases with its rim model: the stuck + bow cases put the pan mean 5–65 K
   above SP (`hc-cosim.json`), which a rim reading may see.
3. **Cleaning / user instruction**: the bore must be wiped; the "pan must
   touch" message already exists for losses.

## R-C. Open items and bench measurements

1. **Gradual contact loss (HS_GRAD, stuck post + bow)** is not detectable by
   the window or D1. It needs the rim cross-check or the mechanical margin
   (R-B4).
2. **Below the floor (HS_DEEP, 1000 → 150)**: escalates to a probe that passes;
   overshoot unchanged (24.7 K). Same root cause as 1.
3. **Water pot below its design contact**: no window (slope change below the
   trigger); 4.7–5.0 K overshoot unchanged.
4. **Pan mean above SP with a wet pocket**: T_c stays ≤ SP + 6.05 K, but the pan
   mean reaches SP + 22 K (Python) / 22.1 K (C) because the annulus heats while
   the centre boils. The safety line is on T_c (B5); the hob-level pan-mean
   limit is for the safety owner.
5. **Plateau guard and real liquid in the pan**: a deglaze at a setpoint above
   105 °C gets full power for the energy budget (the whole pan to setpoint),
   then 0.2 K/s / a until the liquid boils off. That slows a reduction; the
   bench should time it on a deglaze.
6. **Bench measurements:**
   - hot-pan bow: dial gauge at the base centre, 25 → 230 °C, the four pan
     classes (replaces the 0–0.3 mm assumption);
   - crud friction: caramelised sugar and polymerised oil on the wiper and
     post, pull force after 10 heat cycles (the 6.5× margin);
   - wet-pocket test: 0.05–0.35 ml in the bore, pan placed and heated to 200 °C;
     log Pt100, rim NTC and a pan-centre thermocouple (validates WaterTruth and
     the guard);
   - varnish: contact τ63 against varnish thickness on as-cast cast iron (the
     ~60 µm limit);
   - deliberate nudge / tilt steps on a seated pan at hold: the step sizes and
     settling times the window assumes (0.2–3.5 s);
   - dry τ63 per pan class (the h0 prior error that the window keeps, R-A1).
