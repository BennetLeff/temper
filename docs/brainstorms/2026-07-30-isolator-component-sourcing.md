<!-- provenance: commit=66ae51fc75de41b191fccad4ff7472275d24d2aa dirty=false -->

# Isolator component sourcing: U7, U3, C6, K2, K3 against the 8.0mm and 10.0mm bars

Branch `docs/isolator-creepage-sourcing`, from `origin/main` at `66ae51fc`.
All gap figures below were reproduced live, on this checkout, by calling this
repo's own `compute_pad_groups` / `evaluate_isolator_feasibility`
(`packages/temper-placer/src/temper_placer/placer/cp_sat/isolation_barrier.py`)
against the real `pcb/temper.kicad_pcb` and `elec/domain_manifest.yaml` —
not copied from a prior document. Every datasheet figure cited below was
fetched in this session (URLs and page/section references given); nothing
was estimated or pattern-matched from a manufacturer's numbering scheme.

## 0. This is not a green field — read this first

**Three of the five parts are already partially fixed, and one document
this task pointed at does not exist.** Before sourcing anything, two facts
changed the shape of the work:

1. `docs/brainstorms/2026-07-29-mains-selv-barrier-requirements.md` (cited
   in this task's brief as PR #437) is **not in this repository**, on any
   branch, at any commit. PR #437 on `BennetLeff/temper` is a real, merged
   PR, but its actual content is an unrelated `STRATEGY.md` drift-gate
   change. The real analysis matching this task's description lives at
   `docs/evidence/2026-07-28-barrier-constrained-placement.md` (the CP-SAT
   `INFEASIBLE` run) and `docs/evidence/2026-07-28-isolator-sourcing-brief.md`
   (a prior sourcing pass covering these same five parts). This document
   independently re-verifies and extends that prior work; it does not just
   cite it.
2. **`elec/src/*.ato` (the schematic source of truth) already carries
   corrected MPNs and footprint *references* for C6, U3, and U7**, dated
   2026-07-28. `pcb/temper.kicad_pcb` (the board) does **not** — it still
   carries the original, undersized footprints for all five parts. K2/K3
   are unfixed in both source and board. This is a "board not resynced to
   source" gap, not a sourcing gap, for three of the five. See §6.

## 1. Live current state (reproduced this session)

```
$ uv run --no-sync python -c "... compute_pad_groups / evaluate_isolator_feasibility over C6,K2,K3,U3,U7 ..."

Ref  Footprint (as placed on the board)              gap_x     gap_y   achievable  @8.0mm  @10.0mm
C6   Capacitor_THT:C_Disc_D10.0mm_W5.0mm_P5.00mm     3.200    -1.800    3.200      NO      NO
K2   Relay_THT:Relay_SPDT_Omron-G5LE-1              -2.500    -0.500   -0.500      NO      NO
K3   Relay_THT:Relay_SPDT_Omron-G5LE-1              -2.500    -0.500   -0.500      NO      NO
U3   Package_DIP:DIP-6_W7.62mm                       6.020    -1.600    6.020      NO      NO
U7   lib:SOIC16W_Isolated (board's embedded copy)     7.250    -0.600    7.250      NO      NO
```

`achievable_gap_mm` is intrinsic pad geometry (best of 4 rotations) and does
not depend on corridor width, so a single run answers both the 8.0mm gate
(`scripts/check_isolation_keepout.py`, `MIN_BARRIER_WIDTH_MM = 8.0`) and the
disputed 10.0mm figure (`docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` §5.2,
"DC Bus to SELV / Reinforced / 400V pk / Min Required 10.0mm"). Live gate
run this session: `scripts/check_isolation_keepout.py` → exit 3, 1 violation
(no `MAINS_SELV_ISOLATION_BARRIER` keepout on the board) — unchanged from
the 2026-07-28 baseline, confirming the board itself has not moved.

For reference, the other three isolators (not in this task's scope, but
relevant to the two-bar framing in §7): K1 = 8.000mm (passes 8.0 exactly,
fails 10.0), T1 = 9.100mm (passes 8.0, fails 10.0), PS1 = 35.500mm (passes
both).

## 2. U7 — TI UCC21550 gate driver: **model/footprint error, not a part failure**

### The part itself clears 8.0mm with margin; the board's land pattern does not

Fetched directly this session: TI **UCC21550x**, document **SLUSE89C**, MAY
2023, **revised AUGUST 2024** (Rev. C) —
https://www.ti.com/lit/ds/symlink/ucc21550.pdf (54 pages, extracted and
read in full via `pdftotext`, not OCR/summary).

**§5.6 Insulation Specifications (independently re-extracted, page 7):**

| Symbol | Parameter | Value |
|---|---|---|
| CLR | External clearance | **> 8 mm** |
| CPG | External creepage | **> 8 mm** |
| DTI | Distance through insulation | > 17 µm |
| CTI | Comparative tracking index (DIN EN 60112) | > 600 V |

The part's own datasheet-rated clearance and creepage are both open-ended
above 8mm — this is not a knife-edge part. What fails is the **board's land
pattern**.

**§13 "EXAMPLE BOARD LAYOUT" (pages 46, 49 — both DW0016B and DWK0014A give
identical numbers, independently re-extracted):**

| Land pattern | Pad span | Pad size | **Stated clearance/creepage** |
|---|---:|---:|---:|
| IPC-7351 NOMINAL | 9.3mm | 2.0 × 0.6mm | 7.3mm |
| **HV / ISOLATION OPTION** | 9.75mm | 1.65 × 0.6mm | **8.1mm** |

TI's own footnote (1) to the insulation table: *"Care should be taken to
maintain the creepage and clearance distance of a board design to ensure
that the mounting pads of the isolator on the printed-circuit board do not
reduce this distance."*

**Packaging addendum (page 55, re-extracted):** confirms `UCC21550BDWKR` is
**Active, Production**, SOIC (DWK) | 14 pins, part marking `21550B`. Only
five orderables exist, all `...R` (tape-and-reel): `UCC21550ADWKR`,
`UCC21550ADWR`, `UCC21550BDWKR`, `UCC21550BDWR`, `UCC21550CDWKR`. There is
**no plain `UCC21550BDW` (no suffix) orderable part** — confirms a
pre-existing MPN defect independent of the geometry question.

### What's on the board today vs. what's already fixed in the library

- **`elec/src/components.ato:49`**: `mpn = "UCC21550BDWKR"` — already
  corrected (2026-07-28), matches the real orderable part above.
- **`pcb/libs/lib.pretty/SOIC16W_Isolated.kicad_mod`**: already rewritten
  (2026-07-28, `descr` self-documents the change) to TI's **HV / ISOLATION
  OPTION** land pattern — pads `1.65 × 0.6mm` at `±4.875mm` span, giving
  `9.75 - 0.825 - 0.825 = 8.100mm`.
- **`pcb/temper.kicad_pcb` (the board, read-only for this task)**: still
  carries the *board's own embedded copy* of the old footprint — pads
  `2.05 × 0.6mm` at `±4.65mm` span (verified directly, lines 8046-8072),
  giving the `7.250mm` measured above. KiCad footprints are baked into the
  board file at placement time; a library fix does not propagate until the
  board is re-synced/re-placed. **The fix exists. It has not been applied
  to the board.**

### Verdict: U7 is a footprint/model defect, not a sourcing problem, at 8.0mm

No new component is needed. `UCC21550BDWKR` on TI's own published HV land
pattern clears 8.0mm (8.100mm, 0.100mm margin — a "just clears it" result,
not a comfortable one). This is a **tooling/board-resync fix**, exactly the
category of finding this task's brief anticipated for U7.

### At the disputed 10.0mm bar: unresolved, flagged honestly

TI publishes exactly two land patterns for this package family, and **no
land pattern reaching a 10.0mm net copper gap exists for the UCC21550 in
either DW0016B or DWK0014A.** I checked TI's UCC21750 (5.7kV single-channel
driver, same DW SOIC-16 10.3×7.5mm body) as a candidate for a
larger-package reinforced gate driver — SLUSD78C, its own §6.6 Insulation
Specifications table (independently re-extracted) gives the **identical**
CLR/CPG **>8mm** figures on the **identical package**, so it does not help.
I did not find a manufacturer-published, in-production isolated gate-driver
land pattern in this power/pin-count class that converts to a 10.0mm net
copper gap under this repo's own (deliberately conservative, straight-line
pad-edge) geometry model. **This is reported as UNRESOLVED, not
estimated or worked around.**

One structural observation worth surfacing to whoever reconciles the 8.0mm
vs 10.0mm question: `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` §5.2's own
design table has a row **"Across UCC21550 | Reinforced | 400V | 10.0mm |
Per device spec"** — i.e. that document's own author already anticipated
that an isolator IC's *own* certified rating, not a literal board copper
gap, might be the correct thing to satisfy for this specific crossing. That
is a pre-existing carve-out in the disputed spec itself, not something I
am proposing to resolve the dispute here.

---

## 3. U3 — zero-cross-detect optocoupler: **lead-form problem, not a device problem (at 8.0mm)**

### Current state

`elec/src/components.ato:550`: `mpn = "H11L1TVM"` (onsemi) — already
corrected 2026-07-28. `pcb/temper.kicad_pcb` still places U3 on
`Package_DIP:DIP-6_W7.62mm` (300-mil, verified directly), giving the
`6.020mm` measured above. No `pcb/libs` file exists for this footprint — it
uses a stock KiCad library part, so there is no local library fix pending;
only the board placement needs to change.

### Datasheet, re-fetched this session

Fairchild/onsemi **H11L1M, H11L2M, H11L3M**, "6-Pin DIP Schmitt Trigger
Output Optocoupler," Rev 1.0.0 —
https://datasheet.octopart.com/H11L1SM.-Fairchild-Semiconductor-datasheet-8428600.pdf
(hosted mirror of the manufacturer datasheet; read directly).

- Ordering table defines lead-form suffixes: `T` = 0.4" (10.16mm) lead
  spacing, `V` = VDE 0884, `TV` = both. Package drawing gives the wide
  form's lead span as **0.400" (10.16mm) / 0.425" (10.80mm)**.
- Pinout: 1=Anode, 2=Cathode, 3=NC, 4=Vo, 5=GND, 6=Vcc — **identical** to
  the `.ato`'s declared pin mapping. Same die, same electrical behavior,
  different lead form only.
- Isolation voltage V_ISO = 7500 V_PEAK (t=1s); UL file E90700 vol.2; VDE
  file #102497 via the `V` option.

**Geometry, computed with this repo's own `pad_axis_radius` model
(independently re-run this session):**

```
Package_DIP:DIP-6_W10.16mm, 1.6mm round pads: 10.16 - 2×0.8 = 8.560mm
```

Clears 8.0mm (0.560mm margin) — meaningfully better margin than U7's
0.100mm.

### Verified candidate for the 8.0mm bar

**`H11L1TVM`** — onsemi, DigiKey product page 401266.

| Spec | Value | Source |
|---|---|---|
| Package | 6-DIP, 0.400" (10.16mm) lead spacing | DigiKey 401266; H11LxM datasheet package drawing |
| Isolation voltage | 4170 Vrms (DigiKey); V_ISO 7500 V_PEAK, t=1s (datasheet) | as cited |
| Approvals | UL E90700 vol.2; VDE file #102497 (via `V` option) | H11LxM datasheet, Features |
| Output | Open collector, sinks 16mA at 0.4V max | H11LxM datasheet |
| Supply | 3V–15V | DigiKey 401266 |
| Status/stock | Active, 1,701 + 6,000 factory stock | DigiKey 401266 |

**Caveat, carried forward and not resolved here:** the H11LxM datasheet
publishes V_ISO and a VDE file number but **no package creepage/clearance
figure**. Moving the pads to 10.16mm satisfies the board-level keepout
gate; it does not by itself establish a *certified reinforced-insulation*
rating for this working voltage, since the certificate itself was not
read. Flagged, not resolved.

### At the disputed 10.0mm bar: a genuine ≥10mm-creepage part exists, but it does not close this gate

I found and independently fetched **Vishay VOW136** — "Widebody, High
Isolation, High Speed Optocoupler, 1 MBd," Rev. 1.4, 13-Oct-2025, Document
Number 84156 — https://www.vishay.com/docs/84156/vow136.pdf.

| Spec | Value | Source |
|---|---|---|
| Package | DIP-8, 400 mil widebody (also SMD-8) | datasheet package dimensions, p.6 |
| **External creepage (datasheet-stated, DIP-8 widebody)** | **≥ 10mm** | Insulation Characteristics table |
| **External clearance (datasheet-stated)** | **≥ 10mm** | same table |
| VIORM / VIOTM | 1414 Vpeak / 8000 Vpeak | same table |
| CTI | 250 | same table |
| Approvals | UL, cUL, DIN EN 60747-5-5 (VDE 0884-5) | Agency Approvals, p.1 |
| Lead pitch (row spacing) | 10.16mm typ. | Package Dimensions, p.6 |
| Ordering | `VOW136-X001` (DIP-8, 400mil, through-hole) | Ordering Information, p.1 |
| Pinout | 1=NC, 2=Anode, 3=Cathode, 4=NC, 5=GND, 6=VO, 7=VB, 8=VCC | p.1 |

**This is not a drop-in for H11L1.** It's a logic-output family (VO pin
with defined VOL/leakage-IOH, not a raw Schmitt-trigger phototransistor),
driven at IF=16mA typical (vs. H11L1's ≤1.6mA turn-on grade the existing
LED-drive resistor was specifically sized for), with a different pinout
(8 pins, not 6; VCC/VB present). Swapping in this part means re-deriving
the LED drive resistor and re-checking the output stage, not just changing
an MPN.

**And critically, it still does not clear a 10.0mm *board copper gap*
under this repo's model.** Same computation, same pitch as H11L1TVM's
10.16mm row spacing:

```
10.16mm pitch, 1.6mm round pads: 10.16 - 2×0.8 = 8.560mm  (same as H11L1TVM)
```

The datasheet's "≥10mm creepage" figure is measured **along the package
body surface** (the certified isolation path), which is longer than the
straight-line PCB pad-edge-to-pad-edge gap this repo's gate measures for
the same lead pitch — the same tension already flagged for U7/T1 in the
prior evidence doc. **No DIP/SMD optocoupler package was found, at any
pin count, whose *board-level straight-line copper gap* reaches 10.0mm** —
package body width caps out around 11mm total, and pad diameter always
eats back into the pitch. Closing this gap on the board itself (as opposed
to accepting the component's own certified rating) would require either a
non-standard, non-vendor-published land pattern (would need independent
qualification, not done here) or accepting the "per device spec" carve-out
language already present in `HIGH_VOLTAGE_CLEARANCE_SPEC.md` §5.2.
**UNRESOLVED at the 10.0mm board-copper bar; flagged, not estimated.**

---

## 4. C6 — Y-capacitor, mains-derived return to protective earth: **genuinely under-pitched; both a footprint fix (8.0mm) and possibly a new part (10.0mm)**

### Electrical requirement

`elec/src/modules.ato:904-908`: 2.2nF ±20%, **Y1** class (not Y2 — the old
board stub footprint's `descr` says Y2, a different, weaker safety class),
≥250VAC r.m.s. line-to-ground, through-hole, bonding the doubler midpoint
(a mains-derived node) to protective earth in a Class I appliance under
IEC 60335-1.

### Current state

`elec/src/modules.ato:957-958`: `mpn = "VY1222M47Y5UQ6TV0"`,
`footprint = "Capacitor_THT:C_Disc_D12.5mm_W5.0mm_P10.00mm"` — already
corrected 2026-07-28. `pcb/temper.kicad_pcb:3395-3407` (verified directly)
still carries C6 on the original **`Capacitor_THT:C_Disc_D10.0mm_W5.0mm_P5.00mm`**
stub, whose own `descr` reads *"Stub for safety capacitor (Y2 type)...
Created to resolve netlist reference"* — i.e. this was never a real part's
footprint, it was a placeholder. That stub is what produces the measured
3.200mm gap.

### Verified candidate for the 8.0mm bar

**`VY1222M47Y5UQ6TV0`** — Vishay BCcomponents, VY1 series. Re-fetched this
session: **Vishay document 28537, Rev. 18-Aug-2025** —
https://www.vishay.com/docs/28537/vy1series.pdf (independently
`pdftotext`-extracted and read).

| Spec | Value | Source |
|---|---|---|
| **Class** | **X1 (760 VAC), Y1 (500 VAC)**, per IEC 60384-14 | title block, p.1 |
| Capacitance | 2200 pF ±20% | technical data table, p.2, row `VY1222#47Y5UQ6###` |
| Rated voltage | Y1: 500VAC — exceeds the 250VAC requirement | title block |
| **Lead spacing (F)** | 10.0mm (this part) or 12.5mm (sibling, see below) | technical data table, "10.0 or 12.5" |
| Body max diameter | 12.0mm | technical data table |
| Ordering code (independently decoded from the datasheet's own table, p.4) | `T`=tape&reel, `V`=inline kinked, `0`=10.0mm spacing | Ordering Code section |
| Stock (DigiKey 2824499) | Active, 365 in stock | DigiKey, this session |

**Geometry (re-run this session against the repo's own model):** on the
stock KiCad `Capacitor_THT:C_Disc_D12.5mm_W5.0mm_P10.00mm` footprint (2.0mm
pads), `10.00 - 2×1.0 = 8.000mm`. Passes 8.0mm **exactly**, zero margin — a
smaller pad (1.4-1.6mm, reasonable for a 0.6mm lead) buys margin back:
1.6mm pads → 8.400mm, 1.4mm pads → 8.600mm. This footprint is **stock KiCad
9**, no new library file needed, and `docs/evidence/2026-07-28-tank-cap-and-isolator-footprints.md`
already confirmed this exact land pattern is collision-free at C6's current
board position (clear by 6.15mm).

**Real Murata part it was probably reaching for, checked and rejected:**
`DE1E3KX222MA4BN01F` (Murata's real spelling of the fabricated
`DE1E3KX222MA4BA01` in the pre-2026-07-28 source) is **DigiKey 4421160,
Obsolete, 0 stock**. Do not design it in.

### At the disputed 10.0mm bar: a real candidate exists, but needs a new (unstocked) footprint

Vishay's own datasheet states the VY1 2200pF/Y5U part is available at
**either 10.0mm or 12.5mm lead spacing** (same technical data table,
"10.0 or 12.5" column). Decoding the manufacturer's own published ordering
code (not a pattern-matched guess): changing the final digit from `0`
(10.0mm) to `X` (12.5mm) gives **`VY1222M47Y5UQ6TVX`**.

I checked this specific, fully-decoded part number against DigiKey rather
than writing it down unverified: it **is a real, listed catalog entry**
(confirmed via DigiKey's own product filter for the `VY1222M47Y5UQ6` family
this session), alongside sibling packaging/lead-style variants at the same
12.5mm spacing (`VY1222M47Y5UQ6UVX`, `VY1222M47Y5UQ6TLX`, etc.). **All of
them currently show 0 units on hand ("0 in stock" / "check lead time")** —
this is a real, orderable Vishay catalog part, not a part in active
distributor stock today. Reported honestly, not rounded up to "verified
in stock."

**Geometry (computed with the repo's own model this session):**

```
12.50mm pitch, 2.0mm round pads: 10.500mm
12.50mm pitch, 1.6mm round pads: 10.900mm
12.50mm pitch, 1.4mm round pads: 11.100mm
```

**This clears the 10.0mm bar comfortably** (0.5-1.1mm margin depending on
pad choice) and even approaches the spec doc's own "Design Value" column
(12.0mm) with smaller pads. **No stock KiCad footprint exists at 12.5mm
disc pitch** (checked: `Capacitor_THT.pretty` has `P10.00mm` variants at
several body diameters, no `P12.50mm` variant) — a new footprint would need
to be created, following the same pattern as the existing
`C_Disc_D12.5mm_W5.0mm_P10.00mm` (body ≥ 12.0mm, width ≥ 5.0mm, pitch
12.50mm). Not done in this pass — `pcb/libs/**` may only be edited where a
datasheet *proves the current geometry wrong*, and this would be adding a
new footprint for a not-yet-selected part, not correcting an existing one.

---

## 5. K2 / K3 — bus-discharge relays: **genuinely inadequate, unfixed in source and board, needs a different device**

### Current state

`elec/src/modules.ato:1121-1128`: `k_dis1.mpn`/`k_dis2.mpn = "G5LE-1 DC12"`
(Omron), footprint `Relay_THT:Relay_SPDT_Omron-G5LE-1`, **unchanged** —
this is the one part of the five where the schematic source was never
updated. `pcb/temper.kicad_pcb:3782-3841` (verified directly): both K2 and
K3 still on the same footprint.

### Why no footprint fix can close this

The G5LE-1's terminal layout (from the board's own placed pad coordinates,
frame mm): COM at (0.0, -7.1), the two coil terminals at (-6.0, -5.1) and
(6.0, -5.1). The pole terminal sits 2.0mm from a coil terminal in Y and
level with the other in X — **both axes negative** on every rotation. No
land-pattern change, pad shrink, or rotation can produce 8mm from this
arrangement; the copper has to be where the pins are. (The
`corridor_width_mm=1.0` control run in `2026-07-28-barrier-constrained-placement.md`
already showed K2/K3 fail even at a 1mm corridor, confirming this is a
terminal-topology fact, not a width-sensitivity artifact.) This is
explicitly **not** an insulation-quality problem — the G5LE-1's own
coil-contact insulation (`modules.ato:906-908`: 2000VAC dielectric, 4.5kV
impulse) is fine. The part was simply never designed to have its coil and
contacts on opposite sides of a PCB barrier.

### Electrical requirement a replacement must meet

From `modules.ato:837-1092` (`BusDischarge` module):

| Requirement | Value | Why |
|---|---|---|
| Contact form | SPDT / 1 form C, accessible NC contact | Fail-safe: coils energized → NC open (discharge disengaged); loss of power closes NC |
| Coil | 12VDC nominal, via a 100Ω dropper (`RC1206FR-07100RL`) from the 15V SELV rail | ~32.6mA, ~11.7V at the coil with a 360Ω coil |
| Contact duty | Break ~21.8mA at up to 170VDC, resistive, with an RC snubber (100Ω 2W + 470nF/630V PP) across NC-COM | `modules.ato:875-890` |

**Note: the 170VDC DC break is already out-of-catalog on the G5LE-1**
(design's own comment, `modules.ato:875-880`: "max switching voltage is
125VDC... a 170VDC break is out-of-catalog at ANY current"), mitigated by
the snubber, not the relay. **No candidate below fixes this separately
tracked open item** — it is called out explicitly per candidate so it does
not get silently absorbed into "problem solved."

### Verified candidate — clears BOTH bars

**`RT314012`** — TE Connectivity / Schrack Power PCB Relay **RT1** family.
Re-fetched this session directly from TE's document server (revision date
in the document metadata: **2025-06-20**) —
https://www.te.com/commerce/DocumentDelivery/DDEController?Action=showdoc&DocId=Data+Sheet%7FRT1%7F0718%7Fpdf%7FEnglish%7FENG_DS_RT1_0718.pdf%7F9-1393239-8
(independently `pdftotext`-extracted and read; TE's own catalog document
number is `ENG_DS_RT1_0718`).

| Spec | Value | Source |
|---|---|---|
| Contact arrangement | 1 form C (CO) | Product Information table, RT314 row |
| **Coil-to-contact clearance/creepage** | **≥ 10 / 10 mm** | Insulation Data table (independently re-extracted) |
| Coil-contact dielectric strength | 5000 Vrms | same table |
| Feature claim | **"5kV/10mm coil-contact, reinforced insulation"** | Features, line 1 |
| Standards | "Product in accordance to IEC 60335-1" | Features — the same standard the board's own 8.0mm figure is drawn from |
| Coil, code 012 | Rated 12VDC, operate 8.4V, release 1.2V, **360Ω ±10%, 400mW** | Coil Versions, DC Coil table |
| Contact rating | 16A / 250VAC rated, **400VAC max switching voltage** | Contact Data table |
| Material group | IIIa | Insulation Data table |
| Approvals | VDE Cert. 40007571, cULus E214025, cCSAus 1142018 | p.1 |
| Part table entry | `RT314012`, contact material AgNi 90/10, TE part numbers **9-1393239-5** (Austria) / **1-1649328-3** (China) | Product Information table (independently re-extracted, exact row match) |
| Status/stock (DigiKey 1128622) | Active, **7,442 in stock** (14-week factory lead time for more) | DigiKey, this session |

**Coil is a drop-in for the existing dropper:** 360Ω/400mW is identical to
the G5LE-1's own declared coil (`modules.ato:907`), so `r_coil1`/`r_coil2`
(100Ω) keep delivering ~11.7V, comfortably above the RT1's 8.4V
must-operate.

**Board-level geometry** (re-run this session on the stock
`Relay_SPDT_Schrack-RT1-16A-FormC_RM5mm` footprint): `achievable = 12.760mm`
— clears **both** 8.0mm and 10.0mm bars, with margin left even against the
spec doc's 12.0mm "Design Value" column (0.76mm short of *that*, for the
record, but that is not either of the two bars this task asked for).
**This part clears the requirement two ways independently — the
manufacturer's own coil-contact rating (≥10/10mm) and the board-level pad
geometry (12.76mm) — which is the strongest evidentiary position of any
candidate in this document.**

**Package/footprint impact:** courtyard grows from the G5LE-1's
17.0×23.0mm (391 mm²) to the RT1-16A-FormC's 29.9×13.6mm (407 mm²) — +4%
area, but a long/thin aspect ratio (coil at one end) that is favorable for
a barrier-constrained placement. Not a KiCad-stock footprint issue: `Relay_SPDT_Schrack-RT1-16A-FormC_RM5mm`
exists in the stock `Relay_THT.pretty` library.

**Honest caveats (not resolved by this candidate):**
1. RT1's DC breaking capacity at 170V is published only as a graph image
   in the datasheet PDF, not machine-extractable; the existing snubber
   argument carries over unchanged.
2. DigiKey's parametric "Coil Current: 14.2 mA" figure for RT314012
   contradicts the datasheet's own 360Ω/12V (=33.3mA) figure. Unresolved;
   confirm the actual delivered coil resistance at procurement before
   assuming the 100Ω dropper's sizing holds.
3. Same-family alternatives `RT114012` (12A, 3.5mm pinning) and
   `RT214012` (12A, 5mm pinning) appear in the same datasheet's product
   table with real TE part numbers but their distributor stock was **not**
   checked this session — do not substitute either without checking.

---

## 6. Summary table

| Ref | Genuinely inadequate, or model/footprint error? | Current gap | Fix @ 8.0mm | Fix @ 10.0mm |
|---|---|---:|---|---|
| **U7** | **Footprint/model error.** Part's own CLR/CPG both >8mm. | 7.250mm | Board resync to TI's own published HV/ISOLATION land pattern — **already written into `pcb/libs/lib.pretty/SOIC16W_Isolated.kicad_mod`**, not yet applied to the board (8.100mm, 0.100mm margin) | **UNRESOLVED** — no TI (or checked alternative) land pattern reaches 10.0mm net copper gap |
| **U3** | **Lead-form error (8.0mm); part-family question (10.0mm).** Same die as declared, wrong pitch. | 6.020mm | `H11L1TVM` on stock `DIP-6_W10.16mm` — **already written into `elec/src/components.ato`**, not yet on the board (8.560mm) | **UNRESOLVED** — `VOW136` (Vishay, ≥10mm datasheet creepage) exists but converts to the same 8.560mm board copper gap at its 10.16mm pitch; not a drop-in (different pinout/drive) either way |
| **C6** | **Footprint error (8.0mm) + real MPN correction; possibly new part (10.0mm).** Declared part always had 10mm lead spacing; the board footprint is an unsourced stub. | 3.200mm | `VY1222M47Y5UQ6TV0` on stock `C_Disc_D12.5mm_W5.0mm_P10.00mm` — **already written into `elec/src/modules.ato`**, not yet on the board (8.000mm exact) | `VY1222M47Y5UQ6TVX` (real, decoded, DigiKey-listed, 0 in stock) on a **new** 12.5mm-pitch footprint (not stock) → 10.500-11.100mm depending on pad size |
| **K2** | **Genuinely inadequate.** Terminal topology (COM 2mm from a coil pin, both axes) — no rotation or land pattern helps. | -0.500mm | `RT314012` (TE Schrack RT1) — **not yet written anywhere in source or board** | Same part — clears both bars: manufacturer's own ≥10/10mm rating AND 12.760mm board geometry |
| **K3** | Identical part, identical problem, as K2 | -0.500mm | Same as K2 | Same as K2 |

**"Genuinely inadequate" in the strict sense this task asked (needs a
different physical device, not just a different footprint of the same
part) applies to K2 and K3 only.** U7, U3, and C6 are footprint/MPN
defects on parts that were always adequate (U7, C6's Y1 rating) or a
lead-form variant of the exact declared die (U3) — matching the pattern
this task's brief called out as having already happened twice on this
board (K1's Faston tabs, the ESP32 pad transposition).

## 7. Documentation gap found while doing this (reported, not fixed)

`docs/hardware/BOM.md` documents the C6 and U7 corrections at length (with
its own dated notes) but **has no line item for U3 at all** — the
`zcd_opto` component (only its divider/clamp support parts, `R_ZCD_TOP1/2`,
`R_ZCD_BOT`, `D_ZCD_CLAMP`, are listed). `elec/src/modules.ato` instantiates
it (`zcd_opto = new H11L1`, line 1024) and `components.ato` carries the
corrected MPN, but the BOM is silent on it. Not fixed here — BOM edits are
outside this task's scope (analysis and sourcing, not a fait-accompli
part/BOM change) — but flagged because a missing BOM line is exactly the
kind of drift this project's own gates exist to catch, and this one isn't
caught by anything currently.

## 8. What I could not verify (stated plainly)

- **IEC 60335-1's own primary text** for either the 8.0mm or 10.0mm
  creepage figures remains paywalled; not independently re-derived here,
  same as every prior evidence doc's own UNVERIFIED note.
- **No 10.0mm-bar candidate for U7** was found. Checked TI UCC21550 (both
  land patterns) and TI UCC21750 (larger single-channel part, same
  package) — neither clears it. Did not exhaustively survey every
  reinforced isolated gate driver on the market; this is reported as
  "not found in the time available," not "does not exist."
- **No 10.0mm-*board-copper*-bar candidate for U3** was found, despite
  finding a component (`VOW136`) whose own datasheet claims ≥10mm
  creepage — the board-level gate's straight-line geometry model is
  stricter than any DIP/SMD package's certified body-surface creepage
  path converts to at achievable lead pitches.
- **`VY1222M47Y5UQ6TVX`'s (C6, 10mm-bar candidate) stock status**: listed
  by DigiKey as a real catalog entry, 0 on hand, "check lead time." Not
  confirmed as immediately purchasable.
- **RT114012 / RT214012 (K2/K3 same-family siblings) distributor stock**:
  not checked. Only `RT314012` is the part I am putting a citation behind.
- **DigiKey's 14.2mA coil-current figure for RT314012** vs. the
  datasheet's 360Ω/400mW: contradiction noted, not resolved — confirm at
  procurement.
- **H11L1TVM's and VOW136's certified creepage/clearance *certificates***
  (as opposed to VIORM/VIOTM/VDE-file-number data on the datasheet page):
  not read. The lead-form/pitch fixes the board geometry; whether the
  component itself carries a reinforced-insulation *certificate* at this
  working voltage is a separate, unresolved question for both.
- **RT1's DC breaking capacity at 170V**: published only as a graph image
  in the PDF, not machine-extractable. The 170VDC open item on K2/K3
  carries over unchanged regardless of which relay is chosen.

## 9. Hard-constraint compliance

- `pcb/temper.kicad_pcb`: **not modified** (read-only per this task;
  verified `git status --short` clean apart from this new file).
- `pcb/libs/**`: **not modified** by this task (the one file that already
  differs from a stock library, `SOIC16W_Isolated.kicad_mod`, was changed
  in a prior session on 2026-07-28, with its own datasheet-cited `descr`
  justifying the change against SLUSE89C — reused and re-verified here,
  not re-touched).
- `elec/src/*.ato`, `docs/hardware/BOM.md`,
  `mpn-fabrication-allowlist.yaml`: **not modified.** No BOM
  part-number substitution was committed as a fait accompli — every
  candidate is presented with citations for a human purchasing decision,
  per this task's scope boundary.
- No MPN in this document was constructed by pattern-matching a
  manufacturer's numbering scheme against an unconfirmed target. Every
  part number was either read directly off a fetched datasheet/distributor
  page (`UCC21550BDWKR`, `H11L1TVM`, `VY1222M47Y5UQ6TV0`, `RT314012`,
  `VOW136-X001`), or decoded from the manufacturer's own explicit,
  published ordering-code table and then checked against a live
  distributor listing before being written down (`VY1222M47Y5UQ6TVX`).
- The 8.0mm creepage requirement was never reduced, and no gate, baseline,
  or threshold was weakened. Both the 8.0mm and 10.0mm bars are reported
  for every candidate; neither was picked silently.
- No `git stash` used anywhere in this session.

## Sources (all fetched this session)

- TI UCC21550x, **SLUSE89C**, MAY 2023, revised AUGUST 2024 —
  https://www.ti.com/lit/ds/symlink/ucc21550.pdf. Used: §5.6 Insulation
  Specifications (CLR >8mm, CPG >8mm, DTI >17µm, CTI >600V); §13 Example
  Board Layout for DW0016B and DWK0014A (IPC-7351 nominal: 9.3mm span,
  7.3mm clearance/creepage; HV/ISOLATION OPTION: 9.75mm span, 8.1mm
  clearance/creepage); Packaging Information addendum (orderable part
  numbers and status).
- TI UCC21750, **SLUSD78C**, FEBRUARY 2019, revised JANUARY 2023 —
  https://www.ti.com/lit/ds/symlink/ucc21750.pdf. Used: Features (DW
  SOIC-16, 10.3×7.5mm, creepage/clearance >8mm); §6.6 Insulation
  Specifications (CLR >8mm, CPG >8mm — checked as a candidate for the
  10.0mm bar, does not clear it).
- Fairchild/onsemi H11L1M/H11L2M/H11L3M, Rev 1.0.0 —
  https://datasheet.octopart.com/H11L1SM.-Fairchild-Semiconductor-datasheet-8428600.pdf.
  Used: Ordering Information (T/V/TV lead-form suffixes); package drawing
  (0.400"/10.16mm wide lead form); Isolation Characteristics (V_ISO 7500
  V_PEAK); Schematic (pinout).
- Vishay BCcomponents VY1 Series, doc **28537**, Rev. **18-Aug-2025** —
  https://www.vishay.com/docs/28537/vy1series.pdf. Used: title/class (X1
  760VAC, Y1 500VAC); technical data table (2200pF Y5U row, F = 10.0 or
  12.5mm ±1mm); Ordering Code table (full digit-by-digit decode, including
  the `X` = 12.5mm lead-spacing digit).
- Vishay VOW136, Rev. **1.4, 13-Oct-2025**, Document Number 84156 —
  https://www.vishay.com/docs/84156/vow136.pdf. Used: Features (external
  creepage >10mm, reinforced isolation); Insulation Characteristics table
  (clearance/creepage ≥10mm DIP-8 widebody, VIORM 1414V, VIOTM 8000V, CTI
  250); Ordering Information (`VOW136-X001`); Package Dimensions (10.16mm
  typ. row spacing); pinout diagram.
- TE Connectivity / Schrack Power PCB Relay RT1, document
  `ENG_DS_RT1_0718`, metadata date **2025-06-20** —
  https://www.te.com/commerce/DocumentDelivery/DDEController?Action=showdoc&DocId=Data+Sheet%7FRT1%7F0718%7Fpdf%7FEnglish%7FENG_DS_RT1_0718.pdf%7F9-1393239-8.
  Used: Features ("5kV/10mm coil-contact, reinforced insulation"; "Product
  in accordance to IEC 60335-1"); Insulation Data (coil-contact
  clearance/creepage ≥10/10mm, 5000Vrms, material group IIIa); Coil
  Versions DC (012: 8.4V operate, 1.2V release, 360Ω±10%, 400mW); Contact
  Data (400VAC max switching); Product Information table (RT314012 row,
  TE part numbers 9-1393239-5 / 1-1649328-3).

**Distributor pages, fetched this session:**

- TI `UCC21550BDWKR` — confirmed via the datasheet's own packaging
  addendum (no separate distributor fetch needed; addendum is primary).
- onsemi `H11L1TVM` — DigiKey 401266 (Active, 1,701 + 6,000 factory stock).
- Vishay `VY1222M47Y5UQ6TV0` — DigiKey 2824499 (Active, 365 in stock).
- Vishay `VY1222M47Y5UQ6TVX` and sibling 12.5mm-spacing codes
  (`UVX`, `TLX`, `3VX`) — DigiKey product family filter for
  `VY1222M47Y5UQ6*` (this session; real listed part numbers, 0 on hand /
  "check lead time" for all 12.5mm variants).
- TE `RT314012` — DigiKey 1128622 (Active, 7,442 in stock).

**In-repo sources:**

- `packages/temper-placer/src/temper_placer/core/pad_geometry.py`,
  `.../placer/cp_sat/isolation_barrier.py` (the geometry model used for
  every gap figure in this document, re-run live, not copied).
- `scripts/check_isolation_keepout.py` (`MIN_BARRIER_WIDTH_MM = 8.0`,
  re-run live this session, exit 3).
- `docs/specs/HIGH_VOLTAGE_CLEARANCE_SPEC.md` §5.1/§5.2 (the disputed
  10.0mm figure and its "per device spec" carve-out language).
- `elec/src/modules.ato`, `elec/src/components.ato` (current MPN/footprint
  declarations for C6, U3, U7, K2, K3, verified directly, line numbers
  cited inline).
- `pcb/temper.kicad_pcb` (read-only; footprint state verified directly for
  all five refs, line numbers cited inline).
- `pcb/libs/lib.pretty/SOIC16W_Isolated.kicad_mod` (U7's already-corrected
  library footprint, not yet applied to the board).
- `docs/evidence/2026-07-28-barrier-constrained-placement.md`,
  `docs/evidence/2026-07-28-isolator-sourcing-brief.md`,
  `docs/evidence/2026-07-28-tank-cap-and-isolator-footprints.md` (prior
  work this document independently re-verifies and extends, not just
  cites).
- `docs/hardware/BOM.md` (current documented state; U3 documentation gap
  noted in §7).
