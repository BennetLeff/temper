# Rev38 source-to-PFC insulation review package

**Prepared 2026-09-24 for a future product-safety reviewer. Decision OPEN.**
This package asks for a governing insulation schedule and a disposition of
the two DWW digital-isolator crossings. It is not a certification request,
a fabrication release, or permission to energize the board. No reviewer or
approved standard/edition has yet been named.

## Product and evidence offered for review

- **Proposed installation:** portable, plug-in residential induction cooker,
  108–132 V ac, 15 A rms. The F1 study proposes a dedicated 20 A branch and
  10 kA prospective fault-current envelope; neither is a qualified product
  rating. The existing cooker enclosure is vented; it has no demonstrated
  pollution-degree-2 compartment. The project therefore screens the board as
  OVC II, pollution degree 3. Confirm or replace each premise.
- **Scope candidate:** [IEC 60335-2-9:2019](https://webstore.iec.ch/en/publication/61318)
  expressly lists portable cookers and hotplates. Its IEC page says the
  publication was established on IEC 60335-1 edition 5, while the
  [IEC 60335-1:2020 edition 6 page](https://webstore.iec.ch/en/publication/61880)
  says that edition 6 is to be used only with parts 2 established on its
  basis. The correct part-1/part-2 pairing, amendment set and national
  adoption need an explicit reviewer decision. For a US listing,
  [UL 1026](https://www.shopulstandards.com/ProductDetail.aspx?UniqueKey=23847)
  is a scope candidate, not a selected rule set. Review stationary-appliance
  scope, including [UL 858](https://www.shopulstandards.com/ProductDetail.aspx?UniqueKey=28697),
  instead if the product mounting or cord arrangement changes.
- **Frozen digital inputs:** [`source-build-06`](source-build-06/),
  [`placement-review/04`](placement-review/04/README.md) and
  [`INSULATION-COVERAGE.md`](INSULATION-COVERAGE.md). The `/04` PCB SHA-256 is
  `03dfa0f74a62666215315c880f49bc2b9ce7e7b2a9b964607a58c3f104cabb79`;
  its source manifest is
  `5de94dbf38b1d67cd764293f76fde93583f2642d21b4942140422fd94b8d5147`
  and the independently regenerated KiCad native export is
  `71165f96f527a2821b6cc40bfee3ac0aa64f02e7672a1d40f0fbf6b4d630bee6`.
  KiCad 10.0.4 ERC, non-routing DRC, source/native numeric-pad parity and
  provisional CAD stackup checks pass on these bytes. The board is unrouted;
  KiCad caps its unconnected report at 499. No insulation net-pair rules or
  reviewed `native/section.kicad_pcb` exist.
- **Voltage input:** the joined PFC analysis gives 409.307 V maximum static
  bank regulation. This crosses the older 400 V row boundary. Ripple,
  overshoot, F2-open `VD_LOCAL` versus `VB_BANK`, AC surge and fault envelopes
  remain unbounded. The 22 µF local reservoir is across F2 from the separate
  2,240 µF bank. See [`INSULATION-BASIS.md`](INSULATION-BASIS.md) and
  [`timing-analysis.md`](timing-analysis.md).

## Crossing that needs a disposition

| Path | Current evidence | Decision needed |
| --- | --- | --- |
| PCB surface at U1 `ISO7741FQDWWRQ1` and U44 `ISO6742FQDWWRQ1` | TI option-03 lands leave **15.2 mm nominal copper-edge gap**. The project's provisional PD3, Group IIIa/IIIb FR-4 >400–500 V reinforced-creepage screen is **16.0 mm**. `/04` has 104 below-screen pad pairs, all inside these two packages (52 each). | Confirm the actual board-surface requirement and CTI. Decide whether a controlled slot, qualified higher-CTI laminate, another footprint/device, or another construction can meet it at assembled tolerances. |
| Direct air and molded package surface | Both TI DWW data sheets specify **>14.5 mm** external package clearance and creepage, Group I CTI, and list **PD2** in their component insulation tables. The project's separately applied Group I package-surface screen is provisionally **12.6 mm**; the board's bare-land projection is 15.2 mm. | Derive the required assembled air clearance and package-surface treatment. Decide whether these PD2-listed components are acceptable in the proposed vented PD3 appliance, or specify a demonstrated compartment or different component. A PCB slot changes neither direct air nor molded-package path. |
| Internal isolator and other crossings | TI lists reinforced component insulation, but that does not qualify board lands or the appliance. Y1 capacitors, AC/AUX input, connector, PE, F2 studs, mounting hardware and exposed metal have separate paths. | Confirm insulation grade, normal/fault working voltage, impulse, accessible-part and PE treatment for each crossing and each relevant net pair. |

The exact native land coordinates, a proposed **1.0 × 20 mm** through-slot
measurement specimen under each isolator, its geometric limitations and
manufacturer sources are in [`DWW-BARRIER-FEASIBILITY.md`](DWW-BARRIER-FEASIBILITY.md).
The [replayable slot patch](placement-review/04/slot-specimen.patch) and
[KiCad probe receipt](placement-review/04/slot-specimen-receipt.json) show
native outline feasibility with two silkscreen-to-slot warnings. That
specimen is a path to measure; it is not an approved creepage value.
The six-layer, 1.8 mm stackup is a CAD consistency candidate without a
fabricator, laminate CTI, slot tolerance or solid-insulation approval.

## Requested reviewer output

Please return a dated decision record identifying the reviewer, jurisdiction,
product category, applicable part-1/part-2 editions and amendments, national
differences, and the clauses/tables used. For the actual installation and
construction, the record needs to state:

1. The insulation grade and accessible-part/PE boundary for every
   SELV-to-live crossing; OVC, pollution degree, altitude and material-group
   assumptions, including whether a real compartment can support PD2.
2. The maximum normal, transient and relevant fault voltage for AC, HOT0,
   HOT logic/AUX, `VD_LOCAL`, `VB_BANK` and F2-open states; the method for
   selecting rated impulse and the applicable creepage, air-clearance and
   solid-insulation requirement for each path.
3. Whether each exact DWW orderable part's component recognition and
   external package path can be used in the chosen appliance environment;
   any conditions on coating, enclosure or mounting, and the treatment of
   solder/land geometry. Give a separate ruling for the board surface,
   package surface, direct air and internal component insulation.
4. If a slot or special laminate is acceptable, the minimum manufactured
   slot width/end radius, copper-to-slot and solder tolerances, CTI evidence,
   layer keepouts, contamination assumptions and required assembled path
   measurement. If it is not acceptable, identify the replacement barrier
   or construction criterion before routing.
5. A net-pair schedule covering all 246 named source nets (62 SELV, 183
   live, one PE) or an explicit, reviewable grouping rule. For each required
   pair, specify classification, voltage case, air and surface limits,
   exception basis and KiCad rule owner. The census contains 30,135 unordered
   pairs; none currently has an accepted release rule.

Only after that decision can the integration owner encode a complete native
`section.kicad_dru`, check missing/reduced-rule and copper-bridge mutations,
and review a routed `native/section.kicad_pcb`. Fabricator and assembler
construction evidence, physical hipot/clearance measurements and fault
injection remain separate **NOT RUN** acceptance gates. The current digital
board must not be described as insulated or safe to energize.

## Primary component references

- [TI ISO774x-Q1 Rev. G](https://www.ti.com/lit/gpn/ISO7742-Q1), insulation
  specifications and DWW0016A option-03 land pattern.
- [TI ISO674x-Q1 Rev. F](https://www.ti.com/lit/gpn/ISO6742-Q1), insulation
  specifications and DWW0016A option-03 land pattern.
