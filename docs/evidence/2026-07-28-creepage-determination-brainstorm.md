<!-- provenance: commit=fed05e82b45c7612a2f1e636b007511e7deda8c1 dirty=false -->

# Mains<->PELV creepage/clearance: closing the determination against primary text

Base commit: `fed05e82` (`merge: barrier-constrained placement is INFEASIBLE -- and
it is a BOM problem`). Worktree `agent-affde0c273cebb0ff`, branch
`brainstorm/creepage-determination`, checked out directly at that commit.

**This is a structured brainstorm and a requirement determination. It changes
nothing.** No BOM file, `packages/temper-placer/configs/netclass_rules.yaml`, the
`8.0` constant in `scripts/check_isolation_keepout.py`, `pcb/temper.kicad_pcb`,
or any gate was touched.

## Provenance labels used throughout

| Label | Meaning |
|---|---|
| **CITED-PRIMARY** | Quoted from the standard's own text (see "Sources" for exactly what was reached and how). |
| **CITED-SECONDARY** | Quoted from a manufacturer/agency document reproducing standards content. |
| **MEASURED** | Computed this session from `pcb/temper.kicad_pcb` / `elec/domain_manifest.yaml`, script and output shown. |
| **DERIVED** | Arithmetic on labelled inputs, shown in full. |
| **ASSUMED** | Not established. Flagged for a human. |

---

## Verdict up front

**8.0 mm is the correct REINFORCED CREEPAGE figure under exactly one set of
inputs, and that set is now clause-cited rather than reconstructed:**

> IEC 60335-1 clause 29.2.3 ("Creepage distances of reinforced insulation shall
> be at least double those specified for basic insulation in Table 17") applied
> to Table 17 row iv (working voltage >250 V and <=400 V), pollution degree 2,
> material group IIIa/IIIb: basic 4.0 mm, therefore **reinforced 8.0 mm**.
> — CITED-PRIMARY

It is **too small** if pollution degree 3 applies at that working-voltage
bracket (2 x 6.3 = **12.6 mm**), and IEC 60335-2-6 clause 29.2 makes **PD3 the
default for this appliance class**, with PD2 an exception that must be earned by
enclosure. This is the live risk and it points the opposite way from the whole
prior arc.

It is **too conservative** if the barrier working voltage is really <=250 V
(2 x 2.5 = **5.0 mm** at PD2/IIIa-IIIb), or if a material-group-II laminate is
specified (**5.6 mm** at >250-400 V/PD2), or if a clause-29 Annex J Type A
conformal coating is qualified (PD1 under the coating: **2.0 mm**).

**8.0 mm is badly wrong as a CLEARANCE figure, and the repo's own two candidate
clearance numbers (4.0 mm and 6.4 mm) are wrong too — because neither is a
clearance number.** IEC 60335-1's clearance requirement here is
**1.5 mm (2.0 mm with the clause-29.1 soldered-construction adder)**, up to
3.0-3.5 mm under a stricter reading. See §4.

**The single most consequential finding is methodological, not numeric:**
`scripts/check_isolation_keepout.py` enforces 8.0 mm as a *straight-line,
zero-copper corridor width* — a **clearance-shaped constraint carrying a
creepage-derived number**. Straight-line corridor width is a *sufficient* but
not *necessary* condition for creepage. **CP-SAT proving that condition
INFEASIBLE therefore does not prove the requirement unsatisfiable, and the BOM
conclusion does not follow from it.** See §7.

**Re-measuring the isolators with a rectangle-aware pad model (exact here — all
eight isolator footprints are rotated by multiples of 90 degrees) shrinks the
"7 of 8 isolators are a BOM problem" finding to 3 of 8, and to 2 sourced parts.**
`T1` (9.10 mm) and `K1` (8.00 mm) pass 8.0 mm outright; the prior doc's 7.0 mm
and 5.425 mm for them are bounding-circle artifacts. See §6.

---

## 1. Reconciling the repo's figures — where each one actually came from

I traced every creepage/clearance figure in the repo against IEC 60335-1's own
Tables 16 and 17 (CITED-PRIMARY, §3) and IEC 60664-1's Tables (CITED-SECONDARY,
§3.4). Result:

| Repo figure | Source doc | Claimed as | What it actually is |
|---|---|---|---|
| **8.0 mm creepage** | `docs/evidence/2026-07-28-isolation-keepout.md` | reinforced creepage | **Correct.** = 2 x Table 17 (>250-400 V, PD2, MG IIIa/IIIb) = 2 x 4.0. Also = 2 x Table 17 (>125-250 V, **PD3**, IIIa/IIIb) = 2 x 4.0. Defensible in two independent cells — which is why it "felt right". |
| **6.4 mm "clearance"** | same doc | reinforced clearance | **A creepage value wearing a clearance label.** 6.4 = 2 x 3.2 = Table 17 (>125-250 V, PD3, material group **I**), and independently = IEC 60664-1's 320 V / PD2 / Group III reinforced creepage. **6.4 appears in no clearance table in either standard.** IEC 60335-1 Table 16's entire value set is {0.5, 1.5, 3.0, 5.5, 8.0, 11.0}. |
| **6.5 mm creepage** | `docs/PCB_SAFETY_DESIGN_RULES.md` §2.1 | reinforced creepage | **Untraceable.** Matches no cell of Table 17, no 2x-Table-17 value, no Table 16 value, and no IEC 60664-1 value. Nearest neighbours are 6.3 (Table 17 basic, >250-400 V, PD3, IIIa/IIIb) and 6.4 (above). |
| **4.0 mm "clearance"** | same doc §2.1 | reinforced clearance | **Also a creepage value wearing a clearance label.** 4.0 = Table 17 basic (>250-400 V, PD2, IIIa/IIIb), and = 2 x 2.0 = reinforced at the same row for material group **I**. Not a Table 16 clearance value. |
| **8.0 mm "design target"** | same doc §2.1 | margined target above 6.5 | Coincides with the true reinforced creepage figure by accident, not by derivation. Its stated basis ("provides margin for manufacturing") is not a standards basis. |
| **3.0 mm creepage / 2.0 mm clearance** | same doc §2.2 "Basic" | basic, HV-to-HV | 3.0 is a Table 16 *clearance* value (at 4000 V impulse); it is not a Table 17 creepage value at any plausible row. Same category of mix-up. |
| **6.0 mm clearance, `because: "IEC 60335-1 Table 16 working isolation at 400V"`** | `netclass_rules.yaml` (`ACMains`, `HighVoltage`, all 9 `class_pairs`) | HV-to-HV working isolation | **Misattributed twice over.** Table 16 is indexed by *rated impulse voltage*, not working voltage; 400 V is not one of its rows (rows are 330/500/800/1500/2500/4000/6000/8000/10000 V); and 6.0 mm is not one of its values. |
| **"clause 22.3 — creepage/clearance >8mm for basic insulation"** | `docs/hardware/GROUNDING_EMI_STRATEGY.md:389` | IEC 60335-2-6 clause | Clause 29, not 22.3, is the creepage/clearance clause. 8 mm is not a basic-insulation figure at any row applicable here. |
| **">6mm for mains (Reinforced)"** | `docs/REGULATORY_COMPLIANCE.md:126` | reinforced | Checklist prose, no PD / material group / voltage given. Not a calculation. |
| **8.0 / 6.0 / 3.0 / 4.0 mm matrix** | `temper_placer/requirements/validators/clearance.py` `IEC60335_REQUIREMENTS` | MAINS<->LV_CONTROL basic & reinforced | The **only** internal artifact whose creepage numbers are right: basic creepage 4.0, reinforced creepage 8.0 — exactly Table 17 row iv PD2 IIIa/IIIb and its double. Its *clearance* numbers (basic 3.0, reinforced 6.0) are not Table 16 values. |

### The single pattern behind all of it

**Every wrong number in this repo is a creepage value that has been relabelled
as a clearance value.** 4.0, 6.0, 6.4, and 3.0 are all real numbers from
creepage tables (or, for 3.0, from Table 16 misapplied to creepage). Not one of
them is the clearance figure for this appliance. Nobody in this project's
history has ever computed the clearance requirement — they computed creepage
(sometimes correctly), then wrote a second, smaller creepage number in the
clearance column because "clearance is smaller than creepage".

That heuristic is true as a *comparison* and useless as a *derivation*. The two
quantities are indexed by different inputs: clearance by **rated impulse
voltage** (Table 16), creepage by **working voltage x pollution degree x
material group** (Table 17). Knowing one tells you nothing about the other
beyond the ordering constraint.

### Provenance of the two source documents

- `docs/PCB_SAFETY_DESIGN_RULES.md` self-dates 2025-12-17 but entered git in
  `b29b4432` (2026-07-17), a bulk-import commit touching the whole tree.
  `git log --follow` shows **no derivation history whatsoever** — it has never
  been revised for content. Its header claims "Derived from IEC 60335-1 /
  60335-2-6" and it cites **no clause and no table**. MEASURED (git).
- `docs/evidence/2026-07-28-isolation-keepout.md` states its own figures as
  "reconstructed from secondary/industry sources" for the "closely analogous
  IEC 60950-1/62368-1" case, explicitly labelled UNVERIFIED-at-primary by its
  own author. That self-assessment was accurate and honest. Its creepage number
  is right; its clearance number is a mislabelled creepage number.

**Neither document is derived for a different insulation class or a different
standard.** Both are aiming at the same requirement. One got creepage right by
route; the other got a number nobody can trace.

---

## 2. Which insulation class applies — and why both prior mechanisms are superseded

The task asked me to test "HV side floats => reinforced" **on its own merits
rather than letting it inherit confidence from the conclusion.** Doing so
produces a better answer than either version, from primary text.

### 2.1 The tested mechanism does not hold as stated

The claim was: the Class-I earthed-substitute argument needs the earth bond on
the hazardous side so a fault drives current to trip upstream protection; here
the HV side floats, so it does not; therefore reinforced.

Two premises fail:

1. **"The HV side floats" is not true in the sense the argument needs.**
   `power_return`/`PWR_RTN` is the voltage-doubler midpoint. It is DC-coupled to
   the AC input through the doubler diodes and bulk capacitors — a mains-derived
   node that tracks neutral, not an isolated secondary. What is true is narrower:
   it has no *deliberate* PE bond, only C6's 2.2 nF AC/EMI path
   (`elec/src/main.ato:456-465`). "Unearthed" is correct; "floating" overstates it.
   DERIVED from `main.ato` + `domain_manifest.yaml`.
2. **"A breakdown does not reliably trip upstream protection" is directionally
   right but for the wrong reason.** A hard short from `+170V_BUS` to PE-bonded
   `gnd` would in fact source large current from the bus caps and the mains
   through the doubler. The safety-relevant point is not the magnitude of that
   current — it is that **`gnd ~ pe` is a functional/reference bond, not a
   protective bonding conductor.** IEC 60335-1 clause 27.5's earthing
   requirement is a measured one: a test current is passed and "the resistance
   calculated from the current and this voltage drop shall not exceed 0.1 Q"
   [ohm] (CITED-PRIMARY). Whether the `gnd`->`pe` connection on this board meets
   that as a *protective* bond is a PCB/mechanical fact that no document in this
   repo establishes.

So the corrected mechanism reaches the right conclusion, but its reasoning would
not survive a safety assessor's question. Good news: it does not have to.

### 2.2 The mechanism that does hold, from primary text

IEC 60335-1 clause 27.1 (CITED-PRIMARY):

> "Safety extra-low voltage circuits shall not be earthed unless they are
> protective extra-low voltage circuits."

`elec/src/main.ato:475` is `gnd ~ pe` — a hard 0-ohm DC bond. **The low-voltage
domain is therefore, by the standard's own definitions, a PELV circuit, not a
SELV circuit.** The entire repo — `domains.SELV` in `elec/domain_manifest.yaml`,
`docs/hardware/SELV_ISOLATION_REDESIGN.md`, `netclass_rules.yaml` — calls it
SELV. Under IEC 60335-1 clause 3.4.2 and 27.1, that naming is wrong. (Naming
only; it does not by itself change any distance.)

And clause 3.4.4 (CITED-PRIMARY):

> "Protective Extra-Low Voltage Circuit — Earthed circuit operating at safety
> extra-low voltage which is separated from other circuits by basic insulation
> and protective screening, double insulation or reinforced insulation."

with its Note 1: "Protective screening is the separation of circuits from live
parts by means of an earthed screen."

**This settles the class outright, and does so without appealing to
user-accessibility or to floating-ness.** A PELV circuit must be separated from
the mains circuit by one of exactly three constructions:

| Option | Available here? |
|---|---|
| (a) basic insulation **+ protective screening** | **Not available today, in either axis.** There is no earthed screen between an HV pad and an LV pad sitting side by side on `F.Cu`. Nor is there one vertically: **MEASURED — the board's 96 copper zones are all on `F.Cu`/`B.Cu`, none on `In1.Cu` or `In2.Cu`, and not one of them is on the `gnd` net.** The two inner layers carry no pour at all. `netclass_rules.yaml`'s `GND: layer: "In1.Cu"` is a router *preference*, not an existing plane. So this option is **an unexploited design opportunity, not a current construction** — see §11 item 6. |
| (b) double insulation | Not the construction here. |
| (c) **reinforced insulation** | **This is the one. Required for every lateral mains<->PELV crossing.** |

### 2.3 What this means for the three readings

- **Reading A ("user-accessible => reinforced")** — the original. Not wrong in
  outcome, but the stated reason is not load-bearing: accessibility is not what
  clause 3.4.4 keys on. Correctly criticised by the prior session.
- **Reading B ("HV side floats => reinforced")** — the correction. Right
  outcome, unsound mechanism (§2.1). **Superseded, not adopted.**
- **Reading C ("PE-bonded, so Class I basic insulation suffices")** — the
  `domain_manifest.yaml` OVP-01 argument. **Correctly does not extend here**,
  and now for a citable reason: clause 3.4.4 permits basic insulation for a PELV
  circuit *only when accompanied by protective screening*, which does not exist
  laterally on this board. The OVP-01 dividers and C6 remain governed by the
  separate protective-impedance provision — they are current-limited paths
  (~130 uA normal, ~380 uA two-fault, per the manifest's own arithmetic); the
  galvanic isolators are not current-limited at all. **That current-limiting
  distinction, not accessibility and not floating-ness, is what separates the
  two classes of crossing.**

**Best-supported: reinforced insulation is required.** Same conclusion the repo
already carries, now with a clause behind it and with both prior mechanisms
retired.

---

## 3. Primary-text inputs

### 3.1 Overvoltage category and rated impulse voltage

IEC 60335-1 clause 29.1 (CITED-PRIMARY): **"Appliances are in overvoltage
category II."** This confirms `docs/ENVIRONMENTAL_SPEC.md`'s CAT II from the
standard rather than by assumption.

Table 15 "Rated Impulse Voltage" (CITED-PRIMARY):

| Rated voltage (V) | OVC I | OVC II | OVC III |
|---|---:|---:|---:|
| <=50 | 330 | 500 | 800 |
| >50 and <=150 | 800 | **1 500** | 2 500 |
| >150 and <=300 | 1 500 | 2 500 | 4 000 |

`elec/src/main.ato:52` sets `v_ac_nominal = 120V` with
`assert v_ac_nominal within 100V to 130V` (MEASURED, repo). Rated voltage 120 V
falls in row ii; OVC II => **rated impulse voltage 1 500 V**. DERIVED.

Table 15 Note 2 (CITED-PRIMARY): "The values are based on the assumption that
the appliance will not generate higher overvoltages than those specified. If
higher overvoltages are generated, the clearances have to be increased
accordingly." — directly relevant: this appliance contains a voltage doubler and
a resonant tank.

### 3.2 Table 16 — Minimum Clearances (CITED-PRIMARY)

| Rated impulse voltage (V) | Minimum clearance (mm) |
|---:|---:|
| 330 | 0.5 |
| 500 | 0.5 |
| 800 | 0.5 |
| 1 500 | 0.5 *(footnote: "This value is increased to 0.8 mm for pollution degree 3")* |
| 2 500 | 1.5 |
| 4 000 | 3.0 |
| 6 000 | 5.5 |
| 8 000 | 8.0 |
| 10 000 | 11.0 |

Note the entire value set: **{0.5, 1.5, 3.0, 5.5, 8.0, 11.0}**. Neither 4.0 nor
6.4 nor 6.0 nor 6.5 is in it. That is the arithmetic proof behind §1's claim
that the repo has no clearance figure at all.

Clause 29.1.3 (CITED-PRIMARY): "Clearances of reinforced insulation shall be not
less than those specified for basic insulation in Table 16, but using the next
higher step for rated impulse voltage as a reference."

Clause 29.1 (CITED-PRIMARY): "if the construction is such that the distances
could be affected by wear, by distortion, by movement of the parts or during
assembly, the clearances for rated impulse voltages of 1 500 V and above are
increased by 0.5 mm and the impulse voltage test is not applicable" —
and, naming the relevant constructions: "Examples of constructions in which
distances are likely to be affected are those involving **soldering**, snap-on
and screw terminals and clearances from motor windings."

Clause 29.1.5 (CITED-PRIMARY): "For appliances having higher working voltages
than rated voltage, for example on the secondary side of a step-up transformer,
**or if there is a resonant voltage**, the voltage used for determining
clearances from Table 16 shall be the sum of the rated impulse voltage and the
difference between the peak value of the working voltage and the peak value of
the rated voltage." Note 1: "Clearances for intermediate values of Table 16 may
be determined by interpolation."

### 3.3 Table 17 — Minimum Creepage Distances for **Basic** Insulation (CITED-PRIMARY)

Columns: pollution degree 1 (single column), then PD2 and PD3 each split by
material group I / II / IIIa-IIIb.

| Working voltage (V) | PD1 | PD2 I | PD2 II | PD2 IIIa/IIIb | PD3 I | PD3 II | PD3 IIIa/IIIb |
|---|---:|---:|---:|---:|---:|---:|---:|
| <=50 | 0.2 | 0.6 | 0.9 | 1.2 | 1.5 | 1.7 | 1.9 |
| >50 and <=125 | 0.3 | 0.8 | 1.1 | 1.5 | 1.9 | 2.1 | 2.4 |
| >125 and <=250 | 0.6 | 1.3 | 1.8 | **2.5** | 3.2 | 3.6 | **4.0** |
| >250 and <=400 | 1.0 | 2.0 | 2.8 | **4.0** | 5.0 | 5.6 | **6.3** |
| >400 and <=500 | 1.3 | 2.5 | 3.6 | 5.0 | 6.3 | 7.1 | 8.0 |
| >500 and <=800 | 1.8 | 3.2 | 4.5 | 6.3 | 8.0 | 9.0 | 10.0 |
| >800 and <=1000 | 2.4 | 4.0 | 5.6 | 8.0 | 10.0 | 11.0 | 12.5 |

Clause 29.2.3 (CITED-PRIMARY): **"Creepage distances of reinforced insulation
shall be at least double those specified for basic insulation in Table 17."**

Clause 29.2 material groups (CITED-PRIMARY): material group I 600<CTI;
II 400<CTI<600; IIIa 175<CTI<400; IIIb 100<CTI<175.

**Note carefully: IEC 60335-1 merges IIIa and IIIb into a single column.** The
prior evidence docs spent effort on "IIIb is the conservative assumption for
generic FR4 vs IIIa". Under the governing standard that distinction **buys
nothing** — IIIa and IIIb take identical values. Only reaching group II
(CTI>400) or I (CTI>600) changes anything.

### 3.4 Cross-check against IEC 60664-1 (CITED-SECONDARY)

Broadcom/Avago *Regulatory Guide to Isolation Circuits*, §4.5, reproduces
IEC 60664-1's tables. Its Table 4.5.4 (creepage vs working voltage, PD2/PD3,
material group III) gives: 250 V basic 2.5 / reinforced 5.0; 320 V basic 3.2 /
reinforced **6.4**; 400 V basic 4.0 / reinforced **8.0**; 500 V basic 5.0 /
reinforced 10.0. Its PD3 column: 250 V basic 4.0; 400 V basic 6.3.

**Every value agrees with IEC 60335-1 Table 17 above at the corresponding row.**
Two independent sources, one primary and one secondary, in exact agreement —
this is what raises confidence in the OCR'd Table 17 transcription above the
level of a single-source read.

The same section also states the two structural rules explicitly
(CITED-SECONDARY): "Reinforced insulation will have creepage distances that are
twice the value of the voltage specified for basic insulation" (matching clause
29.2.3), and "A creepage distance cannot be less than the associated clearances".

That last one matters: it means the *governing* number for a flat, ungrooved PCB
gap is **max(clearance, creepage) = creepage**, always, on this board.

---

## 4. CLEARANCE — kept strictly separate

Inputs: rated impulse voltage **1 500 V** (§3.1, DERIVED). Peak rated voltage
= 120 x sqrt(2) = **169.7 V** (DERIVED).

Clause 29.1.5 determining voltage `V_det = 1500 + (V_pk_working - 169.7)`:

| Peak working voltage across the barrier | V_det (V) | Basic clearance (Table 16, interpolated) | Reinforced (29.1.3: next higher step) |
|---|---:|---:|---:|
| 170 V (half-bus vs. doubler midpoint) | 1 500 | 0.5 | **1.5** (2 500 step) |
| 340 V (full bus) | 1 670 | ~0.67 | **1.5** (2 500 step) |
| 400 V (`v_bus_abs_max`) | 1 730 | ~0.73 | **1.5** (2 500 step) |
| 1 000 V (resonant tank ring) | 2 330 | ~1.33 | **1.5** (2 500 step) |
| 1 200 V | 2 530 | ~1.53 | **3.0** (4 000 step) |

Clause 29.1's soldered-construction adder (+0.5 mm at rated impulse >=1 500 V)
applies to a soldered PCB by the clause's own example list: **+0.5 mm**.

A stricter reading of 29.1.3 combined with 29.1.5 — take the next tabulated step
above 160% of `V_det` rather than above `V_det` itself, the "intermediate value"
rule IEC 60664-1 states for reinforced — gives 2 672 V at the 340 V case, hence
the 4 000 V step, hence 3.0 mm.

**Reinforced clearance requirement: 1.5 mm nominal, 2.0 mm with the soldering
adder, 3.5 mm under the strictest reading available.** DERIVED from
CITED-PRIMARY inputs.

**Not 4.0 mm. Not 6.4 mm. Not 8.0 mm.**

Consequence: **clearance is not binding anywhere on this board.** The *smallest*
isolator pad gap measured (§6) is C6 at 3.2 mm, which clears 2.0 mm; every other
isolator clears it by 1.75x to 17x. Even the tightest cross-domain pair anywhere
on the board (`C17`<->`R32` at 2.115 mm, from
`docs/evidence/2026-07-28-barrier-constrained-placement.md`) clears the 2.0 mm
figure — marginally, and it would fail the 3.5 mm strict reading.

**Every "isolation" failure on this board is a creepage failure. Not one is a
clearance failure.** That is the fact that makes grooves/slots the right tool.

---

## 5. Pollution degree — the input most likely to move the answer, and it moves it the wrong way

IEC 60335-1 clause 29.2 (CITED-PRIMARY):

> "Pollution degree 2 applies unless: a) precautions have been taken to protect
> the insulation, in which case pollution degree 1 applies; and b) the
> insulation is subjected to conductive pollution, in which case pollution
> degree 3 applies."

**IEC 60335-2-6 clause 29.2 Addition (CITED-PRIMARY — this is the particular
standard for hobs and cooking ranges, and it overrides Part 1's default):**

> "The microenvironment is **pollution degree 3** unless the insulation is
> enclosed or located so that it is unlikely to be exposed to pollution during
> normal use of the appliance."

**This inverts the burden of proof.** `docs/ENVIRONMENTAL_SPEC.md` asserts "PD2 —
Normal household environment" with no justification. Under the appliance's own
particular standard, PD2 is not the default — **PD3 is**, and PD2 must be earned
by showing the PCB is enclosed or located away from cooking pollution. The same
spec's IP20 rating ("No liquid ingress protection guaranteed") argues against
having earned it, and I found no document in this repo specifying the PCB
compartment's sealing (checked `docs/SENSOR_MOUNT_DESIGN.md`,
`docs/COIL_BRACKET_DESIGN.md`, `docs/CONNECTORS_AND_WIRING.md`,
`docs/CHASSIS_AIRFLOW_DESIGN.md`).

Note also that `docs/CHASSIS_AIRFLOW_DESIGN.md` exists at all: a **vented**
compartment with forced airflow past the board is the paradigm case for PD3,
because it pulls the kitchen's grease-laden air across the insulation.

### The Annex J lever — the highest-leverage option, and nobody has mentioned it

IEC 60335-1 clause 29 preamble (CITED-PRIMARY):

> "If coatings are used on printed circuit boards to protect the
> microenvironment (Type A coating) or to provide basic insulation (Type B
> coating), Annex J applies. **The microenvironment is pollution degree 1 under
> Type A coating.** There are no creepage distance or clearance requirements
> under Type B coating."

A qualified Annex J Type A conformal coating drops the microenvironment to
**PD1**, where Table 17's material-group split disappears entirely (single
column) and reinforced creepage at >250-400 V becomes **2 x 1.0 = 2.0 mm**.
Every isolator on this board passes that, including K2/K3 and C6, with margin.

This is a documented provision of the governing standard, not a workaround. It
costs an Annex J qualification (coating process, test coupons, adhesion and
thermal-cycling requirements — **not read this session**) and a manufacturing
step. **It is the option a safety engineer should be asked about first**,
because it is the only one that resolves the requirement without a BOM change,
a re-layout, or a laminate change.

---

## 6. MEASURED — the real isolator geometry, rectangle-aware

Prior analyses used a **bounding-circle** pad model (`radius = max(w,h)/2`),
which charges a long rectangular pad its full length in *every* direction. That
is conservative but not physical: creepage is measured between actual copper
edges.

All eight isolator footprints are rotated by exact multiples of 90 degrees
(`C6` 0, `K1` 0, `K2` 0, `K3` 90, `PS1` 180, `T1` 90, `U3` 0, `U7` 270 —
MEASURED), so a rectangle-aware axis-aligned model is **exact**, not
approximate, on this board.

Script: `measure.py` (scratchpad, not committed — read-only analysis).
Denominators: 168 footprints, 519 pads, 21 HV nets, 33 SELV nets, 8 mixed-domain
components — matching both prior evidence docs exactly.

| Ref | Part | Centre-to-centre (mm) | **Edge-to-edge (mm)** | Prior doc's figure | Delta |
|---|---|---:|---:|---:|---|
| C6 | Y-cap **stub footprint** | 5.000 | **3.200** | 3.200 | same |
| K1 | Omron G4A-1A-E | 9.500 | **8.000** | 5.425 | **+2.575** |
| K2 | Omron G5LE-1 | 6.325 | **3.500** | -0.500 | **+4.000** |
| K3 | Omron G5LE-1 | 6.325 | **3.500** | -0.500 | **+4.000** |
| PS1 | Mean Well IRM-10-15 | 38.500 | **35.500** | 35.500 | same |
| T1 | Coilcraft CST3015-100ED | 13.823 | **9.100** | 7.000 | **+2.100** |
| U3 | H11L1 DIP-6 | 7.620 | **6.020** | 6.020 | same |
| U7 | TI UCC21550BDWK | 9.300 | **7.250** | 7.250 | same |

The four unchanged rows have square/round pads, where circle and rectangle
models agree. The four changed rows have elongated pads (K1's 6.35x1.2 contact
pad, K2/K3's diagonal offset, T1's 4.8x9.0 primary pad) — exactly where the
circle model over-penalises.

### The task's three input figures are measured inconsistently

- `U3` "7.62 mm pad gap" — that is **centre-to-centre**, and equals the 300-mil
  DIP row pitch. The copper-edge gap is **6.02 mm**.
- `U7` "7.25 mm" — that one **is** edge-to-edge.
- `K2/K3` "6.32 mm" — **centre-to-centre**. Edge-to-edge is **3.50 mm**.

Mixing centre-to-centre and edge-to-edge across three parts in one comparison
table is the same class of error as the `U27: 1.27 mm` figure the prior session
debunked. **Creepage is measured between conductive parts, i.e. copper edges**,
so edge-to-edge is the correct measure throughout, and the corrected table above
is what any pass/fail call must use.

### Scope caveat: isolator pad gaps are a lower bound on the problem, not the problem

Creepage is a property of *any* two conductors at different potential, not only
of pads on the same component. **MEASURED: the board carries 96 copper pour
zones on `F.Cu`/`B.Cu`, including pours on HV nets (`ac_l`, `ac_n`, `PWR_RTN`,
`DC_BUS_RTN`, `SW_NODE`) and on SELV nets (`+3V3`, `vcc`, `+15V`) on the same
two layers.** Pour-to-pour and trace-to-pour approaches may well be shorter than
any isolator pad gap — the prior placement doc already reports a
`C17`<->`R32` pair at **2.115 mm** and 11 cross-domain component pairs under
8.0 mm. This section answers the BOM question the task posed ("do these parts
have enough intrinsic separation"); it does **not** establish that the assembled
board meets 8.0 mm anywhere else. Those are two different questions and only the
first is closed here.

---

## 7. The keepout gate measures the wrong thing

`scripts/check_isolation_keepout.py` requires a contiguous zero-copper corridor
**>=8.0 mm wide everywhere**, verified by Shapely negative-buffer erosion, that
partitions the board into exactly two regions.

Corridor width is a **straight-line** quantity. Creepage is a **surface-path**
quantity. A corridor of width W does guarantee creepage >= W across it — so the
gate is *sufficient*. It is not *necessary*: creepage can equally be achieved by
lengthening the path (a groove or slot) without widening the straight-line gap.

Three consequences:

1. **It over-constrains clearance by roughly 4x.** The clearance requirement is
   1.5-2.0 mm (§4). Nothing needs an 8 mm air gap.
2. **It cannot represent the standard's own remedies.** Annex J coating (PD1),
   protective screening via the earthed `In1.Cu` plane (clause 3.4.4 option (a),
   for vertical separation), and grooves are all legitimate, clause-backed ways
   to satisfy the requirement, and the gate can express none of them.
3. **Therefore the CP-SAT INFEASIBLE result does not carry the weight placed on
   it.** It proves that *one particular sufficient condition* is unsatisfiable
   given these footprints. It does not prove the *requirement* is unsatisfiable.
   `docs/evidence/2026-07-28-barrier-constrained-placement.md` states the
   conclusion as "it is a BOM problem"; the supported conclusion is narrower:
   "an 8.0 mm straight-corridor formulation of the barrier is infeasible on
   these footprints."

To be fair to that document: it flagged this tension itself, under UNVERIFIED
("a genuine, reportable tension between component-level certified isolation and
board-level zero-copper keepout enforcement"). It was right to flag it, and it
correctly declined to weaken the gate. The resolution is not to weaken the gate
but to recognise that the gate answers a different, stricter question than the
standard asks.

### Where the creepage path actually runs

For an isolator, the creepage between primary and secondary is
**min(path across the component package, path across the PCB surface)**. A PCB
groove lengthens only the second. This is the correct per-part frame:

| Ref | Package path | PCB path (MEASURED) | Binding path | Groove helps? |
|---|---|---:|---|---|
| U7 | **>8 mm, material group I, CTI>600** — TI SLUSE89C §5.6 (CITED-PRIMARY, fetched by the prior session) | 7.250 | **PCB** | **Yes** — this is exactly the case TI's own footnote warns about ("the mounting pads of the isolator... do not reduce this distance") |
| T1 | ">=8 mm" claimed by Coilcraft; `docs/hardware/IEC60335_CRITICAL_COMPONENTS.md` records **no agency recognition** for it | 9.100 | **Package** | No — PCB already longer |
| U3 | **UNVERIFIED** (3 fetch attempts failed in the prior session; not retried here) | 6.020 | unknown | Only if the package path is adequate |
| K1 | UNVERIFIED (general-purpose relay) | 8.000 | unknown | Marginal — see below |
| K2/K3 | UNVERIFIED (general-purpose relay); COM contact to coil pin across the relay's own base | 3.500 | **almost certainly the package** | **No** — the relay body sits on the board; a slot cannot lengthen a path that runs over the part's own case |
| C6 | A real Y1-rated cap is a **certified component** whose creepage is part of its approval | 3.200 | Package (once sourced) | N/A — footprint is an unsourced 5 mm-pitch **stub** |
| PS1 | Isolating AC/DC module | 35.500 | Package | N/A |

**K2/K3 are the only genuine BOM problem among sourced parts**, and now for a
sharper reason than "the pins are close": the shortest creepage path runs across
the G5LE-1's own plastic base, which no board feature can lengthen. That is a
property of the part.

---

## 8. Pass/fail at 6.5 mm vs 8.0 mm — the question as asked

Using MEASURED edge-to-edge copper gaps (§6), against the candidate creepage
figures:

| Ref | Edge-to-edge | **8.0** (PD2, >250-400 V, IIIa/IIIb) | **6.5** (untraceable) | 5.6 (PD2, >250-400 V, **MG II**) | 5.0 (PD2, <=250 V, IIIa/IIIb) | 12.6 (**PD3**, >250-400 V, IIIa/IIIb) | 2.0 (clearance) |
|---|---:|:--:|:--:|:--:|:--:|:--:|:--:|
| C6 | 3.200 | FAIL | FAIL | FAIL | FAIL | FAIL | PASS |
| K1 | 8.000 | **PASS (0.000 margin)** | PASS | PASS | PASS | FAIL | PASS |
| K2 | 3.500 | FAIL | FAIL | FAIL | FAIL | FAIL | PASS |
| K3 | 3.500 | FAIL | FAIL | FAIL | FAIL | FAIL | PASS |
| PS1 | 35.500 | PASS | PASS | PASS | PASS | PASS | PASS |
| T1 | 9.100 | PASS | PASS | PASS | PASS | FAIL | PASS |
| U3 | 6.020 | FAIL (-1.98) | **FAIL (-0.48)** | PASS | PASS | FAIL | PASS |
| U7 | 7.250 | FAIL (-0.75) | **PASS** | PASS | PASS | FAIL | PASS |

**Direct answers to the question posed:**

- **`U7` passes at 6.5 mm** (7.25 >= 6.5). It fails 8.0 mm by 0.75 mm.
- **`U3` does NOT pass at 6.5 mm.** Its real copper-edge gap is **6.02 mm**, not
  the 7.62 mm centre-to-centre figure in the task's framing — it misses 6.5 mm
  by **0.48 mm**. It fails 8.0 mm by 1.98 mm. It *does* pass at 5.6 mm and 5.0 mm.
- **`K2`/`K3` still fail at 6.5 mm**, by 3.00 mm (3.50 vs 6.5). They fail every
  candidate creepage figure including the most permissive (5.0 mm), and they
  fail 8.0 mm by 4.50 mm — not the 9.0 mm the prior doc's bounding-circle model
  reported.

**Two corrections to the prior BOM conclusion that change the decision:**

- **`T1` (9.100 mm) and `K1` (8.000 mm) pass at 8.0 mm.** The prior doc listed
  both as needing BOM changes (+1.5 mm and +3.1 mm respectively) on the strength
  of bounding-circle figures. They do not. `K1`'s margin is exactly zero,
  however, which is not a pass in practice — it needs land-pattern margin.
- At 8.0 mm the failing set is **C6, K2, K3, U3, U7** — five, not seven. Of
  those, `C6` is an unsourced stub footprint (a sourcing gap, not a part-choice
  gap), and `U3`/`U7` are PCB land-pattern shortfalls of 1.98 mm and 0.75 mm
  against a part whose package is rated >8 mm. **The genuine
  sourced-part BOM exposure is K2 and K3.**

---

## 9. Material group — unspecified, and worth 2x

**MEASURED: the repo specifies no laminate anywhere.** No `(stackup ...)` block
in `pcb/temper.kicad_pcb`; no CTI, IPC-4101 slash sheet, Tg, or laminate part
number in `docs/`, `elec/`, or `pcb/`. The only CTI references in the repo are
for the OVP-01 *resistors* in `elec/domain_manifest.yaml` — a component
property, unrelated to the board substrate.

**The board substrate governs PCB creepage, not the component package.** TI's
Material Group I rating for the UCC21550 (CITED-PRIMARY, SLUSE89C §5.6) applies
to the part's own moulding compound. It bounds the *package* path only. It is
evidence that 8 mm-ish is the right order of magnitude for a reinforced barrier
at this voltage class — and, since Group I is the *least* demanding group, it is
a soft floor, not a ceiling.

What follows from the gap, at working voltage >250-400 V, PD2:

| Material group | CTI | Basic (Table 17) | **Reinforced (x2)** | Which isolators pass |
|---|---|---:|---:|---|
| I | >600 | 2.0 | **4.0** | all but C6 (3.2), K2/K3 (3.5) |
| II | 400-600 | 2.8 | **5.6** | all but C6, K2/K3 |
| **IIIa/IIIb** | 100-400 | 4.0 | **8.0** | K1 (exactly), PS1, T1 |

Two things follow:

1. **The IIIa-vs-IIIb debate in the prior evidence docs is moot** — IEC 60335-1
   Table 17 gives them one shared column. Assuming IIIb "to be conservative"
   bought nothing.
2. **Specifying a CTI>=400 (group II) laminate would cut the requirement from
   8.0 mm to 5.6 mm**, at which `U3` (6.02) and `U7` (7.25) both pass outright
   and the failing set collapses to C6/K2/K3. Whether such laminates are
   available from this project's target fabs (`docs/PCB_DFM_GUIDELINES.md` names
   JLCPCB and PCBWay) at acceptable cost is **ASSUMED / not checked**, and is a
   concrete, cheap thing to go find out.

Until a real laminate datasheet is in hand, **IIIa/IIIb is the correct default**
and 8.0 mm follows from it — so the current figure is the right one to hold, but
for a reason that is a *procurement gap*, not a physical fact.

---

## 10. Slots and grooves

- **A slot or groove increases CREEPAGE only.** Clearance is the shortest
  through-air, line-of-sight path; removing substrate beneath that path does not
  lengthen it. CITED-SECONDARY (TI SLUSE89C §5.6 footnote 1: "Techniques such as
  inserting grooves, ribs, or both on a printed-circuit board are used to help
  increase these specifications") and consistent with
  `docs/PCB_SAFETY_DESIGN_RULES.md` §3.2.
- Since **clearance is not binding anywhere on this board (§4)**, that one-sided
  benefit is exactly the benefit needed. **Every binding constraint on this
  board is creepage, and creepage is the quantity a groove fixes.**
- IEC 60335-1 clause 29.2 Note (CITED-PRIMARY) delegates measurement: "The way
  in which creepage distances are measured is specified in IS 15382 (Part 1)"
  (= IEC 60664-1). **That measurement standard's groove-width rule — the minimum
  width X below which a groove is bridged rather than followed — was NOT read
  this session.** `docs/PCB_SAFETY_DESIGN_RULES.md` §3.2's "Slot width: 1.0 mm
  minimum" remains **UNVERIFIED** against primary text.
- A groove never changes a component's own package path (§7). For `U7` the PCB
  path is the binding one, so a groove is the right fix. For `K2`/`K3` it is not.
- `docs/PCB_SAFETY_DESIGN_RULES.md` §4's claim that solder mask "does not
  contribute to creepage reduction per IEC 60335" is **UNVERIFIED** — but note
  clause 29's Annex J provision (§5) means a *qualified* coating does far more
  than "not contribute": it changes the pollution degree outright. The repo's
  framing understates the standard's own position.

---

## 11. What a human safety engineer must decide

Ordered by how much each moves the number.

1. **Pollution degree — PD2 or PD3.** IEC 60335-2-6 clause 29.2 makes **PD3 the
   default** for this appliance class. PD2 is an exception that must be earned by
   showing the PCB compartment is enclosed or located away from cooking
   pollution. No document in this repo establishes that; `ENVIRONMENTAL_SPEC.md`
   asserts PD2 with an IP20 rating and the repo also contains a chassis
   *airflow* design. **If PD3 stands, the requirement is 12.6 mm and 8.0 mm is
   under-protective** — and no isolator on the board except PS1 passes.
2. **Whether to qualify an Annex J Type A conformal coating.** PD1 under the
   coating => reinforced creepage 2.0 mm => the whole problem dissolves,
   including K2/K3. This is the highest-leverage decision available and it is
   a documented provision of the governing standard.
3. **The working-voltage bracket for Table 17.** <=250 V (row iii) gives 5.0 mm;
   >250-400 V (row iv) gives 8.0 mm; the resonant tank node (`tank-out`, an HV
   net on T1) may sit in row v or vi. The circuit derivation puts the
   doubler-referenced barrier voltage at ~170-200 V but the tank caps are rated
   1000 V+ (`main.ato:310-311`) for a reason. **A per-crossing working voltage
   should be assigned, not one number for the whole barrier.**
4. **Laminate material group.** Unspecified anywhere. Group IIIa/IIIb => 8.0 mm;
   group II => 5.6 mm; group I => 4.0 mm. Worth two millimetres and possibly
   the `U3`/`U7` decision. IIIa vs IIIb is *not* worth arguing about.
5. **Whether `gnd ~ pe` qualifies as protective bonding under clause 27.5
   (<=0.1 ohm).** If not, the PELV classification itself is in question, and
   with it every argument in `domain_manifest.yaml` that leans on the earthed
   reference — including the OVP-01 protective-impedance justification.
6. **Whether to add an earthed inner-layer screen and claim clause 3.4.4 option
   (a) (basic insulation + protective screening) for vertical HV-over-LV
   separation.** A real, clause-backed alternative to reinforced spacing in the
   z-axis. **Entirely unexploited today: MEASURED, both inner layers are empty
   and no `gnd` pour exists anywhere on the board.**
7. **`K2`/`K3` (Omron G5LE-1) replacement or circuit change.** The only genuine
   sourced-part BOM exposure. Their coil-to-contact creepage is a package
   property; no board feature fixes it. Needs either a relay family with
   certified reinforced coil-to-contact isolation, or a topology that keeps the
   discharge function on one side of the barrier.
8. **`C6` sourcing.** Currently a 5 mm-pitch stub footprint, not a part. A real
   Y1-rated safety capacitor is a certified component; its approval, not the
   board gap, carries the isolation. Sourcing gap, not a spacing gap.
9. **`U3` (H11L1) component-level isolation rating.** Still unverified after two
   sessions' fetch attempts. Determines whether a groove alone can qualify it.
10. **`K1` zero-margin pass.** 8.000 mm against an 8.0 mm requirement is
    arithmetically a pass and practically not one. Needs land-pattern margin
    regardless of which figure is adopted.
11. **Groove/slot geometry** — minimum width per IEC 60664-1's measurement rules
    (not read), fab capability, and re-measurement on the real board.
12. **Final sign-off and type testing** (dielectric withstand, and the clause
    29.3 solid-insulation requirements not analysed here) remain a certified
    test lab's responsibility. Nothing in this document substitutes for it.

---

## 12. Sources — exactly what was reached

**Reached and read this session:**

- **IS 302-1:2008, *Safety of household and similar electrical appliances,
  Part 1: General Requirements*** — the Bureau of Indian Standards' identical
  adoption of IEC 60335-1, published under India's Right to Information Act and
  hosted by Public.Resource.Org. Downloaded the item's OCR text layer
  (`is.302.1.2008_djvu.txt`, 312 KB) and read clauses 3.4.1-3.4.4, 27.1, 27.5,
  and 29.1-29.3 including Tables 15, 16 and 17 **directly**, not via a
  summarising model. This is an identical national adoption, so its clause and
  table numbering match IEC 60335-1. **Caveat: it is an OCR'd scan and it is the
  2008 edition** (IEC 60335-1 Ed. 4.2-era); a current edition may renumber or
  revise. Every quotation above was read from the raw text by me.
  <https://archive.org/download/gov.in.is.302.1.2008/is.302.1.2008_djvu.txt>
- **IS 302-2-6:2009** (identical adoption of IEC 60335-2-6, stationary cooking
  ranges/hobs/ovens), same source, `pdftotext`-extracted and read directly.
  Clause 29.2 Addition quoted verbatim in §5.
  <https://law.resource.org/pub/in/bis/S05/is.302.2.6.2009.pdf>
- **Broadcom/Avago, *Regulatory Guide to Isolation Circuits*, §4.5** —
  manufacturer reproduction of IEC 60664-1's Tables (rated impulse voltage,
  minimum clearances basic and reinforced, minimum creepage vs working voltage)
  and of the reinforced-vs-basic rules. `pdftotext`-extracted and read directly.
  Used as the independent cross-check in §3.4.
  <https://docs.broadcom.com/doc/AV02-2041EN>
- **TI UCC21550 datasheet (SLUSE89C) §5.6** — not re-fetched this session;
  quoted from `docs/evidence/2026-07-28-creepage-requirement-determination.md`,
  where the prior session fetched and extracted the PDF directly. Treated as
  CITED-PRIMARY on that basis, with the dependency stated.

**Attempted and failed:**

- `WebSearch`: **budget exhausted (200/200) before this task began**, on the
  first query and every query thereafter — the identical hard constraint the
  prior session hit. Every source above was found by direct-URL reasoning
  without search.
- TI SLYY149 (isolation glossary), Broadcom AN-1074, Wikipedia
  "Creepage distance", CUI/Bel creepage overview, Wurth ANP023, incompliancemag:
  scanned-image PDFs with no text layer, 404, or no tabular content.
- IS 302-1's own PDF from law.resource.org: 80-page scan, no text layer
  (`pdftotext` yields 36 lines). The archive.org OCR sidecar was the way in.

**NOT reached, and not reconstructed:**

- IEC 60335-1's current edition, IEC 60664-1's own primary text, and Annex J's
  qualification requirements. Every figure attributed to IEC 60664-1 above comes
  via the Broadcom secondary source and is labelled as such.
- The IEC 60664-1 groove-width rule governing when a slot counts toward creepage.
- H11L1, Omron G5LE-1, and Omron G4A-1A-E component isolation ratings.
- Whether the laminate a real fab would supply is group IIIa/IIIb or better.

---

## 13. UNVERIFIED

- The Table 17 transcription is from an **OCR'd scan of a 2008 national
  adoption**. It agrees cell-for-cell with the independent IEC 60664-1
  reproduction at every overlapping row (§3.4), which is strong corroboration,
  but neither source is the current IEC 60335-1 text. **A safety engineer must
  read the current edition before sign-off.** Column mapping (PD1 single column;
  PD2 and PD3 each split I / II / IIIa-IIIb) was inferred from the header
  structure and confirmed by the IEC 60664-1 cross-check, not read from a clean
  table image.
- Clause 29.1.3's "next higher step" applied *after* clause 29.1.5's
  determining-voltage arithmetic is my reading; the standard does not spell out
  the interaction. §4 gives both the permissive and strict readings and neither
  changes the conclusion that clearance is non-binding here.
- Whether the +0.5 mm soldered-construction adder is intended for SMD pads on a
  rigid PCB, or only for the wire-terminal constructions the clause's examples
  emphasise. Applied conservatively above.
- Peak working voltage at the `tank-out` node (T1's HV pad) was not derived. If
  the resonant tank exceeds ~1170 V peak, the clearance figure moves up a step.
- No claim here is a compliance determination, and no clause number, table
  number, or table value above is stated except where I read it myself in the
  raw text and can point at the file it came from.

---

## Compliance with the task's hard rules

- **Changed nothing.** No edit to the BOM, `netclass_rules.yaml`, the `8.0`
  constant, `pcb/temper.kicad_pcb`, or any gate. The only file added is this one.
- No `git stash` anywhere.
- No `run_in_background`, no `Monitor`, no waiting on background jobs.
- No additional worktrees, no cargo builds, no large fixtures. The two standards
  PDFs and the analysis script live in the session scratchpad, not the repo.
- Work confined to worktree `agent-affde0c273cebb0ff`.
- Not pushed.
