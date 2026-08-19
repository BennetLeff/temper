<!-- provenance: branch research/table-17-row-determination, based on origin/main tip eb5022510.
     pcb/temper.kicad_pcb sha256 =26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b,
     verified identical before and after this session -- never opened for write. No design value,
     threshold, DRC rule, DRU, ratchet, oracle or config was changed. MIN_BARRIER_WIDTH_MM = 12.6
     remains enforced. elec/**/*.ato was read only.
     This document reads no repo state at runtime and loads no compiled extension, so
     `make venv-isolate` was NOT run -- stated explicitly per the task brief. Repo state was read
     with cat/grep/sed/git-show and one `python3 -c` arithmetic call only.
     Primary standards text: IS 302-1:2008 (BIS adoption of IEC 60335-1, published under India's
     RTI Act at law.resource.org), sha256 924652d8e791c780fc09d934600ad2558fd5a63e1feb76464963b471ee2d3168,
     5,568,079 bytes, 80 PDF pages -- read BOTH from a full-document OCR text layer and, for every
     load-bearing quotation, re-read from 150-160 dpi `pdftoppm` page renders viewed as images.
     IS 15382 (Part 1):2003 (BIS adoption of IEC 60664-1:2002) retrieved THIS SESSION from
     law.resource.org, 4,025,813 bytes, 71 pages, read from its EMBEDDED TEXT LAYER via
     `pdftotext -layout` (not OCR). IEC 60335-1 cl. 29.2's own NOTE points normatively to this
     document for how creepage distances are measured, so it is in-scope primary text, not a
     side reference. -->

# Table 17 row determination for the HV↔SELV barrier: row **iii** governs the DC-bus crossing (8.0 mm), row iv is not reachable — but the barrier is not a DC-bus barrier, and its worst crossing needs **20 mm and a standard this project cannot obtain**

## Verdict up front

**For the pairing everyone has been arguing about — the ±170 V DC bus against SELV — the
governing row is Table 17 row iii (>125–250 V), PD3, material group IIIa/IIIb = 4.0 mm
basic, ×2 for reinforced = 8.0 mm.** The prior session reached that number; this session
closes the fork it explicitly left open, and closes it from primary text rather than by
assumption.

**The reason row iv is unreachable is not the one the task anticipated.** The task
proposed that row iv might survive on a single-fault argument: if the PE bond or the
neutral connection opens, the doubler midpoint floats and an HV rail sits at 340 V
against SELV. That argument fails twice over, and the second failure is the durable one:

1. **IEC 60335-1 does not assess working voltage under fault.** cl. 3.1.3 conditions the
   definition on *"operating under normal operation"*, cl. 3.1.9 defines normal operation
   as normal use connected to the mains, and Annex L — **recovered in full this session,
   having been recorded as unobtainable** — lays out the entire creepage procedure with
   no fault condition anywhere in it. The single-fault allowance is expressed as the ×2
   of cl. 29.2.3, not as an inflated working voltage. Applying both would double-count.

2. **Even if you refuse to rely on that, row iv still does not appear.** IEC 60335-1
   cl. 29.2 carries a NOTE — *"The working voltage for parts connected to the neutral are
   the same as for parts connected to the phase"* — which forbids taking credit for the
   doubler midpoint sitting at neutral/earth potential. This is normal-operation text, so
   it survives finding (1) and is the strongest thing on the page against row iii. Apply
   it in its most aggressive form: treat the midpoint as sitting at full phase potential
   against earth, and stack the 170 V DC half-bus on top of it. **The answer is still row
   iii**, because IEC 60664-1 cl. 3.2.1.1 states that *"the basis for the determination of
   a creepage distance is the long-term r.m.s. value of the voltage existing across it"* —
   and the r.m.s. value of 170 V DC with 120 V r.m.s. superimposed is
   √(170² + 120²) = **208.1 V r.m.s.**, inside row iii's >125–250 V band. Only a *peak*
   basis (170 + 170 = 340 V) reaches row iv, and 60664-1 rules the peak basis out for
   creepage explicitly. See §4.

**So the 12.6 mm figure is, for the DC bus, a row-iv fossil exactly as the prior session
said — and it is now safe to say so from primary text rather than by inference.**

**And that is the least important finding in this document.** The question as posed —
"which Table 17 row governs the HV↔SELV barrier" — is malformed, because
`MIN_BARRIER_WIDTH_MM` is a **single scalar applied across a 27-net domain boundary**,
and the DC bus is not that domain's worst member. `elec/domain_manifest.yaml` puts
`tank-out` and `tank.c_tank1-p2` in the HV domain. Those nets are measured in this
repository at **570.5 V r.m.s.** That is Table 17 **row vi** (>500–800 V), PD3,
IIIa/IIIb = 10.0 mm basic → **20.0 mm reinforced**. And they switch at **47 kHz**, which
is **outside IEC 60664-1's declared scope** (*"rated frequencies up to 30 kHz"*) and
routed by cl. 2.3 to **IEC 60664-4, which is paywalled and was not obtained**.

**Stated plainly, because it closes a hoped-for escape rather than opening one: on the
evidence in this document, 12.6 mm is not a conservative barrier that could be relaxed to
8.0 mm. It is simultaneously ~1.6× too generous for the bus crossing and at least ~1.6×
too small for the tank crossing, against a requirement whose true value needs a standard
this project cannot obtain.** Lowering the scalar to 8.0 mm would tighten the only part of
the barrier that is currently over-provisioned while leaving the under-provisioned part
untouched.

**No value was changed. `MIN_BARRIER_WIDTH_MM` = 12.6 remains enforced.** This document is
evidence for the owner's decision, not the decision.

---

## Provenance labels

| Label | Meaning |
|---|---|
| **PRIMARY** | Standard's own text, retrieved and read directly this session; source, page and method given. |
| **REPO** | Read this session from this repository's committed files (path and quote given). |
| **INFERRED** | Reasoning on labelled inputs, shown in full and marked as reasoning, never as standards text. |
| **UNOBTAINABLE** | Sought this session and not reached. Stated as a gap; never reconstructed. |

---

## 1. What was recovered this session that was not previously in this repository

Three documents the prior session recorded as unrecovered or unobtainable were obtained
and read. This is the reason this determination can close a fork the prior one could not.

### 1.1 cl. 3.1.3, the working-voltage definition — PRIMARY, page-verified

Recorded by the prior session as *"the definition body unrecovered"*. Read from
IS 302-1:2008; its NOTES verified against a 150 dpi render of printed page 3 (PDF page 8),
the definition body sitting at the foot of printed page 2:

> **3.1.3 Working Voltage** — Maximum voltage to which the part under consideration is
> subjected when the appliance is supplied at its rated voltage and operating under
> normal operation.
>
> NOTES
> 1 The different positions of controls and switching devices are taken into account.
> 2 Working voltage takes into account resonant voltages.
> 3 When deducing the working voltage, the effect of transient voltages is ignored.

And the term it depends on, same page, page-verified:

> **3.1.9 Normal Operation** — Conditions under which the appliance is operated in normal
> use when it is connected to the supply mains.

### 1.2 Annex L — PRIMARY, the procedure cl. 29.2 points to

Recorded in the task brief as *"paywalled and unobtainable"*. It is present in the BIS
adoption. Captioned *"(Clauses 29.1 and 29.2)"*, titled **"Guidance for the Measurement of
Clearances and Creepage Distances"**. The operative half:

> **L-2** When measuring creepage distances, the following applies.
>
> The working voltage, pollution degree and material group are determined.
>
> The creepage distances of basic insulation and supplementary insulation are measured
> and compared with the minimum values specified in Table 17. A particular creepage
> distance is then compared with the corresponding clearance of Table 16 and enlarged if
> necessary in order not to be less than the clearance. […]
>
> The creepage distances of functional insulation are measured and compared with the
> minimum values specified in Table 18.
>
> The creepage distances of reinforced insulation are measured and compared with twice
> the minimum values specified in Table 17.

**Its significance is what it does not contain.** This is the standard's own complete
procedure for arriving at a creepage figure, and it is three inputs — working voltage,
pollution degree, material group — followed by a measurement and a comparison. There is
no fault condition, no open-neutral case, no loss-of-earth case. See §3.

### 1.3 IEC 60664-1 (as IS 15382 Part 1:2003) — PRIMARY, retrieved this session

cl. 29.2's own NOTE (page-verified, §2.1) says: *"The way in which creepage distances are
measured is specified in IS 15382 (Part 1)."* Annex M likewise states it is *"extracted
from IS 15382 (Part 1)"*. This document is therefore normatively pointed to by the clause
under determination, not an outside reference. It carries an embedded text layer, so the
quotations below are extracted text, not OCR. It settles the peak/r.m.s./DC question in
§4 and it supplies the >30 kHz scope limit in §6.

---

## 2. The clause chain, page-verified

### 2.1 cl. 29.2 and the neutral NOTE — PRIMARY

Read from a 160 dpi render of printed page 52 (PDF page 57), fully legible:

> **29.2** Appliances shall be constructed so that creepage distances are not less than
> those appropriate for the working voltage, taking into account the material group and
> the pollution degree.
>
> NOTE — The working voltage for parts connected to the neutral are the same as for parts
> connected to the phase.
>
> Pollution degree 2 applies unless:
> a) precautions have been taken to protect the insulation, in which case pollution degree
> 1 applies; and
> b) the insulation is subjected to conductive pollution, in which case pollution degree 3
> applies.
>
> NOTE — An explanation of pollution degree is given in Annex M.
>
> NOTE — The way in which creepage distances are measured is specified in IS 15382 (Part 1).
>
> Parts such as hexagonal nuts that can be tightened to different positions during
> assembly, and movable parts, are placed in the most unfavourable position.

Same page: **29.2.3** *"Creepage distances of reinforced insulation shall be at least
double those specified for basic insulation in Table 17."*

Note the only "most unfavourable position" provision in the clause is **mechanical** —
hex nuts and movable parts. The standard knows how to demand a worst-case configuration
and does so for geometry. It does not do so for electrical fault states.

### 2.2 Table 17 — PRIMARY, page-verified cell-for-cell

Read from a 160 dpi render of printed page 53 (PDF page 58). Column (9) is pollution
degree 3, material group IIIa/IIIb — the column this board is in. Rows relevant here:

| Row | Working voltage (V) | col (9) PD3 IIIa/IIIb, basic | ×2 reinforced (cl. 29.2.3) |
|---|---|---|---|
| ii | >50 and ≤125 | 2.4 | 4.8 |
| **iii** | **>125 and ≤250** | **4.0** | **8.0** |
| iv | >250 and ≤400 | 6.3 | 12.6 |
| v | >400 and ≤500 | 8.0 | 16.0 |
| **vi** | **>500 and ≤800** | **10.0** | **20.0** |
| vii | >800 and ≤1 000 | 12.5 | 25.0 |

This confirms, independently and at higher resolution, the prior session's cell-for-cell
verification and the in-tree recovery at
`packages/temper-design-bundle/src/safety_value.rs:531-551`. **The table is sound and is
not in dispute.** Only the row selection ever was.

**Table 17 NOTE 3, page-verified verbatim — and the prior session's quotation of it was
incomplete in a way that matters:**

> 3 **Except for circuits on the secondary side of an isolating transformer,** the working
> voltage is considered to be not less than the rated voltage of the appliance.

The prior session quoted this without the leading exception. For the HV nets the floor
applies and equals 120 V, which lands in row ii and is subsumed by the actual 170 V — so,
as the task suspected, **NOTE 3 does not interact with the 125 V row boundary and changes
nothing here** (§5). The recovered exception matters separately: SELV/PELV circuits fed
from the isolated bias supply are on the secondary side of an isolating transformer and
are therefore *not* floored at 120 V, so intra-SELV creepage must not be dimensioned as
if they were.

**Table 17 footnote 1), page-verified, not previously in this repository:**

> ¹⁾ Material group IIIb is allowed if the working voltage does not exceed 50 V.

**REPO/INFERRED consequence:** every crossing on this board works above 50 V, so the
laminate may not be relied on as material group IIIb (100 ≤ CTI < 175). It must qualify as
**group IIIa (175 ≤ CTI < 400) or better**. The Table 17 number is unaffected — IIIa and
IIIb share column (9) — but this converts the laminate CTI from an assumption into a
**purchasing requirement**, and this document found no CTI specification for the board
stack-up. Flagged, not resolved.

### 2.3 Table 18 — PRIMARY, page-verified, and a numbering trap

Table 18 (Minimum Creepage Distances for **Functional** Insulation, clauses 29.2.4 and
L-2) is on the same page. **Its row numbering is offset by one from Table 17's**: its
≤50 V row is unnumbered, so its row i) is >50–125, row ii) is >125–250, row iii) is
>250–400, row v) is >500–800. Anything in this repository that cites a Table 18 "row"
by Table 17's numbering is off by one. Column (9), PD3 IIIa/IIIb:

| Table 18 row | Working voltage (V) | PD3 IIIa/IIIb (not doubled) |
|---|---|---|
| ii | >125 and ≤250 | 3.2 |
| **iii** | **>250 and ≤400** | **5.0** |
| v | >500 and ≤800 | 10.0 |

Functional insulation is **not** doubled — cl. 29.2.3's ×2 applies only to reinforced.

---

## 3. Single-fault behaviour — the crux, answered explicitly

**The question:** if the PE bond or the neutral connection opens, the midpoint floats and
an HV rail sits at 340 V relative to SELV. Does IEC 60335-1 assess working voltage under
that condition?

**PRIMARY answer: no. Working voltage is a normal-operation quantity, and the fault case
does not enter the creepage determination.** Four independent pieces of the standard's own
text say so, and none of them is an argument from silence:

1. **cl. 3.1.3 conditions the definition explicitly**: *"…when the appliance is supplied at
   its rated voltage and operating under normal operation."* The qualifier is in the
   definition itself, not in a note.
2. **cl. 3.1.9 defines that qualifier without any fault case**: *"Conditions under which
   the appliance is operated in normal use when it is connected to the supply mains."*
3. **Annex L, the procedure cl. 29.2 points to, contains no fault step** (§1.2). It is
   working voltage + pollution degree + material group → measure → compare.
4. **The standard places the fault allowance somewhere else, and says so.** Page-verified
   from printed page 3:
   > **3.3.2 Supplementary Insulation** — Independent insulation applied in addition to
   > basic insulation, in order to provide protection against electric shock **in the event
   > of a failure of basic insulation**.
   >
   > **3.3.4 Reinforced Insulation** — Single insulation applied to live parts, that
   > provides a degree of protection against electric shock **equivalent to double
   > insulation** under the conditions specified in this standard.

   Reinforced insulation *is* the single-fault provision, and cl. 29.2.3 prices it as ×2 on
   a basic figure that is itself derived from the normal-operation working voltage.
   **Inflating the working voltage to a fault value and then doubling it applies the same
   safety factor twice.**

IEC 60664-1 cl. 1.3.5 (PRIMARY) agrees and is more explicit about the boundary:

> **working voltage** — highest r.m.s. value of the a.c. or d.c. voltage across any
> particular insulation which can occur when the equipment is supplied at rated voltage
> NOTE 1 Transients are disregarded.
> NOTE 2 **Both open circuit conditions and normal operating conditions** are taken into
> account.

"Open circuit" here is the unloaded/no-load operating condition, which is why it is paired
with "normal operating conditions" rather than contrasted with them. It is not a broken-PE
or broken-neutral condition.

**INFERRED, and labelled as such:** on this reading, "row iv is correct because the fault
case governs" is not available. That is the answer the task said it would scrutinise least,
and it is not the answer the primary text supports. §4 is where I test whether row iv
survives anyway.

### 3.1 What the neutral NOTE does and does not do — the one live counterweight

cl. 29.2's NOTE (*"The working voltage for parts connected to the neutral are the same as
for parts connected to the phase"*) is **normal-operation text**, so it is untouched by
everything above, and it is the strongest instrument against row iii. Its purpose is
plainly to forbid the argument "this conductor connects to neutral, neutral is earthed,
therefore its working voltage to earth is zero."

That argument is exactly the one this board's topology invites, so the NOTE bites here.
Its narrow, uncontested effect: **the doubler midpoint's own working voltage against
SELV/PE is 120 V, not 0 V.** That is row ii.

Whether it further propagates — whether adopting "neutral may sit at phase potential"
requires re-referencing everything defined relative to the midpoint, putting the half-buses
at up to 340 V peak against earth — is a **genuine interpretive fork that the text does not
close**. I am recording it as a fork rather than resolving it in the convenient direction.
**§4 makes the fork moot**, which is why this determination does not rest on picking a side.

One national-difference datum bearing on the fork, labelled **SECONDARY** because it comes
from a certification body's summary of the standard rather than the standard: an Intertek
Standards Update Notice for **CAN/CSA-C22.2 No. 60335-1:16 / UL 60335-1, 6th Edition**
(issued 2017-08-23), already present in this session's working directory, records
cl. 25.1DV.1.1–25.1DV.1.2 requiring a polarized attachment plug, with a note that *"A
grounding-type attachment plug fulfils the requirement for a polarized attachment plug."*
For a Class I appliance in North America this excludes line/neutral reversal — the physical
scenario that most strongly motivates the propagating reading. It weakens the fork for this
market; it does not delete it, because the IEC/BIS NOTE is unconditional and a CB-scheme
submission would face the unmodified text.

---

## 4. Peak vs r.m.s. vs DC — the finding that actually decides the bus pairing

**PRIMARY, IEC 60664-1 cl. 3.2.1.1 "Voltage":**

> The basis for the determination of a creepage distance is the **long-term r.m.s. value**
> of the voltage existing across it. This voltage is the working voltage (see 3.2.2), the
> rated insulation voltage (see 3.2.3) or the rated voltage (see 3.2.3).
>
> Transient overvoltages are neglected since they will normally not influence the tracking
> phenomenon. However, temporary and functional overvoltages have to be taken into account
> if their duration and frequency of occurrence can influence tracking.

**Creepage is dimensioned on r.m.s., not peak.** This is consistent with the physics —
tracking is an electrolytic, energy-over-time phenomenon, not a breakdown-at-peak one —
and it is corroborated inside IEC 60335-1 itself in two places:

- **cl. 29.1.5 says "peak" when it means peak**, and it is a *clearance* clause:
  *"…the sum of the rated impulse voltage and the difference between the peak value of the
  working voltage and the peak value of the rated voltage."* Clause 29.2 and Table 17
  contain no such language.
- **Table 17 NOTE 3 floors working voltage at "the rated voltage of the appliance"**, and
  rated voltage is an r.m.s. quantity for a.c. Had the table been peak-referenced, the
  floor would have had to be expressed as the peak of the rated voltage.

IEC 60664-1 also keeps the peak quantity strictly separate and gives it a different name
and a different job — cl. 1.3.6 **recurring peak voltage (U<sub>rp</sub>)**, *"maximum peak
value of periodic excursions of the voltage waveform resulting from distortions of an a.c.
voltage or **from a.c. components superimposed on a d.c. voltage**."* That is precisely this
board's waveform, and the standard routes it to clearance and partial-discharge assessment,
**not** to the creepage table.

### 4.1 The arithmetic that closes the fork — INFERRED, from PRIMARY definitions

| Reading of cl. 29.2's neutral NOTE | Voltage across the bus↔SELV insulation | r.m.s. value | Table 17 row | Reinforced |
|---|---|---|---|---|
| Narrow (midpoint is at neutral ≈ earth) | 170 V d.c. | **170.0 V** | iii | 8.0 mm |
| Propagating (midpoint treated as at phase potential) | 170 V d.c. + 120 V r.m.s. superimposed | **√(170²+120²) = 208.1 V** | iii | 8.0 mm |
| *Peak basis, shown only to be excluded* | 170 + 169.7 | *339.7 V* | *iv* | *12.6 mm* |

**Both admissible readings land in row iii.** Row iv is reachable only on a peak basis, and
IEC 60664-1 cl. 3.2.1.1 excludes the peak basis for creepage in terms.

This is the single most load-bearing result in the document, so its weakest joint is named
explicitly: **the √(V_dc² + V_ac,rms²) step is my arithmetic**, not a formula quoted from
either standard. Neither 60335-1 nor 60664-1 gives an explicit composition rule for a d.c.
offset with a superimposed a.c. component in the *creepage* context. It is the ordinary
r.m.s. of the composite waveform and I believe it is what "the long-term r.m.s. value of
the voltage existing across it" means, but it is INFERRED. **It has margin: the row-iii
ceiling is 250 V and the figure is 208.1 V, so the composition rule would have to be wrong
by more than 20 % before row iv came back into play.** Simple addition of the two r.m.s.
values (170 + 120 = 290 V), which is not a defensible r.m.s. composition but is the most
conservative arithmetic anyone could argue for, *would* reach row iv — that is the one
route by which row iv survives, and it survives only on an arithmetic error.

---

## 5. Table 17 NOTE 3 and the 125 V boundary — confirmed non-interacting

The task asked for confirmation that the NOTE 3 floor does not interact with the row-ii/iii
boundary at 125 V. **Confirmed.**

- Rated voltage of the appliance is 120 V. **REPO**, corroborated by `elec/src/modules.ato`
  (`v_bus_half: voltage = 170V`, half-bus, not full) and by the prior session's observation
  that RV1 is a 150 V r.m.s. MOV.
- NOTE 3 floors the working voltage at 120 V. 120 ≤ 125, so the floor itself lands in row
  ii (2.4 mm basic / 4.8 mm reinforced).
- Every HV↔SELV pairing on this board has an actual working voltage of 170 V or more, which
  exceeds the floor. **The floor is therefore inactive on every pairing** and cannot move
  any row.
- The 125 V boundary is never the operative boundary for any HV crossing here. The operative
  boundary is 250 V, and §4 shows the bus pairing sits 42 V below it.

---

## 6. Per-pairing determination

**REPO — topology, re-verified directly this session rather than taken on trust:**

- `elec/src/modules.ato:917` — *"CMC: N path — neutral → CMC winding 2 (pins 2→3) → doubler
  midpoint"*, with `ac_n ~ cmc.W2_1` and `cmc.W2_2 ~ dc_bus.gnd_ref`. The midpoint is
  **hard-connected to neutral**. Confirmed.
- `elec/src/modules.ato:932` — the PE connection from the midpoint is a **Y-capacitor**, and
  the comment itself says it provides an EMI return *"without a DC short."* **Correction to
  the task's framing:** the midpoint is *Y-cap coupled* to PE, **not PE-bonded**. Its
  potential against earth is set by the neutral connection, not by the Y-cap, which is a
  ~MΩ impedance at 60 Hz. This makes cl. 29.2's neutral NOTE (§3.1) *more* relevant, not
  less, and it is why this document does not lean on the midpoint being at earth potential.
- `elec/src/main.ato:753` — `gnd ~ pe`. **SELV ground is hard-bonded to protective earth.**
  So the HV↔SELV barrier is physically an **HV↔earth** barrier. `elec/domain_manifest.yaml:854`
  confirms the Y-cap's SELV-side pin is *"bonded to pe (now part of the gnd net)."*
- `elec/src/modules.ato:821,877` — `c_bus1.voltage_rating = 250V` with
  `assert c_bus1.voltage_rating >= v_bus_half * 1.25`. 250 ≥ 212.5 passes; 250 ≥ 425 would
  not. **The task's naming-independent proof re-verified: `+170V_BUS` is the half-bus.**
- `elec/domain_manifest.yaml` — the HV domain has **27 nets**, including `tank-out`,
  `tank.c_tank1-p2`, `SW_NODE`, `GATE_HS`, `GATE_LS` and `+15V_LS`. The SELV domain has 35.
- `elec/src/main.ato:134` — `f_switching: frequency = 47kHz`, asserted within 20–100 kHz.

### 6.1 The table

Material group IIIa/IIIb, pollution degree 3 throughout (PD3 is settled and not revisited
here; see `docs/evidence/2026-08-19-60335-2-6-cl-29-2-pd2-condition.md`). "Reinforced"
applies cl. 29.2.3's ×2; functional applies Table 18 undoubled.

| # | Pairing | Working voltage (r.m.s. basis) | Insulation | Table / row | Required |
|---|---|---|---|---|---|
| 1 | `PWR_RTN` (doubler midpoint = neutral) ↔ SELV/PE | 120 V — cl. 29.2 NOTE forbids 0 V; NOTE 3 floor equals it | reinforced *(as enforced)* | 17, **ii** | 4.8 mm |
| 2 | `ac_l` ↔ SELV/PE | 120 V | reinforced | 17, **ii** | 4.8 mm |
| 3 | **`+170V_BUS` ↔ SELV/PE** | **170.0 V d.c.** (208.1 V on the propagating reading, §4.1) | reinforced | 17, **iii** | **8.0 mm** |
| 4 | **`DC_BUS_RTN` ↔ SELV/PE** | **170.0 V d.c.** (208.1 V likewise) | reinforced | 17, **iii** | **8.0 mm** |
| 5 | `+170V_BUS` ↔ `DC_BUS_RTN` (rail-to-rail) | 340 V d.c. | **functional** | **18, iii** | **5.0 mm** |
| 6 | `SW_NODE`, `GATE_HS`, `GATE_LS`, `+15V_LS` ↔ SELV/PE | ~170 V class, **at 47 kHz** | reinforced | **out of scope — see §6.2** | **not determinable** |
| 7 | **`tank-out` / `tank.c_tank1-p2` ↔ SELV/PE** | **≥570.5 V r.m.s.**, **at 47 kHz** | reinforced | **17, vi** *and* out of scope | **≥20.0 mm**, true value not determinable |
| 8 | tank ↔ bus rails | 570.5 V r.m.s., at 47 kHz | functional | 18, v | 10.0 mm |

**Rows 3 and 4 are the pairing the project has been arguing about, and they are row iii.**
**Rows 6 and 7 are why that does not settle the barrier.**

Notes on the table:

- **Row 1 and 2 at row ii is not a licence to narrow anything.** They are the same physical
  barrier as rows 3 and 4 and are governed by whichever pairing is worst.
- **Row 5 is a genuine correction of category, not of number.** HV↔HV rail-to-rail is
  *functional* insulation (cl. 3.3.5: *"Insulation between conductive parts of different
  potential which is necessary only for the proper functioning of the appliance"*), so it
  takes Table 18 undoubled — 5.0 mm — and cl. 29.2.4 additionally permits reduction if the
  appliance complies with clause 19 with the functional insulation short-circuited. It is
  **not** a 12.6 mm obligation and never was. The task's expectation that this is "a
  different clause, different figure" is confirmed.
- **Row 7's working voltage is carried forward, not re-derived.** 570.5 V r.m.s. / 923.7 V
  peak comes from `docs/evidence/2026-08-12-hv-clearance-adequacy.md:306,152`, measured
  there against ngspice-42. **REPO.**

### 6.2 The tank and switch-node crossings: Table 17 does not reach them — UNOBTAINABLE

**PRIMARY, IEC 60664-1 cl. 1.1.1 (Scope):**

> It applies to equipment for use up to 2 000 m above sea level having a rated voltage up
> to a.c. 1000 V **with rated frequencies up to 30 kHz** or a rated voltage up to d.c. 1500 V.

**PRIMARY, IEC 60664-1 cl. 2.3 (Frequency), in full:**

> Information on the dimensioning for frequencies above 30 kHz is given in IEC 60664-4.

This board switches at **47 kHz** (`elec/src/main.ato:134`, REPO), inside an asserted
20–100 kHz band. Every net that floats on the switch node or the tank is therefore **above
the frequency ceiling of the document that IEC 60335-1 cl. 29.2 points to for creepage
measurement**, and the dimensioning authority is **IEC 60664-4**.

**IEC 60664-4 was not obtained and is recorded as UNOBTAINABLE.** It is paywalled. Nothing
in this document reconstructs, estimates or infers a value from it, and no figure for
pairings 6 and 7 should be taken from this document as a requirement.

Two corroborations that this is a real gap and not a technicality:

- The Intertek Standards Update Notice for CAN/CSA-C22.2 No. 60335-1:16 / UL 60335-1 6th
  Edition (**SECONDARY**) records against clauses 29.2.1–29.2.4: *"Added requirements for
  minimum basic, supplementary, reinforced and functional insulation creepage distances for
  circuits operating at greater than 30 kHz."* So the North American adoption has already
  written >30 kHz creepage requirements into the same clauses this determination turns on,
  and this project has not read them.
- `docs/evidence/2026-08-12-hv-clearance-adequacy.md` (**REPO**) independently flagged
  *"an unconsidered high-frequency standard"* as an open hazard. This document confirms that
  flag from the primary scope text and extends it: it is not merely unconsidered, it is the
  **governing** document for the barrier's worst crossings.

**The direction of the error is knowable even though its magnitude is not.** Table 17's
row vi already demands 20.0 mm reinforced at 570.5 V r.m.s. on the ≤30 kHz basis, against
an enforced 12.6 mm. Whatever IEC 60664-4 says, it is applied to a crossing that is
**already short by ~1.6× before frequency is considered at all**, and high-frequency
creepage requirements are not known to be more permissive than low-frequency ones.

**INFERRED bound for pairing 7**, labelled: the tank's 570.5 V r.m.s. is measured against
the bus rails, and the rails sit within ±170 V d.c. of earth, so tank↔earth is
√(570.5² + 170²) ≈ 595.3 V r.m.s. — still row vi, still 20.0 mm. **The tank↔SELV working
voltage has never been measured in this repository.** That is a measurement gap, not a
standards gap, and it is cheap to close.

---

## 7. An adjacent question this determination deliberately does not resolve

`gnd ~ pe` makes the low-voltage domain an **earthed** extra-low-voltage circuit. Under
IEC 60335-1 cl. 3.4.4 (PRIMARY, page-verified, printed page 4) that is a **PELV** circuit,
not a SELV circuit:

> **3.4.4 Protective Extra-Low Voltage Circuit** — Earthed circuit operating at safety
> extra-low voltage which is separated from other circuits by basic insulation and
> protective screening, double insulation or reinforced insulation.

cl. 3.4.4 offers **three** permitted separations, and reinforced is only one of them —
basic insulation plus protective screening is another. Whether this barrier must be
*reinforced* at all, or whether cl. 8.2's probe-B touchability test (already analysed in
commit `17a4e6d94`) independently commands it, is a **separate question from the row**, and
it controls the ×2 rather than the base figure.

**It is flagged and not resolved, and nothing here should be read as suggesting the ×2 be
dropped.** It is recorded because an owner deciding what `MIN_BARRIER_WIDTH_MM` should be
needs to know that the factor and the row are two independent determinations, and only the
row was asked for.

---

## 8. Confidence, and exactly what would raise it

| Claim | Confidence | Basis |
|---|---|---|
| Table 17 row iii = 4.0 mm PD3 IIIa/IIIb; row iv = 6.3; row vi = 10.0 | **Very high** | Page-verified at 160 dpi, agrees cell-for-cell with the in-tree recovery and the prior session's independent read |
| Working voltage is a normal-operation quantity; the fault case does not govern | **High** | cl. 3.1.3 + cl. 3.1.9 + Annex L + cl. 3.3.2/3.3.4, all page-verified; four independent supports, none an argument from silence |
| Creepage is dimensioned on long-term r.m.s., not peak | **High** | IEC 60664-1 cl. 3.2.1.1 verbatim from an embedded text layer, normatively pointed to by cl. 29.2's own NOTE |
| **Bus↔SELV is row iii → 8.0 mm** | **Medium-high** | Holds under both readings of the neutral NOTE (§4.1), with 42 V of headroom to the row boundary. Discounted from "high" because the r.m.s. composition step is INFERRED and because the edition is 2004-based (below) |
| Rail-to-rail 340 V is functional insulation, Table 18 row iii → 5.0 mm | **High** | cl. 3.3.5 + cl. 29.2.4 + page-verified Table 18 |
| **Tank↔SELV exceeds row iv and needs ≥20 mm on the ≤30 kHz basis** | **Medium-high** | Table 17 is page-verified and 570.5 V r.m.s. is repo-measured; the tank↔*earth* figure is an INFERRED bound, never measured |
| **The true tank/switch-node requirement is not determinable from anything obtained** | **High** | IEC 60664-1 cl. 1.1.1 and cl. 2.3 verbatim; 47 kHz is repo-asserted |

**The documents that would raise confidence, in order of leverage:**

1. **IEC 60664-4** — *the* gap. It is the dimensioning authority for pairings 6 and 7, which
   are the barrier's worst crossings, and no substitute for it was found. **UNOBTAINABLE**
   (paywalled; no national adoption of it was located this session, unlike 60664-1).
2. **IEC 60335-1:2020 (Ed. 6) clause 29.2 and Table 17.** Everything here rests on
   IS 302-1:2008, which adopts IEC 60335-1:2004. The row boundaries, the neutral NOTE and
   NOTE 3 are all assumed stable across editions; the Intertek SUN indicates Table 17's
   NOTE 1 *was* modified and a NOTE 4 *was* added in the 6th Edition, which proves the table
   is not frozen. **UNOBTAINABLE** (paywalled).
3. **A measurement, not a document:** tank↔SELV and `SW_NODE`↔SELV working voltages against
   earth, which this repository has never taken. Cheap, in-house, and it would replace the
   only INFERRED number in §6.2.
4. **The laminate's CTI**, to establish material group IIIa vs IIIb per Table 17 footnote 1)
   (§2.2). Does not move the number; does move it from assumption to evidence.

---

## 9. What was not done

- **No design value, threshold, DRC rule, DRU, ratchet, oracle or config was changed.**
  `MIN_BARRIER_WIDTH_MM` = 12.6 remains enforced; PD3 remains enforced.
- **`pcb/temper.kicad_pcb` was never opened for write.** sha256
  `26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b` verified identical
  before and after this session.
- **`elec/**/*.ato` was read only.**
- **No certification body, laboratory or manufacturer was contacted.** The two BIS documents
  were retrieved from a public RTI-Act mirror; the Intertek SUN was already present in the
  working directory from an earlier session.
- **No standards value was reconstructed or inferred.** Where a document was not obtained
  (IEC 60664-4, IEC 60335-1 Ed. 6) the result is marked not determinable and left there.
- **No recommendation to change the enforced constant is made.** §6 is a per-pairing
  requirement table; deciding what a single scalar should be in light of it — or whether it
  should remain a single scalar — is the owner's call.
</content>
</invoke>
