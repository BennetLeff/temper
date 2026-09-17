# B-INF-GATE report — populated gate network, Infineon EVAL_2.5KW_CCM_4PIN

Task **B-INF-GATE** · attempt **attempt-001** · campaign `2026-09-17-pfc-campaign` · contract C1.
Source-only (no solver, no model/CAD edit). Base revision `abfd531752d6d73b40687c5faf16aad1a5fd5890` (verified).

## 1. Question

Which gate network is actually populated on the Infineon **EVAL_2.5KW_CCM_4PIN**
(schematic sheet `EVAL_2.5KW_CCM_4PIN (FPS27)`, V01, 23.07.2015), and how are the
three recorded gate resistances — **3.3 Ω** (Fig 12/13 captions), **20 Ω** (R9/R16),
**10 Ω** (R7/R11 component list) — reconciled?

## 2. Sources read (input digests verified against the dispatch)

- `B-INF/.../raw/chipdip_appnote.pdf` — Infineon **AN_201408_PL11_027 Rev 1.2**,
  2015-11-02, 31 pp., sha256 `fdbed1c5…49ce`. Read §1.5 p.5, §3.2 p.7,
  Fig 6 p.12, Table 2 pp.14–16, Table 3 p.20, Fig 12/13 captions p.21.
- `B-INF/.../raw/infineon_presentation.pdf` — manufacturer deck, 16 pp.,
  sha256 `b213daba…c78d`. Read p.5 (board components) and **p.7 (Schematic)**.
- High-DPI renders of both PDFs (`pdftoppm`, 150–600 dpi) read as images, because
  the page-12 schematic is a raster: text extraction carries no designators.

## 3. The conflict and how it was tested

The document contradicts itself. Caption p.21: *“…@ 65 kHz & 100 kHz **3.3 Ω**”*.
Schematic R9/R16: **20R**. Component list p.15: R9, R16 = **20 Ω** (3314G-1-200E);
R7, R11 = **10 Ω**. (The same document also mis-numbers its figure cross-references:
p.20 body text says “Figures 10 and 11” for what are Figures 12/13 — the prose is not
reliable; the schematic and table are.)

The high-resolution deck p.7 and the app-note Fig 6 p.12 show the **same** schematic.
Tracing it settles the designators:

- **No split turn-on/turn-off path and no steering diode.** AN §1.5 p.5 states the
  driver’s two output pins are joined: *“the design did not take the opportunity to
  separate turn-on and turn-off gate resistors.”* Schematic confirms Out+ (pin 6)
  and Out− (pin 7) are tied together into one node.
- **R9 and R16 are the gate resistors**, one per device configuration (the “two
  different changeable gate resistors” of §1.5): R9 with a parallel 2-pin header
  **X6 “Rg_4pin”**, R16 with header **X7 “Rg_3pin”**. Their far ends join the driver
  output node; the near ends join the **B1/B2** gate/source-sense elements at DUT1A.
- Both are **Bourns 3314G-1-200E 20 Ω trimmers** — i.e. *adjustable*. The schematic
  value “20R” is the trimmer’s full-scale rating, **not** necessarily its setting.
- **R7 is not a gate resistor.** It is the driver secondary **VCC2 supply filter**:
  `Gate_12V / Galv_12V → J9/J10 → D6 (“short”, 0 Ω) → R7 (10R) → IC4 pin 5 (VCC2)`,
  decoupled by C14 (1 µ) / C25 (100 n) to SGND.
- **R11 is not a gate resistor.** It is the series element in the controller
  **VBTHL / BOFO enable divider**: `12 V (J11) → R11 (10R) → R18 (36k) → BOFO/VBTHL
  tap → R8 (10k) → GND`.

So the “10 Ω in the component list” is a **misattribution**: the BOM pairs R7 and R11
at 10 Ω, but neither sits in the gate path. The remaining real question is 20 Ω vs 3.3 Ω,
which is resolved by the part being adjustable: schematic/BOM give the fitted **component
rating (20 Ω)**; the only gate-resistance number tied to any measurement is the caption’s
**3.3 Ω**, and the caption’s frequencies (65 & 100 kHz) are exactly those of Table 3.

## 4. Resolved network

| Item | Resolution | Source |
| --- | --- | --- |
| Driver | `1EDI60N12AF` (IC4), 6 A isolated | §1.5 p.5; Table 2 p.15; deck pp.5,7 |
| Out+/Out− | joined; no steering diode, no R_on/R_off split | §1.5 p.5; Fig 6 p.12 |
| Turn-on gate R | **R9, 20 Ω trimmer** (4-pin path, ∥ X6 “Rg_4pin”) | Fig 6 p.12; Table 2 p.15 |
| Turn-off gate R | **same element as turn-on** (shared) | §1.5 p.5 |
| 3-pin path | **R16, 20 Ω trimmer** (∥ X7 “Rg_3pin”) | Fig 6 p.12; Table 2 pp.15–16 |
| Effective R under measured data | **3.3 Ω** | Fig 12/13 captions p.21 |
| Gate–source resistor | none observed (`null`) | Fig 6 p.12; deck p.7 |
| Gate bias (VCC2) | **≈12 V** (Gate_12V/Galv_12V, via D6 “short”, R7) | Fig 6 p.12; deck p.7 |
| R7 / R11 (10 Ω) | VCC2 filter / VBTHL divider — excluded | Fig 6 p.12; deck p.7 |

## 5. Verdict

**Effective populated gate resistance under the published measured data: 3.3 Ω**
(fitted component: a 20 Ω trimmer, R9/R16). **Confidence: medium-high.**
- High confidence: no split on/off path, no steering diode; R9/R16 are the gate
  resistors; R7/R11 are not.
- Medium-high confidence: 3.3 Ω is the operating value behind Table 3 / Figs 12–13.
  The as-shipped trimmer setting is *not documented*, so it stays `null`; 3.3 Ω is
  asserted as the **measurement condition**, which is what the bound compares against.

## 6. What this implies for the model bound

The coordinator’s probe (`reference_loss_bound_probe.rs`) found the model’s switch-only
loss exceeds the board’s whole-board loss at 20 Ω but is a minority share (~30–35 %) at
3.3 Ω. Since the published data was taken at **3.3 Ω**, the correct comparison is 3.3 Ω
and the model is **not** falsified by this board. The bias makes the probe conservative:
it used the device’s 10 V datasheet condition while the board drives ≈12 V, the
lower-loss direction. **The model’s consistency claim should be stated at 3.3 Ω.**

## 7. Accounting and limits

- Solver invocations 0 · model/CAD edits 0 · commits 0 · wall time ≈45 min.
- Completion FINISHED; physical qualification **NOT_PERFORMED**.
- Unresolved (kept `null`, reasons in `resolved_gate_network.json`): as-shipped
  trimmer wiper setting; exact R9∥R16 value if both branches are simultaneously
  in-circuit. Both are documented, not inferred.
- Files: `resolved_gate_network.json`, `REPORT.md`, `manifest.json`.
