<!-- provenance: commit=4cdfd1a1d2cb74d3a0a106106e61c3243fcab18f dirty=true -->

# P0 #1/#2 data-driven resolution (2026-08-09)

Investigation record for two P0 reports dispatched against `origin/main`
(`4cdfd1a1`). Both were resolved as **TEST-UPDATED** on branch
`fix/p0-data-driven`; neither required a safety-hardware edit to
`elec/src/modules.ato` or `pcb/temper.kicad_pcb`. `dirty=true`: committed
alongside the uncommitted-at-write-time test edits it describes.

## P0 #1 — `fault_any_or` → `latch` set-path wiring

### Claim

`tests/validation/test_ucc21550_contract_pbt.py::test_schematic_keeps_fault_qualified_set_dominant_wiring`
asserts the connections `fault_or.Y2 ~ fault_any_or.A1`,
`rtd_hw_fault.line ~ fault_any_or.B1`, `fault_any_or.Y1 ~ latch.A1`,
`fault_any_or.Y1 ~ fault_any_or.A2`, `reset_n_in.line ~ fault_any_or.B2`,
`fault_any_or.Y2 ~ latch.A3` exist in `elec/src/modules.ato`, and the
dispatch claimed `grep fault_any_or elec/src/modules.ato` finds NOTHING.

### Data

- `git log --all --oneline -S 'fault_any_or' -- elec/src/modules.ato` shows 5
  commits; the most recent is `b3e055f9`
  ("feat(elec): add third fan-in package, wire UVL-02's fault into the SET
  path", 2026-07-27), which is an ancestor of `origin/main`.
- `grep fault_any_or elec/src/modules.ato` on `origin/main` (`4cdfd1a1`)
  finds **24 occurrences** — the dispatch's "finds NOTHING" claim is false
  for current main. `fault_any_or` is instantiated (line 3165) and wired
  (lines 3235–3238, 3246, 3305–3308).
- The one asserted connection that is genuinely absent is
  `fault_any_or.Y1 ~ latch.A1`. `git show b3e055f9 -- elec/src/modules.ato`
  shows that commit **deliberately replaced** it with the third-package
  chain: `fault_any_or.Y1 ~ fault_or3.A2 -> fault_or3.Y1 ~ fault_or3.B2 ->
  fault_or3.Y2 ~ latch.A1`, adding `fault_or3` (a third SN74HC4075DR) so
  UVL-02/OCP-02 had a SET-path fan-in (both existing packages were fully
  occupied). This is a **documented, deliberate redesign**, not an
  accidental merge drop:
  - commit message cites `docs/hardware/UVL02_DESIGN.md` SS7.1 and
    `docs/evidence/2026-07-27-fault-tree-capacity-expansion.md` (which at
    lines 42–43 states "`Y2` now drives `latch.A1`, replacing the previous
    direct `fault_any_or.Y1 ~ latch.A1` connection").
  - the removal (wire edit) happened in `b3e055f9`, before any of the
    2026-08-08 elec consolidation merges named in the dispatch
    (`c617e0d0`/`ef4355ee` OCP-02, `ebb8aff2`/`04411445` J_RTD1). Those
    merges only WIRED OCP-02 into the reserved `fault_or3.B1` input and
    added the J_RTD1 connector; `git show c617e0d0` confirms they did not
    drop the set path.
- The full safety chain is intact under the new name:
  `fault_or.Y2 -> fault_any_or.A1`, `rtd_hw_fault.line -> fault_any_or.B1`,
  `coil_thermal.fault.line -> fault_any_or.C1`,
  `fault_any_or.Y1 -> fault_or3.A2 -> fault_or3.Y1 -> fault_or3.B2 ->
  fault_or3.Y2 -> latch.A1`, `latch.Y1 ~ latch.A2`, `latch.Y3 ~ latch.B2`,
  `latch.Y2 ~ latch.B3`, `latch.Y2 -> shutdown/fault_status`,
  `reset_n_in.line -> fault_any_or.B2`, `fault_any_or.Y2 -> latch.A3`,
  `runaway_cut.line -> fault_or.C2`. Fault-qualified set-dominant latch
  behavior (the UCC21550 + RTD hardware safety contract the property tests
  exercise) is unchanged.

### Decision

**TEST-UPDATED.** The schematic wiring is the documented design; the test
was stale. Updated the test's `required_wiring` to the post-2026-07-27
topology (`fault_any_or.Y1 ~ fault_or3.A2`, `fault_or3.Y1 ~ fault_or3.B2`,
`fault_or3.Y2 ~ latch.A1`), citing the redesign in the docstring. No edit to
`elec/src/modules.ato`.

### Test result

`pytest tests/validation/test_ucc21550_contract_pbt.py` — 3 passed.

## P0 #2 — `test_r2_serialize_board.py` isolator refset / U3

### Claim

The serialized board's isolator refset no longer includes U3 (H11L1
mains-ZCD optocoupler), and the dispatch asserts a "quarantine deliberately
HELD BACK the ZCD/H11L1 deletion (2 commits `5842767c` + `300c4a70` on
`integration/2026-08-07-session-merge` were excluded from main as
contamination)", so main's board should still contain U3.

### Data

- `pcb/temper.kicad_pcb` **still contains U3**: line 7867
  `(property "Reference" "U3")`, line 7870
  `(property "Sheetpath" "power_in.zcd_opto")`, DIP-6 footprint with pads on
  nets `a`, `PWR_RTN`, `ZCD_ISO` (net 26), `gnd`, `+3V3`. The board did not
  lose U3.
- The dispatch's quarantine claim is **incorrect for main's actual state**:
  both `5842767c` ("fix(elec): delete U3 (H11L1 mains-ZCD optocoupler)...")
  and `300c4a70` ("fix(elec): drop ZCD_ISO from the split-board SELV
  interface contract") **are ancestors of `origin/main`**, merged in via the
  2026-08-08 15:05 worktree-agent merges (`fbbdf707`/`ed77e3f6`/...). The
  elec-side deletion DID land on main. What did NOT land is the board
  resync: `5842767c`'s file list (`elec/domain_manifest.yaml`,
  `elec/src/components.ato`, `elec/src/main.ato`, `elec/src/modules.ato`)
  contains no `pcb/*` edit, and the removal's own evidence doc
  (`docs/evidence/2026-07-30-zcd-optocoupler-removal.md`) states the board
  resync was explicitly deferred ("the resync step this task explicitly
  deferred").
- The isolator refset is derived, not hardcoded:
  `tools/wasm/r2_serialize_board.py::_isolator_component_refs` reads
  `elec/domain_manifest.yaml`'s `isolators:` list
  (`_isolator_instance_paths`) and matches each `instance_path` against the
  board's `Sheetpath` property. `power_in.zcd_opto` was removed from that
  list by `5842767c`, so U3 no longer resolves — even though the board
  still physically carries the part.
- The removal is **deliberate and documented**: no firmware consumer
  (`PIN_ZCD_INPUT` never read past its `#define`), no architectural role in
  this DC-bus resonant converter, not in the safety chain, and U3's
  8.560mm HV<->SELV pad separation permanently fails the 12.6mm PD3 target
  (see `docs/evidence/2026-07-30-zcd-optocoupler-removal.md` and the
  manifest comment at `elec/domain_manifest.yaml` lines 465–471).
- The test's hardcoded expectation `refs == {"C6","K1","K2","K3","PS1",
  "T1","U3","U7"}` was written in `a85e8c57` (2026-08-08) when the manifest
  still declared 8 resolvable isolators; it is stale relative to the
  post-deletion manifest. Actual refset: `{"C6","K1","K2","K3","PS1","T1",
  "U7"}` (7). `safety.ocp2.ct` (the OCP-02 CT, added to the manifest
  `isolators:` list 2026-08-07) likewise has no footprint on the
  un-resynced board yet, so it resolves to nothing.

### Decision

**TEST-UPDATED** (board untouched — it already contains U3, so there is
nothing to restore; the manifest removal is the documented design). Updated
the test's expected refset to the manifest-derived 7-component set and the
serializer docstring, with the removal evidence cited. Board resync
(removing U3 from `pcb/temper.kicad_pcb`) remains an open deferred step and
is flagged for a human below.

### Test result

`pytest scripts/tests/test_r2_serialize_board.py` — 27 passed.

## What needs a human

1. **Board resync / U3 (P0 #2).** `pcb/temper.kicad_pcb` still physically
   contains U3 + `ZCD_ISO` copper while the manifest/schematics no longer
   declare it. This is the documented deferred resync, but it is now an
   open inconsistency on main: the board and the design disagree until the
   resync lands. The 2026-08-08 worktree-agent merges carried the elec-side
   deletion in even though the dispatch believed a quarantine excluded it —
   if the quarantine was intended to hold the deletion entirely, main's
   elec side now carries a change that was supposed to be held back.
2. **`safety.ocp2.ct` (OCP-02 CT) not on the board.** Declared in the
   manifest's `isolators:` list but no footprint/sheetpath on the
   un-resynced board — resolves to nothing in the refset. Same deferred
   resync family as U3.
3. Nothing on P0 #1: set-path wiring is intact by design and now covered by
   the updated test.
