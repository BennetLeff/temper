---
title: "Worst-case every term in a safety formula, not just the one you thought of -- a careful derivation on one input hides the omission on another"
date: "2026-07-29"
category: best-practices
module: hardware_design
problem_type: best_practice
component: hardware_design
severity: critical
applies_when:
  - "a safety-relevant threshold is derived from a formula with more than one uncertain input"
  - "a derivation applies a component tolerance to one term of a product or ratio and a nominal value to another term that enters the same way"
  - "a code comment carefully justifies WHY one input is worst-cased, and no comment addresses the other inputs at all"
  - "a CI gate or hand derivation says 'worst case' without naming every quantity it worst-cased"
  - "extending an existing safety derivation (e.g. adding a new tolerance) rather than writing one from scratch"
  - "reviewing a derivation that already looks rigorous because it shows its work on some of its inputs"
tags:
  - worst-case-analysis
  - safety-margin
  - tolerance-stacking
  - resonant-tank
  - pll-floor
  - partial-rigor
  - review-discipline
---

# Worst-case every term in a safety formula, not just the one you thought of -- a careful derivation on one input hides the omission on another

## Context

`scripts/check_pll_range_consistency.py` derives the minimum safe PLL
frequency for `temper`'s series-resonant induction tank. Below resonance the
half-bridge loses zero-voltage switching and hard-switches into the tank's
capacitive impedance; `docs/hardware/TANK_COIL_SPECIFICATION.md` and
`docs/evidence/2026-07-27-inductance-range-sweep.md` establish this as a
threshold, not a gradient. `PLL_MIN_FREQ_HZ` in
`firmware/components/control/pll_control.h` is therefore a safety floor: below
it, the design destroys its own IGBTs.

The floor comes from `f_res = 1/(2*pi*sqrt(L_loaded * C))`. `L_loaded` and `C`
enter identically -- both under the same square root, both as `1/sqrt`. PR
#408 (`fix/pll-floor-above-resonance`, merged) derived the floor correctly
worst-casing the **inductance**: `elec/src/main.ato`'s `l_tank_tolerance`
comment states, in the code itself, exactly why minimum `L` is the hazardous
case --

> "f_res scales as 1/sqrt(L), so MINIMUM L is the hazardous end (highest
> resonance, so the floor must be highest) -- the gate derives against
> l_tank_assumed\*(1-this), never against nominal."

That reasoning is correct, was applied, and reads as careful engineering. The
gate's `derive_zvs_floor()` took `c_tank_total` -- the **capacitance** -- at
its nominal declared value, with no tolerance term at all. The same
`1/sqrt` relationship that makes minimum `L` hazardous makes minimum `C`
equally hazardous, and nothing in the gate or in `main.ato` said so until PR
#413 (`fix/pll-floor-cap-tolerance`, open) found it.

## The measurement

Committed values before PR #413: `l_tank_assumed = 88uH`,
`l_pan_loaded_ratio = 0.68`, `l_tank_tolerance = 0.10`,
`c_tank_total = 300nF`, `ZVS_MARGIN_MIN = 1.05`,
`PLL_MIN_FREQ_HZ = 42000` (from PR #408).

```
L_loaded_worst = 88uH * (1 - 0.10) * 0.68 = 53.856uH   (correctly worst-cased)

C nominal  300nF -> f_res 39595 Hz -> floor 41575 Hz  (PLL_MIN 42000 PASSES)
C -5%      285nF -> f_res 40624 Hz -> floor 42655 Hz  (PLL_MIN 42000 FAILS by  655 Hz)
C -10%     270nF -> f_res 41737 Hz -> floor 43824 Hz  (PLL_MIN 42000 FAILS by 1824 Hz)
```

`c_tank1`/`c_tank2`'s MPN, `FKP1T031507G00JSSD` (WIMA FKP 1), decodes against
WIMA's own ordering table (cross-checked against two independent hostings,
Mouser rev 01.19 and WIMA rev 03.26, and against `docs/hardware/BOM.md`
§1.4's independent prior decode of the same MPN) to **±5% tolerance** --
the `J` in the trailing `00JSSD`, not the `G` earlier in the fixed base
code. That is not a 0%-tolerance part, and the shipped 42000 Hz floor sat
below the resonance a real -5%-down capacitor produces. See
`docs/evidence/2026-07-29-pll-floor-cap-tolerance.md` for the full arithmetic,
independently recomputed and cross-checked against the gate's own printed
output.

PR #413's fix: declare `c_tank_tolerance = 0.05` in `elec/src/main.ato`,
worst-case `C` in `derive_zvs_floor()` alongside `L`, and raise
`PLL_MIN_FREQ_HZ` from 42000 to 43000 -- the smallest round kHz at or above
the corrected 42655 Hz floor. The 1800 W operating point (`f_switching =
47000 Hz`) keeps 1.157x ZVS margin against the corrected worst case, more
margin than the pre-fix state had at the old floor (1.061x).

## The tell: rigor on one term is more dangerous than rigor on none

A derivation that worst-cases *no* inputs reads as unfinished -- the next
reviewer knows to check it. A derivation that worst-cases *some* inputs, with
an explicit comment explaining why, reads as *finished*. The presence of
careful tolerance reasoning on `L` is exactly what made the missing
reasoning on `C` invisible: anyone scanning `main.ato` for "did we handle
tolerances here" found a well-argued yes and stopped looking, because the
question felt answered. It was answered for one of the two symmetric terms
in the same square root.

This is a sharper version of the failure this project already named in
`docs/solutions/design-patterns/resonant-tank-only-loaded-inductance-resonates-2026-07-28.md`:
there, two *wrong* values canceled and looked right by coincidence. Here,
one *correctly*-handled term made an *unhandled* term look handled by
association. Neither is visible from reading the conclusion; both require
naming every input on the right-hand side and checking it individually.

## What to do instead

**Enumerate every quantity on the right-hand side of a safety-relevant
formula, and mark each one explicitly**, as one of:

- **worst-cased** -- with the direction stated (why the minimum, or the
  maximum, is the hazardous end for this quantity in this formula) and the
  tolerance value cited to its source (an MPN decode, a datasheet, a
  declared spec);
- **nominal-by-justification** -- with a stated reason the nominal value is
  safe to use here (e.g. the quantity is measured per-unit at test time and
  cannot silently drift, or its tolerance is provably non-hazardous in this
  direction);
- **not-applicable** -- with a one-line reason it doesn't enter the hazard
  direction (e.g. it only ever pushes the result away from the boundary).

**Silence is the defect.** `c_tank_total` was none of the three -- it had no
tolerance reasoning attached at all, worst-cased or otherwise, and that
absence was unreadable as a gap precisely because the sibling term (`L`) had
a filled-in, correct-looking answer sitting right next to it.

**Treat "we already worst-case this formula" as a claim about specific named
terms, not the formula as a whole.** "The gate worst-cases the tank" is true
and was also incomplete; "the gate worst-cases `L_loaded` and, since
2026-07-29, `C`" is the same claim made falsifiable.

**When adding a new tolerance to an existing derivation (as PR #413 did),
check every other term in the same formula before adding just the one you
came to fix.** The task that produced PR #413 was scoped to the capacitor;
the discipline that would have caught this earlier is asking, for any
formula under a square root or a product, "what else is under here."

## What this does NOT invalidate

The **300 nF tank capacitance** and the **88 uH × 0.68 loaded-inductance
pair** are settled, established independently in
`docs/solutions/design-patterns/resonant-tank-only-loaded-inductance-resonates-2026-07-28.md`,
and untouched by this fix -- PR #413 changes how the floor is *derived* from
those committed values, not the values themselves. Nor does this reopen the
tank capacitor's AC-current-rating finding in
`docs/solutions/best-practices/verify-the-binding-axis-not-the-headline-rating-2026-07-28.md`;
that is a different binding constraint (thermal dissipation) on the same
part, orthogonal to its tolerance percentage.

The compile-time `_Static_assert`-style guard in `pll_control.c`
(`PLL_MIN_FREQ_HZ*100 >= DEFAULT_RESONANT_FREQ_HZ_INT*105`) is unaffected and
remains the weaker, nominal-resonance check it always was;
`scripts/check_pll_range_consistency.py` is the authority per its own module
comment, and this finding concerns that gate specifically.

## Detection

`scripts/check_pll_range_consistency.py` check 5 (`derive_zvs_floor()`) now
worst-cases both `L` and `C` together, and
`scripts/tests/test_check_pll_range_consistency.py` gained
`TestCapacitorToleranceWorstCase`, including
`test_regression_to_nominal_c_is_caught_by_the_floor_check` -- a test that
asserts the *old*, L-only floor (`PLL_MIN_FREQ_HZ = 42000`) is now correctly
flagged as a violation, so any future edit that silently reverts `C` to
nominal in the derivation fails that test immediately (74/74 tests passing
after the change, up from 59; 15 new).

There is no general mechanized check for "every input to this formula has an
explicit worst-case/nominal/n-a marking" across the codebase, and a naive one
(e.g. requiring a comment near every constant) would produce noise divorced
from whether the marking is *correct*. What is tractable, and is the
concrete ask of this doc: when writing or reviewing a derivation like this
one, list the formula's inputs before writing the worst-case logic, and
require the list to be complete before the code that implements it is
considered done. `derive_zvs_floor()`'s own docstring now states which two
quantities (`L`, `C`) are worst-cased and which one (`l_pan_loaded_ratio`) is
treated as exact -- see
`docs/hardware/TANK_COIL_SPECIFICATION.md` §8 item 0, which names that
remaining gap explicitly rather than leaving it silent.
