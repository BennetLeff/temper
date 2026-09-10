# Plan 2 — freeze the BOM and prepare the fabrication package

Created: 2026-09-10

## Assignment and completion

Produce an order-ready package for the standalone buck Rev A prototype: every populated part purchasable by exact identity, every fabrication/assembly file derived from one frozen board, and enough documentation to assemble the board without guessing. Preparing the package does not authorize a purchase or fabrication order.

Read the [handoff index](2026-09-10-1105-buck-prototype-handoff-plan.md) and [board plan](2026-09-10-1105-buck-prototype-board-plan.md). Work in `/Users/bennet/Desktop/temper/.worktrees/codex/buck-harness-experiment-plan`, branch `codex/buck-harness-experiment-plan`, preserving existing WIP.

You own `pcb/prototypes/buck-reva/procurement/`, `release/`, and `export-release.sh`. The board owner alone changes CAD, component fields, footprints and `source-manifest.json`. Request corrections through that owner; do not hand-edit generated exports to compensate for wrong source fields.

## Dependency and parallel work

Start now with BOM reconciliation, dated availability research, output structure and export-command preparation. Final export waits for `pcb/prototypes/buck-reva/verification/board-freeze.md` and its source hashes. If those files do not exist yet, report “awaiting board freeze” while completing independent preparation; do not export a fixture as though it were the final prototype.

Default is a generic small batch with user-procured parts and hand/reflow assembly. Prepare a per-board BOM and an editable quantity worksheet, initially five bare boards and two populated boards as a planning assumption. No purchase quantity is committed. Separate assembly spares from installed quantity, and show the cost impact rather than silently rounding quantities.

## Step 1 — reconcile the complete board BOM

1. Read `elec/src/modules.ato::BuckConverter3V3`, `harness-lab/audits/buck-final-20260910/components/current-buck-bom.md`, and the adjacent source-build evidence. The nine-reference core is fixed for this prototype unless a concrete defect requires an explicit change.
2. Obtain J1/J2 exact MPNs from the board owner. The three old `fixture:*` terminals have no procurement authority. The final design has J1 VIN/GND and J2 3V3/GND.
3. Generate `procurement/bom.csv` from the completed schematic fields, grouping only identical MPN, value, footprint and population status. Keep the reference list and quantity reconcilable to every physical footprint.
4. Include Manufacturer, MPN, Reference(s), Qty per board, Value, Footprint/package, Datasheet, DNP, SMT/THT, and assembly inclusion. Explicitly classify bare test pads and mechanical holes as non-purchased items. Include hardware, jumpers, mating connectors or standoffs only where the actual design requires them.

The starting core BOM is:

| References | Quantity | Manufacturer / MPN | Nominal specification |
|---|---:|---|---|
| U3 | 1 | Texas Instruments LMR51430XDDCR | 500 kHz PFM buck, SOT-23-6 |
| L2 | 1 | Bourns SRP1265A-5R6M | 5.6 µH ±20%, SRP1265A |
| C9 | 1 | Samsung CL32B106KBJZW6E | 10 µF ±10%, 50 V X7R, 1210 |
| C10, C13 | 2 | KEMET C0603C104K5RACTU | 100 nF ±10%, 50 V X7R, 0603 |
| C11, C12 | 2 | Murata GRM32ER71E226KE15L | 22 µF ±10%, 25 V X7R, 1210 |
| R16 | 1 | Yageo RC0603FR-07100KL | 100 kΩ ±1%, 0603 |
| R17 | 1 | Yageo RC0603FR-0722K1L | 22.1 kΩ ±1%, 0603 |

The two pairs of capacitors account for four individual physical components. Core quantity is nine, not seven BOM rows. Verify complete prototype population independently; adding connectors and optional testpoint hardware changes the total.

## Step 2 — make the DigiKey purchasing mapping usable

1. Look up current DigiKey listings during execution. Record exact MPN, DigiKey SKU, product URL, cut-tape/reel/tray packaging, minimum/order multiple, available quantity, lead time if relevant, selected order quantity, unit/extended price, currency and retrieval date/time.
2. Prefer cut tape or similarly practical packaging for a small build. Distinguish distributor stock from marketplace or manufacturer-direct lead time. Do not claim a dated snapshot guarantees future stock.
3. Verify listing MPN and package against manufacturer evidence. Do not accept search-result similarity or a shortened part number. The Samsung MPN ends in `E`; do not copy the older ledger's shortened product-link suffix as proof of identity.
4. Create `procurement/digikey.csv` keyed to BOM identity and `procurement/README.md` summarizing cost, stock constraints, packaging and recommended spares. Shipping/tax stay explicitly unknown unless actually quoted.
5. If a part is unavailable in a practical quantity, first check alternate DigiKey packaging for the same MPN. Then propose a small number of electrically and mechanically checked substitutes to the board owner. Any change of exact component requires source/footprint review and a new freeze. Never substitute a nominally equal MLCC without checking dielectric, voltage, size, termination and available bias evidence.
6. Keep purchasing status separate from performance qualification: unresolved combined capacitor derating and hot-inductor data are recorded risks, not missing SKU fields. Do not restart broad vendor research to close them here.

No cart checkout, payment, purchase order or vendor message is part of this assignment.

## Step 3 — define the release contents and fabrication notes

Create this directory structure under `pcb/prototypes/buck-reva/release/`:

```text
gerbers/                  copper, mask, silk, paste and Edge.Cuts as applicable
drill/                    plated/non-plated Excellon and drill map
assembly/                 generated BOM, SMT positions, THT/manual list, assembly drawing
docs/                     schematic PDF, fabrication drawing, stackup/order notes
verification/             ERC/DRC receipts, reviewed layer images, export log
manifest.json             input/output hashes, versions and commands
release-checklist.md      review result, exceptions and ordering instructions
buck-reva-fabrication.zip  only files intended for the fabricator
```

Keep the editable purchasing worksheet outside the fabrication ZIP. If the assembler needs a separate package, prepare it explicitly rather than mixing procurement notes into a generic Gerber upload.

The fabrication notes must agree with the frozen board: outline dimensions, two-layer stackup, board thickness, finished copper, surface finish, solder-mask sides, silk sides, minimum geometry, drill sizes and any mounting requirements. The board plan proposes 1.6 mm FR-4, 1 oz finished copper and lead-free HASL; confirm the frozen selection and chosen manufacturer's capability. Do not inherit production-board 2 oz/multilayer assumptions from general Temper documents.

Include a readable assembly drawing with every reference/value, U3 pin 1, J1/J2 pin numbering and wire-entry direction, testpoint map, DNP instructions and an SMT-versus-hand-solder sequence. Small-batch hand assembly does not require an assembler-specific CPL, but generate generic SMT positions now so the package remains usable later.

## Step 4 — implement one reproducible export entry point

1. Read the export and Gerber review skills during execution. Use a small `export-release.sh` wrapper or an existing suitable exporter; avoid a new dependency framework or Python source of truth.
2. Require an explicit KiCad CLI path and verify its version. Use the board owner's 10.0.6 runtime unless a reviewed migration changes the entire package. Consult that executable's `--help` for actual supported flags rather than copying options for another release.
3. The wrapper must target only the standalone project, quote paths, fail on command errors, capture commands/version/logs, and refuse output from a changed or unverified freeze. Do not delete arbitrary paths; rebuild only its designated generated output directory.
4. Export schematic PDF/netlist/BOM; Gerbers for actual layers; Excellon drill and map; generic SMT position CSV; board/assembly/fabrication views. Include top paste for a stencil. Exclude THT connectors from SMT placement and list them explicitly for manual installation.
5. Record origin, units, axis convention, layer, rotation convention and board side in assembly notes. Spot-check U3 and a non-symmetric component against the board to catch mirrored coordinates or a rotation convention error. Do not invent an assembler conversion before an assembler is selected.
6. Generate input/output SHA-256 hashes and archive file lists after all files are finalized. Hash ZIPs outside the ZIP itself to avoid self-referential manifests. Retain exact source identity even if the surrounding checkout remains dirty.

## Step 5 — inspect the exports, not just command success

1. Recheck source hashes before and after export. A mismatch invalidates the release and returns it to the board owner for a new freeze.
2. Run final native ERC/DRC with the same resolved libraries/rules and tool version, or retain a demonstrably identical freeze receipt with an explicit identity check. Require zero errors and zero unrouted nets; carry reviewed warnings forward visibly.
3. Render/open exported Gerbers and drill layers. Check outline closure, copper around U3/L2, mask openings, paste apertures, connector holes, silk clearance and drilled-hole alignment. Inspect both board sides. Save annotated findings or a concise review log with the reviewed images.
4. Open the exact final ZIP and compare its contents to the manifest; reject stale alternate revisions, missing drill files, duplicated outlines or accidental fabrication layers.
5. Reconcile BOM and positions to the frozen schematic/board: every populated electrical component accounted for; no synthetic terminals; no lost DNP flags; no THT parts incorrectly treated as SMT; no refdes duplicates or blank MPNs on purchased parts.
6. Confirm documentation consistently labels J1.1 VIN, J1.2 GND, J2.1 3V3, J2.2 GND. Send final revision/hash and assembly images to the bring-up owner.

Do not run the full unrelated firmware/placer/harness test suites for export-only work. If exporter logic is added, verify it by producing and inspecting a real package and by checking that missing inputs/tool failures cannot report success. Do not alter production DRC ceilings.

## Acceptance and handoff

- [ ] All purchased population has exact MPNs and a dated DigiKey mapping; unavailable items are explicitly unresolved.
- [ ] Installed quantities, order quantities and spares are separated and consistent.
- [ ] CAD, BOM, coordinates, Gerbers, drills and drawings describe one frozen revision.
- [ ] Actual exported layers and final ZIP have been visually inspected and checksummed.
- [ ] Assembly and fabrication notes specify the actual stackup, pinout and population.
- [ ] A second agent can regenerate the package using the documented tool and command.
- [ ] Final status distinguishes “ready for order review” from “ordered,” “assembled” and “qualified.”

Stop final release for a mismatched freeze, incorrect footprint/pinout, missing essential manufacturing output, native error, unreviewed warning, or a part with no feasible purchasing path. Finish unaffected preparation and report the exact dependency. Missing optional 3D cosmetics or unresolved later thermal/model qualification alone do not block this prototype package.

## Ready-to-send agent prompt

> Use Luna to execute this release plan in `/Users/bennet/Desktop/temper/.worktrees/codex/buck-harness-experiment-plan`. Own only the standalone prototype procurement/release directories and export wrapper. Start BOM and DigiKey work in parallel with the board owner, then export and inspect the exact frozen board. Request CAD corrections from its owner; never patch generated BOM values to hide source errors. Deliver an order-ready, checksummed package and concise review result. Do not purchase, place fabrication orders, message vendors or claim hardware qualification.
