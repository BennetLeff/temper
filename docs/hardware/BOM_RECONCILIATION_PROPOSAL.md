# BOM ↔ Source Reconciliation Proposal

**Status:** proposal only. Nothing under `elec/`, `docs/hardware/BOM.md`, the gate
script, or `bom-reconciliation-allowlist.yaml` is touched by this document.
Every recommendation below is a procurement/design decision for a human (or a
follow-up PR) to apply.

**Scope:** the 49 findings currently seeded into `bom-reconciliation-allowlist.yaml`
(2026-08-07) as backlog, reported by `scripts/check_bom_source_reconciliation.py`
comparing `docs/hardware/BOM.md` against `elec/src/*.ato`. Verified against a live
gate run on this worktree (`154 BOM row(s) / 174 source instantiation(s)`, `49
backlog finding(s) suppressed`, `0 new finding(s)`).

**Counts:** 14 `costed_no_circuit` + 27 `wired_uncosted` (spread over 20 allowlist
entries, several of which cover 2–4 reused-variable-name instances each) + 8
`mpn_mismatch` = 49.

---

## 1. Safety-relevant findings (read this first)

Three root causes, covering 11 of the 49 findings, are not bookkeeping — they
are cases where **trusting `BOM.md` for procurement would put the wrong part
on the board**, not just a different part number for the same part:
`R_DIS1A/1B/2A/2B` (4 findings, §1.1), `R_OCP_REF_T` (1 finding, §1.2), and
the THM-01/THM-02 dividers (6 findings, §1.3). The first two were named in
the task brief; the THM-01/THM-02 case is a **new finding this review
surfaced** — not named in the brief, but the same class of defect as the
discharge-resistor case.

### 1.1 Bus-discharge resistors `R_DIS1A/1B/2A/2B` — BOM's value fails the 60s discharge-time requirement

`docs/hardware/BOM.md:95` costs these as **4.7kΩ** (`AC05000004701JAC00`).
`elec/src/modules.ato:1263-1289` (`BusDischarge`) currently instantiates them
at **3.9kΩ** (`AC05000003901JAC00`) — a deliberate, dated, worst-case-tolerance
resize (`docs/evidence/2026-07-27-busdischarge-tolerance-retune.md`, commit
`66ed6279`, superseding an earlier 4.3k candidate that also failed).

The board's fail-safe active-discharge requirement (`modules.ato:636-640`,
`PowerInput`'s own docstring): bring the bus from 170V to <34V within **<60s**
of power loss, backed by two 3.9k/4.7k resistors in series per half-bus
(2 resistors × N per string) across a nominal 3600µF/half bus capacitance
(`EKMQ251VSN182MA50S`, rated ±20%).

**Recomputed independently** (τ = R·C, t = 1.6094·τ for 170V→34V, i.e.
ln(170/34) = ln(5) = 1.6094):

| Per-string R (2 resistors in series) | t at C = 4320µF (cap's own +20% tol.) | t at C+20% **and** R+5% stacked | vs. <60s target |
|---|---|---|---|
| **9.4k = 2×4.7k (BOM's costed value)** | **65.35s** | — (already fails at C-only) | **FAILS** |
| 8.6k = 2×4.3k (rejected intermediate) | 59.79s | 62.78s | FAILS once R's own tolerance is included |
| **7.8k = 2×3.9k (current source)** | 54.23s | **56.94s** | **PASSES**, ~3.1s margin |

This is a real defect, not a documentation lag: **if `R_DIS1A/1B/2A/2B` were
procured and populated per `BOM.md`'s 4.7kΩ, the built board would take
65.35s to discharge the bus to a safe touch voltage under the capacitor's own
rated tolerance alone — a ~9% overshoot of the board's own 60s safety
target**, before the resistor's own ±5% tolerance is even added. The source's
3.9kΩ is the value that was deliberately derived to clear this target with
margin under stacked worst-case tolerances. Peak dissipation at 3.9k (1.85W,
37% of the 5W rating) is also within spec.

Note: the <60s/<34V target is documented as an internal design comment in
`modules.ato`/`docs/hardware/BUS_CAPACITANCE_DERIVATION.md`, not pinned to a
specific IEC 60335-1 clause number by this repo's own docs (confirmed:
`BUS_CAPACITANCE_DERIVATION.md` line 249 says as much) — the requirement
itself is a design target, not independently re-derived here from the
standard text, but the safe-discharge intent is unambiguous ("Bus capacitors
store hazardous energy... verify bus voltage with a meter before servicing").

**Verdict: BOM is stale, and the staleness is a safety defect if acted on.**
Update `R_DIS1A/1B/2A/2B` to 3.9kΩ / `AC05000003901JAC00`.

### 1.2 OCP-01 reference divider `R_OCP_REF_T` — BOM's value/part is fabricated, not just outdated

`BOM.md:377` costs 3.2kΩ, `RC0603FR-073K2L`. `elec/src/modules.ato:2113-2116`
(`OCPComparator`, OCP-01's `r_ref_top`) currently uses **3.24kΩ**,
`RC0603FR-073K24L` — already fixed in source per the module's own docstring
and `docs/evidence/2026-07-27-ocp01-uvl02-part-resolution.md`: 3.2kΩ is not
an E24 or E96 value, and `RC0603FR-073K2L` returns zero DigiKey hits (the MPN
encodes the same invented "3K2" figure). This is stronger than a value drift
— **BOM currently costs a part number that does not exist at any
distributor.**

Trip-point math (already computed in the source docstring, spot-checked
here): comparator trips when the current-sense signal exceeds
`V_ref = VCC·r_ref_bot/(r_ref_top+r_ref_bot)`. At 3.24k/10k off a 3.3V rail,
`V_ref = 3.3×10000/13240 = 2.492V` (vs. 2.500V at the fictional 3.2k — a
0.3%-of-reference difference, immaterial on its own). Folded through the
current-sense chain and burden resistor, the source's own worst-case sweep
(±1% tol + ±100ppm/°C tempco, ΔT=60°C) gives a trip window of
**48.77–51.16A**, comfortably inside the 45–55A spec (and 46.34–53.71A even
folding in the 3.3V rail's own ±5% regulation tolerance) — so **no residual
defect once the correct part is used**; the only defect is that `BOM.md`
still names a part that was never real.

**Verdict: BOM is stale.** Update `R_OCP_REF_T` to 3.24kΩ /
`RC0603FR-073K24L`. (`R_OCP_REF_B` is already correctly matched — not part of
the 49.)

### 1.3 THM-01 / THM-02 reference/hysteresis dividers — BOM reproduces a design that failed its own hysteresis requirement (new finding)

All 6 rows in `BOM.md` §5.7/§5.8 (`R_THM_REF_T/B`, `R_THM_HYST`,
`R_THM2_REF_T/B`, `R_THM2_HYST`) are in the 49. This is not a rename: BOM's
costed values are byte-for-byte the **superseded** divider values from
before commit `a4fb15dc` (2026-07-26, `fix(elec): add the hysteresis three
gates actually specify`), which exists specifically because those earlier
values under-delivered on `docs/FUNCTIONAL_TEST_CRITERIA.md` §2.3's
requirement:

| Sensor | Required trip/recovery (§2.3) | Required hysteresis | BOM's costed divider (= pre-`a4fb15dc` design) | Hysteresis it gives | Current source divider | Hysteresis it gives |
|---|---|---|---|---|---|---|
| THM-01 (heatsink) | 85°C / 70°C | **15°C** | `r_ref_top`=9.53k, `r_ref_bot`=10k, `r_hyst`=100k | **5.6°C** | `r_ref_top`=9.09k, `r_ref_bot`=11.5k, `r_hyst`=34.8k | **15.2°C** |
| THM-02 (coil) | 120°C / 100°C | **20°C** | `r_ref_top`=9.09k, `r_ref_bot`=10k, `r_hyst`=100k | **6.6°C** | `r_ref_top`=3.16k, `r_ref_bot`=4.42k, `r_hyst`=11.5k | **19.9°C** |

(Trip temperatures were already correct in both the old and new dividers —
only the release/hysteresis behavior changes, per `a4fb15dc`'s commit
message, which contains the full two-constraint E96 derivation and is the
authoritative record; no separate evidence doc exists for this commit.)

**If `BOM.md`'s values were procured, the resulting board's thermal
protection would trip and then re-arm 3–5°C above the actual recovery
temperature**, giving 5.6°C of hysteresis where 15°C is required (THM-01) and
6.6°C where 20°C is required (THM-02) — a real risk of chatter/oscillation
right at the trip threshold instead of a clean latch-until-cooldown, which is
the entire point of a hysteresis band on a thermal-shutdown gate. This is the
same class of defect as §1.1: not a naming mismatch, a **functionally
deficient part set that was already identified and fixed once in source and
never propagated back to the BOM.**

`git log` confirms `BOM.md`'s own THM-01 note ("Re-verified 2026-07-26: this
subsection's parts and values still match source exactly") predates or was
never re-checked against `a4fb15dc` (same day); the BOM's last touch since
then (`b39035f5`, 2026-07-29, unrelated K2/K3 relay note) did not catch it.

**Verdict: BOM is stale for all 6 rows.** Update to: `R_THM_REF_T`→9.09k
(`RC0603FR-079K09L`), `R_THM_REF_B`→11.5k (`RC0603FR-0711K5L`),
`R_THM_HYST`→34.8k (`RC0603FR-0734K8L`), `R_THM2_REF_T`→3.16k
(`RC0603FR-073K16L`), `R_THM2_REF_B`→4.42k (`RC0603FR-074K42L`),
`R_THM2_HYST`→11.5k (`RC0603FR-0711K5L`).

### 1.4 Adjacent but not independently unsafe: K_DIS1/K_DIS2, C_TANK1/C_TANK2

Not computed as defects here, but flagged because they sit in the same
safety-relevant circuits as §1.1 and §1.3:

- **K_DIS1/K_DIS2** (discharge relays, same `BusDischarge` module as §1.1):
  BOM still costs `G5LE-1 DC12`; source has used `RT314012` since
  2026-07-31 (`23f103c9`, finalized `de59c045`/PR #602) specifically because
  the G5LE-1 fails reinforced coil↔contact creepage/clearance (3.559mm vs an
  8.0mm/6.0mm bar). Coil/contact electrical ratings are equivalent (12V/10A
  both parts) — this is an isolation-distance fix, not a rating fix, so it
  does not change the §1.1 discharge-time math. `BOM.md`'s own note at line
  90 describes a *different*, already-reverted, earlier relay excursion and
  was never updated after the real (`23f103c9`) swap landed.
- **C_TANK1/C_TANK2** (resonant tank caps): BOM still costs 2× WIMA 150nF
  `FKP1T031507G00JSSD`; source has used 3× CDE 100nF `942C16P1K-F` since
  2026-07-29 (`3ae26dfe`, PR #410) because the WIMA part's AC-current rating
  undershot the 10.37A required at 47kHz switching (CDE clears at 1.38×
  margin). Same 300nF total, but the physical part count grew from 2→3
  (see `c_tank3` in §3) and tolerance loosened ±5%→±10%, neither reflected
  in BOM.

Both are **BOM is stale**; see §4 for designator-level detail.

---

## 2. `costed_no_circuit` (14) — BOM costs a part with no matching source designator

| BOM designator | BOM value/MPN | Cause | Verdict | Evidence |
|---|---|---|---|---|
| R_OCP_REF_T | 3.2kΩ, `RC0603FR-073K2L` (fabricated) | Fabricated E-series value/MPN, since fixed in source to 3.24k | **BOM stale** — see §1.2 | `docs/evidence/2026-07-27-ocp01-uvl02-part-resolution.md` |
| R_OVP1, R_OVP2, R_OVP3 | 430kΩ, `RC1206FR-07430KL` | Pure designator drift — source's `r_div_top1/2/3` (modules.ato:2251-2270) have the **identical** value+MPN, untouched by the 07-26/07-27 OVP redesign (protective-impedance chain deliberately not touched) | **Not real drift** — designator-normalization miss only | n/a — value already correct |
| R_OVP4 | 10kΩ, `RC0603FR-0710KL` | Source's `r_div_bot` (2295) is now 16.9kΩ, `RT0603BRD0716K9L` — re-derived for the fixed REF2025 reference (Option C) | **BOM stale** | `docs/evidence/2026-07-27-ovp01-ref2025-implementation.md` |
| R_OVP_REF_T | 732Ω, `RC0603FR-07732RL` | Resistor **deleted from the circuit entirely** — `comp.INN` now driven directly by `RTDSensing`'s REF2025 `VREF` (2.5V fixed) | **BOM stale** — strong form: costs a part that no longer exists on the board | `docs/evidence/2026-07-27-ovp01-ref2025-implementation.md`, `docs/evidence/2026-07-27-threshold-sensitivity-tempco-budget.md` |
| R_OVP_REF_B | 10kΩ, `RC0603FR-0710KL` | Same deletion as R_OVP_REF_T | **BOM stale**, same strong form | same |
| R_OVP_ADC_T | 510kΩ, `RC1206FR-07510KL` | Split into 3× 169kΩ `RC1206FR-07169KL` (`r_adc_top1/2/3`) — single-resistor divider violated IEC 60335-1 protective-impedance (one shorted top resistor dumps full bus across `r_adc_bot`, ~29× its power rating) | **BOM stale** — needs 3 new rows, not a value edit | `docs/evidence/2026-07-26-ovp-crossing-resolution.md` |
| R_THM_REF_T | 9.53kΩ | Superseded pre-`a4fb15dc` value; current source 9.09k | **BOM stale** — see §1.3 | commit `a4fb15dc` |
| R_THM_REF_B | 10kΩ | Superseded; current source 11.5k | **BOM stale** — see §1.3 | commit `a4fb15dc` |
| R_THM_HYST | 100kΩ | Superseded; current source 34.8k | **BOM stale** — see §1.3 | commit `a4fb15dc` |
| R_THM2_REF_T | 9.09kΩ | Superseded (THM-02's own first-revision value, not a copy-paste of THM-01's current value); current source 3.16k | **BOM stale** — see §1.3 | commit `a4fb15dc` |
| R_THM2_REF_B | 10kΩ | Superseded; current source 4.42k | **BOM stale** — see §1.3 | commit `a4fb15dc` |
| R_THM2_HYST | 100kΩ | Superseded; current source 11.5k | **BOM stale** — see §1.3 | commit `a4fb15dc` |

R_OVP1-3 aside (3 designators, already correct, just unmatched by name),
all 11 remaining rows are **BOM is stale**, none genuinely ambiguous.

---

## 3. `wired_uncosted` (27 findings / 20 allowlist entries) — source has a part with no matching BOM row

| Source designator(s) | Value/MPN | Circuit | Verdict / proposed action | Evidence |
|---|---|---|---|---|
| `r_div_top1/2/3` | 430k, `RC1206FR-07430KL` | OVP-01 divider top | Alias of R_OVP1-3 — see §2, no BOM edit needed beyond designator mapping | — |
| `r_div_bot` (OVP-01) | 16.9k, `RT0603BRD0716K9L` | OVP-01 divider bottom | Replaces R_OVP4 — see §2 | `docs/evidence/2026-07-27-ovp01-ref2025-implementation.md` |
| `r_hyst` (OVP-01 instance, line 2366) | 487k, `RT0603BRD07487KL` | OVP-01 hysteresis feedback | **New BOM row needed** (`R_OVP_HYST`) — this resistor has **no BOM.md row at all**, old or new; a genuine uncosted gap surfaced by this review, not previously flagged in §5.6's note | `docs/evidence/2026-07-27-ovp01-ref2025-implementation.md` (derivation) |
| `r_adc_top1/2/3` | 169k, `RC1206FR-07169KL` ×3 | OVP-01 ADC-tap divider top | Replaces R_OVP_ADC_T — see §2 | `docs/evidence/2026-07-26-ovp-crossing-resolution.md` |
| `r_hyst` (THM-01, line 2541) | 34.8k, `RC0603FR-0734K8L` | THM-01 hysteresis | Replaces R_THM_HYST — see §1.3 | commit `a4fb15dc` |
| `r_hyst` (THM-02, line 2634) | 11.5k, `RC0603FR-0711K5L` | THM-02 hysteresis | Replaces R_THM2_HYST — see §1.3 | commit `a4fb15dc` |
| `r_hyst` (UVLO-02, line 2940) | 3.74M, `RC0603FR-073M74L` | UVLO-02 hysteresis | Part of a wholly uncosted circuit — see below | `docs/hardware/UVL02_DESIGN.md` |
| `r_ref_top` (OCP-01, line 2113) | 3.24k, `RC0603FR-073K24L` | OCP-01 reference divider top | Replaces R_OCP_REF_T — see §1.2/§2 | `docs/evidence/2026-07-27-ocp01-uvl02-part-resolution.md` |
| `r_ref_top` (THM-01, line 2522) | 9.09k, `RC0603FR-079K09L` | THM-01 reference divider top | Replaces R_THM_REF_T — see §1.3 | commit `a4fb15dc` |
| `r_ref_top` (THM-02, line 2618) | 3.16k, `RC0603FR-073K16L` | THM-02 reference divider top | Replaces R_THM2_REF_T — see §1.3 | commit `a4fb15dc` |
| `r_ref_top` (OCP-02, line 2745) | 3.74k, `RC0603FR-073K74L` | `SecondaryOCPComparator` (OCP-02) reference divider top | **Not a content defect — same status as the already-explained `shunt`/`r_ref_bot` OCP-02 findings.** `ocp2 = new SecondaryOCPComparator` is commented out at `main.ato:3058`; OCP-02 is designed but deliberately not wired into the board pending the sensing-domain topology decision BOM.md §4.4 already documents. No BOM row needed until that decision is made. | `main.ato:3056-3058`, BOM.md §4.4 |
| `boot_cap` | 10µF, `GRM32ER71H106KA12L` | `GateDriveHS` bootstrap cap | **False positive, not a real gap.** `BOM.md:19` already has `C_BOOT` with the *exact same MPN/value/qty*. It's simply un-allowlisted — same situation `D_BOOT` was in before its own manual allowlist entry. Proposed action: add a `costed_no_circuit`-style manual entry mapping `C_BOOT`↔`boot_cap`, same pattern as the existing `R_NTC_PU`/`R_DT` entries. **No BOM.md edit needed.** Note in passing: `BOM.md` has a *second*, unrelated `C_BOOT` row at line 164 (buck-converter bootstrap cap, different part) — a designator collision worth a follow-up cleanup, out of scope here. | — |
| `c_tank3` | 100nF, `942C16P1K-F` | Resonant tank (3rd cap) | Real gap: PR #410 grew the tank from 2→3 physical caps; BOM §1.4 still lists qty 2. **Bump `C_TANK1, C_TANK2` row to qty 3** (or add an explicit `C_TANK3` row) in the same edit that fixes the MPN mismatch (§1.4/§4) | `3ae26dfe` (PR #410) |
| `fault_or3` | `SN74HC4075DR` | Safety interlock fault fan-in (UVLO-02 addition) | Real gap — allowlist's own note confirms `U_OR1`/`U_OR2` (BOM §5.2) cover `fault_or`/`fault_any_or` only; `fault_or3` added 2026-07-27 for UVLO-02 fan-in capacity has no BOM row. **New row needed.** | — |
| `zcd_opto` | `H11L1TVM` | ZCD isolation optocoupler | See §5 (H11L1 branch) | `docs/evidence/2026-07-26-ovp-crossing-resolution.md`-adjacent SELV redesign |
| `r_zcd_opto` | 430Ω, `RC0603FR-07430RL` | ZCD opto LED drive | See §5 | same |
| `r_zcd_pullup` | 10k, `RC0603FR-0710KL` | ZCD opto output pull-up | See §5 | same |
| `mon`, `r_div_top`, `r_div_bot`, `r_hyst`, `r_outa_pullup`, `inv` (UVLO-02 instances) | TPS3700DDCR; 698k `RC0603FR-07698KL`; 100k `RC0603FR-07100KL`; 3.74M `RC0603FR-073M74L`; 10k `RC0603FR-0710KL`; SN74LVC1G38DBVR | `LogicUVLOComparator` (UVLO-02), a full non-negotiable STRATEGY gate | **Real, wholesale pricing gap — the entire UVLO-02 circuit (6 line items here, plus `fault_or3` and `tp_uvlo2_fault` below = 8 total) is missing from BOM.md.** Not a same-cost alias of the RTD hardware-window chain (§4.6) or anything else already priced. **Add a new BOM subsection** (e.g. "§5.9 Logic UVLO (UVLO-02)") with all 8 parts. **Correction**: `r_fault_pullup`'s UVLO-02 instance (`modules.ato:2979`, reused-name sibling of the RTD chain's `r_fault_pullup`) is *not* actually one of the 49 gate findings — verified directly against a live gate run's `ALLOWLISTED -- BACKLOG` section, which does not list it (only its own diagnostic prose, printed for the *already-matched* RTD instance, says the 2979 instance "is left as a real finding" — that claim does not match the gate's actual current output, a discrepancy worth a separate follow-up on the gate itself, not actioned here). | `docs/hardware/UVL02_DESIGN.md`, `docs/evidence/2026-07-26-uvl02-logic-uvlo-sim.json`, `docs/evidence/2026-07-27-uvl02-logic-uvlo-sim.json`, MPN history in `docs/evidence/2026-07-27-ocp01-uvl02-part-resolution.md` |
| `tp_uvlo2_fault` | `GENERIC_TEST_POINT` | UVLO-02 bench probe point | Real gap — BOM §10.2 lists only TP1/TP2 (TP3-5 were explicitly *removed* as having no source counterpart at the time); this is a newer, distinct instance. **Add as TP3 (or similar) in §10.2**, alongside the UVLO-02 subsection. | — |

Verdicts: 22 of 27 are **source is correct, BOM needs a new/updated row**
(the OVP/THM/OCP-01 `r_ref_top`/`r_hyst` instances are covered under §1–2,
cross-referenced above, not separately actioned here). 1 (`boot_cap`) is a
**false positive** — a gate/allowlist gap, not a BOM content gap. 1
(`r_ref_top`, OCP-02 instance) is **not a content defect** — OCP-02 is
deliberately unwired pending a design decision BOM.md already documents.
`r_hyst` (OVP-01) is a genuinely new gap this review found (no prior BOM
note even mentions it), separate from the already-tracked R_OVP_REF_T/B
deletion. Net actionable rows to add/update: `r_div_top1-3` (alias only),
`r_div_bot`/OVP-01, `r_hyst`/OVP-01 (new), `r_adc_top1-3`, `r_hyst`×2
(THM-01/02, covered in §1.3), `boot_cap` (allowlist only), `c_tank3`,
`fault_or3`, the ZCD trio (§5), the full UVLO-02 group (7 items), and
`tp_uvlo2_fault`.

---

## 4. `mpn_mismatch` (8) — designator matches, but MPN/value disagrees

| Designator | BOM | Source | Cause | Verdict | Evidence |
|---|---|---|---|---|---|
| K_DIS1 | `G5LE-1 DC12` | `RT314012` (modules.ato:1227) | Reinforced-isolation fix, 2026-07-31 → 2026-08-03 | **BOM stale** — see §1.4 | `23f103c9` (origin), `0f0a1341` (interim board-placement revert of `k_dis2` only), `de59c045`/PR #602 (final) |
| K_DIS2 | `G5LE-1 DC12` | `RT314012` (modules.ato:1249) | Same swap, mirrored, delayed by a placement blocker | **BOM stale** — see §1.4 | same three commits |
| C_TANK1 | `FKP1T031507G00JSSD` | `942C16P1K-F` (modules.ato:513) | AC-current re-sourcing, PR #410 | **BOM stale** — see §1.4 | `3ae26dfe` |
| C_TANK2 | `FKP1T031507G00JSSD` | `942C16P1K-F` (modules.ato:520) | Same | **BOM stale** — see §1.4 | `3ae26dfe` |
| R_DIS1A | `AC05000004701JAC00` (4.7k) | `AC05000003901JAC00` (3.9k, modules.ato:1263) | Worst-case tolerance retune | **BOM stale — safety-relevant** — see §1.1 | `docs/evidence/2026-07-27-busdischarge-tolerance-retune.md` |
| R_DIS1B | same | same (modules.ato:1270) | same | **BOM stale — safety-relevant** | same |
| R_DIS2A | same | same (modules.ato:1277) | same | **BOM stale — safety-relevant** | same |
| R_DIS2B | same | same (modules.ato:1284) | same | **BOM stale — safety-relevant** | same |

All 8 are **BOM is stale**, none ambiguous. The task brief's `0f0a1341`/
`de59c045` attribution for K_DIS is directionally right but incomplete: the
actual MPN swap originates at `23f103c9`; `0f0a1341` is an *interim revert*
of `k_dis2` specifically (kept `k_dis1`'s swap, reverted `k_dis2`'s, to match
an unresolved PCB placement blocker), and `de59c045` is what finally lands
both relays at `RT314012` together.

---

## 5. H11L1 / ZCD branch — the net-49→50 (or →46) case

A prepared, unmerged commit `27725af9` ("`fix(elec): delete U3 (H11L1
mains-ZCD optocoupler) and its dedicated circuitry`", 2026-07-30, on
`origin/codex/handoff-actionables`, not an ancestor of `main`; also
cherry-picked as `5842767c` on sibling worktree branch
`worktree-agent-a671f1b607d4fe283`, which carries a second follow-on commit
`300c4a70` "drop ZCD_ISO from the split-board SELV interface contract")
deletes the **entire** ZCD block as one hunk — not just the H11L1 opto
chain, but also the HV-side divider+clamp (`r_zcd_top1`, `r_zcd_top2`,
`r_zcd_bot`, `d_zcd_clamp`) that the opto chain feeds.

**Current state:** `R_ZCD_TOP1/TOP2`, `R_ZCD_BOT`, `D_ZCD_CLAMP` (BOM.md:60-62)
already match `r_zcd_top1/top2/bot`/`d_zcd_clamp` cleanly (not in the 49).
Only the opto trio (`zcd_opto`, `r_zcd_opto`, `r_zcd_pullup`) is currently
`wired_uncosted`, backlogged as 3 of the 27.

**If the branch lands as-is** (source deletion only, no BOM edit): the 3
opto-trio `wired_uncosted` findings resolve (49→46), but the 4
divider/clamp BOM rows become newly orphaned `costed_no_circuit` findings
(46→**50**) — net worse than today, exactly as the task brief anticipated,
just because the whole ZCD block moves together rather than the opto chain
alone.

**If BOM.md is pruned of `R_ZCD_TOP1/TOP2/BOT`/`D_ZCD_CLAMP` in the *same*
change that lands the branch**: 49→46, net improvement, no orphans.

**Proposed action:** this is a design decision (whether to actually remove
mains-side ZCD sensing and rely on some other soft-start timing mechanism —
not evaluated here, out of scope), not a reconciliation call. **Recommend:
if/when the maintainer decides to merge `27725af9`, require the BOM.md prune
in the same PR**, mirroring this repo's own stated discipline elsewhere
(AGENTS.md's "same-PR" pattern for DRC-ceiling re-measurement) — a
follow-up BOM cleanup PR would just repeat the exact gap this reconciliation
gate exists to catch.

---

## 6. Ordering — what unblocks fabrication soonest

**Tier 1 — fix before any procurement run (wrong part would be built into
hardware, two are safety-relevant):**
1. `R_DIS1A/1B/2A/2B` → 3.9k / `AC05000003901JAC00` (§1.1)
2. `R_THM_REF_T/B`, `R_THM_HYST`, `R_THM2_REF_T/B`, `R_THM2_HYST` → new
   values (§1.3)
3. `K_DIS1/K_DIS2` → `RT314012` (§1.4)
4. `C_TANK1/C_TANK2` → `942C16P1K-F`, qty 3 with `c_tank3` folded in (§1.4, §3)

**Tier 2 — parts entirely missing from BOM (board cannot be fully populated
without them, but wrong-part risk doesn't apply since nothing would be
ordered at all):**
5. UVLO-02 full 7-item subsection (§3)
6. `fault_or3`, `tp_uvlo2_fault`, `r_hyst` (OVP-01) new rows (§3)
7. `boot_cap`/`C_BOOT` allowlist entry (no BOM content change, just closes a
   gate false-positive) (§3)

**Tier 3 — cleanup, no populated-hardware risk:**
8. `R_OCP_REF_T` → 3.24k / `RC0603FR-073K24L` (§1.2 — low urgency because the
   fictional MPN can't actually be ordered, so nobody would build the wrong
   part; still worth fixing so nobody wastes time chasing a nonexistent part
   number)
9. `R_OVP4`, `R_OVP_REF_T/B` (delete 2 rows), `R_OVP_ADC_T` (split into 3
   rows) (§2)
10. `R_OVP1/2/3` designator alias fix (cosmetic — value was never wrong) (§2)

**Tier 4 — blocked on a design decision, not actionable yet:**
11. H11L1/ZCD branch merge-and-prune coordination (§5)

Tiers 1–3 are all independent of each other and of Tier 4; none blocks any
other. Tier 4 is the only item with an open dependency (a merge decision
outside this reconciliation's scope).

---

## Summary counts

| Category | Count |
|---|---|
| Total findings | 49 |
| `costed_no_circuit` | 14 |
| `wired_uncosted` | 27 (20 allowlist entries; `r_ref_top`/`r_hyst` each cover 4 reused-name instances, `r_div_bot` covers 2) |
| `mpn_mismatch` | 8 |
| Verdict: BOM is stale (real edit needed) | 41 |
| Verdict: not a real defect (designator/matcher artifact only — `R_OVP1`/`R_OVP2`/`R_OVP3` (3) + `r_div_top1`/`r_div_top2`/`r_div_top3` (3) + `boot_cap` (1) = 7) | 7 |
| Verdict: not a content defect (deliberate, already-documented design decision — OCP-02's `r_ref_top` instance) | 1 |
| Verdict: source is stale | 0 |
| Verdict: genuinely ambiguous | 0 |
| Safety-relevant (§1) | 11 findings across 3 root causes: `R_DIS1A/1B/2A/2B` (4), `R_OCP_REF_T` (1), THM-01/THM-02 dividers (6) |
