# Heatsink insulation basis, r1: does the FET-to-sink insulation need to be reinforced?

Date: 2026-10-27. Read-only research. Nothing was built or run. **This is not legal or certification
advice.** Each claim is tagged with its source:

- **[STD]**: primary standard text read in this session. IEC 60335-1 text comes from IS 302-1:2008, India's
  identical adoption of IEC 60335-1 ed. 4.x. IEC 60335-2-6 text comes from IS 302-2-6:2009. Both are public
  scans on archive.org.
- **[TRF]**: clause wording printed in an IECEE test report form for IEC 60335-1:2010 (ed. 5).
- **[SEC]**: a secondary source, such as a lab notice, magazine or vendor page.
- **[REPO]**: this repository.
- **[EST]**: my own estimate.
- **[MEM]**: my recollection, not verified in this session.

## Answer

**Yes. Basic insulation between the FET tabs and the heatsink is acceptable under IEC 60335-1 / -2-6, provided
the sink is a protectively earthed part of this Class I appliance.** "Protectively earthed" means bonded to the
earthing terminal permanently and reliably, and passing the 27.5 bond test. In Class I, earthed metal (even
metal the user can touch) needs only basic insulation from live parts. Reinforced insulation is required only
for Class II appliances and Class II constructions (cl. 8.2). The 29.3 thickness rules apply only to
supplementary and reinforced insulation; there is no thickness rule for basic. IEC 60335-2-6 shows the same
model: with earthed metal between the live parts and the hob glass, the pan-side electric strength test is the
basic-level 1250 V, not 3000 V.

**The repo's reinforced call does not come from the standard.** It comes from the repo's own D5-BASIS rule:
"maintain the full HOT-to-controller reinforced insulation requirement with PE open". That rule matters
because R38 ties the controller return to PE. Two parts of the repo's stated reasoning are wrong:

- CHECKLIST CMP-15 cites cl. 8.2, but 8.2 covers Class II only.
- CHECKLIST PWR-22 calls the sink "user-touchable", but the enclosure's own analysis says Ø5 mm openings keep
  test probe B out.

**Basic insulation does not, by itself, make the proposed Sil-Pad K-10 / SP2000 work.** Both fail the repo's
0.7 °C/W-per-FET thermal budget (D-36). Thin pads also raise the switch-node-to-PE capacitance roughly 3-8×.
That is an EMI and touch-current question, not an insulation-class one. The cheapest route that is both
compliant and thermally viable is a protectively bonded sink with **basic** insulation made from either a thin
low-impedance film (HI-FLOW 300P class) or thin catalogue ceramic. Both need an EMI re-check for the two
switch-node tabs.

**Overall confidence:** high that IEC does not require reinforced insulation at a protectively earthed sink.
Medium that a lab will accept basic insulation here without asking for changes around R38 / PELV.

## 1. What the repo says, and where

| Location | Claim | Verdict |
| --- | --- | --- |
| `zapote/power-stage-120v/DECISIONS.md:270` (M11) | "Requirement: reinforced. R38 ties PE to the controller return, and D5-BASIS keeps that barrier reinforced." | **Accurate account of the repo's own reason.** It is a self-imposed rule, not a clause requirement (see §3). |
| `zapote/power-stage-120v/D5-BASIS.md:9-15` | "maintain the full HOT-to-controller reinforced insulation requirement with PE open … heatsink insulators must also be checked for bypassing that barrier … Do not carry the old basic-only HOT-to-PE rule forward without a justified system insulation analysis" | This is the root. The owner approved it as a *conditional placement basis*, and it asks for a system analysis. This README is part of that analysis. |
| `…/owner-items/m11/RECOMMENDATION.md:91-101` | "In IEC 60335-1, Class I logic normally allows *basic* insulation from live parts to earthed metal … With PE open, a single failure of a basic-only tab insulator puts HOT onto the controller ground. Design to reinforced." | **The first sentence is correct.** The second treats "PE open + insulator failure" as a single fault. Under the Class I definition it is two faults (see §3). |
| `DECISIONS.md:286` (M11 amendment, item 3) | "In a Class I appliance an earthed sink normally needs only basic insulation … If the lab accepts basic, revisit the stack." | **Correct.** The repo had already flagged this as a certifier question. |
| `DECISIONS.md:273`, `CHECKLIST.md` PWR-22 | "2.00 mm AlN … count as reinforced by thickness (IEC 60335-1 29.3.1)" | **Correct reading of 29.3.1** *if* reinforced insulation were needed. 29.3.1 b) does say 2 mm for reinforced. |
| `output/temper-checklist/CHECKLIST.md:143` PWR-22 | "Sink is PE-bonded and user-touchable, so HOT↔PE needs reinforced insulation" | **Wrong on both counts.** (a) The enclosure analysis says the sink sits behind Ø5 mm holes, which probe B (Ø12) cannot enter. (b) Even a touchable earthed sink needs only basic insulation in Class I. |
| `CHECKLIST.md:530` CMP-15 | "cl. 8.2 keys reinforced insulation on probe-B touchability (the repo's own reading)" | **Misapplied.** 8.2 opens: "Class II appliances and Class II constructions shall …". It does not apply to an earthed sink in a Class I appliance. The source note (`docs/evidence/2026-08-19-60335-2-6-cl-29-2-pd2-condition.md` §6.5, commit 17a4e6d94) was written about a non-conductive panel in a Class II construction. The same note says: "For Class I, accessible metal is earthed under cl. 27, and live parts still need **basic** insulation to that earthed metal." |
| `/Users/bennet/Desktop/temper/output/temper-manufacturing-r43/evidence/airflow-r32/REPORT.md:115-118` | "Ø5 holes don't admit test probe B (Ø12, IEC 61032) … Probe 13 applies to class II only" | Supports "the sink is internal". The lab still has to confirm it (`design/r32/CERTIFICATION-QUESTIONS.md:84`). |
| `DECISIONS.md:379-386` | Sink bond: M4 ear, toothed washers, 14 AWG strap to the chassis star, ≤ 0.1 Ω at 25 A (§27.5). The bar-to-sink joint has toothed washers outside the compound area. | This is a **protective** bond construction. It is exactly what basic insulation relies on. Keep it. |

**Is the sink user-accessible?** It is not touchable from outside: it is behind Ø5 openings and inside a metal
enclosure **[REPO]**. Under the definition in cl. 3.6.3, however, it is still an "accessible part", because it
is metal connected to the accessible metal chassis. 3.6.3 reads: "Part or surface that can be touched by means
of test probe B …, and if the part or surface is metal, any conductive part connected to it" **[STD]**. That
does not change the answer: accessible earthed metal in Class I needs basic insulation.

## 2. Findings per question

### Q1. Is basic insulation to an earthed accessible metal part acceptable in Class I? **Yes. Confidence: high.**

- **Class I definition (3.3.9) [STD]:** "protection against electric shock does not rely on basic insulation
  only but which includes an additional safety precaution, in that conductive accessible parts are connected
  to the protective earthing conductor … in such a way that conductive accessible parts cannot become live in
  the event of a failure of the basic insulation."
- **Insulation types (3.3.1-3.3.4) [STD]:**
  - Basic: "Insulation applied to live parts to provide basic protection against electric shock."
  - Supplementary: "Independent insulation applied in addition to basic insulation … in the event of a failure
    of basic insulation."
  - Double: basic plus supplementary.
  - Reinforced: "Single insulation … equivalent to double insulation."
- **8.1 [STD]:** "constructed and enclosed so that there is adequate protection against accidental contact with
  live parts". It is tested with probe B, and through openings "to any depth that the probe will permit". The
  earthed sink is not a live part.
- **8.2 [STD]:** "**Class II appliances and Class II constructions** shall be constructed and enclosed so that
  there is adequate protection against accidental contact with basic insulation and metal parts separated from
  live parts by basic insulation only. It shall only be possible to touch parts which are separated from live
  parts by double insulation or reinforced insulation." **This is the only clause that requires double or
  reinforced insulation for touchable parts, and it is scoped to Class II.**
- **27.1 [STD]:** "Accessible metal parts of Class I appliances that may become live in the event of an
  insulation fault, shall be permanently and reliably connected to an earthing terminal …". It also says:
  "Safety extra-low voltage circuits shall not be earthed unless they are protective extra-low voltage
  circuits." Note 1 says metal screened from live parts by earthed metal "is not regarded as likely to become
  live".
- **27.5 [STD/REPO]:** the bond test. The repo specifies ≤ 0.1 Ω at 25 A (`DECISIONS.md:385`).
- **29.3 [STD, ed. 4; same in ed. 5 per TRF]:** "**Supplementary insulation and reinforced insulation** shall
  have adequate thickness, or have a sufficient number of layers …".
  - 29.3.1: "a) 1 mm for supplementary insulation; and b) 2 mm for reinforced insulation."
  - 29.3.2: layers. 29.3.3: dry heat plus the 16.3 test.
  - **There is no thickness requirement for basic insulation.** Basic solid insulation is qualified by the
    16.3 electric strength test, plus clearance (29.1) and creepage (29.2) around it.
- **Electric strength, type test (16.3, Table 7) [STD, ed. 4]:** at rated voltage ≤ 150 V:

  | Insulation | Test voltage |
  | --- | --- |
  | Basic | 1250 V |
  | Supplementary | 1250 V |
  | Reinforced | 2500 V |

  Footnote b: for appliances rated ≤ 150 V, the > 150-250 V column applies to parts with a working voltage of
  > 150 V. That column gives basic 1250 V and reinforced 3000 V. Ed. 5 / ed. 6 values were not read here;
  **[MEM]** basic may be 1000 V in ed. 5+.
- **Electric strength, routine test (Annex A, Table 19) [STD, ed. 4], 1 s:**
  - live to accessible metal, basic insulation only, rated ≤ 150 V: **800 V**;
  - double or reinforced: **2000 V**.

  The repo's PWR-29 plan (3000 Vac 60 s type test, 2000 Vac 1 s routine) is the reinforced set.
- **Creepage / clearance for basic [REPO, from Table 16/17 ed. 4]:**
  - clearance 1.3 mm (0.8 + 0.5);
  - creepage 4.0 mm (PD3, IIIa/IIIb, row iii);
  - over ceramic, creepage "need not be greater than the associated clearance" (Table 17 note 2) **[STD]**.

### Q2. What if the sink is internal and not accessible? **Confidence: high on the logic, medium on the lab's reading.**

- **If the sink stays bonded to the earthed chassis:** it is an accessible part by definition (3.6.3, see §1).
  The answer stays "basic plus protective bond". Being internal adds nothing and takes nothing away.
- **If the sink floats** (not bonded and not probe-B reachable): it is not an accessible part.
  - Tab-to-sink then needs only functional insulation.
  - But the sink must be treated as possibly live. It needs basic insulation (4.0 mm creepage, PD3) to every
    earthed or accessible part: mounting brackets, chassis, hood.
  - It must not be reachable through any opening:
    - probe B (8.1.1);
    - -2-6 8.1.2 Addition: "Test probe 12 … applied … to parts liable to be touched accidentally in normal use
      by a fork" **[STD -2-6]**.
  - **Anything SELV/PELV mounted on the sink would then need reinforced insulation to the sink.** That
    includes the fan-loop NTC (`/Users/bennet/Desktop/temper/output/temper-manufacturing-r43/evidence/airflow-r32/REPORT.md:132`).
  - The sink sits in the spill path the repo already found (-2-6 15.2 overflow, REPORT.md:98).
  - **A floating sink therefore moves the problem rather than removing it. It is not recommended.**

### Q3. Do induction or -2-6 changes alter this? **No. Confidence: medium-high (2009 adoption of -2-6; the current edition is 2024 and was not read).**

- **-2-6 cl. 27 [STD]:** "This clause of Part 1 is applicable." There is no earthing modification.
- **-2-6 cl. 29 [STD]:**
  - 29.2 Addition sets the microenvironment default to PD3. The repo already uses PD3.
  - 29.3 Addition only exempts glowing-element sheaths.
  - Nothing adds to the solid-insulation rules for the power stage.
- **-2-6 16.3 Addition [STD]:** "If there is earthed metal between live parts and the surface of glass-ceramic …
  of hobs, a test voltage of **1 250 V** is applied between live parts and all the vessels connected to the
  earthed metal. If there is no earthed metal, a test voltage of **3 000 V** is applied."
  - 13.3 has the same pattern: 1000 V / 3000 V.
  - **This is the standard itself accepting basic insulation plus earthed metal, even on the path to the
    user's pan.**
- **-2-6 7.12 Addition [STD, via REPO evidence note]:** the glass-ceramic "protects live parts" warning about
  cracked glass. It concerns the glass and coil, not the FET sink.
- **Glass breakage and the pan path** do not reach the FET sink. They are not grounds for reinforced
  insulation there.
- **Part 2 choice:** -2-6 (stationary) vs -2-9 (portable) is still open (R43 `CERTIFICATION-QUESTIONS.md`).
  The repo found -2-9 carries the same 29.2 PD3 Addition (commit 6b109dd91).

### Q4. US standards. **Confidence: medium on scope, low on clause detail (no primary UL text for spacings or dielectric was read).**

**Which standard:**
- UL 1026 (2002 ed.) 1.1 **[STD, preview read]**: "electric household cooking and food serving appliances,
  rated at 250 V or less …". 1.2 excludes "household electric ranges", skillets, woks and others. Hot plates
  and cooktops are not excluded.
- UL 858 added "Appliances with Induction Heating Functionality" in its Feb 2017 revision, for example
  47.7/47.8 and 59.6 "Small metal object heating test – induction cooktop surface units" **[SEC: Intertek SUN,
  2018]**. UL 858 scope is "floor or cabinet supported, wall-mounted, counter mounted" equipment
  **[REPO c54, read there]**.
- **Reading:** a cord-connected countertop unit that is not mounted falls under UL 1026. A counter-mounted
  built-in falls under UL 858. This matches CHECKLIST CMP-01 (still open).
- No US "UL 60335-2-6" was found. Canada has CAN/CSA-E60335-2-6 (an IEC adoption) **[SEC]**.
- UL 197 is commercial cooking and does not apply to a household product **[MEM]**.

**Insulation model:**
- UL appliance standards do not use basic/reinforced categories for live-to-grounded-dead-metal insulation.
  They use spacings tables, a dielectric withstand test, material ratings (UL 746C, RTI) and grounding of dead
  metal **[SEC: china-item.com]**.
- "Reinforced" vocabulary only enters through double-insulation claims (UL 1097) **[SEC]**.
- So under UL 1026/858, a grounded internal sink with a recognised insulating pad that passes the dielectric
  test is ordinary practice **[MEM / not verified from primary UL text]**.

**Dielectric test:** typically **1000 Vac for 1 min** for a 120 V appliance **[SEC: china-item.com; PSMA
table]**. UL 1026 places it in sec. 44 in the current edition (sec. 38 in 2002) **[SEC]**.

**Spacings and liners:** UL appliance standards have their own spacing tables and allow UL 840 as an
alternative. A thin insulating liner used instead of spacing has a minimum thickness unless it meets
exceptions **[MEM]**. None of this was read in primary text. Ask the lab (§5).

**Leakage:** 0.5 mA for a grounded portable appliance, measured with ground open **[REPO c54]**. This is where
the tab-to-PE capacitance shows up (§4).

### Q5. Is there any legitimate reason for reinforced insulation? **Partly. Confidence: medium.**

1. **The R38 / PELV argument (the repo's real reason).**
   - R38 bonds the controller return to PE, so the controller ELV circuit is earthed. By 27.1 it must then be
     PELV. PELV is defined in 3.4.4 **[STD]**: "Earthed circuit operating at safety extra-low voltage which is
     separated from other circuits by **basic insulation and protective screening**, double insulation or
     reinforced insulation."
   - The tab-to-sink path is "basic insulation plus an earthed screen" (the sink). That is one of the
     constructions the PELV definition allows, as long as a fault current into the sink goes to the cord PE
     without passing through R38 or the controller copper.
   - D5-BASIS already requires this: "J6, its PCB trace and R38 are never in series with the primary PE bond".
     The sink strap goes to the chassis star.
   - **"Reinforced with PE open" therefore covers a double fault (PE open + insulator failed).** Class I does
     not cover that case: see the 3.3.9 wording above.
   - **The rule is also inconsistent when applied only at the sink.** With PE open, a basic-insulation failure
     anywhere to the earthed chassis would put HOT on PE and, through R38, on the controller return. Examples
     are mains wiring, inlet hardware, or anything else insulated from chassis by basic insulation only. To
     deliver what it aims for, the rule would have to make every HOT-to-chassis insulation reinforced, which
     amounts to Class II. **[EST/argument]** Verify with the lab.
   - **Caveat:** IEC 60335-1:2020 "clarified requirements for PELV circuits", "revised and clarified
     requirements for appliances incorporating a functional earth" and added "22.59 … separation between parts
     operating at PELV and SELV" **[SEC: EVS and UL summaries]**. The ed. 6 text was not read. If the lab
     calls R38 a *functional* earth (D5-BASIS calls it a "functional connection") rather than a PELV earth, it
     may treat the controller as SELV. SELV must not be earthed (27.1), and it needs double or reinforced
     separation from live parts (3.4.2) **[STD]**. In that case the sink becomes part of a SELV barrier, and
     reinforced insulation (or removing R38) is the consistent answer.
   - **This is the one real question for the lab.**
2. **Sink bond judged functional.** The lab could rule the sink bond functional or not reliable
   (R43 `CERTIFICATION-QUESTIONS.md:78` already asks). Then basic insulation would not be enough. The fix is to
   make the bond protective (27.5 test, toothed washers, strap), not to use thick ceramic.
3. **HF stress on the two switch-node tabs** (Q3 `sw_a`, Q6 `sw_b`, 33-40 kHz).
   - Ed. 5 adds IEC 60664-4 checks above 30 kHz: 29.2.1 for creepage, and 29.3 "as specified in subclause 6.3
     of IEC 60664-4" for solid insulation **[TRF]**.
   - The 29.3 route sits in the supplementary/reinforced clause. Whether ed. 6 applies an HF field limit to
     basic solid insulation was not read.
   - The repo computes 3.1 kV/mm on K-10 at 470 V (`m11/RECOMMENDATION.md:132-133`). Ask the lab.
   - This is a check, not a reason for 2 mm.
4. **EMI and touch current (engineering, not insulation class).** 2 mm AlN gives 5.8-9.1 pF per tab
   **[REPO]**. Thin pads give 33-52 pF (K-10) **[REPO]**, about 46-74 pF for HI-FLOW 300P, and about 18-33 pF
   for 0.635 mm ceramic **[EST, parallel plate, 151-240 mm² tab]**.
   - Only the two switch-node tabs matter. The bus_p tabs and BR1 are quiet relative to PE at HF.
   - c54 shows CM at 180 kHz is already the binding EMI line, and it is sensitive to node-to-PE pF
     (`validation-results/11-candidates/c54-touch-current/README.md:81`).
   - **This is the strongest real argument for a thick, low-capacitance insulator on Q3/Q6.** It is a reason
     to re-run the EMI model, not a compliance requirement.
5. **Thermal (D-36 0.7 °C/W budget).** This is the reason the *proposed* pads fail:
   - K-10: 1.10-1.75 °C/W **[REPO]**.
   - SIL PAD 2000: 0.38 °C·in²/W at 50 psi **[SEC: Bergquist datasheet]**, about 1.0-1.6 °C/W over the TO-247
     tab area **[EST]**.
   - SIL PAD 1500ST: 0.62-0.98 °C/W **[REPO]**.
   - All of these fail regardless of insulation class.
6. **29.3.1 itself is quoted correctly.** It is misapplied only in that it was reached through 8.2, which is a
   Class II clause, and through "user-touchable", which the enclosure evidence contradicts.

## 3. Cheapest compliant sink-mount options (production), ranked

All options assume the following stays as built: the PE-bonded sink, the protective bond (`DECISIONS.md:382-385`),
the 8 mm setback geometry (needed even for basic, per `DECISIONS.md:283`) and the insulated comb clamp with an
FR-4 strip. Package mould compound is not credited (Infineon V_ISO "n.a." [REPO]).

| Rank | Option | Thermal vs 0.7 °C/W | Tab→PE pF (sw tabs) | Compliance basis | Cost / risk |
| ---: | --- | --- | --- | --- | --- |
| 1 | **One shared sheet of HI-FLOW 300P-class film** (polyimide carrier, 5 kVac [REPO]) across Q5/Q6/Q3/Q2, with ≥ 4.0 mm margin beyond tab metal (organic surface, PD3). BR1 keeps its gap pad. | 0.35-0.55, pass [REPO] | ~46-74 [EST] | Basic: 16.3 at 1250 V (ed. 4), creepage 4.0 mm, clearance 1.3 mm. M11's own geometry gives 4.6 mm lead-top to pedestal for a thin film (`RECOMMENDATION.md:183`), which is ≥ 4.0. | Cheapest. Catalogue sheet (price not quoted [EST: a few $/board]). **Needs the EMI CM re-run** with the higher sw-tab capacitance. |
| 2 | **Thin catalogue ceramic per device** (0.635 mm alumina or AlN, with non-conductive grease) | ~0.45-0.65 alumina [EST], AlN lower | ~18-33 [EST] | Basic. Over ceramic, creepage may equal clearance (Table 17 note 2), so a small overhang is enough and per-device parts fit the 18 mm pitch. | Low cost. Brittle, needs grease squeeze-out control. AlN is not stocked as TO-247 parts [REPO]; alumina is (e.g. Boyd 4180G class [SEC]). |
| 3 | **Mixed:** option 1 under the quiet tabs (Q5, Q2 bus_p) and option 2 or 1 mm AlN under the switch-node tabs (Q3, Q6) | pass | low on the sw tabs | Basic | Keeps CM capacitance near today's model at about half the ceramic count. |
| 4 | **Keep the 2 mm AlN tiles** (current design) | 0.40-0.63, pass [REPO] | 5.8-9.1 [REPO] | Compliant either way (reinforced by 29.3.1). | ~$350/board set [REPO]. Right for the 4 prototype stacks already decided (`DECISIONS.md` item 80), because it does not wait on the lab. |
| 5 | **Floating internal sink** | — | lowest to PE | Functional tab insulation, basic sink-to-chassis. | **Not recommended.** The NTC on the sink would need reinforced insulation; there are probe 12/B and spill exposures; the hardware just moves. |

**Recommendation [EST]:**
- Keep option 4 for the prototype lot. It is already sized at 4 stacks.
- For production, plan option 1 or 3 once the lab answers §5 Q1-Q2, and re-run the CM EMI model with the new
  sw-tab capacitance.
- Do not pick K-10 or SP2000. They fail the thermal budget.

## 4. What changes in the repo if the lab accepts basic (for the coordinator; not done here)

- **PWR-22:** replace the rationale "user-touchable, so reinforced" with "protectively earthed internal sink;
  basic per Class I (3.3.9, 27.1); reinforced kept only under D5-BASIS pending the lab".
- **PWR-29:** the basic type test is 1250 V × 60 s (ed. 4 Table 7; ed. 6 value to confirm). The routine test
  is 800 V × 1 s (Table 19). The UL dielectric test is ~1000 V × 60 s [SEC]. Keep the 27.5 bond test.
- **D5-BASIS:** add a carve-out stating that HOT to *protectively bonded* metal is basic, provided the fault path
  avoids R38. Otherwise, revisit R38, as `DECISIONS.md:286` already proposes.

## 5. What to ask the certifier (replaces CHECKLIST CMP-15)

**Proposed CMP-15 row text:** "Heatsink insulation class. The repo's reinforced call comes from D5-BASIS
(R38 bonds the controller return to PE; reinforced 'with PE open'), not from cl. 8.2, which is Class II only.
IEC Class I needs basic insulation to protectively earthed metal (3.3.9, 27.1, 29.3). The lab is to confirm
Q1-Q7 below. Prototype stays on 2 mm AlN. See `output/temper-insulation-basis-r1/README.md`."

1. **Standard set.** UL 1026 (portable countertop) or UL 858 (counter-mounted)? For CSA/NOM, which part? For
   the IEC basis, -2-6 or -2-9, and which edition of 60335-1 (2020 + A1:2025)?
2. **Class I sink.** The FET tabs sit on an aluminium sink inside a metal Class I enclosure. The sink is
   bonded to the chassis star by a 14 AWG strap and toothed-washer joints, tested at ≤ 0.1 Ω / 25 A (27.5). It
   cannot be reached by probe B (Ø5 openings). Is **basic** insulation tab-to-sink sufficient? Is the bond
   accepted as protective?
3. **R38 / PELV.** The controller ELV return is bonded to PE by a 0 Ω link (R38) on a separate PE branch. R38
   is not in series with the sink's fault path to the cord PE. Do you classify the controller as PELV
   (3.4.4: "basic insulation and protective screening" allowed)? If so, is basic insulation at the sink
   acceptable? Or do you treat R38 as a functional earth on a SELV circuit, which would make the sink part of
   a reinforced barrier? What do the ed. 6 PELV / functional-earth / 22.59 changes require here?
4. **Basic solid insulation.** For a 0.1-0.65 mm insulator, please confirm:
   - the type-test voltage (Table 7, current edition);
   - the routine test (Table 19);
   - that no minimum thickness applies to basic insulation;
   - whether an IEC 60664-4 field-strength check applies to basic insulation on tabs switching at 33-40 kHz,
     ~200 V working, 470 V peak.
5. **Creepage over the insulator.** PD3 inside the forced-air duct? Is creepage over ceramic credited at the
   clearance value (Table 17 note 2) when the edges carry non-conductive silicone grease?
6. **Clamp.** A PE-connected spring presses on the TO-247 mould face through a 3 mm FR-4 strip. Is the strip
   accepted as the basic insulation, given that the mould is not credited?
7. **UL specifics.** Under the governing UL standard:
   - What spacings apply between the live tab and grounded dead metal?
   - Is a recognised thermally conductive insulator under a semiconductor accepted in place of spacings, and
     with what material ratings (RTI, UL 94, file)?
   - What is the dielectric test voltage and duration?

## 6. Confidence summary

| Conclusion | Confidence | Main basis |
| --- | --- | --- |
| IEC 60335-1 does not require reinforced insulation from live parts to a protectively earthed Class I part | **High** | 3.3.9, 8.2 scope, 27.1, 29.3 [STD]. Same structure in ed. 5 [TRF]. |
| CMP-15's cl. 8.2 basis is misapplied | **High** | 8.2 text [STD] |
| The sink is not touchable from outside | **Medium** | Enclosure R32 analysis [REPO]. Lab confirmation pending. |
| -2-6 adds nothing that forces reinforced at the FET sink | **Medium-high** | 2009 adoption read [STD]. 2024 edition not read. |
| The R38/PELV argument lets basic stand | **Medium** | 3.4.4, 27.1 [STD]. Ed. 6 PELV / functional-earth changes not read [SEC]. |
| US (UL 1026/858) treats it as grounded dead metal + spacings + dielectric, ~1000 V | **Low-medium** | Secondary sources only |
| K-10 / SP2000 fail the 0.7 °C/W budget | **High** | Repo stack-calc and Bergquist datasheet |
| A thin insulator raises sw-tab CM capacitance enough to matter for EMI | **Medium** (direction certain, size needs the model) | c54 [REPO], EST |

## 7. Sources (all read 2026-10-27)

- IS 302-1:2008 (≡ IEC 60335-1 ed. 4.x), archive.org OCR text:
  https://archive.org/download/gov.in.is.302.1.2008/is.302.1.2008_djvu.txt. Clauses used: 3.3.1-3.3.10,
  3.4.2-3.4.4, 3.6.3, 8.1-8.2, 16.3 Table 7, 27.1, 29.3-29.3.3, Annex A Table 19. This is the same file the
  repo cites (312,769 bytes).
- IS 302-2-6:2009 (≡ IEC 60335-2-6:2002/2004 era):
  https://archive.org/download/gov.in.is.302.2.6.2009/is.302.2.6.2009_djvu.txt. Clauses used: 8.1.2, 13.3,
  16.3 Additions, 27, 29.2/29.3 Additions.
- IECEE TRF, IEC 60335-1:2010 (ed. 5), Victron Cyrix report:
  https://www.victronenergy.com/upload/documents/Safety-EN-IEC-60335-1-Cyrix.pdf (29.2.1 HF, 29.3, 29.3.1-29.3.4).
- Intertek SUN, UL 858 Feb/Nov 2017 revisions (induction requirements):
  https://cdn.intertek.com/www-intertek-com/dms-legacy/UL-858-Rev-2-8-2017-and-11-1-2017-ED-9-1-2020.pdf
- UL 1026:2002 preview (scope 1.1/1.2): https://avadocuments2026.com/preview/ul-1026-2002.pdf
- IEC 60335-1:2020 change list: https://www.evs.ee/en/iec-60335-1-2020 ; UL clause table:
  https://ul.com/services/iec-60335-1-standard-safety-household-and-similar-electrical-appliances
- UL vs IEC differences (UL dielectric 1000 V typical): http://www.china-item.com/Newsshow_262.html [SEC]
- Bergquist SIL PAD 2000 data (via search summary of the Bergquist datasheet):
  https://www.electronicsdatasheets.com/download/4998.pdf?format=pdf [SEC]
- Repo:
  - `zapote/power-stage-120v/DECISIONS.md:268-304, 378-386`
  - `zapote/power-stage-120v/D5-BASIS.md`
  - `zapote/power-stage-120v/validation-results/08-manufacturing-package/native-21/owner-items/m11/RECOMMENDATION.md`
  - `zapote/power-stage-120v/validation-results/11-candidates/c54-touch-current/README.md`
  - `output/temper-checklist/CHECKLIST.md` (PWR-22, PWR-29, CMP-15)
  - `docs/evidence/2026-08-19-60335-2-6-cl-29-2-pd2-condition.md` @ d452536c8
  - `/Users/bennet/Desktop/temper/output/temper-manufacturing-r43/evidence/airflow-r32/REPORT.md` and
    `design/r32/CERTIFICATION-QUESTIONS.md`

**Not found or not verified:**
- a commercial induction-cooker teardown that documents IGBT pad mounting and sink earthing;
- primary UL 1026 / UL 858 spacing and dielectric clauses;
- the IEC 60335-1:2020 and IEC 60335-2-6:2024 text.
