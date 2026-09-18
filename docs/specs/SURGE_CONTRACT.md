# Surge and transient environment contract — AC mains port

**Status:** COMMITTED (design target). **Date:** 2026-09-18.
**Authority:** this document. Entry point: `REQ-EMC-03` in `REQUIREMENTS.md`.
**Supersedes:** the *provisional* surge contract used by the AR-MOV and AR-PROTCKT
attempts, which marked the level "ASSUMED, not adopted" because it came from a
curriculum checklist rather than a requirement.

## 1. Why this document exists

Downstream decisions were blocked on a surge environment that nobody had adopted:

- **active rectifier** — worth building only if the bridge can be sized against a
  committed transient;
- **MOV selection** — the clamp must be known at the current the surge actually
  produces, not at a datasheet test point;
- **device ratings** — the clamped terminal voltage, not the 400 V bus, sets the
  required bridge and switch class.

Each was previously answered "provisional" or "unknown". This fixes the
environment so those become answerable. It does **not** by itself qualify any part.

## 2. The committed environment

| Field | Committed value | Status |
| --- | --- | --- |
| Test method | IEC 61000-4-5, combination wave | **adopted** — see §6 |
| Waveform | 1.2/50 µs open-circuit voltage, 8/20 µs short-circuit current | **adopted** |
| Generator source impedance | 2 Ω (combination-wave generator) | **sourced** — defining property of the test method |
| **Differential (L–N)** | **1 kV** → prospective **500 A** at 8/20 µs | **adopted** |
| **Common mode (L–PE, N–PE)** | **2 kV** → prospective **1000 A** at 8/20 µs | **adopted** |
| Coupling modes in scope | differential (L–N) and common mode (L–PE, N–PE) | **adopted** |
| Polarity / count | both polarities, per the test method | to confirm against the standard |
| Acceptance criterion | no safety hazard, no component damage, full function restored without operator action | **project-adopted**; the standard's performance criterion to be confirmed |

Prospective current is the generator's short-circuit current, `I = V_OC / Z_source`
= 1000 V / 2 Ω = **500 A**, and 2000 V / 2 Ω = **1000 A**.

**Board context.** 120 V RMS ±10% (`REQ-SYS-01`), so the steady-state line peak is
132 × √2 = **186.68 V**. The surge environment sits far above this; it is a
transient requirement, not a steady-state one.

## 3. What is clamped on this board today

The fitted part is **RV1 = `V150LA10AP`** (Littelfuse LA series, 14 mm disc),
wired **line-to-neutral only** (`fuse.p2 ~ mov.p1`, `mov.p2 ~ ac_n`). Its captured
ratings:

| Parameter | Value | Source |
| --- | --- | --- |
| Max clamp | **395 V at 50 A, 8/20 µs** (25 °C) | LA series datasheet p.2 |
| Nominal varistor voltage | 216–264 V at 1 mA DC | same |
| MCOV | **150 V RMS / 200 V DC** | same |
| Peak current I_TM | 4500 A (8/20 µs) | same |
| Energy W_TM | 45 J (10/1000 µs) | same |

**Consequence, stated plainly.** The MOV clamps the **differential** mode. The
**common-mode (L–PE, N–PE) surge is not clamped at all** — the Y2 capacitors
provide a path but no clamp. The L–PE case is therefore **INDETERMINATE**, and this
contract does not pretend otherwise.

## 4. Design obligations this contract creates

1. **The MOV clamp must be bounded — not merely asserted — at the committed
   current of 500 A (differential).** The captured 395 V is specified **at 50 A
   only**, and the V–I characteristic rises with current, so **395 V is a lower
   bound for any current above 50 A**. The clamp at 500 A is presently `null`.
2. **The bounded clamp must sit below the downstream surge limits**, which are the
   binding constraints — not the 400 V bus:
   - TEA2209T: **440 V operating / 700 V mains-transient** at the relevant pins
     (Rev 1.1 p.8); p.12 states surges must be limited below 700 V.
   - Active-bridge candidate, 600 V class: 1.52× margin at 395 V, falling to
     **1.00× at a 600 V clamp**.
   A higher-rated MOSFET does **not** lower the node voltage; the clamp does.
3. **Common-mode must be resolved** — either a clamp is fitted for L–PE/N–PE, or
   the mode is accepted as unclamped and recorded as an open qualification gap.
   That decision is deliberately **not** made here.
4. **MOV energy margin must be established** for the committed event. `I_TM =
   4500 A` suggests survival at 500 A, but that is not an energy calculation and
   is not treated as one.

## 5. Known conflicts this contract forces into the open

**The requirement and the fitted part disagree.**
`REQUIREMENTS.md` REQ-EMC-01 listed "MOV: **275 V**, 10 kA surge rating"; the
committed part is `V150LA10AP`, a **150 V RMS MCOV** varistor on a 132 V-max line.
These are not interchangeable: a 275 V MCOV part has a varistor voltage near 430 V
and would not conduct until well above that, so it would clamp the surge far higher
and would not protect a 440 V-limited controller. A 275 V MCOV MOV suits a 230 V
design, not this one. REQ-EMC-01 is corrected in the same change; how the
discrepancy arose is not established.

**The clamp at the committed current is unknown**, and it is the single input that
decides both open questions below. An automated trace of the datasheet's V–I figure
was attempted and **rejected as an unreliable instrument** (it hopped between
adjacent family curves); no digitised value is used.

## 6. Basis and status — what is adopted versus sourced

Being explicit here is the whole point of committing this document.

**Sourced** (a document establishes it): the MOV ratings and clamp in §3, from the
captured LA-series datasheet; the controller limits, from the TEA2209T datasheet;
the generator impedance, being a defining property of the combination-wave test.

**Adopted** (a project decision, not a verified reading): the IEC 61000-4-5 test
method, the 1.2/50 µs / 8/20 µs waveform, the **1 kV differential / 2 kV
common-mode levels**, and the acceptance criterion. The levels previously appeared
only in a curriculum checklist
(`docs/architecture/induction_curriculum.md`), not in a requirements document.
Adopting them here makes them a design target with a stated basis.

**To confirm.** The exact clause and level for this product class against the
applicable standard text. The standard chain for a US residential induction cooker
is a safety standard (`IEC 60335-2-6` / `UL 1026`) plus an EMC immunity standard
for household appliances (`EN 55014-2`, which invokes IEC 61000-4-5 for the surge
test); `REQUIREMENTS.md` §11 currently lists `EN 55014-1` only, which is emissions.
**No standard text was opened while writing this document**, and no claim here
should be read as a verified reading of one. The levels are adequate as a design
target; they must be confirmed before any compliance submission.

## 7. Open items, and what closes each

| Open item | Closed by |
| --- | --- |
| MOV clamp at 500 A | the V150LA10A(P) V–I curve read at the calculated current — a clean single-part curve or a measured clamp |
| MOV energy margin at the committed event | a waveform-based energy calculation once the clamp is known |
| Common-mode disposition | a design decision: fit an L–PE/N–PE clamp, or record the gap |
| Standard clause and level | the applicable standard text, for the product class and market |
| Bridge/device class | follows once the clamp is bounded |

## 8. What this contract does not cover

**The internal capacitor-discharge fault is a different problem and is not in
scope.** That loop stores ~179 J in 2240.47 µF and discharges through failed
short-circuited devices; it never reaches the MOV terminals, and no MOV clamp
figure bounds it. It is addressed — or left unqualified — under power-entry
protection, which remains **explicitly unqualified** pending a defensible
protection choice and its qualification plan.
