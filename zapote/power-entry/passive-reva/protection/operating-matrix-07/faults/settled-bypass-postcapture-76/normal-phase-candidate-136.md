# BYPASS-NEG normal-prefix and crest-phase candidate

**Status: PARENT_REVIEW_PENDING; accepted=false.** This is a bounded diagnostic
candidate for the completed BYPASS-NEG capture. It does not establish a
protection result, hardware behavior, or acceptance of the fault case. The
overall observation remains live/pending, and the legacy pass is unrun.

## Capture and identity

The immutable archive has 32,287,070 rows, 5,351,164,676 bytes, endpoint
`0.662 s`, and SHA-256
`75f444f8e422e445c2e5d65f21760af1658f0b14f05dcd088d1c80cd2b87b0a1`. Source
and run-parameter identities, together with hashes of every small report,
are recorded in `normal-phase-candidate-136.json`.

## Event-aware normal prefix

The exact selector retained 30,111,244 rows through
`0.6499999880006718 s` for the `<=0.65 s` prefix. The endpoint gap is
`1.1999328197731529e-8 s` (below the `1e-6 s` bound), and the detected fault
edge is `0.6541666661706754 s`. The displayed metrics window is
`0.5999999880006718..0.6499999880006718 s`.

Reported values are Vrms 120.000000 V, Irms 7.320158 A, input power
868.399907 W, load power 773.441525 W, PF 0.988594, and VB mean 383.374390 V
(381.315709..385.385643 V). The three cycle means give a derived drift
fraction of `0.0026890160140442057` (the report displays 0.002689). Armed and
on fractions are both 1.0; all report-only engineering screens are zero.
The inductor peak (30.636523 A) is retained as a report-only observation.

The repeated-time audit found 42 equal-time groups, 57 repeated intervals,
maximum group size 3, no missing right rows, logic changes, or boundary
groups, and retained all original rows. Rust completed without a backwards-
time rejection; the displayed `backwards=0` is not an independent counter
claim.

## Crest phase diagnostic

The declared crest interval is `[0.65, 0.6583333333333] s` with tolerance
0.01. The report has one event edge, initial marker low, strict neighbors on
both sides, and a positive peak. The observed source-spread D bound is
`2.8421709430404014e-14 V`; the representative criterion error is
`1.7585035537258278e-14`, so the sufficient bound is reported as passing.
This is a phase diagnostic only; it does not override any fault or protection
screen.

## Retained failure and pending work

The authoritative prior all-row node screen remains failed: VD peak
`651.1730124191079 V` exceeds the 500 V limit. This prefix/phase packet does
not reinterpret or waive that failure. Legacy analysis, overall observation,
parent normal-prefix review, and final fault disposition remain pending.

