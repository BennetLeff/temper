<!-- provenance: commit=03a7415c8f08e6e8128a9ff90d8bc724ed8ddb58 dirty=false (branch analysis/mains-selv-barrier-derivation, = origin/main at measurement time). pcb/temper.kicad_pcb sha256=6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64 -- byte-identical to the hash recorded in docs/evidence/2026-08-12-hv-clearance-adequacy.md, i.e. the board has not changed since 2026-08-08. pcb/** was READ-ONLY for the whole of this work: every DRU variant measured below was written into a scratch board copy outside the repo by scripts/measure_uncapped_drc.py's own make_scratch_board(), never written back. NO VALUE IS CHANGED BY THIS DOCUMENT -- it is a determination only; scripts/generate_kicad_dru.py, packages/temper-placer/configs/netclass_rules.yaml and pcb/** are untouched. kicad-cli 10.0.5, MaximumThreads pinned per measure_uncapped_drc.py's _single_thread_env(). Every IEC 60335-1 / 60335-2-6 clause and table cell quoted below is reproduced from text ALREADY RECOVERED AND TRANSCRIBED in this repository -- docs/evidence/2026-07-28-creepage-determination-brainstorm.md (Tables 15/16/17, clauses 3.4.4, 27.1, 29.1, 29.1.3, 29.1.5, 29.2, 29.2.3, and IEC 60335-2-6 cl. 29.2's Addition) and docs/evidence/2026-08-12-hv-hv-creepage-determination.md (Table 18, clauses 3.1.3 Notes, 29.1.4, 29.2, 29.2.4) -- each cited by path:line. NOTHING is stated from memory. Where the governing text is NOT in this repository, that is said explicitly and the figure is presented as a fork, not a conclusion (sec 6.3, sec 9). -->

# The mains↔SELV barrier is REINFORCED at 120 V nominal: clearance **2.0 mm**, creepage **8.0 mm**. The enforced 6.0 mm clearance is **3× over-specified**, 22 of its 23 violations are artifacts, and the barrier's real, binding, unmet constraint is the creepage figure — 8 violations, 7 of them live and every one of those on `ac_n`.

**Verdict, up front. No value is changed.**

1. **Tier: REINFORCED.** IEC 60335-1 cl. 27.1 + cl. 3.4.4. The low-voltage
   domain is hard-bonded to protective earth (`elec/src/main.ato:753`,
   `gnd ~ pe`), which makes it a **PELV** circuit, not SELV, by the standard's
   own definition. Clause 3.4.4 then permits exactly three constructions for
   separating a PELV circuit from the mains, and the only one available on a
   flat PCB with no earthed inner-layer screen is **reinforced insulation**.
   The DRU's `"IEC 60335-1 basic insulation for 240V AC"`
   (`scripts/generate_kicad_dru.py:825`) is wrong on the tier. Sec 2.

2. **Working voltage: 120 V rms nominal; rated impulse voltage 1 500 V at
   OVC II.** The board is **120 V, US-single-market**, not 240 V and not
   dual-voltage — established from the committed electrical source and from
   parts, not from prose (sec 3). The 240 V/230 V references scattered through
   `docs/hardware/` are aspirational product-family text with **no committed
   part behind them**, and one BOM line refutes them outright: `RV1` is a
   **`V150LA10AP`, a 150 V rms MCOV varistor across L–N**
   (`docs/hardware/BOM.md:46`). A 150 V MCOV MOV on a 230 V supply conducts
   continuously and self-destructs. The DRU comment's "240V AC" is wrong on the
   voltage too. Sec 3.

3. **Pollution degree: PD3.** Carried, not re-litigated:
   `docs/evidence/2026-08-12-pollution-degree-resolution.md:6-16` — IEC
   60335-2-6 cl. 29.2's Addition makes PD3 the default for a cooking appliance
   and the PD2 compartment is neither built nor thermally free. Sec 4.

4. **The resulting figures.**

   | | requirement | table / row / conditions |
   |---|---:|---|
   | **Clearance (reinforced)** | **2.0 mm** | Table 15 row ii (>50 ≤150 V) → OVC II → 1 500 V; cl. 29.1.3 "next higher step" → Table 16 @ 2 500 V = 1.5 mm; + cl. 29.1's +0.5 mm soldered-construction adder |
   | **Creepage (reinforced)** | **8.0 mm** | Table 17 row iii (>125 ≤250 V), **PD3**, material group IIIa/IIIb = 4.0 mm basic; cl. 29.2.3 ×2 |

   The creepage row selection has an honest fork at the 125 V boundary and it
   is the single soft joint in this determination — sec 6.3. **I would go with
   8.0 mm**, for reasons given there; the alternative (4.8 mm) costs 2 fewer
   violations and is the only thing at stake.

5. **The board does not meet the creepage figure and comfortably meets the
   clearance figure.** Measured live, uncapped, deterministic (sec 7):

   | `AC Mains to LV` band | enforced today | **correct** | violations today | **violations at correct figure** | Δ |
   |---|---:|---:|---:|---:|---:|
   | clearance | 6.0 mm | **2.0 mm** | 23 | **1** | **−22 (spurious)** |
   | creepage | 8.0 mm | **8.0 mm** | 8 | **8** | **0** |

   **22 of the 23 currently-reported `AC Mains to LV` clearance violations are
   artifacts of an over-specified figure, not safety defects.** Whole-board
   `clearance` would go 1 664 → 1 642. The one surviving clearance violation is
   **R6 at 1.8 mm**, and R6 is the dead ZCD circuit already established as
   stale-board noise, not a live defect. The **creepage violations are the
   actual finding**: 8 in total, and the 7 that are not R6 are all `ac_n` on
   `C1`, `RV1` or `L1` against SELV routing, at 2.6–5.9 mm against 8.0 mm.

6. **`HV_INTERNAL_CLEARANCE_MM` is the mains-barrier figure, correctly derived,
   attached to the wrong rule — and it is simultaneously the right figure for
   the rule it is attached to. Two different derivations collided on one
   constant.** Its own comment
   (`scripts/generate_kicad_dru.py:59-67`) opens *"Fail-closed reinforced
   clearance for the mains<->PELV barrier, uncoated"* and then derives exactly
   the sec-5 chain above — 120 V, OVC II, Table 15, Table 16, cl. 29.1.3, +0.5 —
   while the constant is consumed only at line 1188, by
   `"HV internal same footprint"`, a same-HV-domain rule. The mains barrier
   rule it describes (`"AC Mains to LV"`, line 884) instead carries a bare,
   uncited `6.0mm` literal. Nothing is mis-enforced *today* only because a
   completely independent derivation for the HV↔HV pair (923.7 V peak, cl.
   29.1.5 → 2 254 V → Table 16 @ 2 500 = 1.5 + 0.5) lands on the same 2.0 mm.
   Sec 8 gives the conditions under which the two diverge.

---

## 1. What is enforced today, and what it cites

`scripts/generate_kicad_dru.py`, RULE 2:

```
scripts/generate_kicad_dru.py:823   "# RULE 2: AC Mains isolation - 6mm to everything except itself"
scripts/generate_kicad_dru.py:825   "# IEC 60335-1 basic insulation for 240V AC"
...
scripts/generate_kicad_dru.py:876   '(rule "AC Mains to LV"'
scripts/generate_kicad_dru.py:878-882   condition: A.NetClass=='ACMains' && B.NetClass not in
                                        {ACMains, HighVoltage, HighVoltageTank, GateDriveHV}
scripts/generate_kicad_dru.py:884   "   (constraint clearance (min 6.0mm))"
scripts/generate_kicad_dru.py:885   "   (constraint creepage (min {HV_CREEPAGE_ENFORCED_MM}))"   # = 8.0mm
```

`HV_CREEPAGE_ENFORCED_MM = HV_CREEPAGE_PD2_MM = 8.0`
(`scripts/generate_kicad_dru.py:81,110`).

**Membership.** On the committed board the `ACMains` net class resolves to
exactly two real nets, `ac_l` (net 29) and `ac_n` (net 30). `pcb/temper.kicad_pro`'s
`netclass_assignments` also lists `AC_L`, `AC_N` and `PE`, but no net by any of
those three spellings exists in `pcb/temper.kicad_pcb` — `pe` is merged into
`gnd` by `elec/src/main.ato:753`. (Latent, flagged not fixed: if a future
netlist resync ever emits a *separate* `pe` net, it would be classed `ACMains`
and every `gnd`↔`pe` pair — working voltage **zero volts** — would be charged
the full mains barrier. Same shape as the `GateDriveHV` false positive RULE 2's
own comment block at lines 839-874 already records.)

**Three independent defects in the citation at line 825**, and the third is the
one nobody has named:

1. **Wrong tier** — "basic", where cl. 3.4.4 requires reinforced (sec 2).
2. **Wrong voltage** — "240V AC", where the board is 120 V nominal (sec 3).
3. **6.0 mm does not follow from its own citation even if you grant both
   errors.** Take the comment entirely at face value — *basic* insulation at
   *240 V*: Table 15 row iii (>150 and ≤300 V), OVC II → 2 500 V rated impulse
   → Table 16 @ 2 500 V = **1.5 mm** basic, 2.0 mm with cl. 29.1's soldered
   adder. Not 6.0. **Table 16's entire value set is {0.5, 1.5, 3.0, 5.5, 8.0,
   11.0}** (`docs/evidence/2026-07-28-creepage-determination-brainstorm.md:243-257`)
   — 6.0 is not in it at any row, under any insulation tier, at any voltage.
   The number was never derived from the standard it names. It is the same
   orphan figure that `netclass_rules.yaml:13,17,21` still carries under the
   separately-debunked `"IEC 60335-1 Table 16 working isolation at 400V"`
   string (a row that does not exist —
   `docs/evidence/2026-07-28-creepage-determination-brainstorm.md:84`), and
   which `netclass_rules.yaml:204-212` repeats across nine `class_pairs` rows.

---

## 2. The tier is REINFORCED — clause 3.4.4, not accessibility, not floating-ness

### 2.1 The LV domain is PELV, not SELV

IEC 60335-1 clause 27.1, CITED-PRIMARY
(`docs/evidence/2026-07-28-creepage-determination-brainstorm.md:162-166`):

> "Safety extra-low voltage circuits shall not be earthed unless they are
> protective extra-low voltage circuits."

`elec/src/main.ato:753` is `gnd ~ pe` — a hard 0 Ω DC bond, commented in-source
as *"SELV ground reference: bonded to protective earth, NOT to power_return"*.
The domain the whole repo calls SELV (`elec/domain_manifest.yaml`,
`netclass_rules.yaml`, `docs/hardware/SELV_ISOLATION_REDESIGN.md`) is, by the
standard's own definition, a **PELV** circuit. This is a naming defect only; it
moves no distance by itself. It does, however, select which clause governs.

### 2.2 Clause 3.4.4 admits exactly three constructions, and two are unavailable

IEC 60335-1 clause 3.4.4, CITED-PRIMARY
(`docs/evidence/2026-07-28-creepage-determination-brainstorm.md:174-181`):

> "Protective Extra-Low Voltage Circuit — Earthed circuit operating at safety
> extra-low voltage which is separated from other circuits by **basic
> insulation and protective screening, double insulation or reinforced
> insulation**."

with Note 1: *"Protective screening is the separation of circuits from live
parts by means of an earthed screen."*

| construction | available on this board? |
|---|---|
| (a) basic insulation **+ protective screening** | **No.** There is no earthed screen between a mains pad and an LV pad sitting side by side on `F.Cu`, and none vertically either: the brainstorm doc's own board measurement found all 96 copper zones on `F.Cu`/`B.Cu`, none on `In1.Cu`/`In2.Cu`, and not one on the `gnd` net (`…brainstorm.md:189`). An unexploited design opportunity, not a present construction. |
| (b) double insulation | **No.** Double insulation is basic + supplementary as two independent insulations in series. A single lateral gap across one laminate surface is one insulation, not two. |
| (c) **reinforced insulation** | **This is the one.** |

**Therefore: reinforced. Every lateral mains↔PELV crossing on this board.**

### 2.3 Two independent corroborations, reached by different routes

- `docs/evidence/2026-07-30-insulation-tier-audit.md:5-16` audited
  `IEC60335_REQUIREMENTS`'s tier column head-on and concluded
  `(MAINS, LV_CONTROL, REINFORCED)` is correct — via operator-accessibility of
  the RTD probe/controls and the observation that the `gnd~pe` bond is *"a
  SELV-domain noise-reference decision on ordinary PCB copper, not a certified,
  continuity-tested protective-earth conductor of the kind IEC 60335-1's Class I
  basic-insulation-plus-earthing exception actually requires."*
- The brainstorm doc reached the same conclusion via cl. 3.4.4 after explicitly
  **retiring** two earlier mechanisms that had been used to justify it —
  "user-accessible ⇒ reinforced" and "the HV side floats ⇒ reinforced" — as
  unsound (`…brainstorm.md:193-213`). The conclusion survived the retirement of
  both of its original arguments. That is the strongest form this evidence
  comes in.

**Not basic. Not supplementary. Not double. Reinforced, on cl. 3.4.4.**

---

## 3. The board is 120 V, single-market. The dual-voltage prose has no part behind it.

This is the fork the brief asked to be checked, and it is worth stating plainly
because the documentation genuinely does contradict itself.

### 3.1 What the committed electrical source says

| fact | path:line |
|---|---|
| `v_ac_nominal = 120V` | `elec/src/main.ato:52` |
| `assert v_ac_nominal within 100V to 130V  # NEMA 5-15 tolerance` | `elec/src/main.ato:56` |
| `f_line: frequency = 60Hz`; `assert f_line within 59Hz to 61Hz  # US grid tolerance` | `elec/src/main.ato:62-63` |
| `v_bus_nominal = 340V`; `assert v_bus_nominal within 280V to 380V  # Doubler output range` | `elec/src/main.ato:65-66` |
| "AC Mains (120V)" in the complete power path | `docs/hardware/VOLTAGE_DOUBLER_DESIGN.md:206` |
| "Compatible with 120V/15A outlet (no 240V required)" | `docs/hardware/VOLTAGE_DOUBLER_DESIGN.md:23` |

There is no voltage-selector switch and no doubler-bypass path anywhere in
`elec/src/*.ato`. `K_BYPASS` is the NTC soft-start bypass relay
(`elec/src/main.ato:925-926`, `docs/hardware/BOM.md:50`), not a 120/240 range
selector.

### 3.2 The parts settle it, and one part settles it alone

- **`RV1` = Littelfuse `V150LA10AP`, "150VAC clamp, L-N after fuse"**
  (`docs/hardware/BOM.md:46`). The `V150LA` family's maximum continuous
  operating voltage is 150 V rms. Fitted across L–N on a 230 V supply it
  conducts continuously at line frequency and fails thermally, typically
  within seconds. **This single line is dispositive: the as-built board cannot
  be energised from 230 V at all.**
- **The topology is a full-wave (Delon) doubler**
  (`docs/hardware/VOLTAGE_DOUBLER_DESIGN.md:42-56`) producing ~314–340 V from
  120 V. Fed 230 V it would produce ~650 V against
  `v_bus_abs_max = 400V` (`elec/src/main.ato:50`) and against 400–450 V bulk
  capacitors — an immediate destructive over-voltage, not a derating question.
- **NEMA 5-15 / 15 A branch**: `main.ato:56`'s own comment, plus a 15 A
  continuous load at 1 800 W/120 V.

### 3.3 The 240 V prose, named so it can be corrected separately

| claim | path:line | status |
|---|---|---|
| "Supply Voltage (EU) 207 / 230 / 253 V AC" | `docs/ENVIRONMENTAL_SPEC.md:19` | **Not supported by any committed part.** Contradicted by `RV1` and by the doubler. |
| "AC mains: 120/240 VAC" | `docs/hardware/COMPONENT_COMPATIBILITY_VERIFICATION.md:323` | same |
| "120 V AC (US) / 230 V AC (EU)" | `docs/REGULATORY_COMPLIANCE.md:63` | same |
| "240V System (2.0kW)" thermal columns, DC bus 320 V | `docs/hardware/SYSTEM_THERMAL_BUDGET.md:63,91,150` | Describes a **bridge-rectifier variant** (320 V bus from 240 V), i.e. a *different power stage* from the one in `elec/src`. Not this board. |

**Finding, stated as the brief asked:** the repository documents an aspirational
120/230 V product family while committing a 120 V-only design. This is a real
documentation defect and it should be fixed — but it does **not** change the
barrier derivation, because the derivation must follow the board that exists.
**Rated voltage for insulation purposes: 120 V.**

*(Cost if this call is wrong and a 230 V variant is genuinely intended: Table 15
row iii (>150 ≤300 V) at OVC II → 2 500 V rated impulse → cl. 29.1.3 next step
→ Table 16 @ 4 000 V = 3.0 mm, +0.5 = **3.5 mm clearance**; creepage is
**unchanged at 8.0 mm**, because 230 V sits in the same Table 17 row iii the
120 V case reaches under sec 6.3. Measured cost of 3.5 mm: **3** clearance
violations instead of 1. So even the wrong answer here is cheap — the
dual-voltage question is a documentation problem, not a barrier-geometry one.)*

---

## 4. Pollution degree: PD3. Carried, not re-derived.

IEC 60335-2-6 clause 29.2, Addition, CITED-PRIMARY
(`docs/evidence/2026-07-28-creepage-determination-brainstorm.md:381-386`):

> "The microenvironment is **pollution degree 3** unless the insulation is
> enclosed or located so that it is unlikely to be exposed to pollution during
> normal use of the appliance."

This is the particular standard for hobs and cooking ranges and it inverts Part
1's cl. 29.2 default (*"Pollution degree 2 applies unless…"*,
`…brainstorm.md:374-379`). PD2 must be **earned** by an enclosure that does not
exist: `docs/evidence/2026-08-12-pollution-degree-resolution.md:6-16` records no
cover, gasket, partition or inspection geometry anywhere in the repo,
`docs/specs/pd2_compartment_evidence.yaml` absent, and
`scripts/check_pd2_compartment_evidence.py` failing today. The same document's
sec 5 (`:60-84`) adds that building the compartment is not free either — the
repo's own thermal bound puts the LMR51430 and UCC21550 at zero-to-negative
junction-temperature margin once the airflow the seal removes is gone.

**PD3 governs the as-built board.** Note that `scripts/generate_kicad_dru.py:110`
still selects `HV_CREEPAGE_PD2_MM`; that mismatch is pre-existing and is not
this document's to resolve, but it matters below only because — by a
coincidence documented in sec 6.4 — the PD2 and PD3 paths land on the same
8.0 mm here.

---

## 5. Clearance: **2.0 mm** reinforced

### 5.1 Rated impulse voltage

IEC 60335-1 clause 29.1, CITED-PRIMARY (`…brainstorm.md:221`):
**"Appliances are in overvoltage category II."**

Table 15, "Rated Impulse Voltage", CITED-PRIMARY (`…brainstorm.md:225-231`):

| Rated voltage (V) | OVC I | OVC II | OVC III |
|---|---:|---:|---:|
| ≤50 | 330 | 500 | 800 |
| **>50 and ≤150** | 800 | **1 500** | 2 500 |
| >150 and ≤300 | 1 500 | 2 500 | 4 000 |

Rated voltage **120 V** (sec 3) → **row ii**; OVC II → **rated impulse voltage
1 500 V**. DERIVED.

*OVC sensitivity, as the brief asked.* The clause states OVC II unconditionally
for appliances, and this one is cord-connected through a NEMA 5-15 plug — the
paradigm OVC II installation, not equipment at the origin of the installation.
If a reviewer nonetheless imposed **OVC III**: row ii → 2 500 V → cl. 29.1.3
next step → Table 16 @ 4 000 V = 3.0 mm, +0.5 = **3.5 mm**. Measured cost:
**3** violations instead of 1 (sec 7). Creepage is untouched by OVC — Table 17
is not indexed by impulse voltage at all.

### 5.2 Table 16 and the reinforced step

Table 16, "Minimum Clearances", CITED-PRIMARY (`…brainstorm.md:243-256`):

| Rated impulse voltage (V) | Minimum clearance (mm) |
|---:|---:|
| 1 500 | 0.5 — *footnote: "This value is increased to 0.8 mm for pollution degree 3"* |
| **2 500** | **1.5** |
| 4 000 | 3.0 |

Clause 29.1.3, CITED-PRIMARY (`…brainstorm.md:261-263`):

> "Clearances of reinforced insulation shall be not less than those specified
> for basic insulation in Table 16, but **using the next higher step for rated
> impulse voltage as a reference**."

1 500 V → next higher step **2 500 V** → **1.5 mm**.

**The PD3 footnote does not reach this lookup.** It is attached, in the
recovered text, to the **1 500 V row only**; cl. 29.1.3 sends the reinforced
lookup to the 2 500 V row, which carries no such footnote. So — usefully —
**the PD3 determination that dominates the creepage answer changes the
clearance answer not at all.** (Basic insulation at this board's impulse
voltage *would* move, 0.5 → 0.8 mm; that is not the tier here.)

### 5.3 The soldered-construction adder

Clause 29.1, CITED-PRIMARY (`…brainstorm.md:265-271`):

> "if the construction is such that the distances could be affected by wear, by
> distortion, by movement of the parts or during assembly, the clearances for
> rated impulse voltages of 1 500 V and above are increased by 0.5 mm and the
> impulse voltage test is not applicable" … "Examples of constructions in which
> distances are likely to be affected are those involving **soldering**, snap-on
> and screw terminals and clearances from motor windings."

A soldered PCB is one of the clause's own named examples. Rated impulse voltage
is 1 500 V, i.e. "1 500 V and above". **+0.5 mm.**

### 5.4 Clause 29.1.5 adds nothing here

Clause 29.1.5, CITED-PRIMARY (`…brainstorm.md:273-279`), raises the determining
voltage by *"the difference between the peak value of the working voltage and
the peak value of the rated voltage"*. Across the **mains↔PELV** barrier the
working voltage **is** the mains voltage: peak working = peak rated = 120·√2 =
169.7 V, difference **zero**, `V_det` = 1 500 V unchanged.

This is the one place where the mains barrier and the DC-bus barrier genuinely
part company, and it is why they are different determinations: the resonant
tank's 923.7 V peak (`docs/evidence/2026-08-12-hv-clearance-adequacy.md:8-18`)
drives `V_det` to 2 254 V on **its** crossing. Nothing on the `ac_l`/`ac_n`
nets rings.

### 5.5 Result

```
120 V rated  →  Table 15 row ii, OVC II       →  1 500 V rated impulse
             →  cl. 29.1.3 next higher step   →  Table 16 @ 2 500 V = 1.5 mm
             →  cl. 29.1 soldered adder       →  +0.5 mm
                                              =  2.0 mm  REINFORCED CLEARANCE
```

**2.0 mm.** Not 6.0. The enforced figure is **3× the requirement**.

---

## 6. Creepage: **8.0 mm** reinforced at PD3

### 6.1 The indexing inputs

Clause 29.2, CITED-PRIMARY
(`docs/evidence/2026-08-12-hv-hv-creepage-determination.md:295-297`):

> "Appliances shall be constructed so that creepage distances are not less than
> those appropriate for the **working voltage**, taking into account the
> **material group** and the **pollution degree**."

- **Pollution degree: PD3** (sec 4).
- **Material group: IIIa/IIIb.** No laminate MPN, stackup file or CTI value is
  tied to this board anywhere —
  `docs/hardware/IEC60335_CRITICAL_COMPONENTS.md:92` says so explicitly
  (*"there is no fab drawing, stackup file, or laminate MPN in the repo that
  ties this requirement to an actual UL-recognized laminate"*), and
  `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md:87` states IIIb as a design
  *target*. Generic FR-4 with an unstated CTI is IIIa/IIIb. **IEC 60335-1
  merges IIIa and IIIb into a single column** (`…brainstorm.md:302-306`), so
  the IIIa-vs-IIIb question buys nothing; only reaching group II (CTI > 400)
  or I (CTI > 600) would move the answer, and neither is specified.
- **Working voltage: 120 V rms** — the mains voltage, line to earthed PELV.
  Clause 3.1.3's Notes, CITED-PRIMARY
  (`…hv-hv-creepage-determination.md:302-304`): *"Working voltage takes into
  account resonant voltages"* and *"When deducing the working voltage, the
  effect of transient voltages is ignored."* Neither reaches the `ACMains`
  nets: they carry no resonant node, and the MOV-clamped surge environment is
  transient by definition. `ac_n` is treated as a live mains conductor at the
  same working voltage as `ac_l`, not as a near-earth node — plug reversal and
  open-neutral faults are exactly why the standard does not distinguish them.

### 6.2 Table 17 and the reinforced doubling

Table 17, "Minimum Creepage Distances for **Basic** Insulation", CITED-PRIMARY
(`…brainstorm.md:281-294`); the two candidate rows, IIIa/IIIb columns:

| Working voltage (V) | PD1 | PD2 IIIa/IIIb | **PD3 IIIa/IIIb** |
|---|---:|---:|---:|
| **>50 and ≤125** | 0.3 | 1.5 | **2.4** |
| **>125 and ≤250** | 0.6 | 2.5 | **4.0** |

Independently cross-checked: the identical Table 17 cells are transcribed from
a separate OCR pass in `…hv-hv-creepage-determination.md:254-259` (the T17
columns of its 500 V-cliff comparison table) and agree cell-for-cell, and the
brainstorm doc's sec 3.4 (`…brainstorm.md:308-319`) cross-checks the same rows
against Broadcom's reproduction of IEC 60664-1 with exact agreement.

Clause 29.2.3, CITED-PRIMARY (`…brainstorm.md:296-297`):

> "Creepage distances of reinforced insulation shall be **at least double**
> those specified for basic insulation in Table 17."

- Row ii → 2 × 2.4 = **4.8 mm**
- Row iii → 2 × 4.0 = **8.0 mm**

*(Table 18, the functional-insulation table, is **not** applicable here: it
governs cl. 29.2.4 functional insulation, and cl. 3.3.5 defines that as
insulation *"necessary only for the proper functioning of the appliance"*
(`…hv-hv-creepage-determination.md:170-174`). A mains↔PELV shock barrier is
not that. Table 17, doubled, is the right instrument.)*

### 6.3 The fork at 125 V, and which way I would go

**This is the one soft joint in the determination and I will not paper over it.**
120 V nominal sits 4 % below Table 17's 125 V row boundary. Two defensible
readings:

| reading | working voltage | row | **reinforced** | measured violations |
|---|---:|---|---:|---:|
| **A** — working voltage = *rated* voltage, 120 V | 120 V | ii (>50 ≤125) | **4.8 mm** | 6 |
| **B** — working voltage = top of the declared supply envelope | 130 V (`elec/src/main.ato:56`) / 132 V (`docs/ENVIRONMENTAL_SPEC.md:18`) | iii (>125 ≤250) | **8.0 mm** | 8 |

**What is missing, stated precisely.** The deciding text is the **body of IEC
60335-1 clause 3.1.3's definition of working voltage** (and, if the appliance
is marked with a rated voltage *range* rather than a single rated voltage,
clause 3.1.x's rated-voltage-range provision). **Only Notes 2 and 3 of cl.
3.1.3 have been recovered into this repository** (`…hv-hv-creepage-determination.md:302-304`);
the definition body has not. **A qualified reviewer must obtain the verbatim
text of cl. 3.1.3's definition body and of the rated-voltage-range clause, and
must confirm what rated voltage will appear on the appliance's own rating
plate** — "120 V" selects reading A, "100–130 V" or "120 V ±10 %" selects
reading B. I am not reconstructing that text; reconstructing a clause from
memory is exactly the failure that put 6.0 mm in this file for months.

**Which way I would go: B, 8.0 mm.** Four reasons, in order of weight:

1. **It is the conservative side of a 4 %-wide margin on a primary shock
   barrier.** A 132 V supply is inside this design's own declared envelope, not
   a fault condition. Reading A leaves the barrier under-specified for the top
   8 % of its legal operating range.
2. **It costs nothing.** 8.0 mm is *already what RULE 2 emits*
   (`scripts/generate_kicad_dru.py:885`). Reading A would be a **relaxation**
   of a shipped safety figure, and relaxing a barrier on an unrecovered clause
   is the wrong direction to be wrong in.
3. **The entire delta is 2 violations** (sec 7). There is no engineering
   pressure pushing toward the looser reading.
4. **It is independently reachable.** See 6.4.

### 6.4 8.0 mm is defensible in two disjoint cells — which is why it "felt right"

`…brainstorm.md:78` already recorded this, before anyone had picked a row:

> 8.0 mm = 2 × Table 17 (>250–400 V, **PD2**, IIIa/IIIb) = 2 × 4.0. **Also**
> = 2 × Table 17 (>125–250 V, **PD3**, IIIa/IIIb) = 2 × 4.0. "Defensible in two
> independent cells — which is why it 'felt right'."

`scripts/generate_kicad_dru.py:69-71` derives its 8.0 mm by the **first** cell —
PD2, working voltage >250–400 V. **That derivation is wrong for this rule on
both inputs**: PD3 governs (sec 4), and no `ACMains` net works at 250–400 V
(that is the DC bus, RULE 4's crossing). **The value is nevertheless correct**,
by the second cell: PD3 × row iii × ×2. Two errors that cancel exactly.

This is worth naming because *the comment is the thing that will be maintained*.
The next person who corrects the pollution degree from PD2 to PD3 in that
comment block, or who narrows the working voltage from "400 V" to the real
`ACMains` band, will — following a correct instinct on a wrong comment —
compute 12.6 mm (PD3 row iv) or 4.8 mm (PD2 row iii) and move a number that is
already right.

---

## 7. Does the board meet it? Measured, uncapped, live.

### 7.1 Method and its acceptance test

`scripts/measure_uncapped_drc.py` (PR #1111). The `AC Mains to LV` rule's own
condition is extracted from the generator's emitted DRU text by that tool's own
independent parser, and measured in isolation with a two-rule scratch DRU:
`(severity ignore)` on `!(condition)`, the real value on `condition`. Single-rule
isolation is exact here because the emitted DRU is **shadow-free** — the
generator's `find_shadowing()` guard (`scripts/generate_kicad_dru.py:489,1496`)
fails the build otherwise — so no pair matching this rule's condition is
governed by any other rule, and the AND-NOT chain reduces to the bare condition.
Every reading below was taken twice and reproduced **exactly**; determinism, not
proximity to a cap, is the signature of a true count
(`docs/evidence/2026-08-12-uncapped-drc-measurement.md:2.3`). No reading came
near its cap (499 clearance / 199 creepage).

**Acceptance test.** At the value actually shipped, 6.0 mm, this method reports
**23** — reproducing, to the unit, the `AC Mains to LV` band figure independently
derived twice before (`docs/evidence/2026-08-12-uncapped-drc-measurement.md:5.1`,
and PR #1110's hand protocol quoted in the same document's sec 4). The
measurement apparatus is calibrated against a known answer before it is used on
an unknown one.

### 7.2 Clearance sweep — `AC Mains to LV` band

| min clearance | violations | note |
|---:|---:|---|
| 0.8 mm | 0 | |
| 1.5 mm | 0 | reinforced before the soldered adder |
| **2.0 mm** | **1** | **the requirement (sec 5)** |
| 2.3 / 2.5 mm | 1 | flat |
| 3.0 mm | 3 | |
| 3.5 mm | 3 | the OVC III reading (sec 5.1) |
| 4.8 mm | 16 | |
| **6.0 mm** | **23** | **enforced today** |
| 8.0 mm | 38 | |

**22 of the 23 violations reported today are spurious** — they are pairs that
meet the reinforced requirement and are being failed by a figure with no
standards basis. Whole-board `clearance` moves 1 664 → **1 642**
(`docs/evidence/2026-08-12-uncapped-drc-measurement.md:5.1` for the 1 664; the
band is disjoint from every other rule by the shadow-free guard, so the
subtraction is exact).

**The one surviving clearance violation:**

```
actual 1.8000 mm | Pad 1 [ac_l] of R6  <->  Pad 2 [power_in.r_zcd_top1-p2] of R6
```

R6 is `power_in.r_zcd_top1`, a 220 kΩ 1206 in the mains zero-crossing-detect
divider. That entire circuit (R6–R10, D2, U3) was deleted from `elec/src/` on
main; `pcb/temper.kicad_pcb` was never resynced. 1.8 mm is simply the standard
pad-to-pad gap of a 1206 chip resistor. **This is stale-board noise, not a live
safety defect** — established in detail on branch `fix/r6-mains-pad-pitch`
(commit `a61e189aa`, not on main). The honest reading: **at the correct
clearance figure, this board has zero live mains↔SELV clearance defects.**

### 7.3 Creepage sweep — `AC Mains to LV` band

| min creepage | violations |
|---:|---:|
| 2.4 mm | 1 |
| 4.0 mm | 4 |
| **4.8 mm** (reading A) | **6** |
| 6.3 mm | 8 |
| **8.0 mm** (reading B — enforced today, and the recommendation) | **8** |
| 10.0 mm | 8 |
| 12.6 mm | 16 |

**No change from the correction: 8 violations today, 8 at the correct figure.**
Reading A would remove 2. The band is flat from 6.3 mm through 10.0 mm, so the
125 V row question is worth exactly two violations and nothing else.

**All 8, in full** (measured at 8.0 mm):

| actual | pair |
|---:|---|
| 1.8000 mm | Pad 1 `[ac_l]` of **R6** ↔ Pad 2 `[power_in.r_zcd_top1-p2]` of R6 — *dead ZCD, sec 7.2* |
| 2.6176 mm | PTH pad 2 `[ac_n]` of **C1** ↔ Track `[hb.gate_hs.driver-p1-1]` on F.Cu |
| 3.9571 mm | PTH pad 2 `[ac_n]` of **C1** ↔ Track `[rtd_pan.high_window-out]` on B.Cu |
| 3.9592 mm | PTH pad 2 `[ac_n]` of **C1** ↔ Track `[rtd_pan.rail_monitor-outa]` on F.Cu |
| 4.4866 mm | PTH pad 2 `[ac_n]` of **C1** ↔ Via `[rtd_pan.high_window-out]` F.Cu–B.Cu |
| 4.5151 mm | PTH pad 2 `[ac_n]` of **C1** ↔ Track `[y]` on B.Cu |
| 5.7400 mm | PTH pad 2 `[ac_n]` of **RV1** ↔ Track `[WDT_RESET_N]` on F.Cu |
| 5.9050 mm | PTH pad 2 `[ac_n]` of **L1** ↔ Track `[cs_n]` on B.Cu |

**Seven of eight are live, and seven of eight are the same node**: `ac_n`, on
three through-hole EMI-filter/protection parts (`C1` the X2 cap, `RV1` the MOV,
`L1` the common-mode choke), against SELV routing that has been allowed to
approach them. Worst is 2.62 mm against 8.0 mm — **3.1× short**. These are
routing/placement defects on the primary safety barrier, not part-selection
defects: nothing here needs a different component, only a keepout the router
respects.

### 7.4 The answer to "over- or under-specified?"

**Both, on the two different quantities the one rule carries, and nobody could
tell because the rule's comment describes neither of them.**

- As a **clearance** figure, 6.0 mm is **over**-specified by 3× — and the two
  cited errors did not cancel to it: even "basic at 240 V", the comment's own
  claim taken at face value, yields 1.5–2.0 mm (sec 1). The 6.0 mm never came
  from anywhere.
- As the **binding** constraint on a flat, ungrooved, uncoated board, creepage
  governs — the brainstorm doc's cross-check records the structural rule
  *"a creepage distance cannot be less than the associated clearances"*
  (`…brainstorm.md:321-327`), so the governing distance is
  max(clearance, creepage) = creepage = **8.0 mm**. That figure is separately
  and correctly enforced, by a wrong derivation (sec 6.4), and **the board
  fails it in 7 live places**.

The practical consequence of correcting the clearance figure is that **22
false alarms stop masking 7 real ones.**

---

## 8. `HV_INTERNAL_CLEARANCE_MM`: the mains-barrier figure on the wrong rule — and two derivations that collided on one constant

**Yes. Both halves of the brief's hypothesis are true simultaneously.**

### 8.1 The constant self-describes as the mains barrier

`scripts/generate_kicad_dru.py:59-67`, verbatim:

```python
# Fail-closed reinforced clearance for the mains<->PELV barrier, uncoated.
# IEC 60335-1 clause 29.1: rated impulse voltage 1500V (120V nominal, OVC II,
# Table 15) -> Table 16 basic clearance 0.5mm at that step -> clause 29.1.3
# "next higher step" for reinforced -> 1.5mm nominal, PLUS clause 29.1's
# +0.5mm soldered-construction adder (this is a soldered PCB, one of the
# clause's own named examples) = 2.0mm. See
# docs/evidence/2026-07-28-creepage-determination-brainstorm.md sec 4 and
# docs/evidence/2026-07-28-conformal-coating-pd1.md sec 3, item 3.
HV_INTERNAL_CLEARANCE_MM = 2.0
```

That is **sec 5 of this document, line for line** — same clauses, same table
rows, same adder, same 120 V, same OVC II, same answer. **The correctly-derived
mains↔SELV reinforced clearance already exists in this file, with a complete
and correct citation.**

### 8.2 It is wired to a same-HV-domain rule

Its only consumer is `scripts/generate_kicad_dru.py:1188`, inside:

```
scripts/generate_kicad_dru.py:1179  '(rule "HV internal same footprint"'
scripts/generate_kicad_dru.py:1181-1185  condition: A.NetClass in {HighVoltage, HighVoltageTank}
                                         && B.NetClass in {HighVoltage, HighVoltageTank}
                                         && A.Reference == B.Reference
scripts/generate_kicad_dru.py:1188  "   (constraint clearance (min 2.0mm))"
```

`ACMains` appears nowhere in that condition. The rule the comment describes —
`"AC Mains to LV"` at line 876 — takes the uncited `6.0mm` literal at line 884
instead. **The right number and the right rule are 300 lines apart in the same
file and have never been connected.**

### 8.3 They are two different figures that happen to be equal

`docs/evidence/2026-08-12-hv-clearance-adequacy.md:8-18` independently derived
2.0 mm for same-domain `HighVoltage` pairs — by a **completely different
route**: 923.7 V peak measured working voltage at the tank node → cl. 29.1.5's
resonant-voltage provision → `V_det` = 1 500 + (923.7 − 169.7) = 2 254 V →
Table 16 @ the 2 500 V step = 1.5 mm → +0.5 mm soldered = 2.0 mm.

| | mains↔PELV barrier (sec 5) | same-domain HV↔HV (`hv-clearance-adequacy`) |
|---|---|---|
| tier | reinforced (cl. 3.4.4) | functional (cl. 29.1.4) |
| voltage input | 169.7 V peak = rated peak | 923.7 V peak, resonant |
| route to Table 16 | cl. 29.1.3 "next higher step" | cl. 29.1.5 `V_det` |
| Table 16 row reached | 2 500 V | 2 500 V |
| base | 1.5 mm | 1.5 mm |
| adder | +0.5 mm | +0.5 mm |
| **result** | **2.0 mm** | **2.0 mm** |

**Nothing is mis-enforced today. Both figures are 2.0 mm and one constant
carries both.** But the equality is a coincidence of Table 16's coarse steps,
not a shared derivation, and it is *load-bearing on inputs that are already
known to be marginal*:

- `hv-clearance-adequacy.md:22-31` states the HV↔HV figure is *"adequate at the
  step boundary"* — the 1.5 → 3.0 mm step sits at 1 169.7 V peak, the worst
  OCP-passing measured point is 923.7 V (1.27× margin), and **one real
  in-tolerance parameter combination reaches 1 289.4 V**, which crosses the
  step and would require **3.5 mm**. It is prevented only by OCP-01 tripping.
- The mains-barrier figure would move to 3.5 mm only under OVC III (sec 5.1) —
  an entirely unrelated trigger.

**So: the moment either input moves — an OCP-01 threshold change, an OVC
reclassification, a laminate or voltage-range decision — one figure moves and
the other does not, and a single constant cannot express that.** The finding,
stated plainly as the brief asked: **`HV_INTERNAL_CLEARANCE_MM` is the
correctly-derived mains↔PELV barrier clearance, carrying the mains barrier's
citation, attached to the HV-internal rule; the HV-internal rule's own correct
figure is a different derivation that currently produces the same number. They
should be two named constants with two citations, and `"AC Mains to LV"` should
consume the mains one.** No change is made here.

---

## 9. What a qualified reviewer must obtain

Everything below is a text this repository does not hold. Nothing in secs 2–8
depends on any of it *except where noted*.

1. **IEC 60335-1 cl. 3.1.3, definition body** (only Notes 2 and 3 are recovered),
   **and the rated-voltage-range clause.** Decides sec 6.3's fork between
   4.8 mm and 8.0 mm. **Cost of the wrong call: 2 violations.** Recommendation
   pending that text: hold 8.0 mm.
2. **The appliance's rating-plate marking** ("120 V" vs "120 V ±10 %" vs
   "100–130 V"). Same fork, same 2 violations.
3. **A laminate MPN with a UL-recognised CTI.** If the board is built on a
   material group **II** laminate (CTI > 400), Table 17 row iii PD3 gives
   3.6 mm basic → **7.2 mm** reinforced; group **I** (CTI > 600) gives 3.2 →
   **6.4 mm**. Neither is a large enough relief to close the 2.62 mm worst
   pair, so **this cannot rescue the board** — but it is the cheapest thing to
   pin down and it is currently unspecified
   (`docs/hardware/IEC60335_CRITICAL_COMPONENTS.md:92`).
4. **Confirmation of OVC II for a cord-connected countertop appliance.** Clause
   29.1's own text is recovered and unconditional; this is a formality.
   **Cost if OVC III: 2 additional clearance violations** (1 → 3).
5. **The PD2-vs-PD3 question is NOT on this list.** It is settled at PD3
   (sec 4), and by sec 6.4's coincidence it does not move the creepage figure
   for *this* rule anyway. It very much moves other rules; that is
   `pollution-degree-resolution.md`'s business, not this document's.

**Not required, and deliberately so:** an Annex J conformal-coating
qualification. `docs/evidence/2026-07-28-conformal-coating-pd1.md` and
`scripts/generate_kicad_dru.py:20-57`'s fail-closed `COATING_QUALIFIED` gate
already establish that IEC 60664-3 cl. 4.3 requires the *entire* path covered,
that 100 % of the shortest HV↔PELV surface paths lie under component bodies,
and that no coating exists in the BOM or assembly process. Coating is not a
route to relief here and should not be reopened as one.

---

## 10. Reproduction

```bash
git worktree add <path> -b analysis/mains-selv-barrier-derivation origin/main
cd <path> && uv sync --all-packages

# Isolate the `AC Mains to LV` band and sweep it. The driver builds a two-rule
# scratch DRU (severity-ignore on !condition, the swept value on condition) and
# runs kicad-cli against a scratch board copy; pcb/** is never written.
UNCAPPED_DRC_REPO_ROOT=$PWD uv run --all-packages python <driver> \
  --repo $PWD --scratch-dir /tmp/scratch/cl \
  --ctype clearance --values 0.8,1.5,2.0,3.0,3.5,4.8,6.0,8.0
UNCAPPED_DRC_REPO_ROOT=$PWD uv run --all-packages python <driver> \
  --repo $PWD --scratch-dir /tmp/scratch/cr \
  --ctype creepage --values 2.4,4.0,4.8,6.3,8.0,10.0,12.6
```

The driver is ~90 lines over `scripts/measure_uncapped_drc.py`'s public
helpers (`parse_dru_rules`, `make_scratch_board`, `run_kicad_drc`, `cap_for`)
plus `scripts/generate_kicad_dru.py`'s `generate_dru()`; it is scratch analysis
code and is not committed, exactly as `…brainstorm.md:438` handled its own
`measure.py`. Its acceptance test is sec 7.1: it must report **23** at 6.0 mm
before any other reading is trusted.

Board unchanged throughout: `sha256(pcb/temper.kicad_pcb) =
6928b7c8950a732f1991578f5ff7c080104c0847bf438ccd8bf2c75150544b64`, identical
before and after.
