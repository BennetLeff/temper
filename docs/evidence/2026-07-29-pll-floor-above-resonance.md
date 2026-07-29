# The PLL's legal frequency range extended 7.6 kHz below resonance — and now cannot

<!-- provenance: commit=1dee28b914e4ee8629df466552c1bcd4d13be33c dirty=true -->

**Date:** 2026-07-29
**Base commit:** `1dee28b9` (`origin/main`), branch `fix/pll-floor-above-resonance`
in an isolated worktree. `dirty=true`: every number below was computed against
this document's own changes applied on top of that commit — the pre-change
numbers are reproduced by reverting the two constants named in §2.
**Scope touched:** `firmware/components/control/pll_control.h`,
`firmware/components/control/pll_control.c`, `firmware/test/test_pll_control.c`,
`elec/src/main.ato`, `scripts/check_pll_range_consistency.py`,
`scripts/tests/test_check_pll_range_consistency.py`, `scripts/manifest.yaml`,
this document. No `pcb/`, no `simulation/`.
**Method:** first-harmonic solution of the half-bridge series tank using this
repo's own committed T-model coupling relation and pan preset, cross-validated
against the repo's ngspice-derived numbers at the committed operating point
(§1.3). No bench hardware, no new ngspice runs.

---

## Falsifier, stated before computing

> *"Raising `PLL_MIN_FREQ_HZ` above resonance is only worth doing if 1800 W
> remains reachable above the new floor. If 1.05 × f_res makes 1800 W
> unreachable, or if it can only be made to work by widening
> `PLL_MAX_FREQ_HZ`, this change is wrong and must be reported as a stop, not
> shipped with a smaller margin."*

**Result: the falsifier does not fire, and the margin did not have to be
shaved.** 1800 W lands at **47.1 kHz** — 5.1 kHz *above* the new 42 kHz floor
and 2.9 kHz below the unchanged 50 kHz ceiling. The floor is nowhere near
binding on rated power: at 42 kHz the tank still delivers **~3.7 kW**, twice
rated. The entire 30–42 kHz band that was removed was either hard-switching or
2–3× over-power. `PLL_MAX_FREQ_HZ` was **not** touched.

A second falsifier fired, in a place the task did not ask about, and is
reported rather than fixed: see §6.2 (at −10 % coil the 1800 W point moves to
50.05 kHz, marginally *above* the ceiling).

---

## 1. The hazard

### 1.1 What the constant said

`firmware/components/control/pll_control.h:22` (pre-change):

```c
#define PLL_MIN_FREQ_HZ     30000   /**< Minimum switching frequency */
```

`elec/src/main.ato` mirrored it (`f_pll_tracking_min: frequency = 30kHz`), and
`scripts/check_pll_range_consistency.py` confirmed the two agreed. **They did
agree. They were both wrong.** That is the whole lesson of this pass: a
cross-check between two declarations is silent about whether either declaration
is physical.

### 1.2 Why below-resonance is not a mild inefficiency

This is a **series**-resonant inverter. The tank impedance is

```
Z(f) = R_reflected(f) + j*( 2*pi*f*L_loaded(f) - 1/(2*pi*f*C) )
```

Above the loaded resonance the reactance is positive — the tank is inductive,
current lags voltage, and the half-bridge commutates into the anti-parallel
diode: zero-voltage switching. Below resonance the reactance is negative — the
tank is **capacitive**, current *leads*, and the incoming device turns on into
a charged output capacitance while the opposite diode is still conducting. On a
1200 V IGBT half-bridge at the full 340 V bus and ~1.8 kW that is turn-on loss
plus diode reverse recovery on every edge: a device-destroying regime, not a
tuning shortfall.

The pre-change legal range put **7.58 kHz of that regime inside the firmware's
own declared bounds.**

### 1.3 The model, and its agreement with the repo's own harness

First-harmonic analysis with this repo's committed `cast_iron`/`stainless` pan
preset (`simulation/harness/run_zvs_sweep.py`: K = 0.79, R_PAN = 10 Ω,
L2 = 218 µH) and the exact T-model relation
`run_tank_coil_sweep.py:f_res_loaded_hz()` iterates:

```
L_apparent/L1 = 1 - K^2*x^2/(R_PAN^2 + x^2),      x = omega*L2
R_reflected   = omega^2*K^2*L1*L2*R_PAN/(R_PAN^2 + x^2)
V1_rms        = 2*Vbus/(pi*sqrt(2)) = 153.05 V   at Vbus = 340 V
```

| Quantity | This pass | Repo's committed figure | Δ |
|---|---|---|---|
| `f_res,loaded` at L = 150 µH | **37 579 Hz** | 37 580 Hz (`pll_control.c` `DEFAULT_RESONANT_FREQ`), 37.58 kHz (ngspice harness) | **0.003 %** |
| P at 47 kHz | **1827 W** | ~1804 W (`main.ato` comment, ngspice) | +1.3 % |
| I_peak at 47 kHz | **29.5 A** | 28.76 A (ngspice) | +2.6 % |

The model reproduces the repo's own numbers, so the sweep below is not a new
physics claim — it is the committed model, evaluated at frequencies nobody had
evaluated it at.

### 1.4 The sweep, at L = 150 µH / 300 nF / 340 V

| f_sw | reactance | state | I_rms | I_peak | P | V_cap |
|---|---|---|---|---|---|---|
| **30.0 kHz** *(old floor)* | **−6.07 Ω** | **CAPACITIVE — HARD SWITCHING** | 21.0 A | 29.7 A | **1783 W** | 371 Vrms |
| 37.58 kHz *(f_res)* | 0.00 Ω | at the cliff | 37.0 A | **52.3 A** | 5661 W | 522 Vrms |
| 39.44 kHz *(1.05 × f_res, nominal L)* | +1.29 Ω | ZVS | 35.2 A | **49.8 A** | 5145 W | 474 Vrms |
| 40.0 kHz | +1.67 Ω | ZVS | 34.2 A | 48.3 A | 4856 W | 453 Vrms |
| **42.0 kHz** *(new floor)* | +2.97 Ω | ZVS | 29.9 A | 42.3 A | 3725 W | 378 Vrms |
| 46.6 kHz | +5.78 Ω | ZVS | 21.4 A | 30.3 A | 1925 W | 244 Vrms |
| 47.0 kHz *(f_switching)* | +6.02 Ω | ZVS | 20.9 A | 29.5 A | 1827 W | 236 Vrms |
| 50.0 kHz *(ceiling)* | +7.72 Ω | ZVS | 17.4 A | 24.6 A | 1275 W | 185 Vrms |

**The row that makes this worth a hard guard is the first one.** At 30 kHz the
tank delivers **1783 W** — within 1 % of the 1800 W rating — *while hard
switching*. A power-seeking outer loop commanded to 1800 W has a solution at
30 kHz, and every power reading at that solution looks correct. Nothing in the
measured quantities distinguishes it from the safe 47 kHz solution. The bridge
finds out first.

The second hazard is the band immediately above resonance: **37.6–40 kHz
delivers 4.9–5.7 kW at 48–52 A peak**, against OCP-01's 50.1 A trip and an
1800 W rating. `docs/evidence/2026-07-28-coil-selection-research.md` §5.3
reported 5.5–7.3 kW / 41–48 A / 671 Vrms for this band on its own 88 µH model;
that figure was flagged there as reported-not-verified. **It is corroborated in
magnitude here by this repo's own committed model** — 4.9–5.7 kW rather than
5.5–7.3 kW, same order, same conclusion. The band just above resonance is the
most dangerous place in the sweep, and the old floor let the loop pass straight
through it on the way down.

---

## 2. The derived floor

### 2.1 Arithmetic

`f_res` is set by `L_loaded = L × (loaded/unloaded ratio)`, because that is
what resonates with C. From `elec/src/main.ato`'s declarations:

```
L (nominal)         = 150 µH          (l_tank_assumed)
loaded ratio        = 0.399           (l_pan_loaded_ratio)
C                   = 300 nF          (c_tank_total = c_tank1 + c_tank2)
coil tolerance      = ±10 %           (l_tank_tolerance)

L_worst  = 150 µH × (1 − 0.10)                    = 135.0 µH
L_loaded = 135.0 µH × 0.399                       =  53.865 µH
f_res    = 1/(2π·sqrt(53.865 µH × 300 nF))        =  39 592 Hz
floor    = 1.05 × 39 592 Hz                       =  41 571 Hz
```

**`PLL_MIN_FREQ_HZ = 42000`** — the next round kilohertz above the requirement,
at **1.0608 ×** the worst-case loaded resonance and **1.1176 ×** the nominal
one.

The `1.05` is the ZVS cliff from `docs/hardware/TANK_COIL_SPECIFICATION.md`,
confirmed to be a *threshold* rather than a gradient in
`docs/evidence/2026-07-27-inductance-range-sweep.md` §2.3 and used as the
recommended guard ratio in `docs/evidence/2026-07-28-coil-selection-research.md`
§5.3.

### 2.2 Why this survives the coil being unspecified

Two independent routes to `L_loaded` agree:

| | L_unloaded | loaded ratio | **L_loaded** | f_res @ 300 nF |
|---|---|---|---|---|
| Repo's committed model | 150 µH (assumed) | 0.399 (K = 0.79 T-model) | **59.85 µH** | 37.58 kHz |
| Infineon QR coil, measured 30–50 kHz | ≈88 µH | 0.68 | **59.8 µH** | 37.31 kHz |

The coil assumption is ~1.7× too high and the coupling ~1.7× too strong the
other way. Only the product resonates with C, and the two models agree on it to
0.7 %. `f_res ≈ 37.3–37.6 kHz` is therefore robust across both, and a 42 kHz
floor clears 1.05 × f_res under either (39.18 kHz for the 88 µH model,
39.46 kHz for the repo's).

### 2.3 What it costs

For a series-resonant inverter **lower frequency means more power**, so raising
the floor lowers the maximum deliverable power. Stated plainly:

| | old (30 kHz floor) | new (42 kHz floor) |
|---|---|---|
| Usable band | 30–50 kHz (20 kHz wide) | 42–50 kHz (8 kHz wide) |
| Max deliverable power at the floor | 1783 W *(hard-switching)* | **3725 W** |
| Power at the ceiling | 1275 W | 1275 W |
| 1800 W operating point | 47.1 kHz | 47.1 kHz (unchanged) |
| Headroom below the 1800 W point | 17.1 kHz *(all of it unusable)* | **5.1 kHz** |
| Headroom above it | 2.9 kHz | 2.9 kHz |

**Nothing usable was given up.** The removed 30–42 kHz band was, in its
entirety, either capacitive-mode hard switching (below 37.58 kHz) or
3.7–5.7 kW at 42–52 A peak against a 50.1 A trip (37.58–42 kHz). The design's
real turndown — 1800 W at 47.1 kHz down to 1275 W at 50 kHz — is untouched, and
the floor still admits 2.07× rated power before the guard intervenes.

The honest way to say what the floor *is not*: **it is not a power limiter.**
At 42 kHz the converter can still deliver twice its rating. Limiting power to
1800 W remains the outer control loop's job. This floor only guarantees that
whatever the loop does, it does it in the ZVS half-plane.

---

## 3. ±10 % coil spread, and why the guard keys off worst case

`f_res ∝ 1/√L`, so:

| Coil | L_loaded | f_res,loaded | 1.05 × f_res | 42 kHz floor sits at |
|---|---|---|---|---|
| **−10 %** (135 µH) | 53.87 µH | **39 727 Hz** *(fixed-point)* / 39 592 Hz *(closed form)* | 41 713 / 41 571 Hz | **ratio 1.057** |
| nominal (150 µH) | 59.85 µH | 37 579 Hz | 39 458 Hz | ratio 1.118 |
| **+10 %** (165 µH) | 66.15 µH | 35 727 Hz | 37 513 Hz | ratio 1.176 |

**The guard keys off worst-case (minimum) L, deliberately.** A low-tolerance
coil resonates *higher*, so it is the unit that most needs a high floor. A
guard derived at nominal L would have produced 39.46 kHz — which at a −10 %
coil is **ratio 0.993, i.e. below resonance**. Nominal-L keying would
under-protect exactly the unit at risk, which is the failure mode of a safety
bound derived from a typical value.

At +10 % the floor is conservative by 12 %. That costs maximum power on
high-tolerance units and is the correct direction to be wrong.

**Two derivations of the worst-case f_res are shown above because they
differ slightly and the difference is worth naming.** The gate uses the closed
form `1/(2π√(L·ratio·C))` with the ratio declared at the nominal operating
point; the repo's harness iterates the ratio to a fixed point per (L, f). The
ratio is weakly L-dependent (0.3963 at −10 %, 0.3986 nominal, 0.4009 at +10 %),
so the closed form understates worst-case f_res by **0.34 %** — a
non-conservative direction. That is an order of magnitude inside the 5 % ZVS
margin and is absorbed by the floor's actual 5.7 % worst-case margin (42 000 vs
the fixed point's 41 713 Hz requirement). Declaring one ratio rather than
mirroring (K, R_PAN, L2) trades 0.34 % of accuracy for two fewer mirrored
constants; the trade and its size are recorded at the declaration site in
`main.ato`.

---

## 4. How the guard is enforced — three independent paths

### 4.1 `scripts/check_pll_range_consistency.py`, checks 5 and 6

The gate already cross-checked `pll_control.h` against `main.ato`. It was
extended in its existing idiom (targeted per-name regexes, full denominators,
fail-closed on partial discovery) rather than duplicated:

- **Check 5 — derived floor.** Parses `l_tank_assumed`, `c_tank_total`,
  `l_pan_loaded_ratio` and `l_tank_tolerance` from `main.ato`, each matched
  together with its atopile type keyword (so a *retyped* quantity is a miss,
  not a misread), derives `1.05 × f_res(L_min)`, and fails if
  `PLL_MIN_FREQ_HZ` is below it.
- **Check 6 — capacitance mirror.** `main.ato`'s `c_tank_total` is a
  restatement of two real parts, and an untethered restatement is precisely
  this repo's recurring defect (`+340V_BUS`, the 20–100 kHz range). The gate
  reads `c_tank1.value` and `c_tank2.value` from `elec/src/modules.ato` and
  requires the parallel sum to equal the mirror.

**`ZVS_MARGIN_MIN = 1.05` lives in the gate, not in `main.ato`**, on purpose:
`main.ato` owns the physics (what the tank *is*), the gate owns the safety
threshold (how much margin above the cliff is *required*). A margin declared in
the file under test can be relaxed from the side being checked.

**Fail-closed contract.** There is no fallback floor and check 5 is never
skipped. A GATE ERROR (exit 5) results from: any of the three files missing;
any named constant absent or unparseable; and any derived-floor input outside
its sanity band (`L, C > 0`; ratio in (0, 1]; tolerance in [0, 1)). That last
class matters — `l_tank_tolerance = 0` on its own is legitimate (a measured,
binned coil) and is allowed, with a test pinning that as a deliberate property;
but `l_pan_loaded_ratio = 0` or `tolerance = 1.0` would drive the derivation to
a degenerate floor, so they abort loudly instead.

### 4.2 A compile-time guard in the firmware

`pll_control.c` already declared `DEFAULT_RESONANT_FREQ 37580.0f` — the loaded
resonance. Its `pll_ctx` initializer sets `.min_freq = PLL_MIN_FREQ_HZ` and
`.resonant_freq = DEFAULT_RESONANT_FREQ` **five lines apart in the same struct**,
one of them 7.58 kHz below the other, with nothing comparing them. That
comparison is now structural:

```c
typedef char pll_min_freq_is_above_loaded_resonance_check[
    (PLL_MIN_FREQ_HZ * 100 >= DEFAULT_RESONANT_FREQ_HZ_INT * 105) ? 1 : -1
];
```

Spelled as a negative-array-size typedef rather than `_Static_assert` because
`firmware/test` builds with `CMAKE_C_STANDARD 99`. It is deliberately the
*weaker* of the two guards: it keys off nominal resonance, because the firmware
does not know the coil tolerance. The Python gate, keying off worst case, is
the authority. Two paths, neither able to silently skip; the firmware one works
for anyone who compiles without CI.

**Falsified:** compiling the same expression with `PLL_MIN_FREQ_HZ 30000` fails
with `'guard' declared as an array with a negative size`.

### 4.3 Removing a second declaration instead of checking it

`PLL_DEFAULT_CONFIG()` hardcoded `.min_freq_hz = 30000, .max_freq_hz = 50000` —
a second, uncrosschecked copy of the same safety bound that the gate could not
see (it reads only the `#define`s). It now references `PLL_MIN_FREQ_HZ` /
`PLL_MAX_FREQ_HZ`. Drift removed by construction rather than by checking, which
is strictly better than adding a seventh check.

---

## 5. Verification

| Command | Result |
|---|---|
| `uv run --no-sync pytest scripts/tests/test_check_pll_range_consistency.py` | **51 passed** (was 24) |
| `uv run --no-sync python scripts/check_pll_range_consistency.py` | **exit 0**, 6/6 checks, 3/3 + 4/4 + 2/2 constants discovered |
| `cmake -B firmware/test/build firmware/test && cmake --build firmware/test/build` | **builds clean** (guard compiles) |
| `ctest --test-dir firmware/test/build` | **13/13 passed**, including `pll_tests` |
| `cd elec && ato build` | **exit 0** — the new `main.ato` declarations and their `assert`s hold |
| `uv run --no-sync ruff check` on changed Python | clean |
| `uv run python scripts/check_vacuous_gates.py` | passed, 0 violations (546 + 885 files) |
| `uv run --no-sync python scripts/check_manifest_gate.py` | passed, 78 files / 79 entries |

**New tests (27 added, 24 → 51 collected).** The three the task named, plus the
coverage that makes them meaningful:

- *Passes:* `test_committed_min_freq_passes_the_floor_check`,
  `test_derives_the_committed_floor` (pins 53.865 µH → 39 592 Hz → 41 571 Hz
  against hand-computed constants declared in the test module, so a bug in the
  gate's own formula cannot make the test agree with it).
- *Fails on a too-low floor:* `test_too_low_floor_is_a_violation_not_a_pass`,
  `test_floor_boundary_is_inclusive` (floor ± 1 Hz, pinning the comparison
  direction), `test_floor_tracks_declared_physics_rather_than_a_constant`
  (halving C raises f_res by √2 and the same 42 kHz floor must then fail — this
  is the property "derived, not hand-set" actually buys).
- *Fails closed:* each of the four physics inputs omitted in turn
  (parametrized), five out-of-band values (parametrized), an unparseable value,
  a missing `modules.ato`, a missing tank capacitor, and a mismatched
  `c_tank_total` mirror.
- *Fail-before/pass-after:*
  `test_the_2026_07_28_fix_itself_fails_the_derived_floor` — the previous fix,
  which made both files agree on 30–50 kHz, **passes all four original checks
  and fails check 5.** That single test is the argument for this whole pass.

**Firmware tests touching PLL bounds** (`firmware/test/test_pll_control.c`),
all now passing:

- `test_frequency_min_limit` asserted `freq >= 30000.0f`. That literal would
  have kept "passing" after the floor moved to 42 kHz while no longer testing
  the clamp at all — a silent weakening. Changed to `>= (float)PLL_MIN_FREQ_HZ`
  (and the max test likewise), so it tracks whatever the derived floor is.
- `test_pll_init_custom_config` used `min_freq_hz = 35000` as its example
  config. 35 kHz is *below* resonance. It only ever exercised config plumbing,
  but a fixture is also an example, and this one demonstrated a
  bridge-destroying value; changed to 43000.
- `test_pll_never_locks_at_uncalibrated_defaults` — unaffected, still asserts
  the known-open lock-window gap (§6.1).

---

## 6. Deliberately not done

### 6.1 Not fixed, and why

- **`PLL_MAX_FREQ_HZ` was not widened.** Stated explicitly and separately, per
  the constraint: the floor rose, the ceiling did not, and the usable band
  therefore narrowed from 20 kHz to 8 kHz. Widening it is a switching-loss
  question about the bridge, gate drive and snubber that needs bench data this
  project does not have.
- **`C_TANK` (300 nF), `f_switching` (47 kHz) and `l_tank_assumed` (150 µH) are
  unchanged.** All three are under active review
  (`docs/evidence/2026-07-28-coil-selection-research.md` §5.2 proposes 470 nF);
  none is in scope here. The new `c_tank_total` declaration restates 300 nF, it
  does not change it.
- **`pll_is_frequency_safe()`'s asymmetric window is unchanged.**
  `FREQ_MARGIN_LOW_HZ = 5000` would permit 32.58 kHz — below resonance, the
  same hazard in a second place. It is now **unreachable**, because the
  `PLL_MIN_FREQ_HZ` clamp is strictly tighter, so the protection is in place;
  retuning this file's safety-window constants is a control-loop decision, and
  a comment now records the reasoning at the constant.
- **The lock-confirmation gap is untouched.** `FREQ_TOLERANCE_HZ = 2000` still
  cannot confirm lock at the intended ~1.25 ratio offset
  (`docs/evidence/2026-07-28-pll-defaults-and-range-gate.md`). Unrelated to the
  floor; still open; its test still asserts the broken behaviour on purpose.
- **`simulation/harness/run_zvs_sweep.py`'s `PAN_PRESETS` K = 0.79 is
  untouched**, though `docs/evidence/2026-07-28-coil-selection-research.md` §7.2
  argues it is frequency-mismatched (solved against a 90–150 kHz measurement,
  applied at 47 kHz). Changing it would move `f_res` and therefore the derived
  floor — a bigger decision than this pass, and one the gate will now
  automatically re-derive against when it is made.

### 6.2 Found while verifying, reported not fixed

**At a −10 % coil, the 1800 W operating point moves to 50.05 kHz — marginally
above `PLL_MAX_FREQ_HZ` = 50 000.** This is a property of the *ceiling* and
predates this change; the raised floor neither causes nor worsens it. The
consequence is that a low-tolerance coil trades **full power**, not ZVS, which
is the correct direction to fail. Recording it rather than acting on it,
because the remedy is either widening the ceiling (explicitly out of bounds
here) or moving C to 470 nF, which recentres the 1800 W point at 38.1 kHz and
is a live proposal elsewhere. It is noted at the `f_pll_tracking_max`
declaration in `main.ato` so the next reader meets it there.

### 6.3 A correction carried forward

`main.ato`'s PLL comment block asserted that "every comparable real coil already
cited in this project's own evidence (Infineon AN235020, Wurth 760308101303,
APHO2025) measures 47-50uH". `docs/evidence/2026-07-28-coil-selection-research.md`
§2.4 established that the Würth part is a 26 mm / 1.5 A / 20 W Qi
wireless-power receiver coil and that APHO2025's bench coil was validated
against it — so the "three independent sources" are one comparable coil,
measured only at 90–150 kHz. That correction is now recorded at the declaration
site, because the sentence was load-bearing for the claim that the 30–50 kHz
range is "KNOWN TO BE INSUFFICIENT". **The capability gap is not declared
closed** — only its evidence is marked as weaker than written.

---

## 7. UNVERIFIED

- **The coil.** `l_tank_assumed = 150 µH` remains an assumption; `inductor_conn`
  is still a placeholder footprint. The floor is robust to this (§2.2) but is
  not independent of it: if the real coil's `L_loaded` differs from ~60 µH by
  more than ~10 %, the derived floor moves — which is now automatic, and is the
  point.
- **`l_pan_loaded_ratio = 0.399`** inherits every caveat of `PAN_PRESETS`
  K = 0.79: solved from Infineon AN235020's 0.40 loaded/unloaded ratio measured
  at **90–150 kHz** and applied at 47 kHz, with 3 unknowns against 2 literature
  equations (`docs/evidence/2026-07-27-coil-pan-coupling-resolution.md` §2.5).
  The corroborating 0.68 @ 40 kHz figure is a chart reading of an unnamed
  Infineon coil. The *agreement* of the two (§2.2) is the strongest evidence
  here; neither input is independently solid.
- **±10 % coil tolerance** is a recommended acceptance spec, not a measured
  part-to-part distribution. No coil has been bought or measured.
- **All power/current figures** are first-harmonic, ±3 % on current and −6 %/0 %
  on power against this repo's ngspice harness (§1.3). No new ngspice run was
  performed — deliberately, since it would mean touching `simulation/`.
- **The 5.5–7.3 kW figure** from the coil-selection research remains
  reported-not-verified. This pass corroborates its *magnitude* (4.9–5.7 kW)
  with a different model, which is not the same as confirming it.
- **Nothing here is a claim about thermal behaviour.** 3.7 kW at 42 A peak
  through a tank capacitor pair already known to be ~1.7× over its permissible
  AC current (PR #402) is a separate, unresolved problem; the floor does not
  address it and does not make it worse.

---

## Provenance

- Committed repo models: `simulation/harness/run_zvs_sweep.py` (`PAN_PRESETS`,
  `C_TANK_F`), `simulation/harness/run_tank_coil_sweep.py` (`f_res_hz`,
  `f_res_loaded_hz`) — read and reimplemented, then cross-validated against the
  repo's own published figures at the committed operating point (§1.3).
- `docs/evidence/2026-07-28-coil-selection-research.md` — §4.4 (the L_loaded
  cancellation), §5.3 (the floor proposal and the 1.05 guard ratio), §2.4 (the
  Würth correction).
- `docs/evidence/2026-07-27-inductance-range-sweep.md` §2.3 — the ZVS cliff as
  a threshold rather than a gradient.
- `docs/evidence/2026-07-28-pll-defaults-and-range-gate.md` — the gate this one
  extends, and the lock-window gap left open.
- Arithmetic: a ~70-line first-harmonic solver written for this pass in the
  session scratchpad and validated as in §1.3. Not checked in — it reproduces
  from the equations in §1.3 and would otherwise be a fourth unmaintained
  solver alongside the three in `simulation/harness/`. The one number the CI
  actually depends on (the derived floor) is computed by
  `scripts/check_pll_range_consistency.py:derive_zvs_floor()` and pinned
  against independently hand-computed constants in the test module.
