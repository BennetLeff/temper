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
its V–I curve meets the generator's load line. In the retained fixed-resistance
source sensitivity, the MOV carries ~56 % of the 500 A prospective (see §4);
that is not a qualified event current. The prospective figure characterizes the
test setup; device assessment needs the loaded waveform.

Prospective current is `V_OC / Z`. ST AN4275 Table 2 gives the standard's own
values: 2 Ω → 500 A at 1 kV; **12 Ω → 167 A at 2 kV**. The common-mode figure is
**not** 1,000 A — that would apply the differential impedance to a common-mode
level. (ST AN4275: "The 12 Ω (10 Ω + 2 Ω) impedance represents the source impedance
of the low-voltage power supply network and ground (common mode).")

**Board context.** 120 V RMS ±10% (`REQ-SYS-01`), so the steady-state line peak is
132 × √2 = **186.68 V**. The surge environment sits far above this; it is a
transient requirement, not a steady-state one.

## 3. What is clamped on this board today

On the assessed PFC candidate the part is **U7 = `V150LA10AP`** (authored instance
`mov`, Littelfuse LA series, 14 mm disc),
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
   required the device's V–I curve and a loaded source model. A conditional
   screen now exists in `zapote/power-entry/surge/README.md`: approximately
   443 V / 279 A on the typical curve and 454 V / 273 A on an assumed scaled
   curve. Neither curve scaling nor a fixed 2 Ω source establishes a worst-case
   combination-wave response. **Qualification remains open.**
2. **The bounded clamp must sit below the downstream surge limits**, which are the
   binding constraints — not the 400 V bus:
   - TEA2209T: **440 V operating / 700 V mains-transient** at the relevant pins
     (Rev 1.1 p.8); p.12 states surges must be limited below 700 V.
   - Active-bridge candidate, 600 V class: 1.52× margin at 395 V, falling to
     **1.00× at a 600 V clamp**.
   A higher-rated MOSFET does **not** lower the node voltage; the clamp does.
3. **Common-mode must be resolved.** The development choice is insulation and
   return-path withstand on the actual PFC assembly, with qualification open.
   No PE clamp is selected at this stage; see `zapote/power-entry/CLOSEOUT.md`, Q4.
4. **MOV energy/current survival must be established** for the committed event.
   The 4500 A catalog value applies at 8/20 µs. The retained approximately
   3.5 J calculation uses a voltage-source waveform without a verified 8/20
   short-circuit response, and does not close this obligation.

## 5. Known conflicts this contract forces into the open

**The earlier requirement and the fitted part disagreed.** REQ-EMC-01
previously listed 275 V / 10 kA, while the assessed board uses V150LA10AP,
a 150 V RMS MCOV device. The requirement was reconciled to the selected part.
MCOV alone does not specify another MOV's clamp voltage; do not derive a
replacement-part verdict from that rating alone. The original discrepancy's
cause is not established.

**The clamp above 50 A remains unbounded by the single tabulated point.**
Vector-path extraction supports a conditional curve calculation, not a guaranteed
maximum characteristic. See `zapote/power-entry/surge/README.md` for the source
model's limits and `zapote/power-entry/CLOSEOUT.md` for qualification.

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
| Loaded clamp and terminal stress | Conditional screen available; close with a calibrated combination-wave model/test including actual terminals, mains phase and wiring (closeout Q3) |
| MOV energy/current survival | Open; the retained voltage-source energy is not a qualified event or waveform-matched rating comparison (Q3) |
| Common-mode disposition | Development route chosen: insulation/return-path withstand. Qualify the actual U41/PE/HOT-interface assembly (Q4) |
| Standard clause and level | Confirm applicable product/market standard and test details before compliance submission |
| Bridge/device class | 600 V remains a candidate; the assumed 454 V result is not a worst-case voltage bound |

## 8. What this contract does not cover

**The internal capacitor-discharge fault is a different problem and is not in
scope.** That loop stores ~179 J in 2240.47 µF and discharges through failed
short-circuited devices; it never reaches the MOV terminals, and no MOV clamp
figure bounds it. It is addressed — or left unqualified — under power-entry
protection, which remains **explicitly unqualified** pending a defensible
protection choice and its qualification plan.
