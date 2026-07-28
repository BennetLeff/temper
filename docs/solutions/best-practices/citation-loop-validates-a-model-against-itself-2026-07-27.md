---
title: "A citation loop — validating a model against the uncited table it came from"
date: "2026-07-27"
category: best-practices
module: simulation
problem_type: best_practice
component: hardware_design
severity: high
applies_when:
  - "a design conclusion traces back through two or more documents/scripts before reaching its ultimate source"
  - "the same uncited table, constant, or figure appears in more than one file, independently"
  - "a downstream result is proposed as validation for the model that produced it"
  - "a per-material or per-condition table has no citation anywhere in its own file's history"
tags:
  - citation-loop
  - uncited-source
  - pan-load-model
  - self-validation
  - circular-evidence
  - tank-coil-specification
---

# A citation loop — validating a model against the uncited table it came from

## Context

`simulation/models/pan_load.sub`'s header carries a "PAN MATERIALS (typical
values at 30-40kHz)" table (Cast Iron/Stainless/Aluminum coupling and
resistance figures) with **no source ever given anywhere in the file's
history** — confirmed directly, and now flagged in the file itself:
`*** These per-material k/Rpan figures are UNCITED (no source ever given
anywhere in this file's history)`. Before 2026-07-27's correction pass,
that uncited table fed a three-hop chain with no independent source at any
link:

```
pan_load.sub's uncited header table
  -> run_zvs_sweep.py's PAN_PRESETS (literal Python constants,
     copied from the table, not read from it)
  -> sweep results (run_zvs_sweep.py, run_tank_coil_sweep.py)
  -> docs/hardware/TANK_COIL_SPECIFICATION.md's conclusions
     ("1800 W is unreachable at every L tested", implied tank Q of 143)
```

Separately, `docs/hardware/RESONANT_TANK_DESIGN.md` §3.1 carries its own
k/Rpan-by-material table — different numbers (Cast Iron 0.5–0.6 vs.
`pan_load.sub`'s 0.4–0.6; Aluminum 0.05–0.15 vs. 0.1–0.2) but the same
shape, same lack of citation, independently unsourced. Using either table
to "corroborate" the other, or using a sweep result derived from one to
validate the model that produced it, is not independent evidence — it is
the same unfounded number, laundered through a second file.

**This is distinct from
`docs/solutions/best-practices/derived-documents-lose-qualifiers-2026-07-26.md`.**
That doc is about lossy compression: a summary table drops a real
qualifier (peak/RMS, falling/rising) that its own cited source still
carries. Nothing here was ever *lost* — the header table's coupling
figures were carried forward faithfully, hop for hop. The defect is that
the chain is a cycle with no ground: no hop cites a measurement, a
datasheet, or a first-principles derivation; each hop cites the previous
hop, and the previous hop cites nothing. A perfectly faithful copy of an
unfounded number is still unfounded.

**Resolved same-day, in two passes** (`docs/evidence/2026-07-27-pan-model-correction.md`,
`docs/evidence/2026-07-27-pan-preset-correction.md`): `PANLOAD_TRANSFORMER`'s
`K`/`L2` defaults were re-derived from an independent, external source
(Infineon AN235020's measured loaded/unloaded inductance ratio on a real
stainless pan) rather than the uncited table, and `run_zvs_sweep.py`'s
`PAN_PRESETS` entries now each carry a source note citing either that
derivation or an explicit `ASSUMPTION` label — **none cite `pan_load.sub`
any longer**, closing the citation loop for the coupling coefficient `K`,
the parameter that most distinguishes one pan material from another. One
residual link remains, disclosed rather than hidden: the `stainless`
preset's `RPAN=10Ω` note still cites `pan_load.sub`'s own subcircuit
default as its anchor, because no independent RPAN measurement exists —
this is reported as a still-uncited value, not silently inherited.
`TANK_COIL_SPECIFICATION.md` itself was **not** updated in this pass and
still states "1800 W is unreachable at every L tested" — a conclusion the
correction's own re-derivation shows does not survive (§ below) — so the
loop's downstream end remains stale as of this writing.

## Guidance

1. **Before treating a table as evidence, trace it to a citation that is
   not another file in this project.** A datasheet, a measurement, a
   standard, or a first-principles derivation ends the chain; another
   script or document that "already has the number" does not, no matter
   how many hops separate them from the header table.
2. **A downstream result cannot validate the model that produced it.**
   Sweep results computed from `PAN_PRESETS`, which were copied from
   `pan_load.sub`'s uncited table, cannot be cited back as evidence the
   table is reasonable — that is exactly the loop. Independent validation
   requires a source outside the chain (here: Infineon AN235020, an
   external measurement of a different pan).
3. **The same unsourced table appearing in two files is not corroboration.**
   `pan_load.sub` and `RESONANT_TANK_DESIGN.md` carry different numbers for
   the same claimed quantity, both uncited — two guesses agreeing loosely
   in shape is not two independent measurements agreeing in value.
4. **When a correction reaches only part of a citation chain, say which
   part explicitly.** The 2026-07-27 fix closed the loop for `K` but left
   `RPAN=10Ω` citing the same subcircuit default it always did, for lack of
   any better source — flagged in the source note itself
   (`"RPAN=10 ohm (pan_load.sub's own single non-material-specific subckt
   default)"`), not silently carried forward as if it were now grounded.
5. **A model correction is not the same task as re-validating everything
   downstream of it.** Fixing `pan_load.sub`'s defaults did not, by itself,
   update `TANK_COIL_SPECIFICATION.md`'s conclusions — that document
   still asserts a result its own stated falsifier ("this recommendation
   fails if the pan model's coupling is not representative") now fires
   against. Closing a citation loop at its source and propagating the
   correction to every downstream conclusion are two separate, both
   necessary, steps.

## Why This Matters

A citation loop is more dangerous than an unlabeled guess, because it
*looks* like convergent evidence — three artifacts (a SPICE subcircuit, a
Python preset table, a specification document) all agreeing on the same
number. The agreement is real; the independence is not. Every hop in the
2026-07-27 chain was faithfully computed from the hop before it — no
arithmetic error, no lossy summary — which is exactly why the loop
persisted undetected: nothing about reading any single link looks wrong.
It took tracing the whole chain back to its origin, and finding nothing
there, to see that three files agreeing was one unfounded table counted
three times. The downstream cost was real: `TANK_COIL_SPECIFICATION.md`
concluded a design target (1800 W) was unreachable at every inductance
tested, based on a tank Q of 143 that the corrected model's own re-run
shows was a >10x overstatement — a real specification decision built on
the top of an uncited loop.

## When to Apply

- Before citing a table, constant, or figure as support for a design
  decision — trace it past every intermediate file to something that is
  not itself part of this project's own derivation chain.
- Before treating agreement between two documents/scripts as
  corroboration — check whether both ultimately cite the same, or no,
  original source.
- Before using a sweep, simulation, or measurement result to justify the
  model that generated it — identify what would count as independent
  evidence and confirm the result actually is that, not a restatement.
- When a correction fixes one link in a citation chain — explicitly check,
  and state, which downstream documents still assert conclusions from the
  pre-correction chain.

## Examples

```
# The loop, before 2026-07-27's correction:
pan_load.sub header table (uncited)
  --copied into-->  PAN_PRESETS (run_zvs_sweep.py)
  --feeds-->        sweep results
  --cited by-->     TANK_COIL_SPECIFICATION.md's "1800W unreachable" verdict

# Using the sweep results, or the spec doc, to argue the header table is
# "reasonable" closes the loop -- there is no link in this chain that
# points outside it.
```

```python
# AFTER -- each preset entry names an external source or an explicit
# assumption, never the file this correction started from (run_zvs_sweep.py):
(
    "stainless", 0.79, 10.0, PAN_L2_DEFAULT_H,
    "Infineon AN235020 (EVAL_2KW_SiC_IH app note), measured loaded/unloaded "
    "L-ratio 0.40 on a stainless stockpot, 90-150kHz. K=0.79/L2=218uH solved "
    "to jointly satisfy that ratio and the sqrt(f)-extrapolated R_eff~=2.2 "
    "ohm at 35kHz, holding RPAN=10 ohm (pan_load.sub's own single "
    "non-material-specific subckt default) fixed.",
    #                     ^^^^^^^^^^^^^^ still uncited -- disclosed, not hidden
),
```

## Related

- `docs/solutions/best-practices/derived-documents-lose-qualifiers-2026-07-26.md`
  — the sibling failure this is explicitly distinct from: lossy
  propagation of a real qualifier, versus a faithfully-propagated but
  ungrounded cycle.
- `docs/solutions/best-practices/correction-lands-on-dead-defaults-2026-07-27.md`
  — the second, independent defect found in the same file the same day:
  the `K`/`L2` correction to `pan_load.sub` was, on its own, inert for both
  official simulation harnesses.
- `docs/evidence/2026-07-27-pan-model-correction.md`,
  `docs/evidence/2026-07-27-pan-preset-correction.md` — the two-pass fix:
  the Infineon-anchored re-derivation and the harness-side preset
  correction that closes the citation loop for `K`/`L2`.
- `docs/evidence/2026-07-27-coil-pan-coupling-prior-art.md` — the
  literature search (Infineon AN235020, APHO2025) used as the external,
  outside-the-loop source.
- `simulation/models/pan_load.sub`, `docs/hardware/RESONANT_TANK_DESIGN.md` §3.1,
  `docs/hardware/TANK_COIL_SPECIFICATION.md` — the three files carrying the
  same claim; the last of these was not updated in the correction pass and
  still asserts the pre-correction conclusion.
