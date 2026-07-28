# Does the PLL deliver the ratio-tracking mitigation? No.

**Date:** 2026-07-28
**Question:** `docs/evidence/2026-07-27-inductance-range-sweep.md` found that the
0.84% ZVS margin does not survive the plausible inductance range, but that a
**ratio-tracking** mode — PLL retunes `f_sw` to hold `f_sw / f_res_loaded ≈ 1.25`
— would hold ZVS across all of L ∈ [50, 250] µH, requiring **35.7–83.0 kHz**
agility. That doc marked the capability "not confirmed as implemented."

**Answer: the PLL exists, but it cannot deliver this mitigation, and it
disagrees with the hardware design in four independent places.**

## 1. The frequency clamp is 30–50 kHz. The mitigation needs 35.7–83.0 kHz.

`firmware/components/control/pll_control.h:22-24`:

```c
#define PLL_MIN_FREQ_HZ     30000
#define PLL_MAX_FREQ_HZ     50000
#define PLL_DEFAULT_FREQ_HZ 35000
```

Enforced by hard clamps in `pll_control.c:228-233`. **50 kHz is a ceiling the
loop cannot exceed**, against the 83.0 kHz the mitigation requires at the low
end of the inductance range.

That low end is not hypothetical: every comparable real coil cited in
`2026-07-27-coil-pan-coupling-prior-art.md` measures **47–50 µH** (Infineon
AN235020 48–50 µH measured; APHO2025 48.7 µH measured; Würth 760308101303
47 µH datasheet). **The mitigation is unavailable exactly where it is needed.**

## 2. The firmware still starts at 35 kHz — the frequency condemned today

`PLL_DEFAULT_FREQ_HZ` is **35000**, used at init (`:60`, `:123`) and on reset
(`:353`, `:360`).

`2026-07-27-zvs-operating-point.md` established that with corrected coupling
(K = 0.79), 35 kHz gives **100.7% ZVS margin lost** — full hard switching of the
1200 V IGBT half-bridge — for cast iron and stainless. `elec/src/main.ato:91`
was updated to `f_switching = 47kHz` for exactly this reason.

**The firmware was not updated.** Design-as-code says 47 kHz; the firmware
starts the bridge at 35 kHz.

## 3. `main.ato` asserts a tracking range the firmware cannot provide

`elec/src/main.ato:92`:

```
assert f_switching within 20kHz to 100kHz  # Resonant tracking range
```

The comment names this the *resonant tracking range*. The firmware provides
**30–50 kHz** — narrower by 5× at the top. Nothing cross-checks the two, so the
assertion passes while describing a capability that does not exist.

## 4. A fourth, disagreeing resonant frequency

`pll_control.c:51`:

```c
#define DEFAULT_RESONANT_FREQ   35800.0f /* Default: 35.8 kHz from RESONANT_TANK_DESIGN */
```

That is a fourth number for the tank's resonance, alongside `f_resonant_nominal
= 25 kHz` (`main.ato:111`) and the 23.7 kHz unloaded / ≈38 kHz loaded pair the
ZVS analysis derives at L = 150 µH. Used for lock detection (`:263`), so a wrong
value here mis-reports lock state.

## 5. The mechanism is not ratio tracking

The loop targets a **fixed absolute phase lag**, not a frequency ratio —
`TARGET_PHASE_US = 1.5f` (`:37`), error term `target_phase_us - measured_lag_us`
(`:208`).

A fixed 1.5 µs is a *different phase angle* at every frequency:

| f_sw | period | 1.5 µs as phase |
|---|---|---|
| 35 kHz | 28.6 µs | **18.9°** |
| 50 kHz | 20.0 µs | **27.0°** |
| 83 kHz | 12.0 µs | **44.8°** |

So the sweep's modelled "hold ratio = 1.25 against loaded resonance" is **not
what this firmware implements**. Whether a fixed 1.5 µs lag happens to
approximate ZVS across the range is a separate question this check does not
answer — but it is not the modelled mitigation.

## 6. `pll_init()` has no non-test caller

`grep` across `firmware/` excluding `test/` finds `pll_init(` only at its own
definition (`pll_control.c:107`). No production call site passes a
`pll_config_t`, so the compile-time defaults above are authoritative — and it is
not established that the PLL is wired into the main control loop at all.

## Verdict

The inductance risk is **not** absorbed by the control loop. The mitigation
identified by the range sweep is unavailable as built: the clamp stops 33 kHz
short of what it needs, the mechanism is phase-lag rather than ratio, and the
startup frequency is the one the hardware analysis condemned.

## UNVERIFIED

- **Whether a fixed 1.5 µs phase-lag target approximates ZVS** across L ∈
  [50, 250] µH. It is a different control law from the modelled one; it was not
  simulated here. This is the single most useful follow-up — if it happens to
  work, the picture improves substantially.
- **Whether the PLL is invoked at all in the production control loop.** Absence
  of a `pll_init` caller is suggestive, not proof; the firmware may be
  incomplete rather than mis-wired.
- Whether `PLL_MIN/MAX_FREQ_HZ` were chosen deliberately or inherited from the
  pre-correction 35 kHz design. No rationale is recorded at the definition.
- The 35.7–83.0 kHz requirement is taken from the range sweep, not
  independently re-derived here.

## Recommended

1. Raise `PLL_MAX_FREQ_HZ` toward 85–100 kHz **only if** the switching losses,
   gate-drive and snubber design support it — this is a hardware question, not a
   constant edit.
2. Change `PLL_DEFAULT_FREQ_HZ` 35000 → 47000 to match `main.ato`, or record why
   startup should differ from the nominal operating point.
3. Add a gate asserting the firmware's PLL range covers `main.ato`'s declared
   tracking range, so items 1–3 above cannot drift apart again silently.
4. Reconcile `DEFAULT_RESONANT_FREQ` against `f_resonant_nominal`, stating
   loaded vs unloaded, per the ambiguity already recorded in the ZVS doc.
