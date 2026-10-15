# sensor-r3 bench kit: decisions

2026-10-15. All numbers come from the scripts in this folder:
- `fit.py --selftest` → `selftest.json`
- `jig.py` → `jig.json`
- `surrogate.py` → `surrogate.json`
- `bom.py` → `bom.json` (reference and lean kits)
- `plate_check.py` → `plate-check.json`
- `fit.py --selftest --selftest-probe probe.lean.json` → `selftest-lean.json`
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

The reference kit is about $1,285 at estimated list prices (`bom.py`),
excluding the oven and the cookware. The biggest items are the disc lot ($250,
a quote item) and machining ($250).

**Superseded by the lean kit, about $313 (L1–L7).** The reference kit stays in
`bom.json` as the C1-exact option.

## Lean kit (2026-10-15, after the owner asked why $1,285 and why devkits)

The owner asked for the cheapest kit that still answers the question: dry
τ63_C1 per pan, PASS ≤ 1.2 s, STOP > 1.35 s. **Lean must-buy is about
$313, plus $65 optional** (`bom.py`). Fidelity is kept where the answer
depends on it: the face finish class, the spring force, the proud height, the
tilt-following mount, and a weighed disc heat capacity.

### L1. Logger: devkit + breakouts, not a JLC board

A JLC PCBA board for this one-off instrument would cost about $70–90 for the
2-board minimum. That covers:
- 5 PCBs;
- SMT setup and stencil;
- extended-part fees for the ESP32-S3 module, MAX31865 and MAX31856;
- parts and DHL.

It also means about a day of schematic and layout, 1–2 weeks of lead time,
and the risk of a respin. The devkit, the Adafruit MAX31865 (whose 430 Ω
0.1 % Rref sets the reading), a generic MAX31856 and a bead cost about $48.
They arrive in days and work with `logger_fw/logger_fw.ino` as written.

**Where JLC helps:** a repeatable multi-probe fixture, the factory
end-of-line sensor check Impulse runs on every unit (mining r2), or a
production test jig. Those are worth a board. This survey isn't.

### L2. Disc: core option B from one polished alumina substrate

The reference disc lot ($250 quote, laser-cut, 20 pieces) is replaced by:
- one 25.4 × 25.4 × 0.254 mm polished 99.6 % alumina substrate (about $20);
- a diamond core bit (about $8).

**The core bit's inside diameter sets the disc**, so buy a bit with an
8.0–8.3 mm inside diameter, which is often sold as 10 mm. Core 3–4 discs and
keep the best edge.

**Why it is safe:**
- This is option B (+20.2 % heat capacity vs C1). D2 already allows it with
  the model correction, and it is the self-test's own probe.
- The fit uses the weighed mass and the measured contact diameter.
- `surrogate.json` row "B-lean" is identical to B.
- The face finish class is unchanged (polished thin-film grade,
  Ra ≤ 0.1 µm).

### L3. Element: keep IST P0K1.202, buy 2 instead of 3

A distributor M222-class chip (about 2.0 × 2.3 × 0.8 mm, about 12.9 mJ/K, about
$7) was tried in `probe.lean.json`. **The self-test failed** at
h 888: +0.056 s against a 0.055 s tolerance. The larger element lengthens
τ_int from 0.159 to 0.247 s, and the 2-node fit's bias grows.

The error was on the slow side and the verdicts were still correct. But the
tolerance was not loosened to pass it: the saving is about $30. So the lean
kit keeps the reference element, 1 + 1 spare.

With that, `selftest-lean.json` **passes: max |error| 0.0485 s**, identical
to the reference self-test.

### L4. Jig: JLCCNC parts and a standard set screw

The $250 shop machining estimate plus $70 of stock is replaced by:
- the PEEK post, turned at JLCCNC (about $25, estimate);
- the 6061 holder at JLCCNC (about $25, estimate);
- an M10 × 1 fine-thread set screw (about $3) instead of the turned plug.

The post touches the disc and sees the pan temperature, so it stays PEEK. A
printed resin would creep at 150–230 °C. The holder sits under the plate and
stays well below 100 °C, but aluminium is cheap at JLCCNC, so it isn't worth
printing.

Quotes are online and instant; the estimates need confirming.

### L5. Metrology: buy only the milligram scale

The disc's mass, about 49 mg, needs 0.001 g, which gives C_cap ±2 %, inside
the D6 4 % term.

Everything else is commonly owned:
- **Force window 143–163 g:** a kitchen scale with 1 g resolution.
- **Proud height ±0.02 mm:** a digital caliper in step mode. Buy the dial
  indicator only if the readings scatter.
- **Pan flatness:** a steel rule and feelers.
- **Roughness comparator:** optional. Pan Ra class is metadata, and the fit
  measures h_c directly.

### L6. Plate: any flat non-metal plate. The reference bead moves into the bore.

`plate_check.py` asks whether the plate matters. h_c doesn't involve the
plate: it is the disc face, the pan base, the force and the mount. The plate
acts only through a gradient. The pan base resting on a cold plate cools
there, while the contact point over the Ø18 bore does not.

**Method:**
- A radial finite-difference pan base with plate flux outside the bore. That
  is contact conductance h_pp in series with a semi-infinite plate.
- Carbon steel 2 mm, clad 2.6 mm and cast iron 5 mm.
- h_pp of 300 and 1500 W/m²K.
- ΔT of 125 K (cold plate) and 40 K (preheated plate).
- Each slope mismatch is pushed through `fit.py`'s own synthetic generator
  and fit.

**Results** (worst case, τ63_C1 error at h 888–1300; the zero-mismatch
baseline is the fit's own +0.037 s):

| Plate | Reference at 15 mm, cold plate | Reference at 6.5 mm, inside the bore |
|---|---|---|
| Glass-ceramic or porcelain | +0.069 s, **over the 0.05 s tolerance** | +0.047 s, cold plate |
| Calcium-silicate board | +0.053 s | +0.043 s |
| Aluminium | +0.29 s | +0.10 s |

- **Preheated plate, reference at 15 mm:** glass-ceramic gives +0.047 s.
- **Every error is positive,** meaning a slower reading: conservative, never
  a false PASS.

**Decision:**
- **Move the reference to r = 6.5 mm,** inside the bore. RIG §2 is updated.
- **Warm the plate before a session.**
- **Use any flat non-metal plate.** The lean kit uses a replacement
  induction-cooker glass panel (about $30) instead of a cut offcut ($80) plus
  a bore service ($40). Porcelain tile or calcium-silicate board also pass if
  checked flat. **Never metal.**

This also applies to the reference kit. It is a fix to the survey method, not
only a cost item.

An earlier version of `plate_check.py` used a crude smoothing factor in place
of the radial model. It overstated the effect by about 10×, and its numbers
are not used.

### L7. What the lean kit gives up

- **The C1-exact Si3N4 disc,** replaced by the model correction, which is
  self-tested.
- **Shop-machined tolerances,** replaced by JLCCNC's standard tolerances. The
  proud height is shimmed and measured anyway.
- **Calibrated metrology** for force and height, replaced by consumer tools
  inside the stated windows.

None of these enters the gated number except through terms the fit already
carries (D6). The Si3N4 lot is worth buying later, if C1 goes ahead, as the
first production-intent disc sample.
