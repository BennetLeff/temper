---
title: "Paying down 74 vacuous assertions: 12 → 27 circuit-coupled, 5 now VIOLATED, 4 INDETERMINATE"
date: "2026-08-20"
category: best-practices
module: elec
problem_type: best_practice
component: electrical-assertions
severity: critical
applies_when:
  - "an assertion gate finds a large fraction of a design's assertions cannot be falsified by any circuit change"
  - "deciding whether to add derived quantities to a .ato module so its own assertions can catch a real defect"
  - "a component rating (fuse, choke, relay contact) has never been checked against an actual computed circuit draw"
  - "a gate-driver or divider margin looks fine in prose but has never been asserted against the real resistor/component values"
tags:
  - ato-assertions
  - vacuity-gate
  - circuit-coupling
  - fuse-rating
  - gate-driver-current
  - ovp-divider
  - derived-quantities
---

# Paying down 74 vacuous assertions: 12 → 27 circuit-coupled, 5 now VIOLATED, 4 INDETERMINATE

## Verdict, up front

The vacuity gate (PR #1392, `gate/ato-assertion-vacuity`) inventoried 86
electrical assertions in `elec/src/*.ato` and found 74 could not be
falsified by any circuit change (`NO_CIRCUIT_COUPLING`), 3 more were
effectively vacuous ties (`TIE_MARGIN`), and only 12 were genuinely coupled
to circuit values. The paydown (`fix/ato-assertion-vacuity-paydown`, commit
`9fe4134a5`) derived new circuit-coupled assertions from the design's actual
component values instead of hand-typed literals, taking the count from 86
assertions (12 circuit-coupled) to **88 assertions (27 circuit-coupled)**.
Run against the real design, **5 of those now fail (VIOLATED)** and 4 more
cannot be resolved either way (INDETERMINATE) — each one a real, previously
invisible defect or open question.

## The before/after count

| | Total assertions | Circuit-coupled | `NO_CIRCUIT_COUPLING` | `TIE_MARGIN` |
|---|---:|---:|---:|---:|
| Before (PR #1392 inventory) | 86 | 12 | 74 | 3 |
| After (paydown, `9fe4134a5`) | 88 | **27** | 60 | 0 |

Run against real circuit values, the 27 circuit-coupled assertions split
**5 VIOLATED / 4 INDETERMINATE / 18 pass.**

```
gh pr view 1392
git show 9fe4134a5 -s
```

## What the 5 VIOLATED assertions found

| # | Assertion | Rated/expected | Actual demand | Margin |
|---|---|---:|---:|---|
| 1 | Fuse F1 rating vs. real branch draw | 16 A | **28.81 A** | Fuse undersized by ~1.8× against the design's own worst-case draw |
| 2 | Choke L1 rating vs. same draw | 16 A | 28.81 A | Same margin |
| 3 | Relay K1 IEC contact rating vs. same draw | 20 A | 28.81 A | Exceeds even K1's higher UL508 rating class boundary in this check |
| 4 | UCC21550 gate-driver source current vs. `rg_on = 2.2 Ω` demand | 4 A | **6.8–9.1 A** | 1.7–2.3× over the driver's own rated source current |
| 5 | OVP bus-ADC divider output vs. 3.3 V rail | ≤3.3 V | **3.360 V** | 60 mV over the rail at worst-case ±1% resistor tolerance, at the nominal half-bus |

**On item 3:** two related but distinct figures exist, and neither is simply
"wrong." **28.81 A** is the stiffest-line-case *simulated* rms draw from the
time-domain doubler model in
`docs/evidence/2026-08-19-input-stage-power-ceiling.md`
(`analysis/input-stage-power-ceiling`, commit `fe9cf6752`); the paydown's own
prose and code comments round this to "28.8 A" throughout. **28.83 A** is the
*exact value the landed assertion itself computes*: `i_line_rms_max =
i_line_real_equiv * k_line_rms` with `i_line_real_equiv = (1800W/0.90)/120V
= 16.667 A` and `k_line_rms = 1.73` (`elec/src/modules.ato:734`, commit
`9fe4134a5`) — `16.6667 * 1.73 = 28.8333`, i.e. **28.83 A to two decimals**,
computed live rather than found as a typed literal (`git log --all -p
-S"28.83"` finds zero hits because it is never written as a string — it is
the runtime value of a derived field). The two figures agree to within 0.1%
because `k_line_rms = 1.73` was chosen from the simulation's own
stiffest-line ratio. Either **28.81 A** (simulated) or **28.83 A** (the
assertion's own derived value) is a correct citation for "what F1/L1/K1 are
checked against"; **28.8 A** is the repo's own rounding of the former.

**On item 4:** `elec/src/modules.ato` already carried the diagnosis in
prose before this assertion existed, in the `GateDriveHS` module:
*"Rg = 2.2Ω: 15V/2.2Ω ≈ 6.8A peak demand, UCC21550 limits to 4A source"* and,
more conservatively, *"the first-instant demand is 20.1V/2.2Ω = 9.1A"* — so
the 6.8–9.1 A range is exactly what the design's own comments already said,
just never asserted against the driver's rating. (Note: the paydown
commit's own *commit message* — not the code — separately states "6.5-7.2A"
for the same quantity; that figure is not corroborated anywhere else in the
diff and looks like a drafting slip in the commit message rather than a
real number. Use 6.8–9.1 A, which matches the code comment.)

**On item 5:** *"OVPComparator's bus ADC divider, written against its real
resistors instead of copies of their values, reaches 3.360V at worst-case
+/-1% -- 60mV over the 3.3V rail, at the nominal half-bus."* (commit
`9fe4134a5`)

```
git show 9fe4134a5 -- elec/src/modules.ato
git log -1 --format=%B 9fe4134a5
```

## The pattern behind items 1–3: a rating checked against nothing

Fuse, choke, and relay ratings existed as component values in the schematic
for as long as the design has existed, but nothing in `main.ato` or
`modules.ato` had ever asserted them against a derived circuit draw — the
28.81 A figure only exists because a separate analysis
(`analysis/input-stage-power-ceiling`) computed it. The vacuity paydown's
contribution is not the 28.81 A number itself; it is **wiring that number
into an assertion that will fail again automatically** if a future change
moves the draw further from the rated components, instead of requiring a
fresh from-scratch analysis to notice.

## Related documentation cross-references retired by this paydown

Commit `3e7a2626c` (same session) retires two prose cross-references in
`elec/src/*.ato` that the paydown invalidated — comments that pointed at
now-superseded assumptions once the derived assertions existed. See that
commit directly for which lines.

```
git show 3e7a2626c -s
```

## What remains open

- **60 of 88 assertions are still `NO_CIRCUIT_COUPLING`.** This paydown
  closed the highest-value subset (fuse/choke/relay/gate-driver/OVP-divider),
  not the full 74. The remaining count and which assertions they are is not
  re-inventoried in this document — re-run the vacuity gate to get a current
  list.
- **The 4 INDETERMINATE assertions** are not itemized in the commit message
  with the same detail as the 5 VIOLATED ones; a reader picking this up
  should re-run the paydown's own reporting to get their identities before
  assuming they are understood.
- **None of the 5 VIOLATED findings has a landed fix** as of this
  document — F1/L1/K1 are still rated below the design's own computed draw,
  the UCC21550's gate resistor is still 2.2 Ω, and the OVP divider still
  reaches 3.360 V. This document records that the gate now catches these
  correctly; it does not claim they are resolved.
- `fix/ato-assertion-vacuity-paydown` and `gate/ato-assertion-vacuity` are
  not merged to main as of this writing (PR #1392 is open).

## Related

- `docs/solutions/architecture-patterns/checks-that-cannot-fail-catalogue-2026-08-20.md` — row 6 is this document's starting point (74/86 unfalsifiable assertions).
- `docs/solutions/logic-errors/power-stage-1800w-rating-unreachable-2026-08-20.md` — `p_output_max`'s fix landed in the same commit (`9fe4134a5`) as part of this paydown.

## Verification notes

Every figure above was checked directly against `gh pr view 1392` and
`git show 9fe4134a5` (including the full commit message and the `.ato`
diff), read-only. The 28.83 A figure from the session's own prior summary
does not appear as a written literal anywhere in the repository (`git log
--all -p -S"28.83"`: zero hits), but it is reproduced by hand-evaluating the
landed assertion's own formula (`i_line_real_equiv * k_line_rms` =
`16.6667 * 1.73` = `28.8333`) — recorded above as a derived, not a found,
figure, alongside the 28.81 A simulated figure the repo's own prose cites.
