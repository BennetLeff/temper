# Tank coil selection: what is purchasable, and which (L, C, f) actually closes

<!-- provenance: commit=77f88827af479f94446aa1308692bf808050c798 dirty=false -->

**Date:** 2026-07-28
**Base commit:** `77f88827` (`origin/main`), branch `docs/coil-selection-research`
in an isolated worktree.
**Scope touched:** this document only. No `elec/src/*.ato`, no `pcb/`, no
`scripts/`, no `simulation/`. Every number below is a proposal, not an applied
change.
**Method:** web literature/datasheet retrieval (WebSearch/WebFetch + `curl` for
hosts that block the fetch tool), plus a first-harmonic tank solver written for
this pass and cross-validated against this repo's own ngspice harness (§4.1).
No bench hardware, no new simulation runs.

---

## Falsifier, stated before searching

> *"A purchasable ~50 µH coil forces either a larger tank capacitor, a wider
> PLL range, or both. This research fails to change anything if the answer is
> just 'buy a 50 µH coil and scale C by 3×.'"*

**Result: the falsifier fires, in the opposite direction from the one the task
anticipated.** The 47–50 µH cluster this project has been treating as
"what real coils measure" is **not a 1.8 kW-class cooktop cluster at this
project's frequency**. Two of its three sources are not cooktop coils at all
(§2.4), and the one that is was characterized only at 90–150 kHz for a
100–140 kHz inverter (§2.2). At 20–50 kHz — this design's actual band — the
manufacturer-published figure for a 2 kW cooking coil is **≈88 µH unloaded /
≈59 µH loaded**, and **that coil closes the design at the committed 300 nF with
`f_switching = 47 kHz` unchanged and inside the existing 30–50 kHz PLL window**
(§4.2).

A ~48 µH coil, by contrast, is **not rescuable by any capacitor**: with
L_loaded ≈ 19 µH there is a hard floor of **f_sw ≥ 43 kHz to throttle down to
1800 W even with C → ∞**, and landing inside 30–50 kHz needs **C ≈ 4.7–6.8 µF**,
16–23× the committed value (§4.3).

---

## 1. What binds, named before anything is verified

Per `docs/solutions/best-practices/verify-the-binding-axis-not-the-headline-rating-2026-07-28.md`:
name the constraint first, then verify against it. For this selection the
binding axes are, in order:

1. **f_sw at full power must fall inside the firmware's real 30–50 kHz PLL
   window** (`firmware/components/control/pll_control.h:22-23`,
   mirrored in `main.ato` and enforced by `scripts/check_pll_range_consistency.py`).
   Not the 20–100 kHz "LC tank theoretical bound".
2. **f_sw/f_res,loaded ≥ ~1.05 at full power** — the ZVS cliff, established in
   `docs/hardware/TANK_COIL_SPECIFICATION.md` and confirmed as a *threshold*,
   not a gradient, in `docs/evidence/2026-07-27-inductance-range-sweep.md` §2.3.
3. **Tank RMS current at 1800 W**, because it sets (a) the OCP-01 peak trip
   margin (50.1 A peak) and (b) the tank capacitor's *thermal* rating, which is
   the axis that was missed once already (PR #402, 1.7× over).
4. **Capacitor RMS current at the operating frequency** — not DC voltage, not
   the `f ≤ 1000 Hz` headline VAC figure.

Note what is *not* on this list: coil unloaded inductance. **L on its own does
not bind anything.** What binds is `L_loaded = L × (loaded/unloaded ratio)`,
because that is what resonates with C. This turns out to be the whole story
(§4.4).

---

## 2. What is actually purchasable

### 2.1 Candidate A — Infineon EVAL-IHW25N140R5L cooking coil ★ best evidenced

Shipped as item 3 of 3 in the EVAL-IHW25N140R5L kit ("Cooking coil — Typical
cooking coil with sized inductance value for the resonant tank", Table 1,
[user guide rev 1.0, 2023-08-04](https://docs.rs-online.com/e357/A700000012089135.pdf)).

| Parameter | Value | Provenance |
|---|---|---|
| Board class | 2 kW quasi-resonant single-ended induction cooker, 220 V | **read from source** (§1.3 Main features) |
| Characterization band | **0–50 kHz** | **read from source** (Fig. 16 axis) |
| L, no vessel | ≈90 µH at DC, **≈87 µH flat 15–50 kHz** | **read off a chart** (Fig. 16, pink solid, right axis) |
| L, with vessel | 105 µH @ DC → 66 @ 20 k → 62 @ 30 k → **60 @ 40 k** → 58 @ 50 k (µH) | **read off a chart** (Fig. 16, pink dashed) |
| R, no vessel | 0.10 Ω @ DC → **0.34 Ω @ 40 kHz** → 0.40 @ 50 k | **read off a chart** (Fig. 16, grey solid) |
| R, with vessel | 0.10 @ DC → 1.40 @ 10 k → 2.25 @ 20 k → **3.25 @ 40 k** → 3.70 @ 50 k (Ω) | **read off a chart** (Fig. 16, grey dashed) |
| Resonant capacitor used with it | **0.33 µF / 1200 Vdc (630 Vac)**, Fengming `PSB2123330KHSD`, 35×15×26 mm, P=30.5 mm | **read from source** (Table 3, BOM) |
| Coil assembly extras | integrated pot temperature sensor (3-pin, CN3) | **read from source** (§2.1 step 3) |
| Orderability | `EVALIHW25N140R5LTOBO1`, DigiKey `448-EVALIHW25N140R5LTOBO1-ND` (DK PN 21738765), ~₹11,918 / €121.77 at RS | **read from source** (DigiKey product page; RS listing via search index) |
| Stock / lead time | **1 unit in stock, 99-week manufacturer lead time** at the time of this fetch | **read from source** (DigiKey product page) |

**Not published anywhere I could find:** the coil's own MPN, diameter, turn
count, litz spec, ferrite arrangement, current rating, temperature rating, or
whether Infineon will sell it separately. It is characterized but not
specified. **There is no coil part number to cite, and I am not inventing one.**

The derived quantity that matters:
**loaded/unloaded L ratio ≈ 60/88 = 0.68 at 40 kHz** (0.66 at 50 kHz, 0.71 at
30 kHz) — i.e. implied coupling `k = √(1−0.68) = 0.57`.

### 2.2 Candidate B — Infineon EVAL_2KW_SiC_IH resonant coil

Ships with the EVAL_2KW_SiC_IH kit ("The evaluation board kit also contains the
resonant coil", §1.1,
[AN235020 v1.0, 2025-09-30](https://www.infineon.com/assets/row/public/documents/24/42/infineon-eval-2kw-sic-ih-applicationnotes-en.pdf)).
This is the source already cited throughout this repo's evidence chain.

| Parameter | Value | Provenance |
|---|---|---|
| Board class | 2 kW half-bridge series resonant, **f_sw 100–140 kHz**, V_DC 0–340 V, I_AC 0–20 A_rms | **read from source** (Table 2) |
| Characterization band | **90–150 kHz only** | **read from source** (Fig. 9 axis) |
| L, no pot | ≈48 µH, flat | **read off a chart** (Fig. 9) |
| L, with pot | 19.5 µH @ 90 k → 17.5 @ 150 k | **read off a chart** (Fig. 9) |
| R, no pot | 0.20 → 0.35 Ω | **read off a chart** (Fig. 9) |
| R, with pot | 3.65 → 4.85 Ω | **read off a chart** (Fig. 9) |
| Resonant caps | 4 × EPCOS/TDK `B32684A0473K000`; DC-link 1 × `B32774X4106K000` | **read from source** (Table 3, BOM) |
| Loaded/unloaded L ratio | **0.41 @ 90 kHz** | derived from the two rows above |

Two things to record honestly:

- **I could not verify the capacitance of `B32684A0473K000`.** TDK's product
  pages and datasheet PDFs return HTTP 403 to both WebFetch and `curl`. The MPN
  is quoted verbatim from Infineon's own BOM table; its value is **UNVERIFIED**
  and I decline to decode it from the part-number pattern — that is exactly the
  failure mode `docs/evidence/2026-07-27-fabricated-mpn-audit.md` exists to
  prevent.
- Fig. 6's oscilloscope screenshot appears to show `P1 rms(C3) 16.911 A` and
  `P4 max 22.39 A` at 2 kW / 100 kHz. **Read off a screenshot, low confidence**
  — it implies R_eff ≈ 7.0 Ω against Fig. 9's ≈3.9 Ω at the same frequency, a
  1.8× disagreement I cannot resolve. Not used in any calculation below.

**Below 90 kHz this coil is uncharacterized.** Every figure I compute for it at
20–50 kHz in §4.3 is extrapolation and is labelled as such.

### 2.3 Candidate C — OEM appliance spare coils

Real, orderable, in stock, and **electrically unspecified**.

| Part | Description | Price / stock | Provenance |
|---|---|---|---|
| Electrolux/Simpson **4055092979** | "Element Induction Coil 180mm", fits SHI643BA 4-zone boosted induction cooktop; part 280×230×60 mm, 0.675 kg | A$97.99, in stock | **read from source** ([shop.simpson.com.au](https://shop.simpson.com.au/part/cooktops-elements-induction-coil-180mm-387404832/)) |

No inductance, resistance, current or temperature rating is published for it.
This is representative of the whole OEM-spares channel: you can buy the part,
you cannot design with it until you measure it.

**A caution found while checking this channel.** A search index returned
`5304519440` under the RepairClinic page title *"Frigidaire Induction Range
Ferrite Coil Replacement"*. Two other listings for the same number in the same
result set describe it as **"HARNESS, WIRING, INDUCTION, W/F"** — a wiring
harness with a ferrite core, not a coil. All three pages returned HTTP 403 to
direct fetch, so I could not adjudicate. **It is therefore not a candidate
here.** A page *title* is not a specification, and a part number lifted from a
search snippet is precisely the artifact this repo's MPN gate exists to catch.

### 2.4 Candidate D — Würth Elektronik 760308101303: **not applicable**

The task asked specifically whether this part is genuinely applicable. It is
not, and the finding matters beyond this document.

Read verbatim from Würth's own datasheet (rev 001.006, 2022-05-09,
`https://www.we-online.com/components/products/datasheet/760308101303.pdf`):

| Parameter | Value |
|---|---|
| Description | **WE-WPCC Wireless Power Transfer Receiver Coil** |
| Size/type | **Ø 26 × 1.3 mm** (Ø26.3 ± 0.3 mm, 1.31 ± 0.3 mm thick) |
| Inductance | 47 µH ±10 % @ **125 kHz / 10 mA** |
| Rated current | **1.5 A max** (ΔT = 40 K) |
| Power capability | **20 W typ** (V_DC = 20 V) |
| R_DC | 460 mΩ typ / 500 mΩ max |
| Q | 25 typ @ 125 kHz |
| Self-resonant frequency | 8 MHz |
| Operating temperature | −20 … +105 °C |

A 26 mm, 1.5 A, 20 W Qi receiver coil. This design needs ~180 mm, 20–25 A,
1800 W. **The 47 µH agreement with a 2 kW cooktop coil is a coincidence of
value, not a corroboration of design intent** — the two parts are separated by
a factor of ~90 in power and ~7 in diameter.

**Consequence for this repo's existing evidence chain.**
`docs/evidence/2026-07-27-coil-pan-coupling-prior-art.md` lists this part as an
"off-the-shelf commercial coil, coincidentally close in scale to Infineon's
unloaded L", and `docs/evidence/2026-07-27-inductance-range-sweep.md` §1.3b
presents "three independent sources… converge to a tight 47–50 µH cluster".
Of those three:

- **Infineon AN235020** — a genuine 2 kW cooktop coil, but measured only at
  90–150 kHz for a 100–140 kHz inverter (§2.2).
- **Würth 760308101303** — a 20 W wireless-charging receiver coil (this section).
- **APHO2025 §1.4** — a small bench demo coil, 48.7 µH, *cross-checked against
  the Würth part* (per that document's own description). It is not an
  independent third source; it is a validation of the second.

So the "tight cluster of three independent sources" is **one comparable coil,
plus a wireless-power coil, plus a bench coil validated against the
wireless-power coil.** That cluster is currently load-bearing in
`elec/src/main.ato`'s PLL comment block, which states that "every comparable
real coil already cited in this project's own evidence (Infineon AN235020,
Wurth 760308101303, APHO2025) measures 47-50uH". **That sentence should be
corrected** — see §7.

### 2.5 Candidate E — custom-wound / generic Chinese coils

Searching AliExpress/Alibaba/eBay for "induction cooker coil 2000 W" returns
hundreds of listings (Guangzhou Golden Hongfa, Zhongshan Imichef and others at
MOQ 100–500). **None of them publish an inductance.** Sourcing an induction
cooktop coil in this channel means specifying it to a winder and measuring what
arrives — which is a legitimate route, and probably the eventual production
route, but it is not a datasheet and should not be dressed as one. Stated
plainly, per the task's instruction.

---

## 3. Capacitors that can actually carry the current

The tank capacitor must be re-sourced regardless of which coil is chosen —
`c_tank1`/`c_tank2` (WIMA `FKP1T031507G00JSSD`) are already ~1.7× over their
permissible AC current at 47 kHz (PR #402 / the binding-axis best-practice doc).
So the question is not "does the coil choice break the capacitor" but "which
(L, C) pairs have a capacitor solution at all".

### 3.1 Parts with published RMS current, from manufacturer tables

Cornell Dubilier Types 940C and 942C publish a per-part `IRMS @ 70 °C, 100 kHz`
column in a **table**, not a chart — which is the whole reason to prefer them
here (the FKP1 failure came from a figure that only exists as a curve).

From [`940C.pdf`](https://www.cde.com/resources/catalogs/940C.pdf) and
[`942C.pdf`](https://www.cde.com/resources/catalogs/942C.pdf), 1600 Vdc rows,
all **read from source (table)**:

| Part | C (µF) | ESR typ (mΩ) | dV/dt (V/µs) | I_RMS 70 °C/100 kHz (A) | D×L (mm) |
|---|---|---|---|---|---|
| `942C16S47K-F` | 0.047 | 8 | 3425 | **6.7** | 16.5 × 34 |
| `942C16S68K-F` | 0.068 | 6 | 3425 | **8.4** | 19.0 × 34 |
| `942C16P1K-F` | 0.10 | 4 | 3425 | **11.4** | 22.5 × 34 |
| `942C16P15K-F` | 0.15 | 5 | 1919 | **10.9** | 20.5 × 46 |
| `942C16P22K-F` | 0.22 | 5 | 1919 | **11.8** | 23.5 × 46 |
| `942C16P33K-F` | 0.33 | 5 | 1919 | **13.3** | 28.5 × 46 |
| `942C16P47K-F` | 0.47 | 5 | 1507 | **14.6** | 30.0 × 54 |
| `940C16P15K-F` | 0.15 | 5 | 1427 | 9.9 | 21.5 × 34 |
| `940C16P1K-F` | 0.10 | 7 | 1427 | 7.5 | 18.0 × 34 |

Two properties of this family that decide the design:

- **Current capability per µF rises as the part gets smaller.** 0.10 µF gives
  114 A/µF; 0.47 µF gives 31 A/µF. So a bank of several small parts beats one
  large part for the same total C. This is why "we need more capacitance" and
  "we need more current headroom" are not in tension here.
- **The RMS-voltage-vs-frequency curves are not the binding limit at 47 kHz for
  these values.** The 942C 1600 Vdc curve (**read off a chart**, p.4) holds
  ≈460 Vrms flat to ~30 kHz for 0.47 µF, and for 0.15 µF and below it is still
  at the 460 Vrms plateau at 47 kHz. Against the 200–260 Vrms this tank
  develops (§4), the thermal `IRMS` column binds first. Named explicitly so the
  next reader does not have to re-derive which axis was checked.

### 3.2 The purpose-built alternative, and why it is not the recommendation

The induction-cooking industry's own part is the "MKPH resonance capacitor",
0.24–0.5 µF / 1200 Vdc (630 Vac), sold by BM Capacitor, CG, Ruva, Fengming and
others. Infineon's own 2 kW quasi-resonant board uses one: **Fengming
`PSB2123330KHSD`, 0.33 µF / 1200 Vdc (630 Vac)** (§2.1). BM's published series
data gives 0.01–0.9 µF, 1000/1200/1600/2000 Vdc, dV/dt ≤ 500 V/µs,
tanδ ≤ 0.0007 @ 10 kHz, class 40/105/21 — but **no RMS current rating at any
frequency**, which is the one number this selection turns on. They are almost
certainly adequate (an ESR of `tanδ/ωC` ≈ 7 mΩ at 47 kHz implies ~1 W of
dissipation at 12 A), but that is **inference, not a sourced rating**. Use them
only after asking the manufacturer for the current curve.

---

## 4. The (L, C, f, I) analysis

### 4.1 The model, and its cross-check against this repo's simulator

First-harmonic (fundamental-mode) analysis of the half-bridge series tank:

```
V1_rms = 2*Vbus/(pi*sqrt(2)) = 153.1 V   at Vbus = 340 V
Z(f)   = R_load(f) + j*( 2*pi*f*L_loaded(f) - 1/(2*pi*f*C) )
I_tank = V1/|Z| ;  P = I_tank^2 * R_load ;  V_cap_rms = I_tank/(2*pi*f*C)
```

The capacitor is in series with the coil, so **I_cap = I_tank** and the two
tank capacitors in parallel each carry half of it.

**Cross-check against `run_zvs_sweep.py` / `run_tank_coil_sweep.py`** at the
repo's own committed operating point (L=150 µH, C=300 nF, cast_iron K=0.79):

| Quantity | This model | Repo harness (ngspice) | Δ |
|---|---|---|---|
| f_res,loaded | 37.570 kHz | 37.58 kHz | **0.03 %** |
| I_tank @ 47.0 kHz | 20.06 A rms / 28.36 A pk | 20.70 / 28.71 | −3.1 % / −1.2 % |
| P_pan @ 47.0 kHz | 1686 W | 1798 W | −6.2 % |
| V_Ctank peak @ 47 kHz | 320 V | 331 V | −3.3 % |

First-harmonic analysis understates slightly, as expected (it discards the
harmonics the square-wave drive actually delivers). **Treat every number below
as carrying a −6 %/0 % bias on power and ±3 % on current.** That is well inside
the spread between the coil candidates, so it does not change any verdict.

### 4.2 Candidate A (≈88 µH Infineon QR coil) — closes at the committed 300 nF

Solving for the f_sw that delivers 1800 W, above resonance:

| C | f_res,loaded | f_sw @1800 W | in 30–50 kHz? | ratio | L_loaded | R_load | I_tank | I_cap (each of 2) | V_cap |
|---|---|---|---|---|---|---|---|---|---|
| 150 nF | 54.37 kHz | 65.02 kHz | **OUT** | 1.196 | 55.0 µH | 4.38 Ω | 20.3 A | 10.2 A | 331 Vrms |
| 220 nF | 44.11 | 53.89 | **OUT** | 1.222 | 57.2 | 3.88 | 21.6 | 10.8 | 289 |
| **300 nF** | **37.31** | **46.60** | **IN** | **1.249** | **58.7** | **3.55** | **22.5 A** | **11.3 A** | **256** |
| 330 nF | 35.45 | 44.61 | IN | 1.259 | 59.1 | 3.46 | 22.8 | 11.4 | 247 |
| 390 nF | 32.41 | 41.38 | IN | 1.277 | 59.9 | 3.31 | 23.3 | 11.7 | 230 |
| **470 nF** | **29.33** | **38.09** | **IN** | **1.298** | **60.5** | **3.15** | **23.9 A** | **12.0 A** | **212** |
| 680 nF | 24.02 | 32.46 | IN | 1.351 | 61.8 | 2.87 | 25.0 | 12.5 | 180 |

Peak tank current at the 300 nF point is **31.9 A**, against OCP-01's 50.1 A
peak trip — **36 % margin**, the same order as the current design's claimed 43 %.

Tank efficiency at the 300 nF point: R_total 3.55 Ω of which R_coil 0.38 Ω →
**1607 W into the pan, 193 W in the coil, η_tank = 89.3 %**. That is a normal
number for a domestic hob and is the first efficiency figure in this project's
evidence chain that is not built on the discredited `pan_load.sub` Q.

### 4.3 Candidate B (≈48 µH) — not rescuable by any capacitor

Using the Infineon-measured loaded ratio (0.40) held constant and R_reflected
√f-extrapolated from 3.45 Ω @ 90 kHz — **both extrapolations, both labelled**:

| C | f_res,loaded | f_sw @1800 W | in 30–50 kHz? | ratio | I_tank | V_cap |
|---|---|---|---|---|---|---|
| 300 nF | 66.31 kHz | 95.09 kHz | OUT | 1.434 | 21.9 A | 122 Vrms |
| 470 nF | 52.98 | 82.03 | OUT | 1.548 | 22.7 | 94 |
| 940 nF | 37.46 | 67.24 | OUT | 1.795 | 23.8 | 60 |
| 1.5 µF | 29.66 | 60.16 | OUT | 2.029 | 24.4 | 43 |
| 2.2 µF | 24.49 | 55.74 | OUT | 2.276 | 24.8 | 32 |
| 3.3 µF | 19.99 | 52.15 | OUT | 2.608 | 25.2 | 23 |
| **4.7 µF** | 16.75 | **49.77** | **IN (barely)** | 2.971 | 25.5 | 17 |
| 6.8 µF | 13.93 | 47.89 | IN | 3.439 | 25.7 | 13 |

**The task's premise that ~950 nF fixes a 48 µH coil is incorrect**, and the
reason is worth stating precisely, because it is not obvious. 950 nF puts
*resonance* back at 37.5 kHz — but frequency is the **power-control** variable,
and 1800 W is not full power. With L_loaded ≈ 19 µH the tank's reactance per
hertz is 3× smaller, so throttling from the ~8 kW this tank can deliver down to
1800 W requires standing much further above resonance. The limit is hard:

> **With C → ∞ (the capacitor contributing zero reactance), 1800 W into
> R ≈ 2.6 Ω through L_loaded = 19.2 µH still requires f_sw ≥ 43.0 kHz** — and
> at ratios of 3–4× resonance, which is a different converter, not a tuning.

For comparison, the same floor for candidate A is **11.0 kHz**. The 88 µH coil
has room to be regulated; the 48 µH coil does not.

Rating the 4.7 µF option honestly: 4.7 µF of 1600 V polypropylene carrying
25.5 A at 50 kHz is ten `942C16P47K-F` in parallel — 30 mm × 54 mm each,
~0.4 litres of capacitor, on a board that currently has room for two. **This is
the "unbuildable capacitor" case the task asked me to identify.**

### 4.4 Why the 150 µH assumption "worked" — the two errors cancel

This is the load-bearing insight and it deserves to be stated on its own.

| | L_unloaded | loaded/unloaded ratio | **L_loaded** | f_res @300 nF |
|---|---|---|---|---|
| Repo's committed model | 150 µH (assumed) | 0.399 (from K=0.79, itself derived from Infineon's **90–150 kHz** measurement) | **59.8 µH** | 37.57 kHz |
| Infineon QR coil, measured at 30–50 kHz | ≈88 µH | **0.68** | **58.7 µH** | 37.31 kHz |

**The design is pinned by L_loaded ≈ 60 µH, and both routes land there.** The
150 µH assumption is wrong about the coil by ~1.7×, and the K=0.79 coupling is
wrong about the pan by ~1.7× in the opposite direction, and the product — the
only quantity that resonates with C — agrees to **2 %**.

That also explains, and dissolves, the alarming result in
`docs/evidence/2026-07-27-inductance-range-sweep.md`: "ZVS is completely lost
below ≈97 µH". That threshold is an artifact of applying a coupling ratio
measured at 90–150 kHz (0.40) to a design operating at 47 kHz, where the same
manufacturer measures 0.68 for a comparable coil. Re-run with the 30–50 kHz
ratio, an 88 µH coil sits at ratio 1.25 — comfortably on the ZVS-holding side —
not at ratio 0.9 as that sweep predicts.

**This is a claim about the pan-coupling model, not about the sweep's
arithmetic.** The sweep is internally correct; its `PAN_PRESETS` input is
frequency-mismatched. Fixing it is out of scope here (§7).

### 4.5 What the repo's own model says about a 48 µH coil, for completeness

If one keeps `PAN_PRESETS` cast_iron as committed (K=0.79) and simply swaps in
48 µH, R_reflected falls with L (it scales as M² ∝ L1) and the current problem
compounds the frequency problem:

| C | f_sw @1800 W | R_eff | I_tank | **I_peak** vs OCP-01 50.1 A |
|---|---|---|---|---|
| 300 nF | 87.85 kHz (OUT) | 1.83 Ω | 31.3 A | 44.3 A (88 % of trip) |
| 940 nF | 58.56 kHz (OUT) | 1.50 Ω | 34.7 A | 49.0 A (98 % of trip) |
| 1.5 µF | 50.82 kHz (OUT) | 1.39 Ω | 35.9 A | **50.8 A — trips OCP-01** |

Under this repo's own committed model, a 48 µH coil is out of the PLL window
*and* at or over its own overcurrent protection. Both models agree it is the
wrong choice; they disagree only about why.

### 4.6 Does a larger C really mean more capacitor current?

The task states it does. **Directionally yes, but by 6 %, not by the ~3× the
capacitance change might suggest** — and the effect runs through a different
mechanism than the one implied.

Capacitor RMS current in a *series* tank equals tank current, which is set by
`P = I²R_load`, i.e. by delivered power and reflected resistance. It does not
depend on C at all except through the operating frequency C forces you to.
Going 300 nF → 470 nF on candidate A moves the 1800 W point from 46.60 kHz to
38.09 kHz, where R_load is lower (3.15 vs 3.55 Ω), so current rises
**22.5 → 23.9 A (+6.2 %)**.

Meanwhile capacitor *voltage* falls **256 → 212 Vrms (−17 %)**, because
`V_cap = I/(ωC)` and C rose faster than I. So the larger capacitor is
**strictly easier on the dielectric and marginally harder on the thermals**,
and since the thermal limit is what binds (§3.1), the honest summary is: the
two problems interact weakly and in the direction of "manageable", not
"compounding". The compounding case in this design is candidate B, where the
current rises for a different reason — low reflected resistance (§4.5) — and
the capacitance needed is genuinely unbuildable (§4.3).

### 4.7 Buildable capacitor banks

Needed: ≥22.5 A rms at 300 nF, or ≥23.9 A at 470 nF, with margin. From the CDE
942C 1600 Vdc table (§3.1), banks within ±5 % of target:

**For 300 nF:**

| Bank | C | I_RMS capability | Margin |
|---|---|---|---|
| **3 × `942C16P1K-F`** | 0.300 µF | **34.2 A** | **1.52×** |
| 2 × `942C16P1K-F` + 2 × `942C16S47K-F` | 0.294 | 36.2 | 1.61× |
| 2 × `942C16P15K-F` | 0.300 | 21.8 | 0.97× — **fails** |
| *(present)* 2 × WIMA `FKP1T031507G00JSSD` | 0.300 | ~12 A (chart-read) | **0.53× — fails, as already known** |

**For 470 nF:**

| Bank | C | I_RMS capability | Margin |
|---|---|---|---|
| **3 × `942C16P15K-F`** | 0.450 µF | **32.7 A** | **1.37×** |
| `942C16P15K-F` + `942C16P1K-F` + `942C16P22K-F` | 0.470 | 34.1 | 1.43× |
| 1 × `942C16P47K-F` | 0.470 | 14.6 | 0.61× — **fails** |

Three 22.5 × 34 mm axial parts occupy less board volume than the two
41.5 × 20 × 39.5 mm WIMA boxes the design currently calls for and has *not yet
been laid out for* (`modules.ato`: "BOARD REWORK REQUIRED, NOT DONE HERE").
**The tank-capacitor land pattern has to be redrawn either way**, so moving to a
3-part bank costs no additional rework beyond what is already owed.

---

## 5. Recommendation

### 5.1 Coil

**Specify `L_unloaded = 88 µH ±10 %` measured at 40 kHz, flat-spiral litz,
ferrite-backed, ~180–200 mm OD, with `L_loaded ≥ 0.60 × L_unloaded` on a
ferromagnetic pan at 40 kHz as an acceptance criterion.**

Not "buy this part number", because **no purchasable coil in this class has a
published inductance**, and inventing one would be the exact failure this
repo has already paid for four times. What exists is:

1. **A characterized reference to buy and measure:** EVAL-IHW25N140R5L
   (`EVALIHW25N140R5LTOBO1`, ~€122). It is the only 2 kW cooking coil I found
   with manufacturer-published L and R **across this design's actual 20–50 kHz
   band**, and it comes with a working quasi-resonant inverter to sanity-check
   against. Caveat: 1 in stock, 99-week lead time at the time of this fetch.
2. **A cheap unspecified spare to cross-measure:** Electrolux/Simpson
   `4055092979`, 180 mm, A$98.
3. **A production route:** custom-wound to the spec above from a magnetics
   house, accepted on measured L and R.

**Do not target 47–50 µH.** That number belongs to a 100–140 kHz half-bridge
design; it is out of reach of this converter at any capacitance (§4.3).

### 5.2 Capacitance — keep 300 nF, or move to 470 nF; do not move to ~950 nF

Both 300 nF and 470 nF close with an 88 µH coil. The trade is **tolerance to
coil-to-coil L spread**, which is the thing this whole investigation is about:

| C | L spread over which f_sw @1800 W stays inside 30–50 kHz | Full-power f_sw | Min power at 50 kHz |
|---|---|---|---|
| 300 nF | **−10 % … +30 %** (exits the top of the window at 0.8× L) | 46.6 kHz | 1210 W (1.5:1 turndown) |
| 390 nF | −20 % … +30 % | 41.4 kHz | 754 W (2.4:1) |
| **470 nF** | **−30 % … +30 %, the entire plausible spread** | 38.1 kHz | **599 W (3.0:1)** |

**Recommendation: 470 nF**, if the tank capacitor is being re-laid-out anyway —
which it is. It centres the 1800 W point in the PLL window, absorbs ±30 % coil
error without any firmware change, doubles the usable power-turndown range, and
*reduces* capacitor voltage stress. **Recommendation: 300 nF is acceptable and
requires zero value change**, if the coil's measured L comes in at 88 µH +0/−5 %
and the schedule cannot absorb the capacitance change. The decision is the
user's; both are buildable and I am not applying either.

**950 nF is the one value to avoid** — it is optimal only under the assumption
that a 48 µH coil is coming, and a 48 µH coil does not work at any capacitance.

### 5.3 PLL range — raise the floor, do not widen the window

The task asked whether the PLL range should move instead of the capacitance.
**The window does not need to be wider. Its floor is in the wrong place, and
that is a latent defect independent of which coil is chosen.**

At C = 300 nF with an 88 µH coil, `f_res,loaded = 37.31 kHz`. `PLL_MIN_FREQ_HZ`
is **30 000 Hz — 7.3 kHz below resonance.** The firmware's own declared legal
range therefore contains a region where the half-bridge hard-switches:

| f_sw | ratio | state | I_tank | P | V_cap |
|---|---|---|---|---|---|
| 30.0 kHz | 0.80 | **HARD SWITCHING** | 23.4 A | 1511 W | 415 Vrms |
| 38.0 kHz | 1.02 | ZVS, at the cliff | 48.0 A | 7268 W | 671 Vrms |
| 40.0 kHz | 1.07 | ZVS | 41.1 A | 5492 W | 545 Vrms |
| 46.6 kHz | 1.25 | ZVS | 22.5 A | **1800 W** | 256 Vrms |
| 50.0 kHz | 1.34 | ZVS | 18.1 A | 1210 W | 192 Vrms |

Two hazards visible in that table, neither of which is about the coil:

1. **30 kHz is below resonance** — a 1200 V half-bridge hard-switching at full
   bus, inside the firmware's declared range.
2. **38–40 kHz delivers 5.5–7.3 kW**, 3–4× the design power, at 41–48 A rms
   (58–68 A peak — well over OCP-01's 50.1 A trip) and 671 Vrms across the tank
   capacitor. The band just above resonance is not a low-power region; it is the
   most dangerous place in the whole sweep.

**Proposed (not applied):** `PLL_MIN_FREQ_HZ` should be a *derived guard* at
`1.05 × f_res,loaded` — 39.2 kHz at 300 nF, 30.8 kHz at 470 nF — not a
hard-coded 30 kHz. At 470 nF the existing 30 kHz floor happens to sit at ratio
1.023, i.e. exactly on the ZVS cliff, so the guard is needed there too.

Note that raising the floor makes the **300 nF** option worse on turndown
(usable band 39.2–50 kHz) and the **470 nF** option better (30.8–50 kHz) — a
second, independent argument for 470 nF.

### 5.4 Tank capacitor part

**3 × `942C16P1K-F`** (0.10 µF / 1600 Vdc, 11.4 A rms each) for a 300 nF tank,
or **3 × `942C16P15K-F`** (0.15 µF, 10.9 A each) for a 450 nF tank. Both clear
the required current by ≥1.37× on a **table** figure, not a chart reading. This
replaces the WIMA FKP1 pair, which fails on the axis that binds.

---

## 6. Summary table: is it buildable?

| Coil | L_unl | L_loaded @40 k | C needed | f_sw @1800 W | PLL 30–50 k? | I_tank | I_cap each | Cap exists? | **Verdict** |
|---|---|---|---|---|---|---|---|---|---|
| **Infineon QR (A)** | 88 µH | 60 µH | **300 nF (as committed)** | 46.6 kHz | ✅ | 22.5 A | 11.3 A | ✅ 3×942C16P1K-F | **BUILDABLE, no value changes** |
| **Infineon QR (A)** | 88 µH | 60 µH | **470 nF** | 38.1 kHz | ✅ | 23.9 A | 12.0 A | ✅ 3×942C16P15K-F | **BUILDABLE, best L-tolerance** |
| Infineon SiC HB (B) | 48 µH | 19 µH (extrap.) | 940 nF | 67.2 kHz | ❌ | 23.8 A | 11.9 A | ✅ | **NOT BUILDABLE — f out of window** |
| Infineon SiC HB (B) | 48 µH | 19 µH (extrap.) | **4.7 µF** | 49.8 kHz | ✅ barely | 25.5 A | 12.8 A | ❌ ~10 parts, ~0.4 L | **NOT BUILDABLE — capacitor** |
| 48 µH under repo's K=0.79 | 48 µH | 19 µH | 1.5 µF | 50.8 kHz | ❌ | 35.9 A | 18.0 A | marginal | **NOT BUILDABLE — trips OCP-01** |
| Würth 760308101303 | 47 µH | — | — | — | — | 1.5 A rated | — | — | **NOT A CANDIDATE — 20 W Qi coil** |
| Electrolux 4055092979 | unpublished | — | — | — | — | — | — | — | **Buy and measure; cannot design on it** |

---

## 7. What should change elsewhere — described, not implemented

Per the task's hard constraint, nothing outside `docs/evidence/` was touched.

1. **`elec/src/main.ato`, the PLL comment block.** Its statement that "every
   comparable real coil already cited in this project's own evidence (Infineon
   AN235020, Wurth 760308101303, APHO2025) measures 47-50uH" rests on a 20 W
   wireless-charging coil and a bench coil validated against it (§2.4). The
   conclusion it supports — that the firmware's 30–50 kHz range is "KNOWN TO BE
   INSUFFICIENT" — does not follow from the corrected evidence. The range is
   sufficient; its *floor* is misplaced (§5.3).
2. **`simulation/harness/run_zvs_sweep.py`, `PAN_PRESETS`.** `K=0.79` was solved
   to reproduce Infineon's 0.40 loaded/unloaded L ratio measured at
   **90–150 kHz**. The same manufacturer publishes **0.68 at 40 kHz** for a
   comparable 2 kW coil (§2.1). At this design's frequency the preset overstates
   coupling by ~1.7×, which is what produces the "ZVS lost below 97 µH" result
   (§4.4). A frequency-dependent K, or simply a K solved against the 0–50 kHz
   dataset, would be the correct input.
3. **`docs/evidence/2026-07-27-coil-pan-coupling-prior-art.md` and
   `…-inductance-range-sweep.md`.** Both should carry a correction noting that
   the "three independent sources, 47–50 µH cluster" is one comparable source.
4. **`docs/hardware/TANK_COIL_SPECIFICATION.md`.** The withheld L can now be
   proposed as a *specification with an acceptance test* (§5.1) rather than a
   value — which is what that document asked for.
5. **`elec/src/modules.ato`.** `inductor_conn` remains `new Resistor` /
   `CUSTOM_LITZ_COIL`. Nothing here changes that; a coil is still not a
   specified part until one is measured.

---

## 8. UNVERIFIED

- **The recommended coil's inductance.** 88 µH is **read off a chart** in
  Infineon's user guide for a coil with no published part number, dimensions,
  current rating, or temperature rating. It is the best-evidenced figure I
  found and it is still a chart reading of an unspecified part. ±5 % on the
  read; unknown on part-to-part spread.
- **The 0.68 loaded/unloaded ratio at 40 kHz.** Same chart, same caveat.
  Measured on Infineon's unnamed cookware, not on this project's pan set.
  This number is doing more work in this document than any other; if it is
  wrong, §4.4's cancellation argument fails.
- **Everything about candidate B below 90 kHz.** L_loaded held at the measured
  0.40 ratio and R_reflected √f-extrapolated. Given that candidate A's ratio
  *rises* by 70 % as frequency falls, holding B's flat is almost certainly
  wrong — probably conservative in the direction of making B look better than
  it is, which does not change B's verdict.
- **`B32684A0473K000`'s capacitance.** MPN read from Infineon's BOM; value not
  verified (TDK 403s every automated fetch). Deliberately not decoded from the
  part-number pattern.
- **Infineon AN235020 Fig. 6's `16.911 A` reading.** Read off a scope
  screenshot; implies R_eff 1.8× above the same document's Fig. 9. Unresolved,
  unused.
- **MKPH induction-cooker capacitors' RMS current.** No manufacturer in that
  channel publishes it. The ~1 W dissipation estimate in §3.2 is **inferred**
  from tanδ, not sourced.
- **Frigidaire `5304519440`.** Described as a ferrite coil by one page title and
  as a wiring harness by two others; all three 403'd. Not used.
- **Whether Infineon will sell either coil separately.** Neither app note nor
  distributor listing says. Both are kit contents.
- **First-harmonic bias.** All §4 figures carry the −6 %/±3 % offsets measured
  in §4.1. No ngspice run was performed for the new candidates — that is the
  obvious next step and it is deliberately not done here, since it would mean
  touching `simulation/`.
- **Coil temperature rise, litz strand spec, ferrite loss, and EMC** are not
  addressed by any source found. A 180 mm coil dissipating ~193 W of its own
  copper loss (§4.2) needs a thermal design that this document does not have.

---

## Provenance

- Infineon **AN235020** (EVAL_2KW_SiC_IH), v1.0 2025-09-30 — fetched as PDF and
  read page-by-page (Tables 2 & 3, Figs. 6, 8, 9).
- Infineon **EVAL-IHW25N140R5L user guide** rev 1.0, 2023-08-04 — fetched via
  `docs.rs-online.com/e357/A700000012089135.pdf`, text-extracted and Fig. 16
  rendered at 500 dpi and digitized by hand.
- **Würth 760308101303** datasheet rev 001.006, 2022-05-09 — fetched from
  `we-online.com` and read verbatim.
- **Cornell Dubilier 940C and 942C** catalogs — fetched from `cde.com`, tables
  text-extracted, RMS-voltage charts rendered and read.
- **shop.simpson.com.au** part page for 4055092979 — fetched directly.
- **DigiKey** product page for `EVALIHW25N140R5LTOBO1` — fetched directly.
- Arithmetic: `coil_lc.py` / `coil_lc2.py` / `coil_lc3.py` written for this pass
  in the session scratchpad, cross-validated against this repo's own ngspice
  harness at the committed operating point (§4.1). Not checked in — they
  reproduce from the equations in §4.1 in a few lines and would otherwise be a
  fourth unmaintained solver alongside the three already in
  `simulation/harness/`.
- Blocked and therefore unused: `product.tdk.com` and
  `tdk-electronics.tdk.com` (403 to both WebFetch and `curl`), `mdpi.com`
  (403), `repairclinic.com` / `partselect.ca` / `searspartsdirect.com` /
  `applianceparts.homedepot.ca` (403), `farnell.com` (timeout).
