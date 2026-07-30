<!-- provenance: commit=8d1884031462fb2f5d41811c4165469067057f13 dirty=false -->

> **PARTIALLY SUPERSEDED (touch-current hedge only):** §2.5's rough
> two-term estimate that the 5.6nF `B81123C1562M000` alternative "plausibly
> exceeds" the 1.35mA touch-current budget (1389.5uA vs. 1350uA) was based
> on an incomplete leakage inventory. `docs/evidence/2026-07-30-c6-touch-current-budget-and-part2-routes.md`
> performs a corrected, full leakage-current accounting and reverses this:
> the 5.6nF part clears the touch-current budget with 9-15% headroom. This
> document's C6 **creepage** finding (§2.1, the false-solve correction of
> the 12.600mm "CONFIRMED" claim in the two prior part-selection docs) and
> the K1 (`RT33K012`) finding are unaffected.

# PD3 part-selection research: K1 (bypass relay) solved with real margin; C6
# (Y-capacitor) and T1 (current-sense transformer) have no verified drop-in
# that clears 12.6mm without a value/ratio change out of this task's scope

Base commit `8d188403` (`origin/main`). Worktree
`/Users/bennet/Desktop/temper-pd3-parts`, branch
`research/pd3-part-selection-k1-c6-t1`, created fresh from `origin/main`
per this task's hard rule. **Research and analysis only** -- no design
file, footprint, netclass, or safety constant touched; `git status --short`
clean apart from this document throughout. No part swapped in the design.

This document continues the PD3 part-selection thread already committed to
this session's scratchpad (not yet on `main`) in
`docs/evidence/2026-07-29-pd3-part-selection-verification.md` (K2/K3 = TE
RT114012, CONFIRMED; C6 = TDK B81123C1222M000, flagged by this task as a
**false solve**) and
`docs/evidence/2026-07-29-relay-60335-1-certification-resolution.md` (the
standards-mapping finding that a relay's IEC 61810-1 certificate cannot
substitute for the board's own pad-to-pad creepage measurement -- PCB
geometry is the decisive test, regardless of what a datasheet's front-page
"in accordance to IEC 60335-1" bullet claims). Those two documents'
methodology (manufacturer-primary dimensioned drawings, cross-checked
against real KiCad footprints where one exists, worst-case tolerance
applied, certificate *scope* read directly from the certifying body's own
database rather than trusted from a datasheet bullet) is followed here for
three different targets: **K1** (bypass relay), **C6** (Y-capacitor,
re-opened because the prior "CONFIRMED" verdict used a pad convention that
erases the part's own margin), and **T1** (current-sense transformer).

## Verdict up front

| Target | Verdict | Recommendation |
|---|---|---|
| **K1** | **SOLVED, real margin** | TE Schrack **RT33K012** (PN `2-1393240-3`), SPST-NO, 20A UL / 16A IEC, 12VDC/360R/400mW coil. PCB coil-to-contact spacing **17.8mm nominal** (worst-case ~17.6mm), clearing 12.6mm by **+5.0mm**, MEASURED against TE's own dimensioned drawing and cross-checked against a stock KiCad footprint built from the same datasheet family. |
| **C6** | **No verified drop-in exists at the required 2.2nF value; the 5.6nF alternative is not established as electrically safe either.** | TDK's own B81123 Y1 family (the part flagged as a false solve) offers a genuinely larger lead spacing (22.5mm, which would clear 12.6mm with large margin) **but only starting at 5.6nF -- 2.5x the spec'd 2.2nF +/-20% window**. No Y1-rated part at ~2.2nF with adequate lead spacing was found across TDK, Vishay (three ceramic-disc Y1 series), or KEMET. **Follow-up (Sec. 2.5): a rough touch-current cross-check against this project's own documented 1.35mA budget (`docs/hardware/IEC60335_CRITICAL_COMPONENTS.md`) suggests 5.6nF, stacked on the OVP divider's own documented worst-case fault current, plausibly exceeds that budget (~1.39mA vs. 1.35mA) -- a full leakage-current audit, not performed here, is a precondition before that part could be considered, not a formality.** |
| **T1** | **No verified drop-in exists that preserves the 1:100 ratio and current range -- but this is not a physics ceiling.** | Every PCB-trace-primary current-sense transformer found with a 1:100 ratio and >=50A sensed-current range (Coilcraft's own CST1211, CS4xxx, SCS families; TDK's B78419A) has *equal or smaller* primary-secondary creepage than the incumbent CST3015-100ED, despite some having higher hipot voltage ratings -- hipot rating and PCB creepage are not the same figure, the same lesson this project's evidence chain already learned from the relay case. **Follow-up (Sec. 3.5): donut/aperture-primary designs (Talema ASM, ICE Components CT07/CT08/CT10) have no PCB primary pin at all -- MEASURED for ICE CT07-1000, the primary is a wire/bus-bar threaded through the core's bore, so primary-to-secondary spacing becomes a board-layout choice, not a fixed component figure. This is a real redesign path (one burden-resistor value change, verified concretely: 4.99R -> 49.85R for a 1:1000 part at the same 50A trip point, plus a mechanical change to how the AC line is routed), not a dead end -- but the specific parts checked (ICE Components) lack a verified third-party reinforced-insulation certificate, so this path is not itself a solved recommendation.** |

---

## Provenance labels

Same convention as the two documents this one follows on from:

| Label | Meaning |
|---|---|
| **CITED-PRIMARY** | Manufacturer's own datasheet or a certifying body's own database, fetched and read this session. |
| **MEASURED** | Computed this session from a real file/drawing/footprint, method shown. |
| **DERIVED** | Arithmetic on labelled inputs, shown in full. |
| **UNVERIFIED** | Not established; flagged for a human. |

All PDFs fetched this session (`curl` with a browser user-agent, since
`WebFetch`'s default UA was refused with HTTP 403 by TDK, Coilcraft, and
Mouser alike -- the same workaround the prior verification doc used) are
saved under this session's scratchpad,
`/private/tmp/claude-501/-Users-bennet-Desktop-temper/413756c0-69f4-4db3-98b7-0b98b4a5e1f8/scratchpad/pdfs/`,
and are reproducible from the URLs cited in each section.

---

## 1. K1 -- the bypass relay, SOLVED

### 1.1 What K1 actually needs, read from `elec/src/modules.ato` this session

`bypass_relay` (`PowerInput` module, `elec/src/modules.ato:757-761`):
`coil_voltage = 12V`, `contact_current = 20A`, currently Omron
`G4A-1A-E DC12`, SPST (`Relay_SPST`), footprint
`temper:Relay_SPST_Omron-G4A-E`. Connections
(`elec/src/modules.ato:874-875`): `cmc.W1_2 ~ bypass_relay.COM`,
`bypass_relay.NO ~ d1.A` -- **only COM and NO are used, no NC contact
needed** (unlike K2/K3, which need the NC position). Per the task's own
framing and the docstring context: this relay bypasses the NTC inrush
limiter once soft-start completes, so it carries the **full steady-state
branch current continuously** (`ACMainsConstraints.i_max = 15A`,
`elec/src/constraints.ato:11`), not the 21.8mA the K2/K3 discharge relays
carry -- confirmed CITED-PRIMARY (`Omron G4A-1A-E DC12` datasheet via
DigiKey/Newark listings, fetched this session): SPST-NO, 12VDC coil,
**160 ohm / 75mA / 900mW**, 20A switching current, 80A motor-load surge.

### 1.2 Candidate: TE Schrack RT33K012 (same "RT1" case family already verified for K2/K3)

The task suggested checking the RT1-class part first. TE's **"Power PCB
Relay RT1 Inrush"** datasheet (Rev. 0415, fetched from
`https://www.enika.cz/data/files/RT3_serie.pdf`, CITED-PRIMARY -- despite
the document's title, the ordering codes are `RT3x`, and this is the same
physical case as the already-verified RT114012, confirmed below) covers
exactly this need: **1 pole, 16A, 1 Form C (CO) or 1 Form A (NO) contact,
for inrush peak currents up to 80A, 5kV/10mm coil-contact, reinforced
insulation.**

**Contact rating, CITED-PRIMARY (same datasheet):**

- "Rated current 16A ... Limiting continuous current 16A, **UL: 20A
  (K-version)**."
- Contact ratings table: **`RT33K`, A (NO), 20A, 277VAC general purpose,
  40C, UL508, 10x10^3 cycles** -- the AgNi90/10 ("K") contact-material
  variant is the one that carries the 20A UL rating; the AgSnO2 ("L")
  variant's table entries stop at 16A. **This is an exact match to
  `bypass_relay.contact_current = 20A`** on the same UL508 basis the
  incumbent Omron part is rated on.
- Breaking capacity 4000VA, far above this branch's ~1800W load.

**Coil, CITED-PRIMARY:** code `012` -> 12VDC, operate 8.4V, release 1.2V,
**360 ohm +/-10%, 400mW** -- identical to K2/K3's RT114012 coil (already
confirmed in the prior verification doc), but **different from the
incumbent G4A-1A-E's 160 ohm/75mA/900mW coil**. See 1.5 below -- this is a
real compatibility flag, not a paperwork detail.

**Ordering table, CITED-PRIMARY, same datasheet:** `RT33K012`, 1 Form A
(NO), AgNi90/10, monostable, 12VDC, TE part number **`2-1393240-3`**. (A
`RT33L012WG` "product in accordance to IEC 60335-1" variant also exists in
the same table, AgSnO2/16A-only -- consistent with the already-established
pattern that the "WG" suffix does not carry the specific certification
claim it markets; not pursued further since the K-version's UL 20A rating
is what this design actually needs, and the certification question is
independently settled in Track B of the relay-certification survey this
document builds on.)

### 1.3 PCB geometry -- MEASURED against TE's own dimensioned drawing

TE prints a dedicated **"PCB layout / terminal assignment"** figure for
"16A, 1 form A (NO) contact, pinning 5mm" (drawing ref `S0418-CV`, page 3
of the datasheet, rendered at 600dpi this session,
`rt3_pg3_hi-3.png`/`rt3_no_crop.png` in the scratchpad). Printed dimensions,
read directly off the drawing:

- Hole diameter: Ø1.3 (+0.1/-0) mm -- same as RT114012.
- Row pitch: **7.5 +/-0.2mm** -- same as RT114012.
- Contact-pin sub-pitch (the two contact pins, "11"/"14"): **5.04 +/-0.15mm**
  (printed once, vs. RT1's 3.5mm "pinning" printed twice for its 3-pin CO
  layout -- this NO relay only has 2 contact pins).
- Reference datum span (coil column to far contact pin): **20.3 +/-0.2mm**
  -- same printed value as RT114012's datum.
- Overall case length: **22.65 +/-0.2mm** -- same as RT114012's case.

These are the *same case-family dimensions* as the already-verified
RT114012 (row pitch, datum span, and overall length all identical); only
the contact sub-pitch differs (5.04mm here vs. 3.5mm for the CO/RT1
part), because this NO relay only needs 2 contact pins where the CO part
needs 3.

**Cross-check against a stock KiCad footprint**, same methodology as the
prior verification doc used for RT114012:
`/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints/Relay_THT.pretty/Relay_SPST_Schrack-RT1-16A-FormA_RM5mm.kicad_mod`
(its own `descr` field cites a TE RT2/RT1-family document URL; read
directly, not re-derived):

```
A1  (0, 0)                pad "11" (20.3, 0) AND (20.3, -7.5)   [same net, duplicate pad positions]
A2  (0, -7.5)              pad "14" (25.34, 0) AND (25.34, -7.5)  [same net, duplicate pad positions]
pad "11"/"14": oval 2mm(x) x 3mm(y), 1.3mm drill
pad "A1": rect 3mm(x) x 2mm(y), 1.3mm drill
pad "A2": oval 3mm(x) x 2mm(y), 1.3mm drill
```

The footprint reproduces TE's printed numbers exactly: `25.34 - 20.3 =
5.04mm` (matches the printed contact sub-pitch), and `20.3` matches the
printed datum span verbatim. **Governing (shortest, same-row) coil-to-contact
pair: A1 <-> pin "11", both at y=0, center-to-center 20.3mm.** Per EN 50005
numbering (already established for RT1: tens digit=pole, units 1=common),
pin "11" is COM -- the same pin used for K1's actual circuit
(`bypass_relay.COM`, `bypass_relay.NO`), so this is the pin pair that
actually matters electrically, not an unrelated one.

**Edge-to-edge, DERIVED:** A1 is a 3mm(x)-wide rect pad (half-width
1.5mm); pin "11" is a 2mm(x)-wide oval pad (half-width 1.0mm, since its
3mm dimension runs along y, the row direction, not x):

```
20.3mm (center-to-center) - 1.5mm (A1 half-width) - 1.0mm (pin-11 half-width) = 17.8mm
```

**Worst case, applying TE's own printed +/-0.2mm tolerance on the 20.3mm
datum** (pad sizes held fixed, since TE does not publish a pad-size
tolerance -- same treatment the prior RT114012 verification gave this
same case family):

```
(20.3 - 0.2) - 2.5 = 17.6mm
```

**Margin against 12.6mm: +5.0mm nominal, +5.0mm worst case** (rounding;
exact worst-case margin is +5.0mm). This is not a knife-edge pass --
it clears with more than 5mm to spare even under the manufacturer's own
printed tolerance, unlike the C6 case below. As with RT114012, TE does not
publish a recommended pad diameter (only the Ø1.3mm hole spec), so the
KiCad footprint's 2-3mm pad choice is a plausible, not mandated, choice;
a tighter pad would only *increase* this margin further.

### 1.4 Reinforced-insulation rating and certificate scope

**CITED-PRIMARY, same datasheet:** "Initial dielectric strength ...
between contact and coil: 5000Vrms. Clearance/creepage between contact and
coil: >=10/10mm. Material group of insulation parts: IIIa." **Approvals:
VDE Cert. No. 40007571, UL E214025, cCSAus 1142018** -- the **identical**
VDE certificate number already investigated in depth in
`docs/evidence/2026-07-29-relay-60335-1-certification-resolution.md`
(Track B), which read the certificate's own scope directly from VDE's
database: **EN/IEC 61810-1 only, no IEC 60335-1 reference**. That
document's standards-mapping conclusion applies unchanged here: the
internal 61810-1 rating (10mm coil-contact, 5kVrms) is real and solidly
certified, but it governs the relay's own internal path, not this board's
external pad-to-pad path -- the PCB geometry measurement in 1.3 above is
the test that actually answers this board's construction requirement, and
it passes with wide margin. The datasheet's own "WG version: product in
accordance to IEC 60335-1" front-page bullet is present on this datasheet
too and should be treated with the same skepticism already established --
not cited here as a certification claim.

### 1.5 Electrical compatibility -- one real flag, not a blocker

**Contact/coil topology, contact rating, and reinforced-insulation basis
all match or improve on the incumbent.** The one place this is *not* a
transparent drop-in: **the coil differs substantially**. Incumbent
(Omron G4A-1A-E DC12): 160 ohm / 75mA / 900mW. Recommended (RT33K012):
360 ohm / 33.3mA / 400mW. The existing driver circuit
(`elec/src/modules.ato:767-772`, `r_relay_drop`, 39 ohm/1W, feeding the
coil from the 15V rail) was sized for *some* coil -- DERIVED, with
RT33K012's 360 ohm coil: `I = 15V / (360+39) = 37.6mA`, `V_coil = 37.6mA x
360R = 13.5V`, **112.7% of the 12V rated coil voltage**, above the typical
80-110% continuous-operation window IEC 61810-1 "Operative range Category
2" implies for this relay class. **This is a real design flag a human
should resolve before this part is designed in** (re-tune or remove
`r_relay_drop`) -- it does not affect the PCB-geometry or certification
findings above, but it is not a zero-change swap either. Flagged here per
the task's "electrical compatibility with the incumbent's role"
requirement; not fixed, per the "no design file touched" hard constraint.

### 1.6 Stock

DigiKey lists `RT33K012` (DigiKey part `PB2347-ND`, TE part `2-1393240-3`)
as orderable ("order today, ships today" per the product listing fetched
this session) -- CITED-SECONDARY (distributor page, used only for
stock/orderable confirmation per this task's evidence standard, not for
any dimensional or certification claim).

---

## 2. C6 -- the Y-capacitor, no verified drop-in at the required value

### 2.1 Why the prior "CONFIRMED" verdict is a false solve, restated

`docs/evidence/2026-07-29-pd3-part-selection-verification.md` computed two
numbers for TDK B81123C1222M000 (15.00mm lead spacing, 2.2nF, Y1/500VAC):
**12.600mm** using the stock KiCad footprint's 2.4mm pad (`15.00 - 1.2 -
1.2`), and **13.500mm** using a smaller, non-stock 1.5mm pad derived from
the part's 0.8mm lead diameter by a standard annular-ring convention. This
task's framing is correct that the *first* number is the one that actually
governs if this project's standing convention (stock KiCad footprints with
2.4mm pads, the same convention `c_x2`'s
`C_Rect_L18.0mm_W7.0mm_P15.00mm_FKS3_FKP3` footprint uses elsewhere in this
same file, `elec/src/modules.ato:725-741`) is applied consistently, and
that TDK's own printed **+/-0.4mm lead-spacing tolerance** (`tdk_b81123.pdf`
page 2, "Lead spacing 15, 22.5 -> +/-0.4") erodes even the 13.500mm number:
worst case `15.00 - 0.4 - 2.4 = 12.2mm`, **below 12.6mm**. This document
treats 12.2mm-vs-13.500mm as the same part either way -- the part itself
is unchanged; only the pad convention applied to it differs, and neither
number has genuine margin once tolerance is stacked onto the 2.4mm-pad
convention.

### 2.2 TDK's own B81123 family: a genuinely bigger lead spacing exists, but not at this value

**CITED-PRIMARY**, `tdk_b81123.pdf` (TDK B81123 datasheet, "Y1 / 500 V AC",
dated June 2026, fetched this session), ordering table read directly:

```
Lead spacing   CR (uF)    Max dimensions (mm)     Ordering code
15             0.0010     5.0 x 10.5 x 18.0        B81123C1102M***
               0.0015     6.0 x 11.0 x 18.0        B81123C1152M***
               0.0022     7.0 x 12.5 x 18.0        B81123C1222M***   <- current C6 pick
               0.0033     8.5 x 14.5 x 18.0        B81123C1332M***
               0.0047     9.0 x 17.5 x 18.0        B81123C1472M***
22.5           0.0056     7.0 x 16.0 x 26.5        B81123C1562M***  <- 22.5mm tier starts here
               0.0068     8.5 x 16.5 x 26.5        B81123C1682M***
               0.010     10.5 x 18.5 x 26.5        B81123C1103M***
```

**This is the load-bearing finding for C6.** The 22.5mm-lead-spacing tier
of TDK's own Y1 family exists and would clear 12.6mm with very large margin
-- DERIVED, same 2.4mm-pad convention: `22.5 - 0.4 - 2.4 = 19.7mm`, +7.1mm
over 12.6mm even worst-case. But **it only starts at 0.0056uF (5.6nF)** --
**2.5x the 2.64nF upper bound of `y_cap_pe.value = 2.2nF +/- 20%`**
(`elec/src/modules.ato:915`). The lead-spacing/case-size jump is tied
directly to capacitance in this film-capacitor family (larger C needs more
film, hence a longer case, hence the next lead-spacing tier) -- it is not
an independently selectable option at the same value. Approvals for the
whole datasheet (both tiers, one document): **ENEC-05495** (EN IEC
60384-14:2023) and **UL E97863 / CSA E60348-14** -- granted, not pending,
same certs already verified for the 15mm tier in the prior document;
nothing in the datasheet scopes these certs to only one lead-spacing tier,
though the certificate database itself was not independently queried this
session to confirm the full CR range each cert actually covers (flagged
in UNVERIFIED, section 4).

**Whether a 5.6nF Y1 capacitor is functionally acceptable in this circuit's
role was not evaluated here** -- it is a real electrical value change (EMI
corner frequency and touch/leakage current both scale with capacitance:
DERIVED, leakage at 250VAC/50Hz: 2.2nF -> ~0.17mA, 5.6nF -> ~0.44mA), and
changing it is exactly the kind of "swap the part" decision this task's
hard constraints put out of scope for this pass. It is reported here as
the closest same-manufacturer, same-certificate, genuinely-margined
alternative TDK's own catalog offers, not as a recommendation to adopt
without that separate review.

### 2.3 Every other Y1 family checked tops out well short of genuine margin

**Ceramic-disc Y1 capacitors cap out at 12.5mm lead spacing, independent of
manufacturer or capacitance** -- checked across three separate Vishay
BCcomponents disc-Y1 series this session, all CITED-PRIMARY datasheets:

- **VY1 series** (`vishay_vy1.pdf`, doc 28537, incumbent's own family --
  the currently-installed VY1222M47Y5UQ6TV0 is this series): "leads having
  a lead spacing of 10.0 mm, or 12.5 mm" -- printed once, for the *entire*
  capacitance range (10pF to 4.7nF) the datasheet covers.
- **WKP series** (`vishay_wkp.pdf`, doc 22206): "leads having a lead
  spacing of 10.0 mm or 12.5 mm" -- identical statement, different case
  style, same ceiling.
- **AY1 series** (`vishay_ay1.pdf`, doc 28563, automotive-grade): same
  "10.0 mm and 12.5 mm" ceiling, printed ordering table confirms every row
  from 470pF to 4.7nF uses "10 or 12.5" spacing, no exceptions.

12.5mm cannot clear 12.6mm even before any tolerance or pad allowance is
subtracted -- these three families are disqualified on the nominal figure
alone, not even reaching the false-solve territory the film part did.

**KEMET's AH-type Y1 line** (`kemet_c1067.pdf`, doc `C1067_X1_400_VAC_
Y1_250_VAC`): 10.0mm lead spacing only, one option, "Class X1/Y1" --
smaller than the incumbent, not a candidate.

**No genuinely large-lead-spacing (>=18mm) Y1 film capacitor at ~2.2nF was
found at any other manufacturer checked** (Panasonic's film-safety-capacitor
catalog PDF timed out on fetch and was not successfully retrieved this
session -- see UNVERIFIED; WIMA's small-value safety line (MP3-Y2, the only
WIMA safety-cap datasheet actually retrieved this session) is **Y2, not
Y1**, and its own lead-spacing note caps standard taping support "up to and
including PCM 22.5" but the datasheet found was Y2/300VAC, not Y1 --
WIMA's Y1 offering, MP3-Y1, could not be located as a fetchable primary
datasheet this session, only a distributor listing; not used as a basis
for any claim here).

### 2.4 Bottom line for C6

**No Y1-rated capacitor at 2.2nF +/-20% (1.76-2.64nF) with lead spacing
capable of clearing 12.6mm with genuine margin under this project's own
pad convention was found.** This is reported as a real "no suitable part
exists at spec" finding, not a gap in search effort -- the physical
pattern (ceramic-disc Y1 caps hard-capped at 12.5mm industry-wide; film Y1
caps' lead spacing tied to capacitance, with large spacing arriving only
well above the required value) was confirmed across enough independent
manufacturers and series that it reads as a real market constraint, not
missing coverage. **The only path to genuine margin found this session is
TDK's own 22.5mm-tier B81123C1562M000 (5.6nF, same series/certs/manufacturer),
which requires accepting a 2.5x capacitance increase and a separate
leakage-current/EMI-corner re-verification** -- a decision for a human, not
resolved here.

### 2.5 Follow-up: does the *circuit* actually tolerate 5.6nF, or was this only "a part exists"?

The analysis in 2.2-2.4 established that a 5.6nF Y1 part *exists* with
genuine PCB margin. It did not, as first written, check whether this
design's actual touch-current budget can absorb 2.5x C6's leakage --
that is a different question, and answering "a drop-in exists" without
answering it would overstate how solved C6 is. This section is a
same-session follow-up, done after the fact and clearly labelled as such.

**The governing limit, already established elsewhere in this repo, not
re-derived here:** `docs/hardware/IEC60335_CRITICAL_COMPONENTS.md:66`
(CITED-SECONDARY, an existing project document, re-read this session, not
independently re-verified against the standard) states the applicable
touch-current limit for this appliance is **1.35mA** (IEC 60335-2-6,
0.75mA/kW capped at 5mA, at this design's 1.8kW rating), and that the
`OVPComparator` protective-impedance dividers alone already draw, by that
same document's own arithmetic: **normal 130.1uA (comparator-sense) /
328.8uA (ADC-sense); worst single/double-fault case 380.4uA
(comparator-sense) / 949.7uA (ADC-sense)** -- i.e. the ADC-sense divider's
*own* documented worst-case fault current is already **949.7uA, 70% of the
1.35mA budget, on its own, before any Y-capacitor leakage is added.**

**DERIVED, this session, C6's own standalone leakage** (`I = V * 2*pi*f *
C`, 250VAC/50Hz, the node's own voltage rating): at **2.2nF: 172.8uA**; at
**5.6nF: 439.8uA**.

**Stacked against the ADC-sense divider's documented worst-case fault
current (the same "single fault condition" touch-current evaluation IEC
60335-1 requires -- normal leakage from undisturbed paths plus the fault
current from the one faulted path), DERIVED:**

```
2.2nF:  949.7uA + 172.8uA = 1122.5uA   (83% of 1.35mA budget, ~227uA / ~1.2x margin)
5.6nF:  949.7uA + 439.8uA = 1389.5uA   (EXCEEDS the 1.35mA budget by ~40uA)
```

**This is a rough, two-term estimate, not a full leakage-current budget --
it omits the X2 cap (`c_x2`), the CMC's own winding-to-winding
capacitance, the MOV, and any other stray-capacitance contributors that a
real IEC 60335-1 leakage-current test would include.** Adding any of those
in only makes both numbers worse, not better. **Direct answer to the
question asked: no, this was not evaluated before this follow-up, and now
that it has been (at this rough-estimate level), the 5.6nF alternative
looks like it plausibly exceeds this design's own documented touch-current
budget on its own, without even counting the other omitted leakage paths
-- and the incumbent 2.2nF value itself has less headroom against that
budget (~1.2x) than the "3.5x-10x margin" language in
`IEC60335_CRITICAL_COMPONENTS.md` might suggest at a glance, because that
margin figure describes one divider's normal-vs-fault range in isolation,
not the combined total once C6's own leakage is stacked on top.** This
changes the finding's character: it is not "no 2.2nF part exists, but a
5.6nF one would work fine" -- it is "no 2.2nF part exists with genuine PCB
margin, and the one larger-spacing alternative found is not established as
electrically safe either, pending a real full-budget leakage-current
audit this session did not do." A human evaluating the 5.6nF option should
treat that audit as a precondition, not a formality.

---

## 3. T1 -- the current-sense transformer, no verified drop-in at matching ratio/current

### 3.1 What T1 needs, read from `elec/src/modules.ato` this session

`CurrentSensing.ct` (`elec/src/modules.ato:1652`): `CST3015_100E`
(Coilcraft `CST3015-100ED`), 1:100 ratio, 88A sensed rating. `r_burden`
(4.99 ohm) sets the OCP trip at 50.1A (worst-case 48.77-51.16A per
`docs/evidence/2026-07-27-ocp01-uvl02-part-resolution.md`, cited in the
component's own docstring), leaving 1.73x headroom to the 88A sensed
rating. The docstring is explicit about *why* this margin matters: the
prior part (CST2010-100L, 47A sensed) was rejected specifically because a
50.1A trip point sat *above* its rated sensed current, where core
saturation could make the secondary under-read and the OCP trip late or
not at all. **Any replacement must sense meaningfully above 50A, not just
above the 15A steady-state branch current**, or this exact failure mode
recurs. Task-measured incumbent PCB spacing: 9.100mm, fails 12.6mm.

### 3.2 Coilcraft's own broader catalog: nothing bigger than CST3015 was found

Checked this session, all CITED-PRIMARY (Coilcraft datasheets, fetched via
`curl` after `WebFetch` was refused with HTTP 403 on coilcraft.com):

- **CST1211 series** (`coilcraft_cst1211.pdf` + search-confirmed
  datasheet): sensed current **28A max** (below even the 50A trip point --
  same disqualifying failure mode as the already-rejected CST2010, and
  worse), and creepage **9mm Pri/Sec, 8mm clearance** -- smaller package,
  smaller creepage, smaller current range than the incumbent. Not a
  candidate on any axis.
- **CS4xxx series** (`coilcraft_senhitr.pdf`, Coilcraft Document 132,
  "Current Sense Transformers"): includes a genuine 1:100 part,
  `CS4100V-01L`. Higher hipot rating (3750Vrms vs. CST3015's 5000Vrms --
  actually *lower*) but explicitly **"3 mm creepage/clearance between
  primary and secondary windings"** -- printed directly on the datasheet's
  own front matter, a third of the incumbent's 8mm. Sensed current only
  **35A max**, also below the 50A trip point. Disqualified on both current
  range and creepage.
- **SCS series**: sensed current up to only 30A per its own product page
  (below the 50A trip point); creepage figure not found in the pages
  fetched this session (flagged UNVERIFIED, not pursued further once the
  30A ceiling alone disqualified it on current range).

**The pattern across Coilcraft's own catalog: higher hipot voltage rating
does not track with more PCB creepage.** CS4xxx's 3750Vrms hipot with only
3mm creepage, next to CST3015's lower 5000Vrms-vs-CS4xxx-3750Vrms... (the
CST3015 figure is in fact the *higher* hipot number, 5000Vrms, and also
the higher creepage number, 8mm nominal / 9.1mm measured) shows hipot and
PCB creepage are two different figures a datasheet reports, governed by
different internal construction choices -- the same lesson this project's
evidence chain already learned from the relay case (a relay's internal
5kV/10mm rating does not settle its external PCB pad spacing either).
**Within Coilcraft's own current-sensing lineup, CST3015 already appears
to be the highest-PCB-creepage, 1:100-ratio, >=50A-sensed part they sell.**

### 3.3 Other manufacturers: same conclusion

- **TDK B78419A** (`tdk_b78419a.pdf`, "SMT current sense transformers,
  EP11 core"): "Np (mould-in) / Ns (CuL) creepage >=6mm, clearance
  >=3.9mm"; "sensed current: Iprim, the primary current of 30A causes
  approx +40C" -- both smaller creepage and smaller current range than the
  incumbent.
- **Talema ASM series** (`talema_asm.pdf`): a fundamentally different
  mechanical construction -- "the conductor carrying the current to be
  measured functions as a one turn primary," i.e. a donut/aperture core
  the mains wire (or a bus bar) is threaded through, with **no PCB primary
  pin at all**. This decouples primary-secondary PCB creepage from the
  problem entirely (the relevant distance becomes bore-to-secondary-pin,
  not pad-to-pad), which is a genuinely different and potentially
  effective *mechanism* -- but the ASM-050/075/100 (the current-range-
  appropriate models, per the family's "primary current ratings from 1 to
  100A" spec) uses a high-turn-count secondary sized for a mA-level output
  into a fixed burden, not a 1:100 current-ratio part: DERIVED from the
  datasheet's own ASM-100 response curve (~135mV across a 220 ohm burden
  at 100A primary) -> secondary current ~0.61mA at 100A primary -> an
  effective ratio near **1:163,000**, not 1:100. Using this part would mean
  redesigning the burden resistor and the OCP comparator's reference
  divider from scratch, not a drop-in swap -- out of this task's scope,
  flagged as a possible path for a human to evaluate separately, not
  recommended here.
- **ICE Components CT07/CT08/CT10 series** (`ice_ct07.pdf` +
  product-page fetches): same donut/aperture, single-turn-primary
  construction as Talema (CT07 explicitly: "1:1000 (single-turn primary)",
  200A reference rating "limited by the current capacity of the
  customer-supplied primary conductor"; CT08: fixed 1:1200 ratio, 50A).
  Both wrong ratio by an order of magnitude for the same reason as ASM,
  **and** neither datasheet cites a third-party reinforced-insulation
  certificate (VDE/ENEC/CB) -- only "Hi-Pot tested" (a manufacturer's own
  test, per CT07's datasheet note 8: "Tested @ 60Hz, 1mA," no certificate
  number) and a UL-94V-0 flammability mark, which is a materials-
  flammability rating (the same clause-30.2-style claim this project's
  evidence chain already learned to distinguish from clause-29 insulation
  coordination, in the relay research). **Disqualified on both ratio
  mismatch and certification standard**, independent of whatever creepage
  their mechanical drawings show (not extracted this session, since the
  ratio mismatch alone was already disqualifying).

### 3.4 Bottom line for T1

**No current-sense transformer was found this session that simultaneously
(a) uses a PCB-trace primary matching the incumbent's mechanical
integration, (b) preserves the 1:100 turns ratio this design's burden
resistor and OCP comparator reference are built around, (c) senses
meaningfully above the 50A OCP trip point (not just the 15A steady-state
current), and (d) clears 12.6mm primary-to-secondary PCB spacing with
genuine margin on a manufacturer-dimensioned drawing.** Coilcraft's
CST3015-100ED -- the incumbent -- appears from this session's research to
already be the highest-creepage part meeting (a)-(c) in Coilcraft's own
catalog, and no other manufacturer checked (TDK, Talema, ICE Components)
beat it while also meeting (a)-(c). The donut/aperture-primary designs
(Talema ASM, ICE CT07/08/10) are a genuinely different *mechanism* that
could plausibly solve the PCB-creepage problem by construction (no PCB
primary pin to have a pad-to-pad path at all) but require a full
redesign of the ratio, burden, and OCP reference circuit, and (for the ICE
parts specifically) lack a verified third-party insulation certificate --
flagged as a possible direction for a human to pursue as a separate,
larger redesign, not reported as a solved target.

### 3.5 Follow-up: is T1's blocker a physics ceiling, or only a ratio/current-range mismatch?

Section 3.3 named the donut/aperture-primary parts (Talema ASM, ICE CT07/
08/10) but had not extracted their actual mechanical dimensions, since the
ratio mismatch alone was already disqualifying against this task's
"matching turns ratio" instruction. Following up specifically to answer
this: **it is not a physics ceiling.**

**MEASURED this session**, ICE CT07-1000 datasheet mechanical drawing
(`ice_ct07.pdf` page 1, rendered at 300dpi, `ice_ct07_pg1-1.png`): the part
has **three pins total (1, 2, 3), all secondary** -- the schematic on the
same page shows the primary as leads "A"/"B" drawn as a dashed wire
threaded through the core's Ø9.20mm bore, not a PCB pad at all. **There is
no "primary PCB pin" for this part -- the primary conductor is whatever
wire or bus bar the designer routes through the bore.** This means the
question "what is the primary-to-secondary PCB creepage" stops being a
fixed, component-supplied number and becomes a **board-layout choice**:
the designer controls how close the primary conductor's own routing comes
to the secondary pins (1/2/3, clustered at 7.62mm x 7.62mm per the
datasheet's recommended PCB layout), and can make that distance as large
as the board allows. **This is a mechanism, not a part-selection ceiling
-- the same category of solution the task description already flagged for
U3/U7 ("need a different isolation mechanism"), just discovered here for
T1 rather than assigned to it up front.**

**What changing mechanism would actually require, worked through
concretely rather than left abstract:** the existing OCP circuit's trip
point is set by burden resistor and a fixed comparator-reference voltage
window (2.4-2.6V at the design's 500mA-referred trip current,
`elec/src/modules.ato`, `CurrentSensing`/`OCPComparator`). Swapping to a
1:1000-ratio part (CT07) and keeping the same 50A primary trip point:
DERIVED, `R_burden_new = V_ref / (I_prim_trip / ratio) = 2.4925V /
(50A/1000) = 2.4925V / 0.05A = 49.85 ohm` (vs. the current 4.99 ohm) --
**a single resistor value change**, not a cascading redesign, and it
*reduces* continuous burden dissipation at the 15A steady-state current
(`I_sec = 15mA`, `P = I^2*R = 0.015^2 * 49.85 = 11.2mW`, well under the
current 112mW). **The larger lift is mechanical, not electrical**: routing
the AC line as a discrete conductor through the CT's bore instead of as
continuous PCB copper, which changes how the primary connects to the rest
of the L-path (fuse, MOV, CMC, NTC, bypass relay) -- a real layout/assembly
change, not a "no such part exists" dead end.

**This does not make CT07 itself a recommendation.** Per 3.3, it still
lacks a verified third-party reinforced-insulation certificate (only
"Isolation Voltage (Hi-Pot) 3750VAC" as a manufacturer-stated test result,
plus UL-94V-0 flammability and "Material Group UL CTI 3" -- no VDE/ENEC/CB
certificate number was found for any ICE Components CT part this session),
which is a separate, still-open gap from the geometry question this
follow-up answers. **Direct answer to the question asked: the blocker is
that no part was found matching the *current* ratio/current-range
*and* clearing 12.6mm -- not that no part exists with adequate creepage at
all. A mechanism change (donut primary, off-PCB conductor routing) is a
real, electrically modest (one-resistor) redesign path that would very
plausibly clear 12.6mm by construction, at the cost of a mechanical
layout change and a still-unresolved certification gap on the specific
parts checked.**

---

## 4. UNVERIFIED (explicit list)

- **C6**: whether TDK's ENEC-05495 / UL E97863 certificates for the
  B81123 series cover the full CR range printed in one datasheet
  (including the 22.5mm/5.6nF+ tier) or only a sub-range, was not
  independently confirmed against the certificate-issuing body's own
  database this session (the datasheet's own Approvals section does not
  print a CR-range qualifier the way, e.g., Vishay's AY1 datasheet does
  for its VDE mark -- "470 pF to 4.7 nF" -- so this is a real gap, not
  an assumption stated as fact).
  - Panasonic's plastic-film-capacitor catalog PDF (`S_Film_cap_catalog_
    e.pdf`) timed out on fetch (>2 min) and was not successfully retrieved
    this session; Panasonic's Y1 film-safety-capacitor lineup (if a
    distinct series from the X2/Y2 ECQUL/ECQE lines that *were* found) was
    not checked. A real gap, not a "no part exists" finding for Panasonic
    specifically.
  - WIMA's MP3-Y1 (2200pF, referenced only by a distributor listing this
    session, not a fetched primary datasheet) was not independently
    verified -- no claim is made about it here.
- **K1**: RT33K012's max 20ms making-current rating is stated in the
  datasheet as "80A, RT33L version" specifically (the AgSnO2 contact
  material) -- the datasheet does not separately restate this figure for
  the K (AgNi90/10) version this document recommends. Likely a non-issue
  given the NTC inrush limiter is already closed and current-limiting
  before this relay's contacts close (per the design's own bypass
  sequencing), but not independently confirmed for the K-version
  specifically this session.
  - VDE 40007571's certificate scope was not re-fetched from VDE's
    database this session (already fetched and read directly in
    `docs/evidence/2026-07-29-relay-60335-1-certification-resolution.md`
    for the same certificate number); this document relies on that prior
    fetch rather than re-querying, on the basis that it is the identical
    certificate number printed on both datasheets.
- **T1**: SCS series creepage/clearance figure was not extracted (its 30A
  sensed-current ceiling alone was sufficient to disqualify it before that
  became necessary). ICE Components CT07/08/10's actual mechanical-drawing
  creepage numbers were not extracted from the PDF (a vector graphic, not
  text) since the ratio mismatch and missing third-party certificate were
  independently disqualifying; a human pursuing the donut-primary
  redesign path would need those numbers.

## Hard-constraint compliance

- **No design file, constant, footprint, or netclass modified.** Only this
  document was written this session; `git status --short` clean apart from
  it.
- **Own git worktree**, `/Users/bennet/Desktop/temper-pd3-parts`, branched
  fresh from `origin/main` at `8d188403`, not a shared/pre-existing
  worktree.
- **No `git stash`** used.
- **No sub-agents spawned** this session, per the task's explicit
  instruction (several agents on this same task today stalled after doing
  the work but before committing when they spawned sub-agents).
- **No part swapped, no 12.6mm relaxation proposed, no domain
  reclassified.** K1's recommendation is reported with its one real
  compatibility flag (coil mismatch) stated plainly, not smoothed over.
  C6 and T1 are reported as unsolved at the exact required spec, with the
  closest same-family alternative shown and explicitly marked as requiring
  a separate value/ratio-change decision, not silently substituted.
- Not pushed, no PR opened.

## Sources (fetched this session; local copies under this session's
scratchpad `/private/tmp/claude-501/-Users-bennet-Desktop-temper/
413756c0-69f4-4db3-98b7-0b98b4a5e1f8/scratchpad/pdfs/`)

- TE "Power PCB Relay RT1 Inrush" (RT3x ordering codes), Rev. 0415 --
  `https://www.enika.cz/data/files/RT3_serie.pdf` (`rt3.pdf`,
  `rt3_pg3_hi-3.png`)
- Stock KiCad footprint (KiCad 10,
  `/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints/`):
  `Relay_THT.pretty/Relay_SPST_Schrack-RT1-16A-FormA_RM5mm.kicad_mod`
- Omron G4A-1A-E DC12 coil spec -- DigiKey/Newark/Octopart listings
  (CITED-SECONDARY, coil R/I/P figures only)
- DigiKey `RT33K012` (`PB2347-ND`) stock listing (CITED-SECONDARY, stock
  confirmation only)
- TDK B81123 Y1/500VAC datasheet, June 2026 --
  `https://www.tdk-electronics.tdk.com/inf/20/20/db/fc_2009/Y1_B81123.pdf`
  (`tdk_b81123.pdf`)
- TDK B3202*A3/B3/C3 Y2/300VAC datasheet, June 2026 --
  `https://www.tdk-electronics.tdk.com/inf/20/20/db/fc_2009/Y2_B32021_026.pdf`
  (`tdk_y2_b32021_026.pdf`)
- Vishay VY1 Series, rev. 18-Aug-2025 --
  `https://www.vishay.com/docs/28537/vy1series.pdf` (`vishay_vy1.pdf`)
- Vishay WKP Series -- `https://www.vishay.com/docs/22206/wkp.pdf`
  (`vishay_wkp.pdf`)
- Vishay AY1 Series, rev. 12-May-2025 --
  `https://www.vishay.com/docs/28563/ay1series.pdf` (`vishay_ay1.pdf`)
- KEMET C1067 (AH type, X1 400VAC/Y1 250VAC) --
  `https://content.kemet.com/datasheets/KEM_C1067_X1_400_VAC_Y1_250_VAC.pdf`
  (`kemet_c1067.pdf`)
- WIMA MP 3-Y2 (Farnell-hosted archival copy) --
  `https://www.farnell.com/datasheets/309337.pdf` (`wima_mp3_farnell.pdf`)
- Coilcraft Document 132, "Current Sense Transformers" (CS4xxx family) --
  `https://www.coilcraft.com/getmedia/d17a2738-6771-49e9-8bde-a53c8e05be0b/senhitr.pdf`
  (`coilcraft_senhitr.pdf`)
- TDK B78419A (EP11 core) SMT current sense transformer --
  `https://product.tdk.cn/system/files/dam/doc/product/transformer/transformer/current-sense/data_sheet/85/ds/b78419a_ep11.pdf`
  (`tdk_b78419a.pdf`)
- Talema ASM Series 50/60Hz Current Sensors --
  `https://talema.com/wp-content/uploads/datasheets/ASM.pdf`
  (`talema_asm.pdf`)
- ICE Components CT07 Series datasheet --
  `https://www.icecomponents.com/wp-content/uploads/2023/10/CT07-Series-Datasheet_20260422.pdf`
  (`ice_ct07.pdf`), CT08/CT10/CT11 product pages
  (`icecomponents.com/product/ct08-series/`, etc.)
- In-repo: `elec/src/modules.ato`, `elec/src/constraints.ato`,
  `docs/evidence/2026-07-29-pd3-part-selection-verification.md`,
  `docs/evidence/2026-07-29-relay-60335-1-certification-resolution.md`,
  `docs/evidence/2026-07-30-pollution-degree-determination.md`,
  `docs/evidence/2026-07-27-ocp01-uvl02-part-resolution.md`.
