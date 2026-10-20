# Audit pass 1: the contradiction register (2026-10-19)

Scope: the 35 entries in `CHECKLIST.md` "Contradiction register". Verdicts below were checked against the cited source line in this pass, or are marked "not re-checked". No source document was edited; the doc fixes listed are for a later commit, because several of those files have uncommitted edits from other lanes.

Paths: PS = `zapote/power-stage-120v`, FW = `firmware`, CJ = controller worktree `zapote/controller`.

## Settled from the repo (verified this pass)

| # | Verdict | Basis | Fix still to make |
|---|---|---|---|
| C3 | Stud is M4. "M6" is review item M6 (coil-stud spacing). | PS/DECISIONS.md:242 (M6 = spacing), :1365 (Würth 7466004R, M4) | Already corrected in `output/temper-coil-r1/HOT-LIMITS.md` (4d07e3a18) |
| C7 | Board of record is s53. | PS/DECISIONS.md:2972 (item 75). PS/OPEN-ITEMS.md:3 still says s51 (board 0b0ebcf7) | Update OPEN-ITEMS.md:3 and PS/README.md:3 |
| C12 | PS3 is MPM-65-15ST. | PS/DECISIONS.md:1504 records the swap "IRM-60-15ST → MPM-65-15ST" | R43 BOM line 206 and CJ/README.md:135 still say IRM-60-15ST. The R43 BOM is in the main checkout, not this worktree: not re-read |
| C33 | The firmware has 9 states. | FW/main/state_machine.h:30-39 lists INIT, IDLE, PAN_DET, PREHEAT, HEATING, NO_PAN, COOLDOWN, FAULT, RUNAWAY_FAULT | FW/README.md:9-20 says 8 |
| C6 | The release ceiling is 17.5 A. | PS/DECISIONS.md item 61: "the release tank ceiling drops 18 → 17.5 A (2026-10-15; adopted)". OPEN-ITEMS S2 quotes a different quantity (gated still-air ceiling 18.3 A at 61 °C), so some of its 18 A mentions may be that, not a stale release ceiling | Reword OPEN-ITEMS lines 25, 105, 112 so each says which ceiling it means. Lines 105 and 112 not re-read |

## Real, and not a documentation fix

| # | What is wrong | Basis | Needed |
|---|---|---|---|
| C4 / C5 | This branch's MAX31865 driver uses the AUTOMATIC fault cycle (`MAX31865_CONFIG_FAULT_CYCLE_AUTOMATIC`, max31865.h:34 and the comment at :48) and the older threshold words. The controller decisions (C37, C46) require the manual cycle with ≥ 5.5 ms steps and words 35544/12844. | max31865.h read this pass; CJ/DECISIONS.md:544-545 and 669-685 cited by the checklist, not re-read | Port the origin/main fix onto this branch (or merge), then re-run the host tests. A firmware code change: needs the owner's go-ahead on which branch carries it, since three firmware lines exist |
| C2 | Insulated lugs are required by PS/DECISIONS.md:245 ("why not bare lugs": at 15 mm stud spacing the lugs can be turned into contact), but the coil study specifies non-insulated lugs. | PS/DECISIONS.md:245 read this pass | Change the coil study (BUILD-AND-MEASURE.md:70, ORDER-LIST.md:60) to insulated, high-temperature lugs. This makes the PTFE lug (50840 or equal) the right class of part, and the sleeve-only route a fallback only |

## Cosmetic, source says one thing

| # | Verdict | Basis |
|---|---|---|
| C20 | R39 CPL rotation is 0 in the shipped CPL (CJ/fab/cpl-jlcpcb.csv line 158). ORDER.md:85 says 180. R39 is set do-not-place at JLC, so no assembled part is affected. Fix ORDER.md. | CPL read this pass |

## Not settled by the repo (need a decision, a measurement, or a source not read)

| # | Needs |
|---|---|
| C1 rated power | Bench power runs (TST-09). Until then no nameplate figure. Old 1800 W doc should be marked superseded |
| C8 laminate | Answer from JLC on the 61 µm inner-copper UL row (OI/JLC-LAMINATE-QUESTION.md): owner-only outreach |
| C9 BR1 gap pad (0.5 vs 1.0 mm), C10 clamp force | A single recorded decision; changes stack height, so it affects the sink drawing. Not re-checked |
| C11 FET soldering | Owner decision with JLC about seat-before-solder |
| C13, C14, C15, C16, C17, C18, C19, C21–C27, C28–C32, C34, C35 | Not re-checked in this pass. Rows are as the checklist author cited them |
| C30 J1 temperature | Measure with a real cord |

## Next pass
Re-check C9, C10, C13, C16, C17 and C21–C25 against source, then sample the DONE rows in the checklist (50 rows) for whether their evidence is a decision, a simulation or a measurement.
