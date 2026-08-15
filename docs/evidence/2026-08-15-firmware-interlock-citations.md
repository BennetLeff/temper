<!-- provenance: commit=7f6a6bd5c3cf9ce8adc1cd9ab67b677239d34792 dirty=false (base of branch fix/firmware-interlock-citations, = origin/main at measurement time; doc and all audit changes committed on the branch) -->

# Firmware interlock thresholds — citation audit and single-sourcing (2026-08-15)

**Date:** 2026-08-15
**Method:** git archaeology + repo documentation cross-reference. No simulation,
no hardware. Every claim below is traced to a committed file and line.
**Scope:** the software safety interlocks in
`firmware/components/safety/safety.c`, `firmware/main/state_machine.c`,
`firmware/main/state_handlers.c`.
**Finding:** `OVER_TEMP_THRESHOLD = 100.0 °C` and
`OVER_CURRENT_THRESHOLD = 35.0 A` both date to the initial 2025-12-14 sync
(commit `04fe05232`, "syncing dec 14") and carry **no citation**. They are
labelled **UNCITED** and flagged below with every repo-internal anchor they
are consistent or inconsistent with. This change single-sources the whole
interlock family into `firmware/config.yaml` (one home, citations attached);
it does **not** change any value — the correct values are owner decisions
that the repo cannot resolve on its own.

---

## 1. The values, as built

| Constant | Value | Homes before this change | Origin |
|---|---|---|---|
| `OVER_TEMP_THRESHOLD` | 100.0 °C | `safety.c` `#define`; literal `100.0f` in `state_machine.c:391` | commit `04fe05232` (2025-12-14) |
| `OVER_CURRENT_THRESHOLD` | 35.0 A | `safety.c` `#define`; literal `35.0f` in `state_machine.c:398` | commit `04fe05232` (2025-12-14) |
| IGBT-short threshold | 50.0 A | literal `50.0f` in `state_machine.c:394` | commit `04fe05232` (2025-12-14) |
| Fault-state temp monitor | 125.0 °C | literal `125.0f` in `state_handlers.c:634` | commit `04fe05232` (2025-12-14) |

Git archaeology (`git log -S OVER_CURRENT_THRESHOLD -- firmware/components/safety/safety.c`,
`git log --diff-filter=A -- firmware/components/safety/safety.c`): the first
commit to touch the file is `04fe05232` ("syncing dec 14", 2025-12-14), which
introduces both `#define`s with their final values. They were placeholder-era
constants from the initial repo sync; no later commit ever revisited or cited
them.

The same family is pinned, uncited, in the firmware requirements:
`docs/requirements/FIRMWARE_REQUIREMENTS.md` REQ-FW-SAFETY-02 (shutdown at
100 °C heatsink, restart at 90 °C) and REQ-FW-SAFETY-03 (shutdown at 35 A DC
bus), both `Status: VERIFIED` with `Linked Issues: (baseline requirement)`.
Both validation references in that file are stale: `test_over_temp_shutdown`
does not exist anywhere in `firmware/` (the real test is
`test_sm_fault_on_over_temperature` in `firmware/test/test_state_machine.c`),
and `sim_ocp_response.cir` does not exist either.

## 2. OVER_TEMP_THRESHOLD = 100.0 °C — analysis

**Sensor:** NTC thermistor on the IGBT heatsink — `NTC_HS` = Vishay
`NTCALUG01A104GA` (100 kΩ @ 25 °C, B25/85 = 4190 K, M3 lug)
(`docs/hardware/BOM.md` §NTC_HS). The firmware reads it through
`read_heatsink_temperature()`.

**What 100 °C is consistent with:**

- IKW40N120H3 datasheet (recovered in
  `components/IKW40N120H3/IKW40N120H3_Documentation.md` §1.2): **Tc(max
  recommended) = 100 °C**; Tvj(max) = 175 °C; Rth(j-c) = 0.31 K/W. A 100 °C
  heatsink/case trip leaves junction margin: at 40 W/IGBT loss,
  Tvj = 100 + 0.31·40 = 112 °C, well inside the 175 °C absolute max and the
  doc's own "design for ≤ 125 °C" guidance (§5.1.1).
- The same datasheet's protection section (§5.2.3) *recommends* a heatsink
  trip at **Tc > 90 °C** — 100 °C is 10 °C above its own recommendation.

**What 100 °C contradicts (repo-internal, all committed):**

| Document | Heatsink shutdown | Notes |
|---|---|---|
| `docs/FUNCTIONAL_SAFETY_TEST_PROCEDURE.md` §3.1 | **95 °C** (warn 75 °C) | The acceptance procedure for the built system |
| `docs/guides/THERMAL_DESIGN_GUIDE.md` §6.2 | **95 °C** (derate 85 °C) | `T_heatsink > 95°C → Shutdown, fault LED` |
| `docs/hardware/SAFETY_INTERLOCK_DESIGN.md` §5.1 | **85 °C** (reset 75 °C) | Hardware thermal latch (TLV3201 comparator), "IGBT max junction 150°C, margin" |
| `docs/FUNCTIONAL_TEST_CRITERIA.md` §2.3 | **85 °C** trip / 70 °C recovery | Hardware NTC path |
| `docs/hardware/BOM.md` §NTC_HS (2026-08-07 note) | **85.0 °C** trip / 69.8 °C release | Re-derived from the actual divider (9.09 k/11.5 k/34.8 k + NTC curve) |
| firmware (as built) | **100 °C** | `OVER_TEMP_THRESHOLD` |
| `firmware/main/state_handlers.c:634` | **125 °C** | Fault-state backup monitor |
| thermal analysis (another agent's scope) | 150 °C | "typical shutdown" used by the thermal FDM analysis |

**Layering problem:** the hardware thermal latch trips at **85 °C** and is
latched (manual reset). The firmware threshold at 100 °C sits *above* it, so
on a fully-wired board the hardware always fires first and the firmware
interlock can never engage. The documented software-first hierarchy
(FUNCTIONAL_SAFETY_TEST_PROCEDURE: firmware derates at 75 °C, shuts down at
95 °C; THERMAL_DESIGN_GUIDE: firmware derates at 85 °C, shuts down at 95 °C)
requires the firmware threshold to be **below** the hardware latch, i.e.
≤ 85 °C, not 100 °C. Note the docs disagree with each other about where the
hardware trip actually sits (85 °C) vs where the firmware shutdown should sit
(95 °C) — 95 > 85, so the acceptance procedure's own firmware threshold is
also above the hardware latch. **The repo has no internally consistent
thermal shutdown story; an owner must pick the hierarchy and ratchet the
firmware value against it.** This is a design decision, not a derivable
fact — "not obtainable" applies to any claim that one of 85/95/100/125 °C is
*the* correct value.

## 3. OVER_CURRENT_THRESHOLD = 35.0 A — analysis

**Sensor:** current transformer on the resonant tank. Two committed CT
designs exist; the current one (`elec/src/modules.ato` `CurrentSensing`,
re-derived 2026-07-27) is **CST3015-100ED, 1:100, 4.99 Ω burden, 100 nF
noise filter, 1.65 V mid-rail bias** for the ESP32 ADC. The older
`docs/hardware/CT_SENSING_DESIGN.md` (2025-12-14) describes 1:1000/50 Ω —
superseded. There is no rectifier and no averaging; the sense path sees the
raw bipolar tank waveform (`docs/evidence/2026-07-26-ocp01-vs-full-power-current.md`).

**Hardware OCP (independent of firmware):** TLV3201 comparator, trip at
**50.1 A peak** (worst case 48.77–51.16 A over tolerance/tempco), acceptance
window **45–55 A peak**, < 1 µs, latched
(`docs/FUNCTIONAL_TEST_CRITERIA.md` §2.1, `docs/FUNCTIONAL_SAFETY_TEST_PROCEDURE.md`
§2, `elec/src/modules.ato`). The firmware 35 A is a **separate, earlier
software trip** — below the hardware window, so software acts first and the
hardware latch is the backstop. That layering is *correct*: the audit's
framing ("35 A contradicts the documented 45–55 A OCP acceptance") conflates
two protection layers. The docs are not wrong; they describe the hardware.

**The real problem is the value's basis.** 35 A is also the **RMS equivalent
(35.4 A) of the 50.1 A peak hardware trip** (`docs/evidence/2026-07-26-ocp01-vs-full-power-current.md`:
"Equivalent RMS (sinusoid) 35.4 A"). Two readings:

- **Peak basis** (what the comparator and the CT path actually deliver):
  35 A peak sits **inside the documented full-power operating band**.
  Tank current at 1800 W: 35.4 A RMS / 50.0 A peak at R_eff = 1.44 Ω
  (good coupling) up to 56.6 A peak at R_eff = 1.12 Ω (typical coupling —
  which already exceeds even the *hardware* 50.1 A trip). A 35 A peak
  threshold would fault at roughly 700–900 W, making the 1800 W target
  unreachable through the firmware path.
- **RMS basis** (only defensible if the firmware filters/averages): 35 A RMS
  ≈ 49.5 A peak, i.e. the software trip mirrors the hardware trip — redundant
  rather than early, and there is no averaging circuit or firmware filter
  anywhere in the sense path to make this basis real.

`FIRMWARE_REQUIREMENTS.md` REQ-FW-SAFETY-03 says "35A DC bus" — but the CT
senses **tank** current, not DC-bus average current (1800 W / 300 V ≈ 6 A
average), and in a half-bridge the bus pulses carry the tank peak. No
committed document states which quantity `read_dc_bus_current()` is meant to
return. **The correct threshold is therefore not derivable from the repo: it
depends on (a) the intended basis (peak vs RMS vs average), (b) the tank
current at the target power, which itself is unresolved pending an R_eff
measurement (the open question in `2026-07-26-ocp01-vs-full-power-current.md`),
and (c) how much margin below the 45 A hardware-window floor the software
trip should hold. Owner decision required; "not obtainable" is the honest
label for a *justified* value.**

**IGBT margin context:** the device is a 40 A continuous / 160 A pulse IGBT
(IKW40N120H3, 1200 V); the hardware OCP at 50.1 A is "125% of rated 40 A"
(`SAFETY_INTERLOCK_DESIGN.md` §3.1). The IGBT itself is not the binding
constraint at 35 A — the operating-band tension is.

## 4. IGBT_SHORT (50 A) and fault-state monitor (125 °C)

- The 50 A IGBT-short threshold coincides with the hardware OCP trip. There
  is **no desaturation path** (`docs/hardware/DESAT_DECISION_BRIEF.md`), so
  firmware's "IGBT short" is simply "current > 50 A" — it is the same trip as
  the hardware OCP, in software, and carries the same full-power-band tension.
- The 125 °C fault-state monitor is a last-resort backup that only matters
  while the unit is already latched in FAULT; above the datasheet's Tc(max
  recommended) = 100 °C. Its value is likewise uncited.

## 5. What this change did (and did not) do

**Changed (single-sourcing, no behavior change):**

1. `firmware/config.yaml` — new `interlocks:` section with the four
   thresholds, each carrying its citation/UNCITED status in `doc:`; emitted
   as bare `#define`s only (`legacy_define_only: true`) so a safety interlock
   stays compile-time constant and is not runtime-tunable via env vars.
2. `firmware/tools/config.h.j2` — `interlocks` added to the legacy `#define`
   block; the `legacy_define_only` branch now emits float literals with the
   `f` suffix (cosmetic; `MESSAGE_DISPLAY_TIME_MS` output unchanged).
3. `firmware/config.h` — regenerated (`python3 firmware/tools/gen_config.py`),
   +4 `#define`s, nothing else changed.
4. `firmware/components/safety/safety.c` — local `#define OVER_TEMP_THRESHOLD`
   / `OVER_CURRENT_THRESHOLD` removed; the names now resolve from `config.h`.
   Hysteresis constants remain local.
5. `firmware/main/state_machine.c` — literals `100.0f` / `50.0f` / `35.0f`
   replaced with `OVER_TEMP_THRESHOLD` / `IGBT_SHORT_CURRENT_THRESHOLD` /
   `OVER_CURRENT_THRESHOLD`.
6. `firmware/main/state_handlers.c` — literal `125.0f` replaced with
   `FAULT_STATE_MAX_TEMP_C`.

**Not changed (deliberately):** any value. `ctest` (13/13 suites) passes
unchanged, including `test_sm_fault_on_over_temperature` (105 °C trips),
`test_sm_fault_on_over_current` (40 A trips), `test_sm_fault_on_igbt_short`
(55 A trips), and `test_sm_fault_on_igbt_short_is_distinct` (40 A →
FAULT_OVER_CURRENT, not FAULT_IGBT_SHORT) — the tests pin behavior, not
constants, and behavior is unchanged.

## 6. Owner decisions required

1. **Thermal hierarchy.** Pick the shutdown story: firmware derate/shutdown
   thresholds below the 85 °C hardware latch (software first), or keep the
   hardware latch as primary with the firmware as a higher backup. Ratchet
   `OVER_TEMP_THRESHOLD` (and `FAULT_STATE_MAX_TEMP_C`) to match, and make
   FUNCTIONAL_SAFETY_TEST_PROCEDURE / THERMAL_DESIGN_GUIDE / FIRMWARE_REQUIREMENTS
   agree on one number. The five committed values (85/95/100/125 °C, plus the
   thermal analysis's 150 °C) cannot all be true.
2. **Current basis and threshold.** Decide what `read_dc_bus_current()`
   returns (peak tank / RMS / filtered) and ratchet `OVER_CURRENT_THRESHOLD`
   to sit above the full-power operating peak with margin and below the
   45 A hardware-window floor. This is blocked on the same unmeasured R_eff
   that `docs/evidence/2026-07-26-ocp01-vs-full-power-current.md` is blocked
   on.
3. **Sensor-read implementation.** `read_dc_bus_current()` and
   `read_heatsink_temperature()` are declared `extern` for ESP_PLATFORM in
   `safety.c`/`state_machine.c` but have **no implementation anywhere in the
   ESP32 HAL** (only the test mock in `firmware/test/state_machine_stubs.c`).
   On real hardware the interlock checks cannot run (link failure if the
   symbols are referenced). Until the ADC drivers exist, every threshold above
   is theoretical — worth flagging in the functional-safety test plan.

## 7. Files touched

- `firmware/config.yaml` (new `interlocks:` section, citations)
- `firmware/tools/config.h.j2` (section list)
- `firmware/config.h` (regenerated)
- `firmware/components/safety/safety.c`
- `firmware/main/state_machine.c`
- `firmware/main/state_handlers.c`
- `docs/requirements/FIRMWARE_REQUIREMENTS.md` (stale validation references)
- this document
