# Audit pass 6: contradiction register, last batch (2026-10-20)

Sources read this pass; PS = `zapote/power-stage-120v`, N = `PS/validation-results/08-manufacturing-package/native-21`.

| # | Verdict | Basis | Action taken |
|---|---|---|---|
| C8 laminate | **Two different questions, not a contradiction.** KB-6164 was named to settle CTI (DECISIONS 41; FAB-JLCPCB.md marks the earlier CTI question superseded). The open question (OPEN-ITEMS S12) is whether UL's KB-6164/6165 multilayer rows cover 61 µm (2 oz) inner copper; they list 35 and 54 µm, and the F-suffix rows list 102 µm. So "hard order condition" holds for CTI and the UL scope at 61 µm is still open | PS/OPEN-ITEMS.md S12; PS/FAB-JLCPCB.md:20-26 | None. Needs the owner's JLC question (PWR-06) |
| C11 FET soldering | **Not settled.** FAB-NOTE.md says JLC hand-solders some parts into 22.5 mm holes (L1 and another), and Q2/Q3/Q5/Q6 are consigned (84 shipped for 80 placements). I did not find the sentence that has JLC hand-solder the FETs on lead shoulders, nor the seat-before-solder fixture being applied to a JLC-built board | N/fab/FAB-NOTE.md:5-6, 67-68; PS/DECISIONS.md:473 | None. Ask whether FET seating is done by JLC or by the owner (PWR-15) |
| C17 ledger counts | **Different dates.** OPEN-ITEMS S21 gives 3 VERIFIED / 91 PARTIAL / 0 UNAUDITED / 0 VIOLATION (working tree, latest); S7 gives 3 / 32 / 58 UNAUDITED (SIGNAL) of 93 lines, from the s42-era commit. The committed ledger README (2/28/62) I could not read | PS/OPEN-ITEMS.md S7, S21 | None. S7 is history; the ledger files carry uncommitted edits from another lane, so I did not touch them |
| C26 mounting holes | **Board uses H1 and H3–H8; H2, H9, H10 stay empty.** DECISIONS 76 says FAB-NOTE's "H2–H7" were R43's numbers, not the board's | PS/DECISIONS.md:3013-3020; N/PROTOTYPE-LOT.md:115, 139 | Annotated PROTOTYPE-LOT.md:115 |
| C31 power-stage README | **Header is stale.** Its status line still says 240 × 160 mm and UCC21550. DECISIONS names 2EDR8259X (11 mentions), CA-IS3720HW, KLDR025, 290 × 190 and PS1 deleted | PS/README.md:3-5; PS/DECISIONS.md | Added a stale-header note; the body below it is not re-audited |
| C32 sink cut-off | **Different quantities.** Firmware hard trip is 95 °C (config.yaml); hardware sink comparators trip 98.3–104.6 °C (thermal_mgmt.h:152-159). The README's "about 120 °C" is from G4A ratings in an open question about the under-glass cutoff, not those trips | firmware/components/control/thermal_mgmt.h:152-159; PS/README.md:134 | None. Rename the README item so it is not read as the sink trip |
| C35 aux allowance | **Unresolved.** OPEN-ITEMS B11 gives 0.31 / 0.60 / 0.887 A (off / mid / full); firmware README gives 0.31 / 0.65 typical / 0.887. Mid and typical may be different duty points; I did not run `blower_aux.c` to find out | PS/OPEN-ITEMS.md B11; firmware/README.md:78-86; firmware/components/power/blower_aux.c | None. Evaluate the model at the mid duty and update whichever is wrong |
| C34 plan 09 | **Not found.** A search of the Markdown in this worktree finds no "not started" text for Plan 09 | n/a | None |
| C1, C30 | **Need a bench**: rated power; J1 terminal temperature | n/a | None |

## Documentation corrected in this pass (all in the power-stage worktree, explicit paths)
- PS/OPEN-ITEMS.md: s53 is the board of record; the three 18 A ceiling mentions now say 17.5 A (DECISIONS 61) supersedes.
- N/PROTOTYPE-LOT.md: J13 merge landed on `controller-j13-merge`; mounting-hole numbering.
- PS/DECISIONS.md: two BR1 gap-pad lines marked superseded by the 1.0 mm grade.
- PS/README.md: stale-header note.
- firmware/README.md: added RUNAWAY_FAULT (9 states).
- firmware/components/power/Kconfig: help text no longer says the source was never compiled.
- docs/hardware/TANK_COIL_SPECIFICATION.md line 59: names rows 1 and 7 as updated.
- output/temper-coil-r1/README.md line 253: the committed spec has the corrections.

## Not corrected
- R43 files (frozen): BOM PS3 part, UI controls, the certification questions' inlet-fuse lines. Fix when R44 opens.
- SR3 files (untracked in the main checkout): HANDOFF.md rim threshold and rim ADC. The folder is not on a branch.
- Controller worktree docs: ORDER.md R39 rotation and J4 drawing lines. They sit on branch `controller-j13-merge`, which I did not touch here.
- Anything in the datasheet-ledger or certifier files, which carry other lanes' uncommitted edits.
