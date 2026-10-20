# Longitudinal slot between Rev B divider legs

**Verdict:** a longitudinal cutout can preserve the 20 mm PCB-surface budget while bringing selected opposing conductors to their 10 mm air budget. It does **not** permit a 10 mm divider-row pitch. With the present resistor/capacitor arrangement, the HV-only pitch floor is **21.375 mm**. Retaining the complete present leg cells imposes a stronger **31.87 mm courtyard bound**, so useful compaction requires moving the low-leg parts as well as cutting the slot.

## Evidence and scope

This analysis reads `tools/layout.rs`, `layout/placement.tsv`, `layout/copper.tsv`, `docs/layout.md`, native KiCad footprint geometry and exported `validation/pcb-pads.tsv`. The source PCB SHA-256 is `b0c15add2b69967cee0593962e1b3b22795725ed36ccbfc408b05c3fb4002b65`. No canonical design or BOM was changed. The main Temper hardware identity check also passed; that separate power-stage candidate supplies no probe spacing evidence.

Rev B is 240 × 84 mm, with resistor centerlines y=20 and 55 mm: 35 mm pitch. Capacitors are 8 mm below each resistor row. The plane boundary x=128 divides the rectangular board into approximately 53% HV and 47% LV area; visual sparseness is different from area allocation. The existing 600 V section budgets remain 2 mm air / 4 mm surface, and the full-tip budgets remain 10 / 20 mm. Opposite-leg requirements use the larger node rank under simultaneous `|V+|`, `|V−|` and `|V+−V−|` ≤3 kV. No 6 kV opposing-tip condition is introduced.

## What actually limits pitch

Let p be the resistor-row pitch, keeping the first row at y=20 and translating the second cell vertically.

| Geometry | Coordinates or calculation | Consequence |
|---|---|---|
| C1.1, TIP_P | center (36.950,28.000), pad 1.4 × 3.4 mm | Bottom copper y=29.700 |
| R21.2, rank 9 | center (37.4625,20+p), pad 1.225 × 3.35 mm | Top copper y=18.325+p |
| Their flat copper edges overlap in x | Air gap = p−11.375 | p≥21.375 for 10 mm air |
| Same pair without an intervening cutout | Surface gap = p−11.375 | p≥31.375 for 20 mm surface |
| W_HV1/W_HV2 | x=20, 4 mm diameter | Opposing input-pad air gap = p−4; p≥14 alone |

Thus the capacitor row, rather than resistor-body width or input-pad diameter, sets the tighter HV-only bound. At p=22 mm the critical air gap is 10.625 mm. A slot cannot increase that air distance. The 2512 resistor bodies span about y±1.65 mm; the 1812 capacitor bodies span y±1.65 mm, so they do not collide at this pitch. Actual copper, including rounded-pad flat edges, supplies the tighter calculation.

The low-leg cells prevent a simple translation to this pitch:

* RV1's native courtyard is x=118.415…128.505, y=35.315…40.695. C51's is x=127.675…132.325, y=p+8.825…p+11.175. They overlap in x; the lower capacitor must start below RV1, requiring **p≥31.870 mm**. Subsequent capacitors cannot rescue this by sliding through the occupied interval. Their component bodies have only a narrow lateral gap: courtyard clearance is a real assembly constraint even where body rectangles narrowly miss.
* CT1's courtyard ends at y=41.525; U2's courtyard begins at y=p+17.275. Their x envelopes overlap, requiring **p≥24.250 mm**. At 22 mm, even the trimmer body and buffer body intrude into each other's space.

Keeping those positions gives roughly 32 mm practical pitch, where the critical HV straight gap is already 20.625 mm. The new slot therefore buys essentially no extra reduction for the unchanged full cells.

## Slot geometry and native controls

Four isolated two-pad fixtures in `interleg-slot-fixtures/` reproduce C1.1 and R21.2 pad shapes, dimensions and nets with the canonical project/rules. These deliberately isolate the limiting pair, rather than claiming a complete rerouted PCB. KiCad 10.0.4 native DRC with `--all-track-errors` returned:

| Fixture | Result |
|---|---|
| p=22, cutout x=10…118, y=34…35.2 | Zero violations/unconnected items |
| p=22, no cutout | Creepage 10.6250 mm against 20 mm |
| p=22, cutout starting x=36.5 | End runaround creepage 10.6584 mm against 20 mm |
| p=21, long cutout | Air clearance 9.6250 mm against 10 mm |

JSON reports and command logs are retained. Initial sandboxed violating runs crashed in macOS font services; the completed controls above ran with those services available.

The slot must extend beyond the earliest HV landings, not merely beneath the resistor array. Short ends permit surface shortcuts, as the negative control demonstrates. A tentative x=10 left end lies 8 mm left of input-pad copper; the right end can terminate near the low-rank ladder end, subject to checking every actual route. At y=34…35.2 it also leaves 2 mm of material beyond the existing upper capacitor slots ending y=32. Long cuts reduce board stiffness and require retained insulating support.

[TI SLUP419, page 11](https://www.ti.com/lit/pdf/slup419) explains that cutouts increase surface distance without increasing clearance, and gives pollution-dependent minimum widths: 1.0 mm for degree 2, 1.5 mm for degree 3. [JLCPCB's capabilities](https://jlcpcb.com/capabilities/pcb-capabilities/) list 1.0 mm minimum non-plated slots, ±0.2 mm slot tolerance and rounded corners. A nominal 1.2 mm slot has no width margin beyond a 1.0 mm lower tolerance limit; specify the finished width deliberately. These are engineering references, not a standards compliance determination.

## Useful next design target

With relocated RV/CT and low-leg compensation parts, **22–24 mm pitch** is a credible exploration target; 21.375 mm is an analytic boundary with no tolerance allowance. That saves 11–13 mm of HV height. A 240 ×71–73 mm rectangle is only an optimistic whole-board envelope: it requires corresponding LV reflow, mounting changes and route review. The existing LV circuitry reaches y≈82 mm, so changing ladder pitch alone leaves the 84 mm board height intact. Preserve paired geometry and requalify parasitic compensation/CMRR after any such rearrangement. Component surfaces, soldered leads, shield spacing and mechanical slot fabrication still require assembly review.
