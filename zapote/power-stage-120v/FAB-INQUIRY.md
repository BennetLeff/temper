# Fabricator stackup and plating inquiry — draft, not sent

Status: draft, 2026-09-26. The owner sends it and chooses the fabricator. The
answers feed D3 (stackup acceptance) and the finished-copper inputs every
current screen assumes (see native-07/verification/README.md). Figures below
come from `stackup.json` and the native-07 board (`68fb5234…`).

---

**Subject: Quote and DFM review request: 4-layer, 2 oz on all layers, 240 × 160 mm, 1.6 mm**

Hello,

We'd like a quote and a DFM/stackup review for a prototype power board. It is a
mains-connected 120 V induction power stage. This order is for bench prototypes
only.

**Board**
- 4 copper layers, 240 × 160 mm rectangle, nominal 1.6 mm finished thickness.
- Quantity 5, and 10 as an alternate price.
- Through-hole only: no blind/buried vias and no microvias. No controlled impedance.

**Requested stackup** (please propose your nearest standard build if this isn't one)

| Layer | Material | Thickness |
| --- | --- | --- |
| Top (L1) | Cu, 2 oz finished | 70 µm |
| Prepreg | FR-4 | 0.55 mm |
| L2 (plane) | Cu, 2 oz | 70 µm |
| Core | FR-4 | **0.20 mm** |
| L3 (plane) | Cu, 2 oz | 70 µm |
| Prepreg | FR-4 | 0.55 mm |
| Bottom (L4) | Cu, 2 oz finished | 70 µm |

The thin L2–L3 core is deliberate: those two planes form a low-inductance
DC-bus pair.

**Geometry (from our design)**
- Minimum track 0.20 mm (most signals are 0.30 mm); minimum copper clearance
  0.20 mm; copper to board edge ≥ 0.5 mm.
- Vias: 116 of 0.8 mm pad / 0.4 mm drill, and 31 of 1.6 mm pad / 0.8 mm drill.
- Plated component holes from 0.9 to 4.3 mm, 8 non-plated holes, no slots.

**Questions**
1. **Stackup:** can you build 2 oz on both inner layers with a 0.20 mm core
   and about 0.55 mm prepregs? What finished thicknesses would you actually
   deliver for each dielectric and for the whole board?
2. **Inner-layer insulation:** L2 and L3 differ by up to about 500 V peak in
   operation. What dielectric-withstand or hipot capability do you state for
   your 0.20 mm core material? We're not asking for a certification here, just
   your material data.
3. **Finished copper:** what are the *minimum* finished thicknesses on outer
   layers (base plus plating) and on inner layers, not the nominal values?
4. **Via plating:** what are your minimum and average barrel plating
   thicknesses (IPC-6012 Class 2 vs Class 3 pricing if different), and your
   finished-hole tolerance?
5. **Annular ring on 2 oz:** is a 0.8 mm pad on a 0.4 mm drill acceptable on
   all four 2 oz layers? If not, what minimum pad size do you need?
6. **Laminate:**
   - We require CTI ≥ 175 V (material group IIIa, PLC ≤ 3) and UL 94 V-0.
   - Please name the laminate and give its CTI/PLC grade.
   - Please also state its Tg; we'd prefer Tg ≥ 150 °C.
7. **Minimum track and space on 2 oz:** are 0.20 mm / 0.20 mm OK, or do you
   need wider?
8. **Finish and soldermask:** please quote lead-free HASL and ENIG, with
   green soldermask on both sides and white silkscreen.
9. **Lead time and DFM:** what is the lead time? Please also flag any DFM
   concerns once you've seen the Gerbers.

We'll send Gerbers and drill files with the order. If a fabrication drawing
would help your review, we can provide one.

Thank you,

---

## Why each question matters (internal)

- **Q1, Q3:** The power review treats 70 µm nominal as 2 oz on all layers. The
  bus, return and tank screens scale with actual finished copper.
- **Q2:** The 0.2 mm core separates the HV_RET and BUS_P planes. That is
  functional insulation between HOT groups; the SELV barrier doesn't depend on it.
- **Q4:** The via-resistance sensitivity in the power review assumed 10–15 µm
  of finished plating. Replace it with the fabricator's minimum.
- **Q5, Q7:** The routed board uses 0.8/0.4 mm vias and 0.2 mm spacing
  (LOW-group signals) on 2 oz copper. A larger minimum pad or space means a
  routing change, which would need re-verification.
- **Q6:** D5-BASIS requires CTI ≥ 175 (group IIIa or better).
