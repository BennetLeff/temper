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

**C6 — datasheet-verified, no open blocker.** 22.50 mm lead pitch, body
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
(`docs/evidence/2026-08-13-pd3-land-k1-c6.md`). **Footprint growth: significant,
and it is the binding problem.** This one needs re-placement, not re-sourcing.

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

---

## 6. Where this leaves each part

| ref | live? | exemption | part sourced? | remaining blocker |
|---|---|---|---|---|
| C6 | yes | no | **yes** — TDK B81123C1562M000, measured **20.10 mm** | board resync only; re-check the 8–15 % touch-current margin |
| K1 | yes | no | **yes** — TE Schrack RT33K012, measured **17.80 mm** | **does not fit at K1's site**; needs re-placement/reroute |
| U6 | yes | no | **no** — package ceiling; slot rescue is illusory (§5.2a) | needs a topology change, not a part swap |
| T1 | yes | no | **no** — none found at this ratio/current class | needs a topology change or lab adjudication |
| T2 | **no — DNF** | no | n/a | de-scoped 2026-08-16; still trips the geometric gate |

## 7. What the owner has to decide

1. **The exemption is closed.** Do not add a certification carve-out to any DRC
   rule. IEC 60335-1 cl. 24.1 scopes the component-standard creepage
   substitution to functional insulation, and this barrier is reinforced.
   `MIN_BARRIER_WIDTH_MM` = 12.6 stands, unchanged by this work.

2. **C6 and K1 are already solved on paper.** Both replacement parts are
   certified, orderable, and independently re-measured this session at 20.10 mm
   and 17.80 mm. What is missing is board work: a footprint resync for C6, and a
   genuine re-placement for K1, which currently collides with routing that was
   laid through space the incumbent Omron footprint left copper-free.

3. **U6 and T1 have no part-level fix, and the slot does not substitute for
   one.** §5.2a is the load-bearing finding: milling the laminate raises the
   board path only, while the package path — > 8 mm for the UCC21550, ≥ 8 mm
   claimed for the CST3015 — continues to govern. Adopting the slot would move
   the DRC number without moving the hazard. The in-tree route already
   identified for U6 (a discrete certified digital isolator plus a local
   secondary-side driver per switch, reported at > 14.5 mm) is a **topology
   change**, and it is the honest shape of the fix.

4. **Two determinations must go to the certification lab, and both can only
   raise the bar.** IEC 60664-4 Table 2 governs alongside Table 17 wherever
   working voltage is periodic above 30 kHz — which is T1, T2 and U6 at
   44–50 kHz — and IEC 60664-4 is not obtainable. And `tank-out`'s peak working
   voltage has never been derived, with the adjacent node at 923.7 V pk /
   570.5 V rms; above 500 V rms, T1's reinforced requirement becomes **20.0 mm**,
   not 12.6 mm. Neither can be settled in-tree, and neither is an argument for
   relaxing anything.
