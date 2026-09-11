# Buck Rev A procurement — release owner preparation (2026-09-10)

Status: **dated listing snapshot complete; Samsung C11/C12 substitution recorded for order review.** No purchase, fabrication order, or vendor message is authorized.

## Sources reconciled

- `elec/src/modules.ato::BuckConverter3V3` — nine-reference core (U3 L2 C9 C10 C11 C12 C13 R16 R17).
- `harness-lab/audits/buck-final-20260910/components/current-buck-bom.md` — exact MPN/value/footprint ledger.
- `harness-lab/audits/buck-final-20260910/source-build/` (`collection.json` `resolved-components.json`) — Atopile 0.2.69 build evidence; core MPNs agree.
- `harness-lab/fixtures/buck-v2/buck-dev-a/source.json` — witness admits the same nine references; its J1/J2/J3 same-net pairs are synthetic and carry no procurement authority.

Core quantity is **nine components in seven orderable rows** (C10+C13 share one MPN; C11+C12 share one MPN).

## What `bom.csv` contains

`bom.csv` is generated from completed schematic fields once the board freezes; the current copy is reconciled to the Atopile source + audit ledger pending that freeze. Grouping is by identical MPN + value + footprint + population only. Columns: Manufacturer MPN References Qty-per-board Value Footprint Datasheet DNP SMT/THT assembly-inclusion. Bare test pads (TP1–TP4, optional TP5) and mounting holes are explicitly non-purchased — no MPN, no price.

J1/J2 are frozen as Würth Elektronik `691253500002`; the three old `fixture:*` terminals are excluded. Final design: J1.1 VIN, J1.2 GND; J2.1 3V3, J2.2 GND; common 5.08 mm 2-pos vertical top-entry TH terminal. Request CAD corrections through the board owner; never hand-edit generated exports to compensate.

## What `digikey.csv` contains (dated 2026-09-10T18:29:28Z UTC)

Listing identity, packaging SKU, stock, MOQ and single-unit CT price were captured for all eight populated identities (seven core MPN rows plus the shared J1/J2 connector) on the dated DigiKey listing pages. Samsung suffix `E` was checked, 22.1k vs 22k distinguished, KEMET 50 V confirmed, and the stale Yageo product-page ID was corrected.

The observation is a point-in-time distributor listing and does not guarantee future stock. Prices are USD CT single-unit tiers where available; the planning quantities and extended values are recorded in the CSV. Shipping/tax remain unknown.

The previously selected `GRM32ER71E226KE15L` was unavailable, so the board owner approved the prototype substitution `CL32B226KAJNNWE` and issued a new freeze. Its exact CT SKU `1276-3393-1-ND` was observed in stock on 2026-09-10. Samsung DC-bias behavior is unverified; the prior Murata bias curves and conservative sensitivity assumption do not establish a Samsung minimum. The other populated identities and the two Würth terminals have a feasible listed path.

Substitute policy: same-MPN alternate packaging first; then a small number of electrically+mechanically checked substitutes proposed to the board owner (dielectric voltage size termination bias evidence for any MLCC). Any exact-component change needs source/footprint review and a new freeze.

## Quantities and cost

Planning assumption only: **five bare boards, two populated boards**. `quantity-worksheet.csv` separates installed qty (per-board × 2) from spares and order qty, and calls out MOQ/multiple deltas as cost impact instead of silently rounding. No purchase quantity is committed. Shipping/tax explicitly unknown unless actually quoted.

Performance qualification stays separate from purchasing status: combined capacitor derating and hot-inductor data are recorded risks, not missing SKU fields. No broad vendor research was restarted to close them here.

## Next step for release

With the replacement freeze now present, `bom.csv` and this snapshot are reconciled to the frozen connector map. Run `../export-release.sh` and inspect the package per `../release/release-checklist.md` before any order decision.
