<!-- provenance: commit=eb5022510d8f1272adf0a27d76c849aa2bb6e210 dirty=false
     (origin/main; branch analysis/input-stage-power-ceiling, cut from it).
     pcb/temper.kicad_pcb sha256=26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b
     -- verified before and after this analysis; the board file was never
     opened for writing.  NO clearance, creepage, copper-weight, loop-area,
     ampacity or DRU threshold was changed.  No elec/*.ato file was edited.
     power_pcb_dataset/drc_ceiling.json untouched.  No _*_py_oracle.py touched,
     deleted or re-pinned.  No test skipped, xfailed, relaxed or allowlisted.
     git stash never invoked.  No pushed history rewritten.  Two files are
     added: this document and its companion script, and nothing else. -->
---
module: power
tags: [power-input, doubler, power-factor, ripple, bus-capacitor, branch-circuit, analysis-only]
problem_type: engineering-analysis
---

# The input stage tops out at **146 W** output (bracket 133–158 W), bound by the four bus capacitors' ripple-current rating. 1800 W is not reachable by any component change, because 1800 W **is** the entire volt-ampere capacity of a 15 A / 120 V branch circuit.

**Answer, as a number with a binding constraint named:**

> **Maximum continuous output power: 146 W** (bracket **133–158 W** across every
> input bracket checked).
> **Binding constraint: `C_BUS1 / C_BUS1B / C_BUS2 / C_BUS2B` ripple current**
> — 2.70 A rms rated (Chemi-Con KMQ, 105 °C / 120 Hz), and at that power the
> dominant term is not the rectifier at all but the **47 kHz tank current**,
> which the bank carries because the only HF bypass on the DC bus is a 0.47 µF
> film capacitor presenting 7.2 Ω at 47 kHz.

**And the answer the brief flagged as most consequential is also true, one level
up:** once the capacitor problem is set aside entirely, **the binding constraint
on reaching 1800 W is the 15 A branch circuit itself, and no component change
fixes it.** A 15 A / 120 V branch is 1800 VA. The declared output is 1800 W.
`P_out = V · I · PF · η`, so 1800 W out of that branch requires **PF × η =
1.000** — unity power factor *and* 100 % efficiency, simultaneously. At the
repo's own efficiency bracket the hard ceiling is **1530 W (η = 0.85) to 1656 W
(η = 0.92) even at perfect power factor.** The declared 1800 W was never
achievable on this branch circuit, independent of topology, PFC, or parts.

`main.ato:495` already says this out loud — `assert p_output_max within 1500W to
1800W  # 15A circuit limit` — and then sets `p_output_max = 1800W`, i.e. exactly
at the physically unreachable end of its own assertion.

Reproduce with (pure stdlib, reads no repo state, `make venv-isolate` **not**
required — stated explicitly per the task's environment rule):

```
python3 docs/evidence/2026-08-19-input-stage-power-ceiling.py
```

---

## 0. The ceiling ladder

Each row is the output power at which that one rating is first reached. The
minimum is the answer; the rows above it are what you would hit next if the row
below were fixed. Bracket = across `stiffest-line` / `central` / `softest-line`
(defined in §2).

| # | Rating | Limit | **P_out ceiling** | Provenance |
|---|---|---|---|---|
| **1** | **`C_BUS×4` ripple, LF + HF in quadrature** | **2.70 A rms** | **133 – 158 W (central 146 W)** | `[datasheet]` |
| 2 | └ of which: HF (47 kHz tank) term alone | 2.70 A rms | 147 – 188 W | `[datasheet]` + `[repo]` |
| 3 | └ of which: LF (60 Hz recharge) term alone | 2.70 A rms | 441 – 491 W | `[datasheet]` + `[derived]` |
| 4 | D1/D2 MUR1560 **I_FRM** repetitive peak | 30 A | 392 – 702 W | `[datasheet]` |
| 5 | Branch circuit, 80 % continuous-load rule | 12 A rms | 649 – 747 W | `[uncited-standard]` |
| 6 | Branch circuit, **repo's declared `i_max`** | 15 A rms | **844 – 955 W** | `[repo]` |
| 6 | NTC RT1 SL32 10015 (*only if K1 fails open*) | 15 A rms | 844 – 955 W | `[datasheet]` |
| 7 | F1 fuse / L1 choke / K1 IEC contact | 16 A rms | 911 – 1028 W | `[datasheet]`/`[repo]` |
| 8 | K1 contact, UL508 rating | 20 A rms | 1183 – 1319 W | `[repo]` |
| 9 | D1/D2 MUR1560 I_F(AV) @ T_C = 145 °C | 15 A | 2975 W – no limit < 3 kW | `[datasheet]` |

Nothing in the ladder reaches 1800 W. **The highest ceiling any single component
in the input stage grants is 1319 W** (K1's UL508 contact rating), and that is
above the branch circuit's own 955 W, so it is unreachable anyway.

**Row 4 is new.** No document in this repository has checked the rectifier
diodes against their *repetitive peak* rating. Fairchild's MUR1540/MUR1560
Rev. B prints **I_FRM = 30 A** in the Absolute Maximum Ratings block; the
simulated recharge pulse peaks at **60–83 A** at 1800 W, i.e. **2.0–2.8× the
absolute-maximum repetitive peak.** The 15 A I_F(AV) rating that
`components.ato:291` records is not the one that binds — average current is only
6.4–7.8 A. (I_FRM's printed condition is a 20 kHz square wave, not a 60 Hz,
~2 ms recharge pulse. A longer pulse at the same peak is thermally *worse*, so
30 A is a conservative ceiling for this waveform, not an optimistic one.)

---

## 1. Power factor and rms line current, as designed

`PowerInput` (`elec/src/modules.ato:633–1025`) is a **Delon (half-wave cascade)
voltage doubler**: `ac_l → F1 → L1.W1 → {RT1 ∥ K1} → node A`, `D1` from node A
to `hv_plus` charging `C_BUS1 ∥ C_BUS1B` (3600 µF) on the positive half-cycle,
`D2` from `hv_minus` to node A charging `C_BUS2 ∥ C_BUS2B` on the negative,
`ac_n → L1.W2 → gnd_ref` as the midpoint. **Each half-bus bank recharges once
per 60 Hz cycle, not twice** — as the committed 2026-07-26 ripple doc §2 already
established, and which I confirm.

The companion script runs this as a **time-domain simulation**, not a
closed-form approximation. Results at the declared 1800 W:

| case | R_series | P_in | **θ** | **I_line rms** | I_line pk | crest | **PF** | V_bus avg | V_bus p-p |
|---|---|---|---|---|---|---|---|---|---|
| stiffest-line (η 0.92) | 76 mΩ | 1957 W | 43.3° | **28.81 A** | 83.2 A | 2.89 | **0.595** | 308.4 V | 22.7 V |
| central (η 0.90) | 265 mΩ | 2000 W | 58.0° | **26.61 A** | 65.0 A | 2.44 | **0.697** | 292.4 V | 22.2 V |
| softest-line (η 0.85) | 455 mΩ | 2118 W | 70.6° | **27.32 A** | 60.3 A | 2.21 | **0.763** | 273.3 V | 22.9 V |

**The task's physical reading is confirmed.** PF is 0.60–0.76 — inside the
0.5–0.6 band the brief predicted for a capacitor-input rectifier, slightly better
because the doubler's two pulses per cycle are wider than a bridge's. The rms
line current is **1.6–1.8× the real-power-equivalent current**, and 26.6–28.8 A
against a 15 A declared limit. **The topology cannot deliver 1800 W from a 15 A
branch circuit, and this is a design finding, not a component-selection one.**

### 1.1 The conduction angle is not a free parameter — this closes the prior derivation's largest estimated input

The 2026-07-26 ripple doc carries θ as assumption **A5**, "40° central (30–60°
bounds) … typical range for cap-input rectifiers … not bench-verified," and
`43d056e15` §7 names it "the largest single estimated input in this document."

**θ is not an input. It is an output of charge balance.** For a bank drooping
`ΔV = I_dc · T / C` between recharges, conduction restarts when the rising line
catches the sagged capacitor: `cos θ_start = (V_pk − ΔV)/V_pk`, then widened by
the series resistance. With `C = 3600 µF` per half and the real loop resistance,
the simulation *produces*:

| R_series | θ | I_line rms | PF | I_line pk |
|---|---|---|---|---|
| 30 mΩ | 39.9° | 30.74 A | 0.562 | 94.7 A |
| 80 mΩ | 44.3° | 29.19 A | 0.602 | 83.2 A |
| 200 mΩ | 53.6° | 27.19 A | 0.670 | 69.2 A |
| 450 mΩ | 68.5° | 25.82 A | 0.754 | 57.8 A |
| 600 mΩ | 75.9° | 25.69 A | 0.789 | 54.6 A |

**Sensitivity is the good news here.** Across a 20× sweep of series resistance —
far wider than any real installation spread — rms line current moves only
30.74 → 25.69 A, a 16 % band, because the two effects fight: more resistance
widens the pulse (lowers rms) but sags the bus (raises the DC current needed for
the same power). **Every point in that sweep is 1.7–2.0× the 15 A limit.** The
verdict does not depend on θ, which is why it survives θ having been an estimate.

The A5 band 30–60° was **not wrong** — the simulated 43–71° overlaps it — but the
low end of it is unreachable at this capacitance and the high end is exceeded on
a soft branch.

### 1.2 Where I disagree with `43d056e15`

That document reports **19.93–30.51 A**. I get **26.6–28.8 A** — the same order,
but its *best case* is roughly 25 % too low, and I can name both reasons:

1. **It evaluates `I_dc,half = (P_in/2) / 170 V`.** The half-bus does not sit at
   170 V under load; it averages **146 V** (central case), because 3600 µF
   drooping at 6.8 A for a full 16.7 ms line period loses ~27 V, and the diode
   drop and series resistance take more. Using 170 V understates `I_dc` by 16 %,
   and every current downstream with it.
2. **The rectangular-pulse identity `I_rms = I_dc·√(2/δ)` understates by ~10 %**
   at the *same* θ. Cross-checked directly in the script §1: sim/rect ratio is
   0.899–0.906 across all three cases. A real recharge pulse is peakier than a
   rectangle of equal area and duration.

Both errors run in the same direction — the prior document is **optimistic**, not
conservative. Its qualitative conclusion is unaffected and I endorse it.

**Inputs I took unchanged from the prior committed work** (not re-derived):
Schurter FST 16 A fuse resistance 3.75–5.73 mΩ `[datasheet]`; TDK CMC DCR
2 × 7.1 mΩ `[datasheet]`; K1 contact resistance 5–20 mΩ `[estimated]` — TE
publishes no contact-resistance line, as the prior agent found and I did not
re-check; efficiency bracket 0.85/0.90/0.92 `[repo]`; tank rms 35.4–40 A at
1800 W `[repo]`, from `2026-07-26-ocp01-vs-full-power-current.md`; the KMQ
frequency-multiplier table and 2.70 A rating `[datasheet]`, from the committed
ripple doc; per-cap HF share 0.3536 `[repo]`, assumption A6.

---

## 2. The binding constraint

Three bracket cases span every uncertain input simultaneously:

- **`stiffest-line`** — lowest series R (short branch, low-resistance contact),
  η = 0.92, tank 35.4 A. Narrowest pulse ⇒ **highest rms and peak currents.**
- **`central`** — midpoint of every bracket, η = 0.90.
- **`softest-line`** — highest series R, η = 0.85, tank 40 A. Widest pulse ⇒
  lowest rms, but lowest bus voltage.

The full per-case ladder is §0 and the script's §2. **The minimum is
`C_BUS×4` ripple current at 133–158 W, central 146 W.** That is the answer.

### 2.1 The capacitor ceiling is dominated by the *tank*, not the rectifier

| case | P_out | LF/cap | HF/cap | total | × rated | dominant |
|---|---|---|---|---|---|---|
| central | 1800 W | 8.84 A | 8.90 A | 12.54 A | **4.64×** | tied |
| central | 900 W | 4.65 A | 6.29 A | 7.82 A | 2.90× | HF (tank) |
| central | 400 W | 2.25 A | 4.19 A | 4.76 A | 1.76× | HF (tank) |
| central | 150 W | 0.95 A | 2.57 A | 2.74 A | 1.01× | HF (tank) |

(All figures are per capacitor, at 120 Hz-equivalent, with each spectral
component divided by the datasheet's own frequency multiplier at its own
frequency — a per-harmonic DFT rather than the single-multiplier approximation.)

**Independent confirmation of the committed FAILS verdict.** My time-domain
simulation gives **4.64–4.87× rated** at 1800 W. The committed
`2026-07-26-bus-capacitor-ripple.md` gives **4.2–5.8×, central 4.8×**, by an
entirely different method (closed-form rectangular pulse + externally-bounded
tank term). **Agreement to within 4 % on the central case.** That finding is
correct and I reproduce it independently.

The reason the ceiling lands so low is the **P^0.75 / P^0.5 scaling**: LF ripple
falls only as `P^0.75` (the pulse narrows as the load drops, raising crest
factor) and HF only as `P^0.5` (series-resonant into a fixed reflected pan
resistance, `P = I_tank² · R_eq`). **Throttling power is a very inefficient way
to buy ripple margin** — an 12× power reduction buys only a 4.6× ripple
reduction. Reported both ways in the script; under the alternative `I_tank ∝ P`
scaling the ceiling rises to 344–358 W, still nowhere near 1800 W.

### 2.2 The 0.47 µF film bypass does not relieve the electrolytics

`HalfBridge` instantiates `c_dc_hf`, a 0.47 µF / 630 V PP film cap
(`modules.ato:347–355`), as the DC bus HF bypass. Two independent reasons it
carries essentially none of the 47 kHz current:

1. **Impedance.** |Z| = 7.20 Ω at 47 kHz, against the electrolytic bank's
   0.11 Ω per unit at 120 Hz (from the datasheet tan δ) falling further with
   frequency. Two orders of magnitude the wrong way.
2. **Topology.** It sits `hv_plus → hv_minus`. The switching loop is
   `hv_plus → Q_high → tank → power_return (the doubler midpoint)`. The film cap
   does not span that loop; it can only reach the midpoint *through* `C_BUS2`.

So the ripple doc's assumption A6 — that each half-bus electrolytic bank carries
its own half of the tank current — **stands**, and the HF term is real.

---

## 3. Headroom to 1800 W, and what PFC does

**The headroom factor is 12.3× at the capacitor ceiling** (1800 / 146) and
**1.9–2.1× at the branch-circuit ceiling** (1800 / 844–955).

### 3.1 PFC quantified

At PF = 0.95+ the line current is a sinusoid, `I = P_in / (V_line · PF)`:

| η | PF | P_in | **I_line rms** | verdict |
|---|---|---|---|---|
| 0.92 | 1.00 | 1957 W | **16.30 A** | still exceeds 12 A, 15 A, 16 A |
| 0.92 | 0.95 | 1957 W | **17.16 A** | still exceeds 12 A, 15 A, 16 A |
| 0.90 | 0.95 | 2000 W | **17.54 A** | still exceeds 12 A, 15 A, 16 A |
| 0.85 | 0.95 | 2118 W | **18.58 A** | still exceeds 12 A, 15 A, 16 A |

**PFC does not close the gap, and this is the central finding of §3.** Not one
row clears the declared 15 A limit, the 16 A fuse, the 16 A choke, or K1's 16 A
IEC contact. **Only K1's 20 A UL508 rating clears** — and a relay is not a
branch circuit. Even at a physically impossible **PF = 1.00 and η = 0.92**, the
draw is 16.30 A.

**Which components still do not clear at PF ≈ 0.95, named as the brief asks:**
the branch circuit (15 A), F1 (16 A), L1 (16 A), and K1 on its IEC rating
(16 A). K1 on its UL508 rating (20 A) clears. RT1 is bypassed and does not
apply.

What PFC *does* buy, if 1800 W were dropped as a target:

| rating | ceiling at PF = 0.95 |
|---|---|
| 80 % continuous rule, 12 A | 1163 – 1259 W |
| declared 15 A | 1454 – 1573 W |
| fuse / choke / K1-IEC 16 A | 1550 – 1678 W |
| K1 UL508 20 A | 1938 – 2098 W |

### 3.2 What branch circuit 1800 W actually needs

| branch | VA | 80 % continuous VA | P_out at PF 0.95 | continuous-rule P_out |
|---|---|---|---|---|
| **15 A / 120 V** | 1800 | 1440 | 1454 – 1573 W | 1163 – 1259 W |
| 20 A / 120 V | 2400 | 1920 | 1938 – 2098 W | 1550 – 1678 W |
| 30 A / 120 V | 3600 | 2880 | 2907 – 3146 W | 2326 – 2517 W |

**1800 W is a 20 A-branch product at minimum**, and even a 20 A branch is
marginal once the continuous-load rule is applied (1550–1678 W). **This is a
branch-circuit-class decision, not a component-selection one, and it is the
owner's to make.**

### 3.3 PFC does *not* fix the capacitors

A boost PFC removes the 60 Hz recharge pulse but replaces it with the
unavoidable 120 Hz second-harmonic bus current of any single-phase PFC
(`I_120 = P_in / 2 V_bus`), and **does not touch the 47 kHz tank term at all**:

| case | V_bus | 120 Hz term | HF term | total | × rated |
|---|---|---|---|---|---|
| central | 340 V | 1.47 A/cap | 8.90 A/cap | 9.02 A | **3.34×** |
| central | 400 V | 1.25 A/cap | 8.90 A/cap | 8.99 A | **3.33×** |
| softest-line | 400 V | 1.32 A/cap | 9.44 A/cap | 9.53 A | **3.53×** |

**With a perfect PFC in front, these four capacitors still run at 3.1–3.5×
their rated ripple current at 1800 W.**

---

## 4. Is the bus-capacitor overage the topology, or an independent selection error?

**It is two problems, not one, and they need different fixes.** This is the
sharpest result in the analysis.

The test: hold the topology fixed, sweep only the capacitance, and **re-solve
the load at each point so every row delivers the same 1800 W** (an
apples-to-apples comparison the earlier constant-resistance framing does not
give).

| C/half | θ | I_line | PF | V_half | V p-p | **LF/cap** | **HF/cap** | × rated |
|---|---|---|---|---|---|---|---|---|
| 100 µF | 166.0° | 18.04 A | **0.977** | 52.4 V | 160 V | **1.57 A** | 8.91 A | 3.35× |
| 330 µF | 140.8° | 21.11 A | 0.846 | 59.2 V | 160 V | **4.80 A** | 8.89 A | 3.74× |
| 1000 µF | 87.2° | 27.13 A | 0.686 | 108.0 V | 105 V | **8.96 A** | 8.90 A | 4.68× |
| **3600 µF (as built)** | 58.3° | 26.60 A | 0.699 | 145.3 V | 27 V | **8.84 A** | 8.91 A | 4.65× |
| 5000 µF | 56.9° | 26.40 A | 0.699 | 147.3 V | 19 V | 8.76 A | 8.88 A | 4.62× |

**Problem A — the LF term is the capacitance choice.** LF/cap falls 5.6× (8.84 →
1.57 A) as capacitance drops from 3600 µF to 100 µF per half, and power factor
rises 0.699 → 0.977. This is exactly the mechanism the committed
`2026-07-26-bus-capacitor-architecture-review.md` §4 argued from the Hsieh 2023
IET precedent ("a low value of filter capacitor is chosen to get a high power
factor"), and **the simulation confirms it quantitatively: at 100 µF/half the LF
term alone clears its 2.70 A rating.** So this part *is* self-inflicted by the
capacitance choice, and it is fixable by capacitance alone.

**Problem B — the HF term is an independent selection error.** HF/cap is
**flat at ~8.9 A** across a 50× capacitance sweep at constant delivered power.
No capacitance value changes it. §3.3 shows no PFC changes it. It is the 47 kHz
tank current landing on 105 °C snap-in electrolytics because the only HF bypass
is 0.47 µF (§2.2). **This is a separate defect from the one the committed ripple
doc found, it is not a consequence of the doubler topology, and neither of the
two remedies the ripple doc's §8 names as out-of-scope ("more parallel
capacitors, a higher-ripple-rated part, or active PFC") addresses it except by
brute force.**

**And note what problem A's fix costs, which nobody has priced:** at 100 µF/half
the half-bus averages **52 V with 160 V peak-to-peak ripple**. That is a
different converter. It also *still* draws **18.04 A** at 1800 W — above the
15 A limit, because §3's arithmetic is inescapable. Whether the tank, the ZVS
margin and the PLL floor survive a bus that swings 50–170 V every cycle is
exactly the question `BUS_CAPACITANCE_DERIVATION.md` §7 already named as its own
blocking measurement, and it is **not** answered here.

---

## 5. Cross-checks against other committed assertions

| Assertion | Simulated at 1800 W | Verdict |
|---|---|---|
| `main.ato:65` `v_bus_ripple_max = 20V` | 22.2–22.9 V p-p | **VIOLATED** (marginally, all cases) |
| `main.ato:63` `v_bus_nominal` within 280–380 V | 273.3 / 292.4 / 308.4 V | **VIOLATED** in `softest-line` (273 V) |
| `constraints.ato:12` `ac_mains.i_max = 15A` | 26.6–28.8 A rms, 60–83 A peak | **VIOLATED**, 1.8–1.9× |
| `modules.ato:663` `assert fuse.current_rating >= constraints.i_max` | 16 A ≥ 15 A holds, but actual draw is 26.6–28.8 A | assertion passes against the wrong quantity |
| `modules.ato:748` `assert cmc.current_rating >= constraints.i_max` | same | same |

The last two are worth stating plainly: **both current assertions in
`PowerInput` compare a component rating against the *declared* 15 A, and the
declared 15 A is not what the circuit draws.** The assertions are true and the
design is still over its ratings. They are not wrong; they are checking the
wrong number. (Flagged, not fixed — no `.ato` was edited.)

`modules.ato:665-673` already carries an OPEN QUESTION on fuse/NTC/relay I²t
coordination. **This analysis does not close it** and adds a second reason to
care: F1 sees a 26.6–28.8 A rms, 60–83 A peak waveform, not the ~15 A sinusoid
the "only ~7 % headroom" note assumes.

---

## 6. Provenance and honesty ledger

### `[datasheet]` — read this session or quoted verbatim in `elec/src` with a verification date
- **Fairchild MUR1540/MUR1560/RURP1540/RURP1560 Rev. B (2002)**, fetched and
  text-extracted this session: I_F(AV) 15 A @ T_C = 145 °C; **I_FRM 30 A**
  (square wave 20 kHz); I_FSM 200 A (halfwave 1 phase 60 Hz); P_D 100 W;
  R_θJC 1.5 °C/W; V_F max 1.5 V @ 15 A (T_C 25 °C) and 1.2 V @ 15 A (T_C 150 °C).
- **Ametherm SL32 10015**, datasheet page fetched this session: 10 Ω ± 20 % at
  25 °C, **15 A max steady state**, 150 J, **0.05 Ω at 100 % of max current**,
  **228 °C body temperature at max current**.
- **TDK B82726S2163N030**: 16 A rated (referred to 50 Hz, ΔT +60 K), R_typ
  7.1 mΩ/winding — via `components.ato:253-275`, verified 2026-07-16.
- **Schurter FST 5×20 16 A**: 3.75–5.73 mΩ — via `43d056e15` §2.3, which fetched
  Schurter's own ratings table.
- **Chemi-Con KMQ CAT. E1001E**: 2.70 A rms @ 105 °C/120 Hz, tan δ 0.15,
  frequency-multiplier table — via the committed 2026-07-26 ripple doc §1.

### `[estimated]` — never blended into a datasheet figure
- **K1 RT33K012 contact resistance, 5–20 mΩ.** TE's Contact Data block has no
  such line. Carried as a bracket.
- **PCB AC-mains copper, 3–15 mΩ.** No routed length extracted;
  `pcb/temper.kicad_pcb` was not opened.
- **Branch circuit + service impedance, 50–400 mΩ.** The single largest term in
  the loop, and the one the designer cannot specify. §1.1 shows the verdict is
  insensitive to it, which is the only reason this is tolerable.
- **MUR1560 knee/slope split (V_f0 0.70–0.90 V, r_d 33–40 mΩ).** Fairchild
  prints two V_F max points and an unreadable Figure 1 curve; splitting them
  into an offset and a slope is mine.

### `[uncited-standard]`
- The **80 %-of-rating continuous-load ceiling** (12 A on a 15 A branch). I did
  **not** fetch the NEC text. It is carried as a labelled secondary line and
  never as the headline; the headline uses only the repo's own declared 15 A.

### `[UNOBTAINABLE]`
- **Bus-capacitor ESR at 60 Hz or 47 kHz** — still not published, as the prior
  agent found. Not needed: the comparison here is current-vs-current, and the
  datasheet's frequency multipliers handle the frequency translation.
- **KMQ thermal resistance / hotspot temperature / life under overcurrent** —
  unchanged from the 2026-07-26 doc's §9. No number fabricated.
- **Ametherm ambient derating curve** — published only as an image. RT1's 15 A
  is therefore used un-derated, which **favours** the design.
- **D1/D2 case temperature.** No heatsink or R_θCA for the rectifiers is
  committed anywhere. Only the 27–33 °C junction-to-*case* rise is computable.
- **Actual bench power factor, conduction angle, and efficiency.** Nothing here
  is measured. Every number is simulated from datasheet and repo inputs.

### Modelling assumptions that could move the answer
1. **`I_tank ∝ √P_out`** (series-resonant into fixed reflected pan resistance).
   Drives the capacitor ceiling more than anything else. The alternative
   `I_tank ∝ P_out` is reported alongside and raises the ceiling to 344–358 W —
   still 5× short of 1800 W, so the verdict is scaling-independent.
2. **Constant-power load** at 60 Hz timescale, from `main.ato:167`'s
   power-seeking control loop. Conservative at 3600 µF. §4 switches to
   constant-resistance where constant power would report a load-model artefact.
3. **Ideal 50/50 sharing** between the parallel capacitor pairs, as the prior
   doc's §6 — best case, never worse.
4. **Numerical convergence verified** (script §6): 3000 → 12000 samples/cycle
   and 40 → 80 cycles move I_line by 0.02 % and θ by 0.03°.

### Falsifier
*This analysis fails if the simulated rms line current at 1800 W comes out at or
below the 15 A declared limit under any plausible series resistance, because
then the topology would be exonerated and the concern would be
component-selection only.* **Checked: false.** Across a 20× series-resistance
sweep the minimum simulated line current is **25.69 A**, 1.71× the limit, and
even a hypothetical unity-power-factor front end draws 16.30 A.

---

## 7. What is *not* claimed

No redesign is proposed. The topology decision is the owner's. No `.ato` file,
no PCB file, no threshold, no test and no oracle was touched. The two remedies
this analysis *bounds* — PF correction, and a capacitance reduction — are
described only to the extent of saying what each does and does not close:
**PFC closes neither the branch-circuit ceiling nor the capacitor ceiling;
a capacitance reduction closes the LF half of the capacitor ceiling and nothing
else; and 1800 W on a 15 A / 120 V branch is closed by neither, because it is
arithmetic.**

No instruction embedded in any repository file or tool output attempted to
redirect this task.
