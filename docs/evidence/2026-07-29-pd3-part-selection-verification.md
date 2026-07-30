<!-- provenance: commit=ed5ee134bc0ef1bdcb64a884af266afd66314529 dirty=false -->

> **SUPERSEDED (C6 finding only):** this document's "CONFIRMED" verdict on
> TDK/EPCOS `B81123C1222M000` at exactly 12.600mm is a **false solve** —
> that figure is the nominal-tolerance boundary case, not a margined pass.
> At the part's own published lead-spacing tolerance (15.00mm ±0.4mm), the
> worst-case achievable gap is 12.2mm, below the 12.6mm requirement. See
> `docs/evidence/2026-07-30-pd3-part-selection-k1-c6-t1.md` §2.1 for the
> corrected analysis. The K2/K3 (`RT114012`) verification in this document
> is unaffected.

# PD3 part-selection survey verification: TE RT114012 (K2/K3) and TDK
# B81123C1222M000 (C6) checked against manufacturer-authoritative sources

Base commit `ed5ee134` (`origin/main`, "fix(evidence): repair provenance
stamps on two docs failing the gate (#454)"). Branch
`docs/verify-pd3-part-selection`, worktree created fresh from `origin/main`
per this task's hard rule. **Verification/research only** -- no design file,
constant, footprint, or netclass touched; `git status --short` clean apart
from this document throughout.

This document checks two claims made in
`docs/evidence/2026-07-29-pd3-part-selection-survey.md` (branch
`docs/pd3-creepage-part-selection`, not yet on `main`) against manufacturer
primary sources, per the standard of evidence set by
`docs/evidence/2026-07-28-pd3-retarget-relay.md` -- the session that found
the Finder 40.52's "11mm coil-to-contact pitch" was invented, and the real
manufacturer figure (7.5mm) reversed the design verdict. Both PDFs fetched
this session are saved under this worktree's scratchpad
(`/private/tmp/.../scratchpad/pdfs/`) and are reproducible from the URLs
cited below.

## Verdict up front

| Claim | Verdict | One-line reason |
|---|---|---|
| 1.1 WG / IEC 60335-1 qualification | **REFUTED as stated; material new finding** | The WG SKU is discontinued, and the VDE certificate TE cites for the whole family covers EN 61810-1 only -- **not** IEC 60335-1 -- for any currently-orderable part number. |
| 1.2 13.820mm PCB pin-spacing | **CONFIRMED** | TE's own dimensioned PCB-layout drawing reproduces the stock KiCad footprint's pad coordinates to within manufacturer tolerance. Governing spacing is real. |
| 1.3 DC breaking-capacity read | **CONFIRMED as extrapolation, correctly flagged as such -- with one factual correction** | The graph reads the way the survey describes, but the gap being bridged is <1 decade, not "a full decade." It is a physically safe-direction extrapolation, not a manufacturer-warranted rating. |
| 1.4 NC contact / coil compatibility | **CONFIRMED** | Pin "12" (NC, per standard EN 50005 numbering) is the *same* pin that governs creepage -- the safety-relevant pin and the geometry-relevant pin are one and the same. Coil is bit-for-bit identical to the incumbent. |
| 2. TDK B81123C1222M000 | **CONFIRMED, more solidly than the survey itself established** | Real, orderable, in stock. Y1/500VAC with *granted* ENEC and UL/CSA certificates (not the WG-style ambiguity above). 15.00mm lead spacing and 0.8mm lead diameter are both manufacturer-published, not assumed. |

**Bottom line for a human:** C6 (TDK B81123C1222M000) is safe to design in
on the evidence gathered here. K2/K3 (TE RT114012) is **not yet** safe to
design in on the "IEC 60335-1" basis specifically -- the geometry, DC-break,
and NC/coil findings all hold up, but the regulatory-compliance claim that
was the survey's stated reason for recommending this part over the
incumbent does not currently rest on any live, independently-issued
certificate. A human needs to either get TE to confirm in writing that the
Standard (non-WG) RT114012 is IEC 60335-1 qualified, or accept the relay on
the strength of its EN 61810-1 reinforced-insulation rating alone (which
**is** solidly certified) via whatever IEC 60335-1/60664-1 clause permits
that substitution -- the same open question
`docs/evidence/2026-07-28-pd3-retarget-relay.md` already surfaced for a
different relay and left to a safety engineer.

---

## Claim 1.1 -- the WG / IEC 60335-1 question (highest priority)

### What TE's own datasheets say, two revisions compared

Two TE-sourced PDFs were fetched and compared, both for the RT1 family:

- **RS Components-hosted archival copy**, `A700000007238306.pdf`
  (`https://docs.rs-online.com/2e70/A700000007238306.pdf`), header
  "11-2020, Rev. 1120", PDF metadata `CreationDate: 2020-11-09`.
- **TE's own live DDEController URL**
  (`https://www.te.com/commerce/DocumentDelivery/DDEController?Action=showdoc&DocId=Data+Sheet%7FRT1%7F0718%7Fpdf%7FEnglish%7FENG_DS_RT1_0718.pdf%7F9-1393239-8`),
  which serves TE's *current* document regardless of the `0718` revision tag
  embedded in the request URL -- the PDF actually returned is a different,
  newer document: title "Power PCB Relay RT1", PDF metadata
  `CreationDate: 2025-06-20`, footer "06/25 ED", ©2025 TE Connectivity.
  **This is the live datasheet a designer fetching this URL today gets.**

**2020 (Rev.1120) datasheet, verbatim, MEASURED (pdftotext + page-image
cross-check):**

- Front-page feature bullet: *"WG version: product in accordance to IEC
  60335-1"* -- explicitly WG-gated.
- "Other Data" table, "Resistance to heat and fire": *"WG version or Reflow
  version -- according EN60335, par30"* -- again explicitly gated to WG (or
  Reflow), not the Standard version.
- Product-code ordering table lists, as a distinct row: **`RT114012WG`,
  "IEC60335-1 compliant"**, TE part number `7-1415538-6`, separate from
  `RT114012` (blank/"Standard"), TE part number `1419108-1`.

**2025 ("06/25 ED") datasheet, verbatim, MEASURED (same method,
cross-checked against rendered page images at 600dpi to rule out a
text-extraction artifact -- see `pgA-1.png`, `pgA-4.png` in the scratchpad):**

- Front-page feature bullet: *"Product in accordance to IEC 60335-1"* --
  **the "WG version:" qualifier has been dropped.** This now reads as a
  blanket family claim.
- "Other Data" table, "Resistance to heat and fire": *"according EN60335,
  par30"* -- **the "WG version or Reflow version" qualifier has also been
  dropped** from this specific line. Confirmed visually against the
  rendered page (not a column-merge artifact of `pdftotext`).
- The **product-code ordering table now has only two "Version" options:
  "Blank -- Standard version" and "R -- Reflow solderable". There is no WG
  row at all**, for this or any other type in the family. `RT114012`'s own
  TE part number (`1419108-1`, Austria) is unchanged from 2020's Standard
  row.

### The WG SKU is discontinued -- confirmed independently at two distributors

- **DigiKey**: TE part number `7-1415538-6` (the old WG-specific internal
  number) is listed **"Obsolete and no longer manufactured."** DigiKey's
  own manufacturer-recommended substitute is `RT114012` (DigiKey PB2140-ND,
  Active, 1,224 units in stock, TE p/n `1419108-1` -- the Standard part).
- **onlinecomponents.com**: `RT114012WG` itself (the ordering code, not
  just the old TE internal number) shows **"Item discontinued," final order
  date 12/18/2023, 1 unit remaining, MOQ 85** -- i.e. not practically
  orderable. Its own listed replacement is `RT114012` (Standard, 3,560
  units).

**Both independently confirm the same fact: the dedicated, explicitly
"IEC60335-1 compliant" SKU for this coil/contact combination has been
discontinued, with no WG successor introduced.** This is consistent with
(and explains) the ordering table's WG row disappearing in the 2025
datasheet.

### The decisive check: what does the cited VDE certificate actually cover?

Both datasheet revisions -- 2020 and 2025, WG-having and WG-lacking alike --
cite the **identical** approvals list: `VDE Cert. No. 40007571, cULus
E214025, cCSAus 1142018` (plus CQC numbers). This is the *only* agency
evidence TE offers for either the WG-gated 2020 claim or the blanket 2025
claim -- there is no second, IEC-60335-1-specific certificate number
anywhere in either document.

**Fetched directly, this session, from VDE's own certificate database**
(`https://www.vde.com/tic-en/marks-and-certificates/vde-approved-products/certificate?id=40007571&type=zertreg%7Ccertificate`):

- Manufacturer: TE Connectivity Austria GmbH, Schrackstrasse 1, 3830
  Waidhofen/Thaya, Austria.
- Product type: "Electromechanical elementary relay."
- **Standards applied: DIN EN 61810-1 (VDE 0435-201):2015-10; EN
  61810-1:2015; DIN EN 61810-1/A1 (VDE 0435-201/A1):2020-08; EN
  61810-1:2015/A1:2020; IEC 61810-1:2015; IEC 61810-1:2015/AMD1:2019.**
- **No mention of IEC 60335-1 appears anywhere in the certificate.**
- Scope: "RT Serie(s)," status Active.

**This is the load-bearing finding.** VDE certificate 40007571 -- the
certificate TE's own datasheet points to as approval evidence, unchanged
across both revisions -- is a general electromechanical-relay construction
certificate under **EN/IEC 61810-1**, not a household-appliance conformity
certificate under **IEC 60335-1**. These are different standards governing
different things: 61810-1 certifies the relay's own internal
construction (which is where the "5kV/10mm coil-contact, reinforced
insulation" rating comes from, and that figure **is** solidly certified,
unconditionally, for the Standard part -- see next paragraph); 60335-1
certifies suitability for use *in* a household appliance, which is the
standard this project's own `docs/ENVIRONMENTAL_SPEC.md` and PD3 creepage
requirement are derived from. **TE's datasheet asserting "product in
accordance to IEC 60335-1" is not, on the evidence gathered here, backed by
any independently-issued certificate specific to that standard, for any
currently-orderable part number in this family.** It reads as a
manufacturer self-declaration, not a third-party-verified conformity claim
-- and the one SKU (`RT114012WG`) that historically made this distinction
concrete and orderable is discontinued.

**What is NOT in question, and should not be conflated with the above:**
the "5kV/10mm coil-contact, reinforced insulation" claim -- Insulation Data
table, "Clearance/creepage between contact and coil >=10/10mm," "Initial
dielectric strength between contact and coil 5000Vrms," Material group
IIIa -- appears **identically, unconditionally, and without any WG
qualifier** in both the 2020 and 2025 datasheets. This is exactly the field
VDE 40007571 (EN 61810-1) certifies, and it is real and applies to the
Standard `RT114012` too. **The reinforced-insulation basis for this
recommendation is not undermined by this finding. Only the specific
"qualified to IEC 60335-1" claim is.**

### Answering the task's question directly

- **Exact orderable MPN carrying IEC 60335-1 qualification**: none found.
  `RT114012WG` (TE p/n `7-1415538-6`) was the part that historically
  carried this distinction; it is **discontinued** (final order 12/18/2023
  per onlinecomponents.com; DigiKey lists the underlying TE number
  obsolete). No successor WG-suffixed part exists in TE's current catalog
  for this coil/contact/pinning combination.
- **Is the base part 60335-1 qualified?** TE's newest datasheet *says* so
  in an unqualified feature bullet, but the certificate it cites in support
  (VDE 40007571) does not mention IEC 60335-1 at all -- it is an EN
  61810-1 certificate. **This is exactly the "probably certified is not
  certified" trap this project's own evidence standard warns against; it
  is reported here, not resolved past what the primary sources show.**
- **What a human must do before relying on this claim**: either (a) obtain
  written confirmation from TE (their datasheet's own "Technical data of
  approved types on request" note is the channel for this) that the
  Standard `RT114012` is IEC 60335-1 qualified and on what certificate
  number, or (b) treat the relay as certified only to EN 61810-1
  (reinforced coil-contact insulation, real and solid) and separately
  resolve, as a standards-interpretation question, whether that satisfies
  this board's IEC 60335-1/60664-1 PD3 requirement -- the same open
  question `docs/evidence/2026-07-28-pd3-retarget-relay.md` already left
  unresolved for a different relay ("The conflation question" section of
  that document).

---

## Claim 1.2 -- the 13.820mm PCB pin-spacing claim

**Source used**: TE's own dimensioned "PCB LAYOUT / TERMINAL ASSIGNMENT"
figure, "12A, pinning 3.5mm" drawing, page 5 of the 2025 ("06/25 ED")
datasheet (identical dimensions on page 2 of the 2020 Rev.1120 datasheet --
cross-checked, both give the same numbers). This is a real, fully
dimensioned manufacturer drawing (not a schematic, not a hand-derived
footprint) -- unlike the Finder 40.52 case, TE prints exact toleranced
numbers directly on the drawing; no pixel-calibration of an un-dimensioned
vector image was required, though pixel measurement was used as an
independent cross-check (below).

**Dimensions printed on the drawing (MEASURED, read directly, 600dpi
render, `crop_dim.png`/`dimline_check.png` in the scratchpad):**

- Hole diameter: Ø1.3 (+0.1/-0) mm.
- Coil-row-to-contact-row... no -- **row pitch (A1 row to A2 row, i.e. the
  two pin rows): 7.5 +/-0.2mm.**
- Contact-pin sub-pitch: **3.5 +/-0.15mm, twice** (adjacent contact pins,
  matching the part family's own name, "pinning 3.5mm").
- Reference span from the A1/A2 column to the dimension chain's datum
  point: **20.3 +/-0.2mm.**
- Overall case length: 22.65 +/-0.2mm.

**Cross-check against the stock KiCad footprint the survey actually used**
(`/Applications/KiCad/.../Relay_THT.pretty/Relay_SPDT_Schrack-RT1-FormC_RM3.5mm.kicad_mod`,
whose own `descr` field cites a Schrack RT114012 datasheet URL) -- read
directly, not re-derived:

```
A1  (0, 0)        A2  (0, 7.62)
11  (20.32, 0)    12  (16.82, 7.62)    14  (23.82, 7.62)
pad size 3.0mm dia, drill 1.3mm  (drill matches TE's Ø1.3mm spec exactly)
```

**These two sources agree to within TE's own printed tolerance:** the
KiCad footprint's `20.32mm` reference x-coordinate (pin "11") matches TE's
printed `20.3 +/-0.2mm` datum almost exactly; the KiCad footprint's
`23.82 - 16.82 = 7.00mm` contact-pin span matches TE's `3.5 + 3.5 = 7.0mm`
chain exactly; and independently-measured pixel positions of the actual
pin-hole centers in the rendered drawing (row pitch computed as
175px/23.622px-per-mm = 7.41mm) reproduce the printed `7.5 +/-0.2mm` to
within 0.1mm. **This is a genuine, successful independent reproduction of
the manufacturer's own drawing by the stock KiCad footprint -- the opposite
finding from the Finder 40.52 case.**

Governing (shortest) coil-to-contact pair, computed from the KiCad
footprint's own coordinates: **A2 <-> "12" = 16.82mm center-to-center**
(same-row pair; every cross-row pair is longer by the Pythagorean addition
of the 7.5mm row offset). With the footprint's own 3.0mm pad (1.5mm
radius): **16.82 - 1.5 - 1.5 = 13.82mm edge-to-edge** -- reproducing the
survey's claimed 13.820mm figure exactly.

**Is the pad size manufacturer-specified?** No -- TE specifies only the
hole diameter (Ø1.3mm), not a recommended pad diameter. The KiCad
footprint's 3.0mm pad (0.85mm annular ring on a 1.3mm drill) is a generous,
plausible, but not manufacturer-mandated choice; a smaller pad (closer to
typical 0.25-0.3mm annular ring, e.g. ~1.9-2.0mm pad) would only *increase*
edge-to-edge creepage, not reduce it. **13.820mm is therefore a
conservative (lower-bound) figure relative to what a tighter-but-still-
manufacturable pad would give, not an optimistic one.**

**Verdict: CONFIRMED.** The 13.820mm figure is not hand-derived; it is
reproducible from TE's own dimensioned datasheet drawing, and the stock
KiCad footprint used to compute it matches that drawing to within printed
tolerance.

---

## Claim 1.3 -- DC load breaking-capacity graph read

**Source**: "MAX. DC LOAD BREAKING CAPACITY" graph, RT1 datasheet page 2
(2025 edition), rendered at 300dpi (`pgGraph-2.png` in scratchpad).
Directly legible without pixel-calibration tricks -- axis gridlines and
curve are clean vector art.

**Read directly**: Y-axis "DC voltage [VDC]," log scale, 10 to 300. X-axis
"DC current [A]," log scale, 0.1 to 20. Caption "resistive load." The curve
is **flat at the chart's ceiling (300V) from the leftmost plotted point
(0.1A) to approximately 0.3-0.35A**, then falls steeply to roughly 30V by
1-2A, then declines gently to about 25-27V near the 15-16A right edge
(consistent with the family's 16A rating). This matches the survey's
qualitative description.

**One factual correction to the survey's framing**: the survey states this
design's 21.8mA duty is "a full decade below the graph's lowest plotted
point." **Computed directly: 0.1A / 0.0218A = 4.6x, i.e. ~0.66 decades, not
a full decade.** The gap being extrapolated is real but smaller than
claimed -- worth correcting since "how far below the plotted range" is
exactly the kind of number this evidence standard requires getting right.

**A second point the survey did not make, which strengthens its own
conclusion**: this design's *voltage* requirement (170-200VDC) does **not**
require any extrapolation at all -- it sits comfortably under the graph's
300V flat ceiling at any current from 0.1A up to ~0.3A, which is squarely
inside the *plotted*, non-extrapolated range. The only dimension needing
extrapolation is current (0.1A plotted minimum down to 0.0218A actual), not
voltage.

**Is reading below a graph's plotted range legitimate extrapolation, or
out-of-specification use? Answered plainly, as the task asks:**

**It is both, depending on register, and the two registers should not be
conflated.** As an *engineering prediction* of likely physical behavior, it
is a reasonable and safety-directional extrapolation: DC contact breaking
capacity is fundamentally an arc-energy-at-opening problem (arc energy
scales with both voltage and current), and the graph's own shape shows the
relay's *voltage* withstand is current-independent (flat) precisely in the
low-current region already covered by test data -- extrapolating that
flatness to an even lower current is extrapolating in the direction of
*less* arc energy, not more, which is the safe direction, not the risky
one. This is a fundamentally different situation from extrapolating a
curve *beyond* its tested range in the direction where the curve is
*worsening*.

As a *formal qualification/certification* claim, however, it is **squarely
out-of-specification**: TE does not publish, state, or footnote any
guarantee that the 300V ceiling holds below 0.1A. There is no manufacturer
statement -- express or implied -- covering 21.8mA. **A design cannot cite
this graph as the part being "rated" for 170-200V at 21.8mA; it can only
cite it as strong circumstantial evidence, pending either a direct
manufacturer confirmation or empirical bench testing at the design's actual
operating point.**

**Verdict: the survey's underlying finding is CONFIRMED (the graph reads as
described, and the extrapolation is defensible) with one numerical
correction (less than a decade, not "a full decade") and one added
qualification the survey didn't make explicit (the voltage figure needs no
extrapolation at all -- only the current does). This does not amount to a
manufacturer-warranted DC-break rating at this exact operating point; a
human should treat it as strong supporting evidence, not a closed item.**

---

## Claim 1.4 -- NC contact and coil compatibility

**Contact arrangement**: `RT114012`'s own product code ("Contact
arrangement: 1 -- 1 form C (CO) contact," per TE's product-code-structure
table, both datasheet revisions) is SPDT with a genuine NC position, same
topology the incumbent Omron G5LE-1 was chosen for ("SPDT so the NC
contact is available," `elec/src/modules.ato:1177`).

**Which physical pin is NC**: per the standard EN 50005 / IEC relay pin
numbering convention used throughout the European relay industry (Schrack/
TE, Omron, Finder alike) -- tens digit = pole number, units digit 1 =
common/root, 2 = NC (break), 4 = NO (make) -- pin **"12" is the NC
contact**, pin "11" is common, pin "14" is NO. This is corroborated by the
datasheet's own wiring diagram (the "11" lead is drawn as the moving
wiper/root; "12" and "14" are the two fixed contacts).

**This is the same pin that governs creepage** (Claim 1.2, above: A2<->"12"
= 16.82mm c2c, the shortest pair). The safety-relevant electrical pin and
the geometry-relevant pin are one and the same -- not a coincidence worth
over-reading, but a useful sanity check that the creepage measurement is
being taken on the pin that actually carries the discharge duty, not an
unrelated one.

**Coil compatibility**: TE's coil-versions table, code "012": **12VDC,
operate voltage 8.4V, release voltage 1.2V, coil resistance 360 ohm
+/-10%, rated power 400mW** -- both datasheet revisions, identical numbers.
`elec/src/modules.ato`'s own docstring states the incumbent G5LE-1's coil
as **"12VDC coil 360R / 33.3mA / 400mW"** and describes the existing
per-relay 100 ohm dropper resistor circuit ("15V -> ~11.7V at the 360R
coil, 97.5% of rated"). **These are numerically identical figures** -- the
existing coil-drive circuit (100 ohm dropper from the 15V rail) requires no
change for this substitution.

**Verdict: CONFIRMED** on both points -- NC availability and coil
drop-in compatibility.

---

## Claim 2 -- TDK/EPCOS B81123C1222M000 (C6, Y-capacitor to PE)

### What C6 actually is (per `elec/src/modules.ato`, read this session)

C6 (`y_cap_pe` in the `Top` module, lines ~915-972) is a Class-I-appliance
PE-bonding Y-capacitor: *"provides EMI return path from the power return
net to PE without a DC short. Y1 safety rating required per IEC 60335-1 for
line-to-ground (250VAC) applications."* Required electrical spec:
**2.2nF +/-20%, Y1 dielectric, >=250VAC.** The currently-installed part
(`VY1222M47Y5UQ6TV0`, Vishay BCcomponents VY1, X1/Y1 per IEC 60384-14,
760VAC, 10.00mm lead spacing) is **not a placeholder** -- its own docstring
records it as MPN-VERIFIED 2026-07-28 against a Vishay datasheet, replacing
an earlier fabricated Murata part number. **What *is* a placeholder is the
board-level footprint**: `pcb/temper.kicad_pcb` still carries a stale
5.00mm-pitch land pattern the docstring itself calls a stub, *"Created to
resolve netlist reference"* -- a mismatch between the real 10.00mm-pitch
part and the board's un-reworked 5.00mm footprint, not a placeholder part
number. (This corrects the task's framing slightly: the *schematic* part is
real and verified; the *board footprint* is the stale placeholder, and
neither this document nor the survey it checks touches board files.)

### TDK's own datasheet, fetched and read directly this session

`https://www.tdk-electronics.tdk.com/inf/20/20/db/fc_2009/Y1_B81123.pdf`
(WebFetch returned 403 on this URL, consistent with the survey's own note;
`curl` with a standard browser user-agent succeeded, HTTP 200, real PDF,
945559 bytes, PDF metadata title "Film Capacitors - EMI Suppression
Capacitors (MKP) - B81123", **`Date: June 2026`** -- current TDK edition).

- **Series/class**: B81123, "Y1 / 500 V AC" -- printed as the document's
  own subtitle. **No X1 rating appears anywhere in this datasheet** (the
  survey's aside that "some listings" also show X1 is a distributor
  categorization artifact, not a TDK claim; irrelevant to C6's role since
  only Y1 line-to-ground is required here).
- **Ordering table, MEASURED directly**: for CR = 0.0022uF (2200pF),
  lead spacing 15mm: **ordering code `B81123C1222M***`**, max dimensions
  7.0 x 12.5 x 18.0mm. The composition-of-ordering-code table confirms
  `M` = +/-20% tolerance and packaging suffix `000` = "Straight terminals,
  untaped (lead length 6+1mm)" -- **`B81123C1222M000` is a real,
  well-formed, catalog-listed ordering code**, not a guessed pattern.
- **Lead spacing / lead diameter, MEASURED directly from the "Dimensions"
  table**: **lead spacing 15mm, tolerance +/-0.4mm; lead diameter d1 =
  0.8mm.** Both manufacturer-published -- the survey had flagged lead
  diameter as unconfirmed/assumed; **it is not assumed here, it is
  read directly off TDK's own dimensions table.**
- **Rated voltage**: "Rated AC voltage 500V (50/60Hz), per UL
  60384-14:2014"; "Maximum continuous AC voltage 750V." Both exceed the
  250VAC this circuit node requires, with margin.
- **Capacitance/tolerance**: 2200pF (0.0022uF), M = +/-20% -- **matches
  `y_cap_pe.value = 2.2nF +/- 20%` exactly.**
- **Approvals, MEASURED directly, both with granted (not "Pending")
  certificate numbers**: **ENEC-05495** (per EN IEC 60384-14:2023) and
  **UL E97863** (per UL 60384-14:2014, CSA E60348-14). IEC 60384-14 is
  itself the standard specifically titled "Fixed capacitors for
  electromagnetic interference suppression and connection to the supply
  mains" -- i.e. the Y-capacitor standard directly, not an adjacent
  standard being stretched to cover this use the way Claim 1.1's VDE
  certificate is. **This is a cleaner certification picture than the
  relay's.**

### Achievable board creepage

Stock KiCad footprint (`Capacitor_THT:C_Rect_L18.0mm_W7.0mm_P15.00mm_FKS3_
FKP3`, 15.00mm pitch, matching TDK's own 18.0mm body length and 15mm lead
spacing) with its stock 2.4mm pad:

```
15.000mm (TDK-published, MEASURED) - 1.2mm - 1.2mm = 12.600mm  (exact)
```

With a realistic pad sized off TDK's own **measured** 0.8mm lead diameter
(standard THT practice: ~1.0-1.1mm drill for a 0.8mm lead, ~1.5mm pad for a
~0.3-0.35mm annular ring -- comfortably above typical 0.13-0.15mm fab
minimums, not a squeeze):

```
15.000mm - 0.75mm - 0.75mm = 13.500mm   (margin: +0.900mm over 12.6mm)
```

**This reproduces the survey's 12.600mm/13.500mm figures exactly, and
upgrades the basis for the 13.500mm figure from "assumed lead gauge" (the
survey's own UNVERIFIED flag) to "derived from TDK's own measured 0.8mm
lead diameter via standard annular-ring convention."**

**Verdict: CONFIRMED**, and on stronger footing than the survey itself
established for the lead-diameter/pad-choice step. Real, orderable (DigiKey
198,918 units in stock, Active lifecycle, re-checked fresh this session --
matches the survey's snapshot number exactly), electrically suitable as a
drop-in replacement for C6's role (same capacitance/tolerance, higher
voltage margin, cleanly-certified Y1), and its board-figure claims follow
directly from manufacturer-published dimensions, not inferred ones.

---

## UNVERIFIED / residual uncertainty (stated plainly)

- **The scope of VDE 40007571 was read from VDE's own certificate-database
  page**, not from the full certificate PDF itself (the database page gives
  the standards list and manufacturer/product-type fields but not a
  line-item part-number annex). It is possible the full certificate
  document has an appendix listing specific type numbers with additional
  standards not surfaced in the database summary page -- this was not
  fetched. The database page's own standards list, however, is
  unambiguous: EN/IEC 61810-1 only, no 60335-1 reference at all.
- **TE was not contacted directly.** The datasheet's own "Technical data of
  approved types on request" note exists for exactly this kind of
  question; this document does not substitute for that.
- **RT314012/RT424012 (the RM5mm-pitch, +0.160mm-margin secondary options)
  were not independently re-verified this session** -- the primary
  recommendation (`RT114012`, +1.220mm margin) was the focus, consistent
  with the survey's own preference ordering.
- **NC-contact-specific DC breaking capacity was not separately published
  by TE** for the 12A/RT114 variant -- the graph is captioned generically
  ("resistive load," no NO/NC split) and is read here as applying to
  either fixed-contact position of the single moving contact; TE does not
  state this explicitly.
- **TDK's dimensional drawing figure itself (the vector graphic, not the
  text tables) was not independently pixel-measured** -- the text-table
  dimensions (15mm spacing, 0.8mm lead diameter) were read directly and
  are unambiguous, so pixel cross-verification of the drawing was not
  necessary the way it was for the relay's un-dimensioned Finder 40.52
  case.
- **Board-level rework for either part is out of scope here and not
  assessed**: `pcb/temper.kicad_pcb` still carries stale footprints for
  both C6 (5.00mm stub) and K2/K3 (Omron G5LE-1 3.825mm land); this
  document is schematic/part-selection verification only, per the task's
  constraints.

## Hard-constraint compliance

- **No design file, constant, footprint, or netclass modified.** Only this
  document was written this session in this worktree;
  `git status --short` clean apart from it.
- **Own git worktree**, branched fresh from `origin/main` at `ed5ee134`,
  under this session's scratchpad directory, not a shared/pre-existing
  worktree. Not pushed, no PR opened.
- **No `git stash`** used.
- **No part swapped, no verdict silently softened**: Claim 1.1 is reported
  as refuted-as-stated with the actual certificate evidence shown, not
  smoothed over into a restated "probably fine."

## Sources (fetched this session; local copies in this worktree's scratchpad
`/private/tmp/claude-501/-Users-bennet-Desktop-temper/413756c0-69f4-4db3-98b7-0b98b4a5e1f8/scratchpad/pdfs/`)

- TE RT1 datasheet, live/current: `rt1.pdf` --
  `https://www.te.com/commerce/DocumentDelivery/DDEController?Action=showdoc&DocId=Data+Sheet%7FRT1%7F0718%7Fpdf%7FEnglish%7FENG_DS_RT1_0718.pdf%7F9-1393239-8`
  (served content: "Power PCB Relay RT1", created 2025-06-20, footer
  "06/25 ED")
- TE RT1 datasheet, 2020 archival copy: `rt1_rs2020.pdf` --
  `https://docs.rs-online.com/2e70/A700000007238306.pdf` ("11-2020,
  Rev. 1120")
- VDE certificate 40007571 --
  `https://www.vde.com/tic-en/marks-and-certificates/vde-approved-products/certificate?id=40007571&type=zertreg%7Ccertificate`
- TDK/EPCOS B81123 Y1 datasheet: `tdk_b81123.pdf` --
  `https://www.tdk-electronics.tdk.com/inf/20/20/db/fc_2009/Y1_B81123.pdf`
  (Date: June 2026 edition; fetched via `curl` with a browser user-agent
  after WebFetch's default UA was refused with HTTP 403)
- DigiKey product pages: `RT114012` (PB2140-ND / 1128623), `7-1415538-6`
  (obsolete), `B81123C1222M000` (679513)
- `onlinecomponents.com`: `RT114012WG` listing (discontinued)
- Stock KiCad footprints (KiCad 9,
  `/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints/`):
  `Relay_THT.pretty/Relay_SPDT_Schrack-RT1-FormC_RM3.5mm.kicad_mod`
- In-repo: `elec/src/modules.ato`,
  `docs/evidence/2026-07-28-pd3-retarget-relay.md`,
  `docs/evidence/2026-07-29-pd3-part-selection-survey.md` (branch
  `docs/pd3-creepage-part-selection`)
