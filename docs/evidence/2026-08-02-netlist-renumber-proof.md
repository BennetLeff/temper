<!-- provenance: commit=f28a5944bc29479fccc5aa193f587f7076aacbb9 dirty=false -->

# Netlist-mutation corpus: wholesale-renumber proof

Base: plan `2026-08-02-021` (netlist↔board reconciliation & mutation, R16 +
R39), implemented in worktree `scratch-p1-netlist`, branch
`p1/netlist-reconciliation`, branched from `validation/p1-execution`
(`d3e99b153`). All numbers below were produced by actually running the
commands shown against the real `pcb/temper.kicad_pcb` and a freshly built
`elec/build/default.net` (`make netlist`, 2026-08-02) in that worktree.

## Summary (read this first)

**The wholesale-renumber class is proven to defeat the 95% refdes-overlap
check and to be caught by the sheetpath reconciliation oracle.** Injecting a
set-preserving ref permutation into a copy of the compiled design netlist
(seed 7, prefix `R`, all 78 resistors) leaves the refdes *set* byte-identical
-- so `preflight_identity`'s overlap check **PASSES** (it never looks at what
moved where, only whether the same names mostly still exist) -- while the
reconciliation oracle reports **78 RENUMBERED findings** (one per renumbered
instance path), and the preflight surface embedding the oracle fails. This is
the class the portfolio handoff named: "Match components by sheetpath, not
refdes" (docs/handoffs/2026-07-31-ci-enforcement-and-board-defects.md), and
the board `C27` = `tank.c_tank3` vs netlist `C27` = `ct_sense.c_filter`
incident is the same one-ref-two-components failure mode at the refdes-reuse
end of the spectrum.

## Method

1. Built the compiled netlist: `make netlist` (content-hash build stamp
   written by `scripts/write_build_stamp.py`).
2. Loaded it with `scripts/netlist_mutator.py::load_netlist` (which parses
   with `check_domain_partition.parse_netlist`, the canonical authority).
3. Applied `mutate_renumber(seed=7)`: a deterministic permutation of the
   numeric suffixes of the most-populated ref prefix (`R`, 79 components; 78
   of them actually renumbered -- the permutation is never the identity).
4. Wrote the mutated netlist with `write_netlist` and re-parsed it with the
   reconciliation oracle's own parser (strict `check_domain_partition`
   parsing also accepts it -- refs stay unique).
5. Ran the identity check set from the corpus runner
   (`scripts/check_netlist_mutation_corpus.py::evaluate_netlist`):
   - `preflight_identity(pcb/temper.kicad_pcb, mutated)` -- overlap leg;
   - `run_all_preflight_checks(board_path=..., design_netlist_path=...)` --
     preflight surface leg (embeds the reconciliation as `RECON_*` issues);
   - `reconcile(extract_board_netlist(pcb), parse_design_netlist(mutated))` --
     oracle leg.

## Verdicts

| Check | Verdict on the renumber-mutated netlist |
|---|---|
| `preflight_identity` (95% refdes-overlap) | **PASS** -- the refdes set is exactly preserved, so overlap is unchanged |
| `run_all_preflight_checks` (with oracle embedded) | **FAIL** -- `RECON_RENUMBERED` ERROR issues |
| Reconciliation oracle | **FAIL** -- 78 `RENUMBERED` findings |
| Anti-vacuity control (unmutated netlist) | every check **PASSES** |

## The exact permutation (seed 7, prefix R, old ref -> new ref -> instance path)

All 78 renumbered components; every other ref (C/K/Q/U/J/D/L prefixes,
non-prefix components) is untouched, and the refdes set as a whole is
identical before and after.

```
R33 -> R9  (ct_sense.r_bias_bot)          R32 -> R10  (ct_sense.r_bias_top)
R31 -> R49 (ct_sense.r_burden)            R15 -> R35  (discharge.r_coil1)
R16 -> R53 (discharge.r_coil2)            R11 -> R48  (discharge.r_dis1a)
R12 -> R38 (discharge.r_dis1b)            R13 -> R61  (discharge.r_dis2a)
R14 -> R65 (discharge.r_dis2b)            R17 -> R24  (discharge.r_gate)
R18 -> R52 (discharge.r_gate_pd)          R19 -> R31  (discharge.r_snub1)
R20 -> R39 (discharge.r_snub2)            R25 -> R50  (hb.gate_hs.r_filt_a)
R26 -> R19 (hb.gate_hs.r_filt_b)          R23 -> R44  (hb.gate_hs.rg_on)
R24 -> R28 (hb.gate_hs.rgs)               R27 -> R21  (hb.gate_ls.rg_on)
R28 -> R36 (hb.gate_ls.rgs)               R76 -> R71  (mcu.r_boot)
R75 -> R20 (mcu.r_en)                     R78 -> R15  (mcu.r_scl_pullup)
R77 -> R18 (mcu.r_sda_pullup)             R4  -> R78  (power_in.r_bleed1)
R5  -> R11 (power_in.r_bleed2)            R2  -> R63  (power_in.r_gate)
R3  -> R66 (power_in.r_gate_pd)           R1  -> R45  (power_in.r_relay_drop)
R8  -> R27 (power_in.r_zcd_bot)           R9  -> R47  (power_in.r_zcd_opto)
R10 -> R1  (power_in.r_zcd_pullup)        R6  -> R73  (power_in.r_zcd_top1)
R7  -> R2  (power_in.r_zcd_top2)          R22 -> R70  (power_mgmt.buck_3v3.r_fb_bot)
R21 -> R37 (power_mgmt.buck_3v3.r_fb_top) R39 -> R75  (rtd_pan.fb_power)
R46 -> R33 (rtd_pan.r_avdd_bottom)        R45 -> R77  (rtd_pan.r_avdd_top)
R37 -> R74 (rtd_pan.r_cs)                 R48 -> R67  (rtd_pan.r_fault_pullup)
R43 -> R69 (rtd_pan.r_high_bottom)        R42 -> R54  (rtd_pan.r_high_top)
R41 -> R8  (rtd_pan.r_low_bottom)         R40 -> R7   (rtd_pan.r_low_top)
R38 -> R30 (rtd_pan.r_miso)               R36 -> R25  (rtd_pan.r_mosi)
R47 -> R26 (rtd_pan.r_rail_ok_pullup)     R34 -> R5   (rtd_pan.r_ref)
R35 -> R3  (rtd_pan.r_sclk)               R44 -> R40  (rtd_pan.r_window_ok_pulldown)
R65 -> R14 (safety.coil_thermal.ntc)      R69 -> R6   (safety.coil_thermal.r_hyst)
R66 -> R23 (safety.coil_thermal.r_ntc_fixed) R68 -> R58 (safety.coil_thermal.r_ref_bot)
R67 -> R17 (safety.coil_thermal.r_ref_top) R50 -> R59 (safety.ocp.r_ref_bot)
R49 -> R64 (safety.ocp.r_ref_top)         R59 -> R22  (safety.ovp.r_adc_bot)
R56 -> R43 (safety.ovp.r_adc_top1)        R57 -> R72  (safety.ovp.r_adc_top2)
R58 -> R46 (safety.ovp.r_adc_top3)        R54 -> R60  (safety.ovp.r_div_bot)
R51 -> R79 (safety.ovp.r_div_top1)        R52 -> R32  (safety.ovp.r_div_top2)
R53 -> R56 (safety.ovp.r_div_top3)        R55 -> R62  (safety.ovp.r_hyst)
R60 -> R42 (safety.thermal.ntc)           R64 -> R41  (safety.thermal.r_hyst)
R61 -> R57 (safety.thermal.r_ntc_fixed)   R63 -> R76  (safety.thermal.r_ref_bot)
R62 -> R12 (safety.thermal.r_ref_top)     R71 -> R34  (safety.uvlo_logic.r_div_bot)
R70 -> R13 (safety.uvlo_logic.r_div_top)  R74 -> R51  (safety.uvlo_logic.r_fault_pullup)
R72 -> R68 (safety.uvlo_logic.r_hyst)     R73 -> R16  (safety.uvlo_logic.r_outa_pullup)
R30 -> R4  (tank.inductor_conn)           R79 -> R55  (thermal.r_fan_drop)
```

## Why this matters

Every earlier identity check in this repo compared refdes *sets*
(`preflight_identity`, 95% overlap). A set-preserving permutation is invisible
to any set comparison by construction -- the class cannot be caught by
raising or lowering a threshold. The reconciliation oracle keys identity by
the dotted atopile instance path (`tank.c_tank3`), which is derived from the
module-instantiation structure, not positional numbering, so it reports every
renumbered component by name. The corpus runner
(`scripts/check_netlist_mutation_corpus.py`) now asserts, on every run, that
this exact demonstration holds: the renumber class must produce RENUMBERED
findings while the overlap check passes -- so a future regression of either
half (oracle stops biting, or overlap check starts "catching" a permutation
it must not be trusted to catch) fails CI.

## Repro

```bash
make netlist
uv run --no-sync python scripts/check_netlist_mutation_corpus.py
uv run python scripts/check_netlist_board_reconciliation.py
uv run --no-sync python scripts/netlist_mutator.py --netlist elec/build/default.net \
    --mutate renumber --seed 7 --out /tmp/renumbered.net
```
