<!-- provenance: commit=eb5022510d8f1272adf0a27d76c849aa2bb6e210 dirty=false
     (origin/main; branch analysis/emi-esr-derivation, fresh worktree cut from it).
     pcb/temper.kicad_pcb sha256=26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b
     -- verified before and after; the board file was never opened for writing.
     NO clearance, creepage, copper-weight, loop-area, DRU or ratchet threshold
     was changed. MIN_BARRIER_WIDTH_MM is 12.6 and remains 12.6; PD3 remains the
     enforced classification. power_pcb_dataset/drc_ceiling.json untouched. No
     _*_py_oracle.py was touched, deleted or re-pinned. No test was skipped,
     xfailed or relaxed. git stash never invoked. No pushed history rewritten.
     Only two files are added: this document and its companion script. -->
---
module: thermal
tags: [thermal, enclosure, emi-filter, capacitor-esr, ripple, pollution-degree, analysis-only]
problem_type: engineering-analysis
---

# The two unverified inputs are not overstated — they are understated, the larger one by 8–25×, and the sealed compartment is **not** thermally viable. The ESP32-S3 fails by 17–30 °C under the most favourable bracket I can defend.

**Verdict: NOT VIABLE.** The 2026-08-19 viability analysis
(`analysis/sealed-compartment-thermal`) named the EMI-filter (2.0 W) and
capacitor-ESR (4.0 W) line items as "the largest remaining unverified inputs"
and left them at their 2025-12-14 budget values on the reasoning that this was
the conservative direction. **It was not the conservative direction.** Every
prior re-derivation of a 2025-12-14 figure found it overstated; these two are
the exception, and they run the other way:

| Line item | 2025-12-14 budget | Derived here | Direction |
|---|---|---|---|
| EMI filter | 2.0 W | **5.2–9.0 W** at the declared 15 A line current; **14.3–24.9 W** at the line current the topology actually draws | **2.6–12× higher** |
| Capacitor ESR | 4.0 W | **31.7 W** most-favourable bracket; **99 W** central; **228 W** least-favourable | **8–57× higher** |
| *(no line existed)* | — | bus bleeders **2.63 W** + relay coils/droppers **1.48 W** | **+4.1 W omitted entirely** |

**The ESP32-S3 does not survive.** Its breakeven is **Q = 16.4 W** (compact
envelope, ε = 0.5, 60 °C ambient, ×1.3 film factor) or **22.4 W** on the bare-wall
convention the predecessor used for this part. The lowest corrected heat load I
can construct — taking *every* term at its most favourable value simultaneously,
including two values that cannot both hold at once — is **41.8 W**. The part is
**−17.1 °C** (wall) to **−29.8 °C** (film-boosted) at that floor. **If the
ESP32-S3 fails, the compartment decision fails, and it fails.**

**This reverses ground (b) of the 2026-08-15 decision back to unproven-favourable.**
It does *not* change anything enforced today: PD3 and the 12.6 mm bar govern,
`MIN_BARRIER_WIDTH_MM` is untouched, and the compartment is still unbuilt.

**But read §6 before acting on the headline.** The dominant term is not a
compartment problem. It is the thermal consequence of an *already-committed*
design failure — `docs/evidence/2026-07-26-bus-capacitor-ripple.md` found the bus
capacitors running at **4.2–5.8× their rated ripple current** and returned a
verdict of **FAILS**. Dissipation goes as the square of that, and nobody ever
propagated it into the thermal budget. Fix that first; the compartment question
cannot be answered until it is, and §4 shows that even with it fixed the
compartment lands at **+1.4 °C** on the ESP32-S3.

Reproduce with:

```
python3 docs/evidence/2026-08-19-emi-filter-and-capacitor-esr-derivation.py
```

Stdlib only, no repo state read. Every input is a literal tagged `[datasheet]`,
`[repo]`, `[derived]`, `[estimated]` or `[UNOBTAINABLE]`. **Those five tags are
not blended into a single confident total anywhere in this document** — §2 and §3
report brackets, and the bracket endpoints are labelled.

---

## 1. The rated input power, and the line current the topology actually draws

**Rated power used: 1800 W output.** Source: `elec/src/main.ato:53`
(`power_max = 1800W`) and `:494` (`p_output_max = 1800W`). Nominal line
120 V / 60 Hz (`main.ato:51`, `f_line`). The design's own declared line-current
limit is **15 A rms** (`elec/src/constraints.ato:12`,
`ACMainsConstraints.i_max`), which the fuse assertion in `modules.ato` checks
against.

**15 A is not achievable by this front end.** `PowerInput` is a Delon cascade
doubler feeding 3600 µF per half-bus with no PFC. Its line current is a pair of
narrow recharge pulses, not a sinusoid. Using the repo's own conduction-angle
model (`docs/evidence/2026-07-26-bus-capacitor-ripple.md` §3, assumptions A1–A5)
and the charge-balance identity `I_line,rms = I_dc,half · √(2/δ)` `[derived]`:

| case | η | θ | P_in | δ | **I_line,rms** | PF | I_cap,LF per cap |
|---|---|---|---|---|---|---|---|
| best | 0.92 | 60° | 1957 W | 0.167 | **19.93 A** | 0.818 | 6.43 A |
| central | 0.90 | 40° | 2000 W | 0.111 | **24.96 A** | 0.668 | 8.32 A |
| worst | 0.85 | 30° | 2118 W | 0.083 | **30.51 A** | 0.578 | 10.33 A |

η is `[repo]` (`main.ato:88` `eta_min = 0.90`, `assert >= 0.85`; STRATEGY EFF-02's
0.92 target, unmeasured). **θ is `[estimated]`** — carried unchanged from the
2026-07-26 doc's A5, which flags it "typical range for cap-input rectifiers … not
bench-verified." It is the largest single estimated input in this document, and
it drives *both* the line current and the bus-cap low-frequency ripple, so the two
stay consistent with each other by construction.

**Every case exceeds the 15 A declared limit, the 16 A fuse, the choke's 16 A
rating and the K1 contact's 20 A UL limiting continuous current.** That
inconsistency is pre-existing — `modules.ato` already carries an OPEN QUESTION on
fuse/NTC/relay coordination, and the 2026-07-26 ripple doc's FAILS verdict is the
same inconsistency seen from the capacitor side. **This document does not resolve
it and does not need to**: §4 shows the compartment fails even at the 15 A floor.

---

## 2. EMI filter — claimed 2.0 W. Derived: **5.2–9.0 W at 15 A, 14.3–24.9 W at the topology-consistent current.**

### 2.1 What the 2.0 W was scoped to cover

`docs/hardware/SYSTEM_THERMAL_BUDGET.md` §1 carries "EMI filter | 2.0 W"; its own
§3.5 scopes that as "**EMI filter inductors** | 1-2W | I²R + core loss". The two
scopings disagree, and the summary table's 2.0 W is the top of §3.5's own range.
**Both are evaluated below. The choke alone busts the line at 15 A.**

### 2.2 The actual components (`elec/src/modules.ato`, `PowerInput`)

| Ref | Part | Role | Term |
|---|---|---|---|
| F1 | Schurter 0034.3129, FST 5×20 16 A/250 VAC T | series | I²R |
| RV1 | Littelfuse V150LA10AP MOV | L-N shunt | leakage |
| C_X2 | EPCOS B32922C3224M289, 0.22 µF X2 305 VAC | L-N shunt | tanδ |
| L1 | TDK/EPCOS **B82726S2163N030** CM choke | series, both windings | I²R + core |
| NTC | 10 Ω/15 A inrush limiter | series, **relay-bypassed** | ~0 |
| K1 | TE Schrack RT33K012 | bypasses NTC | contact I²R |
| C_Y | EPCOS B81123C1562M000, 5.6 nF Y1 | bus-ref → PE | tanδ |

### 2.3 Term by term

| Term | Value | Provenance |
|---|---|---|
| **F1 resistance** | 3.75 mΩ … 5.73 mΩ | **`[datasheet]`** — schurter.com `typ_fst_5x20.pdf`, rev 21.07.2026, fetched and text-extracted this session. 16 A row: *Voltage Drop 1.0·In typ = 60 mV* → 3.750 mΩ; *Power Dissipation 1.5·In typ = 3300 mW* → 5.729 mΩ. The "1.0·In max" cell is blank (`-`) for this rating, so no maximum exists to cite. The two printed points bracket the hot resistance; neither is extrapolated. |
| **L1 DCR** | 7.1 mΩ/winding, **14.2 mΩ total** | **`[datasheet]`** via `elec/src/components.ato:252-281`, which quotes the TDK April-2025 datasheet verbatim with a 2026-07-16 verification date: "250 VAC / 16 A rated (referred to 50 Hz, T_R +60 °C), 2.2 mH ±30 %/winding, R_typ 7.1 mΩ/winding, ferrite ring core". Both windings carry the line current (W1 = L, W2 = N), so the line sees 2×DCR. Direct fetch of TDK's own PDF and product page both returned **HTTP 403** this session; the repo citation stands on its own verification trail. |
| **L1 core loss** | **`[UNOBTAINABLE]`** | TDK publishes no core-loss curve for the B82726 family and the product page is 403 to automated fetch. Bounded, not measured: in a current-compensated choke the two windings' line currents are equal and opposite, so their flux cancels in the ring core; only common-mode current magnetises it, and the only committed CM path is the 5.6 nF Y-cap passing 0.25 mA at 60 Hz. Core loss is therefore far below the winding I²R. Broadband CM noise current is **not derivable from committed data and is left unquantified.** |
| **K1 contact resistance** | **`[UNOBTAINABLE]`**; 5–20 mΩ `[estimated]` | The TE `ENG_DS_RT1` datasheet (farnell.com/datasheets/3775998.pdf, read this session) publishes coil resistance, rated current, limiting continuous current and breaking capacity — **its Contact Data block contains no contact-resistance line at all**, initial or end-of-life. 5–20 mΩ is typical-for-class for a 16 A/UL-20 A AgNi 90/10 power contact. **This is the second-largest estimated input and it spans a 3.4 W range at 15 A.** |
| **NTC** | ~0 W | `[repo, topology]` — `bypass_relay.COM`/`NO` shunts it in steady state; with a hot NTC of order 0.3–1 Ω against a 5–20 mΩ contact, >97 % takes the contact. The residual is inside the contact bracket. |
| **C_X2 / C_Y** | 1.2 µW / 0.03 µW | `[estimated]` tanδ ≤ 1×10⁻³ for metallised PP at 60 Hz (EPCOS's own B3292x spec sheet was not retrieved). Microwatts under *any* value in that class, so the estimate cannot matter. Stated rather than skipped so the total is auditable. |
| **MOV standby leakage** | ≤ 24 mW | **`[UNOBTAINABLE]`** — the Littelfuse LA-series datasheet was not retrieved this session, so no leakage figure is cited. Carried as a bounded upper limit (≤200 µA at 120 V), not a value. |

### 2.4 Totals

| I_line | F1 | L1 I²R | K1 contact | C/MOV | **Total** | *choke alone (§3.5 scope)* |
|---|---|---|---|---|---|---|
| **15.00 A** (declared floor, PF = 1, **not achievable**) | 0.84–1.29 W | **3.20 W** | 1.13–4.50 W | ≤0.03 W | **5.17–9.01 W** | *3.20 W* |
| **24.96 A** (central, topology-consistent) | 2.34–3.57 W | **8.84 W** | 3.11–12.46 W | ≤0.03 W | **14.30–24.90 W** | *8.84 W* |

**Even under the §3.5 "inductors only" scoping, at a line current the design
cannot actually draw, the datasheet DCR alone gives 3.20 W against a 2.0 W
budget.** There is no bracket in which 2.0 W is correct.

### 2.5 Continuously-energised board loads with no budget line at all

Both are on the PCB, inside the compartment, and conduct whenever the appliance
is powered:

| Item | Power | Provenance |
|---|---|---|
| Bus bleeders `r_bleed1`/`r_bleed2` | **2.627 W** | **`[repo, exact]`** — `modules.ato` computes it itself: `p_bleed_actual = v_bus_half²/r_bleed1.value` = 170²/22 kΩ = 1.313 W, ×2. |
| Relay coils K1 + K2 + K3 | **1.164 W** | **`[datasheet]`** TE `ENG_DS_RT1` coil table, code 012: 360 Ω ±10 %, 400 mW rated. K2/K3 are energised *to hold discharge disengaged* (`modules.ato`: "coils energized = NC contacts open = discharge disengaged"), i.e. on the whole time it runs. |
| Coil dropper resistors | **0.313 W** | `[repo]` 91 Ω (K1) + 2×100 Ω (K2/K3). |
| **Subtotal** | **4.104 W** | |

That is, on its own, **43 % of the entire 9.65 W heat load the viability analysis
carried.**

---

## 3. Capacitor ESR — claimed 4.0 W. Derived: **31.7 W floor, 99 W central, 228 W ceiling.**

### 3.1 Resonant tank, 3 × CDE 942C16P1K-F — the one fully datasheet-derived term

The brief is right that a 100/120 Hz ESR would be badly wrong here. It would also
be wrong to copy the datasheet's own 100 kHz figure across.

| Quantity | Value | Provenance |
|---|---|---|
| ESR @ 100 kHz | 4.0 mΩ | **`[datasheet]`** CDE catalog `942C.pdf` p.2 "Ratings and Dimensions", 1600 Vdc block, 0.10 µF row — quoted verbatim in `elec/src/modules.ato:474-478`. The ESR column shares the IRMS column's 100 kHz condition. |
| ESR @ 47 kHz | **5.60 mΩ** | **`[derived from datasheet curves]`** — ×1.40, from CDE's own DF-vs-frequency curve for PP (`filmAPPguide.pdf` p.3): DF(47 k) = 2.95×10⁻⁴, DF(100 k) = 4.48×10⁻⁴; `ESR = DF/(2πfC)` → ratio (2.95/4.48)×(100/47) = 1.40. Extraction and axis calibration are in `docs/evidence/2026-07-29-tank-cap-cde-942c-verification.md` §2.3. |
| I_tank | 22.5 A rms | **`[repo]`** `modules.ato` `ResonantTank`: "22.5 A rms at the 1800 W" point for the declared 88 µH coil at `f_switching = 47 kHz` (`main.ato:134`). |

| I_tank (rms) | source | per cap | P per cap | **P bank** |
|---|---|---|---|---|
| **22.50 A** | committed, 88 µH @ 47 kHz | 7.50 A | 0.315 W | **0.945 W** |
| 20.75 A | harness, superseded 150 µH model | 6.92 A | 0.268 W | 0.804 W |
| 35.40 A | OCP-01-derived, **disputed** (`2026-07-27-inductance-range-sweep.md` §4 calls it an overestimate that reconciles at no consistent operating point) | 11.80 A | 0.780 W | 2.339 W |

**The tank bank is ~0.95 W and is not the problem.** It is well characterised, its
part was re-sourced specifically for this duty, and it clears its own current
rating by 1.38×.

### 3.2 DC bus, 4 × United Chemi-Con EKMQ251VSN182MA50S — where the 4.0 W goes

**ESR at 120 Hz** — `[derived]` from the printed tanδ maximum,
`ESR = tanδ/(2πfC)`. Three values, because two catalogue revisions disagree:

| tanδ (max, 20 °C/120 Hz) | ESR(120 Hz) | Provenance |
|---|---|---|
| 0.15 | 110.5 mΩ | `[repo cite]` — `2026-07-26-bus-capacitor-ripple.md` §1, cited to CAT. No. **E1001E**, 160–250 Vdc group. |
| **0.20** | **147.4 mΩ** | **`[datasheet, read this session]`** — chemi-con.com KMQ-Series.pdf, CAT. No. **E1001U**: the DF row reads *"160 to 250V → 0.20"* at 20 °C/120 Hz. |
| 0.22 | 162.1 mΩ | `[datasheet + derived]` — same table's footnote: *"When nominal capacitance exceeds 1,000 µF, add 0.02 to the value above for each 1,000 µF increase."* 1800 µF is one partial increment; 0.22 reads it as a full one. |

**The repo's 0.15 and the revision I read directly disagree, and I did not
reconcile them — I carry both.** All three are **maxima**; neither revision prints
a typical tanδ or any ESR at all. A typical-to-max ratio near 0.5 is common for
this class but is `[estimated]` and appears only as an explicit sensitivity row.

**ESR at 60 Hz — `[UNOBTAINABLE]`.** Neither revision has a 60 Hz point. Bracketed
by the two limiting assumptions: ×1.0 (ESR flat, favourable) to ×2.0 (tanδ flat,
so ESR ∝ 1/f — the usual behaviour in the 50–120 Hz band where the oxide term
dominates).

**ESR at 47 kHz — `[UNOBTAINABLE]`.** Not published in either revision; the
2026-07-26 doc's own §9 already lists "ESR at 35 kHz" as unverified. Inferred
`[derived]` from the published **Rated Ripple Current Multipliers**, which are
constructed for constant allowed dissipation, so `ESR(f) = ESR(120)/FM²`. **The
two revisions give different multipliers and 1800 µF falls in a gap between rows
of the newer one:**

- FM = **1.50** — `[repo, E1001E]` 160–250 Vdc column at 50 kHz; also `[datasheet, E1001U]` the "100 to 1,000 µF" row at 100 kHz. *(favourable)*
- FM = **1.08** — `[datasheet, E1001U]` the "2,200 to" µF row at 100 kHz, which is the row for cans of this physical class. *(unfavourable)*

**Ripple currents.** LF per cap from §1 (`[estimated]`, via θ). HF per cap =
0.3536 × I_tank — `[repo, estimated]` assumption A6 of the 2026-07-26 doc (tank
current gated on one half-cycle per period, split equally across the parallel
pair; equal sharing is best case, and that doc's §6 notes any ESR mismatch makes
it worse).

| Bracket | P_LF | P_HF | per cap | **×4 caps** |
|---|---|---|---|---|
| **MOST FAVOURABLE** (tanδ 0.15, ESR flat to 60 Hz, FM 1.50, θ = 60°, I_tank 22.5 A) | 4.57 W | 3.11 W | 7.68 W | **30.7 W** |
| ↳ + typical-not-max ESR `[estimated]` | 2.29 W | 1.55 W | 3.84 W | **15.4 W** |
| **CENTRAL** (tanδ 0.20 max, tanδ-flat to 60 Hz, FM 1.50, θ = 40°) | 20.40 W | 4.14 W | 24.54 W | **98.2 W** |
| ↳ + typical-not-max ESR `[estimated]` | 10.20 W | 2.07 W | 12.27 W | **49.1 W** |
| **LEAST FAVOURABLE** (tanδ 0.22, tanδ-flat, FM 1.08, θ = 30°, I_tank 35.4 A) | 34.59 W | 21.77 W | 56.36 W | **225.4 W** |

**Every bracket, including the one built by taking the favourable end of every
single unresolved question at once and then halving the ESR on top of it, exceeds
the 4.0 W budget by at least 3.9×.**

### 3.3 What the 4.0 W actually was

Four caps at their **rated** 2.70 Arms/120 Hz ripple dissipate 4.30 W (at the
E1001U max tanδ); add the 0.95 W tank bank and you get **5.24 W**. **The 4.0 W
line is nameplate arithmetic** — it is what the capacitors would dissipate if they
were operated inside their rating. They are not:
`docs/evidence/2026-07-26-bus-capacitor-ripple.md` §5 puts the as-designed
per-capacitor ripple at **4.2–5.8× rated** and returns **FAILS**. Dissipation goes
as the square. **The thermal budget was never updated to reflect a failure the
repo had already found and committed.**

### 3.4 Everything else

Contact snubbers (`c_snub1`/`c_snub2`, 470 nF PP + 100 Ω across the K2/K3
contacts): the contacts are static in normal running, so the snubber sees DC and
passes leakage only — nanowatts `[repo, topology]`. X2/Y safety caps: accounted in
§2 (microwatts). Buck output/decoupling caps: already inside the LMR51430 stage's
efficiency term in the predecessor script, not double-counted.

---

## 4. The re-run verdict at the committed 60 °C ambient

Same enclosure closure as the 2026-07-30 bound and the 2026-08-19 analysis
(`Q = h·A·ΔT + εσA(Ts⁴−Ta⁴)`, `h = 1.42·(ΔT/Lc)^0.25`, compact 152×234×33 mm
envelope, ×1.3 internal-film factor) — **carried unchanged, and unchanged
deliberately: only Q moves.** Ambient 60 °C (`thermal_constants.rs:50`), not the
superseded 70 °C. θJA are the **datasheet** values the predecessor used and are
**not silently improved on**: UCC21550 DWK **74.1 °C/W**, LMR51430 DDC
**107.8 °C/W**.

*Sanity check on the closure: at Q = 9.65 W, ε = 0.5 this script reproduces the
predecessor's 12.1 °C wall rise, its 75.8 °C central local ambient and its
+12.9 °C ESP32-S3 margin exactly.*

### 4.1 Corrected heat load

Fixed corrected items: gate driver 0.121 W + buck 0.20 W + ESP32 0.50 W +
bleeders 2.63 W + relay string 1.48 W = **4.93 W**.

| Scenario | EMI | caps | **Q** |
|---|---|---|---|
| 2025-12-14 budget (for scale) | 2.00 W | 4.0 W | **9.7 W** |
| *HYPOTHETICAL: bus-cap ripple fault fixed* | 5.16 W | 5.2 W | **15.3 W** |
| floor: each term at its most favourable value | 5.16 W | 31.7 W | **41.8 W** |
| floor + typical-not-max ESR `[estimated]` | 5.16 W | 50.0 W | **60.1 W** |
| central (topology-consistent) | 24.89 W | 99.1 W | **128.9 W** |
| least favourable | 37.20 W | 227.8 W | **269.9 W** |

The *floor* row takes 15 A line current **and** the θ = 60° capacitor ripple —
which cannot both hold at once. It is a lower bound, not an operating point, and
it is stated that way so it cannot be quoted as one.

### 4.2 Per-part outcome (ε = 0.5)

ESP32-S3 is shown **both** ways — at the bare wall rise (the predecessor's own
convention for this part) and at the ×1.3 film-boosted local air — so this
document is not silently harsher than the one it corrects.

| Q | T_wall | T_local | **ESP32 @wall** | **ESP32 @local** | UCC21550 | LMR51430 | e-cap 105 °C |
|---|---|---|---|---|---|---|---|
| 9.7 W | 72.1 °C | 75.8 °C | **+12.9 °C** | +9.2 °C | +65.3 °C | +52.7 °C | +32.9 °C |
| 15.3 W | 78.1 °C | 83.6 °C | **+6.9 °C** | **+1.4 °C** | +57.5 °C | +44.9 °C | +26.9 °C |
| **41.8 W** | 102.1 °C | 114.8 °C | **−17.1 °C** | **−29.8 °C** | +26.2 °C | +13.7 °C | +2.9 °C |
| 60.1 W | 116.6 °C | 133.6 °C | −31.6 °C | −48.6 °C | +7.4 °C | −5.2 °C | −11.6 °C |
| 128.9 W | 162.3 °C | 193.0 °C | −77.3 °C | −108.0 °C | −52.0 °C | −64.6 °C | −57.3 °C |
| 269.9 W | 233.1 °C | 285.0 °C | −148.1 °C | −200.0 °C | −143.9 °C | −156.5 °C | −128.1 °C |

The e-cap column ignores the capacitors' **own** self-heating above local air,
which at the §3.2 dissipations is tens of K more — so that column is optimistic by
a wide margin wherever the caps are the source of the heat.

### 4.3 The thinnest margin, stated plainly

**The ESP32-S3 fails.** It is an 85 °C **module ambient** rating: there is no θJA
to spend and no re-specification available; it responds only to compartment ΔT.

| | Breakeven Q |
|---|---|
| bare wall rise (predecessor's convention) | **22.35 W** |
| ×1.3 film-boosted local air | **16.43 W** |

| Scenario | Q | @wall | @local |
|---|---|---|---|
| HYPOTHETICAL: ripple fault fixed | 15.3 W | PASS | PASS (+1.4 °C) |
| floor: each term most favourable | 41.8 W | **FAIL** | **FAIL** |
| floor + typical-not-max ESR | 60.1 W | **FAIL** | **FAIL** |
| central (topology-consistent) | 128.9 W | **FAIL** | **FAIL** |
| least favourable | 269.9 W | **FAIL** | **FAIL** |

**No as-designed scenario passes, on either convention, at any emissivity in the
sweep.** The predecessor's +4.8 °C was correct arithmetic on a Q that was 4–28×
too small.

Unlike the 2026-08-19 result, **this verdict does not need the enclosure model to
be right.** The floor case exceeds the breakeven by 2.5×; the model's entire
ε = 0.2→0.9 spread is ~10 °C of local ambient, against a 30 °C deficit.

---

## 5. The `thermal_constants.rs` U6/Q1/Q2 mapping — **reporting only, no gate**

Asked as a side item. Determined by call-graph, not by running anything:

`packages/temper-thermal/src/thermal_constants.rs:179-181` maps
`"Q1" | "Q2" | "U4" | "U5" | "U6"` to the IKW40N120H3 TO-247 stackup, resolving to
(0.31, 0.20, 0.45) = **0.96 K/W** — a fan-cooled heatsink figure — for a SOIC-14
gate driver whose real θJA is 74.1 °C/W. `U3` falls to the flat placeholder
(0.6, 0.25, 1.0) = 1.85 K/W against a real 107.8 °C/W, the same class of error.

`thermal_resistance_for` has **exactly three consumers**, and none is a gate:

1. `packages/temper-placer/src/temper_placer/physics/thermal.py:75` — a thin
   pyo3 wrapper. **Grep across `packages/*/src` and `crates` finds no production
   caller of it.**
2. `packages/temper-placer/tests/metrics/_physics_py_oracle.py:225`
   (`_oracle_measure_thermal`). **That function is never called** — the only hits
   for its name are inside its own file's docstrings. It mirrors a production
   `measure_thermal` that **no longer exists**: `grep -rn "def measure_thermal"`
   over the whole repo returns nothing. The Rust `measure_thermal_edges` takes
   (Rjc, Rch, Rha) as *caller-supplied arrays* and has no Python caller either.
3. `docs/evidence/2026-08-15-thermal-analysis-run.py:74,114` — a reporting script.

The one thing that *looks* like a gate, `refdes_lookup_matches_python_table`
(`thermal_constants.rs:295-314`), asserts the Rust table is byte-identical to its
pre-move Python twin. **It is a self-consistency pin, so it enforces the wrong
values rather than checking them** — both sides carry the same error and the test
is blind to it by construction.

**Conclusion: the error affects reporting and one dormant test oracle. No DRC,
placement score, ratchet, or CI gate consumes it.** **Not fixed here**, per
instruction — the root cause is `(property "Value" "?")` on U3 and U6 in
`pcb/temper.kicad_pcb`, which is forbidden to touch, and the table itself is
pinned as another agent's surface. **No figure in this document comes from that
table.**

---

## 6. What this changes, and what it does not

**It does not reclassify anything.** PD3 and 12.6 mm remain enforced;
`MIN_BARRIER_WIDTH_MM` is 12.6 and untouched. Ground (a) of the 2026-08-15
decision — the compartment is unbuilt — is unaffected and remains sufficient on
its own.

**It reverses ground (b) in the opposite direction from the 2026-08-19
document.** That analysis moved "thermally counterproductive" from *unestablished*
to *positively refuted*. On these figures it moves back past *unestablished* to
**positively established, for the design as committed.**

**But the honest framing is narrower than the headline.** The dominant term —
75–85 % of every corrected Q — is bus-capacitor I²R at 4.2–5.8× rated ripple.
That is a **pre-existing, already-committed design failure**
(`docs/evidence/2026-07-26-bus-capacitor-ripple.md`, verdict FAILS) whose thermal
consequence was never carried into the budget. It is not a compartment problem and
sealing is not what breaks it — those capacitors are over their rating in free
air too.

So the actionable statement is:

1. **The compartment cannot be decided today**, because its heat load is dominated
   by a design fault that must be fixed first (more/larger capacitors, a
   lower-ESR family, or PFC ahead of the doubler to remove the high-crest-factor
   charging).
2. **Even with that fault fixed**, the compartment lands at **+1.4 °C** on the
   ESP32-S3 at ε = 0.5 (Q = 15.3 W against a 16.43 W breakeven). That is not a
   margin anyone should build a gasket around, and the ×1.3 film factor and the
   envelope are still `[assumed]`.
3. **The EMI/input-stage term does not shrink when the capacitors are fixed.**
   It is I²R in the choke, fuse and relay contact at whatever line current the
   topology draws, and 3.20 W of it is datasheet DCR at a current the design
   cannot even achieve.

---

## 7. What this document does not settle

1. **The conduction angle θ is `[estimated]`** and sets both the line current and
   the LF cap ripple. It is the largest lever here. A bench capture of the input
   current waveform would collapse most of §1–§3's spread and is the single
   highest-value measurement available.
2. **K1's contact resistance is `[UNOBTAINABLE]`** from TE's datasheet and spans
   3.4 W at 15 A. A four-wire measurement on a sample would close it.
3. **Bus-cap ESR at 60 Hz and at 47 kHz is `[UNOBTAINABLE]`.** Both are inferred
   from tanδ maxima and from ripple multipliers whose two catalogue revisions
   disagree, with 1800 µF falling in a gap between rows of the newer one. An
   impedance-analyser sweep on one capacitor would replace the whole bracket.
4. **The E1001E (0.15) vs E1001U (0.20) tanδ discrepancy is unreconciled.** Both
   are carried; the newer one is the one I read directly.
5. **CMC core loss and MOV leakage are `[UNOBTAINABLE]`** and carried as bounds.
6. **The 15 A vs ~25 A line-current inconsistency is pre-existing and unresolved.**
   The fuse, the choke and the K1 contact are all rated below the topology-consistent
   current.
7. **The compartment boundary is inherited, not re-derived.** D1/D2 (MUR1560,
   TO-220 on the shared HS1 heatsink) are excluded, as in the predecessor. If they
   sit inside the sealed volume, Q rises further.
8. **No physical measurement exists.** As with both predecessors, this is hand
   calculation — committed and re-runnable, with every input tagged, but not
   measured.
9. **`make venv-isolate` was not run.** This artifact is stdlib-only and reads no
   repo state, exactly like its predecessor script; no repo tooling, extension
   build or test was invoked, so the stale-`.so` hazard that instruction guards
   against does not arise. Running a full `uv sync --all-packages` + Rust
   extension build purely ceremonially would have competed for memory against the
   other agents, which was explicitly cautioned against.

---

## 8. Recommended follow-ups (none performed here)

- **Resolve the bus-capacitor ripple failure before revisiting the compartment.**
  It is a 2026-07-26 finding with a FAILS verdict and it now has a quantified
  thermal consequence as well as a life consequence.
- Correct `docs/hardware/SYSTEM_THERMAL_BUDGET.md` §1/§3.5: EMI filter 2.0 W →
  the §2.4 bracket; capacitors 4.0 W → the §3.2 bracket; **add** bleeders (2.63 W)
  and relay coils/droppers (1.48 W), which have no line at all.
- Capture the input current waveform (§7.1) — it is the cheapest measurement that
  moves the most.
- Give U3 and U6 real `Value` properties (still the root cause of §5; needs the
  board-file owner).
