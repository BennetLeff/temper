<!-- provenance: commit=f8b5f43c dirty=false -->

# Annex J Type A conformal coating as a route to Pollution Degree 1: determination

Base commit: `f8b5f43c` (`docs(solutions): add lesson on fail-soft defaults
masking missing safety inputs`), branch `docs/methodology-loop-discipline`.
Work done in worktree `agent-a4005790622d73862`, reset to that commit.

**This is a determination. It changes nothing.** No BOM, no
`packages/temper-placer/configs/netclass_rules.yaml`, no constant in
`scripts/check_isolation_keepout.py`, no `pcb/temper.kicad_pcb`, no gate. The
only file added is this one.

## Provenance labels

| Label | Meaning |
|---|---|
| **CITED-PRIMARY** | Read by me this session from the standard's own text; source file and URL given in §11. |
| **CITED-SECONDARY** | Read by me this session from a manufacturer document; URL given in §11. |
| **MEASURED** | Computed this session from `pcb/temper.kicad_pcb` / `elec/domain_manifest.yaml`; script named, method described. |
| **DERIVED** | Arithmetic or logic on labelled inputs, shown. |
| **ASSUMED** | Not established. Flagged for a human. |

---

## Verdict up front

**Annex J Type A coating is a PARTIAL route to PD1 on this board, and it does
not reach a single one of the isolation paths that are currently failing.**

Three findings, in descending order of how much they should change the plan.

### 1. The coverage rule is explicit in primary text, and this board fails it everywhere that matters

IEC 60664-3 clause 4.3 (CITED-PRIMARY), which is the standard IEC 60335-1
Annex J delegates to:

> "type 1 protection improves the microenvironment of the parts under the
> protection. The clearance and creepage distance requirements of Part 1 or
> Part 5 for pollution degree 1 apply **under the protection**. Between two
> conductive parts, it is a requirement that one or both conductive parts,
> **together with all the spacings between them, are covered by the
> protection**;"

and, two paragraphs later:

> "Clearance and creepage distance requirements according to Part 1 or Part 5
> apply to **all unprotected parts of the equipment**."

So PD1 is earned *per creepage path*, and only for paths whose **entire**
length is covered. There is no partial credit and no multiplier.

**MEASURED: for all seven of the eight declared mains<->PELV isolators that
have a body outline in their footprint, 100.0% of the shortest HV<->SELV
board-surface path lies underneath the component body.** Not most of it —
all of it, on every one of them.

| Ref | Part | Shortest HV<->SELV copper-edge gap | % of that path under the component body |
|---|---|---:|---:|
| C6 | Y-cap stub footprint (D10 disc, 5 mm pitch) | 3.200 mm | no F.Fab/F.SilkS/F.CrtYd outline in footprint — see §4.3 |
| K2 | Omron G5LE-1 | 3.500 mm | **100.0%** |
| K3 | Omron G5LE-1 | 3.500 mm | **100.0%** |
| U3 | H11L1, DIP-6 300 mil | 6.020 mm | **100.0%** |
| U7 | TI UCC21550, SOIC-16W | 7.250 mm | **100.0%** |
| K1 | Omron G4A-1A-E | 8.000 mm | **100.0%** |
| T1 | Coilcraft CST3015 | 9.100 mm | **100.0%** |
| PS1 | Mean Well IRM-10-15 | 35.500 mm | **100.0%** |

(Gaps agree to the millimetre with
`docs/evidence/2026-07-28-creepage-determination-brainstorm.md` §6, which
measured them independently with a different script. Method and script in §4.)

A conformal coating applied to a populated board after reflow/wave does not
reach the board surface beneath a seated component body, and — decisively —
**cannot be shown to have reached it**. §7 covers why "cannot be shown" is
the operative half of that sentence.

### 2. Coating and the K2/K3 relay replacement are NOT alternatives. Both are needed.

The task asked me to say this plainly if I found it, and I found it.

K2/K3's shortest mains<->PELV path is **3.500 mm from pad 1 (COM, on `PWR_RTN`
/ `DC_BUS_RTN`) to pad 2 (coil1, SELV)** — MEASURED. The G5LE-1's F.Fab body
outline spans local x[-8.25, 8.25], y[-2.55, 19.95] mm; both pads and the
entire straight path between them sit inside it. The relay's plastic base is
seated on the board over that path. A post-assembly coating does not get
there.

Worse, the relay is worse than "not helped". **CITED-PRIMARY, Omron G5LE
datasheet: the G5LE gives no creepage or clearance figure at all between coil
and contacts, and its coil-to-contact dielectric strength is 2,000 VAC for
1 min.** IS 302-1:2008 Table 7 (clause 16.3) requires, for **reinforced**
insulation, **2,500 V** at the most permissive applicable column (rated
voltage <=150 V) and **3,000 V** for working voltage >150–250 V, rising to
`2.4U + 2400` above 250 V — CITED-PRIMARY. The part is under the requirement
on electric strength before pollution degree is even discussed, and pollution
degree has no bearing on an electric-strength test.

So: **the relay swap in `docs/evidence/2026-07-28-discharge-relay-isolation.md`
is required on its own merits and coating does not substitute for it.** Any
earlier framing that presented coating and the relay replacement as competing
options was wrong.

### 3. Even a perfectly-qualified Type A coating does not make this board compliant

**MEASURED, board-wide:** 97 HV pads and 221 SELV pads (denominators matching
`docs/evidence/2026-07-28-isolation-keepout.md` exactly). 222 cross-domain pad
pairs sit closer than 12.6 mm edge-to-edge. **Four of them are closer than
2.0 mm** — the reinforced creepage requirement *at PD1*:

| Gap | Pair | HV net | SELV net | Path crosses a body bbox? |
|---:|---|---|---|---|
| **0.905 mm** | `C17.2` <-> `R32.1` | `hb.gate_hs.driver-p2` | `+3V3` | no — coatable |
| **1.100 mm** | `R30.2` <-> `R1.1` | `tank-out` | `+15V` | yes (`R1`, axial body — see caveat §4.4) |
| **1.124 mm** | `R30.1` <-> `R1.1` | `tank.c_tank1-p2` | `+15V` | yes (`R1`) |
| **1.148 mm** | `R30.1` <-> `R1.2` | `tank.c_tank1-p2` | `power_in.bypass_relay-coil1` | yes (`R1`) |

`R30` is `tank.inductor_conn`, an 8 x 8 mm `LitzPad_15A` carrying the resonant
tank output. It sits **1.100 mm** from a +15 V SELV pad. That is a defect no
pollution degree fixes.

**DERIVED: PD1 would take the sub-requirement failing set from 68 pad pairs
(at 8.0 mm) to 4 pairs (at 2.0 mm) — a large improvement, and still not zero.**

---

## 1. What Annex J actually is

**Annex J of IEC 60335-1 is nine lines long and contains no substantive
requirements of its own.** It is a pointer with five modifications.
CITED-PRIMARY, read verbatim from IS 302-1:2008 (identical adoption), the
whole annex:

> **ANNEX J** *(Clause 29)* — **COATED PRINTED CIRCUIT BOARDS**
>
> The testing of protective coatings of printed circuit boards is carried out
> in accordance with IS 15382 (Part 3) with the following modifications.
>
> **6.6 Climatic Sequence** — When production samples are used, three samples
> of the printed circuit board are tested.
> **6.6.1 Cold** — The test is carried out at −25 °C.
> **6.6.3 Rapid Change of Temperature** — Severity 1 is specified.
> **6.8.6 Partial Discharge Extinction Voltage** — Type A coatings are not
> subjected to a partial discharge test.
> NOTE — Partial discharges do not normally occur at voltages lower than
> 700 V peak.
> **6.9 Additional Tests** — This sub-clause is not applicable.

`IS 15382 (Part 3)` is named in IS 302-1's own normative-references list as
"*Insulation coordination for equipment within low-voltage systems: Part 3 —
Use of coatings to achieve insulation coordination of printed board
assemblies*" (CITED-PRIMARY). The document itself is
**IS 15382 (Part 3):2006, identical with IEC 60664-3:2003** — stated on its
title page (CITED-PRIMARY).

The enabling sentence lives in clause 29's preamble, not in Annex J
(CITED-PRIMARY, IS 302-1 cl. 29):

> "If coatings are used on printed circuit boards to protect the
> microenvironment (Type A coating) or to provide basic insulation (Type B
> coating), Annex J applies. **The microenvironment is pollution degree 1
> under Type A coating.** There are no creepage distance or clearance
> requirements under Type B coating."

### 1.1 A numbering discrepancy, reported rather than smoothed over

Annex J cites **6.6 / 6.6.1 / 6.6.3 / 6.8.6 / 6.9**. IEC 60664-3:2003's
corresponding subclauses are **5.7 (Conditioning; its own NOTE calls
5.7.1–5.7.4 "the climatic sequence") / 5.7.1 (Cold) / 5.7.3 (Rapid change of
temperature) / 5.8.5 (Partial discharge extinction voltage) / 5.9 (Additional
tests)** — CITED-PRIMARY, all read this session. The subject matter maps
one-to-one and the modifications make sense against the 2003 text; the clause
*numbers* do not. **DERIVED: IS 302-1:2008 (IEC 60335-1 Ed. 4.2-era) is citing
an earlier edition of IEC 60664-3, in which the test clause was numbered 6.**
I did not obtain that earlier edition, and I did not obtain the current
IEC 60335-1 (Ed. 5.2:2016) Annex J to see whether it was renumbered.
**A safety engineer must read the current Annex J against the current
IEC 60664-3 before relying on any subclause number quoted here.** The
*substance* below is quoted from IEC 60664-3:2003 itself and does not depend
on the numbering.

### 1.2 Type A / Type B vs type 1 / type 2

IEC 60335-1 says "Type A coating" and "Type B coating". IEC 60664-3 says
"type 1 protection" and "type 2 protection". The definitions align exactly:

| IEC 60664-3 cl. 1 and 4.3 (CITED-PRIMARY) | IEC 60335-1 cl. 29 (CITED-PRIMARY) |
|---|---|
| "type 1 protection improves the microenvironment of the parts under the protection" | "Type A coating … to protect the microenvironment … The microenvironment is pollution degree 1 under Type A coating" |
| "type 2 protection is considered to be similar to solid insulation" | "Type B coating … to provide basic insulation … no creepage distance or clearance requirements under Type B coating" |

**DERIVED: Type A == type 1, Type B == type 2.** Everything below about
"type 1" is the Type A route.

---

## 2. What Type A / type 1 protection actually requires

All CITED-PRIMARY from IS 15382 (Part 3):2006 = IEC 60664-3:2003, read this
session.

### 2.1 Design requirements (clause 4)

- **cl. 4.1** — "When type 1 protection is used, dimensioning of clearances
  and creepage distances shall follow the requirements of Part 1 or Part 5.
  If the requirements of this standard are met, pollution degree 1 applies
  under the protection."
- **cl. 4.3 coverage rule** — quoted in full in the Verdict. One or both
  conductive parts *and all the spacings between them* must be covered.
- **cl. 4.3, final paragraph** — "Clearance and creepage distance requirements
  according to Part 1 or Part 5 apply to all unprotected parts of the
  equipment."
- **cl. 4.2** — "Stresses such as temperature, chemical, mechanical … shall be
  taken into account when the protective material is selected. Absorption of
  humidity by the protective material shall not impair the insulation
  properties of the parts being protected."
- **cl. 1 Scope, two sentences that matter here** — "This standard refers only
  to **permanent** protection. It does **not cover assemblies that are
  subjected to mechanical adjustment or repair**." And: "The principles of
  this standard are applicable to functional, basic, supplementary and
  reinforced insulation" — so the route is available for the reinforced
  barrier this board needs.
- **No coating material class, no chemistry, and no minimum thickness is
  specified anywhere in the standard.** The requirement is entirely a
  *performance* requirement, proven by the clause-5 test regime on a coupon
  built with the production materials and process. The repo's
  `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` §6.4 figure of "25–75 µm" is a
  vendor process window, not a standards requirement (it matches Electrolube's
  own TDS wording — CITED-SECONDARY, §11).

### 2.2 Test regime (clause 5), with Annex J's modifications applied

**Six specimens** (cl. 5.1), reduced to **three** if production samples are
used (Annex J's modification of "6.6"). **No failure of any specimen under
test is permitted** (cl. 5.1). The sequence is normative (Annex A).

| Step | Requirement | Annex J modification |
|---|---|---|
| cl. 5.2 / Annex C | Coupon per Annex C, or production specimens. Coupon "shall have the **same minimum distances as those from production**" — 10 pairs of 100 mm parallel conductors, 5 at the minimum production spacing and 5 at the highest-stress production spacing; 84 lands in 6 groups. | — |
| cl. 5.4 | "Printed boards shall be cleaned and coated using the normal procedure of the manufacturer. **The soldering procedure is carried out but without components being in place.**" | — |
| cl. 5.5 | Scratch resistance: 5 scratches across conductor pairs, hardened steel pin, 40° cone, 0.25 ± 0.02 mm tip radius, **10 ± 0.5 N** axial force, ~20 mm/s. | — |
| cl. 5.6 | Visual examination per test 1b of IEC 60326-2. Failure on: blistering, swelling, separation from base material, cracks, voids, **"areas with adjacent unprotected conductive parts, with the exception of lands"**, electromigration. | — |
| cl. 5.7.1 | Cold, IEC 60068-2-1 test Ab, 96 h, severity from {−10, −25, −40, −65 °C}. | **−25 °C fixed.** |
| cl. 5.7.2 | Dry heat, IEC 60068-2-2 test Bb, per **Table 2**, keyed to base material *and declared maximum working surface temperature*. Epoxide/woven glass (FR-4): 140 °C -> **175 °C for 1000 h**; 100 °C -> **125 °C for 1000 h**; 75 °C -> **95 °C for 1000 h**. | — |
| cl. 5.7.3 | Rapid change of temperature, IEC 60068-2-14 test Na, Table 3 severities; 1 h cycle (30 ± 2 min at each extreme), transition within 30 s, **5 cycles**. | **Severity 1 = −10 °C / +125 °C.** |
| cl. 5.7.4.1 | Damp heat with polarising voltage: **40 ± 2 °C, 93% RH, 96 h, 100 V DC applied between conductors and adjacent lands.** | — |
| cl. 5.7.4.2 | Optional longer electromigration soak (10 / 21 / 56 days). | — |
| cl. 5.8.2 | **Adhesion (tape test)**: IEC 60454-3-1 pressure-sensitive tape >=13 mm wide, 50 mm length applied, removed by snap pull within 10 s. "After the test the coating shall not have loosened and there shall be no material transferred to the tape that is visible to the naked eye." | — |
| cl. 5.8.3 | Insulation resistance between conductors, **>=100 MΩ**. | — |
| cl. 5.8.4 | AC withstand voltage per Part 1 cl. 4.1.2.3; test voltage is the higher of Part 1 cl. 3.3.3.2.2's value or **0.707 x rated impulse voltage**. **Reinforced insulation is tested at twice the basic voltage.** And: "**If the assembly is subjected to pollution degree 3 or 4, the withstand voltage test shall be carried out with a conductive layer on the surface of the protection to simulate the pollution degree.**" | — |
| cl. 5.8.5 | Partial discharge extinction voltage. | **Not applicable to Type A.** (IEC 60664-3:2003 already restricts it to type 2 on its own.) |
| cl. 5.9 | Additional tests: solder heat, flammability, solvent resistance. | **"This sub-clause is not applicable."** |

Two of these deserve emphasis for this project specifically.

**(a) The cl. 5.8.4 conductive-layer variant applies here.** IEC 60335-2-6
cl. 29.2 Addition (CITED-PRIMARY, read this session from IS 302-2-6:2009)
makes PD3 the *macroenvironment* default for this appliance class. The
assembly is therefore "subjected to pollution degree 3", so the withstand test
must be run with a **conductive layer laid on top of the coating**. That is the
hard variant of the test and it is not optional.

**(b) The coupon is a bare board.** cl. 5.4's "without components being in
place" means the clause-5 regime qualifies the *coating system* — laminate +
coating chemistry + cleaning + solder process — and says **nothing whatsoever
about whether coating reached under a relay on the real assembly**. Coverage
under bodies is a **clause 4.3 design requirement**, and clause 5 does not test
it. That gap is the whole story of §4.

---

## 3. Does it yield PD1, and over what?

**Yes, and only over what it covers.** Three consequences, all DERIVED from
the clauses quoted above.

1. **PD1 applies path-by-path, not board-by-board.** A "PD1 board" is not a
   thing the standard recognises. Each creepage path is separately either
   fully covered (PD1) or not (whatever the microenvironment is).
2. **For paths this board does not cover, the requirement is 12.6 mm, not
   8.0 mm.** IEC 60335-2-6 cl. 29.2's PD3 default governs uncovered paths
   unless the PCB compartment's enclosure is separately argued.
   IS 302-1 Table 17 row iv (>250 and <=400 V), PD3, material group IIIa/IIIb
   = 6.3 mm basic; cl. 29.2.3 doubles it for reinforced = **12.6 mm**
   (CITED-PRIMARY, Table 17 read from raw text by me this session; PD1 column
   row iv = 1.0 mm, so reinforced at PD1 = **2.0 mm**).
   **Coating therefore has 6.3x leverage where it applies and zero where it
   does not — and this board's failing paths are all in the second category.**
3. **Clearance does not go away.** IS 302-1 Annex L, L-2 (CITED-PRIMARY):
   "For pollution degree 1, the reduced clearance based on the impulse voltage
   test can be used. However, the creepage distance can not be less than the
   values of Table 17." And cl. 29.2.1: "Except for pollution degree 1, if the
   test of 14 has been used to check a particular clearance, the corresponding
   creepage distance shall not be less than the minimum dimension specified for
   the clearance of Table 16." So PD1 relaxes the *interaction*, not the
   clearance requirement itself. The prior determination's clearance figure
   (1.5 mm nominal / 2.0 mm with the cl. 29.1 soldered-construction adder)
   stands unchanged.

### 3.1 There is no "creepage multiplier"

`docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` §6.4 states:

> **Creepage Multiplier:** ×1.5 for coated surfaces

**No such provision exists in IEC 60335-1 or IEC 60664-3.** I read both
clause 29 and the whole of IEC 60664-3 this session; the mechanism is a
binary change of pollution degree under qualified protection, not a scaling
factor on the distance. A ×1.5 multiplier is *less* generous than the real
provision at PD2 (8.0 -> 5.33 vs 8.0 -> 2.0) and *far* more generous than the
real provision where coverage fails (no reduction at all). It is wrong in both
directions and it appears in a document marked "Status: Implemented".

---

## 4. The coverage problem, measured

This is the crux the task flagged, and it is decisive.

### 4.1 Method

Script `coverage2.py` / `boardwide.py` (session scratchpad, not committed —
read-only analysis, matching the precedent of the sibling evidence docs).

1. Load `elec/domain_manifest.yaml`'s `domains.HV.nets` (21) and
   `domains.SELV.nets` (33); classify every pad by exact net-name set
   membership, never substring match.
2. Parse `pcb/temper.kicad_pcb` with `kiutils.board.Board` — the same library
   `resync_pcb_netlist.py` and `check_copper_net_consistency.py` use.
3. Model each pad as an **axis-aligned rectangle** in absolute board
   coordinates. All eight isolator footprints are rotated by exact multiples
   of 90°, so this is exact, not approximate, for them (independently
   re-confirmed this session: C6 0°, K1 0°, K2 0°, K3 90°, PS1 180°, T1 90°,
   U3 0°, U7 270°).
4. Take each footprint's **component body outline** as the bounding box of its
   `F.Fab` graphics, falling back to `F.SilkS` then `F.CrtYd`, excluding
   `fp_text`. `F.Fab` is the mechanical body outline in KiCad convention.
5. Sample the straight segment between the two closest pad rectangles at 400
   or 2000 points and count the fraction lying inside a body box.

Denominators: **168 footprints, 97 HV pads, 221 SELV pads, 161 footprints with
a usable body outline.** The 97/221 figures match
`docs/evidence/2026-07-28-isolation-keepout.md` exactly, and all eight isolator
gaps match `2026-07-28-creepage-determination-brainstorm.md` §6 to three
decimal places — two independent scripts, same answer.

### 4.2 Result for the declared isolators

Every isolator: **100.0% of the shortest path under the body.** The reason is
structural, not accidental, and it is worth spelling out per package class.

- **SOIC-16 wide (`U7`, TI UCC21550).** Pads at local x = ±4.65 mm, 2.05 mm
  wide, so pad inner edges at ∓3.625 mm. `F.Fab` body spans x[−3.75, +3.75].
  **The entire 7.250 mm inter-row gap lies inside the package body outline,
  and the pads themselves tuck 0.125 mm under it.** MEASURED. This is exactly
  the geometry TI's own layout note warns about, and it is why a **routed slot**
  is the correct remedy for `U7` — a slot is a board feature and reaches under
  the body; a coating is a surface film and does not.
- **THT relay (`K2`/`K3`, Omron G5LE-1).** Pads are `thru_hole` with
  `(layers *.Cu *.Mask)`, so copper exists on the top *and* bottom annular
  rings. There are therefore two geometrically identical 3.500 mm paths, one
  on each face. The **bottom** one is over open board and is coatable; the
  **top** one runs under the relay's seated plastic base and is not. Creepage
  is the minimum over all surface paths, so coating the bottom face buys
  nothing: min(3.500 coated, 3.500 uncoated) is still an uncoated 3.500 mm.
  **DERIVED.** The same argument applies to `U3` (DIP-6), `C6`, and `PS1`.
- **THT relay with SMD contact tabs (`K1`, Omron G4A-1A-E).** The 8.000 mm
  governing pair is `pad 13` (a 6.35 x 1.2 mm `F.Cu`-only Faston landing pad,
  HV) to `pad A1` (a thru-hole coil pin, SELV). The straight path between them
  is 100% inside K1's 30.50 x 23.50 mm silkscreen body outline.

### 4.3 `C6` — the one gap in the measurement

`C6`'s footprint (`C_Disc_D10.0mm_W5.0mm_P5.00mm`) carries no `F.Fab`,
`F.SilkS`, or `F.CrtYd` graphics at all, so the under-body test returns no
answer for it. **NOT MEASURED.** `C6` is in any case an unsourced 5 mm-pitch
stub footprint, not a part; a real Y1-rated safety capacitor is a certified
component whose isolation is carried by its own approval, and the disc body of
a D10 part would span the 3.200 mm pad gap several times over. Treat it as a
sourcing gap, unchanged by this determination.

### 4.4 Board-wide, and the honest limits of the body-box proxy

| Threshold | Cross-domain pad pairs below it | Of which the path crosses >=1 body box |
|---|---:|---:|
| 2.0 mm (reinforced @ **PD1**) | **4** | 3 |
| 5.0 mm | 23 | 9 |
| 5.6 mm | 27 | 12 |
| 8.0 mm (reinforced @ PD2, MG IIIa/IIIb) | 68 | 39 |
| 12.6 mm (reinforced @ **PD3**, MG IIIa/IIIb) | 222 | 106 |

MEASURED. **Two caveats, both of which cut against over-reading this table:**

1. **The body box is a rectangular bounding box, which over-flags.** `R1` is
   an axial `DIN0207` resistor whose body is held above the board on leads; a
   spray or dip coating plausibly does reach under it. The three `R30`<->`R1`
   pairs are therefore probably coatable in reality. They are also all
   **below 2.0 mm**, so they fail at PD1 regardless and the caveat does not
   rescue them. For seated bodies (SOIC, DIP, relay, module) the proxy is
   sound.
2. **Pad-to-pad is a lower bound on the problem, not the problem.** The board
   carries 96 copper pour zones, all on `F.Cu`/`B.Cu`, including pours on both
   HV and SELV nets (established in
   `2026-07-28-creepage-determination-brainstorm.md` §6, not re-measured here).
   Pour-to-pour and trace-to-pour approaches may be shorter than any pad pair.
   Nothing here establishes that the assembled board meets any figure.

**Where coating genuinely does help:** 116 of the 222 sub-12.6 mm pairs have a
path crossing no body at all. Those are open-surface trace/pad approaches
between discrete parts — for those, a qualified Type A coating is a real and
clause-backed remedy, and it is the only remedy that does not require moving
components. That is not nothing. It is just not the failing set.

---

## 5. Thermal and environmental survivability

### 5.1 The declared environment is itself undefended — and is now load-bearing twice

`docs/ENVIRONMENTAL_SPEC.md:45` asserts:

> | **Pollution Degree** | PD2 | Normal household environment. Temporary conductivity caused by condensation is to be expected. |

with **no clause citation and no justification**, immediately below an IP20
row that reads "No liquid ingress protection guaranteed". Under
IEC 60335-2-6 cl. 29.2 (CITED-PRIMARY) **PD3 is the default for this appliance
class**; PD2 must be *earned* by showing the insulation "is enclosed or located
so that it is unlikely to be exposed to pollution during normal use". No
document in this repo establishes that, and `docs/CHASSIS_AIRFLOW_DESIGN.md`
describes forced airflow through the compartment, which argues the other way.

This now matters twice over, because it sets both the requirement for
uncovered paths (12.6 mm) *and* the severity of the coating qualification
test (cl. 5.8.4's conductive-layer variant, §2.2(a)).

The spec's `-20 °C` storage minimum is also below Annex J's fixed **−25 °C**
cold conditioning, so the coating qualification is stricter than the product's
own declared storage floor. That is fine — it just means the spec cannot be
used to argue the conditioning down.

### 5.2 The temperature the coating must survive

The governing input is IEC 60664-3 Table 2 (CITED-PRIMARY), which keys the
**1000 h dry-heat conditioning** to the base material and to the **declared
maximum working surface temperature of the printed board**:

| Base material | Max working surface temp | Conditioning temp | Time |
|---|---:|---:|---:|
| Epoxide/woven glass (FR-4) | 140 °C | 175 °C | 1000 h |
| Epoxide/woven glass | 100 °C | **125 °C** | 1000 h |
| Epoxide/woven glass | 75 °C | 95 °C | 1000 h |

plus Annex J's fixed **Severity 1 rapid change of temperature: −10 °C to
+125 °C, 5 cycles, 30 min dwell, 30 s transition** (Table 3, CITED-PRIMARY).

**The repo has never declared a maximum PCB working surface temperature.**
`docs/hardware/SYSTEM_THERMAL_BUDGET.md` gives component temperatures — IGBT
Tj to 109–150 °C, heatsink case to 89 °C at 70 °C ambient, work coil 90–120 °C
with a 130 °C Class-B insulation limit, LMR51430 Tj to 150 °C at 70 °C ambient
— but no board-surface figure. MEASURED (grep of the whole doc). **This is a
required input for Annex J qualification that does not exist yet**, and given
TO-247 devices and a coil dissipating tens of watts nearby, the honest
expectation is that a 75 °C declaration will not survive measurement, putting
this at the **125 °C / 1000 h** row or worse.

### 5.3 Whether common chemistries clear that bar

CITED-SECONDARY, MG Chemicals *Conformal Coatings* category data sheet
v2.0 (19 Dec 2025), fetched and read this session:

| Product | Binder | Constant service temp | Tg | IPC-CC-830 |
|---|---|---|---:|---|
| 419D | Acrylic | −65 to **125 °C** | 27 °C | B revision |
| 419E | Acrylic | −65 to **130 °C** | 38 °C | C revision |
| 422B / 422C | Silicone-modified acrylic | −40 to **200 °C** | 29 / 31 °C | — |
| 4223F | Polyurethane | −65 to **125 °C** | 57 °C | B revision |
| 4200UV | Urethane acrylate | −65 to **150 °C** | 72 °C | C revision |

CITED-SECONDARY, Electrolube HPA (MacDermid Alpha TDS, 19 Jul 2024): operating
temperature range **−55 to 130 °C**, "IPC-CC-830 — Meets Approval".

**DERIVED:**

- **Plain acrylic and plain polyurethane are marginal.** A 125 °C constant
  service rating against a 1000 h / 125 °C conditioning is zero margin, and
  1000 h continuous at the rating is not the same duty the rating contemplates.
  These would need to be qualified at the 95 °C row, which requires the board
  to demonstrate a <=75 °C maximum working surface temperature.
- **Silicone (or silicone-modified acrylic) has real headroom** — 200 °C
  against 175 °C worst case — and is the chemistry the thermal environment
  points at. It is also the worst on solderability ("Fair") and the hardest to
  rework.
- **Every one of these has a Tg between 27 °C and 72 °C, i.e. at or below
  normal operating temperature.** Above Tg the coating is in its rubbery state
  with a large CTE (72–275 ppm/°C in the table above) against FR-4's ~15 ppm/°C
  in-plane. Adhesion and the cl. 5.8.2 tape test are exactly what the
  1000 h dry heat plus 5 thermal-shock cycles are there to probe, and this is
  the most likely place for a real qualification to fail.
- **Parylene: NOT VERIFIED.** I fetched no parylene datasheet and will not
  state a temperature figure for it from memory. Its relevance is real —
  vapour-deposited parylene is the one chemistry that genuinely penetrates
  under component bodies, which is precisely the failure mode in §4 — so it is
  worth a human investigating. It is also a substantially different and more
  expensive process (vacuum chamber, masking is harder, rework is worse), and
  nothing in this repo contemplates it.
- **IPC-CC-830 qualification is not IEC 60664-3 qualification.** Neither
  vendor document mentions IEC 60664-3 at all (grepped both). They are
  different test regimes with different specimens and different acceptance
  criteria. `HIGH_VOLTAGE_CLEARANCE_SPEC.md` §6.4 cites IPC-CC-830 as the
  coating standard; **that citation does not discharge Annex J.**

---

## 6. Process consequences

### 6.1 Non-sealed relays: the G5LE-1 cannot be coated as specified

**CITED-PRIMARY, Omron G5LE datasheet, Model Number Legend, field 3
"Enclosure rating":**

> None: Flux protection
> 4: Fully sealed

The repo specifies **`G5LE-1 DC12`** (`elec/src/components.ato:312-332`,
`elec/domain_manifest.yaml`) — field 3 empty, i.e. **flux protection, not
sealed**. The fully-sealed variant is `G5LE-14`. A flux-protected relay has a
vent path; liquid coating and the solvent cleaning that precedes it (cl. 5.4
requires "cleaned and coated using the normal procedure of the manufacturer")
can enter the case and contaminate the contacts. **A coating process on this
board would require either masking K2/K3 entirely — which is exactly the region
that needs the PD1 credit and cannot get it — or switching to sealed relays.**

`K1` (Omron G4A-1A-E) has the same question and I did not check its datasheet
this session. **NOT VERIFIED.**

This is a second, independent reason the relay BOM change and the coating
decision are entangled rather than alternative.

### 6.2 Masking inventory

MEASURED from `pcb/temper.kicad_pcb` (script `masking.py`), features a coating
process must mask:

| Class | Count | Refs |
|---|---:|---|
| Relays (vent / seated body) | 3 | `K1`, `K2`, `K3` |
| Test points | 3 | `TP1`, `TP2`, `TP3` |
| TO-247 tab + heatsink interface | 2 | `U5`, `U6` |
| Fuse holder (5x20 mm clips) | 1 | `F1` |
| Pin header | 1 | `J1` |

Plus, not caught by the reference-prefix heuristic: **`K1`'s two 6.35 x 1.2 mm
Faston landing pads** (`pad 13` / `pad 14`, mains-carrying quick-connect tabs)
and **`R30`'s two 8 x 8 mm `LitzPad_15A` pads** (the work-coil connection).
Both are bare-metal wire-attachment surfaces that must not be coated and are
adjacent to the tightest cross-domain gaps on the board (§Verdict item 3).

**A documentation drift worth flagging in passing:** `docs/CONNECTORS_AND_WIRING.md`
lists **eight** connectors (`J_IN`, `J_COIL`, `J_RTD1`, `J_RTD2`, `J_FAN`,
`J_PROG`, `J_UI`, `J_DEBUG`), of which the board carries **one** (`J1`, a
1x02 header). The RTD probe interface the task asked about (`J_RTD1`,
JST B4B-XH-A) **does not exist on this board yet**. Its masking requirement is
therefore not assessable, and it will be a new masking obligation when added.
MEASURED.

### 6.3 Rework and repair

Straight from primary text, IEC 60664-3 cl. 1 (CITED-PRIMARY):

> "This standard refers only to permanent protection. **It does not cover
> assemblies that are subjected to mechanical adjustment or repair.**"

**DERIVED: once the PD1 claim rests on the coating, any rework that breaches
it voids the claim for the paths it covered, and the standard offers no
touch-up provision.** A repaired board is outside IEC 60664-3's scope. For a
development board on which parts are still being swapped, this is a serious
practical cost — every rework cycle invalidates the safety argument until the
board is re-coated and (per the coupon regime) arguably re-qualified.

Note also cl. 5.9.1's solder-heat test and cl. 5.9.3's solvent-resistance test
are exactly the ones **Annex J switches off** ("6.9 Additional Tests — This
sub-clause is not applicable"). So under IEC 60335-1 there is *no* qualified
evidence that the coating survives a soldering iron or a solvent wipe. That is
not an oversight to route around; it is the standard declining to certify
rework.

### 6.4 Inspection and QA — the argument that cannot be made

The task's framing is right: *a coating that cannot be verified in production
is not a compliance argument*. Two specific problems here.

1. **cl. 5.6's visual examination lists "areas with adjacent unprotected
   conductive parts" as a failure criterion** — but it is performed on the
   **bare coupon** (cl. 5.4: "without components being in place"). There is no
   test in clause 5 that inspects coverage on a populated assembly.
2. **Coverage under a seated component body is not visually inspectable, by
   construction.** UV-tracer inspection — the standard production QA for
   conformal coating — works by looking at the surface. It cannot see under a
   relay base or a SOIC body. So the cl. 4.3 coverage requirement for exactly
   the paths that matter on this board is **unverifiable by the normal
   process**, which means it cannot be asserted in a compliance file.

**DERIVED: a Type A claim on this board would have to be scoped to paths that
are visually confirmable, i.e. open-surface paths, and explicitly exclude
every under-body path.** That is a defensible, honest claim. It is also
exactly the claim that does not help.

---

## 7. What this would change in the repo

**Nothing was changed. This is what a human would have to change, and in what
order.**

### 7.1 Two places that already assume coating, with no qualification behind them

This is the most urgent finding in this section, and it corrects the prior
determination's statement that "no prior doc mentions it".

- **`scripts/generate_kicad_dru.py:47`** emits, into the generated KiCad
  design-rules file consumed by DRC:
  > `# IMPORTANT: This board REQUIRES conformal coating for safety!`
  > `# Without coating, TO-247 packages violate IEC 60664-1 clearances.`

  and at line 149, on the "HV internal same footprint" rule (1.5 mm):
  > `# WARNING: This violates IEC 60664-1 PD2 (needs 2.0mm for 400V)`
  > `# REQUIRES: Conformal coating to achieve PD1 (needs 0.8mm for 400V)`

  **The board's DRC constraints are already relaxed on the strength of a
  coating that has never been specified, sourced, or qualified.** This is the
  `fail-soft defaults masking missing safety inputs` pattern the base commit
  itself documents, appearing in a generated artifact. The `0.8 mm` figure is
  also untraceable: IS 302-1 Table 17's PD1 column at row iv (>250–400 V) is
  **1.0 mm** basic, and no PD1 cell in that table equals 0.8.
- **`docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` §6.4** (Status: "Implemented")
  specifies coating type "Silicone or Acrylic (IPC-CC-830)", 25–75 µm, and a
  "**Creepage Multiplier: ×1.5 for coated surfaces**" — a mechanism that does
  not exist (§3.1), and a standard (IPC-CC-830) that is not the one Annex J
  requires (§5.3).

**Neither of these is a coating decision. Both are coating *assumptions*
already load-bearing in the design.** They should be resolved before anything
else in this section.

### 7.2 If a scoped Type A claim were adopted

- **`docs/ENVIRONMENTAL_SPEC.md:45`** — the PD2/IP20 row cannot stand as
  written whatever happens. It needs to become an explicit three-way statement:
  PD3 macroenvironment per IEC 60335-2-6 cl. 29.2; PD1 under qualified Type A
  coating on named, inspectable paths; PD3 everywhere else. Plus a declared
  **maximum PCB working surface temperature**, which selects the IEC 60664-3
  Table 2 conditioning row and does not exist today.
- **`packages/temper-placer/configs/netclass_rules.yaml`** — the nine
  `ACMains-*` / `HighVoltage-*` `class_pairs` all carry
  `clearance: 6.0, because: "IEC 60335-1 Table 16 working isolation at 400V"`,
  and the `ACMains` and `HighVoltage` classes each additionally carry
  `creepage_mm: 6.0` under the same `because:` string — so **one number and one
  citation are doing duty as both the clearance and the creepage figure**, which
  is the exact confusion the prior determination catalogued.
  That attribution is wrong independently of this determination (Table 16 is
  indexed by rated impulse voltage; 400 V is not one of its rows; 6.0 is not
  one of its values — established in the prior brainstorm and re-confirmed
  against the raw table this session). Coating does not fix a misattribution.
  If PD1 were claimed for a named subset, this file would need **per-pair**
  values, not one number, because the file has no concept of "coated path".
- **`scripts/check_isolation_keepout.py`'s `MIN_BARRIER_WIDTH_MM = 8.0`** —
  would become 2.0 only for a corridor whose entire length is coated and
  inspectable. The gate has no way to express that today; it enforces a single
  global straight-line corridor width. **Changing the constant to 2.0 without
  adding a coverage predicate would be a fail-open change**, because it would
  assert PD1 for under-body paths that can never earn it.

### 7.3 Would the CP-SAT barrier become satisfiable at 2.0 mm?

**DERIVED, and NOT RUN — I did not re-run the placement model** (the task
forbids builds and the disk is tight).

The prior barrier-constrained analysis found K2/K3 *unconditionally* infeasible
— no rotation or axis admits a corridor between their own pads, because HV and
SELV pads of the same footprint are ~2 mm apart in both axes on the
bounding-circle model. On the rectangle-aware model every isolator's internal
HV<->SELV gap is **>= 3.200 mm** (C6), and every one exceeds 2.0 mm. **So the
intra-footprint obstruction that made the model unconditionally infeasible
disappears at 2.0 mm.**

What replaces it: the **four inter-component pairs below 2.0 mm** (§Verdict
item 3). Those are pairs of *different* components, so unlike the K2/K3 case
they are addressable by placement. **The honest statement is therefore: at
2.0 mm the model is no longer provably infeasible, and whether it is feasible
is an open question that requires actually running it.** Nobody should record
"feasible at PD1" on the strength of this paragraph.

---

## 8. What a human safety engineer must sign off

Ordered by what blocks what.

1. **Resolve the two existing unqualified coating assumptions** (§7.1) before
   any new decision. The DRC file currently relaxes clearances on a coating
   that does not exist. That is a live fail-open, not a future risk.
2. **Read the current IEC 60335-1 Annex J against the current IEC 60664-3.**
   Everything here is from IS 302-1:2008 and IS 15382 (Part 3):2006, and the
   subclause numbers do not agree between them (§1.1).
3. **Declare a maximum PCB working surface temperature**, measured, not
   assumed. It selects the IEC 60664-3 Table 2 conditioning row and therefore
   selects which coating chemistries are even candidates (§5.2).
4. **Settle the pollution degree of the *uncovered* paths.** PD3 (12.6 mm) is
   the IEC 60335-2-6 default; PD2 (8.0 mm) requires an enclosure argument no
   document in this repo makes. This number governs every under-body path
   whatever the coating does.
5. **Decide whether a scoped Type A claim is worth having at all**, given that
   it covers 116 of 222 sub-12.6 mm pairs and none of the eight isolators.
6. **Accept or reject the relay replacement independently.** The G5LE-1's
   2,000 VAC coil-to-contact dielectric strength is below IS 302-1 Table 7's
   reinforced-insulation requirement regardless of pollution degree (§Verdict
   item 2). Coating is not an alternative to this.
7. **If coating is adopted: choose sealed relays** (`G5LE-14`-class or a
   replacement) or accept masking K2/K3, and decide whether `K1` can be
   coated.
8. **Specify the inspection method and write down what it cannot see.** A
   compliance file that claims PD1 for paths under component bodies is a file
   that claims something no inspection can confirm.
9. **Decide the rework policy.** IEC 60664-3 cl. 1 excludes repaired
   assemblies from its scope, and Annex J switches off the solder-heat and
   solvent-resistance tests. Development rework and a Type A claim are in
   tension.
10. **Type testing and final sign-off** remain a certified test lab's
    responsibility. Nothing here substitutes for it.

---

## 9. Honest cost/benefit

**What it costs**

- A qualification programme: 3–6 coupons per Annex C carrying the production
  minimum spacing, 1000 h dry heat (six weeks of oven time), 96 h cold, 96 h
  damp heat under 100 V DC bias, 5 thermal-shock cycles, scratch, tape
  adhesion, insulation resistance, and an AC withstand test at 2x the basic
  voltage **with a conductive layer on the coating** because the appliance is
  PD3.
- A masking fixture covering at minimum 10 features (§6.2), growing when the
  seven missing connectors are added.
- Either sealed relays or masked relays; masked relays forfeit the credit
  exactly where it is needed.
- A rework policy that is, per the standard's own scope statement, no longer
  covered by the standard.
- A production inspection step that cannot see the paths the claim depends on.

**What it buys**

- PD1 (2.0 mm reinforced instead of 8.0 or 12.6) on **116 of 222**
  sub-12.6 mm cross-domain pad pairs — the open-surface trace and discrete-part
  approaches. Real, and the only remedy for those that does not require moving
  parts.
- **Zero** relief on any of the eight declared isolators.
- **Zero** relief on the four sub-2.0 mm pairs, which fail at PD1 too.

**Compare the two alternatives it was being weighed against**

- A **routed slot** costs one fab feature, is permanently visible, is
  inspectable by looking at the board, survives rework, and works *under
  component bodies* — the exact place coating fails. For `U7` (7.250 mm PCB
  path against a certified >8 mm package path) it is the right and sufficient
  fix.
- A **relay with certified reinforced coil-to-contact isolation** costs a
  footprint and a pin-mapping change and fixes K2/K3 permanently, with the
  isolation carried by a component approval rather than by a process this
  factory has to prove every build.

**DERIVED: coating is the third-best of three tools here, and it is the only
one of the three whose benefit is unverifiable in production.** It is worth
pursuing as a *supplement* — for the open-surface pairs, and for the humidity
and leakage reasons `docs/architecture/induction_curriculum.md` already cites
for the high-impedance ZCD nodes — and it is not worth pursuing as the
solution to the isolator problem, because it does not touch it.

---

## 10. Answering the task's questions directly

| Question | Answer |
|---|---|
| Is Annex J Type A a viable route to PD1 for this board — fully, partially, or not at all? | **Partially, and not where it is needed.** Viable for open-surface cross-domain approaches (116 of 222 sub-12.6 mm pad pairs). Not viable for any of the eight declared isolators. |
| Which paths does it cover? | Paths whose entire length is over exposed, coatable, visually inspectable board surface, between discrete parts. |
| Which does it not? | All eight isolators — 100% of each one's shortest HV<->SELV path lies under its own component body (MEASURED). |
| Residual requirement for the uncovered ones? | IEC 60335-2-6 cl. 29.2 default PD3 -> Table 17 row iv PD3 IIIa/IIIb 6.3 mm x2 = **12.6 mm reinforced**, unless PD2 (8.0 mm) is separately earned by an enclosure argument that does not exist today. |
| Does coating change the microenvironment for K2/K3's case-surface path? | **No.** The board-surface copy of that path is under the relay base and uncoatable; the internal coil-to-contact path is a component property governed by the relay's own approval, and the G5LE-1 has no stated creepage figure and only 2,000 VAC coil-to-contact dielectric strength. |
| Are coating and the relay replacement alternatives? | **No. Both are needed, and the earlier framing to the user was wrong.** Stated plainly, as the task required. |

---

## 11. Sources — exactly what was reached and read

**Reached and read this session, in raw text, by me:**

- **IS 302-1:2008** — Bureau of Indian Standards identical adoption of
  IEC 60335-1, published under India's RTI Act. Archive.org OCR text layer,
  312,769 bytes. Read: clause 16.3 and Table 7; clause 29 preamble; clauses
  29.1, 29.2, 29.2.1–29.2.4, 29.3; Table 17 in full; **Annex J in full**;
  Annex K; Annex L (L-1, L-2); Annex M. Every quotation above was read from
  this raw text. **Caveat: OCR'd scan, 2008 edition (IEC 60335-1 Ed. 4.2-era).**
  <https://archive.org/download/gov.in.is.302.1.2008/is.302.1.2008_djvu.txt>
- **IS 15382 (Part 3):2006 = IEC 60664-3:2003**, *Insulation coordination for
  equipment within low-voltage systems, Part 3: Use of coating, potting or
  moulding for protection against pollution*. Same source, `pdftotext` and
  `pdftotext -layout` extracted, 2448 lines, read in full: Scope, clause 3
  definitions, clause 4 (4.1–4.4) and Table 1, clause 5 (5.1–5.9.3) and
  Tables 2 and 3, Annex A (test sequence), Annex B, Annex C. **This is the
  document Annex J delegates to and it had not been read in this project
  before.**
  <https://law.resource.org/pub/in/bis/S05/is.15382.3.2006.pdf>
- **IS 302-2-6:2009** — identical adoption of IEC 60335-2-6. `pdftotext`
  extracted; clause 29 heading and the 29.2 Addition read verbatim,
  independently re-confirming the prior determination's quotation.
  <https://law.resource.org/pub/in/bis/S05/is.302.2.6.2009.pdf>
- **Omron G5LE datasheet** (en-g5le.pdf, the URL this repo's own
  `components.ato` cites). `pdftotext` extracted; read the Model Number Legend
  (enclosure rating field), the Ordering Information table, and the
  Characteristics table (dielectric strength, impulse withstand, ambient
  operating temperature).
  <https://omronfs.omron.com/en_US/ecb/products/pdf/en-g5le.pdf>
- **MG Chemicals, *Conformal Coatings* category data sheet, v2.0,
  19 December 2025.** `pdftotext -layout` extracted; the full comparison table
  (binder system, IPC-CC-830 revision, dielectric strength, constant service
  temperature, Tg, CTE, solderability, chemical resistance) read directly.
  <https://mgchemicals.com/downloads/category-data-sheets/CDS-Conformal%20Coatings.pdf>
- **Electrolube HPA conformal coating TDS** (MacDermid Alpha, 19 Jul 2024).
  `pdftotext -layout` extracted; operating temperature range, IPC-CC-830
  approval statement, and application thickness window read directly.
  <https://www.macdermidalpha.com/sites/default/files/2025-06/Electrolube-HPA-CNC-TDS-GL-EN-19Jul2024.pdf>

**Method note:** `WebSearch` was not used (budget exhausted in this shared
environment, the same constraint the two prior determinations hit). Sources
were reached by direct-URL reasoning; `lite.duckduckgo.com` served as a
URL-discovery path for the two coating datasheets, whose PDFs were then fetched
and read directly rather than through a summarising layer.

**Attempted and failed:**

- `archive.org` OCR sidecar for IS 15382 (Part 3) — 404. The
  `law.resource.org` PDF has a usable text layer and was used instead.
- IPC-CC-830B from ipc.org — HTTP 500.
- A HumiSeal TDS via `chase-canada.com` — DNS failure.

**NOT reached, and NOT reconstructed:**

- The **current** editions of IEC 60335-1 (Annex J) and IEC 60664-3. The
  clause-numbering discrepancy in §1.1 is unresolved because of this.
- The earlier edition of IEC 60664-3 whose clause 6 Annex J appears to cite.
- IEC 60664-1's own primary text (Part 1 subclauses 3.1, 3.2, 4.1.2.3,
  3.3.3.2.2 and Table 1 are referenced by IEC 60664-3 cl. 4.4 / 5.8.4 and were
  **not** read; the AC withstand test voltage for this board's reinforced
  barrier is therefore **not** computed here).
- Any parylene datasheet. No parylene temperature or process figure is stated
  anywhere in this document.
- Omron G4A-1A-E (`K1`) enclosure rating and coil-to-contact isolation.
- Any coating vendor's IEC 60664-3 qualification data. Neither vendor document
  fetched mentions the standard.

---

## 12. UNVERIFIED — explicit list

- **The clause numbers in IEC 60335-1 Annex J do not match IEC 60664-3:2003.**
  §1.1. The mapping I give is derived from subject matter, not read from a
  concordance.
- **The under-body determination uses a rectangular bounding box** of `F.Fab`
  (or `F.SilkS`/`F.CrtYd`) graphics as the component body. This over-flags for
  parts whose body is raised on leads (axial resistors) and for L-shaped or
  non-rectangular bodies. It is sound for seated bodies — SOIC, DIP, relay,
  module — which is every isolator except `C6`.
- **Whether a conformal coating physically reaches under a given package is a
  process fact I did not measure**, only reasoned about from geometry and from
  the fact that it cannot be *inspected*. The compliance argument in §6.4 rests
  on inspectability, which is the stronger and more defensible half.
- **`C6` has no body outline in its footprint**, so its under-body fraction is
  not measured (§4.3).
- **The pad-pair analysis ignores traces and the 96 copper pours.** Real
  creepage may be shorter than any figure here. Nothing in this document
  establishes that the assembled board meets any requirement.
- **The CP-SAT placement model was not re-run at 2.0 mm** (§7.3). "No longer
  provably infeasible" is not "feasible".
- **The IS 302-1 Table 7 comparison in the Verdict** treats an appliance-level
  clause 16.3 test voltage as a bar for a component's datasheet figure. IEC
  60335-1 clause 24 has provisions for components tested to their own
  standards, which I did not read. The direction of the finding is robust —
  2,000 V is below every reinforced column in Table 7 — but the exact
  applicable column and any component-standard carve-out are not established.
- **The working-voltage bracket** for Table 17 is taken from the prior
  determination (row iv, >250 and <=400 V) and not independently re-derived. A
  per-crossing working voltage was not assigned.
- **The declared maximum PCB working surface temperature does not exist**, so
  the IEC 60664-3 Table 2 row is not selected and the coating-chemistry
  screening in §5.3 is conditional on it.
- **IPC-CC-830 vs IEC 60664-3**: I established that neither vendor document
  mentions IEC 60664-3, and that they are different documents with different
  specimens. I did **not** read IPC-CC-830 and cannot state the precise
  relationship between the two regimes.
- No claim here is a compliance determination. No clause number, table number,
  or table value above is stated except where I read it myself in the raw text
  and can point at the file it came from.

---

## Compliance with the task's hard rules

- **Changed nothing.** No BOM, no `netclass_rules.yaml`, no
  `check_isolation_keepout.py` constant, no `pcb/temper.kicad_pcb`, no gate.
  This file is the only addition. `git status --short` showed only this file
  throughout.
- No `git stash` at any point.
- No `run_in_background`, no `Monitor`, no waiting on any background job.
  Everything foregrounded.
- No additional worktrees. No cargo builds. Downloads: three standards PDFs/
  text files and three datasheets, ~4.6 MB total, all in the session
  scratchpad, none in the repo.
- Analysis scripts (`coverage2.py`, `boardwide.py`, `masking.py`,
  `verify2.py`) live in the session scratchpad and are not committed —
  read-only analysis, matching the precedent of the three sibling evidence
  docs.
- Work confined to worktree `agent-a4005790622d73862`, touching only
  `docs/evidence/`. Not pushed.
