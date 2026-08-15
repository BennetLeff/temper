<!-- provenance: commit=7f6a6bd5c3cf9ce8adc1cd9ab67b677239d34792 dirty=false (base of branch investigate/thermal-threshold-decision = origin/main at measurement time; all readings taken against this commit) -->

# Thermal threshold hierarchy — data-driven decision (2026-08-15)

**Branch:** `investigate/thermal-threshold-decision` (base `origin/main` @ `7f6a6bd5c`)
**Method:** read-only survey of every temperature-bearing site in the repo
(firmware, schematic constraints, placer thermal metrics, thermal design docs,
simulation models, component datasheet recovery), plus git archaeology on the
firmware thresholds. No source files modified; no thresholds changed. This
document is the owner decision input requested by
`docs/evidence/2026-08-15-firmware-interlock-citations.md` §6.1 (agent 35).
**Scope:** the IGBT/heatsink thermal protection family. Coil (120 °C) and
pan/RTD (setpoint/runaway) families are covered only where they intersect.

---

## 1. Verdict up front

1. **The 85 °C hardware thermal latch (THM-01) is the governing trip.**
   It is real (wired in `elec/src/modules.ato` `ThermalComparator`),
   simulated-verified (84.99 °C trip / 69.83 °C release,
   `docs/evidence/2026-07-26-thm01-trip-point-sim.json`), latched with
   15.2 °C hysteresis, and it protects the IGBT with ~80 °C of junction
   margin against the datasheet's 175 °C absolute maximum.
2. **`OVER_TEMP_THRESHOLD` must move from 100 °C to 80 °C.** At 100 °C the
   firmware trip is **dead code on a wired board** (hardware fires at 85 °C
   first, so the firmware interlock can never engage, is never exercised, and
   cannot be acceptance-tested). At 80 °C the firmware becomes the live
   first layer (graceful shutdown, diagnostics, fan control) with the
   hardware latch as the independent backstop — the belt-and-suspenders
   structure the docs always intended, in the correct order.
3. **The 95 °C "shutdown" in three docs is retired** as an acceptance
   criterion: it is unreachable on the as-built board (95 > 85 hardware
   trip) and dates from the pre-2026-07-25 era when the hardware trip was
   ~99.5 °C. The acceptance ladder becomes **75 °C warn/derate → 80 °C
   firmware shutdown → 85 °C hardware latch → 125 °C fault-state backstop**
   (all observable on a wired board).
4. **The 125 °C fault-state monitor stays** — it is a last-resort cooling
   backstop that only matters while latched in FAULT (power already off), at
   which point Tj ≈ Tc ≈ Ts, so 125 °C remains below the 175 °C absolute
   maximum. It is at the NTC sensor's own +125 °C rating; flagged, not
   changed.
5. **The 150 °C family is relabeled/retired as a junction limit.** The
   IKW40N120H3 datasheet gives **Tvj(max) = 175 °C**, not 150 °C. The
   150 °C figure (placer `thermal_margin_c`, `.ato` `igbt_max_temp`, three
   thermal docs, and the interlock doc's own rationale) has no datasheet
   basis — it is most plausibly a confusion with the datasheet's **storage**
   temperature (Tstg = −55…+150 °C). Thermal analysis should use
   **175 °C as the absolute survival limit and 125 °C as the design/
   reliability limit** (the datasheet-recovery doc's own "design for
   ≤125 °C" guidance, §5.1.1).
6. **IEC 60335-1 Table 9's numeric content is NOT obtainable in this repo.**
   Clause 19.13's text is recovered verbatim (it references Table 9), but
   the table's temperature-rise values are absent — the repo's own words:
   "19.13's Table 9 temperature-rise criterion, and nobody has it"
   (`docs/evidence/2026-08-12-hv-hv-creepage-determination.md:514`).
   Touch-temperature limits for accessible parts are likewise not in-repo.
   Per project rule, neither is reconstructed here. The protection chain's
   evidence for 19.13 is structural: heatsink ≤ 85 °C keeps junction
   ≤ ~105 °C even at double nominal loss, far inside every plausible Table 9
   band — but the literal table values remain a certification-lab question.

---

## 2. The five values, their homes, what each measures

| Value | Homes (committed) | Quantity measured | Class |
|---|---|---|---|
| **85 °C** | `elec/src/modules.ato` `ThermalComparator` (THM-01); `docs/FUNCTIONAL_TEST_CRITERIA.md` §2.3 (trip 85 / recovery 70); `docs/hardware/SAFETY_INTERLOCK_DESIGN.md` §5.1; `docs/hardware/BOM.md` NTC_HS (85.0 trip / 69.8 release, re-derived from the real divider); sim-verified 84.99/69.83 °C | **Heatsink temperature Ts, hardware latch trip** | **REAL, WIRED, SIM-VERIFIED — governing** |
| **95 °C** | `docs/FUNCTIONAL_SAFETY_TEST_PROCEDURE.md` §3.1 (shutdown); `docs/guides/THERMAL_DESIGN_GUIDE.md` §6.2 (shutdown); `docs/hardware/SYSTEM_THERMAL_BUDGET.md` §6.1 (shutdown) | Heatsink "shutdown" | **DOC-ONLY — unreachable on as-built hardware (hardware fires at 85 °C first)** |
| **100 °C** | `firmware/components/safety/safety.c:42` (`#define OVER_TEMP_THRESHOLD 100.0f`); `firmware/main/state_machine.c:391` (literal `100.0f`); `docs/requirements/FIRMWARE_REQUIREMENTS.md` REQ-FW-SAFETY-02 (shutdown 100 / restart 90) | Heatsink temperature, firmware trip | **DEAD CODE on a wired board; sensors have no ESP32 implementation (extern-only)** |
| **125 °C** | `firmware/main/state_handlers.c:634` (fault-state monitor); `elec/src/constraints.ato` `igbt_derate_temp = 398.15 K`; `docs/guides/THERMAL_DESIGN_GUIDE.md` §6.3 (thermal fuse 125/130 °C); `docs/hardware/SYSTEM_THERMAL_BUDGET.md` §6.1 (optional IGBT MAX31865, 125 °C); datasheet-recovery §5.1.1 "design for ≤125 °C" (**junction** guidance) | Heatsink fault-state backstop; also a junction design limit and a fuse rating elsewhere | **KEEP as fault-state backstop; relabel the junction usage** |
| **150 °C** | `packages/temper-placer/src/temper_placer/metrics/physics.py:325` (`thermal_margin_c = 150.0 - max_tj`, comment "150C is typical shutdown"); `physics/parameter_bounds.py:259`, `physics/operating_point.py:89`, `validation/results/battery_run.py:245,705` (T_j_max = 150.0); `packages/temper-thermal/src/thermal_edges.rs:157`, `tj_cross_check.rs` tests; `elec/src/constraints.ato` `igbt_max_temp = 423.15 K`; `docs/guides/THERMAL_DESIGN_GUIDE.md` §3.1/§8 (margin vs 150); `docs/hardware/SYSTEM_THERMAL_BUDGET.md` §8.3 ("IKW40N120H3 Max Tj 150 °C"); `docs/hardware/SAFETY_INTERLOCK_DESIGN.md` §5.1 rationale ("IGBT max junction 150 °C, margin"); `firmware/components/safety/include/ntc_guard.h:29` (`NTC_TEMP_MAX_C 150.0f`, sensor plausibility) | Junction "max"/margin in analysis; NTC plausibility ceiling in firmware | **NO DATASHEET BASIS as a junction limit (Tvj max = 175 °C); 150 = Tstg max. The ntc_guard.h use is a different quantity (sensor sanity) and is defensible** |

**Adjacent values that belong to the same ladder** (needed for a coherent
hierarchy):

| Value | Home | Role |
|---|---|---|
| 70 °C | `firmware/main/state_machine.c:518` (`fault_cleared`: heatsink < 70 °C clears FAULT_OVER_TEMP); `docs/FUNCTIONAL_TEST_CRITERIA.md` §2.3 recovery; THM-01 release 69.83 °C | **Recovery — consistent across hardware and firmware already** |
| 75 °C | `docs/FUNCTIONAL_SAFETY_TEST_PROCEDURE.md` §3.1 (warn / derate) | Warn / first derate stage (doc-only today; no firmware derate exists) |
| 120 °C | `firmware/components/safety/include/coil_guard.h:28` (`COIL_MAX_TEMP_C 120.0f`); THM-02 sim 120.3/100.1 °C; `docs/FUNCTIONAL_TEST_CRITERIA.md` §2.3 coil | Coil family — **consistent at 120 °C except** `FUNCTIONAL_SAFETY_TEST_PROCEDURE.md` §3.2's 115 °C (drift) |

Git archaeology (agent 35's audit): `OVER_TEMP_THRESHOLD`, the `100.0f`
literal, and the `125.0f` literal all date to commit `04fe05232`
(2025-12-14, "syncing dec 14") with **no citation ever attached**. The
hardware THM-01 trip was corrected from ~99.5 °C to 84.99 °C on 2026-07-25
(`docs/hardware/BOM.md` THM-01 note; `docs/hardware/PROTECTION_CHAIN_REVIEW.md`
THM-01 section) — **the firmware 100 °C and the doc 95 °C are
pre-correction-era values that were never re-pointed after the hardware
moved to 85 °C.** That is the historical root of the five-value incoherence.

---

## 3. The thermal chain — sensor → Tc → Tj → failure

### 3.1 Where the sensor is and what it measures

- **Sensor:** `NTC_HS` = Vishay `NTCALUG01A104GA`, 100 kΩ @ 25 °C,
  B25/85 = 4190 K, **M3-ring-lug thermistor bolted to the heatsink body**
  (`docs/hardware/BOM.md:414`; `elec/src/modules.ato:2402-2414`). It is a
  flying-lead lug part on `HS1` (Wakefield-Vette 392-120AB), *not* a
  board-mounted sensor.
- **It measures heatsink temperature Ts**, which is **below** the IGBT case
  temperature Tc by the TIM drop: `Tc = Ts + P · Rch`.
- The datasheet-recovery doc's own approximation ("Measures Tc
  (approximately)", `IKW40N120H3_Documentation.md` §7.4) is accurate to
  within a few °C at nominal loss; the exact relation is the chain below.

### 3.2 The chain

```
Tj = Tc + P·Rjc        (junction → case)
Tc = Ts + P·Rch        (case → heatsink, through TIM/isolator pad)
Ts = Ta + P·Rha        (heatsink → ambient, with fan)
```

Values (all committed):

| R | Value | Source |
|---|---|---|
| Rjc (IGBT) | **0.31 K/W** | `components/IKW40N120H3/IKW40N120H3_Documentation.md` §1.2 (datasheet recovery) |
| Rjc (diode) | 1.11 K/W | same |
| Rch (TIM/isolator) | ~0.20 K/W | `docs/guides/THERMAL_DESIGN_GUIDE.md` §3.1 (graphite pad / Sil-Pad class) |
| Rha (HS1 w/ fan) | 0.45 K/W | `docs/guides/THERMAL_DESIGN_GUIDE.md` §3.1; `SYSTEM_THERMAL_BUDGET.md` uses 0.35–0.45 |
| Loss per IGBT | 18–20 W | `SYSTEM_THERMAL_BUDGET.md` (36 W both) vs `THERMAL_DESIGN_GUIDE.md` (20 W each = 40 W) — docs disagree; both used below |

**Model-quality caveat:** the committed SPICE thermal model
(`simulation/models/IKW40N120H3_thermal.sub`) uses **RthetaJC = 0.6 K/W**
and RthetaCH = 0.3 K/W — the Rjc is ~2× the datasheet's 0.31. That makes the
simulation conservative (overestimates Tj), which is the safe direction, but
it is a flat stand-in, not the datasheet value. The placer kernel
(`packages/temper-thermal/src/junction_temp.rs`) likewise uses flat
Rjc/Rch/Rha (0.6/0.25/1.0 in tests). This is exactly the "flat
Rjc/Rch/Rha" the thermal-analysis correction agent is fixing; this document
uses the datasheet Rjc where precision matters.

### 3.3 Numbers that fall out (1.8 kW / 120 V, 20 W per IGBT)

| Condition | Ts (heatsink) | Tc | Tj | vs 125 °C design-for | vs 175 °C abs max |
|---|---|---|---|---|---|
| Normal, 40 °C ambient (rated max per `ENVIRONMENTAL_SPEC.md`) | 49 °C | 53 °C | 59.2 °C | −66 | −116 |
| Design-limit, 60 °C ambient (zero-power point of the spec's own derating curve) | 69 °C | 73 °C | 79.2 °C | −46 | −96 |
| **At hardware latch, Ts = 85 °C** (fault; power still near nominal at the instant of trip) | 85 °C | 89 °C | 95.2 °C | **−30** | **−80** |
| At hardware latch, Ts = 85 °C, **2× nominal loss (40 W/IGBT)** | 85 °C | 93 °C | 105.4 °C | −20 | −70 |
| At firmware 100 °C (unreachable; if it ever fired) | 100 °C | 104 °C | 110.2 °C | −15 | −65 |
| Fault-state backstop, Ts = 125 °C (power off ⇒ P ≈ 0) | 125 °C | ≈125 °C | ≈125 °C | 0 (at design-for) | −50 |

**Every trip point on the ladder protects the IGBT with large margin.** The
IGBT is not the binding constraint anywhere in this family — the decision
below is about *protection-architecture coherence* (which layer fires, in
what order, and what is observable/testable), not about IGBT survival. Note
also: at 40 °C ambient the heatsink sits at ~49 °C, and at the 60 °C
design-limit ambient it sits at ~69 °C — so **80 °C firmware trip has
11–31 °C of normal-operation headroom** and 5 °C below the hardware latch.

---

## 4. The IGBT specs that constrain the decision

From `components/IKW40N120H3/IKW40N120H3_Documentation.md` (datasheet
recovery):

| Parameter | Value | Meaning for this decision |
|---|---|---|
| Tvj(max) | **175 °C** | Absolute junction limit — the survival number |
| Tc(max recommended) | **100 °C** | Case temperature for full rated current — *not* a trip point; the firmware 100 °C is consistent with it *by coincidence of quantity* (firmware trips on heatsink Ts, not case Tc, and 100 °C was never cited to it) |
| Rth(j-c) | **0.31 K/W** (IGBT), 1.11 K/W (diode) | Chain arithmetic above |
| Tstg | −55…+150 °C | **The probable origin of the 150 °C family** — storage, not junction |
| §5.1.1 "Design for ≤125 °C" | 125 °C | The reliability/design-for junction limit |
| §5.2.3 recommended heatsink trip | **Tc > 90 °C**, resume < 70 °C | The datasheet doc's own protection recommendation; the hardware's 85 °C is *more* conservative than it |

The datasheet-doc's thermal-protection section also recommends hysteresis
(trip 90 °C, resume < 70 °C) — the as-built THM-01 (85/69.8) matches the
resume value and undershoots the trip, i.e. **the hardware is already
conservative relative to the manufacturer's own recommendation.**

---

## 5. The IEC 60335-1 constraints on the decision

### 5.1 What is actually recovered (verbatim, in-repo)

Clause **19.13** (abnormal-operation acceptance), quoted verbatim in
`docs/evidence/2026-08-12-hv-hv-creepage-determination.md:363-375`:

> During the tests the appliance shall not emit flames, molten metal, or
> poisonous or ignitable gas in hazardous amounts and **temperature rises
> shall not exceed the values shown in Table 9**.

Clause **19.11.2(a)**: short-circuit of functional insulation is a
mandatory fault condition wherever creepage falls short of clause 29 — it is
owed on this board, and 19.13 is its acceptance criterion.

### 5.2 What is NOT obtainable

- **Table 9's numeric temperature-rise values are not in this repo.** The
  repo's own audit says so outright ("nobody has it"). Per project rule
  ("never invent or reconstruct a standards value; 'not obtainable' is
  correct"), they are **not reconstructed here**.
- **Touch-temperature limits for accessible parts** (the 85 °C "accessible
  metal" figure commonly cited for IEC 60335-1) are **not in this repo** in
  any recoverable form, and are **not reconstructed here**.
- Whether the heatsink counts as "accessible" is a clause-8 probe
  accessibility assessment for the finished appliance — also not in-repo.

### 5.3 How the decision interacts with IEC 60335-1

- The protection chain is the appliance's own engineered evidence for
  19.13's temperature-rise requirement: heatsink is hard-limited to 85 °C,
  which bounds junction ≤ ~105 °C even at double nominal loss and bounds
  *every* heatsink-adjacent surface ≤ 85 °C in all conditions. Those bounds
  are comfortably inside any plausible Table 9 band, but the *literal* pass
  is a certification-lab determination — **flag for the cert-lab package**
  (the two questions already queued there are the natural vehicle).
- **Independent, exercised layers matter for the standard's structure.**
  A firmware protection that can never fire (100 °C above the 85 °C
  hardware latch) is not an independent layer — it is inert. Re-pointing the
  firmware to 80 °C makes software a real first layer (graceful shutdown,
  diagnostics, fan ramp) and the hardware latch a real backstop, which is
  the redundancy the standard's fault-condition framework rewards.

---

## 6. The decision — the full hierarchy

### 6.1 The governing ladder (heatsink temperature, Ts)

| Stage | Threshold | Actor | Action | Observable on a wired board? |
|---|---|---|---|---|
| 1 | 75 °C | Firmware | Warn / derate (fan max; power reduction — **to be implemented**; documented intent in `FUNCTIONAL_SAFETY_TEST_PROCEDURE.md` §3.1) | Yes |
| 2 | **80 °C** | Firmware | `FAULT_OVER_TEMP`: graceful shutdown, fault LED, EEPROM log | Yes |
| 3 | **85 °C** | **Hardware THM-01** | Latched `THERMAL_FAULT` → fault OR gate → UCC21550 DISABLE (independent of firmware; manual reset) | Yes (test with firmware disabled) |
| 4 | 70 °C | Both | Recovery: firmware `fault_cleared` at < 70 °C; THM-01 releases at 69.8 °C | Yes |
| 5 | 125 °C | Firmware (fault state only) + thermal fuse (125/130 °C, one-shot) | While latched in FAULT: if Ts still > 125 °C, `trigger_hardware_shutdown()` (safe mode). Fuse is the last physical line | Yes |
| — | 175 °C (Tj) / 125 °C (Tj design-for) | Physics | **Analysis limits only** — never reached by the ladder above (max Tj at trip ≈ 105 °C even at 2× loss) | — |

### 6.2 `OVER_TEMP_THRESHOLD` = 80 °C — justification

Constraints it must satisfy (all from committed data):

1. **< 85 °C** — below the hardware latch, or the firmware layer is dead
   code (the current 100 °C defect).
2. **> ~69 °C** — above the normal-operation heatsink temperature at the
   60 °C design-limit ambient (zero-power point of the spec's own derating;
   `ENVIRONMENTAL_SPEC.md` §1.1), or it nuisance-trips at the design limit.
3. **≥ ~10 °C below the hardware latch** is not required — 5 °C suffices
   given the comparator's tight window (84.99 °C simulated, ±1% divider) —
   but the gap must exceed the hardware's own tolerance spread.
4. Conservative vs the datasheet-doc's own 90 °C heatsink-trip
   recommendation (§5.2.3) — yes, 80 < 90.

**80 °C** satisfies all four with 5 °C below the hardware latch and
11–31 °C above normal operation. The close runner-up, **75 °C** (matching
the documented warn temperature), leaves only ~6 °C of normal-operation
headroom at the design-limit ambient — a nuisance-trip risk at exactly the
ambient where the appliance is already derating. 80 °C is the better
balance; the 75 °C warn stage stays as stage 1, giving a clean
**75 → 80 → 85** ladder.

**Not adopted:** keep 100 °C as a "hardware-failed" backup (no — both layers
read the same NTC, so a sensor failure defeats both; the value above the
hardware latch is un-exercisable; and the acceptance procedure cannot test
it); and 90 °C (datasheet-doc recommendation — sits *above* the hardware
latch, same dead-code defect).

### 6.3 Per-value disposition

| Value | Verdict | Action |
|---|---|---|
| 85 °C | **GOVERNING** | Keep. Correct the `SAFETY_INTERLOCK_DESIGN.md` §5.1 rationale ("IGBT max junction 150 °C" → 175 °C per datasheet; the trip is even more conservative than its own rationale claimed). |
| 95 °C | **RETIRE** (as shutdown/acceptance) | Re-point in `FUNCTIONAL_SAFETY_TEST_PROCEDURE.md` §3.1, `THERMAL_DESIGN_GUIDE.md` §6.2, `SYSTEM_THERMAL_BUDGET.md` §6.1 to the ladder: warn 75 / firmware 80 / hardware 85. The 95 °C is a pre-2026-07-25-era value that the 85 °C hardware correction orphaned. |
| 100 °C | **CHANGE to 80 °C** | `OVER_TEMP_THRESHOLD` (safety.c / state_machine.c:391 / config.yaml interlocks on agent 35's branch) and `FIRMWARE_REQUIREMENTS.md` REQ-FW-SAFETY-02 (also fixes its stale "restart at 90 °C" → the code's real 70 °C, which matches THM-01's 69.8 °C release). |
| 125 °C | **KEEP** (fault-state) | Keep `state_handlers.c:634`. Add the justification: power-off backstop; Tj ≈ Ts in fault state, 50 °C under absolute max. Flag: it is at the NTCALUG01A104GA's own +125 °C rating (same caveat the BOM already carries for THM-02's 120.3 °C coil trip); sensor part selection should confirm sustained service at the monitor point. |
| 150 °C | **RETIRE as junction limit** | `metrics/physics.py:325` margin → 125 °C design-for (or 175 °C survival; see §6.4). `elec/src/constraints.ato` `igbt_max_temp` 423.15 K → 448.15 K (175 °C); `igbt_derate_temp` 398.15 K (125 °C) already correct as the derate figure. `ntc_guard.h` `NTC_TEMP_MAX_C = 150.0f` is a **sensor-plausibility ceiling, not a trip** — different quantity, defensible; keep, with a comment. |

### 6.4 What the thermal analysis should use as design limits

(For the in-flight thermal-analysis correction agent; this document's data
does not change those corrections, it supplies the target numbers.)

- **Ambient:** 60 °C design-limit (matches `ENVIRONMENTAL_SPEC.md` §1.1's
  zero-power point and `THERMAL_DESIGN_GUIDE.md` §2.2's worst-case design;
  the correction agent's 40 → 60 °C change is correct).
- **Survival limit (junction):** Tvj(max) = **175 °C** (datasheet).
- **Design/reliability limit (junction):** **125 °C** (datasheet-recovery
  §5.1.1 "design for ≤125 °C").
- **Trip-anchored limit:** the firmware/heatsink trip (80 °C at the sensor
  → Tj ≈ 95 °C at nominal loss) — the correction agent's "margin 150 →
  firmware trip" is directionally right, but the *design* margin should be
  reported against 125/175 °C junction, with the 80 °C sensor trip as the
  hardware-realized bound.
- **Rjc/Rch/Rha:** use the datasheet Rjc = 0.31 K/W (IGBT) and the
  committed Rch ≈ 0.20 / Rha ≈ 0.45 for the real HS1/fan assembly, not the
  flat 0.6/0.25/1.0 stand-ins (`IKW40N120H3_thermal.sub`,
  `junction_temp.rs` tests). The 0.6 K/W stand-in is conservative but it is
  not the datasheet, and the correction is the point of the exercise.

### 6.5 Is the firmware 100 °C dead code — and is that acceptable?

**Yes, it is dead code on a wired board** (hardware THM-01 fires at 85 °C,
firmware can never observe 100 °C; and `read_heatsink_temperature()` /
`read_dc_bus_current()` have **no ESP32 implementation** — extern-only in
`safety.c`/`state_machine.c`/`state_handlers.c`, with definitions only in the
non-ESP sim path and the test mock — so the firmware interlocks cannot even
link on real hardware today).

**No, that is not acceptable as-is**, for three reasons:

1. A protection layer that can never fire is not protection — it is inert
   documentation that manufactures confidence (the repo's own deepest
   finding, per the handoff: a running check pinned to a wrong value is
   worse than none).
2. It inverts the documented intent: every thermal doc describes a
   software-first ladder (derate → shutdown) with hardware as backstop.
   100 °C above the 85 °C latch makes software *never* first.
3. It is untestable: `FUNCTIONAL_SAFETY_TEST_PROCEDURE.md` §3.1's
   acceptance test ("shutdown at 95 °C") cannot be executed on a wired
   board because the hardware latch kills power at 85 °C first — the
   acceptance procedure itself is incoherent with the hardware until the
   firmware value is re-pointed below 85 °C.

The fix (80 °C) is not a relaxation of anything — it *activates* a layer
and keeps every protection point within the hardware-verified envelope.

### 6.6 Caveats that travel with this decision

1. **The firmware interlocks cannot run on real hardware yet.** Until
   `read_heatsink_temperature()` / `read_dc_bus_current()` are implemented
   against the ESP32 ADC HAL (`firmware/components/hal/esp32/hal_adc_esp32.c`
   exists; no sensor-read glue does), every firmware threshold — 80, 125,
   and the OCP family — is theoretical. The hardware THM-01/THM-02 latches
   are the *only* live thermal protection today. This is already flagged in
   agent 35's evidence doc §6.3 and in the functional-safety test plan.
2. **THM-01's physical efficacy is unproven end-to-end.** The NTC is a
   flying-lead lug part; `docs/evidence/2026-08-12-thermal-constraint-derivation.md`
   §2 established that the 38.1 mm lead budget vs the installed HS1
   position cannot be confirmed without a chassis drawing. If the lug is
   not actually on the heatsink, *no* threshold in this ladder protects
   anything. This is a hardware/mechanical open item, independent of this
   decision.
3. **The "verified by simulation 35" claim in `FUNCTIONAL_TEST_CRITERIA.md`'s
   appendix is untraceable** — `simulation/results/runaway_boundary_map.svg`,
   `simulation/results/runaway_interlock_margin.md`, and
   `simulation/testbenches/sim_35_runaway_boundary.cir` do not exist
   anywhere in the repo. The 85/120 °C hardware trips rest on THM-01/THM-02
   divider simulation, not on a runaway-boundary sweep. Flagged, not
   re-derived.

---

## 7. Files this decision touches (owner/agent follow-up, not done here)

- `firmware/components/safety/safety.c` — `OVER_TEMP_THRESHOLD` 100 → 80.
- `firmware/main/state_machine.c:391` — literal `100.0f` → `OVER_TEMP_THRESHOLD`.
- `firmware/config.yaml` (interlocks section, agent 35's branch) — value +
  citation update; `firmware/config.h` regenerated.
- `docs/requirements/FIRMWARE_REQUIREMENTS.md` — REQ-FW-SAFETY-02: 100 → 80,
  restart 90 → 70 (matches code and THM-01 release); fix stale validation
  refs (`test_over_temp_shutdown` does not exist; real test is
  `test_sm_fault_on_over_temperature`).
- `docs/FUNCTIONAL_SAFETY_TEST_PROCEDURE.md` §3.1 — ladder 75/80/85;
  §3.2 coil 115 → 120 °C (matches `COIL_MAX_TEMP_C` and THM-02).
- `docs/guides/THERMAL_DESIGN_GUIDE.md` §6.1-6.2 — heatsink 85/95 → 75/80/85
  ladder; §3.1/§8 margin 150 → 125/175 junction; Rjc 0.50 → 0.31.
- `docs/hardware/SYSTEM_THERMAL_BUDGET.md` §6.1/§8.3 — same re-points;
  "IKW40N120H3 Max Tj 150 °C" → 175 °C.
- `docs/hardware/SAFETY_INTERLOCK_DESIGN.md` §5.1 — rationale "IGBT max
  junction 150 °C" → 175 °C.
- Placer/thermal: `metrics/physics.py:325` margin basis 150 → 125
  (design-for) with the 175 absolute kept for the U11 survival gate;
  `elec/src/constraints.ato` `igbt_max_temp` 423.15 K → 448.15 K.
- `packages/temper-thermal/src/junction_temp.rs` / `IKW40N120H3_thermal.sub`
  — Rjc 0.6 → 0.31 (in the thermal-correction agent's scope).
- `docs/FUNCTIONAL_TEST_CRITERIA.md` appendix — either restore the sim_35
  artifacts or strike the "verified by simulation 35" claim.

**Explicitly not changed here:** any threshold, any code, `pcb/**`.
`git status` clean at commit time other than this document.
