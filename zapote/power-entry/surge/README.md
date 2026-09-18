# Loaded differential surge on V150LA10AP

**Question.** Does `V150LA10AP` protect the proposed bridge and controller under the
adopted differential surge (IEC 61000-4-5, 1 kV, combination wave, 2 Ω generator)?

**Answer.** **Yes, against the transient limits — conditionally, and with the clamp
landing just above the controller's continuous-operating rating.**

| | typical curve | scaled to the tabulated maximum |
| --- | ---: | ---: |
| MOV operating point at surge peak | 278.7 A / **442.6 V** | 273.0 A / **454.0 V** |
| share of the 500 A prospective current | 56 % | 55 % |
| absorbed energy | 3.55 J | 3.49 J |
| peak current vs `I_TM` = 4500 A (8/20 µs) | 16.1× margin | 16.5× margin |

Against the applicable limits, worst case:

| Limit | Value | Result |
| --- | ---: | --- |
| TEA2209T continuous **operating** | 440 V | **1.032 — EXCEEDS** |
| TEA2209T mains **transient** | 700 V | 0.649 — passes |
| proposed 600 V bridge class | 600 V | 1.32× margin |

The MOV itself is comfortable: it carries just over half the prospective current
and absorbs ~3.5 J, with peak current 16× below its rating. **The binding
constraint is the clamp voltage against the controller, not the MOV's own
ratings.**

The clamp (~443–454 V) sits **above the TEA2209T's 440 V continuous-operating
rating** and well below its 700 V mains-transient rating. During a ~50 µs surge the
applicable figure is the transient rating — the datasheet's own note says surges
must be limited below 700 V. That is the comparison made above, and it passes. But
the margin against the *operating* line is only −3 %, so if the vendor treats 440 V
as binding during any excursion, this needs their confirmation. **It is stated
rather than smoothed over.**

## Why the answer is not "the clamp at 500 A"

Two corrections to the earlier framing, both of which changed the result:

1. **500 A is the prospective SHORT-CIRCUIT current, not the MOV current.** It is
   `V_OC / Z` = 1000 V / 2 Ω, i.e. what would flow into a short. A MOV clamps, so
   the current through it is lower and must be solved jointly with the voltage:
   the operating point is where the device's V–I curve meets the generator's load
   line `V = V_OC − Z·I`. Here that is ~279 A at ~443 V — the MOV carries **56 %**
   of the prospective current. Sizing the part from 500 A would overstate it by
   ~1.8×.
2. **395 V is a MAXIMUM at 50 A — an upper bound at that current, and nothing at
   any other.** The datasheet tabulates one clamp point. Calling it "a lower bound
   for any current above 50 A" is wrong: the clamp rises with current, but 395 V
   neither bounds it from below nor from above above 50 A. That inference had
   already been withdrawn once in this work and was reintroduced in the contract;
   it is now corrected there too.

## The curve, and why it can be trusted

The datasheet carries the V–I characteristics only as **multi-curve family
charts**. An earlier automated trace was rejected as an unreliable instrument — it
hopped between the adjacent V130/V140/V150/V175 curves.

The figures are **vector**, not raster (only page 1 of the PDF is an image), so the
curve is *read*, not traced: Bézier paths are extracted and chained, and the axes
are calibrated from their own printed tick labels (log-log; ~25.4 px/decade in
current, ~91.4 px/decade in volts, reproducing every tick to ~1 px).

The read is then validated against the datasheet's own tabulated **maximum** clamp
for three consecutive parts — and each identified curve falls just *below* its
stated maximum, as a typical curve must:

| Identified curve | read at 50 A | datasheet max at 50 A |
| --- | ---: | ---: |
| V130LA10A(P) | 333.7 V | 340 V |
| V140LA10A(P) | 346.8 V | 360 V |
| **V150LA10A(P)** | **383.1 V** | **395 V** |

That agreement is three independent checks in one: the curve *identification*, the
axis *calibration*, and the *direction* of the typical-vs-maximum relationship.

The "scaled to the tabulated maximum" column multiplies the whole curve by
395/383.1. **That is an assumption about curve shape, not a datasheet statement** —
it is a worst-case bracket, labelled as such.

## Method and reproduction

```
zapote/power-entry/surge/
  extract_la_vi_curve.py   # PDF -> data/v150la10a_vi_curve.json   (needs pymupdf)
  loaded_surge.py          # curve + generator -> operating point   (stdlib only)
  data/v150la10a_vi_curve.json
```

Inputs: `V_OC` = 1000 V, `Z` = 2 Ω (the committed differential contract), and the
captured LA-series datasheet from
`../loss-budget/campaign/runs/2026-09-17-pfc-campaign/AR-MOV/attempt-001/raw/`.

The generator is modelled as the 1.2/50 µs open-circuit voltage behind 2 Ω, which
is the physically consistent picture for the combination-wave generator: the
open-circuit voltage drives the current, and the MOV's clamping sets it. The fit is
validated against the waveform's own defining markers, and the script **refuses to
report an energy** if they do not converge.

**A cross-check that was dropped, and why.** An 8/20 µs current-wave model was
attempted and removed: a two-exponential cannot reproduce the standard's 8/20
markers under the 1.25 front-time convention (the narrowest achievable
front/half-value ratio is ~3.8 against the 2.5 required). Rather than force a fit,
the check was dropped and this is recorded. The energy figure is therefore from the
1.2/50 voltage-source model only.

## Common mode — an insulation and current-path question

The committed common-mode level is **2 kV at 12 Ω → 167 A prospective** (ST AN4275
Table 2; see the contract §2 — this is not 1,000 A).

**The MOV does not clamp this mode** — it is line-to-neutral only. That is a fact,
not a defect. **Absence of a clamp does not automatically require adding one**, and
the withstanding route is the one to test:

- **Current path.** The common-mode current returns through the Y-caps: the EMI
  filter's 2.2 nF Y2 line-to-PE capacitors and `Y_CAP_PE`
  (`B81123C1562M000`, TDK 5.6 nF **Y1 500 VAC**, doubler midpoint to PE).
- **Where the voltage lands.** At the surge's dominant frequency the Y-caps present
  roughly 1.0 kΩ against a 12 Ω source, so **the great majority of the 2 kV appears
  across the Y-caps** and very little across the source. *(Single-frequency
  estimate at ~20 kHz; the surge is broadband, so treat it as an estimate, not a
  bound.)*
- **Whether that withstands.** The Y-caps carry an impulse-withstand classification
  (Y1 per IEC 60384-14), and the mains-to-SELV barrier is **reinforced**, hipot
  tested at **3000 V AC for 1 minute** (`REQ-SAFETY`), which exceeds the 2 kV
  common-mode level.

**What is NOT established:** the Y-caps' actual impulse-withstand rating (the
datasheet has not been captured), and a computed statement of where the common-mode
current returns and what fraction reaches the SELV side. Until those exist, the
common-mode verdict is **not "protected" and not "must add a clamp"** — it is
**plausibly handled by withstanding, to be demonstrated**.

## What this does not establish

- **Not hardware qualification.** No bench or powered test; everything here is
  computation over a captured datasheet.
- **Not a compliance statement.** The standard clause and level remain unconfirmed
  (contract §6). No standard text was opened.
- **Not the internal fault case.** A line surge MOV across L–N says nothing about
  the internally powered capacitor-discharge fault; that is power-entry protection,
  which remains explicitly unqualified.
- **Not the common-mode verdict** — see above.
