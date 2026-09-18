# Coordinator receipt — AR-MOV attempt-001

Date: 2026-09-18
Attempt: `.../runs/2026-09-17-pfc-campaign/AR-MOV/attempt-001/`
Verdict: **ACCEPTED_CONDITIONAL**, with one critical caveat: the clamp at the
surge current is unknown, so the voltage verdict cannot be settled from this
source.

## Admission

Dispatch ADMITTED; handback **NOT COUNTED AS A VALIDATED RUN** (no checker
issued, per `ADMISSION.md`). Retained as evidence.

## The clamp, with its conditions

**V150LA10AP** (Littelfuse LA Series, 14 mm disc): **VC = 395 V maximum at
IPK = 50 A, 8/20 µs, 25 °C**, from the LA Series datasheet, revision 2024-09-16,
page 2. Rating basis: ITM 4500 A (8/20 µs), WTM 45 J (10/1000 µs), VNOM
216-264 V. Captured as a manufacturer PDF via an Internet Archive snapshot after
the manufacturer returned 403; the non-PDF mirror attempt and the 403s are all
retained as failures.

## The critical caveat

**395 V is an UPPER bound, and only at 50 A.** The datasheet's `VC = 395 V
maximum at IPK = 50 A` says the device clamps at *no more than* 395 V at 50 A.
It is **not** a lower bound at any current: a device could clamp at 350 V at 50 A
and 380 V at a higher current while satisfying both statements, so the clamp at
the surge current **cannot be bounded from this specification in either
direction**. It is **unknown**.

Two further limits on the arithmetic:

- **The MOV current is not the generator's prospective current.** ~500 A is the
  provisional generator short-circuit figure; the current through a
  line-to-neutral MOV during a surge depends on coupling and source impedance,
  and is not established here.
- The 1.52× margin is evaluated at 395 V, which is an **upper bound at 50 A**, so
  it is the most favourable reading rather than a conservative one — and the
  margin at the real surge current is unknown either way.

The attempt set `clamp_at_provisional_product_surge_v = null` rather than
extrapolating, and rejected an automated Figure-10 trace when it hopped between
adjacent curves. That is the right call. This receipt's earlier claim that 395 V
is "a lower bound" and that margins "are necessarily smaller" had the
datasheet's bound direction backwards and is withdrawn.

## Derived stresses, each against its own limit

- **MOSFETs:** 600 V class → 1.52× against the sourced 395 V. Thresholds: 1.36×
  at 440 V, 1.20× at 500 V, **1.00× at 600 V**. The required rating follows from
  the clamped **terminal** voltage — not the controller's 700 V limit, not the
  400 V bus.
- **Controller (own limits 440 V operating / 700 V transient):** at 395 V the
  L/R/VR nodes sit at **0.898 of the operating limit** and 0.564 of the transient
  limit. Above ~440 V they **exceed the operating limit during the surge**. A
  higher-rated MOSFET does not lower that node.

Both are evaluated at 395 V. Neither the clamp value nor the margin at the real
surge current is established, in either direction.

## Surge contract: provisional, as required

IEC 61000-4-5 (1 kV L-L / 2 kV L-PE) is **assumed, not adopted** — no committed
requirement document names it. The MOV is line-to-neutral, so **L-PE common mode
is not clamped** (INDETERMINATE). Settling it needs a released requirement
naming the standard, level and waveform, plus a V-I value at the real MOV
current.

## Internal fault kept separate

Stated explicitly: a line-surge MOV across L-N **does not resolve** the
internally powered boost-switch-short discharge loop (179.238 J, 2240.47 µF;
the MOV terminals are not on that loop). That remains AR-PROTECT's question and
no MOV clamp is admissible there.

## Single gating input

**The V150LA10AP clamp voltage at the actual MOV current of the surge event** —
an 8/20 µs V-I value at a few hundred amps, under a **committed** surge
requirement rather than the datasheet's 50 A test point. Until it is known, both
the MOSFET rating margin and the controller node-stress verdict cannot be
evaluated at the real surge current.

## Net effect

600 V remains **a candidate rating and not a completed qualification** — the
sourced clamp gives 1.52× at 50 A, and the margin at the real surge current is
unknown. The device question and the surge contract are now both waiting on the
same two things: a committed surge requirement, and a clamp value at the current
that requirement produces.
