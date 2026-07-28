# ZVS operating point: f_switching 35 kHz → 47 kHz

<!-- provenance: commit=6b4210992e171d185257664cef4bcec86c572d08 dirty=UNKNOWN -->

**Date:** 2026-07-27
**Status:** change committed (`dd08c286`); this document is the analysis the
implementing agent did not reach before dropping. Written by the coordinator
from the committed artefacts and independently recomputed arithmetic.

## Why the change

With the corrected pan coupling (`K = 0.79` for ferromagnetic pans, anchored to
Infineon AN235020's measured 0.40 loaded/unloaded L-ratio — see
`2026-07-27-pan-preset-correction.md`), ZVS margin at the previously-declared
**35 kHz** nominal flips from **2.2% held** under the old under-coupled model to
**100.7% lost** for cast iron and stainless. That is full hard switching of a
1200 V IGBT half-bridge, at the nominal operating point, for the pans the
appliance exists to heat. Aluminium and no-pan are unaffected.

At **L = 150 µH, ratio ≈ 1.25, f_sw ≈ 47.0 kHz** the corrected model delivers
**1804 W**, holds ZVS at **0.84%** margin, and draws **28.76 A peak** —
clearing OCP-01's 50.1 A trip by 43%.

## Internal-consistency check on the declared frequencies

Recomputed directly from the committed values. `C_tank` = 300 nF
(`c_tank1` + `c_tank2`, 150 nF each, `modules.ato:446,453`).

| Declared | Value | Implies |
|---|---|---|
| `f_resonant_nominal` (`main.ato:111`) | 25 kHz | **L = 135.1 µH** |
| `assert f_resonant_nominal within 20kHz to 35kHz` (`:112`) | — | L = 68.9 – 211.1 µH |
| `f_switching` (`main.ato:91`) | **47 kHz** | — |
| `assert f_switching within 20kHz to 100kHz` (`:92`) | — | satisfied |

**No assertion fails.** But `f_resonant_nominal = 25 kHz` is a third number that
matches neither the simulation's 80 µH default (→ 32.5 kHz) nor the L = 150 µH
the ZVS analysis recommends (→ 23.7 kHz). All three sit inside the assertion
window, so the window never caught the divergence.

## The finding that matters: loaded versus unloaded is not stated

`f_resonant_nominal` does not say whether it is the **loaded** or **unloaded**
resonance, and with the corrected coupling **the two differ by roughly 60%**.

At L = 150 µH:

| | f_res | f_sw / f_res |
|---|---|---|
| unloaded | 23.7 kHz | **1.98** |
| loaded (≈1.6×) | ≈ 38 kHz | **≈ 1.24** |

Only the loaded figure is meaningful for ZVS, and it reproduces the analysis's
reported ratio of ≈1.25. Read as unloaded, 47 kHz looks like it sits at nearly
twice resonance — which would imply very low power transfer and would be the
wrong conclusion.

**This exact ambiguity already produced one real bug today.**
`run_tank_coil_sweep.py` referenced its frequency ratio against the *unloaded*
resonance, which silently reintroduced the under-loading error the moment `K`
was corrected; it needed a self-consistent `f_res_loaded_hz()` fixed-point
solver to fix. The same ambiguity is still present in `main.ato`, undeclared.

**Recommendation:** `f_resonant_nominal` should state which resonance it names,
and the ZVS margin assertion should be expressed against the loaded one.

## What is conditional, and on what

**`f_switching = 47 kHz` is not a measured operating point.** Its dependency
chain:

```
Infineon AN235020 measured L-ratio 0.40  (at 90-150 kHz, not 35-47 kHz)
  -> extrapolated K >= 0.775, chosen 0.79
    -> assumed L = 150 uH          <-- NOT SPECIFIED; inductor_conn is a placeholder
      -> f_sw = 47 kHz
```

`COIL_BRACKET_DESIGN.md` fixes only an OD ceiling, an air gap and a coil
height — no turn count, inner diameter or wire spec — so L cannot be derived
from geometry (`2026-07-27-coil-pan-coupling-resolution.md`).

**47 kHz is better founded than the 35 kHz it replaces**, which is now known to
hard-switch the bridge with a real pan. It is not established. The risk is that
a committed number becomes treated as settled by later readers — precisely what
`+340V_BUS` did, costing a fail-open over-voltage protection.

## UNVERIFIED

- **L = 150 µH** — assumed, not specified or measured.
- **K = 0.79** — extrapolated from a measurement at 3–4× the design frequency.
- **The ~1.6× loaded/unloaded frequency ratio** — taken from the corrected model,
  not measured.
- **Knock-on effects not yet analysed**: PLL tracking range at 47 kHz, tank
  capacitor voltage rating against `v_tank_peak * 1.43`, IGBT switching losses
  at the higher frequency.
- **Aluminium** reaches only 1451 W (19% short of 1800 W) on its deliberately
  retained low-K assumption.

## What would close this

The bench measurement specified in `2026-07-27-coil-pan-coupling-resolution.md`
§4 — an LCR sweep of the production coil, loaded and unloaded, across a pan and
gap matrix, at **three frequency points (25/35/45 kHz)**, since a single
frequency cannot separate `L2` from `RPAN`. That yields `L_unloaded` (the coil
spec directly), the real loaded/unloaded ratio, and a measured `(K, L2, RPAN)`
triple — which would replace every assumption in the chain above.
