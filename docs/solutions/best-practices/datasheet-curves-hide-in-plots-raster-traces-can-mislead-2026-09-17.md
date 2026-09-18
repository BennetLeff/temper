---
title: "A text extractor's silence is not an absent curve, and a raster trace can be less accurate than the effect it must resolve"
date: "2026-09-17"
category: best-practices
module: zapote
problem_type: best_practice
component: measurement_evidence
severity: high
applies_when:
  - "concluding that a datasheet, standard, or drawing lacks a curve, table, figure, or dimension because a text extraction did not return it"
  - "choosing a digitization method for a datasheet plot without first establishing whether the plot is a vector path or an embedded raster image"
  - "tracing a curve off a rendered figure and feeding it into a loss, derating, or timing model"
  - "the decision a traced curve must support is smaller than the trace's own run-to-run spread"
tags:
  - datasheet-extraction
  - pdftotext-drops-plots
  - raster-vs-vector
  - curve-digitization
  - reading-error-budget
  - measurement-instrument
  - absence-is-not-evidence
---

# A text extractor's silence is not an absent curve, and a raster trace can be less accurate than the effect it must resolve

## Context

A planning cycle set out to replace an input bridge's assumed forward-drop
band with the manufacturer's real `V_F(I)` curve. The model's own source
comment recorded why the band was an assumption:

> The retained datasheet has no forward-drop curve and no high-temperature
> point, so a band stays labelled an assumption.

That statement was false. Page 3 of the retained PDF carries **Fig. 2,
"Typical Forward Characteristics, Per Element"**. The claim had been made from
a `pdftotext` extraction, which returns the page's numeric table and silently
drops its plots. "The source has no curve" was really "my extractor showed me
no curve".

Three things then went wrong in sequence, and each is worth separating:

**First, the figure's medium was asserted without being checked.** A research
pass reported the curve as a vector path and concluded that an earlier
vector-extraction recipe transferred. It does not. `pdfimages -list` reports
**four image objects** on page 3; `pdftocairo -svg` emits four `<image>`
elements and only glyph-outline paths. The plots are embedded raster bitmaps.
The recipe depended on sampling a vector path's coordinates.

**Second, the raster trace was not reproducible.** Three tracer variants over
the same 600 dpi render, the same detected frame (1460 px per 2.0 V, 368 px
per decade) and the same masked label boxes returned materially different
answers at 12.5 A:

| tracer | V_F at 12.5 A |
| --- | ---: |
| longest-dark-run | 0.833 V |
| monotonicity-filtered | 0.961 V |
| continuity-tracked | **1.100 V** |

**Third, the source itself contained the check that caught it.** The
datasheet's own table gives `V_F` **maximum 1.05 V at I_F = 12.5 A**. A
*typical* curve can never exceed the maximum at the same condition, so the
third variant is provably wrong — no external oracle was needed to see it.

## The pattern

**An absence observed through a lossy reader is not an absence in the
artifact.** A text extractor is a measurement instrument with a known blind
spot for anything that is not text — plots, dimension drawings, raster images.
Its silence is evidence about the extractor, not about the document. This is
the same class as this repo's standing *"absence is not evidence"* rule, one
layer down: there the question was whether a file exists on any ref; here it is
whether a figure exists in bytes you already hold.

**A trace's accuracy has to be compared to the effect it must resolve, before
it is used.** In this case the bridge term was 28.30 W at 2 × 1.05 V, so a
rectified mean current of ~13.5 A and a sensitivity of ~27 W per volt — about
**2.7 W per 0.1 V**. The comparison the curve was needed for was the
bridge-versus-switch gap of 28.30 W against 26.76 W, about **1.5 W**, which
corresponds to roughly **0.055 V**. The observed run-to-run spread of 0.27 V
was therefore about five times the effect being measured. A trace like that
cannot answer the question it was commissioned for, however carefully it is
averaged.

**A source's own stated bound is a free correctness oracle.** The maximum-V_F
row is not merely a specification; it is an inequality any typical curve must
satisfy. It cost nothing to apply and it failed one of three candidate traces
immediately — the single most useful check in the whole exercise, and it came
from the same document that had been misread as containing no curve.

## Guidance

1. **Before concluding a source lacks a figure, render it.** Use a renderer
   that draws images (`pdftoppm`, `pdftocairo -png`), not a text extractor, and
   look at the page. Check embedded object counts (`pdfimages -list`) when a
   claim about figures matters.
2. **Establish the figure's medium before choosing a method.** Raster and
   vector require different extraction; a recipe that works for one silently
   misreads the other. `pdftocairo -svg` emitting `<image>` elements and only
   short glyph paths is the tell for raster.
3. **Give a trace an acceptance inequality from its own source.** Typical
   curves must not exceed the part's maximum at the same condition. Reject any
   trace that violates it rather than averaging it away.
4. **State a reading error, and compare it to the decision margin before using
   the trace.** If the spread is comparable to or larger than the difference the
   trace must resolve, the trace is not the instrument for the question — find a
   better source (a vector original, a CSV, a manufacturer model) or measure the
   part.
5. **Record the trace's source test conditions on every derived number.**
   Forward-drop curves are per-element, at a stated junction temperature and
   pulse width; a value read without them cannot be compared to a different
   condition's value.
6. **Do not delete the historical evidence that carries the old phrasing.**
   When the false premise is corrected, correct it at the source and in
   artifacts the change actually regenerates. Provenance-pinned evidence and
   archived validation runs record what the tool said at a revision; rewriting
   them falsifies the record.

## Related

- `docs/solutions/best-practices/measurement-convention-must-be-stated-2026-07-28.md`
  — its appended update is the same failure one document earlier: a dimension
  that never entered the PDF text layer, resolved by rendering and
  pixel-calibrating two independent ways.
- `docs/solutions/best-practices/verify-the-binding-axis-not-the-headline-rating-2026-07-28.md`
  — "curves require intent": a figure needs to be identified as the constraint
  before it can be read.
- `docs/solutions/best-practices/calibration-point-must-equal-design-point-2026-07-28.md`
  — a value is only valid at the input it was established against.
- `docs/plans/2026-09-17-001-feat-pfc-bridge-loss-pinning-plan.md` — the plan
  whose first unit this learning came from; U1 now carries the maximum-voltage
  gate and an execution note recording the abandonment.
