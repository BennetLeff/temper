# Handoff Actionables Integration - Implementation Plan

## U1. Land the measurement instrument

- **Goal:** Bring the pairwise HV↔SELV creepage script, tests, manifest entry, and evidence onto the current branch.
- **Source:** `feat/pairwise-creepage-tool` commits `5401a827f` and `3cd4fc4c6`.
- **Verification:** Run `scripts/tests/test_measure_cross_domain_creepage.py`; run manifest/invocation checks; inspect the script's default threshold against the current SSOT.

## U2. Remove the unused mains-ZCD crossing

- **Goal:** Apply the verified source deletion while retaining the CT/comparator ZVS path.
- **Source:** `fix/delete-zcd-optocoupler` commit `43082f16b`.
- **Conflict rule:** Retain the already-landed identical measurement script and resolve only the shared-file add; preserve the deletion's electrical and firmware changes.
- **Verification:** Rebuild the electrical source; inspect the netlist diff by stable instance path; verify no `PIN_ZCD_INPUT` consumer remains and the current-ZCD capture path remains present.

## U3. Reconcile source, netlist, and board

- **Goal:** Regenerate or update the board from the fresh electrical source without importing stale board edits wholesale.
- **Inputs:** Current `pcb/temper.kicad_pcb`, freshly built `elec/build/default.net`, and the documented board synchronization flow.
- **Verification:** Run copper-net consistency, refdes identity, safety, and KiCad DRC/provenance checks applicable to the resulting board. If a gate remains red, classify it as a source mismatch, board-generation limitation, or genuine safety regression.

## U4. Record standards status and close with evidence

- **Goal:** Add only the current edition metadata and provenance needed to prevent older clause readings from being treated as current requirements.
- **Verification:** Check the evidence note against the official IEC catalog URL and ensure no unsupported clause-level claim is introduced.

## Exit criteria

- Targeted measurement tests pass.
- Electrical source and netlist build succeed.
- Source/netlist/board identity checks pass, or a remaining blocker is explicitly recorded with the exact command and commit.
- No board-derived number is reported without fresh-input provenance.
- The worktree is clean apart from intentional commits, and the final status is reported.
