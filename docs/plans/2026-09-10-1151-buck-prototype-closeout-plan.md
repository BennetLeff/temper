# Buck Rev A — remaining work to reach build readiness

Created: 2026-09-10

## Objective

Finish the existing prototype work: freeze a verified board, produce a checked manufacturing package with a usable purchasing BOM, and bind the bring-up instructions to that exact board. Stop at **ready for order review and subsequent assembly**. This plan does not authorize purchasing, fabrication orders, or powered testing.

Continue the existing three assignments rather than starting them again. Their detailed instructions remain applicable:

- [Plan 1: board and interfaces](2026-09-10-1105-buck-prototype-board-plan.md)
- [Plan 2: procurement and release](2026-09-10-1105-buck-prototype-release-plan.md)
- [Plan 3: bring-up documentation](2026-09-10-1105-buck-prototype-bringup-plan.md)
- [Shared context and ownership](2026-09-10-1105-buck-prototype-handoff-plan.md)

This follow-up governs the remaining coordination, the exporter defect, and acceptance of the final combined package. It does not change the electrical requirements or reopen model qualification.

## Starting state

Snapshot verified locally on 2026-09-10:

| Workstream | Existing result | Remaining work |
|---|---|---|
| Board | Standalone schematic, PCB, project, rules and local libraries exist under `pcb/prototypes/buck-reva/` | Finish review and exact connector selection; issue `verification/board-freeze.md` and `source-manifest.json`, both currently absent |
| Release | Procurement CSVs, preliminary notes and `export-release.sh` exist | Harden freeze validation; complete orderable SKUs/stock/prices; run and inspect final exports |
| Bring-up | Documentation committed as `12bf20980`; procedures, equipment guidance, empty templates and provisional figures exist | Bind figures to the frozen board; complete the tabletop walkthrough |
| Hardware evidence | No bench measurements claimed | Assembly and physical testing occur after build preparation and a separate order decision |

Use the existing `codex/buck-harness-experiment-plan` worktree identified in the handoff index. Verify branch and status before editing. It contains substantial uncommitted work; commit `12bf20980` alone does not contain all prototype inputs. Do not reset, stash, regenerate unrelated artifacts, or mistake untracked files for disposable files.

## Owners and execution order

Use the existing Luna owners where available; otherwise assign a Luna agent to each bounded responsibility. Avoid duplicate writers.

| Owner | Exclusive writes | Can start immediately? |
|---|---|---|
| Board | Standalone CAD, local libraries, source manifest, `verification/`, project README | Yes; continue current board work |
| Release | `export-release.sh`, `procurement/`, `release/` | Yes for validation and procurement; final export waits for board freeze |
| Bring-up | `docs/hardware/buck-reva/` | Yes for a document consistency review; final figures/walkthrough wait for frozen CAD and assembly drawing |
| Coordinator | This closeout plan and final cross-package review | Yes; reconcile dependencies without changing another owner's files |

Critical sequence: **board freeze → export and inspection → final assembly drawing/bring-up binding → combined readiness check**. Exporter hardening and purchasing research run alongside board work. The bring-up owner does not need to wait for fabrication to finish the documentation.

## 1. Agree the freeze contract, then finish the board

**Owner: board, with release-owner agreement on the manifest interface.**

1. Finish only the unresolved Plan 1 work. Select exact J1/J2 MPNs, verify their manufacturer footprints and pin numbering, and communicate the selection early. Keep J1.1 VIN, J1.2 GND, J2.1 3V3, J2.2 GND. Report the actual TP1–TP4 map and any optional TP5.
2. Ensure schematic fields contain exact manufacturer/MPN/value/footprint data for all purchased components. Core identities remain those in `elec/src/modules.ato::BuckConverter3V3`; prototype I/O belongs to the standalone schematic. Resolve core connectivity differences explicitly, including EN tied to VIN.
3. Finish routing, zone fills, footprint/body-clearance review, silk and probe access. Verify native schematic ERC and board DRC using the same KiCad 10.0.6 runtime intended for export. Require zero errors and zero unrouted nets; disposition warnings individually.
4. Freeze one concrete fabrication specification and final connector/probe map. Do not leave proposed thickness/copper/finish values in the freeze document.
5. Write a source manifest using one agreed format. Prefer a `files` object mapping project-relative paths to full SHA-256 hashes, plus a schema identifier and revision. The mapping must be nonempty and include:

   - `buck-reva.kicad_sch`, `buck-reva.kicad_pcb`, `buck-reva.kicad_pro`, `buck-reva.kicad_dru`;
   - `fp-lib-table`, `sym-lib-table`, `buck-reva.kicad_sym`;
   - every used local footprint in `buck-reva.pretty/` and any other local dependency affecting CAD interpretation or exports.

6. Record upstream Atopile/core-contract hashes separately as source provenance, with paths explicitly relative to the repository. Do not confuse those upstream records with the project-relative manufacturing input mapping. Record external library/runtime versions where dependencies are not vendored.
7. Write `verification/board-freeze.md` with the manifest digest, review result, report/image paths, KiCad version, final pinout and specification. Avoid circular hashes: the manifest does not hash itself or the freeze document that contains its digest. The release manifest can later hash both.
8. Notify the release and bring-up owners with exact paths and the manifest digest. Pause CAD edits during export. A later change requires a new freeze and new affected outputs.

**Completion evidence:** source manifest, board-freeze document, native reports, connectivity review and footprint/mechanical review all describe the same board. No fabrication export is needed for the board owner to hand off.

## 2. Fix the export gate before using it for release

**Owner: release. Independent of board completion.**

The current `verify_freeze_hashes()` accepts `{"files": {}}` because it checks zero entries and reports success. It also does not require the listed inputs to include the schematic or board. File existence checks elsewhere do not establish their frozen identity. Fix this concrete defect before final export.

1. Implement the agreed manifest contract. Reject an empty mapping, malformed digest, missing required input, missing file, hash mismatch, and project-input paths resolving outside the project. Validate the actual required CAD/library set, not merely “at least one hash.” Handle duplicate/ambiguous entries as invalid rather than silently choosing one.
2. Check that `board-freeze.md` identifies the manifest being used. A placeholder document plus unrelated hashes must not count as a reviewed freeze.
3. Capture the accepted manifest identity and input hashes at the start of the run. The post-export check must compare with that same accepted identity; do not reread and accept a newly changed manifest midway through the run. Hash the exporter/tool identity in release provenance as well.
4. Preserve failure behavior: no successful release status or new final ZIP when validation or a KiCad command fails. A failed attempt must not leave an older successful ZIP/manifest looking like the result of the latest run. Stage outputs separately or clearly invalidate the attempted release before replacing final outputs.
5. Keep the change small. Use the existing wrapper and repository-supported implementation patterns; do not introduce a new generic release framework or independent Python authority.
6. Add focused regression checks using disposable project copies and a controlled CLI stub where useful. These tests verify the gate, not PCB correctness. Cover:

| Input or event | Required result |
|---|---|
| Freeze absent | Existing “awaiting board freeze” refusal |
| Empty `files` mapping | Refuse before any export command |
| Only an unrelated valid hashed file | Refuse because essential CAD is unbound |
| Missing schematic, PCB, project/rules or required library entry | Refuse and name the omission |
| Malformed hash, missing file or changed input bytes | Refuse with a useful reason |
| Changed manifest or CAD during the run | Refuse final release publication |
| Simulated exporter failure after output creation | Nonzero result; no new valid final package |
| Complete, unchanged disposable input set | Pass validation; do not claim native CAD correctness from this test |

Run focused checks and shell syntax validation. A real KiCad export remains necessary after freeze. Do not run the entire unrelated harness, firmware or placer suite.

**Completion evidence:** corrected wrapper and retained regression results. Report the exact accepted schema to the board owner before either side finalizes incompatible files.

## 3. Complete procurement while the board is being verified

**Owner: release. Core parts can be checked now; connector rows wait only for their MPNs.**

1. Keep the existing seven grouped core BOM rows representing nine physical parts. Add the real J1/J2 components once selected. Keep bare test pads explicitly non-purchased.
2. Replace `MANUAL_CHECK_REQUIRED` with an actual dated procurement observation wherever accessible: orderable DigiKey SKU, packaging, stock quantity, minimum/order multiple, selected quantity, unit/extended price and currency. Keep shipping/tax separate if unquoted.
3. A JS-rendered page is a tool limitation, not evidence of no stock. Use an available browser to inspect the listing or an appropriate connector/API. If access remains blocked, record the actual barrier and the exact remaining rows; do not silently convert missing observations into verified availability.
4. Verify MPN and package on the actual listing and manufacturer source. Search snippets alone are preliminary identity evidence. Correct the stale shortened Samsung product link while doing this; the selected part is `CL32B106KBJZW6E`.
5. Use the actual observation timestamp. Review existing `2026-09-10T12:00:00Z` values: retain them as retrieval times only if supported by the original observation, otherwise label them as preparation dates and record the real new retrieval time.
6. Reconcile installed quantities, spares and ordering quantities. Five bare boards/two populated boards remains an editable planning assumption, not an order authorization.
7. If unavailable, check alternate packaging for the same MPN first. Route an actual component substitution through the board owner before freeze; never substitute silently in the procurement CSV after CAD is frozen.

**Completion evidence:** complete BOM and purchasable SKU mapping with real dated availability/pricing, or an explicit small list of unresolved purchasing blockers. Do not label the package order-ready while essential purchasing identities remain TBD.

## 4. Export and inspect the frozen revision

**Owner: release. Starts after steps 1 and 2 pass.**

1. Verify the received freeze digest, review receipts and source hashes. Run the corrected exporter with the explicit KiCad 10.0.6 path used by the board owner.
2. Produce schematic PDF/netlist/BOM, Gerbers, plated/non-plated drills and map, SMT positions, manual-assembly list, fabrication drawing and assembly drawing. Reconcile all purchased references against the frozen schematic; DNP and assembly-exclusion fields must survive export.
3. Replace preliminary fabrication/assembly notes with the actual board specification and connector directions. Fix relative links from `release/`: its project manifest is `../source-manifest.json` and freeze is `../verification/board-freeze.md`; `../../` is only appropriate from a deeper subdirectory such as `release/docs/`.
4. Inspect the exported copper/mask/paste/silk/outline and drill files, both sides. Check U3/L2 geometry, terminal drill alignment, readable polarity and probe access. Open the final ZIP and verify its contents, rather than inferring correctness from command success.
5. Spot-check placement origin, side and rotation against recognizable components. Confirm hand-soldered connectors are not silently included in the SMT population and bare test pads are not mistaken for purchased THT parts.
6. Finalize the visual-review record and release checklist, then calculate final output hashes. If a reviewed document changes after hashing, refresh its hash; avoid a package whose own acceptance edits invalidate its manifest. Hash the ZIP outside the ZIP itself.
7. Record one final release-manifest digest and send that identity plus the assembly drawing to the bring-up owner.

**Completion evidence:** inspected ZIP, complete assembly/fabrication files, native verification, exact source/output hashes and a purchasing summary. A real CAD change returns to step 1; regenerating only the CSV or report is insufficient.

## 5. Finish the existing bring-up documents

**Owner: bring-up. Preserve the work in `12bf20980`; do not rewrite the procedure unnecessarily.**

1. Match the frozen schematic/board, final assembly drawing and source/release identities.
2. Reissue the two provisional SVGs with actual J1/J2 pin numbering, wire-entry directions, TP1–TP4 positions, optional SW access and adjacent ground locations. Remove provisional banners only after verifying the drawings against the final board.
3. Complete a tabletop walkthrough: an operator must be able to inspect, connect, set the supply limit, probe C11/C12 for ripple, apply staged loads and stop safely using the documents alone. Check for contradictory labels, inaccessible probe locations or equipment assumptions missing from the capability table.
4. Update README readiness and the run-record identity fields with the freeze/release digests. Keep actual hardware status **NOT RUN**. Do not fill the 54-row results template with model or example measurements.
5. Recheck CSV structure, empty measured cells and status values after any edits. Preserve the distinction between a finished runbook and a completed bench session.

**Completion evidence:** final board-specific figures, recorded walkthrough, revision-bound documentation and still-empty measurement records.

## 6. Perform one combined readiness review and hand off

**Owner: coordinator; ask the existing owners for targeted corrections if needed.**

- [ ] Board freeze is present and complete; no required circuit/footprint/DRC issue remains.
- [ ] Export gate rejects empty and incomplete manifests and reports failed exports honestly.
- [ ] J1/J2 pinouts and component identities agree across CAD, BOM, assembly drawing and bring-up figures.
- [ ] Procurement contains exact orderable SKUs and dated observations; any blocker is explicitly unresolved.
- [ ] Manufacturing outputs were actually generated and inspected from the frozen inputs.
- [ ] Release hashes still match the final files and ZIP after documentation is finalized.
- [ ] Bring-up documentation is bound to that revision; all physical tests remain NOT RUN.
- [ ] A scoped handoff identifies all deliverable paths and commits, including any required uncommitted inputs. Do not claim a reproducible checkout if necessary files exist only in the working tree.

Produce a short `pcb/prototypes/buck-reva/release/closeout.md` recording the final status, source-manifest digest, fabrication-ZIP digest, package/BOM/runbook paths and remaining physical tasks. Coordinate this write with the release owner and include it in the final hash pass. Avoid a hash cycle: this document must not embed the digest of a release manifest that itself hashes this document. Report the final release-manifest digest in the external handoff after the last hash pass. If commits/pushing are authorized during execution, stage only owned deliverables and preserve unrelated WIP; do not use `git add .`.

The next action after a passing review is an explicit order decision, then assembly and operator-run bring-up. Planning for the next subsystem can use **3.3 V / 0.5 A as a provisional design interface**, with 1 A pulse performance unverified until measured. Do not call the buck fully qualified or connect a sensitive downstream load based on documentation alone.

## Boundaries and stopping rule

Do not change `pcb/temper.kicad_pcb`, production DRC ceilings, benchmark fixtures, the approval registry, adopted requirements or the behavioral model. Keep telemetry disabled. Combined capacitor derating, hot-inductor/fault behavior and environmental/model qualification stay in the existing deferred ledger.

Stop only the affected stage for a concrete failed check or missing dependency. Finish independent work and report the exact missing artifact/defect and owner. Once the combined readiness checklist passes, end this closeout; do not start another optional optimization or qualification loop.

## Ready-to-send coordination prompt

> Continue the existing buck Rev A work using the three Luna owners and this closeout plan. Preserve WIP and file ownership. Run board completion, exporter hardening and procurement checks in parallel. Require the agreed complete source manifest before final export; then inspect the manufacturing package and bind the existing bring-up figures to it. Deliver one reviewable, reproducible build-ready package with honest purchasing and NOT RUN hardware status. Do not purchase, fabricate, energize hardware or reopen deferred model/component qualification.
