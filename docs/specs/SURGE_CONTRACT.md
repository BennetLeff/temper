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
| Generator source impedance | 2 Ω differential; **12 Ω common mode** (10 Ω external + 2 Ω) | **sourced** — ST AN4275 |
| **Differential (L–N)** | **1 kV**, 2 Ω → prospective short-circuit **500 A** | **adopted** |
| **Common mode (L–PE, N–PE)** | **2 kV**, 12 Ω → prospective short-circuit **167 A** | **adopted** |
| Coupling modes in scope | differential (L–N) and common mode (L–PE, N–PE) | **adopted** |
| Polarity / count | both polarities, per the test method | to confirm against the standard |
| Acceptance criterion | no safety hazard, no component damage, full function restored without operator action | **project-adopted**; the standard's performance criterion to be confirmed |

**These are prospective SHORT-CIRCUIT currents, not device currents.** A MOV clamps,
so the current through it is *lower* than the prospective value and is set by where
its V–I curve meets the generator's load line. For this board the MOV carries
~56 % of the 500 A prospective (see §4). The prospective figure sizes the *test
setup*; the device current sizes the *part*.

Prospective current is `V_OC / Z`. ST AN4275 Table 2 gives the standard's own
values: 2 Ω → 500 A at 1 kV; **12 Ω → 167 A at 2 kV**. The common-mode figure is
**not** 1,000 A — that would apply the differential impedance to a common-mode
level. (ST AN4275: "The 12 Ω (10 Ω + 2 Ω) impedance represents the source impedance
of the low-voltage power supply network and ground (common mode).")

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
**common-mode (L–PE, N–PE) surge is not clamped at all** — the Y-caps provide the
return path but no clamp. The common-mode case is therefore an **insulation and
current-path** question, not a clamping one, and is assessed on that basis in
`zapote/power-entry/surge/README.md`. Absence of a clamp does **not** by itself
require adding one.

Two corrections to earlier statements in this document, recorded because both were
wrong in the same direction — overstating what the datasheet supports:

- The captured **395 V is a MAXIMUM at 50 A** — an *upper* bound at that current.
  It bounds nothing at any higher current, in either direction. An earlier revision
  of this document called it "a lower bound for any current above 50 A"; that
  inference had already been withdrawn once in this work and was reintroduced here
  in error.
- The **500 A is the prospective short-circuit current**, not the MOV current. The
  MOV current is lower and is determined jointly with the clamp (§4).

## 4. Design obligations this contract creates

1. **The MOV clamp must be known at the current the surge actually drives through
   it — which is not 500 A.** The captured 395 V is a **maximum at 50 A**; it
   bounds nothing above 50 A in either direction, because the V–I characteristic
   rises with current but its shape above 50 A is not tabulated. Resolving this
   required the device's V–I curve, and the operating point where that curve meets
   the generator's load line. **Done — see
   `zapote/power-entry/surge/README.md`**: the MOV carries ~56 % of the prospective
   current, clamping at ~443 V (typical curve) to ~454 V (curve scaled to its
   tabulated maximum).
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

**The clamp above 50 A was not bounded by the datasheet.** The datasheet tabulates
one clamp point, 395 V **maximum** at 50 A, and carries the V–I characteristic only
as a multi-curve family chart — an earlier automated trace of which was rejected as
an unreliable instrument. It has since been read exactly, from the PDF's **vector**
paths, and validated against the datasheet's own tabulated maxima for three
consecutive parts; the loaded calculation follows. See
`zapote/power-entry/surge/`. How the 275 V figure arose is not established, but the
adjacent 275 VAC X2-capacitor row in `GROUNDING_EMI_STRATEGY.md` is a likely origin.

## 6. Basis and status — what is adopted versus sourced

Being explicit here is the whole point of committing this document.

**Sourced** (a document establishes it): the MOV ratings and clamp in §3, from the
captured LA-series datasheet; the controller limits, from the TEA2209T datasheet;
the generator impedances and the prospective-current table, from **ST AN4275**
(`DocID024389 Rev 1`, Table 2 and the differential/common-mode set-up text).

**Adopted** (a project decision, not a verified reading): the IEC 61000-4-5 test
method, the 1.2/50 µs / 8/20 µs waveform, the **1 kV differential / 2 kV
common-mode levels**, and the acceptance criterion. The levels previously appeared
only in a curriculum checklist
(`docs/architecture/induction_curriculum.md`), not in a requirements document.
Adopting them here makes them a design target with a stated basis.

**A deliberate deviation must be labelled.** The standard's impedance for a
power-line common-mode test is **12 Ω**; imposing 2 Ω common mode instead would be
a more severe *over-test* and must be recorded as such rather than presented as the
standard's requirement. No such deviation is adopted here.

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
| ~~MOV clamp at the surge current~~ | **DONE** — vector-extracted V–I curve + loaded calculation, `zapote/power-entry/surge/` |
| MOV energy margin at the committed event | **DONE for the differential case** (~3.5 J absorbed; peak current 16× below I_TM). Not established for common mode |
| Common-mode disposition | an insulation and current-path assessment (`zapote/power-entry/surge/README.md` §CM): needs the Y-cap impulse rating captured and the CM return path stated |
| Standard clause and level | the applicable standard text, for the product class and market |
| Bridge/device class | **partially resolved**: the differential clamp (~454 V worst case) leaves 1.32× margin on the 600 V class |

## 8. What this contract does not cover

**The internal capacitor-discharge fault is a different problem and is not in
scope.** That loop stores ~179 J in 2240.47 µF and discharges through failed
short-circuited devices; it never reaches the MOV terminals, and no MOV clamp
figure bounds it. It is addressed — or left unqualified — under power-entry
protection, which remains **explicitly unqualified** pending a defensible
protection choice and its qualification plan.
