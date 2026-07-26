---
title: "Derived documents lose qualifiers, and then get reasoned from — the STRATEGY.md summary table that dropped peak/RMS and a recovery threshold"
date: "2026-07-26"
category: best-practices
module: docs
problem_type: best_practice
component: documentation
severity: medium
applies_when:
  - "writing a summary table that condenses a spec table from another document"
  - "reasoning about a threshold, tolerance, or direction using a one-line summary rather than the source table"
  - "a spec value appears in more than one document and the shorter one is quoted more often"
  - "reviewing a design or test-criteria question and the answer 'seems ambiguous' from the doc in hand"
tags:
  - qualifier-loss
  - derived-document
  - single-source-of-truth
  - spec-ambiguity
  - peak-vs-rms
  - falling-vs-rising
  - summary-table
---

# Derived documents lose qualifiers, and then get reasoned from

## Context

`docs/FUNCTIONAL_TEST_CRITERIA.md` §2.1 specifies primary OCP as "50A Peak"
with a trip threshold of "45 - 55 A." §2.4 specifies UVLO with two separate
columns: "Trip Threshold (Falling)" and "Recovery (Rising)" — Logic (3.3V)
falling at "< 2.9 V", recovering at "> 3.0 V".

`docs/STRATEGY.md`'s gate summary table condensed both:

```
OCP-01 | Primary OCP 45-55A, <1µs                | FUNCTIONAL_TEST_CRITERIA.md §2.1
UVL-02 | Logic UVLO <2.9V                          | §2.4
```

Peak/RMS is gone from the OCP-01 row. Direction is gone from the UVL-02 row,
and the "Recovery (Rising)" column has no representation at all. Both
omissions were reasoned from later, by different people, on different days:

- **OCP-01**: `docs/STRATEGY.md`'s own follow-on analysis flagged it directly
  — "`OCP-01: 45-55A` does not say peak or RMS. Read as peak the
  implementation is compliant; read as RMS it trips at 35.4 A, below the 45 A
  minimum" — and had to resolve the ambiguity by cross-checking OCP-02's
  55–65 A window against IGBT ratings (78–92 A peak would be incoherent) to
  infer peak was intended, calling it "the same ambiguity as UVL-02" and
  noting it "should be written into `FUNCTIONAL_TEST_CRITERIA.md` rather than
  inferred a third time."
- **UVL-02**: `docs/hardware/UVLO_TRACEABILITY.md` records a reviewer who,
  working from the "<2.9 V" summary form, read it as "must trip before the
  rail falls below 2.9 V" — under which a 2.93 V typical part passes. Applying
  the source document's own direction convention consistently (falling
  threshold, not a loose ceiling) reverses the verdict: 2.93 V typ / 3.00 V
  max is *above* 2.9 V, so the gate does not cleanly pass. The correction
  required going back to the two-column source table, not the summary row.

The information that resolved both cases was present in
`FUNCTIONAL_TEST_CRITERIA.md` the entire time. Nothing needed to be measured
or derived — it needed to be read from the row that still had the qualifier.

## Guidance

1. **A summary table is a derived document. Treat it as a cache, not a
   source.** Every value in it must resolve to a citation the reader can
   open. `docs/STRATEGY.md`'s summary rows already do this (`§2.1`, `§2.4`) —
   the discipline that was missing is using the citation, not just printing
   it.
2. **When collapsing a multi-column spec into one line, name what you
   dropped, or don't drop it.** "45-55A" without "Peak" silently discards a
   qualifier that changes the value by a factor tied to the load's crest
   factor. "Trip Threshold (Falling) / Recovery (Rising)" collapsed to a
   single "<2.9V" discards which direction the inequality applies to.
3. **Before reasoning from a summary, open the source table it cites.** Both
   corrections in this incident were resolved by going back to
   `FUNCTIONAL_TEST_CRITERIA.md`'s original columns. If the summary is
   ambiguous on a question the source table answers unambiguously, the
   summary is not evidence of an unresolved spec — it is evidence of a lossy
   derivation.
4. **The same ambiguity recurring twice across independent analyses is a
   signal to fix the source, not to re-derive the answer a third time.**
   `docs/STRATEGY.md` names this explicitly for OCP-01 and cross-references
   UVL-02 as "the same ambiguity" — the fix is amending
   `FUNCTIONAL_TEST_CRITERIA.md` to spell out peak/RMS at the point of
   definition, once, rather than leaving every downstream reader to
   re-infer it from IGBT ratings or supervisor datasheets.
5. **A qualifier is not decoration.** "Peak" vs "RMS" on 45-55A is the
   difference between a compliant design (peak) and a design that trips 10 A
   below its stated minimum on a typical 1.8 kW load (RMS, per
   `docs/STRATEGY.md`'s own 38.9 A RMS derivation at the 55 A peak corner).
   "Falling" vs "loose ceiling" on <2.9V is the difference between a passing
   gate and a marginal fail. Neither is safely elidable in a summary meant to
   be reasoned from.

## Why This Matters

Two independent analyses — written on different days, reasoning about
different subsystems (OCP and UVLO) — both derived a wrong-leaning
interpretation from the same document's summary table, and both corrections
required returning to the same source table that had never lost the
qualifier. The cost was not that the information was unknown; it was that the
document doing the summarizing was read as if it were the specification, and
the specification was one file away the entire time. This is a durable
failure shape for any project that maintains a condensed status table
alongside a detailed source-of-truth document: the condensed table gets read
far more often (it is the "at a glance" artifact), so a lossy compression
introduced once gets reasoned from many times before anyone notices the
source table said something more precise.

## When to Apply

- Writing or reviewing any summary/status table that cites a more detailed
  source document — audit every row for a dropped unit, direction, or
  qualifier (peak/RMS, min/max, falling/rising, ±, before/after).
- Before treating an ambiguity found in a summary document as a genuine spec
  gap — check whether the cited source resolves it.
- When the same kind of ambiguity is flagged twice in independent analyses —
  that is the trigger to fix the source document once, not to leave two
  correct-but-derived resolutions standing in two different places.
- When writing the source spec itself: state the qualifier at the point of
  definition (`FUNCTIONAL_TEST_CRITERIA.md` already does this correctly —
  the loss happened only in the derived summary).

## Examples

```
Source  (docs/FUNCTIONAL_TEST_CRITERIA.md §2.1):
  | Primary OCP | 50A Peak | 45 - 55 A | < 1 µs |

Derived (docs/STRATEGY.md gate table):
  OCP-01 | Primary OCP 45-55A, <1µs | §2.1
                        ^^^^^^ "Peak" dropped

Source  (docs/FUNCTIONAL_TEST_CRITERIA.md §2.4):
  | Logic (3.3V) | < 2.9 V (Falling) | > 3.0 V (Recovery, Rising) |

Derived (docs/STRATEGY.md gate table):
  UVL-02 | Logic UVLO <2.9V | §2.4
                    ^^^^^^^^ direction + entire Recovery column dropped
```

## Related

- `docs/STRATEGY.md` — the OCP-01 peak/RMS self-correction ("Spec ambiguity,
  again") and the gate summary table where the qualifier was dropped
- `docs/hardware/UVLO_TRACEABILITY.md` — the UVL-02 direction-of-inequality
  correction, including the reviewer's initial misreading and its resolution
- `docs/FUNCTIONAL_TEST_CRITERIA.md` §2.1, §2.4 — the source table that never
  lost the qualifier
- `docs/solutions/best-practices/multi-document-requirements-review-patterns-2026-07-23.md`
  — a sibling precision failure in derived documents: "identical results" vs
  "within tolerance" language drift across requirements docs

---

## The payoff: three designs falsified by restoring one column

Added after this document was first written, because it is the strongest
evidence for the lesson and it landed later the same day.

Restoring the dropped qualifiers to `docs/STRATEGY.md` immediately invalidated
part of **three protection fixes designed and verified earlier that day**:

| Gate | Spec, once restored | As designed against the lossy table |
|---|---|---|
| THM-01 | trip 85 °C, **recovery 70 °C** → 15 °C hysteresis | trip 84.9 °C, release 79.2 °C → **5.6 °C** |
| THM-02 | trip 120 °C, **recovery 100 °C** → 20 °C hysteresis | trip 120.3 °C, release 113.7 °C → **6.6 °C** |
| OVP-01 | 390–410 V trip, **hysteresis 10–20 V** | **no hysteresis at all** |

The trip points were correct in all three. The *release* behaviour was not —
and the engineer never knew it was specified, because the summary table had
dropped the recovery and hysteresis columns entirely. Hysteresis was therefore
chosen by judgement against a table that had silently removed the constraint
governing it.

This is what makes the failure mode expensive rather than merely untidy. The
work was careful: values hand-derived, tolerance-checked, simulated, and
cross-verified. **None of that helps when the requirement being satisfied is
an abridged one.**

A fourth instance surfaced at the same time: `FUNCTIONAL_TEST_CRITERIA.md`
§1.2 specifies a **200 W ±25%** power tier with no corresponding gate in the
summary at all — an omitted requirement rather than an abridged one, which the
same audit caught only because it was comparing row by row against the source.

**Practical test for whether a summary is safe to reason from:** can a reader
derive a *design* from it, or only recognise a topic? If the former is
intended, every column that constrains an implementation has to survive the
abridgement — and the cheapest way to know is to diff the summary against its
source row by row, which is exactly the audit that found all of this.
