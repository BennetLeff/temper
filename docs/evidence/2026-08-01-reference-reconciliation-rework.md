# Reference reconciliation rework on current main

<!-- provenance: commit=38e55f22c28af9806675f8ff26e8e034cb95cd8c dirty=false -->

<!-- Provenance note: the stamp cites 38e55f22c, the commit on the pushed
branch that authored this file (the pre-rebase local SHA cb6180c32 was
never pushed and does not resolve in a fresh clone; the Evidence
provenance gate requires a commit that persists). -->

**Date:** 2026-08-01
**Scope:** Rework of PR #498 commits `bab2a75aa` + `1162370f2` onto current
main (origin/main @ `27a3ffd8b`). Board-dependent intents are deferred to the
board workstream; this change is placer machinery + source-backed manifest
data only.

## Reference result

`packages/temper-placer/configs/temper_constraints.references.yaml` is the
source-backed map consumed before direct CP-SAT or place→route solving. It
uses production-board `Sheetpath` identity. Only aliases whose targets are
live parsed component references are enabled; live designator collisions and
missing source instances remain explicitly unresolved, so the existing
fail-closed validator stops before a placement candidate is generated.

Verified against the current board (post-#517 re-solve and K2 relay swap,
169 components): all 18 alias targets are present, no alias source is a live
designator, and the documented unresolved names (`J_AC_IN`, `J_COIL`,
`J_DEBUG`, `U_LDO_3V3`, …) are still absent.

**The alias data was re-derived, not carried over.** The #498 branch's
manifest (measured 2026-07-30) predates main's board resync and is stale for
eight identities: the board's KiCad sheetpaths map `hb.gate_hs.driver` →
`U7` (branch said U6), `hb.gate_hs.boot_diode` → `U8` (U7), `rtd_pan.adc` →
`U9` (U8), `mcu.mcu` → `U27` (U26), `power_mgmt.buck_3v3.buck` → `U4` (U3),
`hb.gate_hs.rg_on` → `R23` (R18), `hb.gate_ls.rg_on` → `R27` (R22),
`ct_sense.r_burden` → `R31` (R25). Every target in the committed manifest was
re-checked against `pcb/temper.kicad_pcb` sheetpaths on 2026-08-01; the
decoupler/CT-filter entries (`C_CT_FILT`→`C28`, `C_MCU_1`→`C38`,
`C_MCU_2`→`C39`) were re-confirmed against `ct_sense.c_filter` and
`mcu.c_vcc1/c_vcc2` respectively.

With the manifest applied, the production default config's fail-closed
validation surface drops from 13 to 6 unresolved constraints, all of them
connector-identity constraints (`J_AC_IN`/`J_COIL`/`J_DEBUG`) that cannot be
reconciled until the source model gains those connector instances. The
legacy conceptual `Q1`/`Q2`/`D1`/`D2` names are deliberately NOT aliased:
they are live designators for different source instances on the production
board (`Q1`=`power_in.q_relay_drv`, `Q2`=`discharge.q_dis_drv`,
`D1`=`power_in.d_flyback`, `D2`=`power_in.d_zcd_clamp`), and the half-bridge
switches the config means by them are `U5`/`U6` — aliasing them would
silently change design intent.

## Fail-closed invariant

A deliberately broken alias target (`tests/io/test_reference_aliases.py`),
a self-alias, and an alias to a missing name
(`tests/placer/cp_sat/test_encoder.py::test_alias_to_missing_target_stays_unresolved`)
all fail closed. Property tests (`tests/placer/cp_sat/test_reconciliation_pbt.py`)
pin idempotence, canonical completeness, monotone unresolved-set improvement,
and loop canonicalization over 200 hypothesis examples. The place→route loop
forwarding path is pinned by
`test_loop.py::test_call_solver_forwards_reference_aliases`.

## What was dropped from #498 (with reason)

- **Container digest pin + kicad-cli version recording** (`placer-regression.yml`,
  part of `1162370f2`): DRC-baseline reproducibility is owned by the board
  workstream's ceiling protocol (AGENTS.md DRC section). Re-pinning should be
  a deliberate, separate change tied to the next ceiling remeasurement, not a
  bundled side-effect of a placer feature.
- **Bounded placement objective** (`ebf41c198`): already landed on main in
  evolved form — `add_displacement_objective` gained `max_units` and
  `solve_placement` gained the `max_displacement_mm` guard. Superseded.
- **Board / schematic / DRC-ceiling reconciliation** (`70b843428`,
  `34cc604c9`, `a8bbaca08`): deferred to the board workstream. The U3/ZCD
  deletion is not on main; the board, schematics, `drc_ceiling.json`, and the
  `test_clearance_copper.py` intra-blocker set all describe that
  not-yet-landed board state.
- **Evidence provenance repointing** (`c1e89f06e`): already done on main by
  the #513 provenance repoint — the exact target SHAs are present in main's
  copies of the same files.
- **Duplicate mypy annotation fix** (`5a6582402`): the duplicate only existed
  because of the branch's CLI wiring; the rework writes that wiring without
  the duplicate annotation.

## Remaining blockers

The isolation keepout remains a hardware-layout blocker: the current board
has no `MAINS_SELV_ISOLATION_BARRIER` zone and its HV/SELV footprints are
interleaved. The six remaining unresolved constraints are all
connector-identity gaps (`J_AC_IN`, `J_COIL`, `J_DEBUG`) that need
source-model connector instances before their constraints can be enabled.
Neither is a validator weakening.
