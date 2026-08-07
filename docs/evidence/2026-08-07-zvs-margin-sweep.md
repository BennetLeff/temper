# ZVS margin sweep across the pan-load envelope, at the now-declared 88 µH coil

<!-- provenance: commit=ade39cd7b4691349940b3ea24e7c7fcc411b7cce dirty=false -->

**Date:** 2026-08-07
**Base commit:** `ade39cd7` (this worktree's own commit, `feat(simulation):
update ZVS-sweep harness for the declared 88uH coil and re-derived in-band
pan coupling` — the harness/`.cir` changes landed first, evidence in a
second pass against the clean tree).
**Scope touched:** `simulation/harness/run_zvs_sweep.py`,
`simulation/harness/nets/zvs_margin_sweep.cir`,
`docs/evidence/2026-08-07-zvs-margin-sweep.{json,md}` (this file). **No
`elec/`, `pcb/`, or firmware changes** — findings and recommendations only,
per instruction; changing tank component values is a design decision this
pass does not make.
**Method:** `uv run python simulation/harness/run_zvs_sweep.py
--determinism-runs 3`, ngspice-42 (Ubuntu noble, KLU direct solver,
installed locally into a scratch prefix for this session — not on the
worktree's normal `PATH`). Full run: 132 grid points (4 pan presets × 33
frequencies), all 132 converged, determinism-checked on the baseline and
worst-margin decks (3 runs each, `.meas` values byte-for-byte identical
across all repeats — see `simulator.deterministic` in the JSON). Raw
result: `docs/evidence/2026-08-07-zvs-margin-sweep.json`.

---

## 0. Answers to the four things asked for, up front

1. **Is the coil specified as a real inductor on `main` today? Yes.**
   `elec/src/modules.ato`'s `ResonantTank.inductor_conn` is `new Inductor`,
   `value = 88uH +/-10%`, `current_rating = 25A`, `dcr = 0.1ohm` — not the
   valueless `new Resistor` placeholder `docs/STRATEGY.md`'s 2026-07-26
   entry describes. Commit `852e9fa8` (per the brief) did this; it is
   still true on this session's base tree, and `main.ato`'s
   `l_tank_assumed = 88uH` mirrors it under a machine-checked gate
   (`scripts/check_pll_range_consistency.py` check 7, verified present and
   passing in this tree — see §1).
2. **Is a meaningful sweep possible despite the pan-coupling defect?
   Conditionally yes, with the coupling re-derived first.** The
   `docs/STRATEGY.md` 2026-07-27 defect ("coupling provably too low, the
   geometry can't rescue it") was already fixed once, 2026-07-27, to
   K=0.79/L2=218 µH — but that fix was anchored to a measurement **outside
   this design's operating band** (Infineon AN235020, 90–150 kHz vs. this
   design's 20–50 kHz), and `main.ato` itself, updated two days later,
   silently diverged from it (`l_pan_loaded_ratio` 0.399 → 0.68, an
   **in-band** chart reading) without the harness following. Running the
   harness unchanged today would have swept a coupling point the design
   source no longer asserts. This pass re-derives K/L2 against the
   in-band figure (§2) before sweeping. The result is **still
   constraint-satisfying, not measured** — see §2's own caveats — but it
   is no longer stale relative to `main.ato`.
3. **Tank parameters, resonance vs. switching:** §3.
4. **Where ZVS is lost, and which gates that endangers:** §5–§6. Short
   answer: **not anywhere inside the firmware's actual 44–50 kHz PLL
   range**, for any of the four pan presets, in this model. It is lost
   well outside that range (≤36 kHz for ferromagnetic pans, ≤31 kHz for
   aluminum/no-pan) — the firmware cannot legally command those
   frequencies. The higher-value finding is in §5.3: the design's own
   "47 kHz delivers ~1804 W" claim, which EFF-02 and the 1800 W operating
   point are built on, **does not hold** under the updated coil/coupling
   pair — this model puts 47 kHz at ~1562 W and 1800 W closer to 46 kHz.
   ZVS still holds at both.

---

## 1. Obstacle 1 — the coil, verified on this tree

```
$ grep -n "inductor_conn = new" elec/src/modules.ato
    inductor_conn = new Inductor
$ grep -n "inductor_conn.value" elec/src/modules.ato
    inductor_conn.value = 88uH +/- 10%
$ grep -n "l_tank_assumed:" elec/src/main.ato
    l_tank_assumed: inductance = 88uH
```

`scripts/check_pll_range_consistency.py` check 7 fails the build if
`modules.ato`'s declared inductance and `main.ato`'s `l_tank_assumed` ever
disagree — this is not two independent numbers that happen to match today.
Full history and the acceptance test built on it:
`docs/evidence/2026-07-29-tank-coil-specification.md`,
`docs/hardware/TANK_COIL_SPECIFICATION.md`. **Caveat, unchanged by this
pass:** 88 µH is a manufacturer chart reading (Infineon
EVAL-IHW25N140R5L Fig. 16) of a *different* coil, not a bench measurement
of this project's own wound coil — the incoming acceptance test exists
precisely because that gap is still open.

---

## 2. Obstacle 2 — the pan-coupling model, re-derived against `main.ato`

### 2.1 What was wrong before this pass

The 2026-07-27 fix (`docs/evidence/2026-07-27-coil-pan-coupling-
resolution.md`) moved `pan_load.sub`'s `PANLOAD_TRANSFORMER` coupling from
a *provably impossible* point (K=0.4, L2=1 µH — could never reproduce any
measured loaded/unloaded ratio, independent of geometry) to a
*constraint-satisfying* one (K=0.79, L2=218 µH), solved against Infineon
AN235020's measured 0.40 ratio at **90–150 kHz**. That fix was carried
into `simulation/harness/run_zvs_sweep.py`'s `PAN_PRESETS` and the `.cir`'s
own committed defaults, and stayed there unchanged.

On 2026-07-29, `elec/src/main.ato` was separately updated
(`docs/evidence/2026-07-29-tank-coil-specification.md`): its
`l_pan_loaded_ratio` moved **0.399 → 0.68**, sourced from a *different*
Infineon chart (EVAL-IHW25N140R5L Fig. 16, a 2 kW cooking coil measured
**with a pan**, across **15–50 kHz** — this design's own band) read at
30/40/50 kHz as **0.71/0.68/0.66**. `main.ato`'s own comment on that line
names the resulting gap explicitly:

> "CONSEQUENCE, RECORDED NOT FIXED: `simulation/harness/run_zvs_sweep.py`
> still runs PAN_PRESETS at K=0.79, so this file and that harness now
> describe pan coupling differently... the harness preset is the one
> anchored to out-of-band data."

Running the un-updated harness today would sweep a coupling point
`main.ato` itself has disowned — a confident-but-superseded number, the
exact failure mode this task exists to avoid.

### 2.2 The re-derivation done for this pass

Using the *same* T-model relation `run_tank_coil_sweep.py` already uses
elsewhere in this repo,

```
L_loaded / L1 = 1 - K^2 * x^2 / (RPAN^2 + x^2),   x = omega * L2
```

solved against **two** of `main.ato`'s three in-band points (30 kHz/0.71,
50 kHz/0.66), holding `RPAN = 10 Ω` fixed at `pan_load.sub`'s own
pre-existing uncited placeholder (not re-solved — that would trade one
underdetermined pair for an equally underdetermined triple):

```
K  = 0.6136
L2 = 97.13 µH
```

Checked against the third point (40 kHz): predicts ratio 0.6776 against
`main.ato`'s declared 0.68 — **0.35% off**, an order of magnitude inside
the 1.05 ZVS-margin threshold the PLL floor itself is derived against.
Applied to the ferromagnetic presets (`cast_iron`, `stainless` — no
evidence anywhere in this project distinguishes the two, both are treated
identically, as before). `aluminum` (K=0.15) and `no_pan` (K=0.01) are
**unchanged** — no new evidence touches them.

### 2.3 What this is, and is not

**Is:** a better chart reading, reconciled with the value the design
source actually declares, using the identical constraint-satisfying
methodology the 2026-07-27 fix already established as this project's
practice for this exact situation.

**Is not:** a measurement of this project's own coil and pan. `K`, `L2`,
and `RPAN` remain a 3-unknown, ≤2-equation underdetermined system;
`docs/evidence/2026-07-27-coil-pan-coupling-resolution.md` §4's bench
protocol (three frequency points — a single-frequency measurement cannot
separate `L2` from `RPAN`) is unchanged advice, not superseded by this
pass. **Do not read "re-derived" as "calibrated."**

---

## 3. Tank parameters and resonance vs. switching frequency

Per instruction, **source values**, not `docs/hardware/BOM.md`:

| Parameter | Value | Source |
|---|---|---|
| Coil, unloaded (`L1`) | **88 µH ±10%** | `modules.ato` `inductor_conn.value`, mirrored by `main.ato` `l_tank_assumed` |
| Tank capacitance | **300 nF total = 3 × 100 nF** (CDE `942C16P1K-F`, `c_tank1`+`c_tank2`+`c_tank3`, all in parallel, ±10%) | `modules.ato:513-531` |
| Loaded/unloaded ratio | **0.68** at 40 kHz (0.71 @ 30 kHz, 0.66 @ 50 kHz) | `main.ato` `l_pan_loaded_ratio` |
| Unloaded resonance | **30 975 Hz** (declared 31 kHz) = `1/(2π√(88µH·300nF))` | `main.ato` `f_resonant_nominal`, this sweep's own `F_RESONANT_COMPUTED_HZ` — now the *same* arithmetic, not two independent guesses |
| Loaded resonance (nominal) | **37 563 Hz** = `1/(2π√(88µH·0.68·300nF))` | `main.ato` comment, re-verified here |
| Loaded resonance (worst-case, −10% L, −10% C) | **41 737 Hz** | `main.ato` `f_pll_tracking_min` derivation |
| Declared switching frequency | **47 kHz** | `main.ato` `f_switching` |
| Firmware PLL tracking range | **44–50 kHz** | `main.ato` `f_pll_tracking_min/max`, `firmware/components/control/pll_control.h` `PLL_MIN_FREQ_HZ`/`PLL_MAX_FREQ_HZ` — cross-checked equal by `scripts/check_pll_range_consistency.py` |

**BOM/source discrepancy, confirmed, not resolved here:**
`docs/hardware/BOM.md:110-111` still lists **2 × 150 nF WIMA
`FKP1T031507G00JSSD`** for `C_TANK1`/`C_TANK2` ("300nF combined"). The
*source* (`elec/src/modules.ato:513-531`) declares **3 × 100 nF CDE
`942C16P1K-F`** (`c_tank1`, `c_tank2`, `c_tank3`) — a part-count and MPN
disagreement, not merely a rounding difference, even though both total
300 nF. This was already flagged by `docs/evidence/2026-07-29-tank-cap-
cde-942c-verification.md` (PR #410 re-sourced the source but not the BOM
line) and by this sweep's own harness comments before this pass started.
**This sweep uses the source value** (3×100 nF CDE, `c_tank_tolerance =
0.10`), per instruction. `docs/hardware/BOM.md` needs a follow-up edit —
not made here, outside this task's file scope.

**Ratio, 47 kHz nominal over loaded resonance:** 47000/37563 = **1.2512**
— essentially unchanged from the figure `main.ato`'s comments already
state, because 88 µH×0.68 and the prior 150 µH×0.399 pair land within
0.01% of each other on `L_loaded` (the "matched pair" property
`docs/evidence/2026-07-29-tank-coil-specification.md` §3 already proved).
**What is NOT unchanged is delivered power at that ratio — see §5.3.**

---

## 4. Sweep design

`simulation/harness/run_zvs_sweep.py` (this pass's changes: PAN_L1 88 µH,
K/L2 re-derived per §2, `.cir` `.options` GMIN loosened 1e-11→1e-9 —
needed for the new parameter point to converge reliably, verified
empirically, see the harness's own comments):

- **Pan presets (4):** `cast_iron`, `stainless` (K=0.6136, L2=97.13 µH,
  RPAN=10 Ω), `aluminum` (K=0.15, unverified, unchanged),
  `no_pan` (K=0.01) — covers pan present/absent and a coupling range
  from ~0 to the ferromagnetic point.
- **Frequencies (33):** 28–65 kHz, densified to 500 Hz resolution across
  the firmware's actual 44–50 kHz legal range (the original grid's
  coarser 45/48/50 kHz points could straddle a real transition inside
  that 6 kHz band without landing on it).
- **Power:** each point now also reports delivered pan power (`P_pan =
  i_pan_rms² × RPAN`), so the 1800 W point can be located on the same
  grid as the ZVS numbers, per the build-order instruction to sweep "the
  power range up to 1800 W," not just frequency.

**Result: 132/132 points converged.** Determinism: baseline
(`cast_iron`, 35 kHz) and worst-margin (`aluminum`, 30 kHz) decks each run
3× with byte-identical `.meas` values (raw ngspice stdout is *not*
byte-identical — same documented adaptive-timestep diagnostic-line noise
as every prior run of this deck; see `simulator.note` in the JSON).
Self-consistency check (`grid_reproduces_independent_baseline_run`):
**passed**.

---

## 5. Results

### 5.1 Per-preset ZVS transition (full grid, unrestricted by PLL range)

| Preset | Highest `zvs_lost` | Lowest `zvs_held`/`degraded` |
|---|---|---|
| cast_iron | 36 000 Hz | 38 000 Hz |
| stainless | 36 000 Hz | 38 000 Hz |
| aluminum | 31 000 Hz | 32 000 Hz |
| no_pan | 31 000 Hz | 32 000 Hz |

Ferromagnetic pans (re-derived coupling) transition **6–8 kHz below** the
firmware's 44 kHz PLL floor. Aluminum/no_pan (weak coupling, unchanged
assumption) transition right at the unloaded resonance (~31 kHz), also
well below the floor. Worst margin found anywhere in the full grid:
**101.6% lost, `aluminum`/`no_pan` at 28–31 kHz** — outside the firmware's
legal range in all cases.

### 5.2 Inside the firmware's actual 44–50 kHz PLL range — the answer that matters

**ZVS is held at every converged point, for all four presets. No loss
anywhere inside the legal operating envelope.**

| Preset | Points | Margin range | Worst point | Power range (W) |
|---|---|---|---|---|
| cast_iron | 13/13 held | 0.855–1.025% | 44 000 Hz, 1.025% | 1056–2548 |
| stainless | 13/13 held | 0.855–1.025% | 44 000 Hz, 1.025% | 1056–2548 |
| aluminum | 13/13 held | 0.542–0.881% | 45 000 Hz, 0.881% | 10–47 |
| no_pan | 13/13 held | 0.518–0.930% | 45 000 Hz, 0.930% | 0.0–0.3 |

(Margin = residual Vce at the switch's own turn-on instant, as % of the
full 340 V bus; <10% is "held" by this harness's own convention — every
number above is deep inside that band, i.e. comfortably held, not
marginal. Full per-point table: `results` in the JSON.)

Aluminum's near-zero delivered power (≤47 W across the whole legal range)
and no_pan's near-zero power are consistent with the model's own K
assumptions for those cases (weak/no coupling means the tank barely
loads, which is also why they never come close to ZVS collapse inside
this range) — not a new finding, but a useful sanity check that the model
behaves as its own inputs say it should.

### 5.3 The power finding: 47 kHz is no longer the 1800 W point

`main.ato`'s own comment on `f_switching` states 47 kHz "delivers ~1804 W"
— that figure was computed from the **old** L=150 µH / K=0.79 pair. Under
the now-declared 88 µH coil and the in-band-reconciled K=0.6136 (§2), this
sweep finds:

| f_sw | Delivered power (cast_iron/stainless) | ZVS margin |
|---|---|---|
| 44 000 Hz (PLL floor) | **2548 W** | 1.025% held |
| 45 000 Hz | 2138 W | 0.972% held |
| 46 000 Hz | **1817 W** ← closest to 1800 W | 0.965% held |
| **47 000 Hz (declared nominal)** | **1562 W** | 0.917% held |
| 48 000 Hz | 1358 W | 0.878% held |
| 50 000 Hz (PLL ceiling) | 1056 W | 0.855% held |

**ZVS is not at risk at either frequency** — both 46 kHz (where 1800 W now
falls) and 47 kHz (the declared nominal) hold ZVS with comparable margin
(~0.9–1.0%, and notably close to the ~0.8% figure `main.ato`'s comments
already cite from the old model — the matched-pair cancellation on
`L_loaded` holds up, see §3). **What moved is where 1800 W sits in the
band**, by about 1 kHz, and how much power the *declared nominal* point
now delivers (1562 W, a ~13% shortfall from the 1804 W the design
documentation still asserts). This is a direct, disclosed consequence of
using the better-evidenced (in-band) coupling data instead of the
out-of-band figure the nominal-frequency comment was computed from — it
is not a new defect in the tank, and it does not touch ZVS. It is a stale
number in `main.ato`'s own comment and in the prior evidence chain that
this sweep's own numbers now disagree with; flagged here, not corrected
in `elec/` (out of this task's scope).

Also notable, **not remediated here, flagged for whoever owns power
control**: the model puts **2548 W at the PLL floor (44 kHz)** — well
above the 1800 W rated point. Since a real closed-loop controller
presumably targets power via `t_zcd`/phase rather than a fixed frequency
(`pll_control.c`'s own documented control law), this is not necessarily a
live hazard, but it does mean the *bottom* of the legal PLL range is not
a safe default or fallback frequency for anything expecting ≤1800 W —
that is a power-limiting/control-loop question, out of this sweep's
scope, and is reported rather than adjudicated.

### 5.4 Current cross-check against independently-derived figures

At the model's own recomputed 1800 W point (46 kHz, cast_iron/stainless):
**24.50 A rms / 34.51 A peak** tank current. At the declared nominal
(47 kHz): **22.66 A rms / 32.22 A peak**. At the PLL floor (44 kHz, 2548
W): **29.16 A rms / 40.45 A peak**.

The coordinating brief reports a concurrent, independent part-stress
audit finding the tank coil running **28.7–31.9 A peak** against
`LitzPad_15A`'s 15 A pad rating — I did not independently verify that
audit's source document (its file is not present in this worktree,
consistent with it being written by a separate parallel agent per the
task brief). Taking the figure as given: **this sweep's numbers at and
near the design's nominal/1800 W operating point (32.2–34.5 A peak) are
in the same range as, and at the high end of or modestly above, that
independently-derived figure** — the two do not contradict each other,
and if anything this run's re-derived coupling pushes the current
estimate slightly higher, not lower. Both independently point at the same
underlying fact: `LitzPad_15A`'s declared 15 A rating is exceeded by
roughly 2× on rms current at the design's actual operating point,
regardless of which of the two (differently-derived) coupling models is
used. Against OCP-01's already-established 50.1 A peak trip
(`docs/STRATEGY.md` §OCP-01), every current figure in this sweep's legal
PLL range stays clear — worst case 40.45 A peak at 44 kHz, 19% under trip
— so this is a thermal/pad-rating concern, not an OCP-01 nuisance-trip
risk, per this model.

---

## 6. Gate cross-check

- **EFF-02 (efficiency >92% @ 1800 W, ZVS active):** this sweep cannot
  measure efficiency (the IGBT model is behavioral, no switching-loss
  figure is claimed anywhere in this harness). **What it can and does
  say: ZVS is held at the frequency where this model now puts 1800 W
  (~46 kHz), with 0.965% margin, comfortably inside "held."** It also
  finds that 1800 W is no longer where the design's own comments say it
  is (47 kHz) — a fact EFF-02's test procedure should account for if it
  measures efficiency at a fixed 47 kHz command rather than at whatever
  frequency the closed loop settles on to hit 1800 W. Not itself a gate
  failure; a test-procedure precision issue surfaced by this sweep.
- **OCP-01 (45–55 A, 50.1 A as-built):** no conflict found anywhere in
  the legal PLL range under this model — see §5.4.
- **Protection thresholds generally:** this sweep does not touch
  OVP-01/THM-01/THM-02/UVL-01/UVL-02; no new finding here.
- **No gate is endangered by a ZVS loss inside the legal operating
  envelope**, because this model finds none. The one endangerment this
  sweep *does* surface is indirect: if EFF-02 (or any bench test) is run
  at a literal, hardcoded 47 kHz rather than at whatever frequency
  delivers 1800 W, it would be measuring efficiency at ~1562 W, not
  1800 W, under this updated model — a test-validity risk, not a
  hardware-safety one.

---

## 7. Caveats, stated plainly

- **`calibrated: false` everywhere, unchanged by this pass.** IGBT model
  is behavioral with fixed (non-Vce-dependent) capacitances; margin
  percentages are ordinal, not calibrated switching-loss figures (see
  `models_used` in the JSON).
- **The pan-coupling re-derivation in §2 is a better chart reading, not a
  bench measurement.** It resolves the harness-vs-source divergence
  `main.ato` itself already named as open; it does not resolve the
  underlying "no bench data exists" gap `docs/evidence/2026-07-27-coil-
  pan-coupling-resolution.md` §4 already described. That gap is
  unchanged: three frequency points on the *real* coil and pan are still
  what would close it.
- **The 88 µH coil is a chart reading of a different coil.** No coil, and
  no pan, has been measured by this project. `TANK_COIL_SPECIFICATION.md`'s
  incoming acceptance test is exactly what closes that when a coil is
  actually wound.
- **`aluminum` (K=0.15) is an unverified retained assumption**, not
  touched by this pass — do not read its near-zero delivered power as a
  measured statement that this design cannot heat aluminum pans, only as
  what this particular unverified K implies.
- **`RPAN=10 Ω` was held fixed, not re-solved**, in the §2 re-derivation
  — one more inherited, uncited placeholder this pass did not have
  grounds to touch.
- **Do not present any margin number in §5 as validated.** Every one of
  them is this uncalibrated model's output, re-run today against
  better-reconciled (not measured) inputs than the harness carried
  yesterday.

## 8. What would resolve the remaining gap

Unchanged from prior evidence, restated because it is still the actual
next step: an LCR-bridge measurement of the real coil, unloaded and
loaded with a reference pan, at **three** frequency points (25/35/45 kHz
or similar — a single frequency cannot separate `L2` from `RPAN`), per
`docs/evidence/2026-07-27-coil-pan-coupling-resolution.md` §4 and
`docs/hardware/TANK_COIL_SPECIFICATION.md` §2's already-issued acceptance
test. That measurement would directly replace §2's re-derived (K, L2,
RPAN) with a real one, and would settle §5.3's ~13% power discrepancy
either way.

## 9. Reproduction

```
uv run python simulation/harness/run_zvs_sweep.py --determinism-runs 3
```

Requires `ngspice` on `PATH` (not a normal dependency of this worktree in
every environment — this session installed ngspice-42 into a scratch
prefix via `dpkg-deb -x` from `apt-get download ngspice`, no root
required, to run this sweep). Raw output:
`docs/evidence/2026-08-07-zvs-margin-sweep.json`.
