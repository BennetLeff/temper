<!-- provenance: commit=34132799686105405b75f06533d51fa39a298cb9 dirty=true (baseline figures measured on a clean checkout of that commit -- PR #397's merge -- before any edit; "after" figures measured in the same tree with this branch's edits applied, hence dirty=true. Every before/after pair is labelled inline.) -->

# Tank capacitor 10× value error, and three isolator land-pattern defects

Branch `fix/tank-cap-and-isolator-footprints`, from `origin/main` at
`34132799` ("Merge pull request #397 from BennetLeff/feat/mpn-decoder-families").

Two defect sets, one shape: **the specified part does not fit its own land
pattern.** One of them (the tank capacitor) additionally specifies the wrong
part by a factor of ten.

**`pcb/temper.kicad_pcb` is not modified by this branch.** Footprint
*definitions* and component *assignments* are changed; nothing is re-placed.
The board-space consequences of the parts that grew are measured and reported
below rather than acted on.

---

## Summary

| Ref | Defect | Fixed here | Board rework still required |
|---|---|---|---|
| C25/C26 (`c_tank1`/`c_tank2`) | MPN decodes to 0.015 µF / 2000 V — **10× under** the declared 150 nF, at the wrong voltage; land pattern matches the wrong part | MPN → `FKP1T031507G00JSSD`, footprint → `C_Rect_L41.5mm_W20.0mm_P37.50mm_MKS4` | **Yes.** Case grows 31.5×13 → 41.5×20mm, pitch 27.5 → 37.5mm. C25 would overlap C5; C26 would hang 3.0mm off the board edge. |
| U7 (`UCC21550BDWKR`) | On TI's *IPC-7351 nominal* land pattern (7.3mm) when TI publishes an *HV / isolation option* (8.1mm) for the same package | Footprint definition retargeted to TI's HV option | **Yes** — the board carries its own embedded copy of the footprint. |
| U3 (`H11L1`) | 300-mil DIP land; the barrier needs the 400-mil lead form of the same device | MPN → `H11L1TVM`, footprint → `Package_DIP:DIP-6_W10.16mm` | **Yes**, but no collision: the enlarged outline is clear by 9.43mm. |
| C6 (`y_cap_pe`) | 5.00mm-pitch stub land; every 2.2 nF Y1 disc has 10mm lead spacing | Footprint → `Capacitor_THT:C_Disc_D12.5mm_W5.0mm_P10.00mm` | **Yes**, but no collision: clear by 6.15mm. |

**Everything in the "confirm the claim" column of the brief held up.** Nothing
in `docs/evidence/2026-07-28-isolator-sourcing-brief.md` was found to be
wrong; every geometry figure in it reproduces exactly on this branch.

---

## Part A — the resonant tank capacitor

### A.1 What the declared MPN actually says

`FKP1U021507E00JSSD`, decoded against **WIMA's own 18-digit part-number
system** (FKP 1 datasheet rev. 03.26, p.136 "WIMA Part Number System", which
enumerates every field):

| Field | Digits | Value | Meaning |
|---|---|---|---|
| 1–4 | `FKP1` | FKP 1 | series |
| 5–6 | `U0` | **2000 VDC** | rated voltage |
| 7–10 | `2150` | **0.015 µF** | capacitance |
| 11–12 | `7E` | 41.5mm case / PCM 37.5 family | size and PCM |
| 13–14 | `00` | 2-pin | version code |
| 15 | `J` | ±5 % | tolerance |
| 16 | `S` | bulk | packing |
| 17–18 | `SD` | 6-2 | pin length |

So the declared part is **15 nF at 2000 V** against a declared
`value = 150nF`, `voltage_rating = 1600V`. `scripts/mpn_fabrication_gate.py`
(the WIMA decoder landed in PR #397) reports exactly this, twice.

There is a second, independent error the decoder does not catch: **the
2000 VDC table has no 0.015 µF row in a size-7 case at all.** Its only
0.015 µF row is `FKP1U021506D` — W 13, H 24, L 31.5, PCM 27.5. The size code
`7E` belongs to 0.047 µF at that voltage. The declared string is therefore not
a datasheet row in either direction.

And the land pattern the board carries, `C_Rect_L31.5mm_W13.0mm_P27.50mm_MKS4`,
is **precisely the 6D case of `FKP1U021506D`** — 31.5 × 13.0mm on a 27.5mm
pitch. The board was drawn for the *mis-decoded* part, not for the declared
150 nF. That is the tell that fixes which of the two numbers is the typo: the
land pattern followed the MPN, and both drifted away from the value.

### A.2 The tank inductance, and which capacitance the circuit requires

**The tank inductance is 150 µH — as an explicitly labelled assumption, not a
specified component.** This is the input the task could not read from the
repo, so state it precisely, because the distinction matters:

- `elec/src/modules.ato` `ResonantTank` still declares
  `inductor_conn = new Resistor  # Placeholder for Litz interface`,
  `mpn = "CUSTOM_LITZ_COIL"`. **There is no inductance value in `elec/src`.**
- `docs/hardware/TANK_COIL_SPECIFICATION.md` (2026-07-26) is a specification
  *attempt* whose stated outcome is "**L cannot be specified from the current
  model**" — it withheld the number because the pan model's implied tank Q of
  143 (against ~14 for a real hob) made the delivered-power axis unusable.
- `elec/src/main.ato:80-89`, the comment block immediately above
  `f_switching = 47kHz`, names the working assumption in as many words:
  "at an **ASSUMED coil L=150uH** … ratio ≈ 1.25 over that assumption's K=0.79
  loaded resonance (**37.58 kHz**) delivers ~1804 W, holds ZVS (0.8 % margin)
  … This number is **CONTINGENT on L=150uH**."
- `simulation/harness/run_inductance_range_sweep.py` sweeps L ∈ [50, 250] µH
  around that assumption; `run_zvs_sweep.py` and `run_tank_coil_sweep.py` both
  hard-code `C_TANK_F = 300e-9` with the comment "`c_tank1` (150 nF) +
  `c_tank2` (150 nF) in parallel; **COMMITTED, fixed**".
- `docs/hardware/RESONANT_TANK_DESIGN.md` is an older document built on a
  different assumption again (80 µH uncoupled, 54–64 µH loaded) but the *same*
  ~300 nF tank capacitance.

So: **C is the committed quantity in this design and L is the free one**, and
the arithmetic runs in that direction.

**With 150 nF each (300 nF combined):**

```
f_res_loaded = 1 / (2π √(L_eff · C))
L_eff = L (1 − k²) = 150 µH × (1 − 0.79²) = 150 × 0.376 = 56.4 µH
f_res  = 1 / (2π √(56.4e-6 × 300e-9)) = 1 / (2π × 4.11e-6) = 38.7 kHz
```

which reproduces the 37.58 kHz the harness reports for that operating point to
within the coupling model's own rounding, and gives

```
f_sw / f_res_loaded = 47 kHz / 37.58 kHz = 1.25
```

— exactly the ratio `main.ato` states. It also sits comfortably inside the
declared `assert f_switching within 20kHz to 100kHz`.

The older 80 µH / 300 nF pairing lands in the same band:
`1 / (2π √(60e-6 × 300e-9)) = 37.5 kHz` loaded, 32.5 kHz unloaded.

**With 15 nF each (30 nF combined):**

```
f_res_loaded = 1 / (2π √(56.4e-6 × 30e-9)) = 1 / (2π × 1.30e-6) = 122 kHz
```

To bring 30 nF back inside the declared 20–100 kHz band you would need
`L_eff = 1/((2πf)² C)` = **84 µH … 2.11 mH** loaded, i.e. **225 µH … 5.6 mH**
of uncoupled coil at k = 0.79. To hit the committed 47 kHz switching point
specifically (f_res_loaded = 37.58 kHz at ratio 1.25) you would need
`L_eff = 1/((2π × 37.58 kHz)² × 30e-9)` = **598 µH loaded**, i.e. **~1.59 mH**
of uncoupled coil. Nothing in this project's evidence points anywhere near that:
every comparable real coil cited in `main.ato`'s own PLL comment (Infineon
AN235020, Würth 760308101303, APHO2025) measures **47–50 µH**, and the
sweep range the repo considers plausible is 50–250 µH.

Two further consequences of 30 nF, stated because they are not close calls:

- The firmware PLL's real range is **30–50 kHz**
  (`firmware/components/control/pll_control.h`, mirrored into
  `main.ato`'s `f_pll_tracking_min/max` and enforced by
  `scripts/check_pll_range_consistency.py`). A 122 kHz resonance is not
  merely off-nominal; it is **2.4× above the top of what the controller can
  produce**, so the converter could never track resonance at all.
- Tank impedance at 47 kHz would be 10× higher, collapsing the circulating
  current the pan load depends on.

**Conclusion: the circuit requires 150 nF per capacitor, 300 nF combined. The
value in `elec/src` was always right; the MPN and the footprint were wrong.**
This is the direction that costs the most in board rework, and it is still the
correct one.

### A.3 The correct part

WIMA FKP 1 datasheet rev. 03.26, 1600 VDC ordering table (continuation page 67),
verbatim row:

```
  0.15 µF    W 20    H 39.5    L 41.5    PCM 37.5    FKP1T031507G_ _ _ _ _ _
```

The six trailing positions are the datasheet's own "Part number completion"
box, printed on every page of the table: `00` = 2-pin version, `J` = ±5 %,
`S` = bulk, `SD` = 6-2 pin length. **Those six digits are carried over
unchanged from the previous declaration** — the correction is confined to the
first twelve, which are read directly off the manufacturer table. Lead
diameter is **1.0mm** at PCM 37.5 (2-pin mechanical table, continuation
page 66).

→ **`FKP1T031507G00JSSD`**, 0.15 µF ±5 %, 1600 VDC, 41.5 × 20 × 39.5mm, PCM 37.5mm.

Caveat, stated plainly: the base part number is cited to the **manufacturer's
ordering table**, not to a distributor product page. Repeated searches did not
surface a first-party distributor listing for this exact 18-digit string.
Orderability and lead time must be confirmed at procurement. What is *not* in
doubt is that the previously declared string was wrong.

Land pattern: `Capacitor_THT:C_Rect_L41.5mm_W20.0mm_P37.50mm_MKS4` is stock
KiCad 9; its own `descr` reads "pin pitch=37.50mm, length*width=41.5*20mm^2"
and cites a WIMA datasheet. It matches the `FKP1T031507G` case exactly. Pads
are 2.8mm on a 1.4mm drill — 0.4mm of clearance on the 1.0mm lead.

### A.4 Electrical-behaviour statement

Required by the task, and the answer is unusually clean:

- **Capacitance: unchanged.** 150 nF each, 300 nF combined. Every simulation
  in `simulation/harness/` already used 300 nF; none needs re-running.
- **Voltage rating: unchanged at 1600 V**, and now *true*. The `.ato` declared
  1600 V while naming a 2000 V part; the design floor
  (`assert c_tank1.voltage_rating >= v_tank_peak * 1.43`, i.e. 572 V) is
  unaffected either way.
- **Tolerance: unchanged** at ±5 % (`J`).
- **Dielectric: unchanged** — polypropylene, FKP 1 (metal-foil electrodes,
  internal series connection), the same series.
- **What changes is the physical part that would be bought and the copper it
  lands on.** If the board had been built as drawn, the tank would have been
  30 nF, not 300 nF, and the converter would not have run.

---

## Part B — the three isolator land-pattern defects

Every claim in `docs/evidence/2026-07-28-isolator-sourcing-brief.md` was
re-checked against the actual footprint files and the manufacturer documents.
**All three hold.** Measurements below use the repo's own model
(`temper_placer.core.pad_geometry.pad_axis_radius` via
`isolation_barrier.evaluate_isolator_feasibility`), the same path
`scripts/check_isolation_keepout.py` and the CP-SAT barrier constraint use.

### B.1 U7 — `UCC21550BDWKR` on the wrong one of TI's two published lands

TI SLUSE89C (May 2023, rev. Aug 2024), land-pattern drawing **4224374/A**,
"EXAMPLE BOARD LAYOUT" for **DWK0014A**, read directly from the PDF. Both
options appear side by side on the same sheet:

| Option | Pads | Row span | Pitch | TI's stated clearance/creepage |
|---|---|---:|---:|---:|
| IPC-7351 NOMINAL | 14× (2) × 14× (0.6) | (9.3) | 11× (1.27) | **7.3 mm** |
| **HV / ISOLATION OPTION** | 14× (1.65) × 14× (0.6) | (9.75) | 11× (1.27) | **8.1 mm** |

Confirmed. The board's `lib:SOIC16W_Isolated` was the first of these
(pads 2.05 × 0.6 at ±4.65, i.e. a 9.30mm span — KiCad's
`SOIC-16W_7.5x10.3mm_P1.27mm` with pads 12/13 deleted). The part's own
external clearance and creepage are both **> 8 mm** (SLUSE89C §5.6, CLR and
CPG), and TI states the requirement in footnote (1) to the Insulation
Specifications table:

> "Care should be taken to maintain the creepage and clearance distance of a
> board design to ensure that the mounting pads of the isolator on the
> printed-circuit board do not reduce this distance."

The claim that the footprint "throws ~0.85mm away" is correct: 8.100 − 7.250
= 0.850mm.

**Fixed:** `pcb/libs/lib.pretty/SOIC16W_Isolated.kicad_mod` retargeted to TI's
HV option — pad size 2.05 × 0.6 → **1.65 × 0.6**, row centres ±4.65 → **±4.875**,
courtyard X ±5.93 → ±5.95, pin-1 silk marker moved with pad 1. Pad Y
positions, 1.27mm pitch, numbering (1–11, 14–16), body silk and F.Fab outline
are unchanged. `scripts/validate_footprints.py pcb/libs/lib.pretty` reports
0 errors, and no new warnings.

### B.2 U3 — a lead-form problem, not a device problem

Confirmed. The H11LxM datasheet's ordering table defines `T` = 0.4" lead
spacing, `V` = VDE 0884, `TV` = both, and its package drawing gives the wide
form's lead span as 0.400 (10.16) / 0.425 (10.80) in/mm. Independently
re-verified at DigiKey **401266** (fetched 2026-07-28): `H11L1TVM`, onsemi,
**Active**, package "6-DIP (0.400", 10.16mm)", 4170 Vrms, supply 3–15 V,
open-collector output, 1,701 in stock + 6,000 factory stock. Same die, same
pinout, same L1 (≤1.6 mA) grade.

**Fixed:** `mpn = "H11L1TVM"`, `manufacturer = "onsemi"`,
`footprint = "Package_DIP:DIP-6_W10.16mm"`.

**Not fixed, and flagged in the component docstring:** the H11LxM datasheet
publishes V_ISO and a VDE 0884 file number but **no creepage/clearance figure
for the package**, and the body is only ~6.1–6.6mm wide, so creepage over the
body surface is materially less than 10.16mm. Whether this device is
*certified* for reinforced insulation at this crossing's working voltage
remains open. Widening the land fixes the **board** geometry; it does not
answer the **component** question.

### B.3 C6 — a 5.00mm stub under a 10mm-lead part

Confirmed. `pcb/temper.kicad_pcb:3395` carries C6 on
`Capacitor_THT:C_Disc_D10.0mm_W5.0mm_P5.00mm`, `descr`: "Stub for safety
capacitor (Y2 type) … Created to resolve netlist reference" — note it says
**Y2** where the `.ato` requires **Y1**, two different safety classes. Every
2.2 nF Y1 disc considered for this slot has **10.0mm** lead spacing: the
now-declared `VY1222M47Y5UQ6TV0` (Vishay 28537 p.2: F = 10.0mm, Dmax 12.0,
Tmax 5.0; DigiKey 2824499: lead spacing 0.394"), and both real Murata
spellings. The part does not fit as drawn.

**Fixed:** `footprint = "Capacitor_THT:C_Disc_D12.5mm_W5.0mm_P10.00mm"` —
stock KiCad 9, 10.00mm pitch, 2.0mm pads on a 1.0mm drill, and its own `descr`
cites Vishay's sibling VY2 datasheet (doc 28535). D12.5 ≥ the 12.0mm body,
W5.0 ≥ the 5.0mm thickness.

**Deliberately not done:** the sourcing brief notes that shrinking the pads to
1.4mm (0.8mm drill on the 0.6mm lead) would give 8.600mm and clear the CP-SAT
8.5mm working corridor as well. Vishay publishes **no recommended land
pattern** for this part, so that pad diameter would be an unsourced choice
rather than a manufacturer land pattern. Left for a human, with the number
stated so the decision is cheap.

**Safety-class statement (required):** capacitance, tolerance, class and
voltage are all unchanged by this branch — 2.2 nF ±20 %, **Y1**, and the
already-declared `VY1222M47Y5UQ6TV0` is Y1 at 500 VAC against the 250 VAC this
mains-to-earth node requires. Only the copper changed.

---

## Measurements

### Before (clean checkout of `34132799`)

```
C6   Capacitor_THT:C_Disc_D10.0mm_W5.0mm_P5.00mm   gap_x=3.200  gap_y=-1.800  achievable=3.200  feasible=False
U3   Package_DIP:DIP-6_W7.62mm                     gap_x=6.020  gap_y=-1.600  achievable=6.020  feasible=False
U7   lib:SOIC16W_Isolated                          gap_x=7.250  gap_y=-0.600  achievable=7.250  feasible=False
```

Identical to the sourcing brief's table, to three decimals. That brief's
measurement path reproduces here.

### After (same pad model, this branch's land patterns)

| Ref | Land pattern | HV↔SELV separation | vs 8.0mm gate | vs 8.5mm CP-SAT corridor |
|---|---|---:|:--:|:--:|
| C6 | `C_Disc_D12.5mm_W5.0mm_P10.00mm` (10.00mm pitch, 2.0mm pads) | **8.000mm** | PASS (exactly) | **NO** |
| U3 | `Package_DIP:DIP-6_W10.16mm` (10.16mm rows, 1.6mm pads) | **8.560mm** | PASS | PASS |
| U7 | TI HV / ISOLATION OPTION (9.75mm span, 1.65 × 0.6 pads) | **8.100mm** | PASS | **NO** |

Arithmetic, for the record: C6 `10.00 − 2×1.0 = 8.000`; U3
`10.16 − 2×0.8 = 8.560`; U7 `9.75 − 2×0.825 = 8.100`.

**These are land-pattern figures, not board figures.** `scripts/check_isolation_keepout.py`
measures `pcb/temper.kicad_pcb`, which still carries the old embedded
footprints, so its verdict is unchanged (see below). The separations above are
what the board will measure once the land patterns are synced into it — a
board edit this branch deliberately does not make.

### Board-space consequence of the parts that grew

Computed from each part's placed origin and rotation in `pcb/temper.kicad_pcb`
(read only), against the new land pattern's courtyard, versus a conservative
outline (all graphics + all pads) of every other placed footprint. Board
outline is the `Edge.Cuts` polygon (20, 20) → (172, 254), i.e. 152 × 234mm.

| Ref | Placed at | Old outline | New outline | Verdict |
|---|---|---|---|---|
| **C25** (`c_tank1`) | (75.40, 47.11) rot 180° | 32.0 × 13.5mm | **42.0 × 20.5mm** | **COLLIDES.** Overlaps `C5` (`CP_Radial_D35.0mm_P10.00mm_SnapIn`, a bus electrolytic) by **7.60 × 1.32mm**. Next nearest: C26 at 2.86mm, K3 at 4.92mm, U7 at 6.20mm. |
| **C26** (`c_tank2`) | (59.38, 27.25) rot 0° | 32.0 × 13.5mm | **42.0 × 20.5mm** | **OFF-BOARD.** No footprint collision, but the new outline spans y 17.00…37.50 and the board edge is at y = 20 — it hangs **3.00mm past the edge**. Nearest parts: C25 2.86mm, U21 4.37mm, C4 4.69mm. |
| **C6** | (97.22, 177.06) rot 0° | 6.8 × 1.8mm | 13.0 × 5.5mm | Clear. Nearest: R23 at 6.15mm. |
| **U3** | (118.82, 107.02) rot 0° | 9.7 × 8.1mm | 12.3 × 8.1mm | Clear. Nearest: K2 at 9.43mm. |
| **U7** | — | — | pads move *outward* 0.225mm/side, and get 0.4mm *shorter* | Net outline change ≈ 0. |

**The current placement cannot absorb the tank capacitors.** One of them
collides with a bus electrolytic and the other leaves the board. This is not a
nudge; it is a re-placement of the power stage's largest passives, and it
interacts with the barrier-constrained placement work already in flight. **I
am not doing it, and I am not approximating it.** Note also that each tank cap
takes almost exactly **twice** the board area it did (432 → 861 mm² of
outline) and is 39.5mm tall, which is a mechanical/enclosure input as well as
a layout one.

---

## Verification

| Check | Before | After |
|---|---|---|
| `make netlist` | succeeds, **162 nets** | succeeds, **162 nets** — unchanged |
| `uv run --no-sync python scripts/mpn_fabrication_gate.py` | **2 violations** (`c_tank1`, `c_tank2`: "encodes 15nF, but the declared value is 150nF") | **0 violations**, PASSED |
| `uv run --no-sync python scripts/check_domain_partition.py` | PASSED — 0 crossings, 0 barrier breaches, 0 chain defects | **unchanged**, PASSED |
| `uv run --no-sync python scripts/check_isolation_keepout.py` | FAILED — 1 violation | **unchanged**, FAILED — 1 violation |
| `uv run --no-sync pytest elec/validation/` | 30 passed | **30 passed** |
| `uv run --no-sync python scripts/validate_footprints.py pcb/libs/lib.pretty` | 0 errors, 2 warnings | 0 errors, 2 warnings (both pre-existing, on other footprints) |

**Net count is unchanged and that is the expected result** — nothing about the
connectivity changed. Only MPN strings, footprint assignments, and one
footprint definition's pad geometry moved. `check_domain_partition.py` reads
the netlist, so it is likewise unaffected.

**`check_isolation_keepout.py` stays at 1 violation, and it is the same
violation:** "No keepout zone named `MAINS_SELV_ISOLATION_BARRIER` found on
the board." That gate's blocker is a missing *board* keepout zone, which no
`.ato` or footprint-library change can supply. The per-isolator geometry it
would measure has improved for all three parts, but only in the library — the
board still holds the old embedded footprints. **No gate was weakened, no
allowlist entry was added, and the MPN gate's two violations were cleared by
correcting the part, not by suppressing the check.**

---

## What I could not verify (stated plainly)

- **A distributor listing for `FKP1T031507G00JSSD`.** The base part number
  `FKP1T031507G` is verbatim from WIMA's 1600 VDC ordering table and the six
  completion digits are unchanged from the previous declaration and
  individually documented in WIMA's part-number-system table, but no
  first-party distributor page for the full 18-digit string was reached.
  Confirm at procurement.
- **Whether ±5 % (`J`) is stocked at 0.15 µF/1600 V.** The datasheet offers
  ±20/±10/±5 % for the series without a per-value restriction; the tolerance
  digit is carried over unchanged rather than chosen.
- **The tank inductance as a specified component.** It remains an assumption
  (150 µH) with a placeholder in `elec/src`. `TANK_COIL_SPECIFICATION.md`'s
  blocker — an uncalibrated pan model — is untouched by this branch. Correcting
  the capacitor does not close that out; it does mean the C in the arithmetic
  is now the C on the BOM.
- **H11L1TVM's certified creepage/clearance and its VDE 0884 certificate**
  (unchanged from the sourcing brief).
- **Whether the CP-SAT 8.5mm working corridor should be relaxed to ~8.2mm** so
  that U7 (8.100) and C6 (8.000) fit. Still a human modelling decision; the
  8.0mm safety figure was not touched in any direction.
- **No CP-SAT re-solve was run.** Every "after" figure is closed-form
  arithmetic over the candidate land pattern — the same position- and
  rotation-independent arithmetic the solver applies per isolator.

## Hard-constraint compliance

- `pcb/temper.kicad_pcb`: **not modified**.
- `mpn-fabrication-allowlist.yaml`: **not modified**, nothing added.
- No gate, threshold or baseline was weakened.
- Every part number written down is cited to a manufacturer datasheet table
  (`FKP1T031507G`) or a distributor product page (`H11L1TVM`, DigiKey 401266);
  the C6 and U7 part numbers were already correct on `main` and are unchanged.
- No `git stash`, no `git checkout <sha> -- <paths>`.
