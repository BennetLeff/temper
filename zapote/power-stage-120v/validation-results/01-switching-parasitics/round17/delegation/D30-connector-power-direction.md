# D-30: central board connector supply direction — fix and a validator for the class

**Read [README.md](README.md) first (ground rules, board facts).**
This brief **changes board source** (the round-5 central supervisor board),
regenerates it, and adds a validator; open a draft PR.

## Why it matters

The round-6 investigation (`prototype-closure/round6-investigation/circuit-review.md`,
row P2) found in `prototype-closure/round5/boards/central/generated/pins.tsv`
(lines 1129–1130) that J9/JCTRL pin 1 `CTRL_3V3` and pin 2 `CTRL_GND` are
typed `power_out`, yet nothing on the central board drives `CTRL_3V3`: it
**receives** the controller's supply and feeds the controller side of the
isolators (U98–U105, U107). A `power_out` label on an incoming rail hides
exactly the error ERC exists to catch (an undriven or doubly-driven rail),
because every power net then looks driven. It is a metadata defect, not a
demonstrated copper short.

## Task

1. **Fix the source**, not the generated table: find where J9's pin types
   come from (the round-5 board generator / source for `boards/central`), make
   J9.1 `power_in` and J9.2 the correct return type, regenerate, and rerun the
   board's existing checks (ERC/DRC, XML/netlist parity) exactly as round 5 did.
   Report the before/after ERC.
2. **Audit the same class everywhere in `prototype-closure/round5/boards/`**
   (central, the six voltage boards, the two CT burden boards): every
   connector pin typed `power_out` or `output` whose net has no on-board
   source (regulator output, supply, driver), and every `power_in` net with no
   source anywhere in the joined harness. List each with file:line.
3. **Validator:** add a script (Python with tests, or Rust compiled with plain
   `rustc` like the round-5 model tools) that reads the generated pin tables and
   fails when a connector pin is a power/output type on a net with no on-board
   source, or when a board-to-board harness joins two `power_out` pins on one
   net. Include negative tests (the J9 case, a doubly-driven rail) and run it
   over all nine boards. Wire it into the board package's existing check
   script if one exists.
4. Fix any further instances found by step 2 the same way, or list them for
   the owner if the correct direction is unclear (do not guess).

## Rules specific to this brief

- Change only the round-5 board sources/generated outputs for the affected
  pins, the new validator and its tests. Never edit `pcb/temper.kicad_pcb` or
  `elec/` at the repository root, the power-stage `native-*` boards or
  `frozen/`.
- Do not build the Rust workspace or the native bridge.
- One worktree on `codex/power-stage-120v-build`; do **not** work in the
  `mit-product-guidance` worktree (integrated in #1647; power-stage writes there
  are frozen).

## Deliverable

Draft PR against `codex/power-stage-120v-build`: the fix, regenerated
outputs, before/after ERC, the class audit table, the validator with tests
and its run over all boards, and `round17/delegation/out-D30/README.md`.
