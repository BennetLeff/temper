# Electrical-model review: F2-open sensing/drive claim

Procedure: `zapote/skills/electrical-model-review/SKILL.md`.
Claim under review (as corrected 2026-09-19): with F2 open, the controller
keeps sensing the stranded bank while the boost stage can still energize the
disconnected diode-side output. An earlier wording had this backwards
(controller "blind to the bank"); the wiring refutes that, and this review
records the corrected claim's standing — it does not accept it.

## 1. Path traced (step 1)

From `candidate/source-manifest.json` bridge nets (49 groups), post-open,
U9/U10 healthy:

- Drive loop: mains → `AC_L/N_RECTIFIED_INPUT` → U1 bridge →
  `RECTIFIER_L/R` → `RECTIFIER_POSITIVE` → U8.1 → U8.2 (`a1`) →
  U9.2 → U9.3 → `PFC_BUS_MINUS` → bridge return; and U10.1 (`a1`) →
  U10.2 (`BOOST_DIODE_POSITIVE`) → U40.1 (c_hf) → U40.2
  (`PFC_BUS_MINUS`). Every element conducts given healthy/on states.
- Sense island: U20.1 (`PFC_BUS_PLUS_390V`) → divider chain → U25.2
  (`PFC_BUS_MINUS`); U66.2 sits on the bank net with U66.1 across the open.
  Sensing connects; it measures a node the boost can no longer drive.

## 2. Fault-state separation (failure class 2)

| State | Conducts / blocks | Finding |
|---|---|---|
| F2 open, U9 healthy/on, U10 healthy | Boost keeps pumping `BOOST_DIODE_POSITIVE`/c_hf; controller reads stranded bank | Claim's core case; no interrupting device is named for continued drive — correctly, none is claimed |
| F2 open, U9 healthy/off | Drive stops only if commanded off; detection signal + latency budget unstated | **Null**: off-command path has no evidence rung |
| U9 failed-short (F2 open or closed) | Gate commands cannot open the path | No shutdown credit may be taken; none is |
| U10 failed-short + U9 failed-short | Internal bank loop via proposed F2 location | Coordination unestablished (Q2); F2 is "part selected", not demonstrated |
| U9 failed-short, U10 healthy | Line-fed path through F1, F2 uninvolved | F2-open analysis does not cover it; must not be cited for it (class separation) |

## 3. Numbers and their conditions (failure classes 1, 3)

- c_hf 470 nF / ~0.0376 J at 400 V: **illustrative** (nominal voltage, not
  maximum credible bus; tolerance/temperature excluded). It may not size
  withstand or clearing inputs (class 3).
- Divider ~0.4 mA: illustrative DC estimate at nominal 400 V / 1 MΩ, not a
  pulsed-fuse input and not a measurement.
- No bound-direction claims are made in the corrected wording; no class-1
  reversal found. The honest entries are the nulls below.

## 4. Independent check (step 5)

None exists for post-open control behavior: no manufacturer model,
measurement, or independent implementation of TEA2209T + UCC28180 response to
a stranded-bank/open-output condition is on file. Stated explicitly rather
than covered by self-consistency.

## 5. Machine checks run (step 7)

`zapote-fault-loop` on the compiled manifest nets (`fault-loop/`):

- Drive-loop assignment (U8/U9/U10/U40/U1, illustrative 1 A): CONSISTENT.
- Current through open U66 in the same loop: INCONSISTENT, correctly
  rejected (1 of 2 terminals on loop) — valid counterexample retained.
- Sense-island assignment (U20, illustrative 0.4 mA): CONSISTENT.

Per the skill, these are necessary-connectivity results only: they do not
prove a conductive path, device state, direction, or distribution, and a
passing check does not make the claim true. No evidence ledger exists for
the F2-open claim, so `zapote-claims` has nothing to run against; building
one is future work, not part of this review.

## 6. Nulls and what resolves them

- Post-open diode-side peak voltage / c_hf stress: null → needs Q5
  measurement on the exact assembly (startup, brownout, F2-open transient).
- U9 off-command detection + latency after F2 opens: null → needs a stated
  budget plus test.
- F2 clearing/coordination for any loop above: null → Q1/Q2.
- Controller response to a stranded bank reading: null → no independent
  source; hardware observation only.

## Verdict

The corrected claim survives review as a **correctly stated, unqualified
fault assessment**: path traced, states separated, numbers labelled
illustrative, no interruption credited, checks run with a retained
counterexample. It is not accepted as a qualified prediction — completion
evidence stands at "part selected" for F2 and "none" for post-open control
behavior. No procurement, fabrication, or powered-operation consequence
follows from this review.
