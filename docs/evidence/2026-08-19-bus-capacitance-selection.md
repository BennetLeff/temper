<!-- provenance: commit=eb5022510d8f1272adf0a27d76c849aa2bb6e210 dirty=false
     (origin/main; branch analysis/bus-capacitance-resize, cut from it).
     pcb/temper.kicad_pcb sha256=26981fea2dbc425f456010d4d4e755cdebdefee2b53
     55ad915086352b90c110b -- verified before and after; the board file was
     never opened for writing.  No clearance, creepage, copper-weight,
     loop-area, ampacity or DRU threshold was changed.  MIN_BARRIER_WIDTH_MM
     and PD3 untouched.  power_pcb_dataset/drc_ceiling.json untouched.  No
     _*_py_oracle.py touched, deleted or re-pinned.  No test skipped,
     xfailed, relaxed or allowlisted.  No assertion in any .ato weakened.
     git stash never invoked.  No pushed history rewritten. -->
---
module: power
tags: [power-input, bus-capacitor, ripple-current, ripple-voltage, zvs,
       part-selection, doubler, analysis]
problem_type: engineering-analysis
---

# Bus capacitance: the value is not the lever — the parallel count is. A single bank covers both HF-bypass cases and moves the ceiling from 146 W to ~609 W, at which point the rectifier diodes bind, not the capacitors.

**Reproduce:** `python3 docs/evidence/2026-08-19-bus-capacitance-selection.py`
Pure stdlib, reads no repo state, loads no compiled extension — **`make
venv-isolate` is not required, stated explicitly** per the environment rule.
Runtime ~8 min.

---

## 0. Answer first

### Recommended bank

**6 × Nichicon `LGW2E471MELB25` per half-bus — 12 total, 470 µF / 250 V,
D30 × 25 mm snap-in, 2200 mA rms at 105 °C / 120 Hz — giving 2820 µF per
half-bus.**

| | Case A (HF bypass lands) | Case B (HF bypass does not land) |
|---|---|---|
| **Recommended bank** | 6 × `LGW2E471MELB25` / half | **the same bank** |
| Bank's own ceiling | **1163 – 1314 W** | **1012 W** |
| Bank still binding? | **No** | **No** |
| New binding constraint | **D1/D2 `MUR1560` I_FRM = 30 A** | same |
| **Deliverable output** | **396 – 704 W (central 609 W)** | same |

**Yes — a single selection satisfies both cases.** That is the robust answer
and it is the one to take. Case A and Case B differ only in how much margin
the bank has left over, not in which part to buy.

### Why it is a single selection

Case A is **not** "HF = 0". Branch `fix/hf-bypass-commutation-loop`
(`db44c3aa0`) measures the residual as `I_elec/I_0 = 0.058 … 0.692` — between
**5.8 % and 69.2 % of the 47 kHz current still lands on the electrolytics**
even with the film fitted. So Case A's worst corner and Case B are only
~1.35× apart at the capacitor, not orders of magnitude. A bank sized for
Case B is barely oversized for Case A, which is exactly why one selection
covers both.

### The zero-board-change fallback

If the placement rework in §9 is unacceptable, **swap the MPN only**:

**4 × Nichicon `LGW2E182MELC50`** — 1800 µF / 250 V, **D35 × 50 mm, the
identical footprint already placed**, 4050 mA vs the incumbent's 2700 mA.
**No PCB change of any kind.** Ceiling: Case A 629 – 771 W, Case B 513 W.
It does not clear the branch-circuit ceiling, but it is a **1.9 – 3.5×**
improvement on the as-built bank for a one-line BOM edit, and it is strictly
dominant over the incumbent on every axis at a lower unit price.

### What this does *not* fix

Nothing here makes 1800 W reachable. `fe9cf6752` established that 1800 W is
arithmetically impossible on a 15 A / 120 V branch (1800 VA total ⇒
`PF × η = 1.000`), and §2 below adds a second, independent reason: at the
`+10 % L / +10 % C` tank corner the 1800 W operating point sits at **42.7 kHz**,
below the 44 kHz ZVS floor, at nominal line and zero ripple.

---

## 1. The tank current the two predecessors used is superseded, and it matters by 1.57×

Both committed predecessors put the HF term at **35.4 – 40 A rms** of tank
current, citing `docs/evidence/2026-07-26-ocp01-vs-full-power-current.md`.

**35.4 A is the over-current *trip threshold*, not an operating current.**
`elec/src/main.ato:624-625` says so in the source:

```
i_ocp_trip_peak: current = 50.1A          # 2.500V / 4.99R * 100
i_ocp_trip_rms:  current = 35.4A          # peak / sqrt(2), sinusoidal tank
```

A trip threshold is by construction above the current it protects. I reached
this independently from `main.ato:80-82` (the 47 kHz point's own simulated
**28.76 A peak = 20.34 A rms**) before being pointed at
`docs/evidence/2026-08-15-ocp-threshold-decision.md` §2, which states the same
thing and supplies the committed number:

| quantity | value | status |
|---|---|---|
| 1800 W tank current, first-harmonic solve | **22.5 A rms / 31.9 A peak** (R_eff 3.55 Ω @ 46.6 kHz) | **committed**, `modules.ato:585-593` |
| same, ngspice harness | 20.7 A rms / 28.7 A peak (R_eff 4.2 Ω) | committed |
| my independent value from `main.ato:82` | 20.34 A rms | agrees with the ngspice figure to 2 % |
| 40 A "typical 1.8 kW hob" | — | that document marks it **"UNCITED, not corroborated"** |

**Every figure in this document uses 22.5 A rms.** Which figures moved:

| quantity, at 1800 W | predecessors (35.4 A) | this document (22.5 A) |
|---|---|---|
| HF per cap, actual at 47 kHz | 12.52 A | **7.95 A** |
| HF per cap, 120 Hz-equivalent | 8.35 A | **5.31 A** |
| As-built ceiling, Case B | 146 W | **277 W** |

The `CaseB(OCP)` column is retained in the script for continuity with the
predecessors, but it is not the basis of any recommendation here.

---

## 2. The ripple-voltage constraint, derived — "frequency-floor power ceiling" (FFPC)

The brief asked for the lower bound on capacitance to come from a
ripple-voltage constraint, derived and named, rather than from optimising
ripple current alone. `BUS_CAPACITANCE_DERIVATION.md` §7 parks this as
blocked. It is not blocked; the mechanism is already fully committed.

### 2.1 The mechanism

The half-bridge is a **series-resonant inverter under frequency control**.
The tank returns to the doubler midpoint, so the switch node presents the tank
a square wave of amplitude `V_bus/2`, fundamental rms `V1 = √2·V_bus/π`.
Under the first-harmonic approximation:

```
P(V_bus, f) = V1² · R_eq / (R_eq² + X(f)²) ,   X(f) = ωL_loaded − 1/(ωC_tank)
```

`P` falls as `V_bus²`. The control loop restores it by lowering `f` toward
resonance. **But `f` may not go below `f_pll_tracking_min` = 44 kHz.** That is
not a tuning preference:

- `elec/src/main.ato:269` declares it; `firmware/components/control/pll_control.h:104`
  mirrors it as `PLL_MIN_FREQ_HZ`; `scripts/check_pll_range_consistency.py`
  fails the build if they disagree.
- `main.ato:171-186` **derives** it as `1.05 × worst-case loaded resonance`
  (min-L **and** min-C), = 1.05 × 41 737 Hz = 43 824 Hz → 44 000 Hz.
- The 1.05 is the ZVS cliff from `docs/hardware/TANK_COIL_SPECIFICATION.md`,
  confirmed a **threshold, not a gradient**, in
  `docs/evidence/2026-07-27-inductance-range-sweep.md` §2.3.
- Below the loaded resonance the tank is **capacitive and the bridge
  hard-switches a 1200 V IGBT half-bridge at full bus.** It is a safety floor.

**So the ripple-voltage budget is exactly the power that the 47 kHz → 44 kHz
travel can buy back, and no more.** Formally, with the loop holding
cycle-mean power:

> **FFPC:  `mean_over_line_cycle( V_bus(t)² )  ≥  P_target / k44`,
> where `k44 = (2/π²)·R_eq/(R_eq² + X(44 kHz)²)`.**

This is a genuine lower bound on capacitance, because a smaller `C` deepens the
sag and lowers `mean(V_bus²)`.

### 2.2 Why *cycle-mean* and not instantaneous

`firmware/main/main.c:45` sets `CONTROL_LOOP_PERIOD_MS = 10` — a **100 Hz**
control loop against a **60 Hz** bus disturbance. Nyquist is 50 Hz. **The
firmware cannot track the ripple cycle-by-cycle and will alias it.** The loop
can only settle the cycle-average, which is what the FFPC inequality states.
*(Flagged, not fixed — the aliasing is a firmware finding outside this task.)*

### 2.3 The numbers

`L_loaded` = 88 µH × 0.68 = 59.84 µH (`main.ato:365,434`), `C_tank` = 300 nF
(`main.ato:385`), `f_res,loaded` = 37 563 Hz — matching `main.ato:96` exactly.

`R_eq` is carried as a **bracket 3.55 – 5.31 Ω**: 3.55 Ω is the committed
first-harmonic value, 5.31 Ω is this model's own power anchor
(`P(340 V, 47 kHz) = 1804 W`, `main.ato:80`). `2026-08-15-ocp-threshold-decision.md`
§2 states outright that **"R_eff is NOT computable from the repo; it must be
measured"**, so the bracket is the honest form. `G` is a *ratio* and is stable
across it:

| R_eq | P(44 kHz) | P(47 kHz) | P(50 kHz) | **G = P44/P47** |
|---|---|---|---|---|
| 3.55 Ω | 2541 W | 1559 W | 1044 W | **1.630** |
| 5.31 Ω | 2574 W | 1804 W | 1306 W | **1.427** |

**`G` is a finite budget with three claimants:**

| claimant | demand on G | basis |
|---|---|---|
| **Low line, 100 V** (`main.ato:56` asserts `v_ac_nominal within 100V to 130V`) | **1.440** | `P ∝ V²`, `V ∝ V_line` |
| **Tank tolerance, +10 % L / +10 % C** | **infeasible** | the 1800 W point moves to **42.7 kHz**, below the 44 kHz floor |
| Bus ripple | whatever is left | — |

For a sawtooth droop of fractional depth `r`, `mean(V²)/V_pk² = 1 − r + r²/3`,
so the ripple budget is `(1 − r + r²/3)·G_left = 1`:

| G left for ripple | r_max | V p-p on a 340 V bus |
|---|---|---|
| 1.05 | 4.8 % | 16 V |
| 1.10 | 9.4 % | 32 V |
| 1.20 | 17.7 % | 60 V |
| 1.43 | 33.6 % | 114 V |

**At rated 1800 W, low line alone demands G ≥ 1.440 against an available
1.427 – 1.630. The residual ripple budget is 0 – 8.5 %.**

`main.ato:68`'s `v_bus_ripple_max = 20V` (5.9 % of 340 V) has, until now, no
derivation anywhere in the repo — confirmed by search (only two hits, both in
`main.ato` itself, plus `2026-07-26-bus-capacitor-architecture-review.md`
noting it is un-derived). **It lands inside the derived band. This derivation
therefore ratifies it and, for the first time, gives it a source.** No
threshold was changed.

### 2.4 It is violated today

| case | V_bus p-p at 1800 W | vs `v_bus_ripple_max` = 20 V |
|---|---|---|
| stiffest-line | 22.7 V | **VIOLATED** |
| central | 22.2 V | **VIOLATED** |
| softest-line | 22.9 V | **VIOLATED** |

Reproduces `fe9cf6752` §5 to within rounding.

---

## 3. Hold-up / ride-through: **no requirement exists anywhere in this repo**

Searched exhaustively across `docs/`, `elec/`, `firmware/`, all `*.md`,
`*.ato`, `*.yaml`. **This is a finding, not an absence of effort.**

- **No hold-up, ride-through, brownout-ride-through or line-dropout
  requirement is specified in ms or cycles anywhere.**
- **The design intent is the opposite.** `elec/src/modules.ato:1028-1038`
  (`BusDischarge`): *"ANY loss of power (unplug, fuse, aux-supply fault, MCU
  dead) drops the coils and the NC contacts close → discharge engages with no
  MCU involvement."* A mains dropout of any duration **dumps** the bus into
  7.8 kΩ per half. Riding through is architecturally excluded, not merely
  unspecified.
- **Firmware has no DC-bus undervoltage path at all.** No fault code
  (`firmware/main/fault_list_generated.h:21-35`, 14 entries, none for
  undervoltage), no event or transition (`firmware/transition_table.yaml`),
  and firmware never reads bus voltage — the only hit for
  `adc_v_bus|V_BUS_SENSE|bus_voltage` in all of `firmware/` is test code
  (`firmware/test/test_common.h:286`). "UVLO" in this project means the 15 V
  gate rail and the 3.3 V logic rail (`docs/FUNCTIONAL_TEST_CRITERIA.md`
  §2.4), never the 340 V bus.
- **No controlled-shutdown sequence needs bus energy.**
  `trigger_hardware_shutdown()` (`firmware/components/safety/safety.c:440-448`)
  is three synchronous calls, and the primary cut is a fail-safe,
  default-asserted hardware path.
- **IEC 61000-4-11** (voltage dips and short interruptions) **appears nowhere
  in the repo** — zero hits.
- The closest prior acknowledgement is
  `docs/evidence/2026-07-26-bus-capacitor-architecture-review.md:390`, which
  parks *"brief dropout ride-through"* as **"Not analyzed in this document."**

**Consequence for sizing: hold-up sets no floor. The FFPC constraint of §2 is
the only lower bound on C, and it is the one used.**

**Flagged for the reviewer as an unstated requirement:** if a hold-up
requirement is ever written, the numbers it must cover already exist and are
inconsistent with the current architecture — the hardware watchdog is 1.6 s
(`firmware/README.md:155`) and shutdown-assertion budgets are 100–200 ms
(`docs/SAFETY_TEST_CHECKLIST.md:272`, `docs/PLL_ZVS_INTEGRATION_GUIDE.md:288`),
all far longer than one 60 Hz line cycle (16.7 ms). Nobody has done that
arithmetic. **Reducing capacitance reduces whatever incidental ride-through
exists**, and no one has ever quantified it.

---

## 4. Inrush

| C per half | stored energy per bank | both banks |
|---|---|---|
| 3600 µF (as built) | 51.8 J | 103.7 J |
| **2820 µF (recommended)** | **40.6 J** | **81.2 J** |
| 470 µF | 6.8 J | 13.5 J |

**Peak inrush current is set by the NTC, not by the capacitance:**
`V_pk / R_cold = 169.7 V / 10 Ω = 17.0 A`, independent of C
(`NTC_Inrush`, Ametherm SL32 10015, 10 Ω ±20 % at 25 °C `[datasheet]`).
Capacitance sets the **energy** RT1 must absorb and the **duration** F1 sees.

**How this sizing moves the open question.** `elec/src/modules.ato:665-673`
already carries an OPEN QUESTION on F1 / RT1 / K1 I²t coordination and states
no analysis exists. **This document does not resolve it, as instructed.** What
it does is move it in the *favourable* direction on every axis:

- Charge energy falls **103.7 J → 81.2 J** (−22 %) against RT1's 150 J
  `[datasheet]` rating. Both figures were already inside it; the margin widens
  from 1.45× to 1.85×.
- Peak inrush current is unchanged (NTC-set).
- The inrush *duration*, and hence the I²t the 16 A time-lag fuse integrates,
  falls in proportion to charge.
- **K1 pull-in timing is untouched** — the bypass relay closes on the same
  schedule and now shorts out a smaller charge deficit.

**Nothing here makes the coordination question harder, and the energy term
moves 22 % in its favour. It still needs the fuse I²t vs NTC-profile vs
relay-timing analysis that `modules.ato:665-673` asks for.**

*(A second, unfavourable interaction is flagged in §9: 12 cans instead of 4
lengthens the charge path and adds parallel-branch inductance. That is a
placement question, not a sizing one.)*

---

## 5. The real design trade: capacitance **value** is not the lever

### 5.1 The window

| bound | value | source |
|---|---|---|
| **Upper**, BusDischarge <60 s at worst-case tolerance (R +5 %, C +20 %) | **3793 µF/half** | `modules.ato:1126-1140`, re-derived |
| **Lower**, FFPC at 950 W | **460 µF/half** | §2, derived |
| **Lower**, film bypass ripple-voltage limit at 950 W | **550 µF/half** | §6, derived |

BusDischarge was retuned to 2 × 3.9 kΩ per string on 2026-07-27, so it now
**passes** at the as-built 3600 µF (5.1 % margin) and only ever gets easier as
C falls. **It never binds a reduction** — correcting
`BUS_CAPACITANCE_DERIVATION.md` §5, which was written against the older 9.4 kΩ.

### 5.2 Inside the window, capacitance barely matters

Per-capacitor **LF** ripple, at constant delivered power, at N = 2:

| C/half | 1800 W | 950 W |
|---|---|---|
| 1000 µF | 8.99 A | 4.88 A |
| 2200 µF | 8.84 A | — |
| 3600 µF | 8.85 A | 4.87 A |

**Across the entire legal window the LF ripple current moves by under 2 %.**
The dramatic 8.85 → 1.56 A fall in the brief's sweep happens **only below
~470 µF/half**, and that entire region is excluded by §2's FFPC floor and, if
the film bypass lands, by §6's floor as well.

### 5.3 What is being given up, quantified

The brief asked that if the true optimum lies below the floor, this be said
explicitly rather than averaged away. **It does, and here is the cost:**

| | 3600 µF/half (as built) | 2820 µF/half (recommended) | 100 µF/half (sweep optimum) |
|---|---|---|---|
| LF ripple per cap @1800 W, N=2 | 8.85 A | ~8.9 A | **1.56 A** |
| Power factor @1800 W | 0.699 | ~0.70 | **0.977** |
| Line current @1800 W | 26.6 A | 26.6 A | **18.1 A** |
| Half-bus mean | 145 V | ~143 V | **52 V** |
| Half-bus ripple | 27 V p-p | 33 V p-p | **160 V p-p** |
| **FFPC (§2)** | pass | **pass** | **FAIL** |
| **Film ripple-V limit (§6)** | pass | **pass** | **FAIL, 1.6×** |

**A 5.7× reduction in LF ripple current and a 0.70 → 0.98 power-factor
improvement are genuinely on the table and are genuinely unavailable.** They
require a bus that swings 52–170 V every line cycle. That converter cannot
hold rated power at the ZVS-floor frequency (§2), and it destroys the film
bypass (§6). **This is a real design tension and the owner should see it: the
high-PF, low-C architecture that `2026-07-26-bus-capacitor-architecture-review.md`
§4 and the Hsieh 2023 precedent point at is a *different converter*, not a
component change. It would need the PLL floor, the tank, and the film
selection all re-derived together.**

### 5.4 So the lever is the parallel count

At 950 W, the LF ripple the **bank** must carry is ~9.7 A (120 Hz-equivalent),
essentially fixed. Per unit it is `9.7/N`. **Halving `C` buys nothing; doubling
`N` halves the per-unit stress.** Every recommendation below follows from this.

---

## 6. The film bypass's ripple-voltage floor — I get a different number, and report the disagreement

Branch `fix/hf-bypass-commutation-loop` (`db44c3aa0`) fits 4 ×
`MKP1848C71250JY5` (120 µF/500 V), two per half-bus, `hv_plus→midpoint` and
`midpoint→hv_minus`. Vishay's Quick Reference Data caps applied ripple at
**0.2 × U_NDC = 100 V p-p** `[datasheet, via db44c3aa0 §3]`. Because the film
sits across **one half-bus**, the quantity to compare is `v_half_pp`, not the
full-bus p-p.

**That branch asserts the floor is "roughly 400 µF per half-bus". I get
1047 µF/half at 1800 W — 2.6× higher.**

| P_out | floor (this simulation) |
|---|---|
| 1800 W | **1047 µF/half** |
| 950 W | **550 µF/half** |
| 600 W | **345 µF/half** |

**The two models agree exactly on the waveform.** That branch quotes 27 V p-p
as built and 160 V p-p at 100 µF/half; this model gives **26.9 V** and
**160.4 V**. The disagreement is in reading the crossing: `v_half_pp`
**saturates** near 160 V below ~400 µF and only falls through 100 V around
1000 µF, so a crossing interpolated from two endpoints of that curve comes out
low. Note also that 400 µF is close to this simulation's **600 W** figure
(345 µF), so the two may simply be quoted at different powers.

**Reported, not averaged, not adopted. A human should adjudicate.** It does
not change the recommendation either way: the recommended bank is
2820 µF/half, which clears both the 400 µF and the 1047 µF reading with
room to spare. **The practical consequence is that the direction the brief's
sweep favoured is floored much harder than anyone has assumed — at ~1050 µF,
not ~100 µF and not ~400 µF.**

*(Also noted from that branch and carried forward: a shunt across a half-bus
helps only above `C > 2/(ω²·L_feed)`; below that it series-resonates with the
run back to the bulk bank and amplifies electrolytic current. §9 flags that
this threshold moves with the physical rearrangement my sizing implies.)*

---

## 7. Part selection

### 7.1 What a part must do, at 950 W

| C/half | N | LF per unit (120 Hz-eq) | HF per unit, **actual at 47 kHz** |
|---|---|---|---|
| 2820 µF | 2 | 4.87 A | 5.78 A |
| 2820 µF | 4 | 2.44 A | 2.89 A |
| **2820 µF** | **6** | **1.62 A** | **1.93 A** |

**A 120 Hz ripple rating is not usable for the HF column.** The comparison is
against the 120 Hz rating **times the series' own frequency multiplier at
47 kHz**.

### 7.2 Datasheet-verified candidates

**Nichicon LGW — verified by me, direct `pdftotext` extraction of
CAT.8100N** (`nichicon.co.jp/english/series_items/catalog_pdf/e-lgw.pdf`,
fetched this session). Series: snap-in, **105 °C High Ripple Current**.

Frequency coefficient of rated ripple current, **200 • 250 V row, verbatim**:

| Frequency (Hz) | 50 | **60** | 120 | 300 | 1k | **10k** | **50k or more** |
|---|---|---|---|---|---|---|---|
| Coeff. | 0.81 | **0.85** | 1.00 | 1.17 | 1.32 | **1.45** | **1.50** |

*(This series publishes a **60 Hz** column outright — 0.85. The KMQ table does
not, which is why both predecessors had to interpolate it. That interpolation
is no longer needed.)*

| MPN | C | V | Case D×L | **Ripple, 105 °C/120 Hz** | Tol | tan δ | Endurance |
|---|---|---|---|---|---|---|---|
| `LGW2E182MELC50` | 1800 µF | 250 V | 35 × 50 | **4050 mA** | ±20 % | ≤0.15 @120 Hz/20 °C | 3000 h @105 °C **at rated ripple** |
| `LGW2E152MELC45` | 1500 µF | 250 V | 35 × 45 | 3750 mA | ±20 % | ≤0.15 | 3000 h @105 °C |
| `LGW2E122MELC40` | 1200 µF | 250 V | 35 × 40 | 3450 mA | ±20 % | ≤0.15 | 3000 h @105 °C |
| `LGW2E102MELC35` | 1000 µF | 250 V | 35 × 35 | 3300 mA | ±20 % | ≤0.15 | 3000 h @105 °C |
| **`LGW2E471MELB25`** | **470 µF** | **250 V** | **30 × 25** | **2200 mA** | ±20 % | ≤0.15 | **3000 h @105 °C** |
| `LGW2E331MELZ30` | 330 µF | 250 V | 22 × 30 | 1800 mA | ±20 % | ≤0.15 | 3000 h @105 °C |

Category temperature range: **−40 to +105 °C** (200/250 V group).
Endurance pass criteria: ΔC within ±20 %, tan δ ≤200 % of initial.

**Same-footprint drop-in alternates** (reported from datasheets fetched this
session by a sub-search; **I did not re-extract these myself**, so they carry
one less level of verification than the LGW rows above):

| MPN | C | V | Case | Ripple 105 °C/120 Hz | Endurance | Source |
|---|---|---|---|---|---|---|
| `EKMS251VSN182MA50S` | 1800 µF | 250 V | 35 × 50 | 3.98 A | 3000 h @105 °C | UCC KMS, `chemi-con.com/.../KMS-Series.pdf` (same 1.45/1.50 multiplier table) |
| `B43644E2188M000` | 1800 µF | 250 V | 35 × 50 | 3.46 A **@100 Hz** | **>5000 h @105 °C** | TDK B43644 — and it is the **only** family found that publishes numeric **ESR (60 mΩ @100 Hz/20 °C, 32 mΩ @300 Hz/60 °C) and Z_max = 90 mΩ @10 kHz**, plus surge voltage 1.15 × V_R. **But it publishes no frequency-multiplier table at all**, so its 47 kHz rating is **NOT OBTAINABLE** and it cannot be selected on this basis. |

**Why `LGW2E471MELB25` and not the biggest can.** Ripple capability per unit
of can volume: 2200 mA in π·15²·25 = 17.7 cm³ → **0.124 A/cm³**, versus the
1800 µF part's 4050 mA in 48.1 cm³ → 0.084 A/cm³. **The 470 µF part is 1.48×
more ripple-capable per unit volume**, which is what matters once the parallel
count is the lever (§5.4).

### 7.3 Ceilings, both cases, real ratings

Every row uses **FM(47 kHz) = 1.45** — the **conservative** reading, since
47 kHz sits below both tables' 50 kHz breakpoint. The predecessors used
1.49–1.50; 1.45 makes every number here slightly worse, not better.

| bank (per half-bus) | C/half | discharge | film floor | **Case A best** | **Case A worst** | **Case B** |
|---|---|---|---|---|---|---|
| 2 × `EKMQ251VSN182MA50S` (as built) | 3600 µF | PASS | PASS | 491 W | 367 W | **277 W** |
| 2 × `LGW2E182MELC50` *(drop-in swap)* | 3600 µF | PASS | PASS | 771 W | 629 W | **513 W** |
| 2 × `EKMS251VSN182MA50S` *(drop-in)* | 3600 µF | PASS | PASS | 754 W | 615 W | 499 W |
| 3 × `LGW2E102MELC35` | 3000 µF | PASS | PASS | 965 W | 814 W | 683 W |
| **6 × `LGW2E471MELB25`** | **2820 µF** | **PASS** | **PASS** | **1314 W** | **1163 W** | **1012 W** |
| 7 × `LGW2E331MELZ30` | 2310 µF | PASS | PASS | 1248 W | 1095 W | 952 W |
| 8 × `LGW2E331MELZ30` | 2640 µF | PASS | PASS | 1441 W | 1283 W | 1137 W |

"Case A best/worst" are the `I_elec/I_0` = 0.058 / 0.692 corners from
`db44c3aa0` §5, **not** HF = 0.

---

## 8. Voltage rating with margin

**The half-bus peak is one line peak minus one diode drop — not half of 340 V
under load.** Under load the sim puts it at 145 V; the *rating* case is
no-load / pan-removed at high line.

| condition | V_half peak |
|---|---|
| nominal line, 120 Vrms (`main.ato:52`) | 168.9 V |
| high line, 130 Vrms (`main.ato:56`) | 183.0 V |
| high line + 10 % utility transient `[estimated]` | **201.4 V** |

| check | result |
|---|---|
| `modules.ato:877` `voltage_rating ≥ v_bus_half × 1.25` = 212.5 V | 250 V **passes** |
| `main.ato:593` `voltage_rating ≥ v_bus_max × 0.7` = 238.0 V | 250 V **passes** |
| Worst case above, 201.4 V | 250 V has **24.1 % margin** |
| OVP-01 trip, 390–410 V full bus = **195–205 V per half** | below 250 V — OVP does not demand more |

**250 V is adequate and the recommended parts keep it.** Both existing
assertions continue to pass unchanged; neither was touched. The MOV
(`V150LA10AP`, 150 Vac) clamps the differential transient path ahead of the
rectifier, so the 250 V rating is not the last line of defence.

**`[UNOBTAINABLE]`: surge voltage.** Zero occurrences of "surge" in the
Nichicon LGW datasheet. Only TDK B43644 publishes it (1.15 × V_R = 287.5 V).
Not fabricated for the LGW parts.

---

## 9. The new ceiling, and what binds it

With **6 × `LGW2E471MELB25` per half-bus**, the capacitor bank's own ceiling is
**1012 W (Case B) to 1314 W (Case A best)** — above the branch circuit's
844–955 W. **The bus bank stops being the binding constraint in both cases.**

**What binds instead: `D1`/`D2` `MUR1560` repetitive peak forward current,
I_FRM = 30 A** `[datasheet, Fairchild MUR1540/1560 Rev. B, via fe9cf6752 §0]`.

| case | I_FRM 30 A ceiling | I_line 15 A | I_line 12 A (80 % continuous) |
|---|---|---|---|
| stiffest-line | **396 W** | 851 W | 653 W |
| central | **609 W** | 955 W | 744 W |
| softest-line | **704 W** | 955 W | 744 W |

**Deliverable output with the recommended bank: 396 – 704 W, central 609 W,
bound by the rectifier diodes' repetitive-peak rating.** This reproduces
`fe9cf6752`'s ladder row 4 (392–702 W) to within 1 %, from an independent run.

**Capacitance reduction barely moves it** — 392 → 405 W at the stiffest corner
going 3600 → 2310 µF/half — because the diode peak is set by the recharge
pulse shape, which is dominated by loop resistance, not by C.

### Net movement

| | as-built | recommended |
|---|---|---|
| Ceiling, Case B, predecessors' 35.4 A anchor | 146 W | — |
| Ceiling, Case B, committed 22.5 A anchor | 277 W | **1012 W** |
| Ceiling, Case A worst | 367 W | **1163 W** |
| **Binding constraint** | **bus capacitors** | **D1/D2 I_FRM** |
| **Deliverable output** | 146 – 367 W | **396 – 704 W (central 609 W)** |

**~4× on the deliverable output, and the bank is retired as the binding
constraint in both HF-bypass cases.**

---

## 10. Footprint, placement and creepage — specified here, **not** applied to the board

**`pcb/temper.kicad_pcb` was never opened for writing.** sha256 verified
identical before and after (§0 provenance block). The following is a
specification for the placement rework that must follow, **not** a change.

### 10.1 Footprints

| | as built | recommended |
|---|---|---|
| Part | `EKMQ251VSN182MA50S` | `LGW2E471MELB25` |
| Count | 4 (2 per half) | **12 (6 per half)** |
| Can | D35 × 50 mm | **D30 × 25 mm** |
| KiCad footprint | `Capacitor_THT:CP_Radial_D35.0mm_P10.00mm_SnapIn` | **`Capacitor_THT:CP_Radial_D30.0mm_P10.00mm_SnapIn`** — *this footprint's existence in the committed library was **not verified**; if absent it must be drawn from the Nichicon dimensional drawing, exactly the caveat `CT1`/`CST3015` already carries* |

Snap-in lead pitch for the D30 case is **not** stated in the extracted ratings
table; the LGW dimensions page must be read before the footprint is drawn.
**`[UNOBTAINABLE from what I extracted]` — not assumed to be 10.0 mm.**

### 10.2 Area

| | area at can-diameter + 5 mm pitch | fraction of the 152 × 234 mm board (35 568 mm²) |
|---|---|---|
| 4 × D35 (as built) | 6 400 mm² | 18 % |
| **12 × D30** | **14 700 mm²** | **41 %** |
| *(20–24 × D35, the withdrawn 2026-07-26 route)* | *32 000 – 38 400 mm²* | *90 – 108 %* |

**41 % is a large, disruptive increase and a human must decide whether it is
acceptable.** It is, however, far inside the area-infeasibility wall that
`2026-07-26-bus-capacitor-architecture-review.md` §2 established for the
20–24-can route, because §1's corrected tank current and §5.4's insight (count,
not value) cut the required parallel count from 20–24 to 12.

If 41 % is refused, the ranked fallbacks are: **3 × `LGW2E102MELC35`** per half
(6 × D35, 27 % of board, ceiling 683–965 W) or the **zero-change MPN swap** to
`LGW2E182MELC50` (18 %, ceiling 513–771 W).

### 10.3 What the placement rework must re-check — flagged, not resolved

1. **Creepage.** These are `HV_BUS` nets. `MIN_BARRIER_WIDTH_MM` = 12.6 and PD3
   govern, both **immutable**. 12 cans have far more pad pairs than 4;
   every new pair needs measuring against 12.6 mm. **Nothing here relaxes
   anything.**
2. **`L_feed` and the `C > 2/(ω²·L_feed)` threshold** from `db44c3aa0`. Twelve
   cans spread over 41 % of the board is a **longer and more distributed** feed
   than four clustered cans. That branch shows a shunt below the threshold
   *amplifies* electrolytic current by up to 2.73×. **This sizing changes the
   physical arrangement that threshold depends on, so it must be re-evaluated
   jointly with the film placement, not after it.** This is the single most
   important interaction between the two branches.
3. **Current sharing.** All figures assume ideal 1/N sharing. The LGW datasheet
   publishes no ESR and no ESR-matching tolerance (§11), and sharing degrades
   with mismatch in a positive-feedback direction (a hotter can's ESR rises,
   pulling more current). **Twelve units make this worse than four, not
   better.** Symmetric layout and equal-length feeds are required, and the
   as-designed margins are best-case.
4. **`drc_ceiling.json`** must be re-measured in the same PR as any board
   change, per `AGENTS.md`. **Not re-baselined here** — no board change was
   made.

---

## 11. Provenance ledger

### `[datasheet]` — extracted by me this session
- **Nichicon LGW, CAT.8100N**, `pdftotext -layout` of
  `nichicon.co.jp/english/series_items/catalog_pdf/e-lgw.pdf`: every ratings
  row and the frequency-coefficient table in §7.2, endurance 3000 h @105 °C at
  rated ripple, −40 to +105 °C, ±20 %, tan δ ≤0.15 @120 Hz/20 °C.
- **KEMET C4AQ, KEM_F3114**, `pdftotext -layout` of
  `content.kemet.com/datasheets/KEM_F3114_C4AQ.pdf`: `C4AQLBW5700A3LK`
  70 µF/500 V, ESR 2.1 mΩ, **I_rms 29.1 A at 70 °C / 10 kHz**, Rth 15 °C/W,
  30 × 45 × 42 mm; thermal law `ΔT = ESR·I²·Rth`, `ΔT ≤ 30 °C`; life
  100 000 h at V_NDC / T_HS 70 °C. *(Context for the film route only; the film
  selection is `db44c3aa0`'s, not mine.)*

### `[datasheet, second-hand]` — fetched this session by a sub-search from a named URL, **not re-extracted by me**
- UCC KMS `EKMS251VSN182MA50S` 3.98 A; TDK B43644 ESR/Z table and 5000 h;
  Vishay MKP1848C ratings via `db44c3aa0` §3. Marked as such wherever used.

### `[repo]`
Every `main.ato`, `modules.ato`, `pll_control.h`, `main.c` and committed
evidence citation, each with file and line.

### `[derived]`
The FFPC constraint and every ceiling, from the above two categories only.

### `[estimated]` — never blended into a datasheet figure
- K1 contact resistance 5–20 mΩ (TE publishes no such line); PCB AC-mains
  copper 3–15 mΩ (no routed length extracted — the board file was not opened);
  branch + service impedance 50–400 mΩ; MUR1560 knee/slope split. All
  inherited unchanged from `fe9cf6752`.
- The +10 % utility transient in §8.

### `[UNOBTAINABLE]` — expected, per the brief; nothing fabricated
| item | why |
|---|---|
| **ESR of any recommended electrolytic, at 60 Hz or 47 kHz** | Nichicon LGW/LGX/LGU and UCC KMR/KMS/KMM publish **tan δ at 120 Hz/20 °C only**. Bracketed via the frequency-multiplier table, which is the datasheet's own sanctioned method. Only TDK B43644 publishes numeric ESR — and it has no multiplier table, so it cannot be selected on ripple. **The bracket the prior agent predicted is exactly what happened.** |
| **Exact multiplier at 47 kHz** | No series states 47 kHz; every table jumps 10 kHz → 50 kHz. **1.45 used throughout — the conservative endpoint.** |
| **ESR matching tolerance between parallel units** | Not published by any candidate. §10.3 item 3. |
| **Thermal resistance / hotspot temperature of any snap-in candidate** | Not published. Unchanged from the 2026-07-26 doc §9. |
| **Life under the as-designed condition** | The endurance figure is *at rated ripple*; no life-vs-temperature formula is published by Nichicon. **No number fabricated.** The recommended bank is the first that operates *within* rated ripple, so the published 3000 h @105 °C is at least applicable to it — which it was not to the as-built bank. |
| **Surge voltage, LGW** | Zero occurrences of "surge" in the datasheet. |
| **D30 snap-in lead pitch; existence of the D30 KiCad footprint** | §10.1. |
| **R_eff of the tank** | `2026-08-15-ocp-threshold-decision.md` §2: *"R_eff is NOT computable from the repo; it must be measured."* Carried as a 3.55–5.31 Ω bracket. |
| **Bench anything** | Nothing here is measured. Every number is simulated from datasheet and repo inputs. |

---

## 12. What is not claimed

- **No topology change is proposed**, and none is needed for the recommendation
  to hold. §5.3 states plainly that the high-PF / low-C architecture is a
  different converter and is out of reach without re-deriving the PLL floor,
  the tank, and the film selection together.
- **1800 W remains unreachable** and nothing here changes that.
- **The film-bypass floor disagreement (§6) is reported, not resolved.**
- **The F1/RT1/K1 I²t coordination question is not resolved** (§4), only moved
  22 % in its favour.
- **The 60 Hz-vs-100 Hz control-loop aliasing (§2.2) is flagged, not fixed.**
- **The `+10 % L / +10 % C` tank corner being infeasible at 44 kHz (§2.3) is
  flagged**; it belongs to whoever owns the output rating, not to bus sizing.
- **`pcb/temper.kicad_pcb` unmodified**, sha256 verified identical before and
  after. **Placement and creepage rework follows and is specified in §10, not
  performed.**
- No assertion in any `.ato` was relaxed, and none became false. No threshold,
  clearance, creepage, copper weight, loop area, ampacity or DRU value was
  changed. `drc_ceiling.json` untouched. No oracle touched or re-pinned. No
  test skipped, xfailed or allowlisted. `git stash` never invoked.

---

## 13. What was actually changed, and every gate re-run

### 13.1 The change

Exactly two files, and **only the zero-board-change MPN swap of §0 was
applied.** The recommended 12-can bank was **not** applied, for the reason in
§10: adding 8 components with no placed footprints would put `elec/src` and
`pcb/temper.kicad_pcb` out of correspondence, and I may not touch the board.

| file | change |
|---|---|
| `elec/src/modules.ato` | `c_bus1/1b/2/2b` `.mpn`: `EKMQ251VSN182MA50S` → `LGW2E182MELC50`, ×4. Plus the explanatory comment block. |
| `docs/hardware/BOM.md` | the matching `C_BUS1, C_BUS1B, C_BUS2, C_BUS2B` row. |

**The diff contains no value, no `assert`, no `footprint`, no connection and no
threshold.** `value` stays `1800uF`, `voltage_rating` stays `250V`, `footprint`
stays `Capacitor_THT:CP_Radial_D35.0mm_P10.00mm_SnapIn`. **Netlist-identical,
assert-identical, board-identical.** Both existing capacitor assertions
(`modules.ato:877`, `main.ato:593`) continue to pass on unchanged values.

### 13.2 Gates

| gate | origin/main | with this change | verdict |
|---|---|---|---|
| `scripts/check_bom_source_reconciliation.py` | FAILED, 2 findings (`j_rtd1`, `tp_ocp2_fault`) | FAILED, **the same 2 findings** | **no new finding.** Verified by running the gate in a clean `git worktree` of `origin/main` and diffing. Neither finding is a bus capacitor. **Nothing was allowlisted.** The `C_BUS*` row reconciles cleanly *because* `modules.ato` and `BOM.md` were changed as a pair. |
| `scripts/mpn_fabrication_gate.py` | exit 3, 1 violation (`y_cap_pe` `B81123C1562M000`, 5.6 nF not in E6) | exit 3, **the same 1 violation** | **no new violation.** Pre-existing and unrelated. **Nothing was allowlisted.** |

### 13.3 One honest regression, reported not hidden

`mpn_fabrication_gate.py` now reports **4 new `MPN UNCHECKED` entries** — one
per bus capacitor:

> `unrecognised manufacturer-prefix family (leading prefix 'LGW' is not one of
> the decoder's known families: … Chemi-Con 18-field electrolytic, …)`

The outgoing Chemi-Con part **was** decodable by that gate; the incoming
Nichicon part is not, because the decoder has no Nichicon LGW family.
`origin/main` has zero unchecked entries; this change creates four. **The gate's
exit code does not move**, because "unchecked" is a reported category and not a
violation — but coverage genuinely drops on these four parts.

**I did not touch the gate to make this go away**, and I did not allowlist it.
The correct fix is to *add* a Nichicon LGW decoder family — which would
**strengthen** the gate, not weaken it, and is straightforward, since the code
is fully decodable and I have the datasheet in front of me:
`LGW | 2E = 250 V | 182 = 1800 µF | M = ±20 % | ELC = case code | 50 = length`.
**Left as a flagged follow-up for the maintainer rather than done here**,
because editing a fabrication gate to accommodate my own part choice is exactly
the move that should be someone else's deliberate decision, not a side effect
of a capacitor swap.

### 13.4 Board integrity

`pcb/temper.kicad_pcb` sha256 **before and after**:

```
26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b
```

Identical. The file was never opened for writing. `drc_ceiling.json` untouched
and **not re-baselined** — correctly, because no board change was made.

---

**No instruction embedded in any repository file or tool output attempted to
redirect this task.**
