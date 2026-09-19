# Construction freeze — vsense-bank-side revision, 2026-09-19

Supersedes the earlier freeze section below (board `b0e5d537…`).
No fabrication, procurement, powered operation, or qualification is
authorized by this record.

Frozen board: `candidate/section.kicad_pcb`
SHA-256: `e274d8ad1181f426f731f170e46202e16f969bb751538837a45ee221c3b09ceb`
Frozen schematic: `candidate/section.kicad_sch`
SHA-256: `f0b3682aa653ae900c78f9e3d8f3edfd0f7fd2d4496199e781a797489e80e6f8`

## What changed since `b0e5d537`

U20 vsense-divider deviation dispositioned per `CLOSEOUT.md` §3 intent:
divider top moved from diode-side `boost_output` to bank-side `hv_plus`
(`elec/src/power_entry_active_unit.ato`). With F2 open, the controller keeps
sensing the stranded bank (divider, bank, and control_gnd stay connected)
while the boost stage can still energize the disconnected diode-side output:
diode-side overvoltage, continued mains drive, and the resulting control
behavior remain Q5 qualification work. The Rust
contract (`power_entry_active.rs`), divider feed route (now bank-side F.Cu
stub to the bleeder trunk), schematic, and test fixtures moved with it.

## Verdicts (plan `docs/plans/2026-09-19-001-fix-active-rectifier-construction-freeze-plan.md`)

- **R1–R3 TEA spacing: FAIL vs the 2 mm construction screen (AE2 path),
  unchanged.** U1 pairs 3–5, 10–12, 14–16 at 1.94 mm
  (`evidence/vsense-bank-side-01/common/power-entry.json`). Screen failure
  only; insulation standard/clause still open; no waiver counted.
- **R4–R5 F2 mounting: paper geometry verified, fit provisional,
  unchanged.** Sole copper bridge remains U66 (re-audited on routed copper:
  no shared vias/zones, no second footprint across the split). U20 item
  above is now closed as a deliberate bank-side placement.
- **R6–R7 suite: fresh full run on final bytes,
  `evidence/vsense-bank-side-01/common/`.** Seven units: six indeterminate,
  power entry FAIL only on the three TEA gaps; all 70 required rule IDs
  represented; `suite_changed_during_run` false. KiCad 10.0.4 ERC/DRC: zero
  violations, zero unconnected, zero parity. Current report INDETERMINATE
  (pad/via sharing and excluded-current gaps retained). Per R7 the FAIL is
  the recorded outcome, not a forced green.

## Replay-contract correction found during this revision

`routes.json` at `d36f6cea…` claimed 4.3 mm for the B.Cu rectifier trunk
paths, but the suite-03 board carried 3.0 mm there (verified against
`rust-integration-01/native-contact-repaired.json`). A faithful replay of
`d36f6cea…` produced two new 2 mm spacing failures; reverting those seven
B.Cu segments to 3.0 (`vsense-bank-side-01/bcu-width-edits.json`,
UUID-recorded) reproduces the suite-03 verdict shape exactly, with the
nominal current screen still passing. `routes.json` paths for those two
trunks are corrected to 3.0 in this revision so the contract reproduces the
board. The retained `d36f6cea…` claim is inaccurate for those paths; the
receipt above is preserved as history, not as a reproducible contract.

## Focused verification on final bytes

99 ERC library, 5 active ERC integration, 11 active harness, 6
native-binding tests pass; 5 common-runner tests pass. Test fixtures that
paired the live manifest with historical native bytes failed closed as
designed and were repointed at `vsense-bank-side-01/native.json`; the
historical files are untouched. Import-linter gate could not run in this
worktree (shared-venv package resolution); no imports were changed — Rust
string literals and net lists only. Full-workspace thermal replays and the
legacy GBU/GBJ comparison path remain untouched and unclaimed, per the
handoff.

---

## Superseded: freeze on `b0e5d537` (same day)

Frozen board SHA-256 was
`b0e5d537b0a827eac693b1b0373c650e6b2ef14637c3caf7d7c0a042695cb36b`,
recorded on retained `common-suite-03` evidence with no new rerun. That
record is void for current bytes (source/routing changed) and retained here
as history. Its U20 diode-side deviation and TEA/F2 dispositions above are
carried forward except U20, now closed.
