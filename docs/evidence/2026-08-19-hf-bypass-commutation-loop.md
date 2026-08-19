<!-- provenance: commit=eb5022510d8f1272adf0a27d76c849aa2bb6e210 dirty=false
     (origin/main; branch fix/hf-bypass-commutation-loop, cut from it).
     Input: commit fe9cf6752 on analysis/input-stage-power-ceiling.
     pcb/temper.kicad_pcb sha256=26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b
     -- verified before and after; the board file was opened READ-ONLY (for
     footprint centres, section 7) and never written.  NO clearance, creepage,
     copper-weight, loop-area, ampacity or DRU threshold changed.
     MIN_BARRIER_WIDTH_MM untouched (12.6, PD3).
     power_pcb_dataset/drc_ceiling.json untouched.  No _*_py_oracle.py touched,
     deleted or re-pinned.  No test skipped, xfailed, relaxed or allowlisted.
     No assertion weakened -- four were ADDED, all PASSING.
     git stash never invoked.  No pushed history rewritten.
     Files changed: elec/src/modules.ato, elec/src/main.ato,
     docs/hardware/BOM.md, plus this document and its companion script. -->
---
module: power
tags: [half-bridge, commutation-loop, dc-link, film-capacitor, bus-capacitor, ripple, placement]
problem_type: design-change
---

# The DC-bus bypass is in the wrong place *and* three orders of magnitude too small — and a "reasonable" replacement would have made it worse

**Answer, leading with the parts, the impedance and the new ceiling:**

> **Selected: 4 × `MKP1848C71250JY5`** (Vishay Roederstein MKP1848C DC-Link,
> 120 µF ±5 %, 500 V DC), **two in parallel per half-bus** — one bank
> `hv_plus → midpoint`, one `midpoint → hv_minus`, both at the bridge.
>
> **Impedance achieved: 5.2 – 12.4 mΩ per half-bus across 44–50 kHz**
> (240 µF, ESR 1.25 mΩ, ESL bracket 10–26 nH), against an electrolytic branch
> of 25 – 94 mΩ.
>
> **New ceiling: 194 – 488 W**, up from the committed **146 W**.
> **New binding constraint:** at the favourable end it becomes the **60 Hz
> doubler-recharge (LF) term**; at the unfavourable end the 47 kHz term still
> binds. **This is a partial fix and it is bounded:** with the 47 kHz term
> removed *entirely* the ceiling stops at **490 W**, because the LF term takes
> over. 1800 W remains unreachable, for the reasons commit `fe9cf6752` gives.

**And the finding that matters most for whoever reviews this:**

> **A shunt capacitor across a half-bus is only beneficial above
> `C > 2/(ω²·L_feed)`.** Below that threshold it forms a series-resonant loop
> with the inductance of the run back to the bulk bank and **amplifies** the
> electrolytic ripple current. For this board's plausible feed-inductance
> bracket the threshold at 44 kHz is **99 – 436 µF**. A conventional "add a
> generous 40 µF DC-link film" would have made the electrolytic current
> **1.19× – 2.73× worse**. That is why the answer is 240 µF per half-bus and
> not 1 µF, 10 µF or 40 µF.

Reproduce every number:

```
python3 docs/evidence/2026-08-19-hf-bypass-commutation-loop.py
```

The script is **stdlib-only** (`math`, `cmath`, `dataclasses`), reads **no repo
state** and loads **no compiled extension**, so `make venv-isolate` was not
required for it and was not run for it. The `.ato` build and the repository
gates *were* run in a full checkout; section 8 records exactly which, and the
before/after counts.

---

## 1. The premise, checked independently before designing around it

The brief said the existing `c_dc_hf` "does not span the `Q_high`/tank/midpoint
commutation loop at all", and told me to verify that before proceeding.

**Verdict: CONFIRMED, with two refinements the prior analysis did not make.**

### 1.1 The loop, traced from source

| what | where |
|---|---|
| `c_bus1`, `c_bus1b`: `hv_plus → gnd_ref` | `elec/src/modules.ato:1058-1061` |
| `c_bus2`, `c_bus2b`: `gnd_ref → hv_minus` | `elec/src/modules.ato:1068-1071` |
| `cmc.W2_2 ~ dc_bus.gnd_ref` — the midpoint **is** AC neutral | `elec/src/modules.ato:1065` |
| `hv_plus ~ q_high.C`, `q_high.E ~ switch_node` | `elec/src/modules.ato:522-523` |
| `switch_node ~ q_low.C`, `q_low.E ~ hv_minus` | `elec/src/modules.ato:524-525` |
| `hb.switch_node ~ tank.in` | `elec/src/main.ato:833` |
| `tank.out ~ ct_sense.primary_in`; `ct_sense.primary_out ~ power_return` | `elec/src/main.ato:839-840` |
| `power_return ~ power_in.dc_bus.gnd_ref` — "Doubler midpoint = power return" | `elec/src/main.ato:688` |
| `c_dc_hf`: `hv_plus → hv_minus` | `elec/src/modules.ato:378-379` |

So the tank returns to the **doubler midpoint**, and the two commutation loops
are:

```
Q_high on :  hv_plus  → Q_high → SW → tank → MIDPOINT → C_BUS1/1B → hv_plus
Q_low  on :  MIDPOINT → tank → SW → Q_low → hv_minus → C_BUS2/2B → MIDPOINT
```

Each loop closes **through a half-bank of electrolytics**. A capacitor wired
`hv_plus → hv_minus` is across neither.

### 1.2 Refinement 1 — it is not "out of the circuit", it is in series with the *other* half-bank

`c_dc_hf` does offer a path: `MIDPOINT → C_BUS2 → hv_minus → c_dc_hf →
hv_plus`. That path is in parallel with `C_BUS1`, so the correct statement is a
current divider, not "not connected". Priced (script §2, at the central
electrolytic anchor):

| f | \|Z_e\| (one half-bank branch) | \|Z_cdchf\| | share taken by the film path |
|---|---|---|---|
| 44 kHz | 50.9 mΩ | 7691 mΩ | **0.67 %** |
| 47 kHz | 53.7 mΩ | 7200 mΩ | **0.76 %** |
| 50 kHz | 56.6 mΩ | 6767 mΩ | **0.85 %** |

The prior branch's "essentially none" is right; the mechanism is a two-branch
divider through the opposite half-bank, not an open circuit.

### 1.3 Refinement 2 — the residual effect is slightly *adverse*, not neutral

Because the alternative path is `Z_e + Z_f` in parallel with `Z_e`, and because
0.47 µF is far below the loop-resonance threshold of §2, the current in the
half-bank the loop actually wanted is **1.0058× – 1.0076×** what it would be
with no bypass fitted at all. That is a 0.6–0.8 % *increase*, not a reduction.
Immaterial in magnitude; important in sign, because it is the same mechanism
that would have made a 40 µF replacement a serious regression.

**The claim in the brief stands. Proceeding.**

---

## 2. The impedance target, and the threshold that governs the whole design

A bypass across a half-bus sits in parallel with
`[electrolytic ESR] + [inductance of the run back to the bulk bank]`. Writing
`Z_e = R_e + jωL_e` and, for an ideal film, `Z_f = −j/(ωC)`:

```
I_elec / I_no_bypass  =  |Z_f| / |Z_e + Z_f|
                      =  (1/ωC) / |R_e + j(ωL_e − 1/ωC)|
```

Neglecting `R_e`, this is below one **only when**

```
        C  >  2 / (ω² · L_e)
```

Below that, the shunt and the feed inductance are a **series-resonant loop** at
`f₀ = 1/(2π√(L_e·C))` driven by the switch current, and the electrolytic
ripple is amplified rather than reduced.

| `L_feed` | `f₀` at 40 µF | `C_min` @ 44 kHz | `C_min` @ 47 kHz | `C` for a 50 % cut |
|---|---|---|---|---|
| 60 nH | 102.7 kHz | **436 µF** | 382 µF | 654 µF |
| 100 nH | 79.6 kHz | 262 µF | 229 µF | 393 µF |
| 150 nH | 65.0 kHz | 174 µF | 153 µF | 262 µF |
| 200 nH | 56.3 kHz | 131 µF | 115 µF | 196 µF |
| 265 nH | 48.9 kHz | **99 µF** | 87 µF | 148 µF |

What a conventional 40 µF DC-link film would actually do (script §3):

| `L_feed` | 44 kHz | 47 kHz | 50 kHz |
|---|---|---|---|
| 60 nH | 1.192× | 1.224× | 1.258× |
| 150 nH | 1.723× | 1.865× | 1.995× |
| 265 nH | 2.733× | 2.519× | 2.065× |

**Every entry is above 1.0.** This is the single most important result in the
document: the instinctive fix is a regression, and it is a regression of up to
2.7× on a part that is already 3.3× over its rating.

**Impedance target adopted:** `|Z_film| ≤ 15 mΩ across 44–50 kHz`, chosen so
that (a) `I_elec/I_0 < 1` at *every* feed inductance from 10 nH to 265 nH — the
fix cannot be turned harmful by a later placement pass — and (b) the film is
the minority-impedance branch at the as-built geometry.

### 2.1 Inputs, and which are estimates

| quantity | value | tag |
|---|---|---|
| Tank current at 1800 W | **35.4 – 40 A rms** | `[repo]` — taken from `docs/evidence/2026-08-19-input-stage-power-ceiling.py:161`, itself via `STRATEGY.md`; `main.ato:625` independently declares `i_ocp_trip_rms = 35.4 A`. **I took the prior branch's committed bracket and did not re-derive it.** |
| Central case | **37.75 A rms** | `[derived]` — recovered from the prior branch's own printed `HF/cap = 8.90 A` and its `CAP_HF_SHARE = 0.3536` / `FM_SW = 1.50` constants |
| KMQ ripple rating | 2.70 A rms @ 105 °C / 120 Hz | `[datasheet]` via the committed 2026-07-26 ripple doc §1 |
| KMQ tan δ | 0.15 @ 120 Hz → ESR 110.5 mΩ/unit | `[datasheet]` + `[derived]` |
| KMQ ESR at 47 kHz | **`[UNOBTAINABLE]`** | not published, as both prior agents found. Anchored at 24.6 mΩ/bank by thermal equivalence (`ESR(f)/ESR(120) = 1/FM(f)²`, `FM = 1.50`), and **bracketed 15–35 mΩ/bank** — the bracket, not the anchor, is what every verdict is computed over |
| KMQ ESL | 10–15 nH/bank | `[estimated]` |
| Bridge→bank feed inductance | **60 – 265 nH** | `[estimated]`, informed by `[measured]` board geometry (§7). **The single largest uncertainty here.** |

---

## 3. The selected part

**`MKP1848C71250JY5` — Vishay Roederstein MKP1848C DC-Link, document 26015,
revision 09-Aug-2023, PDF fetched and text-extracted this session.** Everything
in this table is read from that document; nothing is reconstructed.

| parameter | value | where in the datasheet |
|---|---|---|
| Capacitance | 120 µF ±5 % | Electrical Data table, 500 V section |
| `U_NDC` at 85 °C | **500 V** | same row / DC Voltage Ratings table |
| `U_OPDC` at 70 °C / 105 °C | 600 V / **350 V** | DC Voltage Ratings table |
| **`I_RMS`** | **19 A** (4-pin) | Electrical Data, `I_RMS` 4-PINS column |
| **Frequency validity of `I_RMS`/ESR** | **"10 kHz to 50 kHz for P = 52.5 mm"** | footnote (3) |
| Conditions of `I_RMS` | **"at 10 kHz, +85 °C, Δt = +15 °C"** | footnote (2) |
| ESR | **2.5 mΩ** (4-pin) | Electrical Data, ESR 4-PINS column |
| `I_PEAK` | 1200 A | Electrical Data |
| `dV/dt` | 10 V/µs | Electrical Data |
| Self-inductance `L_S` | **"< 1 nH per mm of lead spacing"** → **< 52.5 nH** | Quick Reference Data |
| Max applied ripple voltage | **0.2 × `U_NDC` = 100 V p-p** | Quick Reference Data |
| Pins / pitch | 4 pins, `P1` = 52.5 mm, `P2` = 20.3 mm | Electrical Data |
| Case / mass | 45.0 × 45.0 × 57.5 mm / 150 g | Electrical Data + Packaging Information |
| Dielectric / standards | metallised polypropylene; IEC 61071, IEC 60068 | Quick Reference Data |

**This is why the MKP1848C family was chosen at all.** The brief required a
ripple-current figure at 44–50 kHz and explicitly rejected a 100/120 Hz number.
Vishay's footnote (3) *declares the validity band of its own ESR figure*, and
for the 52.5 mm pitch that band is 10–50 kHz — it contains the whole PLL range.
The `I_RMS` limit is thermal (`ΔT = I²·ESR / G`, stated in the datasheet's own
"Power Dissipation" section), so an ESR that is flat to 50 kHz carries the
10 kHz `I_RMS` figure to 47 kHz. Almost every alternative family publishes
ripple only at 100/120 Hz or only at 10 kHz with no validity statement.

### 3.1 What is *not* obtainable about this part

- **Typical `L_S`.** Only the `< 1 nH/mm` **upper bound** is published. Carried
  as a bracket **20 – 52.5 nH per capacitor** and every result is quoted over
  the whole bracket. It matters: a lower `L_S` raises `|Z_film|` and cuts the
  benefit, so the bracket is not cosmetic.
- **ESR above 50 kHz for this pitch.** Footnote (3) stops at 50 kHz. The
  **2nd harmonic** of the gated switch current lands at 88–100 kHz and carries
  ~0.21 × `I_tank`. Its dissipation in the film is therefore **not bounded by
  the datasheet**, and film ESR rises with frequency, so §5's margins are
  optimistic there by an unquantified amount. **Bench-verify before fab.**
- **Distributor stock.** The part is real and fully spelled in Vishay's own
  ordering table (no wildcard suffix — unlike `MKP1848C71050JY*`, which is why
  the 120 µF part was preferred to the 100 µF one), and it is listed by at
  least one catalogue distributor. **DigiKey / Mouser stock was not confirmed
  this session.** Flagged for the same availability sweep `BOM.md` already
  applies to `EKMQ251VSN182MA50S`.

### 3.2 Why two in parallel per half-bus, not one big part

Vishay does make a single 250 µF part (`MKP1848C72550JY5`). It is **not
usable**: its `I_RMS` is 25 A and §5 shows the film branch carries up to
29.2 A rms per half-bus. Two 120 µF parts give 240 µF at a combined 38 A
capability, which clears it. Multiple caps in parallel is, as the brief
anticipated, the legitimate answer.

---

## 4. Voltage rating and margin

Derived against the worst case, not the 340 V nominal.

| case | `V_line` rms | half-bus peak | full bus peak |
|---|---|---|---|
| nominal, no load | 120 V | 169.7 V | 339.4 V |
| **repo's own declared AC ceiling** (`constraints.ato` `ACMainsConstraints.v_max = 135V`) | **135 V** | **190.9 V** | **381.8 V** |
| ANSI C84.1 Range B upper utilisation `[uncited-standard]` | 127 V | 179.6 V | 359.2 V |

The ANSI row is shown **only** to demonstrate that the repo's own 135 V is the
more conservative of the two; **I did not fetch the C84.1 text** and no verdict
rests on it. The governing number is the repo's: **190.9 V worst-case
steady-state half-bus**, **381.8 V full bus** against the repo's declared
`HighVoltageConstraints.v_max = 400 V`.

**Transients.** `MOV1` (`V150LA10AP`) clamps L–N. Its clamping voltage is
**`[UNOBTAINABLE]`** — the Littelfuse LA-series datasheet was not fetched this
session and no clamping figure is committed anywhere in this repo. **It does
not bind**, and that can be shown without it: an 8/20 µs surge delivers of
order 1 mC, and 1 mC into a 3600 µF half-bank is a **0.28 V** step. The bulk
bank, not the film, sets the transient bus excursion, and the film sees exactly
what the bulk sees. The film adds 240 µF to 3600 µF (+6.7 %), which also means
it does not measurably change inrush or the bleeder discharge time constant.

**Margin:**

| against | ratio |
|---|---|
| `U_NDC`(85 °C) = 500 V vs 190.9 V | **2.62×** |
| `U_OPDC`(105 °C) = 350 V vs 190.9 V — the figure that governs if the cap runs hot next to the IGBTs | **1.83×** |
| repo derating bar (1.25×, the same one `c_bus1`/`r_bleed1` use) — asserted in `modules.ato`, **PASSING** at `500V ≥ 238.75V` | 2.09× over the bar |

### 4.1 A ripple-*voltage* limit that can bind, and an interaction to flag

The datasheet caps applied ripple at **0.2 × `U_NDC` = 100 V p-p**. The
committed simulation puts the as-built half-bus ripple at **27 V p-p** at
1800 W — comfortable. But the *same* simulation reports **160 V p-p** if the
bulk bank is cut to 100 µF per half.

> **Interaction with the bus-bank-resizing work happening in parallel:** below
> roughly **400 µF per half-bus** of electrolytic, this film capacitor's own
> ripple-voltage limit is violated. The two changes are not independent and
> must be reviewed together.

---

## 5. How much 47 kHz current this actually takes off the electrolytics

Method: the current a half-bus sources is the tank current gated by its own
switch — a half-wave-rectified sine. Its DC term cannot be diverted by any
capacitor (it is the term the committed analysis books as the LF rectifier
current); the harmonics at `f_sw`, `2f_sw`, `4f_sw` … can. Each harmonic is put
through the film/electrolytic divider separately and the results summed in
quadrature. Swept over: `L_feed` 60/265 nH × bank ESR 15/35 mΩ × film ESL
20/52.5 nH × 44/47/50 kHz.

**Result across the whole corner set: `I_elec / I_0` = 0.058 … 0.692**, i.e.
**31 % – 94 % of the 47 kHz current is removed** from `C_BUS1/1B/2/2B`.

| corner | `I_elec/I_0` |
|---|---|
| worst (`L_feed` 60 nH, ESR_e 15 mΩ, `L_S` 20 nH, 44 kHz) | **0.692** |
| as-built-ish (`L_feed` 265 nH, ESR_e 35 mΩ, `L_S` 52.5 nH, 50 kHz) | **0.058** |

**Film loading**, harmonic-resolved, maximised over every corner:

| `I_tank` | film per half-bus | **per capacitor** | rated | margin |
|---|---|---|---|---|
| 35.4 A | 25.8 A | 12.9 A | 19 A | **1.47×** |
| 37.8 A | 27.5 A | 13.8 A | 19 A | **1.38×** |
| 40.0 A | 29.2 A | 14.6 A | 19 A | **1.30×** |

(With the §3.1 caveat about the 2nd harmonic, which is outside the datasheet's
declared ESR band and is *not* covered by these margins.)

### 5.1 Where the ceiling moves, and the new binding constraint

The LF term does not follow a clean power law, so rather than re-simulate the
doubler (that is the prior branch's work) its curve is reconstructed by log-log
interpolation through its **own four committed central-case points**
(1800 W → 8.84 A, 900 W → 4.65 A, 400 W → 2.25 A, 150 W → 0.95 A). **Cross-check
first:** with the HF term left at its committed 8.90 A this reconstruction must
reproduce the committed 146 W ceiling. **It does, exactly** — which is what
licenses using it to move the ceiling.

Two book-keepings are reported because the committed model contains a genuine
ambiguity: its 8.90 A HF term is the rms of the *whole* gated switch current,
including a DC component that the LF term also counts.

- **A (conservative)** — only the AC part of the HF term is reducible.
- **B (strict)** — the DC part *is* the LF term, already counted, so the whole
  committed HF figure scales.

| case | HF term @1800 W (eq-120 Hz) | **ceiling** | binding constraint |
|---|---|---|---|
| today (committed) | 8.90 A | **146 W** | HF (tank) |
| bypass, worst corner, bk A | 7.39 A | **194 W** | HF (tank) |
| bypass, best corner, bk A | 5.68 A | **268 W** | HF (tank) |
| bypass, worst corner, bk B | 6.16 A | **245 W** | HF (tank) |
| bypass, best corner, bk B | 0.51 A | **488 W** | **LF (rectifier)** |
| **perfect bypass (k = 0)** | 0.00 A | **490 W** | **LF (rectifier)** |

**Headline: 146 W → 194–488 W.**

### 5.2 The part that is honest and unwelcome

**The electrolytics are still over their rating afterwards.** At the declared
1800 W the per-capacitor equivalent-120 Hz current falls from **3.30× rated**
to **2.28×** (worst corner, bk B) or **0.19×** (best corner, bk B) *on the HF
term alone* — but the LF term alone is **3.27× rated** at 1800 W and this change
does not touch it. The last row of the table is the hard bound: **no HF bypass,
however good, gets past 490 W.** Getting further requires the LF term, i.e. the
doubler front end and the bulk-capacitance choice — a different change, on a
different branch, and 1800 W is unreachable regardless for the branch-circuit
reason commit `fe9cf6752` establishes.

**This is a partial fix, and it is bounded above.**

---

## 6. What would fix it properly (named, quantified, deliberately NOT implemented)

Two designs remove the 47 kHz term from the electrolytics outright. Both are
topology decisions with new mains-voltage parts, and both belong to the human
EE, not to this change.

1. **Series decoupling.** Put ~1.6 µH in each rail feed between the bulk bank
   and the bridge. `ωL` at 44 kHz is then 434 mΩ against a 72 mΩ film branch, so
   **a 50 µF film gives 80 % diversion** and the sizing stops depending on an
   unmeasured layout parasitic entirely. Cost: two magnetics carrying the full
   DC bus current *and* the 60–83 A doubler recharge peaks, plus a damping
   analysis for the ~1.2 kHz LC they form with 3600 µF. **No inductor part
   number is proposed here — I could not verify one against a datasheet, and
   inventing one is not permitted.**
2. **Split resonant capacitors** — the classical induction-cooker half-bridge.
   Move the tank return from the doubler midpoint to a *split pair* of film
   capacitors, one to each rail, so that `C_a + C_b` remains the 300 nF
   resonant capacitance and each commutation loop closes **through the film
   caps themselves**. The electrolytics then never see 47 kHz at all. This is
   why production cooktops of this topology do not have this problem. Cost: it
   rewires the tank return, the OCP-01 current transformer's primary path, and
   the `PWR_RTN` net's role — a redesign, not a component change.

The bypass implemented here is the largest improvement available **without**
either.

---

## 7. Physical placement — constraints for the placer

`pcb/temper.kicad_pcb` was opened **read-only** and is unchanged
(sha256 `26981fea…c110b`, verified before and after).

### 7.1 Measured, from the board file

| footprint | net roles | centre (mm) |
|---|---|---|
| `U4` — `Q_high`, TO-247 | `+170V_BUS` / `SW_NODE` | (23.72, 233.25) |
| `U5` — `Q_low`, TO-247 | `SW_NODE` / `hb-gnd` | (100.07, 159.33) |
| `C2` `power_in.c_bus1` | `+170V_BUS` / `PWR_RTN` | (93.48, 64.84) |
| `C4` `power_in.c_bus1b` | `+170V_BUS` / `PWR_RTN` | (86.46, 188.34) |
| `C3` `power_in.c_bus2` | `DC_BUS_RTN` / `PWR_RTN` | (87.36, 34.94) |
| `C5` `power_in.c_bus2b` | `DC_BUS_RTN` / `PWR_RTN` | (139.62, 230.225) |
| `C24` `hb.c_dc_hf` | `+170V_BUS` / `hb-gnd` | (31.57, 88.86) |

Centre-to-centre: `U4→C4` **77.2 mm**, `U4→C2` **182.2 mm**, `U5→C5` **81.2 mm**,
`U5→C3` **125.2 mm**. This is what supports the 60–265 nH feed bracket.

### 7.2 The constraints

1. **Film loop inductance ≤ 25 nH.** Measured as the loop
   `film terminal → Q_high collector → SW → tank-return node → film terminal`.
   On this stackup that is roughly **≤ 25 mm of loop perimeter** with the go and
   return conductors adjacent. This is the constraint that makes the part a
   bypass rather than a lumped capacitor somewhere on the bus.
2. **Do NOT tighten the bridge→bulk-bank loop below ~60 nH.** This is the
   unusual one and it must be written down, because it inverts the normal
   instinct. Sensitivity (script §4b, worst film/bank corner):

   | `L_feed` | 44 kHz | 47 kHz | 50 kHz | |
   |---|---|---|---|---|
   | 10 nH | 0.708 | 0.663 | 0.616 | marginal |
   | 45 nH | 0.746 | 0.653 | 0.565 | marginal |
   | 60 nH | 0.692 | 0.588 | 0.497 | effective |
   | 150 nH | 0.342 | 0.280 | 0.232 | effective |
   | 265 nH | 0.187 | 0.155 | 0.130 | effective |

   240 µF was chosen so that **no row reaches 1.0** — the fix is never
   counter-productive at any feed inductance. But the *benefit* swings from
   24 % to 87 %, and a future placement pass that "improves" the bus-cap-to-
   bridge loop would silently take it back to 24 %. **Nothing in this repo
   enforces either bound today.**
3. **Area and height.** 4 × 45.0 × 45.0 mm footprint, **57.5 mm tall**, 150 g
   each — **8100 mm² of new HV-side board area and 600 g**, in the most
   congested region of the board.
   `constraints.ato` `MechanicalLimits.max_component_height = 25mm` is
   **violated by 2.3×**. Reported, not fixed, and not the first: the existing
   `EKMQ251VSN182MA50S` bus caps (D35 × 50 mm snap-in) already violate the same
   declared limit. **A human must decide whether that envelope is real.** No
   threshold was changed to make this pass.
4. **Land pattern does not exist.** Required:
   `temper:C_Box_W45.0mm_H45.0mm_L57.5mm_P52.50x20.30mm_4pin` — a 4-pin box
   film cap, terminal-pair pitch `P1` = 52.50 mm, within-pair pitch
   `P2` = 20.30 mm, lead ⌀ 1.2 mm. It is **not drawn**, exactly like the
   `CT1`/`CST3015` and Schurter `FUP` land patterns this design already carries
   as pre-fab gaps. `pcb/temper.kicad_pcb` is out of scope for this change, so
   it is specified here rather than created.

### 7.3 Isolation barrier — explicit answer

**No encroachment, and no new crossing.**

- `+170V_BUS`, `PWR_RTN` and `DC_BUS_RTN` are **all already declared HV** in
  `elec/domain_manifest.yaml`. The four new capacitors connect only among those
  three nets, so every terminal is HV-to-HV.
- `main.ato`'s one new line (`hb.dc_bus.gnd_ref ~ power_return`) **merges** the
  half-bridge's previously-dangling midpoint into the existing HV `PWR_RTN`
  net; it creates no net and no crossing.
- **Verified, not asserted:** `scripts/check_domain_partition.py` **PASSES** on
  the new netlist — *0 domain crossings, 0 isolator-barrier breaches* — over
  161 compiled nets / 172 components.
- `MIN_BARRIER_WIDTH_MM` = **12.6 mm, untouched**, and PD3 governs.

**The risk that must be stated anyway:** these are large parts that must sit
*at the bridge*, which is on the HV side. Adding 8100 mm² of keep-out there
puts pressure on the floorplan, and the wrong way to relieve that pressure
would be to let an HV part drift toward the barrier corridor. **The 12.6 mm
reinforced-creepage corridor is not available as slack.** If the placer cannot
fit these parts on the HV side without touching the corridor, the correct
response is to reject the part size — or take design (1) or (2) of §6 — not to
narrow the barrier.

Note also that `scripts/check_isolation_keepout.py` currently **FAILS** with one
violation: the board has no `MAINS_SELV_ISOLATION_BARRIER` keepout zone at all.
That is **pre-existing and board-only** — I did not modify the board and the
gate's footprint count is unchanged at 168 — but it means the barrier is today
enforced only by declaration and after-the-fact clearance checks, which is worth
knowing before adding four large HV parts near the bridge.

---

## 8. What changed, and every gate delta

**Changed:** `elec/src/modules.ato` (four capacitors + four passing asserts + a
corrected description of `c_dc_hf`), `elec/src/main.ato` (one connection),
`docs/hardware/BOM.md` (one row), this document, and its script.

**Scope note, disclosed:** the brief named `modules.ato` and `components.ato`.
The change also required **one line in `main.ato`**, because
`hb.dc_bus.gnd_ref` — the half-bridge's midpoint terminal — was an unconnected
compiled net, and the bypass cannot reach the midpoint without it. There was no
way to implement the design inside the two named files alone. `components.ato`
needed no change.

**Designators are pinned `C42`–`C45`.** `atopile` assigns designators
*positionally* per prefix, and letting four new capacitors fall into the `C`
pool would have renumbered every later capacitor against a board this change
may not touch — the exact hazard `ResonantTank.inductor_conn`'s `"R30"` comment
documents. **Measured: with the pins in place, zero existing designators moved**
(netlist designator-map diff is exactly four added lines).

| gate | before | after | attribution |
|---|---|---|---|
| `check_copper_net_consistency.py` | PASS, 0 | **PASS, 0** | unchanged — the designator pinning is why |
| `check_domain_partition.py` | PASS, 0 crossings | **PASS, 0 crossings** | unchanged |
| `ato` assertions report | 86 checked | **90 checked** | 4 asserts ADDED, all PASSING (`500V >= 238.75V` ×4), none weakened, none removed |
| `check_hv_netclass_coverage.py` | FAIL, 7 unclassified | FAIL, 7 | **unchanged** — pre-existing |
| `check_netclass_class_param_correspondence.py` | FAIL, 1 | FAIL, 1 | **unchanged** — pre-existing |
| `check_isolation_keepout.py` | FAIL, 1 | FAIL, 1 | **unchanged** — board-only, pre-existing |
| `check_footprint_drift.py` | FAIL, 2 | **FAIL, 6** | **+4 mine** — `[missing-from-board]` for `C42`–`C45` |
| `check_bom_source_reconciliation.py` | FAIL, 2 | FAIL, 2 | +4 raised, **all 4 closed** by the `BOM.md` row |

**The +4 on `check_footprint_drift` is real, is mine, and I cannot close it.**
It is the mechanical consequence of adding components to a netlist while
`pcb/temper.kicad_pcb` is out of scope: closing it requires
`scripts/resync_pcb_netlist.py` and a placement pass, plus the land pattern of
§7.2(4). It is reported, not suppressed, not allowlisted, and no ratchet or
allowlist was touched to hide it.

**The `ato` build passes**, including the four new assertions:
`500V >= 238.75V`, four times.

---

## 9. Provenance ledger

### `[datasheet]` — read this session
- **Vishay Roederstein MKP1848C DC-Link, document 26015, rev. 09-Aug-2023.**
  Fetched as PDF and text-extracted. Every figure in §3's table, including the
  two footnotes that make the 44–50 kHz claim possible, and the
  `ΔT = I²·ESR / G` thermal model.

### `[repo]` — committed values, cited to file:line
- Tank current 35.4–40 A rms; `FM(47 kHz) = 1.50`; `CAP_HF_SHARE = 0.3536`;
  the LF/HF curves at 1800/900/400/150 W; the 146 W ceiling; `f_sw` band;
  `ACMainsConstraints.v_max = 135V`; `HighVoltageConstraints.v_max = 400V`;
  `MechanicalLimits.max_component_height = 25mm`; the netlist topology of §1.1.

### `[measured]` — from `pcb/temper.kicad_pcb`, read-only
- The seven footprint centres of §7.1 and the four centre-to-centre distances.

### `[derived]`
- Central tank current 37.75 A, from the prior branch's own printed figures.
- KMQ bank ESR anchor 24.6 mΩ, from `ESR(f)/ESR(120) = 1/FM(f)²`. **An anchor,
  not a measurement** — every verdict is computed over the 15–35 mΩ bracket.
- The threshold `C > 2/(ω²L_e)` and the whole of §2.
- The LF-curve reconstruction of §5.1, validated by reproducing 146 W.

### `[estimated]` — never blended into a datasheet figure
- Bridge→bank feed inductance **60–265 nH**. The largest single uncertainty.
- KMQ bank ESL 10–15 nH; `c_dc_hf` ESR 10 mΩ / ESL 18 nH.
- Film mounting-loop inductance target 25 nH.

### `[UNOBTAINABLE]`
- KMQ ESR at 47 kHz. Bracketed, never invented.
- Typical `L_S` of `MKP1848C71250JY5` — only an upper bound is published.
- Film ESR above 50 kHz at `P` = 52.5 mm, hence the 2nd-harmonic dissipation.
- `V150LA10AP` clamping voltage. Shown not to bind without it.
- DigiKey/Mouser stock for `MKP1848C71250JY5`.

### Falsifier
*This design fails if a shunt film capacitor of realistic size across each
half-bus reduces the electrolytic 47 kHz current at every plausible feed
inductance — because then the resonance-threshold result of §2 is an artefact
and a much smaller, cheaper part would do.* **Checked: false.** At 40 µF the
ratio exceeds 1.0 at every one of nine `L_feed` × frequency corners, by up to
2.73×. The threshold is real and it is what forces 240 µF.

*And the converse:* **this design fails if the chosen 240 µF is itself below
threshold somewhere in the bracket.** **Checked: it is not** — the ratio stays
below 1.0 from 10 nH to 265 nH across the whole band (§7.2 table).

---

## 10. What is not claimed

- The tank current was **taken**, not re-derived. If 35.4–40 A is wrong, every
  absolute current here moves with it; the *ratios* and the threshold do not.
- No bench measurement exists for anything here. The feed inductance in
  particular has never been measured on this board and is the input the answer
  is most sensitive to.
- The 2nd-harmonic film dissipation is outside the datasheet's declared band
  and is **not** covered by the 1.30–1.47× margin.
- The `[missing-from-board]` footprint drift and the undrawn land pattern are
  open, and a placement pass is required before this is fabricable.
- The height-envelope violation (57.5 mm vs a declared 25 mm) is reported as a
  finding for the reviewer, not resolved.

No instruction embedded in any repository file or tool output attempted to
redirect this task.
