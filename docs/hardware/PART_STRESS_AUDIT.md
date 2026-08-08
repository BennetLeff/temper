# Part Stress Audit — Applied Stress vs. Absolute-Maximum Rating

**Date:** 2026-08-07
**Scope:** every component in `elec/build/default.csv` (the compiled netlist
BOM — used per `docs/STRATEGY.md`'s "`default.net` aliases part identity by
footprint" finding, not `default.net`), cross-checked against
`elec/src/main.ato`, `elec/src/modules.ato`, `elec/src/components.ato` and
real datasheets in `datasheets/` plus manufacturer sources fetched for this
pass.
**Status:** analysis only. **No files under `elec/`, `pcb/`, or
`docs/hardware/BOM.md` were changed.**
**Provenance:** `elec/build/` is gitignored and was rebuilt for this pass
(`ato --non-interactive build` from `elec/`, atopile 0.2.69) at this
worktree's HEAD. `elec/build/default.csv` records **89 BOM lines / 169
component instances** (designators).

Every number below is either (a) quoted from a real datasheet named inline,
(b) quoted from an existing in-repo evidence document (cited), or (c)
computed here from committed `.ato` values and labeled **DERIVED** with the
formula shown. Nothing is estimated without a labeled source. Where no rating
could be found, the entry is marked **UNKNOWN** — see §6.

---

## 0. Headline

**The known ~5× bus-capacitor ripple-current failure (`docs/STRATEGY.md`,
2026-07-26) is still live.** `C2/C3/C4/C5` (`EKMQ251VSN182MA50S`) are
unchanged in `elec/src/modules.ato:798-825` since that finding was recorded.
No board, netlist, or BOM change has touched this bank. See §1.1.

**One new likely-over-rating finding, architecture-level, not previously
documented:** at the low end of the device's own declared AC input voltage
tolerance, holding the rated 1800 W output would draw more current through
`F1`/`L1` (fuse, common-mode choke) than either is rated for — a **normal,
in-tolerance operating condition**, not a fault. See §1.2. This is derived,
not measured, and depends on an assumption about firmware behavior that this
audit could not verify either way (no line-voltage-based power derating was
found in `firmware/`, but its absence there is not proof of its absence in
general).

**Three ceramic capacitors carry the same DC-bias risk the design already
flags on two sibling parts, but are not themselves flagged.** See §2.1.

**One resistor-power safety assertion in `elec/src/modules.ato` is written
backwards** relative to the identical check 250 lines later in the same
file, and is nearly vacuous as written. See §4.

---

## 1. AT OR OVER RATING — lead findings

### 1.1 Bus capacitors: ripple current, ~4.2–5.8× rated (STILL LIVE)

| | |
|---|---|
| Designators | `C2, C3, C4, C5` |
| MPN | `EKMQ251VSN182MA50S` (United Chemi-Con KMQ series) |
| Location | `elec/src/modules.ato:798-825`, two in parallel per half-bus (`+170V_BUS` and `DC_BUS_RTN` sides) |
| Rating | **2.70 A<sub>rms</sub> ripple current, 105 °C, 120 Hz** — United Chemi-Con CAT. No. E1001E, KMQ series, 250 V row, 1800 µF, φ35×L50 |
| Applied | **11.39–15.57 A per cap**, combined 60 Hz mains-recharge + ~35–47 kHz switching ripple in quadrature, across best/central/worst efficiency-and-conduction-angle scenarios |
| Margin | **4.22×–5.77× over rated ripple current** (central case 4.82×) |

Full derivation: `docs/evidence/2026-07-26-bus-capacitor-ripple.md` (still
accurate — re-checked against the current `modules.ato` for this pass, no
values changed). Re-verified here that the design is unchanged: `c_bus1`,
`c_bus1b`, `c_bus2`, `c_bus2b` are still `EKMQ251VSN182MA50S`/1800 µF/250 V,
same topology, same doubler. **This is not a hypothetical — it is the
project's own previously-confirmed finding, and it has not been remediated.**
No ESR-matching assumption in the evidence doc's own §6 closes a gap this
large; any real parallel-pair mismatch makes it worse, not better.

Voltage margin on the same parts is fine (250 V rated vs. 170 V half-bus
nominal = 32% margin, clears the >20% electrolytic-voltage guideline) — this
is a **current**, not voltage, failure.

### 1.2 AC input current at low line voltage vs. fuse/CMC rating (DERIVED, conditional — new finding)

| | |
|---|---|
| Designators | `F1` (fuse), `L1` (common-mode choke) |
| MPN | `0034.3129` (Schurter FST 5×20, 16 A time-lag), `B82726S2163N030` (TDK/EPCOS CMC) |
| Rating | **16 A continuous** each. Fuse: Schurter FST family, time-lag 5×20 (`elec/src/modules.ato:660-676`). CMC: **16 A rated, referred to 50 Hz, ΔT<sub>R</sub> +60 °C** — TDK datasheet, "Date: April 2025" rev., cited directly in `elec/src/components.ato:258-276` |
| Design assumption used elsewhere in-source | `ACMainsConstraints.i_max = 15A` (`elec/src/constraints.ato:10-12`), computed only at 120 V nominal (1800 W / 120 V = 15 A) |
| Applied, **at the documented low end of the input tolerance band** | **18.1–19.6 A** at 108 V (`docs/ENVIRONMENTAL_SPEC.md` §1: "Supply Voltage (US): Min 108, Typ 120, Max 132 V AC"), **19.6–21.2 A** at 100 V (`main.ato:56`'s wider assert, `v_ac_nominal within 100V to 130V`) |

**DERIVED**: `I_line = P_out / (η · V_line)`, `P_out = 1800W`
(`main.ato:53`), `η ∈ {0.85, 0.90, 0.92}` — the project's own committed
efficiency band (`main.ato:500-501`: `eta_min = 0.90`, `assert eta_min >=
0.85`; STRATEGY's EFF-02 target 92%, unmeasured). This is the same A1/A2
efficiency framing `docs/evidence/2026-07-26-bus-capacitor-ripple.md` §3 uses
for the bus-cap derivation, applied here to the AC side instead of the DC
side.

| V_line | η=0.92 | η=0.90 (committed target) | η=0.85 (committed floor) |
|---|---|---|---|
| 108 V | 18.12 A (−13.2% vs. 16A) | 18.52 A (−15.7%) | 19.61 A (−22.5%) |
| 100 V | 19.57 A (−22.3%) | 20.00 A (−25.0%) | 21.18 A (−32.4%) |

At every point in this table, line current **exceeds** both the fuse's and
the CMC's 16 A rating — the negative "margin" column above is `(16 −
I_line)/16`. At 100 V/η=0.90 the current (20.00 A) also lands exactly at the
bypass relay's own 20 A contact rating (`bypass_relay.contact_current = 20A`,
`elec/src/modules.ato:757-761`), and every η=0.85 case exceeds it.

**Why this is flagged as conditional, not confirmed:** this holds only if
the control loop tries to hold constant 1800 W output as line voltage sags —
plausible for a temperature-PID-driven power loop (STRATEGY's PID-01…04
gates describe exactly this kind of control) but not independently confirmed
here. `grep` for line-voltage-based power derating in `firmware/main` and
`firmware/components` found no matches; that is evidence of absence, not
proof — this codebase's own repeated lesson (STRATEGY's fabricated-MPN and
fail-open-OVP incidents) is that "no code found" and "no code exists" are not
the same claim without a fuller firmware audit, which is out of this
document's scope (netlist/BOM-level, not firmware). **No per-component
assertion in `elec/src` currently derives `ACMainsConstraints.i_max` from
the declared voltage tolerance band × rated power** — it is a flat 15 A
constant, computed only at the 120 V nominal case. This gap is real
regardless of the firmware answer: even if firmware does derate, nothing in
`elec/src` encodes or checks that it must.

### 1.3 Resonant-tank coil: peak current vs. its own pad rating (already flagged in-source, reconfirmed)

| | |
|---|---|
| Designator | `R30` (declared as `Inductor`, deliberately mis-prefixed — see the docstring at `modules.ato:598-616`) |
| MPN | `CUSTOM_LITZ_COIL` — not a purchased part |
| Rating | `current_rating = 25A` (imposed thermal requirement, not a datasheet figure); footprint `LitzPad_15A` — **15 A** by its own name |
| Applied | **28.7–31.9 A peak** (both the previous 150 µH model and the current 88 µH model land in this range — `modules.ato:585-596`) |
| Margin | **Negative against both figures**: 15A pad rating exceeded by ~1.9–2.1×; the 25A imposed current_rating exceeded by 15–28% |

This is not a new finding — `modules.ato:585-596` already states it
plainly ("UNRESOLVED AND RECORDED, NOT FIXED HERE... Both were already
exceeded by the PREVIOUS 150uH model's own committed 28.71A peak — this
declaration surfaces the conflict, it does not create it"). Reconfirmed
current at this pass: unchanged.

---

## 2. BELOW NORMAL DERATING GUIDELINE

Guideline used throughout, per this task's instructions: **<20% margin on
working voltage for electrolytics**, **<50% margin (i.e. operating above
50% of rated voltage) for Class II ceramics under DC bias**, and by
extension here, **<20% margin on continuous current for
fuses/inductors/magnetics** and **<50% margin on continuous resistor power
dissipation** (a common thick-film/thin-film SMD guideline, distinct from
any part-specific curve — flagged where a real derating curve was not
independently pulled).

### 2.1 Ceramic capacitors at 60–68% of rated voltage (DC bias) — three unflagged, two already flagged

Class II (X7R) MLCCs lose a large fraction of nominal capacitance under DC
bias, worse than their voltage rating alone implies — this project already
flags this explicitly for two parts. This audit found **three more
structurally identical instances that carry no such flag**, one of them at a
worse bias ratio than either flagged part:

| Designator | MPN | Rated V | Applied V | Bias ratio | Flagged in-source? |
|---|---|---|---|---|---|
| `C14` | `GRM55DR72E106KW01L` (Murata, 10µF, 2220) | 250 V | 170 V (`AuxSupply.c_in_bulk`, half-bus input) | **68%** | **No** (`docs/hardware/BOM.md:181` lists it plainly; no derating note) |
| `C9` | `GRM32ER71E106KA12L` (Murata, 10µF, 1210) | 25 V | 15 V (`BuckConverter3V3.c_in`, on the +15V rail) | 60% | **No** (`BOM.md:161`) |
| `C15` | `GRM32ER71E107ME15L` (Murata, 100µF, 1210) | 25 V | 15 V (`AuxSupply.c_out`, +15V rail output filter) | 60% | **No** (`BOM.md:182`) |
| `C10` (×2, `c_vdda`/`c_vddb`) | `C0603C104K5RACTU` | 25 V | 15 V | 60% | Yes — `modules.ato:312-325`, `BOM.md:38` |
| (AuxSupply `c_out_hf`) | `C0603C104K5RACTU` | 25 V | 15 V | 60% | Yes — `modules.ato:1618-1621`, `BOM.md:183` |

`C14` (`c_in_bulk`) is the **worst instance found in the whole design** —
68% vs. the flagged parts' 60% — and it carries no comment or BOM note at
all, unlike its two structurally-identical (60%-biased) siblings which do.
None of the five have a part-specific DC-bias derating curve pulled from a
datasheet in this repo; all five should be treated as **UNVERIFIED
capacitance retention**, not as still-nominal, per the existing flag's own
language (`modules.ato:314-325`).

Separately: `GRM55DR72E106KW01L` (`C14`) itself was **not independently
confirmed to exist at any distributor** in this pass or any prior one — a
web search found only its 1 µF sibling (`GRM55DR72E105KW01L`) at Mouser; the
10 µF/250V/2220 variant's naming is consistent with Murata's real GRM55
family code (confirmed against the sibling), but is not distributor-verified
here. `docs/evidence/2026-07-26-bom-availability-sweep.md:111,115`
confirms this part was explicitly excluded from that pass's spot-check
("excluded on the brief's own instruction to sample rather than exhaustively
check commodity passives"). Given this project's repeated history of caught
fabricated MPNs, this is listed as **UNKNOWN (part existence unverified)**,
not asserted fake — see §6.

### 2.2 Common-mode choke: current margin 6.25% at nominal 120V/15A (below the >20% guideline)

| | |
|---|---|
| Designator | `L1` |
| MPN | `B82726S2163N030` |
| Rating | 16 A (50 Hz, ΔT<sub>R</sub> +60°C) — TDK datasheet, cited `components.ato:258-276` |
| Applied | 15 A (`ACMainsConstraints.i_max`, 120 V nominal, 1800 W) |
| Margin | **(16−15)/16 = 6.25%** |

Below the 20% current-margin guideline even at the design's own nominal-only
assumption, before §1.2's low-line-voltage scenario is even considered (in
which this part is driven **over** rating, not just under-margined).

### 2.3 Fuse: same 6.25% margin (already flagged in-source)

`F1` (`0034.3129`, 16 A time-lag) against the same 15 A nominal design
current — `elec/src/modules.ato:668-676` already flags this exact number
("only ~7% headroom above rated full-load current... no I²t coordination
analysis... has been found anywhere in this repo"). Reconfirmed unchanged.
See §1.2 for the low-line-voltage case, which pushes this from "thin margin"
to "over rating."

### 2.4 Bus bleeder resistors: 34.5% power margin (below the 50% guideline) — and see §4 for the assertion bug

| | |
|---|---|
| Designators | `R4, R5` |
| MPN | `CRGP2512F22K` (22 kΩ, 2 W rated — "2W@70C pulse-withstanding", verified `modules.ato:831` comment) |
| Applied | `p_bleed_actual = 170V × 170V / 22kΩ = 1.31W` (continuous, always-on across a half-bus whenever the unit is powered — `modules.ato:845`) |
| Margin | `(2W − 1.31W)/2W = 34.5%` — **below the 50% guideline**, i.e. the part runs at 65.5% of its rated continuous power |

This is a continuous-duty resistor (not a pulse/transient load), inside an
enclosure with a declared ambient up to 50°C (`main.ato:490`,
`t_ambient_max = 323.15K`) before self-heating. 65.5% continuous loading is
inside the part's rating but outside the conventional 50% derating margin
for long-life continuous SMD resistor operation. See §4 — the in-source
assertion meant to catch this does not actually enforce a 50% margin.

### 2.5 Tank capacitors: ripple current margin 27–38% (thin, but passing; already analyzed in-source)

| | |
|---|---|
| Designators | `C25, C26, C27` |
| MPN | `942C16P1K-F` (Cornell Dubilier 942C, 0.10µF/1600VDC film) |
| Rating (transferred to 47kHz) | **9.5 A** per cap — CDE catalog 942C.pdf p.2 (11.4A @ 100kHz/70°C) × 0.84 frequency-transfer factor, both cited `modules.ato:468-496` |
| Applied | 6.92 A/cap at the committed 20.75A tank RMS point (1.38× margin), 7.50 A/cap at the 88µH-coil 22.5A stress point (1.27× margin) |

Not flagged as a failure — margin is positive and above the <20% floor this
audit uses for a hard flag — but it is thin enough (27–38%, not the >50%
comfort margin electrolytics/film parts usually carry in this design) to
list here rather than in the "adequate margin" bucket. Also carries a
**tolerance regression**, not a stress finding: 942C's K=±10% tolerance vs.
the WIMA J=±5% part it replaced widens the resonant-frequency spread — see
`modules.ato:498-505`, already tracked via `check_pll_range_consistency.py`.

### 2.6 Coil NTC (THM-02): within 5°C of its own maximum operating temperature

| | |
|---|---|
| Designator | `R60`/`R65`-family (`NTCALUG01A104GA`, two instances — heatsink THM-01 and coil THM-02) |
| Rating | +125°C max operating — Vishay BCcomponents datasheet 29092, cited `modules.ato:2476-2483` |
| Applied (coil instance) | trips at **120.3°C** (`CoilThermalComparator`, `modules.ato:2582-2586`) |
| Margin | `(125−120.3)/125 = 3.8%` |

Already flagged in-source verbatim: "SENSOR RATING CAVEAT... this gate trips
at 120.3C, so the sensor operates within 5C of its maximum... Flagged rather
than silently accepted" (`modules.ato:2582-2586`). Reconfirmed unchanged.

---

## 3. Adequate margin — summary (not exhaustively narrated)

Components below were checked and clear both the stated safety assertion and
this audit's derating guidelines with room to spare. Grouped, not itemized
per-instance, to keep this document proportional to what needs attention.

| Group | Designators | Rated | Applied | Margin | Datasheet basis |
|---|---|---|---|---|---|
| Half-bridge IGBTs | `U5, U6` | 1200V / 40A@Tc=100°C | 340V bus / ≤32A peak | V: 71.7%, I: 20%+ | Infineon IKW40N120H3, `datasheets/infineon-ikw40n120h3-datasheet-en.pdf` (**Rth(j-c)=0.31 K/W, Tvjmax=175°C** confirmed directly from this PDF for this pass — see §6 for why the in-repo thermal budget using these should be re-run) |
| Gate driver isolation | `U7` | 5000V | primary/secondary barrier | large | TI UCC21550BDWKR, `modules.ato:27-49` (package/pinout independently re-verified 2026-07-28) |
| Bootstrap diode | `D5` (`ES1J`) | 600V/1A | ~340V bus swing, mA-level avg. current | V: 43%+ | onsemi ES1J, `components.ato:297-308` |
| Rectifier diodes | `D1, D3` (`MUR1560G`) | 600V/15A | 340V reverse, ~6–12A avg (central-case, `docs/evidence/2026-07-26-bus-capacitor-ripple.md` §3) | large on both axes | ON Semi MUR1560, `components.ato:283-296` |
| DC-bus HF film cap | `C7` | 630V | 340V | 46% | EPCOS/TDK B32671L6474K000 |
| Y1 safety cap | `C6` | 500VAC | 250VAC required | 100% | Vishay VY1 series doc 28537, `modules.ato:915-969` |
| OVP/ADC HV divider resistors | `R51-53, R56-58` (430k/169k ×3 each) | 200V (Yageo RC1206, datasheet-confirmed) | 55.6–55.9V per resistor, single-fault 83–111V | >45% even single-fault | `modules.ato:2244-2438` — protective-impedance construction, IEC 60335-1 |
| Discharge string resistors | `R11-14` | 139V/5W | ≤85V, 1.85W (37%) | V: 39%, P: 63% | Vishay AC05, `modules.ato:1255-1289` |
| Bus discharge snubbers | `C25/C26`-adjacent (`c_snub1/2`) | 630V | 170V | 73% | same B32671 family |
| MCU 3.3V-domain passives (~40 designators) | various | 10–50V rated | 3.3V rail | 84%+ | KEMET/Murata families, all at low bias fraction |

---

## 4. Verification-integrity finding: a resistor-power assertion checks the wrong direction

`elec/src/modules.ato:851-853` (`PowerInput`, bus bleeders):

```
# Power handling check (temper-ip1.3)
assert r_bleed1.power_rating >= p_bleed_actual * 0.5  # 50% derating
assert r_bleed2.power_rating >= p_bleed_actual * 0.5
```

This is labeled "50% derating" but the inequality runs backwards for that
purpose. As written it requires `rated ≥ 0.5 × actual`, i.e. it only fails
if actual dissipation exceeds **2× the rated power** — it does not enforce
that actual stays under 50% of rated. At the committed values (2W rated,
1.31W actual) it reads `2 ≥ 0.657`, trivially true, and would *still* read
true if `p_bleed_actual` were as high as 3.9W — nearly double the resistor's
own rating.

Contrast with the structurally identical check 250 lines later in the same
file, for the same physical function (a resistor string dissipating I²R
continuously across a half-bus), `elec/src/modules.ato:1386-1390`
(`BusDischarge`):

```
# Power: 50% derating even in the abnormal continuous case
assert r_dis1a.power_rating >= p_dis_resistor * 2
assert r_dis1b.power_rating >= p_dis_resistor * 2
```

This one is written correctly: `rated ≥ 2 × actual`, i.e. `actual ≤ 0.5 ×
rated` — a real 50% derating enforcement. The `PowerInput` version's `* 0.5`
should almost certainly be `* 2` to match its own stated intent and its
sibling check's convention. **This audit does not fix it** (out of scope —
`elec/` is off-limits per this task's constraints) but flags it because a
"passing" assertion that cannot actually catch the condition it claims to
check is a verification-integrity gap of exactly the kind
`docs/STRATEGY.md`'s current critical path is about. The physical finding
this assertion was supposed to catch (§2.4, 34.5% margin, below the 50%
guideline) stands independently of this bug — it was found by direct
computation from `p_bleed_actual`, not by trusting the assertion.

---

## 5. Count

- **Total component instances on the board:** 169 (`elec/build/default.csv`, 89 BOM lines)
- **Individually stress-checked in this pass (voltage/current/power/temperature vs. a cited rating):** ~64 — every HV-domain part (bus, doubler, half-bridge, tank, discharge), every capacitor carrying DC bias or ripple current, every current-carrying magnetic/fuse/relay, and the resistor networks setting protection thresholds (OCP/OVP/THM dividers).
- **Reviewed but not independently re-derived:** ~105 — 3.3V/15V-domain digital logic support passives (SPI/I2C pull-ups, comparator/logic-IC decoupling, LEDs, test points, MCU strapping), which already carry wide margins established by existing per-module assertions in `modules.ato` and were not the source of any finding above.
- **At or over rating (§1):** 3 items (bus caps, AC input current at low line — conditional, tank coil current — already known).
- **Below normal derating guideline (§2):** 6 items/groups (3 unflagged DC-biased ceramics, CMC, fuse, bus bleeders, tank caps [thin but passing], coil NTC).
- **Verification-integrity findings (§4):** 1 (inverted assertion).

---

## 6. UNKNOWN — no rating found, not estimated

| Item | What's missing | Why it matters |
|---|---|---|
| IGBT junction temperature at the corrected 47kHz/28.7-31.9A operating point | `docs/hardware/SYSTEM_THERMAL_BUDGET.md` (dated 2025-12-14) is the only in-repo thermal derivation, and it predates the 2026-07-29 coil/frequency correction — it uses a 21A peak tank current and an **Rth(j-c)=0.50 K/W** assumption that does not match the real Infineon datasheet figure confirmed in this pass, **Rth(j-c)=0.31 K/W** (`datasheets/infineon-ikw40n120h3-datasheet-en.pdf`, Table 1). Recomputing with the corrected current and real Rth would likely improve the margin (lower Rth) but the current input is materially higher (28.7–31.9A peak vs. 21A) — direction of the net change is not obvious without redoing the calculation. Not attempted here: it needs a real switching-loss estimate at 47kHz from the datasheet's Eon/Eoff curves, which is a simulation-scale task, not a documentation-pass one. |
| Heatsink thermal resistance (Rth-sa) for the real installed part | `SYSTEM_THERMAL_BUDGET.md` cites "Wakefield-Vette 392-120AB" with assumed Rth-sa 0.35–0.45 K/W but no datasheet for that part exists under `datasheets/` | Needed to close the IGBT Tj loop above |
| `GRM55DR72E106KW01L` (`C14`) existence at any distributor | Not found at Mouser/DigiKey in this pass's search; only the 1µF sibling `GRM55DR72E105KW01L` confirmed | Given this project's history of fabricated MPNs (STRATEGY.md), an unconfirmed MPN on a part carrying the worst DC-bias ratio found in this audit (§2.1) should be resolved before trusting its physical rating at all |
| Coil AC resistance / self-heating (~193W estimated) vs. the actual Litz winding thermal design | `ResonantTank.inductor_conn` docstring (`modules.ato:577-583`) computes this from a chart reading, not a datasheet — the coil itself is a specification, not a purchased part (`docs/hardware/TANK_COIL_SPECIFICATION.md`) | Cannot be closed until a coil is sourced against that spec |
| `WSLP25122L000FEA` (OCP-02 shunt) pulse power rating at the 60A trip point (7.2W vs. 3W continuous rated, 2.4× — `modules.ato:2692-2696`) | Datasheet pulse-duty curve not pulled; the module itself says "the WSLP2512 family is designed for pulse duty" without citing the curve | **Currently moot** — `SecondaryOCPComparator` (OCP-02) is not instantiated in `Top` (`main.ato:761-778`) and this part does not appear in `elec/build/default.csv`. Flagged for whenever OCP-02's sensing-domain decision (STRATEGY's one remaining open design item) lands and this circuit is wired in. |
| CT burden resistor (`r_burden`, `RC1206FR-074R99L`) pulse power rating at the OCP-01 trip transient (1.25W vs. 0.25W continuous rated, 5×) | Module's own comment: "Confirm the part's pulse rating on the bench" (`modules.ato:1727-1730`) — never done | Trip is microseconds-long (latch kills PWM immediately) so likely fine, but unverified against a real pulse-power curve |
| MOV (`V150LA10AP`) surge energy (Joules) rating vs. any computed line-surge energy | No surge-energy computation exists anywhere in this repo for this part | Standard commodity MOV sizing; lower priority than the items above but genuinely unchecked |
| Bypass relay (`G4A-1A-E DC12`) `contact_current = 20A` | No datasheet citation found in `elec/src` for this specific field (contrast with the BusDischarge relays' extensively-cited RT314012 datasheet work) | Used at face value in §1.2's derived scenario; if the real Omron rating differs, that scenario's margin changes |

---

## 7. Re-runnable check

`scripts/part_stress_gate.py` + `scripts/part_stress_limits.yaml` encode the
findings in §1–§2 above as data (rated value, applied-stress value or
formula, source citation, guideline threshold) rather than as hardcoded
numbers in the script, so a part swap or a re-derivation only requires
editing the YAML. It:

1. Loads `elec/build/default.csv` and confirms each limits-file entry's
   designators still carry the expected MPN — a silent part swap (the same
   class of drift `check_footprint_drift.py` and `capacity_budget_gate.py`
   guard against elsewhere in this repo) fails closed rather than silently
   comparing a stale rating against a part that is no longer on the board.
2. Computes `margin = (rated − applied) / rated` for each entry and
   classifies it `FAIL` (margin < 0, at-or-over rating), `WARN` (margin
   below the entry's guideline threshold), or `OK`.
3. Exits 3 if any entry is `FAIL`, 0 otherwise (`WARN`s are reported but do
   not fail the gate — they are guideline advisories, not hard limits).
   Exits 5 on a missing/unparseable BOM or a designator/MPN mismatch
   (tool error, never silently reported as "0 violations" — same convention
   `capacity_budget_gate.py` uses).

**Running it today reports the §1 findings as `FAIL` and the §2 findings as
`WARN` — this is expected and correct, not a bug in the gate.** It is not
wired into any CI workflow (this task's constraints exclude
`.github/workflows/python-tests.yml`); it is a standalone, re-runnable
check for a human or a future pass to invoke.

```
uv run python scripts/part_stress_gate.py
```

Seeded-defect anti-vacuity tests live in
`scripts/tests/test_part_stress_gate.py` (R9/R10 per
`docs/plans/2026-08-04-002-docs-temper-goal-set-plan.md`): a synthetic
fixture BOM/limits pair is used (not the real board, so these tests do not
depend on the real findings ever changing), and includes at least one case
per failure mode the gate must catch — an over-rating margin, a
below-guideline margin, and a designator/MPN mismatch — each verified to
actually flip the gate's exit code, not merely to run without crashing.
