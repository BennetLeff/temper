# Construction freeze — 2026-09-19

Frozen board: `candidate/section.kicad_pcb`.

SHA-256: `b0e5d537b0a827eac693b1b0373c650e6b2ef14637c3caf7d7c0a042695cb36b`
(verified at freeze time; matches `RUST-INTEGRATION.md`).

This freeze is recorded on retained evidence, with no new CAD, Rust, or rerun
performed for it. No fabrication, procurement, powered operation, or
qualification is authorized by this record.

## Verdicts (plan `docs/plans/2026-09-19-001-fix-active-rectifier-construction-freeze-plan.md`)

- **R1–R3 TEA spacing: FAIL vs the 2 mm construction screen (AE2 path).**
  U1 pairs 3–5, 10–12, 14–16 measure 1.94 mm edge clearance against the
  2.00 mm floor (`evidence/rust-integration-01/common-suite-03/power-entry.json`,
  indices 22–24). The retained NXP datasheet (Rev 1.1, 2021-04-14) contains no
  PCB-layout clearance relief — its only clearance sentence is package-internal
  (§9). All three gaps hold an HVS "high-voltage spacer" NC pin, which cuts
  against narrowing. This is a screen failure, not a demonstrated physical
  unsafety, and not hardware qualification. The governing insulation
  standard/clause remains open; a future clause analysis showing required
  clearance ≤ 1.94 mm with written justification may revisit this per R2/AE1.
  No pad narrowing or numerical waiver is counted (R3).
- **R4–R5 F2 mounting: paper geometry verified, fit provisional.**
  Footprint `A70QS50_ETI_CH14_Prototype` transcribes ETI CH14-PCB catalog
  p.34 exactly (G 10.7, F 0.75, D 5, A 16); slot/land allowances are selected,
  fab to confirm. The 38 mm clip-centre spacing is a selected assumption, not
  catalog. Mersen ferrule/engagement dimensions and 3D models are absent.
  Ratings established on paper: 50 A identity, 890 VDC/2.5 ms sentence
  (time-constant definition unconfirmed), 280 A²s pre-arc max. Clearing,
  minimum breaking current, holder DC/thermal ratings, and coordination remain
  Q1/Q2. Net split audited on routed copper (337 segments, 56 vias): no
  footprint touches both `BOOST_DIODE_POSITIVE` and `PFC_BUS_PLUS_390V`, no
  shared vias, sole zone is `PFC_BUS_MINUS` — sole bridge is U66.
  **Deviation recorded:** vsense divider top U20 sits diode-side, against the
  `CLOSEOUT.md` §3 bank-side-sensing intent. After F2 opens, the controller
  reads diode-side voltage, not bank voltage. Disposition (move or justify)
  is open and blocks any claim about post-F2 sensing behavior.
- **R6–R7 suite: bound to retained `common-suite-03` run, no fresh rerun.**
  Seven units; power entry FAIL only on the three TEA gaps; six other units
  indeterminate; all 70 required rule IDs represented;
  `suite_changed_during_run: false`. KiCad 10.0.4 ERC/DRC zero violations;
  stackup and saved-byte/native binding pass. Current-capacity status is
  INDETERMINATE (pad/barrel, sharing, excluded-current gaps retained).
  Per R7/AE2 the FAIL verdict is the recorded freeze outcome, not a forced green.

## What this freeze does not do

- Does not close the insulation-clause OQ, the U20 disposition, Q1–Q5, surge,
  bootstrap/startup, cooling, or any powered testing.
- Does not re-execute the suite; a future rerun on these exact bytes that
  reproduces `common-suite-03` would strengthen this record, and any byte
  change voids it.
- Is not published: this commit has no publication approval (automatic review
  rejected twice; explicit approval outstanding).
