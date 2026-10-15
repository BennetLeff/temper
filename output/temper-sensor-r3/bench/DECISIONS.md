# sensor-r3 bench kit: decisions

2026-10-15. All numbers come from the scripts in this folder:
- `fit.py --selftest` → `selftest.json`
- `jig.py` → `jig.json`
- `surrogate.py` → `surrogate.json`
- `bom.py` → `bom.json`
- `logger.py --selftest`

## D1. The bench gates C1's τ63, computed from the fitted h_c

The surrogate's own τ63 is not the gated number. Each set-down is fitted for
the contact conductance per area h_c. That is a property of the pan base,
the face finish, the tilt-following mount and the force, all of which the
surrogate copies. τ63_C1 = `screen.tau63(C1, h_c)` is then judged against
1.2 / 1.35 s.

**Why:** C1's lag depends on its heat capacity, but the unknown is h_c. This
lets an off-the-shelf disc stand in for C1.

## D2. Disc: Si3N4 (option A) preferred, polished alumina (B) allowed

| Option | Heat capacity | vs C1 | Disposition |
|---|---|---|---|
| A: Si3N4 0.32 mm | 40.4 mJ/K | 0.0 % | **C1-exact. Preferred.** |
| B: 99.6 % polished alumina 0.254 mm | 48.6 mJ/K | +20.2 % | Outside ±15 %, so the stated model correction applies: the fit uses the probe's weighed heat capacity. The self-test runs this case. |
| C: as-fired 96 % alumina | 46.0 mJ/K | +13.8 % | Within ±15 %, but **rejected.** Its roughness would change h_c, which is the quantity being measured. |

## D3. Pan at 150 °C, heated in an oven, coil off

This follows sensor-r3 §5. 150 °C matches the contact model's air
conductivity. A 230 °C subset is reported but not gated.

**Limitation:** an oven heats the pan uniformly. On a hob, the pan is hotter
at the annulus than at the centre and may bow. Static dry contact on a flat,
uniform pan is what §5 asks for. Warping under induction heating needs a
later run on the temper prototype; this survey doesn't cover it.

## D4. Mount: post rocking on a ball in a loose guide

The guide clearance gives 37.5 mrad of free rocking, so the face follows the
pan the way C1's rocking post does (CAD G5: 0.68 mrad residual). The bench
has no wiper, so tilt-following on the bench is slightly better than in C1.

**What to do about it:** if a pan sits near the bar, rerun it with a PTFE
collar giving C1's ≤ 0.185 N wiper friction.

## D5. Proud height and force

- **Proud height:** built 0.80 mm, shimmed down to 0.60 mm. Shims only lower
  the disc.
- **Force:** set at flush on a 0.01 g scale. The spring is selected by rate,
  with preload set by the M10×1 plug. `jig.json`: 1.50 N at flush, 1.32 N at
  rest, 1.92 N at full stroke.
- **Corners:** 1.2 and 1.8 N are run as sensitivity conditions.

## D6. Probe-constant uncertainties behind the verdict band

| Constant | Allowance | Source |
|---|---|---|
| C_cap | ±4 % | ±2 % from disc mass on a 1 mg scale, ±3 % cp |
| C_el | ±30 % | Element not weighed |
| G_leak | ±50 % | |
| τ_int | ±0.015 s | Paste-calibration repeatability plus the paste-joint lag |

**At h 888 (the C1 worst case):**
- the band is 0.061 s;
- C_el contributes 0.049 s and C_cap 0.035 s;
- G_leak contributes 0.010 s and τ_int 0.005 s.

Weighing five spare elements together brings C_el to about ±10 %. The
values can be overridden in `probe.json` under `sys`.

## D7. Verdict rule

| Verdict | Condition |
|---|---|
| PASS | τ63 + band ≤ 1.2 s |
| STOP | τ63 − band > 1.35 s |
| MARGINAL | anything in between |

- **Each pan** is judged on its worst `dry_nominal` repeat, out of 5.
- **Overall:** STOP if any pan stops; MARGINAL if any is marginal; PASS
  otherwise.
- **Coverage:** ≥ 12 pans and all 6 classes, reported separately.

**Why:** the user decides from the worst way a pan gets set down, not the
average.

## D8. Pan reference used for slope only

The fit takes a linear fit of the pan thermocouple over the window, plus a
free offset dT. Thermocouple absolute error and the local pan quench go into
dT, so a taped bead is acceptable. A peened bead is preferred.

## D9. Logger firmware

The firmware writes raw register values to the MAX31865 and MAX31856 in
auto-conversion mode. Each record is stamped with the ESP32 microsecond
clock, so a single clock syncs both channels.

**Not compiled or run here:** no Arduino toolchain or hardware was available.
`logger.py --selftest` checks only the host parser (59.9 Hz from a synthetic
stream).

**Things to check on first power-up:**
- the `#` info line must read back `rtd_cfg=0xC2` and `tc_cr1=0x03`;
- the logged Pt100 rate must be about 60 Hz.

The 16.7 ms continuous conversion time is from the MAX31865 datasheet timing
table, as reported by a search summary; that table was not read directly.

## D10. Fit accuracy (self-test)

**What the self-test simulates:**
- a layered disc (Biot effects);
- contact that settles over 0.03–0.15 s;
- a pan cooling at 0.25 K/s;
- a thermocouple with 0.25 s lag, +1.5 K offset and noise;
- MAX31865 quantisation, 0.02 K noise and timing jitter;
- an element heat capacity 30 % above the fit's nominal value, and a leak
  1.5× nominal.

**Results:**
- τ_int is calibrated at 0.159 s; the true value is 0.152 s.
- τ63_C1 is recovered within **0.0485 s** over h 500–4000, against a
  tolerance of max(0.05 s, 5 %).
- The bias is **+3 to +4 %, always conservative** (it reads slower).
- All 24 verdicts are correct.
- The survey-aggregation check is correct (PASS, STOP, PASS, overall STOP).
- Fit residuals are about 0.035 K rms. That is the basis for the 0.3 K
  reject threshold in PROCEDURE §4.

**Caveat:** the generator shares the 2-node idea of disc plus element. It
cannot test effects absent from both, such as partial-area contact on a
rocking pan. The `dry_force_*` and `dry_proud_*` repeats are the empirical
check.

## D11. Cost

About $1,285 at estimated list prices (`bom.py`), excluding the oven and the
cookware. The biggest items are the disc lot ($250, a quote item) and
machining ($250).
