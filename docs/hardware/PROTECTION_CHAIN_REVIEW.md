# Protection Chain Design Review

**Date:** 2026-07-25
**Scope:** the seven protection gates in `docs/STRATEGY.md` plus IGBT
desaturation.
**Status:** analysis and recommendations. **No design files were changed.**

Every number below is derived from the committed values in
`elec/src/modules.ato` and reproduced by hand; simulated figures come from
`simulation/harness/`. All models are uncalibrated (`calibrated: false`) — no
bench data exists.

---

## Summary

> **Updated 2026-08-07** (correcting forward from the 2026-07-25 update
> below, which itself only covered OCP-01/THM-01). Since this document was
> last edited (2026-07-27 10:52, commit `866de677`): **OVP-01 fixed**
> 2026-07-27 18:19 (`75a708a8`, see the note under "OVP-01" below);
> **THM-02 designed and wired** 2026-07-26; **DESAT formally de-scoped**
> 2026-07-26 (19 BOM lines removed, not merely unpaid-for — see
> `docs/hardware/DESAT_DECISION_BRIEF.md`). **OCP-02 remains the one
> undesigned protection circuit**, blocked on a sensing-domain decision (an
> INA240 at `DC_BUS_RTN` would see ~170 V common-mode against its
> -4..+80 V rating). Nothing below has been validated on hardware — every
> figure in this document remains simulation-only, on uncalibrated models.

| Gate | Requirement | As committed | Disposition |
|---|---|---|---|
| OCP-01 | 45–55 A **Peak**, **< 1 µs** response | 37.6 A → **50.1 A** | **FIXED** — needed a new CT, not just a resistor |
| THM-01 | 85 °C, **recovery 70 °C** | trip **84.99 °C**, recovery **69.83 °C**, hysteresis **15.16 °C** | **FIXED** — resistor + ref divider, then `r_hyst` = 34.8 kΩ (`a4fb15dc`). Trip and recovery both within spec per `docs/evidence/2026-07-26-thm01-trip-point-sim.json` |
| OVP-01 | 390–410 V, **hysteresis 10–20 V** | 195 V sensed — **superseded, see note below** | **FIXED 2026-07-27 18:19**, commit `75a708a8` (Option C: re-referenced to `REF2025`'s fixed 2.5 V output). Simulated worst case 196.11–203.81 V trip, 8.58–8.90 V hysteresis, both inside the 195–205 V / 5–10 V windows including tempco at ΔT=60°C; see `docs/STRATEGY.md` Bottom line and `docs/evidence/2026-07-27-ovp01-ref2025-implementation.md` |
| OCP-02 | 55–65 A **Peak**, **< 5 µs** response | absent | **Needs design** — blocked on the INA240 sensing-domain decision (~170 V common-mode vs. -4..+80 V rating) |
| THM-02 | coil 120 °C, **recovery 100 °C** | **120.3 °C**, wired to a second `ThermalComparator` instance | **DESIGNED & WIRED 2026-07-26** |
| DESAT | (not a numbered gate) | **DE-SCOPED 2026-07-26** — 19 BOM lines removed, residual risk accepted in writing | **Resolved (de-scope), not merely undecided** — see `docs/hardware/DESAT_DECISION_BRIEF.md` |
| UVL-01 | **Falling** < 12.0 V / **Rising** > 13.0 V | UCC21550B internal | Document only |
| UVL-02 | **Falling** < 2.9 V / **Rising** > 3.0 V | ambiguous circuit | Identify intended circuit |

Three are one-part fixes (OCP-01, THM-01, OVP-01). THM-02 is designed and
wired. DESAT is resolved by de-scoping. **OCP-02 is the one remaining gate
that needs a circuit**, and it needs a sensing-domain decision before it can
be designed.

---

## OCP-01 — primary overcurrent

### As built

```
VCC 3V3 ──[3.2k]──┬──[10k]── GND      V_ref = 3.3 × 10/13.2 = 2.500 V
                  └── TLV3201 INN
CT 1:100 ── burden 6.65 Ω ── TLV3201 INP
```

Trip = V_ref × N / R_burden = 2.5 × 100 / 6.65 = **37.6 A** (simulated 37.611 A).

Raising the trip by raising V_ref is impossible: 50 A needs
50 × 6.65 / 100 = **3.325 V from a 3.3 V rail.**

### Recommendation — change the burden resistor only

**R_burden: 6.65 Ω → 4.99 Ω** (E96 standard).

| | |
|---|---|
| Trip | 2.5 × 100 / 4.99 = **50.10 A** — centred in the 45–55 A window |
| Worst case (±1 % divider, ±1 % burden) | **49.4 – 50.9 A** — comfortably inside spec |
| Continuous dissipation at 15 A primary | **0.112 W**, improved from 0.150 W |

Lowering the burden *reduces* continuous dissipation, so the existing 0.25 W
1206 part is no worse off. Fault-condition dissipation is 1.25 W for the
microseconds before the comparator trips — confirm the chosen part's pulse
rating, but this is not a continuous-rating problem.

This is a single line change in `elec/src/modules.ato` plus the matching BOM
entry (`BOM.md:102–103`, which currently disagrees with source anyway).

### OCP-01 — resolution

**The one-resistor fix above was wrong, and was reverted before being kept.**

A 4.99 Ω burden puts the trip at 50.1 A, but `components.ato` records that the
`CST2010-100L` **senses only to 47 A**. Above its rated current the core
saturates and the secondary under-reads, so the comparator could trip late or
not at all — a worse failure than tripping early. Checking the divider and
burden arithmetic without checking the sensor's range was the gap.

The conflict was structural, not a value error:

| R_burden | Trip | Worst case ±1% | |
|---|---|---|---|
| 5.36 Ω | 46.64 A | 46.0 – 47.3 A | exceeds CT |
| 5.49 Ω | 45.54 A | 44.9 – 46.2 A | below spec |

OCP-01 wants 45–55 A; the CT sensed to 47 A; tolerances closed the 45–47 A
overlap. **No E96 value satisfied both.**

**Resolved by changing the transformer** to the Coilcraft **CST3015-100ED**
(Document 1608-1):

| | CST2010-100L | CST3015-100ED |
|---|---|---|
| Sensed current | 47 A | **88 A** |
| Turns ratio | 1:100 | **1:100 — unchanged** |
| Isolation | 1500 Vrms | **5000 Vrms, reinforced** |
| Creepage/clearance | — | **≥8 mm** |
| Frequency | to 1 MHz+ | 0.78 kHz – >1 MHz |
| Volt-time product | — | 638 V·µs |

Holding the ratio at 1:100 means the burden analysis carries over unchanged.
With 4.99 Ω the trip is **50.121 A simulated**, worst case 49.4–50.9 A, leaving
**1.73× headroom** to the 88 A rating.

Checked rather than assumed: volt-time at trip is 2.5 V × 14.3 µs = 35.7 V·µs
against the 638 V·µs limit (**18× margin**); the 35 kHz tank sits inside the
0.78 kHz–1 MHz range; secondary compliance is 3.27 V. Datasheet note 5 records
that the sensed-current figure is a 40 °C-rise reference point, not an absolute
maximum.

The isolation improvement is worth as much as the current rating: 5000 Vrms
reinforced with ≥8 mm creepage materially strengthens the IEC 60335-1 position
over 1500 Vrms.

**Footprint drawn 2026-07-26** (this note was stale even at this document's
own last edit, 2026-07-27 10:52 — `pcb/libs/temper.pretty/CST3015.kicad_mod`
already existed by then, drawn from Coilcraft's official Recommended Land
Pattern, Document 1608-2). `elec/src/components.ato:146,155` references it
and it resolves; `pcb/temper.kicad_pcb` places it. The CST3015 is physically
larger (16.6–16.9 g) than the CST2010 it replaced and required the board
re-layout around T1 described in `docs/STRATEGY.md`'s "Rung 1b"; that
re-layout has already happened, not merely required.

### Still open — OCP-01 timing

The **<1 µs** propagation budget is not yet measured end to end. The `TLV3201`
behavioural model declares no timing model, so simulation cannot supply it.
The BOM records the `TLV3201AIDBVR` at **40 ns** propagation delay, which
leaves generous room, but the budget applies to the *whole chain* — comparator
→ `SN74HC4075` OR → latch — not the comparator alone. Sum the datasheet delays,
then confirm on the bench.

---

## THM-01 — heatsink over-temperature

### As built

```
VCC 3V3 ──[100k fixed]──┬── TLV3201 INP
                        └──[NTC 100k, B=4190]── GND
```

NTC resistance (`NTCALUG01A104GA`, R25 = 100 kΩ, B = 4190 K):

| Temp | R_NTC | V_sense with 100 k fixed |
|---|---|---|
| 25 °C | 100.0 kΩ | 1.650 V |
| **85 °C** (target) | **9.50 kΩ** | **0.286 V** |
| 99.5 °C (actual trip) | 6.02 kΩ | 0.188 V |

The threshold is wrong by ~14.5 °C, contradicting the module's own docstring
("85C threshold").

### The deeper problem

At the trip point the sense node sits at **0.19–0.29 V** — under 9 % of rail.
Comparator offset, leakage and noise all matter at that level, and the
volts-per-degree slope is poor. **The divider is badly proportioned**, not just
mis-valued. A fixed resistor equal to the NTC resistance *at the trip
temperature* maximises sensitivity.

### Recommendation — re-proportion the divider

**`r_ntc_fixed`: 100 kΩ → 10 kΩ**, and set the reference to **≈1.61 V**
(e.g. 10 kΩ / 9.53 kΩ from 3V3 → 1.610 V).

| Temp | V_sense with 10 k fixed |
|---|---|
| 25 °C | 3.000 V |
| **85 °C** | **1.607 V** ← trip, near mid-rail |
| 120 °C | 0.828 V |

Trip lands at **84.9 °C**. Sensitivity improves roughly 5×, and the node now
swings across most of the rail over the useful range.

Confirm the comparator polarity while making this change: rising temperature
*lowers* V_sense, so the fault must assert on `V_sense < V_ref`.

> **Historical note — the hysteresis shortfall described here was FIXED on
> 2026-07-26 and this paragraph is retained only for the record.**
> `FUNCTIONAL_TEST_CRITERIA.md` §2.3 requires **recovery at 70 °C** (15 °C
> hysteresis from the 85 °C trip). The divider was originally recommended
> against a summary that had dropped the recovery requirement, and delivered
> only **5.6 °C** of hysteresis (release ≈79.2 °C).
>
> That was corrected by commit `a4fb15dc` ("add the hysteresis three gates
> actually specify"), which set `r_hyst` to **34.8 kΩ**. Measured after the
> fix (`docs/evidence/2026-07-26-thm01-trip-point-sim.json`):
>
> | | Measured | Spec |
> |---|---|---|
> | Trip | **84.99 °C** | 85.0 °C |
> | Recovery | **69.83 °C** | 70.0 °C |
> | Hysteresis | **15.16 °C** | 15 °C |
>
> with `trip_within_thm01_spec: true` and `recovery_within_thm01_spec: true`.
> **THM-01 passes on both trip and recovery.**

---

## OVP-01 — DC bus overvoltage — **FIXED 2026-07-27** (this section's "decision required" heading is stale)

> **Fixed 2026-07-27 18:19, commit `75a708a8` — read this note first, then
> `docs/STRATEGY.md`'s "Bottom line" for the current summary.** This whole
> file was last touched 2026-07-27 10:52 (commit `866de677`), **before**
> the 18:19 fix the same day, so everything below (including the
> "Superseded 2026-07-26" note, which only covers the fail-open state) is
> now itself superseded. The fix (Option C, selected in
> `docs/evidence/2026-07-27-threshold-sensitivity-tempco-budget.md`):
> `r_ref_top`/`r_ref_bot` (the divider off `power.vcc` referenced in the
> "Superseded 2026-07-26" note below) are deleted outright. `comp.INN` is
> now driven directly by `REF2025`'s fixed 2.5 V VREF output (already
> instantiated elsewhere in the design, previously unused), with
> `r_div_bot` re-derived to 16.9 kΩ and `r_hyst` to 487 kΩ via an exhaustive
> E96 sweep. Simulated worst case (tolerance + tempco at ΔT=60°C): trip
> 196.11–203.81 V, hysteresis 8.58–8.90 V — both inside the 195–205 V /
> 5–10 V windows this table's "Requirement" column specifies. This clears
> the half-bus-sensing fail-open problem the note below describes: the
> divider was never the issue once correctly referenced, and the underlying
> half-bus topology (`dc_bus_plus` = +170 V half-bus) is unchanged and by
> design, per `docs/hardware/SELV_ISOLATION_REDESIGN.md`. See
> `elec/src/modules.ato:2132-2400` for the current source and
> `docs/evidence/2026-07-27-ovp01-ref2025-implementation.md` for the full
> derivation. **Not yet validated on hardware** — simulation only, per this
> whole document's uncalibrated-models caveat.

> **Superseded 2026-07-26 — read `docs/STRATEGY.md` first.** The "As built"
> values immediately below (130:1 divider, ≈1.50 V reference, 195 V sensed)
> describe the pre-2026-07-26 circuit, not what is currently committed in
> `elec/src/modules.ato` (`r_ref_top` = 1.1 kΩ, V_ref = 2.973 V, a
> ~386–400 V-referred trip). That later change is now known to be
> **fail-open**: `dc_bus_plus` is the +170 V half-bus, not the full 340 V
> bus, so the sense node can never reach the reference and the comparator
> can never fire. This section's own "which node does `v_bus` physically
> connect to?" question, below, is now answered — half-bus — but the fix is
> deliberately deferred because it is entangled with the SELV isolation
> work. See `docs/STRATEGY.md` § "OVP-01 senses the half-bus and is now
> fail-open" for the full derivation. The historical values below are left
> unedited rather than silently rewritten.

### As built (historical — see superseded note above)

Divider: 3 × 430 kΩ (1.29 MΩ) over 10 kΩ → ratio **130:1**. Reference ≈1.50 V.
Trip at the sensed node = 1.50 × 130 = **195 V** (simulated 195.18 V).

### The ambiguity, which is in the source itself

`modules.ato`, inside `OVPComparator`:

> *"Note: v_bus reference might be different (HV ground), but here it's
> measuring relative to signal ground via divider? Actually OVP measures HV
> bus."*

The author was unsure what this divider is referenced to, and the uncertainty
was committed. Compounding it, `main.ato` declares `signal dc_bus_plus # +340V`
while every downstream use treats it as a **170 V half-bus** rail.

**Two readings, with opposite verdicts:**

- **Symmetric half-bus** — the divider senses one 170 V half. Trip at 195 V is
  ~15 % over nominal, and the total-bus equivalent is 390 V, matching the
  module comment and roughly satisfying OVP-01.
- **Full bus** — the divider senses the whole 340 V rail. Trip at 195 V is
  **below normal operating voltage**; the cooker would shut down on power-up.

These are not close. **Answering "what node does `v_bus` physically connect
to?" must precede any component change.** It is traceable in `main.ato` and the
schematic, and it is the one question in this review that measurement cannot
settle.

If the answer is full-bus, the top divider must grow to roughly 2.6 MΩ
(e.g. 6 × 430 kΩ) for a ~390 V trip.

---

## OCP-02 — still no circuit exists; THM-02 is fixed

> **Correction, 2026-08-07.** This section originally covered both OCP-02
> and THM-02 as equally undesigned. THM-02 was **designed and wired
> 2026-07-26**: a second `ThermalComparator` instance now exists with a
> coil-mounted NTC, simulated at **120.3 °C** against the 120 °C
> requirement. Only OCP-02 remains without a circuit.

Verified by inspection: exactly one `OCPComparator` instance exists in
`elec/src/modules.ato`, and it is OCP-01's.

- **OCP-02** (secondary OCP, 55–65 A, <5 µs) — `BOM.md:109–111` costs a shunt,
  differential amplifier and `LM393DR` comparator chain for it. None is
  wired. **Blocked on a sensing-domain decision**: an INA240 across a
  `DC_BUS_RTN` shunt would see roughly 170 V common-mode against the part's
  -4..+80 V rating — the design cannot proceed until that is resolved.
- ~~**THM-02** (coil NTC, 120 °C) — no coil-temperature sensing exists at
  all.~~ **Fixed 2026-07-26** — see correction note above.

OCP-02 is a non-negotiable gate in `STRATEGY.md`. It needs a sensing-domain
decision before it can be designed — this is the one remaining protection
circuit gap in the whole chain.

---

## IGBT desaturation — DE-SCOPED 2026-07-26 (was: costed, never designed)

> **Correction, 2026-08-07.** This section originally recommended "design it,
> or de-scope it" as an open decision. **That decision was made: de-scope.**
> See `docs/hardware/DESAT_DECISION_BRIEF.md` for the full recommendation and
> reasoning (the `UCC21550`/`UCC21551` gate-driver family has no DESAT pin;
> `UCC21553`, also named in `IGBT_DESATURATION_PROTECTION.md`, is not a real
> TI part; DESAT via silicon would mean a from-scratch gate-driver
> architecture change). The 19 BOM lines below have been **removed**, not
> merely left costed — `BOM.md` §5.4 records the de-scope, and the
> shoot-through/gate-drive-loss residual risk is accepted in writing rather
> than left implicit.

`BOM.md:145–163` used to cost 19 line items — `STTH1R06` 1200 V DESAT diodes, 1 MΩ
current-limit resistors, blanking capacitors — for a circuit
`grep -ni desat elec/src/*.ato` still confirms does not exist.
`docs/hardware/IGBT_DESATURATION_PROTECTION.md` describes a circuit that was
never buildable as written against the gate driver in use (see the decision
brief for the datasheet-level detail).

DESAT detects an IGBT leaving saturation — the signature of a short-circuit —
and shuts the stage down within microseconds. It is standard practice on
hard-switched mains inverters, and the `UCC21550` gate driver family does
**not** support it (corrected from this document's original claim that it
does — checked directly against TI's SLUSE89C/SLUSEW9D pin tables; see the
decision brief).

OCP-01 (fixed, 50.1 A) and OCP-02 (designed, blocked on sensing domain) are
the sanctioned overcurrent/short-circuit protection chain going forward; the
narrow shoot-through/gate-drive-loss gap DESAT would have closed is recorded
as a next-revision item, not silently dropped.

---

## UVL-01, UVL-02

- **UVL-01** (gate-drive UVLO, <12.0 V): handled inside the `UCC21550B` — fixed
  silicon thresholds (VCC 7.6/8.1 V, VCCI 10.5/11.5 V per
  `docs/hardware/SAFETY_INTERLOCK_DESIGN.md`). No external circuit, no SPICE
  model. **Verify the datasheet thresholds satisfy the gate, then document it
  as vendor-guaranteed** rather than leaving it UNMEASURED.
- **UVL-02** (logic UVLO, <2.9 V): the measured candidate (TPS3700 monitoring
  RTD_AVDD, trips 2.825 V) belongs to the RTD subsystem. The more plausible
  intended circuit is the `TPS3823-33` watchdog supervisor (2.93 V typ), also
  fixed silicon. **Decide which circuit the gate refers to** and record it.

---

## Recommended order

> **Correction, 2026-08-07.** Steps 1–4 below are all complete; only step 5
> remains open, alongside the one gap this list never listed because it
> hadn't been separated out yet: OCP-02's sensing-domain decision (see
> above).

1. ~~**Answer the OVP-01 reference question.**~~ — **done.** Answered
   half-bus (`docs/evidence/2026-07-26-ovp-crossing-resolution.md`), then
   **fixed 2026-07-27** by re-referencing to `REF2025` (see "OVP-01" above).
2. ~~**Apply the two one-part fixes**~~ — **done 2026-07-25**, confirmed in
   simulation, BOM entries updated in `BOM.md` rev 1.5.
3. ~~**Decide DESAT**~~ — **done 2026-07-26: de-scoped.** See "IGBT
   desaturation" above.
4. ~~**Design OCP-02 and THM-02.**~~ — **THM-02 done 2026-07-26. OCP-02
   still open**, blocked on the sensing-domain decision (INA240 common-mode
   vs. rating) rather than on design effort.
5. **Document UVL-01/02** as vendor-guaranteed, with datasheet references —
   still open.

Nothing here should be applied without a power-electronics review — these
figures were derived from committed values and uncalibrated models, and
have never been checked against hardware.
