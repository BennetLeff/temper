<!-- provenance: branched from origin/main (eb5022510). Own git worktree, never the main checkout.
     `make venv-isolate` run (after `unset CONDA_PREFIX`); all pyo3/maturin crates rebuilt.
     pcb/temper.kicad_pcb sha256 26981fea2dbc425f456010d4d4e755cdebdefee2b5355ad915086352b90c110b
     verified IDENTICAL before and after this session -- not modified, not regenerated.
     No clearance, creepage, copper-weight, loop-area, ampacity or DRU threshold was changed.
     MIN_BARRIER_WIDTH_MM remains 12.6. No DRC rule was weakened and no exemption was added. -->

# The certified-component creepage exemption does not apply to any of the five parts, on primary standards text: IEC 60335-1 cl. 24.1 grants the component-standard substitution for **functional insulation only**, and this is a **reinforced** barrier

## Verdict, up front

**The exemption fails, and it fails at the clause level — before any question of
whether a given part is certified.** IEC 60335-1 clause 24.1 does contain an
explicit component-standard substitution for creepage. Its scope is one word
wide, and that word is *functional*:

> "Components can comply with the requirements for clearances and creepage
> distances **for functional insulation** in the relevant component standard"

The HV↔SELV barrier at C6, K1, U6, T1 and T2 is **reinforced** insulation — that
is the entire basis of the 12.6 mm figure (Table 17 row iv basic 6.3 mm, doubled
per cl. 29.2.3). Reinforced is not functional. The standard drafted a
component-standard carve-out for creepage, and deliberately did not extend it
past functional insulation. **`MIN_BARRIER_WIDTH_MM` = 12.6 geometric stands for
all five parts.**

Per component, with the certification chain verified independently anyway:

| ref | part (as sourced) | certification chain | exemption verdict |
|---|---|---|---|
| C6 | TDK **B81123C1562M000** Y1 500 VAC | **series-level only** — see §2 note; part-specific certificate numbers not verified this session | **does not apply** (cl. 24.1: functional only) |
| K1 | TE Schrack **RT33K012** | **complete** — IEC 61810-1, VDE 40007571 | **does not apply** (cl. 24.1: functional only) |
| U6 | TI **UCC21550BDWKR** | **complete** — UL FPPT2.E181974, VDE, CQC, 5 kVrms reinforced | **does not apply** (cl. 24.1: functional only) |
| T1 | Coilcraft **CST3015-100ED** | **FAILS AT STEP 1 — no agency recognition at all** | **does not apply**, twice over |
| T2 | Coilcraft **CST3015-100ED** | **FAILS AT STEP 1 — no agency recognition at all** | **does not apply**, twice over |

Two of the five would have failed the exemption even if the clause had been
permissive, because the part carries no third-party certification to invoke.

**Two findings push in the opposite direction from relaxation — the 12.6 mm
figure may be a floor, not the governing value, at three of the five sites.**
See §4. Neither is resolvable in-tree; both need the certification lab.

---

## 1. The standards question, clause by clause

### 1.1 What actually governs the barrier

**IEC 60335-1 cl. 29.2** (recovered primary, IS 302-1:2008 identical adoption,
in-tree at `docs/evidence/2026-08-12-hv-hv-creepage-determination.md`):

> "Appliances shall be constructed so that creepage distances are not less than
> those appropriate for the working voltage, taking into account the material
> group and the pollution degree."

**cl. 29.2.3**, same source:

> "Creepage distances of reinforced insulation shall be at least double those
> specified for basic insulation in Table 17."

Table 17 row iv (working voltage > 250 V and ≤ 400 V), pollution degree 3,
material group IIIa/IIIb → basic **6.3 mm** → reinforced **12.6 mm**. No margin,
no third multiplier. This is exactly `MIN_BARRIER_WIDTH_MM`.

### 1.2 The one component carve-out that exists, and its scope

Clause 24.1 is where a component standard can displace clause 29. Retrieved
this session from **two independent accredited-lab CB test reports**, which
reproduce clause wording verbatim in their requirement column:

**Source A — IEC 60335-1:2020 (Ed. 6.0)**, TRF No. `IEC60335_1Z`, Report No.
`EFSH23070262-IE-07-L01`, pp. 43–44
(`https://www.globtek.info/certs/GTM961005P/CB%20-REPORT-GTM961005P-xPDxxx%20IEC60335.2020.pdf`):

> "The requirements of Clause 29 apply between live parts of components and
> accessible parts of the appliance"
>
> "Components can comply with the requirements for clearances and creepage
> distances **for functional insulation** in the relevant component standard"

**Source B — IEC 60335-1:2010 (Ed. 5.0) incl. Corr. 1:2010**, Report No.
`15PP116-01_0`, p. 30
(`https://www.victronenergy.com/upload/documents/Safety-EN-IEC-60335-1-Cyrix.pdf`):

> "The requirements of Clause 29 apply between live parts of components and
> accessible parts of the appliance"
>
> "Components can comply with the requirements for clearances and creepage
> distances **for functional insulation** in the relevant component standard"

**Identical wording across two editions, fifteen years apart, from two
unrelated laboratories.** The carve-out is stable, it is real, and it stops at
functional insulation.

**Source C — an older edition, via EN 60335-2-30**, Report No.
`140401243SHA-002`, TRF `IEC60335_2_30J`
(`https://media.adeo.com/media/1381208/media.pdf`), carries clause 24.1 as:

> "Components comply with the safety requirements specified in the relevant
> standards as far as they reasonably apply"
>
> "The requirements of Clause 29 of this standard apply between live parts of
> components and accessible parts of the appliance."

— and **contains no component creepage/clearance substitution sentence at all.**
So the edition sweep gives only two possible readings, and neither helps: on the
older edition there is no component carve-out for creepage whatsoever; on
Ed. 5 and Ed. 6 there is one and it is confined to functional insulation. There
is no edition of IEC 60335-1 sampled here under which a component standard
displaces **reinforced** creepage.

This also matches the in-tree recovered text of the same clause at edition 4.1
(`docs/evidence/2026-07-29-relay-60335-1-certification-resolution.md`):

> "24.1 Components shall comply with the safety requirements specified in the
> relevant IEC standards as far as they reasonably apply.
>
> NOTE 1 Compliance with the IEC standard for the relevant component does not
> necessarily ensure compliance with the requirements of this standard.
>
> Unless otherwise specified, the requirements of clause 29 of this standard
> apply between live parts of components and accessible parts of the appliance."

NOTE 1 is the general disclaimer; the functional-insulation sentence is the
specific grant. Neither reaches reinforced insulation.

### 1.2a The other sentence in cl. 24.1 confirms clause 29 applies here

The companion sentence — "The requirements of Clause 29 apply between live parts
of components and accessible parts of the appliance" — could be misread as
*limiting* clause 29 to live-part-to-accessible-part pairs, and then used to
argue the SELV domain is not "accessible". That reading does not rescue the
exemption, for two independent reasons.

First, the sentence extends clause 29's reach into components; it does not
narrow cl. 29.2, which is written generally ("Appliances shall be constructed so
that creepage distances are not less than those appropriate for the working
voltage…").

Second, **on this design the SELV domain is accessible.** `gnd` is bonded
directly to protective earth (`elec/src/main.ato`: `gnd ~ pe`), the domain feeds
a user-touchable RTD food probe, and the design's own protective strategy for
`LV_CONTROL` rests on certified galvanic isolators rather than Class I earthing
(`docs/hardware/IEC60335_CRITICAL_COMPONENTS.md` §2.4). So the HV↔SELV crossings
at C6, K1, U6, T1 and T2 *are* live-part-to-accessible-part boundaries. The
sentence therefore affirmatively places them inside clause 29 rather than
outside it.

### 1.3 How accredited laboratories actually apply this to a certified isolator

Source A's appended clause-29 measurement table, p. 125, records a row for a
**certified optocoupler** — the same class of part as U6, doing the same job:

```
Clearance cl and creepage      Up      U r.m.s.   Required    cl     Required   dcr
distance dcr at/of:            (V)       (V)       cl (mm)   (mm)    dcr (mm)   (mm)
L / N to output (optocoupler)  339       240         4.5      8.0       5.0      8.0
```

The laboratory **measured** the creepage across the optocoupler (`dcr = 8.0 mm`)
and compared it against a clause-29 **required** value (`5.0 mm`). It did not
waive the measurement because the part was a certified isolator. This is the
exemption being asked about, applied by a lab in a real IEC 60335-1
certification, and the answer is that the geometric path is still measured and
still has to clear the table figure.

### 1.4 Why the component certificate covers a different physical thing

Component isolation standards (IEC 60747-17 / VDE 0884-11 for optical and
magnetic isolators, IEC 60384-14 for Y-capacitors, IEC 61810-1 for relays)
qualify the **internal** insulation: distance-through-insulation, partial
discharge, dielectric withstand. That maps onto IEC 60335-1 **cl. 29.3** (solid
insulation), not cl. 29.2 (creepage). Creepage is a *surface* phenomenon on the
board's own external microenvironment, governed by that board's pollution degree
and laminate CTI — neither of which the component vendor controls or certifies.

The PSMA safety-compliance forum's own framing of the regulatory landscape for
isolator components states the split plainly
(`https://www.psma.com/sites/default/files/uploads/tech-forums-safety-compliance/presentations/is132-component-level-safety-certification-systems-iec60747-17ul1577.pdf`,
"What Standards For Thin Film Isolators"):

> "Under System Standards — They could be qualified under system level standards
> as **solid insulation**."

Solid insulation, not creepage. (Secondary source, cited only for the concept
split; the verdict above rests on cl. 24.1, not on this.)

The accepted framing already recorded in-tree is the correct one and this
session's primary text confirms it: the governing distance is
**min(path across the component package, path across the PCB surface)**, and a
certificate speaks to the package's internals only.

---

## 2. Certification chain, verified per part

The brief required that certification be verified per part rather than assumed
from the part being "an isolator". Done below, even though §1 makes it
non-dispositive. Sources are the in-tree component-approval register
(`docs/hardware/IEC60335_CRITICAL_COMPONENTS.md`), whose every cell cites a
manufacturer datasheet fetched directly.

| ref | agency + file | standard | certified rating | covers this application? |
|---|---|---|---|---|
| C6 (TDK B81123C1562M000) | **see note below** | IEC 60384-14 Class Y1 | Y1 **500 VAC** | **Yes on voltage** — 500 VAC exceeds the ≥250 VAC line-to-ground need |
| K1 (TE Schrack RT33K012) | VDE **40007571** | EN/IEC 61810-1 | 20 A UL508 / 16 A IEC, 277 VAC | **Yes** for the contact duty |
| U6 (TI UCC21550BDWKR) | UL **FPPT2.E181974**, cert **20160516-E181974**; VDE; CQC **CQC16001155011**; CSA **70097761** | IEC 60747-5-5 / UL 1577 | 5 kVrms **reinforced** | **Yes** on voltage |
| T1, T2 (Coilcraft CST3015-100ED) | **none** | — | — | **No — there is no certificate** |

**C6 certification note — stated precisely, not rounded up.** The in-tree record
carries agency certificate numbers (ENEC-05495, UL E97863) for the **sibling**
part `B81123C1222M000` (2.2 nF), recorded in
`docs/evidence/2026-07-30-pd3-board-expansion-measurement.md`, **not** for the
5.6 nF `B81123C1562M000` actually specified. What is verified for the specified
MPN is: Active/orderable (DigiKey `495-1653-ND`), 5600 pF, 500 VAC, 22.50 mm lead
spacing, AEC-Q200 — from a direct product-page fetch recorded in
`docs/evidence/2026-08-13-pd3-land-k1-c6.md`. Both parts are in TDK's B81123
film-Y1 family and the approvals are almost certainly series-wide, **but that is
an inference, not a document I read.** Before purchase, the B81123 datasheet's
approvals table should be checked against this exact ordering code. This does not
affect the verdict — the exemption fails on clause scope regardless — but it is
an open item for the BOM, not a closed one.

**T1/T2 detail.** Coilcraft's own `cst3015.pdf` states 5000 Vrms/1 min isolation
and ≥8 mm creepage/clearance as **design/test specifications only**; no UL, CSA,
VDE or other agency recognition file appears anywhere in the datasheet
(`IEC60335_CRITICAL_COMPONENTS.md` row "Current sense transformer"). A datasheet
number is not a certification. Any exemption argument for T1/T2 fails at the
first link regardless of clause scope — and the datasheet's own ≥8 mm figure is
below 12.6 mm in any case.

---

## 3. What is not obtainable

Stated plainly, not reconstructed, not inferred:

- **IEC 60335-1 Annex L** — not obtainable. Paywalled, no free national adoption route found.
- **IEC 60664-4:2005** (the >30 kHz creepage/clearance standard, including its Table 2) — **not obtainable**. Paywalled, no free adoption route found. This matters materially; see §4.1.
- **IEC 60384-14 Table 2** (Class Y subclass definitions) and **Table 3** (the component standard's own creepage/clearance figures) — not obtainable. The freely published Ed. 5.0 (2023-01) commented-version sample
  (`https://cdn.standards.iteh.ai/samples/102862/fcafa89368c44ad486740b70884e3602/IEC-60384-14-2023.pdf`)
  ends at p. 13; Table 2 is at p. 17 and Table 3 at p. 20. Confirmed present in the
  table-of-contents, contents not retrieved.
- **IEC 60335-1 clause 29 body text and Tables 16/17/18 as printed by IEC** — the
  official Ed. 6.0 sample (`https://cdn.standards.iteh.ai/samples/101518/78945351a99747cd8a166a9ac8688b50/IEC-60335-1-2020.pdf`)
  is 15 pages of front matter and stops long before clause 29 (p. 107). The
  in-tree recovered tables from IS 302-1:2008 remain the working source; this
  session's CB reports corroborate the clause *wording* but not the table cells.

The sample's table-of-contents does independently confirm the table identities
the brief flagged: **Table 16 – Minimum clearances (p. 109); Table 17 – Minimum
creepage distances for basic insulation (p. 113); Table 18 – Minimum creepage
distances for functional insulation (p. 114).** Table 8 is not among them.

---

## 4. Two findings that push the requirement **up**, not down

Both surfaced while retrieving the clause text. Neither can be closed in-tree.

### 4.1 The >30 kHz rule reaches three of the five parts

Source A, cl. 29.2.1 and 29.2.3 verbatim:

> **29.2.1** "Creepage distances of basic insulation not less than specified in
> Table 17. However, if the working voltage is periodic and has a frequency
> exceeding 30 kHz, the creepage distances are also determined from Table 2 of
> IEC 60664-4:2005, these values being used if exceeding the values in Table 17"
>
> **29.2.3** "Creepage distances of reinforced insulation at least double those
> specified for basic insulation in Table 17, excluding NOTE 1 and NOTE 2, **or
> Table 2 of IEC 60664-4:2005, as applicable**"

This inverter switches at **44–50 kHz**. T1 (`tank-out`), T2 (`hb-gnd`) and U6
(secondary side on `hb-gnd`/`SW_NODE`) all carry periodic working voltage above
30 kHz. For those three, Table 17 alone does not settle the requirement:
IEC 60664-4 Table 2 must also be evaluated and **the larger value governs**.
IEC 60664-4 is not obtainable (§3). **12.6 mm is therefore a lower bound at T1,
T2 and U6, not a determined requirement.** It cannot be argued downward, and it
may need to go up. The existing cert-lab inquiry
(`docs/cert-lab-inquiry-final-2026-08-16.md`) already raises this; it remains
open.

### 4.2 T1's HV-side working voltage was never derived, and the neighbouring node is 923.7 V peak

T1's HV pad sits on `tank-out`. In-tree ngspice sweeps
(`docs/evidence/2026-08-12-hv-clearance-adequacy.md`) put the node one inductor
away (`tank.c_tank1-p2`) at **923.7 V pk / 570.5 V rms** at the worst
OCP-passing corner. `tank-out`'s own peak working voltage is recorded in-tree as
never computed:

> "Peak working voltage at the `tank-out` node (T1's HV pad) was not derived. If
> the resonant tank exceeds ~1170 V peak, the clearance figure moves up a step."

If `tank-out`'s working voltage lands above 500 V rms, Table 17 moves from row iv
(>250–400 V, basic 6.3) to row vi (>500–800 V, basic 10.0) and the **reinforced
requirement becomes 20.0 mm, not 12.6 mm**. This is an open determination, not a
claim — but it means T1's 3.5 mm shortfall is a floor on the shortfall.

---

## 5. Replacement sourcing

### 5.1 C6 and K1 — already sourced in `elec/src`; the board is the gap

Both were re-specified on 2026-08-13 and the schematic already carries the
replacements. **`pcb/temper.kicad_pcb` was deliberately not resynced**, which is
why the measurement script still reports the old packages. `elec/src/modules.ato`
says so in terms:

> "BOARD REWORK REQUIRED, NOT DONE HERE: pcb/temper.kicad_pcb still carries the
> P10.00mm disc footprint for C6 and is deliberately untouched by this change"

Both replacement footprints were **re-measured independently this session** with
the same canonical kernel (`temper_placer.core.pad_geometry.pad_pair_distance`)
used by the isolator-package-maxima script — not taken from the footprint `descr`:

| ref | replacement | measured HV↔SELV | vs 12.6 mm |
|---|---|---:|---|
| C6 | TDK **B81123C1562M000**, 5.6 nF Y1 500 VAC, `C_Rect_L26.5mm_W7.0mm_P22.50mm_MKS4` | **20.1000 mm** (pad 1↔2) | **clears by +7.5** |
| K1 | TE Schrack **RT33K012**, `temper:Relay_SPST_Schrack-RT33K012` | **17.8000 mm** (pad 4↔2) | **clears by +5.2** |

Both reproduce the in-tree figures exactly.

**C6 — the specified part is not currently buyable.** Digi-Key, checked
2026-08-19: `B81123C1562M000` (495-1653-ND) shows **0 in stock, 630 estimated
2027-01-20**, $1.88/1. The geometry is the best of any candidate, but the part is
effectively unavailable for ~17 months. This is the single most actionable
procurement finding in this document and it was not previously recorded in-tree.

**The 2.2 nF / 15.00 mm alternatives keep the design value but are marginal, and
the repo has already rejected one of them once.** Two Y1 500 VAC parts at 15.00 mm
±0.4 mm pitch, 0.8 mm leads, both datasheet-verified this session:

| part | value | approvals | Digi-Key stock 2026-08-19 |
|---|---|---|---|
| TDK **B81123C1222M000** | 2.2 nF ±20% | ENEC-05495, UL/CSA E97863 | **198,828**, Active |
| KEMET **P295BJ222M500A** | 2.2 nF ±20% | IMQ CA08.00252, UL/CSA E73869, CQC16001145222 | listed, quantity not retrieved |

`docs/evidence/2026-07-29-pd3-part-selection-verification.md` carries a
superseding note calling `B81123C1222M000` a **"false solve"** — at 15.00 ±0.4 mm
the worst-case gap is **12.2 mm, below 12.6 mm**. That figure assumes the KiCad
**stock 2.4 mm pad**. The arithmetic is pad-diameter-dependent:

| pad diameter | worst-case gap (pitch 14.6 mm) | verdict |
|---|---:|---|
| 2.4 mm (KiCad stock, as used by C1) | 12.200 mm | **fails** — this is the recorded false solve |
| 2.0 mm (what C6's land uses today) | 12.600 mm | passes with **exactly zero margin** |
| 1.6 mm (still 0.4 mm annular ring on a 0.8 mm lead) | 13.000 mm | passes, +0.4 mm |

So the "false solve" verdict is correct *at stock pad size* and escapable only by
deliberately tightening the land pattern. **A part that clears a reinforced-safety
limit by 0.0 mm, and only because the pad was shrunk to make it, is not a solve I
would put on a mains BOM** — that is the shape of a check being fitted to a part
rather than a part to the check. The 1.6 mm option is defensible on annular ring
but still carries +0.4 mm against a limit that §4 argues may not even be the final
figure.

**Neither Y-capacitor datasheet states a creepage figure at all.** Seven safety-cap
datasheets were fetched (TDK B81123, KEMET P295, Vishay VY1, Murata DE1/DE2,
Songtian CD, Suntan TS22); **every one gives lead pitch only** and none contains
the word "creepage". Lead pitch is a package dimension. It must not be recorded as
a datasheet creepage figure — the same hipot-vs-creepage conflation §5.3a flags
for the CT category.

**Ceramic-disc Y1 cannot reach 12.6 mm at any capacitance**, confirming the
in-tree survey: disc Y1 tops out at 12.5 mm ±1.0 mm nominal pitch (Vishay VY1),
below the bar before tolerance is even applied. Only film/paper box construction
goes wider. The incumbent `VY1222M47Y5UQ6TV0` measures 9.500 mm worst case.

**The owner's actual choice at C6** is therefore: (a) 5.6 nF at 22.50 mm — real
geometric margin (19.7 mm worst case / 20.1 mm nominal), but unbuyable until
2027 and needs the 2.5× capacitance change signed off against touch current; or
(b) 2.2 nF at 15.00 mm — stocked in volume, keeps the design value and its
leakage budget, but only clears with a tightened land pattern and ~0–0.4 mm
margin. Neither is free.

*(Geometry note: my nominal measurement of the 22.50 mm land pattern is
**20.1000 mm**; the 19.700 mm figure above is the same part at worst-case pitch
tolerance. Both clear 12.6 mm comfortably; they differ only in whether pitch
tolerance is applied.)*

**C6 physical detail.** 22.50 mm lead pitch, body
26.5 × 7.0 × 16.0 mm. Not a drop-in: needs the new land pattern. Capacitance was
raised 2.2 nF → 5.6 nF because film-Y1 lead pitch is tied to capacitance; the
binding electrical constraint is touch current, and in-tree arithmetic puts it at
1153.7–1241.7 µA against the 1.35 mA IEC 60335-2-6 limit — **8–15 % headroom,
thinner than this design's other PD3 crossings.** That margin should be
re-checked by the owner before commitment, not treated as settled.
**Footprint growth: significant** (P10.00 → P22.50 mm). Placement was already
trialled in-tree and reported clean: "C6 alone: clean … zero new violations of
any kind."

**K1 — datasheet-verified part, but an open board blocker.** RT33K012 is the same
RT1 case family as K2/K3's already-passing RT314012, 1 Form A, 20 A UL508 /
16 A IEC 277 VAC, 12 VDC/360 Ω/400 mW coil, VDE 40007571. The coil dropper was
already retuned 39 Ω → 91 Ω in-tree to suit the different coil resistance.
**It does not currently fit at K1's board site.** The incumbent Omron footprint's
contact pins are Faston tabs drawn on F.Fab with *zero PCB copper*, so traces
were routed through space a real THT relay occupies; all four cardinal rotations
produce new shorts plus a courtyard collision with C27
(`docs/evidence/2026-08-13-pd3-land-k1-c6.md`).

**Correction on footprint growth — the replacement body is smaller, not bigger.**
RT33K012 body is **29.0 × 12.7 × 15.7 mm** (TE drawing S0272-BC) against the
G4A-E's **30.5 × 16 × 23.5 mm** — smaller in all three dimensions, and 14 g.
What is wider is the *pad field* (17.8 mm coil-to-contact against 8.0 mm), which
is the entire point. So K1 exerts **no new area pressure on placement**; the
blocker is purely that the incumbent Omron footprint declared its contact pins as
F.Fab tabs with no copper, and traces were routed through the space a real THT
relay body occupies. This is a routing-clearance problem at one site, not a
board-density problem.

Stock: Digi-Key **PB2347-ND, 1,197 in stock**, $7.03/1, Active (2026-08-19).

**Relay category ceiling, for the record.** No relay datasheet from any vendor
surveyed states a coil-to-contact creepage ≥ 12.6 mm. The category maximum found
is **11.0 mm** (Panasonic HE-S / AHES3191, "Between Form A contact and coil —
Min. 11.0 mm"), and that same datasheet's *certified* IEC 61810-1 figure is only
**5.5 / 8.0 mm** — so the 11.0 mm construction number buys nothing a test house
would credit. The mainstream cluster (Omron G2RL, Finder 40/62/34, Panasonic
HE/JW) sits at exactly **8 mm**, the PD2 figure again (§5.4). The incumbent Omron
G4A is the worst of the set at **6.4 mm creepage / 3.2 mm clearance**.

**RT33K012 wins on land pattern, not on its internal rating.** TE's datasheet
states "Clearance/creepage between contact and coil ≥ 10/10 mm" and — unlike the
ICs in §5.4 — rates the part at **IEC 60664-1 pollution degree 3, material group
IIIa, reinforced, rated insulation voltage 250 V** (VDE 40007571, UL E214025,
cCSAus 1142018). Its 10 mm internal figure is still under 12.6 mm; what clears
the requirement is the **17.8 mm pad-to-pad span** of its land pattern, which is
the measurement that actually governs (§1.4).

**And they interact.** `docs/hardware/BOM.md` records that landing both new
footprints together "does introduce one new courtyard collision between the two
new footprints specifically" — C6 alone is clean, K1 alone fails, and the pair
adds a third problem neither has alone. The board work here is a single
re-placement exercise covering both parts, not two independent resyncs.

### 5.2 U6 — the part's own datasheet settles two questions at once

Retrieved this session from TI's UCC21550 datasheet, **§5.6 Insulation
Specifications** (`https://www.ti.com/lit/ds/symlink/ucc21550.pdf`):

| parameter | test condition (verbatim) | value |
|---|---|---|
| **CPG External Creepage** | "Shortest terminal-to-terminal distance **across the package surface**" | **> 8 mm** |
| CLR External clearance | "Shortest terminal-to-terminal distance through air" | > 8 mm |
| DTI | Minimum internal gap | > 17 µm |
| CTI | IEC 60112 | > 600 V |
| Material Group | per IEC 60664-1 | **I** |
| **Pollution degree** | — | **2** |
| VIOWM max isolation working voltage | AC sine, TDDB | 1500 V rms / 2121 V DC |
| VISO withstand (UL 1577) | 5000 V rms, 60 s | 5000 V rms |

**Two things follow, and they point in opposite directions.**

*The working-voltage prong passes.* VIOWM 1500 V rms / 2121 V DC amply covers
the ~340 V bus and the ~170 V DC / 344 V pk excursions at U6's barrier. The
certification is real and the voltage is covered. This is the one part where
that whole chain is clean — and it still does not earn the exemption, because
of §1.

*The pollution-degree prong fails, on the vendor's own paper.* **The UCC21550's
insulation specification is stated at pollution degree 2.** This board is PD3.
The brief's hypothesis — that these footprints were selected against PD2 — is
confirmed here in the vendor's own table, not inferred. The part offers > 8 mm,
which is the PD2 reinforced figure, and 8 mm is precisely where the corridor
sweep found the feasibility cliff.

### 5.2a The proposed slot rescue does not deliver physical compliance at U6

This needs saying plainly, because a slot is already proposed in-tree
(`docs/evidence/2026-08-13-hv-creepage-slot-rescue-t1-t2-u6.md`: a
7.30 × 17.00 mm slot raising U6's figure "from the measured baseline 8.100mm to
14.85mm nominal / 14.11mm worst-case").

Creepage is **min(path across the package surface, path across the PCB
surface)**. A slot milled in the board lengthens only the second term. TI defines
CPG as the shortest terminal-to-terminal distance *across the package surface*,
and specifies it at **> 8 mm**. That path runs over the plastic body and is
entirely unaffected by anything done to the laminate underneath it.

So the slot raises the **board-path measurement** to 14.85 mm while the
**governing physical creepage stays at the package term, > 8 mm**. The in-tree
slot analysis measures only the board path and does not carry a package-path
term at all.

**A slot at U6 would make the pad-to-pad DRC pass without raising the actual
creepage of the barrier.** That is the failure mode this project explicitly
guards against, and it should not be adopted at U6 on the strength of the
current analysis. The same objection applies to the proposed T1 slot, whose part
(CST3015-100ED) likewise states only ≥ 8 mm creepage/clearance.

This does not mean slots are never legitimate — IEC 60664-1 cl. 4.2 groove
credit is real, and the widths proposed (7.30 mm, 8.0 mm) comfortably exceed both
the PD3 groove minimum X = 1.5 mm and JLCPCB's 1.0 mm non-plated slot floor
(`docs/hardware/FAB_CAPABILITY.md` §1 row 5d). It means a slot only helps where
the **package** path is already adequate and the **board** path is the binding
term. At U6 and T1 it is the package path that binds, so the slot does not help.

### 5.2b The one datasheet-verified route past the U6 ceiling — and it is a topology change

**No isolated gate driver reaches 12.6 mm.** The in-tree survey found every
reinforced gate-driver IC and every optocoupler plateauing at 7–8.5 mm, and the
UCC21550's own > 8 mm CPG (§5.2) is representative. That is a lead-frame and
package-geometry ceiling, not a die limitation.

**A wide-body digital isolator does reach it, comfortably.** Retrieved this
session from TI's ISO7740/ISO7741/ISO7742 datasheet (SLLSEP4K), **§5.6 Insulation
Specifications**, which tabulates three packages side by side:

| parameter | DW-16 | **DUW-16** | DBQ-16 |
|---|---:|---:|---:|
| CLR external clearance | > 8 mm | **> 21.2 mm** | > 3.7 mm |
| **CPG external creepage** ("shortest terminal-to-terminal distance across the package surface") | > 8 mm | **> 21.2 mm** | > 3.7 mm |
| CTI | > 600 V | > 600 V | > 600 V |
| Material group | I | I | I |
| Pollution degree | 2 | 2 | 2 |
| VIOWM max working isolation voltage | 1500 V rms / 2121 V DC | 1500 V rms / 2121 V DC | 400 V rms / 566 V DC |
| VIOTM max transient | 8000 V pk | 8000 V pk | 4242 V pk |

TI's §8 application text states the intent directly:

> "The DWW package provides wider creepage and clearance without the need for two
> isolators in series or an extra isolated power supply"

(TI uses **DUW** as the package code and **DWW** as the orderable suffix for the
same wide-body part; the in-tree candidate `ISO7741FQDWWRQ1` is this package.)

**> 21.2 mm clears 12.6 mm outright, and also clears the 20.0 mm figure** that
would apply if `tank-out`-class working voltages ever pushed a barrier into
Table 17 row vi. This is the one candidate in the whole exercise with genuine
headroom rather than a thin margin.

Three caveats, stated plainly:

1. **It is not a gate driver.** ISO7741 is a 4-channel digital isolator. Using it
   means moving the barrier upstream of the driver and putting a non-isolated
   gate-driver IC on the secondary side of each switch — the topology change the
   in-tree analysis already identified. The design already has a
   `hv_minus`-referenced 15 V rail and a bootstrap for the high side, so the
   supply architecture is not starting from zero, but this is a redesign of the
   gate-drive chain, not a part swap. Dead-time generation (currently the
   UCC21550's `DT` pin, 34 kΩ → 305.4 ns) and the `DIS` safety-shutdown path
   would both need re-homing.
2. **Footprint growth is large and it is the placement risk.** A > 21.2 mm
   terminal-to-terminal span means the land pattern is at least 21.2 mm across
   the barrier, against U6's current 8.1 mm. **This is the candidate most likely
   to disturb the placer's currently-`optimal` inter-component result** — it is
   roughly 2.6× the current pin-row separation, plus a second driver package per
   switch. Flagged explicitly, as requested.
3. **The datasheet still states pollution degree 2**, as the UCC21550 does. That
   does not undermine the candidate here, because the argument is *geometric*
   (> 21.2 mm of actual terminal-to-terminal surface path against a 12.6 mm PD3
   requirement), not a certification-credit argument. Per §1 no certificate is
   being invoked.

### 5.3 T1 / T2 — the incumbent, re-verified from the vendor's own datasheet

Coilcraft **Document 1608-1**, retrieved and text-extracted this session
(`https://www.coilcraft.com/getmedia/df31d5fe-b3af-4586-82a7-7b773ac9f838/cst3015.pdf`).
Verbatim, the two isolation bullets:

> "5000 Vrms, one minute isolation (hipot) between windings."
>
> "**Designed to meet** reinforced insulation, at least 8 mm creepage/clearance"

CST3015-100ED row: 1:100, 3.20 mH, DCR 0.0001 Ω pri / 1.54 Ω sec, frequency range
**0.78 – >1000 kHz**, volt-time product 638 V-µs, **sensed current 88 A**,
terminating resistance 1 Ω. Body 23.0 × 30.0 mm.

**No agency file or recognition number appears anywhere in the document.** A
full scan of all 112 extracted lines for UL/CSA/VDE/TÜV file patterns, and for
the words "recognized", "approved", "certified", "listed", returns only
Coilcraft's own high-risk-application disclaimer. This independently confirms the
in-tree register's reading.

Note the wording carefully: **"Designed to meet"** is a design intent statement,
not a certification, and **"at least 8 mm"** is below 12.6 mm regardless. So for
T1 and T2:

- the exemption fails on clause scope (§1), *and*
- there is no certificate to invoke even if it did not, *and*
- the part's own claimed figure is short of the requirement anyway.

Three independent reasons, any one of which is sufficient.

**T2 is already de-scoped and is not a live sourcing problem.** It sits at
`(100.0, 300.0)` in `pcb/temper.kicad_pcb` — off the board outline — and
`docs/hardware/BOM.md` §4.4 marks OCP-02's T2/R65/C37 **DNF: "do not populate,
do not place, do not cost"** as of 2026-08-16. T2 still trips the geometric
measurement because the footprint is still in the netlist, but it is not a part
that will be bought or fitted. **The live CT problem is T1 only.**

### 5.3a T1 — no compliant drop-in exists; the fix is a change of sensing mechanism

**Stated plainly, as the brief asked: no commercially available current-sense
transformer meets this requirement while remaining a drop-in.** The exhaustive
survey is in-tree at `docs/evidence/2026-07-30-pd3-part-selection-k1-c6-t1.md`
§3, whose figures are datasheet-cited. I did not re-run it — this session's web
search budget was exhausted before I reached this category, which I record here
rather than papering over. What I *did* independently verify is the incumbent
(§5.3). The survey's own results:

| part | primary↔secondary creepage (datasheet) | sensed current | verdict |
|---|---|---|---|
| Coilcraft CST3015-100ED (incumbent) | "at least 8 mm" | 88 A | short of 12.6 mm |
| Coilcraft CST1211 | 9 mm creepage / 8 mm clearance | 28 A max | short, and under the 50 A trip |
| Coilcraft CS4100V-01L | **3 mm** | 35 A max | far short |
| TDK B78419A | ≥ 6 mm | ~30 A | short |

The requirement that disqualifies most alternatives is not creepage at all: T1's
burden and OCP-01 comparator are built around **1:100** and the trip sits at
**50.1 A**, so a replacement must sense meaningfully above 50 A or the core
saturates and the OCP trips late or never. Higher hipot ratings do **not** track
with more PCB creepage — CS4100V-01L has 3750 V rms hipot with 3 mm creepage.
That is the same lesson as the relay case: an internal withstand rating and an
external pad-to-pad distance are different numbers.

**But it is not a physics ceiling.** The survey's §3.5 follow-up found that
aperture/toroid CTs (Talema ASM, ICE Components CT07/CT08/CT10) have **no primary
PCB pin at all** — the primary is whatever wire or bus bar the designer threads
through the core bore. For those parts the primary-to-secondary pad-to-pad
distance stops being a component constant and becomes a board-layout choice,
which dissolves this specific failure mode by construction.

The cost is real and should not be understated: those parts are ratio-mismatched
by orders of magnitude (ASM ≈ 1:163 000 effective, CT07 1:1000, CT08 1:1200), so
adopting one means redesigning the turns ratio, the burden resistor and the
OCP-01 comparator reference divider together. The ICE parts additionally carry
**no third-party insulation certificate** — only manufacturer hipot testing and a
UL-94V-0 flammability mark, which is a clause-30.2 materials rating, not
clause-29 insulation coordination.

**So T1's honest disposition is: change the sensing mechanism, or send it to the
lab.** It is not a part-substitution problem and no purchase order fixes it.

### 5.4 Why every incumbent lands on 8 mm — the PD2 cliff, confirmed in three vendors' own numbers

The brief's hypothesis was that 8 mm is the industry-standard reinforced-isolation
creepage and that it is exactly the PD2 figure. Three unrelated datasheets read
this session say so independently:

| part | vendor's own stated external creepage | vendor's stated pollution degree |
|---|---|---|
| TI UCC21550 (DWK) — U6 | CPG **> 8 mm** | **2** |
| TI ISO7741 (DW-16) — the narrow sibling | CPG **> 8 mm** | **2** |
| Coilcraft CST3015-100ED — T1/T2 | "at least **8 mm** creepage/clearance" | not stated |

8.0 mm is 2 × 4.0 mm — Table 17 row iv, **pollution degree 2**, material group
IIIa/IIIb, doubled for reinforced. The component industry converged on the PD2
reinforced figure, and two of the three datasheets say "pollution degree 2" in
as many words. That is why the corridor sweep finds its feasibility cliff at
exactly 8.0 mm, and it is why this is a **category-wide** problem rather than a
bad-part-choice problem: the parts are all built to a bar this board does not
get to use.

---

## 6. Where this leaves each part

| ref | live? | exemption | part sourced? | remaining blocker |
|---|---|---|---|---|
| C6 | yes | no | **yes, but** — TDK B81123C1562M000, measured **20.10 mm** | **0 stock until 2027-01-20**; the stocked 2.2 nF/15 mm fallback only clears with a shrunk pad (0–0.4 mm margin) |
| K1 | yes | no | **yes** — TE Schrack RT33K012, measured **17.80 mm**, 1,197 in stock | **does not fit at K1's site**; needs re-placement/reroute (body is smaller, so no area pressure) |
| U6 | yes | no | **no isolated gate driver reaches it** (ceiling ~8–8.5 mm); slot rescue is illusory (§5.2a) | route exists — TI **ISO7741 in DUW/DWW-16, CPG > 21.2 mm** — but it is a gate-drive topology change and a large footprint |
| T1 | yes | no | **no compliant drop-in exists** (§5.3a) | needs a change of sensing mechanism (aperture CT) or lab adjudication |
| T2 | **no — DNF** | no | n/a | de-scoped 2026-08-16; still trips the geometric gate |

## 7. What the owner has to decide

1. **The exemption is closed.** Do not add a certification carve-out to any DRC
   rule. IEC 60335-1 cl. 24.1 scopes the component-standard creepage
   substitution to functional insulation, and this barrier is reinforced.
   `MIN_BARRIER_WIDTH_MM` = 12.6 stands, unchanged by this work.

2. **K1 is solved on paper and needs board work only.** RT33K012 is certified,
   stocked (1,197 units), independently re-measured at 17.80 mm, and physically
   *smaller* than the part it replaces. The only blocker is re-placement/reroute
   at its site.

3. **C6 needs a procurement decision before any board work.** The specified
   5.6 nF part has the best geometry and **no stock until 2027-01-20**. The
   stocked 2.2 nF/15 mm alternatives keep the design value but clear 12.6 mm only
   with a deliberately tightened land pattern, at 0.0–0.4 mm margin — and the
   repo already recorded the same part as a "false solve" at stock pad size.
   Pick: wait for stock and sign off the 2.5× capacitance change against touch
   current, or accept a near-zero-margin land pattern. **Do not let the second
   option be chosen implicitly by someone shrinking a pad to make the DRC go
   green.**

4. **U6 and T1 have no part-level fix, and the slot does not substitute for
   one.** §5.2a is the load-bearing finding: milling the laminate raises the
   board path only, while the package path — > 8 mm for the UCC21550, ≥ 8 mm
   claimed for the CST3015 — continues to govern. Adopting the slot would move
   the DRC number without moving the hazard. The in-tree route already
   identified for U6 (a discrete certified digital isolator plus a local
   secondary-side driver per switch, reported at > 14.5 mm) is a **topology
   change**, and it is the honest shape of the fix.

5. **Two determinations must go to the certification lab, and both can only
   raise the bar.** IEC 60664-4 Table 2 governs alongside Table 17 wherever
   working voltage is periodic above 30 kHz — which is T1, T2 and U6 at
   44–50 kHz — and IEC 60664-4 is not obtainable. And `tank-out`'s peak working
   voltage has never been derived, with the adjacent node at 923.7 V pk /
   570.5 V rms; above 500 V rms, T1's reinforced requirement becomes **20.0 mm**,
   not 12.6 mm. Neither can be settled in-tree, and neither is an argument for
   relaxing anything.

---

## 8. Second independent vendor sweep — corrections, ceilings, and one datasheet trap

A second sourcing sweep (21 CT datasheets, ~20 gate-driver families) returned
after the sections above were written. It corrects two facts and hardens three
conclusions. Load-bearing claims re-verified by me directly.

### 8.1 Correction: U6 is a **DWK-14**, not a SOIC16W

The brief and the footprint filename both say `SOIC16W_Isolated`. The land
pattern at `pcb/libs/lib.pretty/SOIC16W_Isolated.kicad_mod` has **14 pads,
numbered 1–11 and 14–16** — verified by direct count. That is TI's **DWK**
(14-pin wide-body SOIC: the DW-16 lead frame with positions 12/13 omitted), which
matches `UCC21550BDWKR`. The filename is misleading; nothing else changes.

### 8.2 The 8.1 mm is TI's own HV land-pattern maximum — there is no headroom

Verified by me in the UCC21550 datasheet's land-pattern drawing (4224374/A), which
publishes two options side by side, four times over:

```
        IPC-7351 NOMINAL              HV / ISOLATION OPTION
   7.3 mm CLEARANCE/CREEPAGE       8.1 mm CLEARANCE/CREEPAGE
```

**The board is already on the HV/ISOLATION land.** The measured 8.1000 mm is not
an accident of layout — it is the maximum TI publishes for this package, chosen
deliberately to match the package's own > 8 mm CPG. This independently confirms
§5.2a: TI sized the land to the package's capability, so lengthening the board
path past it (by slot or otherwise) buys nothing the package can support.

### 8.3 Datasheet trap — do not buy ISO5852S on its stated 14.5 mm

TI's **ISO5852S** datasheet (SLLSEQ0C) §7.6 states **CLR = 14.5 mm and
CPG = 14.5 mm**. Taken at face value that clears 12.6 mm and looks like the
answer. It is not achievable at the pins, and the same document contradicts it:

- package **DW0016B** body is 10.1–10.5 mm × 7.4–7.6 mm, lead span
  9.97–10.63 mm — a 14.5 mm terminal-to-terminal path is geometrically impossible
  on a part whose widest dimension is 10.63 mm;
- the land-pattern page of the *same* datasheet states **8.1 mm
  CLEARANCE/CREEPAGE** for the HV/ISOLATION option, identical to UCC21550 (same
  DW0016B family).

**Treat the 14.5 mm as a datasheet error.** Recorded here so nobody re-finds it
and specifies it. This is exactly why every figure in this document is tied to a
package geometry rather than a single quoted number.

### 8.4 Isolated gate driver ceiling — 10.0 mm, and not a drop-in

| part | package | creepage | cert / PD |
|---|---|---:|---|
| **Broadcom HCNW3120** | DIP-8 widebody 400 mil | **10.0 mm** | UL 1577 E55361, 5000 V rms; DIN EN 60747-5-5; **PD2** |
| **Vishay VOW3120** | DIP-8 **and** SMD-8 widebody 400 mil (option 7) | **≥ 10 mm** | UL 1577 5300 V rms; **PD2**; no UL file no. in PDF |
| PI SIC1181KQ / SIC1182KQ | eSOP-R16B | 9.5 mm | UL 1577; VDE 0884-17 reinforced **pending** |
| Broadcom HCPL-316J | SO-16 | 8.3 mm | UL 1577 E55361; **PD2** |
| TI UCC21550 (incumbent) | DWK-14 | > 8 mm | UL 1577 5000 V rms; VDE 0884-17 reinforced; **PD2** |

**Maximum in the category is 10.0 mm; maximum in any surface-mount package is
9.5 mm. Nothing reaches 12.6 mm.** And the 10 mm parts are not substitutes: they
are **single-channel LED-input optocouplers**, so a half-bridge needs two plus LED
drive and a second isolated supply; propagation delay is **0.25 µs typ / 0.5 µs
max against the UCC21550's 33 ns**, which would force dead time to ~1 µs at
44–50 kHz; peak drive drops to 2.5 A against a gate demand already near 6.8 A;
and there is **no dead-time interlock and no DIS pin**, so the existing shutdown
path would have to be rebuilt. All of that cost still lands 2.6 mm short.

### 8.5 CT category — the negative result, quantified

**21 CT datasheets read end-to-end. Three state a creepage distance in mm; two
assert compliance qualitatively with no number; sixteen give only a
dielectric-withstand voltage and no creepage at all.** Roughly **1 in 7** CT
datasheets quantifies creepage. Talema's entire 28-page CT catalog returns **zero
hits** for "creepage" or "clearance" across all pages.

The largest creepage verified in any CT PDF is **9.2 mm** (ICE Components CT09) —
on a **6 A** part, ~10× below the current requirement. The incumbent's own 8 mm
claim is *below* the board's as-built 9.1 mm, confirming it is a floor rather than
a measured terminal-to-terminal figure.

Best remaining lead, **vendor-listing only — do not put on a PO**: Pulse
**PAS6322** series, marketed by Digi-Key as "10 mm extended creepage", 50 A,
20 kHz–1 MHz. **Datasheet not retrieved** (Pulse's server refused connection on
three attempts). Even on its own claimed numbers it fails both bars (10 mm < 12.6;
50 A < the 60 A window).

Aperture-primary parts that *do* fit the band and current: **Talema AS-406**
(1:500, 65 A) and **AS-407** (1:500, 80 A), 20 kHz–200 kHz. Both state **no
creepage figure and carry no agency file number** — only "Meets VDE norms". And
the size flag matters: **AS-406 is 30.0 mm tall against the CST3015's 15.2 mm**,
roughly double, on a board already only just placeable.

**Procurement risk on the incumbent:** Digi-Key returns **zero results** for
`CST3015-100ED` and for `CST3015`. Current stock for the part actually fitted is
**not established**.

### 8.6 Pollution degree 2 is universal across isolator certificates

Every IEC 60747-17 / VDE 0884 / DIN EN 60747-5-5 certificate read across both
sweeps — TI, Power Integrations, Broadcom, Vishay — states **Pollution Degree 2**.
Not one isolator certificate encountered is scoped to PD3. This generalises §5.4
well beyond the three datasheets I read myself: a hypothetical 12.6 mm isolator
would still carry a certificate whose own stated precondition this board does not
meet. Notably the **one** part in this whole exercise rated at **IEC 60664-1
pollution degree 3** is the TE Schrack RT33K012 relay (§5.1).

### 8.7 Two suggestions from the sweep that are declined here

**(a) Re-opening the PD3 determination.** The sweep observes that if a PD2
compartment prerequisite could be earned, "the industry-standard 8 mm becomes the
bar and the incumbent parts pass on their existing geometry." **Declined.**
`MIN_BARRIER_WIDTH_MM` = 12.6 is immutable for this work and PD3 governs per
`docs/evidence/2026-08-12-pollution-degree-resolution.md`. Recorded only so the
suggestion is visible and explicitly refused rather than quietly acted on. Note
also that the sweep's supporting point — that candidate parts are material group I
(CTI > 600) rather than IIIa/IIIb — does not move the figure, as the sweep itself
concedes: **Table 17's row is selected by the *board's* material group, not the
component's.**

**(b) The slot as "the only mechanism available".** The sweep endorses the
in-tree slot rescue. **§5.2a stands unchanged**, and §8.2 strengthens it: the slot
lengthens only the board path, while TI's CPG is defined across the *package
surface* at > 8 mm and TI's own HV land is sized to exactly that. The sweep did
not carry a package-path term. A slot at U6 or T1 would move the DRC number
without moving the hazard.

### 8.8 Caveats carried forward from the sweep

- The session's WebSearch budget (200/200) was exhausted early, so later retrieval
  was direct-URL only. **"None found" means "not found in the vendors reached."**
- CT vendors never reached at all: **Bourns** (incl. PCS020), **TDK/EPCOS**,
  **Murata**, **Triad**, **Signal Transformer**, **Amveco/Eaton**, and Coilcraft's
  own CS4xxxV / CST1211 / CSE / SCS families.
- Gate-driver families not retrieved: Broadcom ACNW3190/ACPL-32JT/352J/339J,
  Skyworks Si823x/827x/828x, onsemi (403), Toshiba TLP5214/351/358, Renesas, ADI
  ADuM4135/4136/4121 (timeouts).
- **ISO7741U (the §5.2b recommendation) needs vendor confirmation before
  commitment**: TI marks it a **preview** product, stock could not be confirmed,
  the §5.6 table says **DUW** while the §8 text says **DWW**, and the DUW
  mechanical drawing is absent from the retrieved PDF — so **package body
  dimensions are NOT VERIFIED**. Given §8.3, do not commit without TI confirming
  the package drawing directly.
- **A further consequence of the ISO7741 route, not previously stated:** moving
  the barrier to a digital isolator means the HV-side gate-driver bias supply must
  then cross the barrier too. That relocates the ≥ 12.6 mm requirement onto an
  isolation transformer rather than eliminating it. The topology change is larger
  than §5.2b implied.
