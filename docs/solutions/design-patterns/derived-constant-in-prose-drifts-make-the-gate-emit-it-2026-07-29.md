---
title: "A derived constant that lives in prose will drift -- make the gate emit it, not just check it"
date: "2026-07-29"
category: design-patterns
module: hardware_design
problem_type: design_pattern
component: hardware_design
severity: critical
applies_when:
  - "a human-facing document states a numeric threshold derived from values elsewhere under version control"
  - "the number is a supply-chain acceptance criterion -- something a buyer or incoming-inspection process checks a delivered part against"
  - "the derivation has more than one committed input, especially inputs that can move independently and in different directions"
  - "an acceptance test is specified as a ratio between two measured quantities rather than an absolute threshold on one of them"
  - "a doc and a gate both encode the same physical relationship and nothing cross-checks them"
  - "deciding whether to hand-derive a spec number once versus deriving it from a script every time it's read"
tags:
  - derived-constants
  - documentation-drift
  - acceptance-testing
  - ratio-vs-absolute-threshold
  - ci-gate-design
  - supply-chain-spec
  - single-source-of-truth
---

# A derived constant that lives in prose will drift -- make the gate emit it, not just check it

## Context

`docs/hardware/TANK_COIL_SPECIFICATION.md` carries an incoming-inspection
threshold for the purchased induction coil: `L_loaded >= <value> uH` is
requirement #3, the criterion a buyer checks a delivered coil against before
accepting it. It is a genuine supply-chain acceptance criterion, hand-derived
and correct when first written (PR #411, `feat/tank-coil-specification`).

It is a function of four separate committed values --
`l_tank_assumed`, `l_pan_loaded_ratio`, the L and C tolerances, and
`PLL_MIN_FREQ_HZ` -- via

```
f_res_max_guarded = PLL_MIN_FREQ_HZ / ZVS_MARGIN_MIN
L_loaded_min       = 1 / ((2*pi*f_res_max_guarded)**2 * C_worst)
```

Nothing connected the prose sentence in the doc to any of the five inputs on
its right-hand side. It went wrong twice at once, in PR #413
(`fix/pll-floor-cap-tolerance`): the threshold had been derived at **nominal
C** (see
`docs/solutions/best-practices/worst-case-every-term-in-the-formula-not-just-the-one-you-thought-of-2026-07-29.md`
for that half), and separately `PLL_MIN_FREQ_HZ` itself moved (42000 ->
43000 in the same change).

## Why a reviewer cannot catch this by inspection

The two error directions pull opposite ways, and that is what makes the
staleness unfixable by eyeballing the number:

- **Raising `PLL_MIN_FREQ_HZ` relaxes the coil requirement.** A higher floor
  tolerates a higher minimum resonance, which a *higher* `L_loaded_min`
  would guard -- no, the algebra runs the other way in this formula:
  `L_loaded_min` scales as `1/f_res_max_guarded^2`, so a higher floor
  frequency actually *lowers* the required `L_loaded_min` (a stiffer floor
  guards against a higher resonance, which needs less inductance to avoid).
- **Worst-casing `C` tightens the coil requirement.** A lower worst-case `C`
  raises `f_res_max_guarded` for the same floor, which raises the required
  `L_loaded_min`.

A reviewer checking "did the floor change get reflected in the coil spec"
sees the floor went up and might reasonably expect the coil requirement to
tighten -- and stop there, satisfied. A reviewer checking "did the
capacitor-tolerance change get reflected in the coil spec" sees it should
tighten and, if they only check that direction, might not notice the floor
change pulling the other way. Either check in isolation produces a
plausible-looking confirmation. Only recomputing the actual number catches
that the two moved together to net **52.77 uH -> 53.00 uH**, a small shift
that hides exactly how easily the two effects could have summed to something
far more wrong. The gate added in PR #413 (see Detection, below) is what
makes recomputation the default instead of an occasional audit.

## The other failure this push found: a ratio test cannot protect an absolute threshold

Before PR #413, the coil's acceptance test (from
`docs/evidence/2026-07-28-coil-selection-research.md` §5.1) was specified as
a **ratio**: `L_loaded >= 0.60 * L_unloaded`. `TANK_COIL_SPECIFICATION.md`
§2 works the counterexample explicitly:

```
L_unloaded = 79.2 uH   (-10%, still inside the +/-10% spec)
ratio      = 0.60      (passes the ratio screen exactly)
L_loaded   = 47.52 uH
f_res      = 42152 Hz
required PLL floor = 1.05 x 42152 = 44260 Hz
PLL_MIN_FREQ_HZ    = 43000 Hz          <- BELOW resonance
```

That coil passes requirement #1 (unloaded inductance in tolerance) and
passes a bare 0.60 ratio screen, and still resonates above the firmware's
declared legal frequency range -- the hard-switching, IGBT-destroying regime
`docs/evidence/2026-07-29-pll-floor-above-resonance.md` exists to keep the
firmware out of. The two screens are individually satisfiable and jointly
insufficient because the quantity that actually matters -- absolute loaded
inductance -- is their *product* with `L_unloaded`, and a ratio test can hold
across the entire range of `L_unloaded` while the product still crosses the
line.

This is **a type error, not a tuning error**. No choice of ratio threshold
fixes it, because a ratio is invariant to where `L_unloaded` sits inside its
own tolerance band, and the resonance is not. `TANK_COIL_SPECIFICATION.md`
now states the absolute `L_loaded >= 53.00 uH` as the binding requirement
(#3) and keeps the ratio (#3b, `>= 0.60`) only as a secondary coupling-quality
screen -- a coil that clears #3 only because its unloaded inductance sits at
the top of tolerance has weak coupling and won't repeat on a different pan,
which the ratio is good at catching. It is retained for that purpose, not as
the acceptance gate.

## The fix

PR #413 added check 8 to `scripts/check_pll_range_consistency.py`: the gate
computes `L_loaded_min` itself, from `PLL_MIN_FREQ_HZ`, `ZVS_MARGIN_MIN`,
`c_tank_total`, and `c_tank_tolerance` -- the same committed constants that
already feed the PLL floor derivation -- then parses
`TANK_COIL_SPECIFICATION.md`'s own `` `L_loaded >= <value> uH` is requirement
#3 `` sentence by exact anchor and **fails the build** if the two disagree
by more than a 0.01 uH rounding allowance. The doc stays human-readable -- a
buyer still reads one number and one procedure -- but the number can no
longer silently diverge from the constants it is a function of.

`scripts/tests/test_check_pll_range_consistency.py` gained
`TestCoilAcceptanceThresholdMirror` to cover this. `docs/hardware/BOM.md`
§1.4's own cross-reference to the same threshold was updated in the same
change, because it is a second parallel copy of the same number and would
otherwise have drifted independently of the doc the gate actually checks.

## The general pattern

**A constant that a human must act on, derived from values under version
control, needs a gate that re-derives it and cross-checks the acted-upon
copy.** The doc is an *output* of the build, not a parallel source of truth
that happens to usually agree with it. Anywhere a spec, a BOM note, or a
runbook states a number that is actually `f(committed_constant_1,
committed_constant_2, ...)`, the number will eventually be read by a human
who trusts it and by a machine that could have recomputed it -- and only one
of those two will notice when an upstream constant moves.

## Say the cost honestly

This gate works by **parsing prose** -- a fixed anchor string
(`` `L_loaded >= <value> uH` is requirement #3 ``) inside a markdown
document. That is brittle in a way a pure-code check is not: rewording the
sentence, reformatting the table, or moving the number into a different
paragraph breaks the parser, not just the value it protects. This project
has no machine-readable spec format for `TANK_COIL_SPECIFICATION.md`, so the
alternative to prose-parsing was no check at all.

**Pay this cost when the constant is safety-relevant, human-actioned, and a
function of multiple independently-movable inputs** -- exactly the coil
threshold here: a wrong number causes physical hardware damage, a person
(not another program) is the one who reads and acts on it, and it depends on
five separate committed values that this push already demonstrated can move
in opposite directions on the same day.

**Don't pay it** for constants that are single-input (staleness is visible
on sight -- "this says 88uH and modules.ato says 90uH" needs no derivation to
catch), not human-actioned (a value only ever read by another program should
just be computed at read time, with no prose copy to drift), or not
safety-relevant (a stale convenience number in a doc is an annoyance, not a
hazard, and the parsing brittleness is not worth it). `main.ato`'s own
`l_tank_assumed` vs `modules.ato`'s `inductor_conn` value (check 7) is the
simpler, single-input version of this same idea and needs no prose parsing
because both sides are code.

## What this does NOT invalidate

The **300 nF tank capacitance** and the **88 uH x 0.68 loaded-inductance
pair** are settled
(`docs/solutions/design-patterns/resonant-tank-only-loaded-inductance-resonates-2026-07-28.md`)
and untouched here; this finding is about how the *acceptance threshold
derived from them* is kept in sync, not about the values themselves. The
ratio screen (#3b, `>= 0.60`) is not eliminated -- it remains a genuinely
useful secondary check for coupling quality, demoted from binding criterion
to secondary screen, not removed.

`l_pan_loaded_ratio` (0.68) still has **no declared tolerance** and is
treated as exact by both the PLL floor derivation and check 8 --
`TANK_COIL_SPECIFICATION.md` §8 item 0 names this as the one remaining open
gap the 2026-07-29 fix did not close, and it is not reopened or resolved by
either doc in this pair.

## Detection

`scripts/check_pll_range_consistency.py` check 8 (see
`derive_zvs_floor()` and the coil-acceptance-mirror logic in the same
module) is the gate: it prints the derived `L_loaded_min`, parses
`TANK_COIL_SPECIFICATION.md`'s stated value, and turns a mismatch into a
`GateError` rather than a skipped check. `TestCoilAcceptanceThresholdMirror`
in `scripts/tests/test_check_pll_range_consistency.py` covers it directly.

Heads-up left in the same evidence trail
(`docs/evidence/2026-07-29-pll-floor-cap-tolerance.md` §6): PR #410 (held,
re-sources the tank capacitors to a +/-10% part) will, when merged, raise
`c_tank_tolerance` from 0.05 to 0.10 and make check 5 (and therefore check 8)
fail again until `PLL_MIN_FREQ_HZ` is re-raised -- roughly to 44000 Hz, to be
re-derived at merge time rather than assumed. That future failure is the
gate doing exactly its job, not a regression to work around.
