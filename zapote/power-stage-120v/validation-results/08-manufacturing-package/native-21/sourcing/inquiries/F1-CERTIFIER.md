> **s52 status (2026-10-16): the body below is the 2026-10-08 MDA-25-R inquiry and is not yet rewritten.** On the board of record F1 is the
> Littelfuse KLDR025.TXP (UL Class CC, 600 Vac, 200 kA) in 2 x 01250003H open clips (FAB-NOTE.md); there is no inlet fuse and F1 never
> opens at 15-25 A (CERTIFIER-CHECKLIST.md entries 11 and 13). Ask the lab: the open-clip acceptance (01250003H voltage rating and agency
> file), the tank-voltage RMS convention, and the abnormal-operation test with the firmware limit defeated. Drop the MDA-25-R
> interrupting-rating questions. Rewrite before sending; not sent.

# [Nameplate decided 2026-10-08: **120–127 V~ 60 Hz, US/Canada and Mexico from day 1**. Keep the 127 V-nominal questions, and add NOM (ANCE/NYCE) to the scope. **F1 is now a UL Class CC Littelfuse KLDR025.TXP (600 Vac, 200 kA, UL Listed) in 2 × Littelfuse 01250003H open PCB clips.** The interrupting-rating-at-127 V questions are moot; rewrite them to state the Class CC fuse. Keep the open-clip acceptance question (01250003H's voltage rating and agency file), and the heatsink-grade and tank-RMS questions.]

# Inquiry 2: F1 fuse interrupting rating at 127 V, to a certification lab

Status: draft, **not sent**. Prepared 2026-10-08 for the owner to send.
Gate: the native-21 FAB-NOTE.md requires "the certifier's confirmation that the 10 kA @ 125 Vac rating covers the 127 V (+6 %) corner (nominal-voltage rule), and Recognized-component / clip acceptance".

## Bottom line

- **Public sources don't settle this.** The standards say what a fuse's ratings mean and how they are tested. Whether an appliance certifier accepts a 125 Vac interrupting rating at a 127–132 V corner is an end-product judgment, so the inquiry is needed.
- **The voltage rating isn't the issue.** MDA-25-R is rated 125/250 Vac, so 132 V is within its voltage rating. The question is which **interrupting rating** applies between 125 V and 250 V: the 10 kA @ 125 Vac figure or the 1.5 kA @ 250 Vac figure.
- **The issue only bites above 1.5 kA.** The repo's bound for prospective fault current at the inlet is 4.26 kA (1.8 m cord) or 7.66 kA (1.0 m cord), with a zero-impedance source and a 14 AWG cord. Both exceed 1.5 kA, so the 125 V figure is the one that would have to apply. With a realistic 15 m branch the bound is about 0.46 kA, below even 1.5 kA. If the lab accepts a branch-circuit-impedance basis instead of the zero-impedance source, the question disappears.
- **Two things support accepting the 125 V figure for a 120 V nominal product:**
  - NEC 110.9 measures interrupting rating "at nominal circuit voltage";
  - the tri-national fuse standard tests interrupting capacity at rated voltage +5 %/−0 % recovery voltage, i.e. 125–131.25 V for a 125 V rating.
  The second shows only that the test may be run up to 131.25 V. It doesn't guarantee performance there, and the high-line corner (~132 V) lies above even that.
- **Possible bigger issue: is 127 V a rated voltage?** The repo treats 127 V in two ways.
  - FAB-NOTE.md calls 127 V a "+6 %" corner of 120 V.
  - Other documents give the target as "nominal US/Mexico 120/127 V" (`prototype-closure/round3/integration/README.md`), and ORACLE-ANSWER.md has a "Rated 127 V" column.
  - Mexico's standardized low-voltage system is 220Y/127 V. If the product is rated or marketed for 127 V nominal (NOM/Mexico), the nominal circuit voltage is 127 V. That is above 125 V, and the nominal-voltage argument then cuts **against** the 10 kA figure.
  - **The owner should decide which applies before sending.** The draft asks the lab to answer both cases.

## Facts of the design (from the repo)

- **Fuse:** F1 = Eaton Bussmann **MDA-25-R**, 25 A time-delay, 6.3 × 32 mm ceramic tube.
- **Ratings (Eaton Technical Data 2002, eff. Nov 2025):**
  - interrupting ratings, p.2: 10,000 A @ 125 Vac; 1,500 A @ 250 Vac; 10,000 A @ 125 Vdc;
  - agency scope, p.1: **cULus Recognized**, JDYX2/JDYX8, file E19180.
  - The MDA-20-R comparison part is cULus **Listed** (JDYX/JDYX7).
  - Owner's browser verification is in `sourcing/F1-J3-PARTS.md`, with screenshots `eaton-browser-2026-10-08/page2-ratings.jpg` and `page1-approvals.jpg`. Eaton's PDF refused automated fetch again today (timeout), so it was not re-read.
- **Clips:** 2 × **Littelfuse 01220088Z** (122 series, BeCu, tin), 30 A, UL file E14721, PCB through-hole, hand-soldered.
  - The repo cites Littelfuse 102/122 datasheet rev 06/26/18 p.1 for 30 A and "listed for 326-series fuses".
  - The clip voltage rating is not confirmed. Distributors disagree (250 V ac/dc vs 1 kV) [UNVERIFIED].
  - Is the clip's UL status Recognized (holders/clips category) or something else? [UNVERIFIED]
- **Position:** F1 is on the power-stage PCB, in line after the cord inlet (J1 L/N), ahead of the EMI filter and the GBJ2510 bridge rectifier.
  - The supply is a 15 A plug (NEMA 5-15P class), owner's choice 2026-10-08. Total input is capped at ≤ 15 A RMS by firmware.
  - An upstream inlet fuse or disconnect exists in the prototype pod: F0, proposed KLDR015.TXP, 15 A Class CC. Whether the production appliance keeps an upstream fuse is [owner to confirm].
- **Line envelope:** 120 V nominal; 127 V (+6 %) operating corner; ~132 V high line (+10 %). The front-end brief uses 108–140 V for design calculations (ORACLE-INSULATION-QUESTION.md).
- **Fault-current bound:** R23 `evidence/fuse/fault_current_bound.py` (enclosure session); figures as in the bottom line.

## Findings with sources

### Fuse standards: voltage rating, interrupting rating, test voltage

UL 248-1 is tri-national: the same text is NMX-J-009/248/1-ANCE and CSA C22.2 No. 248.1. The copy read is the **Second Edition, August 1, 2000** ([copy](http://u.dianyuan.com/bbs/u/31/1122353370.pdf)). The current edition may differ; clause numbers and values for the current edition are [UNVERIFIED].

| Clause (2000 ed.) | Text | Printed page |
| --- | --- | --- |
| 1.1.1 Scope | "low-voltage fuses rated 1000 V or less … These fuses are intended to be used in accordance with the Canadian Electrical Code, Part I (CEC), and the National Electrical Code, NFPA 70 (NEC)." | 11 |
| 2.3.15.1 Voltage rating | "The nominal rms AC and/or DC voltage for which a fuse is designed." | 15 |
| Interrupting rating (definition) | "…under specified conditions verified by operation at rated voltage tests." | ~14 |
| 5.2 Voltage rating | "For AC, the preferred values of voltage are 125, 250, 300, 480, or 600 V ac as specified for the particular fuse class." | 17 |
| 8.4 / Table 5, Verification of operation at rated voltage (AC) | Recovery voltage for the high-current, maximum-energy, threshold and intermediate tests: "**Rated voltage + 5 percent, - 0 percent**". Low-current tests: "Rated +20 percent voltage - 0 percent". Footnote d: "The recovery voltage may exceed +5 percent with the manufacturer's agreement." | 27 |
| Annex B4 Recovery voltage | Recovery voltage peaks "at least equal to √2 times the rms value of the rated voltage of the fuse" | B5 |

What this shows:
- A 125 Vac interrupting rating is demonstrated with recovery voltage between 125 V and 131.25 V.
- The standard defines the rating by **rated voltage**. It says nothing about applying a 125 V rating to a circuit above 125 V.
- 127 V lies inside the +5 % test window; 132 V does not.

UL 248-14 / CSA C22.2 No. 248.14 (Supplemental Fuses), current text [UNVERIFIED]:
- A search snippet of the standard preview reads: AC interrupting rating "10,000 A unless otherwise specified … A fuse rated 250 V ac may have a dual interrupting rating. This rating shall be 10,000 A at 125 V ac; the rest of the rating appears in Table A."
- The UL catalog lists an edition dated 2026-03-04, with clause 9.4 "Verification of operation at rated voltage". Part 1 applies unless modified.
- The full text is paywalled behind Cloudflare and was not read.

### Installation codes: the "nominal-voltage rule"

- **NEC 110.9:** "Equipment intended to interrupt current at fault levels shall have an interrupting rating at nominal circuit voltage sufficient for the current that is available at the line terminals of the equipment."
  - Reproduced from NEC 2014 in T. Domitrovich, "Marking Available Fault Current", IAEI Magazine, 2014-01-16 ([link](https://iaeimagazine.org/?p=8445)).
  - This is an installation rule for equipment connected to premises wiring. Whether the end-product standard or the certifier applies the same convention to a fuse *inside* an appliance is the core question [UNVERIFIED].
- **ANSI C84.1:** for a 120 V nominal system, Range A max is 126 V and Range B max is 127 V (service and utilization).
  - Secondary source: search summary of USDA RUS Bulletin 1724D-114, citing C84.1-2016. The primary was not opened (403) [UNVERIFIED verbatim].
  - So 127 V is the top of Range B on a 120 V system, and ~132 V exceeds both ranges.
- **Mexico:** NMX-J-098-ANCE-2014 standardizes 220Y/127 V. A reproduced table shows a 133.3 V maximum service voltage for the 127 V system.
  - Sources: [Catálogo Mexicano de Normas](https://platiica.economia.gob.mx/normalizacion/?p=38843); UNAM thesis table ([link](https://ru.dgb.unam.mx/bitstream/20.500.14330/TES01000659992/3/0659992_A1.pdf)). The values are from a secondary reproduction [UNVERIFIED against the 2014 text].
  - Note that the 2000 UL 248-1 copy is the NMX/CSA/UL tri-national text, so NOM certification would apply the same fuse rating definitions.

### Appliance standards (cooktops)

| Standard | What could be verified publicly | Open [UNVERIFIED] |
| --- | --- | --- |
| UL 1026 (household electric cooking and food-serving appliances, ≤ 250 V) | Scope only ([UL catalog](https://standardscatalog.ul.com/standards/en/standard_1026_6)). An Intertek summary references clause 41.1.14 test voltage | The test-voltage clause (in UL appliance standards, typically "rated 110–120 V → test at 120 V"); requirements for internal fuses / overcurrent devices and their interrupting ratings; Recognized-component acceptance |
| UL 858 (household electric ranges, incl. built-in cooktops) | Not retrieved | All. Which of UL 858 and UL 1026 applies depends on the product format (built-in vs countertop). The repo doesn't state the format; the 15 A cord-and-plug suggests countertop/UL 1026 |
| IEC 60335-2-6 / CAN/CSA-E60335-2-6:18 (R2023) | Scope covers "induction hobs, induction wok elements", rated up to 250 V single-phase. The CSA edition adopts IEC 60335-2-6:2014 with Canadian deviations, used with CAN/CSA-C22.2 No. 60335-1:16 ([CSA store](https://www.csagroup.org/store/product/2426252/), [ANSI](https://webstore.ansi.org/standards/csa/CSAE603352018)) | IEC 60335-1 test voltages: heating appliances at 1.15 × rated input (cl. 10/11), abnormal tests at 0.94/1.06 or 1.1 × rated voltage (cl. 19). Clause 24 component rules (fuses per IEC 60127/60269, used within ratings). Whether a UL 248-rated fuse is accepted under the CSA/IEC route. None was verified verbatim |
| UL 60335-2-6 | No published UL edition found | Whether one exists or applies |

### Recognized component and clip conditions

- **UL directory:** JDYX2 is "Fuses, Supplemental - Component" (Recognized); JDYX is Listed supplemental fuses.
  - A 2008 UL directory copy of JDYX2.E19180 ([interpower.com](https://www.interpower.com/docs/ur-e19180.pdf), "Last Updated on 2008-03-18") lists "Cat. Nos. MDA+, MDA-R+, 25-30A, 125/250 V ac, 125 V dc". The current Product iQ entry and its Conditions of Acceptability were not read (login).
- **JDYX2 Guide Information (conditions of acceptability, intended use)** wasn't retrievable [UNVERIFIED].
  - Practitioner statements, not UL text, from the IEEE EMC-PSTC list, May 2020 ([thread](https://www.mail-archive.com/emc-pstc@listserv.ieee.org/msg77281.html)): Recognized fuses carry "caveats about the device being only acceptable in the final equipment installation", and "Recognized overcurrent protectors are generally not acceptable for branch circuit protection".
  - F1 is a supplementary (internal) fuse, not branch-circuit protection, so a Recognized supplemental fuse is plausible, subject to the certifier.
- **Clip/holder:**
  - The MDA cartridge is used in open PCB clips, not a Listed/Recognized fuseholder assembly.
  - The lab must confirm several things: the clip's agency category and its voltage and current rating; that fuse + clip temperature rise at ~15 A RMS continuous is evaluated in the end product; and that the cartridge's I²t and arc containment are acceptable in clips (open mounting).
  - Eaton states melting I²t 734.7 A²s, typical.

## Draft message (ready to send)

**To:** UL Solutions, Intertek (ETL) or CSA Group: an engineering inquiry / preliminary review / project scoping contact. Use the lab's web inquiry or the account engineer if a project exists. Don't send to all three at once without deciding which mark is wanted.

**Subject:** Pre-submission question: 250 V supplemental fuse with 10 kA @ 125 Vac rating in a 120 V (127 V high-line) induction cooking appliance

> Hello,
>
> We are preparing a household induction cooking appliance for certification and would like your engineering view on one internal fuse before we freeze the design. Our product format is [countertop, cord-and-plug / built-in]. We believe the applicable standard is [UL 1026 / UL 858; CSA C22.2 No. … / CAN/CSA-E60335-2-6]; please correct us if not.
>
> **Product and supply**
> - Supply: single-phase 60 Hz, NEMA 5-15P cord. Rated **[120 V] / [120/127 V]** (please see question 4). Input ≤ 15 A RMS, enforced by the control.
> - We design for operation up to 127 V and a high-line condition of about 132 V (+10 %).
>
> **The fuse in question (F1)**
> - Eaton Bussmann **MDA-25-R**: 25 A, time-delay, 6.3 × 32 mm ceramic tube, UL 248-14 supplemental fuse.
> - Ratings per Eaton Technical Data 2002 (Nov 2025): voltage rating 125/250 Vac; interrupting ratings **10,000 A @ 125 Vac** and **1,500 A @ 250 Vac**.
> - Agency: **cULus Recognized, JDYX2/JDYX8, file E19180**.
> - Mounting: two **Littelfuse 01220088Z** PCB fuse clips (122 series, 30 A, UL file E14721), soldered to the main power PCB.
> - Location: F1 is the first device after the line cord, ahead of the EMI filter and bridge rectifier. It protects the internal power stage only; branch-circuit protection is the building's 15 A or 20 A breaker.
>
> **Available fault current**
> - Our calculation assumes an infinite (zero-impedance) source at the receptacle plus the cord. It gives a prospective fault current at F1 of **4.3 kA (1.8 m, 14 AWG cord)** to **7.7 kA (1.0 m cord)**.
> - Including about 15 m of branch wiring, it falls to about 0.46 kA.
>
> **Questions**
> 1. For a product rated 120 V nominal, will you accept the fuse's **10,000 A @ 125 Vac** interrupting rating as the applicable rating, including at the 127 V (+6 %) and ~132 V (+10 %) high-line conditions? We understand this as the convention that interrupting rating is judged at nominal circuit voltage (cf. NEC 110.9), and that UL 248-1 interrupting tests use recovery voltage of rated +5 %/−0 %.
>    If not, would the 1,500 A @ 250 Vac rating govern? In that case, what available-fault-current basis do you apply for a cord-connected appliance? Is it an infinite source at the plug, or a specified minimum branch-circuit impedance or standard test circuit? Please cite the clause.
> 2. Is a **Recognized (JDYX2)** supplemental fuse acceptable for this position, and under which Conditions of Acceptability?
>    For comparison, Eaton's MDA-20-R is cULus **Listed** (JDYX). Would a Listed fuse avoid any additional end-product testing?
> 3. Are the **Littelfuse 01220088Z** open PCB clips acceptable as the fuse holder (agency category, voltage rating, accessibility/replaceability, marking of fuse rating near the clips)? What tests will you run on the fuse-in-clip combination: temperature rise at rated input, abnormal operation, short-circuit?
> 4. **If we also rate the product for 127 V nominal** (Mexico, 220Y/127 V systems), the nominal circuit voltage exceeds the fuse's 125 Vac interrupting-rating voltage. Would you then require a fuse with an interrupting rating at ≥ 127 V (e.g. 250 Vac) adequate for the available fault current? Would the same answer apply under the NOM/NMX scheme?
> 5. Do you need anything else from us to answer: schematic, PCB layout, Eaton datasheet, our fault-current calculation, or an upstream-fuse coordination study?
>
> Please also tell us whether this can be answered as a free pre-submission question or needs a quoted engineering-consultation / preliminary-review project.
>
> Best regards,
> [Name], [Company]
> [email] · [phone]
> Attachments: Eaton Technical Data 2002 (MDA); Littelfuse 102/122 clip datasheet; fault_current_bound summary (one page)

## Owner choices before sending

- **The rated voltage on the nameplate:** 120 V only, or 120/127 V. This decides whether question 4 applies. FAB-NOTE.md's "+6 %" wording assumes 120 V only.
- **The target mark and lab:** cULus/UL Solutions, ETL/Intertek or cCSAus/CSA. Also the product format, which decides UL 1026 vs UL 858.
- **If the lab rejects the 125 V figure:** keep a fallback ready. The cheapest is to show available fault current ≤ 1.5 kA on a basis the lab accepts. Otherwise use a 25 A 6.3 × 32 fuse with ≥ 10 kA at 250 Vac (or at least the bounded current), or a current-limiting upstream fuse in a tested series combination. Check what the market offers before committing [UNVERIFIED].


## Added 2026-10-08: two more questions for the same lab inquiry

6. **Heatsink insulation grade (review M11).** The FET/bridge heatsink is PE-bonded (Class I). The controller's SELV return is also bonded to PE through R38, a single functional bond. Our provisional basis (D5-BASIS) requires the HOT↔PE barrier at the sink to stay *reinforced* with PE open. Is reinforced insulation required between HOT and the earthed sink, or does basic insulation plus protective earthing satisfy IEC 60335-1 / UL 60335 for this construction? The answer decides between standard per-device silicone pads (basic) and ceramic insulators (reinforced).
7. **Tank working voltage (review M6).** The resonant tank is line-modulated HF (≈ 35–60 kHz carrier under a 50/60 Hz envelope). At the 28 A ceiling the coil terminals see ≤ 362 V rms envelope-RMS (≤ 732 V pk) in normal use, with a pan; the no-pan clamp holds 22 A. A no-pan 28 A fault point reaches 409 V rms / 818 V pk.
   - **Question 1:** for creepage per IEC 60335-1 Table 18 / IEC 60664-4, which RMS convention applies: envelope RMS, or carrier-crest RMS (≈ 518–583 V rms)? The answer sets the board's tank creepage rule at 5.0 mm or at 6.3–7.4 mm.
   - **Question 2:** is the working voltage the normal-use (with-pan) value, or must it include the firmware-prevented no-pan 28 A point?
   - Evidence: `owner-items/m6m10/coil-voltage-28a/`.

## Added 2026-10-14: the one question that decides F1 (DECISIONS 32)

8. **Recognized supplemental fuse as the internal mains fuse.** Will the lab accept a UL-Recognized (cURus, UL 248-14 supplemental) 25 A fast-acting 6.3 × 32 mm ceramic fuse, rated 30 kA at 500 VAC, as F1 in place of the Listed Class CC KLDR025? The candidate is Bel Fuse 0ADEC9250-BE, file E20624. It would sit in PCB clips downstream of the cord, with a 4.7–8.4 kA prospective bound at 127 V + 10 %. If yes, for UL, CSA and NOM:
   - which conditions of acceptance apply;
   - whether the end-product short-circuit test must be run with it, and at what available current.
   - Evidence: `12-decisions/f1-data/f1_decision.py` (every technical gate passes; board-copper margin 3.61× against KLDR025's 0.99×), `12-decisions/f1-data/SURVEY.md`. Worth $18.86 per board.
