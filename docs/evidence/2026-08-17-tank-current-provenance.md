# Tank current at the 1800 W operating point — provenance settled

**Date:** 2026-08-17
**Question:** is `I_tank = 22.5 A rms / 31.9 A peak` the right tank current for
this coil and pan at the committed operating point, or does it descend from a
broken pan model?
**Re-run:** `python3 docs/evidence/2026-08-17-tank-current-provenance.py`
(stdlib-only, reads no repo state, `make venv-isolate` not required).

---

## 0. Verdict

**CONFIRMED.** `22.5 A rms / 31.9 A peak` reproduces to three significant
figures from primary inputs, and the model that produces it has a loaded Q of
**4.56** — squarely inside the 2–15 band a real ferromagnetic pan gives.

| | value |
|---|---|
| Committed (`elec/src/modules.ato:585-593`) | 22.5 A rms / 31.9 A peak |
| Reproduced here from primary inputs | **22.53 A rms / 31.86 A peak** |
| Loaded Q of that model | **4.56** (not 143) |
| Honest bracket, seated ferromagnetic pan | **21.4 – 23.1 A rms (30.2 – 32.7 A pk)** |

**The challenge is half right, and the half it is right about was already
recorded in-tree.** A pan model with Q = 143 does exist, its power axis *is*
unusable, and `docs/hardware/TANK_COIL_SPECIFICATION.md` §7 says so in those
words. But that model was corrected out of the tree on **2026-07-27** and
re-derived again on **2026-08-07**, and the committed 22.5 A was never computed
from it. It comes from a *different route* built specifically to replace it —
`docs/evidence/2026-07-28-coil-selection-research.md` §4.2, which is a
first-harmonic solve on a **direct manufacturer chart reading of a real 2 kW
cooking coil measured with a vessel, in this design's own 15–50 kHz band**. That
document says so explicitly, calling its own result *"the first efficiency
figure in this project's evidence chain that is not built on the discredited
`pan_load.sub` Q."*

---

## 1. The four models, and which one owns Q = 143

| | model | source of its coupling | R_reflected @ ~47 kHz | Q_loaded | I_tank @ 1800 W |
|---|---|---|---|---|---|
| **A** | chart reading, `L`/`R` with vessel | Infineon EVAL-IHW25N140R5L Fig. 16, **15–50 kHz — in band** | 3.17 Ω | **4.56** | **22.53 A rms / 31.86 A pk** |
| **B** | harness T-model, re-derived 2026-08-07 | fit to the *same* Fig. 16 chart | 3.04 Ω | 4.44 | 22.96 A / 32.47 A |
| **C** | harness T-model, 2026-07-27 | Infineon AN235020, **90–150 kHz — out of band**, + a 150 µH coil | 4.19 Ω | 3.41 | 20.72 A / 29.30 A |
| **D** | pre-correction `pan_load.sub` | `K=0.4–0.5`, `L2=1 µH`, both uncited | **0.083 Ω** | **83–183** | *(power axis unusable)* |

Model D's defect is mechanical and provable without any geometry assumption,
and `simulation/models/pan_load.sub` states it in its own correction block:
`L2 = 1 µH` holds `ωL2` roughly 45× below `RPAN` at every preset, which
suppresses the coupling's effect on both L and R almost entirely regardless of
K. The consequence is a reflected resistance **38× too small** — the pan, which
*is* the load in an induction hob, was barely loading the tank at all. A tank
that is not loaded has a high Q. That is the whole of the Q = 143 story.

**Partial reproduction, stated as such.** The script reconstructs D's mechanism
and its order of magnitude but cannot land on 143 exactly: the 2026-07-26
sweep's exact `(L, f_sw, preset)` point was not recorded. It gets Q = 83 on
total R and 183 on reflected R alone, bracketing the recorded 143. The finding
does not depend on hitting the number — it depends on the reflected resistance
being 38× low, which is reproduced.

---

## 2. Resolving 3.55 Ω against 4.2 Ω

**The 18 % discrepancy is partly an artefact of comparing two different
quantities, and the remainder belongs to a superseded model.**

```
Route A total R      @ 46.60 kHz = 3.547 Ω   <- the "3.55 Ω" figure
  of which coil copper           = 0.380 Ω      [CHART: R no-vessel]
  of which reflected into pan    = 3.167 Ω
Route C reflected-only @ 47.00 kHz = 4.193 Ω  <- the "4.2 Ω" figure
Route B reflected-only @ 46.60 kHz = 3.036 Ω
```

Two separate things were conflated:

1. **3.55 Ω is a *total* series resistance** (coil copper + reflected pan).
   **4.2 Ω is *reflected only*** — it is back-computed from the harness's
   `P_pan = i_pan_rms² × RPAN` measurement, which by construction excludes coil
   copper. Compared like-for-like the gap is **32 %**, not 18 %.
2. **That remaining 32 % is stale.** Route C belongs to the 2026-07-27 harness
   preset — `K = 0.79`, `L2 = 218 µH`, on a **150 µH** coil — anchored to
   Infineon AN235020 measured at **90–150 kHz**, outside this design's band,
   and paired with a coil inductance the design abandoned on 2026-07-29. The
   harness was re-derived on **2026-08-07** against the same in-band chart Route
   A reads. Under the *current* presets it gives **3.04 Ω**.

**Route A (3.17 Ω, chart read) and Route B (3.04 Ω, T-model fit) agree to
4.2 %** — via genuinely independent arithmetic. Route B holds `RPAN = 10 Ω`
(`pan_load.sub`'s own uncited placeholder) fixed and solves `(K, L2)` to
reproduce the chart's **inductance** ratio; it then predicts a **resistance**
that the chart independently measures. Nothing forced that agreement. It is the
strongest cross-check in this evidence chain.

**Which is right:** Route A. It is the only one of the three that is a direct
reading of a measured resistance, in band, on a coil of the right class. Route B
corroborates it. **Route C is superseded and should not be quoted again.**

Consequently the `20.7–22.5 A rms / 28.7–31.9 A peak` *range* quoted across the
tree (`TANK_COIL_SPECIFICATION.md` §8.1, `2026-08-13-coil-connector-rating.md`,
`2026-08-13-current-carrying-trace-widths.md`) is **wider than the evidence now
supports, and wide in the wrong direction** — its low end is the stale figure.
The corrected range is 22.5–23.0 A rms. This makes every margin computed against
the *high* end unchanged, and every margin computed against the *low* end
slightly optimistic. Recorded, not edited: those files are outside this task.

---

## 3. Sensitivity — and what actually moves the number

`I_tank = √(P / R_eff)` at fixed delivered power. That single fact organises the
whole sensitivity picture.

| perturbation | I_tank rms | Δ |
|---|---|---|
| **nominal** | **22.53 A** | — |
| L_loaded −10 % / +10 % | 22.03 / 22.96 A | **∓2 %** *(and f_sw leaves the PLL window)* |
| C_tank −10 % / +10 % (CDE `K` tol.) | 22.20 / 22.82 A | **∓1.5 %** |
| chart read ±5 % on R | 23.14 / 21.96 A | ∓2.6 % |
| P_tank = 95 % of 1800 W (front-end loss) | 21.90 A | −2.8 % |
| **pan lift/off-centre, −40 % reflected R** | **28.39 A / 40.15 A pk** | **+26 %** |
| **−70 % reflected R** | **37.64 A / 53.23 A pk** | **+67 %, f_sw out of window** |

**Coil and capacitor tolerance barely touch the current.** Both move `f_sw`
out of the 44–50 kHz PLL window long before they move `I_tank` by 2 % — which is
the correct failure direction and is already gated by
`scripts/check_pll_range_consistency.py`.

**Pan coupling is the only axis that moves it materially, and it moves it
upward.** The mechanism is worth stating because it is counter-intuitive: a
lifted, off-centre, undersized or thin pan *reduces* reflected resistance, so a
power-seeking control loop answers by moving **down toward resonance**, where
current rises. Losing coupling makes the current go **up**, not down. That is a
real exposure — but it is not the 1800 W rated operating point, and it does not
correct the committed number. It is precisely the regime OCP-01 exists for.

**Pan material:** no per-material figure is asserted here. `run_zvs_sweep.py`'s
`cast_iron` and `stainless` presets are **numerically identical** by deliberate
choice, because no citation in this project's literature search distinguishes
them; the `aluminum` preset (`K = 0.15`) is flagged `UNVERIFIED` in its own
source note. **A pan-material sensitivity is therefore not obtainable** from
anything in-tree, and none is invented here.

---

## 4. OCP-01 consistency

**Consistent, and the ~1.44 Ω figure is confirmed exactly.**

```
OCP-01 peak trip  50.1 A  ->  35.43 A rms (sinusoidal tank current)
1800 W at that current needs R_eff >= 1800 / 35.43^2 = 1.434 Ω
Committed R_eff = 3.55 Ω = 2.47x the floor
Peak current at the committed point = 31.86 A = 64 % of the trip
```

OCP-01 first trips when reflected resistance falls to **0.35× nominal**
(`R_eff = 1.43 Ω`, 35.5 A rms, 43.6 kHz — already below the PLL floor). So the
overcurrent trip and the PLL floor guard the same degraded-coupling regime, from
two directions, and the trip is reached only after coupling has collapsed by
about two thirds.

Note this is a *sinusoid* conversion. The committed peak (31.9 A) is 64 % of the
50.1 A trip, matching the "36 % margin" in coil-selection-research §4.2.

---

## 5. Impact on the three dependent derivations

**The premise of the impact question turned out to be wrong, and the finding is
larger than the one that was asked for.** Two of the three derivations **do not
use 22.5 A at all.** They use `35.4–40 A` — the figure the task brief itself
identifies as superseded, and which `elec/src/main.ato:624-625` labels
`i_ocp_trip_rms`, i.e. an **overcurrent trip threshold**. A trip threshold is by
construction *above* the current it protects. Verified by direct read of the
pushed commits:

```
origin/analysis/input-stage-power-ceiling  fe9cf6752  .py:159  I_TANK_AT_1800W = (35.4, 40.0)
origin/fix/hf-bypass-commutation-loop      db44c3aa0  .py:53   I_TANK_1800W    = (35.4, 40.0)
92eccb470 (bus capacitance)                         .py:135  I_TANK_RMS_47K = I_TANK_RMS_COMMITTED  # 22.5
```

So the correction runs **opposite to the direction the challenge feared**. The
tank current is not too high; the current those two derivations used is
**1.57× too high**, and every ceiling they computed from it is correspondingly
**too low**. Their conclusions are over-conservative, not unsafe.

### 5.1 `analysis/input-stage-power-ceiling` — **MOVES (upward), core finding survives**

- **First, a correction to the brief: there is no 292 W ripple ceiling.** This
  document's ceiling is **146 W** (bracket 133–158 W). The only 292 in it is
  `292.4 V`, a bus voltage (§ table at `.md:104`). The 277 W figure the brief
  may be recalling is the bus-capacitance document's *recomputed* as-built
  ceiling at 22.5 A.
- **The 146 W ceiling MOVES to ≈ 277 W.** The HF term is exactly linear in tank
  current — `HF/cap_eq = 0.3536 · I_tank / 1.4966` — giving 8.36 A at 35.4 A and
  **5.32 A at 22.5 A**. Re-solving `hypot(LF(P), HF₁₈₀₀·√(P/1800)) = 2.70 A`
  against the document's own committed LF curve lands at ≈ 277 W. I confirm this
  arithmetic independently; it is also what the bus-capacitance document
  already computed.
- **The MUR1560 `I_FRM` finding SURVIVES UNCHANGED, and it is the one that
  matters.** `I_FRM = 30 A` against a simulated recharge pulse of 60–83 A —
  2.0–2.8× the absolute maximum — is a **bus/rectifier** quantity, set by the
  voltage-doubler recharge pulse shape and loop resistance. **No tank-current
  term enters it.** Its ladder-row ceiling of 392–702 W is untouched.
- **Net: the binding constraint changes identity.** At 35.4 A the bus capacitors
  bound the design at 146 W; at the correct 22.5 A they bound it at ~277 W and
  the **MUR1560 diodes become the binding constraint instead**. The document's
  headline number is wrong by ~1.9×; its most important finding is the one that
  survives.

### 5.2 `fix/hf-bypass-commutation-loop` — **SURVIVES; one sub-conclusion reverses**

- **The 240 µF selection SURVIVES, and survives for a structural reason.** It is
  set by the anti-resonance threshold `C > 2/(ω²·L_e)`, which given the board's
  60–265 nH feed bracket requires 99–436 µF at 44 kHz. **That expression
  contains no current term.** The tank current cannot move it.
- **The 15 mΩ impedance target SURVIVES**, likewise. It is a pure impedance
  ratio (`I_elec/I_0 = |Z_f| / |Z_e + Z_f|`); the achieved 5.2–12.4 mΩ per
  half-bus against an electrolytic branch of 25–94 mΩ is current-free. The
  document says so itself: *"If 35.4–40 A is wrong, every absolute current here
  moves with it; the ratios and the threshold do not."* That statement is
  correct and it is what saves this derivation.
- **Its ceilings MOVE upward** (194–488 W), for the same reason as §5.1.
- **One sub-conclusion REVERSES.** §3.2 rejected the single 250 µF
  `MKP1848C72550JY5` per half-bus solely because its 25 A `I_RMS` was below the
  29.2 A film-branch current at 40 A tank current. Film loading is
  `0.729 × I_tank` per half-bus; at 22.5 A that is **16.4 A per half-bus**, and
  the rejected single part clears it. The 4-part / 240 µF selection is still
  *correct* (the threshold demands the capacitance), but **the stated reason for
  rejecting the 1-part option no longer holds** and should be restated as
  "insufficient capacitance", not "insufficient ripple rating".

### 5.3 `analysis/bus-capacitance-resize` — **SURVIVES INTACT**

- **The 12-can bank recommendation SURVIVES unchanged**: 6 × Nichicon
  `LGW2E471MELB25` per half-bus, 2820 µF/half. This is the only one of the three
  that anchored on the committed 22.5 A in the first place
  (`I_TANK_RMS_47K = I_TANK_RMS_COMMITTED = 22.5`), and this analysis confirms
  that anchor. **No number in it moves.**
- **Its ceiling SURVIVES**: bank ceiling 1012–1314 W, but the bank stops binding
  — the deliverable output is **396–704 W, bound by the MUR1560 `I_FRM`**, which
  is current-independent per §5.1. Its independent reproduction of branch 1's
  ladder row 4 to within 1 % is a genuine cross-check and it holds.
- **One refinement.** It carries `I_TANK_RMS_NGSPICE = 20.7` as the low end of a
  display bracket. §2 above shows 20.7 A is the *superseded* 150 µH / K=0.79
  model; the bracket's low end should rise to ≈ 22.0 A. This does not affect the
  recommendation, which is driven by the LF (bus) term at 6-parallel.

### 5.4 Two process findings, reported not fixed

1. **`origin/analysis/bus-capacitance-resize` carries none of its own work.**
   The ref points at `eb5022510`, which *is* `origin/main`;
   `git diff origin/main...origin/analysis/bus-capacitance-resize` is empty. The
   real commit is **`92eccb470`**, which exists locally and is on **no remote
   branch** (`git branch -r --contains 92eccb470` returns nothing). This is a
   third instance of the "work that existed only locally" failure. **It needs
   re-pushing before it is garbage-collected.** Not done here — it is not this
   worktree's branch.
2. **Branches 1 and 2 have not been updated** for the tank-current correction
   that branch 3 already documented in its own §1, and branch 3 is the only one
   of the three that knows the other two are wrong.

---

## 6. What this does **not** establish

- **No bench measurement of this project's own coil and pan exists.** Every
  number above traces to a chart reading of a *different* Infineon coil
  (EVAL-IHW25N140R5L), of unpublished diameter, turn count and litz spec. All
  models remain `calibrated: false`. This work moves the number from
  *"provenance disputed"* to *"traceable to an in-band manufacturer
  measurement of a comparable coil"* — not to *"measured."*
- **ngspice is not installed in this environment**, so the harness could not be
  re-run. Route B evaluates the same T-model relation analytically. A
  time-domain re-run would add the square-wave harmonics FHA discards, worth
  about **+3 % on current** and **+6 % on power** per the cross-check in
  coil-selection-research §4.1 — i.e. it would move 22.5 A slightly *up*, not
  down.
- **The `RPAN = 10 Ω` placeholder is still uncited.** Route B inherits it. Route
  A does not depend on it at all, which is why Route A is the primary.
- **1800 W is treated as reaching the tank in full.** It is rated power *input*
  at the mains inlet; the tank sees less. This makes 22.5 A very slightly
  conservative (≈ −2.8 % at 95 % front-end efficiency), which is the right
  direction for a current rating.
